import datetime
from typing import Annotated, Literal

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field, model_validator

from api.deps import Cursor
from api.errors import NOT_FOUND
from api.routes.estimates import Currency, Rooms, Travelers, check_rooms, require_known_origin
from app.queries import DATE_GRID_DAYS, HOTEL_TIERS, get_date_grid, get_destination, list_active_destinations
from app.search import display_currency_and_rate
from app.trip import trip_options
from etl.common.currency import from_usd

router = APIRouter()


class Destination(BaseModel):
    destination_id: int
    city_name: str
    country_name: str
    city_name_he: str | None = Field(description="Hebrew name; null when the seed has none (show city_name)")
    country_name_he: str | None = Field(description="Hebrew name; null when the seed has none (show country_name)")
    iata_code: str


# Every destination a search covers - for picking one in the search form.
@router.get("/destinations")
def destinations(cur: Cursor) -> list[Destination]:
    return [Destination.model_validate(row) for row in list_active_destinations(cur)]


class TripParams(BaseModel):
    depart_date: datetime.date
    return_date: datetime.date
    origin_iata: str = "TLV"
    currency: Currency = "ILS"
    travelers: Travelers = 1
    rooms: Rooms = 1


class TripQuery(TripParams):
    @model_validator(mode="after")
    def return_after_depart(self):
        if self.return_date <= self.depart_date:
            raise ValueError("return_date must be after depart_date")
        check_rooms(self.travelers, self.rooms)
        return self


# A date grid's middle pair isn't a trip: moving the grid can center it on a
# return before the departure, and the grid still has whole rows of real
# trips. It only needs one - a return after a departure - somewhere in it.
class GridQuery(TripParams):
    @model_validator(mode="after")
    def window_has_a_trip(self):
        latest_return = self.return_date + datetime.timedelta(days=DATE_GRID_DAYS)
        earliest_depart = self.depart_date - datetime.timedelta(days=DATE_GRID_DAYS)
        if latest_return <= earliest_depart:
            raise ValueError("no return in this grid comes after a departure in it")
        check_rooms(self.travelers, self.rooms)
        return self


class FlightOption(BaseModel):
    depart_date: datetime.date
    return_date: datetime.date
    airline_code: str | None
    airline_name: str | None
    flight_number: str | None
    depart_time: datetime.time | None = Field(description="Local time at the departure airport")
    return_time: datetime.time | None = Field(description="Local time at the return flight's airport")
    outbound_stops: int | None
    return_stops: int | None = Field(description="null when the option comes from collected data")
    outbound_minutes: int | None = Field(description="null when the option comes from collected data")
    return_minutes: int | None = Field(description="null when the option comes from collected data")
    price_amount: float = Field(description="One traveler's round trip, without checked baggage")
    price_seen_on: datetime.date | None = Field(
        description="The day a real Aviasales search saw this price; null when a live answer didn't say"
    )
    booking_url: str | None = Field(description="Search for this flight on Aviasales; null for collected data")


class HotelTierPrice(BaseModel):
    per_night_amount: float = Field(description="One room, one night")
    total_amount: float = Field(description="Every room, every night")


class Hotel(BaseModel):
    nights: int = Field(description="Nights of the flight found, which may differ from the request")
    rooms: int
    price_age_days: int | None = Field(description="Days since the hotel prices were collected")
    budget: HotelTierPrice | None = Field(description="null when this tier has no price on file")
    average: HotelTierPrice | None
    luxury: HotelTierPrice | None


class Trip(BaseModel):
    destination: Destination
    currency: str = Field(description="Every amount is in this currency: the one requested, or USD if it has no rate")
    source: Literal["live", "collected"] | None = Field(
        description="live: asked for these exact dates just now. collected: from data collected earlier,"
        " on the nearest dates. null: no flights either way"
    )
    live_status: Literal["found", "empty", "failed", "off"] = Field(
        description="What the live search did: found options; answered with none for these exact dates"
        " (the common case - its cache only has dates people searched); failed; or is switched off"
    )
    flight_out_date: datetime.date | None
    flight_return_date: datetime.date | None
    exact_dates: bool = Field(description="Whether the flights are for exactly the requested dates")
    flights: list[FlightOption] = Field(description="Cheapest first")
    hotel: Hotel


# All flight options for one destination on the requested dates, with its
# hotel prices. Tries Travelpayouts live first; if that fails or has
# nothing, falls back to the collected data (see app/trip.py).
@router.get("/destinations/{destination_id}/trip", responses=NOT_FOUND)
def destination_trip(destination_id: int, query: Annotated[TripQuery, Query()], cur: Cursor) -> Trip:
    destination = known_destination(cur, destination_id, query.origin_iata)
    trip = trip_options(cur, query.origin_iata, destination, query.depart_date, query.return_date)
    currency, usd_per_unit = display_currency_and_rate(cur, query.currency)

    def amount(usd):
        return from_usd(usd, usd_per_unit)

    def tier_price(per_night_usd):
        if per_night_usd is None:
            return None
        return HotelTierPrice(
            per_night_amount=amount(per_night_usd),
            total_amount=amount(float(per_night_usd) * trip.hotel_nights * query.rooms),
        )

    return Trip(
        destination=Destination.model_validate(destination),
        currency=currency,
        source=trip.source,
        live_status=trip.live_status,
        flight_out_date=trip.depart_date,
        flight_return_date=trip.return_date,
        exact_dates=trip.depart_date == query.depart_date and trip.return_date == query.return_date,
        flights=[FlightOption.model_validate({**f, "price_amount": amount(f["price_usd"])}) for f in trip.flights],
        hotel=Hotel(
            nights=trip.hotel_nights,
            rooms=query.rooms,
            price_age_days=destination["hotel_price_age_days"],
            **{tier: tier_price(per_night) for tier, per_night in trip.hotel_per_night_usd.items()},
        ),
    )


class TierTotals(BaseModel):
    budget: float | None
    average: float | None
    luxury: float | None


class DateGridCell(BaseModel):
    depart_date: datetime.date
    return_date: datetime.date
    nights: int
    flight_amount: float = Field(description="One traveler's cheapest round trip on file for these exact dates")
    total_amount: TierTotals = Field(
        description="Every traveler's flight + every room for these nights, per hotel tier;"
        " null when the tier has no hotel price"
    )


class DateGrid(BaseModel):
    currency: str = Field(description="Every amount is in this currency: the one requested, or USD if it has no rate")
    days: int = Field(description="The grid spans this many days either side of the requested dates")
    cells: list[DateGridCell] = Field(
        description="Only the date pairs with a flight on file - an absent pair is missing data"
    )


# Collected prices for every date pair near the requested one, so a flexible
# traveler can see which dates are cheaper. Collected data only - no live
# call, which would be one per cell.
@router.get("/destinations/{destination_id}/date-grid", responses=NOT_FOUND)
def destination_date_grid(destination_id: int, query: Annotated[GridQuery, Query()], cur: Cursor) -> DateGrid:
    destination = known_destination(cur, destination_id, query.origin_iata)
    currency, usd_per_unit = display_currency_and_rate(cur, query.currency)

    cells = []
    for row in get_date_grid(cur, query.origin_iata, destination_id, query.depart_date, query.return_date):
        nights = (row["return_date"] - row["depart_date"]).days
        flight_usd = float(row["flight_price_usd"])
        totals = {}
        for tier in HOTEL_TIERS:
            per_night = destination[f"hotel_{tier}_per_night_usd"]
            if per_night is None:
                totals[tier] = None
            else:
                party_usd = flight_usd * query.travelers + float(per_night) * nights * query.rooms
                totals[tier] = from_usd(party_usd, usd_per_unit)
        cells.append(
            DateGridCell(
                depart_date=row["depart_date"],
                return_date=row["return_date"],
                nights=nights,
                flight_amount=from_usd(flight_usd, usd_per_unit),
                total_amount=TierTotals(**totals),
            )
        )
    return DateGrid(currency=currency, days=DATE_GRID_DAYS, cells=cells)


# The active destination, after checking the origin; a 404 when there's no
# such active destination.
def known_destination(cur, destination_id, origin_iata):
    require_known_origin(cur, origin_iata, location="query")
    destination = get_destination(cur, destination_id)
    if destination is None:
        raise HTTPException(status_code=404, detail="Destination not found")
    return destination

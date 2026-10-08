import datetime
from typing import Annotated, Literal

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field, model_validator

from api.deps import Cursor
from api.routes.estimates import Currency, require_known_origin
from app.queries import get_destination, list_active_destinations
from app.search import display_currency_and_rate
from app.trip import trip_options
from etl.common.currency import from_usd

router = APIRouter()


class Destination(BaseModel):
    destination_id: int
    city_name: str
    country_name: str
    iata_code: str


# Every destination a search covers - for picking one in the search form.
@router.get("/destinations")
def destinations(cur: Cursor) -> list[Destination]:
    return [Destination.model_validate(row) for row in list_active_destinations(cur)]


class TripQuery(BaseModel):
    depart_date: datetime.date
    return_date: datetime.date
    origin_iata: str = "TLV"
    currency: Currency = "ILS"

    @model_validator(mode="after")
    def return_after_depart(self):
        if self.return_date <= self.depart_date:
            raise ValueError("return_date must be after depart_date")
        return self


class FlightOption(BaseModel):
    airline_code: str | None
    airline_name: str | None
    flight_number: str | None
    depart_time: datetime.time | None = Field(description="Local time at the departure airport")
    return_time: datetime.time | None = Field(description="Local time at the return flight's airport")
    outbound_stops: int | None
    return_stops: int | None = Field(description="null when the option comes from collected data")
    outbound_minutes: int | None = Field(description="null when the option comes from collected data")
    return_minutes: int | None = Field(description="null when the option comes from collected data")
    price_amount: float = Field(description="Round trip, without checked baggage")
    price_seen_on: datetime.date | None = Field(
        description="The day a real Aviasales search saw this price; null for prices collected before it was recorded"
    )
    booking_url: str | None = Field(description="Search for this flight on Aviasales; null for collected data")


class HotelTierPrice(BaseModel):
    per_night_amount: float
    total_amount: float


class Hotel(BaseModel):
    nights: int = Field(description="Nights of the flight found, which may differ from the request")
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
    flight_out_date: datetime.date | None
    flight_return_date: datetime.date | None
    exact_dates: bool = Field(description="Whether the flights are for exactly the requested dates")
    flights: list[FlightOption] = Field(description="Cheapest first")
    hotel: Hotel


# All flight options for one destination on the requested dates, with its
# hotel prices. Tries Travelpayouts live first; if that fails or has
# nothing, falls back to the collected data (see app/trip.py).
@router.get("/destinations/{destination_id}/trip")
def destination_trip(destination_id: int, query: Annotated[TripQuery, Query()], cur: Cursor) -> Trip:
    require_known_origin(cur, query.origin_iata, location="query")
    destination = get_destination(cur, destination_id)
    if destination is None:
        raise HTTPException(status_code=404, detail="Destination not found")

    trip = trip_options(cur, query.origin_iata, destination, query.depart_date, query.return_date)
    currency, usd_per_unit = display_currency_and_rate(cur, query.currency)

    def amount(usd):
        return from_usd(usd, usd_per_unit)

    def tier_price(per_night_usd):
        if per_night_usd is None:
            return None
        return HotelTierPrice(
            per_night_amount=amount(per_night_usd), total_amount=amount(float(per_night_usd) * trip.hotel_nights)
        )

    return Trip(
        destination=Destination.model_validate(destination),
        currency=currency,
        source=trip.source,
        flight_out_date=trip.depart_date,
        flight_return_date=trip.return_date,
        exact_dates=trip.depart_date == query.depart_date and trip.return_date == query.return_date,
        flights=[FlightOption.model_validate({**f, "price_amount": amount(f["price_usd"])}) for f in trip.flights],
        hotel=Hotel(
            nights=trip.hotel_nights,
            price_age_days=destination["hotel_price_age_days"],
            **{tier: tier_price(per_night) for tier, per_night in trip.hotel_per_night_usd.items()},
        ),
    )

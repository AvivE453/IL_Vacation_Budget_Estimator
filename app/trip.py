# A destination view: every flight option for one destination on the
# requested dates - live when Travelpayouts answers (and then stored as
# observations, source 'live_search'), otherwise from the collected data -
# plus that city's hotel prices. All amounts in USD.

import datetime
from dataclasses import dataclass

from app import live_flights
from app.live_flights import fetch_live_flight_options
from app.queries import (
    HOTEL_TIERS,
    get_airline_names,
    get_collected_flight_options,
    insert_live_flight_observations,
)


@dataclass
class TripOptions:
    source: str | None  # "live", "collected", or None when neither had flights
    # What the live search did: "found" options, answered "empty", "failed",
    # or was switched "off" (LIVE_FLIGHT_SEARCH=off).
    live_status: str
    depart_date: datetime.date | None
    return_date: datetime.date | None
    flights: list[dict]
    hotel_nights: int
    hotel_per_night_usd: dict[str, float | None]


def trip_options(cur, origin_iata, destination, depart_date, return_date):
    source, live_status, flights = _live_or_collected(cur, origin_iata, destination, depart_date, return_date)
    if flights:
        depart_date, return_date = flights[0]["depart_date"], flights[0]["return_date"]
    # Hotel nights follow the flight that was found, as in estimate_all_destinations.
    nights = (return_date - depart_date).days
    return TripOptions(
        source=source,
        live_status=live_status,
        depart_date=depart_date if flights else None,
        return_date=return_date if flights else None,
        flights=flights,
        hotel_nights=nights,
        hotel_per_night_usd={tier: destination[f"hotel_{tier}_per_night_usd"] for tier in HOTEL_TIERS},
    )


def _live_or_collected(cur, origin_iata, destination, depart_date, return_date):
    live = fetch_live_flight_options(origin_iata, destination["iata_code"], depart_date, return_date)
    if live is None:
        live_status = "failed" if live_flights.LIVE_FLIGHT_SEARCH else "off"
    else:
        live_status = "found" if live else "empty"
    if live:
        # Every option for the exact dates, where the collector gets only the
        # cheapest per date pair - kept for later estimates and fallbacks.
        insert_live_flight_observations(
            cur, destination["destination_id"], origin_iata, destination["iata_code"], live
        )
        names = get_airline_names(cur, {o["airline_code"] for o in live if o["airline_code"]})
        return "live", live_status, [{**o, "airline_name": names.get(o["airline_code"])} for o in live]

    collected = get_collected_flight_options(cur, origin_iata, destination["destination_id"], depart_date, return_date)
    if collected:
        return "collected", live_status, [_from_collected(row) for row in collected]
    return None, live_status, []


# The collector keeps only part of what the live call returns; the rest is None.
def _from_collected(row):
    return {
        "depart_date": row["depart_date"],
        "return_date": row["return_date"],
        "depart_time": row["depart_time"],
        "return_time": row["return_time"],
        "airline_code": row["airline_code"],
        "airline_name": row["airline_name"],
        "flight_number": None,
        "outbound_stops": row["number_of_stops"],
        "return_stops": None,
        "outbound_minutes": None,
        "return_minutes": None,
        "price_usd": float(row["price_amount_usd"]),
        "price_seen_on": row["price_seen_on"],
        "booking_url": None,
    }

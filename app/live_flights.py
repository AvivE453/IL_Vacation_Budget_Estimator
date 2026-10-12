# Live flight options for one exact date pair, fetched while a user waits.
#
# Same Travelpayouts endpoint as the collector, but asked for exact days
# rather than a month: a month query returns only the cheapest round trip per
# date pair, an exact one returns every option for the pair (verified
# 2026-10-08: 12 options TLV-BCN, direct flights included).
#
# Unlike the collector, nothing here waits or retries: a user can't sit
# through the collector's up-to-60s wait after a 429, so any failure returns
# None and the caller falls back to the collected data.

import datetime
import logging

import requests

from etl.collectors.flights_collector import PRICES_URL, RESULTS_PER_CALL, price_seen_on
from etl.common.config import LIVE_FLIGHT_SEARCH, TRAVELPAYOUTS_MARKER, TRAVELPAYOUTS_TOKEN

LIVE_TIMEOUT_SECONDS = 5
# The API returns each option's search link as a path on this site.
AVIASALES_URL = "https://www.aviasales.com"

logger = logging.getLogger(__name__)


# The options for exactly these dates, cheapest first, or None if the call
# failed (or live search is switched off). An empty list means the API
# answered but had nothing cached.
def fetch_live_flight_options(origin_iata, destination_iata, depart_date, return_date):
    if not LIVE_FLIGHT_SEARCH:
        return None
    try:
        response = requests.get(
            PRICES_URL,
            params={
                "origin": origin_iata,
                "destination": destination_iata,
                "departure_at": depart_date.isoformat(),
                "return_at": return_date.isoformat(),
                "currency": "usd",
                "sorting": "price",
                "limit": RESULTS_PER_CALL,
                "token": TRAVELPAYOUTS_TOKEN,
                "marker": TRAVELPAYOUTS_MARKER,
            },
            timeout=LIVE_TIMEOUT_SECONDS,
        )
        response.raise_for_status()
        # Parsed inside the try: one malformed result means the answer can't
        # be trusted, which is a fallback, not a 500.
        options = [_parse(r) for r in response.json()["data"]]
    except (requests.RequestException, ValueError, KeyError, TypeError) as e:
        logger.warning("live flight search %s->%s failed: %s", origin_iata, destination_iata, e)
        return None

    # It's an outside answer to an exact-date question: drop anything for
    # other dates rather than show it as an exact match.
    return [o for o in options if (o["depart_date"], o["return_date"]) == (depart_date, return_date)]


def _parse(result):
    price = float(result["price"])
    # Options are stored, and flight_price_observations requires a positive price.
    if price <= 0:
        raise ValueError(f"non-positive price {price}")
    departure_at = datetime.datetime.fromisoformat(result["departure_at"])
    return_at = datetime.datetime.fromisoformat(result["return_at"])
    link = result.get("link")
    return {
        "depart_date": departure_at.date(),
        "return_date": return_at.date(),
        # Local wall-clock time at each airport, like the collector stores.
        "depart_time": departure_at.time().replace(tzinfo=None),
        "return_time": return_at.time().replace(tzinfo=None),
        "airline_code": result.get("airline"),
        # Seen as a string ("6404"); str() in case it ever comes as a number.
        "flight_number": str(result["flight_number"]) if result.get("flight_number") is not None else None,
        "outbound_stops": result.get("transfers"),
        "return_stops": result.get("return_transfers"),
        "outbound_minutes": result.get("duration_to"),
        "return_minutes": result.get("duration_back"),
        "price_usd": price,
        "price_seen_on": price_seen_on(link),
        "booking_url": AVIASALES_URL + link if link else None,
    }

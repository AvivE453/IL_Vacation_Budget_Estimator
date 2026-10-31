# Daily collector: pulls round-trip fares for each active destination from
# Travelpayouts' v3/prices_for_dates endpoint and inserts a snapshot row into
# flight_price_observations. Never upserts on route+date - every run adds the
# prices it hasn't stored yet, so the price history is kept.
#
# Each API result is a complete round trip: (one combined price) ,
# correctly-ordered departure_at/return_at, and a real airline code + flight number.
#
# Run with: uv run python -m etl.collectors.flights_collector

import datetime
from urllib.parse import parse_qs, urlparse

import psycopg2.extras
import requests
from tenacity import retry, retry_if_exception, stop_after_attempt, wait_exponential

from etl.common.config import TRAVELPAYOUTS_MARKER, TRAVELPAYOUTS_TOKEN
from etl.common.db import get_conn

PRICES_URL = "https://api.travelpayouts.com/aviasales/v3/prices_for_dates"

ORIGIN_IATA = "TLV"

# prices_for_dates takes a calendar month (YYYY-MM), not a specific day, for
# each of departure_at/return_at, and returns whatever real round trips are
# cached within them. This month and the next six, with no gaps, so a trip
# planned half a year ahead is covered as well as next month's.
MONTH_OFFSETS = range(7)

# Each result is a full round trip, so this bounds observations per call.
# 1000 is the API's maximum. It used to be 40, which silently dropped most of
# the cache: a single destination/month has returned up to ~270 round trips.
RESULTS_PER_CALL = 1000

# Travelpayouts allows 600 requests per minute (X-Rate-Limit: 600, verified
# from real response headers - not the 200/hour older docs claimed).
DEFAULT_RATE_LIMIT_RESET_SECONDS = 60
backoff_on_other_errors = wait_exponential(multiplier=1, min=1, max=10)


# A 429 says exactly when the rate-limit window resets (X-Rate-Limit-Reset,
# in seconds), so wait that long instead of a short backoff that would just
# hit the limit again. Anything else backs off exponentially.
def wait_before_retry(retry_state):
    error = retry_state.outcome.exception()
    if isinstance(error, requests.HTTPError) and error.response.status_code == 429:
        return int(error.response.headers.get("X-Rate-Limit-Reset", DEFAULT_RATE_LIMIT_RESET_SECONDS))
    return backoff_on_other_errors(retry_state)


# Only errors the next attempt could get past: the rate-limit window resets,
# the server recovers, the network comes back. Anything else, like a 401 for a
# bad token, would fail the same way every time.
def is_worth_retrying(error):
    if isinstance(error, requests.HTTPError):
        return error.response.status_code == 429 or error.response.status_code >= 500
    return isinstance(error, (requests.ConnectionError, requests.Timeout))


# The day an Aviasales user actually saw this price. It isn't a documented
# field - it's the search_date=DDMMYYYY parameter of the result's search
# link - so anything missing or malformed gives None rather than failing the run.
def price_seen_on(link):
    if not link:
        return None
    values = parse_qs(urlparse(link).query).get("search_date")
    if not values:
        return None
    try:
        return datetime.datetime.strptime(values[0], "%d%m%Y").date()
    except ValueError:
        return None


def month_string(today, offset):
    month_index = today.month - 1 + offset
    return f"{today.year + month_index // 12:04d}-{month_index % 12 + 1:02d}"


# (depart_month, return_month) per call: each month on its own, and departing in
# it while returning the next - a same-month query never returns a trip across
# a month boundary (28 Nov -> 4 Dec), and those are about a quarter of the days.
def target_month_pairs(today, month_offsets=MONTH_OFFSETS):
    pairs = []
    for n in month_offsets:
        month, next_month = month_string(today, n), month_string(today, n + 1)
        pairs += [(month, month), (month, next_month)]
    return pairs


@retry(retry=retry_if_exception(is_worth_retrying), stop=stop_after_attempt(3), wait=wait_before_retry, reraise=True)
def fetch_round_trips(origin, destination, depart_month, return_month):
    resp = requests.get(
        PRICES_URL,
        params={
            "origin": origin,
            "destination": destination,
            "departure_at": depart_month,
            "return_at": return_month,
            "currency": "usd",
            "marker": TRAVELPAYOUTS_MARKER,
            "limit": RESULTS_PER_CALL,
        },
        # Not a URL parameter: a failed request's message holds the URL, and it gets logged.
        headers={"X-Access-Token": TRAVELPAYOUTS_TOKEN},
        timeout=15,
    )
    resp.raise_for_status()
    return resp.json()


def fetch_destinations(cur):
    cur.execute(
        "SELECT destination_id, iata_code FROM destinations WHERE is_active ORDER BY destination_id"
    )
    return cur.fetchall()


def collect_destination_months(cur, destination_id, destination_iata, depart_month, return_month, counters):
    try:
        payload = fetch_round_trips(ORIGIN_IATA, destination_iata, depart_month, return_month)
    except requests.RequestException as e:
        print(f"  ERROR fetching {ORIGIN_IATA}->{destination_iata} {depart_month}/{return_month}: {e}")
        counters["errors"] += 1
        return

    results = payload.get("data", [])
    if not results:
        counters["skipped_no_offer"] += 1
        return
    if len(results) == RESULTS_PER_CALL:
        # The API stops at the limit, so there are probably more trips than it returned.
        print(f"  WARNING {ORIGIN_IATA}->{destination_iata} {depart_month}/{return_month} "
              f"returned {RESULTS_PER_CALL} results, the most one call returns")
        counters["hit_results_limit"] += 1

    currency = (payload.get("currency") or "usd").upper()

    for result in results:
        departure_at = result.get("departure_at") or ""
        return_at = result.get("return_at") or ""
        depart_date = departure_at[:10]
        return_date = return_at[:10]
        # [11:16] pulls local wall-clock HH:MM from the ISO timestamp, dropping the UTC offset (not stored).
        depart_time = departure_at[11:16] or None
        return_time = return_at[11:16] or None
        if not depart_date or not return_date:
            continue  # one-way result
        if return_date <= depart_date:
            continue  # a same-day round trip would violate chk_return_after_depart
        seen_on = price_seen_on(result.get("link"))
        if seen_on is None:
            # The column is NOT NULL: the seen-on day is what tells a new price
            # from one an earlier run already stored (uq_flight_obs).
            counters["skipped_no_search_date"] += 1
            continue

        cur.execute(
            """
            INSERT INTO flight_price_observations
                (destination_id, origin_iata, destination_iata, depart_date, return_date,
                 depart_time, return_time,
                 price_amount, currency_code, price_amount_usd, number_of_stops, return_stops, airline_code,
                 price_seen_on)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            -- Skips a price this run or an earlier one already stored (uq_flight_obs).
            ON CONFLICT DO NOTHING
            """,
            (
                destination_id,
                ORIGIN_IATA,
                destination_iata,
                depart_date,
                return_date,
                depart_time,
                return_time,
                result["price"],
                currency,
                result["price"],
                result.get("transfers", 0),
                result.get("return_transfers"),
                result.get("airline"),
                seen_on,
            ),
        )
        # rowcount, not 1: ON CONFLICT DO NOTHING inserts 0 rows for a duplicate.
        counters["inserted"] += cur.rowcount


# The scheduled job collects a subset of the months per run (FLIGHT_SHARDS in
# etl/lambda_jobs.py); the command line collects them all.
def main(month_offsets=MONTH_OFFSETS):
    if not TRAVELPAYOUTS_TOKEN:
        raise SystemExit("TRAVELPAYOUTS_TOKEN is not set -- register at travelpayouts.com and set it in .env")

    counters = {
        "inserted": 0, "skipped_no_offer": 0, "skipped_no_search_date": 0, "errors": 0, "hit_results_limit": 0,
    }

    with get_conn() as conn, conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        destinations = fetch_destinations(cur)

        month_pairs = target_month_pairs(datetime.date.today(), month_offsets)
        for dest in destinations:
            for depart_month, return_month in month_pairs:
                collect_destination_months(
                    cur, dest["destination_id"], dest["iata_code"], depart_month, return_month, counters
                )
            # Commit per destination: a crash or Ctrl+C partway through a run of
            # ~1,400 API calls keeps everything collected up to that point.
            conn.commit()

    print(f"inserted {counters['inserted']} round-trip flight observations "
          f"({counters['skipped_no_offer']} route/month-pair combos had no offer, "
          f"{counters['skipped_no_search_date']} prices had no search date, "
          f"{counters['errors']} request errors, "
          f"{counters['hit_results_limit']} calls hit the {RESULTS_PER_CALL}-result limit)")
    return counters


if __name__ == "__main__":
    main()

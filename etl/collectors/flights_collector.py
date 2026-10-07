# Daily collector: pulls round-trip fares for each active destination from
# Travelpayouts' v3/prices_for_dates endpoint and inserts a snapshot row into
# flight_price_observations. Never upserts on route+date - every run adds new
# rows so trend/aggregation queries over observed_at have something to work with.
#
# Each API result is a complete round trip: (one combined price) ,
# correctly-ordered departure_at/return_at, and a real airline code + flight number.
#
# Run with: uv run python -m etl.collectors.flights_collector

import datetime

import psycopg2.extras
import requests
from tenacity import retry, stop_after_attempt, wait_exponential

from etl.common.config import TRAVELPAYOUTS_MARKER, TRAVELPAYOUTS_TOKEN
from etl.common.db import get_conn

PRICES_URL = "https://api.travelpayouts.com/aviasales/v3/prices_for_dates"

ORIGIN_IATA = "TLV"

# prices_for_dates takes a calendar month (YYYY-MM), not a specific day, for
# both departure_at/return_at -- passing the same month for both returns
# whatever real round trips are cached within it.
MONTH_OFFSETS = [0, 1, 2, 3, 6]

# Each result is a full round trip, so this bounds observations per call.
RESULTS_PER_CALL = 40


def target_months():
    today = datetime.date.today()
    months = []
    for n in MONTH_OFFSETS:
        month_index = today.month - 1 + n
        year = today.year + month_index // 12
        month = month_index % 12 + 1
        months.append(f"{year:04d}-{month:02d}")
    return months


@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=1, max=10), reraise=True)
def fetch_round_trips(origin, destination, target_month):
    resp = requests.get(
        PRICES_URL,
        params={
            "origin": origin,
            "destination": destination,
            "departure_at": target_month,
            "return_at": target_month,
            "currency": "usd",
            "token": TRAVELPAYOUTS_TOKEN,
            "marker": TRAVELPAYOUTS_MARKER,
            "limit": RESULTS_PER_CALL,
        },
        timeout=15,
    )
    resp.raise_for_status()
    return resp.json()


def fetch_destinations(cur):
    cur.execute(
        "SELECT destination_id, iata_code FROM destinations WHERE is_active ORDER BY destination_id"
    )
    return cur.fetchall()


def collect_destination_month(cur, destination_id, destination_iata, target_month, counters):
    try:
        payload = fetch_round_trips(ORIGIN_IATA, destination_iata, target_month)
    except requests.RequestException as e:
        print(f"  ERROR fetching {ORIGIN_IATA}->{destination_iata} {target_month}: {e}")
        counters["errors"] += 1
        return

    results = payload.get("data", [])
    if not results:
        counters["skipped_no_offer"] += 1
        return

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
            # a same-day round trip would violate chk_return_after_depart.
            counters["skipped_no_offer"] += 1
            continue

        cur.execute(
            """
            INSERT INTO flight_price_observations
                (destination_id, origin_iata, destination_iata, depart_date, return_date,
                 depart_time, return_time,
                 price_amount, currency_code, price_amount_usd, number_of_stops, airline_code)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT ON CONSTRAINT uq_flight_obs DO NOTHING
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
                result.get("airline"),
            ),
        )
        # rowcount, not 1: ON CONFLICT DO NOTHING inserts 0 rows for a duplicate.
        counters["inserted"] += cur.rowcount


def main():
    if not TRAVELPAYOUTS_TOKEN:
        raise SystemExit("TRAVELPAYOUTS_TOKEN is not set -- register at travelpayouts.com and set it in .env")

    counters = {"inserted": 0, "skipped_no_offer": 0, "errors": 0}

    with get_conn() as conn, conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        destinations = fetch_destinations(cur)

        for dest in destinations:
            for target_month in target_months():
                collect_destination_month(cur, dest["destination_id"], dest["iata_code"], target_month, counters)
            # Commit per destination: a crash or Ctrl+C partway through a run of
            # ~225 API calls keeps everything collected up to that point.
            conn.commit()

    print(f"inserted {counters['inserted']} round-trip flight observations "
          f"({counters['skipped_no_offer']} route/month combos had no offer, "
          f"{counters['errors']} request errors)")


if __name__ == "__main__":
    main()

# The flights collector with the Travelpayouts API replaced by canned
# payloads, writing into the test database.

import psycopg2
import pytest

from etl.collectors import flights_collector

ROUND_TRIP = {
    "departure_at": "2030-06-01T10:00:00+03:00",
    "return_at": "2030-06-08T18:00:00+03:00",
    "price": 300,
    "transfers": 0,
    "airline": "LY",
}


def new_counters():
    return {"inserted": 0, "skipped_no_offer": 0, "errors": 0}


def test_inserted_counter_ignores_duplicate_rows(cur, monkeypatch):
    monkeypatch.setattr(flights_collector, "fetch_round_trips", lambda *args: {"data": [ROUND_TRIP, ROUND_TRIP]})
    cur.execute("SELECT destination_id FROM destinations WHERE iata_code = 'BCN'")
    counters = new_counters()

    flights_collector.collect_destination_month(cur, cur.fetchone()["destination_id"], "BCN", "2030-06", counters)

    cur.execute("SELECT COUNT(*) AS n FROM flight_price_observations")
    assert cur.fetchone()["n"] == 1
    assert counters["inserted"] == 1


# main() opens its own connection and commits for real (that's what's under
# test), so it's pointed at the test database and cleaned up afterwards.
@pytest.fixture()
def collector_db(test_db_url, monkeypatch):
    monkeypatch.setattr("etl.common.db.DB_URL", test_db_url)
    monkeypatch.setattr(flights_collector, "TRAVELPAYOUTS_TOKEN", "test-token")
    yield test_db_url
    conn = psycopg2.connect(test_db_url)
    with conn, conn.cursor() as cur:
        cur.execute("DELETE FROM flight_price_observations")
    conn.close()


def test_destinations_collected_before_a_crash_are_kept(collector_db, monkeypatch):
    destinations_seen = []

    def fetch(origin, destination, month):
        if destination not in destinations_seen:
            destinations_seen.append(destination)
        if len(destinations_seen) > 1:
            raise RuntimeError("collector crashed on the second destination")
        return {"data": [ROUND_TRIP]}

    monkeypatch.setattr(flights_collector, "fetch_round_trips", fetch)

    with pytest.raises(RuntimeError):
        flights_collector.main()

    conn = psycopg2.connect(collector_db)
    with conn, conn.cursor() as cur:
        cur.execute("SELECT COUNT(*) FROM flight_price_observations")
        assert cur.fetchone()[0] == 1
    conn.close()

# The flights collector with the Travelpayouts API replaced by canned
# payloads, writing into the test database.

import psycopg2
import pytest
import requests

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


class FakeResponse:
    def __init__(self, status_code, headers=None, body=None):
        self.status_code = status_code
        self.headers = headers or {}
        self._body = body or {}

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.HTTPError(f"{self.status_code}", response=self)

    def json(self):
        return self._body


def test_rate_limited_request_waits_for_the_window_to_reset(monkeypatch):
    responses = iter([
        FakeResponse(429, headers={"X-Rate-Limit-Reset": "7"}),
        FakeResponse(200, body={"data": [ROUND_TRIP]}),
    ])
    monkeypatch.setattr(flights_collector.requests, "get", lambda *args, **kwargs: next(responses))
    slept = []
    monkeypatch.setattr(flights_collector.fetch_round_trips.retry, "sleep", slept.append)

    payload = flights_collector.fetch_round_trips("TLV", "BCN", "2030-06")

    assert payload == {"data": [ROUND_TRIP]}
    assert slept == [7]


def test_inserted_counter_ignores_duplicate_rows(cur, monkeypatch):
    monkeypatch.setattr(flights_collector, "fetch_round_trips", lambda *args: {"data": [ROUND_TRIP, ROUND_TRIP]})
    cur.execute("SELECT destination_id FROM destinations WHERE iata_code = 'BCN'")
    counters = new_counters()

    flights_collector.collect_destination_month(cur, cur.fetchone()["destination_id"], "BCN", "2030-06", counters)

    cur.execute("SELECT COUNT(*) AS n FROM flight_price_observations")
    assert cur.fetchone()["n"] == 1
    assert counters["inserted"] == 1


def test_destinations_collected_before_a_crash_are_kept(committing_db, monkeypatch):
    monkeypatch.setattr(flights_collector, "TRAVELPAYOUTS_TOKEN", "test-token")
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

    conn = psycopg2.connect(committing_db)
    with conn, conn.cursor() as cur:
        cur.execute("SELECT COUNT(*) FROM flight_price_observations")
        assert cur.fetchone()[0] == 1
    conn.close()

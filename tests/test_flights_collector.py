# The flights collector with the Travelpayouts API replaced by canned
# payloads, writing into the test database.

import datetime

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
    "link": "/search/TLV0106BCN08061?t=abc&search_date=04102026&expected_price=300",
}


def new_counters():
    return {"inserted": 0, "skipped_no_offer": 0, "skipped_no_search_date": 0, "errors": 0}


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

    payload = flights_collector.fetch_round_trips("TLV", "BCN", "2030-06", "2030-06")

    assert payload == {"data": [ROUND_TRIP]}
    assert slept == [7]


def test_months_cover_trips_that_return_the_next_month():
    pairs = flights_collector.target_month_pairs(datetime.date(2026, 11, 20))

    assert pairs[:4] == [("2026-11", "2026-11"), ("2026-11", "2026-12"), ("2026-12", "2026-12"), ("2026-12", "2027-01")]
    assert pairs[-2:] == [("2027-05", "2027-05"), ("2027-05", "2027-06")]  # six months on, none skipped
    assert len(pairs) == 14


def test_each_leg_is_asked_for_its_own_month(monkeypatch):
    sent = []
    monkeypatch.setattr(
        flights_collector.requests, "get",
        lambda url, params, timeout: sent.append(params) or FakeResponse(200, body={"data": []}),
    )

    flights_collector.fetch_round_trips("TLV", "BCN", "2030-06", "2030-07")

    assert (sent[0]["departure_at"], sent[0]["return_at"]) == ("2030-06", "2030-07")


def test_inserted_counter_ignores_duplicate_rows(cur, monkeypatch):
    monkeypatch.setattr(flights_collector, "fetch_round_trips", lambda *args: {"data": [ROUND_TRIP, ROUND_TRIP]})
    counters = new_counters()

    flights_collector.collect_destination_months(cur, bcn_id(cur), "BCN", "2030-06", "2030-06", counters)

    cur.execute("SELECT COUNT(*) AS n FROM flight_price_observations")
    assert cur.fetchone()["n"] == 1
    assert counters["inserted"] == 1


def test_destinations_collected_before_a_crash_are_kept(committing_db, monkeypatch):
    monkeypatch.setattr(flights_collector, "TRAVELPAYOUTS_TOKEN", "test-token")
    destinations_seen = []

    def fetch(origin, destination, depart_month, return_month):
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


@pytest.mark.parametrize(
    ("link", "expected"),
    [
        ("/search/X?t=abc&search_date=04102026&expected_price=176", datetime.date(2026, 10, 4)),
        ("/search/X?t=abc&expected_price=176", None),
        ("/search/X?search_date=99999999", None),
        (None, None),
    ],
)
def test_price_seen_on_comes_from_the_links_search_date(link, expected):
    assert flights_collector.price_seen_on(link) == expected


def bcn_id(cur):
    cur.execute("SELECT destination_id FROM destinations WHERE iata_code = 'BCN'")
    return cur.fetchone()["destination_id"]


def test_collector_stores_when_the_price_was_seen(cur, monkeypatch):
    monkeypatch.setattr(flights_collector, "fetch_round_trips", lambda *args: {"data": [ROUND_TRIP]})

    flights_collector.collect_destination_months(cur, bcn_id(cur), "BCN", "2030-06", "2030-06", new_counters())

    cur.execute("SELECT price_seen_on FROM flight_price_observations")
    assert cur.fetchone()["price_seen_on"] == datetime.date(2026, 10, 4)


def test_price_already_stored_by_an_earlier_run_is_not_inserted_again(cur, monkeypatch):
    earlier_run = datetime.datetime(2026, 10, 5, tzinfo=datetime.UTC)
    cur.execute(
        """
        INSERT INTO flight_price_observations
            (destination_id, origin_iata, destination_iata, depart_date, return_date, depart_time, return_time,
             price_amount, currency_code, price_amount_usd, number_of_stops, airline_code, observed_at, price_seen_on)
        VALUES (%s, 'TLV', 'BCN', '2026-06-01', '2026-06-08', '10:00', '18:00',
                300, 'USD', 300, 0, 'LY', %s, '2026-10-04')
        """,
        (bcn_id(cur), earlier_run),
    )
    same_trip = {**ROUND_TRIP, "departure_at": "2026-06-01T10:00:00+03:00", "return_at": "2026-06-08T18:00:00+03:00"}
    monkeypatch.setattr(flights_collector, "fetch_round_trips", lambda *args: {"data": [same_trip]})
    counters = new_counters()

    flights_collector.collect_destination_months(cur, bcn_id(cur), "BCN", "2026-06", "2026-06", counters)

    cur.execute("SELECT COUNT(*) AS n FROM flight_price_observations")
    assert cur.fetchone()["n"] == 1
    assert counters["inserted"] == 0


def test_price_without_a_search_date_is_skipped_and_counted(cur, monkeypatch):
    # price_seen_on is NOT NULL: it's what tells a new price from a stored one.
    # Every link has carried search_date so far; if one stops, the run says so.
    no_date = {**ROUND_TRIP, "link": "/search/TLV0106BCN08061?t=abc&expected_price=300"}
    monkeypatch.setattr(flights_collector, "fetch_round_trips", lambda *args: {"data": [no_date, ROUND_TRIP]})
    counters = new_counters()

    flights_collector.collect_destination_months(cur, bcn_id(cur), "BCN", "2030-06", "2030-06", counters)

    cur.execute("SELECT price_seen_on FROM flight_price_observations")
    assert [r["price_seen_on"] for r in cur.fetchall()] == [datetime.date(2026, 10, 4)]
    assert (counters["inserted"], counters["skipped_no_search_date"]) == (1, 1)

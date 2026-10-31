# The live exact-date flight call (app/live_flights.py), with requests.get
# replaced by a fake - no network. Any failure must come back as None (the
# caller then falls back to collected data), never as an exception.

import datetime
import json

import pytest
import requests

from app import live_flights

DEPART = datetime.date(2030, 6, 1)
RETURN = datetime.date(2030, 6, 8)

# Shaped like a real prices_for_dates result (TLV-BCN, 2026-10-08).
RESULT = {
    "flight_number": "6404",
    "link": "/search/TLV0106BCN08061?t=abc&search_date=04102026&expected_price=176",
    "departure_at": "2030-06-01T18:55:00+03:00",
    "return_at": "2030-06-08T07:30:00+02:00",
    "airline": "W4",
    "price": 176,
    "transfers": 1,
    "return_transfers": 0,
    "duration_to": 360,
    "duration_back": 305,
}


def response(status, payload):
    r = requests.Response()
    r.status_code = status
    r._content = json.dumps(payload).encode()
    return r


@pytest.fixture()
def fake_get(monkeypatch):
    calls = []

    def answer_with(result):
        def get(url, params, timeout, headers=None):
            calls.append({"params": params, "timeout": timeout, "headers": headers})
            if isinstance(result, Exception):
                raise result
            return result

        monkeypatch.setattr(live_flights.requests, "get", get)
        return calls

    return answer_with


def fetch():
    return live_flights.fetch_live_flight_options("TLV", "BCN", DEPART, RETURN)


def test_parses_every_field(fake_get):
    fake_get(response(200, {"data": [RESULT]}))

    assert fetch() == [
        {
            "depart_date": DEPART,
            "return_date": RETURN,
            "depart_time": datetime.time(18, 55),
            "return_time": datetime.time(7, 30),
            "airline_code": "W4",
            "flight_number": "6404",
            "outbound_stops": 1,
            "return_stops": 0,
            "outbound_minutes": 360,
            "return_minutes": 305,
            "price_usd": 176.0,
            "price_seen_on": datetime.date(2026, 10, 4),
            "booking_url": "https://www.aviasales.com/search/TLV0106BCN08061?t=abc&search_date=04102026&expected_price=176",
        }
    ]


def test_asks_for_the_exact_dates_with_a_short_timeout(fake_get):
    calls = fake_get(response(200, {"data": []}))

    fetch()

    assert calls[0]["params"]["departure_at"] == "2030-06-01"
    assert calls[0]["params"]["return_at"] == "2030-06-08"
    assert calls[0]["timeout"] == live_flights.LIVE_TIMEOUT_SECONDS


# A failure is logged with the request's message, which holds its URL: the
# token goes in a header so it never reaches the API's log.
def test_token_is_sent_in_a_header_not_the_url(fake_get, monkeypatch):
    monkeypatch.setattr(live_flights, "TRAVELPAYOUTS_TOKEN", "secret-token")
    calls = fake_get(response(200, {"data": []}))

    fetch()

    assert "secret-token" not in calls[0]["params"].values()
    assert calls[0]["headers"] == {"X-Access-Token": "secret-token"}


def test_results_for_other_dates_are_dropped(fake_get):
    other_day = {**RESULT, "departure_at": "2030-06-02T18:55:00+03:00"}
    fake_get(response(200, {"data": [other_day, RESULT]}))

    assert [o["depart_date"] for o in fetch()] == [DEPART]


def test_nothing_cached_is_an_empty_list_not_a_failure(fake_get):
    fake_get(response(200, {"data": []}))

    assert fetch() == []


@pytest.mark.parametrize(
    "answer",
    [
        requests.Timeout("too slow"),
        requests.ConnectionError("no network"),
        response(429, {"error": "rate limited"}),
        response(500, {}),
        response(200, {"unexpected": "shape"}),
        response(200, {"data": [{**RESULT, "price": None}]}),
        response(200, {"data": [{**RESULT, "price": 0}]}),
        response(200, {"data": [{k: v for k, v in RESULT.items() if k != "departure_at"}]}),
    ],
    ids=["timeout", "connection", "429", "500", "no-data-key", "null-price", "zero-price", "missing-field"],
)
def test_any_failure_is_none(fake_get, answer):
    fake_get(answer)

    assert fetch() is None


def test_switched_off_asks_nothing(fake_get, monkeypatch):
    calls = fake_get(response(200, {"data": [RESULT]}))
    monkeypatch.setattr(live_flights, "LIVE_FLIGHT_SEARCH", False)

    assert fetch() is None
    assert calls == []

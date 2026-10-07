# Flask routes, driven through Flask's test client. The routes' get_cursor()
# is swapped for the test's own cursor, so everything they read and write
# stays inside the test's rolled-back transaction - and is counted, which is
# how the N+1 tests see how many statements a request ran.

import datetime
from contextlib import nullcontext

import pytest

from app.main import app
from app.routes import estimate as estimate_routes
from app.routes import history as history_routes
from tests.factories import add_exchange_rate, add_flight, add_hotel, add_saved_search

DEPART = datetime.date(2030, 6, 1)
RETURN = datetime.date(2030, 6, 8)


class CountingCursor:
    def __init__(self, cur):
        self._cur = cur
        self.executed = 0

    def execute(self, *args, **kwargs):
        self.executed += 1
        return self._cur.execute(*args, **kwargs)

    def __getattr__(self, name):
        return getattr(self._cur, name)


@pytest.fixture()
def app_cursor(cur, monkeypatch):
    counting = CountingCursor(cur)
    for routes in (estimate_routes, history_routes):
        monkeypatch.setattr(routes, "get_cursor", lambda: nullcontext(counting))
    return counting


@pytest.fixture()
def client(app_cursor):
    return app.test_client()


def as_browser(client, session_id):
    with client.session_transaction() as session:
        session["session_id"] = session_id


def statements_for(app_cursor, request):
    before = app_cursor.executed
    response = request()
    assert response.status_code == 200
    return app_cursor.executed - before


# --- /history/<id> -----------------------------------------------------------


def test_saved_search_is_visible_to_the_browser_that_made_it(client, cur):
    search_id = add_saved_search(cur, session_id="browser-a")
    as_browser(client, "browser-a")

    assert client.get(f"/history/{search_id}").status_code == 200


def test_saved_search_of_another_browser_is_not_found(client, cur):
    search_id = add_saved_search(cur, session_id="browser-a")
    as_browser(client, "browser-b")

    assert client.get(f"/history/{search_id}").status_code == 404


def test_history_detail_statement_count_does_not_grow_with_results(client, cur, app_cursor):
    add_exchange_rate(cur, "ILS", 0.27)
    one = add_saved_search(cur, "browser-a", ["BCN"], budget_currency="ILS")
    three = add_saved_search(cur, "browser-a", ["BCN", "MAD", "FCO"], budget_currency="ILS")
    as_browser(client, "browser-a")

    assert statements_for(app_cursor, lambda: client.get(f"/history/{one}")) == statements_for(
        app_cursor, lambda: client.get(f"/history/{three}")
    )


# --- /estimate ---------------------------------------------------------------


def test_estimate_statement_count_does_not_grow_with_destinations(client, cur, app_cursor):
    add_exchange_rate(cur, "ILS", 0.27)
    form = {
        "origin_iata": "TLV",
        "depart_date": DEPART.isoformat(),
        "return_date": RETURN.isoformat(),
        "budget_amount": "100000",
        "budget_currency": "ILS",
        "hotel_tier": "average",
    }

    def search():
        return client.post("/estimate", data=form)

    add_flight(cur, "BCN", DEPART, RETURN, price_usd=300)
    add_hotel(cur, "barcelona", avg_usd=100)
    with_one = statements_for(app_cursor, search)

    for iata, city in (("MAD", "madrid"), ("FCO", "rome")):
        add_flight(cur, iata, DEPART, RETURN, price_usd=300)
        add_hotel(cur, city, avg_usd=100)
    with_three = statements_for(app_cursor, search)

    assert with_one == with_three

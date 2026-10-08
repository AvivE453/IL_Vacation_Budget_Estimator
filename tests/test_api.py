# FastAPI routes, driven through its TestClient. The db_cursor dependency is
# overridden with the test's own cursor, so everything a route reads and
# writes stays inside the test's rolled-back transaction.
#
# The SQL behind each route is checked in test_queries.py; these check the
# JSON contract React will rely on - field names, types, and how gaps look.

import datetime

import pytest
from fastapi.testclient import TestClient

from api.deps import db_cursor
from api.main import app
from app import trip as trip_module
from app.db import PoolExhausted
from app.queries import count_active_destinations
from tests.factories import add_airline, add_exchange_rate, add_flight, add_hotel, add_saved_search

DEPART = datetime.date(2030, 6, 1)
RETURN = datetime.date(2030, 6, 8)


# No test here reaches the real Travelpayouts: the live call fails unless a
# test hands it an answer through `live`.
@pytest.fixture(autouse=True)
def live(monkeypatch):
    answer = {"options": None}
    monkeypatch.setattr(trip_module, "fetch_live_flight_options", lambda *args: answer["options"])
    return answer


@pytest.fixture()
def client(cur):
    app.dependency_overrides[db_cursor] = lambda: cur
    yield TestClient(app)
    app.dependency_overrides.clear()


def test_health_reports_ok(client):
    response = client.get("/api/v1/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_busy_database_is_503_not_500(client):
    def no_free_connection():
        raise PoolExhausted("no free database connection")

    app.dependency_overrides[db_cursor] = no_free_connection
    response = client.get("/api/v1/health")

    assert response.status_code == 503
    assert response.headers["Retry-After"] == "1"


def test_origins_lists_israeli_airports(client):
    response = client.get("/api/v1/origins")

    assert response.status_code == 200
    assert response.json() == [{"iata_code": "TLV", "airport_name": "Ben Gurion Airport", "city_name": "Tel Aviv"}]


def test_data_quality_shows_coverage_and_gaps(client, cur):
    add_flight(cur, "BCN", DEPART, RETURN, price_usd=300)
    add_hotel(cur, "barcelona", avg_usd=150, sample_size=25)

    response = client.get("/api/v1/data-quality")

    assert response.status_code == 200
    coverage = {row["city_name"]: row for row in response.json()["coverage"]}
    assert coverage["Barcelona"] == {
        "city_name": "Barcelona",
        "country_name": "Spain",
        "flight_obs_count": 1,
        "hotel_sample_size": 25,
        "hotel_price_age_days": 0,
    }
    # Nothing collected: still listed, with the missing hotel data as null.
    assert coverage["Madrid"]["flight_obs_count"] == 0
    assert coverage["Madrid"]["hotel_sample_size"] is None
    assert coverage["Madrid"]["hotel_price_age_days"] is None


def test_data_quality_collection_volume_is_per_day(client, cur):
    observed = datetime.datetime(2030, 1, 1, 12, tzinfo=datetime.UTC)
    add_flight(cur, "BCN", DEPART, RETURN, price_usd=300, observed_at=observed)
    add_flight(cur, "MAD", DEPART, RETURN, price_usd=250, observed_at=observed)

    response = client.get("/api/v1/data-quality")

    assert response.json()["collection_volume"] == [{"day": "2030-01-01", "observations_collected": 2}]


# --- POST /api/v1/estimates --------------------------------------------------


def search_body(**overrides):
    return {
        "origin_iata": "TLV",
        "depart_date": DEPART.isoformat(),
        "return_date": RETURN.isoformat(),
        "budget_amount": 5000,
        "budget_currency": "ILS",
        "hotel_tier": "average",
        **overrides,
    }


def test_estimate_returns_all_three_tiers_in_the_budget_currency(client, cur):
    add_exchange_rate(cur, "ILS", 0.25)
    add_flight(cur, "BCN", DEPART, RETURN, price_usd=300, airline_code="IZ")
    add_hotel(cur, "barcelona", avg_usd=100, budget_usd=60, luxury_usd=250)

    response = client.post("/api/v1/estimates", json=search_body())

    assert response.status_code == 200
    body = response.json()
    assert body["currency"] == "ILS"
    assert body["budget_amount"] == 5000
    assert set(body["tiers"]) == {"budget", "average", "luxury"}
    budget_tier = body["tiers"]["budget"]
    assert budget_tier["exact_dates_only"] is True
    assert budget_tier["has_missing_data"] is False
    assert budget_tier["destinations"] == [
        {
            "destination_id": budget_tier["destinations"][0]["destination_id"],
            "city_name": "Barcelona",
            "airline_code": "IZ",
            "airline_name": None,
            "flight_out_date": "2030-06-01",
            "flight_return_date": "2030-06-08",
            "matched_nights": 7,
            "flight_total_amount": 1200.0,  # $300 at 0.25 USD per ILS
            "hotel_total_amount": 1680.0,  # 7 * $60
            "total_estimate_amount": 2880.0,
        }
    ]
    # Luxury: 300 + 7 * 250 = $2050 = 8200 ILS, over the 5000 ILS budget.
    assert body["tiers"]["luxury"] == {"exact_dates_only": False, "has_missing_data": False, "destinations": []}


def test_estimate_saves_only_the_requested_tier_to_this_browsers_history(client, cur):
    add_flight(cur, "BCN", DEPART, RETURN, price_usd=300)
    add_flight(cur, "MAD", DEPART, RETURN, price_usd=300)
    add_hotel(cur, "barcelona", avg_usd=100, budget_usd=60, luxury_usd=250)
    add_hotel(cur, "madrid", avg_usd=100, budget_usd=60, luxury_usd=None, sample_size=5)

    response = client.post("/api/v1/estimates", json=search_body(budget_currency="USD", hotel_tier="luxury"))

    cur.execute(
        "SELECT session_id, hotel_tier, (SELECT COUNT(*) FROM search_results WHERE search_query_id = %(id)s) AS saved"
        " FROM search_queries WHERE search_query_id = %(id)s",
        {"id": response.json()["search_id"]},
    )
    saved = cur.fetchone()
    assert saved["session_id"] == response.cookies["session_id"]
    assert saved["hotel_tier"] == "luxury"
    assert saved["saved"] == 1  # Madrid has no luxury price, so only Barcelona


def test_searches_from_one_browser_share_a_session(client, cur):
    # TestClient sends back the cookies it received, like a browser.
    responses = [client.post("/api/v1/estimates", json=search_body(budget_currency="USD")) for _ in range(2)]
    ids = [r.json()["search_id"] for r in responses]

    cur.execute("SELECT DISTINCT session_id FROM search_queries WHERE search_query_id = ANY(%s)", (ids,))

    assert [r["session_id"] for r in cur.fetchall()] == [client.cookies["session_id"]]


@pytest.mark.parametrize(
    ("overrides", "field"),
    [
        ({"return_date": DEPART.isoformat()}, None),  # model-level check: same-day return
        ({"depart_date": "2030-13-01"}, "depart_date"),
        ({"budget_amount": 0}, "budget_amount"),
        ({"budget_amount": 100_000_000}, "budget_amount"),
        ({"budget_amount": "abc"}, "budget_amount"),
        ({"budget_currency": "GBP"}, "budget_currency"),
        ({"hotel_tier": "premium"}, "hotel_tier"),
        ({"origin_iata": "XYZ"}, "origin_iata"),
        ({"origin_iata": "BCN"}, "origin_iata"),  # a real airport, but not one we depart from
    ],
)
def test_invalid_search_is_422_naming_the_field(client, overrides, field):
    response = client.post("/api/v1/estimates", json=search_body(**overrides))

    assert response.status_code == 422
    if field:
        assert [e["loc"] for e in response.json()["detail"]] == [["body", field]]


def test_missing_field_is_422(client):
    body = search_body()
    del body["depart_date"]

    response = client.post("/api/v1/estimates", json=body)

    assert response.status_code == 422
    assert response.json()["detail"][0]["loc"] == ["body", "depart_date"]


# --- GET /api/v1/searches ----------------------------------------------------


def as_browser(client, session_id):
    client.cookies.set("session_id", session_id)


def test_search_list_shows_this_browsers_searches_newest_first(client, cur):
    older = add_saved_search(cur, "browser-a", budget_currency="ILS")
    newer = add_saved_search(cur, "browser-a")
    add_saved_search(cur, "browser-b")
    # One transaction means one now(), so give the older search an earlier time.
    cur.execute(
        "UPDATE search_queries SET created_at = created_at - interval '1 day' WHERE search_query_id = %s", (older,)
    )
    as_browser(client, "browser-a")

    searches = client.get("/api/v1/searches").json()

    assert [s["search_id"] for s in searches] == [newer, older]
    assert {k: v for k, v in searches[1].items() if k != "created_at"} == {
        "search_id": older,
        "origin_iata": "TLV",
        "depart_date": "2030-06-01",
        "return_date": "2030-06-08",
        "budget_amount": 5000.0,
        "budget_currency": "ILS",
        "hotel_tier": "average",
    }


def test_new_browser_has_no_searches_and_gets_a_session(client):
    response = client.get("/api/v1/searches")

    assert response.json() == []
    assert response.cookies["session_id"]


def test_saved_search_is_shown_in_its_budget_currency(client, cur):
    add_exchange_rate(cur, "ILS", 0.25)
    search_id = add_saved_search(cur, "browser-a", ["BCN"], budget_currency="ILS")
    as_browser(client, "browser-a")

    body = client.get(f"/api/v1/searches/{search_id}").json()

    assert body["search_id"] == search_id
    assert body["currency"] == "ILS"
    assert body["exact_dates_only"] is None  # not recorded by the factory
    assert body["results"] == [
        {
            "cost_rank": 1,
            "destination_id": body["results"][0]["destination_id"],
            "city_name": "Barcelona",
            "airline_code": None,
            "airline_name": None,
            "estimated_total_amount": 4000.0,  # $1000 at 0.25 USD per ILS
            "within_budget": True,
        }
    ]


def test_search_with_no_saved_results_is_found(client, cur):
    search_id = add_saved_search(cur, "browser-a", [])
    as_browser(client, "browser-a")

    response = client.get(f"/api/v1/searches/{search_id}")

    assert response.status_code == 200
    assert response.json()["results"] == []


def test_another_browsers_search_is_not_found(client, cur):
    search_id = add_saved_search(cur, "browser-a")
    as_browser(client, "browser-b")

    assert client.get(f"/api/v1/searches/{search_id}").status_code == 404


def test_saved_search_without_a_rate_is_shown_in_usd(client, cur):
    search_id = add_saved_search(cur, "browser-a", ["BCN"], budget_currency="GBP")
    as_browser(client, "browser-a")

    body = client.get(f"/api/v1/searches/{search_id}").json()

    assert body["currency"] == "USD"
    assert body["results"][0]["estimated_total_amount"] == 1000.0


# --- GET /api/v1/destinations ------------------------------------------------


def test_destinations_lists_every_active_destination(client, cur):
    destinations = client.get("/api/v1/destinations").json()

    assert len(destinations) == count_active_destinations(cur)
    barcelona = next(d for d in destinations if d["iata_code"] == "BCN")
    assert (barcelona["city_name"], barcelona["country_name"]) == ("Barcelona", "Spain")


# --- GET /api/v1/destinations/{id}/trip --------------------------------------


def barcelona_id(cur):
    cur.execute("SELECT destination_id FROM destinations WHERE iata_code = 'BCN'")
    return cur.fetchone()["destination_id"]


def trip(client, cur, **params):
    query = {"depart_date": DEPART.isoformat(), "return_date": RETURN.isoformat(), "currency": "USD", **params}
    return client.get(f"/api/v1/destinations/{barcelona_id(cur)}/trip", params=query)


def live_option(price, **overrides):
    return {
        "depart_date": DEPART,
        "return_date": RETURN,
        "depart_time": datetime.time(18, 55),
        "return_time": datetime.time(7, 30),
        "airline_code": "IZ",
        "flight_number": "6404",
        "outbound_stops": 0,
        "return_stops": 1,
        "outbound_minutes": 300,
        "return_minutes": 420,
        "price_usd": price,
        "price_seen_on": datetime.date(2030, 5, 20),
        "booking_url": "https://www.aviasales.com/search/x",
        **overrides,
    }


def test_trip_shows_live_options_with_hotel_prices(client, cur, live):
    add_exchange_rate(cur, "ILS", 0.25)
    add_airline(cur, "IZ", "Arkia")
    add_hotel(cur, "barcelona", avg_usd=100, budget_usd=60, luxury_usd=None, sample_size=5)
    add_flight(cur, "BCN", DEPART, RETURN, price_usd=999)  # collected data is ignored when live answers
    live["options"] = [live_option(176), live_option(231, airline_code="XX", flight_number=None)]

    body = trip(client, cur, currency="ILS").json()

    assert body["source"] == "live"
    assert body["exact_dates"] is True
    assert (body["flight_out_date"], body["flight_return_date"]) == ("2030-06-01", "2030-06-08")
    assert body["currency"] == "ILS"
    assert body["flights"][0] == {
        "airline_code": "IZ",
        "airline_name": "Arkia",
        "flight_number": "6404",
        "depart_time": "18:55:00",
        "return_time": "07:30:00",
        "outbound_stops": 0,
        "return_stops": 1,
        "outbound_minutes": 300,
        "return_minutes": 420,
        "price_amount": 704.0,  # $176 at 0.25 USD per ILS
        "price_seen_on": "2030-05-20",
        "booking_url": "https://www.aviasales.com/search/x",
    }
    assert body["flights"][1]["airline_name"] is None  # code not in the airlines table
    assert body["hotel"] == {
        "nights": 7,
        "price_age_days": 0,
        "budget": {"per_night_amount": 240.0, "total_amount": 1680.0},
        "average": {"per_night_amount": 400.0, "total_amount": 2800.0},
        "luxury": None,  # no luxury price on file
    }


@pytest.mark.parametrize("live_answer", [None, []], ids=["live-failed", "live-empty"])
def test_trip_falls_back_to_the_nearest_collected_dates(client, cur, live, live_answer):
    live["options"] = live_answer
    add_hotel(cur, "barcelona", avg_usd=100)
    nearest_depart = DEPART + datetime.timedelta(days=1)  # a 6-night trip
    # The same flight seen twice: only the price seen last is an option.
    add_flight(cur, "BCN", nearest_depart, RETURN, price_usd=300, airline_code="IZ",
               price_seen_on=datetime.date(2030, 5, 1))
    add_flight(cur, "BCN", nearest_depart, RETURN, price_usd=280, airline_code="IZ",
               price_seen_on=datetime.date(2030, 5, 3))
    add_flight(cur, "BCN", nearest_depart, RETURN, price_usd=250, airline_code="W4", number_of_stops=1)
    # Farther from the request, so not the pair shown.
    add_flight(cur, "BCN", DEPART + datetime.timedelta(days=3), RETURN, price_usd=100)

    body = trip(client, cur).json()

    assert body["source"] == "collected"
    assert body["exact_dates"] is False
    assert body["flight_out_date"] == nearest_depart.isoformat()
    assert [(f["airline_code"], f["price_amount"]) for f in body["flights"]] == [("W4", 250.0), ("IZ", 280.0)]
    w4 = body["flights"][0]
    assert w4["outbound_stops"] == 1
    assert [w4[k] for k in ("return_stops", "outbound_minutes", "return_minutes", "booking_url")] == [None] * 4
    assert body["hotel"]["nights"] == 6


def test_trip_with_no_flights_anywhere(client, cur):
    body = trip(client, cur).json()

    assert body["source"] is None
    assert body["flights"] == []
    assert body["exact_dates"] is False
    assert body["hotel"]["nights"] == 7  # the requested trip, with no flight to follow
    assert body["hotel"]["average"] is None  # no hotel price on file either


def test_unknown_or_inactive_destination_is_404(client, cur):
    query = {"depart_date": DEPART.isoformat(), "return_date": RETURN.isoformat()}
    assert client.get("/api/v1/destinations/999999/trip", params=query).status_code == 404

    cur.execute("UPDATE destinations SET is_active = false WHERE iata_code = 'BCN'")
    assert trip(client, cur).status_code == 404


@pytest.mark.parametrize(
    ("params", "field"),
    [
        ({"return_date": DEPART.isoformat()}, None),
        ({"currency": "GBP"}, "currency"),
        ({"origin_iata": "XYZ"}, "origin_iata"),
    ],
)
def test_invalid_trip_query_is_422(client, cur, params, field):
    response = trip(client, cur, **params)

    assert response.status_code == 422
    if field:
        assert [e["loc"] for e in response.json()["detail"]] == [["query", field]]

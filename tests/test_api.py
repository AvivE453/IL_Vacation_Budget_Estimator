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
from app.db import PoolExhausted
from tests.factories import add_flight, add_hotel

DEPART = datetime.date(2030, 6, 1)
RETURN = datetime.date(2030, 6, 8)


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

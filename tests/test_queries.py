# The app's read queries, checked for exact values against rows each test
# inserts itself into the seeded test database (see conftest.py).

import datetime

from app.queries import (
    count_active_destinations,
    get_collection_volume,
    get_data_quality_report,
    list_origin_airports,
)
from tests.factories import add_flight, add_hotel

DEPART = datetime.date(2030, 6, 1)
RETURN = datetime.date(2030, 6, 8)


def test_list_origin_airports_returns_only_israeli_airports(cur):
    rows = list_origin_airports(cur)

    assert [r["iata_code"] for r in rows] == ["TLV"]


def test_count_active_destinations_ignores_inactive(cur):
    before = count_active_destinations(cur)
    cur.execute("UPDATE destinations SET is_active = false WHERE iata_code = 'BCN'")

    assert count_active_destinations(cur) == before - 1


def test_data_quality_report_counts_per_destination(cur):
    for day in range(3):
        add_flight(cur, "BCN", DEPART + datetime.timedelta(days=day), RETURN, price_usd=300)
    add_hotel(cur, "barcelona", avg_usd=150, sample_size=25)

    rows = {r["city_name"]: r for r in get_data_quality_report(cur)}

    assert len(rows) == count_active_destinations(cur)
    assert rows["Barcelona"]["country_name"] == "Spain"
    assert rows["Barcelona"]["flight_obs_count"] == 3
    assert rows["Barcelona"]["hotel_sample_size"] == 25
    # A destination with nothing collected still appears, with its gaps visible.
    assert rows["Madrid"]["flight_obs_count"] == 0
    assert rows["Madrid"]["hotel_sample_size"] is None


def test_collection_volume_groups_by_observation_day(cur):
    day1 = datetime.datetime(2030, 1, 1, 12, tzinfo=datetime.UTC)
    day2 = datetime.datetime(2030, 1, 2, 12, tzinfo=datetime.UTC)
    add_flight(cur, "BCN", DEPART, RETURN, price_usd=300, observed_at=day1)
    add_flight(cur, "MAD", DEPART, RETURN, price_usd=250, observed_at=day1)
    add_flight(cur, "BCN", DEPART, RETURN, price_usd=310, observed_at=day2)

    rows = get_collection_volume(cur)

    assert [(r["day"].date(), r["observations_collected"]) for r in rows] == [
        (day1.date(), 2),
        (day2.date(), 1),
    ]

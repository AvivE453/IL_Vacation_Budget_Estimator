# The hotels collector with SerpApi replaced by canned results. Every real
# SerpApi search costs one of 250 a month, so these pin down which cities a
# run spends them on and that it never spends more than it's allowed.

import psycopg2
import pytest

from etl.collectors import hotels_collector

PROPERTIES = [{"rate_per_night": {"extracted_lowest": price}} for price in (80, 100, 120, 200)]


def test_refreshes_cities_without_a_price_first_then_the_oldest(cur):
    cur.execute(
        """
        INSERT INTO hotel_prices (city_name_raw, city_name_normalized, avg_price_per_night_usd, sample_size)
        SELECT city_name, hotel_data_city_key, 100, 20 FROM destinations WHERE is_active
        """
    )
    cur.execute("UPDATE hotel_prices SET loaded_at = '2020-01-01' WHERE city_name_normalized = 'rome'")
    cur.execute("UPDATE hotel_prices SET loaded_at = '2021-01-01' WHERE city_name_normalized = 'madrid'")
    cur.execute("DELETE FROM hotel_prices WHERE city_name_normalized = 'barcelona'")

    picked = hotels_collector.pick_destinations(cur, 3)

    assert [d["city_name"] for d in picked] == ["Barcelona", "Rome", "Madrid"]


@pytest.fixture()
def searched_cities(committing_db, monkeypatch):
    monkeypatch.setattr(hotels_collector, "SERPAPI_KEY", "test-key")
    searched = []

    def fetch(city, check_in, check_out):
        searched.append(city)
        return PROPERTIES

    monkeypatch.setattr(hotels_collector, "fetch_hotel_properties", fetch)
    return searched


def test_never_spends_more_searches_than_the_account_has_left(searched_cities, monkeypatch):
    monkeypatch.setattr(hotels_collector, "fetch_searches_left", lambda: 3)

    hotels_collector.main(max_searches=100)

    assert len(searched_cities) == 3


def test_stops_at_the_runs_search_budget(searched_cities, monkeypatch):
    monkeypatch.setattr(hotels_collector, "fetch_searches_left", lambda: 250)

    hotels_collector.main(max_searches=2)

    assert len(searched_cities) == 2


def test_cities_priced_before_a_crash_are_kept(committing_db, monkeypatch):
    monkeypatch.setattr(hotels_collector, "SERPAPI_KEY", "test-key")
    monkeypatch.setattr(hotels_collector, "fetch_searches_left", lambda: 250)
    searched = []

    def fetch(city, check_in, check_out):
        searched.append(city)
        if len(searched) > 1:
            raise RuntimeError("collector crashed on the second city")
        return PROPERTIES

    monkeypatch.setattr(hotels_collector, "fetch_hotel_properties", fetch)

    with pytest.raises(RuntimeError):
        hotels_collector.main(max_searches=10)

    conn = psycopg2.connect(committing_db)
    with conn, conn.cursor() as cur:
        cur.execute("SELECT COUNT(*) FROM hotel_prices")
        assert cur.fetchone()[0] == 1
    conn.close()

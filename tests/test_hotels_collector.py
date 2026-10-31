# The hotels collector with SerpApi replaced by canned results. Every real
# SerpApi search costs one of 250 a month, so these pin down which cities a
# run spends them on and that it never spends more than it's allowed.

import psycopg2
import pytest
import requests

from etl.collectors import hotels_collector

PROPERTIES = [{"rate_per_night": {"extracted_lowest": price}} for price in (80, 100, 120, 200)]


def test_refreshes_cities_without_a_price_first_then_the_oldest(cur):
    cur.execute(
        """
        INSERT INTO hotel_prices (destination_id, avg_price_per_night_usd, sample_size)
        SELECT destination_id, 100, 20 FROM destinations WHERE is_active
        """
    )
    by_iata = "destination_id = (SELECT destination_id FROM destinations WHERE iata_code = %s)"
    cur.execute(f"UPDATE hotel_prices SET loaded_at = '2020-01-01' WHERE {by_iata}", ("FCO",))
    cur.execute(f"UPDATE hotel_prices SET loaded_at = '2021-01-01' WHERE {by_iata}", ("MAD",))
    cur.execute(f"DELETE FROM hotel_prices WHERE {by_iata}", ("BCN",))

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

    counts = hotels_collector.main(max_searches=2)

    assert len(searched_cities) == 2
    assert counts == {"updated": 2, "skipped_no_results": 0, "errors": 0}


# The "hotels run updated 0" alarm is tested with a real run of
# max_searches 0: it must not spend a search.
def test_a_run_without_a_search_budget_searches_nothing(searched_cities, monkeypatch):
    monkeypatch.setattr(hotels_collector, "fetch_searches_left", lambda: 250)

    counts = hotels_collector.main(max_searches=0)

    assert searched_cities == []
    assert counts["updated"] == 0


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


# SerpApi takes its key only as a URL parameter, and a failed request's message
# holds the URL: a printed or raised error must not carry the key into the
# Lambda log (found by testing an alarm with a wrong token).
def failing_get(*args, **kwargs):
    raise requests.ConnectionError("Max retries exceeded with url: /search?engine=google_hotels&api_key=secret-key")


def test_a_failed_search_is_printed_without_the_key(committing_db, monkeypatch, capsys):
    monkeypatch.setattr(hotels_collector, "SERPAPI_KEY", "secret-key")
    monkeypatch.setattr(hotels_collector, "fetch_searches_left", lambda: 250)
    monkeypatch.setattr(hotels_collector.requests, "get", failing_get)
    monkeypatch.setattr(hotels_collector.fetch_hotels.retry, "sleep", lambda seconds: None)

    counts = hotels_collector.main(max_searches=1)

    out = capsys.readouterr().out
    assert counts["errors"] == 1
    assert "ERROR fetching" in out
    assert "secret-key" not in out


# Not caught by main(): Lambda logs the traceback, the chained original error included.
def test_a_failed_quota_check_raises_without_the_key(monkeypatch):
    monkeypatch.setattr(hotels_collector, "SERPAPI_KEY", "secret-key")
    monkeypatch.setattr(hotels_collector.requests, "get", failing_get)

    with pytest.raises(requests.ConnectionError) as failure:
        hotels_collector.fetch_searches_left()

    assert "secret-key" not in str(failure.value)
    assert failure.value.__cause__ is None and failure.value.__suppress_context__

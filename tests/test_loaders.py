import datetime
import uuid

from etl.loaders import load_destinations_seed
from etl.loaders.cleanup_old_flights import cleanup_old_flights
from etl.loaders.cleanup_old_hotels import cleanup_old_hotels
from etl.loaders.cleanup_old_searches import cleanup_old_searches
from tests.factories import add_flight, add_hotel, add_saved_search


def active_iata_codes(cur):
    cur.execute("SELECT iata_code FROM destinations WHERE is_active ORDER BY iata_code")
    return [row["iata_code"] for row in cur.fetchall()]


def test_a_destination_removed_from_the_seed_is_deactivated_and_comes_back_when_re_added(cur, tmp_path, monkeypatch):
    full_seed = load_destinations_seed.SEED_PATH
    smaller_seed = tmp_path / "destinations_seed.csv"
    smaller_seed.write_text(
        "city_name,iata_code,city_name_he\nBarcelona,BCN,ברצלונה\nRome,FCO,רומא\n", encoding="utf-8"
    )
    cur.execute("SELECT count(*) AS n FROM destinations")
    n_destinations = cur.fetchone()["n"]

    monkeypatch.setattr(load_destinations_seed, "SEED_PATH", smaller_seed)
    load_destinations_seed.load_destinations(cur)

    assert active_iata_codes(cur) == ["BCN", "FCO"]
    cur.execute("SELECT count(*) AS n FROM destinations")
    assert cur.fetchone()["n"] == n_destinations

    monkeypatch.setattr(load_destinations_seed, "SEED_PATH", full_seed)
    load_destinations_seed.load_destinations(cur)

    assert len(active_iata_codes(cur)) == n_destinations


def test_cleanup_deletes_flights_that_returned_over_three_months_ago(cur):
    today = datetime.date.today()
    add_flight(cur, "BCN", today - datetime.timedelta(days=107), today - datetime.timedelta(days=100), 300)
    add_flight(cur, "BCN", today - datetime.timedelta(days=67), today - datetime.timedelta(days=60), 300)

    assert cleanup_old_flights(cur) == 1
    cur.execute("SELECT return_date FROM flight_price_observations")
    assert [r["return_date"] for r in cur.fetchall()] == [today - datetime.timedelta(days=60)]


def test_cleanup_deletes_hotel_prices_not_refreshed_in_three_months(cur):
    add_hotel(cur, "BCN", avg_usd=100)
    add_hotel(cur, "FCO", avg_usd=100)
    cur.execute(
        "UPDATE hotel_prices SET loaded_at = now() - interval '100 days'"
        " WHERE destination_id = (SELECT destination_id FROM destinations WHERE iata_code = 'BCN')"
    )

    assert cleanup_old_hotels(cur) == 1
    cur.execute("SELECT d.iata_code FROM hotel_prices JOIN destinations AS d USING (destination_id)")
    assert [r["iata_code"] for r in cur.fetchall()] == ["FCO"]


def test_cleanup_deletes_searches_older_than_30_days_with_their_results(cur):
    session_id = str(uuid.uuid4())
    old = add_saved_search(cur, session_id)
    recent = add_saved_search(cur, session_id)
    cur.execute("UPDATE search_queries SET created_at = now() - interval '31 days' WHERE search_query_id = %s", (old,))

    assert cleanup_old_searches(cur) == 1
    cur.execute("SELECT DISTINCT search_query_id FROM search_results WHERE search_query_id IN (%s, %s)", (old, recent))
    assert [r["search_query_id"] for r in cur.fetchall()] == [recent]

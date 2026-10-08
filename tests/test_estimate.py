# Characterization tests for estimate_all_destinations: they lock in its
# current behavior (see AGENTS.md for why each rule exists) so later refactors
# - the FastAPI move in particular - can't change it silently.

import datetime

import pytest

from app.queries import MAX_DATE_DRIFT_DAYS, estimate_all_destinations
from tests.factories import add_flight, add_hotel

DEPART = datetime.date(2030, 6, 1)
RETURN = datetime.date(2030, 6, 8)  # 7 nights


def days(n):
    return datetime.timedelta(days=n)


def estimate(cur, budget_usd=None, hotel_tier="average"):
    return estimate_all_destinations(cur, "TLV", DEPART, RETURN, budget_usd, hotel_tier)


def cities(estimates):
    return [r["city_name"] for r in estimates]


# --- date matching -----------------------------------------------------------


def test_flight_within_drift_window_is_matched_beyond_it_is_missing(cur):
    assert MAX_DATE_DRIFT_DAYS == 4
    add_flight(cur, "BCN", DEPART + days(4), RETURN + days(4), price_usd=300)
    add_flight(cur, "MAD", DEPART + days(5), RETURN, price_usd=300)
    add_flight(cur, "FCO", DEPART, RETURN - days(5), price_usd=300)
    for city in ("barcelona", "madrid", "rome"):
        add_hotel(cur, city, avg_usd=100)

    estimates, _ = estimate(cur)

    assert cities(estimates) == ["Barcelona"]


def test_nearest_date_pair_wins_over_cheaper_farther_one(cur):
    add_flight(cur, "BCN", DEPART + days(1), RETURN + days(1), price_usd=500)  # total drift 2
    add_flight(cur, "BCN", DEPART + days(2), RETURN + days(2), price_usd=100)  # total drift 4
    add_hotel(cur, "barcelona", avg_usd=100)

    estimates, _ = estimate(cur)

    assert estimates[0]["flight_total_usd"] == 500


def test_same_dates_use_most_recent_observation(cur):
    older = datetime.datetime(2030, 1, 1, tzinfo=datetime.UTC)
    newer = datetime.datetime(2030, 1, 2, tzinfo=datetime.UTC)
    add_flight(cur, "BCN", DEPART, RETURN, price_usd=400, observed_at=older)
    add_flight(cur, "BCN", DEPART, RETURN, price_usd=350, observed_at=newer)
    add_hotel(cur, "barcelona", avg_usd=100)

    estimates, _ = estimate(cur)

    assert estimates[0]["flight_total_usd"] == 350


def test_same_dates_prefer_the_most_recently_seen_price(cur):
    # Collected later but seen earlier loses to collected earlier but seen later:
    # what counts is when the price was actually quoted, not when we fetched it.
    fetched_later = datetime.datetime(2030, 1, 2, tzinfo=datetime.UTC)
    fetched_earlier = datetime.datetime(2030, 1, 1, tzinfo=datetime.UTC)
    add_flight(cur, "BCN", DEPART, RETURN, price_usd=400,
               observed_at=fetched_later, price_seen_on=datetime.date(2029, 12, 20))
    add_flight(cur, "BCN", DEPART, RETURN, price_usd=350,
               observed_at=fetched_earlier, price_seen_on=datetime.date(2029, 12, 30))
    add_hotel(cur, "barcelona", avg_usd=100)

    estimates, _ = estimate(cur)

    assert estimates[0]["flight_total_usd"] == 350


def test_any_exact_match_drops_every_approximate_one(cur):
    add_flight(cur, "BCN", DEPART, RETURN, price_usd=300)
    add_flight(cur, "MAD", DEPART + days(1), RETURN, price_usd=100)
    add_hotel(cur, "barcelona", avg_usd=100)
    add_hotel(cur, "madrid", avg_usd=100)

    estimates, _ = estimate(cur)

    assert cities(estimates) == ["Barcelona"]


def test_no_exact_match_falls_back_to_nearest_for_everyone(cur):
    add_flight(cur, "BCN", DEPART + days(1), RETURN, price_usd=300)
    add_flight(cur, "MAD", DEPART, RETURN + days(2), price_usd=100)
    add_hotel(cur, "barcelona", avg_usd=100)
    add_hotel(cur, "madrid", avg_usd=100)

    estimates, _ = estimate(cur)

    assert sorted(cities(estimates)) == ["Barcelona", "Madrid"]


# --- missing data vs. filtering ----------------------------------------------


def test_no_data_at_all_reports_missing_data(cur):
    assert estimate(cur) == ([], True)


def test_flight_without_hotel_is_not_viable(cur):
    add_flight(cur, "BCN", DEPART, RETURN, price_usd=300)

    assert estimate(cur) == ([], True)


def test_over_budget_is_not_reported_as_missing_data(cur):
    add_flight(cur, "BCN", DEPART, RETURN, price_usd=300)
    add_hotel(cur, "barcelona", avg_usd=100)

    assert estimate(cur, budget_usd=500) == ([], False)


def test_budget_is_inclusive(cur):
    add_flight(cur, "BCN", DEPART, RETURN, price_usd=300)
    add_hotel(cur, "barcelona", avg_usd=100)  # 300 + 7 * 100 = 1000

    estimates, _ = estimate(cur, budget_usd=1000)

    assert cities(estimates) == ["Barcelona"]


def test_exact_match_over_budget_falls_back_to_approximate_within_budget(cur):
    # Current behavior: the exact-date rule runs after the budget filter, so an
    # over-budget exact match no longer counts as "an exact match exists".
    add_flight(cur, "BCN", DEPART, RETURN, price_usd=2000)
    add_flight(cur, "MAD", DEPART + days(1), RETURN, price_usd=100)
    add_hotel(cur, "barcelona", avg_usd=100)
    add_hotel(cur, "madrid", avg_usd=100)

    estimates, _ = estimate(cur, budget_usd=1000)

    assert cities(estimates) == ["Madrid"]


# --- cost calculation --------------------------------------------------------


def test_hotel_nights_follow_matched_flight_not_request(cur):
    add_flight(cur, "BCN", DEPART + days(1), RETURN - days(1), price_usd=300)  # 5 nights
    add_hotel(cur, "barcelona", avg_usd=100)

    row = estimate(cur)[0][0]

    assert row["matched_nights"] == 5
    assert row["hotel_total_usd"] == 500
    assert row["total_estimate_usd"] == 800


def test_results_sorted_by_total_cost(cur):
    add_flight(cur, "BCN", DEPART, RETURN, price_usd=900)
    add_flight(cur, "MAD", DEPART, RETURN, price_usd=100)
    add_flight(cur, "FCO", DEPART, RETURN, price_usd=500)
    for city in ("barcelona", "madrid", "rome"):
        add_hotel(cur, city, avg_usd=100)

    estimates, _ = estimate(cur)

    assert cities(estimates) == ["Madrid", "Rome", "Barcelona"]


@pytest.mark.parametrize(("tier", "per_night"), [("budget", 60), ("average", 100), ("luxury", 250)])
def test_hotel_tier_picks_its_own_price(cur, tier, per_night):
    add_flight(cur, "BCN", DEPART, RETURN, price_usd=300)
    add_hotel(cur, "barcelona", avg_usd=100, budget_usd=60, luxury_usd=250)

    row = estimate(cur, hotel_tier=tier)[0][0]

    assert row["hotel_price_per_night_usd"] == per_night


def test_tier_missing_from_small_sample_is_missing_data_not_average(cur):
    add_flight(cur, "BCN", DEPART, RETURN, price_usd=300)
    add_hotel(cur, "barcelona", avg_usd=100, budget_usd=None, luxury_usd=None, sample_size=5)

    assert estimate(cur, hotel_tier="luxury") == ([], True)
    assert cities(estimate(cur, hotel_tier="average")[0]) == ["Barcelona"]


def test_unknown_hotel_tier_is_rejected(cur):
    with pytest.raises(ValueError):
        estimate(cur, hotel_tier="premium")


def test_unknown_airline_code_keeps_the_row(cur):
    add_flight(cur, "BCN", DEPART, RETURN, price_usd=300, airline_code="H3")
    add_hotel(cur, "barcelona", avg_usd=100)

    row = estimate(cur)[0][0]

    assert row["airline_code"] == "H3"
    assert row["airline_name"] is None

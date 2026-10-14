# Characterization tests for estimate_all_destinations: they lock in its
# current behavior (see AGENTS.md for why each rule exists) so later refactors
# - the FastAPI move in particular - can't change it silently.

import datetime

import pytest

from app.queries import (
    HOTEL_TIERS,
    MAX_DATE_DRIFT_DAYS,
    estimate_all_destinations,
    estimate_all_tiers,
)
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
    for iata in ("BCN", "MAD", "FCO"):
        add_hotel(cur, iata, avg_usd=100)

    estimates, _ = estimate(cur)

    assert cities(estimates) == ["Barcelona"]


def test_nearest_date_pair_wins_over_cheaper_farther_one(cur):
    add_flight(cur, "BCN", DEPART + days(1), RETURN + days(1), price_usd=500)  # total drift 2
    add_flight(cur, "BCN", DEPART + days(2), RETURN + days(2), price_usd=100)  # total drift 4
    add_hotel(cur, "BCN", avg_usd=100)

    estimates, _ = estimate(cur)

    assert estimates[0]["flight_total_usd"] == 500


def test_same_dates_use_most_recent_observation(cur):
    older = datetime.datetime(2030, 1, 1, tzinfo=datetime.UTC)
    newer = datetime.datetime(2030, 1, 2, tzinfo=datetime.UTC)
    add_flight(cur, "BCN", DEPART, RETURN, price_usd=400, observed_at=older)
    add_flight(cur, "BCN", DEPART, RETURN, price_usd=350, observed_at=newer)
    add_hotel(cur, "BCN", avg_usd=100)

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
    add_hotel(cur, "BCN", avg_usd=100)

    estimates, _ = estimate(cur)

    assert estimates[0]["flight_total_usd"] == 350


def test_any_exact_match_drops_every_approximate_one(cur):
    add_flight(cur, "BCN", DEPART, RETURN, price_usd=300)
    add_flight(cur, "MAD", DEPART + days(1), RETURN, price_usd=100)
    add_hotel(cur, "BCN", avg_usd=100)
    add_hotel(cur, "MAD", avg_usd=100)

    estimates, _ = estimate(cur)

    assert cities(estimates) == ["Barcelona"]


def test_no_exact_match_falls_back_to_nearest_for_everyone(cur):
    add_flight(cur, "BCN", DEPART + days(1), RETURN, price_usd=300)
    add_flight(cur, "MAD", DEPART, RETURN + days(2), price_usd=100)
    add_hotel(cur, "BCN", avg_usd=100)
    add_hotel(cur, "MAD", avg_usd=100)

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
    add_hotel(cur, "BCN", avg_usd=100)

    assert estimate(cur, budget_usd=500) == ([], False)


def test_budget_is_inclusive(cur):
    add_flight(cur, "BCN", DEPART, RETURN, price_usd=300)
    add_hotel(cur, "BCN", avg_usd=100)  # 300 + 7 * 100 = 1000

    estimates, _ = estimate(cur, budget_usd=1000)

    assert cities(estimates) == ["Barcelona"]


def test_exact_match_over_budget_falls_back_to_approximate_within_budget(cur):
    # Current behavior: the exact-date rule runs after the budget filter, so an
    # over-budget exact match no longer counts as "an exact match exists".
    add_flight(cur, "BCN", DEPART, RETURN, price_usd=2000)
    add_flight(cur, "MAD", DEPART + days(1), RETURN, price_usd=100)
    add_hotel(cur, "BCN", avg_usd=100)
    add_hotel(cur, "MAD", avg_usd=100)

    estimates, _ = estimate(cur, budget_usd=1000)

    assert cities(estimates) == ["Madrid"]


# --- cost calculation --------------------------------------------------------


def test_hotel_nights_follow_matched_flight_not_request(cur):
    add_flight(cur, "BCN", DEPART + days(1), RETURN - days(1), price_usd=300)  # 5 nights
    add_hotel(cur, "BCN", avg_usd=100)

    row = estimate(cur)[0][0]

    assert row["matched_nights"] == 5
    assert row["hotel_total_usd"] == 500
    assert row["total_estimate_usd"] == 800


def test_results_sorted_by_total_cost(cur):
    add_flight(cur, "BCN", DEPART, RETURN, price_usd=900)
    add_flight(cur, "MAD", DEPART, RETURN, price_usd=100)
    add_flight(cur, "FCO", DEPART, RETURN, price_usd=500)
    for iata in ("BCN", "MAD", "FCO"):
        add_hotel(cur, iata, avg_usd=100)

    estimates, _ = estimate(cur)

    assert cities(estimates) == ["Madrid", "Rome", "Barcelona"]


@pytest.mark.parametrize(("tier", "per_night"), [("budget", 60), ("average", 100), ("luxury", 250)])
def test_hotel_tier_picks_its_own_price(cur, tier, per_night):
    add_flight(cur, "BCN", DEPART, RETURN, price_usd=300)
    add_hotel(cur, "BCN", avg_usd=100, budget_usd=60, luxury_usd=250)

    row = estimate(cur, hotel_tier=tier)[0][0]

    assert row["hotel_price_per_night_usd"] == per_night


def test_tier_missing_from_small_sample_is_missing_data_not_average(cur):
    add_flight(cur, "BCN", DEPART, RETURN, price_usd=300)
    add_hotel(cur, "BCN", avg_usd=100, budget_usd=None, luxury_usd=None, sample_size=5)

    assert estimate(cur, hotel_tier="luxury") == ([], True)
    assert cities(estimate(cur, hotel_tier="average")[0]) == ["Barcelona"]


def test_unknown_hotel_tier_is_rejected(cur):
    with pytest.raises(ValueError):
        estimate(cur, hotel_tier="premium")


def test_unknown_airline_code_keeps_the_row(cur):
    add_flight(cur, "BCN", DEPART, RETURN, price_usd=300, airline_code="H3")
    add_hotel(cur, "BCN", avg_usd=100)

    row = estimate(cur)[0][0]

    assert row["airline_code"] == "H3"
    assert row["airline_name"] is None


# --- all tiers at once (estimate_all_tiers) ----------------------------------


def test_each_tier_matches_estimating_that_tier_alone(cur):
    add_flight(cur, "BCN", DEPART, RETURN, price_usd=300)
    add_flight(cur, "MAD", DEPART + days(1), RETURN, price_usd=200)
    add_flight(cur, "FCO", DEPART, RETURN, price_usd=900)
    add_hotel(cur, "BCN", avg_usd=100, budget_usd=60, luxury_usd=250)
    add_hotel(cur, "MAD", avg_usd=80, budget_usd=None, luxury_usd=None, sample_size=5)
    add_hotel(cur, "FCO", avg_usd=120, budget_usd=70, luxury_usd=300)

    all_tiers = estimate_all_tiers(cur, "TLV", DEPART, RETURN, 2500)

    for tier in HOTEL_TIERS:
        assert all_tiers[tier] == estimate(cur, budget_usd=2500, hotel_tier=tier)


def test_tiers_get_their_own_budget_and_missing_data_verdicts(cur):
    add_flight(cur, "BCN", DEPART, RETURN, price_usd=300)
    add_hotel(cur, "BCN", avg_usd=100, budget_usd=60, luxury_usd=None, sample_size=5)

    all_tiers = estimate_all_tiers(cur, "TLV", DEPART, RETURN, budget_amount_usd=800)

    assert cities(all_tiers["budget"][0]) == ["Barcelona"]  # 300 + 7 * 60 = 720
    assert all_tiers["average"] == ([], False)  # 300 + 7 * 100 = 1000, over budget
    assert all_tiers["luxury"] == ([], True)  # no luxury price on file


# --- several flights for the same dates (ROADMAP 2.5.1) ----------------------
# One trip can have many flights (the collector's cheapest per date pair over
# time, and every option a live destination view returned): each flight counts
# at its latest-seen price, only the flights seen on the trip's newest seen-on
# day are kept - newer over cheaper, decided 2026-10-12 - and the cheapest of
# those wins.

SEEN = datetime.date(2030, 5, 20)


def test_cheapest_of_several_flights_seen_the_same_day(cur):
    add_flight(cur, "BCN", DEPART, RETURN, price_usd=559, airline_code="LY", price_seen_on=SEEN)
    add_flight(cur, "BCN", DEPART, RETURN, price_usd=176, airline_code="W4", price_seen_on=SEEN)
    add_hotel(cur, "BCN", avg_usd=100)

    row = estimate(cur)[0][0]

    assert (row["airline_code"], row["flight_total_usd"]) == ("W4", 176)


def test_newer_flight_wins_over_a_cheaper_one_seen_a_day_earlier(cur):
    # The collector gets only the cheapest flight per date pair: a pricier one
    # seen later means the cheaper one most likely left the cache.
    add_flight(cur, "BCN", DEPART, RETURN, price_usd=400, airline_code="LY", price_seen_on=SEEN)
    add_flight(cur, "BCN", DEPART, RETURN, price_usd=150, airline_code="W4", price_seen_on=SEEN - days(1))
    add_hotel(cur, "BCN", avg_usd=100)

    row = estimate(cur)[0][0]

    assert (row["airline_code"], row["flight_total_usd"]) == ("LY", 400)


def test_when_every_price_is_old_the_newest_of_them_is_still_shown(cur):
    # Measured from the trip's newest price, not from today.
    add_flight(cur, "BCN", DEPART, RETURN, price_usd=400, airline_code="LY", price_seen_on=SEEN - days(90))
    add_flight(cur, "BCN", DEPART, RETURN, price_usd=300, airline_code="W4", price_seen_on=SEEN - days(90))
    add_flight(cur, "BCN", DEPART, RETURN, price_usd=200, airline_code="U2", price_seen_on=SEEN - days(92))
    add_hotel(cur, "BCN", avg_usd=100)

    assert estimate(cur)[0][0]["airline_code"] == "W4"


def test_rows_without_a_seen_date_use_the_day_we_collected_them(cur):
    collected = datetime.datetime(2030, 5, 1, tzinfo=datetime.UTC)
    add_flight(cur, "BCN", DEPART, RETURN, price_usd=150, airline_code="W4", observed_at=collected)
    add_flight(cur, "BCN", DEPART, RETURN, price_usd=400, airline_code="LY", price_seen_on=SEEN)
    add_hotel(cur, "BCN", avg_usd=100)

    # Collected 2030-05-01, before the newest price: dropped.
    assert estimate(cur)[0][0]["airline_code"] == "LY"


def test_nearest_dates_still_come_before_price_and_freshness(cur):
    add_flight(cur, "BCN", DEPART, RETURN, price_usd=500, airline_code="LY", price_seen_on=SEEN - days(3))
    add_flight(cur, "BCN", DEPART + days(1), RETURN, price_usd=100, airline_code="W4", price_seen_on=SEEN)
    add_hotel(cur, "BCN", avg_usd=100)

    assert estimate(cur)[0][0]["airline_code"] == "LY"


def test_offers_for_the_same_flight_seen_the_same_day_take_the_cheapest(cur):
    # Same airline, stops and times at two prices on one seen-on day: two
    # offers, not a price change. Stored at different moments (a second view
    # can add the pricier one later), the later one used to win.
    stored_first = datetime.datetime(2030, 5, 20, 10, tzinfo=datetime.UTC)
    stored_later = datetime.datetime(2030, 5, 20, 11, tzinfo=datetime.UTC)
    add_flight(cur, "BCN", DEPART, RETURN, price_usd=290, airline_code="GQ",
               price_seen_on=SEEN, observed_at=stored_first)
    add_flight(cur, "BCN", DEPART, RETURN, price_usd=376, airline_code="GQ",
               price_seen_on=SEEN, observed_at=stored_later)
    add_hotel(cur, "BCN", avg_usd=100)

    assert estimate(cur)[0][0]["flight_total_usd"] == 290

# One budget search (POST /api/v1/estimates):
# the budget converted to USD, every hotel tier estimated, the search logged
# for /history, and all amounts converted to the currency the budget was
# entered in.

from dataclasses import dataclass

from app.queries import estimate_all_tiers, insert_search_query, insert_search_results
from etl.common.currency import from_usd, get_usd_per_unit, to_usd


@dataclass
class TierResult:
    estimates: list[dict]
    has_missing_data: bool
    exact_dates_only: bool


@dataclass
class SearchOutcome:
    search_query_id: int
    display_currency: str
    budget_amount_display: float | None
    budget_amount_usd: float | None
    tiers: dict[str, TierResult]


def run_search(
    cur, session_id, origin_iata, depart_date, return_date, budget_amount, budget_currency, hotel_tier,
    travelers=1, rooms=1,
):
    usd_per_unit = _usd_per_unit_or_none(cur, budget_currency)
    # Without a rate the budget can't be compared in USD: the search still
    # runs, unfiltered by budget, but its results aren't saved to /history.
    budget_amount_usd = to_usd(budget_amount, usd_per_unit) if usd_per_unit else None

    per_tier = estimate_all_tiers(cur, origin_iata, depart_date, return_date, budget_amount_usd, travelers, rooms)
    exact = {tier: _exact_dates_only(estimates, depart_date, return_date) for tier, (estimates, _) in per_tier.items()}

    # Only the tier the user picked is saved; the other two are there to switch to.
    search_query_id = insert_search_query(
        cur, session_id, origin_iata, depart_date, return_date,
        budget_amount, budget_currency, hotel_tier, exact[hotel_tier], travelers, rooms,
    )
    if budget_amount_usd is not None:
        insert_search_results(cur, search_query_id, per_tier[hotel_tier][0], budget_amount_usd)

    if usd_per_unit is not None:
        display_currency, budget_amount_display = budget_currency, budget_amount
    else:
        # No rate on file: show the underlying USD amounts rather than fail.
        display_currency, usd_per_unit, budget_amount_display = "USD", 1.0, None

    return SearchOutcome(
        search_query_id=search_query_id,
        display_currency=display_currency,
        budget_amount_display=budget_amount_display,
        budget_amount_usd=budget_amount_usd,
        tiers={
            tier: TierResult(
                estimates=[_with_display_amounts(e, usd_per_unit) for e in estimates],
                has_missing_data=has_missing_data,
                exact_dates_only=exact[tier],
            )
            for tier, (estimates, has_missing_data) in per_tier.items()
        },
    )


# The currency a saved search is shown in, and its rate: the one it was made
# in, or USD when no rate is on file for it.
def display_currency_and_rate(cur, currency):
    try:
        return currency, get_usd_per_unit(cur, currency)
    except ValueError:
        return "USD", 1.0


def _usd_per_unit_or_none(cur, currency):
    try:
        return get_usd_per_unit(cur, currency)
    except ValueError:
        return None


# estimate_all_tiers returns either all-exact or all-approximate rows for a
# tier, never a mix, so the first row speaks for all of them.
def _exact_dates_only(estimates, depart_date, return_date):
    return bool(estimates) and (
        estimates[0]["flight_out_date"] == depart_date and estimates[0]["flight_return_date"] == return_date
    )


def _with_display_amounts(estimate, usd_per_unit):
    return {
        **estimate,
        "flight_price_amount": from_usd(estimate["flight_price_usd"], usd_per_unit),
        "flight_total_amount": from_usd(estimate["flight_total_usd"], usd_per_unit),
        "hotel_total_amount": from_usd(estimate["hotel_total_usd"], usd_per_unit),
        "total_estimate_amount": from_usd(estimate["total_estimate_usd"], usd_per_unit),
    }

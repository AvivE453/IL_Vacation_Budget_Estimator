import datetime

from flask import Blueprint, render_template, request

from app.db import get_cursor
from app.queries import HOTEL_TIERS, estimate_all_destinations, insert_search_query, insert_search_results
from app.session_id import get_session_id
from etl.common.currency import from_usd, get_usd_per_unit, to_usd

bp = Blueprint("estimate", __name__)


# Core budget-estimate flow: ranks destinations, logs the search, renders results.
@bp.route("/estimate", methods=["POST"])
def estimate():
    origin_iata = request.form["origin_iata"]
    depart_date = datetime.date.fromisoformat(request.form["depart_date"])
    return_date = datetime.date.fromisoformat(request.form["return_date"])
    budget_amount = float(request.form["budget_amount"])
    budget_currency = request.form.get("budget_currency", "ILS").upper()
    hotel_tier = request.form.get("hotel_tier", "average")
    if hotel_tier not in HOTEL_TIERS:
        return f"hotel_tier must be one of {HOTEL_TIERS}", 400

    if return_date <= depart_date:
        return "return_date must be after depart_date", 400

    with get_cursor() as cur:
        try:
            usd_per_unit = get_usd_per_unit(cur, budget_currency)
        except ValueError:
            usd_per_unit = None
        # Without a rate the budget can't be compared in USD: the search still
        # runs, unfiltered by budget, but its results aren't saved to /history.
        budget_amount_usd = to_usd(budget_amount, usd_per_unit) if usd_per_unit else None

        estimates, has_missing_data = estimate_all_destinations(
            cur, origin_iata, depart_date, return_date, budget_amount_usd, hotel_tier
        )
        # estimate_all_destinations returns either all-exact or all-approximate
        # rows, never a mix.
        exact_dates_only = bool(estimates) and (
            estimates[0]["flight_out_date"] == depart_date and estimates[0]["flight_return_date"] == return_date
        )

        search_query_id = insert_search_query(
            cur, get_session_id(), origin_iata, depart_date, return_date,
            budget_amount, budget_currency, hotel_tier, exact_dates_only,
        )
        if budget_amount_usd is not None:
            insert_search_results(cur, search_query_id, estimates, budget_amount_usd)

    # Results are displayed in whatever currency the user picked for
    # their budget - everything is still stored/ranked in USD
    if usd_per_unit is not None:
        display_currency = budget_currency
        # Already in budget_currency as entered - no conversion needed,
        # and avoids introducing USD-round-trip rounding noise.
        budget_amount_display = budget_amount
    else:
        # No exchange rate on file for budget_currency - fall back to
        # showing the underlying USD amounts rather than failing the page.
        display_currency, usd_per_unit = "USD", 1.0
        budget_amount_display = budget_amount_usd
    display_estimates = [
        {
            **e,
            "flight_total_amount": from_usd(e["flight_total_usd"], usd_per_unit),
            "hotel_total_amount": from_usd(e["hotel_total_usd"], usd_per_unit),
            "total_estimate_amount": from_usd(e["total_estimate_usd"], usd_per_unit),
        }
        for e in estimates
    ]

    return render_template(
        "results.html",
        estimates=display_estimates,
        has_missing_data=has_missing_data,
        exact_dates_only=exact_dates_only,
        display_currency=display_currency,
        budget_amount_display=budget_amount_display,
        hotel_tier=hotel_tier,
        origin_iata=origin_iata,
        depart_date=depart_date,
        return_date=return_date,
        nights=(return_date - depart_date).days,
        budget_amount=budget_amount,
        budget_currency=budget_currency,
        budget_amount_usd=budget_amount_usd,
        search_query_id=search_query_id,
    )

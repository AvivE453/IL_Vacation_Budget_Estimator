import datetime

from flask import Blueprint, render_template, request

from app.db import get_cursor
from app.queries import HOTEL_TIERS
from app.search import run_search
from app.session_id import get_session_id

bp = Blueprint("estimate", __name__)


# Core budget-estimate flow: ranks destinations, logs the search, renders
# the chosen hotel tier's results.
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
        search = run_search(
            cur, get_session_id(), origin_iata, depart_date, return_date,
            budget_amount, budget_currency, hotel_tier,
        )
    chosen = search.tiers[hotel_tier]

    return render_template(
        "results.html",
        estimates=chosen.estimates,
        has_missing_data=chosen.has_missing_data,
        exact_dates_only=chosen.exact_dates_only,
        display_currency=search.display_currency,
        budget_amount_display=search.budget_amount_display,
        hotel_tier=hotel_tier,
        origin_iata=origin_iata,
        depart_date=depart_date,
        return_date=return_date,
        nights=(return_date - depart_date).days,
        budget_amount=budget_amount,
        budget_currency=budget_currency,
        budget_amount_usd=search.budget_amount_usd,
        search_query_id=search.search_query_id,
    )

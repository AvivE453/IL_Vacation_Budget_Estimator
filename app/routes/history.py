from flask import Blueprint, abort, render_template

from app.db import get_cursor
from app.queries import get_recent_searches, get_search_results
from app.session_id import get_session_id
from etl.common.currency import from_usd, get_usd_per_unit

bp = Blueprint("history", __name__)


# List of this browser session's past searches.
@bp.route("/history")
def index():
    with get_cursor() as cur:
        searches = get_recent_searches(cur, get_session_id())
    return render_template("history.html", searches=searches)


# Ranked destinations saved from one past search.
@bp.route("/history/<int:search_query_id>")
def show(search_query_id):
    with get_cursor() as cur:
        results = get_search_results(cur, search_query_id, get_session_id())
        if not results:
            abort(404)

        # Display in the currency that search was originally made in
        display_currency = results[0]["budget_currency"]
        exact_dates_only = results[0]["exact_dates_only"]
        try:
            usd_per_unit = get_usd_per_unit(cur, display_currency)
        except ValueError:
            # No exchange rate on file for that currency - fall back to
            # showing the underlying USD amounts rather than failing the page.
            display_currency, usd_per_unit = "USD", 1.0

    results =[{**r, "estimated_total_amount": from_usd(r["estimated_total_usd"], usd_per_unit)} for r in results]

    return render_template(
        "history_detail.html",
        results=results,
        search_query_id=search_query_id,
        display_currency=display_currency,
        exact_dates_only=exact_dates_only,
    )

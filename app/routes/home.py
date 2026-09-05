import datetime

from flask import Blueprint, render_template

from app.db import get_cursor
from app.queries import count_active_destinations, list_origin_airports

bp = Blueprint("home", __name__)


# Search form - origin airports, destination count, default dates.
@bp.route("/")
def index():
    with get_cursor() as cur:
        origins = list_origin_airports(cur)
        destination_count = count_active_destinations(cur)

    # Depart date defaults to today (recomputed on every page load, not a
    # fixed date baked into the template) - return date is 7 nights later.
    default_depart = datetime.date.today()
    default_return = default_depart + datetime.timedelta(days=7)

    return render_template(
        "index.html",
        origins=origins,
        destination_count=destination_count,
        default_depart_date=default_depart.isoformat(),
        default_return_date=default_return.isoformat(),
        min_return_date=(default_depart + datetime.timedelta(days=1)).isoformat(),
    )

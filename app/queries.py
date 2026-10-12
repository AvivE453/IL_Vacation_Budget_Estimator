import psycopg2.extras

# Travelpayouts' prices_for_dates is a cache of real-user searches, not an
# exact-date lookup - it rarely has data for the exact dates requested. So
# the nearest observed date pair within this many days is used instead of an
# exact match. beyond that, it's treated as missing data.
MAX_DATE_DRIFT_DAYS = 4

# A quote stays in that cache for about a week. A flight's price seen more
# than this many days before the newest price for the same trip has most
# likely left it - it's no longer a price anyone can get.
FRESHNESS_DAYS = 7

# A destination's date grid spans this many days either side of the requested
# departure and return dates: 7 x 7 date pairs.
DATE_GRID_DAYS = 3

# The flights a trip can use, shared by estimate_all_destinations and
# get_collected_flight_options so the ranking and the destination view pick
# the same flight. For each destination, within MAX_DATE_DRIFT_DAYS of the
# requested dates:
#   1. each distinct flight (airline, stops, times) once, at the price seen
#      most recently - an older price for the same flight is outdated. Those
#      four don't pin down one offer (the same times can come with another
#      connection or fare), so on the same seen-on day the cheapest wins;
#   2. only flights whose price was seen within FRESHNESS_DAYS of the newest
#      price for the same trip. Measured from that newest price, not from
#      today: the collector runs by hand, so a quiet fortnight would
#      otherwise empty every result. An old price drops out only when the
#      same trip has a price more than FRESHNESS_DAYS newer.
# Callers then pick the nearest dates and, among those, the cheapest.
_FRESH_FLIGHTS_CTES = """
    flight_candidates AS (
        SELECT f.*,
               ABS(f.depart_date - %(depart_date)s) + ABS(f.return_date - %(return_date)s) AS date_drift,
               -- Rows from before price_seen_on existed: the day we collected
               -- them, the latest they can have been seen.
               COALESCE(f.price_seen_on, f.observed_at::date) AS seen_on
        FROM flight_price_observations AS f
        WHERE f.origin_iata = %(origin_iata)s
          -- Sargable BETWEEN so idx_flight_obs_depart_date can narrow this
          -- scan; return_date isn't indexed.
          AND f.depart_date BETWEEN %(depart_date)s - %(max_drift)s AND %(depart_date)s + %(max_drift)s
          AND ABS(f.return_date - %(return_date)s) <= %(max_drift)s
    ),
    latest_per_flight AS (
        SELECT DISTINCT ON (destination_id, depart_date, return_date,
                            airline_code, number_of_stops, depart_time, return_time)
               *,
               MAX(seen_on) OVER (PARTITION BY destination_id, depart_date, return_date) AS trip_newest_seen_on
        FROM flight_candidates
        -- Same flight seen on the same day at two prices: two offers (a
        -- different connection or fare), not a price change - the cheaper one.
        ORDER BY destination_id, depart_date, return_date,
                 airline_code, number_of_stops, depart_time, return_time,
                 seen_on DESC, price_amount_usd, observed_at DESC
    ),
    fresh_flights AS (
        SELECT *
        FROM latest_per_flight
        WHERE seen_on >= trip_newest_seen_on - %(freshness_days)s
    )
"""


def _fresh_flights_params(origin_iata, depart_date, return_date):
    return {
        "origin_iata": origin_iata,
        "depart_date": depart_date,
        "return_date": return_date,
        "max_drift": MAX_DATE_DRIFT_DAYS,
        "freshness_days": FRESHNESS_DAYS,
    }


def list_origin_airports(cur):
    cur.execute(
        """
        SELECT a.iata_code, a.airport_name, a.city_name
        FROM airports AS a
        WHERE a.country_code = 'IL'
        ORDER BY a.iata_code
        """
    )
    return cur.fetchall()


def count_active_destinations(cur):
    cur.execute("SELECT COUNT(*) AS n FROM destinations WHERE is_active")
    return cur.fetchone()["n"]


HOTEL_TIERS = ("budget", "average", "luxury")


# For every active destination, finds the nearest-dated flight and its
# hotel price. matched_nights/hotel cost use the matched flight's own
# dates, not the requested nights - date-matching doesn't preserve trip length.
#
# Global exact/approximate rule: if any destination got an exact date
# match, only exact matches are returned; only if none did, falls back to
# nearest-available dates for everyone.
#
# hotel_tier picks budget/average/luxury pricing. NULL when a city's
# sample was too small to split into tiers - real missing data, not a
# fallback average.
#
# Returns (estimates, has_missing_data): estimates is the viable destinations
# (flight + hotel both on file, within budget if given); has_missing_data is
# True only when NOT ONE active destination has both a flight and a hotel on
# file - i.e. the dataset itself came up empty for these dates, before budget
# or exact-date filtering ever ran. That's the distinction the caller needs
# when estimates ends up empty: "genuinely no data" (this flag is True) vs
# "we had candidates, your budget or the exact-date rule excluded them all"
# (this flag is False). It is NOT "some destination is missing data" - with 45
# destinations that would be True almost always, and useless to act on.
def estimate_all_destinations(cur, origin_iata, depart_date, return_date, budget_amount_usd=None, hotel_tier="average"):
    if hotel_tier not in HOTEL_TIERS:
        raise ValueError(f"hotel_tier must be one of {HOTEL_TIERS}, got {hotel_tier!r}")
    rows = _priced_candidates(cur, origin_iata, depart_date, return_date, [hotel_tier])
    return _apply_estimate_rules(rows, depart_date, return_date, budget_amount_usd)


# Same rules as estimate_all_destinations, for every hotel tier from one
# query: {tier: (estimates, has_missing_data)}. Each tier gets its own
# missing-data, budget and exact-date verdicts, since a tier's price decides
# all three.
def estimate_all_tiers(cur, origin_iata, depart_date, return_date, budget_amount_usd=None):
    rows = _priced_candidates(cur, origin_iata, depart_date, return_date, list(HOTEL_TIERS))
    return {
        tier: _apply_estimate_rules(
            [r for r in rows if r["hotel_tier"] == tier], depart_date, return_date, budget_amount_usd
        )
        for tier in HOTEL_TIERS
    }


# One row per active destination per requested hotel tier, cheapest first.
#
# Uses WITH (CTEs) purely for readability over nested subqueries - on
# Postgres 16 a single-use CTE inlines the same way no performance difference.
#
# LEFT JOIN, not JOIN, in the scored CTE below: a destination with no
# matching flight/hotel must still appear (as NULL) so flight_data_missing/
# hotel_data_missing can actually be computed for it. Filtering on those
# flags (and on budget) happens in Python (_apply_estimate_rules), not in
# this SQL, precisely so the missing-data rows survive long enough to be counted.
def _priced_candidates(cur, origin_iata, depart_date, return_date, hotel_tiers):
    cur.execute(
        f"""
        WITH {_FRESH_FLIGHTS_CTES},
        latest_flight AS (
            SELECT DISTINCT ON (destination_id)
                destination_id, price_amount_usd AS flight_total_usd,
                depart_date AS flight_out_date, return_date AS flight_return_date,
                depart_time AS flight_out_time, return_time AS flight_return_time,
                airline_code, seen_on AS flight_seen_on
            FROM fresh_flights
            -- The nearest dates; among their flights, the cheapest.
            ORDER BY destination_id, date_drift, price_amount_usd,
                     price_seen_on DESC NULLS LAST, observed_at DESC
        ),
        tiers AS (
            SELECT unnest(%(hotel_tiers)s::text[]) AS hotel_tier
        ),
        hotel_pick AS (
            SELECT
                hp.city_name_normalized,
                t.hotel_tier,
                CASE t.hotel_tier
                    WHEN 'budget' THEN hp.avg_price_budget_tier_usd
                    WHEN 'luxury' THEN hp.avg_price_luxury_tier_usd
                    ELSE hp.avg_price_per_night_usd
                END AS hotel_price_per_night_usd,
                CURRENT_DATE - hp.loaded_at::date AS hotel_price_age_days
            FROM hotel_prices AS hp
            CROSS JOIN tiers AS t
        ),
        scored AS (
            SELECT
                d.destination_id, d.city_name, d.city_name_he,
                t.hotel_tier,
                lf.flight_total_usd,
                lf.flight_out_date,
                lf.flight_return_date,
                lf.flight_out_time,
                lf.flight_return_time,
                (lf.flight_return_date - lf.flight_out_date) AS matched_nights,
                lf.airline_code,
                al.airline_name,
                lf.flight_seen_on,
                hpk.hotel_price_age_days,
                hpk.hotel_price_per_night_usd,
                hpk.hotel_price_per_night_usd * (lf.flight_return_date - lf.flight_out_date)
                    AS hotel_total_usd,
                lf.flight_total_usd
                    + hpk.hotel_price_per_night_usd * (lf.flight_return_date - lf.flight_out_date)
                    AS total_estimate_usd,
                (lf.flight_total_usd IS NULL) AS flight_data_missing,
                (hpk.hotel_price_per_night_usd IS NULL) AS hotel_data_missing
            -- Every destination once per tier, so a city with no hotel price
            -- still shows up (as missing) under each tier.
            FROM destinations AS d
            CROSS JOIN tiers AS t
            LEFT JOIN latest_flight AS lf ON lf.destination_id = d.destination_id
            LEFT JOIN airlines AS al ON al.airline_code = lf.airline_code
            LEFT JOIN hotel_pick AS hpk
                ON hpk.city_name_normalized = d.hotel_data_city_key AND hpk.hotel_tier = t.hotel_tier
            WHERE d.is_active
        )
        SELECT *
        FROM scored
        ORDER BY total_estimate_usd ASC
        """,
        {**_fresh_flights_params(origin_iata, depart_date, return_date), "hotel_tiers": hotel_tiers},
    )
    return cur.fetchall()


# The Python half of the estimate rules, for one tier's rows.
def _apply_estimate_rules(rows, depart_date, return_date, budget_amount_usd):
    viable = [r for r in rows if not r["flight_data_missing"] and not r["hotel_data_missing"]]
    # True only when NOT ONE active destination has both a flight and a hotel
    # match at all. This is what lets an empty result be told apart from
    # budget/exact-date filtering, where viable is non-empty but every
    # candidate in it still gets excluded downstream.
    #
    # Must stay ABOVE the budget filter below: computing it afterwards would
    # make every over-budget search look like missing data.
    has_missing_data = len(viable) == 0
    if budget_amount_usd is not None:
        viable = [r for r in viable if r["total_estimate_usd"] <= budget_amount_usd]

    # If any destination got an exact date match, keep only exact matches;
    # otherwise fall back to everyone's nearest-available date.
    exact_matches = [
        r for r in viable
        if r["flight_out_date"] == depart_date and r["flight_return_date"] == return_date
    ]
    return (exact_matches if exact_matches else viable), has_missing_data


# Logs one search into search_queries; returns its id for insert_search_results
# and the /history "saved ranking" link.
def insert_search_query(
    cur, session_id, origin_iata, depart_date, return_date, budget_amount, budget_currency,
    hotel_tier="average", exact_dates_only=None,
):
    cur.execute(
        """
        INSERT INTO search_queries
            (session_id, origin_iata, depart_date, return_date,
             budget_amount, budget_currency, hotel_tier, exact_dates_only)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
        RETURNING search_query_id
        """,
        (
            session_id, origin_iata, depart_date, return_date,
            budget_amount, budget_currency, hotel_tier, exact_dates_only,
        ),
    )
    return cur.fetchone()["search_query_id"]


# Logs one search_results row per destination estimate - cost rank,
# within-budget flag, and airline, all frozen for the saved ranking (GET /api/v1/searches/{id}).
def insert_search_results(cur, search_query_id, estimates, budget_amount_usd):
    ranked = sorted(
        (e for e in estimates if e["total_estimate_usd"] is not None),
        key=lambda e: e["total_estimate_usd"],
    )
    rank_by_destination = {e["destination_id"]: i + 1 for i, e in enumerate(ranked)}

    rows = [
        (
            search_query_id,
            e["destination_id"],
            e["flight_total_usd"],
            e["hotel_total_usd"],
            e["total_estimate_usd"],
            e["total_estimate_usd"] is not None and float(e["total_estimate_usd"]) <= budget_amount_usd,
            rank_by_destination.get(e["destination_id"]),
            e["airline_code"],
        )
        for e in estimates
    ]
    # One multi-row INSERT for every destination instead of one per row.
    psycopg2.extras.execute_values(
        cur,
        """
        INSERT INTO search_results
            (search_query_id, destination_id, estimated_flight_usd, estimated_hotel_usd,
             estimated_total_usd, within_budget, rank_by_cost, airline_code)
        VALUES %s
        """,
        rows,
        template="(%s, %s, %s, %s, %s, %s, %s, (SELECT airline_code FROM airlines WHERE airline_code = %s))",
    )


# Scoped to one anonymous browser session - there are no user accounts,
# so this is the only thing that keeps /history from mixing every visitor's 
# searches together.
def get_recent_searches(cur, session_id, limit=20):
    cur.execute(
        """
        SELECT search_query_id, origin_iata, depart_date, return_date,
               budget_amount, budget_currency, hotel_tier, created_at
        FROM search_queries
        WHERE session_id = %s
        ORDER BY created_at DESC
        LIMIT %s
        """,
        (session_id, limit),
    )
    return cur.fetchall()


# One past search's own parameters, or None if it isn't this session's.
# Separate from get_search_results so a search that saved no results (every
# destination over budget) still exists rather than looking like a 404.
def get_search(cur, search_query_id, session_id):
    cur.execute(
        """
        SELECT search_query_id, origin_iata, depart_date, return_date,
               budget_amount, budget_currency, hotel_tier, exact_dates_only, created_at
        FROM search_queries
        WHERE search_query_id = %s
          AND session_id = %s
        """,
        (search_query_id, session_id),
    )
    return cur.fetchone()


# ranked alternatives within budget for a past search, shown
# in the original search's budget_currency. Scoped to session_id like
# get_recent_searches: ids are sequential, so without it any browser could
# read any other browser's search just by changing the number in the URL.
def get_search_results(cur, search_query_id, session_id):
    cur.execute(
        """
        SELECT sr.destination_id, d.city_name, d.city_name_he, sr.estimated_total_usd, sr.within_budget,
               sq.budget_currency, sq.hotel_tier, sq.exact_dates_only, al.airline_name, sr.airline_code,
               RANK() OVER (ORDER BY sr.estimated_total_usd ASC) AS cost_rank
        FROM search_results AS sr
        JOIN destinations AS d ON d.destination_id = sr.destination_id
        JOIN search_queries AS sq ON sq.search_query_id = sr.search_query_id
        LEFT JOIN airlines AS al ON al.airline_code = sr.airline_code
        WHERE sr.search_query_id = %s
          AND sq.session_id = %s
        ORDER BY cost_rank
        """,
        (search_query_id, session_id),
    )
    return cur.fetchall()


def list_active_destinations(cur):
    cur.execute(
        """
        SELECT d.destination_id, d.city_name, c.country_name, d.city_name_he, c.country_name_he, d.iata_code
        FROM destinations AS d
        JOIN countries AS c ON c.country_code = d.country_code
        WHERE d.is_active
        ORDER BY d.city_name
        """
    )
    return cur.fetchall()


# One active destination with its hotel prices per tier (NULL when not on
# file), or None if there's no such active destination.
def get_destination(cur, destination_id):
    cur.execute(
        """
        SELECT d.destination_id, d.city_name, c.country_name, d.city_name_he, c.country_name_he, d.iata_code,
               hp.avg_price_budget_tier_usd AS hotel_budget_per_night_usd,
               hp.avg_price_per_night_usd AS hotel_average_per_night_usd,
               hp.avg_price_luxury_tier_usd AS hotel_luxury_per_night_usd,
               CURRENT_DATE - hp.loaded_at::date AS hotel_price_age_days
        FROM destinations AS d
        JOIN countries AS c ON c.country_code = d.country_code
        LEFT JOIN hotel_prices AS hp ON hp.city_name_normalized = d.hotel_data_city_key
        WHERE d.destination_id = %s
          AND d.is_active
        """,
        (destination_id,),
    )
    return cur.fetchone()


# The collected flight options for one destination on the date pair nearest
# the request, cheapest first - the same flights, by the same rules, that
# estimate_all_destinations chooses from, so its pick is the first row here.
# Empty beyond MAX_DATE_DRIFT_DAYS.
def get_collected_flight_options(cur, origin_iata, destination_id, depart_date, return_date):
    cur.execute(
        f"""
        WITH {_FRESH_FLIGHTS_CTES},
        destination_flights AS (
            SELECT *
            FROM fresh_flights
            WHERE destination_id = %(destination_id)s
        ),
        nearest_pair AS (
            SELECT depart_date, return_date
            FROM destination_flights
            ORDER BY date_drift, price_amount_usd, price_seen_on DESC NULLS LAST, observed_at DESC
            LIMIT 1
        )
        SELECT df.depart_date, df.return_date, df.airline_code, al.airline_name, df.number_of_stops,
               df.depart_time, df.return_time, df.price_amount_usd, df.price_seen_on
        FROM destination_flights AS df
        JOIN nearest_pair AS n ON n.depart_date = df.depart_date AND n.return_date = df.return_date
        LEFT JOIN airlines AS al ON al.airline_code = df.airline_code
        ORDER BY df.price_amount_usd, df.price_seen_on DESC NULLS LAST, df.observed_at DESC
        """,
        {**_fresh_flights_params(origin_iata, depart_date, return_date), "destination_id": destination_id},
    )
    return cur.fetchall()


# The cheapest flight for every date pair within `days` of the requested
# dates, for one destination, by the same freshness rules as the ranking - so
# the cell at the requested dates is the flight an exact-match estimate picks.
# Only pairs with a flight on file: an absent pair is missing data.
def get_date_grid(cur, origin_iata, destination_id, depart_date, return_date, days=DATE_GRID_DAYS):
    cur.execute(
        f"""
        WITH {_FRESH_FLIGHTS_CTES}
        SELECT depart_date, return_date, MIN(price_amount_usd) AS flight_price_usd
        FROM fresh_flights
        WHERE destination_id = %(destination_id)s
        GROUP BY depart_date, return_date
        ORDER BY depart_date, return_date
        """,
        {
            **_fresh_flights_params(origin_iata, depart_date, return_date),
            # The grid's span replaces the ranking's drift window.
            "max_drift": days,
            "destination_id": destination_id,
        },
    )
    return cur.fetchall()


# Every option a live destination view returned, as new observations. Same
# skip-what's-stored rule as the collector (no ON CONFLICT target: covers
# uq_flight_obs and uq_flight_obs_price_seen), so showing the same trip again
# adds nothing. Returns how many rows were new.
def insert_live_flight_observations(cur, destination_id, origin_iata, destination_iata, options):
    rows = [
        (
            destination_id, origin_iata, destination_iata, o["depart_date"], o["return_date"],
            o["depart_time"], o["return_time"], o["price_usd"], o["price_usd"],
            o["outbound_stops"], o["airline_code"], o["price_seen_on"],
        )
        for o in options
    ]
    if not rows:
        return 0
    # One statement for all rows: execute_values otherwise pages by 100, and
    # rowcount would then cover only the last page.
    psycopg2.extras.execute_values(
        cur,
        """
        INSERT INTO flight_price_observations
            (destination_id, origin_iata, destination_iata, depart_date, return_date,
             depart_time, return_time, price_amount, price_amount_usd,
             number_of_stops, airline_code, price_seen_on, currency_code, source)
        VALUES %s
        ON CONFLICT DO NOTHING
        """,
        rows,
        template="(%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, 'USD', 'live_search')",
        page_size=len(rows),
    )
    return cur.rowcount


def get_airline_names(cur, airline_codes):
    cur.execute(
        "SELECT airline_code, airline_name FROM airlines WHERE airline_code = ANY(%s)",
        (list(airline_codes),),
    )
    return {r["airline_code"]: r["airline_name"] for r in cur.fetchall()}


# per-destination observation coverage + missing-data flags
# across both integrated sources.
def get_data_quality_report(cur):
    cur.execute(
        """
        SELECT
            d.city_name, c.country_name, d.city_name_he, c.country_name_he,
            (SELECT COUNT(*)
             FROM flight_price_observations AS f
             WHERE f.destination_id = d.destination_id) AS flight_obs_count,
            hp.sample_size AS hotel_sample_size,
            -- hotel_prices is one refreshed snapshot per city, not a time
            -- series, so its age is the only sign of how stale a price is.
            CURRENT_DATE - hp.loaded_at::date AS hotel_price_age_days
        FROM destinations AS d
        JOIN countries AS c ON c.country_code = d.country_code
        LEFT JOIN hotel_prices AS hp ON hp.city_name_normalized = d.hotel_data_city_key
        WHERE d.is_active
        -- In the order the Hebrew page shows them; Unicode puts Hebrew letters in alphabetical order.
        ORDER BY COALESCE(d.city_name_he, d.city_name)
        """
    )
    return cur.fetchall()


# daily collection volume, justifies the "realistic data volume" claim.
# The collector's rows and those stored from users' destination views are
# counted apart: only the first is the scheduled collection.
def get_collection_volume(cur):
    cur.execute(
        """
        SELECT observed_at::date AS day,
               COUNT(*) FILTER (WHERE source = 'collector') AS observations_collected,
               COUNT(*) FILTER (WHERE source = 'live_search') AS observations_from_searches
        FROM flight_price_observations
        GROUP BY 1
        ORDER BY 1
        """
    )
    return cur.fetchall()

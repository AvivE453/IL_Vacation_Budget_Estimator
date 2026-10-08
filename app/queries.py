import psycopg2.extras

# Travelpayouts' prices_for_dates is a cache of real-user searches, not an
# exact-date lookup - it rarely has data for the exact dates requested. So
# the nearest observed date pair within this many days is used instead of an
# exact match. beyond that, it's treated as missing data.
MAX_DATE_DRIFT_DAYS = 4


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
#
# Uses WITH (CTEs) purely for readability over nested subqueries - on
# Postgres 16 a single-use CTE inlines the same way no performance difference.
#
# LEFT JOIN, not JOIN, in the scored CTE below: a destination with no
# matching flight/hotel must still appear (as NULL) so flight_data_missing/
# hotel_data_missing can actually be computed for it. Filtering on those
# flags (and on budget) happens in Python below, not in this SQL, precisely
# so the missing-data rows survive long enough to be counted.
def estimate_all_destinations(cur, origin_iata, depart_date, return_date, budget_amount_usd=None, hotel_tier="average"):
    if hotel_tier not in HOTEL_TIERS:
        raise ValueError(f"hotel_tier must be one of {HOTEL_TIERS}, got {hotel_tier!r}")
    cur.execute(
        """
        WITH latest_flight AS (
            SELECT DISTINCT ON (destination_id)
                destination_id, price_amount_usd AS flight_total_usd,
                depart_date AS flight_out_date, return_date AS flight_return_date,
                depart_time AS flight_out_time, return_time AS flight_return_time,
                airline_code
            FROM flight_price_observations
            WHERE origin_iata = %(origin_iata)s
              -- Sargable BETWEEN so idx_flight_obs_depart_date can narrow this
              -- scan; return_date and the ORDER BY below aren't indexed.
              AND depart_date BETWEEN %(depart_date)s - %(max_drift)s AND %(depart_date)s + %(max_drift)s
              AND ABS(return_date - %(return_date)s) <= %(max_drift)s
            -- Ties on date drift go to the price seen most recently by a real
            -- search; rows from before price_seen_on existed fall back to
            -- when we collected them.
            ORDER BY destination_id,
                     ABS(depart_date - %(depart_date)s) + ABS(return_date - %(return_date)s),
                     price_seen_on DESC NULLS LAST,
                     observed_at DESC
        ),
        hotel_pick AS (
            SELECT
                city_name_normalized,
                CASE %(hotel_tier)s
                    WHEN 'budget' THEN avg_price_budget_tier_usd
                    WHEN 'luxury' THEN avg_price_luxury_tier_usd
                    ELSE avg_price_per_night_usd
                END AS hotel_price_per_night_usd
            FROM hotel_prices
        ),
        scored AS (
            SELECT
                d.destination_id, d.city_name,
                lf.flight_total_usd,
                lf.flight_out_date,
                lf.flight_return_date,
                lf.flight_out_time,
                lf.flight_return_time,
                (lf.flight_return_date - lf.flight_out_date) AS matched_nights,
                lf.airline_code,
                al.airline_name,
                hpk.hotel_price_per_night_usd,
                hpk.hotel_price_per_night_usd * (lf.flight_return_date - lf.flight_out_date)
                    AS hotel_total_usd,
                lf.flight_total_usd
                    + hpk.hotel_price_per_night_usd * (lf.flight_return_date - lf.flight_out_date)
                    AS total_estimate_usd,
                (lf.flight_total_usd IS NULL) AS flight_data_missing,
                (hpk.hotel_price_per_night_usd IS NULL) AS hotel_data_missing
            FROM destinations AS d
            LEFT JOIN latest_flight AS lf ON lf.destination_id = d.destination_id
            LEFT JOIN airlines AS al ON al.airline_code = lf.airline_code
            LEFT JOIN hotel_pick AS hpk ON hpk.city_name_normalized = d.hotel_data_city_key
            WHERE d.is_active
        )
        SELECT *
        FROM scored
        ORDER BY total_estimate_usd ASC
        """,
        {
            "origin_iata": origin_iata,
            "depart_date": depart_date,
            "return_date": return_date,
            "max_drift": MAX_DATE_DRIFT_DAYS,
            "hotel_tier": hotel_tier,
        },
    )
    rows = cur.fetchall()

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
# within-budget flag, and airline, all frozen for the /history/<id> saved ranking.
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


# ranked alternatives within budget for a past search, shown
# in the original search's budget_currency. Scoped to session_id like
# get_recent_searches: ids are sequential, so without it any browser could
# read any other browser's search just by changing the number in the URL.
def get_search_results(cur, search_query_id, session_id):
    cur.execute(
        """
        SELECT sr.destination_id, d.city_name, sr.estimated_total_usd, sr.within_budget,
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


# per-destination observation coverage + missing-data flags
# across both integrated sources.
def get_data_quality_report(cur):
    cur.execute(
        """
        SELECT
            d.city_name, c.country_name,
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
        ORDER BY d.city_name ASC
        """
    )
    return cur.fetchall()


# daily collection volume, justifies the "realistic data volume" claim.
def get_collection_volume(cur):
    cur.execute(
        """
        SELECT date_trunc('day', observed_at) AS day, COUNT(*) AS observations_collected
        FROM flight_price_observations
        GROUP BY 1
        ORDER BY 1
        """
    )
    return cur.fetchall()

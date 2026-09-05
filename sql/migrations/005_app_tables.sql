-- Logs real app usage: every /estimate request writes one search_queries row;
-- N search_results rows (one per viable destination) follow only if the
-- entered budget currency converted to USD. This gives a natural multi-table
-- join for the /history page without needing user accounts.

CREATE TABLE search_queries (
    search_query_id            BIGSERIAL PRIMARY KEY,
    -- Anonymous per-browser id (signed session cookie, see app/session_id.py)
    -- so /history shows only the current browser's searches -- no login,
    -- no users table. NULL rows predate this column and match no session.
    session_id                  TEXT,
    origin_iata                 CHAR(3) NOT NULL REFERENCES airports(iata_code),
    depart_date                DATE NOT NULL,
    return_date                DATE NOT NULL,
    budget_amount              NUMERIC(10,2) NOT NULL CHECK (budget_amount > 0),
    budget_currency             CHAR(3) NOT NULL DEFAULT 'ILS',
    -- Which hotel_prices column (budget/average/luxury tier -- see
    -- app/queries.py::HOTEL_TIERS and sql/migrations/003_hotel_prices.sql)
    -- this search's estimate was based on, so /history reflects what was
    -- actually searched rather than assuming everything used one default.
    hotel_tier                 TEXT NOT NULL DEFAULT 'average'
        CHECK (hotel_tier IN ('budget', 'average', 'luxury')),
    -- Whether estimate_all_destinations found an exact depart/return date
    -- match for this search (vs falling back to nearest-available dates for
    -- everyone) -- so /history/<id> can disclose the same precision caveat
    -- shown at search time, not just the saved prices with no context.
    -- NULL for rows predating this column: precision at the time is unknown.
    exact_dates_only           BOOLEAN,
    created_at                 TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT chk_search_queries_return_after_depart CHECK (return_date > depart_date)
);

CREATE TABLE search_results (
    search_result_id             BIGSERIAL PRIMARY KEY,
    search_query_id               BIGINT NOT NULL REFERENCES search_queries(search_query_id) ON DELETE CASCADE,
    destination_id                 INTEGER NOT NULL REFERENCES destinations(destination_id),
    estimated_flight_usd          NUMERIC(10,2),
    estimated_hotel_usd           NUMERIC(10,2),
    estimated_total_usd           NUMERIC(10,2),
    within_budget                 BOOLEAN,
    rank_by_cost                  SMALLINT,
    airline_code                  VARCHAR(3) REFERENCES airlines(airline_code)
);

-- Used by get_search_results (/history/<id>) to fetch one search's saved
-- ranking, and by ON DELETE CASCADE above when a search_queries row is deleted.
CREATE INDEX idx_search_results_query ON search_results(search_query_id);

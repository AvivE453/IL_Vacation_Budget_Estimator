-- Append-only flight price observations. Rows are never upserted/overwritten:
-- retaining every snapshot is what lets estimate_all_destinations match the
-- nearest available date per search, and get_collection_volume/
-- get_data_quality_report report real coverage over time.

CREATE TABLE flight_price_observations (
    observation_id      BIGSERIAL PRIMARY KEY,
    destination_id       INTEGER NOT NULL REFERENCES destinations(destination_id),
    origin_iata          CHAR(3) NOT NULL REFERENCES airports(iata_code),
    destination_iata     CHAR(3) NOT NULL REFERENCES airports(iata_code),
    depart_date          DATE NOT NULL,
    return_date          DATE,
    -- Local wall-clock time per leg (UTC offset not kept). Nullable - older
    -- rows simply have no time-of-day on file.
    depart_time          TIME,
    return_time          TIME,
    price_amount         NUMERIC(10,2) NOT NULL CHECK (price_amount > 0),
    currency_code        CHAR(3) NOT NULL,
    price_amount_usd     NUMERIC(10,2) NOT NULL CHECK (price_amount_usd > 0),
    number_of_stops      SMALLINT CHECK (number_of_stops >= 0),
    airline_code         VARCHAR(3),
    observed_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT chk_return_after_depart CHECK (return_date IS NULL OR return_date > depart_date),
    CONSTRAINT uq_flight_obs UNIQUE (destination_id, origin_iata, depart_date, return_date, observed_at, airline_code, number_of_stops)
);


-- Used by estimate_all_destinations's latest_flight CTE to find flights near
-- the requested dates -- the core query behind every /estimate request.
CREATE INDEX idx_flight_obs_depart_date ON flight_price_observations(depart_date);

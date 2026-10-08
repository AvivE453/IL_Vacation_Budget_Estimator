-- When an Aviasales user actually saw each cached price, as opposed to
-- observed_at, which is only when our collector fetched it. The cache keeps
-- prices for about a week, so repeated collector runs fetch the same quote
-- again; this is what tells a genuinely new price from a re-fetched one.
-- NULL for rows collected before this column existed, and whenever the
-- source link carries no search_date.
ALTER TABLE flight_price_observations ADD COLUMN price_seen_on DATE;

-- One row per price actually seen: the same trip, quoted at the same price
-- on the same day, is not stored again by a later run. NULLS NOT DISTINCT so
-- a missing airline or stop count still counts as "the same trip". Rows
-- without price_seen_on can't be told apart, so they're left out.
CREATE UNIQUE INDEX uq_flight_obs_price_seen
    ON flight_price_observations
       (destination_id, origin_iata, depart_date, return_date, airline_code,
        number_of_stops, price_amount_usd, price_seen_on)
    NULLS NOT DISTINCT
    WHERE price_seen_on IS NOT NULL;

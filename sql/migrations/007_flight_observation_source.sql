-- Flight prices now come from two places: the scheduled collector (a month at
-- a time, so only the cheapest round trip per date pair) and a user's
-- destination view (exact dates, so every option). Recording which keeps
-- the daily collection volume from mixing the two. Every existing row came
-- from the collector.
ALTER TABLE flight_price_observations
    ADD COLUMN source TEXT NOT NULL DEFAULT 'collector'
        CHECK (source IN ('collector', 'live_search'));

-- Neither duplicate check could tell apart the many options an exact-date
-- search returns, so one save dropped some of them as "already stored":
-- they left out the flight times, and uq_flight_obs also the price - one
-- live answer for TLV-BCN had GQ 23:30/22:45 at both $290 and $376 (another
-- connection or fare). A wider key can only treat fewer rows as duplicates,
-- so neither change can conflict with rows already stored.
ALTER TABLE flight_price_observations
    DROP CONSTRAINT uq_flight_obs,
    ADD CONSTRAINT uq_flight_obs
        UNIQUE (destination_id, origin_iata, depart_date, return_date, observed_at,
                airline_code, number_of_stops, depart_time, return_time, price_amount_usd);

DROP INDEX uq_flight_obs_price_seen;
CREATE UNIQUE INDEX uq_flight_obs_price_seen
    ON flight_price_observations
       (destination_id, origin_iata, depart_date, return_date, airline_code,
        number_of_stops, depart_time, return_time, price_amount_usd, price_seen_on)
    NULLS NOT DISTINCT
    WHERE price_seen_on IS NOT NULL;

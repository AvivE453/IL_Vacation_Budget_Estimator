-- Every flight price now carries the day it was seen. The rows collected
-- before price_seen_on existed (36,120, 2026-07-23..10-07) are deleted rather
-- than kept on a fallback: they were ~40% re-fetched copies of the same cached
-- quotes, and keeping them meant every query had to treat "seen on" as
-- COALESCE(price_seen_on, observed_at). Most were past trips; future trips
-- went 12,509 -> 11,292.
DELETE FROM flight_price_observations WHERE price_seen_on IS NULL;

ALTER TABLE flight_price_observations ALTER COLUMN price_seen_on SET NOT NULL;

-- One duplicate rule instead of two. The old uq_flight_obs included
-- observed_at, so it only caught a duplicate within one run; the partial
-- index uq_flight_obs_price_seen caught a price an earlier run had stored,
-- but only for rows with price_seen_on - now all of them. NULLS NOT DISTINCT
-- so a missing airline, stop count or time still counts as the same flight.
ALTER TABLE flight_price_observations DROP CONSTRAINT uq_flight_obs;
DROP INDEX uq_flight_obs_price_seen;
ALTER TABLE flight_price_observations
    ADD CONSTRAINT uq_flight_obs UNIQUE NULLS NOT DISTINCT
        (destination_id, origin_iata, depart_date, return_date, airline_code,
         number_of_stops, depart_time, return_time, price_amount_usd, price_seen_on);

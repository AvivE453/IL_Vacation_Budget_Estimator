-- Stops on the way back. number_of_stops was only ever the outbound leg
-- (Travelpayouts' `transfers`); its `return_transfers` wasn't kept, so a trip
-- with a stop on the return leg passed "direct flights only". NULL on rows
-- collected before this: the API answer they came from is gone.
--
-- Not part of uq_flight_obs: two offers that differ only in return stops would
-- also need the same airline, times and price, and adding it would make every
-- quote already stored (NULL) look new the next time a run sees it.
ALTER TABLE flight_price_observations
    ADD COLUMN return_stops SMALLINT CHECK (return_stops >= 0);

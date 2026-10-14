-- A destination's country is its airport's (destinations.iata_code ->
-- airports.country_code), so storing it again here was a transitive
-- dependency (a 3NF violation): nothing kept the two copies equal. They
-- matched for all 103 destinations when this was dropped.
--
-- uq_destinations_city_country kept one destination per city; without the
-- country, the city name alone does that. Two same-named cities would need
-- distinct names (as "Luxembourg City" already has).
ALTER TABLE destinations
    DROP CONSTRAINT uq_destinations_city_country,
    DROP COLUMN country_code,
    ADD CONSTRAINT uq_destinations_city UNIQUE (city_name);

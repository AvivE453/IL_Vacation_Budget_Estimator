-- Crosswalk table: resolves the two source systems' incompatible identifiers
-- (IATA airport code for flights, free-text city name for hotels) to one
-- internal destination_id.

CREATE TABLE destinations (
    destination_id              SERIAL PRIMARY KEY,
    city_name                   TEXT NOT NULL,
    country_code                CHAR(2) NOT NULL REFERENCES countries(country_code),
    iata_code                   CHAR(3) NOT NULL UNIQUE REFERENCES airports(iata_code),
    -- Join key into hotel_prices.city_name_normalized, lowercase (e.g. "rome").
    -- Cities with no match are real missing data, surfaced via LEFT JOIN, not hidden.
    hotel_data_city_key         TEXT NOT NULL,
    is_active                   BOOLEAN NOT NULL DEFAULT TRUE,
    created_at                  TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT uq_destinations_city_country UNIQUE (city_name, country_code),
    CONSTRAINT chk_hotel_data_city_key_lower CHECK (hotel_data_city_key = lower(hotel_data_city_key))
);

-- Reference/lookup tables: countries, airports, airlines, exchange_rates.
-- These hold generic, reusable reference data.

CREATE TABLE countries (
    country_code   CHAR(2) PRIMARY KEY,
    country_name   TEXT NOT NULL UNIQUE
);

CREATE TABLE airports (
    iata_code      CHAR(3) PRIMARY KEY,
    airport_name   TEXT NOT NULL,
    city_name      TEXT NOT NULL,
    country_code   CHAR(2) NOT NULL REFERENCES countries(country_code),
    latitude       NUMERIC(9,6),
    longitude      NUMERIC(9,6)
);

-- IATA airline code -> display name (etl/loaders/load_airlines.py, from
-- Travelpayouts' public reference). No FK from flight_price_observations 
-- an unrecognized code just falls back to the raw code in the UI.
CREATE TABLE airlines (
    airline_code   VARCHAR(3) PRIMARY KEY,
    airline_name   TEXT NOT NULL,
    is_lowcost     BOOLEAN NOT NULL DEFAULT false
);

-- Currency normalization: 1 unit of currency_code = usd_per_unit USD.
CREATE TABLE exchange_rates (
    currency_code  CHAR(3) PRIMARY KEY,
    usd_per_unit   NUMERIC(14,8) NOT NULL CHECK (usd_per_unit > 0),
    as_of_date     DATE NOT NULL,
    updated_at     TIMESTAMPTZ NOT NULL DEFAULT now()
);

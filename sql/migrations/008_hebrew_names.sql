-- Hebrew names for the Israeli-facing frontend, beside the English ones: those
-- stay, since the outside APIs are queried with them (SerpApi searches
-- "<city_name> hotels"). Filled from the seed CSVs by load_airports and
-- load_destinations_seed; nullable so a destination added without one still
-- loads, and the frontend falls back to the English name.
ALTER TABLE countries ADD COLUMN country_name_he TEXT;
ALTER TABLE destinations ADD COLUMN city_name_he TEXT;

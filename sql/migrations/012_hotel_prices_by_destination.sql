-- hotel_prices now references its destination by id, like the flights do,
-- instead of by a normalized city-name text key. The text key dates from the
-- static-CSV hotel source, whose rows had no destination_id and had to be
-- matched by name; the SerpApi collector prices one destination at a time, so
-- it knows the id when it writes. The FK now rejects a price for a destination
-- that doesn't exist, where a misspelled key used to match nothing, silently.
--
-- One row per destination, so destination_id is the primary key and the
-- unused hotel_price_id goes. When this ran, all 103 rows matched a
-- destination; a row that matched none was unreachable by any query anyway.
ALTER TABLE hotel_prices ADD COLUMN destination_id INTEGER REFERENCES destinations(destination_id);

UPDATE hotel_prices AS hp
SET destination_id = d.destination_id
FROM destinations AS d
WHERE d.hotel_data_city_key = hp.city_name_normalized;

DELETE FROM hotel_prices WHERE destination_id IS NULL;

ALTER TABLE hotel_prices
    DROP COLUMN hotel_price_id,
    DROP COLUMN city_name_normalized,
    ADD PRIMARY KEY (destination_id);

-- Its CHECK (lowercase) goes with it.
ALTER TABLE destinations DROP COLUMN hotel_data_city_key;

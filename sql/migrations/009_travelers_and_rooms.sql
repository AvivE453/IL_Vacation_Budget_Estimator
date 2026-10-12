-- How many people a search was for, and how many hotel rooms: the estimate is
-- every traveler's flight plus every room's nights. Searches saved before this
-- were priced for one traveler in one room, which the defaults record.
ALTER TABLE search_queries
    ADD COLUMN travelers SMALLINT NOT NULL DEFAULT 1 CHECK (travelers BETWEEN 1 AND 9),
    ADD COLUMN rooms SMALLINT NOT NULL DEFAULT 1 CHECK (rooms BETWEEN 1 AND 9),
    ADD CONSTRAINT chk_rooms_not_above_travelers CHECK (rooms <= travelers);

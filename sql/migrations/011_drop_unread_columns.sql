-- Two columns that were written but never read.
--
-- search_results.rank_by_cost: derived data. get_search_results recomputes
-- the rank from estimated_total_usd (RANK() OVER ...), so the stored copy
-- could only drift from it - and did differ on ties (Python numbered them
-- 1,2,3; RANK() gives 1,2,2). Matched on all 2,753 rows when dropped.
--
-- hotel_prices.city_name_raw: left over from the static-CSV loader, whose
-- scraped spellings ("Roma") needed keeping beside the normalized key. SerpApi
-- is queried with destinations.city_name, which it always equaled.
ALTER TABLE search_results DROP COLUMN rank_by_cost;
ALTER TABLE hotel_prices DROP COLUMN city_name_raw;

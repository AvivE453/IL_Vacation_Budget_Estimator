-- within_budget was true on every row: a search saves only the destinations
-- left after its budget filter (app/search.py), so none can be over budget.
-- The saved-search page showed it as a column that could only say yes.
ALTER TABLE search_results DROP COLUMN within_budget;

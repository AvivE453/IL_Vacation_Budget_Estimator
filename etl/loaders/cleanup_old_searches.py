# Deletes search_queries rows (and their search_results, via ON DELETE
# CASCADE) older than RETENTION_DAYS, so /history keeps the last 30 days.
# That's also the session cookie's lifetime (SESSION_MAX_AGE in api/deps.py),
# counted from the last visit: a browser that stayed away that long has a new
# session and can't reach its old rows anyway, while one that keeps coming
# back sees only its own last 30 days.
#
# Run with: uv run python -m etl.loaders.cleanup_old_searches

from etl.common.db import get_conn

RETENTION_DAYS = 30


def cleanup_old_searches(cur):
    cur.execute(
        "DELETE FROM search_queries WHERE created_at < now() - (interval '1 day' * %s)",
        (RETENTION_DAYS,),
    )
    return cur.rowcount


def main():
    with get_conn() as conn:
        with conn.cursor() as cur:
            n = cleanup_old_searches(cur)
    print(f"deleted {n} search_queries older than {RETENTION_DAYS} days (search_results cascaded)")


if __name__ == "__main__":
    main()

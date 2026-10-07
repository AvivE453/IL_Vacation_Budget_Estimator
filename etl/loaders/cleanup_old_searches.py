# Deletes search_queries rows (and their search_results, via ON DELETE
# CASCADE) older than RETENTION_DAYS. RETENTION_DAYS matches the session
# cookie's own lifetime (app/main.py) - once a session that old has expired,
# its rows are unreachable from any browser forever, so keeping them is dead weight.
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

# Deletes hotel_prices rows whose loaded_at is more than RETENTION_MONTHS
# in the past. Since hotel_prices is one row per city (upserted, not
# append-only), this removes that city's price entirely rather than pruning
# history - it goes back to hotel_data_missing until re-collected. A price
# nobody has refreshed in 3+ months is more likely to mislead than help.
#
# Run with: uv run python -m etl.loaders.cleanup_old_hotels

from etl.common.db import get_conn

RETENTION_MONTHS = 3


def cleanup_old_hotels(cur):
    cur.execute(
        "DELETE FROM hotel_prices WHERE loaded_at < now() - (interval '1 month' * %s)",
        (RETENTION_MONTHS,),
    )
    return cur.rowcount


def main():
    with get_conn() as conn:
        with conn.cursor() as cur:
            n = cleanup_old_hotels(cur)
    print(f"deleted {n} hotel_prices rows not refreshed in over {RETENTION_MONTHS} months")


if __name__ == "__main__":
    main()

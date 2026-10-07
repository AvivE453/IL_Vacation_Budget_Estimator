# Refreshes exchange_rates from the free, no-key Frankfurter API (https://www.frankfurter.dev).
# Intended to run weekly for a real budget estimate.

# Run with: uv run python -m etl.loaders.refresh_exchange_rates

import requests

from etl.common.db import get_conn

FRANKFURTER_URL = "https://api.frankfurter.dev/v1/latest"

# The only budget_currency options the search form offers.
TRACKED_CURRENCIES = ["ILS", "EUR", "USD"]


def main():
    resp = requests.get(FRANKFURTER_URL, params={"base": "USD", "symbols": ",".join(TRACKED_CURRENCIES)}, timeout=10)
    resp.raise_for_status()
    payload = resp.json()
    as_of_date = payload["date"]
    # rates are USD -> currency (units of currency per 1 USD); invert for usd_per_unit.
    usd_to_currency = payload["rates"]

    rows = [("USD", 1.0, as_of_date)]
    for currency_code, rate in usd_to_currency.items():
        if rate:
            rows.append((currency_code, 1.0 / rate, as_of_date))

    with get_conn() as conn:
        with conn.cursor() as cur:
            for currency_code, usd_per_unit, date in rows:
                cur.execute(
                    """
                    INSERT INTO exchange_rates (currency_code, usd_per_unit, as_of_date)
                    VALUES (%s, %s, %s)
                    ON CONFLICT (currency_code) DO UPDATE SET
                        usd_per_unit = EXCLUDED.usd_per_unit,
                        as_of_date = EXCLUDED.as_of_date,
                        updated_at = now()
                    """,
                    (currency_code, usd_per_unit, date),
                )

    print(f"refreshed {len(rows)} exchange rates as of {as_of_date}")


if __name__ == "__main__":
    main()

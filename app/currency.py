# Currency conversion against the exchange_rates table. Everything is stored
# internally in USD; other currencies exist for the user's budget and display.
#
# Look the rate up once with get_usd_per_unit(), then convert as many amounts
# as needed with to_usd()/from_usd() - they don't touch the database, so a page
# showing N amounts runs one rate query, not N.


# Raises ValueError if no rate is on file - callers decide the fallback
# rather than silently using an unconverted amount.
def get_usd_per_unit(cur, currency_code):
    if currency_code == "USD":
        return 1.0

    cur.execute(
        "SELECT usd_per_unit FROM exchange_rates WHERE currency_code = %s",
        (currency_code,),
    )
    row = cur.fetchone()
    if row is None:
        raise ValueError(f"no exchange rate on file for currency {currency_code!r}")

    return float(row["usd_per_unit"] if isinstance(row, dict) else row[0])


def to_usd(amount, usd_per_unit):
    return round(float(amount) * usd_per_unit, 2)


def from_usd(amount_usd, usd_per_unit):
    return round(float(amount_usd) / usd_per_unit, 2)

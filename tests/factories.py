# Insert controlled rows into the test database. Destinations come from the
# seed (see conftest.py), so they're referenced by IATA code / hotel city key.
# Everything is written through the test's own `cur`, so it's rolled back
# with the rest of the test.


def add_flight(
    cur, destination_iata, depart_date, return_date, price_usd,
    airline_code=None, observed_at=None, price_seen_on=None,
):
    cur.execute(
        """
        INSERT INTO flight_price_observations
            (destination_id, origin_iata, destination_iata, depart_date, return_date,
             price_amount, currency_code, price_amount_usd, airline_code, observed_at, price_seen_on)
        SELECT destination_id, 'TLV', iata_code, %(depart)s, %(return)s,
               %(price)s, 'USD', %(price)s, %(airline)s, COALESCE(%(observed_at)s, now()), %(seen_on)s
        FROM destinations
        WHERE iata_code = %(iata)s
        """,
        {
            "iata": destination_iata,
            "depart": depart_date,
            "return": return_date,
            "price": price_usd,
            "airline": airline_code,
            "observed_at": observed_at,
            "seen_on": price_seen_on,
        },
    )
    assert cur.rowcount == 1, f"no seeded destination with IATA code {destination_iata}"


def add_hotel(cur, city_key, avg_usd, budget_usd=None, luxury_usd=None, sample_size=20):
    cur.execute(
        """
        INSERT INTO hotel_prices
            (city_name_raw, city_name_normalized, avg_price_per_night_usd,
             avg_price_budget_tier_usd, avg_price_luxury_tier_usd, sample_size)
        VALUES (%s, %s, %s, %s, %s, %s)
        """,
        (city_key.title(), city_key, avg_usd, budget_usd, luxury_usd, sample_size),
    )


def add_exchange_rate(cur, currency_code, usd_per_unit):
    cur.execute(
        "INSERT INTO exchange_rates (currency_code, usd_per_unit, as_of_date) VALUES (%s, %s, CURRENT_DATE)",
        (currency_code, usd_per_unit),
    )


# A past /estimate search as /history shows it: one search_queries row plus
# one saved result per destination.
def add_saved_search(cur, session_id, destination_iatas=("BCN",), budget_currency="USD"):
    cur.execute(
        """
        INSERT INTO search_queries
            (session_id, origin_iata, depart_date, return_date, budget_amount, budget_currency)
        VALUES (%s, 'TLV', '2030-06-01', '2030-06-08', 5000, %s)
        RETURNING search_query_id
        """,
        (session_id, budget_currency),
    )
    search_query_id = cur.fetchone()["search_query_id"]
    cur.execute(
        """
        INSERT INTO search_results (search_query_id, destination_id, estimated_total_usd, within_budget)
        SELECT %s, destination_id, 1000, true
        FROM destinations
        WHERE iata_code = ANY(%s)
        """,
        (search_query_id, list(destination_iatas)),
    )
    return search_query_id

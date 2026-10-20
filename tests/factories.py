# Insert controlled rows into the test database. Destinations come from the
# seed (see conftest.py), so they're referenced by IATA code.
# Everything is written through the test's own `cur`, so it's rolled back
# with the rest of the test.


def add_flight(
    cur, destination_iata, depart_date, return_date, price_usd,
    airline_code=None, observed_at=None, price_seen_on=None, number_of_stops=None, return_stops=None,
):
    cur.execute(
        """
        INSERT INTO flight_price_observations
            (destination_id, origin_iata, destination_iata, depart_date, return_date,
             price_amount, currency_code, price_amount_usd, airline_code, observed_at, price_seen_on,
             number_of_stops, return_stops)
        SELECT destination_id, 'TLV', iata_code, %(depart)s, %(return)s,
               %(price)s, 'USD', %(price)s, %(airline)s, COALESCE(%(observed_at)s, now()),
               -- Unless a test says otherwise, seen the day it was collected.
               COALESCE(%(seen_on)s, COALESCE(%(observed_at)s, now())::date),
               %(stops)s, %(return_stops)s
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
            "stops": number_of_stops,
            "return_stops": return_stops,
        },
    )
    assert cur.rowcount == 1, f"no seeded destination with IATA code {destination_iata}"


def add_hotel(cur, destination_iata, avg_usd, budget_usd=None, luxury_usd=None, sample_size=20):
    cur.execute(
        """
        INSERT INTO hotel_prices
            (destination_id, avg_price_per_night_usd,
             avg_price_budget_tier_usd, avg_price_luxury_tier_usd, sample_size)
        SELECT destination_id, %s, %s, %s, %s
        FROM destinations
        WHERE iata_code = %s
        """,
        (avg_usd, budget_usd, luxury_usd, sample_size, destination_iata),
    )
    assert cur.rowcount == 1, f"no seeded destination with IATA code {destination_iata}"


def add_airline(cur, airline_code, airline_name):
    cur.execute("INSERT INTO airlines (airline_code, airline_name) VALUES (%s, %s)", (airline_code, airline_name))


def add_exchange_rate(cur, currency_code, usd_per_unit):
    cur.execute(
        "INSERT INTO exchange_rates (currency_code, usd_per_unit, as_of_date) VALUES (%s, %s, CURRENT_DATE)",
        (currency_code, usd_per_unit),
    )


# A past estimate as the history shows it: one search_queries row plus
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
        INSERT INTO search_results (search_query_id, destination_id, estimated_total_usd)
        SELECT %s, destination_id, 1000
        FROM destinations
        WHERE iata_code = ANY(%s)
        """,
        (search_query_id, list(destination_iatas)),
    )
    assert cur.rowcount == len(destination_iatas), f"not every IATA code in {destination_iatas} is a seeded destination"
    return search_query_id


def count_active_destinations(cur):
    cur.execute("SELECT COUNT(*) AS n FROM destinations WHERE is_active")
    return cur.fetchone()["n"]

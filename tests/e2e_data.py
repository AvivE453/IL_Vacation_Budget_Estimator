# The fixed data the Playwright tests (frontend/e2e/) expect, on top of the
# seeded destinations. Totals in ILS at 0.25 USD per ILS (x4):
#   Rome       $250 + 7 x $120 = $1090 = 4360 ILS  (average hotels)
#   Barcelona  $300 + 7 x $100 = $1000 = 4000 ILS
# Barcelona also has flights on nearby dates for the flexible-dates grid.

import datetime

from tests.factories import add_airline, add_exchange_rate, add_flight, add_hotel

DEPART = datetime.date(2030, 6, 1)
RETURN = datetime.date(2030, 6, 8)
SEEN_ON = datetime.date(2030, 5, 20)


def add_e2e_data(cur):
    add_exchange_rate(cur, "ILS", 0.25)
    add_airline(cur, "IZ", "Arkia")
    add_hotel(cur, "barcelona", avg_usd=100, budget_usd=60, luxury_usd=250)
    add_hotel(cur, "rome", avg_usd=120, budget_usd=70, luxury_usd=300)

    add_flight(cur, "BCN", DEPART, RETURN, price_usd=300, airline_code="IZ", price_seen_on=SEEN_ON, number_of_stops=0)
    add_flight(cur, "FCO", DEPART, RETURN, price_usd=250, airline_code="IZ", price_seen_on=SEEN_ON, number_of_stops=1)
    for depart_offset, return_offset, price in [(-2, 0, 280), (1, 1, 350), (3, -1, 210)]:
        add_flight(
            cur, "BCN",
            DEPART + datetime.timedelta(days=depart_offset),
            RETURN + datetime.timedelta(days=return_offset),
            price_usd=price, airline_code="IZ", price_seen_on=SEEN_ON,
        )

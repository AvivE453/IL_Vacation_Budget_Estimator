# Collector: pulls current hotel prices for each active destination from
# SerpApi's Google Hotels API and upserts a per-city aggregate into hotel_prices.
#
# Unlike flights_collector.py, this upserts a "latest snapshot per city",
# not an append-only time series - SerpApi's free tier caps at 250 searches/month,
# too little for repeated same-day snapshots.
#
# Run with: python -m etl.collectors.hotels_collector

import datetime

import requests
from tenacity import retry, stop_after_attempt, wait_exponential

from etl.common.config import SERPAPI_KEY
from etl.common.db import get_cursor

SEARCH_URL = "https://serpapi.com/search"

# One representative nightly rate per city, not date-specific - the app
# multiplies this by however many nights the user's search needs.
CHECK_IN_OFFSET_DAYS = 1
STAY_NIGHTS = 7

# Budget/luxury tier = average of the cheapest/priciest N hotels in the
# sample, alongside the plain average. min() guard in tier_averages() below
# handles small samples without the two tiers overlapping.
TIER_SAMPLE_SIZE = 10

# Result pages to fetch per destination. Each page is a separate SerpApi
# search (~20 properties) and costs 1:1 against the 250/month quota for a
# genuinely new query.
PAGES = 5


# Returns (budget_tier_avg, luxury_tier_avg) from a price list of any
# size: averages of the cheapest/priciest TIER_SAMPLE_SIZE prices, or
# fewer if the sample is smaller (halved so the two tiers never overlap).
# Returns (None, None) if the sample is too small (<2) to split into two
# non-overlapping tiers at all - missing data, not a zero.
def tier_averages(prices):
    if len(prices) < 2:
        return None, None
    prices_sorted = sorted(prices)
    tier_n = min(TIER_SAMPLE_SIZE, len(prices_sorted) // 2)
    cheapest = prices_sorted[:tier_n]
    priciest = prices_sorted[-tier_n:]
    return sum(cheapest) / len(cheapest), sum(priciest) / len(priciest)


@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=1, max=10), reraise=True)
def fetch_hotels(city_query, check_in_date, check_out_date, next_page_token=None):
    params = {
        "engine": "google_hotels",
        "q": f"{city_query} hotels",
        "check_in_date": check_in_date.isoformat(),
        "check_out_date": check_out_date.isoformat(),
        "currency": "USD",
        "gl": "us",
        "hl": "en",
        "api_key": SERPAPI_KEY,
    }
    if next_page_token:
        params["next_page_token"] = next_page_token
    resp = requests.get(SEARCH_URL, params=params, timeout=20)
    resp.raise_for_status()
    return resp.json()


# Combined property list across up to PAGES pages, following
# serpapi_pagination.next_page_token between requests. Stops early if a
# page has no next_page_token (fewer results than PAGES * ~20 exist).
def fetch_hotel_properties(city_query, check_in_date, check_out_date):
    properties = []
    next_page_token = None
    for _ in range(PAGES):
        payload = fetch_hotels(city_query, check_in_date, check_out_date, next_page_token)
        properties.extend(payload.get("properties", []))
        next_page_token = payload.get("serpapi_pagination", {}).get("next_page_token")
        if not next_page_token:
            break
    return properties


def fetch_destinations(cur):
    cur.execute(
        """
        SELECT destination_id, city_name, hotel_data_city_key
        FROM destinations
        WHERE is_active
        ORDER BY destination_id
        """
    )
    return cur.fetchall()


def main():
    if not SERPAPI_KEY:
        raise SystemExit("SERPAPI_KEY is not set -- register free at serpapi.com and set it in .env")

    check_in = datetime.date.today() + datetime.timedelta(days=CHECK_IN_OFFSET_DAYS)
    check_out = check_in + datetime.timedelta(days=STAY_NIGHTS)

    n_updated, n_skipped_no_results, n_errors = 0, 0, 0

    with get_cursor() as cur:
        destinations = fetch_destinations(cur)

        for dest in destinations:
            try:
                properties = fetch_hotel_properties(dest["city_name"], check_in, check_out)
            except requests.RequestException as e:
                print(f"  ERROR fetching {dest['city_name']}: {e}")
                n_errors += 1
                continue

            prices = [
                p["rate_per_night"]["extracted_lowest"]
                for p in properties
                if p.get("rate_per_night", {}).get("extracted_lowest")
            ]
            if not prices:
                print(f"  no priced results for {dest['city_name']}")
                n_skipped_no_results += 1
                continue

            budget_tier_avg, luxury_tier_avg = tier_averages(prices)

            cur.execute(
                """
                INSERT INTO hotel_prices
                    (city_name_raw, city_name_normalized,
                     avg_price_per_night_usd, min_price_per_night_usd, sample_size,
                     avg_price_budget_tier_usd, avg_price_luxury_tier_usd)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (city_name_normalized) DO UPDATE SET
                    city_name_raw = EXCLUDED.city_name_raw,
                    avg_price_per_night_usd = EXCLUDED.avg_price_per_night_usd,
                    min_price_per_night_usd = EXCLUDED.min_price_per_night_usd,
                    sample_size = EXCLUDED.sample_size,
                    avg_price_budget_tier_usd = EXCLUDED.avg_price_budget_tier_usd,
                    avg_price_luxury_tier_usd = EXCLUDED.avg_price_luxury_tier_usd,
                    loaded_at = now()
                """,
                (
                    dest["city_name"],
                    dest["hotel_data_city_key"],
                    sum(prices) / len(prices),
                    min(prices),
                    len(prices),
                    budget_tier_avg,
                    luxury_tier_avg,
                ),
            )
            n_updated += 1

    print(f"updated {n_updated} destinations "
          f"({n_skipped_no_results} had no priced results, {n_errors} request errors)")


if __name__ == "__main__":
    main()

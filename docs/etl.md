# ETL

The scripts that fill the database: reference data, flight prices, hotel prices, and the cleanup
of rows that are no longer useful. They live in [etl/](../etl/) and are run by hand from the
command line, each as a module (`uv run python -m etl.<folder>.<script>`).

## The folders

| Folder | What's in it | How often it runs |
|---|---|---|
| [common/](../etl/common/) | `config.py` (reads `.env`), `db.py` (one connection per run) | Imported, never run |
| [loaders/](../etl/loaders/) | Migrations, reference data, cleanup scripts | Once, or when their input changes. Safe to rerun |
| [collectors/](../etl/collectors/) | Flight prices, hotel prices | Over and over |
| [tools/](../etl/tools/) | `discover_destinations` | By hand, when choosing new destinations |

The loaders and the flights collector write differently on purpose. A loader upserts
(`ON CONFLICT ... DO UPDATE`), so running it twice leaves the table matching its input. The flights
collector only adds (`ON CONFLICT DO NOTHING`), because every price it has seen is part of the
history.

**Connections.** `get_conn()` opens one connection for the whole script, commits when the block
ends and rolls back if it raises. The collectors also commit after each destination, so a crash
or Ctrl+C partway through keeps what was collected. The API has its own pool
([app/db.py](../app/db.py)), since it serves several requests at once; the rest is shared
(`config.py`, and the live flight search reuses the collector's parser).

**Configuration** comes from environment variables, read from `.env` when that file exists:
`DB_URL`, `TRAVELPAYOUTS_TOKEN` (and optional `TRAVELPAYOUTS_MARKER`), `SERPAPI_KEY`.

## Setting up a database

Run once, in this order (each table references the one before it):

```bash
uv run python -m etl.loaders.run_migrations
uv run python -m etl.loaders.load_airports
uv run python -m etl.loaders.load_airlines
uv run python -m etl.loaders.load_destinations_seed
uv run python -m etl.loaders.refresh_exchange_rates
```

- **`run_migrations`** applies the files in [sql/migrations/](../sql/migrations/) that aren't in
  `schema_migrations` yet. See [database.md](database.md).
- **`load_airports`** loads [countries_seed.csv](../sql/seed/countries_seed.csv) and
  [airports_seed.csv](../sql/seed/airports_seed.csv) in one transaction, so there's never an
  airport whose country didn't load.
- **`load_airlines`** downloads Travelpayouts' public airline list (no token needed). It isn't a
  seed file because it's their own code-to-name mapping, with no reason to curate it by hand. The
  test database doesn't load it, which is one reason every query joins `airlines` with a
  `LEFT JOIN`.
- **`load_destinations_seed`** loads [destinations_seed.csv](../sql/seed/destinations_seed.csv),
  the 103 places the app prices. **The file is the list of active destinations**: after loading
  it, the loader marks every destination missing from the file `is_active = false`, and every one
  in it `true`. Removing a city from the file and rerunning the loader stops both collectors and
  the app from using it, while its price history stays in the database. Re-adding it brings it
  back.
- **`refresh_exchange_rates`** asks [Frankfurter](https://www.frankfurter.dev) for USD to ILS and
  EUR, and stores how many dollars one unit of each is worth. It's what converts a user's budget;
  both collectors fetch prices in USD directly.

Empty Hebrew-name cells in the seed files load as `NULL`, not `""`, so the frontend falls back to
the English name.

## The flights collector

```bash
uv run python -m etl.collectors.flights_collector
```

[flights_collector.py](../etl/collectors/flights_collector.py) asks the
[Travelpayouts Data API](https://travelpayouts-data-api.readthedocs.io/) (`v3/prices_for_dates`)
for round trips from TLV to every active destination.

### What it asks

The endpoint takes a month for each leg, not a day, and returns the round trips that real
Aviasales users searched recently in those months. It's a cache of other people's searches, not a
search for given dates.

For each destination it makes 14 calls: this month and the next six, each asked twice — returning
the same month, and returning the month after. The second one is what collects a trip across a
month boundary (28 Nov to 4 Dec), which a same-month query never returns. With 103 destinations a
run is about 1,440 calls and takes about 11 minutes.

Each call asks for `currency=usd` (without it, many routes answer in roubles, which Frankfurter has
no rate for) and `limit=1000`, the API's maximum. The busiest month seen so far returned 300
results. If a call ever returns exactly 1,000, there are probably more than it sent: the collector
prints a warning and counts it.

**Errors and retries.** Each call is tried up to 3 times (tenacity), but only when another attempt
could succeed:

- **429 (rate limit):** waits exactly the `X-Rate-Limit-Reset` seconds the response gives. The
  limit is 600 requests per minute, from the response headers.
- **5xx, connection errors, timeouts (15s):** waits 1 to 10 seconds, growing each attempt.
- **Anything else** (a 401 for a bad token, say) fails at once.

A call that still fails is counted as an error, and the run moves on to the next month pair.

### What it stores

Each result becomes one row of `flight_price_observations`, unless:

- it has no return date (one-way) or returns the same day it leaves: skipped, not a vacation and
  rejected by `chk_return_after_depart`;
- its link has no `search_date`: skipped and counted. `price_seen_on`, the day an Aviasales user
  saw the price, comes from that undocumented `search_date=DDMMYYYY` link parameter, and it's how
  a new price is told from one already stored, so a row can't be stored without it.

A row holds the dates, the local departure and return times (`HH:MM`, without the UTC offset), the
airline, the stops each way (`number_of_stops` from `transfers`, `return_stops` from
`return_transfers`), the price and `price_seen_on`. The insert is `ON CONFLICT DO NOTHING` against
`uq_flight_obs`, so a quote an earlier run already stored adds nothing; the `inserted` count uses
`cur.rowcount` to count only rows that went in.

### The summary line

```
inserted 6232 round-trip flight observations (489 route/month-pair combos had no offer,
0 prices had no search date, 0 request errors, 0 calls hit the 1000-result limit)
```

- **inserted**: new rows.
- **had no offer**: calls that returned no round trips at all.
- **had no search date**: prices skipped for a missing `search_date`. If this jumps and `inserted`
  drops to 0, Aviasales stopped sending it.
- **request errors**: calls that failed after their retries.
- **hit the limit**: calls that probably lost results.

## The hotels collector

```bash
uv run python -m etl.collectors.hotels_collector [--max-searches N]
```

[hotels_collector.py](../etl/collectors/hotels_collector.py) prices a night in each city through
[SerpApi's Google Hotels API](https://serpapi.com/google-hotels-api), searching
`"<city_name> hotels"` in USD.

**The quota decides everything.** The free tier is 250 searches a month, and each city costs one
(one result page, about 20 hotels; a second page would cost a second search). So a run:

1. asks SerpApi's Account API how many searches are left this month (that call is free);
2. refreshes at most `min(--max-searches, searches left)` cities (the default cap is 120);
3. takes cities with no price first, then the oldest prices (`loaded_at`);
4. commits after each city, because each one was a paid search.

A city that returns no priced hotels keeps its old price and is printed by name. It will be first
in line again next run, which is what's wanted: no results means the search text is wrong (it
happened with "Luxembourg", fixed by renaming it "Luxembourg City" in the seed).

**What a city's row holds** (one row per destination, overwritten each refresh): from each
hotel's lowest nightly rate, the average, the minimum, the sample size, and two tiers: the average
of the 10 cheapest and of the 10 priciest. With fewer than 20 hotels each tier is half the sample,
so they never overlap; with fewer than 2 there are no tiers.

**The stay it quotes is fixed**: check-in tomorrow, 7 nights, the same for every city, and
SerpApi's default occupancy of two adults per room. So a hotel price is a recent rate for a room,
not a price for the user's dates; the app multiplies it by the nights and rooms of the trip, and
shows how old it is.

Run it by hand, not on a schedule, and keep an eye on the monthly count.

## The cleanup scripts

Each is one `DELETE`, run by hand:

```bash
uv run python -m etl.loaders.cleanup_old_flights
uv run python -m etl.loaders.cleanup_old_hotels
uv run python -m etl.loaders.cleanup_old_searches
```

- **`cleanup_old_flights`** deletes flights whose return date is more than 3 months past. A trip
  that's over doesn't help price a future one, and it keeps the table from growing forever.
- **`cleanup_old_hotels`** deletes hotel prices not refreshed in 3 months. There's one row per
  city, so the city then has no hotel price at all and the app says so, rather than showing a
  price that's months out of date.
- **`cleanup_old_searches`** deletes saved searches older than 30 days, and their results with
  them (`ON DELETE CASCADE`). 30 days is also the session cookie's lifetime, counted from the last
  visit (`SESSION_MAX_AGE` in [api/deps.py](../api/deps.py)): a browser away that long has a new
  session and can't reach its old searches, and one that keeps coming back sees its last 30 days.

The history itself is only in the database; the browser holds just the session id cookie.

## Finding new destinations

```bash
uv run python -m etl.tools.discover_destinations
```

[discover_destinations.py](../etl/tools/discover_destinations.py) asks Travelpayouts for round
trips from TLV with no destination, one call per month for 12 months, and prints every airport
that came back: in how many months, how many trips, the cheapest price, and whether it's already
in the seed. It writes nothing. The cache leans towards Russian-speaking users, so each city is
judged by hand as an Israeli vacation destination before it's added to the seed files.

## Known limitations

- **One airport per city.** The seed gives each city one airport code, and a query by airport
  code returns flights to that airport only. Cities with several airports miss the others: London
  is collected through LHR, while the low-cost flights land at Gatwick, Stansted and Luton (in
  November, $394 cheapest through LHR against $177 through the city code LON). Moscow, Paris,
  Tokyo and Milan are affected the same way.
- **Hotel prices aren't seasonal.** Every city is quoted for the same week, so a summer trip is
  priced with the hotel rates of whenever the collector last ran.
- **Collection is manual.** Nothing runs on a schedule; prices are as fresh as the last run.

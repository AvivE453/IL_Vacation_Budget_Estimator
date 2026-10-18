# API and estimate logic

A JSON API in [FastAPI](https://fastapi.tiangolo.com/), in [api/](../api/), over the logic in
[app/](../app/). All the SQL it runs is in [app/queries.py](../app/queries.py), as plain
parameterized strings with no ORM.

```bash
uv run uvicorn api.main:app --reload --port 8000   # interactive docs at http://127.0.0.1:8000/docs
```

## How a request flows

```
browser (React)  →  Vite dev server :5173  →  FastAPI :8000  →  app/  →  Postgres :5433
                    (proxies /api)            (api/)            (logic, SQL)
```

The browser never talks to the database: the API holds its password and allows only the
operations defined below, each with its input checked. In development, Vite serves the React
files and passes every `/api` request through to the API, so the page and the API share one
origin: the `session_id` cookie is sent without any CORS setup.

The routes in `api/` stay thin: they validate the input, call a function in `app/`, and turn
its result into a response model. `app/` knows nothing about FastAPI; it takes a cursor and
returns rows, which is also how the tests call it.

## The API layer

- **[api/main.py](../api/main.py)** creates the app and mounts six routers under `/api/v1`. Each
  operation's `operationId` is its route function's name (`destination_trip`), which becomes its
  name in the generated TypeScript. A `PoolExhausted` anywhere becomes a 503 with
  `Retry-After: 1`: the server is busy, not broken.
- **[api/deps.py](../api/deps.py)** holds two dependencies, which FastAPI runs before a route
  that names them:
  - `Cursor`: one connection from the pool and one transaction per request, committed (or
    rolled back) **before** the response is sent (`scope="function"`), so a failed commit is an
    error response rather than a 200 for data that was never saved. Tests replace it with
    `app.dependency_overrides` to run each test in a transaction they roll back.
  - `SessionId`: the anonymous browser id. A random UUID in an `httponly`, `samesite=lax`
    cookie, re-sent on every response so its 30 days count from the last visit. Not signed:
    there's nothing in it to tamper with, and another browser's id can't be guessed.
- **[api/errors.py](../api/errors.py)** describes the API's own 404 and 503 bodies
  (`{"detail": "..."}`) so they're in the schema too. 422s keep FastAPI's shape.
- **Concurrency.** Routes are plain `def`, so FastAPI runs each request in a worker thread;
  psycopg2 blocks while it waits for the database, which `async def` would turn into blocking
  the whole server. The pool ([app/db.py](../app/db.py)) has 10 connections; a request waits up
  to 5 seconds for a free one, then gets the 503.

## Input validation

Each request is a Pydantic model. FastAPI builds it from the JSON body (or, for a GET, from the
query string: `Annotated[TripQuery, Query()]`), converting as it goes (`"2026-11-07"` becomes a
`date`), and answers 422 without running the route when anything fails:

- types: a date must be a date;
- ranges: `budget_amount` above 0 and below 10^8 (the column is `NUMERIC(10,2)`), `travelers`
  and `rooms` 1 to 9;
- closed lists: the currency is `ILS`, `USD` or `EUR` (the ones with a stored rate), the tier
  `budget`, `average` or `luxury`;
- across fields, in a `model_validator`: the return after the departure, no more rooms than
  travelers.

```json
{"detail": [{"type": "greater_than", "loc": ["body", "budget_amount"],
             "msg": "Input should be greater than 0", "input": -5}]}
```

`loc` names the field, which is how the frontend puts the message next to it. The cross-field
checks run only once every field has passed on its own, so they show up on the next attempt.

The origin airport has to exist in the database, which a model can't check: `require_known_origin`
raises the same 422 itself, before saving the search would hit the foreign key.

Responses are models too (`-> EstimateResponse`): only their fields are sent, and each field's
`description` ends up in the docs and the TypeScript types.

## The contract with the frontend

```
Pydantic models  →  api/openapi.json  →  frontend/src/api/schema.d.ts
```

After changing a route or a model, run `uv run python -m api.export_openapi`, then
`npm run gen:api` in `frontend/`. Both files are committed. `tests/test_openapi.py` fails when
`openapi.json` doesn't match the code, and CI fails when `schema.d.ts` doesn't match
`openapi.json`, so the React app can't use a field the API doesn't send.

## The routes

| Route | What it answers |
|---|---|
| `POST /estimates` | Every destination ranked by total cost, for all three hotel tiers; saves the search |
| `GET /searches` | This browser's last 20 searches |
| `GET /searches/{id}` | One saved search and the ranking saved with it |
| `GET /destinations` | The active destinations, for the search form |
| `GET /destinations/{id}/trip` | Every flight option for one destination on given dates, with its hotel prices |
| `GET /destinations/{id}/date-grid` | The cheapest collected flight for each date pair within 3 days |
| `GET /data-quality` | What's collected per destination, gaps included, and per day |
| `GET /origins` | The airports a search can leave from (Israeli ones) |
| `GET /health` | Runs `SELECT 1`, so it fails when the database is down |

All under `/api/v1`. An unknown destination or another browser's search is a 404.

## How an estimate is computed

The estimate is for the whole party:

```
total = flight × travelers  +  hotel_per_night × nights × rooms
```

The flight price is one passenger's round trip (Travelpayouts); the hotel price is one room for
two adults (SerpApi's default occupancy). `estimate_all_tiers` computes every destination and all
three tiers in one query, then applies the rules below to each tier.

### Choosing the flight

One trip can have many rows: the collector sees new prices over time, and every destination
view stores all its live options. `_FRESH_FLIGHTS_CTES` picks one flight per destination, and
the ranking, the destination view's fallback and the date grid all use it, so they agree:

1. **Within 4 days** (`MAX_DATE_DRIFT_DAYS`) of each requested date. The cache only holds dates
   people searched, so an exact match is rare; beyond 4 days it's no longer the trip asked for.
   The departure condition is a plain `BETWEEN`, so `idx_flight_obs_depart_date` can narrow the
   scan.
2. **Each flight once, at its latest price.** A flight is its dates, airline, stops each way and
   times. Seen on the same day at two prices, it's two offers (another connection or fare), and
   the cheaper one counts.
3. **Only what was seen on the trip's newest day** (`price_seen_on`), even when pricier. The
   collector gets only the cheapest flight per date pair, so a newer, pricier one most likely
   means the cheaper one is gone. Measured from that trip's newest price, not from today:
   collection is manual, and a quiet fortnight mustn't empty every result.
4. **The nearest dates, then the cheapest**, ties broken by `observation_id` so every query
   picks the same flight.

### The hotel

`hotel_prices` holds three nightly prices per city: the average of its 10 cheapest hotels, of
all of them, and of its 10 priciest. A `CROSS JOIN` with the three tier names turns each city
into three rows, one price each. **Nights come from the matched flight**, not the request: the
nearest dates don't keep the trip's length, and one total must describe one trip. A city
without a tier price (too few hotels to split) is missing data for that tier, not its average.

### The rules, and their order

The query returns every active destination, those missing a flight or a hotel included (as
`NULL`, through `LEFT JOIN`s), and the filtering happens in Python afterwards, so the missing
ones can still be counted:

1. **Missing data.** `has_missing_data` is true only when not one destination has both a flight
   and a hotel. It tells "no data for these dates" apart from "the budget excluded everything".
2. **Budget.** Destinations whose total is at most the budget.
3. **Exact dates for all or none.** If any destination matched the dates exactly, only the
   exact matches stay; otherwise everyone keeps their nearest dates. Never a mix: a real price
   next to one for other dates reads as comparable when it isn't.

Rule 1 must come before 2, or every over-budget search would look like missing data. Rule 3 must
come after 2: with a $1,000 budget, an exact match at $2,100 would otherwise remove a nearby
trip at $800 and leave nothing. `tests/test_estimate.py` locks in each rule.

## Saving a search, and the history

`run_search` ([app/search.py](../app/search.py)):

1. looks up the budget currency's rate once (every conversion after it is arithmetic, so a
   search runs one rate query, not one per destination);
2. converts the budget to USD, since every stored price is in USD;
3. estimates all three tiers;
4. saves one `search_queries` row (what was asked, the browser, the tier picked, whether the
   results were for the exact dates), and one `search_results` row per destination in the
   picked tier's results, in one `INSERT`;
5. converts every amount back to the budget's currency.

A destination's airline code is stored as `NULL` when it isn't in `airlines` (some collected
flights carry codes that aren't), because `search_results.airline_code` has a foreign key. With
no rate on file for the currency, the search still runs, unfiltered and in USD, but isn't saved.

Every history query filters by `session_id`: search ids are sequential, so without it any browser
could read another's search by changing the number in the URL. A saved search is read from
`search_queries` first, so one where everything was over budget (no saved results) is still
found. The rank is computed when read (`RANK()`, so ties share a place), and the amounts are
shown in the search's currency at today's rate.

## The destination view

`GET /destinations/{id}/trip` ([app/trip.py](../app/trip.py)):

1. **Asks Travelpayouts live** ([app/live_flights.py](../app/live_flights.py)), for the exact
   days rather than a month: a month query returns only the cheapest round trip per date pair,
   an exact one every option. 5-second timeout and no retries, since the user is waiting; any
   failure falls back. Options for other dates are dropped.
2. **Reports what happened** in `live_status`: `found`, `empty` (it answered with nothing for
   these dates, the common case), `failed`, or `off` (`LIVE_FLIGHT_SEARCH=off`).
3. **Stores the live options** (`source = 'live_search'`), so a view adds flights the collector
   never sees. The duplicate rule makes viewing the same trip again add nothing.
4. **Falls back to the collected data** when there's no live option: the flights on the nearest
   date pair, by the same choice as the ranking, so its pick comes first. Collected flights have
   no duration or booking link.
5. **Prices the hotel** for each tier, for the nights of the flight found.

`GET /destinations/{id}/date-grid` uses the same flight choice with a 3-day window on each date:
up to 7 × 7 date pairs, each with its cheapest flight, and a missing pair is missing data. It
reads collected data only (a live call per cell would be 49 calls). It returns the totals too,
but the frontend colors the cells by the flight price: colored by the total, the shortest trips
always looked cheapest, having the fewest hotel nights.

## Known limitations

- **The destination view holds a database connection while it waits for Travelpayouts**, up to
  5 seconds: ten views at once against a slow API would use the whole pool. It doesn't show with
  one user.
- **Prices come from a cache of other people's searches.** Flights are the nearest dates someone
  searched, hotels a recent rate for one fixed week; see [etl.md](etl.md).

# Tests and CI

Three layers of tests, each faking as little as it can: pytest runs the Python side against a
real Postgres, Vitest renders the React app with the API faked at the network level, and
Playwright drives the whole app in Chrome. CI runs all three on every push.

```bash
uv run pytest -v          # Python, from the repo root; needs the Postgres server up
uv run ruff check .       # lint
cd frontend
npm test                  # Vitest component tests
npx playwright test       # end to end; starts its own API and Vite servers
```

## The three layers

| Layer | Runs for real | Faked | Catches |
|---|---|---|---|
| **pytest** (`tests/`) | Python, SQL, Postgres | Travelpayouts, SerpApi, the live flight call | A wrong estimate rule, query, route response or migration |
| **Vitest** (`frontend/src/`) | React, TanStack Query, the API client, in jsdom | The API (MSW) | A wrong screen: text, state, URL, what a form sends |
| **Playwright** (`frontend/e2e/`) | Chrome, Vite, FastAPI, Postgres | Nothing; live flight search is off | The parts not fitting together: the proxy, the session cookie, routing, real JSON |

Each rule is tested at the lowest layer it lives in: estimate rules in pytest, Hebrew plurals in
Vitest. The end-to-end tests are few, one per main user path.

## Databases

Every test database lives on the same server as the development one and is built from the
migrations and seed files, never copied from the development data.

| Database | Used by | Built |
|---|---|---|
| `vacation_budget` | Development; never touched by a test | By hand |
| `vacation_budget_test` | pytest | At the start of every run; left in place afterwards for inspecting |
| `vacation_budget_migrations_test` | `test_run_migrations.py` | Empty, created and dropped by each test |
| `vacation_budget_e2e` | Playwright | At the start of every run, with fixed data |

A rebuild uses `DROP DATABASE ... WITH (FORCE)`, so a `psql` session left open on the old copy
is disconnected instead of failing the run.

## pytest

### Fixtures ([tests/conftest.py](../tests/conftest.py))

- **`admin_conn`** (per run) connects to the server, in autocommit, since `CREATE DATABASE`
  can't run in a transaction. With no server, the DB tests skip; with `CI` set (GitHub Actions
  sets it), they fail instead, so a missing service can't pass as a green run.
- **`test_db_url`** (per run) rebuilds `vacation_budget_test`: migrations, then the countries,
  airports and destinations from the seed. No flights, hotels, airlines or exchange rates.
- **`cur`** (per test) is a cursor on its own connection, rolled back after the test. A test sees
  the rows it inserted (same transaction); the next test sees none of them.
- **`committing_db`** is for code that opens its own connection and commits (the collectors'
  `main()`). It points `etl.common.db.DB_URL` at the test database and deletes the flight and
  hotel rows afterwards, since there's nothing to roll back.

The API tests ([tests/test_api.py](../tests/test_api.py)) override the `db_cursor` dependency
with `cur`, so what a route writes, a saved search for example, is rolled back too.

### Test data ([tests/factories.py](../tests/factories.py))

Each test inserts the rows it needs, right above its assertions: `add_flight`, `add_hotel`,
`add_airline`, `add_exchange_rate`, `add_saved_search`. Destinations come from the seed, so they
are named by IATA code; each factory asserts it inserted what it was asked to, so a typo in a code
fails at once instead of leaving a test to pass on an empty table. Defaults cover what most tests
don't care about (`TLV`, USD, collected now, seen the day it was collected). Trip dates are in
2030, so they never become past dates.

### What each file covers

| File | What it checks |
|---|---|
| `test_estimate.py` | Every rule of `estimate_all_tiers` ([api.md](api.md)): date matching, missing data versus the budget, nights, tiers, several flights for one trip. Characterization tests: if a change breaks one, decide whether the rule should change |
| `test_queries.py` | The other read queries, against exact values; every seeded city and country has a Hebrew name |
| `test_api.py` | The routes through `TestClient`: the full JSON of each response, 422s naming the field, 404 and 503, session scoping, the live call and its fallback |
| `test_openapi.py` | `api/openapi.json` matches the code; the operationIds; the documented errors |
| `test_db.py` | The API's connection pool: reuse, rollback on error, a dropped connection replaced, waiting for a free one |
| `test_live_flights.py` | The live call's parsing; every failure comes back as `None` |
| `test_flights_collector.py` | Retries (429 waits `X-Rate-Limit-Reset`, 5xx retried, 401 not), parsing, duplicates, the run's counters, a commit per destination |
| `test_hotels_collector.py` | The SerpApi quota: never more searches than the account or the run allows; which cities go first; a commit per city |
| `test_loaders.py` | Deactivating a destination removed from the seed; the cleanup scripts |
| `test_run_migrations.py` | The migration runner, on its own empty database and a copy of the migration files in `tmp_path` |
| `test_currency.py` | Currency conversion, with a fake cursor: the one file that needs no database |

### No network

No test reaches an outside API. Depending on what's under test, a test replaces `requests.get`
(with a `FakeResponse`, to test retries; the retry's `sleep` is replaced too) or the whole fetch
function (to test what's stored). In `test_api.py` an autouse `live` fixture replaces the live
flight call: it answers `None` (a failure, so the fallback is the default path) unless a test sets
`live["options"]`, and it switches live search on whatever `.env` says.

**Statement counts.** `CountingCursor` counts `execute` calls, and two tests check that an
estimate and a saved search take the same number of statements for one destination as for three,
so a query inside a loop fails a test.

## The API contract

```
Pydantic models → api/openapi.json → frontend/src/api/schema.d.ts → client.ts, pages, test fixtures
```

Both generated files are committed, and each link has a check that fails when it's stale:
`test_saved_schema_matches_the_code` (pytest), CI's frontend job (`npm run gen:api`, then
`git diff --exit-code`), and `tsc`, which checks `src/` and `e2e/`, tests included. The types
check shape, not values: a wrong number in the right field still compiles.

## Component tests: Vitest, Testing Library, MSW

Configured in [vite.config.ts](../frontend/vite.config.ts) (`test`): jsdom, `src/**/*.test.{ts,tsx}`,
and `TZ=Asia/Jerusalem`, where the local date differs from the UTC one, so a date bug that CI's UTC
would hide shows up on every machine.

- **[src/test/server.ts](../frontend/src/test/server.ts)**: an MSW server with no handlers; each
  test adds its own with `server.use(...)`. MSW answers `fetch` itself, so everything between the
  page and the network runs as in the browser.
- **[src/test/setup.ts](../frontend/src/test/setup.ts)** runs before each test file. The server
  listens when the file loads, not in `beforeAll`: `openapi-fetch` keeps the `fetch` it finds when
  the client is created, which happens when a test file imports the app. `onUnhandledFrame: "error"`
  fails a test on any request it didn't answer (MSW 3's name; the older `onUnhandledRequest` is
  silently ignored). After each test: `cleanup()` and `resetHandlers()`.
- **[src/test/renderApp.tsx](../frontend/src/test/renderApp.tsx)** renders the whole app at a URL:
  the real routes and pages, a `MemoryRouter`, and a new `QueryClient` per test, with the real retry
  rule but no wait between tries.
- **[src/test/fixtures.ts](../frontend/src/test/fixtures.ts)**: API answers typed by
  `schema.d.ts`, each taking overrides for the fields a test cares about.
- **[src/test/tables.ts](../frontend/src/test/tables.ts)**: a row's cell texts, pieces joined by a
  space, as a reader sees them.

Tests find elements by role and label, as a screen reader does. Tests that depend on today fake
only `Date` (`vi.useFakeTimers({ toFake: ["Date"] })`): faking timers too would stall user-event and
TanStack Query. The client's `baseUrl` is `window.location.origin` because Node's `Request` rejects
a relative URL.

| File | Covers |
|---|---|
| `format.test.ts` | Dates, money, Hebrew counts |
| `api/client.test.ts` | `unwrap` (including an empty error body), `validationMessages`, `shouldRetry` |
| `pages/SearchPage.test.tsx` | The form, what it sends, the results and their empty cases, 422 and failed searches |
| `pages/DestinationPage.test.tsx` | Live and collected flights, the date grid, the URL, 404 |
| `pages/HistoryPage.test.tsx` | The history list and a saved search |
| `pages/DataQualityPage.test.tsx` | Coverage and gaps; a busy API retried, then reported |

## End-to-end tests: Playwright

[playwright.config.ts](../frontend/playwright.config.ts) starts two servers and waits for them:

- **The API on :8001**: [tests/e2e_server.py](../tests/e2e_server.py) rebuilds
  `vacation_budget_e2e` with [tests/e2e_data.py](../tests/e2e_data.py), then replaces itself
  (`os.execvpe`) with uvicorn, with `DB_URL` pointing at that database and
  `LIVE_FLIGHT_SEARCH=off`. A new process because `etl.common.config` reads `DB_URL` once, at
  import.
- **Vite on :5174**, with `API_URL` sending its proxy to :8001.

The ports differ from the dev servers' (8000, 5173), so the tests run while the app is open, and
the servers are never reused, so every run starts from the same data. One worker, since the tests
share a database and a session. `forbidOnly` in CI; traces kept for failed tests in
`frontend/test-results/`. Google Chrome (`channel: "chrome"`), not Playwright's Chromium, which it
doesn't ship for Ubuntu 20.04 (the dev machine).

The fixed data: ILS at 0.25 USD, Barcelona ($300 a seat, $100 a night) and Rome ($250, $120), and
three more Barcelona flights on nearby dates for the date grid. Prices are seen two days before
the run, since a price is always seen in the past. [e2e/app.spec.ts](../frontend/e2e/app.spec.ts)
has three tests, with the expected totals worked out in comments: a search ranked, saved and
found in the history; a destination's view on collected data, its age tag, and a date picked
from its grid; the data-quality page with a destination that has no data.

The Python files live in `tests/` because they import the project's Python code (the factories,
the migrations, the loaders); the TypeScript ones live in `frontend/` with their packages.

## CI ([.github/workflows/ci.yml](../.github/workflows/ci.yml))

GitHub Actions, on every push to any branch and by hand. Three jobs run in parallel:

| Job | Steps |
|---|---|
| `test` | `uv sync --locked`, `ruff`, the migration and seed commands on a fresh `postgres:16` service, `pytest -v` |
| `frontend` | `npm ci` with Node from `.nvmrc`, regenerate `schema.d.ts` and fail on a diff, `npm test`, `npm run build` |
| `e2e` | Both stacks, Postgres, Google Chrome, `npx playwright test`; on failure, the traces as an artifact |

- Postgres starts as a service with a `pg_isready` health check, so the steps wait for it. It's on
  port 5432 there (`DB_URL` in the workflow); locally it's 5433.
- `--locked` and `npm ci` fail when a lock file doesn't match its manifest.
- **Pinned**: the runner (`ubuntu-24.04`, not `ubuntu-latest`), `astral-sh/setup-uv` (an exact
  version: it publishes no major tag), Node (`.nvmrc`) and Postgres (16). GitHub's own actions
  are on their major tag (`@v7`). An upgrade gets its own commit.
- Each job has a `timeout-minutes`, so a hung server stops the run in minutes, not hours.
- CI holds no secrets: nothing in it calls Travelpayouts or SerpApi.

## Not covered

- **The real outside APIs.** Their answers are faked everywhere; a change on their side shows up
  when a collector runs (`skipped_no_search_date` in the flight collector's summary, for example).
- **Layout.** jsdom doesn't lay out text, so right-to-left rendering of mixed Hebrew and English
  is checked by eye in a browser ([frontend.md](frontend.md#hebrew-and-right-to-left)).
- **Other browsers.** Playwright runs Chrome only.
- **An error thrown while rendering**: there is no error boundary, and no test for one.

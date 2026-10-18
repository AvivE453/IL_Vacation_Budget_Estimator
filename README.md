# Vacation Budget Estimator

[![CI](https://github.com/AvivE453/IL_Vacation_Budget_Estimator/actions/workflows/ci.yml/badge.svg)](https://github.com/AvivE453/IL_Vacation_Budget_Estimator/actions/workflows/ci.yml)

Estimates the total cost of a vacation from Israel (flights for every traveler plus hotel
rooms for every night) across 103 destinations, and ranks them by price. It started as a
database course project.

The core data problem: flight prices and hotel prices come from two independent sources that
identify places differently. Flights use airport codes (`BCN`), hotels use city names
(`"Barcelona"`). A hand-curated `destinations` table maps both to one internal id, and every
query joins through it. Missing data is shown to the user, never silently treated as zero.

## How it works

| Layer | What it does |
|---|---|
| **ETL** (`etl/`) | Collects flight prices from the [Travelpayouts Data API](https://travelpayouts-data-api.readthedocs.io/), hotel prices from [SerpApi's Google Hotels API](https://serpapi.com/google-hotels-api), and exchange rates from [Frankfurter](https://www.frankfurter.dev). Run by hand. |
| **Database** (`sql/`) | PostgreSQL 16, raw SQL with no ORM. Flight prices are append-only, so the price history is kept. |
| **API** (`api/`, `app/`) | FastAPI, returns JSON. Interactive docs at `/docs` while it runs. |
| **Frontend** (`frontend/`) | React 19 + TypeScript (Vite), a Hebrew right-to-left interface. Its API types are generated from the API's OpenAPI schema. |

How each part is designed, in more depth: [docs/database.md](docs/database.md), [docs/etl.md](docs/etl.md), [docs/api.md](docs/api.md).

## Running it

Needs [uv](https://docs.astral.sh/uv/), Docker, and Node (the version in
[frontend/.nvmrc](frontend/.nvmrc)).

### One-time setup

```bash
# 1. Postgres, on host port 5433 (or `docker compose up -d`)
docker run -d --name vacation_budget_db -e POSTGRES_USER=vacation \
  -e POSTGRES_PASSWORD=<password> -e POSTGRES_DB=vacation_budget -p 5433:5432 postgres:16

# 2. Python dependencies (uv installs Python 3.12 and the locked versions)
uv sync

# 3. Secrets: fill in DB_URL, TRAVELPAYOUTS_TOKEN/MARKER and SERPAPI_KEY (all free to register)
cp .env.example .env

# 4. Schema and reference data
uv run python -m etl.loaders.run_migrations
uv run python -m etl.loaders.load_airports
uv run python -m etl.loaders.load_airlines
uv run python -m etl.loaders.load_destinations_seed
uv run python -m etl.loaders.refresh_exchange_rates

# 5. Prices
uv run python -m etl.collectors.hotels_collector    # costs 1 of SerpApi's 250 free monthly searches per city
uv run python -m etl.collectors.flights_collector   # rerun to collect more; it only stores prices it doesn't have

# 6. Frontend dependencies
cd frontend && npm ci
```

### Every time after that

```bash
docker start vacation_budget_db                        # the container stops on reboot
uv run uvicorn api.main:app --reload --port 8000       # terminal 1, from the repo root
cd frontend && npm run dev                             # terminal 2 -> http://localhost:5173
```

After a `git pull` that changes dependencies, rerun `uv sync` (repo root) and `npm ci`
(`frontend/`). `LIVE_FLIGHT_SEARCH=off` in `.env` turns off the one live call the API makes
(a Travelpayouts search when you open a destination), so it uses collected prices only.

To change the schema, add a new numbered file to [sql/migrations/](sql/migrations/) and rerun
`run_migrations`. Never edit one that has already run. After changing an API route, rerun
`uv run python -m api.export_openapi`, then `npm run gen:api` in `frontend/`.

## Tests

```bash
uv run pytest -v          # Python: API, queries, collectors, migrations
uv run ruff check .       # lint
cd frontend
npm test                  # React component tests (Vitest, API mocked with MSW)
npx playwright test       # end-to-end, in Chrome against the real API and Postgres
```

The tests never touch the development database: each run builds its own from the migrations
and seed files. CI ([GitHub Actions](.github/workflows/ci.yml)) runs all of them on every push.

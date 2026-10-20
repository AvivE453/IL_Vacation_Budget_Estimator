# Frontend

A React 19 + TypeScript app in [frontend/](../frontend/), built with [Vite](https://vite.dev/).
The interface is Hebrew and right to left. It reads and writes everything through the JSON API
([api.md](api.md)); it never talks to the database.

```bash
cd frontend
npm ci              # the exact versions in package-lock.json
npm run dev         # http://localhost:5173 - needs the API running on :8000
npm run build       # tsc type check, then vite build into dist/ (what CI runs)
npm run gen:api     # after api/openapi.json changes: regenerates src/api/schema.d.ts
```

## Tools

- **Vite** serves the source files in development and bundles them into `dist/` for a build.
  Its dev server **proxies `/api` to the API** ([vite.config.ts](../frontend/vite.config.ts)), so
  the page and the API share one origin: no CORS setup, and the `session_id` cookie is sent as is.
  `API_URL` points the proxy elsewhere (the end-to-end tests use it).
- **TypeScript** runs in `strict` mode with `noEmit`: `tsc` only checks, and Vite strips the
  types without checking them, which is why `npm run build` runs `tsc` first.
  [src/vite-env.d.ts](../frontend/src/vite-env.d.ts) loads Vite's own types, which declare
  `.css` imports: without it, an editor whose newer TypeScript checks side-effect imports
  (`noUncheckedSideEffectImports`) flags `import "./styles.css"`.
- **Versions are pinned.** Node is in [frontend/.nvmrc](../frontend/.nvmrc) (22.14.0, read by CI
  too), which keeps React Router on 7.x (8 needs Node 22.22). TypeScript stays on `~5.9`:
  TypeScript 7 has no JavaScript API, which `openapi-typescript` needs.
- **Five runtime dependencies**: `react`, `react-dom`, `react-router`, `@tanstack/react-query`
  and `openapi-fetch`. Everything else is a build or test tool.

## Files

| Path | What it holds |
|---|---|
| `index.html` | The page Vite starts from: `<html lang="he" dir="rtl">`, an empty `#root`, the Rubik font |
| `src/main.tsx` | Mounts the app: `StrictMode` → `QueryClientProvider` → `BrowserRouter` → `App` |
| `src/App.tsx` | The routes |
| `src/Layout.tsx` | The header and menu every page shares; the page renders into its `<Outlet />` |
| `src/pages/` | One component per route |
| `src/components/` | The parts the pages use: the search form, the results, the date grid, the age tag |
| `src/api/` | The typed client (`client.ts`) and the generated types (`schema.d.ts`) |
| `src/queryClient.ts` | The query cache and its retry rule |
| `src/format.ts`, `src/links.ts` | Formatting (dates, money, Hebrew counts and names) and the destination view's URL |
| `src/styles.css` | All the styling |
| `src/test/`, `*.test.tsx`, `e2e/` | Component tests (Vitest) and end-to-end tests (Playwright) |

## Routes

| Path | Page | API calls |
|---|---|---|
| `/` | `SearchPage`: the form, then the ranked results | `GET /origins`, `GET /destinations`, `POST /estimates` |
| `/destinations/:destinationId?depart_date=…` | `DestinationPage`: one destination's flights, hotel and date grid | `GET /destinations/{id}/trip`, `GET /destinations/{id}/date-grid` |
| `/history` | `HistoryPage`: this browser's last 20 searches | `GET /searches` |
| `/history/:searchId` | `SavedSearchPage`: one search and the ranking saved with it | `GET /searches/{id}` |
| `/data-quality` | `DataQualityPage`: coverage per destination, collection per day | `GET /data-quality` |
| anything else | `NotFoundPage` | — |

Routing happens in the browser: a `Link` changes the URL without loading a new page, so the
query cache survives navigation. A path segment from `useParams` is always a string, so the pages
that take an id convert it with `Number()` and treat anything that isn't an integer as not found,
without asking the API.

## Talking to the API

```
Pydantic models  →  api/openapi.json  →  src/api/schema.d.ts  →  api.GET("/api/v1/...")
```

- **The types are generated**, not written by hand ([api.md](api.md#the-contract-with-the-frontend)).
  `schema.d.ts` is keyed by path and method, so `api.POST("/api/v1/estimates", { body })` is
  checked against the API's own model: a wrong path, a missing field or a misread response is a
  build error. `Schemas["Trip"]` is shorthand for a model's type.
- **[client.ts](../frontend/src/api/client.ts)** creates the client with `openapi-fetch`, which
  serializes the body to JSON and parses the response. It doesn't throw on an error status; it
  returns `{ data }` or `{ error }`. `unwrap()` turns that into a value or a thrown `ApiError`
  (status + body), which is what TanStack Query expects. It tests `error !== undefined`, not
  `if (error)`: when the API is down, Vite's proxy answers 502 with an empty body, and `""` is falsy.
- **JSON types**: a date arrives as a `"YYYY-MM-DD"` string and stays one, so dates are compared
  as strings (that order is the calendar order); `None` arrives as `null`.
- **A 422** becomes one message per rejected field: `validationMessages()` names the field in
  Hebrew (`FIELD_NAMES`, one entry per field of `EstimateRequest`) and keeps the API's message.
  A check on the whole request (return before departure) has no field and stands alone. The
  form's own HTML checks (`required`, `min`, `max`) catch nearly all of these first.

## Server data: TanStack Query

Every request goes through `useQuery` (read) or `useMutation` (write); there is no `fetch` in a
`useEffect`. The cache handles loading and error state, deduplication, out-of-order answers and
retries.

- **`queryKey` is the data's identity**, and holds everything the request depends on:
  `["trip", destinationId, query]` refetches when the dates change, and an answer that arrives
  late is stored under its own key instead of overwriting the current one.
  Keys: `origins`, `destinations`, `searches`, `searches/{id}`, `trip`, `date-grid`, `data-quality`.
- **Estimates are a mutation**: they run on submit and save a search. On success,
  `invalidateQueries(["searches"])` marks the history (and every saved search) stale.
  Mutations never retry, so a failed `POST` can't save the same search twice.
- **Retries** ([queryClient.ts](../frontend/src/queryClient.ts)): queries retry up to three
  times (1, 2, 4 s apart), except on a status under 500 - a 404 or 422 fails the same way again.
- **The destination view's trip** has `staleTime: Infinity` (it's a live Travelpayouts search; no
  refetch on window focus) and, like the date grid, `placeholderData: keepPreviousData`: the last
  answer stays on screen, marked as updating, until the next one arrives.
- **A saved search's query** is `enabled` only for an integer id.

## Where state lives

| State | Where | Why there |
|---|---|---|
| Server data | The query cache | Shared by every component that asks, kept across navigation |
| The destination view's search (dates, origin, currency, party, tier, budget) | The URL (`useSearchParams`) | A refresh, the Back button and a shared link all show the same trip |
| Form inputs, search mode | `useState` in `SearchForm` | Local to the form until submit |
| The trip length while dates are typed | `useRef` in `SearchForm` | Remembered between renders, never shown |
| The tier shown in the results | `useState` in `EstimateResults` | The response holds all three tiers, so switching needs no request |
| "Direct flights only", the date grid's offset | `useState` | How the view is shown, not part of the trip |

Values read from the URL come from outside the app and are checked: an unknown `tier` falls back
to `average` (the API never sees the tier, so nothing else would). A component given a `key` is
rebuilt when the key changes: `EstimateResults` gets the search id (a new search starts on the
tier it asked for) and `DateGrid` gets the trip's dates (a picked cell re-centers the grid).

## The search page

- **[SearchForm](../frontend/src/components/SearchForm.tsx)** has two modes. "Where can I go?"
  posts an estimate. "A specific destination" picks one from a `datalist` (Hebrew names, matched
  in English too; `setCustomValidity` blocks submitting until a listed one is chosen) and opens
  its view by URL, without a request of its own.
- All inputs are controlled and hold strings; `handleSubmit` converts them once. Moving the
  departure keeps the trip's length. Party buttons set travelers and rooms together; typing a
  traveler count sets rooms to one per four people. The budget's number field and slider share
  one value. Switching the currency doesn't convert the amount.
- **[EstimateResults](../frontend/src/components/EstimateResults.tsx)** shows the request that
  was sent (`estimate.variables`), not the form's current values. Each row links to the
  destination view with the same search. It tells apart the three empty cases the API reports:
  results, missing data (`has_missing_data`: not the budget's fault), and nothing within budget.
  With no exchange rate for the currency, amounts are in USD and nothing is filtered.

## The destination view

- **[DestinationPage](../frontend/src/pages/DestinationPage.tsx)**: a summary (the cheapest
  flight for the whole party plus the hotel for the chosen tier), what the live search did
  (`live_status`: `found`, `empty`, `failed` or `off`), the tier buttons, and every flight option,
  with a "direct flights only" filter. The summary always uses the cheapest flight, filter or not.
- **[DateGrid](../frontend/src/components/DateGrid.tsx)**: departure dates down the side, return
  dates across, 3 days each way. Each cell is the cheapest collected flight per traveler, colored
  green (cheapest) to red (priciest) by the flight price, not the total, which would rank the
  shortest trips first. An empty cell is missing data; past departures are unavailable. The
  arrows move the grid a week while it still holds a possible trip; picking a cell makes it the
  search.
- **[AgeTag](../frontend/src/components/AgeTag.tsx)**: "seen N days ago", amber once a flight
  price is over 7 days old or a hotel price over 30.

## Hebrew and right to left

- `dir="rtl"` on `<html>` sets the direction for the whole page, and the CSS uses logical
  properties (`padding-inline-start`, `text-align: start`), so nothing assumes left or right
  except the date grid's diagonal corner.
- **Mixed Hebrew and English in one sentence**: the browser lays out English and numbers left to
  right, and a number right after an English code joins its run. So the trip sentence puts the
  origin last - "7.11.2026 – 14.11.2026 (7 לילות), 2 נוסעים בחדר אחד, יציאה מ-TLV, תקציב …":
  with `TLV` earlier, the screen read "יציאה מ-14.11.2026" or "יציאה מ-2".
- **Names**: `cityName()` / `countryName()` show the Hebrew name and fall back to the English one
  when the seed has none (the `*_he` columns are nullable; see [database.md](database.md)).
- **[format.ts](../frontend/src/format.ts)**: dates as Israel writes them (`7.11.2026`,
  `ש׳ 7.11` with the weekday), whole-unit money (`8,000 ₪`), and counts with their Hebrew
  singular (`לילה אחד`, `יעד אחד`). Today is the browser's local date, not
  `toISOString()`'s UTC one, which in Israel is still yesterday until 02:00 or 03:00. Date
  arithmetic runs in UTC so a daylight-saving change can't shift a day.
- The text is Hebrew in the components themselves; there is no translation layer. The API's
  validation messages stay in English.

## Styling and accessibility

- One stylesheet, [styles.css](../frontend/src/styles.css), with the colors as variables on
  `:root`. The search form's grid fits as many 220px columns as there's room for; wide tables
  scroll sideways on a narrow screen; one media query adjusts the hero and buttons on phones.
- **A chosen button is styled by `[aria-pressed="true"]`**, the same attribute that tells a
  screen reader it's pressed, so the two can't disagree. Button groups have `role="group"` and a
  name, every input a label, and every date-grid cell an `aria-label` with its dates and prices
  (color is never the only signal).
- **Text contrast meets WCAG AA (4.5:1)**: green text and the search button use `--green-dark`
  (`--green` is 3.3:1 on white), and the hero's gradient is dark enough for white text across it.
- A failed search's message has `role="alert"`, so a screen reader announces it.
- The component tests find elements by role and name, the way a screen reader does, so a missing
  label breaks a test.

## Tests

```bash
npm test               # Vitest: components in jsdom, the API answered by MSW
npx playwright test    # end to end in Chrome, against the real API and a separate database
```

The component tests render the whole app at a URL ([src/test/renderApp.tsx](../frontend/src/test/renderApp.tsx))
with the time zone pinned to `Asia/Jerusalem`, so local-versus-UTC date bugs show up on any
machine. How both kinds are set up: [testing.md](testing.md).

## Known limitations

- **No error boundary**: an error thrown while rendering blanks the whole page.
- **No production server yet.** Deployed, it would need to serve `index.html` for every app path
  (refreshing `/history/5` asks the server for that path) and send `/api` to the API.
- **History numbers shift**: the list is numbered within the latest 20, so after more searches a
  search's number changes (its link, by id, doesn't).
- **A saved search with no ranking can't say why**: over budget and missing data both save an
  empty ranking, and the message names both.

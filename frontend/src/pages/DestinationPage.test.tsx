import { screen, within } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import { afterEach, beforeEach, expect, test, vi } from "vitest";

import type { Schemas } from "../api/client";
import { dateGrid, DEPART, flight, gridCell, RETURN, TODAY, trip } from "../test/fixtures";
import { renderApp } from "../test/renderApp";
import { server } from "../test/server";
import { bodyRows, cellTexts } from "../test/tables";

const TRIP_URL = `/destinations/7?depart_date=${DEPART}&return_date=${RETURN}&origin_iata=TLV&currency=ILS&tier=average&budget=7500`;

beforeEach(() => {
  vi.useFakeTimers({ toFake: ["Date"], now: new Date(`${TODAY}T09:00:00Z`) });
});

afterEach(() => {
  vi.useRealTimers();
});

// Answers the trip and date-grid calls; returns the dates each trip call asked for.
function answer(tripBody: Schemas["Trip"], grid: Schemas["DateGrid"] = dateGrid()) {
  const tripDates: string[] = [];
  server.use(
    http.get("/api/v1/destinations/:id/trip", ({ request }) => {
      const query = new URL(request.url).searchParams;
      tripDates.push(`${query.get("depart_date")} -> ${query.get("return_date")}`);
      return HttpResponse.json(tripBody);
    }),
    http.get("/api/v1/destinations/:id/date-grid", () => HttpResponse.json(grid)),
  );
  return tripDates;
}

function flightsTable() {
  return screen.getAllByRole("table").find((t) => !t.classList.contains("date-grid"))!;
}

test("shows every live option with the hotel, the budget count and booking links", async () => {
  answer(trip());
  renderApp(TRIP_URL);

  expect(await screen.findByRole("heading", { name: "Paris, France" })).toBeVisible();
  expect(screen.getByText("Live prices for these exact dates.")).toBeVisible();
  expect(screen.getByText(/900.00 ILS a night, 6300.00 ILS in total/)).toBeVisible();
  // Average hotel 6300: 745 + 6300 fits the 7500 budget, 1460 + 6300 doesn't.
  expect(screen.getByText(/options fit your budget/)).toHaveTextContent("1 of 2 options fit your budget with average hotels.");
  expect(screen.getByText(/without checked baggage/)).toBeVisible();
  expect(bodyRows(flightsTable()).map(cellTexts)[0]).toEqual([
    "Air France 975",
    "15:55",
    "09:00",
    "0 / 0",
    "4h 50m / 4h 15m",
    "1460.00",
    "seen 6 days ago",
    "Search on Aviasales",
  ]);
  expect(within(flightsTable()).getAllByRole("link", { name: "Search on Aviasales" })[0]).toHaveAttribute(
    "href",
    "https://www.aviasales.com/search/TLV0711PAR14111",
  );
});

test("direct-only hides flights with a stop", async () => {
  answer(trip());
  const { user } = renderApp(TRIP_URL);
  await screen.findByRole("heading", { name: "Paris, France" });

  await user.click(screen.getByLabelText("Direct flights only"));

  expect(bodyRows(flightsTable()).map((row) => cellTexts(row)[0])).toEqual(["Air France 975"]);
});

test("a tier with no hotel price says so instead of counting the budget", async () => {
  answer(trip());
  const { user } = renderApp(TRIP_URL);
  await screen.findByRole("heading", { name: "Paris, France" });

  await user.click(screen.getByRole("button", { name: "luxury" }));

  expect(screen.getByText("No luxury hotel price on file for this city.", { exact: false })).toBeVisible();
  expect(screen.queryByText(/options fit your budget/)).not.toBeInTheDocument();
});

test("without a live answer it says which collected dates it shows", async () => {
  answer(
    trip({
      source: "collected",
      exact_dates: false,
      flight_out_date: "2026-11-08",
      flights: [flight({ return_stops: null, outbound_minutes: null, return_minutes: null, booking_url: null })],
    }),
  );
  renderApp(TRIP_URL);

  expect(await screen.findByText(/showing collected prices for the nearest dates, 2026-11-08/)).toBeVisible();
  // The collector keeps the outbound stops only - no return stops, durations or booking link.
  expect(cellTexts(bodyRows(flightsTable())[0]).slice(3, 5)).toEqual(["0 / -", "- / -"]);
  expect(within(flightsTable()).queryByRole("link")).not.toBeInTheDocument();
});

test("the date grid shows missing pairs as empty, and a picked cell becomes the search", async () => {
  const tripDates = answer(
    trip(),
    dateGrid([
      gridCell(DEPART, RETURN, 1460),
      gridCell("2026-11-04", "2026-11-11", 600),
      // Two nights: the lowest total (1000 + 2 * 900), but not the cheapest flight.
      gridCell("2026-11-10", "2026-11-12", 1000, 2),
    ]),
  );
  const { user } = renderApp(TRIP_URL);

  expect(await screen.findByText(/Prices on file for 3 of 49 date pairs/)).toBeVisible();
  const cheapest = screen.getByRole("button", { name: /Depart 2026-11-04, return 2026-11-11: flight 600.00 ILS/ });
  const requested = screen.getByRole("button", { name: /Depart 2026-11-07, return 2026-11-14/ });
  expect(requested.closest("td")).toHaveClass("requested");
  // Colored by flight price: green is the cheapest flight, not the shortest trip.
  expect(cheapest.closest("td")).toHaveStyle({ background: "hsl(120, 65%, 82%)" });
  expect(requested.closest("td")).toHaveStyle({ background: "hsl(0, 65%, 82%)" }); // red: the priciest
  expect(cheapest).toHaveAttribute("title", "7 nights: 6900.00 with average hotels");

  await user.click(cheapest);

  expect(await screen.findByText(/From TLV, 2026-11-04 → 2026-11-11/)).toBeVisible();
  expect(tripDates).toEqual([`${DEPART} -> ${RETURN}`, "2026-11-04 -> 2026-11-11"]);
});

test("an unknown destination is not found after one request, without retries", async () => {
  let calls = 0;
  server.use(
    http.get("/api/v1/destinations/:id/trip", () => {
      calls += 1;
      return HttpResponse.json({ detail: "Destination not found" }, { status: 404 });
    }),
    http.get("/api/v1/destinations/:id/date-grid", () => HttpResponse.json({ detail: "x" }, { status: 404 })),
  );
  renderApp(TRIP_URL);

  expect(await screen.findByRole("heading", { name: "Destination not found" })).toBeVisible();
  expect(calls).toBe(1);
});

test("a link with no dates is not found, without asking the API", () => {
  renderApp("/destinations/7");

  expect(screen.getByRole("heading", { name: "Destination not found" })).toBeVisible();
});

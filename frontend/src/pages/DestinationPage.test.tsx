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

  expect(await screen.findByRole("heading", { name: "פריז, צרפת" })).toBeVisible();
  expect(screen.getByText(/מחירים עדכניים לתאריכים המדויקים/)).toBeVisible();
  // The summary: the cheapest flight (745) + 7 nights of the average hotel (6300).
  expect(screen.getByText("7,045 ₪")).toBeVisible();
  expect(screen.getByText("(900 ₪ ללילה)")).toBeVisible();
  // 745 + 6300 fits the 7500 budget, 1460 + 6300 doesn't.
  expect(screen.getByText(/אפשרויות נכנסות בתקציב שלך/)).toHaveTextContent(
    "1 מתוך 2 אפשרויות נכנסות בתקציב שלך עם מלון ממוצע.",
  );
  expect(screen.getByText(/בלי מזוודה/)).toBeVisible();
  expect(bodyRows(flightsTable()).map(cellTexts)[0]).toEqual([
    "Air France 975",
    "15:55",
    "09:00",
    "0 / 0",
    "4:50 ש׳ / 4:15 ש׳",
    "1,460 ₪",
    "נראה לפני 6 ימים",
    "לחיפוש ב-Aviasales",
  ]);
  expect(within(flightsTable()).getAllByRole("link", { name: "לחיפוש ב-Aviasales" })[0]).toHaveAttribute(
    "href",
    "https://www.aviasales.com/search/TLV0711PAR14111",
  );
});

test("for a couple, flights are per traveler and the total is for both", async () => {
  answer(trip());
  renderApp(TRIP_URL.replace("budget=7500", "budget=8000") + "&travelers=2&rooms=1");

  await screen.findByRole("heading", { name: "פריז, צרפת" });
  // 2 x 745 + 6300 (one room) = 7790.
  expect(screen.getByText("7,790 ₪")).toBeVisible();
  expect(screen.getByText("3,895 ₪ לאדם")).toBeVisible();
  // 2 x 745 + 6300 fits 8000; 2 x 1460 + 6300 doesn't.
  expect(screen.getByText(/אפשרויות נכנסות בתקציב שלך/)).toHaveTextContent("1 מתוך 2");
  expect(cellTexts(bodyRows(flightsTable())[0])[5]).toBe("1,460 ₪"); // the list stays per traveler
});

test("direct-only hides flights with a stop", async () => {
  answer(trip());
  const { user } = renderApp(TRIP_URL);
  await screen.findByRole("heading", { name: "פריז, צרפת" });

  await user.click(screen.getByLabelText("טיסות ישירות בלבד"));

  expect(bodyRows(flightsTable()).map((row) => cellTexts(row)[0])).toEqual(["Air France 975"]);
});

test("a tier with no hotel price says so instead of counting the budget", async () => {
  answer(trip());
  const { user } = renderApp(TRIP_URL);
  await screen.findByRole("heading", { name: "פריז, צרפת" });

  await user.click(screen.getByRole("button", { name: "מלון יוקרתי" }));

  expect(screen.getByText("אין לנו מחיר למלון יוקרתי בעיר הזו.")).toBeVisible();
  expect(screen.queryByText(/נכנסות בתקציב שלך/)).not.toBeInTheDocument();
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

  expect(await screen.findByText(/מוצגים מחירים שנאספו לתאריכים הקרובים: 8.11.2026 – 14.11.2026/)).toBeVisible();
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

  expect(await screen.findByText(/יש לנו מחירים ל-3 מתוך 49 צירופי תאריכים/)).toBeVisible();
  const cheapest = screen.getByRole("button", { name: /יציאה 4.11.2026, חזרה 11.11.2026: טיסה 600 ₪/ });
  const requested = screen.getByRole("button", { name: /יציאה 7.11.2026, חזרה 14.11.2026/ });
  expect(requested.closest("td")).toHaveClass("requested");
  // Colored by flight price: green is the cheapest flight, not the shortest trip.
  expect(cheapest.closest("td")).toHaveStyle({ background: "hsl(120, 65%, 82%)" });
  expect(requested.closest("td")).toHaveStyle({ background: "hsl(0, 65%, 82%)" }); // red: the priciest
  expect(cheapest).toHaveAttribute("title", "7 לילות: 6,900 ₪ עם מלון ממוצע");

  await user.click(cheapest);

  expect(await screen.findByText(/4.11.2026 – 11.11.2026/)).toBeVisible();
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

  expect(await screen.findByRole("heading", { name: "היעד לא נמצא" })).toBeVisible();
  expect(calls).toBe(1);
});

test("a link with no dates is not found, without asking the API", () => {
  renderApp("/destinations/7");

  expect(screen.getByRole("heading", { name: "היעד לא נמצא" })).toBeVisible();
});

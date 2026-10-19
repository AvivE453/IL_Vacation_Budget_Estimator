import { screen, waitFor, within } from "@testing-library/react";
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

// Answers the trip and date-grid calls; returns the dates each call asked for.
function answer(tripBody: Schemas["Trip"], grid: Schemas["DateGrid"] = dateGrid()) {
  const tripDates: string[] = [];
  const gridDates: string[] = [];
  const datesOf = (url: string) => {
    const query = new URL(url).searchParams;
    return `${query.get("depart_date")} -> ${query.get("return_date")}`;
  };
  server.use(
    http.get("/api/v1/destinations/:id/trip", ({ request }) => {
      tripDates.push(datesOf(request.url));
      return HttpResponse.json(tripBody);
    }),
    http.get("/api/v1/destinations/:id/date-grid", ({ request }) => {
      gridDates.push(datesOf(request.url));
      return HttpResponse.json(grid);
    }),
  );
  return { tripDates, gridDates };
}

function flightsTable() {
  return screen.getAllByRole("table").find((t) => !t.classList.contains("date-grid"))!;
}

test("shows every live option with its dates, the hotel, and booking links", async () => {
  answer(trip());
  renderApp(TRIP_URL);

  expect(await screen.findByRole("heading", { name: "פריז, צרפת" })).toBeVisible();
  expect(screen.getByText(/מחירים עדכניים לתאריכים המדויקים/)).toBeVisible();
  // The summary: the cheapest flight (745) + 7 nights of the average hotel (6300).
  expect(screen.getByText("7,045 ₪")).toBeVisible();
  expect(screen.getByText("(900 ₪ ללילה)")).toBeVisible();
  expect(screen.getByText(/בלי מזוודה/)).toBeVisible();
  expect(bodyRows(flightsTable()).map(cellTexts)[0]).toEqual([
    "Air France 975",
    "ש׳ 7.11, 15:55", // the flights' own dates, not just times
    "ש׳ 14.11, 09:00",
    "0 / 0",
    "4:50 / 4:15",
    "1,460 ₪",
    "נראה לפני 6 ימים",
    "Aviasales ↗",
  ]);
  expect(within(flightsTable()).getAllByRole("link", { name: "לחיפוש הטיסה ב-Aviasales" })[0]).toHaveAttribute(
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
  expect(cellTexts(bodyRows(flightsTable())[0])[5]).toBe("1,460 ₪"); // the list stays per traveler
});

test("direct-only hides flights with a stop", async () => {
  answer(trip());
  const { user } = renderApp(TRIP_URL);
  await screen.findByRole("heading", { name: "פריז, צרפת" });

  await user.click(screen.getByLabelText("טיסות ישירות בלבד"));

  expect(bodyRows(flightsTable()).map((row) => cellTexts(row)[0])).toEqual(["Air France 975"]);
});

test("a tier with no hotel price says so", async () => {
  answer(trip());
  const { user } = renderApp(TRIP_URL);
  await screen.findByRole("heading", { name: "פריז, צרפת" });

  await user.click(screen.getByRole("button", { name: "מלון יוקרתי" }));

  expect(screen.getByText("אין לנו מחיר למלון יוקרתי בעיר הזו.")).toBeVisible();
});

test("an unknown tier in the URL falls back to the average hotel", async () => {
  answer(trip());
  renderApp(TRIP_URL.replace("tier=average", "tier=cheap"));

  expect(await screen.findByText("(900 ₪ ללילה)")).toBeVisible();
  expect(screen.getByRole("button", { name: "מלון ממוצע" })).toHaveAttribute("aria-pressed", "true");
});

test("when the live search has nothing for these dates, it says so and which collected dates it shows", async () => {
  answer(
    trip({
      source: "collected",
      live_status: "empty",
      exact_dates: false,
      flight_out_date: "2026-11-08",
      flights: [flight({ return_stops: null, outbound_minutes: null, return_minutes: null, booking_url: null })],
    }),
  );
  renderApp(TRIP_URL);

  const note = await screen.findByText(/לא נמצאו מחירים לתאריכים המדויקים האלה/);
  expect(note).toHaveTextContent("מוצגים מחירים שנאספו לתאריכים הקרובים: 8.11.2026 – 14.11.2026.");
  expect(note).toHaveTextContent("התאים הירוקים במפת החום למטה הם תאריכים שיש להם מחירים.");
  expect(note).not.toHaveTextContent("נכשל"); // an empty answer isn't a failure
  // No durations or booking link on collected prices, and no return stops on ones stored before 2026-10-17.
  expect(cellTexts(bodyRows(flightsTable())[0]).slice(3, 5)).toEqual(["0 / -", "- / -"]);
  expect(within(flightsTable()).queryByRole("link")).not.toBeInTheDocument();
});

test.each([
  ["failed", "החיפוש העדכני נכשל."],
  ["off", "החיפוש העדכני כבוי."],
] as const)("a live search that %s says so", async (liveStatus, sentence) => {
  answer(trip({ source: "collected", live_status: liveStatus, exact_dates: true }));
  renderApp(TRIP_URL);

  const note = await screen.findByText(new RegExp(sentence));
  expect(note).toHaveTextContent(`${sentence} מוצגים מחירים שנאספו לתאריכים האלה.`);
});

test("live prices for the exact dates don't point to the date grid", async () => {
  answer(trip());
  renderApp(TRIP_URL);

  const note = await screen.findByText(/מחירים עדכניים לתאריכים המדויקים/);
  expect(note).not.toHaveTextContent("מפת החום");
});

test("past departures in the date grid are unavailable, not offered", async () => {
  // Today is 12.10: a trip on 13.10 shows departures from 10.10 - two already gone.
  answer(
    trip(),
    dateGrid([gridCell("2026-10-10", "2026-10-20", 300), gridCell("2026-10-13", "2026-10-20", 500)]),
  );
  renderApp(TRIP_URL.replace(`depart_date=${DEPART}&return_date=${RETURN}`, "depart_date=2026-10-13&return_date=2026-10-20"));

  // Only the 13.10 cell counts and can be picked; 10.10 has a price but is in the past.
  expect(await screen.findByText(/יש לנו מחירים ל-1 מתוך/)).toBeVisible();
  expect(screen.queryByRole("button", { name: /יציאה 10.10.2026/ })).not.toBeInTheDocument();
  expect(screen.getByRole("button", { name: /יציאה 13.10.2026, חזרה 20.10.2026/ })).toBeVisible();
  expect(screen.getAllByTitle("תאריך היציאה כבר עבר")).not.toHaveLength(0);
});

test("the date grid shows missing pairs as empty, and a picked cell becomes the search", async () => {
  const { tripDates } = answer(
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

test("the arrows move the date grid a week, and a button brings it back", async () => {
  const { tripDates, gridDates } = answer(trip(), dateGrid([gridCell(DEPART, RETURN, 1460)]));
  const { user } = renderApp(TRIP_URL);
  await screen.findByText(/יש לנו מחירים ל-1 מתוך/);

  await user.click(screen.getByRole("button", { name: "חזרה מאוחרת יותר" }));
  await waitFor(() => expect(gridDates.at(-1)).toBe("2026-11-07 -> 2026-11-21"));
  expect(await screen.findByRole("columnheader", { name: /ש׳ 21.11/ })).toBeVisible();

  await user.click(screen.getByRole("button", { name: "יציאה מאוחרת יותר" }));
  await waitFor(() => expect(gridDates.at(-1)).toBe("2026-11-14 -> 2026-11-21"));

  await user.click(screen.getByRole("button", { name: "חזרה לתאריכים שבחרתם" }));
  await waitFor(() => expect(gridDates.at(-1)).toBe(`${DEPART} -> ${RETURN}`));
  expect(screen.queryByRole("button", { name: "חזרה לתאריכים שבחרתם" })).not.toBeInTheDocument();
  expect(tripDates).toEqual([`${DEPART} -> ${RETURN}`]); // moving the grid never changed the trip
});

// The form's default trip leaves today, so its grid already starts in the
// past: the arrows must still move it - only not to earlier departures.
test("a trip leaving today can still move its date grid later", async () => {
  const { gridDates } = answer(trip(), dateGrid());
  const { user } = renderApp(TRIP_URL.replace(`depart_date=${DEPART}&return_date=${RETURN}`, "depart_date=2026-10-12&return_date=2026-10-19"));
  await screen.findByText(/יש לנו מחירים ל-0 מתוך/);

  expect(screen.getByRole("button", { name: "יציאה מוקדמת יותר" })).toBeDisabled(); // all in the past
  for (const name of ["יציאה מאוחרת יותר", "חזרה מאוחרת יותר", "חזרה מוקדמת יותר"]) {
    expect(screen.getByRole("button", { name })).toBeEnabled();
  }

  // A week later: centered on 19.10 for both - not a trip itself, but the grid holds trips.
  await user.click(screen.getByRole("button", { name: "יציאה מאוחרת יותר" }));
  await waitFor(() => expect(gridDates.at(-1)).toBe("2026-10-19 -> 2026-10-19"));
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

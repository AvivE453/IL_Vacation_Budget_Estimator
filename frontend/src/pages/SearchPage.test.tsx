import { screen, waitFor, within } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import { afterEach, beforeEach, expect, test, vi } from "vitest";

import type { Schemas } from "../api/client";
import {
  dateGrid,
  DEPART,
  destination,
  estimate,
  estimateResponse,
  origin,
  RETURN,
  tier,
  TODAY,
  trip,
} from "../test/fixtures";
import { renderApp } from "../test/renderApp";
import { server } from "../test/server";
import { bodyRows, cellTexts } from "../test/tables";

beforeEach(() => {
  vi.useFakeTimers({ toFake: ["Date"], now: new Date(`${TODAY}T09:00:00Z`) });
  server.use(
    http.get("/api/v1/origins", () => HttpResponse.json([origin()])),
    http.get("/api/v1/destinations", () =>
      HttpResponse.json([
        destination(),
        destination({
          destination_id: 8,
          city_name: "Rome",
          country_name: "Italy",
          city_name_he: "רומא",
          country_name_he: "איטליה",
        }),
      ]),
    ),
  );
});

afterEach(() => {
  vi.useRealTimers();
});

// Answers POST /estimates with `response`, and keeps the request body it got.
function answerEstimate(response: Schemas["EstimateResponse"] | HttpResponse<Schemas["HTTPValidationError"]>) {
  const sent: Schemas["EstimateRequest"][] = [];
  server.use(
    http.post("/api/v1/estimates", async ({ request }) => {
      sent.push((await request.json()) as Schemas["EstimateRequest"]);
      return response instanceof HttpResponse ? response : HttpResponse.json(response);
    }),
  );
  return sent;
}

const departInput = () => screen.getByLabelText("תאריך יציאה");
const returnInput = () => screen.getByLabelText(/^תאריך חזרה/);
const budgetInput = () => screen.getByLabelText("תקציב");

async function fillDatesAndBudget(user: ReturnType<typeof renderApp>["user"]) {
  // A date input's value can't be typed character by character; clear() + type() sets it whole.
  await screen.findByLabelText("תאריך יציאה");
  await user.clear(departInput());
  await user.type(departInput(), DEPART);
  await user.clear(returnInput());
  await user.type(returnInput(), RETURN);
  await user.clear(budgetInput());
  await user.type(budgetInput(), "8000");
}

async function search(user: ReturnType<typeof renderApp>["user"]) {
  await user.click(screen.getByRole("button", { name: "מצאו לי יעדים" }));
}

test("the form starts at today + 7 nights, and the return date can't come first", async () => {
  renderApp("/");

  expect(await screen.findByText(/משווים טיסה ומלון ל-2 יעדים/)).toBeVisible();
  expect(departInput()).toHaveValue(TODAY);
  expect(returnInput()).toHaveValue("2026-10-19");
  expect(returnInput()).toHaveAttribute("min", "2026-10-13");
  expect(screen.getByText("7 לילות")).toBeVisible();
  expect(screen.getByRole("button", { name: /לאן כדאי לטוס/, pressed: true })).toBeVisible();
});

test("trip-length chips set the return date, and moving the departure keeps the length", async () => {
  const { user } = renderApp("/");
  await screen.findByLabelText("תאריך יציאה");

  await user.click(screen.getByRole("button", { name: "שבועיים" }));
  expect(returnInput()).toHaveValue("2026-10-26");
  expect(screen.getByText("14 לילות")).toBeVisible();

  await user.clear(departInput());
  await user.type(departInput(), DEPART);
  expect(returnInput()).toHaveValue("2026-11-21"); // still 14 nights
});

test("an estimate sends the form as typed values and ranks the results", async () => {
  const sent = answerEstimate(estimateResponse());
  const { user } = renderApp("/");

  await fillDatesAndBudget(user);
  await user.click(screen.getByRole("button", { name: "$ דולר" }));
  await user.click(screen.getByRole("button", { name: /^יוקרתי/ }));
  await search(user);

  // The answer opens on the requested tier - empty for luxury in this answer.
  expect(await screen.findByRole("heading", { name: "לא נמצאו יעדים" })).toBeVisible();
  expect(sent).toEqual([
    {
      origin_iata: "TLV",
      depart_date: DEPART,
      return_date: RETURN,
      budget_amount: 8000, // a number, not the input's "8000"
      budget_currency: "USD",
      hotel_tier: "luxury",
      travelers: 2, // the default: most vacations are for two
      rooms: 1,
    },
  ]);
});

test("the party buttons and a typed number of travelers set the rooms", async () => {
  const sent = answerEstimate(estimateResponse());
  const { user } = renderApp("/");
  await fillDatesAndBudget(user);
  expect(screen.getByRole("button", { name: "זוג", pressed: true })).toBeVisible(); // the default

  await user.click(screen.getByRole("button", { name: "שני זוגות" }));
  expect([screen.getByLabelText("נוסעים"), screen.getByLabelText("חדרים")].map((i) => (i as HTMLInputElement).value)).toEqual(["4", "2"]);

  // Typed by hand: up to four share a room, so six need two.
  await user.clear(screen.getByLabelText("נוסעים"));
  await user.type(screen.getByLabelText("נוסעים"), "6");
  expect(screen.getByLabelText("חדרים")).toHaveValue(2);

  await search(user);
  await screen.findByRole("table");
  expect(sent[0]).toMatchObject({ travelers: 6, rooms: 2 });
});

test("more people than a room for two says the hotel price may be low", async () => {
  answerEstimate(estimateResponse());
  const { user } = renderApp("/");
  await fillDatesAndBudget(user);

  await user.click(screen.getByRole("button", { name: "משפחה 2+2" }));
  await search(user);

  expect(await screen.findByText(/מחיר המלון הוא לחדר לשני מבוגרים/)).toBeVisible();
});

test("the ranking shows the totals, with how fresh each price is", async () => {
  answerEstimate(estimateResponse());
  const { user } = renderApp("/");
  await fillDatesAndBudget(user);
  await search(user);

  const table = await screen.findByRole("table");
  expect(screen.getByRole("heading", { name: "1 יעדים בתקציב שלך" })).toBeVisible();
  expect(bodyRows(table).map(cellTexts)).toEqual([
    [
      "פריז",
      "1,400 ₪ (700 ₪ לאדם) Air France נראה לפני 2 ימים",
      "2,100 ₪ מחירים לפני 3 ימים",
      "3,500 ₪ 1,750 ₪ לאדם",
    ],
  ]);
  expect(screen.getByRole("link", { name: "לדירוג השמור של החיפוש" })).toHaveAttribute("href", "/history/41");
});

test("switching hotel tier is instant, with no new request", async () => {
  const sent = answerEstimate(estimateResponse());
  const { user } = renderApp("/");
  await fillDatesAndBudget(user);
  await search(user);
  await screen.findByRole("table");

  await user.click(screen.getByRole("button", { name: "מלון חסכוני" }));
  expect(cellTexts(bodyRows(screen.getByRole("table"))[0]).at(-1)).toBe("2,600 ₪ 1,300 ₪ לאדם");

  await user.click(screen.getByRole("button", { name: "מלון יוקרתי" }));
  expect(screen.queryByRole("table")).not.toBeInTheDocument();
  expect(screen.getByText(/אין יעדים עם מחיר טיסה ומלון בתקציב שלך/)).toBeVisible();
  expect(sent).toHaveLength(1);
});

test("a new search starts on its own hotel tier, not the one picked for the last", async () => {
  answerEstimate(estimateResponse());
  const { user } = renderApp("/");
  await fillDatesAndBudget(user);
  await search(user);
  await screen.findByRole("table");
  await user.click(screen.getByRole("button", { name: "מלון חסכוני" }));

  answerEstimate(estimateResponse({ search_id: 42 }));
  await search(user);

  await waitFor(() =>
    expect(screen.getByRole("link", { name: "לדירוג השמור של החיפוש" })).toHaveAttribute("href", "/history/42"),
  );
  expect(screen.getByRole("button", { name: "מלון ממוצע", pressed: true })).toBeVisible();
});

test("nearest dates and old prices are tagged", async () => {
  answerEstimate(
    estimateResponse({
      tiers: {
        budget: tier([]),
        average: tier(
          [
            estimate({
              flight_out_date: "2026-11-08",
              flight_seen_on: "2026-08-08", // 65 days ago
              hotel_price_age_days: 40,
            }),
          ],
          { exact_dates_only: false },
        ),
        luxury: tier([]),
      },
    }),
  );
  const { user } = renderApp("/");
  await fillDatesAndBudget(user);
  await search(user);
  const row = bodyRows(await screen.findByRole("table"))[0];

  expect(within(row).getByText("תאריכים קרובים: 8.11.2026 – 14.11.2026")).toBeVisible();
  // Amber once older than a flight quote lives in the cache (7 days) / 30 days for hotels.
  expect(within(row).getByText("נראה לפני 65 ימים")).toHaveClass("tag-missing");
  expect(within(row).getByText("מחירים לפני 40 ימים")).toHaveClass("tag-missing");
  expect(screen.getByText(/מוצגים התאריכים הקרובים ביותר לכל יעד/)).toBeVisible();
});

test("missing data is told apart from an empty result because of the budget", async () => {
  answerEstimate(
    estimateResponse({
      tiers: {
        budget: tier([], { has_missing_data: true }),
        average: tier([], { has_missing_data: true }),
        luxury: tier([], { has_missing_data: true }),
      },
    }),
  );
  const { user } = renderApp("/");
  await fillDatesAndBudget(user);
  await search(user);

  expect(await screen.findByText(/זה חוסר בנתונים, לא התקציב שלך/)).toBeVisible();
});

test("a 422 shows what's wrong with each field", async () => {
  answerEstimate(
    HttpResponse.json(
      { detail: [{ loc: ["body", "budget_amount"], msg: "Input should be greater than 0", type: "greater_than" }] },
      { status: 422 },
    ),
  );
  const { user } = renderApp("/");
  await fillDatesAndBudget(user);
  await search(user);

  expect(await screen.findByText("התקציב: Input should be greater than 0")).toBeVisible();
});

test("a specific destination opens its view instead of ranking every one", async () => {
  const sent = answerEstimate(estimateResponse());
  const tripQueries: URLSearchParams[] = [];
  server.use(
    http.get("/api/v1/destinations/:id/trip", ({ request, params }) => {
      tripQueries.push(new URL(request.url).searchParams);
      return HttpResponse.json(
        trip({
          destination: destination({
            destination_id: Number(params.id),
            city_name: "Rome",
            country_name: "Italy",
            city_name_he: "רומא",
            country_name_he: "איטליה",
          }),
        }),
      );
    }),
    http.get("/api/v1/destinations/:id/date-grid", () => HttpResponse.json(dateGrid())),
  );
  const { user } = renderApp("/");
  await fillDatesAndBudget(user);

  await user.click(screen.getByRole("button", { name: /יעד מסוים/ }));
  await user.type(screen.getByLabelText("לאן?"), "רומא, איטליה");
  await user.click(screen.getByRole("button", { name: "הראו את היעד" }));

  expect(await screen.findByRole("heading", { name: "רומא, איטליה" })).toBeVisible();
  expect(Object.fromEntries(tripQueries[0])).toEqual({
    depart_date: DEPART,
    return_date: RETURN,
    origin_iata: "TLV",
    currency: "ILS",
    travelers: "2",
    rooms: "1",
  });
  expect(sent).toEqual([]); // a destination view isn't saved to history
});

test("a destination can be typed in English too", async () => {
  const { user } = renderApp("/");
  await screen.findByLabelText("תאריך יציאה");

  await user.click(screen.getByRole("button", { name: /יעד מסוים/ }));
  await user.type(screen.getByLabelText("לאן?"), "Rome, Italy");

  expect(screen.getByLabelText("לאן?")).toBeValid();
});

test("a destination that isn't on the list can't be searched", async () => {
  const { user } = renderApp("/");
  await screen.findByLabelText("תאריך יציאה");

  await user.click(screen.getByRole("button", { name: /יעד מסוים/ }));
  await user.type(screen.getByLabelText("לאן?"), "Atlantis");

  expect(screen.getByLabelText("לאן?")).toBeInvalid();
  expect((screen.getByLabelText("לאן?") as HTMLInputElement).validationMessage).toBe("בחרו יעד מהרשימה");
});

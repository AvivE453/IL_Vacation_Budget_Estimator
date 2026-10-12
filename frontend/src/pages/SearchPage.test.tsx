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
      HttpResponse.json([destination(), destination({ destination_id: 8, city_name: "Rome", country_name: "Italy" })]),
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

async function fillDatesAndBudget(user: ReturnType<typeof renderApp>["user"]) {
  // A date input's value can't be typed character by character; clear() + type() sets it whole.
  await user.clear(await screen.findByLabelText("Departure date"));
  await user.type(screen.getByLabelText("Departure date"), DEPART);
  await user.clear(screen.getByLabelText("Return date"));
  await user.type(screen.getByLabelText("Return date"), RETURN);
  await user.clear(screen.getByLabelText("Budget"));
  await user.type(screen.getByLabelText("Budget"), "8000");
}

test("the form starts at today + 7 nights, and the return date can't come first", async () => {
  renderApp("/");

  expect(await screen.findByText("Tracking 2 destinations, departing from Israel.", { exact: false })).toBeVisible();
  expect(screen.getByLabelText("Departure date")).toHaveValue(TODAY);
  expect(screen.getByLabelText("Return date")).toHaveValue("2026-10-19");
  expect(screen.getByLabelText("Return date")).toHaveAttribute("min", "2026-10-13");
  expect(screen.getByLabelText("Destination")).toHaveDisplayValue("All destinations, cheapest first");
});

test("an estimate sends the form as typed values and ranks the results", async () => {
  const sent = answerEstimate(estimateResponse());
  const { user } = renderApp("/");

  await fillDatesAndBudget(user);
  await user.click(screen.getByRole("button", { name: "Estimate" }));

  const table = await screen.findByRole("table");
  expect(sent).toEqual([
    {
      origin_iata: "TLV",
      depart_date: DEPART,
      return_date: RETURN,
      budget_amount: 8000, // a number, not the input's "8000"
      budget_currency: "ILS",
      hotel_tier: "average",
    },
  ]);
  expect(bodyRows(table).map(cellTexts)).toEqual([
    ["Paris", "1400.00 Air France seen 2 days ago", "2100.00 prices 3 days ago", "3500.00"],
  ]);
  expect(screen.getByRole("link", { name: "View this search's saved ranking" })).toHaveAttribute("href", "/history/41");
});

test("switching hotel tier is instant, with no new request", async () => {
  const sent = answerEstimate(estimateResponse());
  const { user } = renderApp("/");
  await fillDatesAndBudget(user);
  await user.click(screen.getByRole("button", { name: "Estimate" }));
  await screen.findByRole("table");

  await user.click(screen.getByRole("button", { name: "budget" }));
  expect(cellTexts(bodyRows(screen.getByRole("table"))[0]).at(-1)).toBe("2600.00");

  await user.click(screen.getByRole("button", { name: "luxury" }));
  expect(screen.queryByRole("table")).not.toBeInTheDocument();
  expect(screen.getByText(/No destinations have both a flight and hotel price on file within your budget/)).toBeVisible();
  expect(sent).toHaveLength(1);
});

test("a new search starts on its own hotel tier, not the one picked for the last", async () => {
  answerEstimate(estimateResponse());
  const { user } = renderApp("/");
  await fillDatesAndBudget(user);
  await user.click(screen.getByRole("button", { name: "Estimate" }));
  await screen.findByRole("table");
  await user.click(screen.getByRole("button", { name: "budget" }));

  answerEstimate(estimateResponse({ search_id: 42 }));
  await user.click(screen.getByRole("button", { name: "Estimate" }));

  await waitFor(() =>
    expect(screen.getByRole("link", { name: "View this search's saved ranking" })).toHaveAttribute("href", "/history/42"),
  );
  expect(screen.getByRole("button", { name: "average", pressed: true })).toBeVisible();
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
  await user.click(screen.getByRole("button", { name: "Estimate" }));
  const row = bodyRows(await screen.findByRole("table"))[0];

  expect(within(row).getByText("nearest dates: 2026-11-08 → 2026-11-14")).toBeVisible();
  // Amber once older than a flight quote lives in the cache (7 days) / 30 days for hotels.
  expect(within(row).getByText("seen 65 days ago")).toHaveClass("tag-missing");
  expect(within(row).getByText("prices 40 days ago")).toHaveClass("tag-missing");
  expect(screen.getByText(/showing the nearest available dates/)).toBeVisible();
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
  await user.click(screen.getByRole("button", { name: "Estimate" }));

  expect(await screen.findByText(/this is missing data, not a result of your budget/)).toBeVisible();
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
  await user.click(screen.getByRole("button", { name: "Estimate" }));

  expect(await screen.findByText("budget_amount: Input should be greater than 0")).toBeVisible();
});

test("picking a destination opens its view instead of ranking every one", async () => {
  const sent = answerEstimate(estimateResponse());
  const tripQueries: URLSearchParams[] = [];
  server.use(
    http.get("/api/v1/destinations/:id/trip", ({ request, params }) => {
      tripQueries.push(new URL(request.url).searchParams);
      return HttpResponse.json(
        trip({ destination: destination({ destination_id: Number(params.id), city_name: "Rome", country_name: "Italy" }) }),
      );
    }),
    http.get("/api/v1/destinations/:id/date-grid", () => HttpResponse.json(dateGrid())),
  );
  const { user } = renderApp("/");
  await fillDatesAndBudget(user);

  await user.selectOptions(screen.getByLabelText("Destination"), "Rome, Italy");
  await user.click(screen.getByRole("button", { name: "Show this destination" }));

  expect(await screen.findByRole("heading", { name: "Rome, Italy" })).toBeVisible();
  expect(Object.fromEntries(tripQueries[0])).toEqual({
    depart_date: DEPART,
    return_date: RETURN,
    origin_iata: "TLV",
    currency: "ILS",
  });
  expect(sent).toEqual([]); // a destination view isn't saved to history
});

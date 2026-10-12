import { screen } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import { expect, test } from "vitest";

import type { Schemas } from "../api/client";
import { savedSearch } from "../test/fixtures";
import { renderApp } from "../test/renderApp";
import { server } from "../test/server";
import { bodyRows, cellTexts } from "../test/tables";

function summary(searchId: number, createdAt: string): Schemas["SearchSummary"] {
  return {
    search_id: searchId,
    origin_iata: "TLV",
    depart_date: "2026-11-07",
    return_date: "2026-11-14",
    budget_amount: 8000,
    budget_currency: "ILS",
    hotel_tier: "average",
    created_at: createdAt,
  };
}

test("lists this browser's searches newest first, numbered from the oldest", async () => {
  server.use(
    http.get("/api/v1/searches", () =>
      HttpResponse.json([summary(52, "2026-10-12T13:55:12Z"), summary(41, "2026-10-11T08:00:00Z")]),
    ),
  );
  renderApp("/history");

  const rows = bodyRows(await screen.findByRole("table"));
  expect(rows.map(cellTexts)).toEqual([
    ["2", "TLV", "2026-11-07", "2026-11-14", "8000.00 ILS", "average", "2026-10-12 16:55"],
    ["1", "TLV", "2026-11-07", "2026-11-14", "8000.00 ILS", "average", "2026-10-11 11:00"],
  ]);
  expect(screen.getByRole("link", { name: "2" })).toHaveAttribute("href", "/history/52");
});

test("a browser with no searches is pointed to the search form", async () => {
  server.use(http.get("/api/v1/searches", () => HttpResponse.json([])));
  renderApp("/history");

  expect(await screen.findByText(/No searches from this browser yet/)).toBeVisible();
});

test("a saved search shows the ranking saved at the time", async () => {
  server.use(http.get("/api/v1/searches/41", () => HttpResponse.json(savedSearch())));
  renderApp("/history/41");

  expect(await screen.findByRole("heading", { name: "TLV, 2026-11-07 → 2026-11-14" })).toBeVisible();
  expect(screen.getByText("These estimates were based on an exact date match.")).toBeVisible();
  expect(bodyRows(screen.getByRole("table")).map(cellTexts)).toEqual([
    ["1", "Paris", "Air France", "average", "3500.00", "yes"],
  ]);
});

test("a search where every destination was over budget is found, not a 404", async () => {
  server.use(http.get("/api/v1/searches/41", () => HttpResponse.json(savedSearch({ results: [] }))));
  renderApp("/history/41");

  expect(await screen.findByText(/Every destination was over budget/)).toBeVisible();
});

test("another browser's search is not found after one request, without retries", async () => {
  let calls = 0;
  server.use(
    http.get("/api/v1/searches/:id", () => {
      calls += 1;
      return HttpResponse.json({ detail: "Search not found" }, { status: 404 });
    }),
  );
  renderApp("/history/99");

  expect(await screen.findByRole("heading", { name: "Search not found" })).toBeVisible();
  expect(calls).toBe(1);
});

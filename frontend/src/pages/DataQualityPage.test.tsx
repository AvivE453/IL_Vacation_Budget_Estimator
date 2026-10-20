import { screen } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import { expect, test } from "vitest";

import type { Schemas } from "../api/client";
import { renderApp } from "../test/renderApp";
import { server } from "../test/server";
import { bodyRows, cellTexts } from "../test/tables";

test("shows coverage per destination, gaps included, and the daily volume", async () => {
  server.use(
    http.get("/api/v1/data-quality", () =>
      HttpResponse.json({
        coverage: [
          {
            city_name: "Barcelona",
            country_name: "Spain",
            city_name_he: "ברצלונה",
            country_name_he: "ספרד",
            flight_obs_count: 120,
            hotel_sample_size: 20,
            hotel_price_age_days: 1,
          },
          {
            // No Hebrew name in the seed: the English one is shown.
            city_name: "Madrid",
            country_name: "Spain",
            city_name_he: null,
            country_name_he: "ספרד",
            flight_obs_count: 0,
            hotel_sample_size: null,
            hotel_price_age_days: null,
          },
        ],
        collection_volume: [{ day: "2026-10-07", observations_collected: 9312, observations_from_searches: 12 }],
      } satisfies Schemas["DataQuality"]),
    ),
  );

  renderApp("/data-quality");

  const [coverage, volume] = await screen.findAllByRole("table");
  expect(bodyRows(coverage).map(cellTexts)).toEqual([
    ["ברצלונה", "ספרד", "120", "20", "אתמול"],
    ["Madrid", "ספרד", "0", "-", "-"],
  ]);
  expect(bodyRows(volume).map(cellTexts)).toEqual([["7.10.2026", "9312", "12"]]);
});

test("a busy API is retried, and if it stays busy the page says so", async () => {
  let requests = 0;
  server.use(
    http.get("/api/v1/data-quality", () => {
      requests += 1;
      return HttpResponse.json({ detail: "Server busy, try again shortly" }, { status: 503 });
    }),
  );

  renderApp("/data-quality");

  expect(await screen.findByText("לא הצלחנו לטעון את דוח איכות הנתונים: HTTP 503")).toBeVisible();
  expect(requests).toBe(4); // the first try and shouldRetry's three retries
});

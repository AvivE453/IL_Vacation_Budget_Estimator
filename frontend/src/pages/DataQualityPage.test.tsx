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
            flight_obs_count: 120,
            hotel_sample_size: 20,
            hotel_price_age_days: 1,
          },
          {
            city_name: "Madrid",
            country_name: "Spain",
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
    ["Barcelona", "Spain", "120", "20", "1 day ago"],
    ["Madrid", "Spain", "0", "-", "-"],
  ]);
  expect(bodyRows(volume).map(cellTexts)).toEqual([["2026-10-07", "9312", "12"]]);
});

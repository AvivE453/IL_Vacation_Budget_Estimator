import { http, HttpResponse } from "msw";
import { describe, expect, test } from "vitest";

import { shouldRetry } from "../queryClient";
import { server } from "../test/server";
import { api, ApiError, unwrap, validationMessages } from "./client";

describe("unwrap", () => {
  test("returns the data of a successful call", async () => {
    server.use(http.get("/api/v1/origins", () => HttpResponse.json([{ iata_code: "TLV" }])));

    await expect(unwrap(api.GET("/api/v1/origins"))).resolves.toEqual([{ iata_code: "TLV" }]);
  });

  // The trap from 3.1.4: openapi-fetch reports an empty error body as "",
  // which `if (error)` would take for success.
  test("throws on an error with an empty body, like Vite's 502 when the API is down", async () => {
    server.use(http.get("/api/v1/origins", () => new HttpResponse(null, { status: 502 })));

    const error = await unwrap(api.GET("/api/v1/origins")).catch((e: unknown) => e);

    expect(error).toBeInstanceOf(ApiError);
    expect(error).toMatchObject({ status: 502, message: "HTTP 502" });
  });
});

describe("validationMessages", () => {
  test("names the field, except for a check on the whole request", () => {
    const error = new ApiError(422, {
      detail: [
        { loc: ["body", "budget_amount"], msg: "Input should be greater than 0", type: "greater_than" },
        { loc: ["body"], msg: "Value error, return_date must be after depart_date", type: "value_error" },
      ],
    });

    expect(validationMessages(error)).toEqual([
      "budget_amount: Input should be greater than 0",
      "Value error, return_date must be after depart_date",
    ]);
  });

  test("is empty for any other error", () => {
    expect(validationMessages(new ApiError(503, { detail: "busy" }))).toEqual([]);
    expect(validationMessages(new Error("network"))).toEqual([]);
  });
});

describe("shouldRetry", () => {
  test.each([
    [new ApiError(503, null), true],
    [new ApiError(502, ""), true],
    [new Error("Failed to fetch"), true],
    [new ApiError(404, null), false],
    [new ApiError(422, null), false],
  ])("%s -> %s", (error, expected) => {
    expect(shouldRetry(0, error)).toBe(expected);
  });

  test("gives up after three retries", () => {
    expect(shouldRetry(2, new ApiError(503, null))).toBe(true);
    expect(shouldRetry(3, new ApiError(503, null))).toBe(false);
  });
});

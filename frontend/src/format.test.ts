import { afterEach, describe, expect, test, vi } from "vitest";

import { addDays, clock, dateTime, daysAgo, daysSince, duration, nightsBetween, shortDate, todayIso } from "./format";

// The tests run in Israel's time zone (vite.config.ts -> test.env.TZ), where
// the UTC date lags the local one for two or three hours after midnight.
afterEach(() => {
  vi.useRealTimers();
});

describe("todayIso", () => {
  test("is the local date, not the UTC one, just after midnight", () => {
    vi.useFakeTimers({ toFake: ["Date"], now: new Date("2026-10-11T21:30:00Z") }); // 00:30 in Israel

    expect(todayIso()).toBe("2026-10-12");
    expect(new Date().toISOString().slice(0, 10)).toBe("2026-10-11"); // what it must not use
  });
});

describe("addDays and nightsBetween", () => {
  test.each([
    ["2026-11-07", 7, "2026-11-14"],
    ["2026-12-29", 7, "2027-01-05"], // into the next year
    ["2028-02-28", 1, "2028-02-29"], // a leap day
    ["2026-03-29", 1, "2026-03-30"], // Israel's clocks go forward the night before
    ["2026-11-07", -3, "2026-11-04"],
  ])("%s + %i days = %s", (from, days, expected) => {
    expect(addDays(from, days)).toBe(expected);
    expect(nightsBetween(from, expected)).toBe(days);
  });
});

test("daysSince counts from the local today", () => {
  vi.useFakeTimers({ toFake: ["Date"], now: new Date("2026-10-12T09:00:00Z") });

  expect(daysSince("2026-10-12")).toBe(0);
  expect(daysSince("2026-10-05")).toBe(7);
});

test("daysAgo", () => {
  expect([daysAgo(null), daysAgo(0), daysAgo(1), daysAgo(12)]).toEqual(["-", "today", "1 day ago", "12 days ago"]);
});

test("shortDate shows the weekday", () => {
  expect(shortDate("2026-11-07")).toBe("Sat 7 Nov");
});

test("dateTime is in the local time zone", () => {
  expect(dateTime("2026-10-12T13:55:12Z")).toBe("2026-10-12 16:55");
});

test("clock and duration", () => {
  expect([clock("18:55:00"), clock(null)]).toEqual(["18:55", "-"]);
  expect([duration(305), duration(60), duration(null)]).toEqual(["5h 05m", "1h 00m", "-"]);
});

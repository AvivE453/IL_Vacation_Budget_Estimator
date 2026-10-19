import { afterEach, describe, expect, test, vi } from "vitest";

import {
  addDays,
  clock,
  dateTime,
  daysAgo,
  daysSince,
  destinationCount,
  duration,
  formatDate,
  legTime,
  money,
  nights,
  nightsBetween,
  shortDate,
  todayIso,
} from "./format";

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
  expect([daysAgo(null), daysAgo(0), daysAgo(1), daysAgo(12)]).toEqual(["-", "היום", "אתמול", "לפני 12 ימים"]);
});

test("dates are written the Israeli way, the short one with its weekday", () => {
  expect(formatDate("2026-11-07")).toBe("7.11.2026");
  expect(shortDate("2026-11-07")).toBe("ש׳ 7.11"); // a Saturday
  expect(shortDate("2026-11-08")).toBe("א׳ 8.11");
});

test("dateTime is in the local time zone", () => {
  expect(dateTime("2026-10-12T13:55:12Z")).toBe("12.10.2026 16:55");
});

test("money is whole units with the currency's symbol", () => {
  expect([money(8000, "ILS"), money(1459.62, "USD"), money(745.4, "EUR")]).toEqual(["8,000 ₪", "1,460 $", "745 €"]);
});

test("nights, clock and duration", () => {
  expect([nights(1), nights(7)]).toEqual(["לילה אחד", "7 לילות"]);
  expect([destinationCount(1), destinationCount(5)]).toEqual(["יעד אחד", "5 יעדים"]);
  expect([clock("18:55:00"), clock(null)]).toEqual(["18:55", "-"]);
  expect([legTime("2026-11-07", "18:55:00"), legTime("2026-11-07", null)]).toEqual(["ש׳ 7.11, 18:55", "ש׳ 7.11"]);
  expect([duration(305), duration(60), duration(null)]).toEqual(["5:05", "1:00", "-"]);
});

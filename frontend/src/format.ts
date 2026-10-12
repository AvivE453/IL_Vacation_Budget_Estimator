// Dates travel as "YYYY-MM-DD" strings, the same as the API sends them.

// Today in the browser's time zone. Not new Date().toISOString(): that is the
// UTC date, which in Israel is still yesterday until 02:00 or 03:00.
export function todayIso(): string {
  const now = new Date();
  return toIsoDate(now.getFullYear(), now.getMonth(), now.getDate());
}

export function addDays(isoDate: string, days: number): string {
  const [year, month, day] = isoDate.split("-").map(Number);
  const date = new Date(Date.UTC(year, month - 1, day + days));
  return toIsoDate(date.getUTCFullYear(), date.getUTCMonth(), date.getUTCDate());
}

export function nightsBetween(departIso: string, returnIso: string): number {
  return Math.round((Date.parse(returnIso) - Date.parse(departIso)) / 86_400_000);
}

function toIsoDate(year: number, monthIndex: number, day: number): string {
  return `${year}-${String(monthIndex + 1).padStart(2, "0")}-${String(day).padStart(2, "0")}`;
}

export function money(amount: number): string {
  return amount.toFixed(2);
}

// "2026-10-12T13:55:12Z" -> "2026-10-12 16:55", in the browser's time zone.
export function dateTime(isoTimestamp: string): string {
  const d = new Date(isoTimestamp);
  const time = `${String(d.getHours()).padStart(2, "0")}:${String(d.getMinutes()).padStart(2, "0")}`;
  return `${toIsoDate(d.getFullYear(), d.getMonth(), d.getDate())} ${time}`;
}

export function daysAgo(days: number | null): string {
  if (days === null) {
    return "-";
  }
  if (days === 0) {
    return "today";
  }
  return `${days} day${days === 1 ? "" : "s"} ago`;
}

export function daysSince(isoDate: string): number {
  return nightsBetween(isoDate, todayIso());
}

// "2026-11-07" -> "Sat 7 Nov": the weekday matters when choosing between dates.
export function shortDate(isoDate: string): string {
  const [year, month, day] = isoDate.split("-").map(Number);
  return new Date(Date.UTC(year, month - 1, day)).toLocaleDateString("en-GB", {
    weekday: "short",
    day: "numeric",
    month: "short",
    timeZone: "UTC",
  });
}

// "18:55:00" -> "18:55"
export function clock(time: string | null): string {
  return time === null ? "-" : time.slice(0, 5);
}

// 305 -> "5h 05m"
export function duration(minutes: number | null): string {
  if (minutes === null) {
    return "-";
  }
  return `${Math.floor(minutes / 60)}h ${String(minutes % 60).padStart(2, "0")}m`;
}

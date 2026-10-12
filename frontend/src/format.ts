// Dates travel as "YYYY-MM-DD" strings, the same as the API sends them; what
// the user reads is Hebrew, in Israel's formats.

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

const CURRENCY_SYMBOLS: Record<string, string> = { ILS: "₪", USD: "$", EUR: "€" };

// 8000 -> "8,000 ₪": whole units - agorot or cents mean nothing in an estimate.
export function money(amount: number, currency: string): string {
  const whole = Math.round(amount).toLocaleString("en-US");
  return `${whole} ${CURRENCY_SYMBOLS[currency] ?? currency}`;
}

// "2026-11-07" -> "7.11.2026", the way dates are written in Israel.
export function formatDate(isoDate: string): string {
  const [year, month, day] = isoDate.split("-").map(Number);
  return `${day}.${month}.${year}`;
}

const WEEKDAYS = ["א׳", "ב׳", "ג׳", "ד׳", "ה׳", "ו׳", "ש׳"];

// "2026-11-07" -> "ש׳ 7.11": the weekday matters when choosing between dates.
export function shortDate(isoDate: string): string {
  const [year, month, day] = isoDate.split("-").map(Number);
  const weekday = new Date(Date.UTC(year, month - 1, day)).getUTCDay();
  return `${WEEKDAYS[weekday]} ${day}.${month}`;
}

// "2026-10-12T13:55:12Z" -> "12.10.2026 16:55", in the browser's time zone.
export function dateTime(isoTimestamp: string): string {
  const d = new Date(isoTimestamp);
  const time = `${String(d.getHours()).padStart(2, "0")}:${String(d.getMinutes()).padStart(2, "0")}`;
  return `${d.getDate()}.${d.getMonth() + 1}.${d.getFullYear()} ${time}`;
}

export function nights(count: number): string {
  return count === 1 ? "לילה אחד" : `${count} לילות`;
}

export function daysAgo(days: number | null): string {
  if (days === null) {
    return "-";
  }
  if (days === 0) {
    return "היום";
  }
  if (days === 1) {
    return "אתמול";
  }
  return `לפני ${days} ימים`;
}

export function daysSince(isoDate: string): number {
  return nightsBetween(isoDate, todayIso());
}

// "18:55:00" -> "18:55"
export function clock(time: string | null): string {
  return time === null ? "-" : time.slice(0, 5);
}

// A flight leg's day and, when known, its time: "ש׳ 7.11, 18:55" or "ש׳ 7.11".
export function legTime(isoDate: string, time: string | null): string {
  return time === null ? shortDate(isoDate) : `${shortDate(isoDate)}, ${clock(time)}`;
}

// 305 -> "5:05" (hours:minutes; the column header names the unit)
export function duration(minutes: number | null): string {
  if (minutes === null) {
    return "-";
  }
  return `${Math.floor(minutes / 60)}:${String(minutes % 60).padStart(2, "0")}`;
}

export const TIER_NAMES = { budget: "חסכוני", average: "ממוצע", luxury: "יוקרתי" } as const;
export type HotelTier = keyof typeof TIER_NAMES;
export const TIERS: HotelTier[] = ["budget", "average", "luxury"];

// The Hebrew name, or the English one when the seed has none.
export function cityName(place: { city_name: string; city_name_he?: string | null }): string {
  return place.city_name_he ?? place.city_name;
}

export function countryName(place: { country_name: string; country_name_he?: string | null }): string {
  return place.country_name_he ?? place.country_name;
}

export function travelers(count: number): string {
  return count === 1 ? "נוסע אחד" : `${count} נוסעים`;
}

export function rooms(count: number): string {
  return count === 1 ? "חדר אחד" : `${count} חדרים`;
}

// A room's price is for two adults (SerpApi's default occupancy): say so
// when more people share a room, since an extra bed may cost more.
export function crowdedRoomNote(travelerCount: number, roomCount: number): string | null {
  return travelerCount > 2 * roomCount
    ? "מחיר המלון הוא לחדר לשני מבוגרים. בחדר עם יותר אנשים, מיטה נוספת עשויה לעלות יותר."
    : null;
}

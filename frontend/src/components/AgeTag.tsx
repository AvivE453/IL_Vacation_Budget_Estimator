import { daysAgo } from "../format";

// How old the flight cache's quotes get before they drop out (about a week,
// measured 2026-10-12), and how old a hotel snapshot can be before it's worth
// re-collecting.
export const FLIGHT_STALE_AFTER_DAYS = 7;
export const HOTEL_STALE_AFTER_DAYS = 30;

type Props = {
  label: string;
  days: number | null;
  staleAfter: number;
};

// "נראה לפני 12 ימים", amber once older than staleAfter.
export default function AgeTag({ label, days, staleAfter }: Props) {
  const stale = days === null || days > staleAfter;
  return (
    <span className={stale ? "tag tag-missing" : "tag tag-fresh"}>
      {label} {days === null ? "בתאריך לא ידוע" : daysAgo(days)}
    </span>
  );
}

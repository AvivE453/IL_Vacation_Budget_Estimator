import { daysAgo } from "../format";

// How old the flight cache's quotes get before they drop out (FRESHNESS_DAYS
// in app/queries.py), and how old a hotel snapshot can be before it's worth
// re-collecting.
export const FLIGHT_STALE_AFTER_DAYS = 7;
export const HOTEL_STALE_AFTER_DAYS = 30;

type Props = {
  label: string;
  days: number | null;
  staleAfter: number;
};

// "hotel prices 12 days ago", amber once older than staleAfter.
export default function AgeTag({ label, days, staleAfter }: Props) {
  const stale = days === null || days > staleAfter;
  return (
    <span className={stale ? "tag tag-missing" : "tag tag-fresh"}>
      {label} {days === null ? "date unknown" : daysAgo(days)}
    </span>
  );
}

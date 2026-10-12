import { keepPreviousData, useQuery } from "@tanstack/react-query";
import { useState } from "react";

import { api, type Schemas, unwrap } from "../api/client";
import { addDays, formatDate, type HotelTier, money, nights, shortDate, TIER_NAMES, todayIso } from "../format";

type TripQuery = {
  depart_date: string;
  return_date: string;
  origin_iata: string;
  currency: Schemas["EstimateRequest"]["budget_currency"];
  travelers: number;
  rooms: number;
};

type Props = {
  destinationId: number;
  query: TripQuery;
  tier: HotelTier;
  onPick: (departDate: string, returnDate: string) => void;
};

// The arrows move the grid a week at a time.
const STEP_DAYS = 7;

// Departure dates down the side, return dates across the top, each cell the
// cheapest round-trip flight on file for exactly that pair - green the
// cheapest, red the priciest. Colored by the flight, not the total: the hotel
// costs the same each night, so totals would only rank short trips first.
// An empty cell is a pair with no flight on file: missing data, not a price of zero.
//
// The grid starts around the trip's dates and the arrows move it; the page
// gives it a new key when the trip's dates change, so a picked cell starts a
// fresh grid around the new trip.
export default function DateGrid({ destinationId, query, tier, onPick }: Props) {
  const [shift, setShift] = useState({ depart: 0, back: 0 });
  const center = {
    ...query,
    depart_date: addDays(query.depart_date, shift.depart),
    return_date: addDays(query.return_date, shift.back),
  };
  const grid = useQuery({
    queryKey: ["date-grid", destinationId, center],
    queryFn: () =>
      unwrap(
        api.GET("/api/v1/destinations/{destination_id}/date-grid", {
          params: { path: { destination_id: destinationId }, query: center },
        }),
      ),
    // While the next week loads, keep showing this one.
    placeholderData: keepPreviousData,
  });

  if (grid.isPending) {
    return <p className="updating">טוען תאריכים גמישים...</p>;
  }
  if (grid.error) {
    return <p className="error">לא הצלחנו לטעון תאריכים גמישים: {grid.error.message}</p>;
  }

  const { days, currency } = grid.data;
  // A departure that has already passed can't be booked: its cells are shown
  // as unavailable, and left out of the counts and the colors.
  const today = todayIso();
  const cellList = grid.data.cells.filter((cell) => cell.depart_date >= today);
  const offsets = Array.from({ length: 2 * days + 1 }, (_, i) => i - days);
  const departDates = offsets.map((offset) => addDays(center.depart_date, offset));
  const returnDates = offsets.map((offset) => addDays(center.return_date, offset));
  const cells = new Map(cellList.map((cell) => [`${cell.depart_date}|${cell.return_date}`, cell]));

  const prices = cellList.map((cell) => cell.flight_amount);
  const cheapest = Math.min(...prices);
  const priciest = Math.max(...prices);

  // 120 (green) for the cheapest down to 0 (red) for the priciest.
  function color(price: number): string {
    const share = priciest === cheapest ? 0 : (price - cheapest) / (priciest - cheapest);
    return `hsl(${Math.round(120 * (1 - share))}, 65%, 82%)`;
  }

  // A move is allowed while the grid still holds a trip - its latest return
  // after its earliest departure; its middle pair needn't be one - and an
  // earlier departure only while some of its departures are still ahead.
  // (A grid around a trip that leaves today already starts in the past.)
  function canMove(departDays: number, backDays: number): boolean {
    const depart = addDays(center.depart_date, departDays);
    const back = addDays(center.return_date, backDays);
    const holdsATrip = addDays(back, days) > addDays(depart, -days);
    const someDepartureAhead = departDays >= 0 || addDays(depart, days) >= today;
    return holdsATrip && someDepartureAhead;
  }

  function move(departDays: number, backDays: number) {
    setShift({ depart: shift.depart + departDays, back: shift.back + backDays });
  }

  const arrow = (label: string, symbol: string, departDays: number, backDays: number) => (
    <button
      type="button"
      className="grid-arrow"
      aria-label={label}
      title={label}
      disabled={!canMove(departDays, backDays)}
      onClick={() => move(departDays, backDays)}
    >
      {symbol}
    </button>
  );

  const possiblePairs = departDates.filter((d) => d >= today).flatMap((d) => returnDates.filter((r) => r > d)).length;
  const moved = shift.depart !== 0 || shift.back !== 0;

  return (
    <section className="card">
      <h2>תאריכים גמישים</h2>
      <p className="note">
        מחיר הטיסה הלוך-חזור לאדם. ירוק הוא הזול ביותר, ומעבר עם העכבר מראה את הסך לכל הנוסעים עם מלון{" "}
        {TIER_NAMES[tier]}. יש לנו מחירים ל-{cellList.length} מתוך {possiblePairs} צירופי תאריכים; תא ריק הוא צירוף שאין
        לו מחיר שנאסף. החצים מזיזים את הטבלה בשבוע, ולחיצה על תא מציגה את הטיול הזה.
      </p>
      {moved && (
        <p>
          <button type="button" className="btn" onClick={() => setShift({ depart: 0, back: 0 })}>
            חזרה לתאריכים שבחרתם
          </button>
        </p>
      )}
      {grid.isPlaceholderData && <p className="updating">טוען...</p>}
      <div className="grid-scroll">
        <table className="date-grid">
          <thead>
            <tr>
              {/* Split diagonally: return dates run across the top, departure dates down the side. */}
              <th className="grid-corner">
                <span className="corner-return">חזרה</span>
                <span className="corner-depart">יציאה</span>
              </th>
              {returnDates.map((r, i) => (
                <th key={r}>
                  {i === 0 && arrow("חזרה מוקדמת יותר", "→", 0, -STEP_DAYS)}
                  {shortDate(r)}
                  {i === returnDates.length - 1 && arrow("חזרה מאוחרת יותר", "←", 0, STEP_DAYS)}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {departDates.map((d, i) => (
              <tr key={d}>
                <th>
                  {i === 0 && arrow("יציאה מוקדמת יותר", "▲", -STEP_DAYS, 0)}
                  {shortDate(d)}
                  {i === departDates.length - 1 && arrow("יציאה מאוחרת יותר", "▼", STEP_DAYS, 0)}
                </th>
                {returnDates.map((r) => {
                  const cell = cells.get(`${d}|${r}`);
                  const isRequested = d === query.depart_date && r === query.return_date;
                  const className = isRequested ? "requested" : undefined;
                  if (r <= d) {
                    return <td key={r} className="impossible" />;
                  }
                  if (d < today) {
                    return <td key={r} className="impossible" title="תאריך היציאה כבר עבר" />;
                  }
                  if (cell === undefined) {
                    return (
                      <td key={r} className={className}>
                        &mdash;
                      </td>
                    );
                  }
                  const total = cell.total_amount[tier];
                  const totalNote =
                    total === null
                      ? `אין מחיר למלון ${TIER_NAMES[tier]}`
                      : `${money(total, currency)} עם מלון ${TIER_NAMES[tier]}`;
                  return (
                    <td key={r} className={className} style={{ background: color(cell.flight_amount) }}>
                      <button
                        type="button"
                        onClick={() => onPick(d, r)}
                        title={`${nights(cell.nights)}: ${totalNote}`}
                        aria-label={`יציאה ${formatDate(d)}, חזרה ${formatDate(r)}: טיסה ${money(cell.flight_amount, currency)} לאדם, ${nights(cell.nights)}, ${totalNote}`}
                      >
                        {Math.round(cell.flight_amount).toLocaleString("en-US")}
                      </button>
                    </td>
                  );
                })}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}

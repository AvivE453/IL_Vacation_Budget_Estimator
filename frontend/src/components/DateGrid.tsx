import type { Schemas } from "../api/client";
import { addDays, formatDate, type HotelTier, money, nights, shortDate, TIER_NAMES } from "../format";

type Props = {
  grid: Schemas["DateGrid"];
  departDate: string;
  returnDate: string;
  tier: HotelTier;
  onPick: (departDate: string, returnDate: string) => void;
};

// Departure dates down the side, return dates across the top, each cell the
// cheapest round-trip flight on file for exactly that pair - green the
// cheapest, red the priciest. Colored by the flight, not the total: the hotel
// costs the same each night, so totals would only rank short trips first.
// An empty cell is a pair with no flight on file: missing data, not a price of zero.
export default function DateGrid({ grid, departDate, returnDate, tier, onPick }: Props) {
  const offsets = Array.from({ length: 2 * grid.days + 1 }, (_, i) => i - grid.days);
  const departDates = offsets.map((offset) => addDays(departDate, offset));
  const returnDates = offsets.map((offset) => addDays(returnDate, offset));
  const cells = new Map(grid.cells.map((cell) => [`${cell.depart_date}|${cell.return_date}`, cell]));

  const prices = grid.cells.map((cell) => cell.flight_amount);
  const cheapest = Math.min(...prices);
  const priciest = Math.max(...prices);

  // 120 (green) for the cheapest down to 0 (red) for the priciest.
  function color(price: number): string {
    const share = priciest === cheapest ? 0 : (price - cheapest) / (priciest - cheapest);
    return `hsl(${Math.round(120 * (1 - share))}, 65%, 82%)`;
  }

  const possiblePairs = departDates.flatMap((d) => returnDates.filter((r) => r > d)).length;

  return (
    <section className="card">
      <h2>תאריכים גמישים</h2>
      <p className="note">
        מחיר הטיסה הלוך-חזור, עד {grid.days} ימים לפני ואחרי התאריכים שבחרתם. ירוק הוא הזול ביותר, ומעבר עם העכבר
        מראה את הסך עם מלון {TIER_NAMES[tier]}. יש לנו מחירים ל-{grid.cells.length} מתוך {possiblePairs} צירופי
        תאריכים; תא ריק הוא צירוף שאין לו מחיר שנאסף. לחיצה על תא מציגה את הטיול הזה.
      </p>
      <div className="grid-scroll">
        <table className="date-grid">
          <thead>
            <tr>
              <th>יציאה \ חזרה</th>
              {returnDates.map((r) => (
                <th key={r}>{shortDate(r)}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {departDates.map((d) => (
              <tr key={d}>
                <th>{shortDate(d)}</th>
                {returnDates.map((r) => {
                  const cell = cells.get(`${d}|${r}`);
                  const isRequested = d === departDate && r === returnDate;
                  const className = isRequested ? "requested" : undefined;
                  if (r <= d) {
                    return <td key={r} className="impossible" />;
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
                      : `${money(total, grid.currency)} עם מלון ${TIER_NAMES[tier]}`;
                  return (
                    <td key={r} className={className} style={{ background: color(cell.flight_amount) }}>
                      <button
                        type="button"
                        onClick={() => onPick(d, r)}
                        title={`${nights(cell.nights)}: ${totalNote}`}
                        aria-label={`יציאה ${formatDate(d)}, חזרה ${formatDate(r)}: טיסה ${money(cell.flight_amount, grid.currency)}, ${nights(cell.nights)}, ${totalNote}`}
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

import { useState } from "react";
import { Link } from "react-router";

import type { Schemas } from "../api/client";
import {
  cityName,
  crowdedRoomNote,
  daysSince,
  formatDate,
  type HotelTier,
  money,
  nights,
  nightsBetween,
  rooms,
  TIER_NAMES,
  TIERS,
  travelers,
} from "../format";
import { destinationUrl } from "../links";
import AgeTag, { FLIGHT_STALE_AFTER_DAYS, HOTEL_STALE_AFTER_DAYS } from "./AgeTag";

type Props = {
  request: Schemas["EstimateRequest"];
  response: Schemas["EstimateResponse"];
};

export default function EstimateResults({ request, response }: Props) {
  // The response has all three tiers, so switching is instant - no new request.
  // Only the requested tier was saved to history.
  const [tier, setTier] = useState<HotelTier>(request.hotel_tier ?? "average");
  const chosen = response.tiers[tier];
  const requestedNights = nightsBetween(request.depart_date, request.return_date);
  const { currency } = response;
  const budgetFiltered = response.budget_amount !== null;
  const travelerCount = request.travelers ?? 1;
  const roomCount = request.rooms ?? 1;
  const roomNote = crowdedRoomNote(travelerCount, roomCount);
  const tripSearch = {
    ...request,
    currency: request.budget_currency,
    budget: request.budget_amount,
    tier,
  };

  return (
    <section className="card">
      <h2>
        {chosen.destinations.length > 0
          ? `${chosen.destinations.length} יעדים ${budgetFiltered ? "בתקציב שלך" : ""}`
          : "לא נמצאו יעדים"}
      </h2>
      <p className="note">
        {formatDate(request.depart_date)} – {formatDate(request.return_date)} ({nights(requestedNights)}), יציאה מ-
        {request.origin_iata}, {travelers(travelerCount)} ב{rooms(roomCount)}
        {budgetFiltered && `, תקציב ${money(response.budget_amount!, currency)}`}
      </p>
      {!budgetFiltered && (
        <p className="error">
          אין לנו שער המרה ל-{request.budget_currency}, ולכן אי אפשר לסנן לפי התקציב: מוצגים כל היעדים, במחיריהם בדולרים.
        </p>
      )}

      <div className="segmented" role="group" aria-label="רמת המלון">
        {TIERS.map((t) => (
          <button key={t} type="button" aria-pressed={t === tier} onClick={() => setTier(t)}>
            מלון {TIER_NAMES[t]}
          </button>
        ))}
      </div>

      {chosen.destinations.length > 0 ? (
        <>
          <p className="note">
            {chosen.exact_dates_only
              ? "מוצגים רק יעדים עם טיסה בדיוק בתאריכים האלה."
              : "לאף יעד אין טיסה בדיוק בתאריכים האלה, ולכן מוצגים התאריכים הקרובים ביותר לכל יעד."}{" "}
            מוצגים רק יעדים שיש להם גם מחיר טיסה וגם מחיר מלון. לתמונה המלאה של הנתונים החסרים:{" "}
            <Link to="/data-quality">איכות הנתונים</Link>.
          </p>
          {roomNote && <p className="note">{roomNote}</p>}
          <div className="table-scroll">
            <table>
              <thead>
                <tr>
                  <th>יעד</th>
                  <th>טיסות הלוך-חזור, {travelers(travelerCount)}</th>
                  <th>
                    מלון {TIER_NAMES[tier]}, {rooms(roomCount)}
                  </th>
                  <th>סך הכול</th>
                </tr>
              </thead>
              <tbody>
                {chosen.destinations.map((d) => (
                  <tr key={d.destination_id}>
                    <td>
                      <Link to={destinationUrl(d.destination_id, tripSearch)}>{cityName(d)}</Link>
                    </td>
                    <td>
                      {money(d.flight_total_amount, currency)}
                      {travelerCount > 1 && <small>{` (${money(d.flight_price_amount, currency)} לאדם)`}</small>}
                      {d.airline_code && (
                        <>
                          <br />
                          <small>{d.airline_name ?? d.airline_code}</small>
                        </>
                      )}
                      <br />
                      <AgeTag label="נראה" days={daysSince(d.flight_seen_on)} staleAfter={FLIGHT_STALE_AFTER_DAYS} />
                      {(d.flight_out_date !== request.depart_date || d.flight_return_date !== request.return_date) && (
                        <>
                          <br />
                          <span className="tag tag-missing">
                            תאריכים קרובים: {formatDate(d.flight_out_date)} – {formatDate(d.flight_return_date)}
                          </span>
                        </>
                      )}
                    </td>
                    <td>
                      {money(d.hotel_total_amount, currency)}
                      <br />
                      <AgeTag label="מחירים" days={d.hotel_price_age_days} staleAfter={HOTEL_STALE_AFTER_DAYS} />
                      {d.matched_nights !== requestedNights && (
                        <>
                          <br />
                          <small>({nights(d.matched_nights)})</small>
                        </>
                      )}
                    </td>
                    <td>
                      <span className="total">{money(d.total_estimate_amount, currency)}</span>
                      {travelerCount > 1 && (
                        <>
                          <br />
                          <small>{money(d.total_estimate_amount / travelerCount, currency)} לאדם</small>
                        </>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </>
      ) : chosen.has_missing_data ? (
        <p>
          לאף יעד אין גם מחיר טיסה וגם מחיר מלון בתאריכים האלה. זה חוסר בנתונים, לא התקציב שלך. לפרטים:{" "}
          <Link to="/data-quality">איכות הנתונים</Link>.
        </p>
      ) : (
        <p>
          אין יעדים עם מחיר טיסה ומלון{budgetFiltered && " בתקציב שלך"} בתאריכים האלה. נסו תאריכים אחרים, תקציב גבוה
          יותר או מלון חסכוני יותר.
        </p>
      )}

      <p>
        <Link to={`/history/${response.search_id}`} className="btn">
          לדירוג השמור של החיפוש
        </Link>
      </p>
    </section>
  );
}

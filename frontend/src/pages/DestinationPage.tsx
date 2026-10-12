import { keepPreviousData, useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { Link, useParams, useSearchParams } from "react-router";

import { api, ApiError, type Schemas, unwrap } from "../api/client";
import AgeTag, { FLIGHT_STALE_AFTER_DAYS, HOTEL_STALE_AFTER_DAYS } from "../components/AgeTag";
import DateGrid from "../components/DateGrid";
import {
  cityName,
  clock,
  countryName,
  daysSince,
  duration,
  formatDate,
  type HotelTier,
  money,
  nights,
  nightsBetween,
  TIER_NAMES,
  TIERS,
} from "../format";

type Currency = Schemas["EstimateRequest"]["budget_currency"] & string;

// One destination on the user's dates: every flight option (live when
// Travelpayouts answers), the city's hotel prices, and the flexible-dates grid.
// The search lives in the URL (see links.ts), so picking a grid cell or a
// tier is just a new URL.
export default function DestinationPage() {
  const destinationId = Number(useParams().destinationId);
  const [searchParams, setSearchParams] = useSearchParams();
  const [directOnly, setDirectOnly] = useState(false);

  const query = {
    depart_date: searchParams.get("depart_date") ?? "",
    return_date: searchParams.get("return_date") ?? "",
    origin_iata: searchParams.get("origin_iata") ?? "TLV",
    currency: (searchParams.get("currency") ?? "ILS") as Currency,
  };
  const tier = (searchParams.get("tier") ?? "average") as HotelTier;
  const budgetParam = searchParams.get("budget");
  const budget = budgetParam === null ? null : Number(budgetParam);
  const path = { destination_id: destinationId };
  const ready = Number.isInteger(destinationId) && query.depart_date !== "" && query.return_date !== "";

  const trip = useQuery({
    queryKey: ["trip", destinationId, query],
    queryFn: () => unwrap(api.GET("/api/v1/destinations/{destination_id}/trip", { params: { path, query } })),
    enabled: ready,
    // A live search: keep its answer for this session instead of asking again
    // every time the window regains focus.
    staleTime: Infinity,
    // After picking other dates, keep showing the last trip until the new one arrives.
    placeholderData: keepPreviousData,
  });
  const grid = useQuery({
    queryKey: ["date-grid", destinationId, query],
    queryFn: () => unwrap(api.GET("/api/v1/destinations/{destination_id}/date-grid", { params: { path, query } })),
    enabled: ready,
    placeholderData: keepPreviousData,
  });

  function updateSearch(changes: Record<string, string>) {
    setSearchParams((previous) => {
      const next = new URLSearchParams(previous);
      Object.entries(changes).forEach(([key, value]) => next.set(key, value));
      return next;
    });
  }

  const notFound = !ready || (trip.error instanceof ApiError && trip.error.status === 404);
  if (notFound) {
    return (
      <div className="card">
        <h1>היעד לא נמצא</h1>
        <p>
          <Link to="/">לחיפוש חדש</Link>
        </p>
      </div>
    );
  }
  if (trip.isPending) {
    return <p className="updating">מחפשים מחירים עדכניים לתאריכים האלה...</p>;
  }
  if (trip.error) {
    return <p className="error">לא הצלחנו לטעון את הטיול: {trip.error.message}</p>;
  }

  const t = trip.data;
  const hotel = t.hotel[tier];
  // The budget is in the currency asked for; if that had no rate the trip is in USD and can't be compared.
  const canCompareBudget = budget !== null && t.currency === query.currency && hotel !== null;
  const flights = t.flights.filter(
    (f) => !directOnly || (f.outbound_stops === 0 && (f.return_stops === 0 || f.return_stops === null)),
  );
  const withinBudget = canCompareBudget ? t.flights.filter((f) => f.price_amount + hotel.total_amount <= budget) : [];
  const requestedNights = nightsBetween(query.depart_date, query.return_date);
  const cheapestFlight = t.flights.length > 0 ? Math.min(...t.flights.map((f) => f.price_amount)) : null;

  return (
    <>
      <div className="hero">
        <h1>
          {cityName(t.destination)}, {countryName(t.destination)}
        </h1>
        <p>
          יציאה מ-{query.origin_iata}, {formatDate(query.depart_date)} – {formatDate(query.return_date)} (
          {nights(requestedNights)}){budget !== null && `, תקציב ${money(budget, query.currency)}`}
        </p>
      </div>

      {trip.isPlaceholderData && <p className="updating">מחפשים מחירים עדכניים לתאריכים החדשים...</p>}

      <div className="card">
        {cheapestFlight !== null && hotel !== null ? (
          <div className="trip-summary">
            <div>
              <div className="note">הטיול הזה, עם הטיסה הזולה ומלון {TIER_NAMES[tier]}</div>
              <div className="big">{money(cheapestFlight + hotel.total_amount, t.currency)}</div>
            </div>
            <div>
              <div className="note">טיסה</div>
              <strong>{money(cheapestFlight, t.currency)}</strong>
            </div>
            <div>
              <div className="note">מלון, {nights(t.hotel.nights)}</div>
              <strong>{money(hotel.total_amount, t.currency)}</strong>{" "}
              <span className="note">({money(hotel.per_night_amount, t.currency)} ללילה)</span>
            </div>
          </div>
        ) : (
          <p>
            {hotel === null
              ? `אין לנו מחיר למלון ${TIER_NAMES[tier]} בעיר הזו.`
              : "אין טיסות בתאריכים האלה או עד 4 ימים מהם."}
          </p>
        )}
        <p className="note">
          {t.source === "live" && "מחירים עדכניים לתאריכים המדויקים."}
          {t.source === "collected" &&
            (t.exact_dates
              ? "אין כרגע תשובה עדכנית, ולכן מוצגים מחירים שנאספו לתאריכים האלה."
              : `אין תשובה עדכנית לתאריכים האלה, ולכן מוצגים מחירים שנאספו לתאריכים הקרובים: ${formatDate(t.flight_out_date!)} – ${formatDate(t.flight_return_date!)}.`)}{" "}
          <AgeTag label="מחירי המלון עודכנו" days={t.hotel.price_age_days} staleAfter={HOTEL_STALE_AFTER_DAYS} />
        </p>
        <div className="segmented" role="group" aria-label="רמת המלון">
          {TIERS.map((option) => (
            <button key={option} type="button" aria-pressed={option === tier} onClick={() => updateSearch({ tier: option })}>
              מלון {TIER_NAMES[option]}
            </button>
          ))}
        </div>
      </div>

      {t.flights.length > 0 && (
        <section className="card">
          <h2>טיסות</h2>
          {canCompareBudget && (
            <p>
              <strong>
                {withinBudget.length} מתוך {t.flights.length}
              </strong>{" "}
              אפשרויות נכנסות בתקציב שלך עם מלון {TIER_NAMES[tier]}.
            </p>
          )}
          <label>
            <input type="checkbox" checked={directOnly} onChange={(e) => setDirectOnly(e.target.checked)} /> טיסות
            ישירות בלבד
          </label>
          <p className="note">
            המחירים להלוך-חזור, בלי מזוודה.
            {t.source === "collected" && " במחירים שנאספו אין פרטים על העצירות ומשך הטיסה בחזור."}
          </p>
          <div className="table-scroll">
            <table>
              <thead>
                <tr>
                  <th>חברה</th>
                  <th>המראה</th>
                  <th>חזרה</th>
                  <th>עצירות (הלוך / חזור)</th>
                  <th>משך (הלוך / חזור)</th>
                  <th>מחיר</th>
                  <th>המחיר נראה</th>
                  <th></th>
                </tr>
              </thead>
              <tbody>
                {flights.map((f, index) => (
                  // No id of its own: two options can share airline, times and price.
                  <tr key={index}>
                    <td>
                      {f.airline_name ?? f.airline_code ?? "-"}
                      {f.flight_number && <small> {f.flight_number}</small>}
                    </td>
                    <td>{clock(f.depart_time)}</td>
                    <td>{clock(f.return_time)}</td>
                    <td>
                      {f.outbound_stops ?? "-"} / {f.return_stops ?? "-"}
                    </td>
                    <td>
                      {duration(f.outbound_minutes)} / {duration(f.return_minutes)}
                    </td>
                    <td className="total">{money(f.price_amount, t.currency)}</td>
                    <td>
                      <AgeTag
                        label="נראה"
                        days={f.price_seen_on === null ? null : daysSince(f.price_seen_on)}
                        staleAfter={FLIGHT_STALE_AFTER_DAYS}
                      />
                    </td>
                    <td>
                      {f.booking_url && (
                        <a href={f.booking_url} target="_blank" rel="noopener noreferrer">
                          לחיפוש ב-Aviasales
                        </a>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          {flights.length === 0 && <p>אין טיסות ישירות בין האפשרויות האלה.</p>}
        </section>
      )}

      {grid.isPending && <p className="updating">טוען תאריכים גמישים...</p>}
      {grid.error && <p className="error">לא הצלחנו לטעון תאריכים גמישים: {grid.error.message}</p>}
      {grid.data && (
        <DateGrid
          grid={grid.data}
          departDate={query.depart_date}
          returnDate={query.return_date}
          tier={tier}
          onPick={(depart, back) => updateSearch({ depart_date: depart, return_date: back })}
        />
      )}
    </>
  );
}

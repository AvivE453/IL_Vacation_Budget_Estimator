import { keepPreviousData, useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { Link, useParams, useSearchParams } from "react-router";

import { api, ApiError, type Schemas, unwrap } from "../api/client";
import AgeTag, { FLIGHT_STALE_AFTER_DAYS, HOTEL_STALE_AFTER_DAYS } from "../components/AgeTag";
import DateGrid from "../components/DateGrid";
import { clock, daysSince, duration, money, nightsBetween } from "../format";

type HotelTier = Schemas["EstimateRequest"]["hotel_tier"] & string;
type Currency = Schemas["EstimateRequest"]["budget_currency"] & string;
const TIERS: HotelTier[] = ["budget", "average", "luxury"];

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
      <>
        <h1>Destination not found</h1>
        <p>
          <Link to="/">Start a new search</Link>
        </p>
      </>
    );
  }
  if (trip.isPending) {
    return <p>Searching live prices for these dates...</p>;
  }
  if (trip.error) {
    return <p className="error">Could not load this trip: {trip.error.message}</p>;
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

  return (
    <>
      <div className="hero">
        <h1>
          {t.destination.city_name}, {t.destination.country_name}
        </h1>
        <p>
          From {query.origin_iata}, {query.depart_date} &rarr; {query.return_date} ({requestedNights} nights)
          {budget !== null && `, budget ${money(budget)} ${query.currency}`}
        </p>
      </div>

      {trip.isPlaceholderData && <p className="updating">Searching live prices for the new dates...</p>}
      <p>
        {t.source === "live" && "Live prices for these exact dates."}
        {t.source === "collected" &&
          (t.exact_dates
            ? "No live answer just now - showing collected prices for these dates."
            : `No live answer for these dates - showing collected prices for the nearest dates, ${t.flight_out_date} → ${t.flight_return_date}.`)}
        {t.source === null && "No flights on file for these dates, or within 4 days of them."}
      </p>

      <div className="card">
        <h2>Hotels, {t.hotel.nights} nights</h2>
        <div className="tier-tabs" role="group" aria-label="Hotel tier">
          {TIERS.map((option) => (
            <button
              key={option}
              type="button"
              className="btn"
              aria-pressed={option === tier}
              onClick={() => updateSearch({ tier: option })}
            >
              {option}
            </button>
          ))}
        </div>
        <p>
          {hotel === null
            ? `No ${tier} hotel price on file for this city.`
            : `${money(hotel.per_night_amount)} ${t.currency} a night, ${money(hotel.total_amount)} ${t.currency} in total.`}{" "}
          <AgeTag label="hotel prices" days={t.hotel.price_age_days} staleAfter={HOTEL_STALE_AFTER_DAYS} />
        </p>
      </div>

      {t.flights.length > 0 && (
        <>
          <h2>Flights</h2>
          {canCompareBudget && (
            <p>
              <strong>
                {withinBudget.length} of {t.flights.length}
              </strong>{" "}
              options fit your budget with {tier} hotels.
            </p>
          )}
          <label>
            <input type="checkbox" checked={directOnly} onChange={(e) => setDirectOnly(e.target.checked)} /> Direct
            flights only
          </label>
          <p>
            <small>
              Prices are for the round trip, without checked baggage.
              {t.source === "collected" && " Collected prices don't record the return leg's stops or durations."}
            </small>
          </p>
          <table>
            <thead>
              <tr>
                <th>Airline</th>
                <th>Departs</th>
                <th>Returns</th>
                <th>Stops (out / back)</th>
                <th>Duration (out / back)</th>
                <th>Price ({t.currency})</th>
                <th>Price seen</th>
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
                  <td>{money(f.price_amount)}</td>
                  <td>
                    <AgeTag
                      label="seen"
                      days={f.price_seen_on === null ? null : daysSince(f.price_seen_on)}
                      staleAfter={FLIGHT_STALE_AFTER_DAYS}
                    />
                  </td>
                  <td>
                    {f.booking_url && (
                      <a href={f.booking_url} target="_blank" rel="noopener noreferrer">
                        Search on Aviasales
                      </a>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          {flights.length === 0 && <p>No direct flights among these options.</p>}
        </>
      )}

      {grid.isPending && <p>Loading flexible dates...</p>}
      {grid.error && <p className="error">Could not load flexible dates: {grid.error.message}</p>}
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

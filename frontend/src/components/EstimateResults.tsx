import { useState } from "react";
import { Link } from "react-router";

import type { Schemas } from "../api/client";
import { money, nightsBetween } from "../format";

type Props = {
  request: Schemas["EstimateRequest"];
  response: Schemas["EstimateResponse"];
};

type HotelTier = Schemas["EstimateRequest"]["hotel_tier"];
const TIERS: HotelTier[] = ["budget", "average", "luxury"];

export default function EstimateResults({ request, response }: Props) {
  // The response has all three tiers, so switching is instant - no new request.
  // Only the requested tier was saved to history.
  const [tier, setTier] = useState<HotelTier>(request.hotel_tier ?? "average");
  const chosen = response.tiers[tier];
  const nights = nightsBetween(request.depart_date, request.return_date);
  const { currency } = response;
  const budgetFiltered = response.budget_amount !== null;

  return (
    <section>
      <div className="hero">
        <h1>Results for {request.origin_iata}</h1>
        <p>
          Departure date: {request.depart_date}
          <br />
          Return date: {request.return_date} ({nights} nights)
          <br />
          Budget: {money(request.budget_amount)} {request.budget_currency}
        </p>
      </div>

      <p>
        <Link to={`/history/${response.search_id}`} className="btn">
          View this search's saved ranking
        </Link>
      </p>

      {budgetFiltered ? (
        <p>
          Budget in {currency}: <strong>{money(response.budget_amount!)}</strong>
        </p>
      ) : (
        <p>
          <strong>Warning:</strong> could not convert {request.budget_currency} to USD (no exchange rate on file) --
          budget filtering below is unavailable, showing fully-priced destinations regardless of budget.
        </p>
      )}

      <div className="tier-tabs" role="group" aria-label="Hotel tier">
        {TIERS.map((t) => (
          <button key={t} type="button" className="btn" aria-pressed={t === tier} onClick={() => setTier(t)}>
            {t}
          </button>
        ))}
      </div>

      <p>
        <small>
          Only destinations with a round-trip flight price and a hotel price on file
          {budgetFiltered && ", within your budget,"} are shown. See <Link to="/data-quality">Data Quality</Link> for
          the full missing-data picture.
        </small>
      </p>

      {chosen.destinations.length > 0 ? (
        <>
          <p>
            <small>
              {chosen.exact_dates_only
                ? "Showing only destinations with an exact match for these dates."
                : "No destination had an exact match for these dates -- showing the nearest available dates for each instead."}
            </small>
          </p>
          <table>
            <thead>
              <tr>
                <th>Destination</th>
                <th>Flight, round-trip ({currency})</th>
                <th>
                  Hotel total, {tier} tier ({currency})
                </th>
                <th>Total estimate ({currency})</th>
              </tr>
            </thead>
            <tbody>
              {chosen.destinations.map((d) => (
                <tr key={d.destination_id}>
                  <td>{d.city_name}</td>
                  <td>
                    {money(d.flight_total_amount)}
                    {d.airline_code && (
                      <>
                        <br />
                        <small>{d.airline_name ?? d.airline_code}</small>
                      </>
                    )}
                    {(d.flight_out_date !== request.depart_date || d.flight_return_date !== request.return_date) && (
                      <>
                        <br />
                        <small>
                          (closest: {d.flight_out_date} &rarr; {d.flight_return_date})
                        </small>
                      </>
                    )}
                  </td>
                  <td>
                    {money(d.hotel_total_amount)}
                    {d.matched_nights !== nights && (
                      <>
                        <br />
                        <small>({d.matched_nights} nights)</small>
                      </>
                    )}
                  </td>
                  <td>{money(d.total_estimate_amount)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </>
      ) : (
        <div className="card">
          {chosen.has_missing_data ? (
            <p>
              None of the destinations have both a flight and hotel price on file for these dates at all -- this is
              missing data, not a result of your budget or date match preference. See{" "}
              <Link to="/data-quality">Data Quality</Link> for the full missing-data picture.
            </p>
          ) : (
            <>
              <p>
                No destinations have both a flight and hotel price on file
                {budgetFiltered && " within your budget"} for these dates yet.
              </p>
              <p>
                Try different dates, raise the budget, or check <Link to="/data-quality">Data Quality</Link> to see
                what's missing.
              </p>
            </>
          )}
        </div>
      )}
    </section>
  );
}

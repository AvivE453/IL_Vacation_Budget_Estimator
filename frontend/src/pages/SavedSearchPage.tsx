import { useQuery } from "@tanstack/react-query";
import { Link, useParams } from "react-router";

import { api, ApiError, unwrap } from "../api/client";
import { money } from "../format";

export default function SavedSearchPage() {
  // The :searchId part of /history/:searchId - always a string from the URL.
  const searchId = Number(useParams().searchId);

  const { data, isPending, error } = useQuery({
    queryKey: ["searches", searchId],
    queryFn: () => unwrap(api.GET("/api/v1/searches/{search_id}", { params: { path: { search_id: searchId } } })),
    enabled: Number.isInteger(searchId),
  });

  // Not a number (/history/abc), or no such search in this browser's history.
  const notFound = !Number.isInteger(searchId) || (error instanceof ApiError && error.status === 404);
  if (notFound) {
    return (
      <>
        <h1>Search not found</h1>
        <p>
          It doesn't exist, or it was made in another browser. <Link to="/history">Back to your searches</Link>
        </p>
      </>
    );
  }
  if (isPending) {
    return <p>Loading...</p>;
  }
  if (error) {
    return <p className="error">Could not load this search: {error.message}</p>;
  }

  return (
    <>
      <h1>
        {data.origin_iata}, {data.depart_date} &rarr; {data.return_date}
      </h1>
      <p>
        Budget: {money(data.budget_amount)} {data.budget_currency}, {data.hotel_tier} hotels
      </p>
      {data.exact_dates_only !== null && (
        <p>
          <small>
            {data.exact_dates_only
              ? "These estimates were based on an exact date match."
              : "These estimates were based on the nearest available dates, not an exact match."}
          </small>
        </p>
      )}

      {data.results.length === 0 ? (
        <div className="card">
          <p>Every destination was over budget for this search, so no ranking was saved.</p>
        </div>
      ) : (
        <table>
          <thead>
            <tr>
              <th>Rank</th>
              <th>Destination</th>
              <th>Airline</th>
              <th>Hotel tier</th>
              <th>Total estimate ({data.currency})</th>
              <th>Within budget?</th>
            </tr>
          </thead>
          <tbody>
            {data.results.map((result) => (
              <tr key={result.destination_id}>
                <td>{result.cost_rank}</td>
                <td>{result.city_name}</td>
                <td>{result.airline_name ?? result.airline_code ?? "-"}</td>
                <td>{data.hotel_tier}</td>
                <td>{money(result.estimated_total_amount)}</td>
                <td>
                  <span className={result.within_budget ? "tag tag-yes" : "tag tag-no"}>
                    {result.within_budget ? "yes" : "no"}
                  </span>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </>
  );
}

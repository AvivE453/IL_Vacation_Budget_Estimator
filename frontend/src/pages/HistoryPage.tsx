import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router";

import { api, unwrap } from "../api/client";
import { dateTime, money } from "../format";

export default function HistoryPage() {
  const { data, isPending, error } = useQuery({
    queryKey: ["searches"],
    queryFn: () => unwrap(api.GET("/api/v1/searches")),
  });

  if (isPending) {
    return <p>Loading...</p>;
  }
  if (error) {
    return <p className="error">Could not load your searches: {error.message}</p>;
  }

  return (
    <>
      <h1>Recent Searches</h1>
      {data.length === 0 ? (
        <p>
          No searches from this browser yet. <Link to="/">Start one</Link>.
        </p>
      ) : (
        <table>
          <thead>
            <tr>
              <th>#</th>
              <th>Origin</th>
              <th>Depart</th>
              <th>Return</th>
              <th>Budget</th>
              <th>Hotel tier</th>
              <th>Created</th>
            </tr>
          </thead>
          <tbody>
            {data.map((search, index) => (
              <tr key={search.search_id}>
                {/* Numbered per browser, oldest = 1, rather than by the global id. */}
                <td>
                  <Link to={`/history/${search.search_id}`}>{data.length - index}</Link>
                </td>
                <td>{search.origin_iata}</td>
                <td>{search.depart_date}</td>
                <td>{search.return_date}</td>
                <td>
                  {money(search.budget_amount)} {search.budget_currency}
                </td>
                <td>{search.hotel_tier}</td>
                <td>{dateTime(search.created_at)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </>
  );
}

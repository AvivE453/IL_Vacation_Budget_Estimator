import { useQuery } from "@tanstack/react-query";

import { api, unwrap } from "../api/client";
import { daysAgo } from "../format";

export default function DataQualityPage() {
  const { data, isPending, error } = useQuery({
    queryKey: ["data-quality"],
    queryFn: () => unwrap(api.GET("/api/v1/data-quality")),
  });

  if (isPending) {
    return <p>Loading...</p>;
  }
  if (error) {
    return <p className="error">Could not load the data-quality report: {error.message}</p>;
  }

  return (
    <>
      <h1>Data Quality &amp; Coverage</h1>

      <h2>Per-destination coverage</h2>
      <table>
        <thead>
          <tr>
            <th>City</th>
            <th>Country</th>
            <th>Flight observations</th>
            <th>Hotels in our search</th>
            <th>Hotel price age</th>
          </tr>
        </thead>
        <tbody>
          {data.coverage.map((row) => (
            <tr key={`${row.city_name}-${row.country_name}`}>
              <td>{row.city_name}</td>
              <td>{row.country_name}</td>
              <td>{row.flight_obs_count}</td>
              <td>{row.hotel_sample_size ?? "-"}</td>
              <td>{daysAgo(row.hotel_price_age_days)}</td>
            </tr>
          ))}
        </tbody>
      </table>

      <h2>Collection volume over time</h2>
      <table>
        <thead>
          <tr>
            <th>Day</th>
            <th>Observations collected</th>
            <th>From user searches</th>
          </tr>
        </thead>
        <tbody>
          {data.collection_volume.map((row) => (
            <tr key={row.day}>
              <td>{row.day}</td>
              <td>{row.observations_collected}</td>
              <td>{row.observations_from_searches}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </>
  );
}

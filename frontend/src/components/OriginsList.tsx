import { useQuery } from "@tanstack/react-query";

import { api } from "../api/client";

async function fetchOrigins() {
  const { data, error, response } = await api.GET("/api/v1/origins");
  // Not `if (error)`: an error with an empty body (Vite's 502 when the API is
  // down) comes back as error = "", which is falsy.
  if (error !== undefined) {
    throw new Error(`HTTP ${response.status}`);
  }
  return data;
}

export default function OriginsList() {
  const { data, isPending, error } = useQuery({
    queryKey: ["origins"],
    queryFn: fetchOrigins,
  });

  if (isPending) {
    return <p>Loading airports...</p>;
  }
  if (error) {
    return <p>Could not load airports: {error.message}</p>;
  }

  return (
    <ul>
      {data.map((origin) => (
        <li key={origin.iata_code}>
          {origin.airport_name} ({origin.iata_code}), {origin.city_name}
        </li>
      ))}
    </ul>
  );
}

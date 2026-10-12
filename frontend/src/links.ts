import type { Schemas } from "./api/client";

export type TripSearch = {
  depart_date: string;
  return_date: string;
  origin_iata: string;
  currency: Schemas["EstimateRequest"]["budget_currency"];
  budget?: number;
  tier?: Schemas["EstimateRequest"]["hotel_tier"];
  travelers?: number;
  rooms?: number;
};

// The destination view keeps its search in the URL, so a refresh, the Back
// button or a shared link shows the same trip.
export function destinationUrl(destinationId: number, search: TripSearch): string {
  const params = new URLSearchParams({
    depart_date: search.depart_date,
    return_date: search.return_date,
    origin_iata: search.origin_iata,
    currency: search.currency ?? "ILS",
    tier: search.tier ?? "average",
    travelers: String(search.travelers ?? 1),
    rooms: String(search.rooms ?? 1),
  });
  if (search.budget !== undefined) {
    params.set("budget", String(search.budget));
  }
  return `/destinations/${destinationId}?${params}`;
}

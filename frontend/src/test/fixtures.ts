import type { Schemas } from "../api/client";

// API answers for tests, typed by the generated schema: if the API's shape
// changes, these stop compiling instead of silently testing an old shape.
// Each takes overrides for the fields a test cares about.

export const TODAY = "2026-10-12";
export const DEPART = "2026-11-07";
export const RETURN = "2026-11-14";

export function origin(): Schemas["Origin"] {
  return { iata_code: "TLV", airport_name: "Ben Gurion Airport", city_name: "Tel Aviv" };
}

export function destination(overrides: Partial<Schemas["Destination"]> = {}): Schemas["Destination"] {
  return {
    destination_id: 7,
    city_name: "Paris",
    country_name: "France",
    city_name_he: "פריז",
    country_name_he: "צרפת",
    iata_code: "PAR",
    ...overrides,
  };
}

export function estimate(overrides: Partial<Schemas["DestinationEstimate"]> = {}): Schemas["DestinationEstimate"] {
  return {
    destination_id: 7,
    city_name: "Paris",
    city_name_he: "פריז",
    airline_code: "AF",
    airline_name: "Air France",
    flight_out_date: DEPART,
    flight_return_date: RETURN,
    matched_nights: 7,
    flight_price_amount: 700, // per traveler; the totals are for two
    flight_total_amount: 1400,
    hotel_total_amount: 2100,
    total_estimate_amount: 3500,
    flight_seen_on: "2026-10-10",
    hotel_price_age_days: 3,
    ...overrides,
  };
}

export function tier(destinations: Schemas["DestinationEstimate"][], overrides: Partial<Schemas["TierEstimate"]> = {}) {
  return { exact_dates_only: true, has_missing_data: false, destinations, ...overrides } satisfies Schemas["TierEstimate"];
}

export function estimateResponse(overrides: Partial<Schemas["EstimateResponse"]> = {}): Schemas["EstimateResponse"] {
  return {
    search_id: 41,
    currency: "ILS",
    budget_amount: 8000,
    tiers: {
      budget: tier([estimate({ hotel_total_amount: 1200, total_estimate_amount: 2600 })]),
      average: tier([estimate()]),
      luxury: tier([]),
    },
    ...overrides,
  };
}

export function flight(overrides: Partial<Schemas["FlightOption"]> = {}): Schemas["FlightOption"] {
  return {
    depart_date: DEPART,
    return_date: RETURN,
    airline_code: "AF",
    airline_name: "Air France",
    flight_number: "975",
    depart_time: "15:55:00",
    return_time: "09:00:00",
    outbound_stops: 0,
    return_stops: 0,
    outbound_minutes: 290,
    return_minutes: 255,
    price_amount: 1460,
    price_seen_on: "2026-10-06",
    booking_url: "https://www.aviasales.com/search/TLV0711PAR14111",
    ...overrides,
  };
}

export function trip(overrides: Partial<Schemas["Trip"]> = {}): Schemas["Trip"] {
  return {
    destination: destination(),
    currency: "ILS",
    source: "live",
    live_status: "found",
    flight_out_date: DEPART,
    flight_return_date: RETURN,
    exact_dates: true,
    flights: [flight({ price_amount: 1460 }), flight({ airline_name: "Wizz Air", outbound_stops: 1, price_amount: 745 })],
    hotel: {
      nights: 7,
      rooms: 1,
      price_age_days: 5,
      budget: { per_night_amount: 500, total_amount: 3500 },
      average: { per_night_amount: 900, total_amount: 6300 },
      luxury: null,
    },
    ...overrides,
  };
}

// Hotels at 500 (budget) and 900 (average) a night, as in trip().
export function gridCell(depart: string, back: string, flightAmount: number, nights = 7): Schemas["DateGridCell"] {
  return {
    depart_date: depart,
    return_date: back,
    nights,
    flight_amount: flightAmount,
    total_amount: { budget: flightAmount + 500 * nights, average: flightAmount + 900 * nights, luxury: null },
  };
}

export function dateGrid(cells: Schemas["DateGridCell"][] = []): Schemas["DateGrid"] {
  return { currency: "ILS", days: 3, cells };
}

export function savedSearch(overrides: Partial<Schemas["SavedSearch"]> = {}): Schemas["SavedSearch"] {
  return {
    search_id: 41,
    origin_iata: "TLV",
    depart_date: DEPART,
    return_date: RETURN,
    budget_amount: 8000,
    budget_currency: "ILS",
    hotel_tier: "average",
    travelers: 2,
    rooms: 1,
    created_at: "2026-10-12T13:55:12Z",
    exact_dates_only: true,
    currency: "ILS",
    results: [
      {
        cost_rank: 1,
        destination_id: 7,
        city_name: "Paris",
        city_name_he: "פריז",
        airline_code: "AF",
        airline_name: "Air France",
        estimated_total_amount: 3500,
      },
    ],
    ...overrides,
  };
}

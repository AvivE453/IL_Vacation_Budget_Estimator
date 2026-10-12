import { type ChangeEvent, type FormEvent, useState } from "react";

import type { Schemas } from "../api/client";
import { addDays, todayIso } from "../format";

type Props = {
  origins: Schemas["Origin"][];
  destinations: Schemas["Destination"][];
  isSubmitting: boolean;
  onEstimate: (request: Schemas["EstimateRequest"]) => void;
  onViewDestination: (destinationId: number, request: Schemas["EstimateRequest"]) => void;
};

// What the inputs hold: always strings, converted to the API's types on submit.
type FormValues = {
  origin_iata: string;
  destination_id: string; // "" for every destination
  depart_date: string;
  return_date: string;
  budget_amount: string;
  budget_currency: Schemas["EstimateRequest"]["budget_currency"];
  hotel_tier: Schemas["EstimateRequest"]["hotel_tier"];
};

export default function SearchForm({ origins, destinations, isSubmitting, onEstimate, onViewDestination }: Props) {
  const [values, setValues] = useState<FormValues>(() => {
    const today = todayIso();
    return {
      origin_iata: origins[0].iata_code,
      destination_id: "",
      depart_date: today,
      return_date: addDays(today, 7),
      budget_amount: "5000",
      budget_currency: "ILS",
      hotel_tier: "average",
    };
  });

  // One handler for every input: each one's `name` is the field it updates.
  function handleChange(event: ChangeEvent<HTMLInputElement | HTMLSelectElement>) {
    const { name, value } = event.target;
    setValues((previous) => ({ ...previous, [name]: value }));
  }

  function handleSubmit(event: FormEvent) {
    event.preventDefault();
    const { destination_id, ...rest } = values;
    const request = { ...rest, budget_amount: Number(values.budget_amount) };
    // No destination: rank them all (saved to history). One destination: its
    // own view, with every flight option for the exact dates.
    if (destination_id === "") {
      onEstimate(request);
    } else {
      onViewDestination(Number(destination_id), request);
    }
  }

  return (
    <form className="card" onSubmit={handleSubmit}>
      <label>
        Origin airport
        <select name="origin_iata" value={values.origin_iata} onChange={handleChange} required>
          {origins.map((origin) => (
            <option key={origin.iata_code} value={origin.iata_code}>
              {origin.city_name} ({origin.iata_code})
            </option>
          ))}
        </select>
      </label>

      <label>
        Destination
        <select name="destination_id" value={values.destination_id} onChange={handleChange}>
          <option value="">All destinations, cheapest first</option>
          {destinations.map((d) => (
            <option key={d.destination_id} value={d.destination_id}>
              {d.city_name}, {d.country_name}
            </option>
          ))}
        </select>
      </label>

      <label>
        Departure date
        <input type="date" name="depart_date" value={values.depart_date} onChange={handleChange} required />
      </label>

      <label>
        Return date
        <input
          type="date"
          name="return_date"
          value={values.return_date}
          min={addDays(values.depart_date, 1)}
          onChange={handleChange}
          required
        />
      </label>

      <label>
        Budget
        <input
          type="number"
          name="budget_amount"
          min="1"
          step="1"
          value={values.budget_amount}
          onChange={handleChange}
          required
        />
      </label>

      <label>
        Budget currency
        <select name="budget_currency" value={values.budget_currency} onChange={handleChange}>
          <option value="ILS">ILS</option>
          <option value="USD">USD</option>
          <option value="EUR">EUR</option>
        </select>
      </label>

      <label>
        Hotel tier
        <select name="hotel_tier" value={values.hotel_tier} onChange={handleChange}>
          <option value="budget">Budget (avg of cheapest ~10 hotels)</option>
          <option value="average">Average (all hotels found)</option>
          <option value="luxury">Luxury (avg of priciest ~10 hotels)</option>
        </select>
      </label>

      <button type="submit" className="btn" disabled={isSubmitting}>
        {isSubmitting ? "Estimating..." : values.destination_id === "" ? "Estimate" : "Show this destination"}
      </button>
    </form>
  );
}

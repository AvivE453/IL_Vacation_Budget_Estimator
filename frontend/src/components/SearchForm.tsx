import { type ChangeEvent, type FormEvent, useRef, useState } from "react";

import type { Schemas } from "../api/client";
import {
  addDays,
  cityName,
  countryName,
  type HotelTier,
  nights,
  nightsBetween,
  rooms as roomsLabel,
  TIER_NAMES,
  TIERS,
  todayIso,
} from "../format";

type Currency = "ILS" | "USD" | "EUR";
type Mode = "all" | "destination";

type Props = {
  origins: Schemas["Origin"][];
  destinations: Schemas["Destination"][];
  isSubmitting: boolean;
  onEstimate: (request: Schemas["EstimateRequest"]) => void;
  onViewDestination: (destinationId: number, request: Schemas["EstimateRequest"]) => void;
};

const CURRENCIES: { code: Currency; label: string }[] = [
  { code: "ILS", label: "₪ שקל" },
  { code: "USD", label: "$ דולר" },
  { code: "EUR", label: "€ יורו" },
];

const TIER_HINTS: Record<HotelTier, string> = {
  budget: "ממוצע 10 המלונות הזולים",
  average: "ממוצע כל המלונות",
  luxury: "ממוצע 10 המלונות היקרים",
};

const TRIP_LENGTHS = [
  { label: "סופ״ש", nights: 3 },
  { label: "שבוע", nights: 7 },
  { label: "10 ימים", nights: 10 },
  { label: "שבועיים", nights: 14 },
];

const BUDGET_SLIDER = { ILS: 30_000, USD: 8_000, EUR: 7_500 } satisfies Record<Currency, number>;

const PARTIES = [
  { label: "לבד", travelers: 1, rooms: 1 },
  { label: "זוג", travelers: 2, rooms: 1 },
  { label: "משפחה 2+2", travelers: 4, rooms: 1 },
  { label: "שני זוגות", travelers: 4, rooms: 2 },
];

// Rooms for a party typed by hand: a family of up to four shares one.
const roomsFor = (travelerCount: number) => Math.max(1, Math.ceil(travelerCount / 4));

// What the inputs hold: always strings, converted to the API's types on submit.
type FormValues = {
  origin_iata: string;
  destination: string; // the typed or picked "City, Country"
  depart_date: string;
  return_date: string;
  budget_amount: string;
  budget_currency: Currency;
  hotel_tier: HotelTier;
  travelers: string;
  rooms: string;
};

// Two searches in one form: "where can I go?" ranks every destination for the
// budget (and is saved to history); "a specific destination" opens that
// destination's view with every flight option.
export default function SearchForm({ origins, destinations, isSubmitting, onEstimate, onViewDestination }: Props) {
  const [mode, setMode] = useState<Mode>("all");
  const [values, setValues] = useState<FormValues>(() => {
    const today = todayIso();
    return {
      origin_iata: origins[0].iata_code,
      destination: "",
      depart_date: today,
      return_date: addDays(today, 7),
      budget_amount: "5000",
      budget_currency: "ILS",
      hotel_tier: "average",
      // Most vacations are for two.
      travelers: "2",
      rooms: "1",
    };
  });

  // The trip's length, remembered apart from the dates: a date input is empty
  // while being typed, and moving the departure should still keep the length.
  const tripLength = useRef(7);
  const tripNights = nightsBetween(values.depart_date, values.return_date);
  // Picked in Hebrew ("פריז, צרפת"), but typing the English name finds it too.
  const hebrewLabel = (d: Schemas["Destination"]) => `${cityName(d)}, ${countryName(d)}`;
  const englishLabel = (d: Schemas["Destination"]) => `${d.city_name}, ${d.country_name}`;
  const chosen = destinations.find((d) => [hebrewLabel(d), englishLabel(d)].includes(values.destination.trim()));
  const byHebrewName = [...destinations].sort((a, b) => cityName(a).localeCompare(cityName(b), "he"));

  // One handler for every input: each one's `name` is the field it updates.
  function handleChange(event: ChangeEvent<HTMLInputElement | HTMLSelectElement>) {
    const { name, value } = event.target;
    update({ [name]: value });
  }

  function update(changes: Partial<FormValues>) {
    const next = { ...values, ...changes };
    // Moving the departure keeps the trip's length, as on travel sites.
    if (changes.depart_date && changes.return_date === undefined) {
      next.return_date = addDays(changes.depart_date, tripLength.current);
    }
    if (next.depart_date && next.return_date && nightsBetween(next.depart_date, next.return_date) > 0) {
      tripLength.current = nightsBetween(next.depart_date, next.return_date);
    }
    setValues(next);
  }

  function handleSubmit(event: FormEvent) {
    event.preventDefault();
    const request = {
      origin_iata: values.origin_iata,
      depart_date: values.depart_date,
      return_date: values.return_date,
      budget_amount: Number(values.budget_amount),
      budget_currency: values.budget_currency,
      hotel_tier: values.hotel_tier,
      travelers: Number(values.travelers),
      rooms: Number(values.rooms),
    };
    if (mode === "all") {
      onEstimate(request);
    } else if (chosen) {
      onViewDestination(chosen.destination_id, request);
    }
  }

  return (
    <form className="card" onSubmit={handleSubmit}>
      <div className="mode-tabs" role="group" aria-label="סוג החיפוש">
        <button type="button" aria-pressed={mode === "all"} onClick={() => setMode("all")}>
          לאן כדאי לטוס?
          <small>כל היעדים, מהזול ליקר</small>
        </button>
        <button type="button" aria-pressed={mode === "destination"} onClick={() => setMode("destination")}>
          יעד מסוים
          <small>כל הטיסות ליעד אחד, ותאריכים גמישים</small>
        </button>
      </div>

      <div className="form-grid">
        {mode === "destination" && (
          <>
            <label className="field field-wide">
              <span>לאן?</span>
              <input
                name="destination"
                list="destination-options"
                placeholder="הקלידו עיר, למשל פריז"
                value={values.destination}
                onChange={handleChange}
                // The browser blocks the submit and shows this until a listed destination is picked.
                ref={(input) => input?.setCustomValidity(chosen ? "" : "בחרו יעד מהרשימה")}
                required
                autoComplete="off"
              />
            </label>
            {/* Outside the label: the options' text would otherwise become part of the field's name. */}
            <datalist id="destination-options">
              {byHebrewName.map((d) => (
                // The option's text is shown beside its value, and the browser matches typing against both.
                <option key={d.destination_id} value={hebrewLabel(d)}>
                  {englishLabel(d)}
                </option>
              ))}
            </datalist>
          </>
        )}

        <label className="field">
          <span>יוצאים מ-</span>
          <select name="origin_iata" value={values.origin_iata} onChange={handleChange} required>
            {origins.map((origin) => (
              <option key={origin.iata_code} value={origin.iata_code}>
                {origin.airport_name} ({origin.iata_code})
              </option>
            ))}
          </select>
        </label>

        <label className="field">
          <span>תאריך יציאה</span>
          <input
            type="date"
            name="depart_date"
            value={values.depart_date}
            min={todayIso()}
            onChange={handleChange}
            required
          />
        </label>

        <label className="field">
          <span>
            תאריך חזרה {tripNights > 0 && <span className="nights-badge">{nights(tripNights)}</span>}
          </span>
          <input
            type="date"
            name="return_date"
            value={values.return_date}
            min={addDays(values.depart_date, 1)}
            onChange={handleChange}
            required
          />
        </label>

        <div className="field">
          <span>אורך הטיול</span>
          <div className="chips" role="group" aria-label="אורך הטיול">
            {TRIP_LENGTHS.map((length) => (
              <button
                key={length.nights}
                type="button"
                aria-pressed={tripNights === length.nights}
                onClick={() => update({ return_date: addDays(values.depart_date, length.nights) })}
              >
                {length.label}
              </button>
            ))}
          </div>
        </div>

        <fieldset className="field field-wide">
          <legend>מי נוסע?</legend>
          <div className="chips" role="group" aria-label="מי נוסע">
            {PARTIES.map((party) => (
              <button
                key={party.label}
                type="button"
                aria-pressed={values.travelers === String(party.travelers) && values.rooms === String(party.rooms)}
                onClick={() => update({ travelers: String(party.travelers), rooms: String(party.rooms) })}
              >
                {party.label}
              </button>
            ))}
          </div>
          <div className="party-row">
            <label className="field">
              <span>נוסעים</span>
              <input
                type="number"
                name="travelers"
                min="1"
                max="9"
                value={values.travelers}
                onChange={(event) =>
                  update({ travelers: event.target.value, rooms: String(roomsFor(Number(event.target.value))) })
                }
                required
              />
            </label>
            <label className="field">
              <span>חדרים</span>
              <input
                type="number"
                name="rooms"
                min="1"
                max={values.travelers}
                value={values.rooms}
                onChange={handleChange}
                required
              />
            </label>
            <span className="hint">
              כל נוסע צריך כרטיס טיסה; {roomsLabel(Number(values.rooms) || 1)} במלון.
            </span>
          </div>
        </fieldset>

        <fieldset className="field field-wide">
          <legend>תקציב לטיול: טיסה ומלון, לכל הנוסעים</legend>
          <div className="budget-row">
            <input
              type="number"
              name="budget_amount"
              aria-label="תקציב"
              min="1"
              step="1"
              value={values.budget_amount}
              onChange={handleChange}
              required
            />
            <div className="segmented" role="group" aria-label="מטבע">
              {CURRENCIES.map((currency) => (
                <button
                  key={currency.code}
                  type="button"
                  aria-pressed={values.budget_currency === currency.code}
                  onClick={() => update({ budget_currency: currency.code })}
                >
                  {currency.label}
                </button>
              ))}
            </div>
          </div>
          <input
            type="range"
            aria-label="תקציב, סרגל"
            min="0"
            max={BUDGET_SLIDER[values.budget_currency]}
            step="500"
            value={values.budget_amount}
            onChange={(event) => update({ budget_amount: event.target.value })}
          />
        </fieldset>

        <fieldset className="field field-wide">
          <legend>רמת המלון</legend>
          <div className="segmented" role="group" aria-label="רמת המלון">
            {TIERS.map((tier) => (
              <button
                key={tier}
                type="button"
                aria-pressed={values.hotel_tier === tier}
                onClick={() => update({ hotel_tier: tier })}
              >
                {TIER_NAMES[tier]}
                <small>{TIER_HINTS[tier]}</small>
              </button>
            ))}
          </div>
        </fieldset>
      </div>

      <div className="form-actions">
        <button type="submit" className="btn btn-go" disabled={isSubmitting}>
          {isSubmitting ? "מחפשים..." : mode === "all" ? "מצאו לי יעדים" : "הראו את היעד"}
        </button>
      </div>
    </form>
  );
}

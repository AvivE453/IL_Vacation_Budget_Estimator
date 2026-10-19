import createClient from "openapi-fetch";

import type { components, paths } from "./schema";

// Typed fetch for our API: each call's path, parameters and response come
// from schema.d.ts, which `npm run gen:api` generates from api/openapi.json.
// The page's own origin, spelled out: the browser would resolve "/api/..."
// against it anyway, but openapi-fetch builds a Request first, and outside a
// browser (the component tests) a Request needs a full URL.
export const api = createClient<paths>({ baseUrl: window.location.origin });

export type Schemas = components["schemas"];

export class ApiError extends Error {
  readonly status: number;
  readonly body: unknown;

  constructor(status: number, body: unknown) {
    super(`HTTP ${status}`);
    this.status = status;
    this.body = body;
  }
}

// openapi-fetch returns { data } on success and { error } otherwise, so
// R["data"] is "the success body | undefined"; unwrap returns only the body.
type ApiResult = { data?: unknown; error?: unknown; response: Response };

// Turns an openapi-fetch result into its data, or throws an ApiError that
// TanStack Query reports. Not `if (error)`: an error with an empty body
// (Vite's 502 when the API is down) comes back as error = "", which is falsy.
export async function unwrap<R extends ApiResult>(request: Promise<R>): Promise<Exclude<R["data"], undefined>> {
  const { data, error, response } = await request;
  if (error !== undefined) {
    throw new ApiError(response.status, error);
  }
  return data as Exclude<R["data"], undefined>;
}

// What the user calls each field the API may reject.
const FIELD_NAMES: Record<string, string> = {
  origin_iata: "שדה היציאה",
  depart_date: "תאריך היציאה",
  return_date: "תאריך החזרה",
  budget_amount: "התקציב",
  budget_currency: "המטבע",
  hotel_tier: "רמת המלון",
  travelers: "מספר הנוסעים",
  rooms: "מספר החדרים",
};

// The field-by-field messages of a 422, e.g. "התקציב: Input should be greater
// than 0" (the message itself is the API's). A check on the whole request
// (return before departure) has no field, so its message stands alone.
export function validationMessages(error: unknown): string[] {
  if (!(error instanceof ApiError) || error.status !== 422) {
    return [];
  }
  const { detail } = error.body as Schemas["HTTPValidationError"];
  return (detail ?? []).map((issue) => {
    const field = issue.loc.at(-1);
    if (field === "body") {
      return issue.msg;
    }
    return `${FIELD_NAMES[String(field)] ?? field}: ${issue.msg}`;
  });
}

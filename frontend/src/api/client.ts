import createClient from "openapi-fetch";

import type { components, paths } from "./schema";

// Typed fetch for our API: each call's path, parameters and response come
// from schema.d.ts, which `npm run gen:api` generates from api/openapi.json.
export const api = createClient<paths>();

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

// The field-by-field messages of a 422, e.g. "budget_amount: Input should be
// greater than 0". A check on the whole request (return before departure)
// has no field, so its message stands alone.
export function validationMessages(error: unknown): string[] {
  if (!(error instanceof ApiError) || error.status !== 422) {
    return [];
  }
  const { detail } = error.body as Schemas["HTTPValidationError"];
  return (detail ?? []).map((issue) => {
    const field = issue.loc.at(-1);
    return field === "body" ? issue.msg : `${field}: ${issue.msg}`;
  });
}

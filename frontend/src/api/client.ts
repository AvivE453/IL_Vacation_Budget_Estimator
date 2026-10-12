import createClient from "openapi-fetch";

import type { paths } from "./schema";

// Typed fetch for our API: each call's path, parameters and response come
// from schema.d.ts, which `npm run gen:api` generates from api/openapi.json.
export const api = createClient<paths>();

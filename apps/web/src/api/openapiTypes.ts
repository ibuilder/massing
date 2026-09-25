// Typed seam over the OpenAPI-generated `schema.d.ts` (produced by `openapi-typescript`).
// `import … from "./schema"` resolves to the generated `schema.d.ts` (there is no `schema.ts`).
//
// Regenerate after backend API changes — ONE step, from apps/web:
//   npm run gen:api-types
// It dumps the spec from `aec_api.main:app` into a temp file it then deletes, so the generator reads
// the SERVER and there is no persistent input left to be stale. The two-step recipe that used to live
// here ended in `openapi-typescript src/api/openapi.json`, and `apps/web/.gitignore` ignores
// `src/api/openapi.json` — so step 2 on its own regenerated from whatever untracked dump happened to
// be on the machine, printed a green tick, and wrote the same file. Measured 2026-09-25: the committed
// `schema.d.ts` declared 500 of the 947 paths the app serves, and had done since it was generated.
// `services/api/test_schema_types_agree.py` is the authority now — it asserts every live (path, method)
// is declared here, so forgetting to regenerate reds the build instead of doing nothing.
//
// COVERAGE: the backend returns raw dicts on most endpoints (only a handful of the ~1,021 operations
// declare a response model), so generated *response* types are precise only where FastAPI has a
// schema — request bodies, path/query params, and those typed responses. As backend endpoints adopt
// `response_model=`, coverage grows automatically on the next regen. Hand-written DTOs in `types.ts`
// remain the source for untyped responses until then.

import type { components, operations, paths } from "./schema";

export type { components, operations, paths };

/** A named schema from `components.schemas` (e.g. `Schema<"HTTPValidationError">`). */
export type Schema<K extends keyof components["schemas"]> = components["schemas"][K];

/** The JSON body an operation returns on 200 when the backend declares one — else `unknown`. */
export type OkJson<Op> = Op extends {
  responses: { 200: { content: { "application/json": infer T } } };
} ? T : unknown;

/** The request JSON body an operation accepts, when it declares one. */
export type ReqJson<Op> = Op extends {
  requestBody: { content: { "application/json": infer T } };
} ? T : never;

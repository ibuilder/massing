// Typed seam over the OpenAPI-generated `schema.d.ts` (produced by `openapi-typescript`).
// `import … from "./schema"` resolves to the generated `schema.d.ts` (there is no `schema.ts`).
//
// Regenerate after backend API changes (two steps — dump the FastAPI spec, then generate the types):
//   1. From services/api:  PYTHONPATH=src <venv-python> -c \
//        "import json,pathlib;from aec_api.main import app;\
//         pathlib.Path('../../apps/web/src/api/openapi.json').write_text(json.dumps(app.openapi()))"
//   2. From apps/web:      npm run gen:api-types
// (schema.d.ts is committed; openapi.json is a gitignored intermediate.)
//
// COVERAGE: the backend returns raw dicts on most endpoints (only ~11 of ~540 declare a response
// model), so generated *response* types are precise only where FastAPI has a schema — request bodies,
// path/query params, and those typed responses. As backend endpoints adopt `response_model=`, coverage
// grows automatically on the next regen. Hand-written DTOs in `types.ts` remain the source for untyped
// responses until then.

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

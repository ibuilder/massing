import { readFileSync, readdirSync } from "node:fs";
import { resolve } from "node:path";

import { describe, expect, it } from "vitest";

/**
 * R34-SHEET-SCALE — **a region must never be committed without the scale it was traced under.**
 *
 * The bug this pins was not a wrong formula; the server has priced a per-region `scale_units_per_px`
 * correctly since R34-MEASURE-PROVENANCE. It was that *nothing ever set it*. This overlay keeps a single
 * `scale` that recalibration overwrites, and passed it to `quantify()` at press time — so tracing a plan
 * at 1/8"=1', then recalibrating for a detail at 1/2"=1', silently **re-measured the plan regions at the
 * detail's scale**. Every number stayed plausible, which is why it survived: [[the-dangerous-default-is-
 * the-plausible-one]].
 *
 * Why a source-level gate rather than a DOM one: the failure is a *missing* stamp on one of three commit
 * paths (trace double-click, trace Enter, flood-fill click). Driving the overlay needs an image and a
 * canvas context, and a DOM test that exercised two of the three paths would go green while the third
 * regressed — the [[tests-that-cannot-reach-the-failure]] shape. Asserting that exactly one call site
 * pushes into `regions` makes the partition itself the thing under test, so a *fourth* commit path added
 * later fails this too.
 */
// cwd is `apps/web` under `npm run test --workspace apps/web` (the CI invocation). Same convention as
// `shell/roadmapLanes.test.ts`. Not `import.meta.url` — the happy-dom environment does not give it a
// `file:` scheme, so `fileURLToPath` throws there while working fine under a node-environment run.
const WEB = process.cwd();
const SRC = readFileSync(resolve(WEB, "src/viewer/takeoff2d.ts"), "utf8");
/** The whole `src/api` surface, not `client.ts` alone.
 *
 *  SCALE-SEAM keeps moving methods out of `client.ts` into domain mixins — `takeoff2d` went to
 *  `api/estimate.ts` and its wire types to `api/types.ts` in v0.3.1119 — and a test pinned to one
 *  filename goes red on the extraction rather than on the behaviour it guards. The property here is
 *  "the client declares this", which is a fact about the API surface, not about which file holds it. */
function apiSurface(): string {
  const dir = resolve(__dirname, "..", "api");
  return readdirSync(dir).filter((f) => f.endsWith(".ts") && !f.endsWith(".test.ts"))
    .map((f) => readFileSync(resolve(dir, f), "utf8")).join("\n");
}
const CLIENT = apiSurface();

describe("R34-SHEET-SCALE — scale is stamped at trace time", () => {
  it("has exactly one site that appends to `regions`, so no path can skip the stamp", () => {
    const pushes = SRC.match(/regions\.push\(/g) || [];
    expect(pushes.length, "every commit path must funnel through addRegion()").toBe(1);
    // ...and that one site is inside addRegion, not somewhere that merely happens to compile.
    const addRegion = SRC.slice(SRC.indexOf("const addRegion"), SRC.indexOf("const setStatus"));
    expect(addRegion).toContain("regions.push(");
    expect(addRegion).toContain("scale_units_per_px");
  });

  it("stamps only a positive scale, so a 0 cannot silently re-enable the call-wide fallback", () => {
    const addRegion = SRC.slice(SRC.indexOf("const addRegion"), SRC.indexOf("const setStatus"));
    expect(addRegion).toMatch(/if \(scale > 0\)/);
  });

  it("declares the field on the wire type instead of relying on structural typing", () => {
    // An undeclared extra property reaches the server today, but the next `.map()` over regions would
    // drop it with no type error — the defect would come back invisibly.
    expect(CLIENT).toContain("scale_units_per_px?: number");
  });

  it("keeps the Region type's scale optional, so a single-scale takeoff is unchanged", () => {
    expect(SRC).toMatch(/type Region = \{[^}]*scale_units_per_px\?: number/);
  });

  it("surfaces a multi-scale takeoff rather than leaving it to be discovered", () => {
    // A mixed-scale set is legitimate; it is also where a mis-calibrated sheet hides best.
    expect(SRC).toContain("scales_used");
    expect(SRC).toMatch(/used\.length < 2/);
  });
});

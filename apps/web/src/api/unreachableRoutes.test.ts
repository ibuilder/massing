import { readFileSync, readdirSync } from "node:fs";
import { resolve } from "node:path";

import { describe, expect, it } from "vitest";

/**
 * A server capability with no client is indistinguishable from one that was never built.
 *
 * R27-LAYOUT ②/③ and the `block_cooling` MEP sizing were all COMPLETE on the server and unreachable
 * from this app: `/projects/{pid}/mep/size` had no caller at all, and `client.ts::takeoff2d` never
 * sent `layout`, so the scoping the route implements could not be asked for. Wiring
 * `block_cooling` into the route (v0.3.1116) made it callable and not reachable — the product gap
 * survived the fix that was supposed to close it.
 *
 * These assertions are about REACH, not presence: each one follows the chain from a UI entry point
 * down to the request, because a client method nothing calls is the same defect one layer up.
 */
const SRC = (p: string) => readFileSync(resolve(__dirname, "..", p), "utf8");
/** The whole `src/api` surface, not `client.ts` alone.
 *
 *  SCALE-SEAM keeps moving methods out of `client.ts` into domain mixins — `takeoff2d` went to
 *  `api/estimate.ts` and its wire types to `api/types.ts` in v0.3.1119 — and a test pinned to one
 *  filename goes red on the extraction rather than on the behaviour it guards. The property here is
 *  "the client declares this", which is a fact about the API surface, not about which file holds it. */
function apiSurface(): string {
  const dir = resolve(__dirname);
  return readdirSync(dir).filter((f) => f.endsWith(".ts") && !f.endsWith(".test.ts"))
    .map((f) => readFileSync(resolve(dir, f), "utf8")).join("\n");
}
const CLIENT = apiSurface();

describe("routes the server implements are reachable from the app", () => {
  it("takeoff2d can send the sheet layout the route scopes against", () => {
    expect(CLIENT).toContain("layout: opts.layout");
    expect(CLIENT).toContain("px_per_point");
    // Absent must stay absent: the route distinguishes "no layout" from "a malformed layout" (422),
    // so sending the key with an undefined value would change behaviour for every existing caller.
    expect(CLIENT).toMatch(/\.\.\.\(opts\.layout \? \{ layout: opts\.layout \} : \{\}\)/);
  });

  it("the layout has a producer in the client, not just a consumer", () => {
    // The asymmetry this whole line of work keeps finding: a consumer wired without its producer
    // leaves a route asking for something no caller can obtain.
    expect(CLIENT).toContain("sheetRegions(");
    expect(CLIENT).toContain("/drawings/sheet-regions");
  });

  it("the takeoff UI actually offers the scoping, and the caller supplies the producer", () => {
    const ui = SRC("viewer/takeoff2d.ts");
    expect(ui).toContain("sheetLayout");
    expect(ui).toContain("pxPerPoint");
    // Off by default: this tool's normal case is a drawing with no model behind it.
    expect(ui).toContain("scopeChk.checked");
    // The sheet identity must be PASSED, never defaulted. `sheetRegions(projectId)` defaults to
    // preset `key` / page `A1`, and this tool accepts any uploaded image — so scoping a trace from
    // another sheet compared it against A1's viewports and could price it at the wrong drawing's
    // scale. That is the confident-wrong-number the scoping exists to prevent, reintroduced by the
    // defaulting. Found in review on #374; asserted here so it cannot come back.
    const caller = SRC("viewer/tools/exportsSection.ts");
    expect(caller).toMatch(/api\.sheetRegions\(projectId,\s*preset,\s*page\)/);
    expect(caller).not.toMatch(/api\.sheetRegions\(projectId\)/);
    expect(ui).toContain("presetIn");
    expect(ui).toContain("pageIn");
    // ...and a change of sheet must invalidate the loaded layout, or the previous sheet's viewports
    // are still what a tick of the box scopes against.
    expect(ui).toContain("layoutKey");
  });

  it("an unscoped or ambiguous trace is reported, never folded into the total", () => {
    const ui = SRC("viewer/takeoff2d.ts");
    for (const outcome of ["unscoped", "ambiguous", "unknown", "unreadable_viewports"]) {
      expect(ui).toContain(outcome);
    }
    // `priceable` counts only traces on exactly one drawing. A bare total with three of five traces
    // off the drawing is the confident wrong answer the server-side check exists to prevent.
    expect(ui).toContain("priceable");
  });

  it("mep/size is callable, including the block_cooling kind that had no client", () => {
    expect(CLIENT).toContain("mepSize(");
    expect(CLIENT).toContain("/mep/size");
    expect(CLIENT).toContain("sf_per_ton");
    expect(CLIENT).toContain("gfa_sf");
    expect(CLIENT).toContain("block_cooling");
  });

  it("refuses input it cannot send rather than sending a plausible wrong value", () => {
    const sec = SRC("viewer/tools/mepSection.ts");
    // `Number("")` is 0 and `Number("abc")` is NaN, so a two-state "cancelled or a number" helper
    // sends a blank required field as a zero. Four outcomes, and `blank` is only acceptable where
    // the field is genuinely optional. Raised in review on #374.
    for (const outcome of ['k: "cancelled"', 'k: "blank"', 'k: "bad"', 'k: "ok"']) {
      expect(sec).toContain(outcome);
    }
    // ...and an unparseable OPTIONAL value must not read as an omitted one: `block_cooling` treated
    // a typo'd area as "derive it from the model" and answered a question nobody asked.
    expect(sec).toContain("is not a positive number");
    // The hanger allowlist, the same discipline as `kind`, one level down.
    expect(sec).toContain("pipe_copper");
    expect(sec).toContain("unknown hanger kind");
  });

  it("the scope control is unavailable, not merely inert, when no layout loaded", () => {
    const ui = SRC("viewer/takeoff2d.ts");
    // Showing a tickable box that falls back to "quantifying without scoping" offers something the
    // control cannot do — a smaller cousin of the wrong-scale defect scoping exists to prevent.
    expect(ui).toContain("scopeChk.disabled = true");
    expect(ui).toContain("scopeChk.disabled = false");
  });

  it("mep sizing has a UI entry point wired through to the tools panel", () => {
    const sec = SRC("viewer/tools/mepSection.ts");
    expect(sec).toContain("d.api.mepSize(");
    expect(sec).toContain("block_cooling");
    expect(sec).toContain("sizeCalcBtn");
    // ...and the button is actually placed. A returned button nobody appends is exactly the
    // "built but unreachable" shape, moved one layer up.
    const app = SRC("viewer/app.ts");
    expect(app).toContain("sizeCalcBtn");
    expect(app).toMatch(/advWrap\.append\([^)]*sizeCalcBtn/);
  });
});

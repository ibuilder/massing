import { readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

import { describe, expect, it } from "vitest";

import type { EgressRoutes } from "./egressTravel";
import { egressReading, egressRows, findingGuids, worstSpaces } from "./egressTravel";

/**
 * EGRESS-TRAVEL-DARK, the screen half — IBC 1017 travel distance had no door in the app.
 *
 * The engine half is `services/api/test_egress_payload.py`, which replays the pre-fix route payload
 * and requires it to carry a polyline per space before reporting. This file asserts the client: that
 * a refusal cannot render as a clean building, that `unreachable` outranks `over_limit` rather than
 * being folded into it, and that the table is sorted on the same ordering the headline uses.
 */

const mk = (o: Partial<EgressRoutes> = {}): EgressRoutes => ({
  routed: o.routed ?? true,
  note: o.note ?? "",
  elevation: o.elevation ?? 0,
  cell_m: o.cell_m ?? 0.3,
  max_travel_m: o.max_travel_m ?? 61,
  exits: o.exits ?? 2,
  spaces: o.spaces ?? 10,
  compliant: o.compliant ?? 10,
  over_limit: o.over_limit ?? 0,
  unreachable: o.unreachable ?? 0,
  worst_travel_m: o.worst_travel_m ?? 42.5,
  max_detour_ratio: o.max_detour_ratio ?? 1.4,
  results: o.results ?? [],
  ...o,
});

const space = (name: string, travel: number | null, over = false, unreachable = false) => ({
  guid: `g-${name}`, name, straight_line_m: travel == null ? 10 : travel / 1.5,
  travel_m: travel, compliant: !over && !unreachable, unreachable,
  detour_ratio: travel == null ? null : 1.5,
  ...(unreachable ? { detail: "no route to any exit on this level" } : {}),
});

describe("egressReading — a refusal is not a clean building", () => {
  it("passes the engine's REASON through, because it is what tells the reader what to fix", () => {
    const r = egressReading(mk({
      routed: false,
      note: "no exterior doors found — mark egress doors IsExternal so a route has somewhere to go.",
    }));
    expect(r.kind).toBe("refused");
    expect(r.headline).toContain("not a clean result");
    expect(r.detail).toContain("IsExternal");
  });

  it("tones a refusal as neither a pass nor a finding", () => {
    expect(egressReading(mk({ routed: false, note: "model has no geometry to route over" })).tone)
      .toBe("");
  });

  it("ranks UNREACHABLE above over-limit — a different and worse finding", () => {
    const r = egressReading(mk({ spaces: 10, compliant: 7, over_limit: 2, unreachable: 1 }));
    expect(r.kind).toBe("unreachable");
    expect(r.tone).toBe("bad");
    expect(r.headline).toContain("1 space(s) have NO route to any exit");
    // ...and still states the over-limit count, rather than hiding it behind the worse finding
    expect(r.headline).toContain("2 more exceed");
    expect(r.detail).toContain("not reachable at all");
  });

  it("reports over-limit when nothing is unreachable", () => {
    const r = egressReading(mk({ spaces: 10, compliant: 8, over_limit: 2, worst_travel_m: 78.2 }));
    expect(r.kind).toBe("over");
    expect(r.tone).toBe("bad");
    expect(r.headline).toContain("2 of 10 space(s) exceed");
    expect(r.headline).toContain("78.2 m");
  });

  it("is `clear` only when every space routes within the limit", () => {
    const r = egressReading(mk());
    expect(r.kind).toBe("clear");
    expect(r.tone).toBe("ok");
    expect(r.headline).toContain("All 10 space(s) route to an exit");
  });

  it("always states the BASIS — exits found, limit, and the grid it was routed on", () => {
    for (const r of [egressReading(mk()),
                     egressReading(mk({ over_limit: 1, compliant: 9 })),
                     egressReading(mk({ unreachable: 1, compliant: 9 }))]) {
      expect(r.detail).toContain("exterior exit(s)");
      expect(r.detail).toContain("61.0 m");
      expect(r.detail).toContain("0.3 m grid");
    }
  });

  it("names how much a straight line was understating the walk, when there is a ratio", () => {
    expect(egressReading(mk({ max_detour_ratio: 2.35 })).detail).toContain("×2.35");
    // ...and says nothing rather than ×null when the engine had no ratio to give
    const none = egressReading(mk({ max_detour_ratio: null }));
    expect(none.detail).not.toContain("×");
    expect(none.detail).not.toContain("understated");
  });
});

describe("egressRows", () => {
  it("keeps the three outcomes as three rows", () => {
    const rows = egressRows(mk({ spaces: 10, compliant: 7, over_limit: 2, unreachable: 1 }));
    const get = (k: string) => rows.find((x) => x.k === k)?.v;
    expect(get("Within the limit")).toBe("7");
    expect(get("Over the limit")).toBe("2");
    expect(get("No route at all")).toBe("1");
    expect(get("Grid resolution")).toBe("0.3 m");
  });

  it("renders nothing at all for a refusal, so the caller shows the note instead", () => {
    expect(egressRows(mk({ routed: false }))).toEqual([]);
  });
});

describe("worstSpaces — sorted the way the headline ranks them", () => {
  it("puts unreachable spaces ahead of the longest walk, then longest first", () => {
    // THE OVER-LIMIT SPACES GO IN ASCENDING ORDER ON PURPOSE. The first draft listed them 95 then
    // 70, which is already the output order, so deleting the distance tiebreaker changed nothing and
    // the mutation survived — the same blind spot LAYOUT-RENUMBER's bucket sort had one item
    // earlier. *A reorder is invisible to a fixture already in that order.*
    const r = mk({
      results: [space("C", 70, true), space("B", null, false, true), space("A", 95, true)],
    });
    expect(worstSpaces(r).map((w) => w.label)).toEqual(["B", "A", "C"]);
  });

  it("keys the sort on `unreachable` rather than the distance, which is null for those", () => {
    // `travel_m` is null for an unreachable space, so a distance-only sort would place it anywhere.
    const r = mk({ results: [space("far", 120, true), space("none", null, false, true)] });
    expect(worstSpaces(r)[0]!.label).toBe("none");
  });

  it("includes only the findings, never a compliant space", () => {
    const r = mk({ results: [space("ok", 20), space("bad", 90, true)] });
    expect(worstSpaces(r).map((w) => w.label)).toEqual(["bad"]);
  });

  it("shows routed AGAINST straight-line, which is the whole argument for the routed number", () => {
    const r = mk({ results: [space("bad", 90, true)] });
    expect(worstSpaces(r)[0]!.detail).toContain("90.0 m routed");
    expect(worstSpaces(r)[0]!.detail).toContain("60.0 m straight");
    expect(worstSpaces(r)[0]!.detail).toContain("×1.50");
  });

  it("gives an unreachable space the engine's own wording, not a distance", () => {
    const r = mk({ results: [space("none", null, false, true)] });
    expect(worstSpaces(r)[0]!.detail).toBe("no route to any exit on this level");
  });

  it("falls back to the GUID when a space has no name", () => {
    const r = mk({ results: [{ ...space("x", 90, true), name: null }] });
    expect(worstSpaces(r)[0]!.label).toBe("g-x");
  });

  it("is empty on a refusal, where `results` is absent entirely", () => {
    expect(worstSpaces(mk({ routed: false, results: undefined }))).toEqual([]);
    expect(findingGuids(mk({ routed: false, results: undefined }))).toEqual([]);
  });
});

describe("findingGuids", () => {
  it("isolates the unreachable and the over-limit, and nothing else", () => {
    const r = mk({ results: [space("ok", 20), space("bad", 90, true),
                             space("none", null, false, true)] });
    expect(findingGuids(r)).toEqual(["g-bad", "g-none"]);
  });
});

describe("the panel is WIRED to the reading — the pure tests above cannot see this", () => {
  // Source-level, and the limit is stated: a render inside `if (false)` would pass. Anchored on
  // `__file__` because `vitest` and `run_tests.py` start from different directories.
  const SRC = readFileSync(
    resolve(dirname(fileURLToPath(import.meta.url)), "analyseSection.ts"), "utf-8");

  it("calls the route and hands the response to the module's own renderer", () => {
    expect(SRC).toContain("api.egressRoutes(pid)");
    expect(SRC).toContain("renderEgressCard(r, {");
    expect(SRC).toContain("planUrl: () => api.egressPlanUrl(pid)");
  });

  it("keeps the card BODY out of the eager chunk, which is what the budget refused", () => {
    // Deferring only the reading left the shell at exactly 224.0 KB against a 224 KB ceiling: the
    // panel's thirty lines of card-building were the cost. *Deferring the decision and keeping the
    // rendering is half a lazy module.* So this file must hold no `resultNote`/`kvTable` call for
    // the egress card at all — the whole body lives behind the import.
    expect(SRC).toContain('await import("./egressTravel")');
    expect(SRC).not.toContain("egressRows(");
    expect(SRC).not.toContain("worstSpaces(");
    expect(SRC).not.toContain("findingGuids(");
  });

  it("isolates the findings in 3D rather than every space", () => {
    // The host supplies the isolate primitive; the module decides WHICH guids.
    expect(SRC).toContain("isolate: (g) => { void layerMgr.isolateGuids(g); }");
    const mod = readFileSync(
      resolve(dirname(fileURLToPath(import.meta.url)), "egressTravel.ts"), "utf-8");
    expect(mod).toContain("const guids = findingGuids(r);");
    expect(mod).toContain("if (!r.routed) return;");
  });

  it("and the client DECLARES the fields, or no derivation over declarations sees them", () => {
    const api = readFileSync(
      resolve(dirname(fileURLToPath(import.meta.url)), "../../api/codecheck.ts"), "utf-8");
    expect(api).toContain("unreachable?: number");
    expect(api).toContain("max_detour_ratio?: number | null");
    // ONE query builder shared by the JSON summary and the drawing: a plan showing one grid
    // resolution beside a table computed on another is worse than either alone.
    expect(api).toContain("function _egressQuery(");
    expect(api).toContain("`/projects/${pid}/egress/routes${_egressQuery(opts)}`");
    expect(api).toContain("`/projects/${pid}/egress/plan.svg${_egressQuery(opts)}`");
  });
});

import { readFileSync } from "node:fs";
import { describe, expect, it } from "vitest";

import type { ProdActuals } from "./productivity";
import { productivityRows, productivityScope, provenanceLine } from "./productivity";

/**
 * PROD-DARK — the crew productivity loop, and the two things an ahead/behind read means nothing
 * without.
 *
 * `progressActuals` was frozen as callerless, so the field crew's own productivity record had no
 * screen. Two coverage facts the engine already carries and a first consumer would drop:
 *
 * ① **`planned_compared` is `ahead + on_track + behind`**, and it sits beside `group_count` because
 * they differ. A group with no planned rate gets `status: null` and is in neither tally — so
 * *"0 behind"* over twelve groups none of which has a baseline is not a job running to plan, it is a
 * job with no plan to run to, and the remedies are opposite.
 *
 * ② **The rows may not be the ones you passed.** With an empty `actuals` list the route analyses the
 * project's stored records instead, *"so the loop runs off the record of authority, not a one-shot
 * payload"*, and `source` names which. The client type's own comment already called it *"the one key
 * the type did not name"*.
 */

/**
 * A group, defaulting to the healthy case so each test names only what it varies.
 *
 * **`??` is deliberately NOT used for the nullable fields.** The first draft wrote
 * `installed_rate: over.installed_rate ?? 3`, which collapses an explicit `null` into the default —
 * so the test for *"the engine could not compute a rate"* silently exercised a rate of 3. A factory
 * that cannot express `null` cannot test a module whose whole subject is the difference between a
 * missing figure and a computed one. *Second time today a helper has done this* — `macroTool`'s
 * answer stub turned a cancel into a blank — so the shape is spelled out rather than shortened.
 */
const group = (over: Partial<ProdActuals["groups"][number]> & { group: string }):
  ProdActuals["groups"][number] => {
  const pick = <K extends keyof ProdActuals["groups"][number]>(
    k: K, dflt: ProdActuals["groups"][number][K]) => (k in over ? over[k]! : dflt);
  return {
    group: over.group, material_class: pick("material_class", "concrete"), unit: pick("unit", "m3"),
    entries: pick("entries", 3), installed_qty: pick("installed_qty", 90),
    productive_hours: pick("productive_hours", 30), idle_hours: pick("idle_hours", 6),
    installed_rate: pick("installed_rate", 3), utilization: pick("utilization", 0.833),
    planned_rate: pick("planned_rate", null), variance_pct: pick("variance_pct", null),
    status: pick("status", null), planned_qty: pick("planned_qty", null),
    pct_complete: pick("pct_complete", null), remaining_qty: pick("remaining_qty", null),
    projected_hours_at_rate: pick("projected_hours_at_rate", null),
  };
};

function pa(over: Partial<ProdActuals> = {}): ProdActuals {
  const groups = over.groups ?? [];
  const tally = (s: string) => groups.filter((g) => g.status === s).length;
  return {
    group_count: groups.length, groups,
    overall_utilization: groups.length ? 0.8 : null,
    total_productive_hours: 30, total_idle_hours: 6,
    planned_compared: tally("ahead") + tally("on_track") + tally("behind"),
    ahead: tally("ahead"), on_track: tally("on_track"), behind: tally("behind"),
    worst: null, note: "Installed rate = qty ÷ productive (cycle) hours",
    source: "progress_actual module", ...over,
  };
}

describe("productivityScope — the tally counts only what had a baseline", () => {
  it("is the SHIPPED SHAPE: twelve groups, no planned rate anywhere, '0 behind'", () => {
    const p = pa({ groups: Array.from({ length: 12 }, (_, i) => group({ group: `A${i}` })) });
    expect(p.behind).toBe(0);                     // what a first consumer would have printed
    expect(p.planned_compared).toBe(0);
    const s = productivityScope(p);
    expect(s.kind).toBe("no-baseline");
    expect(s.tone).toBe("warn");
    expect(s.headline).toBe("None of 12 group(s) has a planned rate");
    expect(s.detail).toContain("nothing has a baseline to be ahead OF");
    expect(s.detail).not.toContain("0 behind");
  });

  it("names the uncompared remainder when only some groups have a rate", () => {
    const p = pa({ groups: [group({ group: "Slab", status: "behind", variance_pct: -22 }),
                            group({ group: "Walls" }), group({ group: "Steel" })],
                   worst: "Slab" });
    const s = productivityScope(p);
    expect(s.kind).toBe("partial");
    expect(s.tone).toBe("bad");                   // a behind group is a finding
    expect(s.headline).toContain("1 of 3 group(s) compared");
    expect(s.headline).toContain("0 ahead · 0 on track · 1 behind");
    expect(s.detail).toContain("The other 2 have no planned rate");
    expect(s.detail).toContain("Worst: Slab.");
  });

  it("is `ok` only when every group is compared and none is behind", () => {
    const p = pa({ groups: [group({ group: "Slab", status: "ahead", variance_pct: 12 }),
                            group({ group: "Walls", status: "on_track", variance_pct: 1 })] });
    const s = productivityScope(p);
    expect(s.kind).toBe("full");
    expect(s.tone).toBe("ok");
    expect(s.headline).toContain("All 2 group(s) compared");
  });

  it("a full comparison with a behind group is still a finding", () => {
    const p = pa({ groups: [group({ group: "Slab", status: "behind", variance_pct: -30 })] });
    expect(productivityScope(p).tone).toBe("bad");
  });

  it("nothing logged says what to log rather than reporting a clean job", () => {
    const s = productivityScope(pa());
    expect(s.kind).toBe("none");
    expect(s.tone).toBe("");
    expect(s.detail).toContain("Log installed quantities and crew hours");
  });

  it("carries no markup — the panel escapes it", () => {
    for (const p of [pa(), pa({ groups: [group({ group: "A" })] }),
                     pa({ groups: [group({ group: "A", status: "behind", variance_pct: -9 })] })]) {
      const s = productivityScope(p);
      expect(`${s.headline}${s.detail}`).not.toMatch(/[<>]/);
    }
  });
});

describe("provenanceLine — a productivity figure needs its source stated", () => {
  it("distinguishes the stored log from a supplied payload", () => {
    expect(provenanceLine("progress_actual module")).toContain("record of authority");
    expect(provenanceLine("request")).toContain("not the project's stored log");
  });

  it("says nothing when the server said nothing, rather than guessing", () => {
    expect(provenanceLine(null)).toBeNull();
    expect(provenanceLine("")).toBeNull();
    expect(provenanceLine("   ")).toBeNull();
  });
});

describe("productivityRows", () => {
  it("says 'no planned rate' rather than leaving the variance blank", () => {
    const [r] = productivityRows(pa({ groups: [group({ group: "Walls" })] }));
    expect(r!.vsPlanned).toBe("no planned rate");
    expect(r!.strong).toBe(false);
  });

  it("signs the variance and marks a behind group", () => {
    const [r] = productivityRows(pa({ groups: [
      group({ group: "Slab", status: "behind", variance_pct: -22, pct_complete: 0.4,
              projected_hours_at_rate: 45 })] }));
    expect(r!.vsPlanned).toBe("-22% · behind");
    expect(r!.complete).toBe("40%");
    expect(r!.remaining).toBe("45 h at this rate");
    expect(r!.strong).toBe(true);
    expect(productivityRows(pa({ groups: [group({ group: "S", status: "ahead", variance_pct: 8 })] }))[0]!
      .vsPlanned).toBe("+8% · ahead");
  });

  it("carries the unit with the rate — a bare number is not a rate", () => {
    expect(productivityRows(pa({ groups: [group({ group: "S", unit: "m2", installed_rate: 12 })] }))[0]!
      .rate).toBe("12 m2/h");
  });

  it("shows a dash where the engine could not compute one", () => {
    const [r] = productivityRows(pa({ groups: [
      group({ group: "S", installed_rate: null, utilization: null })] }));
    expect(r!.rate).toBe("—");
    expect(r!.utilization).toBe("—");
  });
});

/** **The engine side**, read rather than assumed. */
describe("the engine these readings are about", () => {
  const SRC = readFileSync("../../services/api/src/aec_api/prod_actuals.py", "utf8");

  it("counts only the compared groups in the tally", () => {
    expect(SRC).toContain('"planned_compared": ahead + on_track + behind,');
    expect(SRC).toContain('"group_count": len(out_groups),');
  });

  it("still states that rates are not summable across trades", () => {
    expect(SRC).toContain("no cross-trade rate");
  });

  it("the route still substitutes the stored log for an empty payload", () => {
    const ROUTE = readFileSync("../../services/api/src/aec_api/routers/research.py", "utf8");
    expect(ROUTE).toContain("the record of authority, not a one-shot payload");
  });
});

/** The render, pinned at the source — a reading nothing calls is the recurring mutation. */
describe("the reading reaches the Operations panel", () => {
  const OPS = readFileSync("src/portal/panels/operations.ts", "utf8");

  it("asks for the STORED log by passing an empty actuals list", () => {
    expect(OPS).toContain("ctx.host.api.progressActuals(pid, [])");
  });

  it("renders the scope, the provenance and the rows", () => {
    expect(OPS).toContain("const scope = productivityScope(pa)");
    expect(OPS).toContain("esc(scope.headline)");
    expect(OPS).toContain("esc(scope.detail)");
    expect(OPS).toContain("const prov = provenanceLine(pa.source)");
    expect(OPS).toContain("productivityRows(pa)");
  });

  it("APPENDS the card — the mutation that survived three times this session", () => {
    expect(OPS).toContain("        body.append(pc);");
  });

  it("escapes every cell — an activity name is user text in innerHTML", () => {
    expect(OPS).toContain("<td>${esc(r.group)}</td>");
    expect(OPS).toContain("${esc(r.vsPlanned)}");
  });
});

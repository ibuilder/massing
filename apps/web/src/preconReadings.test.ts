import { readFileSync } from "node:fs";
import { describe, expect, it } from "vitest";

import type { VeLog } from "./preconReadings";
import { exposureCaveat, veReading, veTargetFromAlignment } from "./preconReadings";

/**
 * VE-DARK — the preconstruction money registers, and what their totals leave out.
 *
 * `precon.py` sums each register's money field through `_num`, which **returns 0.0 for anything it
 * cannot parse**. So a row recorded with no figure is counted in `open_count` or `ve_count`,
 * contributes nothing to the money beside it, and nothing in the response said so. One of the three
 * registers was already on screen printing such a total (`decisionLog` in `reportCenter.ts`), which
 * makes it a live defect there and a latent one in the two that had no caller at all.
 *
 * The sharpest instance is `target_met`, which is `accepted_savings >= target`: an accepted idea
 * with no savings figure adds 0, so a `false` can mean *nobody recorded the numbers* rather than
 * *the ideas do not close the gap* — and those two have **opposite remedies**. Price the accepted
 * ideas, or go and find more of them. A screen printing the boolean sends the reader at the wrong
 * one, which is why the unpriced case is answered BEFORE the verdict is read rather than appended
 * as a caveat beside a number somebody has already believed.
 */

const ve = (over: Partial<VeLog> = {}): VeLog => ({
  ve_count: 0, proposed_savings: 0, accepted_savings: 0, rejected_savings: 0, pipeline_savings: 0,
  rows_without_savings: 0, accepted_without_savings: 0, by_status: {}, rows: [], ...over,
});

const row = (subject: string, status: string, savings: number | null) => ({
  ref: `VE-${subject}`, subject, status, savings: savings ?? 0, savings_given: savings !== null,
});

describe("exposureCaveat — a total over a subset of the count beside it", () => {
  it("names how many rows carry no figure", () => {
    expect(exposureCaveat(3, 11, "cost", "open decision"))
      .toBe("3 of 11 open decision(s) carry no cost figure and add nothing to the total above — "
        + "the money is a sum over the rest, not over the count beside it.");
  });

  it("is null when nothing is missing — the caveat appears only where it changes the number", () => {
    expect(exposureCaveat(0, 11, "cost")).toBeNull();
    expect(exposureCaveat(-1, 11, "cost")).toBeNull();
  });
});

describe("veReading — `target_met` is used only where it means something", () => {
  it("an EMPTY register is not a shortfall", () => {
    const r = veReading(ve({ target: 250_000, target_met: false, gap_after_accepted: 250_000 }),
                        "over budget");
    expect(r.kind).toBe("none");
    expect(r.headline).toContain("No value-engineering ideas recorded");
    expect(r.detail).toContain("not a shortfall");
  });

  it("is the SHARP CASE: unpriced accepted ideas are answered BEFORE the verdict", () => {
    const v = ve({
      ve_count: 4, accepted_savings: 40_000, proposed_savings: 10_000, pipeline_savings: 50_000,
      rows_without_savings: 2, accepted_without_savings: 2,
      target: 250_000, gap_after_accepted: 210_000, target_met: false,
      rows: [row("a", "accepted", 40_000), row("b", "accepted", null),
             row("c", "accepted", null), row("d", "proposed", 10_000)],
    });
    const r = veReading(v, "the latest estimate is $250,000 over the recorded budget");
    expect(r.kind).toBe("unpriced");
    expect(r.detail).toContain("2 of the accepted idea(s) carry NO savings figure");
    expect(r.detail).toContain("opposite remedies");
    expect(r.detail).toContain("Target basis: the latest estimate is $250,000 over");
    // It must NOT read as a shortfall — that is the wrong remedy.
    expect(r.detail).not.toContain("still open after the accepted");
    expect(r.kind).not.toBe("short");
  });

  it("a genuine shortfall says how much is open and how much is still in proposal", () => {
    const v = ve({
      ve_count: 3, accepted_savings: 90_000, proposed_savings: 60_000, pipeline_savings: 150_000,
      target: 250_000, gap_after_accepted: 160_000, target_met: false,
      rows: [row("a", "accepted", 90_000), row("b", "proposed", 60_000)],
    });
    const r = veReading(v, "over budget");
    expect(r.kind).toBe("short");
    expect(r.detail).toContain("$160,000 of the $250,000 target is still open");
    expect(r.detail).toContain("$60,000 is still in proposal");
  });

  it("a met target reads as met even with unpriced ideas elsewhere in the log", () => {
    // `accepted_without_savings` cannot make a MET verdict wrong: the priced ones already clear it.
    const v = ve({
      ve_count: 5, accepted_savings: 300_000, pipeline_savings: 300_000,
      rows_without_savings: 1, accepted_without_savings: 1,
      target: 250_000, gap_after_accepted: -50_000, target_met: true,
    });
    const r = veReading(v, "over budget");
    expect(r.kind).toBe("met");
    expect(r.detail).toContain("closes the $250,000 target");
  });

  it("no target is a list of ideas, not a verdict of any kind", () => {
    const v = ve({ ve_count: 2, proposed_savings: 20_000, pipeline_savings: 20_000,
                   rows: [row("a", "proposed", 20_000)] });
    const r = veReading(v, "the latest estimate is not over budget, so there is no gap to close");
    expect(r.kind).toBe("no-target");
    expect(r.headline).toContain("2 idea(s)");
    expect(r.detail).toContain("not over budget");
    expect(r.detail).not.toContain("target is still open");
  });

  it("carries no markup — reportCenter interpolates these into innerHTML", () => {
    for (const r of [veReading(ve(), null),
                     veReading(ve({ ve_count: 1, target: 1, target_met: false,
                                    accepted_without_savings: 1 }), null)]) {
      expect(`${r.headline}${r.detail}`).not.toMatch(/[<>]/);
    }
  });
});

describe("veTargetFromAlignment — a target with no basis is a number nobody can check", () => {
  it("uses the over-budget variance and says so", () => {
    const t = veTargetFromAlignment({ budget: 40_000_000, variance_to_budget: 1_250_000 });
    expect(t.target).toBe(1_250_000);
    expect(t.basis).toContain("$1,250,000 over the recorded budget");
  });

  it("claims NO target when the project has no budget", () => {
    const t = veTargetFromAlignment({ budget: null, variance_to_budget: 500_000 });
    expect(t.target).toBeNull();
    expect(t.basis).toContain("no budget recorded");
  });

  it("claims no target when the estimate is under budget", () => {
    expect(veTargetFromAlignment({ budget: 1, variance_to_budget: -5 }).target).toBeNull();
    expect(veTargetFromAlignment({ budget: 1, variance_to_budget: 0 }).target).toBeNull();
    expect(veTargetFromAlignment({ budget: 1, variance_to_budget: null }).basis)
      .toContain("not over budget");
  });

  it("claims no target when the alignment read is unavailable", () => {
    expect(veTargetFromAlignment(null).target).toBeNull();
  });
});

/**
 * **The engine side, read rather than assumed.** These readings exist because `_num` collapses
 * "no figure" and "zero" into one number; the counts they render are computed in Python, and a
 * change there leaves every fixture above green.
 */
describe("the engine these readings are about", () => {
  const SRC = readFileSync("../../services/api/src/aec_api/precon.py", "utf8");

  it("still has the `_num` that returns 0.0 — the reason any of this is needed", () => {
    expect(SRC).toContain("def _num(v: Any) -> float:");
    expect(SRC).toMatch(/except \(TypeError, ValueError\):\n {8}return 0\.0/);
  });

  it("distinguishes absent from zero, and excludes booleans from a money field", () => {
    expect(SRC).toContain("def _num_or_none(v: Any) -> float | None:");
    // `float(True)` is 1.0, and a boolean in `cost_impact` is ACCEPTED on write (measured: 201) —
    // so under the old `_num` a stray flag became one dollar of exposure. Not hypothetical, and
    // asserted in `services/api/test_precon.py` against the real write path.
    expect(SRC).toContain("if v is None or isinstance(v, bool):");
    expect(SRC).toContain('if isinstance(v, str) and not v.strip():');
  });

  it("emits the coverage counts all three registers now carry", () => {
    expect(SRC).toContain('"rows_without_savings": sum(1 for r in rows if not r["savings_given"])');
    expect(SRC).toContain('"accepted_without_savings"');
    expect(SRC).toContain('"rows_without_cost_impact"');
    expect(SRC).toContain('"open_without_cost_impact"');
    expect(SRC).toContain('"open_without_schedule_impact"');
  });

  it("still computes `target_met` as the subset comparison these readings qualify", () => {
    expect(SRC).toContain('out["target_met"] = accepted >= gap');
  });
});

/**
 * **And the render, pinned at the source.** `reportCenter.ts` needs some forty api methods mocked
 * to reach one of these tools, so the DOM complement built for MACRO-DARK and CODE-READY-DARK is
 * not available here — stated rather than left as a gap, because a reach that is assumed is what
 * these entries are about. What IS checked is that each reading reaches a render: the alternative
 * is a decision function that is perfect and called by nothing, which is the mutation that survived
 * MACRO-DARK's first pass.
 */
describe("the readings reach the screen", () => {
  const RC = readFileSync("src/reportCenter.ts", "utf8");

  it("renders the VE reading and its missing-figure caveat", () => {
    expect(RC).toContain("const r = veReading(v, basis.basis)");
    expect(RC).toContain("escapeHtml(r.headline)");
    expect(RC).toContain("escapeHtml(r.detail)");
    expect(RC).toContain('exposureCaveat(v.rows_without_savings, v.ve_count, "savings", "idea")');
  });

  it("sends the derived target, with its basis, rather than a bare number", () => {
    expect(RC).toContain("veTargetFromAlignment(await api.preconAlignment(pid))");
    expect(RC).toContain("api.veLog(pid, basis.target ?? undefined)");
  });

  it("qualifies the decision log's exposure — the register that was ALREADY on screen", () => {
    expect(RC).toContain('exposureCaveat(s.open_without_cost_impact, s.open_count, "cost"');
    expect(RC).toContain('exposureCaveat(s.open_without_schedule_impact, s.open_count, "schedule"');
    expect(RC).toContain("(cv ? `<div class=\"meta\">⚠ ${escapeHtml(cv)}</div>` : \"\")");
  });

  it("renders the assumptions register with its own caveat", () => {
    expect(RC).toContain("api.assumptionsRegister(pid)");
    expect(RC).toContain('exposureCaveat(a.open_without_cost_impact, a.open_count, "cost"');
  });

  it("marks an unpriced ROW rather than printing it as $0", () => {
    expect(RC).toContain('x.savings_given ? money(x.savings) : "not priced"');
    expect(RC).toContain('x.cost_impact_given ? money(x.cost_impact) : "no figure"');
  });
});

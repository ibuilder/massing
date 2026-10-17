/** LEVEL-UNREAD — the outcome of a levelling run, asserted without a DOM.
 *
 *  Both fixtures below are the measured response from the same four-activity project at a cap of
 *  8 crew/day, under the two horizons. The pair IS the finding: the `within_float` run is a total
 *  failure whose `move_count` and `finish_moved_days` are both zero, which is exactly what a
 *  schedule already inside its caps produces.
 */
import { describe, expect, it } from "vitest";
import type { LevellingResult } from "../../api/schedule";
import {
  TONE_CSS, capRows, capVerdict, coverageNote, levelIssueRows, uncappedNote, unavailableExtras,
} from "./levelRead";

const COVERAGE: NonNullable<LevellingResult["coverage"]> = {
  activities: 10, with_demand: 8, without_demand: 2,
  without_demand_sample: ["No trade", "No crew"],
  levelled_demands: 5, capped_trades: ["Carpentry"], uncapped_trades: ["Electrical"],
};

/** `horizon: within_float` — measured: peak 26 → 26, 0 moves, 5 unresolved, finish unmoved. */
const FAILED: LevellingResult = {
  available: true, horizon: "within_float", mode: "advisory",
  finish_before: "2027-03-05", finish_after: "2027-03-05", finish_moved_days: 0,
  moves: [], move_count: 0, unresolved_count: 5,
  peak_before: { Carpentry: 26 }, peak_after: { Carpentry: 26 },
  caps: { Carpentry: 8 },
  within_caps: false,
  over_cap: [{ trade: "Carpentry", cap: 8, peak_after: 26, over_by: 18 }],
  coverage: COVERAGE,
  issues: [{ severity: "warning", code: "MASSING.PREDECESSOR_UNRESOLVED",
             message: "Bad pred: predecessor 'NOPE-999' matches no activity",
             action: "relationship dropped", table: null, row_key: "abc",
             field: "predecessors", raw_value: "NOPE-999" }],
};

/** `horizon: extend_finish` — measured: peak 26 → 8, 3 moves, 0 unresolved, finish +21d. */
const SOLVED: LevellingResult = {
  ...FAILED, horizon: "extend_finish", finish_moved_days: 21,
  move_count: 3, unresolved_count: 0,
  peak_after: { Carpentry: 8 }, within_caps: true, over_cap: [],
};

describe("the verdict is the outcome, not the motion", () => {
  it("a run that moved nothing and met no cap is CRITICAL", () => {
    // THE DEFECT. `moves 0 · finish +0d` is what a schedule already inside its caps produces, so
    // the card's three tiles could not tell "nothing needed doing" from "nothing could be done".
    const v = capVerdict(FAILED);
    expect(v?.tone).toBe("crit");
    expect(v?.text).toContain("1 trade(s) still over the cap");
    expect(v?.text).toContain("Carpentry peaks at 26 against a cap of 8");
    expect(v?.text).toContain("18 over");
  });

  it("under 'keep the finish' it names the horizon as the reason and the way to price it", () => {
    // The horizon is the trade-off and has no safe default; a reader looking at a failure needs to
    // know it was a constraint they chose rather than an engine that gave up.
    expect(capVerdict(FAILED)?.text).toContain("allow a later finish");
  });

  it("a successful run is GOOD and states the price it paid", () => {
    const v = capVerdict(SOLVED);
    expect(v?.tone).toBe("good");
    expect(v?.text).toContain("at or below its limit");
    expect(v?.text).toContain("21 day(s) on the finish");
    // ...and does NOT dangle the within_float advice on a run that succeeded.
    expect(v?.text).not.toContain("allow a later finish");
  });

  it("says 'no movement of the finish' when a success cost nothing", () => {
    expect(capVerdict({ ...SOLVED, finish_moved_days: 0 })?.text)
      .toContain("no movement of the finish");
  });

  it("is null for a run that did not happen — not a verdict of failure", () => {
    // `within_caps` is `null` rather than `false` there: the levelling did not fail to meet the
    // caps either, and rendering "over the cap" on a project with no activities would be a finding
    // about nothing.
    expect(capVerdict({ ...FAILED, available: false, within_caps: null })).toBeNull();
    expect(capVerdict({ ...FAILED, within_caps: null })).toBeNull();
  });

  it("emits PLAIN TEXT, so no caller has to decide about escaping a trade name", () => {
    // The trade is whatever the user typed into the caps input.
    const v = capVerdict({ ...FAILED,
      caps: { "<img src=x>": 8 },
      over_cap: [{ trade: "<img src=x>", cap: 8, peak_after: 26, over_by: 18 }] });
    expect(v?.text).not.toContain("<strong>");
    expect(v?.text).toContain("<img src=x>");      // present as TEXT, for the caller to escape
  });
});

describe("the per-trade peaks are shown against their caps", () => {
  it("renders before → after → cap and marks the over ones", () => {
    const rows = capRows(FAILED);
    expect(rows).toEqual([
      { trade: "Carpentry", before: "26", after: "26", cap: "8", tone: "crit" }]);
    expect(capRows(SOLVED)[0]).toEqual(
      { trade: "Carpentry", before: "26", after: "8", cap: "8", tone: "good" });
  });

  it("covers only the CAPPED trades — an uncapped one has no cap to compare to", () => {
    // `Electrical` carries 30 crew/day and is absent from `peak_before` entirely, because the
    // engine only feeds in demands whose trade is capped. `uncappedNote` is what names it.
    expect(capRows(FAILED).map((r) => r.trade)).not.toContain("Electrical");
  });

  it("renders an em-dash rather than 0 for a cap whose trade has no measured peak", () => {
    const rows = capRows({ ...FAILED, caps: { Carpentry: 8, Masonry: 4 },
                           over_cap: [] });
    expect(rows.find((r) => r.trade === "Masonry")).toEqual(
      { trade: "Masonry", before: "—", after: "—", cap: "4", tone: "good" });
  });

  it("keeps two decimals on a fractional peak and none on a whole one", () => {
    expect(capRows({ ...FAILED, peak_after: { Carpentry: 8.5 }, caps: { Carpentry: 8 } })[0]!.after)
      .toBe("8.50");
  });
});

describe("what the verdict is silent about is named", () => {
  it("names the uncapped trades and why they are outside the verdict", () => {
    const n = uncappedNote(FAILED);
    expect(n).toContain("Electrical");
    expect(n).toContain("says nothing about");
    expect(n).toContain("capped at a guess");
  });

  it("is silent when every trade carrying crew has a cap", () => {
    expect(uncappedNote({ ...FAILED,
      coverage: { ...COVERAGE, uncapped_trades: [] } })).toBeNull();
    expect(uncappedNote({ ...FAILED, coverage: null })).toBeNull();
  });

  it("names the activities that could not enter the levelling at all", () => {
    const c = coverageNote(FAILED);
    expect(c?.tone).toBe("warn");
    expect(c?.text).toContain("8 of 10 activity(s)");
    expect(c?.text).toContain("No trade");
    expect(c?.text).toContain("No crew");
  });

  it("says so when the sample is capped and the count is not", () => {
    const c = coverageNote({ ...FAILED, coverage: { ...COVERAGE, activities: 60,
      with_demand: 8, without_demand: 52 } });
    expect(c?.text).toContain("52 carry no trade");
    expect(c?.text).toContain("the count is exact");
  });

  it("reports full coverage affirmatively rather than saying nothing", () => {
    // A silent card and a fully-covered one must not look the same: this is the one place the
    // reader learns that every activity was in scope.
    const c = coverageNote({ ...FAILED,
      coverage: { ...COVERAGE, without_demand: 0, without_demand_sample: [] } });
    expect(c?.tone).toBe("");
    expect(c?.text).toContain("All 10 activity(s)");
  });
});

describe("the engine's issue log reaches a screen", () => {
  it("renders the code, the message and the action it took", () => {
    const rows = levelIssueRows(FAILED);
    expect(rows).toHaveLength(1);
    expect(rows[0]!.code).toBe("MASSING.PREDECESSOR_UNRESOLVED");
    // The ACTION is the part a planner needs: the relationship is gone from the network.
    expect(rows[0]!.text).toContain("relationship dropped");
    expect(rows[0]!.where).toBe("predecessors: NOPE-999");
    expect(rows[0]!.tone).toBe("warn");
  });

  it("orders error before warning before info, not by arrival", () => {
    const rows = levelIssueRows({ ...FAILED, issues: [
      { ...FAILED.issues![0]!, severity: "info", code: "I" },
      { ...FAILED.issues![0]!, severity: "error", code: "E" },
      { ...FAILED.issues![0]!, severity: "warning", code: "W" }] });
    expect(rows.map((r) => r.code)).toEqual(["E", "W", "I"]);
    expect(rows.map((r) => r.tone)).toEqual(["crit", "warn", ""]);
  });

  it("is empty, not undefined, against a server that sends no issues", () => {
    expect(levelIssueRows({ ...FAILED, issues: undefined })).toEqual([]);
  });

  it("puts an unknown severity last rather than dropping it", () => {
    const rows = levelIssueRows({ ...FAILED, issues: [
      { ...FAILED.issues![0]!, severity: "catastrophe", code: "X" },
      { ...FAILED.issues![0]!, severity: "error", code: "E" }] });
    expect(rows.map((r) => r.code)).toEqual(["E", "X"]);
  });
});

describe("a refusal carries its own diagnostic", () => {
  it("names the trades that DO appear, which is what makes 'check the spelling' actionable", () => {
    const n = unavailableExtras({ ...FAILED, available: false,
      reason: "none of the capped trades appear on any activity — check the trade spelling",
      trades: ["Carpentry", "Electrical"], within_caps: null, coverage: null });
    expect(n).toContain("Carpentry · Electrical");
    // The REASON is excluded: `scheduleMethods.render` already printed it, and returning it here
    // left the caller stripping its own prefix back off.
    expect(n).not.toContain("check the trade spelling");
  });

  it("names the loop when there is one", () => {
    expect(unavailableExtras({ ...FAILED, available: false, cycle: ["A", "B", "A"],
                               within_caps: null, coverage: null }))
      .toContain("A → B → A");
  });

  it("is null for an available result and for a refusal with no extras", () => {
    expect(unavailableExtras(FAILED)).toBeNull();
    expect(unavailableExtras({ ...FAILED, available: false, reason: "no activities",
                               within_caps: null, coverage: null })).toBeNull();
  });
});

describe("the tone tokens are literal", () => {
  it("names properties the stylesheets define, never a built name", () => {
    // `shell/cssVars.test.ts` cannot resolve `var(--status-${tone})`, and a custom property nothing
    // defines is ignored in silence.
    expect(TONE_CSS.crit).toBe("var(--status-crit)");
    expect(TONE_CSS.good).toBe("var(--status-good)");
    expect(TONE_CSS[""]).toBe("");
  });
});

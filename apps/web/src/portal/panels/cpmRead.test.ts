import { readFileSync } from "node:fs";
import { resolve } from "node:path";

import { describe, expect, it } from "vitest";

import {
  cpmLine, cpmSeverity, cycleRefs, errors, issuesLine, noDates, refOf, warnings,
  type CpmResult,
} from "./cpmRead";

/** The cyclic response, measured on the live engine from a three-activity loop A→B→C→A.
 *  `project_duration`, `critical_count` and `critical_path` are `blank_result()`'s zeros. */
const CYCLIC: CpmResult = {
  project_duration: 0, activity_count: 3, critical_count: 0, has_cycle: true,
  critical_path: [],
  activities: [
    { id: "a1", ref: "A", name: "Pour slab", duration: 5, es: null, ef: null, total_float: 0, critical: false },
    { id: "a2", ref: "B", name: "Frame walls", duration: 7, es: null, ef: null, total_float: 0, critical: false },
    { id: "a3", ref: "C", name: "Roof", duration: 3, es: null, ef: null, total_float: 0, critical: false },
  ],
  cycle: ["a1", "a2", "a3", "a1"],
  issues: [{ severity: "error", code: "CPM.CIRCULAR_LOGIC",
             message: "Circular logic: a1 -> a2 -> a3 -> a1",
             action: "no dates computed; break the loop and recalculate" }],
};

/** The quieter case, also measured: C cites predecessor "BB" and no such ref exists. The schedule
 *  computes, and is wrong by one dependency. */
const DROPPED: CpmResult = {
  project_duration: 2, activity_count: 3, critical_count: 2, has_cycle: false,
  critical_path: ["A", "B"],
  activities: [
    { id: "a1", ref: "A", name: "Pour slab", duration: 5, es: 0, ef: 5, total_float: 0, critical: true },
    { id: "a2", ref: "B", name: "Frame walls", duration: 7, es: 5, ef: 12, total_float: 0, critical: true },
    { id: "a3", ref: "C", name: "Roof", duration: 3, es: 0, ef: 3, total_float: 9, critical: false },
  ],
  cycle: [],
  issues: [{ severity: "warning", code: "MASSING.PREDECESSOR_UNRESOLVED",
             message: "a3: predecessor 'BB' matches no activity",
             action: "relationship dropped", row_key: "a3", field: "predecessors", raw_value: "BB" }],
};

const CLEAN: CpmResult = {
  project_duration: 15, activity_count: 3, critical_count: 2, has_cycle: false,
  critical_path: ["A", "B"], activities: DROPPED.activities, cycle: [], issues: [],
};

describe("cpmLine", () => {
  it("reports a loop as NO DATES rather than as a zero-day project", () => {
    const line = cpmLine(CYCLIC);
    expect(line).toContain("NO DATES COMPUTED");
    expect(line).toContain("A → B → C → A");
    expect(line).toContain("not available, not zero");
    // the three things the old caption said, none of which were true
    expect(line).not.toContain("cycle broken");
    expect(line).not.toContain("project 0d");
    expect(line).not.toMatch(/0\/3 on the critical path/);
  });

  it("keeps the closing edge, so a cycle does not read as a path", () => {
    expect(cycleRefs(CYCLIC)).toEqual(["A", "B", "C", "A"]);
  });

  it("reports a normal schedule exactly as before", () => {
    expect(cpmLine(CLEAN)).toBe("CPM: project 15d · 2/3 on the critical path");
  });

  it("still reports the headline on a schedule with a dropped relationship", () => {
    // The computation happened; it is the ISSUES line that carries the caveat. Suppressing the
    // headline here would hide a figure the planner needs in order to see it is wrong.
    expect(cpmLine(DROPPED)).toBe("CPM: project 2d · 2/3 on the critical path");
  });

  it("says so when there is nothing to compute", () => {
    expect(cpmLine({ ...CLEAN, activity_count: 0 })).toContain("no activities");
  });
});

describe("the loop's identifiers", () => {
  it("translates engine ids into the refs a planner typed", () => {
    expect(refOf(CYCLIC, "a2")).toBe("B");
  });

  it("falls back to the id when the row carries no ref", () => {
    const noRef: CpmResult = { ...CYCLIC, activities: CYCLIC.activities.map(
      (r) => ({ ...r, ref: null })) };
    expect(cycleRefs(noRef)).toEqual(["a1", "a2", "a3", "a1"]);
  });

  it("falls back to the id when the row is missing entirely", () => {
    expect(refOf({ ...CYCLIC, activities: [] }, "a1")).toBe("a1");
  });
});

describe("noDates", () => {
  it("believes the engine's flag", () => {
    expect(noDates(CYCLIC)).toBe(true);
    expect(noDates(CLEAN)).toBe(false);
  });

  it("also refuses on a cycle list with no flag, since either key reports the same refusal", () => {
    expect(noDates({ ...CLEAN, cycle: ["a1", "a1"] })).toBe(true);
  });

  it("survives a response carrying neither key", () => {
    const bare = { ...CLEAN } as CpmResult;
    delete (bare as { cycle?: string[] }).cycle;
    expect(noDates({ ...bare, has_cycle: false })).toBe(false);
  });
});

describe("issuesLine", () => {
  it("renders the dropped relationship the engine reported and nothing was reading", () => {
    const line = issuesLine(DROPPED);
    expect(line).toContain("1 warning");
    expect(line).toContain("a3: predecessor 'BB' matches no activity");
    expect(line).toContain("relationship dropped");
  });

  it("renders the circular-logic error with the action the engine supplied", () => {
    const line = issuesLine(CYCLIC);
    expect(line).toContain("1 error");
    expect(line).toContain("break the loop and recalculate");
  });

  it("counts errors and warnings separately — the two are not the same news", () => {
    const both: CpmResult = { ...DROPPED, issues: [...CYCLIC.issues!, ...DROPPED.issues!] };
    const line = issuesLine(both)!;
    expect(line).toContain("1 error, 1 warning");
  });

  it("caps the detail and says how much it withheld", () => {
    const many: CpmResult = { ...DROPPED, issues: Array.from({ length: 6 }, (_, i) => ({
      severity: "warning", code: "X", message: `issue ${i}`, action: "dropped" })) };
    const line = issuesLine(many)!;
    expect(line).toContain("6 warnings");
    expect(line).toContain("(+3 more)");
  });

  it("is null when the engine reported nothing, so a clean schedule gets no banner", () => {
    expect(issuesLine(CLEAN)).toBeNull();
    expect(issuesLine({ ...CLEAN, issues: undefined })).toBeNull();
  });

  it("partitions by severity", () => {
    expect(errors(CYCLIC)).toHaveLength(1);
    expect(warnings(CYCLIC)).toHaveLength(0);
    expect(errors(DROPPED)).toHaveLength(0);
    expect(warnings(DROPPED)).toHaveLength(1);
  });
});

describe("cpmSeverity", () => {
  it("is error on a refused schedule, warn on a dropped relationship, none on a clean one", () => {
    expect(cpmSeverity(CYCLIC)).toBe("error");
    expect(cpmSeverity(DROPPED)).toBe("warn");
    expect(cpmSeverity(CLEAN)).toBe("none");
  });

  it("is error on an engine error even when dates were computed", () => {
    expect(cpmSeverity({ ...DROPPED, issues: CYCLIC.issues })).toBe("error");
  });
});

/**
 * The consumer, at source level.
 *
 * The defect was never in a function — it was in two inline template literals in
 * `portal/panels/schedule.ts`, so a reading module with perfect tests and no caller would have left
 * the card saying exactly what it said before. This is the same bargain `test_route_reachability`
 * makes for URL literals, and it has the same limit, written down rather than discovered later:
 * wrapping the render in `if (false)` leaves the call in place and passes. What it does catch is the
 * revert — and the revert is how a reading module becomes decoration.
 */
describe("the schedule panel reads it", () => {
  const panel = readFileSync(resolve(__dirname, "schedule.ts"), "utf8");

  it("renders the headline and the issues line through this module", () => {
    expect(panel).toContain('from "./cpmRead"');
    expect(panel.match(/cpmLine\(c\)/g)?.length,
      "both CPM renderers must go through cpmLine — the second one (the QTO-estimate refresh) said "
      + "even less than the first").toBe(2);
    expect(panel).toContain("issuesLine(c)");
  });

  it("no longer claims the loop was broken, in CODE", () => {
    // `schedule_cpm._cyclic` computes NO dates, so the old caption described the behaviour it
    // replaced. **The first draft of this assertion failed on the comment that records that**, which
    // is the population problem in miniature: a check over a whole file includes the prose
    // explaining the fix, and the choice is to narrow the question or to delete the record. Comment
    // lines are dropped — and the stripper is asserted to have dropped some, because a stripper
    // that removed everything would pass this and every future version of it.
    const code = panel.split("\n").filter((l) => {
      const t = l.trim();
      return !t.startsWith("//") && !t.startsWith("*") && !t.startsWith("/*");
    });
    expect(code.length, "the comment stripper kept every line — it is not stripping")
      .toBeLessThan(panel.split("\n").length);
    expect(code.length, "the comment stripper removed the whole file")
      .toBeGreaterThan(panel.split("\n").length / 2);
    expect(code.join("\n")).not.toContain("cycle broken");
  });
});

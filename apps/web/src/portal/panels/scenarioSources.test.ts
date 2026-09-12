import { describe, expect, it } from "vitest";

import {
  type ScenarioProvenance,
  actionNote, actions, coverageIsWhole, headline, headlineNote, staleness, stalenessNote, summary,
} from "./scenarioSources";

/** A four-driver deal. Small enough that every count in a test is checkable by eye. */
function fixture(over: Partial<ScenarioProvenance> = {}): ScenarioProvenance {
  return {
    scenario_id: "sc1",
    scenario_name: "Base case",
    material_count: 4,
    cited_count: 4,
    uncited_count: 0,
    coverage_pct: 100,
    assumptions: [],
    uncited: [],
    orphaned_sources: [],
    malformed_citation_paths: [],
    malformed_citation_count: 0,
    stale_citation_count: 0,
    current_revision: null,
    basis: "",
    note: "",
    message: null,
    ...over,
  };
}

describe("staleness — the zero that means two different things", () => {
  it("is NOT-CHECKED when no revision was supplied, however clean the count looks", () => {
    // The engine computes `stale` only when `current_revision` is truthy, so with no `?revision=`
    // the count is 0 because nothing was compared. Printing "0 stale" here reports a check that
    // never ran.
    const p = fixture({ stale_citation_count: 0, current_revision: null });
    expect(staleness(p)).toBe("not-checked");
    // The note must DISCLAIM currency, not assert it. A substring check cannot tell a claim from
    // its denial — "says nothing about whether the sources are up to date" contains "up to date" —
    // so assert the disclaimer itself, which was this test's own first mistake.
    expect(stalenessNote("not-checked", p)).toContain("not checked");
    expect(stalenessNote("not-checked", p)).toContain("says nothing about");
  });

  it("is ALL-CURRENT only when a revision WAS supplied and nothing differed", () => {
    const p = fixture({ stale_citation_count: 0, current_revision: "rev-7" });
    expect(staleness(p)).toBe("all-current");
    expect(stalenessNote("all-current", p)).toContain("rev-7");
  });

  it("is SOME-STALE when citations name another revision, and says which is current", () => {
    const p = fixture({ stale_citation_count: 3, current_revision: "rev-7" });
    expect(staleness(p)).toBe("some-superseded");
    expect(stalenessNote("some-superseded", p)).toContain("3 citation(s)");
    expect(stalenessNote("some-superseded", p)).toContain("rev-7");
    expect(stalenessNote("some-superseded", p)).toContain("superseded");
  });

  it("the two zeroes are distinguishable — which is the whole point", () => {
    const unchecked = fixture({ stale_citation_count: 0, current_revision: null });
    const checked = fixture({ stale_citation_count: 0, current_revision: "rev-7" });
    expect(unchecked.stale_citation_count).toBe(checked.stale_citation_count);   // same number
    expect(staleness(unchecked)).not.toBe(staleness(checked));                   // different meaning
  });
});

describe("100% coverage is not the same as sourced", () => {
  it("refuses to call a fully-cited scenario whole when every citation is stale", () => {
    // `STATUS_CITED` is assigned whenever ANY readable citation exists, regardless of revision. So
    // coverage_pct can read 100 while every source is superseded. Coverage and currency are
    // different axes and the headline carries only one.
    const p = fixture({ coverage_pct: 100, cited_count: 4, uncited_count: 0,
      stale_citation_count: 4, current_revision: "rev-9" });
    expect(p.coverage_pct).toBe(100);
    expect(coverageIsWhole(p)).toBe(false);
    expect(headline(p)).toBe("superseded-sources");
  });

  it("refuses to call it whole when currency was never checked", () => {
    const p = fixture({ coverage_pct: 100, current_revision: null });
    expect(coverageIsWhole(p)).toBe(false);
    expect(headline(p)).toBe("unchecked");
    expect(headlineNote("unchecked", p)).toContain("NOT checked");
  });

  it("refuses when a recorded source is unreadable, even at 100% coverage", () => {
    const p = fixture({ coverage_pct: 100, current_revision: "rev-9",
      malformed_citation_count: 1, malformed_citation_paths: ["exit.exit_cap"] });
    expect(coverageIsWhole(p)).toBe(false);
    expect(headline(p)).toBe("unreadable-sources");
  });

  it("calls it whole only when sourced, readable AND current", () => {
    const p = fixture({ coverage_pct: 100, current_revision: "rev-9", stale_citation_count: 0 });
    expect(coverageIsWhole(p)).toBe(true);
    expect(headline(p)).toBe("whole");
    expect(headlineNote("whole", p)).toContain("current revision");
  });
});

describe("headline order — what a reader must be told first", () => {
  it("puts gaps ahead of staleness: a missing source is a bigger hole than an old one", () => {
    const p = fixture({ uncited_count: 2, cited_count: 2, coverage_pct: 50,
      uncited: ["exit.exit_cap", "debt.rate"], stale_citation_count: 5, current_revision: "rev-9" });
    expect(headline(p)).toBe("gaps");
    expect(headlineNote("gaps", p)).toContain("2 of 4");
    // ...and the note refuses to call an absent source a wrong value.
    expect(headlineNote("gaps", p)).toContain("absence of provenance");
  });

  it("puts unreadable sources ahead of staleness, and names them a DIFFERENT fix", () => {
    const p = fixture({ current_revision: "rev-9", stale_citation_count: 2,
      malformed_citation_count: 1, malformed_citation_paths: ["debt.rate"] });
    expect(headline(p)).toBe("unreadable-sources");
    expect(headlineNote("unreadable-sources", p)).toContain("different fix");
  });

  it("a scenario with NO material assumptions is not 'whole' — vacuous truth is not provenance", () => {
    // Found in review. Every conjunct held vacuously: nothing uncited, nothing malformed, and a
    // revision supplied with zero stale — so `coverageIsWhole` said TRUE about a scenario carrying
    // nothing to be whole ABOUT, while `headline()` said "nothing-to-trace" off the same response.
    // `summary()` then handed a reader both at once.
    //
    // This is the defect this whole module exists to prevent, in the module itself: a verdict
    // stronger than the evidence under it. "No assumption lacks a source" is true of a deal with no
    // assumptions, and it is the one case where it means nothing.
    const p = fixture({ material_count: 0, cited_count: 0, uncited_count: 0, coverage_pct: 0,
      current_revision: "rev-9", stale_citation_count: 0 });
    expect(coverageIsWhole(p)).toBe(false);
    expect(headline(p)).toBe("nothing-to-trace");
    // ...and the two agree, which is the property that was broken rather than either alone.
    expect(summary(p).whole).toBe(false);
    expect(summary(p).headline).toBe("nothing-to-trace");
  });

  it("says there is nothing to trace rather than reporting 0% coverage", () => {
    const p = fixture({ material_count: 0, cited_count: 0, coverage_pct: 0 });
    expect(headline(p)).toBe("nothing-to-trace");
    expect(headlineNote("nothing-to-trace", p)).toContain("no material assumptions");
  });
});

describe("actions — the named list, which is the part that gets fixed", () => {
  it("lists uncited paths first, then unreadable, then orphans", () => {
    const p = fixture({ uncited: ["exit.exit_cap"], uncited_count: 1, cited_count: 3,
      malformed_citation_paths: ["debt.rate"], malformed_citation_count: 1,
      orphaned_sources: ["operations.rent_typo"] });
    expect(actions(p).map((a) => [a.path, a.kind])).toEqual([
      ["exit.exit_cap", "uncited"],
      ["debt.rate", "malformed"],
      ["operations.rent_typo", "orphaned"],
    ]);
  });

  it("lists a path that is BOTH uncited and malformed ONCE, flagged", () => {
    // The engine allows both — a recorded entry that is not a readable citation counts as absent AND
    // is named as malformed. The reader needs to know the record is broken as well as missing, but
    // seeing the same path twice in an action list reads as two separate problems.
    const p = fixture({ uncited: ["exit.exit_cap"], uncited_count: 1, cited_count: 3,
      malformed_citation_paths: ["exit.exit_cap"], malformed_citation_count: 1 });
    const rows = actions(p);
    expect(rows).toHaveLength(1);
    expect(rows[0]).toEqual({ path: "exit.exit_cap", kind: "uncited", alsoMalformed: true });
  });

  it("is empty on a scenario with nothing to fix", () => {
    expect(actions(fixture())).toEqual([]);
  });

  it("gives each kind an instruction, not a label", () => {
    expect(actionNote("uncited")).toContain("find one");
    expect(actionNote("malformed")).toContain("fix the record");
    expect(actionNote("orphaned")).toContain("renamed");
  });
});

describe("summary", () => {
  it("carries the second axis so the percentage cannot travel alone", () => {
    const p = fixture({ coverage_pct: 100, current_revision: null });
    const s = summary(p);
    expect(s.coverage).toBe(100);
    expect(s.staleness).toBe("not-checked");   // attached to the same object as the 100
    expect(s.whole).toBe(false);
  });

  it("counts every action a reader has to take", () => {
    const p = fixture({ uncited: ["a.b", "c.d"], uncited_count: 2, cited_count: 2, coverage_pct: 50,
      malformed_citation_paths: ["e.f"], malformed_citation_count: 1,
      orphaned_sources: ["g.h"] });
    expect(summary(p).actionCount).toBe(4);
  });
});

import { describe, expect, it } from "vitest";

import type { SequenceClashResult } from "../../api/schedule";
import {
  sequenceCoverage, sequenceHeadline, sequenceTone, supportCoverageNote,
  unscheduledGuids, unscheduledPageNote, unscheduledRows,
} from "./sequenceClashRead";

/** Base response shaped on what `sequence_clash.analyze` actually returns — every key present, so
 *  a test that needs one coverage gap open sets exactly that one. */
function res(over: Partial<SequenceClashResult> = {}): SequenceClashResult {
  return {
    analyzed: 1, skipped: [], skipped_count: 0, locations: 1,
    findings: [], finding_count: 0,
    support_checked: true, support_pairs: 0, support_evaluated: 0,
    support_findings: [], support_finding_count: 0,
    support_unscheduled: [], support_unscheduled_count: 0,
    support_unscheduled_truncated: false,
    clean: true, note: "n", not_covered: "nc", clean_scope: "cs", bound_activities: 1,
    ...over,
  };
}

/** MEASURED, not invented. From `aec_api.sequence_clash.analyze` with one dated activity binding
 *  `BEAM` and two directed pairs, neither of which has a dated support:
 *
 *      analyzed 1 · skipped_count 0 · finding_count 0 · support_pairs 2 ·
 *      support_evaluated 0 · support_finding_count 0 · support_unscheduled_count 2 · clean true
 *
 *  This is the shipped defect in one object: the support half ruled on NOTHING and `clean` is true. */
const VACUOUS = res({
  support_pairs: 2, support_evaluated: 0, support_unscheduled_count: 2,
  support_unscheduled: [
    { support: "COL", supported: "BEAM", grade: "structural", missing: ["support"] },
    { support: "SLAB", supported: "DECK", grade: "assembly", missing: ["support", "supported"] },
  ],
});

describe("sequenceCoverage", () => {
  it("keeps the two populations apart instead of blending them", () => {
    const c = sequenceCoverage(VACUOUS);
    expect(c).toMatchObject({ analyzed: 1, skipped: 0, pairs: 2, evaluated: 0, unscheduled: 2 });
    expect(c.supportVacuous).toBe(true);
    expect(c.complete).toBe(false);
  });

  it("is NOT vacuous when there were no pairs to date in the first place", () => {
    // A model with no licensed structural relations asked the support question and got an empty
    // denominator. That is a complete answer over nothing, not an unasked question — conflating
    // them would paint every project without a structural frame as half-unchecked.
    const c = sequenceCoverage(res({ support_pairs: 0, support_evaluated: 0 }));
    expect(c.supportVacuous).toBe(false);
    expect(c.complete).toBe(true);
  });

  it("is complete only when BOTH gaps are shut", () => {
    expect(sequenceCoverage(res({ support_pairs: 3, support_evaluated: 3 })).complete).toBe(true);
    expect(sequenceCoverage(res({ skipped_count: 1 })).complete).toBe(false);
    expect(sequenceCoverage(VACUOUS).complete).toBe(false);
  });
});

describe("sequenceHeadline", () => {
  it("never prints a bare 'clean' while the support half dated nothing", () => {
    const h = sequenceHeadline(VACUOUS);
    expect(h).toBe("clean of 1 · support 0/2 dated");
    expect(h).not.toBe("clean");
  });

  it("prints a bare 'clean' when both populations are complete", () => {
    expect(sequenceHeadline(res({ support_pairs: 2, support_evaluated: 2 }))).toBe("clean");
    expect(sequenceHeadline(res())).toBe("clean");
  });

  it("carries the skipped gap and the support gap together", () => {
    expect(sequenceHeadline(res({
      analyzed: 12, skipped_count: 3, support_pairs: 8, support_evaluated: 5,
      support_unscheduled_count: 3,
    }))).toBe("clean of 12 · 3 not checked · support 5/8 dated");
  });

  it("leads with the findings — a real contention outranks a coverage gap", () => {
    expect(sequenceHeadline(res({ finding_count: 1, clean: false }))).toBe("1 sequence clash");
    expect(sequenceHeadline(res({ finding_count: 1, support_finding_count: 2, clean: false })))
      .toBe("3 sequence clashes");
  });

  it("says 'checked' rather than clean when the engine refused the verdict", () => {
    // `clean` is false on an empty or wholly unreadable schedule — the engine requires `usable`.
    expect(sequenceHeadline(res({ analyzed: 0, clean: false }))).toBe("checked");
  });
});

describe("sequenceTone", () => {
  it("does NOT paint green over a support check that dated nothing", () => {
    // As shipped: `n ? "bad" : (clean && !skipped_count ? "ok" : "")` → "ok" on this exact object.
    expect(sequenceTone(VACUOUS)).toBe("warn");
  });

  it("is ok only when both populations are complete", () => {
    expect(sequenceTone(res({ support_pairs: 2, support_evaluated: 2 }))).toBe("ok");
    expect(sequenceTone(res())).toBe("ok");
  });

  it("is neutral — not green and not a warning — on a partially dated support check", () => {
    // Some pairs ruled on, some not: there IS a verdict, over a named subset. A warning colour
    // here would cry wolf on every project, which is how a colour stops being read.
    expect(sequenceTone(res({
      support_pairs: 8, support_evaluated: 5, support_unscheduled_count: 3,
    }))).toBe("");
    expect(sequenceTone(res({ skipped_count: 1 }))).toBe("");
  });

  it("is bad whenever there is a finding, whatever the coverage", () => {
    expect(sequenceTone(res({ finding_count: 1, clean: false }))).toBe("bad");
    expect(sequenceTone({ ...VACUOUS, support_finding_count: 1, clean: false })).toBe("bad");
  });
});

describe("supportCoverageNote", () => {
  it("says the support question went entirely unasked, and groups by the missing end", () => {
    expect(supportCoverageNote(VACUOUS)).toBe(
      "NONE of the 2 directed support pair(s) could be dated, so install-before-support has no "
      + "verdict on this project: 1 × no dated activity on the support · 1 × no dated activity on "
      + "the support + supported. Bind an activity to both ends to bring a pair into the check.");
  });

  it("names the subset when some pairs WERE dated", () => {
    const n = supportCoverageNote(res({
      support_pairs: 8, support_evaluated: 6, support_unscheduled_count: 2,
      support_unscheduled: [
        { support: "A", supported: "B", grade: "structural", missing: ["supported"] },
        { support: "C", supported: "D", grade: "structural", missing: ["supported"] },
      ],
    }));
    expect(n).toContain("2 of 8 directed support pair(s) could not be dated");
    expect(n).toContain("2 × no dated activity on the supported");
    expect(n).not.toContain("NONE");
  });

  it("declares the shortfall rather than rescaling the denominator when the server capped", () => {
    // The count is exact and the list is capped at 200 by the engine — so the REASONS cover fewer
    // pairs than the count, and saying so is the difference between a page and a total.
    const n = supportCoverageNote(res({
      support_pairs: 500, support_evaluated: 0, support_unscheduled_count: 500,
      support_unscheduled_truncated: true,
      support_unscheduled: Array.from({ length: 200 }, (_, i) => ({
        support: `C${i}`, supported: "BEAM", grade: "structural", missing: ["support"],
      })),
    }));
    expect(n).toContain("NONE of the 500 directed support pair(s)");
    expect(n).toContain("reasons cover the 200 pair(s) returned in this response");
  });

  it("is null when every pair was dated", () => {
    expect(supportCoverageNote(res({ support_pairs: 4, support_evaluated: 4 }))).toBeNull();
    expect(supportCoverageNote(res())).toBeNull();
  });

  it("survives a pair the engine sent with no missing end named", () => {
    expect(supportCoverageNote(res({
      support_pairs: 1, support_evaluated: 0, support_unscheduled_count: 1,
      support_unscheduled: [{ support: "A", supported: "B", grade: "structural", missing: [] }],
    }))).toContain("1 × no dated activity on the unstated");
  });
});

describe("unscheduledRows", () => {
  it("marks WHICH end is undated, which is the fix the row is for", () => {
    expect(unscheduledRows(VACUOUS)).toEqual([
      { k: "structural", v: "BEAM supported by COL (undated)" },
      { k: "assembly", v: "DECK (undated) supported by SLAB (undated)" },
    ]);
  });

  it("caps the rows", () => {
    const many = res({
      support_pairs: 10, support_unscheduled_count: 10,
      support_unscheduled: Array.from({ length: 10 }, (_, i) => ({
        support: `S${i}`, supported: `T${i}`, grade: "structural", missing: ["support"],
      })),
    });
    expect(unscheduledRows(many, 3)).toHaveLength(3);
  });
});

describe("unscheduledPageNote", () => {
  it("counts against the exact total, not the length of the page it was handed", () => {
    expect(unscheduledPageNote(res({
      support_unscheduled_count: 500, support_unscheduled_truncated: true,
      support_unscheduled: Array.from({ length: 200 }, (_, i) => ({
        support: `C${i}`, supported: "BEAM", grade: "structural", missing: ["support"],
      })),
    }), 40)).toBe("Showing 40 of 500 undated support pair(s). The server returned the first 200.");
  });

  it("does not mention a server cap that did not bite", () => {
    expect(unscheduledPageNote(res({
      support_unscheduled_count: 60,
      support_unscheduled: Array.from({ length: 60 }, (_, i) => ({
        support: `C${i}`, supported: "BEAM", grade: "structural", missing: ["support"],
      })),
    }), 40)).toBe("Showing 40 of 60 undated support pair(s).");
  });

  it("is null when the table shows everything", () => {
    expect(unscheduledPageNote(VACUOUS)).toBeNull();
    expect(unscheduledPageNote(res())).toBeNull();
  });
});

describe("unscheduledGuids", () => {
  it("takes both ends and de-duplicates", () => {
    expect(unscheduledGuids(VACUOUS)).toEqual(["COL", "BEAM", "SLAB", "DECK"]);
    expect(unscheduledGuids(res({
      support_unscheduled: [
        { support: "COL", supported: "BEAM", grade: "structural", missing: ["support"] },
        { support: "COL", supported: "DECK", grade: "structural", missing: ["support"] },
      ],
    }))).toEqual(["COL", "BEAM", "DECK"]);
  });

  it("is empty when nothing is undated", () => {
    expect(unscheduledGuids(res())).toEqual([]);
  });
});

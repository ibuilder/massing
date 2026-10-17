import { describe, expect, it } from "vitest";

import type { EstimateRead } from "./costEstimateRead";
import {
  deadRulesNote, estimateCoverage, estimateCoverageNote, estimateHeadline, estimateTone, gapGuids,
  gapPageNote, gapRows, linePageNote, lineRows, provenanceNote, rulesPricedNothing, sovBillable,
  sovBillableNotes, sovDriftNote, sovHeadline, sovItemRows, sovPageNote, sovTone, unchosenRatesNote,
} from "./costEstimateRead";
import type { CostSov } from "../../api/cost";

/** MEASURED, not invented. `aec_api.fived.estimate` over four elements —
 *  `{W1: IfcWall, W2: IfcWall, D1: IfcDoor, B1: IfcBeam}` — with two starter rules (walls per area
 *  at $28, doors per count at $1,450), `W1` carrying a DECLARED area of 400 and `W2` carrying none:
 *
 *      line_count 2 · total 12650 · priced_count 3 · coverage_pct 75 · complete false
 *      unpriced ["B1"] · missing_quantity [{W2, "03 30 00", area}] · no_rate []
 *      computed_quantity_lines 1 · computed_quantity_amount 1450 · vintage null
 *
 *  Three facts in that output are the reason this module exists. `priced_count` is 3 while only 2
 *  lines priced — `W2` was MATCHED and then dropped for want of a quantity. `complete` is false and
 *  says nothing about the rates. And `computed_quantity_lines` is 1 for the DOOR, whose quantity was
 *  assumed rather than measured. */
const MEASURED: EstimateRead = {
  lines: [
    { code: "03 30 00", description: "Walls, per ft² (PLACEHOLDER rate — edit me)", basis: "area",
      unit_cost: 28, quantity: 400, amount: 11200, guids: ["W1"], rule: 0,
      quantity_source: "declared", rate_source: "quoted" },
    { code: "08 11 00", description: "Doors, each (PLACEHOLDER rate — edit me)", basis: "count",
      unit_cost: 1450, quantity: 1, amount: 1450, guids: ["D1"], rule: 1,
      quantity_source: "unknown", rate_source: "quoted" },
  ],
  line_count: 2,
  by_element: {
    W1: { code: "03 30 00", basis: "area", quantity: 400, unit_cost: 28, amount: 11200,
          rate_source: "quoted", quantity_source: "declared" },
    D1: { code: "08 11 00", basis: "count", quantity: 1, unit_cost: 1450, amount: 1450,
          rate_source: "quoted", quantity_source: "unknown" },
  },
  total: 12650,
  priced_count: 3,
  unpriced: ["B1"],
  unpriced_count: 1,
  missing_quantity: [{ guid: "W2", code: "03 30 00", basis: "area" }],
  missing_quantity_count: 1,
  no_rate: [],
  no_rate_count: 0,
  vintage_rate_lines: 0,
  vintage: null,
  computed_quantity_lines: 1,
  computed_quantity_amount: 1450,
  coverage_pct: 75,
  complete: false,
  note: "`total` covers the priced lines only. With unpriced elements or missing quantities it is a "
    + "floor, not an estimate — `complete` says which.",
  rules_seeded: true,
  rule_count: 5,
};

/** The same estimate with every gap shut and the firm's own rates saved — the only state that is
 *  allowed to read as a finished number. */
const CLEAN: EstimateRead = {
  ...MEASURED,
  unpriced: [], unpriced_count: 0,
  missing_quantity: [], missing_quantity_count: 0,
  coverage_pct: 100, complete: true,
  computed_quantity_lines: 0, computed_quantity_amount: 0,
  rules_seeded: false, rule_count: 5,
};

describe("estimateCoverage", () => {
  it("keeps the three gap populations apart and names the matched count as matched", () => {
    expect(estimateCoverage(MEASURED)).toMatchObject({
      matched: 3, unpriced: 1, missingQuantity: 1, noRate: 0, coveragePct: 75,
      modelComplete: false, ratesUnchosen: true, vacuous: false,
    });
  });

  it("separates the model axis from the rate axis", () => {
    // A complete estimate at placeholder rates: the engine's axis is shut and the other is open.
    const seededComplete = { ...CLEAN, rules_seeded: true };
    expect(estimateCoverage(seededComplete)).toMatchObject({
      modelComplete: true, ratesUnchosen: true,
    });
    expect(estimateCoverage(CLEAN)).toMatchObject({ modelComplete: true, ratesUnchosen: false });
  });

  it("treats an absent rules_seeded as authored rather than seeded", () => {
    // A server that does not send the flag has made no claim; defaulting to "seeded" would caveat
    // every estimate for ever and the caveat would stop being read.
    const { rules_seeded: _omitted, ...noFlag } = CLEAN;
    expect(estimateCoverage(noFlag as EstimateRead).ratesUnchosen).toBe(false);
  });
});

describe("estimateHeadline", () => {
  it("never prints a bare total while the rates are the starter set's", () => {
    expect(estimateHeadline(MEASURED)).toBe("$12,650 at PLACEHOLDER rates");
  });

  it("says PLACEHOLDER even when the model side is complete", () => {
    // The dangerous case: every element matched, every quantity present, every rate invented.
    expect(estimateHeadline({ ...CLEAN, rules_seeded: true })).toBe("$12,650 at PLACEHOLDER rates");
  });

  it("gives the coverage when the rates are authored and the model is not covered", () => {
    expect(estimateHeadline({ ...MEASURED, rules_seeded: false }))
      .toBe("$12,650 · 75% of the model matched");
  });

  it("prints a plain total only when both axes are shut", () => {
    expect(estimateHeadline(CLEAN)).toBe("$12,650 · complete");
  });

  it("reports nothing priced rather than a total of zero", () => {
    expect(estimateHeadline({ ...MEASURED, lines: [], line_count: 0, total: 0 }))
      .toBe("nothing priced");
  });
});

describe("estimateTone", () => {
  it("is never green on placeholder rates, however complete the coverage", () => {
    expect(estimateTone({ ...CLEAN, rules_seeded: true })).toBe("warn");
    expect(estimateTone(MEASURED)).toBe("warn");
  });

  it("is green only with authored rates and full coverage", () => {
    expect(estimateTone(CLEAN)).toBe("ok");
  });

  it("is neutral on a partial estimate at authored rates", () => {
    expect(estimateTone({ ...MEASURED, rules_seeded: false })).toBe("");
  });

  it("is bad when nothing priced", () => {
    expect(estimateTone({ ...CLEAN, lines: [], line_count: 0, total: 0 })).toBe("bad");
  });
});

describe("unchosenRatesNote", () => {
  it("says the total is arithmetic rather than an estimate", () => {
    expect(unchosenRatesNote(MEASURED)).toBe(
      "These 5 rule(s) are the STARTER SET — placeholder rates nobody on this project has chosen. "
      + "$12,650 is arithmetic, not an estimate. Edit and save the rules to make this number yours.");
  });

  it("is null once a set has been saved", () => {
    expect(unchosenRatesNote(CLEAN)).toBeNull();
  });
});

describe("estimateCoverageNote", () => {
  it("names each gap with the fix it needs, and appends the engine's own note verbatim", () => {
    const n = estimateCoverageNote(MEASURED)!;
    expect(n).toContain("$12,650 is a FLOOR over the 75% of the model a rule matched");
    expect(n).toContain("1 matched by no rule — add a selector");
    expect(n).toContain("1 priced on a basis the model has no quantity for — measure it");
    expect(n).not.toContain("vintage` rule with no rate");       // no_rate_count is 0
    expect(n).toContain(MEASURED.note);
  });

  it("names the cost-database gap as its own third state", () => {
    const n = estimateCoverageNote({
      ...MEASURED, no_rate: [{ guid: "C1", code: "05 12 00", rule: 2, ifc_class: "IfcColumn" }],
      no_rate_count: 1,
    })!;
    expect(n).toContain("1 matched by a `vintage` rule with no rate in the cost database");
    expect(n).toContain("pin a cost vintage");
  });

  it("says a total over nothing is a total over nothing", () => {
    expect(estimateCoverageNote({ ...MEASURED, lines: [], line_count: 0, total: 0 }))
      .toContain("No element was priced at all, so $0 is a total over nothing");
  });

  it("is null when the model side is complete", () => {
    expect(estimateCoverageNote(CLEAN)).toBeNull();
  });
});

describe("provenanceNote", () => {
  it("says NOT DECLARED rather than measured, because the predicate is not declared", () => {
    const n = provenanceNote(MEASURED)!;
    expect(n).toBe("1 line(s) worth $1,450 rest on quantities the model did NOT declare — "
      + "measured, overridden or assumed.");
    expect(n).not.toContain("MEASURED rather than");
  });

  it("names the cost database the vintage lines came from", () => {
    expect(provenanceNote({
      ...CLEAN, vintage_rate_lines: 3,
      vintage: { year: 2026, region: "Denver CO", escalation_pct: 4.2 },
    })).toBe("3 line(s) priced from the pinned cost database (2026 · Denver CO, escalated 4.2%).");
  });

  it("still names the vintage lines when the metadata is bare", () => {
    expect(provenanceNote({ ...CLEAN, vintage_rate_lines: 2, vintage: {} }))
      .toBe("2 line(s) priced from the pinned cost database.");
  });

  it("is null when every line is declared and quoted", () => {
    expect(provenanceNote(CLEAN)).toBeNull();
  });
});

describe("lineRows / linePageNote", () => {
  it("carries the arithmetic and both provenances on every row", () => {
    expect(lineRows(MEASURED)).toEqual([
      { k: "03 30 00 — Walls, per ft² (PLACEHOLDER rate — edit me)",
        v: "$11,200 · 400 area × $28 (declared qty, quoted rate)" },
      { k: "08 11 00 — Doors, each (PLACEHOLDER rate — edit me)",
        v: "$1,450 · 1 count × $1450 (unknown qty, quoted rate)" },
    ]);
  });

  it("counts the page against line_count, not the array", () => {
    expect(linePageNote(MEASURED, 1)).toBe("Showing the 1 largest of 2 line(s) — ordered by amount.");
    expect(linePageNote(MEASURED)).toBeNull();
  });
});

describe("gapRows / gapPageNote / gapGuids", () => {
  it("labels each row with which of the three gaps it is in", () => {
    expect(gapRows({
      ...MEASURED, no_rate: [{ guid: "C1", code: "05 12 00", rule: 2, ifc_class: "IfcColumn" }],
      no_rate_count: 1,
    })).toEqual([
      { k: "no rule matched", v: "B1" },
      { k: "no quantity", v: "W2 · 03 30 00 · needs area" },
      { k: "no rate in the cost database", v: "C1 · 05 12 00 · IfcColumn" },
    ]);
  });

  it("declares the server's cap as well as the table's", () => {
    // `fived.bind` caps `unpriced` at 5,000 with the count exact, so the table can be a page of a
    // page and saying so is the difference between the two claims.
    const many: EstimateRead = {
      ...MEASURED,
      unpriced: Array.from({ length: 5000 }, (_, i) => `G${i}`),
      unpriced_count: 7200,
    };
    expect(gapPageNote(many, 40))
      .toBe("Showing 40 of 7201 element(s) outside the total. The server returned 5001 of them.");
    expect(gapPageNote(MEASURED, 40)).toBeNull();
  });

  it("takes every GlobalId across the three shapes", () => {
    expect(gapGuids({
      ...MEASURED, no_rate: [{ guid: "C1", code: "05 12 00", rule: 2, ifc_class: "IfcColumn" }],
    })).toEqual(["B1", "W2", "C1"]);
  });
});

/** MEASURED. The same route on a project with a source IFC and NO uploaded property index:
 *  `total: 0 · coverage_pct: 0 · priced_count: 0 · unpriced_count: 0 · no_rate_count: 0 ·
 *  complete: false · rules_seeded: true · rule_count: 5`. Pinned in
 *  `services/api/test_cost_rules.py`. */
const NO_INDEX: EstimateRead = {
  ...MEASURED,
  lines: [], line_count: 0, by_element: {}, total: 0,
  priced_count: 0, unpriced: [], unpriced_count: 0,
  missing_quantity: [], missing_quantity_count: 0,
  no_rate: [], no_rate_count: 0,
  computed_quantity_lines: 0, computed_quantity_amount: 0,
  coverage_pct: 0, complete: false,
};

describe("noModelIndex", () => {
  it("tells an unindexed model apart from a rule set that matched nothing", () => {
    expect(estimateCoverage(NO_INDEX).noModelIndex).toBe(true);
    // The distinguishing number is `unpriced_count`: `unpriced` is derived over the index, so an
    // index with elements and no matches reports them.
    expect(estimateCoverage({ ...NO_INDEX, unpriced: ["B1"], unpriced_count: 1 }).noModelIndex)
      .toBe(false);
  });

  it("is false when there are no rules to match with — that is a different absence", () => {
    expect(estimateCoverage({ ...NO_INDEX, rule_count: 0 }).noModelIndex).toBe(false);
    const { rule_count: _omitted, ...noCount } = NO_INDEX;
    expect(estimateCoverage(noCount as EstimateRead).noModelIndex).toBe(false);
  });

  it("says so in the headline and names the fix in the note", () => {
    expect(estimateHeadline(NO_INDEX)).toBe("the model is not indexed");
    const n = estimateCoverageNote(NO_INDEX)!;
    expect(n).toContain("uploaded PROPERTY INDEX, not its source IFC");
    expect(n).toContain("5 rule(s) will have something to match");
    expect(n).not.toContain("total over nothing");
  });

  it("still reads as a total over nothing when the index HAS elements and nothing matched", () => {
    expect(estimateCoverageNote({ ...NO_INDEX, unpriced: ["B1"], unpriced_count: 1 })!)
      .toContain("No element was priced at all");
  });
});

describe("rulesPricedNothing / deadRulesNote", () => {
  it("names the rules that produced no line", () => {
    // MEASURED's two lines carry rule 0 and rule 1; the starter set has five rules.
    expect(rulesPricedNothing(MEASURED)).toEqual([
      { index: 2, reason: "priced nothing" },
      { index: 3, reason: "priced nothing" },
      { index: 4, reason: "priced nothing" },
    ]);
  });

  it("separates a dud selector from a gap in the cost database", () => {
    // `no_rate` carries the RULE index, so the one case the response can explain is explained —
    // and telling a user their selector is wrong when the cost DB is the gap is a message that
    // gets acted on.
    expect(rulesPricedNothing({
      ...MEASURED, rule_count: 3,
      no_rate: [{ guid: "C1", code: "05 12 00", rule: 2, ifc_class: "IfcColumn" }],
      no_rate_count: 1,
    })).toEqual([{ index: 2, reason: "no rate in the cost database" }]);
  });

  it("is empty when every rule earned a line", () => {
    expect(rulesPricedNothing({ ...MEASURED, rule_count: 2 })).toEqual([]);
    expect(deadRulesNote({ ...MEASURED, rule_count: 2 })).toBeNull();
    expect(rulesPricedNothing({ ...MEASURED, rule_count: 0 })).toEqual([]);
  });

  it("explains why a save could not have caught it", () => {
    const n = deadRulesNote(MEASURED)!;
    expect(n).toContain("3 of 5 rule(s) put nothing in this estimate");
    expect(n).toContain("rule(s) 3, 4, 5 — priced nothing");       // 1-based for the reader
    expect(n).toContain("only checked for being well-formed");
  });
});

/** MEASURED from `aec_api.sov_build.from_estimate` through `POST /cost/sov` with `markup_pct: 10`
 *  over the three-rule set in `services/api/test_cost_rules.py`:
 *  `covers_whole_model: true · at_cost: false · reconciles: true · reconciles_by_element: true ·
 *  duplicate_guids: [] · truncated: 0`. */
const SOV: CostSov = {
  items: [
    { item_no: "0001", description: "Walls", cost_code: "03 30 00", scheduled_value: 20020,
      estimate_amount: 18200, markup_amount: 1820, merged_lines: 1, guids: ["W1", "W2"],
      element_count: 2, quantity_source: "override", rate_source: "quoted", basis: "area" },
    { item_no: "0002", description: "Doors", cost_code: "08 11 00", scheduled_value: 1595,
      estimate_amount: 1450, markup_amount: 145, merged_lines: 1, guids: ["D1"],
      element_count: 1, quantity_source: "unknown", rate_source: "quoted", basis: "count" },
  ],
  item_count: 2, grouping: "code", markup_pct: 10, at_cost: false,
  estimate_lines: 2, estimate_total: 19650, sov_total: 21615, residual_applied: 0,
  reconciles: true, reconciles_by_element: true, element_total: 19650,
  duplicate_guids: [], excluded: [], covers_whole_model: true, truncated: 0,
  note: "`reconciles` proves the regrouping lost no money, NOT that the estimate was right.",
};

describe("sovBillable / sovHeadline / sovTone", () => {
  it("reads clean on a reconciled, fully-scoped, marked-up schedule", () => {
    expect(sovBillable(SOV)).toMatchObject({
      coversScope: true, atCost: false, reconciles: true, byElement: true,
      duplicates: 0, truncated: 0, clean: true,
    });
    expect(sovHeadline(SOV)).toBe("$21,615 over 2 item(s) incl. 10% markup");
    expect(sovTone(SOV)).toBe("ok");
  });

  it("says AT COST rather than nothing when no markup was supplied", () => {
    const atCost: CostSov = { ...SOV, markup_pct: 0, at_cost: true, sov_total: 19650,
                              items: SOV.items.map((i) => ({ ...i, markup_amount: 0 })) };
    expect(sovHeadline(atCost)).toBe("$19,650 over 2 item(s) at cost (NO fee)");
    // Neutral, not green: an SOV at cost is correct on cost-plus and an under-bill on lump sum, and
    // the screen cannot know which contract this is.
    expect(sovTone(atCost)).toBe("");
    expect(sovBillableNotes(atCost).some((n) => n.startsWith("AT COST"))).toBe(true);
  });

  it("calls partial scope PARTIAL SCOPE and lists what is outside it", () => {
    const partial: CostSov = { ...SOV, covers_whole_model: false,
      excluded: [{ reason: "unpriced", count: 4, guids: ["a", "b", "c", "d"] },
                 { reason: "missing quantity", count: 1, guids: ["e"] }] };
    expect(sovHeadline(partial)).toContain("PARTIAL SCOPE");
    expect(sovTone(partial)).toBe("warn");
    const n = sovBillableNotes(partial).find((x) => x.startsWith("PARTIAL SCOPE"))!;
    expect(n).toContain("4 unpriced · 1 missing quantity");
    expect(n).toContain("the job is bigger than the total");
  });

  it("is RED on an arithmetic failure, which outranks partial scope", () => {
    expect(sovTone({ ...SOV, reconciles: false })).toBe("bad");
    expect(sovTone({ ...SOV, reconciles_by_element: false })).toBe("bad");
    expect(sovTone({ ...SOV, duplicate_guids: ["W1"] })).toBe("bad");
    expect(sovHeadline({ ...SOV, reconciles: false })).toContain("DOES NOT RECONCILE");
  });

  it("names a double-billed element, which should be impossible", () => {
    const n = sovBillableNotes({ ...SOV, duplicate_guids: ["W1", "D1"] })
      .find((x) => x.includes("BILLED TWICE"))!;
    expect(n).toContain("2 GlobalId(s)");
    expect(n).toContain("W1, D1");
  });

  it("reports the rounding placed on the largest item, and the server's cap", () => {
    const notes = sovBillableNotes({ ...SOV, residual_applied: 0.03, truncated: 7 });
    expect(notes.some((n) => n.includes("$0 of rounding"))).toBe(true);
    expect(notes.some((n) => n.includes("7 further item(s) were dropped"))).toBe(true);
  });

  it("has nothing to say about a clean schedule with a fee", () => {
    expect(sovBillableNotes(SOV)).toEqual([]);
  });
});

describe("sovDriftNote", () => {
  it("is null while the schedule matches the estimate on screen", () => {
    expect(sovDriftNote(SOV, 19650)).toBeNull();
  });

  it("refuses to let a stale estimate be billed from", () => {
    const n = sovDriftNote(SOV, 12650)!;
    expect(n).toContain("totals $19,650, not the $12,650 shown a moment ago");
    expect(n).toContain("Re-run the estimate before billing");
  });
});

describe("sovItemRows / sovPageNote", () => {
  it("keeps the engine's cost-code order and shows the fee inside each value", () => {
    expect(sovItemRows(SOV)).toEqual([
      { k: "0001 · 03 30 00 — Walls", v: "$20,020 (incl. $1,820 fee) · 2 element(s)" },
      { k: "0002 · 08 11 00 — Doors", v: "$1,595 (incl. $145 fee) · 1 element(s)" },
    ]);
  });

  it("counts the page against the items the server dropped as well as the ones it sent", () => {
    expect(sovPageNote({ ...SOV, truncated: 40 }, 60))
      .toBe("Showing 2 of 42 item(s), in cost-code order.");
    expect(sovPageNote(SOV, 60)).toBeNull();
    expect(sovPageNote(SOV, 1)).toBe("Showing 1 of 2 item(s), in cost-code order.");
  });
});

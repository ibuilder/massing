import { describe, it, expect } from "vitest";
import {
  packHeadline, exampleCaveat, adoptionLine, checkGate, checkSummary, attributionLine,
  outcomeLine, deleteConfirm, importRefusal,
  type PackHeader, type Applicability, type CheckOutcome, type PackOutcome,
} from "./jurisdictionPacks";

const PACK: PackHeader = {
  id: "tx-austin-2026", jurisdiction: "TX", authority: "City of Austin DSD",
  name: "Austin submittal data requirements", edition: "2026.1",
  source: "https://example.invalid/ordinance", requirements: [{ id: "r0" }, { id: "r1" }],
};

const REAL: PackOutcome = {
  id: "tx-austin-2026", name: "Austin submittal data requirements",
  authority: "City of Austin DSD", edition: "2026.1", is_example: false,
  total_rules: 4, failing_rules: 0, total_violations: 0,
};

const EXAMPLE: PackOutcome = {
  id: "example", name: "Example pack", authority: "", edition: "",
  is_example: true, total_rules: 2, failing_rules: 0, total_violations: 0,
};

describe("a pack is citable at a glance", () => {
  it("names the authority and the edition, not just the pack", () => {
    const line = packHeadline(PACK);
    expect(line).toContain("City of Austin DSD");
    expect(line).toContain("2026.1");
    expect(line).toContain("TX");
    expect(line).toContain("2 requirements");
  });

  it("counts one requirement in the singular", () => {
    expect(packHeadline({ ...PACK, requirements: [{ id: "r0" }] })).toContain("1 requirement");
    expect(packHeadline({ ...PACK, requirements: [{ id: "r0" }] })).not.toContain("1 requirements");
  });

  it("survives a pack whose requirements were not expanded in the list response", () => {
    expect(packHeadline({ ...PACK, requirements: undefined })).toContain("0 requirements");
  });
});

describe("the example pack can never read as a compliance finding", () => {
  // The load-bearing test of this file. `example` is the ONLY pack present before anything is
  // imported, so it is the one a first-time user runs. A result from it that looks like a verdict
  // tells somebody their model satisfies rules that do not exist anywhere.
  it("carries a caveat that says it asserts nothing about any real place", () => {
    const c = exampleCaveat({ is_example: true });
    expect(c).toContain("DEMONSTRATION");
    expect(c.toLowerCase()).toContain("not a compliance finding");
  });

  it("says NOTHING for a real pack — a caveat on every result is a caveat nobody reads", () => {
    expect(exampleCaveat({ is_example: false })).toBe("");
    expect(exampleCaveat({})).toBe("");
  });

  it("marks the demonstration pack inside the attribution line itself, not in a footnote", () => {
    expect(attributionLine([EXAMPLE])).toContain("demonstration pack");
    expect(attributionLine([REAL])).not.toContain("demonstration");
  });

  it("still marks it when a real pack ran alongside — a mixed run is not a real run", () => {
    const line = attributionLine([REAL, EXAMPLE]);
    expect(line).toContain("City of Austin DSD");
    expect(line).toContain("demonstration pack");
  });
});

describe("attribution is never dropped", () => {
  it("names whose rules produced the figure, in the same sentence as the figure", () => {
    const r: CheckOutcome = {
      model_scored: true, packs: [REAL], total_requirements: 4,
      failing_requirements: 0, total_violations: 0, satisfied: true,
    };
    const s = checkSummary(r);
    expect(s).toContain("Satisfied");
    expect(s).toContain("City of Austin DSD");
  });

  it("says 'an unattributed source' rather than printing a bare number", () => {
    expect(attributionLine([{ ...REAL, authority: null, edition: null }]))
      .toContain("an unattributed source");
  });

  it("reports failures with both the count and the violations", () => {
    const s = checkSummary({
      model_scored: true, packs: [{ ...REAL, failing_rules: 2, total_violations: 7 }],
      total_requirements: 4, failing_requirements: 2, total_violations: 7,
    });
    expect(s).toContain("2 of 4");
    expect(s).toContain("7 violations");
    expect(s).toContain("City of Austin DSD");
  });
});

describe("an absent result is never a pass", () => {
  it("reports an unscored model as the absence it is", () => {
    const s = checkSummary({ model_scored: false, packs: [], total_requirements: 0,
                             note: "no model index loaded" });
    expect(s).toContain("no model index loaded");
    expect(s).not.toContain("Satisfied");
  });

  it("refuses to call zero requirements a pass", () => {
    const s = checkSummary({ model_scored: true, packs: [], total_requirements: 0 });
    expect(s).toContain("nothing to report");
    expect(s).toContain("not a pass");
    expect(s).not.toContain("Satisfied");
  });

  it("falls back to its own wording when the server sent no note", () => {
    const s = checkSummary({ model_scored: false, packs: [], total_requirements: 0 });
    expect(s).toContain("not a pass");
  });
});

describe("the two refusals are told apart", () => {
  // Collapsing them would tell somebody to import a pack when what they need is to upload a model.
  const applies: Applicability = { jurisdiction: "TX", packs: [{ id: "tx-austin-2026" }],
                                   adopted: true };

  it("refuses for want of a pack when nothing applies", () => {
    const g = checkGate({ jurisdiction: "TX", packs: [], adopted: false,
                          why: "no pack has been imported for TX" }, true);
    expect(g.can).toBe(false);
    expect(g.why).toContain("no pack has been imported");
  });

  it("refuses for want of a MODEL when packs do apply", () => {
    const g = checkGate(applies, false);
    expect(g.can).toBe(false);
    expect(g.why).toContain("No model is loaded");
    expect(g.why).not.toContain("pack has been imported");
  });

  it("offers the check when a pack applies and a model is loaded", () => {
    expect(checkGate(applies, true)).toEqual({ can: true, why: "" });
  });

  it("offers it for an explicit pack even when the project's jurisdiction resolves nothing", () => {
    const g = checkGate({ jurisdiction: null, packs: [{ id: "example" }], adopted: false,
                          explicit: true }, true);
    expect(g.can).toBe(true);
  });
});

describe("a project with no jurisdiction is told so, and never given a default", () => {
  it("passes the server's reason through rather than inventing one", () => {
    const line = adoptionLine({ jurisdiction: null, packs: [], adopted: false,
                                why: "this project has no jurisdiction set" });
    expect(line).toBe("this project has no jurisdiction set");
  });

  it("has its own wording when the server sent none", () => {
    expect(adoptionLine({ jurisdiction: null, packs: [], adopted: false }))
      .toContain("no jurisdiction set");
  });

  it("distinguishes 'no jurisdiction' from 'jurisdiction with no packs'", () => {
    expect(adoptionLine({ jurisdiction: "TX", packs: [], adopted: false })).toContain("TX");
  });

  it("says how many apply when they do", () => {
    expect(adoptionLine({ jurisdiction: "TX", packs: [{ id: "a" }, { id: "b" }], adopted: true }))
      .toContain("2 packs apply in TX");
  });

  it("says an explicit pack was NOT resolved from the project", () => {
    const line = adoptionLine({ jurisdiction: null, packs: [{ id: "example" }], adopted: true,
                                explicit: true });
    expect(line).toContain("not resolved");
  });
});

describe("one pack's row", () => {
  it("reports met/total and violations", () => {
    expect(outcomeLine({ ...REAL, failing_rules: 1, total_violations: 3 }))
      .toContain("3/4 met, 3 violations");
  });

  it("says so when a pack carries no requirements rather than printing 0/0", () => {
    expect(outcomeLine({ ...REAL, total_rules: 0, failing_rules: 0, total_violations: 0 }))
      .toContain("no requirements");
  });
});

describe("deleting names the blast radius", () => {
  it("says the library is shared, not per-project", () => {
    const c = deleteConfirm(PACK);
    expect(c).toContain("SHARED");
    expect(c).toContain("TX");
    expect(c).toContain("re-imported");
  });
});

describe("an import refusal is the instruction, so it is shown verbatim", () => {
  it("passes the server's detail through", () => {
    const msg = "requirement 0's scope contains 'Pset_WallCommon.FireRating' — property paths use "
      + "TWO colons";
    expect(importRefusal(msg)).toContain("Pset_WallCommon.FireRating");
    expect(importRefusal(msg)).toContain("TWO colons");
  });

  it("says the server gave no reason rather than printing an empty refusal", () => {
    expect(importRefusal("")).toContain("no reason");
    expect(importRefusal("   ")).toContain("no reason");
  });
});

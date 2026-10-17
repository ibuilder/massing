/** SCOPE-THIN — four states of bid coverage, and the one the card could not show.
 *
 *  The fixtures are `services/api/test_scope_gap.py`'s own: a Structural package citing two CSI
 *  sections, an HVAC package covering the duct and citing none, doors in no package at all, and a
 *  Landscape package with no model elements.
 */
import { describe, expect, it } from "vitest";
import type { ScopeGapResult } from "../../api/procurement";
import {
  TONE_CSS, coverageVerdict, coveredLine, coveredRows, overScopedNote, specCitationNote, thinRows,
} from "./scopeGapRead";

const base = (over: Partial<ScopeGapResult> = {}): ScopeGapResult => ({
  package_count: 3, element_count: 6, covered_pct: 66.7, gap_element_count: 2,
  covered: [
    { discipline: "Structural", element_count: 3,
      classes: [{ ifc_class: "IfcColumn", count: 2 }, { ifc_class: "IfcBeam", count: 1 }],
      packages: ["Concrete structure"], spec_sections: ["03 30 00", "05 12 00"] },
    { discipline: "Mechanical", element_count: 1,
      classes: [{ ifc_class: "IfcDuctSegment", count: 1 }],
      packages: ["HVAC ductwork"], spec_sections: [] },
  ],
  gaps: [
    { discipline: "Architectural", element_count: 2,
      classes: [{ ifc_class: "IfcDoor", count: 2 }], sample_guids: ["w1", "w2"] },
  ],
  covered_without_specs: [
    { discipline: "Mechanical", packages: ["HVAC ductwork"], element_count: 1,
      sample_guids: ["d1"] },
  ],
  spec_sections: ["03 30 00", "05 12 00"], spec_section_count: 2,
  packages_without_model_scope: ["Site landscaping"],
  note: "Coverage matches each element's NCS discipline…",
  ...over,
});

/** Every discipline claimed, and the ONLY covering package cites nothing. This is the state that
 *  used to render as a green tick. */
const ALL_THIN = base({
  covered_pct: 100, gap_element_count: 0, gaps: [],
  covered: [{ discipline: "Structural", element_count: 6, classes: [],
              packages: ["Everything"], spec_sections: [] }],
  covered_without_specs: [{ discipline: "Structural", packages: ["Everything"],
                            element_count: 6, sample_guids: ["c1", "c2"] }],
  spec_sections: [], spec_section_count: 0,
  packages_without_model_scope: [],
});

/** Genuinely clean: nothing uncovered, every covering package cites a section. */
const CLEAN = base({
  covered_pct: 100, gap_element_count: 0, gaps: [], covered_without_specs: [],
  covered: [{ discipline: "Structural", element_count: 6, classes: [],
              packages: ["Concrete structure"], spec_sections: ["03 30 00"] }],
  packages_without_model_scope: [],
});

describe("the verdict has four states, and the card had two", () => {
  it("a job whose only coverage cites no spec section is NOT a green tick", () => {
    // THE DEFECT: `gaps` is empty here, so the old else-branch printed
    // "✅ Every model discipline is covered by a bid package".
    const v = coverageVerdict(ALL_THIN);
    expect(v?.tone).toBe("warn");
    expect(v?.text).toContain("cites no CSI spec section");
    expect(v?.text).toContain("6 element(s)");
    expect(v?.text).toContain("survives buyout");
    expect(v?.text).not.toContain("Every model discipline is covered");
  });

  it("a real gap outranks thin coverage, and mentions both", () => {
    // Quantities in nobody's bid cost more than quantities somebody is pricing without writing
    // down what — so the gap leads, and the thin count is not dropped.
    const v = coverageVerdict(base());
    expect(v?.tone).toBe("crit");
    expect(v?.text).toContain("Architectural (2)");
    expect(v?.text).toContain("nobody's bid");
    expect(v?.text).toContain("A further 1");
  });

  it("a gap with no thin disciplines does not append an empty clause", () => {
    const v = coverageVerdict(base({ covered_without_specs: [] }));
    expect(v?.text).not.toContain("A further");
  });

  it("the clean case says BOTH halves, so the tick means something", () => {
    const v = coverageVerdict(CLEAN);
    expect(v?.tone).toBe("good");
    expect(v?.text).toContain("covered by a bid package");
    expect(v?.text).toContain("at least one CSI spec section");
  });

  it("degrades to the old two-state reading against a server that omits the key", () => {
    // An older server sends no `covered_without_specs`; the clean verdict is then the honest one
    // available rather than a warning about an absence it cannot see.
    const v = coverageVerdict(base({ gaps: [], covered_without_specs: undefined }));
    expect(v?.tone).toBe("good");
  });

  it("is null on an empty takeoff rather than a verdict over nothing", () => {
    expect(coverageVerdict(base({ element_count: 0 }))).toBeNull();
  });
});

describe("the thin disciplines are named with the package to go and ask", () => {
  it("carries the discipline, the element count, the packages and sample GUIDs", () => {
    const rows = thinRows(base());
    expect(rows).toEqual([{ discipline: "Mechanical", elements: 1, packages: "HVAC ductwork",
                            guids: ["d1"] }]);
  });

  it("is empty, not undefined, when the key is absent", () => {
    expect(thinRows(base({ covered_without_specs: undefined }))).toEqual([]);
  });
});

describe("zero spec citations is the sharpest number on the card", () => {
  it("says so when no package anywhere cites a section", () => {
    const n = specCitationNote(ALL_THIN);
    expect(n).toContain("No bid package on this project cites a CSI spec section");
    expect(n).toContain("nothing behind it");
  });

  it("is silent above zero, so the zero does not read like every other render", () => {
    // An always-on count teaches its reader to skip the line, and then the zero looks the same.
    expect(specCitationNote(base())).toBeNull();
    expect(specCitationNote(base({ spec_section_count: undefined }))).toBeNull();
  });
});

describe("covered_pct is qualified where it is printed", () => {
  it("says the percentage is BY DISCIPLINE and names both shortfalls", () => {
    const l = coveredLine(base());
    expect(l).toBe("66.7% of 6 element(s) are in a package by discipline · 2 in none "
                   + "· 1 discipline(s) traceable to no spec section");
  });

  it("a 100% that is entirely untraceable still says so on the same line", () => {
    const l = coveredLine(ALL_THIN);
    expect(l).toContain("100% of 6");
    expect(l).toContain("by discipline");
    expect(l).toContain("1 discipline(s) traceable to no spec section");
  });

  it("a genuinely clean job gets no trailing clauses", () => {
    expect(coveredLine(CLEAN)).toBe("100% of 6 element(s) are in a package by discipline");
  });
});

describe("the per-discipline spec sections finally render", () => {
  it("lists the sections each covering package cites", () => {
    const rows = coveredRows(base());
    expect(rows[0]).toEqual({ discipline: "Structural", elements: 3,
                              packages: "Concrete structure",
                              sections: "03 30 00, 05 12 00", tone: "good" });
  });

  it("renders an empty section list as a WARNING, not a blank", () => {
    // A blank cell reads as "nothing to say"; this one is the finding.
    expect(coveredRows(base())[1]).toEqual({ discipline: "Mechanical", elements: 1,
                                             packages: "HVAC ductwork",
                                             sections: "no section cited", tone: "warn" });
  });

  it("treats an absent key the same as an empty list — the engine omits it on a gap entry", () => {
    const rows = coveredRows(base({ covered: [{ discipline: "X", element_count: 1, classes: [],
                                                packages: ["P"] }] }));
    expect(rows[0]!.sections).toBe("no section cited");
    expect(rows[0]!.tone).toBe("warn");
  });
});

describe("an over-scoped package is the mirror of a gap", () => {
  it("names them and states both readings", () => {
    const n = overScopedNote(base());
    expect(n).toContain("Site landscaping");
    expect(n).toContain("the model is behind it");
    expect(n).toContain("pricing nothing");
  });

  it("is silent when every package has model scope", () => {
    expect(overScopedNote(CLEAN)).toBeNull();
  });
});

describe("the tone tokens are literal", () => {
  it("names properties the stylesheets define", () => {
    expect(TONE_CSS.warn).toBe("var(--status-warn)");
    expect(TONE_CSS.crit).toBe("var(--status-crit)");
    expect(TONE_CSS.good).toBe("var(--status-good)");
  });
});

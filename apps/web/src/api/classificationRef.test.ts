import { describe, it, expect } from "vitest";
import { codeAnnotation, crosswalkFor, divisionOf, type ClassificationRefs } from "./classificationRef";

/** A slice of what `GET /reference/disciplines` actually serves, shapes and values from
 *  `services/api/src/aec_api/classification.py` (MF_DIVISIONS / UNIFORMAT / DISCIPLINES). */
const REFS: ClassificationRefs = {
  disciplines: [{ code: "A", name: "Architectural" }, { code: "M", name: "Mechanical" },
                { code: "S", name: "Structural" }],
  masterformat_divisions: [
    { code: "03", title: "Concrete", discipline: "S" },
    { code: "08", title: "Openings", discipline: "A" },
    { code: "23", title: "Heating, Ventilating and Air Conditioning", discipline: "M" },
    { code: "31", title: "Earthwork", discipline: null },
  ],
  uniformat_crosswalk: [
    { code: "A", title: "Substructure", masterformat_divisions: ["03", "31"] },
    { code: "B20", title: "Exterior Enclosure", masterformat_divisions: ["04", "07", "08"] },
    { code: "D30", title: "HVAC", masterformat_divisions: ["23"] },
  ],
};

describe("divisionOf", () => {
  it("reads the division out of every way a section gets typed", () => {
    expect(divisionOf("08 51 00")).toBe("08");
    expect(divisionOf("085100")).toBe("08");
    expect(divisionOf("08-51-00")).toBe("08");
  });
  it("is null when there are not two digits to read", () => {
    expect(divisionOf("8")).toBeNull();
    expect(divisionOf("")).toBeNull();
    expect(divisionOf("B2020")).toBe("20");   // digits only — the caller picks the right system
  });
});

describe("crosswalkFor", () => {
  it("resolves a code to its element", () => {
    expect(crosswalkFor("B2020", REFS.uniformat_crosswalk)?.code).toBe("B20");
    expect(crosswalkFor("A1010", REFS.uniformat_crosswalk)?.code).toBe("A");
  });

  it("takes the LONGEST matching prefix when a parent and a child BOTH appear", () => {
    // Mutation-driven, and the first version of this test could not see the rule it was named for:
    // it asserted against the served table, where no two entries are prefixes of each other ("A",
    // "B10", "B20", "D30"...), so first-match and longest-match agree on every code and replacing
    // one with the other passed. Uniformat II is a hierarchy and the served table is one level of
    // it; the day "A10" joins "A", a first-match rule silently reports every A10xx as bare
    // "Substructure". The competing rows have to be IN the fixture for the assertion to mean
    // anything.
    const nested = [{ code: "A", title: "Substructure", masterformat_divisions: ["03", "31"] },
                    { code: "A10", title: "Foundations", masterformat_divisions: ["03"] }];
    expect(crosswalkFor("A1010", nested)?.code).toBe("A10");
    expect(crosswalkFor("A1010", [...nested].reverse())?.code).toBe("A10");   // order must not decide
    expect(crosswalkFor("A20", nested)?.code).toBe("A");
  });
  it("is case- and punctuation-insensitive", () => {
    expect(crosswalkFor("b20-20", REFS.uniformat_crosswalk)?.code).toBe("B20");
  });
  it("is null for a code under no element", () => {
    expect(crosswalkFor("Z99", REFS.uniformat_crosswalk)).toBeNull();
    expect(crosswalkFor("", REFS.uniformat_crosswalk)).toBeNull();
  });
});

describe("codeAnnotation", () => {
  it("names the division and the discipline it rolls up to", () => {
    expect(codeAnnotation("MasterFormat", "08 51 00", REFS))
      .toEqual({ text: "Division 08 · Openings (Architectural)", known: true });
  });

  it("flags a division the master does not carry — the transposition case", () => {
    // `80 51 00` for `08 51 00`. This is the defect the whole change exists for: before it, the
    // prompt offered an example and the typo became a classification on an IFC element in silence.
    const ann = codeAnnotation("MasterFormat", "80 51 00", REFS);
    expect(ann?.known).toBe(false);
    expect(ann?.text).toContain("80");
  });

  it("does not refuse an unknown division, it reports one", () => {
    // MasterFormat reserves 48-49 and the 80s-90s for user-defined divisions, so `known: false` is
    // a thing to say, never a thing to block on. The annotation is still returned.
    expect(codeAnnotation("MasterFormat", "48 00 00", REFS)).not.toBeNull();
  });

  it("omits the discipline when the division rolls up to none", () => {
    expect(codeAnnotation("MasterFormat", "31 20 00", REFS))
      .toEqual({ text: "Division 31 · Earthwork", known: true });
  });

  it("crosses a Uniformat element over to the divisions it procures through", () => {
    expect(codeAnnotation("UniFormat", "B2020", REFS))
      .toEqual({ text: "B20 · Exterior Enclosure → MasterFormat 04, 07, 08", known: true });
  });

  it("says nothing for a system this route carries no reference for", () => {
    // OmniClass and Uniclass are not served here. An annotation that appears for two systems and
    // not the others is information; a fabricated one is not.
    expect(codeAnnotation("OmniClass", "23-17 11 11", REFS)).toBeNull();
    expect(codeAnnotation("Uniclass", "SS_25_10", REFS)).toBeNull();
  });

  it("matches the system name however it is cased", () => {
    // The caller passes the UI's label ("UniFormat"); the rule must not depend on that spelling.
    expect(codeAnnotation("uniformat", "D3010", REFS)?.known).toBe(true);
    expect(codeAnnotation("MASTERFORMAT", "23 00 00", REFS)?.known).toBe(true);
  });
});

import { describe, expect, it } from "vitest";

import { classPageNote, classRows, CLASS_PAGE, disciplineRows, mepBasis, mepHeadline,
  unattributedNote } from "./mepExtractRead";
import type { MepModelExtract } from "../../api/model";

function resp(over: Partial<MepModelExtract> = {}): MepModelExtract {
  return {
    model_scored: true,
    mep_elements: 1200,
    by_class: [
      { ifc_class: "IfcDuctSegment", label: "Duct", count: 600 },
      { ifc_class: "IfcPipeSegment", label: "Pipe", count: 400 },
      { ifc_class: "IfcLightFixture", label: "Light fixture", count: 200 },
    ],
    class_count: 3,
    by_discipline: [{ discipline: "Electrical", count: 200 },
      { discipline: "Mechanical", count: 600 }, { discipline: "Plumbing", count: 400 }],
    unattributed: 0,
    note: "MEP elements counted off the model by IFC class. Disciplines are derived from the IFC "
      + "class, not from the model's own discipline metadata.",
    ...over,
  };
}

describe("the MEP headline", () => {
  it("names the disciplines, which is the division a contractor buys by", () => {
    const h = mepHeadline(resp());
    expect(h.text).toContain("1,200 MEP element(s) in 3 IFC class(es)");
    expect(h.text).toContain("Electrical 200 · Mechanical 600 · Plumbing 400");
  });

  it("distinguishes no model from a model with no MEP in it", () => {
    expect(mepHeadline(resp({ model_scored: false })))
      .toEqual({ tone: "", text: "Load a model to count MEP elements off it." });
    const empty = mepHeadline(resp({ mep_elements: 0, by_class: [], by_discipline: [],
      class_count: 0 }));
    expect(empty.tone).toBe("warn");
    expect(empty.text).toContain("contains no MEP elements of any class this reads");
  });

  it("warns when any element could not be attributed to a discipline", () => {
    expect(mepHeadline(resp()).tone).toBe("");
    expect(mepHeadline(resp({ unattributed: 7 })).tone).toBe("warn");
  });
});

describe("the discipline rows", () => {
  it("carry the share, so two columns are comparable at a glance", () => {
    expect(disciplineRows(resp())).toEqual([
      { discipline: "Electrical", count: "200", share: "16.7%" },
      { discipline: "Mechanical", count: "600", share: "50%" },
      { discipline: "Plumbing", count: "400", share: "33.3%" },
    ]);
  });

  it("does not divide by zero on an empty extract", () => {
    expect(disciplineRows(resp({ mep_elements: 0,
      by_discipline: [{ discipline: "Mechanical", count: 0 }] })))
      .toEqual([{ discipline: "Mechanical", count: "0", share: "—" }]);
  });
});

describe("the unattributed note", () => {
  it("is absent at the measured answer of zero rather than a permanent 0 row", () => {
    // All 25 of `_MEP_CLASSES` resolve, so zero is the expected value, not a lucky one.
    expect(unattributedNote(resp())).toBeNull();
  });

  it("says the discipline columns are SHORT, which is the consequence a reader needs", () => {
    const n = unattributedNote(resp({ unattributed: 7 }))!;
    expect(n).toContain("7 element(s) could not be attributed");
    expect(n).toContain("discipline columns above are short by that much");
  });
});

describe("the class table", () => {
  it("renders the largest classes, formatted", () => {
    expect(classRows(resp())[0]).toEqual({ ifcClass: "IfcDuctSegment", label: "Duct", count: "600" });
  });

  it("says nothing about paging when every class fits", () => {
    expect(classPageNote(resp())).toBeNull();
  });

  it("pages against the SERVER's class count, not the length of what shipped", () => {
    // TRUNC-COUNTED: the card sliced 15 of up to 25 and said nothing, in a card headed by a total.
    const n = classPageNote(resp({ class_count: 25 }))!;
    expect(n).toContain(`Showing the ${CLASS_PAGE} largest of 25 IFC class(es)`);
    expect(n).toContain("discipline totals above are over all of them");
  });
});

describe("the basis", () => {
  it("is returned verbatim, and says the discipline comes from the CLASS", () => {
    // A discipline derived from the IFC class is a different claim from one read off the model's own
    // discipline metadata, and only one of them follows what an element IS.
    expect(mepBasis(resp())).toBe(resp().note);
    expect(mepBasis(resp())).toContain("derived from the IFC class");
  });
});

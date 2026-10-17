import { describe, expect, it } from "vitest";

import { checkFieldRows, checkHeadline, conventionNote, namingHeadline, pageNote, unnamedNote,
  unnamedPageNote, unnamedRows, violationPageNote, violationRows } from "./namingRead";
import type { NamingAudit, NamingCheck, NamingRegisterAudit } from "../../api/types";

/** The register block as the server measured it: five containers, one genuinely misnamed, three
 *  with no `container_id` recorded. The numbers are copied from a live `/naming/audit`, not
 *  invented — `services/api/test_naming.py` asserts the same shape at the route. */
function reg(over: Partial<NamingRegisterAudit> = {}): NamingRegisterAudit {
  return {
    total: 5,
    named: 2,
    compliant: 1,
    compliance_pct: 50.0,
    violations: [{ ref: "IC-005", title: "loose", name: "New file (2).pdf",
      issues: ["expected Type_Discipline_Description_Revision_Date (>=5 '_'-separated fields), got 1"] }],
    violations_count: 1,
    violations_truncated: false,
    unnamed: [{ ref: "IC-001", title: "Ground floor plan" },
      { ref: "IC-002", title: "Structural calcs" },
      { ref: "IC-003", title: "Fire strategy" }],
    unnamed_count: 3,
    unnamed_truncated: false,
    ...over,
  };
}

const CONV: NamingAudit["conventions"] = {
  container: {
    pattern: "Type_Discipline_Description_Revision_Date", separator: "_",
    fields: ["Type", "Discipline", "Description", "Revision", "Date"],
    note: "e.g. DR_A_GroundFloorPlan_P01_2026-07-05 — revision-controlled.",
  },
  sheet: { pattern: "NCS Sheet ID: <discipline designator><sheet-type digit><sequence>",
    note: "e.g. A-101 = Architectural / Plans / 01." },
};

describe("the naming compliance headline", () => {
  it("states the population the percentage is over, not the register size", () => {
    const h = namingHeadline(reg(), "container");
    expect(h.text).toContain("1/2 compliant (50%)");
    expect(h.text).toContain("over the 2 of 5 container(s) that carry a name");
    expect(h.text).toContain("the other 3 have none recorded");
  });

  it("is crit on a real naming failure and warn on a recording gap alone", () => {
    expect(namingHeadline(reg(), "container").tone).toBe("crit");
    // Every named row compliant, three still unnamed: a gap, not a failure.
    expect(namingHeadline(reg({ compliant: 2, compliance_pct: 100, violations: [], violations_count: 0 }),
      "container").tone).toBe("warn");
  });

  it("is good only when every registered row carries a compliant name", () => {
    const h = namingHeadline(reg({ total: 2, named: 2, compliant: 2, compliance_pct: 100,
      violations: [], violations_count: 0, unnamed: [], unnamed_count: 0 }), "container");
    expect(h.tone).toBe("good");
    expect(h.text).toContain("over all 2 container(s)");
    expect(h.text).not.toContain("none recorded");
  });

  it("does not report an empty register when the register has rows nothing could rule on", () => {
    // BASIS-UNREAD's lesson: an empty-state branch keyed on the evaluable count denies the rows
    // exist. Five containers, none named — that is not "no containers registered".
    const h = namingHeadline(reg({ named: 0, compliant: 0, compliance_pct: null, violations: [],
      violations_count: 0, unnamed_count: 5 }), "container");
    expect(h.tone).toBe("warn");
    expect(h.text).toContain("5 container(s) registered and NONE carries a recorded name");
    expect(h.text).not.toContain("No container");
  });

  it("reports an actually-empty register as empty, with no verdict and no tone", () => {
    const h = namingHeadline(reg({ total: 0, named: 0, compliant: 0, compliance_pct: null,
      violations: [], violations_count: 0, unnamed: [], unnamed_count: 0 }), "container");
    expect(h).toEqual({ tone: "", text: "No containers registered yet." });
  });
});

describe("the unnamed rows", () => {
  it("name the field that would bring them into the percentage", () => {
    const n = unnamedNote(reg(), "container", "Container ID (ISO 19650 naming)");
    expect(n).toContain("3 of 5 container(s) have no Container ID (ISO 19650 naming) recorded");
    expect(n).toContain("outside every percentage above");
  });

  it("are absent, not zero-valued, when every row carries a name", () => {
    expect(unnamedNote(reg({ unnamed: [], unnamed_count: 0 }), "container", "x")).toBeNull();
  });

  it("declare a shortfall between the listed page and the count", () => {
    const n = unnamedNote(reg({ unnamed_count: 900, unnamed_truncated: true }), "container", "x");
    expect(n).toContain("900 of 5");
    expect(n).toContain("listing the first 3");
  });

  it("render the ref and fall back to a marker rather than an empty cell", () => {
    expect(unnamedRows(reg())[0]).toEqual({ ref: "IC-001", title: "Ground floor plan" });
    expect(unnamedRows(reg({ unnamed: [{ ref: "", title: "" }], unnamed_count: 1 }))[0])
      .toEqual({ ref: "—", title: "(untitled)" });
  });
});

describe("the violation rows", () => {
  it("carry the ref, the string ruled on, and every reason", () => {
    const v = violationRows(reg())[0]!;
    expect(v.ref).toBe("IC-005");
    expect(v.name).toBe("New file (2).pdf");
    expect(v.why).toContain("expected Type_Discipline_Description_Revision_Date");
  });

  it("distinguish the name ruled on from the human title", () => {
    // The whole finding: these are two different strings and the audit used to rule on the title.
    const v = violationRows(reg())[0]!;
    expect(v.title).toBe("loose");
    expect(v.name).not.toBe(v.title);
  });

  it("join several issues rather than showing only the first", () => {
    const v = violationRows(reg({ violations: [{ ref: "IC-9", title: "t", name: "DR_Z_x_zz_nope",
      issues: ["discipline 'Z' is not a known designator / name", "date 'nope' not a YYYY token"] }] }))[0]!;
    expect(v.why).toBe("discipline 'Z' is not a known designator / name; date 'nope' not a YYYY token");
  });

  it("never leave a row with no reason at all", () => {
    const v = violationRows(reg({ violations: [{ ref: "IC-9", title: "t", name: "x", issues: [] }] }))[0]!;
    expect(v.why).toBe("no reason given");
  });
});

describe("the bounded lists", () => {
  it("say nothing while the page IS the total", () => {
    expect(violationPageNote(reg(), 200)).toBeNull();
    expect(unnamedPageNote(reg(), 200)).toBeNull();
  });

  it("print the count, not the page length, and name the server's own cap", () => {
    // TRUNC-COUNTED: three screens printed the length of a page as if it were a total.
    const n = violationPageNote(reg({ violations_count: 640, violations_truncated: true }), 200);
    expect(n).toContain("Showing 1 of 640");
    expect(n).toContain("caps each list at 200");
  });

  it("takes the cap from the response so the client cannot disagree with the server", () => {
    expect(pageNote(2, 50, 25, "thing(s)")).toContain("caps each list at 25");
  });
});

describe("the convention note", () => {
  it("comes from the audit's own response, verbatim", () => {
    const n = conventionNote({ conventions: CONV, containers: reg(), sheets: reg(), max_violations: 200 });
    expect(n).toContain("Type_Discipline_Description_Revision_Date");
    expect(n).toContain(CONV.container.note);
    expect(n).toContain(CONV.sheet.pattern);
    expect(n).toContain(CONV.sheet.note);
  });

  it("is not optional — it is a string, with no absent case to fall through", () => {
    // It used to come from a second route behind `.catch(() => null)`, so a failed request printed
    // the percentages with no basis beside them.
    expect(typeof conventionNote({ conventions: CONV, containers: reg(), sheets: reg(),
      max_violations: 200 })).toBe("string");
  });
});

describe("the on-demand name check", () => {
  const ok: NamingCheck = { name: "DR_A_GroundFloorPlan_P01_2026-07-05", kind: "container",
    valid: true, fields: { type: "DR", discipline: "A", description: "GroundFloorPlan",
      revision: "P01", date: "2026-07-05" }, issues: [] };

  it("passes a compliant name and shows what the parser read", () => {
    expect(checkHeadline(ok)).toEqual({ tone: "good",
      text: `"${ok.name}" satisfies the container convention.` });
    expect(checkFieldRows(ok).map((r) => r.field)).toEqual(
      ["type", "discipline", "description", "revision", "date"]);
  });

  it("gives the reason a name failed, not a bare FAIL", () => {
    const h = checkHeadline({ name: "Final.pdf", kind: "container", valid: false, fields: {},
      issues: ["expected Type_Discipline_Description_Revision_Date (>=5 '_'-separated fields), got 1"] });
    expect(h.tone).toBe("crit");
    expect(h.text).toContain(">=5 '_'-separated fields");
  });

  it("shows no field table when the parser could not split the name at all", () => {
    expect(checkFieldRows({ name: "x", kind: "container", valid: false, fields: {}, issues: ["no"] }))
      .toEqual([]);
  });

  it("drops blank fields rather than printing an empty row", () => {
    expect(checkFieldRows({ ...ok, fields: { type: "DR", discipline: "" } }))
      .toEqual([{ field: "type", value: "DR" }]);
  });

  it("renders the NCS parse for a sheet, whose fields are a different set entirely", () => {
    const rows = checkFieldRows({ name: "A-101", kind: "sheet", valid: true,
      fields: { discipline_code: "A", sheet_type: 1, sequence: "01" }, issues: [] });
    expect(rows).toEqual([{ field: "discipline code", value: "A" },
      { field: "sheet type", value: "1" }, { field: "sequence", value: "01" }]);
  });
});

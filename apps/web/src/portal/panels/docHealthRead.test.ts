import { describe, expect, it } from "vitest";

import { coverageNote, healthHeadline, namingBasis, namingNote, orphanBasis, orphanNote, orphanRows,
  renamedPageNote, renamedRows, stateRows } from "./docHealthRead";
import type { DocumentsHealth } from "../../api/types";

/** The two-file set measured against a live route: one uploaded already conforming, one uploaded as
 *  "Final final v2.pdf" and renamed on intake. 2 of 11 required folders have a document.
 *  `services/api/test_docmanager.py` asserts the same shape at the route. */
function resp(over: Partial<DocumentsHealth> = {}): DocumentsHealth {
  return {
    total_files: 2,
    by_cde_state: { published: 2 },
    naming_compliance_pct: 100.0,
    named_at_source_pct: 50.0,
    renamed_on_intake: 1,
    renamed: [{ id: "f2", orig_name: "Final final v2.pdf",
      name: "DOC_G_FinalFinalV2_P01_2026-10-15.pdf" }],
    renamed_truncated: false,
    naming_basis: "`naming_compliance_pct` is over the FILED name, which `upload` generates.",
    revision_control_pct: 100.0,
    required_coverage_pct: 18.2,
    required_total: 11,
    required_missing: ["02_Drawings", "12_Model"],
    orphans: [], orphan_count: 0, orphans_truncated: false,
    orphan_basis: "An orphan is a filed document whose folder is not in the standard taxonomy.",
    superseded_kept: 0,
    note: "Health of the document set.",
    ...over,
  };
}

describe("the health headline", () => {
  it("leads with the number that is about the PROJECT, not the two the server writes", () => {
    // `naming_compliance_pct` AND `revision_control_pct` are both 100% by construction — `upload`
    // generates every filed name and assigns every revision — so the strip's other two percentages
    // could not vary. Neither belongs in a headline.
    const h = healthHeadline(resp());
    expect(h.text).toContain("50% named to the standard at source");
    expect(h.text).not.toContain("revision control");
    expect(h.text).not.toContain("100%");
  });

  it("warns when most documents are not named to the standard at source", () => {
    expect(healthHeadline(resp({ named_at_source_pct: 10 })).tone).toBe("warn");
    expect(healthHeadline(resp({ named_at_source_pct: 90 })).tone).toBe("");
  });

  it("mentions retained superseded revisions only when there are some", () => {
    expect(healthHeadline(resp({ superseded_kept: 3 })).text)
      .toContain("3 superseded revision(s) kept");
    expect(healthHeadline(resp()).text).not.toContain("superseded");
  });

  it("reports an empty document set as empty", () => {
    expect(healthHeadline(resp({ total_files: 0 })))
      .toEqual({ tone: "", text: "No documents on file yet." });
  });
});

describe("the two naming numbers", () => {
  it("says the filed-name percentage is a check on the generator", () => {
    const n = namingNote(resp())!;
    expect(n).toContain("Filed names 100% conform and revision control is 100%");
    expect(n).toContain("the server writes both");
    expect(n).toContain("1 document(s) were renamed on intake");
  });

  it("says so positively when nothing needed renaming", () => {
    expect(namingNote(resp({ renamed_on_intake: 0, named_at_source_pct: 100, renamed: [] })))
      .toContain("Every document arrived already conforming");
  });

  it("is absent on an empty set rather than printing a percentage over nothing", () => {
    expect(namingNote(resp({ total_files: 0, naming_compliance_pct: null }))).toBeNull();
  });

  it("returns the engine's basis verbatim", () => {
    expect(namingBasis(resp())).toBe(resp().naming_basis);
  });

  it("shows what the uploader actually typed beside what it was filed as", () => {
    expect(renamedRows(resp())[0]).toEqual({ id: "f2", orig_name: "Final final v2.pdf",
      name: "DOC_G_FinalFinalV2_P01_2026-10-15.pdf" });
  });

  it("declares a shortfall between the listed renames and the count", () => {
    expect(renamedPageNote(resp({ renamed_on_intake: 900, renamed_truncated: true })))
      .toContain("Showing 1 of 900");
    expect(renamedPageNote(resp())).toBeNull();
  });
});

describe("the required-folder coverage", () => {
  it("names the missing folders and the denominator, which were declared and never rendered", () => {
    const c = coverageNote(resp())!;
    expect(c.tone).toBe("warn");
    expect(c.text).toContain("9 of 11 required folders have a document (18.2%)");
    expect(c.text).toContain("nothing filed in: 02_Drawings, 12_Model");
  });

  it("is crit when NO required folder has anything in it", () => {
    const c = coverageNote(resp({ required_missing: Array.from({ length: 11 }, (_, i) => `f${i}`),
      required_coverage_pct: 0 }))!;
    expect(c.tone).toBe("crit");
  });

  it("is good and says so plainly when every required folder is covered", () => {
    const c = coverageNote(resp({ required_missing: [], required_coverage_pct: 100 }))!;
    expect(c).toEqual({ tone: "good",
      text: "All 11 required folders have at least one document." });
  });

  it("says nothing when the taxonomy declares no required folders", () => {
    expect(coverageNote(resp({ required_total: 0 }))).toBeNull();
  });
});

describe("the CDE-state spread", () => {
  it("orders by the ISO 19650 progression, not by count", () => {
    // The SHAPE of the spread is the point: everything still WIP reads differently from everything
    // published, at the same total.
    expect(stateRows(resp({ by_cde_state: { published: 2, wip: 9, archived: 1, shared: 4 } })))
      .toEqual([{ state: "wip", count: 9 }, { state: "shared", count: 4 },
        { state: "published", count: 2 }, { state: "archived", count: 1 }]);
  });

  it("puts a state it does not recognise last rather than dropping it", () => {
    const rows = stateRows(resp({ by_cde_state: { "?": 1, wip: 2 } }));
    expect(rows.map((r) => r.state)).toEqual(["wip", "?"]);
  });

  it("is empty for an empty set", () => {
    expect(stateRows(resp({ by_cde_state: {} }))).toEqual([]);
  });
});

describe("the orphaned documents", () => {
  it("say nothing on a clean set — the list is normally empty by construction", () => {
    expect(orphanNote(resp())).toBeNull();
    expect(orphanBasis(resp())).toBeNull();
  });

  it("name the folder and file, and why the list can be non-empty at all", () => {
    const h = resp({ orphan_count: 1,
      orphans: [{ id: "f9", name: "DOC_G_Old_P01_2026-01-01.pdf", folder: "07_Retired" }] });
    expect(orphanNote(h)).toContain("1 document(s) sit outside the standard folder taxonomy");
    expect(orphanNote(h)).toContain("filed before a folder left the standard tree");
    expect(orphanRows(h)[0]!.folder).toBe("07_Retired");
    expect(orphanBasis(h)).toBe(h.orphan_basis);
  });

  it("declares a shortfall between the listed orphans and the count", () => {
    expect(orphanNote(resp({ orphan_count: 400, orphans_truncated: true,
      orphans: [{ id: "f9", name: "n", folder: "f" }] }))).toContain("(showing 1)");
  });
});

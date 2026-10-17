import { readFileSync } from "node:fs";
import { resolve } from "node:path";

import { describe, expect, it } from "vitest";

import type { DrawingRegister } from "./api/drawingSet";
import {
  issuanceLine, orderWarning, registerSuspect, sheetHistory, supersededRows,
} from "./drawingRegisterReadings";

const ORDER_OK = "Every sheet's revision order is recorded: within a record the revision deltas are "
  + "in the order they were made, and no sheet mixes lettered and numbered revisions across records.";
const ORDER_AMBIG = "1 sheet(s) carry both lettered and numbered revisions across separate records. "
  + "Which is later is a set convention, not something these labels state, so the current revision "
  + "on those sheets is this register's ranking rather than a recorded fact -- check them before "
  + "issuing.";

/** `drawingset.register`'s real output, dumped from the engine. A-101 was revised twice through
 *  `revise` (deltas A then B, the second citing CCD-003); A-102 is a genuinely new sheet.
 *  **Before this item A-101 reported `revisions: 1, change: "new"` and `superseded_count` was 0.** */
const REVISED: DrawingRegister = {
  sheet_count: 2, current_count: 2, superseded_count: 1, new_count: 1, revised_count: 1,
  by_discipline: { Architectural: 2 },
  sheet_index: [
    { sheet_number: "A-101", title: "Level 1 Plan", discipline: "Architectural", sheet_id: null,
      current_revision: "B", revisions: 2, change: "revised", order_ambiguous: false },
    { sheet_number: "A-102", title: "Level 2 Plan", discipline: "Architectural", sheet_id: null,
      current_revision: "0", revisions: 1, change: "new", order_ambiguous: false },
  ],
  current_set: [
    { ref: "DWG-1", sheet_number: "A-101", title: "Level 1 Plan", discipline: "Architectural",
      status: "issued", revision: "B", rev_date: "2026-04-02",
      description: "CCD-03 stair revision", instrument: { type: "CCD", ref: "CCD-003" },
      source: "delta" },
    { ref: "DWG-2", sheet_number: "A-102", title: "Level 2 Plan", discipline: "Architectural",
      status: "draft", revision: "0", source: "record" },
  ],
  superseded: [
    { ref: "DWG-1", sheet_number: "A-101", title: "Level 1 Plan", discipline: "Architectural",
      status: "issued", revision: "A", rev_date: "2026-03-01",
      description: "ASI-01 door swap", instrument: null, source: "delta", superseded_by: "B" },
  ],
  order_ambiguous_sheets: [], order_note: ORDER_OK,
};

/** A drawing-log import: four records on one sheet, labels `1, 2, A, B`. The register ranks `2`
 *  current — deterministic, and not a recorded fact, which is what it now says. */
const AMBIGUOUS: DrawingRegister = {
  sheet_count: 1, current_count: 1, superseded_count: 3, new_count: 0, revised_count: 1,
  by_discipline: { Architectural: 1 },
  sheet_index: [
    { sheet_number: "A-101", title: "Level 1 Plan", discipline: "Architectural", sheet_id: null,
      current_revision: "2", revisions: 4, change: "revised", order_ambiguous: true },
  ],
  current_set: [
    { ref: "D2", sheet_number: "A-101", title: "Level 1 Plan", discipline: "Architectural",
      status: "issued", revision: "2", source: "record" },
  ],
  superseded: ["A", "B", "1"].map((rev, i) => ({
    ref: ["D3", "D4", "D1"][i]!, sheet_number: "A-101", title: "Level 1 Plan",
    discipline: "Architectural", status: "issued", revision: rev, source: "record" as const,
    superseded_by: "2",
  })),
  order_ambiguous_sheets: ["A-101"], order_note: ORDER_AMBIG,
};

const EMPTY: DrawingRegister = {
  sheet_count: 0, current_count: 0, superseded_count: 0, new_count: 0, revised_count: 0,
  by_discipline: {}, sheet_index: [], current_set: [], superseded: [],
  order_ambiguous_sheets: [], order_note: ORDER_OK,
};

describe("issuanceLine", () => {
  it("counts 'new' over the sheets it was counted from", () => {
    const line = issuanceLine(REVISED);
    expect(line).toContain("2 current of 2 sheets");
    expect(line).toContain("1 never revised");
    expect(line).toContain("1 revised");
    expect(line).toContain("1 superseded revision");
  });

  it("says 'never revised' rather than 'new'", () => {
    // The register's `new` means "one known revision", not "recently added" — and for every sheet
    // revised through `revise` it used to mean neither.
    expect(issuanceLine(REVISED)).not.toMatch(/\bnew\b/);
  });

  it("is singular on one sheet and one revision", () => {
    const one = { ...REVISED, sheet_count: 1, current_count: 1, superseded_count: 1,
      new_count: 0, revised_count: 1 };
    expect(issuanceLine(one)).toContain("1 current of 1 sheet");
    expect(issuanceLine(one)).not.toContain("1 sheets");
    // Asserted as the ENDING, not with a trailing space: the first draft demanded `"1 superseded
    // revision "` and red on correct output, because that clause is last and nothing follows it.
    expect(issuanceLine(one).endsWith("1 superseded revision")).toBe(true);
    expect(issuanceLine(one)).not.toContain("superseded revisions");
  });

  it("omits the revised and superseded clauses when there are none", () => {
    const fresh = { ...EMPTY, sheet_count: 3, current_count: 3, new_count: 3 };
    expect(issuanceLine(fresh)).toBe("3 current of 3 sheets · 3 never revised");
  });

  it("says so when the set is empty instead of printing four zeroes", () => {
    expect(issuanceLine(EMPTY)).toContain("No sheets in the set yet");
  });
});

describe("supersededRows", () => {
  it("names which revision was superseded, by what, and why", () => {
    // The dark half: `superseded` always carried this and was undeclared, so the register could say
    // how many sheets were superseded and never which.
    expect(supersededRows(REVISED)).toEqual([
      ["A-101", "A", "B", "2026-03-01", "ASI-01 door swap", ""],
    ]);
  });

  it("renders an import's revisions, which carry no delta detail", () => {
    const rows = supersededRows(AMBIGUOUS);
    expect(rows.length).toBe(3);
    expect(rows[0]).toEqual(["A-101", "A", "2", "", "", ""]);
  });

  it("is empty, not undefined, on a register with nothing superseded", () => {
    expect(supersededRows(EMPTY)).toEqual([]);
  });
});

describe("orderWarning", () => {
  it("is silent when every sheet's revision order is recorded", () => {
    expect(orderWarning(REVISED)).toBeNull();
    expect(orderWarning(EMPTY)).toBeNull();
  });

  /** The ordering defect, in one assertion: the two registers agree that A-101 was revised, and
   *  only one of them can say whether the CURRENT revision is a recorded fact. */
  it("names the sheets whose revision order is the register's ranking", () => {
    const w = orderWarning(AMBIGUOUS) ?? "";
    expect(w).toContain("set convention");
    expect(w).toContain("rather than a recorded fact");
    expect(w).toContain("Sheets: A-101");
    expect(REVISED.sheet_index[0]!.change).toBe(AMBIGUOUS.sheet_index[0]!.change);
    expect(orderWarning(REVISED)).toBeNull();
  });

  it("caps the named sheets rather than printing a hundred", () => {
    const many = { ...AMBIGUOUS,
      order_ambiguous_sheets: Array.from({ length: 12 }, (_, i) => `A-1${String(i).padStart(2, "0")}`) };
    const w = orderWarning(many) ?? "";
    expect(w).toContain("+4 more");
    expect(w).not.toContain("A-109,");
  });
});

describe("registerSuspect", () => {
  it("flags only the register whose ordering is a ranking", () => {
    expect(registerSuspect(AMBIGUOUS)).toBe(true);
    expect(registerSuspect(REVISED)).toBe(false);
    expect(registerSuspect(EMPTY)).toBe(false);
  });
});

describe("sheetHistory", () => {
  it("reads a sheet's history out of the two lists the register already states", () => {
    const h = sheetHistory(REVISED, "A-101");
    expect(h.map((r) => r.revision)).toEqual(["A", "B"]);
    expect(h[1]!.instrument?.ref).toBe("CCD-003");
  });

  it("returns just the current revision for a never-revised sheet", () => {
    expect(sheetHistory(REVISED, "A-102").map((r) => r.revision)).toEqual(["0"]);
  });

  it("is empty for a sheet the register does not hold", () => {
    expect(sheetHistory(REVISED, "Z-999")).toEqual([]);
  });
});

/** The consumer, at source level — the same bargain and limit the sibling read-modules record. */
describe("the report centre reads it", () => {
  const panel = readFileSync(resolve(__dirname, "reportCenter.ts"), "utf8");

  it("renders the issuance line, the order warning and the superseded table", () => {
    expect(panel).toContain('from "./drawingRegisterReadings"');
    expect(panel).toContain("issuanceLine(d)");
    expect(panel).toContain("orderWarning(d)");
    expect(panel).toContain("supersededRows(d)");
  });

  it("no longer prints the register's five bare counts", () => {
    const code = panel.split("\n").filter((l) => {
      const t = l.trim();
      return !t.startsWith("//") && !t.startsWith("*") && !t.startsWith("/*");
    });
    expect(code.length, "the comment stripper kept every line").toBeLessThan(panel.split("\n").length);
    expect(code.join("\n")).not.toContain("${d.new_count} new");
  });
});

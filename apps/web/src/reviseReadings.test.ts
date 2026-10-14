/** REVISE-DARK — the revision response, and the picker the register could not supply.
 *
 *  `FAILED` is a measured response: the tagging commit was made to raise inside
 *  `drawingset.revise_sheet` against a live server, and this is what came back once the counter
 *  moved after the commit. Before the fix the same injection returned `markups_carried: 3`.
 */
import { describe, expect, it } from "vitest";

import type { RevisionResult } from "./api/drawingSheets";
import {
  INSTRUMENTS, TONE_CSS, carryReconciles, carryVerdict, nextRev, revisionLine, sheetOptions,
} from "./reviseReadings";

/** Measured: three markups on the sheet, all tagged. */
const OK: RevisionResult = {
  drawing_id: "7ef60f17-9f40-4626-ad7b-94b4add6978a",
  revision: "1",
  delta_count: 1,
  markups_carried: 3,
  markups_to_carry: 3,
  markups_carry_failed: null,
};

/** Measured with the tagging commit injected to raise. The revision landed; nothing was tagged. */
const FAILED: RevisionResult = {
  drawing_id: "88f25e38-681d-4e6e-91ca-9eea218b5e77",
  revision: "4",
  delta_count: 4,
  markups_carried: 0,
  markups_to_carry: 3,
  markups_carry_failed: "RuntimeError",
};

const NO_MARKUPS: RevisionResult = {
  ...OK, revision: "2", delta_count: 2, markups_carried: 0, markups_to_carry: 0,
};

describe("REVISE-DARK · what the response looked like before the fix", () => {
  it("reported three markups carried over zero tagged", () => {
    // The shipped shape had only these three keys, so the screen could not have told the
    // difference — and the number it would have shown was the loop's count, not the commit's.
    const shipped = { drawing_id: FAILED.drawing_id, revision: FAILED.revision,
                      delta_count: FAILED.delta_count, markups_carried: 3 };
    expect(shipped.markups_carried).toBe(3);
    expect(FAILED.markups_carried).toBe(0);
    expect(FAILED.markups_to_carry).toBe(3);
  });
});

describe("REVISE-DARK · revisionLine", () => {
  it("states the revision and the delta count on the sheet", () => {
    expect(revisionLine(OK)).toBe("Rev 1 recorded — 1 delta(s) now on this sheet.");
    expect(revisionLine(FAILED)).toContain("Rev 4 recorded — 4 delta(s)");
  });
});

describe("REVISE-DARK · carryVerdict", () => {
  it("names the failure, the count, and what a reviewer now cannot tell", () => {
    const v = carryVerdict(FAILED);
    expect(v.tone).toBe("crit");
    expect(v.text).toContain("3 markup(s) could NOT be tagged carried-forward (RuntimeError)");
    expect(v.text).toContain("The revision is recorded");
    expect(v.text).toContain("carry no re-check flag");
  });

  it("confirms the tagging when it landed", () => {
    const v = carryVerdict(OK);
    expect(v.tone).toBe("good");
    expect(v.text).toBe("3 markup(s) tagged carried-forward — each now asks a reviewer to "
      + "re-check it against this revision.");
  });

  it("distinguishes 'nothing to carry' from 'nothing carried'", () => {
    const none = carryVerdict(NO_MARKUPS);
    expect(none.tone).toBe("");
    expect(none.text).toBe("No markups on this sheet needed carrying forward.");
    // Both have `markups_carried: 0`, and they are not the same event.
    expect(NO_MARKUPS.markups_carried).toBe(FAILED.markups_carried);
    expect(none.text).not.toBe(carryVerdict(FAILED).text);
    expect(none.tone).not.toBe(carryVerdict(FAILED).tone);
  });
});

describe("REVISE-DARK · carryReconciles", () => {
  it("is silent on both shapes the engine can actually produce", () => {
    expect(carryReconciles(OK)).toBeNull();
    expect(carryReconciles(FAILED)).toBeNull();
    expect(carryReconciles(NO_MARKUPS)).toBeNull();
  });

  it("reports a disagreement with no failure beside it rather than printing the number", () => {
    // Not reachable from the engine today. A consumer that can only report good news is what let
    // this class of defect survive, so the impossible shape is said out loud instead of rendered.
    const impossible: RevisionResult = { ...OK, markups_carried: 1, markups_to_carry: 3 };
    const n = carryReconciles(impossible)!;
    expect(n).toContain("does not reconcile: 1 tagged of 3 attempted");
    expect(n).toContain("no failure reported");
  });
});

describe("REVISE-DARK · sheetOptions", () => {
  const RECORDS = [
    { id: "d2", ref: "DWG-002", data: { sheet_number: "S-201", title: "Framing", revision: "2" } },
    { id: "d1", ref: "DWG-001", data: { sheet_number: "A-101", title: "Level 1 Plan", revision: "" } },
    { id: "d3", ref: "DWG-003", data: { number: "M-301", title: "Ductwork", revision: "B" } },
    { id: "d4", ref: "DWG-004", data: {} },
  ];

  it("labels each sheet with its number, title and current revision", () => {
    expect(sheetOptions(RECORDS).map((o) => o.label)).toEqual([
      "A-101 · Level 1 Plan · no revision",
      "DWG-004 · no revision",
      "M-301 · Ductwork · rev B",
      "S-201 · Framing · rev 2",
    ]);
  });

  it("carries the record id, which the drawing-set register does not have", () => {
    // `drawingset.register` emits `ref` and `sheet_number` and no record id, and the revise route
    // is keyed by the id — so the picker has to come from the module records.
    expect(sheetOptions(RECORDS).map((o) => o.id).sort()).toEqual(["d1", "d2", "d3", "d4"]);
  });

  it("falls back to the ref when no sheet number is recorded", () => {
    expect(sheetOptions(RECORDS).find((o) => o.id === "d4")!.label).toContain("DWG-004");
  });

  it("names an unnumbered, unreferenced record rather than rendering a blank option", () => {
    expect(sheetOptions([{ id: "x", data: {} }])[0]!.label).toBe("(unnumbered) · no revision");
  });
});

describe("REVISE-DARK · nextRev", () => {
  it("suggests the next numeric or alphabetic revision", () => {
    expect(nextRev("0")).toBe("1");
    expect(nextRev("2")).toBe("3");
    expect(nextRev("9")).toBe("10");
    expect(nextRev("A")).toBe("B");
    expect(nextRev("")).toBe("1");
  });

  it("declines to guess rather than reordering the set", () => {
    // `_rev_key` in the engine ranks alpha-only revisions BEFORE numeric ones, so a wrong guess
    // moves which revision counts as current. "" means "the user types it".
    expect(nextRev("Z")).toBe("");
    expect(nextRev("1.A")).toBe("");
    expect(nextRev("P2")).toBe("");
  });
});

describe("REVISE-DARK · INSTRUMENTS and TONE_CSS", () => {
  it("offers 'no instrument' as the first option — a drafting correction cites nothing", () => {
    expect(INSTRUMENTS[0]).toBe("");
    expect(INSTRUMENTS).toContain("ASI");
    expect(INSTRUMENTS).toContain("Addendum");
  });

  it("is a literal tone map", () => {
    expect(TONE_CSS.crit).toBe("var(--status-crit)");
    expect(TONE_CSS[""]).toBe("");
  });
});

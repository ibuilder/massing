import { describe, expect, it } from "vitest";
import type { CxCell, CxMatrix } from "../../api/types";
import { cxCell, cxCellTitle, cxHandoffNote, cxLegend, cxParity, cxPhaseNote, cxRowPct }
  from "./cxMatrixRead";

/** The cell the engine serves for FLAT-A — ten Functional tests, all tested by the contractor,
 *  five Conditional, two Pass, one Fail, two with nothing recorded. Measured, not invented:
 *  `services/api/test_cx.py` asserts this exact dict. */
const ALL_TESTED: CxCell = {
  total: 10, tested: 10, accepted: 0, pass: 2, fail: 1, conditional: 5, no_result: 2,
};
/** FLAT-B — ten Functional tests and nothing done at all. */
const NOT_STARTED: CxCell = {
  total: 10, tested: 0, accepted: 0, pass: 0, fail: 0, conditional: 0, no_result: 10,
};
const DONE: CxCell = {
  total: 4, tested: 4, accepted: 4, pass: 4, fail: 0, conditional: 0, no_result: 0,
};

const mx = (over: Partial<CxMatrix> = {}): CxMatrix => ({
  systems: [], phases: ["Pre-Functional", "Functional", "Integrated Systems", "TAB", "Retro-Cx"],
  extra_phases: [], system_count: 0, note: "n", test_result_basis: "b", ...over,
});

describe("cxCell — the four result states and the two workflow halves", () => {
  it("renders accepted/total first, because that is what a Cx agent reads first", () => {
    expect(cxCell(DONE)).toMatch(/^4\/4/);
  });

  it("DISTINGUISHES all-tested from not-started, which was the live defect", () => {
    // The shipped cell was `${accepted}/${total}` + a ✗ for fails. Both of these are `0/10`, so
    // the only difference on screen was the single Fail — delete that test and the two rows were
    // byte-identical. This is the assertion that fails if the fix is reverted.
    expect(cxCell(ALL_TESTED)).not.toBe(cxCell(NOT_STARTED));
    expect(cxCell(ALL_TESTED)).toContain("t10");
    expect(cxCell(NOT_STARTED)).not.toContain("t0");
  });

  it("stays distinct when the one Fail is removed — the fail mark is not what carries it", () => {
    // The pre-fix rendering was distinguishable ONLY by the ✗. Removing it proves the new cell
    // does not lean on the same accident.
    const noFail: CxCell = { ...ALL_TESTED, fail: 0, no_result: 3 };
    expect(noFail.pass + noFail.fail + noFail.conditional + noFail.no_result).toBe(noFail.total);
    expect(cxCell(noFail)).not.toBe(cxCell(NOT_STARTED));
  });

  it("shows the conditional count, which was in no bucket at all", () => {
    expect(cxCell(ALL_TESTED)).toContain("⊙5");
  });

  it("omits t when tested equals accepted — nothing is in between to report", () => {
    expect(cxCell(DONE)).not.toContain("t");
  });

  it("omits a zero bucket rather than printing four zeroes in a table cell", () => {
    expect(cxCell(DONE)).toBe("4/4 ✓4");
  });

  it("is — for a phase with no test, which is not the same as a cell of zeroes", () => {
    expect(cxCell(null)).toBe("—");
    expect(cxCell(undefined)).toBe("—");
    expect(cxCell({ ...NOT_STARTED, total: 0, no_result: 0 })).toBe("0/0");
  });

  it("is plain text — reportCenter/operations interpolate into innerHTML", () => {
    for (const c of [ALL_TESTED, NOT_STARTED, DONE, null]) {
      expect(cxCell(c)).not.toMatch(/[<>]/);
    }
  });
});

describe("cxCellTitle — the marks spelled out", () => {
  it("names who the cell is waiting on", () => {
    const t = cxCellTitle(ALL_TESTED);
    expect(t).toContain("0 accepted by the Owner");
    expect(t).toContain("10 tested and awaiting acceptance");
  });

  it("says all accepted when it is, instead of 'awaiting 0'", () => {
    expect(cxCellTitle(DONE)).toContain("all accepted by the Owner");
    expect(cxCellTitle(DONE)).not.toContain("awaiting");
  });

  it("lists every non-zero result state in words", () => {
    const t = cxCellTitle(ALL_TESTED);
    for (const s of ["1 failed", "5 conditional", "2 passed", "2 no result yet"]) {
      expect(t).toContain(s);
    }
  });

  it("says no results recorded rather than listing nothing", () => {
    expect(cxCellTitle({ ...NOT_STARTED, no_result: 0, total: 0 }))
      .toContain("no results recorded");
  });

  it("answers for an absent cell too", () => {
    expect(cxCellTitle(null)).toContain("No test recorded");
  });
});

describe("cxLegend", () => {
  it("explains every mark the cell can print", () => {
    const l = cxLegend();
    for (const m of ["t =", "✗", "⊙", "✓"]) expect(l).toContain(m);
  });

  it("says what accepted means, since complete_pct is Owner acceptance", () => {
    expect(cxLegend()).toContain("Owner acceptance");
  });
});

describe("cxPhaseNote — the extra columns are a data finding, not a layout quirk", () => {
  it("is null when the five phases covered everything", () => {
    expect(cxPhaseNote(mx())).toBeNull();
  });

  it("names the unspecified bucket for a test saved with no phase", () => {
    const n = cxPhaseNote(mx({ extra_phases: ["(unspecified)"] }));
    expect(n).toContain("no test type at all");
    expect(n).toContain("(unspecified)");
  });

  it("names a free-form phase and counts it", () => {
    const n = cxPhaseNote(mx({ extra_phases: ["Seasonal"] }));
    expect(n).toContain("Seasonal");
    expect(n).toContain("1 test type(s) outside the standard five");
  });

  it("reports both causes when both are present, measured as the engine serves them", () => {
    const n = cxPhaseNote(mx({ extra_phases: ["(unspecified)", "Seasonal"] }))!;
    expect(n).toContain("no test type at all");
    expect(n).toContain("Seasonal");
    expect(n).toContain("every test counted in a row total is on");
  });

  it("survives a response with no extra_phases key at all", () => {
    expect(cxPhaseNote({ ...mx(), extra_phases: undefined as unknown as string[] })).toBeNull();
  });
});

describe("cxParity — the row total against the cells on screen", () => {
  const row = (over: Record<string, unknown> = {}) => ({
    system: "CHW", assets: 0, tests: 2, tested: 0, accepted: 0, conditional: 0, failed: 0,
    complete_pct: 0, phases: {} as Record<string, CxCell | null>, ...over,
  });

  it("is null when every counted test has a column", () => {
    const cell: CxCell = { total: 2, tested: 0, accepted: 0, pass: 0, fail: 0, conditional: 0, no_result: 2 };
    expect(cxParity(mx({ systems: [row({ phases: { "Pre-Functional": cell } })] }))).toBeNull();
  });

  it("reports the shortfall the pre-fix engine produced", () => {
    // Measured: a system with one unphased test and one 'Seasonal' test reported `tests: 2` above
    // cells summing to 1, because the free-form phase was in no column.
    const cell: CxCell = { total: 1, tested: 0, accepted: 0, pass: 0, fail: 0, conditional: 0, no_result: 1 };
    const p = cxParity(mx({ systems: [row({ phases: { "Pre-Functional": cell } })] }))!;
    expect(p).toContain("CHW (2 counted, 1 shown)");
    expect(p).toContain("1 row(s)");
  });

  it("caps the list and says how many more", () => {
    const rows = Array.from({ length: 7 }, (_, i) => row({ system: `S${i}` }));
    const p = cxParity(mx({ systems: rows }))!;
    expect(p).toContain("and 2 more");
  });

  it("does not count a phase the response left out of `phases`", () => {
    // The parity question is specifically "is it on screen", so a cell present in the row but
    // absent from the column list must still read as a shortfall.
    const cell: CxCell = { total: 2, tested: 0, accepted: 0, pass: 0, fail: 0, conditional: 0, no_result: 2 };
    const p = cxParity(mx({ systems: [row({ phases: { Seasonal: cell } })] }))!;
    expect(p).toContain("2 counted, 0 shown");
  });
});

describe("cxHandoffNote — the chart's one actionable total", () => {
  const sys = (over: Record<string, unknown> = {}) => ({
    system: "AHU-1", assets: 2, tests: 10, tested: 10, accepted: 0, conditional: 5, failed: 1,
    complete_pct: 0, phases: {} as Record<string, CxCell | null>, ...over,
  });

  it("is null on an empty chart rather than printing a row of zeroes", () => {
    expect(cxHandoffNote(mx({ systems: [sys({ tests: 0, tested: 0, conditional: 0, failed: 0 })] })))
      .toBeNull();
  });

  it("separates awaiting-acceptance from not-started", () => {
    const n = cxHandoffNote(mx({ systems: [sys(), sys({ system: "AHU-2", tested: 0, conditional: 0, failed: 0 })] }))!;
    expect(n).toContain("20 test(s)");
    expect(n).toContain("10 tested");
    expect(n).toContain("10 awaiting Owner acceptance");
    expect(n).toContain("10 not started");
  });

  it("omits both gap clauses when the Owner has signed everything off", () => {
    const n = cxHandoffNote(mx({ systems: [sys({ accepted: 10, conditional: 0, failed: 0 })] }))!;
    expect(n).not.toContain("awaiting");
    expect(n).not.toContain("not started");
  });

  it("carries the conditional and failed totals", () => {
    const n = cxHandoffNote(mx({ systems: [sys()] }))!;
    expect(n).toContain("5 conditional");
    expect(n).toContain("1 failed");
  });
});

describe("cxRowPct", () => {
  it("says what the percentage is OVER, since it is Owner acceptance and not progress", () => {
    expect(cxRowPct({
      system: "AHU-1", assets: 2, tests: 10, tested: 10, accepted: 0, conditional: 5, failed: 1,
      complete_pct: 0, phases: {},
    })).toBe("0% accepted");
  });
});

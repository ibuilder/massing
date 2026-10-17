/** CAPTABLE-PIPELINE — the Commit column and the total beneath it.
 *
 *  `MEASURED` is a response read back from a live server on the scenario `capital.cap_table`'s own
 *  docstring describes: one committed LP at $6M and one $10M prospect. `UNTOUCHED` is the other
 *  reading of the same shape — nobody has run the workflow, so the stamped `prospect` carries no
 *  information and every row counts.
 */
import { describe, expect, it } from "vitest";

import type { CapTable } from "../api/finance";
import {
  TONE_CSS, commitColumnTotal, commitHeadline, commitReconciles, ownershipRows, stateLabel,
  workflowNote,
} from "./capTableRead";

const money = (n: number) => `$${n.toLocaleString("en-US")}`;

const MEASURED: CapTable = {
  investor_count: 2,
  total_commitment: 6000000,
  pipeline_commitment: 10000000,
  workflow_in_use: true,
  total_contributed: 3000000,
  total_distributed: 0,
  total_unreturned: 3000000,
  by_class: { LP: 6000000 },
  rows: [
    { investor: "Real LP", investor_class: "LP", commitment: 6000000,
      counts_toward_ownership: true, ownership_pct: 100.0, contributed: 3000000,
      distributed: 0, unreturned: 3000000, status: "committed", id: "r1" },
    { investor: "Big Prospect", investor_class: "LP", commitment: 10000000,
      counts_toward_ownership: false, ownership_pct: 0.0, contributed: 0,
      distributed: 0, unreturned: 0, status: "prospect", id: "r2" },
  ],
};

/** Nobody has run `commit`, so every row is the stamped initial state and every row counts. */
const UNTOUCHED: CapTable = {
  ...MEASURED,
  total_commitment: 16000000,
  pipeline_commitment: 0,
  workflow_in_use: false,
  by_class: { LP: 16000000 },
  rows: MEASURED.rows.map((r) => ({
    ...r, counts_toward_ownership: true, status: "prospect",
    ownership_pct: Number(((100 * r.commitment) / 16000000).toFixed(4)),
  })),
};

const EMPTY: CapTable = {
  investor_count: 0, total_commitment: 0, pipeline_commitment: 0, workflow_in_use: false,
  total_contributed: 0, total_distributed: 0, total_unreturned: 0, by_class: {}, rows: [],
};

describe("CAPTABLE-PIPELINE · the table as it was", () => {
  it("rendered a Commit column of $16,000,000 under a Total row of $6,000,000", () => {
    const column = MEASURED.rows.reduce((s, r) => s + r.commitment, 0);
    expect(money(column)).toBe("$16,000,000");
    expect(money(MEASURED.total_commitment)).toBe("$6,000,000");
    // The difference was published and undeclared.
    expect(column - MEASURED.total_commitment).toBe(MEASURED.pipeline_commitment);
  });
});

describe("CAPTABLE-PIPELINE · commitReconciles", () => {
  it("holds on every shape the engine produces", () => {
    expect(commitReconciles(MEASURED)).toBe(true);
    expect(commitReconciles(UNTOUCHED)).toBe(true);
    expect(commitReconciles(EMPTY)).toBe(true);
  });

  it("is false when the two totals stop accounting for the column", () => {
    // Not reachable from the engine — asserted on the backend across four fixtures. Checked here
    // because the screen is where the two numbers meet, and a column that silently stops adding up
    // is the defect this whole item is.
    expect(commitReconciles({ ...MEASURED, pipeline_commitment: 0 })).toBe(false);
  });
});

describe("CAPTABLE-PIPELINE · commitHeadline", () => {
  it("names the committed total, the uncommitted interest, and why the column differs", () => {
    const h = commitHeadline(MEASURED, money);
    expect(h.tone).toBe("warn");
    expect(h.text).toContain("$6,000,000 COMMITTED across 1 investor(s)");
    expect(h.text).toContain("plus $10,000,000 of uncommitted interest from 1 more");
    expect(h.text).toContain("sums to $16,000,000 and this total does not");
  });

  it("says the column and the total are the same money when nothing is uncommitted", () => {
    const h = commitHeadline(UNTOUCHED, money);
    expect(h.tone).toBe("good");
    expect(h.text).toContain("$16,000,000 committed across 2 investor(s)");
    expect(h.text).toContain("the same money");
  });

  it("distinguishes an empty register from a fully committed one", () => {
    const e = commitHeadline(EMPTY, money);
    expect(e.tone).toBe("");
    expect(e.text).toBe("No investors recorded yet.");
    expect(e.text).not.toBe(commitHeadline(UNTOUCHED, money).text);
  });
});

describe("CAPTABLE-PIPELINE · workflowNote", () => {
  it("names the investors holding 0% and why, when the workflow IS in use", () => {
    const n = workflowNote(MEASURED)!;
    expect(n).toContain("1 investor(s) hold 0% because their interest is not committed");
    expect(n).toContain("(Big Prospect)");
    expect(n).toContain("shown rather than dropped");
  });

  it("says the states are being IGNORED when nobody has run the workflow", () => {
    // The opposite reading of the same 0%/100% arithmetic, and the one a reader cannot guess.
    const n = workflowNote(UNTOUCHED)!;
    expect(n).toContain("No investor has been moved off the initial `prospect` state");
    expect(n).toContain("EVERY recorded interest is counted as ownership");
    expect(n).not.toBe(workflowNote(MEASURED));
  });

  it("is silent when the workflow is in use and every row counts", () => {
    expect(workflowNote({
      ...MEASURED, pipeline_commitment: 0, total_commitment: 6000000,
      investor_count: 1, rows: [MEASURED.rows[0]!],
    })).toBeNull();
    expect(workflowNote(EMPTY)).toBeNull();
  });
});

describe("CAPTABLE-PIPELINE · ownershipRows", () => {
  it("carries the state and the ownership flag the table never showed", () => {
    const rows = ownershipRows(MEASURED);
    expect(rows.map((r) => r.investor)).toEqual(["Real LP", "Big Prospect"]);
    expect(rows[0]).toMatchObject({ state: "committed", pct: "100%", counts: true, tone: "" });
    expect(rows[1]).toMatchObject({ state: "prospect — not ownership", counts: false, tone: "warn" });
  });

  it("does not print a non-owner's 0% as a measurement", () => {
    // `ownership_pct` is 0 for a row that does not count, which is NOT the same as a committed
    // investor who happens to hold nothing — so the cell is a dash, not a number.
    expect(ownershipRows(MEASURED)[1]!.pct).toBe("—");
  });

  it("keeps the engine's order rather than re-sorting", () => {
    // `cap_table` already puts owners first and then by size, and the docstring records why:
    // sorting on commitment alone put the $10M prospect at the TOP as the largest apparent owner.
    const reversed: CapTable = { ...MEASURED, rows: [...MEASURED.rows].reverse() };
    expect(ownershipRows(reversed).map((r) => r.investor)).toEqual(["Big Prospect", "Real LP"]);
  });

  it("names an investor with no name rather than rendering a blank cell", () => {
    expect(ownershipRows({ ...MEASURED, rows: [
      { ...MEASURED.rows[0]!, investor: undefined, ref: "INV-007" }] })[0]!.investor)
      .toBe("INV-007");
    expect(ownershipRows({ ...MEASURED, rows: [
      { ...MEASURED.rows[0]!, investor: undefined, ref: undefined }] })[0]!.investor)
      .toBe("(unnamed)");
  });
});

describe("CAPTABLE-PIPELINE · stateLabel", () => {
  it("marks the stamped initial state as carrying no information", () => {
    expect(stateLabel(MEASURED.rows[1]!, false)).toBe("prospect (workflow unused)");
  });

  it("marks a non-owning state for what it costs the row", () => {
    expect(stateLabel(MEASURED.rows[1]!, true)).toBe("prospect — not ownership");
    expect(stateLabel(MEASURED.rows[0]!, true)).toBe("committed");
  });

  it("renders a dash for no state at all", () => {
    expect(stateLabel({ ...MEASURED.rows[0]!, status: undefined }, true)).toBe("—");
    expect(stateLabel({ ...MEASURED.rows[0]!, status: "" }, false)).toBe("—");
  });
});

describe("CAPTABLE-PIPELINE · commitColumnTotal", () => {
  it("gives the Commit column a total of its own that is true", () => {
    expect(commitColumnTotal(MEASURED, money)).toBe(
      "Column total $16,000,000 = $6,000,000 committed + $10,000,000 uncommitted.");
  });

  it("is silent when the existing total already accounts for the column", () => {
    expect(commitColumnTotal(UNTOUCHED, money)).toBeNull();
    expect(commitColumnTotal(EMPTY, money)).toBeNull();
  });
});

describe("CAPTABLE-PIPELINE · TONE_CSS", () => {
  it("is a literal tone map", () => {
    expect(TONE_CSS.warn).toBe("var(--status-warn)");
    expect(TONE_CSS[""]).toBe("");
  });
});

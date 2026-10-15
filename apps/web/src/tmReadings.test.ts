import { readFileSync } from "node:fs";
import { resolve } from "node:path";

import { describe, expect, it } from "vitest";

import {
  hasUnacceptedClaims, type TmSummary, unbilledCaveat, unbilledLine, unbilledSplit,
} from "./tmReadings";

/** Shaped from `tm.summarize`'s own output. The three fixtures below are the three cases measured
 *  on the engine when this was found — four $30k/$15k tickets moved through `eticket`'s states. */
const base: TmSummary = {
  ticket_count: 2, labor_total: 60000, material_total: 20000, equipment_total: 10000,
  grand_total: 90000, billed_total: 0, unbilled_total: 90000,
  by_status: {},
  // The set the server derives from the shipped `eticket` workflow, asserted against the module in
  // `services/api/test_eticket_tm.py`. `billed` is in it -- accepted AND invoiced.
  accepted_states: ["billed", "gc_signed"],
  workflow_overridden: false,
  rows: [],
};

/** Measured: `{grand_total: 90000, unbilled_total: 90000, by_status: {draft: 90000}}`.
 *  Nobody has signed anything. Not a claim against anyone. */
const ALL_DRAFT: TmSummary = { ...base, by_status: { draft: 90000 } };

/** Measured: `{grand_total: 90000, unbilled_total: 90000, by_status: {gc_signed: 90000}}`.
 *  The GC has accepted every dollar of it — `gc_sign` is party GC and requires `gc_approved_by`.
 *  **Byte-identical to ALL_DRAFT on the old card.** */
const ALL_ACCEPTED: TmSummary = { ...base, by_status: { gc_signed: 90000 } };

/** Measured: one ticket in each state. The split exists in the response and was discarded. */
const MIXED: TmSummary = {
  ...base, ticket_count: 4, grand_total: 90000, billed_total: 10000, unbilled_total: 80000,
  by_status: { billed: 10000, gc_signed: 40000, super_signed: 15000, draft: 25000 },
};

describe("unbilledSplit", () => {
  it("partitions the unbilled total across the states that compose it", () => {
    expect(unbilledSplit(MIXED)).toEqual({
      accepted: 40000, subSigned: 15000, unsigned: 25000, other: 0, reconciles: true,
      acceptanceKnown: true, labelsShipped: true,
    });
  });

  it("excludes `billed` — the split explains the UNBILLED figure, not the grand total", () => {
    const sp = unbilledSplit(MIXED);
    expect(sp.accepted + sp.subSigned + sp.unsigned + sp.other).toBe(MIXED.unbilled_total);
    expect(sp.accepted + sp.subSigned + sp.unsigned + sp.other).not.toBe(MIXED.grand_total);
  });

  it("reports a state it cannot place rather than folding it into a named bucket", () => {
    // The shape `by_status` would otherwise hide: a module whose workflow grows a state.
    const extra: TmSummary = { ...base, unbilled_total: 90000,
      by_status: { gc_signed: 50000, owner_disputed: 40000 } };
    const sp = unbilledSplit(extra);
    expect(sp.other).toBe(40000);
    expect(sp.accepted).toBe(50000);
    expect(sp.reconciles).toBe(true);
  });

  it("says so when the per-state amounts do not account for the figure", () => {
    // Not hypothetical in kind: `unbilled_total` is `grand - billed`, computed independently of
    // `by_status`, so the two CAN disagree and nothing on the server reconciles them.
    const short: TmSummary = { ...base, unbilled_total: 90000, by_status: { draft: 60000 } };
    expect(unbilledSplit(short).reconciles).toBe(false);
  });

  it("tolerates a half-cent, because each bucket is rounded on its own", () => {
    const rounded: TmSummary = { ...base, unbilled_total: 90000.01,
      by_status: { draft: 45000.0, gc_signed: 45000.0 } };
    expect(unbilledSplit(rounded).reconciles).toBe(true);
  });

  it("treats a missing or malformed breakdown as zero, not as NaN", () => {
    const bad = { ...base, by_status: { draft: null, gc_signed: "40000" } } as unknown as TmSummary;
    const sp = unbilledSplit(bad);
    expect(sp.unsigned).toBe(0);
    expect(sp.accepted).toBe(0);
    expect(Number.isNaN(sp.other)).toBe(false);
  });
});

describe("the acceptance set is the server's, not three names written out here", () => {
  it("follows a renamed acceptance state instead of looking for `gc_signed`", () => {
    // What a project that overrode its workflow actually returns. The first draft of `tmReadings`
    // hardcoded `gc_signed`, so this $50,000 would have landed in "other states" — honest, and
    // useless, on a card whose whole job is to say what the GC has accepted.
    const renamed: TmSummary = { ...base, unbilled_total: 90000, workflow_overridden: true,
      accepted_states: ["billed", "owner_accepted"],
      by_status: { owner_accepted: 50000, field_signed: 40000 } };
    const sp = unbilledSplit(renamed);
    expect(sp.accepted).toBe(50000);
    expect(sp.other).toBe(40000);
    expect(sp.labelsShipped).toBe(false);
    expect(unbilledLine(renamed)).toContain("$50,000 GC-accepted");
  });

  it("claims nothing as accepted when the server did not state the set", () => {
    // `null` is not `[]`. A screen that treated "nobody resolved it" as "nothing is accepted" would
    // print $90,000 of GC-accepted exposure as unsigned drafts — the original defect, inverted and
    // worse, because it understates what is owed.
    const blind: TmSummary = { ...base, accepted_states: null,
      by_status: { gc_signed: 90000 } };
    const sp = unbilledSplit(blind);
    expect(sp.acceptanceKnown).toBe(false);
    expect(sp.accepted).toBe(0);
    expect(sp.unsigned).toBe(0);
    expect(sp.other).toBe(90000);
    expect(unbilledCaveat(blind) ?? "").toContain("did not state");
    expect(unbilledLine(blind)).not.toContain("GC-accepted");
  });

  it("excludes `billed` even though the server lists it as accepted", () => {
    // `accepted_states` answers "has the GC accepted this", and `billed` qualifies — it is accepted
    // AND invoiced. The split explains the UNBILLED figure, so counting it would double-count the
    // one state `billed_total` already reports.
    const sp = unbilledSplit(MIXED);
    expect(MIXED.accepted_states).toContain("billed");
    expect(MIXED.by_status.billed).toBe(10000);
    expect(sp.accepted).toBe(40000);
    expect(sp.accepted + sp.subSigned + sp.unsigned + sp.other).toBe(MIXED.unbilled_total);
  });

  it("says the labels are the shipped workflow's when the project replaced it", () => {
    const over: TmSummary = { ...MIXED, workflow_overridden: true };
    const c = unbilledCaveat(over) ?? "";
    expect(c).toContain("replaced the T&M workflow");
    expect(unbilledCaveat(MIXED)).toBeNull();
  });
});

describe("unbilledLine", () => {
  /** **This is the defect, in one assertion.** Both fixtures are `unbilled_total: 90000`. */
  it("tells $90,000 of unsigned drafts apart from $90,000 the GC has accepted", () => {
    expect(ALL_DRAFT.unbilled_total).toBe(ALL_ACCEPTED.unbilled_total);
    expect(unbilledLine(ALL_DRAFT)).not.toBe(unbilledLine(ALL_ACCEPTED));
    expect(unbilledLine(ALL_DRAFT)).toContain("unsigned");
    expect(unbilledLine(ALL_ACCEPTED)).toContain("GC-accepted");
  });

  it("says 'all' when one state holds the whole figure, rather than listing two zeroes", () => {
    expect(unbilledLine(ALL_ACCEPTED)).toContain("all $90,000 GC-accepted");
    expect(unbilledLine(ALL_DRAFT)).not.toContain("$0");
  });

  it("names all three liabilities when the money is spread across them", () => {
    const line = unbilledLine(MIXED);
    expect(line).toContain("unbilled $80,000");
    expect(line).toContain("$40,000 GC-accepted");
    expect(line).toContain("$15,000 sub-signed, not GC-accepted");
    expect(line).toContain("$25,000 unsigned");
    expect(line).not.toContain("all ");
  });

  it("prints full-precision figures, because the parts are claimed to sum to the whole", () => {
    // `money()` is the compact axis form: {500, 400, 100} would render `$1k · $0k · $100`, a
    // partition whose parts visibly do not add up. Same argument `usdCents` makes for the G702.
    const line = unbilledLine(MIXED);
    expect(line).not.toContain("k");
    expect(line).not.toContain("M");
  });

  it("never prints the unbilled figure bare", () => {
    for (const s of [ALL_DRAFT, ALL_ACCEPTED, MIXED]) {
      expect(unbilledLine(s)).toMatch(/\(|—/);
    }
  });

  it("says every ticket is billed rather than splitting a zero", () => {
    const paid: TmSummary = { ...base, billed_total: 90000, unbilled_total: 0,
      by_status: { billed: 90000 } };
    expect(unbilledLine(paid)).toContain("every ticket is billed");
  });

  it("admits the absence of a breakdown instead of calling the whole figure unsigned", () => {
    // A server that stopped sending `by_status` must not silently reclassify $90,000 as `draft`.
    const blind = { ...base, by_status: undefined } as unknown as TmSummary;
    expect(unbilledLine(blind)).toContain("no per-state breakdown");
    expect(unbilledLine(blind)).not.toContain("unsigned");
  });
});

describe("unbilledCaveat", () => {
  it("is silent when the split accounts for the figure", () => {
    expect(unbilledCaveat(MIXED)).toBeNull();
    expect(unbilledCaveat(ALL_DRAFT)).toBeNull();
    expect(unbilledCaveat(ALL_ACCEPTED)).toBeNull();
  });

  it("blames the split, not the total, when they disagree", () => {
    const short: TmSummary = { ...base, unbilled_total: 90000, by_status: { draft: 60000 } };
    const c = unbilledCaveat(short) ?? "";
    expect(c).toContain("do not sum");
    expect(c).toContain("incomplete, not the total");
  });

  it("names an unplaceable state as shown separately, not as accepted or unsigned", () => {
    const extra: TmSummary = { ...base, unbilled_total: 90000,
      by_status: { gc_signed: 50000, owner_disputed: 40000 } };
    expect(unbilledCaveat(extra) ?? "").toContain("$40,000");
  });
});

describe("hasUnacceptedClaims", () => {
  it("is false only when every unbilled dollar is GC-accepted", () => {
    expect(hasUnacceptedClaims(ALL_ACCEPTED)).toBe(false);
    expect(hasUnacceptedClaims(ALL_DRAFT)).toBe(true);
    expect(hasUnacceptedClaims(MIXED)).toBe(true);
  });
});

/** The consumer, at source level — the same bargain and the same limit `fieldLogReadings.test.ts`
 *  and `cpmRead.test.ts` record: an `if (false)` around the render would pass. What it catches is
 *  the revert. */
describe("the report centre reads it", () => {
  const panel = readFileSync(resolve(__dirname, "reportCenter.ts"), "utf8");

  it("renders the split and the caveat through this module", () => {
    expect(panel).toContain('from "./tmReadings"');
    expect(panel).toContain("unbilledLine(s)");
    expect(panel).toContain("unbilledCaveat(s)");
  });

  it("no longer prints the T&M rollup's bare unbilled total", () => {
    // Scoped to the fragment unique to THIS card, not to the word `unbilled` anywhere in the
    // file: `tmByChangeEvent` prints `unassigned`/`linked` two lines below and is a different
    // question. *A negative assertion over a whole file is a claim about every site in it.*
    const code = panel.split("\n").filter((l) => {
      const t = l.trim();
      return !t.startsWith("//") && !t.startsWith("*") && !t.startsWith("/*");
    });
    expect(code.length, "the comment stripper kept every line").toBeLessThan(panel.split("\n").length);
    expect(code.join("\n")).not.toContain("· unbilled ${money(s.unbilled_total)}</div>");
  });
});

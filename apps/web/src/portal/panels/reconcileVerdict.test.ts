import { describe, expect, it } from "vitest";

import { reconcileSuffix } from "./ledger";

/**
 * NEGATED-VERDICT, the ledger half.
 *
 * `fin_ingest.reconcile` returned `fully_reconciled: not actuals_only and not uncoded` — a verdict
 * defined by the ABSENCE of two problem lists, with nothing requiring that a cost was ever recorded.
 * The engine half is `services/api/test_fin_ingest.py`, which replays both projects it was wrong
 * about. This file asserts the SCREEN, and the case that matters is the second one: the guard this
 * panel already carried tested the sum of the four counts, so it caught the empty project and could
 * not catch the budget-only one.
 */

const rec = (o: Partial<Parameters<typeof reconcileSuffix>[0]> = {}) => ({
  fully_reconciled: false, nothing_reconciled_yet: false,
  counts: { matched: 0, budget_only: 0, actuals_only: 0, uncoded: 0 },
  ...o,
});

describe("reconcileSuffix", () => {
  it("says nothing tied out rather than 'fully reconciled' on an empty project", () => {
    expect(reconcileSuffix(rec({ nothing_reconciled_yet: true })))
      .toBe(" — no cost actuals to reconcile yet");
  });

  it("THE CASE THE OLD GUARD MISSED: a budget loaded and no invoice yet", () => {
    // Non-empty input, so the sum-of-counts test passes and the old branch fell through to the
    // flag — which was True, because both problem lists are empty. It read
    //     12 budget with no actual — fully reconciled
    // which is every job before its first pay application, under a heading reading "Period close".
    const r = rec({ nothing_reconciled_yet: true,
                    counts: { matched: 0, budget_only: 12, actuals_only: 0, uncoded: 0 } });
    expect(reconcileSuffix(r)).not.toContain("fully reconciled");
    expect(reconcileSuffix(r)).toBe(" — no cost actuals to reconcile yet");
  });

  it("REPLAY: the pre-fix SERVER response, refused by this function on its own", () => {
    // What `fin_ingest.reconcile` actually sent for the budget-only project before the guard:
    // `fully_reconciled: true`, and no `nothing_reconciled_yet` field at all. The server fix is
    // real and this is the second, independent refusal — the function recomputes from the counts it
    // already has, so it does not depend on the server being fixed. Both layers, as with the
    // classification plan's two refusals.
    const preFix = { fully_reconciled: true,
                     counts: { matched: 0, budget_only: 12, actuals_only: 0, uncoded: 0 } };
    expect(reconcileSuffix(preFix)).not.toContain("fully reconciled");
    expect(reconcileSuffix(preFix))
      .toBe(" — nothing has reconciled: no cost code carries both a budget and an actual");
  });

  it("distinguishes 'no cost data at all' from 'some, and nothing matched'", () => {
    // Both are `fully_reconciled: false`, and they are different instructions: load some actuals,
    // versus go and code the actuals you have. This is what the count test buys that the flag
    // cannot — reading the flag alone collapses them.
    expect(reconcileSuffix(rec({ counts: { matched: 0, budget_only: 0, actuals_only: 3, uncoded: 0 } })))
      .toBe(" — nothing has reconciled: no cost code carries both a budget and an actual");
    expect(reconcileSuffix(rec({ nothing_reconciled_yet: true })))
      .toBe(" — no cost actuals to reconcile yet");
  });

  it("says fully reconciled only when the server does, and the server now requires a match", () => {
    expect(reconcileSuffix(rec({ fully_reconciled: true,
      counts: { matched: 9, budget_only: 0, actuals_only: 0, uncoded: 0 } })))
      .toBe(" — fully reconciled");
  });

  it("appends nothing when there are real findings — the rows below say what they are", () => {
    expect(reconcileSuffix(rec({ counts: { matched: 4, budget_only: 1, actuals_only: 2, uncoded: 1 } })))
      .toBe("");
  });

  it("survives a response missing `counts` rather than throwing on a money screen", () => {
    // The same hazard `lineageHeading` exists for: the client's return type is a hand-written claim
    // about the server, so a shape change typechecks on both sides while disagreeing.
    expect(reconcileSuffix({})).toBe(" — no cost actuals to reconcile yet");
  });
});

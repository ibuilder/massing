import { describe, expect, it, vi } from "vitest";

import type { PanelContext } from "../panelContext";
import { renderDiligence } from "./design";

/**
 * DEAD-FIELD — the rounds that are NOT in the number the card prints.
 *
 * `approval_cycles.cycles()` drops any round with no submitted date: it cannot start a clock, so it
 * `continue`s out of the list entirely. `rounds` is therefore a count of the DATED rounds, and the
 * days split and the agency share are computed over that smaller set — while the register holds
 * more. "2 round(s) · 50d with the agency · 78.1% agency time" over a five-round application reads
 * as a complete answer to the one question this card exists to settle.
 *
 * The engine computes `rounds_undated` to say exactly that, and no consumer read it. Its sibling
 * `rounds_open` is handled a few lines above with precisely the right care — *"counted but not
 * scored"* — which is what makes the omission worth fixing rather than merely noting: the author
 * knew the shape of the problem and covered one of its two cases.
 *
 * Found by deriving the "declared response field with no reader" population after PROP-OVERRIDE
 * (#478) and RESP-ORPHAN (#479). Of the four caveat-shaped candidates checked, this is the one that
 * survived triage — `MakeReady.window_days` is the client's own request parameter echoed back,
 * `PrequalScores.not_in_pool` is already visible as a per-row `rejected` flag, and
 * `PreflightSummary.blocking_checks` is rendered in full immediately above the override button.
 * **A field with no reader is a candidate, not a defect.**
 */

const el = () => document.createElement("div");

const READINESS = {
  go: false,
  due_diligence: { total: 2, cleared: 1, flagged: 0, by_category: {}, high_risk: [] },
  entitlements: { total: 1, by_state: {}, approved: 0, pending: 1, denied: 0,
    expiring_within_180d: [] },
};

/** Two dated rounds scored; three more in the register that no clock can measure. */
const CYCLES_WITH_UNDATED = {
  available: true, status: "ok", reason: undefined,
  rounds: 2, rounds_closed: 2, rounds_open: 0, rounds_undated: 3,
  open_detail: [],
  days_with_agency: 50, days_with_applicant: 14, agency_share_pct: 78.1,
  mean_agency_turnaround_days: 25, mean_applicant_turnaround_days: 7,
  total_comments: 12, rounds_out_of_order: [], days_basis: "calendar",
};

const CYCLES_ALL_DATED = { ...CYCLES_WITH_UNDATED, rounds_undated: 0 };

const flush = async () => { for (let i = 0; i < 8; i++) await Promise.resolve(); };

function ctx(cycles: unknown) {
  const api = {
    diligenceReadiness: vi.fn().mockResolvedValue(structuredClone(READINESS)),
    entitlementReviewCycles: vi.fn().mockImplementation(() => Promise.resolve(structuredClone(cycles))),
    entitlementConditions: vi.fn().mockResolvedValue({ entitlements: [], unrecorded: [], note: "" }),
    entitlementConditionChecks: vi.fn().mockResolvedValue({ checks: [], note: "" }),
    dealAuthority: vi.fn().mockResolvedValue({ decisions: [], note: "" }),
  };
  const c = {
    root: el(),
    host: { projectId: () => "p1", api } as unknown as PanelContext["host"],
    mods: [], activeKey: "diligence",
    bar: (title: string) => { const b = el(); b.textContent = title; return b; },
    buildNav: () => undefined, renderHome: async () => undefined, openModule: async () => undefined,
    navigate: () => undefined, hasDest: () => true,
  } as unknown as PanelContext;
  return { c, api };
}

describe("the review-cycles card answers for the rounds it could not measure", () => {
  it("says how many rounds are NOT in the split", async () => {
    const { c } = ctx(CYCLES_WITH_UNDATED);
    await renderDiligence(c); await flush();
    const text = c.root.textContent ?? "";
    expect(text, "the card printed a split without saying what it excludes")
      .toMatch(/3 more round\(s\) carry no submitted date/);
    // the honest total, not just the scored one
    expect(text).toContain("2 of 5 recorded rounds");
  });

  it("says nothing when every round is dated", async () => {
    // Without this the test above passes for the wrong reason: a card that always warns would
    // satisfy it, and a permanent caveat is noise rather than an answer.
    const { c } = ctx(CYCLES_ALL_DATED);
    await renderDiligence(c); await flush();
    expect(c.root.textContent ?? "").not.toMatch(/carry no submitted date/);
  });

  it("states the day basis, because the rest of this system counts working days", async () => {
    const { c } = ctx(CYCLES_ALL_DATED);
    await renderDiligence(c); await flush();
    expect(c.root.textContent ?? "").toContain("(calendar days)");
  });
});

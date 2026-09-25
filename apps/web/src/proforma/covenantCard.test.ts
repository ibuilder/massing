import { describe, expect, it } from "vitest";

import type { ApiClient } from "../api/client";
import { day, parseActuals, renderRegister } from "./covenantCard";

/**
 * CRE-COVENANT shipped complete and `ApiClient.loanCovenants()` was callerless, so nothing had yet
 * had the chance to get its two verdicts wrong. Both are vacuous on an unevaluated register —
 * **measured through the real engine, not reasoned about**:
 *
 *     register state                                    at_risk   financial.clean
 *     2 uncomputable obligations, 2 untested covenants    false        false
 *     1 of 3 covenants tested and passing                 false        TRUE
 *
 * `at_risk` is `overdue > 0 or due_soon > 0 or breach > 0 or cure_period_open > 0` — every count it
 * reads is zero for want of inputs rather than for want of problems. `clean` is
 * `bool(tested) and all(passing)`, which fails closed only when ZERO covenants are tested.
 *
 * What is pinned here is therefore coverage-before-verdict, the three covenant states (the engine
 * keeps `cure_period_open` apart from `breach` and says why), and the four fields that make a due
 * date re-derivable — which the engine's docstring calls its purpose and which were declared nowhere
 * in `api/creDeal.ts` until this change.
 */

type Register = Awaited<ReturnType<ApiClient["loanCovenants"]>>;

const OBLIGATION = (over: Partial<Register["reporting"]["obligations"][number]> = {}) => ({
  name: "Quarterly financials", computable: true, days: 10, day_basis: "business",
  clock_start: "our_receipt", anchor_date: "2026-09-03", anchor_source: "our receipt",
  due_date: "2026-09-17",
  non_working_days_skipped: [{ date: "2026-09-05", why: "weekend" },
                             { date: "2026-09-06", why: "weekend" }],
  delivered_date: null, status: "outstanding", days_remaining: 8, risk: "ok", ...over,
});

const REG = (over: Record<string, unknown> = {}): Register => ({
  loan: { name: "Senior facility", lender: "Example Bank" },
  at_risk: false,
  summary: { overdue_filings: 0, filings_due_soon: 0, covenant_breaches: 0, in_cure_period: 0,
             untested_covenants: 0, uncomputable_obligations: 0 },
  reporting: {
    as_of: "2026-09-09", horizon_days: 90,
    note: "Due dates show their anchor, basis and skipped non-working days so a reviewer can re-derive them by hand.",
    obligations: [OBLIGATION()], upcoming: [], overdue: [], not_computable: [],
    counts: { total: 1, computable: 1, outstanding: 1, overdue: 0, due_soon: 0, filed_late: 0 },
  },
  financial: {
    as_of: "2026-09-09",
    note: "A covenant with no supplied actual is reported UNTESTED with what it needed — an untested covenant is not a passing one.",
    covenants: [{ name: "DSCR", tested: true, passing: true, status: "pass", actual: 1.41,
                  threshold: 1.25, headroom: 0.16 }],
    untested: [], counts: { total: 1, tested: 1, untested: 0, passing: 1, breach: 0, cure_period_open: 0 },
    clean: true,
  },
  ...over,
} as Register);

const mount = () => {
  const host = document.createElement("div");
  document.body.replaceChildren(host);
  return host;
};

describe("reading the actuals", () => {
  it("accepts `=` and `:`, and strips percent and thousands marks", () => {
    expect(parseActuals("dscr = 1.41\nltv: 62%\ndebt_yield = 0.09").actuals)
      .toEqual({ dscr: 1.41, ltv: 62, debt_yield: 0.09 });
  });

  it("reports a line it cannot read instead of dropping it", () => {
    // An unreadable actual is an ABSENT actual, which the engine reports as an untested covenant —
    // so a typo is indistinguishable from a figure you never had unless the client says so.
    const { actuals, skipped } = parseActuals("dscr = one point four\nltv = 0.62");
    expect(actuals).toEqual({ ltv: 0.62 });
    expect(skipped).toEqual(["dscr = one point four"]);
  });
});

describe("dates", () => {
  it("formats an ISO date", () => expect(day("2026-09-17")).toBe("17 Sep 2026"));
  it("returns the input unchanged rather than 'Invalid Date'", () => expect(day("soon")).toBe("soon"));
  it("renders an absent date as a dash, not as today", () => expect(day(null)).toBe("—"));
});

describe("coverage before verdict", () => {
  // THE SHARPEST CASE. Every count `at_risk` reads is zero because nothing could be evaluated.
  it("refuses to let `at_risk: false` stand for a register that evaluated nothing", () => {
    const t = renderRegister(mount(), REG({
      at_risk: false,
      summary: { overdue_filings: 0, filings_due_soon: 0, covenant_breaches: 0, in_cure_period: 0,
                 untested_covenants: 2, uncomputable_obligations: 2 },
      reporting: { ...REG().reporting, obligations: [], counts: { total: 2, computable: 0 },
                   not_computable: [{ name: "Quarterly financials", reason: "no anchor date" },
                                    { name: "Annual audit", reason: "no anchor date" }] },
      financial: { ...REG().financial, covenants: [], clean: false,
                   untested: [{ name: "DSCR", reason: "no actual supplied" },
                              { name: "Debt yield", reason: "no actual supplied" }],
                   counts: { total: 2, tested: 0, untested: 2, passing: 0, breach: 0, cure_period_open: 0 } },
    })).textContent ?? "";
    expect(t).toContain("Nothing in this register could be evaluated");
    expect(t).toContain("an absence of inputs, not an absence of risk");
    expect(t).toContain("0 of 2 obligations computable");
    expect(t).toContain("0 of 2 covenants tested");
    expect(t).toContain("no anchor date");
  });

  // `clean` fails closed only at ZERO tested. One tested and two not is `true`.
  it("never renders a partially-tested register as clean", () => {
    const t = renderRegister(mount(), REG({
      summary: { ...REG().summary, untested_covenants: 2 },
      financial: { ...REG().financial, clean: true,
                   untested: [{ name: "Debt yield", reason: "no actual supplied" },
                              { name: "LTV", reason: "no actual supplied" }],
                   counts: { total: 3, tested: 1, untested: 2, passing: 1, breach: 0, cure_period_open: 0 } },
    })).textContent ?? "";
    expect(t).toContain("1 of 3 covenants tested");
    expect(t).toContain("could not be tested");
    expect(t).toContain("an untested covenant is not a passing one");
  });

  it("…and says nothing of the sort when every covenant was tested", () => {
    expect(renderRegister(mount(), REG()).textContent).not.toContain("could not be tested");
  });
});

describe("the due date shows its work", () => {
  // The engine's stated purpose: "A due date a reviewer cannot re-derive by hand is not a due date."
  it("renders the anchor, the basis, the count and the skipped days", () => {
    const t = renderRegister(mount(), REG()).textContent ?? "";
    expect(t).toContain("10 business day(s) from our receipt 3 Sep 2026");
    expect(t).toContain("skipping 2 non-working day(s)");
    expect(t).toContain("5 Sep 2026 (weekend)");
    expect(t).toContain("17 Sep 2026");
  });

  // A calendar showing one of two possible dates is worse than one that admits it has two.
  it("renders BOTH readings when the two clock starts disagree", () => {
    const t = renderRegister(mount(), REG({
      reporting: { ...REG().reporting, obligations: [OBLIGATION({
        clock_start_matters: true,
        alternate_reading: { clock_start: "lender_notice", due_date: "2026-09-15",
                             days_difference: 2,
                             warning: "The two clock-start readings give different due dates — confirm the counting basis with counsel before the calendar goes live." },
      })] },
    })).textContent ?? "";
    expect(t).toContain("lender notice");
    expect(t).toContain("15 Sep 2026");
    expect(t).toContain("2 day(s) different");
    expect(t).toContain("confirm the counting basis with counsel");
  });

  it("says an obligation with no computable date is undated, not 'not due yet'", () => {
    const t = renderRegister(mount(), REG({
      reporting: { ...REG().reporting, obligations: [], counts: { total: 1, computable: 0 },
                   not_computable: [{ name: "Annual audit", reason: "no anchor date" }] },
      financial: { ...REG().financial, counts: { total: 1, tested: 1, untested: 0, passing: 1, breach: 0, cure_period_open: 0 } },
    })).textContent ?? "";
    expect(t).toContain("Annual audit");
    expect(t).toContain("no anchor date");
    expect(t).toContain("no date at all");
  });
});

describe("three covenant states, not two", () => {
  it("separates a breach inside an open cure window from one outside it, and carries the note", () => {
    const t = renderRegister(mount(), REG({
      at_risk: true,
      summary: { ...REG().summary, in_cure_period: 1 },
      financial: { ...REG().financial, clean: false,
        covenants: [{ name: "DSCR", tested: true, passing: false, status: "cure_period_open",
                      actual: 1.11, threshold: 1.25, headroom: -0.14, cure_days: 30,
                      cure_ends: "2026-10-09",
                      note: "A breach inside an open cure window is a different conversation from one outside it — this one is still curable." }],
        counts: { total: 1, tested: 1, untested: 0, passing: 0, breach: 0, cure_period_open: 1 } },
    })).textContent ?? "";
    expect(t).toContain("cure period open");
    expect(t).toContain("still curable");
    expect(t).toContain("cure ends 9 Oct 2026");
    expect(t).not.toContain("1 breach");
  });

  it("…and a curable breach does not READ like an uncured one", () => {
    // Asserting the text alone passes a card that paints both red: every word above comes from the
    // server, so the only thing the card contributes to the distinction is how it renders.
    const state = (status: string, note: string) => {
      const el = renderRegister(mount(), REG({
        financial: { ...REG().financial, clean: false,
          covenants: [{ name: "DSCR", tested: true, passing: false, status, actual: 1.11,
                        threshold: 1.25, headroom: -0.14, note }],
          counts: { total: 1, tested: 1, untested: 0, passing: 0,
                    breach: status === "breach" ? 1 : 0,
                    cure_period_open: status === "cure_period_open" ? 1 : 0 } },
      }));
      const cells = [...el.querySelectorAll<HTMLElement>("td")];
      return cells.find((c) => c.textContent?.includes(status.replace(/_/g, " ")))?.style.color ?? "";
    };
    const passing = state("pass", "");
    const curable = state("cure_period_open", "still curable.");
    const uncured = state("breach", "past its cure period.");
    for (const [label, c] of [["pass", passing], ["cure", curable], ["breach", uncured]] as const) {
      expect(c, `the ${label} state has no colour of its own`).toBeTruthy();
    }
    expect(curable, "a curable breach reads as an uncured one").not.toBe(uncured);
    expect(curable, "a curable breach reads as a PASS — worse than folding it into breach")
      .not.toBe(passing);
    expect(uncured).not.toBe(passing);
  });

  it("shows the actual against the threshold, which is what makes headroom checkable", () => {
    const t = renderRegister(mount(), REG()).textContent ?? "";
    expect(t).toContain("1.41");
    expect(t).toContain("1.25");
    expect(t).toContain("0.16");
  });
});

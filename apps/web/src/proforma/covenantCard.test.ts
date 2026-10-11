import { describe, expect, it } from "vitest";

import type { ApiClient } from "../api/client";
import { day, parseActuals, renderRegister, thresholdsOf } from "./covenantCard";

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
  it("accepts `=` and `:`, and strips thousands marks", () => {
    expect(parseActuals("dscr = 1.41\nltv: 0.62\nnoi = 1,250,000").actuals)
      .toEqual({ dscr: 1.41, ltv: 0.62, noi: 1250000 });
  });

  // THE FIRST VERSION OF THIS BLOCK ASSERTED THE DEFECT: it expected `ltv: 62%` to parse to `62`
  // under the heading "strips percent", and the engine's thresholds are FRACTIONS. So the only
  // check that could have caught the misreading had been taught it instead. A percent sign divides.
  it("divides a percent by 100, because every threshold is a fraction", () => {
    expect(parseActuals("ltv: 62%\ndebt_yield = 9%\ndscr = 1.41").actuals)
      .toEqual({ ltv: 0.62, debt_yield: 0.09, dscr: 1.41 });
  });

  it("the two readings land on opposite sides of the same threshold", () => {
    // Measured against the engine's own example register rather than reasoned about: `debt_yield`
    // is `min 0.09`, so the stripped reading PASSES with a hundredfold margin and the correct one
    // sits exactly on the line; `ltv` is `max 0.65`, so the stripped reading BREACHES a loan that
    // is inside its limit. One defect, two confident verdicts, pointing opposite ways.
    expect(parseActuals("debt_yield = 9%").actuals.debt_yield).toBe(0.09);
    expect(parseActuals("ltv = 62%").actuals.ltv).toBeLessThan(0.65);
    expect(parseActuals("ltv = 62%").actuals.ltv).toBeGreaterThan(0.6);
  });

  // AND THE PERCENT FIX WAS ITSELF HALF WRONG, found by the next review. `covenants.py` compares
  // the typed actual against a threshold the USER supplied and normalises neither, so the scale is
  // a property of the register, not of the metric. Dividing unconditionally turned
  // `occupancy = 92%` into `0.92` against `min 90` and reported a breach on a compliant property —
  // the same false breach, in a register shape nothing refuses.
  it("THE SECOND DEFECT: a per-hundred threshold keeps the typed percent as typed", () => {
    const hints = thresholdsOf({ covenants: [
      { name: "Occupancy", metric: "occupancy", direction: "min", threshold: 90 },
      { name: "LTV", metric: "ltv", direction: "max", threshold: 0.65 },
    ] });
    const { actuals } = parseActuals("occupancy = 92%\nltv = 62%", hints);
    expect(actuals).toEqual({ occupancy: 92, ltv: 0.62 });
  });

  it("falls back to dividing when the register declares no threshold for the metric", () => {
    expect(parseActuals("ltv = 62%", { dscr: 1.25 }).actuals).toEqual({ ltv: 0.62 });
    expect(parseActuals("ltv = 62%").actuals).toEqual({ ltv: 0.62 });
  });

  it("reports every percent reading, because the resolution depends on the register", () => {
    const hints = thresholdsOf({ covenants: [
      { metric: "occupancy", threshold: 90 }, { metric: "ltv", threshold: 0.65 }] });
    expect(parseActuals("occupancy = 92%\nltv = 62%\ndscr = 1.41", hints).readings)
      .toEqual(["occupancy 92% read as 92", "ltv 62% read as 0.62"]);
  });

  it("thresholdsOf survives a register that is not one", () => {
    expect(thresholdsOf(null)).toEqual({});
    expect(thresholdsOf({})).toEqual({});
    expect(thresholdsOf({ covenants: "nope" })).toEqual({});
    expect(thresholdsOf({ covenants: [null, { metric: "ltv" }, { threshold: 1 },
                                      { metric: "x", threshold: "1" }] })).toEqual({});
  });

  it("does not FUSE two numbers into a plausible third", () => {
    // `replace(/[%\s,]/g, "")` turned `1.4 1` into `1.41`, which is not a misparse the reader can
    // see — it is a different covenant verdict with no symptom. Strict matching reports the line.
    const { actuals, skipped } = parseActuals("dscr = 1.4 1\nltv = 0.62");
    expect(actuals).toEqual({ ltv: 0.62 });
    expect(skipped).toEqual(["dscr = 1.4 1"]);
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

describe("AUTHORITY-DOWNSTREAM — the covenant verdict defers to the authority gate", () => {
  const BLOCKED = { kind: "blocked" as const, blocks: [
    { fact_type: "operating_statement", why: "required fact type has no authoritative document" }] };

  it("THE POINT: the reassuring reading is withheld, in the gate's own words", () => {
    const t = renderRegister(mount(), REG(), BLOCKED).textContent ?? "";
    expect(t).toContain("no authoritative document");
    expect(t).toContain("Operating statement");
    expect(t).toContain("Verdict withheld");
    // the one sentence somebody forwards to a lender is not stated on its own
    expect(t).not.toMatch(/^.*Nothing overdue, due soon, breached or in cure among what could be evaluated\.$/m);
  });

  it("and a tested-passed reassurance with untested covenants is withheld too", () => {
    const reg = REG({
      financial: {
        as_of: "2026-09-09", note: "An untested covenant is not a passing one.",
        covenants: [{ name: "DSCR", tested: true, passing: true, status: "pass", actual: 1.41,
                      threshold: 1.25, headroom: 0.16 }],
        untested: [], clean: true,
        counts: { total: 3, tested: 1, untested: 2, passing: 1, breach: 0, cure_period_open: 0 },
      },
    }) as never;
    expect(renderRegister(mount(), reg, BLOCKED).textContent)
      .not.toContain("could not be tested");
    expect(renderRegister(mount(), reg, { kind: "clear" }).textContent)
      .toContain("could not be tested");
  });

  it("and says nothing when the gate is clear", () => {
    const t = renderRegister(mount(), REG(), { kind: "clear" }).textContent ?? "";
    expect(t).not.toContain("Withheld");
    expect(t).not.toContain("authority");
  });

  it("a BREACH still renders — the gate must not hide a finding", () => {
    const t = renderRegister(mount(), REG({
      summary: { overdue_filings: 0, covenant_breaches: 1, in_cure_period: 0 },
    }) as never, BLOCKED).textContent ?? "";
    expect(t).toContain("Withheld");
    expect(t).toContain("obligations computable");
  });

  it("an undeclared table notes that the figures are ungoverned, and withholds nothing", () => {
    const t = renderRegister(mount(), REG(), { kind: "undeclared" }).textContent ?? "";
    expect(t).toContain("not governed by a source of record");
    expect(t).not.toContain("Withheld");
  });
});

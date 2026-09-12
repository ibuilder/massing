import { describe, expect, it } from "vitest";

import {
  CERT_LINES, type Certificate, type Sheet,
  checks, consistent, line7Basis, line7Note, percentComplete, summary,
} from "./payAppReview";
import { usdCents as money } from "../../ui/charts";

/** A $100k line at 10% retainage, $50k billed previously and $20k this period — the fixture the
 *  PAY-APP over-billing bug was reproduced on, so the numbers here are the ones that actually moved. */
function fixture(): { cert: Certificate; sheet: Sheet } {
  const sheet: Sheet = {
    lines: [{
      item_no: "01", description: "Sitework", cost_code: null,
      scheduled_value: 100000, completed_prev: 50000, completed_this: 20000,
      materials_stored: 0, total_completed_stored: 70000, percent: 70,
      balance_to_finish: 30000, retainage: 7000, retainage_prev: 5000,
    }],
    totals: { scheduled: 100000, prev: 50000, this: 20000, stored: 0,
      completed: 70000, balance: 30000, retainage: 7000, retainage_prev: 5000 },
  };
  const cert: Certificate = {
    application_no: 1, period: null, retainage_released: false,
    line1_original_contract_sum: 100000,
    line2_net_change_orders: 0,
    line3_contract_sum_to_date: 100000,
    line4_total_completed_stored: 70000,
    line5_retainage: 7000,
    line6_total_earned_less_retainage: 63000,
    line7_less_previous_certificates: 45000,
    line8_current_payment_due: 18000,
    line9_balance_to_finish_incl_retainage: 37000,
  };
  return { cert, sheet };
}

describe("the certificate's own arithmetic", () => {
  it("passes every identity on a sound G702", () => {
    const { cert, sheet } = fixture();
    expect(checks(cert, sheet).filter((c) => !c.ok)).toEqual([]);
  });

  it("catches the exact corruption PAY-APP fixed: line 7 driven to zero", () => {
    // The shipped bug left line 7 at 0 and line 8 at 63,000 — the whole earned-to-date, re-billed.
    // Line 8 still equals line 6 − line 7 arithmetically, so THAT identity cannot see it. What the
    // screen catches is the provenance: line 7 no longer matches the reconstruction either, and 0 is
    // not a plausible certificate when $50k was billed in earlier periods.
    const { cert, sheet } = fixture();
    const broken: Certificate = { ...cert, line7_less_previous_certificates: 0, line8_current_payment_due: 63000 };
    expect(checks(broken, sheet).filter((c) => !c.ok)).toEqual([]);          // the identities hold
    expect(line7Basis(broken, sheet)).toBe("differs-from-reconstruction");   // the provenance does not
    expect(line7Basis(cert, sheet)).toBe("matches-reconstruction");
  });

  it("fails loudly when the sheet and line 4 disagree", () => {
    const { cert, sheet } = fixture();
    const drifted: Sheet = { ...sheet, totals: { ...sheet.totals, completed: 71000 } };
    const failed = checks(cert, drifted).filter((c) => !c.ok);
    expect(failed.map((c) => c.label)).toContain("Line 4 = the continuation sheet's completed total");
    expect(failed[0]?.detail).toContain("$71,000.00");   // to the cent, since the check is
  });

  it("fails when line 3 does not equal line 1 plus line 2", () => {
    const { cert, sheet } = fixture();
    const bad: Certificate = { ...cert, line2_net_change_orders: 5000 };   // line 3 not restated
    expect(checks(bad, sheet).map((c) => c.label).filter((_, i) => !checks(bad, sheet)[i]!.ok))
      .toContain("Line 3 = line 1 + line 2");
  });

  it("does NOT fail line 5 on a final application that released retainage", () => {
    // `release_retainage` zeroes line 5 by design while the sheet still carries the per-line amounts.
    // Asserting equality unconditionally would report a correct final certificate as broken — which
    // is worse than not checking, because it teaches the reviewer to ignore the checks.
    const { cert, sheet } = fixture();
    const final: Certificate = {
      ...cert, retainage_released: true, line5_retainage: 0,
      line6_total_earned_less_retainage: 70000, line8_current_payment_due: 25000,
      line9_balance_to_finish_incl_retainage: 30000,
    };
    expect(checks(final, sheet).filter((c) => !c.ok)).toEqual([]);
  });

  it("compares in cents, so a certificate that is right to the penny passes", () => {
    // 0.1 + 0.2 !== 0.3 in binary floating point. Comparing the raw numbers would fail this.
    const sheet: Sheet = {
      lines: [],
      totals: { scheduled: 0.3, prev: 0, this: 0.3, stored: 0, completed: 0.3,
        balance: 0, retainage: 0, retainage_prev: 0 },
    };
    const cert: Certificate = {
      application_no: 1, period: null, retainage_released: false,
      line1_original_contract_sum: 0.1, line2_net_change_orders: 0.2,
      line3_contract_sum_to_date: 0.3, line4_total_completed_stored: 0.3,
      line5_retainage: 0, line6_total_earned_less_retainage: 0.3,
      line7_less_previous_certificates: 0, line8_current_payment_due: 0.3,
      line9_balance_to_finish_incl_retainage: 0,
    };
    expect(0.1 + 0.2).not.toBe(0.3);                       // the hazard, stated
    expect(checks(cert, sheet).filter((c) => !c.ok)).toEqual([]);
  });
});

describe("money is printed to the cent", () => {
  it("keeps two decimals, because the checks compare in cents", () => {
    // `ui/charts`'s usd rounds to whole dollars. Using it here meant a certificate failing by a penny
    // rendered as two IDENTICAL numbers beside a red verdict — the screen showing no reason to
    // believe itself. This test fails against that formatter.
    expect(money(45000.01)).toBe("$45,000.01");
    expect(money(45000)).toBe("$45,000.00");
    expect(money(0.5)).toBe("$0.50");
  });

  it("marks a negative with a true minus sign, not a hyphen", () => {
    expect(money(-1234.5)).toBe("\u2212$1,234.50");
  });

  it("shows the penny that a failing check is about", () => {
    const { cert, sheet } = fixture();
    const offByAPenny: Sheet = { ...sheet, totals: { ...sheet.totals, completed: 70000.01 } };
    const failed = checks(cert, offByAPenny).filter((c) => !c.ok);
    expect(failed).toHaveLength(1);
    // The two numbers must be DISTINGUISHABLE in the message, which is the whole point.
    expect(failed[0]?.detail).toContain("$70,000.01");
    expect(failed[0]?.detail).toContain("$70,000.00");
  });
});

describe("cross-document consistency (the torn-read detector)", () => {
  it("is true when the certificate and sheet describe the same SOV", () => {
    const { cert, sheet } = fixture();
    expect(consistent(cert, sheet)).toBe(true);
  });

  it("is false when the two documents were read from different states", () => {
    const { cert, sheet } = fixture();
    expect(consistent(cert, { ...sheet, totals: { ...sheet.totals, completed: 71000 } })).toBe(false);
  });

  it("looks ONLY at the two cross-document identities, not the certificate's internal ones", () => {
    // A certificate that is internally wrong is not a torn read, and re-reading will not fix it.
    // Conflating the two would make the panel retry forever on a real engine bug.
    const { cert, sheet } = fixture();
    const internallyWrong: Certificate = { ...cert, line3_contract_sum_to_date: 999 };
    const failed = checks(internallyWrong, sheet).filter((c) => !c.ok);
    // Two, not one: restating line 3 breaks both "3 = 1 + 2" and "9 = 3 − 6". Asserting an exact
    // count here was my error, and the count is incidental — what matters is that the failures are
    // all INTERNAL and none of them is a cross-document one.
    expect(failed.length).toBeGreaterThan(0);
    expect(failed.map((c) => c.label).join(" ")).not.toContain("continuation sheet");
    expect(consistent(internallyWrong, sheet)).toBe(true);
  });

  it("does not call a final application torn just because line 5 is zero", () => {
    const { cert, sheet } = fixture();
    const final: Certificate = {
      ...cert, retainage_released: true, line5_retainage: 0,
      line6_total_earned_less_retainage: 70000, line8_current_payment_due: 25000,
      line9_balance_to_finish_incl_retainage: 30000,
    };
    expect(consistent(final, sheet)).toBe(true);
  });
});

describe("the form's shape", () => {
  it("prints all nine lines in the AIA's order", () => {
    expect(CERT_LINES.map((l) => l.no)).toEqual([1, 2, 3, 4, 5, 6, 7, 8, 9]);
  });

  it("names a key that actually exists on the certificate", () => {
    const { cert } = fixture();
    for (const l of CERT_LINES) expect(typeof cert[l.key]).toBe("number");
  });
});

describe("percent complete", () => {
  it("is the sheet's completed over its scheduled, to one decimal", () => {
    const { sheet } = fixture();
    expect(percentComplete(sheet)).toBe(70);
  });

  it("is 0 rather than NaN when nothing is scheduled", () => {
    const empty: Sheet = { lines: [], totals: { scheduled: 0, prev: 0, this: 0, stored: 0,
      completed: 0, balance: 0, retainage: 0, retainage_prev: 0 } };
    expect(percentComplete(empty)).toBe(0);
  });
});

describe("summary", () => {
  it("reports the payment due and calls a sound certificate sound", () => {
    const { cert, sheet } = fixture();
    const s = summary(cert, sheet);
    expect(s.due).toBe(18000);
    expect(s.percent).toBe(70);
    expect(s.sound).toBe(true);
    expect(s.failures).toEqual([]);
  });

  it("is NOT sound, and names the failure, when the sheet drifted from the certificate", () => {
    const { cert, sheet } = fixture();
    const s = summary(cert, { ...sheet, totals: { ...sheet.totals, completed: 71000 } });
    expect(s.sound).toBe(false);
    expect(s.failures).toHaveLength(1);
  });
});

describe("line 7 provenance", () => {
  it("explains both bases in words a reviewer can act on", () => {
    expect(line7Note("differs-from-reconstruction")).toContain("certified");
    expect(line7Note("matches-reconstruction")).toContain("re-added");
  });
});

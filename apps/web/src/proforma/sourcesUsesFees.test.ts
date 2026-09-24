import { describe, expect, it, vi } from "vitest";

import type { ApiClient } from "../api/client";
import type { ProformaResult } from "../api/types";
import { ProformaUI } from "./proforma";

/**
 * SCREEN-VS-REPORT — the deal's Sources & Uses on screen omitted the line the PDF itemises.
 *
 * `report_builders/finance.py` prints six rows: Total uses, Loan amount, **Loan fees**, Interest
 * reserve, Equity — LP, Equity — GP. This panel printed five of them. The missing one is the
 * origination points, and the reason it went unnoticed for so long is that its absence balances:
 * `proforma/solve.py` folds the fee INTO `total_uses` and funds it out of `equity`, so uses still
 * equal debt plus equity and every visible number reconciles.
 *
 * *A total that balances is not the same as a total that is explained.* On a deal with two points
 * on a $13m loan that is $260k of equity with no line of its own — the screen could tell you the
 * equity cheque and not what a quarter of a million of it bought.
 *
 * It is one of the fifty-two asymmetric DEAD-FIELD candidates: declared in `ProformaResult`,
 * rendered by the report builder, read by nothing in the web tree.
 */

const RESULT = (over: Partial<ProformaResult["sources_uses"]> = {}) => ({
  sources_uses: {
    total_uses: 20_260_000, loan_amount: 13_000_000, loan_fees: 260_000,
    interest_reserve: 410_000, equity: 7_260_000, ltc: 0.65, effective_ltc: 0.642,
    lp_contribution: 6_534_000, gp_contribution: 726_000, ...over,
  },
  returns: { project_irr: 0.141, equity_irr: 0.182, equity_multiple: 2.1, npv: 1_200_000,
    yield_on_cost: 0.068, dev_spread: 0.013, total_contributions: 7_260_000,
    total_distributions: 15_246_000 },
  waterfall: { lp_irr: 0.17, gp_irr: 0.28, lp_equity_multiple: 1.9, gp_equity_multiple: 3.1,
    lp_distributions: 12_400_000, gp_distributions: 2_846_000, style: "american" },
  operations: { stabilized_noi_annual: 1_380_000, reversion: {} },
  cash_flow: { dates: [], equity: [-7_260_000, 1_000_000], project: [], noi_monthly: [] },
} as unknown as ProformaResult);

function render(r: ProformaResult) {
  const root = document.createElement("div");
  document.body.replaceChildren(root);
  const out = document.createElement("div"); out.id = "pf-out";
  document.body.appendChild(out);
  const ui = new ProformaUI(root, {} as unknown as ApiClient, vi.fn(), () => "p1");
  (ui as unknown as { renderResult(x: ProformaResult): void }).renderResult(r);
  return out;
}

/** The label/value pairs of a `.portal-kv` grid, in document order. */
function kv(out: HTMLElement): [string, string][] {
  const cells = [...out.querySelectorAll(".portal-kv > *")];
  const pairs: [string, string][] = [];
  for (let i = 0; i + 1 < cells.length; i += 2)
    pairs.push([cells[i]!.textContent ?? "", cells[i + 1]!.textContent ?? ""]);
  return pairs;
}

describe("SCREEN-VS-REPORT: Sources & Uses on screen", () => {
  it("THE DEFECT: the origination points now have a line of their own", () => {
    const rows = kv(render(RESULT()));
    const fees = rows.find(([k]) => k.includes("Loan fees"));
    expect(fees, "the screen's Sources & Uses still omits the row the PDF itemises").toBeTruthy();
    expect(fees![1]).toContain("260,000");
  });

  it("keeps the PDF's order — fees between the loan and the interest reserve", () => {
    // Not cosmetic: the reserve is the OTHER capitalised financing cost, and reading them adjacent
    // is how a reader sees what the debt costs before it has drawn a dollar.
    const labels = kv(render(RESULT())).map(([k]) => k);
    const loan = labels.findIndex((l) => l.includes("Senior loan"));
    const fees = labels.findIndex((l) => l.includes("Loan fees"));
    const reserve = labels.findIndex((l) => l.includes("Interest reserve"));
    expect(loan).toBeGreaterThanOrEqual(0);
    expect(fees).toBeGreaterThan(loan);
    expect(reserve).toBeGreaterThan(fees);
  });

  it("says where the money already is, because the rows balance WITHOUT it", () => {
    // The reason this was invisible: uses = debt + equity holds whether or not the fee is shown.
    // The row therefore has to carry the explanation, or a reader double-counts it against uses.
    const out = render(RESULT());
    const k = [...out.querySelectorAll(".portal-kv > .k")]
      .find((e) => e.textContent?.includes("Loan fees"))!;
    expect(k.getAttribute("title")).toMatch(/inside Total uses/i);
    expect(k.getAttribute("title")).toMatch(/equity/i);

    const su = RESULT().sources_uses;
    expect(su.loan_amount + su.equity, "the fixture no longer exercises the balancing that hid this "
      + "— pick numbers where uses = debt + equity and the fee is inside both")
      .toBe(su.total_uses);
  });

  it("prints a zero-point deal as $0 rather than hiding the row", () => {
    // "Show it only when non-zero" is this repo's convention for an EXCLUSION caveat, and a fee is
    // not one: $0 of points is a fact about the debt, and a row that vanishes reads as unknown.
    const rows = kv(render(RESULT({ loan_fees: 0, total_uses: 20_000_000, equity: 7_000_000 })));
    const fees = rows.find(([k]) => k.includes("Loan fees"));
    expect(fees).toBeTruthy();
    expect(fees![1]).toContain("0");
  });
});

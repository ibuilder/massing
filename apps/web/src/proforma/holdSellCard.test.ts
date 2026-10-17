import { beforeEach, describe, expect, it, vi } from "vitest";

import type { ApiClient } from "../api/client";
import { VERDICT, coverageLine, isUnderwater, renderHoldSellCard } from "./holdSellCard";

type HoldSell = Awaited<ReturnType<ApiClient["holdSell"]>>;

const year = (n: number, irr: number | null) => ({
  hold_years: n, exit_cap: 0.06, noi_at_exit: 1_000_000 + n * 10_000,
  gross_sale: 16_000_000, loan_payoff: 8_000_000, net_proceeds_at_exit: 7_500_000,
  incremental_irr: irr, beats_hurdle: irr != null && irr >= 0.12,
});

const result = (over: Partial<HoldSell> = {}): HoldSell => ({
  computable: true,
  sell_now: { gross_sale: 16_666_667, selling_costs: 333_333, loan_payoff: 8_000_000,
              net_proceeds: 8_333_334, exit_cap: 0.06 },
  hurdle_rate: 0.12,
  assumptions: { noi_growth_pct: 3, cap_drift_bps_per_year: 0, selling_cost_pct: 0.02,
                 annual_loan_amortization: 0, capex_per_year: 0 },
  years: [year(1, 0.18), year(2, 0.16)],
  coverage: { hold_periods: 2, measured: 2, unevaluable_years: [], reason: null },
  breakeven_hold_years: 1,
  recommendation: "hold",
  best_year: year(1, 0.18),
  note: "The hold case is measured as INCREMENTAL cash flows.",
  ...over,
} as HoldSell);

describe("coverageLine — rendered on EVERY answer, not only the bad ones", () => {
  it("states full coverage in so many words", () => {
    expect(coverageLine(result()))
      .toBe("2 of 2 hold period(s) measured — the recommendation covers the whole horizon.");
  });

  it("names the periods that could not be measured, and why", () => {
    const r = result({
      years: [year(1, -0.9), year(2, null), year(3, null)],
      coverage: { hold_periods: 3, measured: 1, unevaluable_years: [2, 3],
                  reason: "selling today produces no net proceeds" },
      recommendation: "unmeasured",
    });
    expect(coverageLine(r)).toBe("1 of 3 hold period(s) measured; year(s) 2, 3 could not be "
      + "measured — selling today produces no net proceeds.");
  });

  it("is why the complete case is still printed: its absence must not read as completeness", () => {
    // Both branches return a sentence. A card that printed coverage only when it was short would
    // train a reader to read silence as "all measured" — which is the defect this item is about,
    // one layer up.
    expect(coverageLine(result())).not.toBe("");
    expect(coverageLine(result({
      coverage: { hold_periods: 2, measured: 1, unevaluable_years: [2], reason: null },
    }))).not.toBe("");
  });
});

describe("isUnderwater", () => {
  it("is true when selling today costs money, and when it nets exactly nothing", () => {
    expect(isUnderwater(result({
      sell_now: { ...result().sell_now, net_proceeds: -833_333 } }))).toBe(true);
    // zero is the boundary and it belongs on the underwater side: a zero cheque is still no cheque,
    // and `_irr` has no sign change to solve either way.
    expect(isUnderwater(result({
      sell_now: { ...result().sell_now, net_proceeds: 0 } }))).toBe(true);
  });

  it("is false for an ordinary sale", () => {
    expect(isUnderwater(result())).toBe(false);
  });
});

describe("VERDICT — the third state is not folded into either call", () => {
  it("gives `unmeasured` its own words and its own colour", () => {
    expect(VERDICT.unmeasured!.word).toContain("NO CALL");
    expect(VERDICT.unmeasured!.word).not.toContain("SELL");
    expect(VERDICT.unmeasured!.colour).not.toBe(VERDICT.sell!.colour);
    expect(VERDICT.unmeasured!.colour).not.toBe(VERDICT.hold!.colour);
  });
});

// --- the card -----------------------------------------------------------------------------------

function ctx(over: Record<string, unknown> = {}) {
  const api = { holdSell: vi.fn().mockResolvedValue(result()), ...over } as unknown as ApiClient;
  const root = document.createElement("div");
  const status: string[] = [];
  const c = { api, projectId: () => "p1", setStatus: (m: string) => status.push(m),
              ...(over.prefill ? { prefill: over.prefill as never } : {}) };
  return { root, api: api as unknown as { holdSell: ReturnType<typeof vi.fn> }, c, status };
}

const run = (host: HTMLElement) =>
  Array.from(host.querySelectorAll("button")).find((b) => b.textContent === "Compare")!;
const field = (host: HTMLElement, label: string) =>
  (Array.from(host.querySelectorAll("label")).find((l) => l.textContent?.startsWith(label))!
    .querySelector("input") as HTMLInputElement);

describe("renderHoldSellCard", () => {
  beforeEach(() => vi.clearAllMocks());

  it("prefills what the live deal already knows", () => {
    const { root, c } = ctx({ prefill: () => ({ noi: 1_000_000, cap: 0.055, sellingCostPct: 0.02 }) });
    const host = renderHoldSellCard(root, c as never);
    expect(field(host, "NOI / year").value).toBe("1000000");
    expect(field(host, "Exit cap now").value).toBe("0.055");
  });

  it("refuses locally without today's income and today's cap, in the engine's own terms", async () => {
    const { root, c, api } = ctx();
    const host = renderHoldSellCard(root, c as never);
    run(host).click();
    await Promise.resolve();
    expect(host.textContent).toContain("NOI and today's cap are both required");
    expect(api.holdSell).not.toHaveBeenCalled();
  });

  it("renders the coverage line on a COMPLETE answer too", async () => {
    const { root, c } = ctx();
    const host = renderHoldSellCard(root, c as never);
    field(host, "NOI / year").value = "1000000";
    field(host, "Exit cap now").value = "0.06";
    run(host).click();
    await Promise.resolve(); await Promise.resolve();
    expect(host.textContent).toContain("HOLD");
    expect(host.textContent).toContain("2 of 2 hold period(s) measured");
  });

  it("never prints a null IRR as a percentage, and says NO CALL rather than SELL", async () => {
    // The shipped defect, from the consumer's side. An unevaluable hold period rendered as 0.0%
    // is a measurement that was never taken, displayed as the worst possible one.
    const { root, c } = ctx({
      holdSell: vi.fn().mockResolvedValue(result({
        sell_now: { ...result().sell_now, net_proceeds: -833_333 },
        years: [year(1, -0.912), year(2, null), year(3, null)],
        coverage: { hold_periods: 3, measured: 1, unevaluable_years: [2, 3],
                    reason: "selling today produces no net proceeds" },
        breakeven_hold_years: null,
        recommendation: "unmeasured",
      })),
    });
    const host = renderHoldSellCard(root, c as never);
    field(host, "NOI / year").value = "500000";
    field(host, "Exit cap now").value = "0.06";
    run(host).click();
    await Promise.resolve(); await Promise.resolve();
    const txt = host.textContent ?? "";
    expect(txt).toContain("NO CALL");
    expect(txt).not.toContain("SELL");
    expect(txt).toContain("not measurable");
    // Year 1 DID compute, so its percentage is present — the point is that the two that did not
    // are words, not numbers. Both halves asserted, because a card that rendered everything as
    // "not measurable" would pass a one-sided check and tell a reader nothing.
    expect(txt).toContain("-91.2%");
    expect((txt.match(/not measurable/g) ?? []).length).toBe(2);
    expect(txt).toContain("Selling today costs");
    expect(txt).toContain("year(s) 2, 3 could not be measured");
  });

  it("leads with the underwater fact, because it is why the hold cannot be measured", async () => {
    const { root, c } = ctx({
      holdSell: vi.fn().mockResolvedValue(result({
        sell_now: { ...result().sell_now, net_proceeds: -833_333 },
        recommendation: "unmeasured",
        coverage: { hold_periods: 2, measured: 0, unevaluable_years: [1, 2], reason: "no net proceeds" },
      })),
    });
    const host = renderHoldSellCard(root, c as never);
    field(host, "NOI / year").value = "500000";
    field(host, "Exit cap now").value = "0.06";
    run(host).click();
    await Promise.resolve(); await Promise.resolve();
    expect(host.textContent).toContain("the debt exceeds the net sale value");
  });

  it("renders the engine's own refusal as a reason, never as a zero", async () => {
    const { root, c } = ctx({
      holdSell: vi.fn().mockResolvedValue({
        computable: false,
        reason: "needs a positive noi_annual and exit_cap_now",
      }),
    });
    const host = renderHoldSellCard(root, c as never);
    field(host, "NOI / year").value = "1";
    field(host, "Exit cap now").value = "0.06";
    run(host).click();
    await Promise.resolve(); await Promise.resolve();
    expect(host.textContent).toContain("needs a positive noi_annual");
    expect(host.textContent).not.toContain("HOLD");
  });

  it("reports a failed request as a reason", async () => {
    const { root, c } = ctx({ holdSell: vi.fn().mockRejectedValue(new Error("403 forbidden")) });
    const host = renderHoldSellCard(root, c as never);
    field(host, "NOI / year").value = "1000000";
    field(host, "Exit cap now").value = "0.06";
    run(host).click();
    await Promise.resolve(); await Promise.resolve();
    expect(host.textContent).toContain("Comparison failed: 403 forbidden");
  });
});

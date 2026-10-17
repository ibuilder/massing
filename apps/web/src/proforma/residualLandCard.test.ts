import { describe, expect, it, vi } from "vitest";

import type { ApiClient } from "../api/client";
import { applyLandBasis, landBasis, renderResidualLandCard } from "./residualLandCard";

/**
 * FIN-CALC's residual-land solve was built, routed, tested and **unreachable** — `ApiClient.residualLand()`
 * sat in `api/clientCallers.test.ts`'s `UNCALLED` list. This pins the card that reaches it, and what it
 * pins is not "the number appears": it is the **three caveats the engine returns and a panel can throw
 * away**, which is the whole of this repo's SCREEN-VS-REPORT axis.
 *
 *   1. `land_value: null` — unreachable even at $0 land. Printing a figure here would be inventing one.
 *      The engine's own note calls it *"the deal, not the dirt"*, and `at_zero_land` is the evidence.
 *   2. `converged: false` with a figure — the bisection hit its cap, so that figure is a **bracket
 *      endpoint, not a price**. A panel that prints the money and drops the flag asserts a precision it
 *      does not have.
 *   3. `bounds` — returned by the route, named in `proforma/residual.py`'s docstring, and **declared
 *      nowhere in this client** until this change. Every unread-field audit here starts from the
 *      declared interfaces, so nothing could have seen it. It is the honest answer in case 2.
 *
 * Each is asserted by its own `it`, because one test over all three passes when two of them work.
 */

type Res = Awaited<ReturnType<ApiClient["residualLand"]>>;

const OK: Res = {
  land_value: 5_250_000, achieved: 0.1501, target: "equity_irr", target_value: 0.15,
  iterations: 34, converged: true, at_zero_land: 0.31, bounds: [5_249_000, 5_251_000],
};

function mount(res: Res, currentLand: number | null = 4_000_000) {
  const root = document.createElement("div");
  document.body.replaceChildren(root);
  const residualLand = vi.fn().mockResolvedValue(res);
  const applyLandValue = vi.fn();
  const setStatus = vi.fn();
  renderResidualLandCard(root, {
    api: { residualLand } as unknown as ApiClient,
    assumptions: () => ({ cost_lines: [{ category: "land", amount: currentLand }] }),
    currentLand: () => currentLand,
    applyLandValue,
    setStatus,
  });
  const host = root.querySelector<HTMLElement>("#pf-residual-land")!;
  const buttons = [...host.querySelectorAll("button")];
  const go = buttons.find((b) => b.textContent === "Solve residual land")!;
  const apply = buttons.find((b) => b.textContent === "Apply to the deal")!;
  const out = () => host.lastElementChild!.textContent ?? "";
  return { host, go, apply, out, residualLand, applyLandValue, setStatus };
}

/** Click Solve and let the mocked promise settle. */
async function solve(go: HTMLButtonElement) {
  go.click();
  await vi.waitFor(() => expect(go.disabled).toBe(false));
}

describe("the land basis the residual is solved for", () => {
  // `proforma/residual.py::_with_land` scales the FIRST `category: "land"` line and zeroes the rest,
  // so "the land basis" is that line and not `cost_lines[0]` — which is merely what the driver form's
  // "Land $" field is bound to, true of the default assumption set and not of an adopted one.
  it("reads the first land line, wherever it sits", () => {
    expect(landBasis([{ category: "hard", amount: 20_000_000 },
                      { category: "land", amount: 4_000_000 }])).toBe(4_000_000);
  });

  it("is null when nothing is categorised as land, rather than falling back to line 0", () => {
    expect(landBasis([{ category: "hard", amount: 20_000_000 }])).toBeNull();
  });

  it("writes the residual as the TOTAL basis, zeroing any second land line", () => {
    // Left standing, a second land line makes the forward re-solve carry more land than the answer
    // allowed for — so the deal would quietly disagree with the number that produced it.
    const lines = [{ category: "land", amount: 4_000_000 }, { category: "hard", amount: 20_000_000 },
                   { category: "land", amount: 750_000 }];
    expect(applyLandBasis(lines, 5_250_000)).toBe(true);
    expect(lines.map((l) => l.amount)).toEqual([5_250_000, 20_000_000, 0]);
  });

  it("refuses when there is no land line to write to", () => {
    const lines = [{ category: "hard", amount: 20_000_000 }];
    expect(applyLandBasis(lines, 5_250_000)).toBe(false);
    expect(lines[0]!.amount).toBe(20_000_000);
  });
});

describe("residual land card", () => {
  it("renders the land price, the achieved metric and the delta against the typed land line", async () => {
    const m = mount(OK);
    await solve(m.go);
    const text = m.out();
    expect(text).toContain("$5,250,000");
    expect(text).toContain("15.0%");          // the achieved metric, in the target's own unit
    expect(text).toContain("$1,250,000");     // headroom over the $4.0m land line
    expect(text).toContain("headroom");
  });

  it("sends the target in the engine's units — a percent box becomes a fraction", async () => {
    const m = mount(OK);
    await solve(m.go);
    expect(m.residualLand).toHaveBeenCalledWith(expect.anything(), "equity_irr", 0.15, undefined);
  });

  it("sends a MULTIPLE target unscaled, because 1.8x is not 180%", async () => {
    const m = mount(OK);
    const sel = m.host.querySelector("select")!;
    sel.value = "equity_multiple"; sel.dispatchEvent(new Event("change"));
    const box = m.host.querySelectorAll<HTMLInputElement>("input")[0]!;
    box.value = "1.8";
    await solve(m.go);
    expect(m.residualLand).toHaveBeenCalledWith(expect.anything(), "equity_multiple", 1.8, undefined);
  });

  // CAVEAT 1 — infeasible. The one case where printing a number would be a false statement.
  it("refuses to print a land value when the target is unreachable at $0 land", async () => {
    const m = mount({ ...OK, land_value: null, achieved: 0.11, at_zero_land: 0.11,
                      converged: false, iterations: 0,
                      note: "target is not achievable even at $0 land — the deal, not the dirt" });
    await solve(m.go);
    const text = m.out();
    expect(text).toContain("Not achievable at any land price");
    expect(text).toContain("11.0%");               // at_zero_land, so the shortfall is quantified
    expect(text).toContain("the deal, not the dirt");
    expect(text).not.toMatch(/\$[1-9]/);           // no dollar figure but the literal "$0"
    expect(m.apply.style.display).toBe("none");    // and nothing to apply
  });

  // CAVEAT 2 + 3 — a figure that did not converge is a range, and `bounds` is the range.
  it("says a non-converged solve is a range, and reads `bounds` for it", async () => {
    const m = mount({ ...OK, converged: false, iterations: 80, bounds: [5_100_000, 5_400_000] });
    await solve(m.go);
    const text = m.out();
    expect(text).toContain("Did not converge");
    expect(text).toContain("$5,100,000");
    expect(text).toContain("$5,400,000");
    expect(text).not.toContain("Converged in");
  });

  it("degrades to 'read this as a range' when the server omits `bounds` entirely", async () => {
    const m = mount({ ...OK, converged: false, iterations: 80, bounds: undefined });
    await solve(m.go);
    expect(m.out()).toContain("Did not converge");
    expect(m.out()).toContain("range, not a price");
  });

  it("applies the solved value back into the deal", async () => {
    const m = mount(OK);
    await solve(m.go);
    expect(m.apply.style.display).not.toBe("none");
    m.apply.click();
    expect(m.applyLandValue).toHaveBeenCalledWith(5_250_000);
  });

  it("shows the route's own message when the assumption set has no land line", async () => {
    const root = document.createElement("div");
    document.body.replaceChildren(root);
    const residualLand = vi.fn().mockRejectedValue(
      new Error("assumptions carry no cost line with category 'land'"));
    renderResidualLandCard(root, {
      api: { residualLand } as unknown as ApiClient,
      assumptions: () => ({ cost_lines: [] }), currentLand: () => null,
      applyLandValue: vi.fn(), setStatus: vi.fn(),
    });
    const go = [...root.querySelectorAll("button")].find((b) => b.textContent === "Solve residual land")!;
    await solve(go);
    expect(root.textContent).toContain("no cost line with category 'land'");
  });

  it("marks a residual BELOW the typed land line as over what the target supports", async () => {
    const m = mount({ ...OK, land_value: 3_400_000 });
    await solve(m.go);
    expect(m.out()).toContain("over what the target supports");
    expect(m.out()).toContain("$600,000");
  });
});

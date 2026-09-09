import { describe, expect, it, vi } from "vitest";

import type { TmPricingReport } from "../../api/cost";
import { TM_MODULE, renderTmReport, tmPricingControl } from "./tmPricing";
import type { ModuleDef, ModuleRecord } from "../../api/client";

/**
 * TM-RATES — the claim about the SCREEN.
 *
 * `services/api/test_tm_rates.py` proves the pricing rules server-side. That is a claim about an
 * ENGINE. This is the claim about the CONTROL: an engine that correctly reports a rate variance
 * into a panel that renders only the total would satisfy the server test completely and leave the
 * user looking at a number whose disagreement with the contract rate table is invisible — which is
 * the situation this whole item exists to end.
 *
 * The four report categories are asserted individually because they are not decoration: `filled` is
 * the feature, and `variance` / `unmatched` / `unpriced` are the three ways a run declines to price
 * something. A control that silently dropped any of them would be worse than no control at all.
 */

const mod = { key: TM_MODULE, name: "eTickets", fields: [] } as unknown as ModuleDef;
const other = { key: "rfi", name: "RFIs", fields: [] } as unknown as ModuleDef;
const rec = { id: "t1", ref: "TM-001" } as unknown as ModuleRecord;

const EMPTY: TmPricingReport = {
  filled: [], variance: [], unmatched: [], unpriced: [], priced: 0,
  totals: { labor_total: 0, material_total: 0, equipment_total: 0, grand_total: 0 },
};

const FULL: TmPricingReport = {
  filled: [{ table: "labor_lines", name: "Electrician", rate: 95 }],
  variance: [{ table: "labor_lines", name: "Plumber", field: "rate", typed: 110, register: 95 },
             { table: "labor_lines", name: "Foreman", field: "amount", typed: 1045, register: 760 }],
  unmatched: [{ table: "labor_lines", name: "Glazier", register: "labor_rate" }],
  unpriced: [{ table: "labor_lines", name: "Electrician", column: "ot_hours", quantity: 2,
               reason: "the rate register holds no rate for these" }],
  priced: 2,
  totals: { labor_total: 760, material_total: 425, equipment_total: 0, grand_total: 1185 },
};

function host(rep: TmPricingReport | Error) {
  return {
    api: {
      priceTicket: vi.fn().mockImplementation(() =>
        rep instanceof Error ? Promise.reject(rep) : Promise.resolve(rep)),
    },
  } as unknown as Parameters<typeof tmPricingControl>[0] & {
    api: { priceTicket: ReturnType<typeof vi.fn> } };
}

const flush = async () => { for (let i = 0; i < 6; i++) await Promise.resolve(); };

describe("the T&M pricing control", () => {
  it("is offered on the eTicket register and nowhere else", () => {
    // A "price from the rate tables" button on an RFI is not a smaller feature, it is a wrong one.
    expect(tmPricingControl(host(EMPTY), "p1", mod, rec, () => undefined)).toBeTruthy();
    expect(tmPricingControl(host(EMPTY), "p1", other, rec, () => undefined)).toBeNull();
  });

  it("prices THIS ticket, by id", async () => {
    const h = host(FULL);
    const el = tmPricingControl(h, "p1", mod, rec, () => undefined)!;
    el.querySelector("button")!.click();
    await flush();
    expect(h.api.priceTicket).toHaveBeenCalledWith("p1", "t1");
  });

  it("shows every line it could not price, not just the total", async () => {
    const h = host(FULL);
    const el = tmPricingControl(h, "p1", mod, rec, () => undefined)!;
    el.querySelector("button")!.click();
    await flush();
    const text = el.textContent ?? "";
    expect(text, "the rate the register supplied").toContain("Electrician");
    expect(text, "a typed rate that disagrees with the register must be VISIBLE")
      .toMatch(/110.*register says.*95/);
    // The amount variance reads differently on purpose: it is not the register disagreeing, it is
    // the line's own arithmetic — an overtime premium the engine must report and not recompute away.
    expect(text, "a typed AMOUNT that disagrees with rate x quantity must be visible, and must not "
      + "be described as the register disagreeing")
      .toMatch(/amount is \$1,045 and rate × quantity is \$760/);
    expect(text, "a trade the register does not know").toContain("Glazier");
    expect(text, "hours nothing could price").toContain("ot hours");
    expect(text, "...and the REASON, since 'unpriced' now covers a per-week rate too")
      .toContain("holds no rate for these");
    expect(text).toContain("$1,185");
  });

  it("says so when a run changes nothing, instead of looking like a failure", async () => {
    // Without this the assertions above pass for the wrong reason — a control that always prints
    // its four sections would satisfy them, and an empty run would read as a broken button.
    const h = host(EMPTY);
    const el = tmPricingControl(h, "p1", mod, rec, () => undefined)!;
    el.querySelector("button")!.click();
    await flush();
    expect(el.textContent ?? "").toMatch(/Nothing changed/);
  });

  it("does NOT repaint the record out from under the report", async () => {
    // `openRecord` rebuilds the whole record view, which would destroy the report in the tick it
    // appeared. The reload is offered as a control instead, so the user keeps the finding.
    const onReload = vi.fn();
    const h = host(FULL);
    const el = tmPricingControl(h, "p1", mod, rec, onReload)!;
    el.querySelector("button")!.click();
    await flush();
    expect(onReload, "the report must survive the run that produced it").not.toHaveBeenCalled();
    const again = [...el.querySelectorAll("button")]
      .find((b) => (b.textContent ?? "").includes("Reload"));
    expect(again, "...but the stale totals above must be reloadable").toBeTruthy();
    again!.click();
    expect(onReload).toHaveBeenCalledTimes(1);
  });

  it("offers no reload when nothing moved", async () => {
    const h = host(EMPTY);
    const el = tmPricingControl(h, "p1", mod, rec, () => undefined)!;
    el.querySelector("button")!.click();
    await flush();
    expect([...el.querySelectorAll("button")].some((b) => (b.textContent ?? "").includes("Reload")))
      .toBe(false);
  });

  it("reports a failure and re-arms, rather than leaving a dead button", async () => {
    const h = host(new Error("403"));
    const el = tmPricingControl(h, "p1", mod, rec, () => undefined)!;
    const btn = el.querySelector("button") as HTMLButtonElement;
    btn.click();
    await flush();
    expect(el.textContent ?? "").toMatch(/pricing failed: 403/);
    expect(btn.disabled, "a failed run must not lock the control").toBe(false);
  });

  it("renders the report into a bare element, without the button", () => {
    // `renderTmReport` is exported so the report can be shown wherever a run happens; the split is
    // asserted rather than assumed, because an export nothing can use is not a seam.
    const box = document.createElement("div");
    renderTmReport(box, FULL);
    expect(box.textContent ?? "").toContain("Glazier");
    expect(box.querySelector("button")).toBeNull();
  });
});

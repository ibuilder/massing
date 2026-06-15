import type { ApiClient, ProformaResult } from "../api/client";

/**
 * Real-estate development finance (Proforma) view — edit the key deal drivers, solve live,
 * and read the capital stack, returns and JV waterfall. Spreadsheet-familiar but live: the
 * pure Python engine solves S&U (with interest-reserve circularity), construction loan,
 * XIRR/NPV/EM and the waterfall server-side in <100ms.
 */
const DEFAULT = {
  timing: { construction_months: 18, leaseup_months: 12, hold_years: 5, start_date: "2026-01-01" },
  cost_lines: [
    { category: "land", name: "Land", amount: 4_000_000, curve: "upfront", start_month: 0, end_month: 0 },
    { category: "hard", name: "Construction", amount: 20_000_000, curve: "scurve", start_month: 1, end_month: 17 },
    { category: "soft", name: "Soft costs", amount: 3_000_000, curve: "linear", start_month: 0, end_month: 17 },
    { category: "contingency", name: "Contingency", amount: 1_000_000, curve: "scurve", start_month: 1, end_month: 17 },
  ],
  debt: { ltc: 0.65, rate: 0.085, points: 0.01, funding: "equity_first" },
  equity: { lp_pct: 0.9, gp_pct: 0.1 },
  operations: { potential_rent_annual: 3_600_000, other_income_annual: 120_000, opex_annual: 1_300_000, stabilized_occ: 0.94, credit_loss_pct: 0.02 },
  exit: { exit_cap: 0.055, selling_cost_pct: 0.02 },
  waterfall: { pref_rate: 0.08, style: "american", clawback: false, tiers: [{ hurdle: 0.12, lp: 0.8, gp: 0.2 }, { hurdle: 0.18, lp: 0.7, gp: 0.3 }, { hurdle: null, lp: 0.6, gp: 0.4 }] },
  discount_rate: 0.1,
};

// editable drivers: [label, path, kind] — kind 'pct' shows/edits as %
type Field = [string, string, "money" | "pct" | "num"];
const FIELDS: Field[] = [
  ["Land $", "cost_lines.0.amount", "money"],
  ["Hard cost $", "cost_lines.1.amount", "money"],
  ["Soft cost $", "cost_lines.2.amount", "money"],
  ["Contingency $", "cost_lines.3.amount", "money"],
  ["LTC", "debt.ltc", "pct"],
  ["Loan rate", "debt.rate", "pct"],
  ["Constr. months", "timing.construction_months", "num"],
  ["Hold years", "timing.hold_years", "num"],
  ["Rent / yr", "operations.potential_rent_annual", "money"],
  ["OpEx / yr", "operations.opex_annual", "money"],
  ["Stab. occ", "operations.stabilized_occ", "pct"],
  ["Exit cap", "exit.exit_cap", "pct"],
  ["LP / GP", "equity.lp_pct", "pct"],
  ["Pref", "waterfall.pref_rate", "pct"],
];

function get(obj: any, path: string): any {
  return path.split(".").reduce((o, k) => o?.[k], obj);
}
function set(obj: any, path: string, val: any): void {
  const ks = path.split("."); const last = ks.pop()!;
  ks.reduce((o, k) => o[k], obj)[last] = val;
}
const money = (n: number) => "$" + Math.round(n).toLocaleString();
const pct = (n: number | null) => (n == null ? "n/a" : (n * 100).toFixed(1) + "%");

export class ProformaUI {
  private a = structuredClone(DEFAULT);
  private timer = 0;

  constructor(private root: HTMLElement, private api: ApiClient,
              private setStatus: (m: string) => void) {}

  async init() {
    this.render();
    await this.solve();
  }

  private render() {
    this.root.innerHTML = `<div class="section-title">Proforma — development underwriting</div>`;
    const form = document.createElement("div"); form.className = "pf-form";
    for (const [label, path, kind] of FIELDS) {
      const wrap = document.createElement("label"); wrap.className = "pf-field";
      wrap.innerHTML = `<span>${label}</span>`;
      const inp = document.createElement("input"); inp.type = "number"; inp.step = "any";
      const raw = get(this.a, path);
      inp.value = String(kind === "pct" ? +(raw * 100).toFixed(3) : raw);
      inp.oninput = () => {
        const v = parseFloat(inp.value); if (isNaN(v)) return;
        set(this.a, path, kind === "pct" ? v / 100 : v);
        if (path === "equity.lp_pct") set(this.a, "equity.gp_pct", 1 - v / 100);
        clearTimeout(this.timer);
        this.timer = window.setTimeout(() => this.solve(), 350);  // debounced live solve
      };
      wrap.appendChild(inp); form.appendChild(wrap);
    }
    this.root.appendChild(form);
    const out = document.createElement("div"); out.id = "pf-out";
    this.root.appendChild(out);
  }

  private async solve() {
    this.setStatus("solving proforma…");
    let r: ProformaResult | undefined;
    try { r = await this.api.solveProforma(this.a); }
    catch (e) { this.setStatus(`proforma error: ${(e as Error).message}`); return; }
    this.renderResult(r);
    this.setStatus(`equity IRR ${pct(r.returns.equity_irr)} · EM ${r.returns.equity_multiple}`);
  }

  private renderResult(r: ProformaResult) {
    const su = r.sources_uses, ret = r.returns, wf = r.waterfall;
    const kpis: [string, string][] = [
      ["Project IRR", pct(ret.project_irr)], ["Equity IRR", pct(ret.equity_irr)],
      ["Equity Mult.", `${ret.equity_multiple}×`], ["NPV", money(ret.npv)],
      ["Yield on Cost", pct(ret.yield_on_cost)], ["Dev Spread", `${Math.round(ret.dev_spread * 1e4)} bps`],
    ];
    const out = document.getElementById("pf-out")!;
    out.innerHTML =
      `<div class="kpi-grid">` +
      kpis.map(([l, v]) => `<div class="kpi"><div class="kpi-v">${v}</div><div class="kpi-l">${l}</div></div>`).join("") +
      `</div>` +
      `<div class="section-title">Sources & Uses</div>` +
      `<div class="portal-kv">` +
      `<div class="k">Total uses</div><div class="v">${money(su.total_uses)}</div>` +
      `<div class="k">Senior loan (${pct(su.ltc)})</div><div class="v">${money(su.loan_amount)}</div>` +
      `<div class="k">Interest reserve</div><div class="v">${money(su.interest_reserve)}</div>` +
      `<div class="k">Equity</div><div class="v">${money(su.equity)}</div>` +
      `<div class="k">LP / GP</div><div class="v">${money(su.lp_contribution)} / ${money(su.gp_contribution)}</div>` +
      `</div>` +
      `<div class="section-title">JV Waterfall (${wf.style})</div>` +
      `<div class="portal-kv">` +
      `<div class="k">LP</div><div class="v">IRR ${pct(wf.lp_irr)} · ${wf.lp_equity_multiple}× · ${money(wf.lp_distributions)}</div>` +
      `<div class="k">GP</div><div class="v">IRR ${pct(wf.gp_irr)} · ${wf.gp_equity_multiple}× · ${money(wf.gp_distributions)}</div>` +
      `</div>` +
      this.cashflowChart(r.cash_flow.equity);
  }

  /** inline SVG bar chart of equity cash flow (outflows during construction, inflows in ops). */
  private cashflowChart(cf: number[]): string {
    const w = 252, h = 70, pad = 4;
    const max = Math.max(1, ...cf.map((v) => Math.abs(v)));
    const bw = (w - 2 * pad) / cf.length;
    const mid = h / 2;
    const bars = cf.map((v, i) => {
      const bh = (Math.abs(v) / max) * (mid - pad);
      const x = pad + i * bw;
      const y = v >= 0 ? mid - bh : mid;
      const col = v >= 0 ? "#2ecc71" : "#e74c3c";
      return `<rect x="${x.toFixed(1)}" y="${y.toFixed(1)}" width="${Math.max(bw - 0.5, 1).toFixed(1)}" height="${bh.toFixed(1)}" fill="${col}"/>`;
    }).join("");
    return `<div class="section-title">Equity cash flow</div>` +
      `<svg viewBox="0 0 ${w} ${h}" style="width:100%;background:#1e1f22;border:1px solid var(--line);border-radius:4px">` +
      `<line x1="${pad}" y1="${mid}" x2="${w - pad}" y2="${mid}" stroke="#444" stroke-width="0.5"/>${bars}</svg>`;
  }
}

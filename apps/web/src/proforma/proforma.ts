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
              private setStatus: (m: string) => void,
              private projectId: () => string | null = () => null) {}

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
    const sens = document.createElement("div"); sens.id = "pf-sens";
    this.root.appendChild(sens);
    const mc = document.createElement("div"); mc.id = "pf-mc";
    this.root.appendChild(mc);
    this.renderDraws();
  }

  /** Actuals / draw bridge — enter actual-to-date per cost line, re-forecast IRR vs underwritten. */
  private renderDraws() {
    const host = document.createElement("div"); host.id = "pf-draws";
    const lines = this.a.cost_lines as any[];
    let html = `<div class="section-title">Actuals / Draw — re-forecast vs underwritten</div>` +
      `<table class="sens-table"><tr><th>Cost line</th><th>Budget</th><th>Actual to date</th></tr>`;
    lines.forEach((ln, i) => {
      html += `<tr><th style="text-align:left">${ln.name}</th><td>${money(ln.amount)}</td>` +
        `<td><input class="pf-actual" data-i="${i}" type="number" step="any" value="0" style="width:90px"></td></tr>`;
    });
    html += `</table><button class="file-btn" id="pf-reforecast" style="margin-top:6px">Re-forecast</button>` +
      `<div id="pf-fc-out"></div>`;
    host.innerHTML = html;
    this.root.appendChild(host);
    (host.querySelector("#pf-reforecast") as HTMLButtonElement).onclick = () => this.reforecast();
  }

  private async reforecast() {
    const inputs = [...document.querySelectorAll<HTMLInputElement>(".pf-actual")];
    const actuals = (this.a.cost_lines as any[]).map((_, i) => {
      const v = parseFloat(inputs.find((x) => +x.dataset.i! === i)?.value || "0") || 0;
      return { actual_to_date: v, committed: 0 };
    });
    this.setStatus("re-forecasting against actuals…");
    let f;
    try { f = await this.api.forecast(this.a, actuals, 9); }
    catch (e) { this.setStatus(`forecast error: ${(e as Error).message}`); return; }
    const uw = f.underwritten_returns.equity_irr, fc = f.forecast_returns.equity_irr;
    const delta = f.irr_delta == null ? "" : `${f.irr_delta >= 0 ? "+" : ""}${(f.irr_delta * 100).toFixed(1)}pp`;
    const dColor = (f.irr_delta ?? 0) >= 0 ? "#2ecc71" : "#e74c3c";
    const rows = f.lines.map((L) =>
      `<tr><th style="text-align:left">${L.name}</th><td>${money(L.budget)}</td>` +
      `<td>${money(L.actual_to_date)}</td><td>${money(L.forecast_at_completion)}</td>` +
      `<td style="color:${L.variance_to_budget > 0 ? "#e74c3c" : "#2ecc71"}">${L.variance_to_budget >= 0 ? "+" : ""}${money(L.variance_to_budget)}</td></tr>`).join("");
    document.getElementById("pf-fc-out")!.innerHTML =
      `<div class="kpi-grid" style="grid-template-columns:1fr 1fr 1fr">` +
      `<div class="kpi"><div class="kpi-v">${pct(uw)}</div><div class="kpi-l">Underwritten IRR</div></div>` +
      `<div class="kpi"><div class="kpi-v">${pct(fc)}</div><div class="kpi-l">Re-forecast IRR</div></div>` +
      `<div class="kpi"><div class="kpi-v" style="color:${dColor}">${delta}</div><div class="kpi-l">Δ IRR</div></div></div>` +
      `<table class="sens-table"><tr><th>Line</th><th>Budget</th><th>Actual</th><th>Forecast</th><th>Var</th></tr>${rows}` +
      `<tr><th style="text-align:left">TOTAL</th><td>${money(f.totals.budget)}</td><td>${money(f.totals.actual_to_date)}</td>` +
      `<td>${money(f.totals.forecast_at_completion)}</td><td style="color:${f.totals.variance_to_budget > 0 ? "#e74c3c" : "#2ecc71"}">${money(f.totals.variance_to_budget)}</td></tr></table>`;
    this.setStatus(`re-forecast IRR ${pct(fc)} (was ${pct(uw)})`);

    // bridge to the GC portal: turn this cost tree + draws into an AIA G702/G703 pay app
    const pid = this.projectId();
    if (pid) {
      const btn = document.createElement("button");
      btn.className = "file-btn"; btn.textContent = "↓ Generate G702 draw package"; btn.style.marginTop = "8px";
      btn.onclick = async () => {
        this.setStatus("generating lender draw package…");
        try {
          const actuals = [...document.querySelectorAll<HTMLInputElement>(".pf-actual")]
            .sort((a, b) => +a.dataset.i! - +b.dataset.i!)
            .map((x) => ({ actual_to_date: parseFloat(x.value) || 0 }));
          const sc = await this.api.createScenario("Draw package", pid, this.a);
          const dp = await this.api.drawPackage(sc.id, { project_id: pid, actuals, as_of_month: 9, app_no: 1 });
          this.setStatus(`SOV (${dp.sov_lines_created} lines) → G702 due $${Math.round(dp.g702.line8_current_payment_due).toLocaleString()}`);
          window.open(this.api.url(dp.g702_pdf), "_blank");
        } catch (e) { this.setStatus(`draw package error: ${(e as Error).message}`); }
      };
      document.getElementById("pf-fc-out")!.appendChild(btn);
    }
  }

  private async solve() {
    this.setStatus("solving proforma…");
    let r: ProformaResult | undefined;
    try { r = await this.api.solveProforma(this.a); }
    catch (e) { this.setStatus(`proforma error: ${(e as Error).message}`); return; }
    this.renderResult(r);
    this.setStatus(`equity IRR ${pct(r.returns.equity_irr)} · EM ${r.returns.equity_multiple}`);
    void this.renderSensitivity();
    void this.renderMonteCarlo();
  }

  /** Monte Carlo risk: sample exit cap, hard cost, and rent; show the equity-IRR distribution. */
  private async renderMonteCarlo() {
    const host = document.getElementById("pf-mc");
    if (!host) return;
    const cap = get(this.a, "exit.exit_cap") as number;
    const hard = get(this.a, "cost_lines.1.amount") as number;
    const rent = get(this.a, "operations.potential_rent_annual") as number;
    const target = 0.15;
    let mc;
    try {
      mc = await this.api.monteCarlo({
        assumptions: this.a,
        iterations: 1000,
        variables: [
          // exit cap & cost skew worse than base; rent is symmetric — a realistic downside tilt
          { path: "exit.exit_cap", dist: { kind: "triangular", low: cap - 0.005, mode: cap, high: cap + 0.012 } },
          { path: "cost_lines.1.amount", dist: { kind: "triangular", low: hard * 0.95, mode: hard, high: hard * 1.2 } },
          { path: "operations.potential_rent_annual", dist: { kind: "normal", mean: rent, std: rent * 0.06, min: rent * 0.8 } },
        ],
        metrics: ["returns.equity_irr"],
        targets: { "returns.equity_irr": target },
      });
    } catch { return; }
    const m = mc.metrics["returns.equity_irr"];
    if (!m || !m.n) return;
    const hmax = Math.max(...m.histogram.counts, 1);
    const bars = m.histogram.counts.map((c, i) => {
      const lo = m.histogram.edges[i];
      return `<span class="pf-bar" title="${(lo * 100).toFixed(1)}%: ${c}" style="height:${Math.round((c / hmax) * 48) + 1}px"></span>`;
    }).join("");
    const prob = Math.round((m.prob_at_least ?? 0) * 100);
    host.innerHTML =
      `<div class="section-title">Monte Carlo — Equity IRR (${mc.solved} draws: exit cap × hard cost × rent)</div>` +
      `<div class="kpi-grid">` +
      [["P10", pct(m.p10)], ["P50 (median)", pct(m.p50)], ["P90", pct(m.p90)], [`P(IRR ≥ ${target * 100}%)`, `${prob}%`]]
        .map(([l, v]) => `<div class="kpi"><div class="kpi-v">${v}</div><div class="kpi-l">${l}</div></div>`).join("") +
      `</div>` +
      `<div class="pf-hist" title="equity IRR distribution (P10 → P90)">${bars}</div>` +
      `<div class="meta">downside-tilted: exit cap and hard cost skew worse than base; rent ±6%.</div>`;
  }

  /** Two-variable data table: Equity IRR vs exit cap × hard cost (around the base case). */
  private async renderSensitivity() {
    const host = document.getElementById("pf-sens");
    if (!host) return;
    const baseCap = get(this.a, "exit.exit_cap") as number;
    const baseHard = get(this.a, "cost_lines.1.amount") as number;
    const xs = [-0.01, -0.005, 0, 0.005, 0.01].map((d) => +(baseCap + d).toFixed(4));
    const ys = [-0.1, -0.05, 0, 0.05, 0.1].map((d) => Math.round(baseHard * (1 + d)));
    let s;
    try {
      s = await this.api.sensitivity({
        assumptions: this.a,
        x: { path: "exit.exit_cap", values: xs },
        y: { path: "cost_lines.1.amount", values: ys },
        metric: "returns.equity_irr",
      });
    } catch { return; }
    const flat = s.matrix.flat().filter((v): v is number => v != null);
    const lo = Math.min(...flat), hi = Math.max(...flat);
    const color = (v: number | null) => {
      if (v == null) return "#333";
      const t = hi > lo ? (v - lo) / (hi - lo) : 0.5;          // red→green
      return `hsl(${Math.round(t * 120)} 55% 32%)`;
    };
    const head = `<tr><th>IRR</th>${s.x_values.map((x) => `<th>${(x * 100).toFixed(1)}%</th>`).join("")}</tr>`;
    const rows = s.matrix.map((row, j) =>
      `<tr><th>$${(s.y_values[j] / 1e6).toFixed(1)}M</th>` +
      row.map((v) => `<td style="background:${color(v)}">${v == null ? "—" : (v * 100).toFixed(1)}</td>`).join("") +
      `</tr>`).join("");
    host.innerHTML =
      `<div class="section-title">Sensitivity — Equity IRR (exit cap × hard cost)</div>` +
      `<table class="sens-table">${head}${rows}</table>`;
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

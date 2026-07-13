import type { ApiClient, MassingParams, MassingResult, ProformaResult, FinancialStatements, StatementLine, Appraisal } from "../api/client";
import { escapeHtml } from "../ui/feedback";
import { askText } from "../ui/prompt";
import { signedBars, donut, lineChart, stackedBar, tornado, groupedBar, money as cmoney } from "../ui/charts";
import { showQrModal } from "../ui/qr";

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
  debt: { ltc: 0.65, rate: 0.085, points: 0.01, funding: "equity_first", max_ltv: null as number | null, min_dscr: null as number | null },
  equity: { lp_pct: 0.9, gp_pct: 0.1 },
  operations: { potential_rent_annual: 3_600_000, other_income_annual: 120_000, opex_annual: 1_300_000, reserves_annual: 0, stabilized_occ: 0.94, credit_loss_pct: 0.02 },
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
  ["Reserves / yr", "operations.reserves_annual", "money"],
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
  private lastResult?: ProformaResult;   // latest solve, for the Overview command center
  private overviewEl?: HTMLElement;       // the Overview tab's container (re-rendered on each solve)

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
    // optional debt-sizing constraints (blank = off → loan sized by LTC only)
    const sizingField = (label: string, path: string, scale: number, placeholder: string) => {
      const wrap = document.createElement("label"); wrap.className = "pf-field";
      wrap.innerHTML = `<span>${label}</span>`;
      const inp = document.createElement("input"); inp.type = "number"; inp.step = "any"; inp.placeholder = placeholder;
      const raw = get(this.a, path);
      inp.value = raw == null ? "" : String(+(raw * scale).toFixed(3));
      inp.oninput = () => {
        const v = parseFloat(inp.value);
        set(this.a, path, inp.value.trim() === "" || isNaN(v) ? null : v / scale);
        clearTimeout(this.timer);
        this.timer = window.setTimeout(() => this.solve(), 350);
      };
      wrap.appendChild(inp); form.appendChild(wrap);
    };
    sizingField("Max LTV", "debt.max_ltv", 100, "off");
    sizingField("Min DSCR", "debt.min_dscr", 1, "off");
    // sticky returns summary bar — always visible, re-solved live (populated by renderResult)
    const bar = document.createElement("div"); bar.id = "pf-returns-bar"; bar.className = "pf-returns-bar";
    bar.innerHTML = `<span class="meta">Edit assumptions to solve the deal…</span>`;
    this.root.appendChild(bar);

    // sub-tabs — Overview is the executive command center (default landing), then the detail panels
    const TABS: [string, string][] = [["over", "Overview"], ["feas", "Feasibility"], ["cap", "Budget & Capital"],
                                      ["uw", "Underwriting"], ["fin", "Statements"], ["appr", "Valuation"],
                                      ["ops", "Operations"], ["asset", "Asset Mgmt"], ["inv", "Investors"], ["deliver", "Deliverables"]];
    const tabbar = document.createElement("div"); tabbar.className = "pf-subtabs";
    const sections: Record<string, HTMLElement> = {}; const tabBtns: Record<string, HTMLButtonElement> = {};
    for (const [key, label] of TABS) {
      const b = document.createElement("button"); b.className = "pf-subtab"; b.textContent = label; b.dataset.k = key;
      b.onclick = () => showTab(key); tabbar.appendChild(b); tabBtns[key] = b;
      const s = document.createElement("div"); s.className = "pf-section"; sections[key] = s;
    }
    this.root.appendChild(tabbar);
    for (const [key] of TABS) { const s = sections[key]; if (s) this.root.appendChild(s); }
    const showTab = (k: string) => {
      for (const [key] of TABS) { const s = sections[key]; const btn = tabBtns[key]; if (!s || !btn) continue; s.style.display = key === k ? "block" : "none"; btn.classList.toggle("active", key === k); }
      localStorage.setItem("pf-tab", k);
      if (k === "fin" && sections.fin) void this.renderStatements(sections.fin);   // (re)compute statements from the live deal
      if (k === "appr" && sections.appr) void this.renderAppraisal(sections.appr);  // tri-approach valuation + disposition
      if (k === "ops" && sections.ops) void this.renderOperations(sections.ops);   // hold-phase rent roll
      if (k === "asset" && sections.asset) void this.renderAssetMgmt(sections.asset); // reserve study + CIP + CAM true-up
      if (k === "inv" && sections.inv) void this.renderInvestors(sections.inv);    // cap table + capital + statements
    };
    // route each panel into its section by temporarily pointing this.root at the section
    const self = this as unknown as { root: HTMLElement };
    const into = (el: HTMLElement, fn: () => void) => { const r = self.root; self.root = el; try { fn(); } finally { self.root = r; } };
    this.overviewEl = sections.over; this.renderOverview();
    if (sections.feas) into(sections.feas, () => { this.renderMassing(); this.renderTestFit(); this.renderProperty(); });
    if (sections.cap) into(sections.cap, () => { this.renderBudget(); this.renderSourcesUses(); this.renderSpecialty(); });
    const uwSec = sections.uw;
    if (uwSec) into(uwSec, () => {
      uwSec.appendChild(form);
      const out = document.createElement("div"); out.id = "pf-out"; uwSec.appendChild(out);
      const sens = document.createElement("div"); sens.id = "pf-sens"; uwSec.appendChild(sens);
      const mc = document.createElement("div"); mc.id = "pf-mc"; uwSec.appendChild(mc);
      this.renderDraws();
    });
    if (sections.deliver) into(sections.deliver, () => { this.renderDeliverables(); this.renderModelLink(); });
    showTab(localStorage.getItem("pf-tab") || "over");
  }

  /** Statements tab: income statement · balance sheet · cash-flow statement · tax, from the live deal. */
  private async renderStatements(host: HTMLElement) {
    host.innerHTML = `<div class="meta">Computing financial statements…</div>`;
    let f: FinancialStatements;
    try { f = await this.api.financials(this.a); }
    catch (e) { host.innerHTML = `<div class="meta">Couldn't compute statements: ${escapeHtml((e as Error).message)}</div>`; return; }
    host.innerHTML = "";
    const a = f.assumptions;
    const note = document.createElement("div"); note.className = "meta"; note.style.marginBottom = "8px";
    note.innerHTML = `Tax basis — income <b>${(a.income_tax_rate * 100).toFixed(0)}%</b> · depreciation `
      + `<b>${a.depreciation_years}-yr</b> straight-line · capital gains <b>${(a.capital_gains_rate * 100).toFixed(0)}%</b> + NIIT `
      + `· recapture <b>${(a.recapture_rate * 100).toFixed(0)}%</b>. Estimate, not tax advice.`;
    host.appendChild(note);

    const stmt = (title: string, lines: StatementLine[]) => {
      const box = document.createElement("div"); box.className = "fin-card";
      box.innerHTML = `<div class="section-title" style="margin:0 0 4px">${title}</div>`;
      const t = document.createElement("table"); t.className = "fin-table";
      for (const ln of lines) {
        const tr = document.createElement("tr");
        if (ln.total) tr.className = "fin-total"; else if (ln.subtotal) tr.className = "fin-sub";
        tr.innerHTML = `<td>${escapeHtml(ln.label)}</td><td class="num">${money(ln.amount)}</td>`;
        t.appendChild(tr);
      }
      box.appendChild(t); return box;
    };
    const grid = document.createElement("div"); grid.className = "fin-grid"; host.appendChild(grid);

    // income statement (stabilized) + operating-by-year
    const isCard = stmt("Income statement — stabilized year", f.income_statement.lines);
    grid.appendChild(isCard);

    // two-sided budget (Uses | Sources)
    const tb = f.two_sided_budget;
    const budCard = document.createElement("div"); budCard.className = "fin-card";
    budCard.innerHTML = `<div class="section-title" style="margin:0 0 4px">Development budget — Uses &amp; Sources `
      + `${tb.balanced ? '<span class="badge" style="background:var(--accent-soft)">balanced</span>' : ""}</div>`;
    const two = document.createElement("div"); two.className = "fin-twoside";
    const col = (head: string, lines: StatementLine[], total: number) => {
      const c = document.createElement("table"); c.className = "fin-table";
      c.innerHTML = `<tr class="fin-sub"><td>${head}</td><td class="num"></td></tr>`
        + lines.map((l) => `<tr><td>${escapeHtml(l.label)}</td><td class="num">${money(l.amount)}</td></tr>`).join("")
        + `<tr class="fin-total"><td>Total</td><td class="num">${money(total)}</td></tr>`;
      return c;
    };
    two.append(col("Uses", tb.uses, tb.total_uses), col("Sources", tb.sources, tb.total_sources));
    budCard.appendChild(two); grid.appendChild(budCard);

    // balance sheet (final year)
    const bs = f.balance_sheet.by_year[f.balance_sheet.by_year.length - 1];
    if (bs) grid.appendChild(stmt(`Balance sheet — year ${bs.year} ${f.balance_sheet.balanced ? "✓" : "⚠"}`, [
      { label: "Land", amount: bs.assets.land },
      { label: "Improvements (net of depreciation)", amount: bs.assets.improvements_net },
      { label: "Capitalized financing", amount: bs.assets.capitalized_financing },
      { label: "Total assets", amount: bs.assets.total, total: true },
      { label: "Loan", amount: bs.liabilities.total },
      { label: "Paid-in capital", amount: bs.equity.paid_in_capital },
      { label: "Retained earnings", amount: bs.equity.retained_earnings },
      { label: "Liabilities + equity", amount: bs.liabilities.total + bs.equity.total, total: true },
    ]));

    // cash-flow statement
    const c = f.cash_flow_statement;
    grid.appendChild(stmt("Cash-flow statement (life)", [
      { label: "Operating (after-tax)", amount: c.operating.after_tax_operating_cash_flow, subtotal: true },
      { label: "Development cost", amount: c.investing.development_cost },
      { label: "Net sale proceeds", amount: c.investing.net_sale_proceeds },
      { label: "Sale tax", amount: c.investing.sale_tax },
      { label: "Investing", amount: c.investing.total, subtotal: true },
      { label: "Financing (net)", amount: c.financing.total, subtotal: true },
      { label: "Net change in cash", amount: c.net_change_in_cash, total: true },
    ]));

    // tax at sale
    const st = f.tax.sale;
    grid.appendChild(stmt("Tax at sale", [
      { label: "Net sale price", amount: st.net_sale },
      { label: "Adjusted basis", amount: st.adjusted_basis },
      { label: "Total gain", amount: st.total_gain, subtotal: true },
      { label: `Depreciation recapture (${(a.recapture_rate * 100).toFixed(0)}%)`, amount: st.recapture_tax },
      { label: "Capital-gains tax (+NIIT)", amount: st.capital_gains_tax },
      { label: "Total sale tax", amount: st.total_sale_tax, total: true },
    ]));

    // operating summary by year (full-width)
    const yr = document.createElement("div"); yr.className = "fin-card fin-wide";
    const at = f.after_tax_returns;
    yr.innerHTML = `<div class="section-title" style="margin:0 0 4px">Operating summary by year · `
      + `after-tax equity IRR <b>${at.equity_irr != null ? (at.equity_irr * 100).toFixed(1) + "%" : "—"}</b>`
      + `${at.equity_multiple != null ? ` · ${at.equity_multiple}× EM` : ""}</div>`;
    const yt = document.createElement("table"); yt.className = "fin-table";
    yt.innerHTML = `<tr class="fin-sub"><td>Year</td><td class="num">NOI</td><td class="num">Interest</td>`
      + `<td class="num">Deprec.</td><td class="num">Taxable</td><td class="num">Income tax</td><td class="num">Net income</td></tr>`
      + f.income_statement.by_year.map((y) => `<tr><td>${y.year}</td><td class="num">${money(y.noi)}</td>`
        + `<td class="num">${money(y.interest)}</td><td class="num">${money(y.depreciation)}</td>`
        + `<td class="num">${money(y.taxable_income)}</td><td class="num">${money(y.income_tax)}</td>`
        + `<td class="num">${money(y.net_income)}</td></tr>`).join("");
    yr.appendChild(yt); grid.appendChild(yr);

    // trend charts: NOI vs net income (line) + cash flow by year (stacked)
    const by = f.income_statement.by_year, cfy0 = f.cash_flow_statement.by_year;
    const trends = document.createElement("div"); trends.className = "fin-card fin-wide";
    trends.innerHTML = `<div class="section-title" style="margin:0 0 4px">Operating trend &amp; cash flow</div>`;
    const trendRow = document.createElement("div"); trendRow.className = "fin-twoside";
    const c1 = document.createElement("div");
    c1.innerHTML = `<div class="meta">NOI vs net income by year</div>` + lineChart([
      { name: "NOI", values: by.map((y) => y.noi) },
      { name: "Net income", values: by.map((y) => y.net_income) },
    ], { title: "NOI vs net income", fmt: cmoney, xlabels: by.map((y) => "Yr " + y.year), height: 150 });
    const c2 = document.createElement("div");
    c2.innerHTML = `<div class="meta">Cash flow by year (operating · investing · financing)</div>` + stackedBar(
      cfy0.map((r) => ({ label: "Yr " + r.year, segments: [
        { name: "Operating", value: r.operating }, { name: "Investing", value: r.investing },
        { name: "Financing", value: r.loan_repayment + r.distributions },
      ] })), { title: "Cash flow by year", fmt: cmoney, height: 150 });
    trendRow.append(c1, c2); trends.appendChild(trendRow); grid.appendChild(trends);

    // per-year columnar statements (years across the top) — the standard financial-statement layout
    const columnar = (title: string, yrs: number[], rows: { label: string; values: number[]; cls?: string }[]) => {
      const card = document.createElement("div"); card.className = "fin-card fin-wide";
      card.innerHTML = `<div class="section-title" style="margin:0 0 4px">${title}</div>`;
      const t = document.createElement("table"); t.className = "fin-table";
      t.innerHTML = `<tr class="fin-sub"><td></td>${yrs.map((y) => `<td class="num">Yr ${y}</td>`).join("")}</tr>`
        + rows.map((r) => `<tr class="${r.cls ?? ""}"><td>${escapeHtml(r.label)}</td>`
          + r.values.map((v) => `<td class="num">${money(v)}</td>`).join("") + "</tr>").join("");
      card.appendChild(t); return card;
    };
    const bsy = f.balance_sheet.by_year;
    grid.appendChild(columnar(`Balance sheet by year ${f.balance_sheet.balanced ? "✓" : "⚠"}`,
      bsy.map((b) => b.year), [
        { label: "Land", values: bsy.map((b) => b.assets.land) },
        { label: "Improvements (net)", values: bsy.map((b) => b.assets.improvements_net) },
        { label: "Capitalized financing", values: bsy.map((b) => b.assets.capitalized_financing) },
        { label: "Total assets", values: bsy.map((b) => b.assets.total), cls: "fin-sub" },
        { label: "Loan", values: bsy.map((b) => b.liabilities.total) },
        { label: "Paid-in capital", values: bsy.map((b) => b.equity.paid_in_capital) },
        { label: "Retained earnings", values: bsy.map((b) => b.equity.retained_earnings) },
        { label: "Liabilities + equity", values: bsy.map((b) => b.liabilities.total + b.equity.total), cls: "fin-total" },
      ]));
    const cfy = f.cash_flow_statement.by_year;
    grid.appendChild(columnar("Cash flow by year", cfy.map((r) => r.year), [
      { label: "Operating (after-tax)", values: cfy.map((r) => r.operating) },
      { label: "Investing", values: cfy.map((r) => r.investing) },
      { label: "Loan repayment", values: cfy.map((r) => r.loan_repayment) },
      { label: "Distributions", values: cfy.map((r) => r.distributions) },
      { label: "Net change in cash", values: cfy.map((r) => r.net_change_in_cash), cls: "fin-total" },
    ]));
  }

  /** Valuation tab: tri-approach appraisal (cost + income + sales) + disposition (listing, share). */
  private async renderAppraisal(host: HTMLElement) {
    const pid = this.projectId();
    if (!pid) { host.innerHTML = `<div class="meta">Open or save a project to value it and create a listing.</div>`; return; }
    host.innerHTML = `<div class="meta">Computing valuation…</div>`;
    let v: Appraisal;
    try { v = await this.api.appraisal(pid); }
    catch (e) { host.innerHTML = `<div class="meta">Couldn't value this project: ${escapeHtml((e as Error).message)}.<br>Save a proforma scenario (Underwriting) and add Comparables (Finance) first.</div>`; return; }
    host.innerHTML = "";
    const rec = v.reconciliation;
    const head = document.createElement("div"); head.className = "fin-card";
    head.innerHTML = `<div class="section-title">Opinion of value</div>`
      + `<div style="font-size:28px;font-weight:800">${money(rec.value)}</div>`
      + `<div class="meta">Range ${money(rec.range.low)} – ${money(rec.range.high)} · spread ${pct(rec.range.spread_pct)} · `
      + `${v.comp_count} comparable${v.comp_count === 1 ? "" : "s"}</div>`;
    host.appendChild(head);

    // bar: indicated value by approach
    if (rec.contributions.length) {
      const chart = document.createElement("div"); chart.className = "fin-card";
      chart.innerHTML = `<div class="section-title">Indicated value by approach</div>` + groupedBar(
        rec.contributions.map((c) => ({ label: c.approach.replace(/_/g, " "), bars: [{ name: "Value", value: c.value }] })),
        { fmt: cmoney, height: 180 });
      host.appendChild(chart);
    }

    // three approach cards
    const cards = document.createElement("div"); cards.className = "fin-grid";
    const row = (a: string, b: string) => `<tr><td>${a}</td><td class="num">${b}</td></tr>`;
    cards.innerHTML = `
      <div class="fin-card"><div class="section-title">Cost approach</div><table class="fin-table">
        ${row("Replacement cost new", money(v.cost.replacement_cost_new))}
        ${row("Less depreciation", "-" + money(v.cost.depreciation_amount))}
        ${row("Plus land", money(v.cost.land_value))}
        <tr class="fin-total"><td>Value</td><td class="num">${money(v.cost.value)}</td></tr></table></div>
      <div class="fin-card"><div class="section-title">Income approach</div><table class="fin-table">
        ${row("Stabilized NOI", money(v.income.stabilized_noi))}
        ${row("Cap rate", (v.income.cap_rate * 100).toFixed(2) + "%")}
        <tr class="fin-total"><td>Value (direct cap)</td><td class="num">${money(v.income.value)}</td></tr></table></div>
      <div class="fin-card"><div class="section-title">Sales comparison</div><table class="fin-table">
        ${row("Comps used", String(v.sales_comparison.comp_count))}
        ${row("Basis", escapeHtml(v.sales_comparison.basis))}
        ${row("Median $/SF", v.sales_comparison.median_price_psf ? money(v.sales_comparison.median_price_psf) : "—")}
        <tr class="fin-total"><td>Value</td><td class="num">${money(v.sales_comparison.value)}</td></tr></table></div>`;
    host.appendChild(cards);

    // comps import — paste CSV (or upload) to bulk-load comparables that feed the sales approach
    const impCard = document.createElement("div"); impCard.className = "fin-card";
    impCard.innerHTML = `<div class="section-title">Import comparables</div>`
      + `<div class="meta">Paste CSV (headers like address, price, price_psf, cap_rate, sqft, sale_date) — RESO field names also work — to add comps to the sales-comparison approach.</div>`;
    const ta = document.createElement("textarea"); ta.placeholder = "address,price,price_psf,cap_rate,sale_date\n123 Main St,5200000,310,5.4,2026-02-01";
    ta.setAttribute("aria-label", "Comparables CSV");
    ta.style.cssText = "width:100%;min-height:70px;margin-top:6px;font-family:monospace;font-size:12px";
    const ib = document.createElement("div"); ib.style.cssText = "display:flex;gap:8px;align-items:center;margin-top:6px";
    const imp = document.createElement("button"); imp.className = "file-btn"; imp.textContent = "Import CSV";
    const file = document.createElement("input"); file.type = "file"; file.accept = ".csv,text/csv"; file.setAttribute("aria-label", "Upload comparables CSV"); file.style.fontSize = "12px";
    file.onchange = async () => { if (file.files?.[0]) ta.value = await file.files[0].text(); };
    imp.onclick = async () => {
      const csv = ta.value.trim(); if (!csv) return;
      imp.disabled = true;
      try {
        const r = await this.api.importComparables(pid, { csv });
        this.setStatus(`Imported ${r.imported} comparable${r.imported === 1 ? "" : "s"}.`);
        await this.renderAppraisal(host);   // recompute the sales approach with the new comps
      } catch (e) { this.setStatus("Comps import failed: " + (e as Error).message); imp.disabled = false; }
    };
    ib.append(imp, file); impCard.append(ta, ib); host.appendChild(impCard);

    // reconciliation weights — editable, persisted
    const recCard = document.createElement("div"); recCard.className = "fin-card";
    recCard.innerHTML = `<div class="section-title">Reconciliation weights</div>`;
    const wrap = document.createElement("div"); wrap.className = "pf-form";
    const wKeys: [string, string][] = [["income", "Income"], ["sales_comparison", "Sales"], ["cost", "Cost"]];
    const inputs: Record<string, HTMLInputElement> = {};
    const cur: Record<string, number> = {};
    for (const c of rec.contributions) cur[c.approach] = c.weight;
    for (const [k, label] of wKeys) {
      const f = document.createElement("label"); f.className = "pf-field";
      f.innerHTML = `<span>${label} %</span>`;
      const inp = document.createElement("input"); inp.type = "number"; inp.step = "any";
      inp.value = String(Math.round((cur[k] ?? 0) * 100)); inputs[k] = inp; f.appendChild(inp); wrap.appendChild(f);
    }
    recCard.appendChild(wrap);
    const save = document.createElement("button"); save.className = "file-btn"; save.textContent = "Save weights & recompute";
    save.onclick = async () => {
      const weights: Record<string, number> = {};
      for (const [k] of wKeys) { const inp = inputs[k]; if (!inp) continue; const n = parseFloat(inp.value); if (!isNaN(n)) weights[k] = n / 100; }
      save.disabled = true;
      try { await this.api.saveAppraisal(pid, { weights }); await this.renderAppraisal(host); }
      catch (e) { this.setStatus("Save failed: " + (e as Error).message); save.disabled = false; }
    };
    recCard.appendChild(save);
    host.appendChild(recCard);

    // (rent roll → Operations tab; investor cap table → Investors tab)

    // disposition: reports + create-listing + share
    const disp = document.createElement("div"); disp.className = "fin-card";
    disp.innerHTML = `<div class="section-title">Disposition &amp; marketing</div>`
      + `<div class="meta">Valuation report and a BIM-native listing kit — generated from the model + proforma.</div>`;
    const bar = document.createElement("div"); bar.style.cssText = "display:flex;gap:8px;flex-wrap:wrap;margin-top:8px";
    const link = (label: string, href: string) => { const a = document.createElement("a"); a.className = "file-btn"; a.textContent = label; a.href = href; a.target = "_blank"; a.rel = "noopener"; return a; };
    bar.appendChild(link("⬇ Valuation report (PDF)", this.api.reportUrl(pid, "appraisal", "pdf")));
    bar.appendChild(link("⬇ Valuation (Excel)", this.api.reportUrl(pid, "appraisal", "xlsx")));
    bar.appendChild(link("⬇ Listing fact sheet (PDF)", this.api.reportUrl(pid, "listing_factsheet", "pdf")));
    bar.appendChild(link("⬇ Marketing flyer (PDF)", this.api.reportUrl(pid, "marketing_flyer", "pdf")));
    const mk = document.createElement("button"); mk.className = "file-btn"; mk.textContent = "✚ Auto-fill & create listing";
    mk.onclick = async () => {
      mk.disabled = true;
      try {
        const { data } = await this.api.listingAutofill(pid);
        const rec2 = await this.api.createModuleRecord(pid, "listing", { data });
        this.setStatus(`Listing ${rec2.ref} created (auto-filled from the proforma).`);
        const share = await this.api.shareListing(pid, rec2.id);
        await showQrModal(this.api.url(share.url), "Share listing");
      } catch (e) { this.setStatus("Couldn't create listing: " + (e as Error).message); }
      finally { mk.disabled = false; }
    };
    bar.appendChild(mk);
    // Syndicate to WPRealWise / MLS — pushes the RESO-serialized listing out (Phase 4 bridge).
    const synd = document.createElement("button"); synd.className = "file-btn"; synd.textContent = "⤴ Syndicate to WPRealWise";
    synd.onclick = async () => {
      synd.disabled = true;
      try {
        const st = await this.api.reSyndicationStatus();
        const listings = await this.api.moduleRecords(pid, "listing");
        const lastListing = listings[listings.length - 1];
        let lid = lastListing ? lastListing.id : null;
        if (!lid) {
          const { data } = await this.api.listingAutofill(pid);
          lid = (await this.api.createModuleRecord(pid, "listing", { data })).id;
        }
        if (!st.enabled) {
          this.setStatus(st.message);   // actionable: how to configure REALWISE_URL + key
          return;
        }
        const res = await this.api.syndicateListing(pid, lid);
        this.setStatus(`Syndicated to ${res.target}${res.remote_id ? ` (id ${res.remote_id})` : ""} — ${res.fields_pushed} RESO fields pushed.`);
      } catch (e) { this.setStatus("Syndication failed: " + (e as Error).message); }
      finally { synd.disabled = false; }
    };
    bar.appendChild(synd);
    disp.appendChild(bar);
    host.appendChild(disp);
  }

  /** Operations tab: the hold-phase rent roll (occupancy / WALT / in-place income). */
  private async renderOperations(host: HTMLElement) {
    const pid = this.projectId();
    if (!pid) { host.innerHTML = `<div class="meta">Open or save a project to track operations.</div>`; return; }
    host.innerHTML = `<div class="meta">Computing rent roll…</div>`;
    try {
      const rr = await this.api.rentRoll(pid);
      host.innerHTML = "";
      if (rr.lease_count === 0) { host.innerHTML = `<div class="meta">No active leases yet — add them under Construction ▸ Operations ▸ Leases.</div>`; return; }
      const rc = document.createElement("div"); rc.className = "fin-card";
      rc.innerHTML = `<div class="section-title">Rent roll (operating)</div>`
        + `<table class="fin-table">`
        + `<tr><td>Occupancy</td><td class="num">${rr.occupancy_pct}%</td></tr>`
        + `<tr><td>Leases</td><td class="num">${rr.lease_count}</td></tr>`
        + `<tr><td>Base rent / yr</td><td class="num">${money(rr.base_rent_annual)}</td></tr>`
        + `<tr><td>In-place income</td><td class="num">${money(rr.in_place_gross_income)}</td></tr>`
        + `<tr class="fin-total"><td>WALT</td><td class="num">${rr.walt_years} yrs</td></tr></table>`;
      const rb = document.createElement("div"); rb.style.cssText = "display:flex;gap:8px;flex-wrap:wrap;margin-top:8px";
      const rl = document.createElement("a"); rl.className = "file-btn"; rl.textContent = "⬇ Rent roll (PDF)"; rl.href = this.api.reportUrl(pid, "rent_roll", "pdf"); rl.target = "_blank"; rl.rel = "noopener";
      const rx = document.createElement("a"); rx.className = "file-btn"; rx.textContent = "⬇ Excel"; rx.href = this.api.reportUrl(pid, "rent_roll", "xlsx"); rx.target = "_blank"; rx.rel = "noopener";
      const rrv = document.createElement("button"); rrv.className = "file-btn"; rrv.textContent = "Value from rent roll";
      rrv.title = "Re-run the appraisal income approach off in-place income";
      rrv.onclick = async () => {
        try { const v = await this.api.appraisalFromRentRoll(pid); this.setStatus(`Income approach (in-place): ${money(v.income.value)}`); }
        catch (e) { this.setStatus("Couldn't value from rent roll: " + (e as Error).message); }
      };
      rb.append(rl, rx, rrv); rc.appendChild(rb); host.appendChild(rc);
      await this.renderLeaseManagement(host, pid);
    } catch (e) { host.innerHTML = `<div class="meta">${escapeHtml((e as Error).message)}</div>`; }
  }

  /** Lease-management card (under Operations): renewal pipeline, escalation steps, CAM recovery. */
  private async renderLeaseManagement(host: HTMLElement, pid: string) {
    try {
      const lm = await this.api.leaseManagement(pid);
      const card = document.createElement("div"); card.className = "fin-card"; card.style.marginTop = "10px";
      const ex = lm.renewals.expiring;
      const esc = lm.escalations;
      const stepPct = esc.current_base_rent ? Math.round((esc.projected_base_rent / esc.current_base_rent - 1) * 1000) / 10 : 0;
      card.innerHTML = `<div class="section-title">Lease management</div>`
        + `<table class="fin-table">`
        + `<tr><td>Expiring ≤90 / ≤180 / ≤365 d</td><td class="num">${ex["<=90d"]?.count ?? 0} / ${ex["<=180d"]?.count ?? 0} / ${ex["<=365d"]?.count ?? 0}</td></tr>`
        + `<tr><td>Holdover · options outstanding</td><td class="num">${lm.renewals.holdover_count} · ${lm.renewals.options_outstanding}</td></tr>`
        + `<tr><td>Rent at risk (≤365 d)</td><td class="num">${money(lm.renewals.at_risk_rent)}</td></tr>`
        + `<tr><td>Base rent now → yr ${esc.years}</td><td class="num">${money(esc.current_base_rent)} → ${money(esc.projected_base_rent)} (+${stepPct}%)</td></tr>`
        + `<tr class="fin-total"><td>Recoverable income (CAM/NNN)</td><td class="num">${money(lm.cam.recoverable_income)}</td></tr>`
        + `</table>`;
      const lb = document.createElement("div"); lb.style.cssText = "display:flex;gap:8px;flex-wrap:wrap;margin-top:8px";
      const ll = document.createElement("a"); ll.className = "file-btn"; ll.textContent = "⬇ Lease management (PDF)";
      ll.href = this.api.reportUrl(pid, "lease_management", "pdf"); ll.target = "_blank"; ll.rel = "noopener";
      const lx = document.createElement("a"); lx.className = "file-btn"; lx.textContent = "⬇ Excel";
      lx.href = this.api.reportUrl(pid, "lease_management", "xlsx"); lx.target = "_blank"; lx.rel = "noopener";
      lb.append(ll, lx); card.appendChild(lb); host.appendChild(card);
    } catch { /* leases optional — omit the card if it can't load */ }
  }

  /** Asset Mgmt tab: reserve study (replacement schedule + funding adequacy), CIP, CAM true-up. */
  private async renderAssetMgmt(host: HTMLElement) {
    const pid = this.projectId();
    if (!pid) { host.innerHTML = `<div class="meta">Open or save a project to manage the asset.</div>`; return; }
    host.innerHTML = "";
    const intro = document.createElement("div"); intro.className = "meta"; intro.style.marginBottom = "8px";
    intro.textContent = "Hold-phase capital stewardship: the reserve study projects component replacements "
      + "(asset register: install date + expected life + replacement cost) and open capital-plan items over "
      + "the horizon and tests funding adequacy; the CAM reconciliation trues up tenant recoveries against "
      + "actual operating expenses with a variable-only gross-up.";
    host.appendChild(intro);

    // --- reserve study card ---------------------------------------------------------------------
    const rcard = document.createElement("div"); rcard.className = "fin-card";
    rcard.innerHTML = `<div class="section-title">Reserve study</div>`;
    const form = document.createElement("div"); form.style.cssText = "display:flex;gap:8px;flex-wrap:wrap;align-items:end;margin-bottom:8px";
    const num = (label: string, value: string, width = 110) => {
      const wrap = document.createElement("label"); wrap.className = "meta"; wrap.style.cssText = "display:flex;flex-direction:column;gap:2px";
      const inp = document.createElement("input"); inp.type = "number"; inp.value = value; inp.style.width = `${width}px`;
      wrap.textContent = label; wrap.appendChild(inp);
      return { wrap, inp };
    };
    const bal = num("Reserve balance ($)", "0");
    const contrib = num("Annual contribution ($)", "0");
    const horizon = num("Horizon (yrs)", "25", 70);
    const infl = num("Inflation (%)", "3", 70);
    const solveBtn = document.createElement("button"); solveBtn.className = "file-btn"; solveBtn.textContent = "Run study";
    form.append(bal.wrap, contrib.wrap, horizon.wrap, infl.wrap, solveBtn);
    rcard.appendChild(form);
    const rout = document.createElement("div"); rcard.appendChild(rout);
    host.appendChild(rcard);
    const runStudy = async () => {
      rout.innerHTML = `<div class="meta">Projecting replacements…</div>`;
      try {
        const rs = await this.api.reserveStudy(pid, {
          horizonYears: Number(horizon.inp.value) || 25, openingBalance: Number(bal.inp.value) || 0,
          annualContribution: Number(contrib.inp.value) || 0, inflationPct: Number(infl.inp.value) || 0,
        });
        rout.innerHTML = "";
        const banner = document.createElement("div"); banner.className = "meta";
        banner.style.cssText = `padding:6px 8px;border-left:3px solid var(${rs.adequately_funded ? "--status-good" : "--status-warn"});margin-bottom:6px`;
        banner.innerHTML = rs.adequately_funded
          ? `<b>Adequately funded</b> through ${rs.horizon.to} at this contribution.`
          : `<b>Underfunded</b> — reserve balance goes negative in <b>${rs.first_underfunded_year}</b>. `
            + `Suggested level contribution: <b>${money(rs.suggested_level_contribution)}/yr</b>.`;
        rout.appendChild(banner);
        const meta = document.createElement("div"); meta.className = "meta"; meta.style.marginBottom = "6px";
        meta.textContent = `${rs.components} component(s) in the study · ${rs.components_missing_data} missing `
          + `life/cost data · total projected outflows ${money(rs.total_outflows)} through ${rs.horizon.to}.`;
        rout.appendChild(meta);
        if (rs.events.length) {
          const t = document.createElement("table"); t.className = "fin-table";
          t.innerHTML = `<tr><th style="text-align:left">Year</th><th style="text-align:left">Replacement</th><th class="num">Cost (escalated)</th></tr>`
            + rs.events.slice(0, 20).map((e) => `<tr><td>${e.year}</td><td>${escapeHtml(e.item)}${e.source === "cip" ? " <span class=\"meta\">(CIP)</span>" : ""}</td>`
              + `<td class="num">${money(e.cost_escalated)}</td></tr>`).join("")
            + (rs.events.length > 20 ? `<tr><td colspan="3" class="meta">… ${rs.events.length - 20} more event(s)</td></tr>` : "");
          rout.appendChild(t);
        } else {
          rout.insertAdjacentHTML("beforeend", `<div class="meta">No components with expected life + replacement cost yet — `
            + `fill the Reserve Study fields on Asset Register records (Construction ▸ Closeout ▸ Asset Register).</div>`);
        }
      } catch (e) { rout.innerHTML = `<div class="meta">${escapeHtml((e as Error).message)}</div>`; }
    };
    solveBtn.onclick = () => void runStudy();
    void runStudy();

    // --- capital plan (CIP) ---------------------------------------------------------------------
    try {
      const cips = await this.api.moduleRecords(pid, "capital_plan");
      if (cips.length) {
        const card = document.createElement("div"); card.className = "fin-card"; card.style.marginTop = "10px";
        card.innerHTML = `<div class="section-title">Capital plan (CIP)</div>`
          + `<table class="fin-table"><tr><th style="text-align:left">Ref</th><th style="text-align:left">Item</th>`
          + `<th class="num">Year</th><th class="num">Cost</th><th>Priority</th><th>State</th></tr>`
          + cips.map((r) => {
            const d = (r.data || {}) as Record<string, string>;
            return `<tr><td>${escapeHtml(r.ref || "")}</td><td>${escapeHtml(d.subject || "")}</td>`
              + `<td class="num">${escapeHtml(String(d.planned_year || ""))}</td><td class="num">${money(Number(d.cost) || 0)}</td>`
              + `<td>${escapeHtml((d.priority || "").split(" (")[0])}</td><td>${escapeHtml(r.workflow_state || "")}</td></tr>`;
          }).join("") + `</table>`;
        host.appendChild(card);
      }
    } catch { /* CIP module optional */ }

    // --- CAM reconciliation ---------------------------------------------------------------------
    const ccard = document.createElement("div"); ccard.className = "fin-card"; ccard.style.marginTop = "10px";
    ccard.innerHTML = `<div class="section-title">CAM reconciliation</div>`;
    const cout = document.createElement("div"); ccard.appendChild(cout); host.appendChild(ccard);
    try {
      const rec = await this.api.camReconciliation(pid);
      if (!rec.expense_lines.length && !rec.tenants.length) {
        cout.innerHTML = `<div class="meta">No CAM expenses or leases yet — add expense lines under `
          + `Construction ▸ Operations ▸ CAM Expenses and leases with rentable SF.</div>`;
      } else {
        cout.innerHTML = `<table class="fin-table">`
          + `<tr><td>Operating year · occupancy</td><td class="num">${rec.year} · ${rec.occupancy_pct}%</td></tr>`
          + `<tr><td>Operating expenses (budget → actual)</td><td class="num">${money(rec.budget_total)} → ${money(rec.actual_total)}</td></tr>`
          + `<tr class="fin-total"><td>Recoverable pool (grossed to ${rec.gross_up_to_pct}%)</td><td class="num">${money(rec.recoverable_pool)}</td></tr></table>`;
        if (rec.tenants.length) {
          const t = document.createElement("table"); t.className = "fin-table"; t.style.marginTop = "6px";
          t.innerHTML = `<tr><th style="text-align:left">Tenant</th><th class="num">SF</th><th class="num">Share</th>`
            + `<th class="num">Owed</th><th class="num">Paid (est.)</th><th class="num">True-up</th><th></th></tr>`
            + rec.tenants.map((tn) => `<tr><td>${escapeHtml(tn.tenant || tn.ref)}</td>`
              + `<td class="num">${tn.rentable_sf.toLocaleString()}</td><td class="num">${tn.share_pct}%</td>`
              + `<td class="num">${money(tn.share_of_expenses)}</td><td class="num">${money(tn.estimated_paid)}</td>`
              + `<td class="num">${tn.balance_due >= 0 ? money(tn.balance_due) + " due" : money(-tn.balance_due) + " cr"}</td>`
              + `<td><a class="file-btn" href="${this.api.camStatementUrl(pid, tn.id)}" target="_blank" rel="noopener">⬇ Statement</a></td></tr>`).join("");
          cout.appendChild(t);
        }
        const note = document.createElement("div"); note.className = "meta"; note.style.marginTop = "6px";
        note.textContent = rec.note; cout.appendChild(note);
      }
    } catch (e) { cout.innerHTML = `<div class="meta">${escapeHtml((e as Error).message)}</div>`; }
  }

  /** Investors tab: cap table, capital calls / distributions, per-investor statement. */
  private async renderInvestors(host: HTMLElement) {
    const pid = this.projectId();
    if (!pid) { host.innerHTML = `<div class="meta">Open or save a project to manage investors.</div>`; return; }
    host.innerHTML = `<div class="meta">Loading cap table…</div>`;
    try {
      const ct = await this.api.capTable(pid);
      host.innerHTML = "";
      if (ct.investor_count === 0) { host.innerHTML = `<div class="meta">No investors yet — add them under Construction ▸ Capital ▸ Investors.</div>`; return; }
      const cc = document.createElement("div"); cc.className = "fin-card";
      const rows = ct.rows.map((r: any) => `<tr><td>${escapeHtml(String(r.investor ?? ""))}</td>`
        + `<td class="num">${money(r.commitment)}</td><td class="num">${r.ownership_pct}%</td>`
        + `<td class="num">${money(r.unreturned)}</td>`
        + `<td><a class="file-btn" style="padding:1px 6px;font-size:11px" target="_blank" rel="noopener" href="${this.api.investorStatementUrl(pid, String(r.id))}">⬇</a>`
        + ` <button class="file-btn" style="padding:1px 6px;font-size:11px" data-share="${r.id}" title="Mint a no-login link to this investor's statement">🔗</button></td></tr>`).join("");
      cc.innerHTML = `<div class="section-title">Investor cap table</div>`
        + `<table class="fin-table"><tr><th style="text-align:left">Investor</th><th>Commit</th><th>Own %</th><th>Unreturned</th><th>Stmt</th></tr>`
        + rows + `<tr class="fin-total"><td>Total</td><td class="num">${money(ct.total_commitment)}</td><td></td>`
        + `<td class="num">${money(ct.total_unreturned)}</td><td></td></tr></table>`;
      const tools = document.createElement("div"); tools.style.cssText = "display:flex;gap:6px;align-items:center;flex-wrap:wrap;margin-top:8px";
      const amt = document.createElement("input"); amt.type = "number"; amt.placeholder = "Amount"; amt.setAttribute("aria-label", "Capital call / distribution amount"); amt.style.cssText = "width:120px;padding:4px";
      const out = document.createElement("div"); out.className = "meta"; out.style.marginTop = "6px";
      const run = (kind: "call" | "distribution", persist: boolean) => async () => {
        const n = parseFloat(amt.value); if (isNaN(n)) return;
        try {
          const r = kind === "call" ? await this.api.capitalCall(pid, n, persist) : await this.api.distribution(pid, n, persist);
          out.innerHTML = `<b>${persist ? "Recorded " : "Preview "}${kind === "call" ? "capital call" : "distribution"} ${money(r.amount)}</b> — `
            + r.allocations.map((a) => `${escapeHtml(a.investor)}: ${money(a.amount)}`).join(" · ");
          if (persist) await this.renderInvestors(host);   // refresh totals
        } catch (e) { out.textContent = (e as Error).message; }
      };
      const callBtn = document.createElement("button"); callBtn.className = "file-btn"; callBtn.textContent = "Preview call"; callBtn.onclick = run("call", false);
      const distBtn = document.createElement("button"); distBtn.className = "file-btn"; distBtn.textContent = "Preview dist."; distBtn.onclick = run("distribution", false);
      const recCall = document.createElement("button"); recCall.className = "file-btn"; recCall.textContent = "Record call"; recCall.title = "Post the call to each investor's contributed total"; recCall.onclick = run("call", true);
      const recDist = document.createElement("button"); recDist.className = "file-btn"; recDist.textContent = "Record dist."; recDist.title = "Post the distribution to each investor's distributed total"; recDist.onclick = run("distribution", true);
      const cl = document.createElement("a"); cl.className = "file-btn"; cl.textContent = "⬇ Cap table (PDF)"; cl.href = this.api.reportUrl(pid, "cap_table", "pdf"); cl.target = "_blank"; cl.rel = "noopener";
      const cx = document.createElement("a"); cx.className = "file-btn"; cx.textContent = "⬇ Excel"; cx.href = this.api.reportUrl(pid, "cap_table", "xlsx"); cx.target = "_blank"; cx.rel = "noopener";
      tools.append(amt, callBtn, distBtn, recCall, recDist, cl, cx); cc.append(tools, out); host.appendChild(cc);
      // per-row "🔗 share statement": mint a signed, expiring no-login link to that investor's statement
      cc.addEventListener("click", async (e) => {
        const btn = (e.target as HTMLElement).closest("[data-share]") as HTMLElement | null;
        if (!btn) return;
        const iid = btn.dataset.share!;
        btn.setAttribute("disabled", "true");
        try {
          const s = await this.api.shareInvestorStatement(pid, iid);
          await showQrModal(this.api.url(s.url), "Investor statement link");
        } catch (err) { this.setStatus("Couldn't create share link: " + (err as Error).message); }
        finally { btn.removeAttribute("disabled"); }
      });
      this.renderWaterfall(host, pid);
      void this.renderSyndication(host, pid);
    } catch (e) { host.innerHTML = `<div class="meta">${escapeHtml((e as Error).message)}</div>`; }
  }

  /** Capital-markets syndication card (under Investors): export the cap table as a neutral investor-
   *  platform package, and — if the connector is configured — sync positions into a securitization /
   *  investor-management platform. Ledger sync only: this never moves money. */
  private async renderSyndication(host: HTMLElement, pid: string) {
    const card = document.createElement("div"); card.className = "fin-card"; card.style.marginTop = "10px";
    card.innerHTML = `<div class="section-title">Capital-markets syndication</div>`
      + `<div class="meta">Export the cap table as a neutral investor-platform package, or sync positions into a `
      + `securitization / investor-management platform. Ledger sync only — this connector never moves money.</div>`;
    const bar = document.createElement("div"); bar.style.cssText = "display:flex;gap:8px;flex-wrap:wrap;margin-top:8px;align-items:center";
    const dl = document.createElement("a"); dl.className = "file-btn"; dl.textContent = "⬇ Syndication package (JSON)";
    dl.href = this.api.url(`/projects/${pid}/securities/package`); dl.target = "_blank"; dl.rel = "noopener";
    dl.title = "The cap table serialized to the investor-platform schema — importable anywhere";
    const sync = document.createElement("button"); sync.className = "file-btn"; sync.textContent = "⤴ Sync to investor platform";
    sync.onclick = async () => {
      sync.disabled = true;
      try {
        const st = await this.api.securitiesSyndicationStatus();
        if (!st.enabled) { this.setStatus(st.message); return; }  // actionable: how to configure the platform URL + key
        const res = await this.api.syndicateSecurities(pid);
        this.setStatus(`Synced to ${res.target}${res.remote_id ? ` (id ${res.remote_id})` : ""} — ${res.positions_pushed} positions (ledger only, no funds moved).`);
      } catch (e) { this.setStatus("Sync failed: " + (e as Error).message); }
      finally { sync.disabled = false; }
    };
    bar.append(dl, sync);
    const status = document.createElement("span"); status.className = "meta"; status.style.marginLeft = "4px";
    bar.append(status);
    card.appendChild(bar); host.appendChild(card);
    try {
      const st = await this.api.securitiesSyndicationStatus();
      status.textContent = st.enabled ? `● ${st.target} connected` : "○ connector not configured";
      status.style.color = st.enabled ? "var(--ok, #2e7d32)" : "var(--muted, #888)";
    } catch { /* status is best-effort */ }
  }

  /** Equity-waterfall scenario card (under Investors): model a distribution / exit through the
   *  pref → return-of-capital → promote tiers and see each investor's take. */
  private renderWaterfall(host: HTMLElement, pid: string) {
    const card = document.createElement("div"); card.className = "fin-card"; card.style.marginTop = "10px";
    card.innerHTML = `<div class="section-title">Distribution waterfall (scenario)</div>`
      + `<div class="meta">Model a one-time distribution / exit through pref → return of capital → promote.</div>`;
    const ctl = document.createElement("div"); ctl.style.cssText = "display:flex;gap:6px;align-items:center;flex-wrap:wrap;margin-top:8px";
    const amt = document.createElement("input"); amt.type = "number"; amt.placeholder = "Exit / distribution $"; amt.setAttribute("aria-label", "Exit or distribution amount"); amt.style.cssText = "width:160px;padding:4px";
    const yrs = document.createElement("input"); yrs.type = "number"; yrs.value = "5"; yrs.title = "Years held (contribution → exit)"; yrs.setAttribute("aria-label", "Years held"); yrs.style.cssText = "width:70px;padding:4px";
    const go = document.createElement("button"); go.className = "file-btn"; go.textContent = "Run waterfall";
    const out = document.createElement("div"); out.className = "meta"; out.style.marginTop = "6px";
    go.onclick = async () => {
      const n = parseFloat(amt.value); if (isNaN(n)) return;
      const heldYears = Math.max(1, parseInt(yrs.value) || 5);
      const today = new Date();
      const c0 = `${today.getFullYear() - heldYears}-${String(today.getMonth() + 1).padStart(2, "0")}-01`;
      const exit = `${today.getFullYear()}-${String(today.getMonth() + 1).padStart(2, "0")}-01`;
      go.disabled = true;
      try {
        const w = await this.api.waterfallScenario(pid, { exit_amount: n, contribution_date: c0, exit_date: exit });
        if (w.note) { out.innerHTML = `<span class="meta">${escapeHtml(w.note)}</span>`; return; }
        const pct = (v: number | null) => v == null ? "—" : `${(v * 100).toFixed(1)}%`;
        out.innerHTML = `<b>LP ${money(w.lp_distributions)}</b> (IRR ${pct(w.lp_irr)}, ${w.lp_equity_multiple}x) · `
          + `<b>GP ${money(w.gp_distributions)}</b> (${w.gp_equity_multiple}x) · pref ${pct(w.pref_rate)} ${escapeHtml(w.style)}<br>`
          + (w.per_investor as any[]).map((p) => `${escapeHtml(String(p.investor))}: ${money(p.distribution)}`).join(" · ");
      } catch (e) { out.textContent = (e as Error).message; }
      finally { go.disabled = false; }
    };
    ctl.append(amt, yrs, go); card.append(ctl, out); host.appendChild(card);
  }

  /** Deliverables tab: the investor outputs (investment memo + pitch deck PDFs). */
  private renderDeliverables() {
    const pid = this.projectId();
    const host = document.createElement("div");
    host.style.cssText = "margin:8px 0;padding:8px 10px;border:1px dashed var(--line);border-radius:8px";
    host.innerHTML = `<div class="section-title" style="margin:0 0 6px">📑 Investor deliverables</div>`;
    if (!pid) { host.insertAdjacentHTML("beforeend", `<div class="meta">Open a project to generate the memo / deck.</div>`); this.root.appendChild(host); return; }
    const row = document.createElement("div"); row.style.cssText = "display:flex;gap:8px;flex-wrap:wrap";
    const memo = document.createElement("button"); memo.className = "file-btn"; memo.textContent = "📄 Investment memo (PDF)";
    const openDoc = (path: string, name: string) => async () => {
      const { openPdfUrl, saveToDocuments } = await import("../drawings/openPdf");
      await openPdfUrl(this.api, this.api.url(path), name, { saveLabel: "Save to Documents", onSave: saveToDocuments(this.api, pid) });
    };
    memo.onclick = openDoc(`/projects/${pid}/investment-memo.pdf`, "investment-memo.pdf");
    const deck = document.createElement("button"); deck.className = "file-btn"; deck.textContent = "📊 Pitch deck (PDF)";
    deck.onclick = openDoc(`/projects/${pid}/investment-deck.pdf`, "pitch-deck.pdf");
    row.append(memo, deck); host.appendChild(row); this.root.appendChild(host);
  }

  /** Zoning → model: enter a lot + zoning envelope (FAR, setbacks, height) and generate a real IFC
   *  massing model + a starter acquisition proforma in one click. The IFC-native answer to TestFit/
   *  Forma feasibility — the generated model flows into the viewer, drawings, QTO and this proforma. */
  private renderMassing() {
    const host = document.createElement("div"); host.id = "pf-massing";
    host.style.cssText = "margin:8px 0;padding:8px 10px;border:1px dashed var(--line);border-radius:8px";
    host.innerHTML = `<div class="section-title" style="margin:0 0 6px">🏗️ Generate from zoning</div>` +
      `<div class="meta" style="margin-bottom:6px">Lot + zoning envelope → buildable program, an IFC massing model, and an acquisition proforma.</div>`;
    // [label, key, default, step]
    const fields: [string, keyof MassingParams, number, string][] = [
      ["Lot width (m)", "lot_width", 50, "any"], ["Lot depth (m)", "lot_depth", 40, "any"],
      ["FAR", "far", 3.0, "0.1"], ["Coverage max", "coverage_max", 0.6, "0.05"],
      ["Front setback (m)", "front_setback", 6, "any"], ["Rear setback (m)", "rear_setback", 6, "any"],
      ["Side setback (m)", "side_setback", 3, "any"], ["Height limit (m)", "height_limit", 0, "any"],
      ["Floor-to-floor (m)", "floor_to_floor", 3.5, "0.1"], ["Avg unit (m²)", "avg_unit_m2", 75, "any"],
      ["Land cost $", "land_cost", 2_500_000, "any"], ["Hard $/sf", "hard_cost_psf", 225, "any"],
      ["Rent $/unit·mo", "rent_per_unit_month", 3000, "any"], ["Exit cap", "exit_cap", 0.05, "0.005"],
    ];
    const grid = document.createElement("div"); grid.className = "pf-form";
    // use type selector
    const useWrap = document.createElement("label"); useWrap.className = "pf-field";
    useWrap.innerHTML = `<span>Use type</span>`;
    const useSel = document.createElement("select");
    useSel.innerHTML = `<option value="residential">Residential</option><option value="commercial">Commercial</option>`;
    useWrap.appendChild(useSel); grid.appendChild(useWrap);
    const inputs: Record<string, HTMLInputElement> = {};
    for (const [label, key, def, step] of fields) {
      const wrap = document.createElement("label"); wrap.className = "pf-field";
      wrap.innerHTML = `<span>${label}</span>`;
      const inp = document.createElement("input"); inp.type = "number"; inp.step = step; inp.value = String(def);
      if (key === "height_limit") inp.placeholder = "none";
      inputs[key] = inp; wrap.appendChild(inp); grid.appendChild(wrap);
    }
    host.appendChild(grid);

    // shape: box (zoning massing) or a monolithic / earth dome (hemisphere by radius)
    const domeWrap = document.createElement("label");
    domeWrap.style.cssText = "display:flex;align-items:center;gap:6px;margin:4px 0;font-size:13px";
    const domeChk = document.createElement("input"); domeChk.type = "checkbox";
    const domeR = document.createElement("input"); domeR.type = "number"; domeR.step = "0.5"; domeR.value = "8";
    domeR.style.cssText = "width:60px"; domeR.title = "Dome radius (m)";
    domeWrap.append(domeChk, document.createTextNode("Earth / monolithic dome (hemisphere, radius m:"), domeR, document.createTextNode(")"));
    host.appendChild(domeWrap);

    // structural frame option — turns the massing into a real concrete frame (columns + beams)
    const frameWrap = document.createElement("label");
    frameWrap.style.cssText = "display:flex;align-items:center;gap:6px;margin:4px 0;font-size:13px";
    const frameChk = document.createElement("input"); frameChk.type = "checkbox";
    frameWrap.append(frameChk, document.createTextNode("Generate concrete structural frame (columns + beams on a 7.5 m grid)"));
    host.appendChild(frameWrap);
    const unitWrap = document.createElement("label");
    unitWrap.style.cssText = "display:flex;align-items:center;gap:6px;margin:4px 0;font-size:13px";
    const unitChk = document.createElement("input"); unitChk.type = "checkbox";
    unitWrap.append(unitChk, document.createTextNode("Subdivide floors into units (per-apartment spaces)"));
    host.appendChild(unitWrap);
    const envWrap = document.createElement("label");
    envWrap.style.cssText = "display:flex;align-items:center;gap:6px;margin:4px 0;font-size:13px";
    const envChk = document.createElement("input"); envChk.type = "checkbox";
    envWrap.append(envChk, document.createTextNode("Wrap in facade + windows (envelope @ 40% WWR)"));
    host.appendChild(envWrap);
    const coreWrap = document.createElement("label");
    coreWrap.style.cssText = "display:flex;align-items:center;gap:6px;margin:4px 0;font-size:13px";
    const coreChk = document.createElement("input"); coreChk.type = "checkbox";
    coreWrap.append(coreChk, document.createTextNode("Add service core (elevator + stair + MEP risers)"));
    host.appendChild(coreWrap);
    const corrWrap = document.createElement("label");
    corrWrap.style.cssText = "display:flex;align-items:center;gap:6px;margin:4px 0;font-size:13px";
    const corrChk = document.createElement("input"); corrChk.type = "checkbox";
    corrWrap.append(corrChk, document.createTextNode("Double-loaded corridor unit layout (test-fit)"));
    host.appendChild(corrWrap);
    const pkWrap = document.createElement("label");
    pkWrap.style.cssText = "display:flex;align-items:center;gap:6px;margin:4px 0;font-size:13px";
    const pkInput = document.createElement("input");
    pkInput.type = "number"; pkInput.min = "0"; pkInput.max = "2000"; pkInput.value = "0"; pkInput.style.width = "70px";
    pkWrap.append(document.createTextNode("Surface parking stalls (real IfcSpaces)"), pkInput);
    host.appendChild(pkWrap);

    const params = (): MassingParams => {
      const p: MassingParams = { use_type: useSel.value as "residential" | "commercial", name: "Massing Study" };
      for (const [, key] of fields) {
        const inp = inputs[key]; if (!inp) continue;
        const v = parseFloat(inp.value);
        if (key === "height_limit") { p.height_limit = isNaN(v) || v <= 0 ? null : v; }
        else if (!isNaN(v)) (p as Record<string, unknown>)[key] = v;
      }
      p.frame = frameChk.checked;
      p.units = unitChk.checked;
      p.envelope = envChk.checked;
      p.core = coreChk.checked;
      if (corrChk.checked) { p.units = true; p.unit_layout = "corridor"; }
      const pk = parseInt(pkInput.value, 10); if (pk > 0) p.parking = pk;
      if (domeChk.checked) { p.shape = "dome"; p.dome_radius = parseFloat(domeR.value) || 8; }
      return p;
    };
    const out = document.createElement("div"); out.style.marginTop = "6px";
    const showResult = (r: MassingResult, generated: boolean) => {
      const m = r.metrics, ret = r.proforma.returns, su = r.proforma.sources_uses;
      out.innerHTML =
        `<div class="meta" style="margin-bottom:4px"><b>${m.floors} floors</b> · ${Math.round(m.building_height_m)} m · ` +
        `<b>${m.buildable_gfa_sf.toLocaleString()} sf</b> GFA · ${m.units} units · ${m.footprint_m2.toLocaleString()} m² plate ` +
        `<span class="meta">(bound by ${m.binding_constraint}, ${m.far_achieved} FAR)</span></div>` +
        (su ? `<div class="meta">Total cost ${money(su.total_uses ?? 0)} · equity ${money(su.equity ?? 0)} · ` +
              `IRR <b>${pct(ret?.equity_irr ?? null)}</b> · ${ret?.equity_multiple ?? "—"}× EM</div>` : "") +
        (r.proforma.solve_error ? `<div class="meta" style="color:var(--status-crit)">proforma: ${r.proforma.solve_error}</div>` : "") +
        (m.structure ? `<div class="meta">🏛 Structure: <b>${m.structure.system}</b> · ${m.structure.lateral_system}` +
              ((m.structure.base_column_mm && m.structure.top_column_mm && m.structure.top_column_mm < m.structure.base_column_mm)
                ? ` · cols taper ${m.structure.base_column_mm}→${m.structure.top_column_mm} mm (base→top)`
                : ` · cols ${m.structure.members_mm.column} mm`) +
              (m.structure.lateral_core?.provided
                ? ` · ${m.structure.lateral_core.plan_w_m}×${m.structure.lateral_core.plan_d_m} m core, ${m.structure.lateral_core.wall_mm} mm walls` : "") +
              `</div>` : "") +
        (generated ? `<div class="meta" style="color:var(--accent)">✓ IFC model generated & publishing — open the Model workspace to view.</div>` : "");
    };

    const btnRow = document.createElement("div"); btnRow.style.cssText = "display:flex;gap:6px;margin-top:6px";
    const estBtn = document.createElement("button"); estBtn.className = "tool-btn"; estBtn.textContent = "Estimate yield";
    estBtn.onclick = async () => {
      out.innerHTML = `<span class="meta">computing…</span>`;
      try { showResult(await this.api.previewMassing(params()), false); }
      catch (e) { out.innerHTML = `<div class="meta" style="color:var(--status-crit)">${(e as Error).message}</div>`; }
    };
    const genBtn = document.createElement("button"); genBtn.className = "file-btn"; genBtn.textContent = "Generate IFC model + apply";
    genBtn.onclick = async () => {
      const pid = this.projectId();
      if (!pid) { out.innerHTML = `<div class="meta">Open or create a project first (＋ New), then generate its model.</div>`; return; }
      out.innerHTML = `<span class="meta">generating model + proforma…</span>`;
      try {
        const r = await this.api.generateMassing(pid, params());
        showResult(r, true);
        // adopt the generated acquisition assumptions as the live proforma
        this.a = structuredClone(r.proforma.assumptions) as typeof this.a;
        this.render(); void this.solve();
        this.setStatus(`generated ${r.metrics.floors}-floor massing (${r.metrics.buildable_gfa_sf.toLocaleString()} sf) → proforma seeded`);
      } catch (e) { out.innerHTML = `<div class="meta" style="color:var(--status-crit)">${(e as Error).message}</div>`; }
    };
    btnRow.append(estBtn, genBtn); host.append(btnRow, out);
    this.root.appendChild(host);
  }

  /** Test Fit: compare unit-mix schemes on a floor plate — yield (units, efficiency, NSF) + parking,
   *  ranked. The TestFit-style "explore scenarios, find the deal that pencils" surface. */
  private renderTestFit() {
    const host = document.createElement("div"); host.id = "pf-testfit";
    host.style.cssText = "margin:8px 0;padding:8px 10px;border:1px dashed var(--line);border-radius:8px";
    host.innerHTML = `<div class="section-title" style="margin:0 0 6px">📐 Test Fit — compare unit-mix schemes</div>`
      + `<div class="meta" style="margin-bottom:6px">Fit a unit mix to a floor plate; compare yield + parking across schemes.</div>`;
    const grid = document.createElement("div"); grid.className = "pf-form";
    const inp = (label: string, val: number) => {
      const w = document.createElement("label"); w.className = "pf-field"; w.innerHTML = `<span>${label}</span>`;
      const i = document.createElement("input"); i.type = "number"; i.step = "any"; i.value = String(val); w.appendChild(i); grid.appendChild(w); return i;
    };
    const wi = inp("Plate width (m)", 40), di = inp("Plate depth (m)", 18), fi = inp("Floors", 6);
    host.appendChild(grid);

    // --- A1b: custom unit-type mix editor (define + save your own studio/1BR/2BR… mix) ----------
    const MIX_KEY = "testfit-mix";
    type UType = { name: string; target_sf: number; mix_pct: number };
    const loadMix = (): UType[] => {
      try { const m = JSON.parse(localStorage.getItem(MIX_KEY) || ""); if (Array.isArray(m) && m.length) return m; } catch { /* default */ }
      return [{ name: "Studio", target_sf: 500, mix_pct: 0.2 }, { name: "1BR", target_sf: 750, mix_pct: 0.5 }, { name: "2BR", target_sf: 1050, mix_pct: 0.3 }];
    };
    const mix: UType[] = loadMix();
    const mixBox = document.createElement("div");
    mixBox.style.cssText = "margin:6px 0;padding:6px 8px;border:1px solid var(--line);border-radius:6px";
    const renderMix = () => {
      const total = mix.reduce((s, u) => s + (+u.mix_pct || 0), 0);
      mixBox.innerHTML = `<div class="meta" style="display:flex;justify-content:space-between"><span>Your unit mix</span>`
        + `<span${Math.abs(total - 1) > 0.011 ? ' style="color:var(--status-crit)"' : ""}>mix Σ ${(total * 100).toFixed(0)}%</span></div>`;
      mix.forEach((u, idx) => {
        const row = document.createElement("div"); row.style.cssText = "display:flex;gap:4px;align-items:center;margin-top:4px";
        const nm = document.createElement("input"); nm.value = u.name; nm.className = "portal-filter"; nm.style.flex = "1"; nm.placeholder = "type";
        const sf = document.createElement("input"); sf.type = "number"; sf.value = String(u.target_sf); sf.className = "portal-filter"; sf.style.width = "72px"; sf.title = "target SF";
        const pc = document.createElement("input"); pc.type = "number"; pc.value = String(Math.round(u.mix_pct * 100)); pc.className = "portal-filter"; pc.style.width = "56px"; pc.title = "mix %";
        nm.onchange = () => { u.name = nm.value; }; sf.onchange = () => { u.target_sf = +sf.value; };
        pc.onchange = () => { u.mix_pct = (+pc.value || 0) / 100; renderMix(); };
        const rm = document.createElement("button"); rm.className = "tool-btn"; rm.textContent = "✕"; rm.title = "remove";
        rm.onclick = () => { mix.splice(idx, 1); renderMix(); };
        const pct = document.createElement("span"); pct.className = "meta"; pct.textContent = "%";
        row.append(nm, sf, pc, pct, rm); mixBox.appendChild(row);
      });
      const bar = document.createElement("div"); bar.style.cssText = "display:flex;gap:6px;margin-top:6px";
      const add = document.createElement("button"); add.className = "tool-btn"; add.textContent = "+ unit type";
      add.onclick = () => { mix.push({ name: "Unit", target_sf: 800, mix_pct: 0.1 }); renderMix(); };
      const save = document.createElement("button"); save.className = "tool-btn"; save.textContent = "Save mix";
      save.onclick = () => { localStorage.setItem(MIX_KEY, JSON.stringify(mix)); this.setStatus("unit mix saved"); };
      bar.append(add, save); mixBox.appendChild(bar);
    };
    renderMix(); host.appendChild(mixBox);

    const out = document.createElement("div"); out.style.marginTop = "6px";
    // Sweep plate depth: makes daylight-limited leasable depth an optimize dimension (form follows finance)
    const sweepLbl = document.createElement("label"); sweepLbl.className = "meta";
    sweepLbl.style.cssText = "margin-left:8px;cursor:pointer;user-select:none";
    const sweepCb = document.createElement("input"); sweepCb.type = "checkbox"; sweepCb.style.verticalAlign = "middle";
    sweepLbl.append(sweepCb, document.createTextNode(" sweep plate depth"));
    sweepLbl.title = "Also sweep plate depth (×0.6–1.4) — find the depth where daylight-limited yield peaks before a dark core eats rentable area";
    const opt = document.createElement("button"); opt.className = "tool-btn"; opt.style.marginLeft = "6px";
    opt.textContent = "⚡ Optimize (find the deal that pencils)";
    opt.onclick = async () => {
      out.innerHTML = `<span class="meta">sweeping schemes…</span>`;
      try {
        const targets: Record<string, number | string | boolean> = { min_units: 1 };
        if (sweepCb.checked) targets.sweep_depth = true;
        const r = await this.api.testFitOptimize({ plate_w: +wi.value, plate_d: +di.value, floors: +fi.value, targets });
        if (!r.best) { out.innerHTML = `<div class="meta">no feasible scheme for these targets</div>`; return; }
        const dcol = r.swept_depths.length > 1 ? `<th>Depth</th>` : "";
        const rows = r.ranked.map((s, n) => `<tr${n === 0 ? ' style="font-weight:700"' : ""}>`
          + `<th style="text-align:left">${s.name}${n === 0 ? " ★" : ""}</th>`
          + (r.swept_depths.length > 1 ? `<td style="text-align:right">${s.plate_d ?? ""}m</td>` : "")
          + `<td style="text-align:right">${s.total_units}</td><td style="text-align:right">${(s.efficiency * 100).toFixed(0)}%</td>`
          + `<td style="text-align:right">${s.parking_stalls}</td><td style="text-align:right">${(s.yield_on_cost * 100).toFixed(1)}%</td></tr>`).join("");
        // form-follows-finance curve: best yield + daylight/core efficiency per swept depth
        let curveHtml = "";
        if (r.depth_curve.length > 1 && r.best_depth_m != null) {
          const crows = r.depth_curve.map((p) => `<tr${p.plate_d === r.best_depth_m ? ' style="font-weight:700"' : ""}>`
            + `<th style="text-align:left">${p.plate_d}m${p.plate_d === r.best_depth_m ? " ★" : ""}</th>`
            + `<td style="text-align:right">${(p.yield_on_cost * 100).toFixed(1)}%</td>`
            + `<td style="text-align:right">${(p.daylight_efficiency * 100).toFixed(0)}%</td>`
            + `<td style="text-align:right">${(p.core_efficiency * 100).toFixed(0)}%</td>`
            + `<td style="text-align:right">${p.total_units}</td></tr>`).join("");
          curveHtml = `<div class="meta" style="margin:6px 0 2px">Plate-depth sweep — best at <b>${r.best_depth_m}m</b> `
            + `(daylight-limited yield peaks before the dark core eats rentable area):</div>`
            + `<table class="sens-table" style="font-size:12px"><tr><th style="text-align:left">Depth</th><th>YoC</th>`
            + `<th>Daylight</th><th>Core</th><th>Units</th></tr>${crows}</table>`;
        }
        out.innerHTML = `<div class="meta" style="margin-bottom:2px">Swept ${r.considered} schemes · ${r.feasible} feasible · ranked by ${r.objective.replace(/_/g, " ")}</div>`
          + `<table class="sens-table" style="font-size:12px"><tr><th style="text-align:left">Scheme</th>${dcol}<th>Units</th><th>Eff.</th><th>Stalls</th><th>YoC</th></tr>${rows}</table>`
          + curveHtml;
      } catch { out.innerHTML = `<div class="meta">optimize unavailable (API offline)</div>`; }
    };
    const run = document.createElement("button"); run.className = "file-btn"; run.textContent = "Compare schemes";
    run.onclick = async () => {
      out.innerHTML = `<span class="meta">fitting…</span>`;
      try {
        const schemes = mix.length ? [{ name: "My mix", unit_types: mix }] : undefined;
        const r = await this.api.testFitCompare({ plate_w: +wi.value, plate_d: +di.value, floors: +fi.value, schemes, with_defaults: !!schemes });
        const rows = r.schemes.map((s) => `<tr${s.name === r.best ? ' style="font-weight:700"' : ""}>`
          + `<th style="text-align:left">${s.name}${s.name === r.best ? " ★" : ""}</th>`
          + `<td style="text-align:right">${s.total_units}</td>`
          + `<td style="text-align:right"${s.daylight_limited ? ' title="deep plate — dark interior earns no rent"' : ""}>${(s.daylight_efficiency * 100).toFixed(0)}%${s.daylight_limited ? " ⚠" : ""}</td>`
          + `<td style="text-align:right">${s.avg_unit_sf.toLocaleString()}</td><td style="text-align:right">${s.total_nsf.toLocaleString()}</td>`
          + `<td style="text-align:right">${s.parking_stalls}</td></tr>`).join("");
        const eg = r.egress;
        const egLine = eg
          ? `<div class="meta" style="margin-top:6px;padding:6px 8px;border-radius:6px;background:var(--panel2);border:1px solid var(--line)">`
            + `<b>${eg.compliant ? "✅" : "⚠️"} Egress / life-safety (A2)</b> — `
            + `${eg.occupant_load_per_floor} occ/floor · max travel ${eg.max_travel_m} m (limit ${eg.limit_m}) · `
            + `${eg.min_exits_required} exits req'd · separation ${eg.exit_separation_m}/${eg.required_separation_m} m`
            + (eg.flags.length ? `<br><span style="color:var(--status-crit)">${eg.flags.map((f) => "• " + f).join("<br>")}</span>` : "")
            + `</div>`
          : "";
        out.innerHTML = `<table class="sens-table" style="font-size:12px"><tr><th style="text-align:left">Scheme</th>`
          + `<th>Units</th><th title="rentable ÷ gross, daylight-limited">Daylight</th><th>Avg SF</th><th>Rent. SF</th><th>Stalls</th></tr>${rows}</table>`
          + `<div class="meta" style="margin-top:4px">Best by units: <b>${r.best}</b> · daylight efficiency = rentable area within ~9 m of a window ÷ gross</div>`
          + egLine;
      } catch { out.innerHTML = `<div class="meta">test-fit unavailable (API offline)</div>`; }
    };
    host.append(run, opt, sweepLbl, out); this.root.appendChild(host);
  }

  /** Property & tax assumptions: parcel/areas/purchase/taxes; taxes → OPEX, price → acquisition. */
  private renderProperty() {
    const host = document.createElement("div"); host.id = "pf-property";
    host.style.cssText = "margin:8px 0;padding:8px 10px;border:1px dashed var(--line);border-radius:8px";
    const pid = this.projectId();
    host.innerHTML = `<div class="section-title" style="margin:0 0 6px">🏢 Property & tax assumptions</div>`;
    if (!pid) { host.insertAdjacentHTML("beforeend", `<div class="meta">Open a project to set property facts.</div>`); this.root.appendChild(host); return; }
    const body = document.createElement("div"); body.innerHTML = `<div class="meta">loading…</div>`; host.appendChild(body); this.root.appendChild(host);
    void this.api.property(pid).then((resp) => {
      const prop = resp.property as Record<string, number> & { taxes?: Record<string, number> };
      let timer = 0; const save = () => { clearTimeout(timer); timer = window.setTimeout(() => void this.api.saveProperty(pid, prop).then((r) => { sumEl.textContent = summary(r.summary.total_taxes, r.summary.purchase_price); }), 500); };
      const grid = document.createElement("div"); grid.className = "pf-form";
      const field = (label: string, key: string, taxes = false) => {
        const w = document.createElement("label"); w.className = "pf-field"; w.innerHTML = `<span>${label}</span>`;
        const i = document.createElement("input"); i.type = "number"; i.step = "any";
        i.value = String(taxes ? (prop.taxes?.[key] ?? 0) : (prop[key] ?? 0));
        i.oninput = () => { const v = parseFloat(i.value) || 0; if (taxes) { prop.taxes = prop.taxes || {}; prop.taxes[key] = v; } else prop[key] = v; save(); };
        w.appendChild(i); grid.appendChild(w);
      };
      field("Purchase price $", "purchase_price"); field("Building SF", "building_sf"); field("Land SF", "land_sf");
      field("School tax $", "school", true); field("County tax $", "county", true); field("Town tax $", "town", true); field("Fire tax $", "fire", true);
      const summary = (tax: number, price: number) => `Total taxes ${money(tax)}/yr → OPEX · purchase ${money(price)} → acquisition`;
      const sumEl = document.createElement("div"); sumEl.className = "meta"; sumEl.style.marginTop = "4px";
      sumEl.textContent = summary(resp.summary.total_taxes, resp.summary.purchase_price);
      const apply = document.createElement("button"); apply.className = "file-btn"; apply.style.marginTop = "6px"; apply.textContent = "Apply to proforma";
      apply.onclick = async () => {
        const r = await this.api.saveProperty(pid, prop); const d = r.summary.deltas;
        const a = this.a as { cost_lines: { name: string; amount: number }[]; operations: { opex_annual: number } };
        if (d.acquisition_amount) { const land = a.cost_lines.find((c) => /acquisition|land/i.test(c.name)); if (land) land.amount = d.acquisition_amount; }
        a.operations.opex_annual = (a.operations.opex_annual || 0) + d.opex_annual_add;
        this.render(); void this.solve(); this.setStatus(`applied property: ${money(d.acquisition_amount)} acquisition, ${money(d.opex_annual_add)}/yr taxes`);
      };
      body.innerHTML = ""; body.append(grid, sumEl, apply);
    }).catch(() => { body.innerHTML = `<div class="meta">property unavailable (API offline)</div>`; });
  }

  /** Sources & Uses: the capital plan from the cost budget — grouped uses vs sized debt + equity. */
  private renderSourcesUses() {
    const host = document.createElement("div"); host.id = "pf-su";
    host.style.cssText = "margin:8px 0;padding:8px 10px;border:1px dashed var(--line);border-radius:8px";
    const pid = this.projectId();
    host.innerHTML = `<div class="section-title" style="margin:0 0 6px">🏦 Sources &amp; Uses</div>`;
    if (!pid) { host.insertAdjacentHTML("beforeend", `<div class="meta">Open a project to see the capital plan.</div>`); this.root.appendChild(host); return; }
    const body = document.createElement("div"); body.innerHTML = `<div class="meta">loading…</div>`;
    host.appendChild(body); this.root.appendChild(host);
    void this.api.sourcesUses(pid).then((su) => {
      const rows = (items: { label: string; amount: number }[]) =>
        items.map((i) => `<tr><th style="text-align:left;font-weight:400">${i.label}</th><td style="text-align:right">${money(i.amount)}</td></tr>`).join("");
      body.innerHTML =
        `<div style="display:grid;grid-template-columns:1fr 1fr;gap:14px">`
        + `<div><div class="section-title" style="font-size:12px;margin:0 0 2px">Uses</div>`
        + `<table class="sens-table" style="font-size:12px">${rows(su.uses)}`
        + `<tr style="font-weight:700"><th style="text-align:left">Total uses</th><td style="text-align:right">${money(su.total_uses)}</td></tr></table></div>`
        + `<div><div class="section-title" style="font-size:12px;margin:0 0 2px">Sources</div>`
        + `<table class="sens-table" style="font-size:12px">${rows(su.sources)}`
        + `<tr style="font-weight:700"><th style="text-align:left">Total sources</th><td style="text-align:right">${money(su.total_sources)}</td></tr></table></div>`
        + `</div>`
        + `<div class="meta" style="margin-top:6px">${(su.ltc * 100).toFixed(0)}% LTC · debt sized by ${su.binding_constraint} · ${su.balanced ? "✓ balanced" : "⚠ unbalanced"}</div>`;
    }).catch(() => { body.innerHTML = `<div class="meta">Sources &amp; Uses unavailable — build a cost budget first.</div>`; });
  }

  /** Specialty assets: on-site energy (solar/wind/battery/rainwater) + vertical-farm (PFAL) tower
   *  revenue. Capex + annual revenue/opex/energy-offset flow into the proforma — the thesis-grounded
   *  differentiator tying the physical program to the deal economics. */
  private renderSpecialty() {
    const host = document.createElement("div"); host.id = "pf-specialty";
    host.style.cssText = "margin:8px 0;padding:8px 10px;border:1px dashed var(--line);border-radius:8px";
    const pid = this.projectId();
    host.innerHTML = `<div class="section-title" style="margin:0 0 6px">⚡ Specialty: energy & vertical farm</div>`;
    if (!pid) { host.insertAdjacentHTML("beforeend", `<div class="meta">Open a project to model on-site energy + farm revenue.</div>`); this.root.appendChild(host); return; }
    const bodyEl = document.createElement("div"); host.appendChild(bodyEl); this.root.appendChild(host);
    bodyEl.innerHTML = `<div class="meta">loading…</div>`;

    void this.api.specialty(pid).then((resp) => {
      const params = resp.params as Record<string, Record<string, number> & { [k: string]: unknown }> & { energy_enabled?: boolean; pfal_enabled?: boolean };
      let timer = 0;
      const save = () => { clearTimeout(timer); timer = window.setTimeout(() => void this.api.saveSpecialty(pid, params).then((r) => paint(r.summary)), 500); };
      // [label, group, key]
      const FIELDS: [string, "energy" | "pfal", string][] = [
        ["Solar SF", "energy", "solar_sf"], ["$/panel", "energy", "cost_per_panel"],
        ["Battery units", "energy", "battery_units"], ["Rainwater $", "energy", "rainwater_capex"],
        ["PFAL SF", "pfal", "pfal_sf"], ["Greens $/lb", "pfal", "green_price_lb"], ["Herbs $/lb", "pfal", "herb_price_lb"],
      ];
      const paint = (sum?: import("../api/client").SpecialtySummary) => {
        bodyEl.innerHTML = "";
        // enable toggles
        const tog = document.createElement("div"); tog.style.cssText = "display:flex;gap:14px;margin-bottom:6px";
        for (const [k, lbl] of [["energy_enabled", "On-site energy"], ["pfal_enabled", "Vertical farm (PFAL)"]] as const) {
          const w = document.createElement("label"); w.style.cssText = "display:flex;align-items:center;gap:5px;font-size:12px";
          const cb = document.createElement("input"); cb.type = "checkbox"; cb.checked = params[k] !== false;
          cb.onchange = () => { (params as Record<string, unknown>)[k] = cb.checked; save(); paint(); };
          w.append(cb, document.createTextNode(lbl)); tog.appendChild(w);
        }
        bodyEl.appendChild(tog);
        const grid = document.createElement("div"); grid.className = "pf-form";
        for (const [label, group, key] of FIELDS) {
          params[group] = params[group] || {};
          const wrap = document.createElement("label"); wrap.className = "pf-field"; wrap.innerHTML = `<span>${label}</span>`;
          const inp = document.createElement("input"); inp.type = "number"; inp.step = "any";
          inp.value = String((params[group] as Record<string, number>)[key] ?? 0);
          inp.oninput = () => { (params[group] as Record<string, number>)[key] = parseFloat(inp.value) || 0; save(); };
          wrap.appendChild(inp); grid.appendChild(wrap);
        }
        bodyEl.appendChild(grid);
        if (sum) {
          const s = document.createElement("div"); s.className = "meta"; s.style.marginTop = "6px";
          s.innerHTML = `Capex <b>${money(sum.capex_total)}</b>`
            + (sum.energy ? ` · ${sum.energy.solar_panels.toLocaleString()} panels` : "")
            + (sum.pfal ? ` · ${sum.pfal.towers.toLocaleString()} towers` : "")
            + `<br>Produce revenue <b>${money(sum.annual_revenue)}</b>/yr · energy offset ${money(sum.annual_energy_offset)}/yr · farm opex ${money(sum.annual_opex)}/yr`
            + `<br>Net operating contribution <b>${money(sum.annual_net_contribution)}</b>/yr`;
          bodyEl.appendChild(s);
        }
        const apply = document.createElement("button"); apply.className = "file-btn"; apply.style.marginTop = "6px";
        apply.textContent = "Apply to proforma";
        apply.onclick = async () => {
          const r = await this.api.saveSpecialty(pid, params);
          const d = r.deltas;
          const a = this.a as { cost_lines: { category: string; name: string; amount: number }[]; operations: { other_income_annual: number; opex_annual: number } };
          if (d.cost_line) {
            const ex = a.cost_lines.find((c) => c.name === d.cost_line!.name);
            if (ex) ex.amount = d.cost_line.amount; else a.cost_lines.push({ ...d.cost_line, start_month: 0, end_month: 0 } as never);
          }
          a.operations.other_income_annual = (a.operations.other_income_annual || 0) + d.other_income_annual_add;
          a.operations.opex_annual = (a.operations.opex_annual || 0) + d.opex_annual_add;
          this.render(); void this.solve();
          this.setStatus(`applied specialty assets: ${money(r.summary.capex_total)} capex, ${money(r.summary.annual_net_contribution)}/yr net`);
        };
        bodyEl.appendChild(apply);

        // U4 depth: a multi-year P&L with production ramp + specialty-only IRR + blended-deal lift
        const pnl = document.createElement("button"); pnl.className = "tool-btn"; pnl.style.cssText = "margin:6px 0 0 6px";
        pnl.textContent = "P&L + ramp";
        const pnlOut = document.createElement("div"); pnlOut.className = "meta"; pnlOut.style.marginTop = "6px";
        pnl.onclick = async () => {
          pnlOut.innerHTML = `<span class="meta">modelling ramp…</span>`;
          try {
            await this.api.saveSpecialty(pid, params);           // persist edits so the P&L reflects them
            const { proforma: pf } = await this.api.specialtyProforma(pid, { years: 10, ramp_years: 3 });
            const irr = pf.specialty_irr == null ? "—" : pct(pf.specialty_irr);
            const rows = pf.rows.map((r) =>
              `<tr><td>Y${r.op_year}</td><td style="text-align:right">${Math.round(r.ramp * 100)}%</td>`
              + `<td style="text-align:right">${money(r.revenue + r.energy_offset)}</td>`
              + `<td style="text-align:right">${money(r.net)}</td>`
              + `<td style="text-align:right;color:${r.cumulative < 0 ? "var(--status-crit)" : "var(--accent)"}">${money(r.cumulative)}</td></tr>`).join("");
            // blend into the live deal's equity to show the IRR lift (this.a is the RE-only proforma)
            let blendLine = "";
            try {
              const { blended: b } = await this.api.specialtyBlended(pid, this.a, { years: 10, ramp_years: 3 });
              if (b.blended_irr != null && b.re_only_irr != null)
                blendLine = `<div style="margin-top:4px">Deal IRR <b>${pct(b.re_only_irr)}</b> → blended <b>${pct(b.blended_irr)}</b>`
                  + (b.irr_lift != null ? ` <span style="color:var(--accent)">(+${(b.irr_lift * 100).toFixed(1)} pts)</span>` : "") + `</div>`;
            } catch { /* deal not solved yet — show the standalone P&L only */ }
            pnlOut.innerHTML =
              `<div>Specialty IRR <b>${irr}</b> · capex ${money(pf.capex_total)} · stabilized ${money(pf.stabilized_net_annual)}/yr`
              + ` · payback ${pf.payback_op_year ? "Y" + pf.payback_op_year : "—"} · terminal ${money(pf.terminal_value)}</div>`
              + `<table class="mini-table" style="margin-top:4px;width:100%;font-size:11px"><thead><tr>`
              + `<th>Yr</th><th style="text-align:right">Ramp</th><th style="text-align:right">Rev+offset</th>`
              + `<th style="text-align:right">Net</th><th style="text-align:right">Cum.</th></tr></thead><tbody>${rows}</tbody></table>`
              + blendLine;
          } catch (e) { pnlOut.innerHTML = `<div class="meta" style="color:var(--status-crit)">${(e as Error).message}</div>`; }
        };
        bodyEl.appendChild(pnl); bodyEl.appendChild(pnlOut);
      };
      paint(resp.summary);
    }).catch(() => { bodyEl.innerHTML = `<div class="meta">specialty assets unavailable (API offline)</div>`; });
  }

  /** Developer cost budget: line-item hard/soft/acquisition costs (description × $/unit × qty) with
   *  per-category contingency, that roll into the proforma's cost_lines. The institutional gap the
   *  flat cost drivers don't cover. */
  private renderBudget() {
    this.root.querySelector("#pf-budget")?.remove();   // idempotent — re-render replaces, never duplicates
    const host = document.createElement("div"); host.id = "pf-budget";
    host.style.cssText = "margin:8px 0;padding:8px 10px;border:1px dashed var(--line);border-radius:8px";
    const pid = this.projectId();
    host.innerHTML = `<div class="section-title" style="margin:0 0 6px">🧱 Cost budget (hard / soft)</div>`;
    if (!pid) { host.insertAdjacentHTML("beforeend", `<div class="meta">Open a project to build a line-item cost budget.</div>`); this.root.appendChild(host); return; }
    const body = document.createElement("div"); host.appendChild(body); this.root.appendChild(host);
    body.innerHTML = `<div class="meta">loading…</div>`;

    // GC GMP ↔ developer hard-cost reconciliation — ties the underwriting to the live construction number
    const recon = document.createElement("div"); recon.style.cssText = "margin:0 0 8px;padding:6px 8px;border:1px solid var(--line);border-radius:6px";
    host.insertBefore(recon, body); recon.innerHTML = `<div class="meta">checking GC GMP…</div>`;
    const refreshRecon = () => {
      void this.api.gmpReconciliation(pid).then((g) => {
        if (!g.gc_gmp) { recon.style.display = "none"; return; }
        const col = g.in_sync ? "var(--status-good)" : (g.delta > 0 ? "var(--status-crit)" : "var(--status-warn)");
        recon.innerHTML = `<div style="display:flex;justify-content:space-between;align-items:center;gap:8px;flex-wrap:wrap">`
          + `<span class="meta">🤝 GC GMP <b>${money(g.gc_gmp)}</b> · EAC ${money(g.gmp_eac)} vs hard cost <b>${money(g.dev_hard_cost)}</b> · `
          + `<span style="color:${col}">${g.in_sync ? "in sync" : (g.delta > 0 ? "GMP over by " : "GMP under by ") + money(Math.abs(g.delta))}</span></span>`
          + `<button class="tool-btn" id="pf-sync-gmp"${g.in_sync ? " disabled" : ""}>⤵ Set hard cost = GMP</button></div>`;
        const btn = recon.querySelector<HTMLButtonElement>("#pf-sync-gmp");
        if (btn) btn.onclick = async () => {
          btn.disabled = true; btn.textContent = "syncing…";
          try {
            await this.api.syncGmpToHard(pid);
            // close the loop: flow the synced budget into the proforma assumptions and re-solve, so
            // the GMP reaches Sources & Uses + returns (not just the line-item budget)
            const r = await this.api.devBudgetCostLines(pid);
            (this.a as { cost_lines: unknown[] }).cost_lines = r.cost_lines.map((c) => ({ ...c, start_month: 0, end_month: 0 }));
            this.setStatus(`hard cost synced to GC GMP → applied to proforma (${money(r.summary.grand_total)} uses)`);
            this.render(); void this.solve();
          } catch (e) { this.setStatus(`sync failed: ${(e as Error).message}`); refreshRecon(); }
        };
      }).catch(() => { recon.style.display = "none"; });   // no GMP / endpoint absent → hide quietly
    };
    refreshRecon();

    // construction draw schedule — sourced from the GC's cost-loaded schedule (relational tie)
    const draws = document.createElement("div"); draws.className = "meta"; draws.style.cssText = "margin:0 0 8px;font-size:11px";
    host.insertBefore(draws, body);
    void this.api.constructionDraws(pid).then((d) => {
      if (!d.projected_total) { draws.style.display = "none"; return; }
      draws.innerHTML = `📉 Construction draws (from GC schedule): <b>${money(d.projected_total)}</b> over ${d.months} mo`
        + ` · peak ${money(d.peak_month_cost)}/mo · billed ${money(d.actual_billed)} (${d.pct_billed}%)`;
    }).catch(() => { draws.style.display = "none"; });

    const CATS: [string, string][] = [["acquisition", "Acquisition"], ["hard", "Hard costs"], ["soft", "Soft costs"]];
    void this.api.devBudget(pid).then((resp) => {
      const lines = resp.budget.lines.slice();
      const contingency: Record<string, number> = { hard: 0.1, soft: 0.1, acquisition: 0, ...resp.budget.contingency };
      let timer = 0;
      const save = () => { clearTimeout(timer); timer = window.setTimeout(() => void this.api.saveDevBudget(pid, { lines, contingency }).then(paint), 500); };
      const num = (v: string) => { const n = parseFloat(v); return isNaN(n) ? 0 : n; };

      const paint = (r?: import("../api/client").DevBudgetResponse) => {
        const sum = r?.summary;
        body.innerHTML = "";
        for (const [cat, label] of CATS) {
          const head = document.createElement("div"); head.className = "section-title"; head.style.cssText = "margin:8px 0 2px;font-size:12px";
          const subtotal = sum?.categories[cat];
          head.innerHTML = `${label} <span class="meta" style="font-weight:400">${subtotal ? "· " + money(subtotal.subtotal) + (subtotal.contingency ? " + " + money(subtotal.contingency) + " contingency" : "") : ""}</span>`;
          body.appendChild(head);
          const tbl = document.createElement("table"); tbl.className = "sens-table"; tbl.style.fontSize = "12px";
          tbl.innerHTML = `<tr><th style="text-align:left">Description</th><th>$/unit</th><th>Qty</th><th>Total</th><th></th></tr>`;
          lines.forEach((ln, i) => {
            if (ln.category !== cat) return;
            const tr = document.createElement("tr");
            const tot = (ln.unit_cost || 0) * (ln.quantity || 1);
            tr.innerHTML = `<td><input data-i="${i}" data-k="description" value="${(ln.description || "").replace(/"/g, "&quot;")}" style="width:150px"></td>`
              + `<td><input data-i="${i}" data-k="unit_cost" type="number" step="any" value="${ln.unit_cost || 0}" style="width:90px"></td>`
              + `<td><input data-i="${i}" data-k="quantity" type="number" step="any" value="${ln.quantity ?? 1}" style="width:60px"></td>`
              + `<td style="text-align:right">${money(tot)}</td><td><button class="tool-btn" data-rm="${i}" title="Remove">✕</button></td>`;
            tbl.appendChild(tr);
          });
          body.appendChild(tbl);
          const addRow = document.createElement("div"); addRow.style.cssText = "display:flex;gap:8px;align-items:center;margin:3px 0 2px";
          const add = document.createElement("button"); add.className = "tool-btn"; add.textContent = "+ line";
          add.onclick = () => { lines.push({ category: cat as "hard", description: "New line", unit_cost: 0, quantity: 1 }); save(); paint(); };
          const cw = document.createElement("label"); cw.className = "meta"; cw.style.fontSize = "11px";
          cw.innerHTML = `contingency % <input type="number" step="any" value="${+((contingency[cat] ?? 0) * 100).toFixed(2)}" style="width:56px">`;
          (cw.querySelector("input") as HTMLInputElement).oninput = (e) => { contingency[cat] = num((e.target as HTMLInputElement).value) / 100; save(); };
          addRow.append(add, cw); body.appendChild(addRow);
        }
        body.querySelectorAll<HTMLInputElement>("input[data-i]").forEach((inp) => {
          inp.oninput = () => {
            const i = +inp.dataset.i!, k = inp.dataset.k!;
            (lines[i] as unknown as Record<string, unknown>)[k] = k === "description" ? inp.value : num(inp.value);
            save();
            if (k !== "description") paint();   // refresh totals
          };
        });
        body.querySelectorAll<HTMLButtonElement>("button[data-rm]").forEach((b) => {
          b.onclick = () => { lines.splice(+b.dataset.rm!, 1); save(); paint(); };
        });
        const foot = document.createElement("div"); foot.style.cssText = "display:flex;justify-content:space-between;align-items:center;margin-top:8px";
        foot.innerHTML = `<b>Total uses ${money(sum?.grand_total ?? 0)}</b>`
          + `<span class="meta" style="font-size:11px">${sum ? `hard ${(sum.hard_pct * 100).toFixed(0)}% / soft ${(sum.soft_pct * 100).toFixed(0)}%` : ""}</span>`;
        const apply = document.createElement("button"); apply.className = "file-btn"; apply.textContent = "Apply to proforma";
        apply.onclick = async () => {
          const r = await this.api.devBudgetCostLines(pid);
          (this.a as { cost_lines: unknown[] }).cost_lines = r.cost_lines.map((c) => ({ ...c, start_month: 0, end_month: 0 }));
          this.render(); void this.solve();
          this.setStatus(`applied cost budget: ${money(r.summary.grand_total)} total uses`);
        };
        const fwrap = document.createElement("div"); fwrap.style.marginTop = "6px"; fwrap.append(apply);
        body.append(foot, fwrap);
      };
      paint(resp);
    }).catch(() => { body.innerHTML = `<div class="meta">cost budget unavailable (API offline)</div>`; });
  }

  /** Model → proforma: pull GFA from the project's source IFC and seed hard cost + rent from it,
   *  so the deal underwrites against the real model instead of hand-keyed numbers. */
  private renderModelLink() {
    const host = document.createElement("div"); host.id = "pf-model";
    host.style.cssText = "margin:8px 0;padding:8px 10px;border:1px dashed var(--line);border-radius:8px";
    const pid = this.projectId();
    host.innerHTML = `<div class="section-title" style="margin:0 0 6px">📐 From model</div>`;
    if (!pid) { host.insertAdjacentHTML("beforeend", `<div class="meta">Open a project to seed the proforma from its IFC.</div>`); this.root.appendChild(host); return; }
    const btn = document.createElement("button"); btn.className = "tool-btn"; btn.textContent = "Pull model metrics";
    const body = document.createElement("div"); body.style.marginTop = "6px";
    btn.onclick = async () => {
      body.innerHTML = `<span class="meta">reading model…</span>`;
      let m;
      try { m = await this.api.proformaModelMetrics(pid); }
      catch { body.innerHTML = `<div class="meta">No source IFC yet — open an IFC in the Model workspace, then retry.</div>`; return; }
      const sf = m.net_floor_area_sf;
      body.innerHTML =
        `<div class="meta" style="margin-bottom:6px"><b>${sf.toLocaleString()} sf</b> net floor area · ${m.space_count} spaces · ${m.storey_count} storeys</div>` +
        `<div class="pf-form">` +
        `<label class="pf-field"><span>Hard cost $/sf</span><input id="pf-hard-rate" type="number" step="any" value="250"></label>` +
        `<label class="pf-field"><span>Rent $/sf·yr</span><input id="pf-rent-rate" type="number" step="any" value="36"></label>` +
        `</div><button class="file-btn" id="pf-apply-model" style="margin-top:6px">Apply to proforma</button>`;
      (body.querySelector("#pf-apply-model") as HTMLButtonElement).onclick = () => {
        const hard = parseFloat((body.querySelector("#pf-hard-rate") as HTMLInputElement).value) || 0;
        const rent = parseFloat((body.querySelector("#pf-rent-rate") as HTMLInputElement).value) || 0;
        set(this.a, "cost_lines.1.amount", Math.round(sf * hard));      // hard cost line
        set(this.a, "operations.potential_rent_annual", Math.round(sf * rent));
        this.render();                                                   // refresh the driver inputs
        void this.solve();
        this.setStatus(`seeded from model: ${sf.toLocaleString()} sf → hard ${money(sf * hard)}, rent ${money(sf * rent)}/yr`);
      };
    };
    host.append(btn, body);
    this.root.appendChild(host);
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
    html += `</table>`
      + `<button class="file-btn" id="pf-pull-draws" title="Fill construction actuals from the GC's owner-invoice draws to date">⤵ Pull actuals from GC draws</button>`
      + ` <button class="file-btn" id="pf-reforecast" style="margin-top:6px">Re-forecast</button>`
      + `<div id="pf-draws-note" class="meta" style="font-size:11px;margin-top:3px"></div>`
      + `<div id="pf-loan-draws" class="meta" style="font-size:11px;margin-top:3px"></div>`
      + `<div id="pf-draw-comp" class="meta" style="font-size:11px;margin-top:3px"></div>`
      + `<div id="pf-fc-out"></div>`;
    host.innerHTML = html;
    this.root.appendChild(host);
    (host.querySelector("#pf-reforecast") as HTMLButtonElement).onclick = () => this.reforecast();
    (host.querySelector("#pf-pull-draws") as HTMLButtonElement).onclick = () => this.pullGcDraws();

    // per-cost-code draw composition — what the construction draw is for, from the GC's SOV
    const comp = host.querySelector("#pf-draw-comp") as HTMLElement;
    const pidc = this.projectId();
    if (pidc) void this.api.constructionDraws(pidc).then((cd) => {
      if (!cd.by_cost_code || !cd.by_cost_code.length) { comp.style.display = "none"; return; }
      const top = cd.by_cost_code.slice(0, 6);
      comp.innerHTML = "Draw by cost code: " + top.map((x) =>
        `<b>${x.code}</b> ${money(x.billed)}`).join(" · ")
        + (cd.by_cost_code.length > top.length ? ` · +${cd.by_cost_code.length - top.length} more` : "");
    }).catch(() => { comp.style.display = "none"; });

    // construction-loan draw status — owner invoices funded equity-first then debt vs the sized stack
    const pid = this.projectId();
    const ld = host.querySelector("#pf-loan-draws") as HTMLElement;
    if (pid) void this.api.loanDraws(pid).then((l) => {
      if (!l.loan_amount && !l.equity) { ld.style.display = "none"; return; }
      ld.innerHTML = `🏦 Construction loan: drawn <b>${money(l.drawn_to_date)}</b> of ${money(l.loan_amount + l.equity)} `
        + `(${l.pct_capital_drawn}%) — equity ${money(l.equity_drawn)}/${money(l.equity)} · `
        + `loan ${money(l.loan_drawn)}/${money(l.loan_amount)} · available ${money(l.loan_available)}`
        + (l.accrued_interest ? ` · <span style="color:var(--status-crit)">accrued interest ${money(l.accrued_interest)}</span> @ ${(l.interest_rate * 100).toFixed(2)}% (outstanding ${money(l.outstanding_with_interest)})` : "")
        + ` `;
      // interest re-forecast vs the underwritten reserve — is the live carrying cost on plan?
      if (l.budgeted_interest_reserve || l.forecast_interest) {
        const iv = l.interest_variance;
        const ic = iv < 0 ? "var(--status-crit)" : "var(--status-good)";
        const il = document.createElement("div"); il.style.marginTop = "2px";
        il.innerHTML = `↳ Interest re-forecast: reserve <b>${money(l.budgeted_interest_reserve)}</b> vs forecast <b>${money(l.forecast_interest)}</b> `
          + `(accrued ${money(l.accrued_interest)} + to-go) · <span style="color:${ic}">${iv >= 0 ? "under" : "over"} ${money(Math.abs(iv))}</span>`;
        ld.appendChild(il);
      }
      const dr = document.createElement("button"); dr.className = "tool-btn"; dr.textContent = "⬇ Lender draw request (PDF)";
      dr.style.fontSize = "10px"; dr.onclick = async () => {
        try { const blob = await this.api.loanDrawRequestPdf(pid, 1);
          const a = document.createElement("a"); a.href = URL.createObjectURL(blob); a.download = "draw-request-1.pdf"; a.click(); URL.revokeObjectURL(a.href);
          this.setStatus("lender draw request generated"); }
        catch (e) { this.setStatus(`draw request failed: ${(e as Error).message}`); }
      };
      ld.appendChild(dr);
    }).catch(() => { ld.style.display = "none"; });
  }

  /** Actuals loop: pull the GC's owner-invoice draws to date into the construction line's actual,
   *  so the developer's re-forecast runs against what's really been billed (not hand-keyed). */
  private async pullGcDraws() {
    const pid = this.projectId();
    const note = document.getElementById("pf-draws-note");
    if (!pid) { if (note) note.textContent = "Open a project with a GC budget to pull draws."; return; }
    this.setStatus("pulling GC draws…");
    let d;
    try { d = await this.api.constructionDraws(pid); }
    catch (e) { this.setStatus(`pull failed: ${(e as Error).message}`); return; }
    const lines = this.a.cost_lines as { name: string; category?: string }[];
    let idx = lines.findIndex((l) => l.category === "hard");
    if (idx < 0) idx = lines.findIndex((l) => /hard|construction/i.test(l.name));
    if (idx < 0) idx = Math.min(1, lines.length - 1);
    const inp = document.querySelector<HTMLInputElement>(`.pf-actual[data-i="${idx}"]`);
    if (inp) inp.value = String(d.actual_billed);
    if (note) note.innerHTML = `Pulled <b>${money(d.actual_billed)}</b> billed to date (${d.pct_billed}% of `
      + `${money(d.projected_total)} projected draws, ${d.invoice_count} owner invoice${d.invoice_count === 1 ? "" : "s"}) → construction actual.`;
    this.setStatus(`pulled GC draws: ${money(d.actual_billed)} (${d.pct_billed}%)`);
    void this.reforecast();
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
          this.setStatus(`SOV (${dp.sov_lines_created} lines) → G702 due $${Math.round(dp.g702.line8_current_payment_due ?? 0).toLocaleString()}`);
          { const { openPdfUrl, saveToDocuments } = await import("../drawings/openPdf");
            await openPdfUrl(this.api, this.api.url(dp.g702_pdf), "G702-draw.pdf", { saveLabel: "Save to Documents", onSave: saveToDocuments(this.api, pid) }); }
        } catch (e) { this.setStatus(`draw package error: ${(e as Error).message}`); }
      };
      document.getElementById("pf-fc-out")!.appendChild(btn);
    }
  }

  private async solve() {
    this.setStatus("solving proforma…");
    let r: ProformaResult | undefined;
    const pid = this.projectId();
    try {
      // with a project open, solve project-scoped so the guardrails also validate the exit cap
      // against the deal's own sale comps (U3); otherwise the plain stateless solve
      r = pid ? await this.api.solveProformaForProject(pid, this.a) : await this.api.solveProforma(this.a);
    } catch (e) { this.setStatus(`proforma error: ${(e as Error).message}`); return; }
    this.lastResult = r;
    this.renderResult(r);
    this.renderOverview();           // refresh the executive command center with the new solve
    this.setStatus(`equity IRR ${pct(r.returns.equity_irr)} · EM ${r.returns.equity_multiple}`);
    void this.renderSensitivity();
    this.renderMonteCarloPrompt();   // on-demand: a 1000-solve run shouldn't fire on every edit
  }

  /** Sticky returns bar: the headline KPIs + underwriting guardrail badges, always visible. */
  private updateReturnsBar(r: ProformaResult) {
    const bar = document.getElementById("pf-returns-bar"); if (!bar) return;
    const ret = r.returns;
    const kpi = (v: string, l: string) => `<div class="pf-rk"><b>${v}</b><span>${l}</span></div>`;
    let html = kpi(pct(ret.equity_irr), "Equity IRR") + kpi(`${ret.equity_multiple}×`, "Equity mult.")
      + kpi(pct(ret.yield_on_cost), "Yield on cost") + kpi(money(ret.npv), "NPV");
    const g = r.guardrails;
    if (g && g.flags.length) {
      const worst = g.flags.find((f) => f.level === "high") || g.flags.find((f) => f.level === "med") || g.flags[0];
      if (worst) html += `<span class="pf-guard ${worst.level === "info" ? "ok" : worst.level}" title="${g.flags.map((f) => f.message).join(" · ").replace(/"/g, "'")}">`
        + `${worst.level === "info" ? "✓ within market bands" : (worst.level === "high" ? "⚠ check assumptions" : "△ review") + ` · ${worst.message.slice(0, 60)}…`}</span>`;
    }
    bar.innerHTML = html;

    // construction status from the GC (GMP + draws) — the developer's on-cost view next to returns,
    // so the returns bar answers "on returns AND on cost?" the way the PX band does on-schedule/budget
    const pid = this.projectId();
    if (pid) {
      const chip = document.createElement("span"); chip.className = "pf-guard ok"; chip.textContent = "construction…";
      bar.appendChild(chip);
      void Promise.all([
        this.api.gmpReconciliation(pid).catch(() => null),
        this.api.constructionDraws(pid).catch(() => null),
      ]).then(([g, d]) => {
        if (!g || !g.gc_gmp) { chip.remove(); return; }
        const sync = g.in_sync ? "in sync" : (g.delta > 0 ? `GMP +${money(Math.abs(g.delta))}` : `GMP −${money(Math.abs(g.delta))}`);
        chip.className = `pf-guard ${g.in_sync ? "ok" : "med"}`;
        chip.textContent = `🏗 GMP ${money(g.gc_gmp)} · ${sync}` + (d && d.projected_total ? ` · draws ${d.pct_billed}% billed` : "");
        chip.title = `GC GMP ${money(g.gc_gmp)} · EAC ${money(g.gmp_eac)} · committed ${money(g.gmp_committed)} · VAC ${money(g.gmp_variance_at_completion)}`;
      });
    }
  }

  /** Cheap placeholder with a Run button — Monte Carlo (~1000 solves) runs only when asked,
   *  so editing assumptions stays snappy (solve + sensitivity are the live-updating views). */
  private renderMonteCarloPrompt() {
    const host = document.getElementById("pf-mc");
    if (!host) return;
    host.innerHTML = `<div class="section-title">Monte Carlo — Equity IRR risk</div>`
      + `<div class="meta">Probabilistic downside on exit cap × hard cost × rent.</div>`;
    const btn = document.createElement("button");
    btn.className = "tool-btn"; btn.textContent = "▶ Run risk simulation (1000 draws)";
    btn.style.cssText = "display:block;margin:6px 0;width:100%;text-align:left";
    btn.onclick = () => void this.renderMonteCarlo();
    host.appendChild(btn);
  }

  /** Monte Carlo risk: sample exit cap, hard cost, and rent; show the equity-IRR distribution. */
  private async renderMonteCarlo() {
    const host = document.getElementById("pf-mc");
    if (!host) return;
    host.innerHTML = `<div class="section-title">Monte Carlo — Equity IRR risk</div>`
      + `<div class="meta">running 1000 draws…</div>`;
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
    } catch { this.renderMonteCarloPrompt(); return; }
    const m = mc.metrics["returns.equity_irr"];
    if (!m || !m.n) { this.renderMonteCarloPrompt(); return; }
    const hmax = Math.max(...m.histogram.counts, 1);
    const bars = m.histogram.counts.map((c, i) => {
      const lo = m.histogram.edges[i] ?? 0;
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
      `<tr><th>$${((s.y_values[j] ?? 0) / 1e6).toFixed(1)}M</th>` +
      row.map((v) => `<td style="background:${color(v)}">${v == null ? "—" : (v * 100).toFixed(1)}</td>`).join("") +
      `</tr>`).join("");
    // one-way tornado, derived from the same matrix for free: the middle row sweeps exit cap at the
    // base hard cost; the middle column sweeps hard cost at the base exit cap.
    const midR = Math.floor(s.matrix.length / 2), midC = Math.floor((s.x_values.length) / 2);
    const base = s.matrix[midR]?.[midC];
    const rowVals = s.matrix[midR]?.filter((v): v is number => v != null) ?? [];
    const colVals = s.matrix.map((r) => r[midC]).filter((v): v is number => v != null);
    let torn = "";
    if (base != null && rowVals.length && colVals.length) {
      torn = `<div class="section-title" style="margin-top:8px">Tornado — IRR drivers</div>`
        + tornado([
            { label: "Exit cap", low: Math.min(...rowVals), high: Math.max(...rowVals) },
            { label: "Hard cost", low: Math.min(...colVals), high: Math.max(...colVals) },
          ], { base, fmt: (v) => (v * 100).toFixed(1) + "%", title: "IRR sensitivity tornado" });
    }
    host.innerHTML =
      `<div class="section-title">Sensitivity — Equity IRR (exit cap × hard cost)</div>` +
      `<table class="sens-table">${head}${rows}</table>` + torn;
  }

  /** Developer command center (Overview tab) — the executive landing, mirroring the GC dashboard:
   *  an "on returns & on cost" health band + KPI cards + capital-stack drawdown + Sources & Uses +
   *  underwriting guardrails. Re-rendered on every solve. */
  private renderOverview() {
    const host = this.overviewEl; if (!host) return;
    host.innerHTML = "";
    const r = this.lastResult;
    if (!r) { host.innerHTML = `<div class="meta">Solving the deal…</div>`; return; }
    const ret = r.returns, su = r.sources_uses;
    const pid = this.projectId();
    const TARGET = 0.15;                              // hurdle for the "on returns" read
    const card = () => { const d = document.createElement("div"); d.className = "dash-card"; return d; };
    const irrColor = ret.equity_irr == null ? "var(--muted)" : ret.equity_irr >= TARGET ? "var(--status-good)" : ret.equity_irr >= TARGET * 0.8 ? "var(--status-warn)" : "var(--status-crit)";

    // toolbar — save the current solve as a scenario (so it rolls into the Portfolio returns)
    const tools = document.createElement("div"); tools.style.cssText = "display:flex;gap:6px;align-items:center;margin-bottom:8px";
    const save = document.createElement("button"); save.className = "file-btn"; save.textContent = "💾 Save scenario";
    save.title = "Save this solve as a named scenario — it then appears in the Portfolio with its returns";
    save.onclick = async () => {
      if (!pid) { this.setStatus("open a project to save a scenario"); return; }
      const name = await askText("Save scenario", { label: "Save scenario as:", value: "Base case" }); if (!name) return;
      try { await this.api.createScenario(name, pid, this.a); this.setStatus(`saved scenario “${name}” — now in the Portfolio`); }
      catch (e) { this.setStatus(`save failed: ${(e as Error).message}`); }
    };
    tools.append(save, Object.assign(document.createElement("span"), { className: "meta",
      textContent: pid ? "Saved scenarios roll into the Portfolio's developer returns." : "Open a project to save scenarios." }));
    host.appendChild(tools);

    // KPI cards
    const kpis = document.createElement("div"); kpis.className = "dash-cols"; kpis.style.marginBottom = "10px";
    const kpi = (label: string, val: string, color?: string) => {
      const c = card(); c.style.flex = "1";
      c.innerHTML = `<div class="meta">${label}</div><div style="font-size:18px;font-weight:700${color ? `;color:${color}` : ""}">${val}</div>`;
      return c;
    };
    kpis.append(kpi("Equity IRR", pct(ret.equity_irr), irrColor), kpi("Equity multiple", `${ret.equity_multiple}×`),
                kpi("Yield on cost", pct(ret.yield_on_cost)), kpi("NPV", money(ret.npv)));
    host.appendChild(kpis);

    // investment-health band — on returns (vs hurdle) + on cost (construction); pill set after the fetch
    const health = card(); health.style.marginBottom = "10px";
    const hh = document.createElement("div"); hh.className = "section-title";
    hh.style.cssText = "display:flex;justify-content:space-between;align-items:center";
    hh.append(Object.assign(document.createElement("span"), { textContent: "Investment health — on returns & on cost" }));
    const pillEl = document.createElement("span"); pillEl.className = "ball-badge"; hh.appendChild(pillEl); health.appendChild(hh);
    const cols = document.createElement("div"); cols.className = "dash-cols";
    const rCol = card(); rCol.style.flex = "1";
    rCol.innerHTML = `<div class="meta">📈 On returns</div>`
      + `<div style="font-size:15px;font-weight:700;color:${irrColor}">IRR ${pct(ret.equity_irr)}</div>`
      + `<div class="meta">vs ${pct(TARGET)} hurdle · ${ret.equity_multiple}× EM · ${Math.round(ret.dev_spread * 1e4)} bps spread</div>`;
    const cCol = card(); cCol.style.flex = "1";
    cCol.innerHTML = `<div class="meta">🏗 On cost (construction)</div><div class="meta">loading GC status…</div>`;
    cols.append(rCol, cCol); health.appendChild(cols); host.appendChild(health);

    const onReturns = ret.equity_irr == null || ret.equity_irr >= TARGET;
    const setPill = (onCost: boolean | null) => {
      const ok = onReturns && (onCost !== false);
      const warn = onReturns !== (onCost !== false);
      const [lbl, col] = ok ? ["On plan", "var(--status-good)"] : warn ? ["Watch", "var(--status-warn)"] : ["Off plan", "var(--status-crit)"];
      pillEl.textContent = lbl; pillEl.style.cssText = `background:${col}22;color:${col};border-color:${col}`;
    };
    setPill(null);
    if (pid) {
      void Promise.all([this.api.gmpReconciliation(pid).catch(() => null), this.api.loanDraws(pid).catch(() => null)]).then(([g, l]) => {
        if (g && g.gc_gmp) {
          const sync = g.in_sync ? "in sync with underwriting" : (g.delta > 0 ? `GMP ${money(Math.abs(g.delta))} over hard cost` : `GMP ${money(Math.abs(g.delta))} under hard cost`);
          cCol.innerHTML = `<div class="meta">🏗 On cost (construction)</div>`
            + `<div style="font-size:15px;font-weight:700;color:${g.in_sync ? "var(--status-good)" : "var(--status-warn)"}">GMP ${money(g.gc_gmp)}</div>`
            + `<div class="meta">${sync}${l && l.drawn_to_date ? ` · drawn ${money(l.drawn_to_date)} (${l.pct_capital_drawn}%)` : ""}</div>`;
          setPill(g.in_sync);
        } else { cCol.innerHTML = `<div class="meta">🏗 On cost (construction)</div><div class="meta">No GC budget linked yet.</div>`; setPill(null); }
      });
    } else { cCol.innerHTML = `<div class="meta">🏗 On cost (construction)</div><div class="meta">Open a project to link the GC budget.</div>`; }

    // capital stack drawdown (from loan-draws)
    if (pid) {
      const cap = card(); cap.style.marginBottom = "10px";
      cap.appendChild(Object.assign(document.createElement("div"), { className: "section-title", textContent: "Capital stack" }));
      const cb = document.createElement("div"); cb.className = "meta"; cb.textContent = "loading…"; cap.appendChild(cb); host.appendChild(cap);
      void this.api.loanDraws(pid).then((l) => {
        if (!l.loan_amount && !l.equity) { cap.style.display = "none"; return; }
        cb.innerHTML = `Loan <b>${money(l.loan_amount)}</b> · equity <b>${money(l.equity)}</b> · drawn ${money(l.drawn_to_date)} (${l.pct_capital_drawn}%)`
          + ` — equity ${money(l.equity_drawn)} · loan ${money(l.loan_drawn)} · available ${money(l.loan_available)}`
          + (l.accrued_interest ? ` · <span style="color:var(--status-crit)">accrued interest ${money(l.accrued_interest)}</span>` : "");
      }).catch(() => { cap.style.display = "none"; });
    }

    // Sources & Uses + guardrails
    const su2 = card(); su2.style.marginBottom = "10px";
    su2.appendChild(Object.assign(document.createElement("div"), { className: "section-title", textContent: "Sources & Uses" }));
    su2.insertAdjacentHTML("beforeend", `<div class="portal-kv">`
      + `<div class="k">Total uses</div><div class="v">${money(su.total_uses)}</div>`
      + `<div class="k">Senior loan</div><div class="v">${money(su.loan_amount)}</div>`
      + `<div class="k">Equity (LP / GP)</div><div class="v">${money(su.equity)} (${money(su.lp_contribution)} / ${money(su.gp_contribution)})</div>`
      + `</div>`);
    host.appendChild(su2);
    if (r.guardrails && r.guardrails.flags.length) {
      const gc = card();
      gc.appendChild(Object.assign(document.createElement("div"), { className: "section-title", textContent: "Underwriting guardrails" }));
      for (const f of r.guardrails.flags.slice(0, 5)) {
        const col = f.level === "high" ? "var(--status-crit)" : f.level === "med" ? "var(--status-warn)" : "var(--status-good)";
        gc.insertAdjacentHTML("beforeend", `<div class="meta" style="margin:1px 0"><span style="color:${col}">${f.level === "info" ? "✓" : "△"}</span> ${f.message}</div>`);
      }
      host.appendChild(gc);
    }
  }

  private renderResult(r: ProformaResult) {
    const su = r.sources_uses, ret = r.returns, wf = r.waterfall;
    this.updateReturnsBar(r);
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
      `<div class="k">Senior loan (${pct(su.effective_ltc ?? su.ltc)} LTC)</div><div class="v">${money(su.loan_amount)}</div>` +
      this.sizingRow(r) +
      `<div class="k">Interest reserve</div><div class="v">${money(su.interest_reserve)}</div>` +
      `<div class="k">Equity</div><div class="v">${money(su.equity)}</div>` +
      `<div class="k">LP / GP</div><div class="v">${money(su.lp_contribution)} / ${money(su.gp_contribution)}</div>` +
      `</div>` +
      `<div class="section-title">JV Waterfall (${wf.style})</div>` +
      `<div class="portal-kv">` +
      `<div class="k">LP</div><div class="v">IRR ${pct(wf.lp_irr)} · ${wf.lp_equity_multiple}× · ${money(wf.lp_distributions)}</div>` +
      `<div class="k">GP</div><div class="v">IRR ${pct(wf.gp_irr)} · ${wf.gp_equity_multiple}× · ${money(wf.gp_distributions)}</div>` +
      `</div>` +
      // capital stack (sources) + JV split + equity cash flow — the at-a-glance visuals
      `<div class="fin-grid" style="margin-top:8px">`
      + `<div><div class="section-title" style="margin:0 0 2px">Capital stack</div>`
      + donut([
          { label: "Senior debt", value: su.loan_amount },
          { label: "LP equity", value: su.lp_contribution },
          { label: "GP equity", value: su.gp_contribution },
        ], { title: "Capital stack", center: cmoney(su.total_uses), height: 150 }) + `</div>`
      + `<div><div class="section-title" style="margin:0 0 2px">JV distributions (LP vs GP)</div>`
      + donut([
          { label: "LP", value: wf.lp_distributions }, { label: "GP", value: wf.gp_distributions },
        ], { title: "JV distributions", height: 150 }) + `</div>`
      + `</div>`
      + `<div class="section-title">Equity cash flow</div>`
      + signedBars(r.cash_flow.equity, { title: "Equity cash flow", fmt: cmoney });
  }

  /** "Loan sizing" row: which constraint bound the loan + the resulting DSCR/LTV. */
  private sizingRow(r: ProformaResult): string {
    const ds = r.debt_sizing;
    if (!ds) return "";
    const label: Record<string, string> = { ltc: "LTC", ltv: "LTV", dscr: "DSCR", debt_yield: "Debt yield" };
    const metrics = [
      ds.actual_dscr != null ? `DSCR ${ds.actual_dscr.toFixed(2)}×` : "",
      ds.actual_ltv != null ? `LTV ${(ds.actual_ltv * 100).toFixed(0)}%` : "",
      ds.actual_debt_yield != null ? `DY ${(ds.actual_debt_yield * 100).toFixed(1)}%` : "",
    ].filter(Boolean).join(" · ");
    const bound = ds.binding_constraint === "ltc" ? "" : ` <span class="meta">(binds)</span>`;
    return `<div class="k">Loan sizing</div><div class="v">${label[ds.binding_constraint] ?? ds.binding_constraint}${bound} — ${metrics}</div>`;
  }

}

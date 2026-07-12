import { money as cmoney } from "../../ui/charts";
import { noProjectHtml } from "../../ui/empty";
import { escapeHtml as esc } from "../../ui/feedback";
import type { PanelContext } from "../panelContext";

/**
 * Work-in-Progress schedule — the construction-accounting twin to the earned-value module. Shows
 * percentage-of-completion (cost-to-cost), earned revenue vs billed, and the over/under-billing
 * contract position (liability vs asset), plus retainage, gross profit, backlog, and a portfolio roll-up.
 */
export async function renderWip(ctx: PanelContext) {
  const root = ctx.root; root.innerHTML = "";
  const el = (t: string, c = "") => { const e = document.createElement(t); if (c) e.className = c; return e; };
  root.appendChild(ctx.bar("📄 Work-in-Progress (WIP)", () => { ctx.activeKey = null; void ctx.renderHome(); ctx.buildNav(); }));
  const pid = ctx.host.projectId();
  if (!pid) { root.insertAdjacentHTML("beforeend", noProjectHtml("Work-in-Progress")); return; }

  const intro = el("div", "meta"); intro.style.marginBottom = "8px";
  intro.innerHTML = "Percentage-of-completion (cost-to-cost) turns job cost + billing into revenue. "
    + "<b>Earned revenue</b> = % complete × contract; comparing it to <b>billed</b> gives the contract "
    + "position — <b>over-billing</b> is a liability (borrowed against future work), <b>under-billing</b> "
    + "is an asset that ties up cash. Needs a prime contract, budgets, direct costs and owner invoices.";
  root.appendChild(intro);
  const pdf = el("a", "portal-btn") as HTMLAnchorElement; pdf.textContent = "⬇ WIP report (PDF)";
  pdf.href = ctx.host.api.reportUrl(pid, "wip", "pdf"); pdf.target = "_blank"; pdf.rel = "noopener";
  root.appendChild(pdf);
  const spdf = el("a", "portal-btn") as HTMLAnchorElement; spdf.textContent = "⬇ Contractor statements (PDF)";
  spdf.style.marginLeft = "6px"; spdf.href = ctx.host.api.reportUrl(pid, "contractor_financials", "pdf");
  spdf.target = "_blank"; spdf.rel = "noopener"; root.appendChild(spdf);
  const body = el("div"); body.style.marginTop = "8px"; body.textContent = "loading…"; root.appendChild(body);

  let w; let pf; let cs;
  try {
    w = await ctx.host.api.wip(pid);
    pf = await ctx.host.api.wipPortfolio().catch(() => null);
    cs = await ctx.host.api.contractorStatements(pid).catch(() => null);
  } catch (e) { body.textContent = `failed: ${(e as Error).message}`; return; }
  body.innerHTML = "";
  const usd = (n: number) => cmoney(n);
  if (!w.contract_value && !w.cost_to_date) {
    body.innerHTML = `<div class="meta">No contract or cost yet — add a <b>prime contract</b> (value), `
      + `<b>budgets</b> + a Schedule of Values, <b>direct costs</b> and <b>owner invoices</b> to compute WIP.</div>`;
    return;
  }

  // --- KPI cards ---
  const cards = el("div"); cards.style.cssText = "display:flex;gap:8px;flex-wrap:wrap;margin-bottom:8px";
  const card = (label: string, value: string, color?: string, sub?: string) => {
    const cc = el("div", "dash-card"); cc.style.cssText = `min-width:112px${color ? `;border-left:3px solid ${color}` : ""}`;
    cc.innerHTML = `<div style="font-size:18px;font-weight:600${color ? `;color:${color}` : ""}">${value}</div>`
      + `<div class="meta">${label}</div>` + (sub ? `<div class="meta" style="font-size:10px">${sub}</div>` : "");
    return cc;
  };
  const over = w.billing_status === "over-billed";
  const posColor = over ? "var(--status-warn)" : w.billing_status === "under-billed" ? "var(--status-crit)" : "var(--status-good)";
  cards.append(
    card("% complete", `${w.percent_complete}%`, undefined, `cost-to-cost`),
    card("Earned revenue", usd(w.earned_revenue), undefined, `vs billed ${usd(w.billed_to_date)}`),
    card(over ? "Over-billing" : "Under-billing", usd(over ? w.over_billing : w.under_billing), posColor,
      over ? "liability" : "asset"),
    card("Gross profit", usd(w.gross_profit), undefined, `${w.gross_margin_pct}% margin`),
    card("Backlog", usd(w.backlog), undefined, `retainage ${usd(w.retainage)}`));
  body.append(cards);

  // --- contract position callout ---
  const callout = el("div", "dash-card"); callout.style.cssText = `margin-bottom:8px;border-left:3px solid ${posColor}`;
  callout.innerHTML = over
    ? `<b>Over-billed by ${usd(w.over_billing)}</b> <span class="meta">— billings in excess of costs &amp; earnings (a contract <b>liability</b>). You've billed ahead of the work; protect the cash for the effort still owed.</span>`
    : w.billing_status === "under-billed"
      ? `<b>Under-billed by ${usd(w.under_billing)}</b> <span class="meta">— costs &amp; earnings in excess of billings (a contract <b>asset</b>). You've earned more than you've billed — accelerate billing to free up cash.</span>`
      : `<b>Billing is even</b> <span class="meta">— billed matches earned revenue.</span>`;
  body.append(callout);

  // --- contract-position table ---
  const rows: [string, string][] = [
    ["Contract value", usd(w.contract_value)], ["Total estimated cost", usd(w.estimated_cost)],
    ["Cost to date", usd(w.cost_to_date)], ["Cost to complete", usd(w.cost_to_complete)],
    ["Earned revenue (POC)", usd(w.earned_revenue)], ["Billed to date", usd(w.billed_to_date)],
    ["Profit earned to date", usd(w.profit_to_date)], ["Retainage held", usd(w.retainage)],
  ];
  const tbl = el("table", "portal-table") as HTMLTableElement; tbl.style.cssText = "width:100%;font-size:12px";
  tbl.innerHTML = `<tbody>${rows.map(([k, v]) => `<tr><td>${esc(k)}</td><td style="text-align:right">${v}</td></tr>`).join("")}</tbody>`;
  body.append(tbl);

  // --- model cross-check: physical % complete (installed elements ÷ total, by GlobalId) vs cost ---
  if (w.model) {
    const m = w.model;
    const flagColor = m.flag === "cost-ahead" ? "var(--status-warn)"
      : m.flag === "physical-ahead" ? "var(--status-crit)" : "var(--status-good)";
    const flagText = m.flag === "cost-ahead"
      ? "Cost is running ahead of physical progress — the classic front-loaded-billing / cost-overrun signal. Review before recognizing revenue."
      : m.flag === "physical-ahead"
        ? "Physical progress is ahead of cost — possible under-costing or productivity gains; you may be under-billing the work in place."
        : "Physical and cost progress agree — the cost-to-cost POC is corroborated by what's installed in the model.";
    const mc = el("div", "dash-card"); mc.style.cssText = `margin-top:8px;border-left:3px solid ${flagColor}`;
    mc.innerHTML = `<b>Model cross-check</b> <span class="meta">— physical progress from the model `
      + `(${m.installed_elements}/${m.total_elements} elements installed, by IFC GlobalId) vs cost-to-cost POC</span>`
      + `<div style="display:flex;gap:16px;margin:6px 0;flex-wrap:wrap">`
      + `<div><div style="font-size:18px;font-weight:600">${m.model_percent_complete}%</div><div class="meta">physical (installed)</div></div>`
      + `<div><div style="font-size:18px;font-weight:600">${m.cost_percent_complete}%</div><div class="meta">cost-to-cost</div></div>`
      + `<div><div style="font-size:18px;font-weight:600;color:${flagColor}">${m.divergence_pct > 0 ? "+" : ""}${m.divergence_pct}pt</div><div class="meta">divergence</div></div>`
      + `</div><div class="meta">${flagText}</div>`;
    body.append(mc);
  }

  // --- contractor statements (POC income statement + contract-position balance-sheet section) ---
  if (cs) {
    const inc = cs.income_statement, pos = cs.contract_position;
    const card2 = el("div", "dash-card"); card2.style.marginTop = "8px";
    const money = (n: number) => usd(n);
    card2.innerHTML = `<b>Contractor statements</b> <span class="meta">(percentage-of-completion)</span>`
      + `<table class="fin-table" style="width:100%;font-size:12px;margin-top:4px">`
      + `<tr><td colspan="2" style="font-weight:700">Income statement</td></tr>`
      + `<tr><td>Revenue earned (POC)</td><td class="num">${money(inc.revenue_earned)}</td></tr>`
      + `<tr><td>Cost of revenue</td><td class="num">${money(inc.cost_of_revenue)}</td></tr>`
      + `<tr class="fin-total"><td>Gross profit (${inc.gross_margin_pct}%)</td><td class="num">${money(inc.gross_profit)}</td></tr>`
      + `<tr><td colspan="2" style="font-weight:700;padding-top:4px">Contract position (balance sheet)</td></tr>`
      + `<tr><td>Contract asset — under-billings</td><td class="num">${money(pos.contract_asset_underbillings)}</td></tr>`
      + `<tr><td>Contract liability — over-billings</td><td class="num">${money(pos.contract_liability_overbillings)}</td></tr>`
      + `<tr><td>Retainage receivable</td><td class="num">${money(pos.retainage_receivable)}</td></tr>`
      + `<tr><td>Accounts payable (subs)</td><td class="num">${money(pos.accounts_payable)}</td></tr>`
      + `<tr class="fin-total"><td>Net contract working capital</td><td class="num" style="color:${pos.net_contract_working_capital < 0 ? "var(--status-crit)" : "var(--status-good)"}">${money(pos.net_contract_working_capital)}</td></tr>`
      + `</table>`;
    body.append(card2);
  }

  // --- portfolio WIP ---
  if (pf && pf.project_count > 1) {
    const h = el("div", "meta"); h.style.cssText = "font-weight:700;margin:10px 0 2px";
    h.textContent = "Portfolio WIP (largest under-billing first)";
    const pt = el("table", "portal-table") as HTMLTableElement; pt.style.cssText = "width:100%;font-size:11px";
    pt.innerHTML = `<thead><tr><th scope="col" style="text-align:left">Project</th><th scope="col">%</th>`
      + `<th scope="col">Earned</th><th scope="col">Billed</th><th scope="col">Under</th><th scope="col">Over</th></tr></thead><tbody>`
      + pf.projects.map((p) => `<tr><td>${esc(p.name)}</td><td style="text-align:center">${p.percent_complete}%</td>`
        + `<td style="text-align:right">${usd(p.earned_revenue)}</td><td style="text-align:right">${usd(p.billed_to_date)}</td>`
        + `<td style="text-align:right;color:${p.under_billing ? "var(--status-crit)" : "var(--muted)"}">${p.under_billing ? usd(p.under_billing) : "—"}</td>`
        + `<td style="text-align:right;color:${p.over_billing ? "var(--status-warn)" : "var(--muted)"}">${p.over_billing ? usd(p.over_billing) : "—"}</td></tr>`).join("")
      + `</tbody>`;
    body.append(h, pt);
  }
}

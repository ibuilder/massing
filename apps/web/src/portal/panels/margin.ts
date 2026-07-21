import { escapeHtml as esc } from "../../ui/feedback";
import type { PanelContext } from "../panelContext";

/**
 * MARGIN-CBS money card (R16) — per-cost-code reconciliation surfaced in the portal: budget vs committed
 * vs actual vs billed, the projected buyout margin (budget − committed) and cost variance, with
 * over-committed / over-budget codes flagged worst-margin first.
 */
export async function renderMargin(ctx: PanelContext) {
  const pid = ctx.host.projectId()!;
  ctx.root.innerHTML = "";
  ctx.root.appendChild(ctx.bar("📒 Cost-code margin", () => { ctx.activeKey = null; void ctx.renderHome(); ctx.buildNav(); }));

  const body = document.createElement("div");
  body.innerHTML = `<div class="meta">Reconciling budget vs committed vs actual…</div>`;
  ctx.root.appendChild(body);

  const usd = (n: number) => (n < 0 ? "−$" : "$") + Math.round(Math.abs(n)).toLocaleString();
  const marginCol = (n: number) => n < 0 ? "var(--status-crit)" : n > 0 ? "var(--status-good)" : "var(--fg)";

  try {
    const m = await ctx.host.api.marginByCostCode(pid);
    body.replaceChildren();
    if (!m.code_count) {
      body.innerHTML = `<div class="meta">No cost-code budget/commitment records yet — add budget lines, commitments, direct costs and sub invoices with a cost code to see the reconciliation.</div>`;
      return;
    }

    const head = document.createElement("div"); head.className = "dash-card"; head.style.marginBottom = "10px";
    head.innerHTML = `<div style="display:flex;justify-content:space-between;align-items:baseline;gap:12px;flex-wrap:wrap">`
      + `<div class="section-title" style="margin:0">Buyout margin</div>`
      + `<div style="font-size:20px;font-weight:800;color:${marginCol(m.total_buyout_margin)}">${usd(m.total_buyout_margin)}</div></div>`
      + `<div class="meta" style="margin-top:2px">Budget <b>${usd(m.total_budget)}</b> · committed <b>${usd(m.total_committed)}</b> · actual <b>${usd(m.total_actual)}</b> · billed <b>${usd(m.total_billed)}</b></div>`
      + `<div class="meta" style="margin-top:2px">${m.pct_committed ?? 0}% committed · ${m.pct_spent ?? 0}% spent · variance <b style="color:${marginCol(m.total_variance)}">${usd(m.total_variance)}</b>`
      + (m.over_committed_codes ? ` · <b style="color:var(--status-crit)">${m.over_committed_codes} over-committed</b>` : "")
      + (m.over_budget_codes ? ` · <b style="color:var(--status-crit)">${m.over_budget_codes} over-budget</b>` : "") + `</div>`;
    body.appendChild(head);

    const wrap = document.createElement("div"); wrap.className = "dash-card"; wrap.style.overflowX = "auto";
    const t = document.createElement("table"); t.className = "portal-table"; t.style.cssText = "width:100%;font-size:11px";
    t.innerHTML = `<thead><tr><th scope="col" style="text-align:left">Cost code</th>`
      + `<th scope="col" style="text-align:right">Budget</th><th scope="col" style="text-align:right">Committed</th>`
      + `<th scope="col" style="text-align:right">Actual</th><th scope="col" style="text-align:right">Buyout margin</th>`
      + `<th scope="col" style="text-align:right">Variance</th></tr></thead><tbody>`
      + m.rows.map((r) => {
        const flag = r.over_committed ? " ⚠" : "";
        return `<tr><td style="text-align:left">${esc(r.cost_code)}${flag}</td>`
          + `<td style="text-align:right;font-variant-numeric:tabular-nums">${usd(r.budget)}</td>`
          + `<td style="text-align:right;font-variant-numeric:tabular-nums">${usd(r.committed)}</td>`
          + `<td style="text-align:right;font-variant-numeric:tabular-nums">${usd(r.actual)}</td>`
          + `<td style="text-align:right;font-variant-numeric:tabular-nums;color:${marginCol(r.buyout_margin)}">${usd(r.buyout_margin)}</td>`
          + `<td style="text-align:right;font-variant-numeric:tabular-nums;color:${marginCol(r.variance)}">${usd(r.variance)}</td></tr>`;
      }).join("") + `</tbody>`;
    wrap.appendChild(t);
    body.appendChild(wrap);
  } catch (e) {
    body.innerHTML = `<div class="meta">Cost-code margin unavailable: ${esc((e as Error).message)}</div>`;
  }
}

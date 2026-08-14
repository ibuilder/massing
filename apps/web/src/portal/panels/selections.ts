import { countNarrative, deltaChip, statusChip } from "../../ui/chips";
import { escapeHtml as esc } from "../../ui/feedback";
import type { PanelContext } from "../panelContext";
import { usd } from "../../ui/charts";

/**
 * SELECTIONS money card (SPRINT D phase-3c) — the owner selections & allowances rollup surfaced in the
 * portal: total allowance vs actual, the net over/under, per-category deltas, and the over-allowance
 * change-order candidates, with a one-click "push to change events" action (idempotent).
 */
export async function renderSelections(ctx: PanelContext) {
  const pid = ctx.host.projectId()!;
  ctx.root.innerHTML = "";
  ctx.root.appendChild(ctx.bar("◈ Selections & allowances", () => { ctx.activeKey = null; void ctx.renderHome(); ctx.buildNav(); }));

  const body = document.createElement("div");
  body.innerHTML = `<div class="meta">Rolling up allowances vs. actuals…</div>`;
  ctx.root.appendChild(body);


  const load = async () => {
    try {
      const s = await ctx.host.api.selectionsSummary(pid);
      body.replaceChildren();

      // headline: net over/under
      const head = document.createElement("div"); head.className = "dash-card"; head.style.marginBottom = "10px";
      const dirCol = s.direction === "over" ? "var(--status-crit)" : s.direction === "under" ? "var(--status-good)" : "var(--fg)";
      const dirLabel = s.direction === "over" ? "over allowance" : s.direction === "under" ? "under allowance (credit)" : "on allowance";
      // UX-CHIPS — the shared chip vocabulary rather than hand-rolled spans. On a cost line an
      // overage is bad and a credit is good, hence goodWhenNegative. The unpriced remainder is
      // stated explicitly: a rollup over half-priced selections is not the same number as a
      // finished one, and the reader should not have to subtract to notice.
      const unpriced = s.count - s.priced;
      head.innerHTML = `<div style="display:flex;justify-content:space-between;align-items:baseline;gap:12px;flex-wrap:wrap">`
        + `<div class="section-title" style="margin:0">Allowance vs. actual</div>`
        + `<div style="font-size:20px;font-weight:800;color:${dirCol}">${s.net_delta >= 0 ? "+" : "−"}${usd(Math.abs(s.net_delta))} <span style="font-size:12px;font-weight:500;opacity:.8">${dirLabel}</span></div></div>`
        + `<div style="margin-top:4px;display:flex;gap:6px;flex-wrap:wrap;align-items:center">`
        + deltaChip(s.net_delta, { currency: true, goodWhenNegative: true })
        + statusChip(`${s.priced}/${s.count} priced`, { tone: unpriced ? "warn" : "ok" })
        + statusChip(`${s.approved} owner-approved`, { tone: s.approved ? "ok" : "neutral" })
        + `</div>`
        + `<div class="meta" style="margin-top:4px">Allowance <b>${usd(s.total_allowance)}</b> · Actual <b>${usd(s.total_actual)}</b></div>`
        + `<div class="meta" style="margin-top:2px">${countNarrative(
            [[s.over_count, "over allowance"], [s.under_count, "under"], [s.on_count, "on allowance"]],
            "No selections priced against an allowance yet")}`
        + (unpriced ? ` · <b>${unpriced}</b> not yet priced, so this total is incomplete` : "")
        + `</div>`;
      body.appendChild(head);

      // per-category deltas
      if (s.by_category.length) {
        const cat = document.createElement("div"); cat.className = "dash-card"; cat.style.marginBottom = "10px";
        cat.innerHTML = `<div class="section-title" style="margin:0 0 4px">By category</div>`
          + s.by_category.map((c) => {
            const col = c.delta > 0 ? "var(--status-crit)" : c.delta < 0 ? "var(--status-good)" : "var(--fg)";
            return `<div class="meta" style="display:flex;justify-content:space-between;margin:1px 0"><span>${esc(c.category)} <span style="opacity:.6">(${c.count})</span></span>`
              + `<span style="color:${col};font-variant-numeric:tabular-nums">${c.delta >= 0 ? "+" : "−"}${usd(Math.abs(c.delta))}</span></div>`;
          }).join("");
        body.appendChild(cat);
      }

      // over-allowance change-order candidates + push action
      const co = document.createElement("div"); co.className = "dash-card";
      const rows = s.co_candidates.length
        ? s.co_candidates.map((x) => `<div class="meta" style="display:flex;justify-content:space-between;margin:1px 0">`
            + `<span>${esc(x.item ?? x.ref)} <span style="opacity:.6">${esc(x.category)}</span></span>`
            + `<span style="color:var(--status-crit);font-variant-numeric:tabular-nums">+${usd(x.delta)}</span></div>`).join("")
        : `<div class="meta">No over-allowance selections — nothing to push.</div>`;
      co.innerHTML = `<div style="display:flex;justify-content:space-between;align-items:center;gap:8px">`
        + `<div class="section-title" style="margin:0">Change-order candidates (${s.co_candidate_count})</div></div>` + rows;
      if (s.co_candidate_count > 0) {
        const btn = document.createElement("button"); btn.className = "btn"; btn.style.marginTop = "8px";
        btn.textContent = "→ Push overages to change events";
        btn.title = "Create a change event (reason 'Allowance Reconciliation', ROM = the overage) for each over-allowance selection. Idempotent — already-pushed overages are skipped.";
        btn.onclick = async () => {
          btn.disabled = true; btn.textContent = "Pushing…";
          try {
            const r = await ctx.host.api.pushSelectionChangeEvents(pid);
            btn.textContent = `✓ ${r.created} created, ${r.skipped} already tracked`;
          } catch (e) {
            btn.disabled = false; btn.textContent = "→ Push overages to change events";
            body.appendChild(Object.assign(document.createElement("div"), { className: "meta", textContent: `Push failed: ${(e as Error).message}` }));
          }
        };
        co.appendChild(btn);
      }
      body.appendChild(co);
    } catch (e) {
      body.innerHTML = `<div class="meta">Selections rollup unavailable: ${esc((e as Error).message)}</div>`;
    }
  };
  await load();
}

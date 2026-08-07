import type { ResolveAction } from "../../api/types";
import { statusChip } from "../../ui/chips";
import { escapeHtml as esc } from "../../ui/feedback";
import type { PanelContext } from "../panelContext";

/**
 * UX-ACT: dispatch a resolve-action descriptor to the right portal behaviour. Shared across the ring so
 * every actionable diagnostic (margin, rules, schedule) resolves the same way. Currently: open_module
 * (optionally filtered) — the one-click jump from a flagged row to the records behind it.
 */
export function dispatchResolveAction(ctx: PanelContext, a: ResolveAction) {
  // open_module / open_record: jump to that module's records view, optionally pre-filtered.
  if ((a.kind === "open_module" || a.kind === "open_record") && a.module) {
    const m = ctx.mods.find((x) => x.key === a.module);
    if (!m) return;
    ctx.activeKey = a.module;
    void ctx.openModule(m, a.q ? { q: a.q } : undefined);
    ctx.buildNav();
    return;
  }
  // navigate: jump to a portal nav-destination (a `__key__` in the destination map).
  if (a.kind === "navigate" && a.target) {
    ctx.navigate(a.target);
    return;
  }
  // select_elements: the diagnostic named geometry, not records — switch to the model workspace and
  // highlight the offending elements. The viewer owns selection, so this hands off through the same
  // window event the rest of the portal uses and calls the viewer's own multi-select.
  if (a.kind === "select_elements" && a.guids?.length) {
    window.dispatchEvent(new CustomEvent("aec:goto-workspace", { detail: "model" }));
    const v = (window as unknown as { __viewer?: { selectByGuids?: (g: string[], fit?: boolean) => Promise<void> } }).__viewer;
    // the workspace switch is async (the viewer may still be mounting) — retry briefly, then give up
    // quietly rather than throwing into a click handler
    let tries = 0;
    const attempt = () => {
      const api = v ?? (window as unknown as { __viewer?: { selectByGuids?: (g: string[], fit?: boolean) => Promise<void> } }).__viewer;
      if (api?.selectByGuids) { void api.selectByGuids(a.guids!, true); return; }
      if (++tries < 20) setTimeout(attempt, 100);
    };
    attempt();
  }
}

/** Build the inline action buttons for a diagnostic row (UX-ACT). Returns "" when there are none. */
export function resolveActionButtons(ctx: PanelContext, actions: ResolveAction[] | undefined, cls = "ux-act"): HTMLElement | null {
  if (!actions?.length) return null;
  const span = document.createElement("span");
  span.style.cssText = "display:inline-flex;gap:4px;flex-wrap:wrap";
  for (const a of actions) {
    const b = document.createElement("button");
    b.className = cls;
    b.type = "button";
    b.textContent = a.label;
    b.style.cssText = "font-size:10px;padding:1px 6px;border:1px solid var(--border,#3a3a3a);border-radius:4px;background:transparent;color:var(--accent,#5b9);cursor:pointer;white-space:nowrap";
    b.onclick = () => dispatchResolveAction(ctx, a);
    span.appendChild(b);
  }
  return span;
}

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
      + (m.over_committed_codes ? ` · ${statusChip(`${m.over_committed_codes} over-committed`, { tone: "bad" })}` : "")
      + (m.over_budget_codes ? ` · ${statusChip(`${m.over_budget_codes} over-budget`, { tone: "bad" })}` : "") + `</div>`;
    body.appendChild(head);

    // COST-SPINE — the coverage caveat belongs next to the number that inherits it. A buyout margin
    // computed over 55%-traceable spend is a different claim from one computed over 100%, and the
    // reader should not have to go and work that out on another screen. Loaded separately so a slow
    // or failing trace never blocks the margin table.
    void ctx.host.api.costSpine(pid).then((sp) => {
      if (sp.traceability_pct === null) return;              // nothing spent yet — no caveat to make
      const clean = sp.traceability_pct === 100 && !sp.unassigned_count;
      const band = document.createElement("div");
      band.className = "dash-card";
      band.style.cssText = "margin:-4px 0 10px;display:flex;gap:8px;align-items:center;flex-wrap:wrap";
      band.innerHTML = statusChip(`${sp.traceability_pct}% traceable`, { tone: clean ? "ok" : "warn" })
        + (sp.unassigned_count
          ? statusChip(`${sp.unassigned_count} uncoded · ${usd(sp.unassigned_total)}`, { tone: "bad" })
          : "")
        + (sp.broken.length ? statusChip(`${sp.broken.length} broken chain${sp.broken.length === 1 ? "" : "s"}`, { tone: "warn" }) : "")
        + `<span class="meta" style="flex:1;min-width:220px">${esc(sp.note)}</span>`;
      const open = document.createElement("button");
      open.className = "ux-act"; open.type = "button"; open.textContent = "Cost spine →";
      open.style.cssText = "font-size:10px;padding:1px 6px;border:1px solid var(--border,#3a3a3a);border-radius:4px;background:transparent;color:var(--accent,#5b9);cursor:pointer";
      open.onclick = () => { void renderCostSpine(ctx); };
      band.appendChild(open);
      head.insertAdjacentElement("afterend", band);
    }).catch(() => { /* the trace is a caveat on the table, never a blocker for it */ });

    const wrap = document.createElement("div"); wrap.className = "dash-card"; wrap.style.overflowX = "auto";
    const t = document.createElement("table"); t.className = "portal-table"; t.style.cssText = "width:100%;font-size:11px";
    t.innerHTML = `<thead><tr><th scope="col" style="text-align:left">Cost code</th>`
      + `<th scope="col" style="text-align:right">Budget</th><th scope="col" style="text-align:right">Committed</th>`
      + `<th scope="col" style="text-align:right">Actual</th><th scope="col" style="text-align:right">Buyout margin</th>`
      + `<th scope="col" style="text-align:right">Variance</th><th scope="col" style="text-align:left">Fix</th></tr></thead><tbody>`
      + m.rows.map((r, i) => {
        const flag = r.over_budget ? " " + statusChip("Over budget", { tone: "bad" })
          : r.over_committed ? " " + statusChip("Over-committed", { tone: "warn" }) : "";
        return `<tr><td style="text-align:left">${esc(r.cost_code)}${flag}</td>`
          + `<td style="text-align:right;font-variant-numeric:tabular-nums">${usd(r.budget)}</td>`
          + `<td style="text-align:right;font-variant-numeric:tabular-nums">${usd(r.committed)}</td>`
          + `<td style="text-align:right;font-variant-numeric:tabular-nums">${usd(r.actual)}</td>`
          + `<td style="text-align:right;font-variant-numeric:tabular-nums;color:${marginCol(r.buyout_margin)}">${usd(r.buyout_margin)}</td>`
          + `<td style="text-align:right;font-variant-numeric:tabular-nums;color:${marginCol(r.variance)}">${usd(r.variance)}</td>`
          + `<td style="text-align:left" data-act="${i}"></td></tr>`;
      }).join("") + `</tbody>`;
    // UX-ACT: inject the one-click resolve buttons into each flagged row's Fix cell (onclick needs DOM)
    m.rows.forEach((r, i) => {
      const cell = t.querySelector(`td[data-act="${i}"]`);
      const btns = resolveActionButtons(ctx, r.actions);
      if (cell && btns) cell.appendChild(btns);
    });
    wrap.appendChild(t);
    body.appendChild(wrap);

    // COMMERCIAL DRIFT — per DOCUMENT, beside the per-code table it cannot be derived from.
    // The table above adds before it compares: two subcontracts can net to the right code total
    // while one award drifted up and another down. This walks bid -> executed contract -> invoiced
    // along references the registers already carry, so the individual award is visible.
    // Change orders are NOT drift here (they are money somebody signed for) and a hop missing a
    // figure on either side is `incomparable`, which is not a zero-dollar difference.
    void ctx.host.api.commercialDrift(pid).then((cd) => {
      if (!cd.subcontract_count) return;
      const drifted = cd.rows.filter((r) => r.hops.some((h) => h.status === "compared" && h.delta));
      if (!drifted.length && !cd.hops_incomparable) return;
      const card = document.createElement("div"); card.className = "dash-card"; card.style.marginTop = "10px";
      const dt = document.createElement("table"); dt.className = "portal-table"; dt.style.fontSize = "11px";
      dt.innerHTML = `<thead><tr><th scope="col" style="text-align:left">Subcontract</th>`
        + `<th scope="col" style="text-align:left">Hop</th><th scope="col" style="text-align:right">From</th>`
        + `<th scope="col" style="text-align:right">To</th><th scope="col" style="text-align:right">Drift</th></tr></thead>`;
      const tb = document.createElement("tbody");
      for (const r of drifted.slice(0, 25)) {
        for (const h of r.hops) {
          if (h.status !== "compared" || !h.delta) continue;
          const col = (h.delta ?? 0) > 0 ? "var(--status-crit)" : "var(--status-good)";
          tb.innerHTML += `<tr><td>${esc(r.vendor)}</td><td class="meta">${esc(h.hop.replace(/_/g, " "))}</td>`
            + `<td style="text-align:right">${h.from == null ? "—" : usd(h.from)}</td>`
            + `<td style="text-align:right">${h.to == null ? "—" : usd(h.to)}</td>`
            + `<td style="text-align:right;color:${col}">${usd(h.delta)}`
            + (h.drift_pct == null ? "" : ` <span class="meta">${h.drift_pct > 0 ? "+" : ""}${h.drift_pct}%</span>`)
            + `</td></tr>`;
        }
      }
      dt.appendChild(tb);
      card.innerHTML = `<b>Commercial drift</b> <span class="meta">per document, along bid → contract → invoiced`
        + (cd.total_change_orders ? ` · ${usd(cd.total_change_orders)} in change orders, counted as agreed and NOT as drift` : "")
        + (cd.hops_incomparable ? ` · ${cd.hops_incomparable} hop(s) incomparable — a figure is missing on one side, which is not a zero difference` : "")
        + `</span>`;
      card.appendChild(dt);
      body.appendChild(card);
    }).catch(() => { /* drift is best-effort; the per-code table stands on its own */ });
  } catch (e) {
    body.innerHTML = `<div class="meta">Cost-code margin unavailable: ${esc((e as Error).message)}</div>`;
  }
}

/**
 * COST-SPINE panel — cost-code identity across budget → commitment → actual → invoice.
 *
 * The margin table answers "what is the margin on 03-3000". This answers the question underneath it:
 * is 03-3000 the same scope at every stage? A code that appears at one stage and not the next still
 * produces a margin row that looks fine, so this shows PRESENCE — a stage strip per code, where the
 * chain first breaks, and the spend that carries no code at all and therefore appears in no per-code
 * row anywhere.
 */
export async function renderCostSpine(ctx: PanelContext) {
  const pid = ctx.host.projectId()!;
  ctx.root.innerHTML = "";
  ctx.root.appendChild(ctx.bar("🧬 Cost spine", () => { void renderMargin(ctx); }));

  const body = document.createElement("div");
  body.innerHTML = `<div class="meta">Tracing cost-code identity across the stages…</div>`;
  ctx.root.appendChild(body);
  const usd = (n: number) => (n < 0 ? "−$" : "$") + Math.round(Math.abs(n)).toLocaleString();

  try {
    const sp = await ctx.host.api.costSpine(pid);
    body.replaceChildren();

    const head = document.createElement("div"); head.className = "dash-card"; head.style.marginBottom = "10px";
    const clean = sp.traceability_pct === 100 && !sp.unassigned_count;
    head.innerHTML = `<div class="section-title" style="margin:0 0 4px">Traceability</div>`
      + `<div style="display:flex;gap:6px;flex-wrap:wrap;align-items:center;margin-bottom:4px">`
      + (sp.traceability_pct === null ? statusChip("nothing spent yet", { tone: "neutral" })
        : statusChip(`${sp.traceability_pct}% of spend on a budgeted code`, { tone: clean ? "ok" : "warn" }))
      + (sp.unassigned_count ? statusChip(`${sp.unassigned_count} record(s) with no cost code · ${usd(sp.unassigned_total)}`, { tone: "bad" }) : "")
      + (sp.codes_not_in_register.length ? statusChip(`${sp.codes_not_in_register.length} off-register code(s)`, { tone: "warn" }) : "")
      + `</div><div class="meta">${esc(sp.note)}</div>`;
    body.appendChild(head);

    if (!sp.code_count) {
      const none = document.createElement("div"); none.className = "meta";
      none.textContent = "No cost-coded budget or spend records yet — nothing to trace.";
      body.appendChild(none);
      return;
    }

    const wrap = document.createElement("div"); wrap.className = "dash-card"; wrap.style.overflowX = "auto";
    const t = document.createElement("table"); t.className = "tbl"; t.style.width = "100%";
    t.innerHTML = `<thead><tr><th>Cost code</th><th>Chain</th>`
      + sp.stages.map((s) => `<th style="text-align:right">${esc(s)}</th>`).join("")
      + `<th>Issue</th><th></th></tr></thead>`;
    const tb = document.createElement("tbody");
    for (const r of sp.rows) {
      const tr = document.createElement("tr");
      // the stage strip: a filled pip per stage the code actually reaches, so a broken chain is
      // visible at a glance rather than inferred from four numbers
      const strip = sp.stages.map((s) => {
        const on = (r.counts[s] ?? 0) > 0;
        const broke = r.first_break === s;
        return `<span title="${esc(s)}${on ? "" : " — absent"}" style="display:inline-block;width:9px;height:9px;border-radius:50%;margin-right:3px;`
          + `background:${on ? "var(--status-good)" : broke ? "var(--status-crit)" : "var(--border,#3a3a3a)"}"></span>`;
      }).join("");
      tr.innerHTML = `<td>${esc(r.cost_code)}</td><td style="white-space:nowrap">${strip}</td>`
        + sp.stages.map((s) => {
          const v = (r as unknown as Record<string, number>)[s] ?? 0;
          return `<td style="text-align:right;font-variant-numeric:tabular-nums">${v ? usd(v) : "—"}</td>`;
        }).join("")
        + `<td>${r.flags.map((f) => statusChip(f.replace(/_/g, " "),
             { tone: f === "budget_without_spend" ? "info" : "bad" })).join(" ")}</td>`;
      const act = document.createElement("td");
      const btns = resolveActionButtons(ctx, r.actions);
      if (btns) act.appendChild(btns);
      tr.appendChild(act);
      tb.appendChild(tr);
    }
    t.appendChild(tb); wrap.appendChild(t); body.appendChild(wrap);

    if (sp.unused_register_codes.length) {
      const un = document.createElement("div"); un.className = "dash-card"; un.style.marginTop = "10px";
      un.innerHTML = `<div class="section-title" style="margin:0 0 4px">Register codes never used (${sp.unused_register_codes.length})</div>`
        + `<div class="meta">Normal early on. Late in a job it means the estimate's scope breakdown and the actual buyout have drifted apart.</div>`
        + `<div class="meta" style="margin-top:4px">${sp.unused_register_codes.map(esc).join(" · ")}</div>`;
      body.appendChild(un);
    }
  } catch (e) {
    body.innerHTML = `<div class="meta">Cost spine unavailable: ${esc((e as Error).message)}</div>`;
  }
}

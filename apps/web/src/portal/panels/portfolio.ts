import { esc, usd } from "../../ui/charts";
import type { PanelContext } from "../panelContext";

/**
 * REL-4 — **executive portfolio**, out of `portal.ts`.
 *
 * The cross-project view an owner or lender asks for: portfolio KPIs, the per-project table,
 * prioritisation, and the compare card — each fetched independently so one slow endpoint does not
 * blank the others.
 *
 * ## Chosen by the method REL-4 states, not by size
 *
 * That entry says to grep the `this.` references of every candidate BEFORE naming a slice, because
 * doing it the other way round picked a method that turned out not to be a leaf. Done here, over
 * the four largest remaining:
 *
 *   | method | lines | touches on the class |
 *   |---|---|---|
 *   | `renderPortfolio` | 116 | the PanelContext surface only — **a leaf** |
 *   | `renderDesignHome` | 94 | five SIBLING renders (analyse, ids, lifecycle, modelQa, program) |
 *   | `renderPxBand` | 54 | two sibling renders (budget, scheduleViews) |
 *   | `renderModelQa` | 34 | a leaf, but small |
 *
 * The two mid-sized ones are not leaves: extracting either would drag five more methods across the
 * seam or leave it calling back into the class. `renderPortfolio` is bigger AND cleaner, which is
 * only visible if you look at the references first.
 *
 * `this.panelCtx()` collapses to `ctx` — the nested `renderDealBrief` call already took exactly
 * the context this function now receives.
 */
export async function renderPortfolio(ctx: PanelContext) {
  ctx.root.innerHTML = "";
  ctx.root.appendChild(ctx.bar("Portfolio", () => { ctx.activeKey = null; void ctx.renderHome(); ctx.buildNav(); }));
  ctx.root.appendChild(await (await import("./dealBrief")).renderDealBrief(ctx));
  const vcol = (v: number) => v < 0 ? "var(--status-crit)" : v > 0 ? "var(--status-good)" : "var(--muted)";
  const pill: Record<string, [string, string]> = { on_track: ["On track", "var(--status-good)"], at_risk: ["At risk", "var(--status-warn)"], behind: ["Behind", "var(--status-crit)"] };
  const status = document.createElement("div"); status.className = "meta"; status.textContent = "loading portfolio…";
  ctx.root.appendChild(status);
  const here = ctx.host.projectId();

  void ctx.host.api.executivePortfolio().then((pf) => {
    status.remove();
    const t = pf.totals, ta = pf.status_tally;
    const kpis = document.createElement("div"); kpis.className = "dash-cols"; kpis.style.marginBottom = "10px";
    const kpi = (label: string, val: string, color?: string) => {
      const c = document.createElement("div"); c.className = "dash-card"; c.style.flex = "1";
      c.innerHTML = `<div class="meta">${label}</div><div style="font-size:18px;font-weight:700${color ? `;color:${color}` : ""}">${val}</div>`;
      return c;
    };
    const irrPct = (v: number | null) => v == null ? "—" : `${(v * 100).toFixed(1)}%`;
    kpis.append(
      kpi("Projects", String(pf.project_count)),
      kpi("Portfolio GMP", usd(t.gmp)),
      kpi("Variance at completion", usd(t.variance_at_completion), vcol(t.variance_at_completion)),
      kpi("Blended equity IRR", irrPct(t.blended_equity_irr)),
      kpi("Status", `${ta.on_track}✓ ${ta.at_risk}△ ${ta.behind}⚠`),
    );
    ctx.root.appendChild(kpis);

    const card = document.createElement("div"); card.className = "dash-card";
    const tbl = document.createElement("table"); tbl.className = "portal-table"; tbl.style.fontSize = "11px";
    tbl.innerHTML = `<thead><tr><th scope="col">Project</th><th scope="col">Status</th><th scope="col" style="text-align:right">CPI</th><th scope="col" style="text-align:right">SPI</th>`
      + `<th scope="col" style="text-align:right">% cmpl</th><th scope="col" style="text-align:right">GMP</th>`
      + `<th scope="col" style="text-align:right">VAC</th><th scope="col" style="text-align:right">Equity IRR</th><th scope="col" style="text-align:right">EM</th><th scope="col" style="text-align:right">Late MS</th></tr></thead>`;
    const tb = document.createElement("tbody");
    for (const p of pf.projects) {
      const tr = document.createElement("tr"); tr.className = "kpi-click";
      if (p.id === here) tr.style.fontWeight = "700";
      const [lbl, col] = pill[p.status] ?? ["—", "var(--muted)"];
      const irrCol = p.equity_irr == null ? "var(--muted)" : p.equity_irr >= 0.15 ? "var(--status-good)" : p.equity_irr >= 0.12 ? "var(--status-warn)" : "var(--status-crit)";
      tr.innerHTML = `<td>${esc(p.name)}${p.id === here ? " ·" : ""}</td>`
        + `<td><span class="ball-badge" style="background:${col}22;color:${col};border-color:${col}">${lbl}</span></td>`
        + `<td style="text-align:right;color:${p.cpi == null ? "var(--muted)" : p.cpi >= 0.95 ? "var(--status-good)" : "var(--status-crit)"}">${p.cpi ?? "—"}</td>`
        + `<td style="text-align:right;color:${p.spi == null ? "var(--muted)" : p.spi >= 0.95 ? "var(--status-good)" : "var(--status-crit)"}">${p.spi ?? "—"}</td>`
        + `<td style="text-align:right">${p.pct_complete}%</td><td style="text-align:right">${usd(p.gmp)}</td>`
        + `<td style="text-align:right;color:${vcol(p.variance_at_completion)}">${usd(p.variance_at_completion)}</td>`
        + `<td style="text-align:right;color:${irrCol}">${irrPct(p.equity_irr)}</td>`
        + `<td style="text-align:right">${p.equity_multiple == null ? "—" : p.equity_multiple + "×"}</td>`
        + `<td style="text-align:right;color:${p.milestones_late ? "var(--status-crit)" : "var(--muted)"}">${p.milestones_late || "—"}</td>`;
      tr.onclick = () => { if (p.id !== here) window.location.search = `?project=${p.id}`; };
      tb.appendChild(tr);
    }
    tbl.appendChild(tb); card.appendChild(tbl); ctx.root.appendChild(card);
    ctx.root.appendChild(Object.assign(document.createElement("div"), { className: "meta",
      textContent: "Click a project to switch to it. On-schedule (SPI / % complete / late milestones) + on-budget (GMP / variance) + developer returns (IRR / EM) across the book." }));
    // prioritization matrix — projects ranked 0-100 on return / budget / schedule / risk
    void ctx.host.api.portfolioPrioritization().then((pr) => {
      if (!pr.projects.length) return;
      const pc = document.createElement("div"); pc.className = "dash-card"; pc.style.marginTop = "10px";
      const bar = (v: number) => { const col = v >= 70 ? "var(--status-good)" : v >= 45 ? "var(--status-warn)" : "var(--status-crit)"; return `<span style="display:inline-block;min-width:34px;text-align:right;color:${col};font-variant-numeric:tabular-nums">${v}</span>`; };
      const pt = document.createElement("table"); pt.className = "portal-table"; pt.style.fontSize = "11px";
      pt.innerHTML = `<thead><tr><th scope="col">#</th><th scope="col">Project</th><th scope="col" style="text-align:right">Score</th>`
        + `<th scope="col" style="text-align:right">Return</th><th scope="col" style="text-align:right">Budget</th>`
        + `<th scope="col" style="text-align:right">Schedule</th><th scope="col" style="text-align:right">Risk</th></tr></thead>`;
      const pb = document.createElement("tbody");
      for (const p of pr.projects) {
        const tr = document.createElement("tr"); tr.className = "kpi-click";
        tr.innerHTML = `<td>${p.rank}</td><td>${esc(p.name)}</td>`
          + `<td style="text-align:right;font-weight:700">${bar(p.composite)}</td>`
          + `<td style="text-align:right">${bar(p.scores.return)}</td><td style="text-align:right">${bar(p.scores.budget)}</td>`
          + `<td style="text-align:right">${bar(p.scores.schedule)}</td><td style="text-align:right">${bar(p.scores.risk)}</td>`;
        tr.onclick = () => { if (p.id !== here) window.location.search = `?project=${p.id}`; };
        pb.appendChild(tr);
      }
      pt.appendChild(pb);
      pc.innerHTML = `<b>Prioritization matrix</b> <span class="meta">weighted 0–100 · return ${Math.round(pr.weights.return * 100)}% / budget ${Math.round(pr.weights.budget * 100)}% / schedule ${Math.round(pr.weights.schedule * 100)}% / risk ${Math.round(pr.weights.risk * 100)}%</span>`;
      pc.appendChild(pt);
      ctx.root.appendChild(pc);
    }).catch(() => { /* prioritization is best-effort */ });

    // RETURNS SPREAD — the executive roll-up above gives a BLENDED equity IRR, which is one number
    // for the whole book and cannot show that one deal is carrying it. `/proforma/portfolio/compare`
    // gives per-project IRR / equity multiple / yield-on-cost from each project's latest solved
    // scenario, plus the best-and-worst spread. An `absent` return renders as em-dash, never 0%:
    // a project with no solved scenario has not returned zero, and on a spread a fabricated zero
    // would take the "worst" slot away from a deal that genuinely holds it.
    void ctx.host.api.portfolioCompare().then((pc2) => {
      if (!pc2.rows.length) return;
      const card = document.createElement("div"); card.className = "dash-card"; card.style.marginTop = "10px";
      const num = (v: number | null, f: (n: number) => string) => v == null ? "—" : f(v);
      const ct = document.createElement("table"); ct.className = "portal-table"; ct.style.fontSize = "11px";
      ct.innerHTML = `<thead><tr><th scope="col" style="text-align:left">Project</th><th scope="col" style="text-align:left">Scenario</th>`
        + `<th scope="col" style="text-align:right">Equity IRR</th><th scope="col" style="text-align:right">Multiple</th>`
        + `<th scope="col" style="text-align:right">Yield on cost</th><th scope="col" style="text-align:right">Total uses</th></tr></thead>`;
      const cb = document.createElement("tbody");
      for (const r of pc2.rows) {
        const tr = document.createElement("tr"); tr.className = "kpi-click";
        tr.innerHTML = `<td>${esc(r.project_name)}</td><td class="meta">${esc(r.scenario_name)}</td>`
          + `<td style="text-align:right">${num(r.equity_irr, (n) => `${(n * 100).toFixed(1)}%`)}</td>`
          + `<td style="text-align:right">${num(r.equity_multiple, (n) => `${n.toFixed(2)}x`)}</td>`
          + `<td style="text-align:right">${num(r.yield_on_cost, (n) => `${(n * 100).toFixed(2)}%`)}</td>`
          + `<td style="text-align:right">${num(r.total_uses, usd)}</td>`;
        tr.onclick = () => { if (r.project_id !== here) window.location.search = `?project=${r.project_id}`; };
        cb.appendChild(tr);
      }
      ct.appendChild(cb);
      const sp = pc2.spread?.equity_irr;
      card.innerHTML = `<b>Returns spread</b> <span class="meta">${pc2.project_count} project(s), each from its latest solved scenario`
        + (sp && sp.best ? ` · best ${esc(sp.best)} · worst ${esc(sp.worst ?? "—")}` : "")
        + `</span>`;
      card.appendChild(ct);
      ctx.root.appendChild(card);
    }).catch(() => { /* returns spread is best-effort; the roll-up above stands on its own */ });
  }).catch(() => { status.className = "empty-state"; status.innerHTML = `Portfolio unavailable<span class="es-hint">Needs at least one project with schedule/budget data.</span>`; });

}

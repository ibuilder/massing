import { groupedBar, money as cmoney } from "../../ui/charts";
import { confirmModal } from "../../ui/modal";
import type { PanelContext } from "../panelContext";

/**
 * GC GMP budget dashboard — the agreed GMP broken to every cost code & bid package plus GC/GR,
 * overhead, fee & contingency, shown budget vs committed vs actual vs EAC with owner + sub billing,
 * buyout savings, and the cost-loaded cash-flow curve. Extracted from portal.ts (PanelContext seam).
 */
export async function renderBudget(ctx: PanelContext) {
  const pid = ctx.host.projectId()!;
  ctx.root.innerHTML = "";
  ctx.root.appendChild(ctx.bar("Budget", () => { ctx.activeKey = null; void ctx.renderHome(); ctx.buildNav(); }));
  const usd = (n: number) => `$${Math.round(n).toLocaleString()}`;
  const vcol = (v: number) => v < 0 ? "var(--status-crit)" : v > 0 ? "var(--status-good)" : "var(--muted)";
  const jumpTo = (k: string) => { const tm = ctx.mods.find((x) => x.key === k); if (tm) { ctx.activeKey = k; void ctx.openModule(tm); ctx.buildNav(); } };

  const intro = document.createElement("div"); intro.style.cssText = "display:flex;gap:6px;align-items:center;flex-wrap:wrap;margin:2px 0 8px";
  const jump = document.createElement("select"); jump.className = "sb-sel"; jump.title = "Open a budget input list";
  jump.innerHTML = `<option value="">＋ edit inputs…</option><option value="cost_code">Cost codes</option>`
    + `<option value="budget">Budget lines</option><option value="staffing">Staffing plan</option>`
    + `<option value="commitment">Commitments / POs</option><option value="bid_package">Bid packages</option>`
    + `<option value="prime_contract">Prime contract (markups)</option>`;
  jump.onchange = () => { if (jump.value) jumpTo(jump.value); };
  const sovBtn = document.createElement("button"); sovBtn.className = "tool-btn"; sovBtn.dataset.cap = "edit";
  sovBtn.textContent = "⎘ Build owner SOV"; sovBtn.title = "Seed the owner pay-app Schedule of Values from these GMP lines";
  sovBtn.onclick = async () => {
    try {
      let r = await ctx.host.api.sovFromBudget(pid);
      if (!r.created && r.skipped && (await confirmModal(`The SOV already has ${r.skipped} lines. Rebuild it from the budget?`, "")))
        r = await ctx.host.api.sovFromBudget(pid, true);
      ctx.host.setStatus(r.created ? `built ${r.created} SOV lines from the budget` : "SOV unchanged");
      if (r.created) jumpTo("sov");
    } catch (e) { ctx.host.setStatus(`couldn't build SOV: ${(e as Error).message}`); }
  };
  const baseBtn = document.createElement("button"); baseBtn.className = "tool-btn"; baseBtn.dataset.cap = "edit";
  baseBtn.textContent = "📌 Set baseline"; baseBtn.title = "Snapshot the current GMP budget to track movement against";
  baseBtn.onclick = async () => {
    if (!(await confirmModal("Snapshot the current GMP budget as the baseline? (re-baseline after an approved change)", ""))) return;
    try { const r = await ctx.host.api.setBudgetBaseline(pid); ctx.host.setStatus(`baseline set (${r.lines} lines)`); void renderBudget(ctx); }
    catch (e) { ctx.host.setStatus(`couldn't set baseline: ${(e as Error).message}`); }
  };
  const note = document.createElement("span"); note.className = "meta";
  note.innerHTML = "The agreed <b>GMP</b> broken to every cost code & bid package + GC/GR, overhead, fee & contingency — budget vs committed vs actual.";
  intro.append(jump, sovBtn, baseBtn, note); ctx.root.appendChild(intro);

  // budget movement vs baseline (shown only if a baseline exists; 409 otherwise → ignored)
  const bvHolder = document.createElement("div"); ctx.root.appendChild(bvHolder);
  void ctx.host.api.budgetVariance(pid).then((v) => {
    const col = v.total_delta > 0 ? "var(--status-crit)" : v.total_delta < 0 ? "var(--status-good)" : "var(--muted)";
    bvHolder.className = "meta"; bvHolder.style.margin = "0 0 6px";
    bvHolder.innerHTML = `Vs baseline (${v.captured_at}): GMP moved <span style="color:${col}">${v.total_delta > 0 ? "+" : ""}$${Math.round(v.total_delta).toLocaleString()}</span>`
      + (v.lines.length ? ` across ${v.lines.length} line${v.lines.length > 1 ? "s" : ""}` : " — no drift");
  }).catch(() => {});

  const status = document.createElement("div"); status.className = "meta"; status.textContent = "loading budget…";
  ctx.root.appendChild(status);

  void ctx.host.api.gmpBudget(pid).then((b) => {
    status.remove();
    const g = b.gmp;
    // headline KPI row
    const kpis = document.createElement("div"); kpis.className = "dash-cols"; kpis.style.marginBottom = "10px";
    const kpi = (label: string, val: string, color?: string) => {
      const c = document.createElement("div"); c.className = "dash-card"; c.style.flex = "1";
      c.innerHTML = `<div class="meta">${label}</div><div style="font-size:18px;font-weight:700${color ? `;color:${color}` : ""}">${val}</div>`;
      return c;
    };
    // defensive defaults so the page renders against any API version (new fields fill once present)
    const comp = b.completion ?? { eac: b.totals.forecast, etc: 0, actual_to_date: b.totals.actual,
      projected_over_under: b.totals.variance, pct_spent: 0, bac: b.totals.budget };
    const buyout = b.buyout ?? { packages: b.bid_packages.length, bought_out: 0, budget: 0, awarded: 0, savings: 0 };
    kpis.append(
      kpi("GMP (computed)", usd(g.computed)),
      kpi("Committed (buyout)", usd(b.totals.committed)),
      kpi("Forecast at completion", usd(comp.eac)),
      kpi("Projected variance", usd(comp.projected_over_under), vcol(comp.projected_over_under)),
    );
    ctx.root.appendChild(kpis);

    // cost-to-complete + buyout savings line
    const ctc = document.createElement("div"); ctc.className = "meta"; ctc.style.margin = "0 0 6px";
    ctc.innerHTML = `Cost to complete (ETC) <b>${usd(comp.etc)}</b> · spent ${usd(comp.actual_to_date)} (${comp.pct_spent}%)`
      + (buyout.bought_out
          ? ` · buyout ${buyout.bought_out}/${buyout.packages} · savings <span style="color:${vcol(buyout.savings)}">${usd(buyout.savings)}</span>` : "");
    ctx.root.appendChild(ctc);

    if (g.approved_changes) {
      const ch = document.createElement("div"); ch.className = "meta"; ch.style.margin = "0 0 6px";
      ch.innerHTML = `Approved changes <b>${usd(g.approved_changes)}</b> → revised GMP <b>${usd(g.revised ?? g.computed)}</b>`
        + (g.unallocated_changes ? ` <span style="color:var(--status-warn)">(${usd(g.unallocated_changes)} unallocated — assign a cost code)</span>` : "");
      ctx.root.appendChild(ch);
    }

    if (g.contract_value || b.proforma) {
      const recon = document.createElement("div"); recon.className = "meta"; recon.style.margin = "0 0 8px";
      recon.innerHTML = (g.contract_value
        ? `Contract GMP <b>${usd(g.contract_value)}</b> · reconciliation <span style="color:${vcol(g.reconciliation ?? 0)}">${usd(g.reconciliation ?? 0)}</span>` : "")
        + (b.proforma ? `${g.contract_value ? " · " : ""}vs developer proforma hard cost <b>${usd(b.proforma.hard_cost)}</b> `
            + `<span style="color:${vcol(-b.proforma.gmp_vs_hard)}">(${b.proforma.gmp_vs_hard > 0 ? "+" : ""}${usd(b.proforma.gmp_vs_hard)})</span>` : "");
      ctx.root.appendChild(recon);
    }

    // category table, with expandable direct-work division groups
    const card = document.createElement("div"); card.className = "dash-card"; card.style.marginBottom = "10px";
    card.appendChild(Object.assign(document.createElement("div"), { className: "section-title", textContent: "Budget by category" }));
    const tbl = document.createElement("table"); tbl.className = "portal-table"; tbl.style.fontSize = "11px";
    tbl.innerHTML = `<thead><tr><th scope="col">Category</th><th scope="col" style="text-align:right">Budget</th>`
      + `<th scope="col" style="text-align:right">Committed</th><th scope="col" style="text-align:right">Actual</th>`
      + `<th scope="col" style="text-align:right">Forecast (EAC)</th><th scope="col" style="text-align:right">Variance</th></tr></thead>`;
    const tb = document.createElement("tbody");
    const row = (name: string, c: { budget: number; committed: number; actual: number; eac?: number; variance: number }, opts: { bold?: boolean; indent?: boolean } = {}) => {
      const tr = document.createElement("tr"); if (opts.bold) tr.style.fontWeight = "700";
      tr.innerHTML = `<td style="${opts.indent ? "padding-left:16px;color:var(--muted)" : ""}">${name}</td>`
        + `<td style="text-align:right">${usd(c.budget)}</td><td style="text-align:right">${usd(c.committed)}</td>`
        + `<td style="text-align:right">${usd(c.actual)}</td><td style="text-align:right">${usd(c.eac ?? c.budget)}</td>`
        + `<td style="text-align:right;color:${vcol(c.variance)}">${usd(c.variance)}</td>`;
      return tr;
    };
    for (const cat of b.categories) {
      tb.appendChild(row(cat.name, cat, { bold: cat.key === "direct" }));
      if (cat.key === "direct") for (const grp of (cat.groups ?? [])) {       // division breakdown
        tb.appendChild(row(grp.name, { budget: grp.budget, committed: 0, actual: 0, variance: 0 } as any, { indent: true }));
      }
    }
    tb.appendChild(row("Total (GMP)", b.totals, { bold: true }));
    tbl.appendChild(tb); card.appendChild(tbl);
    // budget vs committed vs actual vs EAC, by category — grouped bar
    const cats = (b.categories || []).filter((c: { budget?: number }) => (c.budget ?? 0) > 0);
    if (cats.length) {
      const chart = document.createElement("div"); chart.style.marginTop = "8px";
      chart.innerHTML = `<div class="section-title" style="margin:0 0 2px">Budget vs committed vs actual vs EAC</div>`
        + groupedBar(cats.map((c: { name: string; budget?: number; committed?: number; actual?: number; eac?: number }) => ({
            label: c.name, bars: [
              { name: "Budget", value: c.budget ?? 0 }, { name: "Committed", value: c.committed ?? 0 },
              { name: "Actual", value: c.actual ?? 0 }, { name: "EAC", value: c.eac ?? c.budget ?? 0 },
            ],
          })), { title: "Budget vs committed vs actual vs EAC", fmt: cmoney, height: 180 });
      card.appendChild(chart);
    }
    ctx.root.appendChild(card);

    // bid-package buyout
    const bc = document.createElement("div"); bc.className = "dash-card"; bc.style.marginBottom = "10px";
    const bh = document.createElement("div"); bh.className = "section-title";
    bh.style.cssText = "display:flex;justify-content:space-between;align-items:center";
    bh.append(Object.assign(document.createElement("span"), { textContent: `Bid-package buyout (${b.bid_packages.length})` }));
    bh.append(Object.assign(document.createElement("span"), { className: "meta",
      textContent: buyout.bought_out ? ` ${buyout.bought_out} bought out · savings ${usd(buyout.savings)}` : "" }));
    const openBp = document.createElement("button"); openBp.className = "tool-btn"; openBp.textContent = "open"; openBp.onclick = () => jumpTo("bid_package");
    bh.appendChild(openBp); bc.appendChild(bh);
    if (b.bid_packages.length) {
      for (const bp of b.bid_packages) {
        const r = document.createElement("div"); r.className = "meta"; r.style.margin = "1px 0";
        r.innerHTML = `${bp.name ?? bp.ref}${bp.trade ? ` · ${bp.trade}` : ""} · budget <b>${usd(bp.budget)}</b>`
          + (bp.bought_out
              ? ` · awarded <b>${usd(bp.awarded)}</b> · savings <span style="color:${vcol(bp.savings)}">${usd(bp.savings)}</span>`
              : ` · ${bp.submissions || 0} bids · <span style="color:var(--status-warn)">not bought out</span>`);
        bc.appendChild(r);
      }
    } else { bc.appendChild(Object.assign(document.createElement("div"), { className: "meta", textContent: "No bid packages yet." })); }
    ctx.root.appendChild(bc);

    // owner billing — close the loop: budget → SOV → G702/G703 pay app → owner invoice
    const billing = document.createElement("div"); billing.className = "dash-card"; billing.style.marginBottom = "10px";
    billing.appendChild(Object.assign(document.createElement("div"), { className: "section-title", textContent: "Owner billing" }));
    const brow = document.createElement("div"); brow.style.cssText = "display:flex;gap:6px;flex-wrap:wrap;align-items:center";
    const seedBtn = document.createElement("button"); seedBtn.className = "tool-btn"; seedBtn.dataset.cap = "edit";
    seedBtn.textContent = "↻ Seed SOV from budget";
    seedBtn.onclick = async () => {
      try { const r = await ctx.host.api.sovFromBudget(pid, true);
        ctx.host.setStatus(`SOV seeded: ${r.created} lines${r.scheduled_value ? ` = $${Math.round(r.scheduled_value).toLocaleString()}` : ""}`); }
      catch (e) { ctx.host.setStatus(`SOV seed failed: ${(e as Error).message}`); }
    };
    const pdfBtn = document.createElement("button"); pdfBtn.className = "tool-btn"; pdfBtn.textContent = "⬇ Pay app (PDF)";
    pdfBtn.onclick = async () => {
      try { const blob = await ctx.host.api.payAppPdf(pid, 1);
        const a = document.createElement("a"); a.href = URL.createObjectURL(blob); a.download = "pay-app-1.pdf"; a.click(); URL.revokeObjectURL(a.href);
        ctx.host.setStatus("pay-app PDF generated"); }
      catch (e) { ctx.host.setStatus(`pay app failed: ${(e as Error).message}`); }
    };
    const invBtn = document.createElement("button"); invBtn.className = "tool-btn"; invBtn.dataset.cap = "edit";
    invBtn.textContent = "＋ Owner invoice from draw";
    invBtn.onclick = async () => {
      try { const r = await ctx.host.api.payAppInvoice(pid, 1);
        ctx.host.setStatus(`owner invoice created: $${Math.round(r.amount).toLocaleString()}`); jumpTo("owner_invoice"); }
      catch (e) { ctx.host.setStatus(`invoice failed: ${(e as Error).message}`); }
    };
    brow.append(seedBtn, pdfBtn, invBtn); billing.appendChild(brow);
    billing.appendChild(Object.assign(document.createElement("div"), { className: "meta",
      textContent: "The G702/G703 pay app and owner invoice draw from this same budget-seeded Schedule of Values." }));
    ctx.root.appendChild(billing);

    // subcontractor billing — the GC-pays-subs mirror of owner billing
    const subc = document.createElement("div"); subc.className = "dash-card"; subc.style.marginBottom = "10px";
    const sh = document.createElement("div"); sh.className = "section-title";
    sh.style.cssText = "display:flex;justify-content:space-between;align-items:center";
    sh.append(Object.assign(document.createElement("span"), { textContent: "Subcontractor billing" }));
    const openSi = document.createElement("button"); openSi.className = "tool-btn"; openSi.textContent = "open"; openSi.onclick = () => jumpTo("sub_invoice");
    sh.appendChild(openSi); subc.appendChild(sh);
    const sbody = document.createElement("div"); sbody.innerHTML = `<div class="meta">loading…</div>`;
    subc.appendChild(sbody); ctx.root.appendChild(subc);
    void ctx.host.api.subcontractorBilling(pid).then((sb) => {
      if (!sb.invoice_count) { sbody.innerHTML = `<div class="meta">No subcontractor invoices yet — log them in Subcontractor Invoices.</div>`; return; }
      const t = sb.totals;
      sbody.innerHTML = `<div class="meta" style="margin-bottom:4px">${sb.subs.length} subs · billed <b>${usd(t.billed)}</b> of ${usd(t.contract_value)} `
        + `· retainage ${usd(t.retainage)} · paid ${usd(t.paid)} · remaining ${usd(t.remaining)}</div>`;
      for (const s of sb.subs.slice(0, 8)) {
        const r = document.createElement("div"); r.className = "meta"; r.style.margin = "1px 0";
        r.innerHTML = `${s.vendor ?? s.subcontract_ref ?? "—"}${s.trade ? ` · ${s.trade}` : ""}: billed <b>${usd(s.billed)}</b>`
          + (s.contract_value ? ` / ${usd(s.contract_value)}` : "") + ` · retainage ${usd(s.retainage)} · paid ${usd(s.paid)}`;
        sbody.appendChild(r);
      }
    }).catch(() => { sbody.innerHTML = `<div class="meta">Subcontractor billing unavailable.</div>`; });

    // cash-flow / draw curve — the cost-loaded schedule (monthly bars + cumulative S-curve)
    const cfCard = document.createElement("div"); cfCard.className = "dash-card"; cfCard.style.marginBottom = "10px";
    cfCard.appendChild(Object.assign(document.createElement("div"), { className: "section-title", textContent: "Cash flow (cost-loaded schedule)" }));
    const cfBody = document.createElement("div"); cfBody.innerHTML = `<div class="meta">loading cash flow…</div>`;
    cfCard.appendChild(cfBody); ctx.root.appendChild(cfCard);
    void ctx.host.api.budgetCashflow(pid).then((cf) => {
      if (!cf.series.length) { cfBody.innerHTML = `<div class="meta">No cash flow yet — give schedule activities a budgeted cost + start/finish dates.</div>`; return; }
      const W = 560, H = 130, pad = 22, n = cf.series.length;
      const maxCost = Math.max(...cf.series.map((s) => s.cost), 1);
      const bw = (W - pad * 2) / n;
      const bars = cf.series.map((s, i) => {
        const h = (s.cost / maxCost) * (H - pad * 2);
        return `<rect x="${pad + i * bw + 1}" y="${H - pad - h}" width="${Math.max(1, bw - 2)}" height="${h}" fill="var(--accent)" opacity="0.55"/>`;
      }).join("");
      const pts = cf.series.map((s, i) => `${pad + i * bw + bw / 2},${(H - pad) - (s.pct / 100) * (H - pad * 2)}`).join(" ");
      const ticks = cf.series.map((s, i) => (i % Math.ceil(n / 6) === 0
        ? `<text x="${pad + i * bw + bw / 2}" y="${H - 6}" fill="var(--muted)" font-size="8" text-anchor="middle">${s.month.slice(2)}</text>` : "")).join("");
      cfBody.innerHTML = `<div class="meta" style="margin-bottom:4px">Total <b>${usd(cf.total)}</b> over ${cf.months} months · peak ${usd(cf.peak_month_cost)}/mo · ${cf.loaded_activities} cost-loaded activities</div>`
        + `<svg viewBox="0 0 ${W} ${H}" width="100%" role="img" aria-label="cash flow curve">${bars}`
        + `<polyline points="${pts}" fill="none" stroke="var(--status-good)" stroke-width="1.5"/>${ticks}</svg>`;
    }).catch(() => { cfBody.innerHTML = `<div class="meta">Cash flow unavailable.</div>`; });

    const foot = document.createElement("div"); foot.className = "meta"; foot.style.marginTop = "2px";
    foot.innerHTML = `Staffing projection ${usd(b.staffing.projected)} across ${b.staffing.headcount_roles} roles · `
      + `markups: ${g.markups.overhead_pct}% OH · ${g.markups.fee_pct}% fee · ${g.markups.contingency_pct}% contingency`;
    ctx.root.appendChild(foot);
  }).catch(() => {
    status.className = "empty-state";
    status.innerHTML = `Budget not available yet<span class="es-hint">Add cost codes + budget lines, a staffing plan, bid packages, and a prime contract with markup % — then the GMP assembles here.</span>`;
  });
}

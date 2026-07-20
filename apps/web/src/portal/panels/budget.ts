import { groupedBar, money as cmoney, esc } from "../../ui/charts";
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

  // SURF-2: model-based estimating + 2D takeoff were fully backed but had no surface. One card, a
  // button row, and a shared results drawer — each button fills it on demand.
  const estCard = document.createElement("div"); estCard.className = "dash-card"; estCard.style.marginBottom = "10px";
  const estHead = document.createElement("div"); estHead.className = "section-title"; estHead.textContent = "📐 Estimate from the model";
  const estRow = document.createElement("div"); estRow.style.cssText = "display:flex;gap:6px;flex-wrap:wrap;margin:4px 0";
  const estDrawer = document.createElement("div"); estDrawer.innerHTML = `<div class="meta">Price the model's takeoff against the cost DB, or take off a 2D CAD sheet.</div>`;
  estCard.append(estHead, estRow, estDrawer); ctx.root.appendChild(estCard);
  const fillEst = (html: string) => { estDrawer.innerHTML = html; };
  const rows = (arr: string[]) => arr.join("");

  const emBtn = document.createElement("button"); emBtn.className = "tool-btn"; emBtn.textContent = "＄ Conceptual (unit-rate)";
  emBtn.title = "Conceptual estimate: the model's IFC takeoff × cost-DB unit rates → priced line items";
  emBtn.onclick = async () => {
    fillEst(`<div class="meta">Pricing the model…</div>`);
    try {
      const e = await ctx.host.api.estimateFromModel(pid);
      const lines = e.lines.map((l) => `<tr><td>${esc(l.ifc_class.replace("Ifc", ""))}</td><td style="text-align:right">${l.count}</td><td style="text-align:right">${l.quantity.toLocaleString()} ${esc(l.unit)}</td><td style="text-align:right">${usd(l.rate)}</td><td style="text-align:right">${usd(l.amount)}</td></tr>`);
      const unpriced = e.unpriced.length ? `<div class="meta" style="margin-top:4px">Unpriced (no rate): ${e.unpriced.map((u) => `${esc(u.ifc_class.replace("Ifc", ""))}×${u.count}`).join(", ")}</div>` : "";
      fillEst(`<div style="font-weight:600;margin-bottom:4px">Conceptual estimate — <b>${usd(e.total)}</b> · ${e.element_count} elements</div>`
        + `<div style="overflow:auto"><table class="mini-table" style="width:100%"><thead><tr><th>Class</th><th style="text-align:right">Count</th><th style="text-align:right">Qty</th><th style="text-align:right">Rate</th><th style="text-align:right">Amount</th></tr></thead><tbody>${rows(lines)}</tbody></table></div>${unpriced}`);
    } catch (err) { fillEst(`<div class="meta">Estimate unavailable: ${(err as Error).message}</div>`); }
  };
  const rbBtn = document.createElement("button"); rbBtn.className = "tool-btn"; rbBtn.textContent = "🧱 Resource-based (L/M/E)";
  rbBtn.title = "Assembly estimate: each class built up from labor + material + equipment, with crew-hours";
  rbBtn.onclick = async () => {
    fillEst(`<div class="meta">Building resource-loaded estimate…</div>`);
    try {
      const e = await ctx.host.api.estimateResourceBased(pid);
      const trades = e.by_trade.slice(0, 12).map((t) => `<tr><td>${esc(t.name)}</td><td style="text-align:right">${Math.round(t.hours).toLocaleString()} h</td><td style="text-align:right">${usd(t.cost)}</td></tr>`);
      fillEst(`<div style="font-weight:600;margin-bottom:4px">Resource-based — <b>${usd(e.total)}</b> · ${Math.round(e.labor_hours).toLocaleString()} crew-hours</div>`
        + `<div class="meta">Labor ${usd(e.by_kind.labor)} · Material ${usd(e.by_kind.material)} · Equipment ${usd(e.by_kind.equipment)}</div>`
        + `<div style="overflow:auto"><table class="mini-table" style="width:100%"><thead><tr><th>Trade</th><th style="text-align:right">Hours</th><th style="text-align:right">Cost</th></tr></thead><tbody>${rows(trades)}</tbody></table></div>`
        + (e.unmapped.length ? `<div class="meta" style="margin-top:4px">Unmapped: ${e.unmapped.map((u) => `${esc(u.ifc_class.replace("Ifc", ""))}×${u.count}`).join(", ")}</div>` : ""));
    } catch (err) { fillEst(`<div class="meta">Resource estimate unavailable: ${(err as Error).message}</div>`); }
  };
  const bandBtn = document.createElement("button"); bandBtn.className = "tool-btn"; bandBtn.textContent = "📊 Range (low/likely/high)";
  bandBtn.title = "Range estimate: three-point cost bands per line from design-stage uncertainty, rolled to a probabilistic P10/P50/P90 bid range";
  bandBtn.onclick = async () => {
    fillEst(`<div class="meta">Building the range estimate…</div>`);
    try {
      const e = await ctx.host.api.estimateBands(pid);
      const lines = e.lines.slice(0, 20).map((l) => `<tr><td>${esc(l.ifc_class.replace("Ifc", ""))}</td><td style="text-align:right">${usd(l.low)}</td><td style="text-align:right"><b>${usd(l.likely)}</b></td><td style="text-align:right">${usd(l.high)}</td><td style="text-align:right">±${l.spread_pct}%</td></tr>`);
      fillEst(`<div style="font-weight:600;margin-bottom:4px">Range estimate — likely <b>${usd(e.expected)}</b> · ${e.element_count} elements</div>`
        + `<div class="meta">Bid range (P10–P90): <b>${usd(e.range.p10)}</b> – <b>${usd(e.range.p90)}</b> · P50 ${usd(e.range.p50)}</div>`
        + `<div class="meta">Worst/best envelope: ${usd(e.envelope.low)} – ${usd(e.envelope.high)}</div>`
        + `<div style="overflow:auto;margin-top:4px"><table class="mini-table" style="width:100%"><thead><tr><th>Class</th><th style="text-align:right">Low</th><th style="text-align:right">Likely</th><th style="text-align:right">High</th><th style="text-align:right">±</th></tr></thead><tbody>${rows(lines)}</tbody></table></div>`
        + `<div class="meta" style="margin-top:4px">${esc(e.range.note)}</div>`);
    } catch (err) { fillEst(`<div class="meta">Range estimate unavailable: ${(err as Error).message}</div>`); }
  };
  const cbsBtn = document.createElement("button"); cbsBtn.className = "tool-btn"; cbsBtn.textContent = "🧱 Cost breakdown (CBS)";
  cbsBtn.title = "Cost Breakdown Structure: the model's direct cost layered through indirect → contingency → management reserve → overhead & profit → taxes";
  cbsBtn.onclick = async () => {
    fillEst(`<div class="meta">Building the cost breakdown structure…</div>`);
    try {
      const e = await ctx.host.api.estimateCbs(pid);
      const rows2 = e.layers.map((l) => `<tr><td>${esc(l.level)}</td><td style="text-align:right">${l.rate != null ? Math.round(l.rate * 1000) / 10 + "%" : "—"}</td><td style="text-align:right">${usd(l.amount)}</td><td style="text-align:right">${l.pct_of_total}%</td></tr>`);
      fillEst(`<div style="font-weight:600;margin-bottom:4px">Cost breakdown — total <b>${usd(e.total)}</b> (direct ${usd(e.direct)})</div>`
        + `<div style="overflow:auto"><table class="mini-table" style="width:100%"><thead><tr><th>Layer</th><th style="text-align:right">Rate</th><th style="text-align:right">Amount</th><th style="text-align:right">% total</th></tr></thead><tbody>${rows(rows2)}</tbody>`
        + `<tfoot><tr><td><b>Total</b></td><td></td><td style="text-align:right"><b>${usd(e.total)}</b></td><td style="text-align:right">100%</td></tr></tfoot></table></div>`
        + `<div class="meta" style="margin-top:4px">${esc(e.note)}</div>`);
    } catch (err) { fillEst(`<div class="meta">CBS unavailable: ${(err as Error).message}</div>`); }
  };
  const flBtn = document.createElement("button"); flBtn.className = "tool-btn"; flBtn.textContent = "🏢 QTO by floor";
  flBtn.title = "Quantity + cost by storey and discipline — quantities mapped to where they are";
  flBtn.onclick = async () => {
    fillEst(`<div class="meta">Taking off by floor…</div>`);
    try {
      const e = await ctx.host.api.qtoByFloor(pid);
      const st = e.storeys.map((s) => `<tr><td>${esc(s.storey)}</td><td style="text-align:right">${s.element_count}</td><td style="text-align:right">${usd(s.total)}</td></tr>`);
      fillEst(`<div style="font-weight:600;margin-bottom:4px">QTO by floor — grand total <b>${usd(e.grand_total)}</b> · ${e.element_count} elements</div>`
        + `<div style="overflow:auto"><table class="mini-table" style="width:100%"><thead><tr><th>Storey</th><th style="text-align:right">Elements</th><th style="text-align:right">Cost</th></tr></thead><tbody>${rows(st)}</tbody></table></div>`);
    } catch (err) { fillEst(`<div class="meta">By-floor QTO unavailable: ${(err as Error).message}</div>`); }
  };
  const dxfLabel = document.createElement("label"); dxfLabel.className = "tool-btn"; dxfLabel.style.cursor = "pointer";
  dxfLabel.textContent = "⬒ Takeoff a DXF"; dxfLabel.title = "2D CAD quantity takeoff — linear metres, enclosed area and block counts per layer";
  const dxfInput = document.createElement("input"); dxfInput.type = "file"; dxfInput.accept = ".dxf"; dxfInput.style.display = "none"; dxfLabel.appendChild(dxfInput);
  dxfInput.onchange = async () => {
    const f = dxfInput.files?.[0]; if (!f) return;
    fillEst(`<div class="meta">Taking off ${esc(f.name)}…</div>`);
    try {
      const e = await ctx.host.api.takeoffDxf(pid, f);
      const ly = e.layers.slice(0, 15).map((l) => `<tr><td>${esc(l.layer)}</td><td style="text-align:right">${l.entities}</td><td style="text-align:right">${l.length_m.toFixed(1)}</td><td style="text-align:right">${l.area_m2.toFixed(1)}</td><td style="text-align:right">${l.inserts}</td></tr>`);
      fillEst(`<div style="font-weight:600;margin-bottom:4px">DXF takeoff — ${e.layer_count} layers · ${e.total_length_m.toFixed(1)} ${esc(e.units)} linear · ${e.total_area_m2.toFixed(1)} ${esc(e.units)}² area${e.unitless ? " <span class='meta'>(unitless DXF — verify scale)</span>" : ""}</div>`
        + `<div style="overflow:auto"><table class="mini-table" style="width:100%"><thead><tr><th>Layer</th><th style="text-align:right">Ent.</th><th style="text-align:right">Length</th><th style="text-align:right">Area</th><th style="text-align:right">Blocks</th></tr></thead><tbody>${rows(ly)}</tbody></table></div>`);
    } catch (err) { fillEst(`<div class="meta">DXF takeoff failed: ${(err as Error).message}</div>`); }
    finally { dxfInput.value = ""; }
  };
  estRow.append(emBtn, rbBtn, bandBtn, cbsBtn, flBtn, dxfLabel);

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

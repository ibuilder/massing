import { money as cmoney } from "../../ui/charts";
import { noProjectHtml } from "../../ui/empty";
import { toast } from "../../ui/feedback";
import type { PanelContext } from "../panelContext";

/**
 * Analytics & benchmarking panels (cross-project benchmarks, subcontractor risk & cost).
 * Extracted from portal.ts as free render*(ctx) functions (portal.ts decomposition).
 */

  // --- Benchmarks: cross-project cost distribution + response rates ------------------------------
export async function renderBenchmarks(ctx: PanelContext) {
    const root = ctx.root; root.innerHTML = "";
    const el = (t: string, c = "") => { const e = document.createElement(t); if (c) e.className = c; return e; };
    root.appendChild(ctx.bar("📈 Benchmarks", () => { ctx.activeKey = null; void ctx.renderHome(); ctx.buildNav(); }));
    const intro = el("div", "meta"); intro.style.marginBottom = "8px";
    intro.textContent = "Your own history across every project: what things actually cost (per cost code) and "
      + "how fast RFIs/submittals turn around. Sanity-check a new estimate or hold the team accountable.";
    root.appendChild(intro);
    const rr = el("div"); const costs = el("div"); costs.style.marginTop = "10px";
    root.append(rr, costs);
    rr.textContent = "loading…"; costs.textContent = "";
    try {
      const resp = await ctx.host.api.benchmarkResponseRates();
      rr.innerHTML = "";
      const card = (title: string, m: { total: number; open: number; avg_turnaround_days: number | null; overdue: number; overdue_pct: number }) => {
        const c = el("div", "kpi-card"); c.style.cssText = "display:inline-block;margin:4px 8px 4px 0;padding:8px 12px;border:1px solid var(--line);border-radius:8px";
        c.innerHTML = `<div class="meta"><b>${title}</b></div>`
          + `<div style="font-size:12px">${m.total} total · ${m.open} open · ${m.overdue} overdue (${m.overdue_pct}%)`
          + ` · avg turnaround ${m.avg_turnaround_days ?? "—"} d</div>`;
        return c;
      };
      rr.append(card("RFIs", resp.rfi), card("Submittals", resp.submittal));
    } catch (e) { rr.textContent = `response rates failed: ${(e as Error).message}`; }
    try {
      const cb = await ctx.host.api.benchmarkCosts();
      if (!cb.cost_codes.length) { costs.innerHTML = `<div class="meta">${cb.message || "No cost history yet."}</div>`; }
      else {
        const tbl = el("table", "portal-table") as HTMLTableElement; tbl.style.cssText = "width:100%;font-size:12px";
        tbl.innerHTML = `<thead><tr><th scope="col" style="text-align:left">Cost code</th><th scope="col">n</th><th scope="col">low</th><th scope="col">p25</th>`
          + `<th scope="col">median</th><th scope="col">p75</th><th scope="col">high</th></tr></thead><tbody>`
          + cb.cost_codes.map((c) => `<tr><td>${c.cost_code}</td><td style="text-align:center">${c.samples}</td>`
            + `<td style="text-align:right">${cmoney(c.low)}</td><td style="text-align:right">${cmoney(c.p25)}</td>`
            + `<td style="text-align:right"><b>${cmoney(c.median)}</b></td><td style="text-align:right">${cmoney(c.p75)}</td>`
            + `<td style="text-align:right">${cmoney(c.high)}</td></tr>`).join("") + `</tbody>`;
        const h = el("div", "meta"); h.style.margin = "10px 0 4px"; h.innerHTML = `<b>Actual cost by code</b> (${cb.code_count} codes, ≥${cb.min_samples} samples each)`;
        costs.append(h, tbl);
      }
    } catch (e) { costs.textContent = `cost benchmarks failed: ${(e as Error).message}`; }
  }

  // --- Market Intelligence: regional escalation / labour / location + warm-cold sectors ----------
export async function renderMarket(ctx: PanelContext) {
    const root = ctx.root; root.innerHTML = "";
    const el = (t: string, c = "") => { const e = document.createElement(t); if (c) e.className = c; return e; };
    root.appendChild(ctx.bar("📈 Market Intelligence", () => { ctx.activeKey = null; void ctx.renderHome(); ctx.buildNav(); }));
    const pid = ctx.host.projectId();
    const intro = el("div", "meta"); intro.style.marginBottom = "8px";
    intro.innerHTML = "Regional cost escalation, labour rates and a location index, plus the two-speed "
      + "<b>warm/cold</b> demand signal by sector — so an estimate is escalated to the <b>midpoint of "
      + "construction</b> in the region where it will actually be built. Set a project's assumptions under "
      + "Finance → <b>Market Assumptions</b> (region · sector · construction start · duration).";
    root.appendChild(intro);
    const tempTone = (t: string) => t === "hot" ? "var(--status-crit)" : t === "warm" ? "var(--status-warn)"
      : t === "cold" ? "var(--muted)" : "var(--status-good)";
    const editBtn = el("button", "tool-btn"); editBtn.textContent = "✎ Market assumptions";
    editBtn.title = "Set this project's region / sector / construction timeline"; editBtn.style.marginBottom = "8px";
    editBtn.onclick = () => { const m = ctx.mods.find((x) => x.key === "market_assumption"); if (m) { ctx.activeKey = "market_assumption"; void ctx.openModule(m); ctx.buildNav(); } };
    root.appendChild(editBtn);

    // per-project market context (region economics + sector temp + escalation factor to midpoint)
    if (pid) {
      const ctxSlot = el("div", "dash-card"); ctxSlot.style.marginBottom = "8px"; ctxSlot.textContent = "loading project context…";
      root.appendChild(ctxSlot);
      ctx.host.api.marketContext(pid).then((c) => {
        const r = c.region; const s = c.sector;
        ctxSlot.innerHTML = `<b>This project</b> ${c.from_assumption ? "" : `<span class="meta">(defaults — no Market Assumption yet)</span>`}`
          + `<div class="meta" style="margin-top:2px"><b>${r.label}</b> · escalation ${r.escalation_pct}%/yr · `
          + `labour $${r.labour_usd_hr}/hr · location index ${r.location_index}</div>`
          + `<div class="meta">Sector <b>${s.sector}</b> — <span style="color:${tempTone(s.temperature)}">${s.temperature}</span>: ${s.note}</div>`
          + `<div class="meta">Escalation factor <b>${c.escalation_factor}×</b> to ${c.midpoint_year} (${c.escalation_basis})</div>`;
      }).catch((e) => { ctxSlot.textContent = `context failed: ${(e as Error).message}`; });

      // escalation calculator
      const calc = el("div", "dash-card"); calc.style.marginBottom = "8px";
      calc.innerHTML = `<b>Escalate a base cost</b> <span class="meta">to the construction midpoint</span>`;
      const row = el("div"); row.style.cssText = "display:flex;gap:6px;flex-wrap:wrap;align-items:center;margin-top:4px";
      const amt = el("input", "portal-filter") as HTMLInputElement; amt.type = "number"; amt.placeholder = "base amount ($)";
      amt.setAttribute("aria-label", "Base amount USD"); amt.style.width = "150px";
      const go = el("button", "file-btn") as HTMLButtonElement; go.textContent = "Escalate";
      const out = el("span", "meta"); out.style.marginLeft = "8px";
      go.onclick = async () => {
        const a = Number(amt.value); if (!a) { out.textContent = "enter an amount"; return; }
        out.textContent = "…";
        try {
          const r = await ctx.host.api.marketEscalate(pid, a);
          out.innerHTML = `<b>${cmoney(r.escalated_amount)}</b> at ${r.midpoint_year} `
            + `(×${r.escalation_factor} · ${r.annual_rate_pct}%/yr · ${r.escalation_basis})`;
        } catch (e) { out.textContent = `failed: ${(e as Error).message}`; }
      };
      row.append(amt, go, out); calc.append(row); root.appendChild(calc);
    }

    // the market table (regions + sector board), shared across projects
    const snap = el("div"); snap.textContent = "loading market table…"; root.appendChild(snap);
    ctx.host.api.marketSnapshot().then((m) => {
      snap.innerHTML = "";
      const t = el("table", "portal-table") as HTMLTableElement; t.style.cssText = "width:100%;font-size:12px;margin-bottom:8px";
      t.innerHTML = `<thead><tr><th scope="col" style="text-align:left">Region</th><th scope="col">Escalation %/yr</th>`
        + `<th scope="col">Labour $/hr</th><th scope="col">Location index</th></tr></thead><tbody>`
        + m.regions.map((r) => `<tr><td>${r.label}</td><td style="text-align:center">${r.escalation_pct}</td>`
          + `<td style="text-align:right">$${r.labour_usd_hr}</td><td style="text-align:center">${r.location_index}</td></tr>`).join("")
        + `</tbody>`;
      snap.append(t);
      const sig = el("div", "dash-card"); sig.style.marginBottom = "8px";
      const chips = (list: string[], t2: string) => list.map((s) => `<span class="badge" style="background:${tempTone(t2)};color:#fff;margin:2px">${s}</span>`).join("");
      sig.innerHTML = `<b>Two-speed market</b> <span class="meta">${m.market_signal.headline}</span>`
        + `<div style="margin-top:4px">Warm/hot: ${chips(m.market_signal.warm_or_hot, "warm")}</div>`
        + `<div style="margin-top:4px">Cold: ${chips(m.market_signal.cold, "cold")}</div>`;
      snap.append(sig);
      const src = el("div", "meta"); src.style.fontSize = "11px"; src.textContent = m.source; snap.append(src);
    }).catch((e) => { snap.textContent = `market table failed: ${(e as Error).message}`; });
  }

  // --- Risk & Cost: prequal, COI, lien exposure, carbon, pricing, accounting export -------------
export async function renderRiskCost(ctx: PanelContext) {
    const root = ctx.root; root.innerHTML = "";
    const pid = ctx.host.projectId();
    if (!pid) { root.innerHTML = noProjectHtml("Risk & Cost"); return; }
    const el = (t: string, c = "") => { const e = document.createElement(t); if (c) e.className = c; return e; };
    const api = ctx.host.api;
    root.appendChild(ctx.bar("🛡 Risk & Cost", () => { ctx.activeKey = null; void ctx.renderHome(); ctx.buildNav(); }));
    const tone = (band: string) => band === "high" ? "var(--status-crit)" : band === "medium" ? "var(--status-warn)" : "var(--status-good)";
    const section = (title: string) => { const h = el("div", "meta"); h.style.cssText = "margin:12px 0 4px;font-weight:600"; h.textContent = title; root.appendChild(h); return h; };
    const slot = () => { const d = el("div"); d.textContent = "loading…"; root.appendChild(d); return d; };

    section("Subcontractor prequalification (Q-score, worst first)");
    const pqSlot = slot();
    section("Insurance (COI) expiry");
    const coiSlot = slot();
    section("Procurement compliance gate (can bid / can bill)");
    const gateSlot = slot();
    section("Lien exposure (paid without an unconditional waiver)");
    const lienSlot = slot();
    section("Embodied carbon");
    const carbonSlot = slot();
    section("Takeoff pricing vs estimate");
    const priceSlot = slot();
    section("Model classification (improve QTO + carbon)");
    const classifySlot = slot();
    section("Conceptual estimate (parametric $/SF)");
    const ceWrap = el("div");
    root.appendChild(ceWrap);
    section("Materials 3-way match (PO ↔ delivery ↔ invoice)");
    const matchSlot = slot();
    section("Accounting export");
    const acct = el("div");
    const glBtn = el("a", "file-btn") as HTMLAnchorElement; glBtn.textContent = "⬇ GL (CSV)";
    glBtn.href = api.accountingGlCsvUrl(pid); glBtn.style.marginRight = "8px";
    const iifBtn = el("a", "file-btn") as HTMLAnchorElement; iifBtn.textContent = "⬇ QuickBooks bills (IIF)";
    iifBtn.href = api.accountingIifUrl(pid);
    acct.append(glBtn, iifBtn); root.appendChild(acct);

    api.prequalScores(pid).then((r) => {
      pqSlot.innerHTML = "";
      if (!r.count) { pqSlot.innerHTML = `<div class="meta">No prequalification records yet.</div>`; return; }
      const t = el("table", "portal-table") as HTMLTableElement; t.style.cssText = "width:100%;font-size:12px";
      t.innerHTML = `<thead><tr><th scope="col" style="text-align:left">Company</th><th scope="col">Trade</th><th scope="col">Score</th><th scope="col" style="text-align:left">Flags</th></tr></thead><tbody>`
        + r.subs.map((s) => `<tr><td>${s.company || ""}</td><td style="text-align:center">${s.trade || ""}</td>`
          + `<td style="text-align:center;color:${tone(s.risk_band)}"><b>${s.score}</b> ${s.risk_band}</td>`
          + `<td>${(s.flags || []).join("; ")}</td></tr>`).join("") + `</tbody>`;
      pqSlot.append(t);
    }).catch((e) => { pqSlot.textContent = `failed: ${(e as Error).message}`; });

    api.coiExpiry(pid).then((r) => {
      coiSlot.innerHTML = `<div class="meta">${r.expired_count} expired · ${r.expiring_count} expiring ≤30d</div>`;
      const rows = [...r.expired.map((x) => ({ ...x, k: "EXPIRED" })), ...r.expiring_soon.map((x) => ({ ...x, k: "soon" }))];
      if (rows.length) {
        const ul = el("ul"); ul.style.cssText = "margin:4px 0 0 16px;font-size:12px";
        rows.forEach((x) => { const li = el("li");
          li.innerHTML = `<span style="color:${x.k === "EXPIRED" ? "var(--status-crit)" : "var(--status-warn)"}">${x.k}</span> `
            + `${x.vendor || ""} — ${x.coverage_type || ""} exp ${x.expires} (${x.days}d)`; ul.append(li); });
        coiSlot.append(ul);
      }
    }).catch((e) => { coiSlot.textContent = `failed: ${(e as Error).message}`; });

    api.procurementComplianceFeed(pid).then((r) => {
      gateSlot.innerHTML = `<div class="meta">${r.vendors_flagged} vendor(s) need a compliance nudge before they can bid or bill.</div>`;
      if (r.vendors.length) {
        const t = el("table", "portal-table") as HTMLTableElement; t.style.cssText = "width:100%;font-size:12px;margin-top:4px";
        t.innerHTML = `<thead><tr><th scope="col" style="text-align:left">Vendor</th><th scope="col" style="text-align:left">Issues</th>`
          + `<th scope="col">Bid</th><th scope="col">Bill</th></tr></thead><tbody>`
          + r.vendors.map((v) => `<tr><td>${v.vendor}</td><td>${v.issues.map((i) => `<span style="color:var(--status-warn)">${i}</span>`).join("; ")}</td>`
            + `<td style="text-align:center">${v.can_bid ? "✅" : "⛔"}</td>`
            + `<td style="text-align:center">${v.can_bill ? "✅" : "⛔"}</td></tr>`).join("") + `</tbody>`;
        gateSlot.append(t);
      } else {
        gateSlot.insertAdjacentHTML("beforeend", `<div class="meta">✅ All vendors clear on insurance + prequalification.</div>`);
      }
    }).catch((e) => { gateSlot.textContent = `failed: ${(e as Error).message}`; });

    api.lienExposure(pid).then((r) => {
      lienSlot.innerHTML = `<div class="meta">Total exposure <b style="color:${r.total_lien_exposure > 0 ? "var(--status-crit)" : "var(--status-good)"}">${cmoney(r.total_lien_exposure)}</b>`
        + (r.vendors_at_risk.length ? ` · at risk: ${r.vendors_at_risk.join(", ")}` : "") + `</div>`;
      const risky = r.vendors.filter((v) => v.exposure > 0);
      if (risky.length) {
        const t = el("table", "portal-table") as HTMLTableElement; t.style.cssText = "width:100%;font-size:12px;margin-top:4px";
        t.innerHTML = `<thead><tr><th scope="col" style="text-align:left">Vendor</th><th scope="col">Paid</th><th scope="col">Unconditional waived</th><th scope="col">Exposure</th></tr></thead><tbody>`
          + risky.map((v) => `<tr><td>${v.vendor}</td><td style="text-align:right">${cmoney(v.paid)}</td>`
            + `<td style="text-align:right">${cmoney(v.waived_unconditional)}</td>`
            + `<td style="text-align:right;color:var(--status-crit)">${cmoney(v.exposure)}</td></tr>`).join("") + `</tbody>`;
        lienSlot.append(t);
      }
    }).catch((e) => { lienSlot.textContent = `failed: ${(e as Error).message}`; });

    api.projectCarbon(pid).then((r) => {
      if (!r.line_count) { carbonSlot.innerHTML = `<div class="meta">${r.message || "No material quantities."}</div>`; return; }
      const mats = Object.entries(r.by_material).slice(0, 6).map(([m, v]) => `${m}: ${(v / 1000).toFixed(1)} t`).join(" · ");
      carbonSlot.innerHTML = `<div><b>${r.total_tco2e.toLocaleString()} tCO₂e</b> embodied (A1-A3)`
        + (r.unmatched ? ` · ${r.unmatched} line(s) unmatched` : "") + `</div><div class="meta">${mats}</div>`;
    }).catch((e) => { carbonSlot.textContent = `failed: ${(e as Error).message}`; });

    api.pricingReconcile(pid).then((r) => {
      if (!r.matched) { priceSlot.innerHTML = `<div class="meta">No priced quantities (${r.pricing_source}).</div>`; return; }
      const v = r.variance_total;
      priceSlot.innerHTML = `<div>Priced <b>${cmoney(r.priced_total)}</b> (${r.pricing_source})`
        + (v != null ? ` vs estimate ${cmoney(r.estimated_total)} — variance <b style="color:${v > 0 ? "var(--status-warn)" : "var(--status-good)"}">${cmoney(v)}</b>` : "")
        + `</div>`;
    }).catch((e) => { priceSlot.textContent = `failed: ${(e as Error).message}`; });

    api.ifcClassify(pid).then((r) => {
      if (!r.count) { classifySlot.innerHTML = `<div class="meta">${r.message || "No reclassification suggestions (load a model in the Model workspace)."}</div>`; return; }
      const tops = Object.entries(r.by_target_class).slice(0, 5).map(([c, n]) => `${c}: ${n}`).join(" · ");
      classifySlot.innerHTML = `<div><b>${r.count}</b> element(s) suggested for reclassification`
        + (r.generic_elements ? ` (${r.generic_elements} generic/proxy)` : "") + `</div><div class="meta">${tops}</div>`;
    }).catch((e) => { classifySlot.textContent = `failed: ${(e as Error).message}`; });

    // conceptual estimate mini-form (developer-side $/SF from building params)
    void api.conceptualCatalog().then((cat) => {
      ceWrap.innerHTML = "";
      const type = el("select", "portal-filter") as HTMLSelectElement; type.style.cssText = "margin:2px 4px 2px 0";
      type.setAttribute("aria-label", "Building type");
      type.innerHTML = cat.building_types.map((t) => `<option value="${t}">${t}</option>`).join("");
      const region = el("select", "portal-filter") as HTMLSelectElement; region.style.cssText = "margin:2px 4px";
      region.setAttribute("aria-label", "Region");
      region.innerHTML = cat.regions.map((rg) => `<option value="${rg}"${rg === "us_average" ? " selected" : ""}>${rg}</option>`).join("");
      const gfa = el("input", "portal-filter") as HTMLInputElement; gfa.type = "number"; gfa.placeholder = "GFA (sf)"; gfa.setAttribute("aria-label", "Gross floor area (sf)"); gfa.style.cssText = "width:110px;margin:2px 4px";
      const go = el("button", "file-btn") as HTMLButtonElement; go.textContent = "Estimate";
      const out = el("div"); out.style.marginTop = "6px";
      go.onclick = async () => {
        if (!Number(gfa.value)) { toast("Enter GFA", "error"); return; }
        out.textContent = "estimating…";
        try {
          const r = await api.conceptualEstimate(pid, { building_type: type.value, region: region.value, gfa_sf: Number(gfa.value) });
          if (r.error) { out.textContent = r.error; return; }
          out.innerHTML = `<div><b>${cmoney(r.total_cost)}</b> total (${cmoney(r.range.low)}–${cmoney(r.range.high)}) `
            + `· ${cmoney(r.metrics.total_per_sf)}/sf · hard ${cmoney(r.hard_cost)} + soft ${cmoney(r.soft_cost)}</div>`;
        } catch (e) { out.textContent = `failed: ${(e as Error).message}`; }
      };
      ceWrap.append(type, region, gfa, go, out);
    }).catch(() => { ceWrap.innerHTML = `<div class="meta">conceptual estimator unavailable</div>`; });

    api.procurementThreeWayMatch(pid).then((r) => {
      if (!r.po_count) { matchSlot.innerHTML = `<div class="meta">No purchase orders (commitments) yet.</div>`; return; }
      matchSlot.innerHTML = `<div class="meta">${r.po_count} PO(s)`
        + (r.flagged.length ? ` · <span style="color:var(--status-warn)">${r.flagged.length} need review</span>` : " · all clear") + `</div>`;
      const flagged = r.pos.filter((p) => p.status === "review");
      if (flagged.length) {
        const t = el("table", "portal-table") as HTMLTableElement; t.style.cssText = "width:100%;font-size:11px;margin-top:4px";
        t.innerHTML = `<thead><tr><th scope="col" style="text-align:left">PO</th><th scope="col">Vendor</th><th scope="col">PO</th><th scope="col">Recd</th><th scope="col">Invoiced</th><th scope="col" style="text-align:left">Issue</th></tr></thead><tbody>`
          + flagged.map((p) => `<tr><td>${p.po}</td><td>${p.vendor || ""}</td><td style="text-align:right">${cmoney(p.po_amount)}</td>`
            + `<td style="text-align:center">${p.received}</td><td style="text-align:right;color:${p.variance > 0 ? "var(--status-crit)" : "inherit"}">${cmoney(p.invoiced)}</td>`
            + `<td>${(p.flags || []).join("; ")}</td></tr>`).join("") + `</tbody>`;
        matchSlot.append(t);
      }
    }).catch((e) => { matchSlot.textContent = `failed: ${(e as Error).message}`; });
  }

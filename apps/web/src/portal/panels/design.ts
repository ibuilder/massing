import { money as cmoney } from "../../ui/charts";
import { noProjectHtml } from "../../ui/empty";
import { escapeHtml as esc, toast } from "../../ui/feedback";
import { promptModal } from "../../ui/modal";
import type { PanelContext } from "../panelContext";

/**
 * Design & feasibility panels (land screening, project-lifecycle gates, diligence, ESG/POE).
 * Extracted from portal.ts as free render*(ctx) functions (portal.ts decomposition).
 */

  // --- Land Screening: filter a parcel set → max-buildable envelope + cost ----------------------
export async function renderLandScreen(ctx: PanelContext) {
    const root = ctx.root; root.innerHTML = "";
    const el = (t: string, c = "") => { const e = document.createElement(t); if (c) e.className = c; return e; };
    root.appendChild(ctx.bar("🗺️ Land Screening", () => { ctx.activeKey = null; void ctx.renderHome(); ctx.buildNav(); }));
    const intro = el("div", "meta"); intro.style.marginBottom = "8px";
    intro.textContent = "Screen a parcel set by size / zoning / flood / utilities and rank by max-buildable "
      + "opportunity — each parcel gets an envelope (area × FAR) and a conceptual cost. Paste parcels as "
      + "JSON (from a GIS export). Nationwide parcel data is an optional paid connector (Settings).";
    root.appendChild(intro);
    const ta = el("textarea", "portal-filter") as HTMLTextAreaElement;
    ta.placeholder = '[{"id":"A","acres":5,"zoning":"MU","flood_zone":"X","sewer":true,"price":2000000,"far":2.0}]';
    ta.setAttribute("aria-label", "Parcels as JSON");
    ta.style.cssText = "width:100%;min-height:90px;margin:4px 0;font-family:monospace;font-size:11px";
    const row = el("div"); row.style.cssText = "display:flex;gap:6px;flex-wrap:wrap;align-items:center;margin:4px 0";
    const minAc = el("input", "portal-filter") as HTMLInputElement; minAc.type = "number"; minAc.placeholder = "min acres"; minAc.setAttribute("aria-label", "Minimum acres"); minAc.style.width = "90px";
    const zoning = el("input", "portal-filter") as HTMLInputElement; zoning.placeholder = "zoning (comma)"; zoning.setAttribute("aria-label", "Allowed zoning (comma-separated)"); zoning.style.width = "130px";
    const far = el("input", "portal-filter") as HTMLInputElement; far.type = "number"; far.placeholder = "assume FAR"; far.setAttribute("aria-label", "Assumed FAR"); far.style.width = "90px";
    const btype = el("input", "portal-filter") as HTMLInputElement; btype.placeholder = "building type"; btype.setAttribute("aria-label", "Building type"); btype.value = "multifamily"; btype.style.width = "120px";
    const flood = el("label", "meta") as HTMLLabelElement; const floodCk = el("input") as HTMLInputElement; floodCk.type = "checkbox"; floodCk.checked = true;
    flood.append(floodCk, document.createTextNode(" exclude flood"));
    row.append(minAc, zoning, far, btype, flood);
    const go = el("button", "file-btn") as HTMLButtonElement; go.textContent = "Screen";
    const out = el("div"); out.style.marginTop = "8px";
    go.onclick = async () => {
      let parcelList: unknown[];
      try { parcelList = JSON.parse(ta.value || "[]"); if (!Array.isArray(parcelList)) throw new Error("expected an array"); }
      catch (e) { toast(`Invalid JSON: ${(e as Error).message}`, "error"); return; }
      const criteria: Record<string, unknown> = { building_type: btype.value || undefined, exclude_flood: floodCk.checked };
      if (minAc.value) criteria.min_acres = Number(minAc.value);
      if (far.value) criteria.assume_far = Number(far.value);
      if (zoning.value.trim()) criteria.zoning_in = zoning.value.split(",").map((z) => z.trim()).filter(Boolean);
      out.textContent = "screening…";
      try {
        const r = await ctx.host.api.parcelsScreen(parcelList, criteria);
        out.innerHTML = `<div class="meta"><b>${r.match_count}</b> of ${r.screened} parcels pass</div>`;
        if (r.matches.length) {
          const tbl = el("table", "portal-table") as HTMLTableElement; tbl.style.cssText = "width:100%;font-size:12px;margin-top:4px";
          tbl.innerHTML = `<thead><tr><th scope="col" style="text-align:left">Parcel</th><th scope="col">Acres</th><th scope="col">Zoning</th><th scope="col">Max GFA</th><th scope="col">Concept. cost</th><th scope="col">Land $/bldbl sf</th></tr></thead><tbody>`
            + r.matches.map((m) => `<tr><td>${m.id}</td><td style="text-align:center">${m.acres}</td><td style="text-align:center">${m.zoning || ""}</td>`
              + `<td style="text-align:right">${m.buildable.max_gfa_sf ? m.buildable.max_gfa_sf.toLocaleString() : "—"}</td>`
              + `<td style="text-align:right">${m.buildable.conceptual_cost ? cmoney(m.buildable.conceptual_cost) : "—"}</td>`
              + `<td style="text-align:right">${m.buildable.land_cost_per_buildable_sf ? cmoney(m.buildable.land_cost_per_buildable_sf) : "—"}</td></tr>`).join("") + `</tbody>`;
          out.append(tbl);
        }
        if (r.rejected.length) { const rj = el("div", "meta"); rj.style.marginTop = "6px";
          rj.textContent = "Rejected: " + r.rejected.map((x) => `${x.id} (${x.failed[0]})`).join(", "); out.append(rj); }
      } catch (e) { out.textContent = `failed: ${(e as Error).message}`; }
    };
    root.append(ta, row, go, out);
  }

  // --- Project Lifecycle: RIBA/AIA design phases + gate sign-off + soft-cost allocation ----------
export async function renderLifecycle(ctx: PanelContext) {
    const root = ctx.root; root.innerHTML = "";
    const el = (t: string, c = "") => { const e = document.createElement(t); if (c) e.className = c; return e; };
    root.appendChild(ctx.bar("🧭 Project Lifecycle", () => { ctx.activeKey = null; void ctx.renderHome(); ctx.buildNav(); }));
    const pid = ctx.host.projectId();
    if (!pid) { root.insertAdjacentHTML("beforeend", noProjectHtml("Project Lifecycle")); return; }
    const intro = el("div", "meta"); intro.style.marginBottom = "8px";
    intro.textContent = "The architect/engineer design-to-turnover lifecycle: RIBA Plan of Work 0–7 "
      + "mapped to AIA phases (SD · DD · CD · CA). Each phase is a gate the Architect + Owner sign off "
      + "before advancing, with its A/E design-fee share and ISO-19650 information status.";
    root.appendChild(intro);
    const body = el("div"); body.textContent = "loading…"; root.appendChild(body);
    const load = async () => {
      let lc;
      try { lc = await ctx.host.api.lifecycle(pid); }
      catch (e) { body.textContent = `failed: ${(e as Error).message}`; return; }
      body.innerHTML = "";
      if (!lc.seeded || !lc.phases.length) {
        const seedBtn = el("button", "file-btn") as HTMLButtonElement;
        seedBtn.textContent = "Seed design phases";
        seedBtn.onclick = () => void ctx.host.api.lifecycleSeed(pid)
          .then(() => { toast("Design phases seeded", "success"); void load(); })
          .catch((e) => toast((e as Error).message, "error"));
        const note = el("div", "meta"); note.textContent = "No design phases yet for this project.";
        note.style.marginBottom = "6px";
        body.append(note, seedBtn);
        return;
      }
      if (lc.current_stage) {
        const cur = el("div", "meta"); cur.style.margin = "2px 0 8px";
        cur.innerHTML = `Current stage: <b>${lc.current_stage.riba_stage}</b> — ${lc.current_stage.aia_phase}`;
        body.append(cur);
      }
      const STATE_TONE: Record<string, string> = { approved: "var(--status-good)", in_review: "var(--status-warn)",
        returned: "var(--status-crit)", active: "var(--muted)" };
      for (const ph of lc.phases) {
        const card = el("div", "dash-card"); card.style.cssText = `border-left:3px solid ${STATE_TONE[ph.state] || "var(--muted)"};margin:6px 0`;
        const fee = ph.design_fee_amount ? ` · A/E fee ${cmoney(ph.design_fee_amount)}` : "";
        card.innerHTML = `<div style="display:flex;justify-content:space-between;align-items:center;gap:8px">`
          + `<div><b>${ph.riba_stage}</b> <span class="meta">→ ${ph.aia_phase}</span></div>`
          + `<span class="badge">${ph.state}</span></div>`
          + `<div class="meta" style="margin-top:2px">Fee ${ph.design_fee_pct || 0}%${fee} · ${ph.iso_status || ""}</div>`
          + (ph.deliverables.length ? `<ul style="margin:4px 0 0 16px;font-size:12px">${ph.deliverables.map((d) => `<li>${d}</li>`).join("")}</ul>` : "");
        // gate actions
        const actions = el("div"); actions.style.cssText = "margin-top:6px;display:flex;gap:6px;flex-wrap:wrap;align-items:center";
        const act = (label: string, action: string, pre?: () => Promise<boolean>) => {
          const b = el("button", "file-btn") as HTMLButtonElement; b.textContent = label;
          b.onclick = async () => {
            if (pre && !(await pre())) return;
            try { await ctx.host.api.transitionRecord(pid, "project_phase", ph.id, action);
              toast(`${label} ✓`, "success"); void load(); }
            catch (e) { toast((e as Error).message, "error"); }
          };
          actions.append(b);
        };
        if (ph.state === "active") act("Submit for gate review", "submit_for_review");
        if (ph.state === "in_review") {
          act("Approve gate (Architect/Owner)", "approve_gate", async () => {
            const v = await promptModal("Gate sign-off",
              [{ name: "name", label: "Certifying name (Architect / Owner)", required: true }], "Approve");
            if (!v) return false;
            await ctx.host.api.updateModuleRecord(pid, "project_phase", ph.id, { signed_by: v.name });
            return true;
          });
          act("Return", "return");
        }
        if (ph.state === "returned") act("Revise", "revise");
        if (ph.signed_by) { const s = el("span", "meta"); s.textContent = `signed: ${ph.signed_by}`; actions.append(s); }
        card.append(actions);
        body.append(card);
      }
      // soft-cost allocation
      if (lc.soft_costs) {
        const sc = el("div"); sc.style.marginTop = "12px";
        sc.innerHTML = `<div class="meta"><b>Itemized soft costs</b> — total ${cmoney(lc.soft_costs.total)} (of ${cmoney(lc.hard_cost)} hard)</div>`;
        const t = el("table", "portal-table") as HTMLTableElement; t.style.cssText = "width:100%;font-size:12px;margin-top:4px";
        t.innerHTML = `<thead><tr><th scope="col" style="text-align:left">Soft cost</th><th scope="col">% of hard</th><th scope="col">Amount</th></tr></thead><tbody>`
          + lc.soft_costs.lines.map((x) => `<tr><td>${x.label}</td><td style="text-align:center">${x.pct_of_hard}%</td>`
            + `<td style="text-align:right">${cmoney(x.amount)}</td></tr>`).join("") + `</tbody>`;
        sc.append(t); body.append(sc);
      }
    };
    await load();
  }

  // --- Diligence & Entitlements: pre-acquisition go/no-go rollup --------------------------------
export async function renderDiligence(ctx: PanelContext) {
    const root = ctx.root; root.innerHTML = "";
    const el = (t: string, c = "") => { const e = document.createElement(t); if (c) e.className = c; return e; };
    root.appendChild(ctx.bar("📜 Diligence & Entitlements", () => { ctx.activeKey = null; void ctx.renderHome(); ctx.buildNav(); }));
    const pid = ctx.host.projectId();
    if (!pid) { root.insertAdjacentHTML("beforeend", noProjectHtml("Diligence & Entitlements")); return; }
    const intro = el("div", "meta"); intro.style.marginBottom = "8px";
    intro.textContent = "Pre-acquisition readiness: due-diligence studies (title/ALTA, Phase I ESA, "
      + "geotech, utilities, traffic, …) and entitlement applications (rezoning, site plan, variances) "
      + "rolled into a go/no-go before releasing contingencies. Add records in the Acquisition section.";
    root.appendChild(intro);
    const body = el("div"); body.textContent = "loading…"; root.appendChild(body);
    let rd;
    try { rd = await ctx.host.api.diligenceReadiness(pid); }
    catch (e) { body.textContent = `failed: ${(e as Error).message}`; return; }
    body.innerHTML = "";
    // go / no-go banner
    const dd = rd.due_diligence; const en = rd.entitlements;
    const banner = el("div", "dash-card");
    banner.style.cssText = `border-left:4px solid ${rd.go ? "var(--status-good)" : "var(--status-warn)"};margin-bottom:8px`;
    banner.innerHTML = `<b>${rd.go ? "✅ GO — diligence cleared, entitlements approved"
      : "⏳ NOT READY — open items below"}</b>`
      + `<div class="meta">Due diligence: ${dd.cleared}/${dd.total} cleared · ${dd.flagged} flagged · `
      + `Entitlements: ${en.approved} approved · ${en.pending} pending · ${en.denied} denied</div>`;
    body.append(banner);
    // high-risk flags
    if (dd.high_risk.length) {
      const hr = el("div", "dash-card"); hr.style.cssText = "border-left:3px solid var(--status-crit);margin:6px 0";
      hr.innerHTML = `<b>High-risk findings</b><ul style="margin:4px 0 0 16px;font-size:12px">`
        + dd.high_risk.map((x) => `<li>${esc(x.ref)} ${esc(x.item || "")} — <b>${esc(x.risk)}</b> (${esc(x.category)})</li>`).join("") + `</ul>`;
      body.append(hr);
    }
    // DD by category
    const cats = Object.entries(dd.by_category);
    if (cats.length) {
      const t = el("table", "portal-table") as HTMLTableElement; t.style.cssText = "width:100%;font-size:12px;margin:6px 0";
      t.innerHTML = `<thead><tr><th scope="col" style="text-align:left">Category</th><th scope="col">Cleared</th>`
        + `<th scope="col">Flagged</th><th scope="col">Open</th></tr></thead><tbody>`
        + cats.map(([c, v]) => `<tr><td>${esc(c)}</td><td style="text-align:center">${v.cleared}/${v.total}</td>`
          + `<td style="text-align:center">${v.flagged || ""}</td><td style="text-align:center">${v.open || ""}</td></tr>`).join("")
        + `</tbody>`;
      body.append(t);
    } else {
      const none = el("div", "meta"); none.textContent = "No due-diligence items yet — add them under Acquisition → Due Diligence.";
      body.append(none);
    }
    // expiring approvals
    if (en.expiring_within_180d.length) {
      const ex = el("div", "dash-card"); ex.style.cssText = "border-left:3px solid var(--status-warn);margin:6px 0";
      ex.innerHTML = `<b>Approvals expiring ≤180 days</b><ul style="margin:4px 0 0 16px;font-size:12px">`
        + en.expiring_within_180d.map((x) => `<li>${esc(x.ref)} ${esc(x.application || "")} — expires ${esc(x.expires)}</li>`).join("") + `</ul>`;
      body.append(ex);
    }
  }

  // --- ESG & POE: asset sustainability scorecard + Stage-7 feedback loop ------------------------
export async function renderEsg(ctx: PanelContext) {
    const root = ctx.root; root.innerHTML = "";
    const el = (t: string, c = "") => { const e = document.createElement(t); if (c) e.className = c; return e; };
    root.appendChild(ctx.bar("🌱 ESG & Post-Occupancy", () => { ctx.activeKey = null; void ctx.renderHome(); ctx.buildNav(); }));
    const pid = ctx.host.projectId();
    if (!pid) { root.insertAdjacentHTML("beforeend", noProjectHtml("ESG & POE")); return; }
    const intro = el("div", "meta"); intro.style.marginBottom = "8px";
    intro.textContent = "The asset's sustainability scorecard, computed locally: metered energy (EUI), "
      + "operational greenhouse gas by scope, water, certification tracking — plus post-occupancy "
      + "evaluations closing the loop between design intent and measured performance.";
    root.appendChild(intro);
    const body = el("div"); body.textContent = "loading…"; root.appendChild(body);
    let s;
    try { s = await ctx.host.api.esgSummary(pid); }
    catch (e) { body.textContent = `failed: ${(e as Error).message}`; return; }
    body.innerHTML = "";
    const perf = s.performance;
    // KPI cards
    const cards = el("div"); cards.style.cssText = "display:flex;gap:8px;flex-wrap:wrap;margin-bottom:8px";
    const card = (label: string, value: string) => {
      const c = el("div", "dash-card"); c.style.minWidth = "125px";
      c.innerHTML = `<div style="font-size:20px;font-weight:600">${value}</div><div class="meta">${label}</div>`;
      return c;
    };
    cards.append(
      card("EUI (kBtu/sf/yr)", perf.energy.eui_kbtu_sf_yr != null ? String(perf.energy.eui_kbtu_sf_yr) : "—"),
      card("GHG total (tCO₂e)", String(perf.ghg.total_tco2e)),
      card("Scope 1 / Scope 2", `${perf.ghg.scope1_tco2e} / ${perf.ghg.scope2_tco2e}`),
      card("water (gal)", perf.water.gallons.toLocaleString()),
      card("cert points", `${s.certifications.points_achieved}/${s.certifications.points_targeted}`));
    body.append(cards);
    // GHG detail
    const g = el("div", "dash-card"); g.style.marginBottom = "8px";
    g.innerHTML = `<b>Operational GHG</b><div class="meta">${esc(perf.ghg.note)}</div>`
      + `<div class="meta">Intensity: ${perf.ghg.intensity_kgco2e_sf != null ? `${perf.ghg.intensity_kgco2e_sf} kgCO₂e/sf` : "— (needs GFA)"} · `
      + `grid factor ${perf.ghg.grid_factor_kgco2e_kwh} kgCO₂e/kWh · ${s.data_coverage.meter_months} meter month(s)</div>`;
    body.append(g);
    // POE
    const p = s.poe.latest;
    const pc = el("div", "dash-card"); pc.style.marginBottom = "8px";
    if (p) {
      const gap = p.eui_gap_pct;
      pc.innerHTML = `<b>Post-occupancy evaluation</b> <span class="meta">(${s.poe.reported}/${s.poe.count} reported)</span>`
        + `<div class="meta">${esc(p.ref)} · ${esc(p.level || "")} · ${esc(p.state)}`
        + (p.satisfaction_score != null ? ` · satisfaction ${p.satisfaction_score}/7` : "") + `</div>`
        + `<div class="meta">Design EUI ${p.design_eui ?? "—"} → actual ${p.actual_eui ?? "—"}`
        + (gap != null ? ` · <b style="color:var(${gap > 10 ? "--status-warn" : "--status-good"})">${gap > 0 ? "+" : ""}${gap}% vs design</b>` : "")
        + `</div>`;
    } else {
      pc.innerHTML = `<b>Post-occupancy evaluation</b><div class="meta">None yet — add one under `
        + `Operations → Post-Occupancy Evaluations (level 1 indicative → 3 diagnostic; a reported POE `
        + `compares design EUI against the metered actual).</div>`;
    }
    body.append(pc);
    // report link
    const rb = el("div");
    const a = document.createElement("a"); a.className = "portal-btn"; a.textContent = "⬇ ESG summary (PDF)";
    a.href = ctx.host.api.reportUrl(pid, "esg", "pdf"); a.target = "_blank"; a.rel = "noopener";
    rb.append(a); body.append(rb);
  }

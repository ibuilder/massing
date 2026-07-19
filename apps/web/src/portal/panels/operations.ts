import { escapeHtml as esc, toast } from "../../ui/feedback";
import { progressBar, groupedBar, lineChart, money as cmoney } from "../../ui/charts";
import { promptModal } from "../../ui/modal";
import { noProjectHtml } from "../../ui/empty";
import type { PanelContext } from "../panelContext";

/**
 * Operations & facility panels, extracted from portal.ts (portal.ts decomposition).
 * CMMS operations, Facility Condition (FCI), discipline Spine traceability, climate/water
 * Resilience, metered Energy, and the Turnover package — each a free render*(ctx) function.
 */

  // --- Operations: CMMS — work orders, PM generation, maintenance KPIs --------------------------
export async function renderOperations(ctx: PanelContext) {
    const root = ctx.root; root.innerHTML = "";
    const el = (t: string, c = "") => { const e = document.createElement(t); if (c) e.className = c; return e; };
    root.appendChild(ctx.bar("🔧 Operations — Maintenance", () => { ctx.activeKey = null; void ctx.renderHome(); ctx.buildNav(); }));
    const pid = ctx.host.projectId();
    if (!pid) { root.insertAdjacentHTML("beforeend", noProjectHtml("Operations")); return; }
    const intro = el("div", "meta"); intro.style.marginBottom = "8px";
    intro.textContent = "Post-turnover maintenance: PM schedules generate preventive work orders "
      + "before failures happen; KPIs show whether the building is run proactively (PM compliance) "
      + "or reactively (MTTR, overdue backlog). Manage records under Operations → Work Orders / PM Schedules.";
    root.appendChild(intro);
    const body = el("div"); body.textContent = "loading…"; root.appendChild(body);
    const load = async () => {
      body.innerHTML = "";
      let k; let wos;
      try {
        k = await ctx.host.api.cmmsKpis(pid);
        wos = await ctx.host.api.moduleRecords(pid, "work_order");
      } catch (e) { body.textContent = `failed: ${(e as Error).message}`; return; }
      // KPI cards
      const cards = el("div"); cards.style.cssText = "display:flex;gap:8px;flex-wrap:wrap;margin-bottom:8px";
      const card = (label: string, value: string, warn = false) => {
        const c = el("div", "dash-card"); c.style.cssText = `min-width:110px${warn ? ";border-left:3px solid var(--status-warn)" : ""}`;
        c.innerHTML = `<div style="font-size:20px;font-weight:600">${value}</div><div class="meta">${label}</div>`;
        return c;
      };
      cards.append(card("open work orders", String(k.open)),
        card("overdue", String(k.overdue), k.overdue > 0),
        card("PM compliance", k.pm_compliance_pct != null ? `${k.pm_compliance_pct}%` : "—"),
        card("MTTR (days)", k.mttr_days != null ? String(k.mttr_days) : "—"),
        card("completed", String(k.completed)));
      body.append(cards);
      // generate-PM action
      const act = el("div"); act.style.marginBottom = "8px";
      const gen = el("button", "portal-btn") as HTMLButtonElement;
      gen.textContent = "Generate PM work orders";
      gen.title = "Create preventive work orders for every active PM schedule that is due";
      gen.onclick = async () => {
        gen.disabled = true;
        try {
          const r = await ctx.host.api.cmmsGeneratePm(pid);
          toast(r.generated ? `${r.generated} PM work order(s) created` : "No PM schedules due", "success");
          void load();
        } catch (e) { toast(`failed: ${(e as Error).message}`, "error"); gen.disabled = false; }
      };
      act.append(gen); body.append(act);
      // open-by-priority chart
      const pri = Object.entries(k.open_by_priority);
      if (pri.length) {
        const wrap = el("div", "dash-card"); wrap.style.marginBottom = "8px";
        wrap.innerHTML = groupedBar(pri.map(([p, n]) => ({ label: p, bars: [{ name: "open", value: n }] })),
          { title: "Open work orders by priority", fmt: (n) => String(Math.round(n)) });
        body.append(wrap);
      }
      // open WO table
      const open = wos.filter((w) => w.workflow_state !== "completed" && w.workflow_state !== "verified");
      if (open.length) {
        const t = el("table", "portal-table") as HTMLTableElement; t.style.cssText = "width:100%;font-size:12px";
        t.innerHTML = `<thead><tr><th scope="col" style="text-align:left">Ref</th><th scope="col" style="text-align:left">Work order</th>`
          + `<th scope="col">Type</th><th scope="col">Priority</th><th scope="col">Due</th><th scope="col">State</th></tr></thead><tbody>`
          + open.slice(0, 50).map((w) => {
            const d = (w.data || {}) as Record<string, string>;
            return `<tr><td>${esc(w.ref || "")}</td><td>${esc(d.subject || "")}</td>`
              + `<td style="text-align:center">${esc(d.wo_type || "")}</td><td style="text-align:center">${esc(d.priority || "")}</td>`
              + `<td style="text-align:center">${esc(d.due_date || "")}</td><td style="text-align:center">${esc(w.workflow_state || "")}</td></tr>`;
          }).join("") + `</tbody>`;
        body.append(t);
      } else {
        const none = el("div", "meta");
        none.textContent = "No open work orders — add corrective ones under Operations → Work Orders, or set up PM Schedules and generate.";
        body.append(none);
      }
      // digital-twin readiness — asset↔system linkage, sensor mapping, DPP (ISO 23247 / EU DPP)
      try {
        const tw = await ctx.host.api.twinReadiness(pid);
        const tc = el("div", "dash-card"); tc.style.marginTop = "8px";
        const pct = (v: number | null) => v != null ? `${v}%` : "—";
        tc.innerHTML = `<b>Digital-twin readiness</b> <span class="meta">${tw.systems} building system(s), `
          + `${tw.bms_integrated_systems} BMS-integrated</span>`
          + `<table class="fin-table" style="width:100%;font-size:12px;margin-top:4px">`
          + `<tr><td>Assets linked to a system</td><td class="num">${pct(tw.system_linked_pct)}</td></tr>`
          + `<tr><td>Assets mapped to a sensor</td><td class="num">${pct(tw.sensor_mapped_pct)}</td></tr>`
          + `<tr class="fin-total"><td>Twin readiness</td><td class="num">${pct(tw.twin_readiness_pct)}</td></tr>`
          + `<tr><td>Product Passport complete (GS1/EPD/mfr)</td><td class="num">${pct(tw.dpp.complete_pct)}</td></tr>`
          + `</table>`
          + `<div class="meta" style="margin-top:4px">${esc(tw.dpp.note)}</div>`;
        body.append(tc);
      } catch { /* twin data optional */ }
    };
    await load();
  }

  // --- Facility Condition (FCI) — the deferred-maintenance backlog scored against replacement value
export async function renderFca(ctx: PanelContext) {
    const root = ctx.root; root.innerHTML = "";
    const el = (t: string, c = "") => { const e = document.createElement(t); if (c) e.className = c; return e; };
    root.appendChild(ctx.bar("🏥 Facility Condition (FCI)", () => { ctx.activeKey = null; void ctx.renderHome(); ctx.buildNav(); }));
    const pid = ctx.host.projectId();
    if (!pid) { root.insertAdjacentHTML("beforeend", noProjectHtml("Facility Condition")); return; }
    const usd = (n: number) => `$${Math.round(n).toLocaleString()}`;
    const bandColor = (b: string) => b === "Good" ? "var(--status-good)" : b === "Fair" ? "var(--status-warn)"
      : b === "Poor" ? "var(--status-crit)" : "var(--status-crit)";
    const intro = el("div", "meta"); intro.style.marginBottom = "8px";
    intro.innerHTML = "Assess every building element (UNIFORMAT II), price its deficiencies, and score the "
      + "<b>Facility Condition Index</b> = (deferred maintenance + capital renewal) ÷ replacement value. "
      + "Lower is better. Add elements under Operations → <b>Facility Condition</b>; resolved items leave the backlog.";
    root.appendChild(intro);
    const editBtn = el("button", "tool-btn"); editBtn.textContent = "✎ Assess elements";
    editBtn.title = "Add / edit facility-condition elements"; editBtn.style.marginBottom = "8px";
    editBtn.onclick = () => { const m = ctx.mods.find((x) => x.key === "fca_element"); if (m) { ctx.activeKey = "fca_element"; void ctx.openModule(m); ctx.buildNav(); } };
    const pdf = el("a", "tool-btn") as HTMLAnchorElement; pdf.textContent = "⬇ PDF"; pdf.target = "_blank"; pdf.rel = "noopener";
    pdf.href = ctx.host.api.url(`/projects/${pid}/reports/fca.pdf`); pdf.style.marginLeft = "6px";
    const actions = el("div"); actions.append(editBtn, pdf); root.appendChild(actions);
    const body = el("div"); body.textContent = "loading…"; root.appendChild(body);

    let s;
    try { s = await ctx.host.api.fcaIndex(pid); }
    catch (e) { body.textContent = `failed: ${(e as Error).message}`; return; }
    body.innerHTML = "";
    if (!s.elements) {
      body.innerHTML = `<div class="meta">No elements assessed yet — click <b>✎ Assess elements</b> to log building elements with their condition and any deficiency cost.</div>`;
      return;
    }
    // headline FCI + band
    const head = el("div", "dash-card"); head.style.cssText = "margin-bottom:8px;display:flex;gap:16px;align-items:baseline;flex-wrap:wrap";
    head.innerHTML = `<div><span style="font-size:32px;font-weight:700;color:${bandColor(s.band)}">${s.fci_pct}%</span>`
      + ` <span style="font-weight:600;color:${bandColor(s.band)}">${s.band}</span> <span class="meta">FCI</span></div>`
      + `<div class="meta">Deferred <b>${usd(s.deferred_maintenance)}</b> + renewal <b>${usd(s.capital_renewal)}</b> ÷ CRV <b>${usd(s.crv)}</b></div>`
      + `<div class="meta">${s.open_deficiencies} open deficiency(s) across ${s.elements} element(s) · bands: Good &lt;5% · Fair 5–10% · Poor 10–30% · Critical &gt;30%</div>`;
    body.append(head);
    // by-UNIFORMAT table
    if (s.by_uniformat.length) {
      const t = el("table", "portal-table") as HTMLTableElement; t.style.cssText = "width:100%;font-size:12px;margin-bottom:8px";
      t.innerHTML = `<thead><tr><th scope="col" style="text-align:left">UNIFORMAT group</th><th scope="col">Elements</th>`
        + `<th scope="col">Deferred</th><th scope="col">Renewal</th><th scope="col">CRV</th><th scope="col">FCI</th></tr></thead><tbody>`
        + s.by_uniformat.map((u) => `<tr><td>${esc(u.group)}</td><td style="text-align:center">${u.count}</td>`
          + `<td style="text-align:right">${usd(u.deferred)}</td><td style="text-align:right">${usd(u.renewal)}</td>`
          + `<td style="text-align:right">${usd(u.crv)}</td><td style="text-align:center">${u.fci_pct != null ? u.fci_pct + "%" : "—"}</td></tr>`).join("")
        + `</tbody>`;
      body.append(t);
    }
    // recommended spend by year
    if (s.recommended_by_year.length) {
      const wrap = el("div", "dash-card"); wrap.style.marginBottom = "8px";
      wrap.innerHTML = groupedBar(s.recommended_by_year.map((x) => ({ label: String(x.year), bars: [{ name: "cost", value: x.cost }] })),
        { title: "Recommended spend by year", fmt: usd });
      body.append(wrap);
    }
    // worst elements
    if (s.worst_elements.length) {
      const t = el("table", "portal-table") as HTMLTableElement; t.style.cssText = "width:100%;font-size:12px;margin-bottom:8px";
      t.innerHTML = `<thead><tr><th scope="col" style="text-align:left">Ref</th><th scope="col" style="text-align:left">Element</th>`
        + `<th scope="col">Condition</th><th scope="col">Cost</th></tr></thead><tbody>`
        + s.worst_elements.map((w) => `<tr><td>${esc(w.ref)}</td><td>${esc(w.element)}</td>`
          + `<td style="text-align:center">${esc(w.condition)}</td><td style="text-align:right">${usd(w.cost)}</td></tr>`).join("")
        + `</tbody>`;
      const h = el("div", "meta"); h.style.cssText = "font-weight:700;margin-bottom:2px"; h.textContent = "Worst elements (by cost)";
      body.append(h, t);
    }
    // portfolio FCI — capital prioritization across projects
    void ctx.host.api.fcaPortfolio().then((pf) => {
      if (pf.count < 2) return;                        // only interesting across ≥2 assessed buildings
      const pc = el("div", "dash-card"); pc.style.marginTop = "8px";
      pc.innerHTML = `<b>Portfolio — fund worst-first</b> <span class="meta">${pf.count} assessed building(s)</span>`
        + `<table class="fin-table" style="width:100%;font-size:12px;margin-top:4px">`
        + `<tr><th style="text-align:left">Project</th><th class="num">FCI</th><th style="text-align:center">Band</th><th class="num">Backlog</th></tr>`
        + pf.projects.slice(0, 12).map((p) => `<tr><td>${esc(p.project)}</td>`
          + `<td class="num" style="color:${bandColor(p.band)}">${p.fci_pct}%</td>`
          + `<td style="text-align:center">${esc(p.band)}</td><td class="num">${usd(p.backlog)}</td></tr>`).join("")
        + `</table>`;
      body.append(pc);
    }).catch(() => {});
  }

  // --- Discipline Spine — trace discipline → sheets → specs → bid packages → cost codes → budget ----
export async function renderSpine(ctx: PanelContext) {
    const root = ctx.root; root.innerHTML = "";
    const el = (t: string, c = "") => { const e = document.createElement(t); if (c) e.className = c; return e; };
    root.appendChild(ctx.bar("🔗 Discipline Spine", () => { ctx.activeKey = null; void ctx.renderHome(); ctx.buildNav(); }));
    const pid = ctx.host.projectId();
    if (!pid) { root.insertAdjacentHTML("beforeend", noProjectHtml("Discipline Spine")); return; }
    const intro = el("div", "meta"); intro.style.marginBottom = "8px";
    intro.innerHTML = "One thread from the model to the money: <b>discipline → sheets → specifications → "
      + "bid packages → cost codes → budget</b>. The coverage bars show how much of the chain is "
      + "connected; the gaps are where scope could fall between the model, the documents and the money.";
    root.appendChild(intro);
    const body = el("div"); body.textContent = "loading…"; root.appendChild(body);
    const usd = (n: number) => `$${Math.round(n).toLocaleString()}`;
    void ctx.host.api.spineTraceability(pid).then((t) => {
      body.innerHTML = "";
      const cov = t.coverage;
      // coverage bars — the four chain joins
      const bars = el("div", "dash-card"); bars.style.marginBottom = "10px";
      bars.innerHTML = `<div class="section-title">Chain coverage</div>`
        + progressBar(cov.sheets_specced_pct ?? 0, 100, { label: `Sheets → spec (${cov.sheets} sheets)` })
        + progressBar(cov.specs_packaged_pct ?? 0, 100, { label: `Specs → bid package (${cov.specs} specs)` })
        + progressBar(cov.packages_costed_pct ?? 0, 100, { label: `Bid packages → cost code (${cov.bid_packages} pkgs)` })
        + progressBar(cov.spec_to_budget_pct ?? 0, 100, { label: "Spec → budget (fully traceable)" });
      body.appendChild(bars);

      // per-discipline rollup + budget-by-discipline chart
      if (t.disciplines.length) {
        const dc = el("div", "dash-card"); dc.style.marginBottom = "10px";
        dc.innerHTML = `<div class="section-title">By discipline</div>`;
        if (t.disciplines.some((d) => d.budget > 0)) {
          const wrap = el("div"); wrap.style.margin = "4px 0 8px";
          wrap.innerHTML = groupedBar(t.disciplines.filter((d) => d.budget > 0).map((d) => ({ label: d.discipline, bars: [{ name: "budget", value: d.budget }] })),
            { title: "Bid-package budget by discipline", fmt: usd });
          dc.appendChild(wrap);
        }
        const tb = el("table", "portal-table") as HTMLTableElement; tb.style.cssText = "width:100%;font-size:12px";
        tb.innerHTML = `<thead><tr><th scope="col" style="text-align:left">Discipline</th><th scope="col">Sheets</th><th scope="col">Specs</th><th scope="col">Packages</th><th scope="col">Cost codes</th><th scope="col">Budget</th></tr></thead><tbody>`
          + t.disciplines.map((d) => `<tr><td>${esc(d.discipline)} <span class="meta">${d.code ?? ""}</span></td><td style="text-align:center">${d.sheets}</td><td style="text-align:center">${d.specs}</td><td style="text-align:center">${d.packages}</td><td style="text-align:center">${d.cost_codes}</td><td style="text-align:right">${d.budget ? usd(d.budget) : "—"}</td></tr>`).join("") + `</tbody>`;
        dc.appendChild(tb); body.appendChild(dc);
      }

      // coverage gaps
      const g = t.gaps;
      const gapCount = g.specs_without_bid_package.length + g.bid_packages_without_cost_code.length + g.sheets_without_spec.length;
      const gc = el("div", "dash-card"); gc.style.marginBottom = "10px";
      gc.innerHTML = `<div class="section-title">${gapCount ? "⚠ " : "✓ "}Broken links (${gapCount})</div>`;
      const gapList = (title: string, items: string[]) => {
        if (!items.length) return;
        const d = el("div", "meta"); d.style.margin = "3px 0";
        d.innerHTML = `<b>${title} (${items.length}):</b> ${items.slice(0, 12).map(esc).join(", ")}${items.length > 12 ? " …" : ""}`;
        gc.appendChild(d);
      };
      gapList("Specs with no bid package", g.specs_without_bid_package.map((x) => x.section || x.ref));
      gapList("Bid packages with no cost code", g.bid_packages_without_cost_code.map((x) => x.name || x.ref));
      gapList("Sheets with no governing spec", g.sheets_without_spec.map((x) => x.sheet || x.ref));
      if (!gapCount) gc.insertAdjacentHTML("beforeend", `<div class="meta">Every sheet, spec and package is linked through to the budget.</div>`);
      body.appendChild(gc);

      // the chain trace
      if (t.chain.length) {
        const cc = el("div", "dash-card");
        cc.innerHTML = `<div class="section-title">Spec → bid package → cost code</div>`;
        const tb = el("table", "portal-table") as HTMLTableElement; tb.style.cssText = "width:100%;font-size:11px";
        tb.innerHTML = `<thead><tr><th scope="col" style="text-align:left">Spec</th><th scope="col">Discipline</th><th scope="col">Bid package</th><th scope="col">Cost code</th><th scope="col"></th></tr></thead><tbody>`
          + t.chain.map((c) => `<tr><td>${esc(c.section || c.spec)} <span class="meta">${esc(c.title || "")}</span></td><td style="text-align:center">${esc(c.discipline || "—")}</td><td style="text-align:center">${esc(c.bid_package_name || "—")}</td><td style="text-align:center">${esc(c.cost_code_value || "—")}</td><td style="text-align:center;color:${c.linked ? "var(--status-good)" : "var(--status-warn)"}">${c.linked ? "✓" : "○"}</td></tr>`).join("") + `</tbody>`;
        cc.appendChild(tb); body.appendChild(cc);
      }
    }).catch((e) => { body.innerHTML = `<div class="meta">Spine unavailable: ${esc((e as Error).message)}</div>`; });
  }

  // --- Climate & water resilience — flood Design Flood Elevation + Rational-Method stormwater -------
export async function renderResilience(ctx: PanelContext) {
    const root = ctx.root; root.innerHTML = "";
    const el = (t: string, c = "") => { const e = document.createElement(t); if (c) e.className = c; return e; };
    root.appendChild(ctx.bar("🌊 Climate & Water Resilience", () => { ctx.activeKey = null; void ctx.renderHome(); ctx.buildNav(); }));
    const pid = ctx.host.projectId();
    if (!pid) { root.insertAdjacentHTML("beforeend", noProjectHtml("Climate Resilience")); return; }
    const intro = el("div", "meta"); intro.style.marginBottom = "8px";
    intro.innerHTML = "Treat rainfall and flooding as quantifiable parameters across the lifecycle. "
      + "<b>Flood</b> (ASCE 24): the Design Flood Elevation and which equipment sits below it. "
      + "<b>Stormwater</b> (Rational Method): peak runoff Q = C·i·A and detention. <b>Weather</b>: "
      + "weather-sensitive activities and the site-weather-risk register. Records live under "
      + "Resilience → <b>Flood Risk</b> / <b>Drainage Area</b> / <b>Site Weather Risk</b>.";
    root.appendChild(intro);
    const jump = (k: string) => { const m = ctx.mods.find((x) => x.key === k); if (m) { ctx.activeKey = k; void ctx.openModule(m); ctx.buildNav(); } };
    const acts = el("div"); acts.style.cssText = "display:flex;gap:6px;flex-wrap:wrap;margin-bottom:8px";
    const b1 = el("button", "tool-btn"); b1.textContent = "✎ Flood Risk"; b1.onclick = () => jump("flood_risk");
    const b2 = el("button", "tool-btn"); b2.textContent = "✎ Drainage Area"; b2.onclick = () => jump("drainage_area");
    const b3 = el("button", "tool-btn"); b3.textContent = "✎ Site Weather Risk"; b3.onclick = () => jump("climate_site_risk");
    const pdf = el("a", "tool-btn") as HTMLAnchorElement; pdf.textContent = "⬇ PDF"; pdf.target = "_blank"; pdf.rel = "noopener";
    pdf.href = ctx.host.api.url(`/projects/${pid}/reports/resilience.pdf`);
    acts.append(b1, b2, b3, pdf); root.appendChild(acts);
    const usd = (n: number) => Math.round(n).toLocaleString();

    // Physical climate-risk rating (rollup — also feeds ESG)
    const rCard = el("div", "dash-card"); rCard.style.marginBottom = "10px";
    rCard.innerHTML = `<div class="section-title">🌐 Physical climate-risk rating</div><div class="meta">loading…</div>`;
    root.appendChild(rCard);
    void ctx.host.api.resilienceClimateRisk(pid).then((c) => {
      const color = c.rating === "Severe" ? "var(--status-crit)" : c.rating === "High" ? "var(--status-crit)"
        : c.rating === "Moderate" ? "var(--status-warn)" : "var(--status-good)";
      rCard.innerHTML = `<div class="section-title">🌐 Physical climate-risk rating</div>`;
      const head = el("div"); head.style.cssText = "display:flex;align-items:baseline;gap:8px;margin:2px 0 6px";
      head.innerHTML = `<span style="font-size:22px;font-weight:700;color:${color}">${esc(c.rating)}</span>`
        + `<span class="meta">score ${c.score} · rolls up into the ESG scorecard</span>`;
      rCard.appendChild(head);
      const ul = el("ul"); ul.style.cssText = "margin:0;padding-left:18px;font-size:12px";
      ul.innerHTML = c.factors.map((f) => `<li>${esc(f)}</li>`).join("");
      rCard.appendChild(ul);
    }).catch((e) => { rCard.innerHTML = `<div class="meta">Climate-risk data unavailable: ${esc((e as Error).message)}</div>`; });

    // Flood card
    const fCard = el("div", "dash-card"); fCard.style.marginBottom = "10px";
    fCard.innerHTML = `<div class="section-title">🌊 Flood risk — Design Flood Elevation</div><div class="meta">loading…</div>`;
    root.appendChild(fCard);
    void ctx.host.api.resilienceFlood(pid).then((f) => {
      fCard.innerHTML = `<div class="section-title">🌊 Flood risk — Design Flood Elevation</div>`;
      if (!f.count) { fCard.insertAdjacentHTML("beforeend", `<div class="meta">No flood assessment yet — click <b>✎ Flood Risk</b> to enter the FEMA zone + Base Flood Elevation.</div>`); return; }
      const sfhaColor = f.in_special_flood_hazard_area ? "var(--status-crit)" : "var(--status-good)";
      const chips = el("div", "meta"); chips.style.margin = "4px 0 6px";
      chips.innerHTML = `DFE <b>${f.design_flood_elevation_ft ?? "—"} ft</b> · `
        + `<b style="color:${sfhaColor}">${f.in_special_flood_hazard_area ? "In special flood hazard area" : "Outside SFHA"}</b> · `
        + `<b style="color:${f.at_risk_count ? "var(--status-crit)" : "var(--status-good)"}">${f.at_risk_count}</b> asset(s) below the DFE (of ${f.assets_checked} with an elevation)`;
      fCard.appendChild(chips);
      if (f.assets_at_risk.length) {
        const t = el("table", "portal-table") as HTMLTableElement; t.style.cssText = "width:100%;font-size:12px";
        t.innerHTML = `<thead><tr><th scope="col" style="text-align:left">Asset</th><th scope="col">Elev (ft)</th><th scope="col">Below DFE by</th></tr></thead><tbody>`
          + f.assets_at_risk.map((a) => `<tr><td>${esc(a.asset)}</td><td style="text-align:center">${a.elevation_ft}</td><td style="text-align:center;color:var(--status-crit)">${a.below_dfe_by_ft} ft</td></tr>`).join("") + `</tbody>`;
        fCard.appendChild(t);
        const hint = el("div", "meta"); hint.style.marginTop = "4px"; hint.textContent = "Elevate or flood-proof these — or raise their Installed Elevation on the Asset Register.";
        fCard.appendChild(hint);
      }
    }).catch((e) => { fCard.innerHTML = `<div class="meta">Flood data unavailable: ${esc((e as Error).message)}</div>`; });

    // Stormwater card
    const sCard = el("div", "dash-card"); sCard.style.marginBottom = "10px";
    sCard.innerHTML = `<div class="section-title">💧 Stormwater — Rational Method (Q = C·i·A)</div><div class="meta">loading…</div>`;
    root.appendChild(sCard);
    void ctx.host.api.resilienceStormwater(pid).then((s) => {
      sCard.innerHTML = `<div class="section-title">💧 Stormwater — Rational Method (Q = C·i·A)</div>`;
      if (!s.count) { sCard.insertAdjacentHTML("beforeend", `<div class="meta">No catchments yet — click <b>✎ Drainage Area</b> to add surfaces with their area + rainfall intensity.</div>`); return; }
      const chips = el("div", "meta"); chips.style.margin = "4px 0 6px";
      chips.innerHTML = `Peak runoff <b>${s.peak_runoff_cfs} cfs</b> · composite C <b>${s.composite_runoff_coefficient ?? "—"}</b> · `
        + `${s.total_area_acres} ac · detention <b>${usd(s.detention_volume_cf)} cf</b> (${usd(s.detention_volume_gal)} gal)`;
      sCard.appendChild(chips);
      if (s.by_surface.length) {
        const wrap = el("div", "dash-card"); wrap.style.margin = "6px 0";
        wrap.innerHTML = groupedBar(s.by_surface.map((x) => ({ label: x.surface, bars: [{ name: "cfs", value: x.peak_cfs }] })),
          { title: "Peak runoff by surface (cfs)", fmt: (n) => n.toFixed(1) });
        sCard.appendChild(wrap);
      }
      if (s.catchments.length) {
        const t = el("table", "portal-table") as HTMLTableElement; t.style.cssText = "width:100%;font-size:12px";
        t.innerHTML = `<thead><tr><th scope="col" style="text-align:left">Catchment</th><th scope="col">Area (sf)</th><th scope="col">C</th><th scope="col">i (in/hr)</th><th scope="col">Peak (cfs)</th></tr></thead><tbody>`
          + s.catchments.map((x) => `<tr><td>${esc(x.name)}</td><td style="text-align:right">${usd(x.area_sf)}</td><td style="text-align:center">${x.c}</td><td style="text-align:center">${x.i_in_hr}</td><td style="text-align:right">${x.peak_cfs}</td></tr>`).join("") + `</tbody>`;
        sCard.appendChild(t);
      }
    }).catch((e) => { sCard.innerHTML = `<div class="meta">Stormwater data unavailable: ${esc((e as Error).message)}</div>`; });

    // Weather-sequenced construction card
    const wCard = el("div", "dash-card"); wCard.style.marginBottom = "10px";
    wCard.innerHTML = `<div class="section-title">⛈ Weather-sequenced construction</div><div class="meta">loading…</div>`;
    root.appendChild(wCard);
    void ctx.host.api.resilienceWeather(pid).then((w) => {
      wCard.innerHTML = `<div class="section-title">⛈ Weather-sequenced construction</div>`;
      if (!w.sensitive_count && !w.site_risk_count && !w.delay_report_count) {
        wCard.insertAdjacentHTML("beforeend", `<div class="meta">Flag weather-sensitive schedule activities and log site-weather hazards under <b>✎ Site Weather Risk</b> to sequence exposed work out of the wet/freeze season.</div>`);
        return;
      }
      const chips = el("div", "meta"); chips.style.margin = "4px 0 6px";
      chips.innerHTML = `<b>${w.sensitive_count}</b> weather-sensitive activit${w.sensitive_count === 1 ? "y" : "ies"} · `
        + `<b style="color:${w.high_severity_open ? "var(--status-crit)" : w.open_risk_count ? "var(--status-warn)" : "var(--status-good)"}">${w.open_risk_count}</b> open site hazard(s)`
        + `${w.high_severity_open ? ` (${w.high_severity_open} high)` : ""} · `
        + `<b>${w.weather_delay_days}</b> weather-delay day(s) logged`;
      wCard.appendChild(chips);
      if (w.site_risks.length) {
        const sevColor = (s: string) => s === "High" ? "var(--status-crit)" : s === "Moderate" ? "var(--status-warn)" : "var(--status-good)";
        const t = el("table", "portal-table") as HTMLTableElement; t.style.cssText = "width:100%;font-size:12px";
        t.innerHTML = `<thead><tr><th scope="col" style="text-align:left">Hazard</th><th scope="col">Season</th><th scope="col">Severity</th><th scope="col">Status</th></tr></thead><tbody>`
          + w.site_risks.map((x) => `<tr><td>${esc(x.hazard_type)}${x.location ? ` <span class="meta">(${esc(x.location)})</span>` : ""}</td><td style="text-align:center">${esc(x.season)}</td><td style="text-align:center;color:${sevColor(x.severity)}">${esc(x.severity)}</td><td style="text-align:center">${x.open ? esc(x.state) : "closed"}</td></tr>`).join("") + `</tbody>`;
        wCard.appendChild(t);
      }
      if (w.weather_sensitive_activities.length) {
        const t = el("table", "portal-table") as HTMLTableElement; t.style.cssText = "width:100%;font-size:12px;margin-top:6px";
        t.innerHTML = `<thead><tr><th scope="col" style="text-align:left">Weather-sensitive activity</th><th scope="col">Trade</th><th scope="col">Sensitivity</th><th scope="col">Window</th></tr></thead><tbody>`
          + w.weather_sensitive_activities.slice(0, 25).map((a) => `<tr><td>${esc(a.name)}</td><td style="text-align:center">${esc(a.trade || "—")}</td><td style="text-align:center">${esc(a.sensitivity)}</td><td style="text-align:center">${esc(a.start || "?")} → ${esc(a.finish || "?")}</td></tr>`).join("") + `</tbody>`;
        wCard.appendChild(t);
      }
    }).catch((e) => { wCard.innerHTML = `<div class="meta">Weather data unavailable: ${esc((e as Error).message)}</div>`; });
  }

  // --- Energy: metered utilities — EUI, monthly trend, cost by utility --------------------------
export async function renderEnergy(ctx: PanelContext) {
    const root = ctx.root; root.innerHTML = "";
    const el = (t: string, c = "") => { const e = document.createElement(t); if (c) e.className = c; return e; };
    root.appendChild(ctx.bar("⚡ Energy — Metered Utilities", () => { ctx.activeKey = null; void ctx.renderHome(); ctx.buildNav(); }));
    const pid = ctx.host.projectId();
    if (!pid) { root.insertAdjacentHTML("beforeend", noProjectHtml("Energy")); return; }
    const intro = el("div", "meta"); intro.style.marginBottom = "8px";
    intro.textContent = "Operational energy from meter readings (entered manually or CSV-imported "
      + "under Operations → Meter Readings), converted to site kBtu and normalized to EUI "
      + "(kBtu/sf/yr) — the benchmarking currency for building performance. Fully offline.";
    root.appendChild(intro);
    const body = el("div"); body.textContent = "loading…"; root.appendChild(body);
    let e0; let bs;
    try {
      e0 = await ctx.host.api.energyActual(pid);
      bs = await ctx.host.api.energyBenchmarkStatus();
    } catch (err) { body.textContent = `failed: ${(err as Error).message}`; return; }
    body.innerHTML = "";
    // KPI cards
    const cards = el("div"); cards.style.cssText = "display:flex;gap:8px;flex-wrap:wrap;margin-bottom:8px";
    const card = (label: string, value: string) => {
      const c = el("div", "dash-card"); c.style.minWidth = "120px";
      c.innerHTML = `<div style="font-size:20px;font-weight:600">${value}</div><div class="meta">${label}</div>`;
      return c;
    };
    cards.append(card("EUI (kBtu/sf/yr)", e0.eui_kbtu_sf_yr != null ? String(e0.eui_kbtu_sf_yr) : "—"),
      card("site energy (kBtu)", e0.total_kbtu.toLocaleString()),
      card("utility cost", cmoney(e0.total_cost)),
      card("water (gal)", e0.water_gallons.toLocaleString()),
      card("months covered", String(e0.months_covered)));
    body.append(cards);
    if (e0.eui_kbtu_sf_yr == null && e0.total_kbtu > 0) {
      const hint = el("div", "meta"); hint.style.marginBottom = "8px";
      hint.textContent = "EUI needs a gross floor area — load the model (space quantities) or record GFA on the project.";
      body.append(hint);
    }
    // monthly trend
    if (e0.monthly.length > 1) {
      const wrap = el("div", "dash-card"); wrap.style.marginBottom = "8px";
      wrap.innerHTML = lineChart([{ name: "site kBtu", values: e0.monthly.map((m) => m.kbtu) }],
        { title: "Monthly site energy (kBtu)", xlabels: e0.monthly.map((m) => m.month),
          fmt: (n) => n.toLocaleString() });
      body.append(wrap);
    }
    // by-utility table
    const utils = Object.entries(e0.by_utility);
    if (utils.length) {
      const t = el("table", "portal-table") as HTMLTableElement; t.style.cssText = "width:100%;font-size:12px;margin:6px 0";
      t.innerHTML = `<thead><tr><th scope="col" style="text-align:left">Utility</th><th scope="col">Consumption</th>`
        + `<th scope="col">kBtu</th><th scope="col">Cost</th></tr></thead><tbody>`
        + utils.map(([u, v]) => `<tr><td>${esc(u)}</td><td style="text-align:right">${v.consumption.toLocaleString()} ${esc(v.unit)}</td>`
          + `<td style="text-align:right">${v.kbtu.toLocaleString()}</td><td style="text-align:right">${cmoney(v.cost)}</td></tr>`).join("")
        + `</tbody>`;
      body.append(t);
    } else {
      const none = el("div", "meta");
      none.textContent = "No meter readings yet — add meters and readings under Operations, or import a CSV.";
      body.append(none);
    }
    // benchmarking bridge status (honest, flagged)
    const b = el("div", "meta"); b.style.marginTop = "8px"; b.textContent = bs.message;
    body.append(b);
  }

  // --- Turnover: substantial completion (G704) + architect punch-list sign-off ------------------
export async function renderTurnover(ctx: PanelContext) {
    const root = ctx.root; root.innerHTML = "";
    const el = (t: string, c = "") => { const e = document.createElement(t); if (c) e.className = c; return e; };
    root.appendChild(ctx.bar("🏁 Turnover — Substantial Completion", () => { ctx.activeKey = null; void ctx.renderHome(); ctx.buildNav(); }));
    const pid = ctx.host.projectId();
    if (!pid) { root.insertAdjacentHTML("beforeend", noProjectHtml("Turnover")); return; }
    const intro = el("div", "meta"); intro.style.marginBottom = "8px";
    intro.textContent = "Certify substantial completion (AIA G704): the Architect signs off the punch "
      + "list, the current model version is stamped as the record (as-built) model, and the signed "
      + "certificate joins the turnover package.";
    root.appendChild(intro);
    // SURF-4b: the combined turnover STATUS strip (/turnover/status — backed, never surfaced):
    // certified-or-not at a glance, who signed, and whether the record model is locked.
    const strip = el("div", "meta"); strip.style.cssText = "margin-bottom:8px";
    root.appendChild(strip);
    void ctx.host.api.turnoverStatus(pid).then((s) => {
      const sc = s.substantial_completion;
      strip.innerHTML = sc
        ? `🏁 <b>${esc(sc.ref)}</b> certified` + (sc.signed_by.length ? ` — signed by ${esc(sc.signed_by.join(", "))}` : "")
          + (s.record_model_locked ? ` · <span style="color:var(--status-good)">🔒 record model locked${sc.record_model_version != null ? ` at v${sc.record_model_version}` : ""}</span>` : "")
        : (s.readiness.ready_for_substantial_completion
            ? `<span style="color:var(--status-good)">ready to certify</span> — no certificate on file yet`
            : `not yet ready to certify`);
    }).catch(() => { strip.remove(); });
    const body = el("div"); body.textContent = "loading…"; root.appendChild(body);
    // CX-1: the commissioning loop — seed from the model, the system × phase matrix, per-system dossier
    const cxHead = el("div", "meta"); cxHead.style.cssText = "margin:12px 0 4px;font-weight:600";
    cxHead.textContent = "🔌 Commissioning (system × phase)";
    const cxWrap = el("div");
    root.append(cxHead, cxWrap);
    const loadCx = async () => {
      cxWrap.innerHTML = `<div class="meta">loading matrix…</div>`;
      try {
        const mx = await ctx.host.api.cxMatrix(pid);
        cxWrap.innerHTML = "";
        const row = el("div"); row.style.cssText = "display:flex;gap:6px;align-items:center;margin-bottom:6px";
        const seedB = el("button", "file-btn") as HTMLButtonElement;
        seedB.textContent = "⚡ Seed from model";
        seedB.title = "Equipment classes in the published model become GUID-keyed assets (deduped), "
          + "each systemed asset gets Pre-Functional + Functional tests with MEP FPT expected values.";
        seedB.onclick = async () => {
          seedB.disabled = true;
          try {
            const r = await ctx.host.api.cxSeed(pid);
            toast(r.model_scored
              ? `${r.created} asset(s) + ${r.checklists?.created ?? 0} checklist(s) seeded`
              : (r.note || "no model loaded"), r.model_scored ? "success" : "info");
            void loadCx();
          } catch (e) { toast((e as Error).message, "error"); }
          finally { seedB.disabled = false; }
        };
        row.append(seedB);
        cxWrap.append(row);
        if (!mx.system_count) {
          cxWrap.insertAdjacentHTML("beforeend",
            `<div class="meta">No commissioning systems yet — seed from the model or add commissioning records.</div>`);
          return;
        }
        const t = el("table", "portal-table") as HTMLTableElement; t.style.cssText = "width:100%;font-size:11px";
        const cell = (c: { total: number; accepted: number; pass: number; fail: number } | null | undefined) =>
          !c ? "—" : `${c.accepted}/${c.total}` + (c.fail ? ` <span style="color:var(--status-crit)">✗${c.fail}</span>` : "");
        t.innerHTML = `<thead><tr><th scope="col" style="text-align:left">System</th><th scope="col">Assets</th>`
          + mx.phases.map((p) => `<th scope="col">${esc(p)}</th>`).join("")
          + `<th scope="col">%</th><th scope="col"><span class="sr-only">Dossier</span></th></tr></thead><tbody>`
          + mx.systems.map((s) => `<tr><td>${esc(s.system)}</td><td style="text-align:center">${s.assets}</td>`
            + mx.phases.map((p) => `<td style="text-align:center">${cell(s.phases[p])}</td>`).join("")
            + `<td style="text-align:right">${s.complete_pct}%</td>`
            + `<td><a href="#" data-sys="${esc(s.system)}" class="cx-dossier">dossier</a></td></tr>`).join("")
          + `</tbody>`;
        const wrap = el("div"); wrap.style.overflowX = "auto"; wrap.appendChild(t); cxWrap.append(wrap);
        const detail = el("div"); cxWrap.append(detail);
        t.querySelectorAll<HTMLAnchorElement>("a.cx-dossier").forEach((a) => {
          a.onclick = async (ev) => {
            ev.preventDefault();
            try {
              const dz = await ctx.host.api.cxDossier(pid, a.dataset.sys || "");
              const box = el("div", "dash-card"); box.style.cssText = "margin:6px 0";
              box.innerHTML = `<div class="meta"><b>${esc(dz.system)}</b> — ${dz.asset_count} asset(s) · `
                + `${dz.accepted}/${dz.test_count} tests accepted (${dz.complete_pct}%)`
                + (dz.open_punch_mentions ? ` · <span style="color:var(--status-warn)">${dz.open_punch_mentions} open punch mention(s)</span>` : "") + `</div>`
                + (Object.keys(dz.expected_values).length
                  ? `<div class="meta">FPT expected: ${Object.entries(dz.expected_values).slice(0, 8)
                    .map(([k, v]) => `${esc(k)}=${esc(String(v))}`).join(" · ")}</div>` : "")
                + Object.entries(dz.tests).map(([ph, ts]) => `<div class="meta"><b>${esc(ph)}</b>: `
                  + ts.slice(0, 10).map((x) => `${esc(x.ref || "")} ${x.state === "accepted" ? "✅" : x.result === "Fail" ? "🔴" : "·"}`).join(" ")
                  + (ts.length > 10 ? ` +${ts.length - 10} more` : "") + `</div>`).join("");
              detail.innerHTML = ""; detail.append(box);
            } catch (e) { toast((e as Error).message, "error"); }
          };
        });
      } catch (e) { cxWrap.innerHTML = `<div class="meta">commissioning matrix failed: ${esc((e as Error).message)}</div>`; }
    };
    void loadCx();
    const load = async () => {
      body.innerHTML = "";
      let rd; let certs;
      try {
        rd = await ctx.host.api.turnoverReadiness(pid);
        certs = (await ctx.host.api.moduleRecords(pid, "completion_certificate"))
          .filter((r) => (r.data as { type?: string } | undefined)?.type === "Substantial");
      } catch (e) { body.textContent = `failed: ${(e as Error).message}`; return; }
      // readiness
      const p = rd.punch;
      const rdiv = el("div", "dash-card"); rdiv.style.marginBottom = "8px";
      rdiv.innerHTML = `<div class="meta"><b>Punch list</b>: ${p.count} item(s) · ${p.open} open · ${p.verified} verified`
        + (p.complete_pct != null ? ` · ${p.complete_pct}% complete` : "") + `</div>`
        + `<div class="meta">Latest model version: <b>${rd.latest_model_version ?? "—"}</b> · `
        + `${rd.ready_for_substantial_completion ? "<span style=\"color:var(--status-good)\">ready to certify</span>" : "<span style=\"color:var(--status-warn)\">prepare a punch list first</span>"}</div>`;
      body.append(rdiv);
      // substantial-completion certificate(s)
      if (!certs.length) {
        const note = el("div", "meta"); note.textContent = "No substantial-completion certificate yet.";
        const mk = el("button", "file-btn") as HTMLButtonElement; mk.textContent = "Create certificate";
        mk.onclick = () => void ctx.host.api.createModuleRecord(pid, "completion_certificate",
          { data: { subject: "Substantial Completion", type: "Substantial" } })
          .then(() => { toast("Certificate created", "success"); void load(); })
          .catch((e) => toast((e as Error).message, "error"));
        note.style.marginBottom = "6px"; body.append(note, mk);
        return;
      }
      for (const cert of certs) {
        const d = (cert.data || {}) as { signatures?: { party: string; certifies?: boolean }[]; record_model_version?: number };
        const certified = (d.signatures || []).some((s) => s.party === "Architect" && s.certifies);
        const card = el("div", "dash-card"); card.style.cssText = "margin:6px 0";
        card.innerHTML = `<div style="display:flex;justify-content:space-between;align-items:center">`
          + `<b>${cert.ref || "Certificate"}</b><span class="badge">${cert.workflow_state}</span></div>`
          + `<div class="meta">${certified ? `✅ Architect certified · record model v${d.record_model_version ?? "—"}` : "Awaiting architect certification"}</div>`;
        const actions = el("div"); actions.style.cssText = "margin-top:6px;display:flex;gap:6px;flex-wrap:wrap";
        if (!certified) {
          const cbtn = el("button", "file-btn") as HTMLButtonElement; cbtn.textContent = "Architect: certify substantial completion";
          cbtn.onclick = async () => {
            if (!rd!.ready_for_substantial_completion) { toast("Prepare a punch list first", "error"); return; }
            const v = await promptModal("Certify substantial completion (G704)", [
              { name: "arch", label: "Certifying Architect (name / license)", required: true },
              { name: "owner", label: "Owner signatory (optional)" },
            ], "Certify");
            if (!v) return;
            try { await ctx.host.api.turnoverCertify(pid, cert.id, v.arch ?? "", v.owner || undefined);
              toast("Substantial completion certified", "success"); void load(); }
            catch (e) { toast((e as Error).message, "error"); }
          };
          actions.append(cbtn);
        }
        const dl = el("a", "file-btn") as HTMLAnchorElement; dl.textContent = "⬇ G704 certificate";
        dl.href = ctx.host.api.g704Url(pid, cert.id); dl.target = "_blank";
        actions.append(dl);
        card.append(actions); body.append(card);
      }
    };
    await load();
  }

import { noProjectHtml } from "../../ui/empty";
import { escapeHtml as esc, toast } from "../../ui/feedback";
import type { PanelContext } from "../panelContext";

/**
 * Standards & information-management panels (space program, BIM KPI, standards checks, IDS/EIR).
 * Extracted from portal.ts as free render*(ctx) functions (portal.ts decomposition).
 */

  // --- Space Program: the concept adjacency graph that feeds the massing generator --------------
export async function renderProgram(ctx: PanelContext) {
    const root = ctx.root; root.innerHTML = "";
    const el = (t: string, c = "") => { const e = document.createElement(t); if (c) e.className = c; return e; };
    root.appendChild(ctx.bar("🧩 Space Program", () => { ctx.activeKey = null; void ctx.renderHome(); ctx.buildNav(); }));
    const pid = ctx.host.projectId();
    if (!pid) { root.insertAdjacentHTML("beforeend", noProjectHtml("Space Program")); return; }
    const intro = el("div", "meta"); intro.style.marginBottom = "8px";
    intro.textContent = "Program the building before you mass it: spaces as nodes (area × quantity) "
      + "with adjacency preferences as edges. The gross area and use mix feed the zoning → massing "
      + "generator and the proforma. Add spaces under Programming → Space Program.";
    root.appendChild(intro);
    const body = el("div"); body.textContent = "loading…"; root.appendChild(body);
    let s;
    try { s = await ctx.host.api.programSummary(pid); }
    catch (e) { body.textContent = `failed: ${(e as Error).message}`; return; }
    body.innerHTML = "";
    if (!s.spaces) {
      body.innerHTML = `<div class="meta">No program yet — add spaces under Programming → Space Program.</div>`;
      return;
    }
    // area KPI cards
    const cards = el("div"); cards.style.cssText = "display:flex;gap:8px;flex-wrap:wrap;margin-bottom:8px";
    const card = (label: string, value: string) => {
      const c = el("div", "dash-card"); c.style.minWidth = "110px";
      c.innerHTML = `<div style="font-size:20px;font-weight:600">${value}</div><div class="meta">${label}</div>`;
      return c;
    };
    cards.append(card("spaces", String(s.spaces)),
      card("gross area (sf)", s.total_area_sf.toLocaleString()),
      card("net / leasable (sf)", s.net_area_sf.toLocaleString()),
      card("efficiency", s.efficiency_pct != null ? `${s.efficiency_pct}%` : "—"));
    body.append(cards);
    // mix by use
    const mix = Object.entries(s.by_type);
    const t = el("table", "portal-table") as HTMLTableElement; t.style.cssText = "width:100%;font-size:12px;margin-bottom:8px";
    t.innerHTML = `<thead><tr><th scope="col" style="text-align:left">Use</th><th scope="col">Count</th>`
      + `<th scope="col">Area (sf)</th><th scope="col">Mix</th></tr></thead><tbody>`
      + mix.map(([k, v]) => `<tr><td>${esc(k)}</td><td style="text-align:center">${v.count}</td>`
        + `<td style="text-align:right">${v.area.toLocaleString()}</td><td style="text-align:center">${v.pct}%</td></tr>`).join("")
      + `</tbody>`;
    body.append(t);
    // adjacency graph — edges as chips, unmet flagged
    const ac = el("div", "dash-card");
    ac.innerHTML = `<b>Adjacency</b> <span class="meta">${s.adjacency.satisfiable}/${s.adjacency.total} preferences satisfiable</span>`;
    if (s.graph.edges.length) {
      const wrap = el("div"); wrap.style.cssText = "display:flex;gap:6px;flex-wrap:wrap;margin-top:6px";
      s.graph.edges.forEach((e) => {
        const chip = el("span"); chip.style.cssText = `font-size:11px;padding:2px 8px;border-radius:10px;`
          + `border:1px solid var(${e.satisfiable ? "--border" : "--status-warn"});`
          + `color:var(${e.satisfiable ? "--fg" : "--status-warn"})`;
        chip.textContent = `${e.from_type} → ${e.to_type}${e.satisfiable ? "" : " (unmet)"}`;
        wrap.append(chip);
      });
      ac.append(wrap);
    }
    body.append(ac);
    // massing hand-off
    const mh = el("div", "meta"); mh.style.marginTop = "8px";
    mh.textContent = `Massing hand-off: ${s.massing_hints.gross_area_sf.toLocaleString()} sf gross, `
      + Object.entries(s.massing_hints.mix_pct).map(([k, v]) => `${k} ${v}%`).join(" · ");
    body.append(mh);
  }

  // --- BIM KPIs: the 10-category information-management scorecard + handover acceptance ---------
export async function renderBimKpi(ctx: PanelContext) {
    const root = ctx.root; root.innerHTML = "";
    const el = (t: string, c = "") => { const e = document.createElement(t); if (c) e.className = c; return e; };
    root.appendChild(ctx.bar("📊 BIM KPIs (ISO 19650)", () => { ctx.activeKey = null; void ctx.renderHome(); ctx.buildNav(); }));
    const pid = ctx.host.projectId();
    if (!pid) { root.insertAdjacentHTML("beforeend", noProjectHtml("BIM KPIs")); return; }
    const intro = el("div", "meta"); intro.style.marginBottom = "8px";
    intro.textContent = "The standard information-management scorecard — ten categories graded from "
      + "the CDE, model quality and the issue / asset / closeout records. Categories with no inputs "
      + "show n/a rather than a guess.";
    root.appendChild(intro);
    const body = el("div"); body.textContent = "loading…"; root.appendChild(body);
    let sc; let ha;
    try { sc = await ctx.host.api.bimKpiScorecard(pid); ha = await ctx.host.api.handoverAcceptance(pid); }
    catch (e) { body.textContent = `failed: ${(e as Error).message}`; return; }
    body.innerHTML = "";
    // summary cards
    const s = sc.summary;
    const cards = el("div"); cards.style.cssText = "display:flex;gap:8px;flex-wrap:wrap;margin-bottom:8px";
    const card = (label: string, value: string, color?: string) => {
      const c = el("div", "dash-card"); c.style.cssText = `min-width:90px${color ? `;border-left:3px solid var(${color})` : ""}`;
      c.innerHTML = `<div style="font-size:20px;font-weight:600">${value}</div><div class="meta">${label}</div>`;
      return c;
    };
    cards.append(card("health", s.health_pct != null ? `${s.health_pct}%` : "—"),
      card("good", String(s.good), "--status-good"),
      card("warn", String(s.warn), "--status-warn"),
      card("poor", String(s.poor), "--status-crit"),
      card("n/a", String(s.na)));
    body.append(cards);
    // handover acceptance banner
    const hb = el("div", "dash-card");
    hb.style.cssText = `border-left:4px solid var(${ha.accepted ? "--status-good" : "--status-warn"});margin-bottom:8px`;
    hb.innerHTML = `<b>${ha.accepted ? "✅ Handover data-drop ACCEPTED" : "⏳ Handover not ready"}</b>`
      + `<div class="meta">${ha.checks.map((c) => `${c.ok ? "✅" : "⬜"} ${esc(c.label)}`).join(" · ")}</div>`;
    body.append(hb);
    // category table
    const dot = (g: string) => g === "good" ? "🟢" : g === "warn" ? "🟡" : g === "poor" ? "🔴" : "⚪";
    const t = el("table", "portal-table") as HTMLTableElement; t.style.cssText = "width:100%;font-size:12px";
    t.innerHTML = `<thead><tr><th scope="col"></th><th scope="col" style="text-align:left">Category</th>`
      + `<th scope="col" style="text-align:left">Status</th></tr></thead><tbody>`
      + sc.categories.map((c) => `<tr><td style="text-align:center">${dot(c.grade)}</td>`
        + `<td>${esc(c.label)}</td><td>${esc(c.headline)}</td></tr>`).join("") + `</tbody>`;
    body.append(t);
    if (!sc.model_scored) {
      const hint = el("div", "meta"); hint.style.marginTop = "6px";
      hint.textContent = "Load a model to score the authoring-quality and openBIM-exchange categories.";
      body.append(hint);
    }
    // report link
    const rb = el("div"); rb.style.marginTop = "8px";
    const a = document.createElement("a"); a.className = "portal-btn"; a.textContent = "⬇ Scorecard (PDF)";
    a.href = ctx.host.api.reportUrl(pid, "bim_kpi", "pdf"); a.target = "_blank"; a.rel = "noopener";
    rb.append(a); body.append(rb);
  }

  // --- CDE / Standards: ISO 19650 container discipline + requirements register ------------------
export async function renderStandards(ctx: PanelContext) {
    const root = ctx.root; root.innerHTML = "";
    const el = (t: string, c = "") => { const e = document.createElement(t); if (c) e.className = c; return e; };
    root.appendChild(ctx.bar("🗂 CDE / Standards (ISO 19650)", () => { ctx.activeKey = null; void ctx.renderHome(); ctx.buildNav(); }));
    const pid = ctx.host.projectId();
    if (!pid) { root.insertAdjacentHTML("beforeend", noProjectHtml("CDE / Standards")); return; }
    const intro = el("div", "meta"); intro.style.marginBottom = "8px";
    intro.textContent = "Information management to ISO 19650: deliverables move through the Common "
      + "Data Environment (Work-in-progress → Shared → Published → Archived) with suitability codes "
      + "and revisions, and the appointment carries its information requirements (EIR, BEP, AIR). "
      + "Manage records under Information Management → Information Containers / Requirements.";
    root.appendChild(intro);
    const body = el("div"); body.textContent = "loading…"; root.appendChild(body);
    let st; let reg;
    try { st = await ctx.host.api.cdeStatus(pid); reg = await ctx.host.api.infoRequirementsRegister(pid); }
    catch (e) { body.textContent = `failed: ${(e as Error).message}`; return; }
    body.innerHTML = "";
    // container state distribution
    const stages: [string, string][] = [["wip", "WIP"], ["shared", "Shared"], ["published", "Published"], ["archived", "Archived"]];
    const cards = el("div"); cards.style.cssText = "display:flex;gap:8px;flex-wrap:wrap;margin-bottom:8px";
    for (const [k, label] of stages) {
      const c = el("div", "dash-card"); c.style.minWidth = "90px";
      c.innerHTML = `<div style="font-size:20px;font-weight:600">${st.by_state[k] ?? 0}</div><div class="meta">${label}</div>`;
      cards.append(c);
    }
    body.append(cards);
    // CDE discipline metrics
    const d = st.discipline;
    const disc = el("div", "dash-card"); disc.style.marginBottom = "8px";
    const pct = (v: number | null) => v != null ? `${v}%` : "—";
    disc.innerHTML = `<b>CDE discipline</b>`
      + `<table class="fin-table" style="width:100%;font-size:12px;margin-top:4px">`
      + `<tr><td>Revision control</td><td class="num">${pct(d.revision_control_pct)}</td></tr>`
      + `<tr><td>Approval status (past WIP)</td><td class="num">${pct(d.approval_status_pct)}</td></tr>`
      + `<tr><td>Metadata completeness</td><td class="num">${pct(d.metadata_completeness_pct)}</td></tr>`
      + `</table>`;
    body.append(disc);
    // requirements register + core coverage
    const rc = el("div", "dash-card");
    const cov = reg.core_coverage;
    rc.style.cssText = `border-left:3px solid var(${cov.complete ? "--status-good" : "--status-warn"});margin-bottom:8px`;
    rc.innerHTML = `<b>Information requirements</b> <span class="meta">(${reg.total})</span>`
      + `<div class="meta">${cov.complete ? "✅ core documents on file (EIR, BEP, AIR)"
        : `⏳ missing core: ${cov.missing.map(esc).join(", ")}`}</div>`;
    const types = Object.entries(reg.by_type);
    if (types.length) {
      rc.innerHTML += `<table class="fin-table" style="width:100%;font-size:12px;margin-top:4px">`
        + `<tr><th style="text-align:left">Type</th><th class="num">Issued</th><th class="num">Draft</th></tr>`
        + types.map(([t, v]) => `<tr><td>${esc(t)}</td><td class="num">${v.issued}</td><td class="num">${v.draft}</td></tr>`).join("")
        + `</table>`;
    }
    body.append(rc);
    if (!st.total && !reg.total) {
      const none = el("div", "meta");
      none.textContent = "No containers or requirements yet — add them under Information Management.";
      body.append(none);
    }

    // standards-compliance experts — grounded findings against the project's own data
    const sx = el("div", "dash-card"); sx.style.marginTop = "8px";
    const stds: [string, string][] = [["iso19650", "ISO 19650"], ["cobie", "COBie"], ["ids", "IDS"], ["uniclass", "Uniclass"]];
    const picker = el("div"); picker.style.cssText = "display:flex;gap:6px;flex-wrap:wrap;align-items:center";
    picker.innerHTML = `<b>Compliance check</b>`;
    const out = el("div"); out.style.marginTop = "6px";
    const run = async (std: "iso19650" | "cobie" | "ids" | "uniclass") => {
      out.innerHTML = `<div class="meta">checking…</div>`;
      try {
        const r = await ctx.host.api.standardsCheck(pid, std);
        if (r.error) { out.innerHTML = `<div class="meta">${esc(r.error)}</div>`; return; }
        const icon = (l: string) => l === "ok" ? "✅" : l === "warn" ? "⚠️" : "❌";
        out.innerHTML = `<div class="meta" style="margin-bottom:4px"><b>${esc(r.label || std)}</b> — readiness ${r.score}%</div>`
          + `<ul style="margin:0 0 0 16px;font-size:12px">`
          + (r.findings || []).map((f) => `<li>${icon(f.level)} ${esc(f.text)} <span class="meta">(${esc(f.reference)})</span></li>`).join("")
          + `</ul>`;
      } catch (e) { out.innerHTML = `<div class="meta">failed: ${esc((e as Error).message)}</div>`; }
    };
    for (const [key, label] of stds) {
      const btn = el("button", "file-btn") as HTMLButtonElement; btn.textContent = label;
      btn.onclick = () => void run(key as "iso19650");
      picker.append(btn);
    }
    sx.append(picker, out); body.append(sx);
    void run("iso19650");

    // openBIM model quality — only meaningful with a model loaded; degrades to a hint on 404.
    const q = el("div", "dash-card"); q.style.marginTop = "8px";
    q.innerHTML = `<b>openBIM model quality</b> <span class="meta">scoring the loaded model…</span>`;
    body.append(q);
    try {
      const oq = await ctx.host.api.openbimQuality(pid, "fire_life_safety");
      const eh = oq.export_health, lo = oq.loin, bs = oq.bsdd;
      const grade = (g: string) => g === "pass" ? "✅" : g === "warn" ? "⚠️" : g === "fail" ? "❌" : "—";
      q.innerHTML = `<b>openBIM model quality</b>`
        + `<table class="fin-table" style="width:100%;font-size:12px;margin-top:4px">`
        + `<tr><td>LOIN — avg ${lo.avg_score}/${lo.max_score}, coordinated</td><td class="num">${lo.coordinated_pct ?? "—"}%</td></tr>`
        + (oq.ids ? `<tr><td>IDS compliance (fire &amp; life safety)</td><td class="num">${oq.ids.compliance_pct ?? "—"}%</td></tr>` : "")
        + `<tr><td>bSDD / classification coverage</td><td class="num">${bs.alignment_pct ?? "—"}%</td></tr>`
        + eh.checks.map((c) => `<tr><td>${grade(c.grade)} ${esc(c.label)}</td><td class="num">${c.pct ?? "—"}%</td></tr>`).join("")
        + `</table>`;
    } catch {
      q.innerHTML = `<b>openBIM model quality</b><div class="meta">Load a model (Model workspace) to `
        + `score LOIN, IDS compliance, export health and bSDD alignment.</div>`;
    }
  }

  // --- IDS Requirements: author buildingSMART IDS + EIR from templates --------------------------
export async function renderIds(ctx: PanelContext) {
    const root = ctx.root; root.innerHTML = "";
    const el = (t: string, c = "") => { const e = document.createElement(t); if (c) e.className = c; return e; };
    root.appendChild(ctx.bar("📋 IDS Requirements", () => { ctx.activeKey = null; void ctx.renderHome(); ctx.buildNav(); }));
    const intro = el("div", "meta"); intro.style.marginBottom = "8px";
    intro.textContent = "Author information requirements: pick a use case, download a standards-valid "
      + "buildingSMART IDS file to check delivered models against, plus an EIR document for the BIM "
      + "contract. Validate a model against an IDS from the Model workspace.";
    root.appendChild(intro);
    const body = el("div"); body.textContent = "loading templates…"; root.appendChild(body);
    try {
      const cat = await ctx.host.api.idsTemplates();
      body.innerHTML = "";
      const pick = el("select", "portal-filter") as HTMLSelectElement; pick.style.cssText = "margin:4px 0";
      pick.setAttribute("aria-label", "IDS use case");
      pick.innerHTML = cat.use_cases.map((u) => `<option value="${u.key}">${u.label}</option>`).join("");
      const detail = el("div"); detail.style.margin = "8px 0";
      const showDetail = () => {
        const uc = cat.use_cases.find((u) => u.key === pick.value);
        const groups = uc ? uc.groups : [];
        const els = cat.elements.filter((e) => groups.includes(e.key));
        detail.innerHTML = `<div class="meta">Requires data on: ${els.map((e) => e.label).join(", ")}</div>`;
        const tbl = el("table", "portal-table") as HTMLTableElement; tbl.style.cssText = "width:100%;font-size:11px;margin-top:4px";
        tbl.innerHTML = `<thead><tr><th scope="col" style="text-align:left">Element</th><th scope="col" style="text-align:left">Property set</th><th scope="col" style="text-align:left">Property</th></tr></thead><tbody>`
          + els.flatMap((e) => e.requirements.map((r) => `<tr><td>${e.ifc_class}</td><td>${r.pset}</td><td>${r.property}</td></tr>`)).join("") + `</tbody>`;
        detail.append(tbl);
      };
      pick.onchange = showDetail;
      const dlIds = el("button", "file-btn") as HTMLButtonElement; dlIds.textContent = "⬇ Download IDS";
      dlIds.style.marginRight = "8px";
      dlIds.onclick = () => void ctx.host.api.idsDownload("build", { use_case: pick.value }, `${pick.value}.ids`)
        .then(() => toast("IDS downloaded", "success")).catch((e) => toast((e as Error).message, "error"));
      const dlEir = el("button", "file-btn") as HTMLButtonElement; dlEir.textContent = "⬇ Download EIR (contract)";
      dlEir.onclick = () => void ctx.host.api.idsDownload("eir", { use_case: pick.value }, `EIR-${pick.value}.md`)
        .then(() => toast("EIR downloaded", "success")).catch((e) => toast((e as Error).message, "error"));
      body.append(pick, detail, dlIds, dlEir);

      // pin the selected IDS to the project → /validate runs against it with no re-upload
      const pid = ctx.host.projectId();
      if (pid) {
      const pinRow = el("div"); pinRow.style.cssText = "margin-top:10px;display:flex;gap:8px;align-items:center;flex-wrap:wrap";
      const pinStatus = el("span", "meta");
      const pinBtn = el("button", "file-btn") as HTMLButtonElement; pinBtn.textContent = "📌 Pin as project IDS";
      const unpinBtn = el("button", "tool-btn") as HTMLButtonElement; unpinBtn.textContent = "Unpin";
      const refreshPin = async () => {
        try {
          const s = await ctx.host.api.projectIdsStatus(pid);
          pinStatus.textContent = s.exists
            ? `✅ Project IDS pinned (${s.bytes} bytes) — validation runs against it automatically.`
            : "No project IDS pinned — validation uses the built-in QA specs unless one is uploaded.";
          unpinBtn.style.display = s.exists ? "" : "none";
        } catch { pinStatus.textContent = ""; }
      };
      pinBtn.onclick = async () => {
        try {
          const blob = await ctx.host.api.idsBuildBlob(pick.value);
          await ctx.host.api.pinProjectIds(pid, blob, `${pick.value}.ids`);
          toast("IDS pinned to project", "success"); await refreshPin();
        } catch (e) { toast((e as Error).message, "error"); }
      };
      unpinBtn.onclick = async () => {
        try { await ctx.host.api.unpinProjectIds(pid); toast("Project IDS unpinned", "info"); await refreshPin(); }
        catch (e) { toast((e as Error).message, "error"); }
      };
      pinRow.append(pinBtn, unpinBtn, pinStatus);
      body.append(pinRow);
      void refreshPin();
      }
      showDetail();
    } catch (e) { body.textContent = `failed: ${(e as Error).message}`; }
  }


// --- Model Analysis: read + audit the model (capabilities / query / LOD / envelope / MEP / naming) -
export async function renderModelAnalysis(ctx: PanelContext) {
    const root = ctx.root; root.innerHTML = "";
    const el = (t: string, c = "") => { const e = document.createElement(t); if (c) e.className = c; return e; };
    root.appendChild(ctx.bar("🔬 Model Analysis", () => { ctx.activeKey = null; void ctx.renderHome(); ctx.buildNav(); }));
    const pid = ctx.host.projectId();
    if (!pid) { root.innerHTML = noProjectHtml("Model Analysis"); return; }
    const intro = el("div", "meta"); intro.style.marginBottom = "8px";
    intro.textContent = "Read + audit the model: IFC capabilities, element query, achieved LOD, envelope "
        + "code compliance, MEP counts and naming. Model-reading sections need a published model.";
    root.appendChild(intro);

    const section = (title: string) => {
        const s = el("div", "dash-card"); s.style.marginBottom = "8px";
        const h = el("div"); h.style.cssText = "font-weight:600;margin-bottom:4px"; h.textContent = title;
        const b = el("div"); b.textContent = "loading…";
        s.append(h, b); root.appendChild(s); return b;
    };
    const table = (headers: string[], rows: (string | number)[][]) => {
        const t = el("table", "portal-table") as HTMLTableElement; t.style.cssText = "width:100%;font-size:12px";
        t.innerHTML = `<thead><tr>${headers.map((h) => `<th scope="col">${esc(h)}</th>`).join("")}</tr></thead><tbody>`
            + (rows.map((r) => `<tr>${r.map((c) => `<td>${esc(String(c))}</td>`).join("")}</tr>`).join("")
                || `<tr><td colspan="${headers.length}">—</td></tr>`) + "</tbody>";
        return t;
    };
    const fail = (b: HTMLElement) => (e: unknown) => { b.textContent = `failed: ${(e as Error).message}`; };

    const cap = section("🧩 IFC capabilities");
    void ctx.host.api.modelCapabilities(pid).then((c) => {
        cap.textContent = "";
        const m = el("div", "meta");
        const ifc5 = c.ifc5.status === "data"
            ? "IFC5/IFCX: <b>data reads now</b> (geometry rendering pending upstream)"
            : `IFC5/IFCX: ${esc(c.ifc5.status)}`;
        m.innerHTML = `Reads: <b>${esc(c.supported_read_schemas.join(" · "))}</b>. Loaded model: `
            + `<b>${esc(c.loaded_model.detected || "none")}</b>`
            + (c.loaded_model.detected && c.loaded_model.supported === false
                ? (c.loaded_model.data_readable ? ` (data-only — geometry pending)` : ` (not a supported read schema)`)
                : "")
            + `. ${ifc5}.`;
        cap.appendChild(m);
    }).catch(fail(cap));

    // Fast model summary (G3 — streaming STEP scan, no full parse)
    const sum = section("🧾 Model summary (fast scan)");
    void ctx.host.api.modelStepSummary(pid).then((s) => {
        sum.textContent = "";
        if (!s.ok) { sum.textContent = "no source model on this project"; return; }
        const m = el("div", "meta");
        m.innerHTML = `Schema <b>${esc(s.schema || "?")}</b> · <b>${s.total_entities ?? 0}</b> entities · `
            + `<b>${s.distinct_types ?? 0}</b> types`;
        sum.appendChild(m);
        if (s.histogram?.length) sum.appendChild(table(["IFC class", "Count"],
            s.histogram.slice(0, 12).map((h) => [h.ifc_class, h.count])));
    }).catch(fail(sum));

    // Export + columnar/interning efficiency (G1). Gated on a loaded model to avoid raw 409s.
    const ex = section("📤 Export & analytics");
    void ctx.host.api.modelColumnarStats(pid).then((st) => {
        ex.textContent = "";
        if (!st.model_loaded) { ex.textContent = "Publish a model to export or analyse it."; return; }
        const eff = el("div", "meta");
        eff.innerHTML = `Columnar interning: <b>${st.unique_strings ?? 0}</b> unique strings, `
            + `dedup <b>${st.dedup_ratio ?? "—"}×</b>`
            + (st.est_reduction_pct != null ? ` (~${st.est_reduction_pct}% smaller in RAM)` : "");
        const note = el("div", "meta"); note.style.marginTop = "6px";
        note.textContent = "Element table (CSV / JSON-LD / Parquet), the EAV parameter table (Parquet, "
            + "for DuckDB/pandas), or the geometry as glTF 2.0:";
        const row = el("div"); row.style.cssText = "display:flex;gap:8px;flex-wrap:wrap;margin-top:6px";
        const link = (label: string, href: string) => {
            const a = el("a", "btn") as HTMLAnchorElement;
            a.href = href; a.textContent = label; a.setAttribute("download", ""); a.target = "_blank"; return a;
        };
        row.append(
            link("CSV", ctx.host.api.modelExportUrl(pid, "csv")),
            link("JSON-LD", ctx.host.api.modelExportUrl(pid, "jsonld")),
            link("Parquet (elements)", ctx.host.api.modelExportUrl(pid, "parquet")),
            link("Parquet (params)", ctx.host.api.modelParamsParquetUrl(pid)),
            link("glTF (geometry)", ctx.host.api.modelGltfUrl(pid)),
        );
        ex.append(eff, note, row);
    }).catch(fail(ex));

    const q = section("🔎 Model query");
    void ctx.host.api.modelQueryViews(pid).then((v) => {
        q.textContent = "";
        const pick = el("select", "portal-filter") as HTMLSelectElement; pick.style.marginBottom = "6px";
        pick.setAttribute("aria-label", "Saved model query");
        pick.innerHTML = v.views.map((x) => `<option value="${esc(x.id)}">${esc(x.label)}</option>`).join("");
        const out = el("div");
        const run = () => { out.textContent = "…"; void ctx.host.api.modelQuery(pid, pick.value).then((r) => {
            out.innerHTML = ""; if (!r.model_scored) { out.textContent = "load a model to query it"; return; }
            out.appendChild(table(["Group", "Count"], r.rows.slice(0, 20).map((x) => [x.group, x.value]))); }).catch(fail(out)); };
        pick.onchange = run; q.append(pick, out); run();
    }).catch(fail(q));

    const lod = section("🎚 LOD coverage");
    void ctx.host.api.lodAssessment(pid).then((a) => {
        lod.textContent = "";
        if (!a.model_scored) { lod.textContent = "targets only — load a model to assess achieved LOD"; return; }
        lod.appendChild(table(["LOD band", "Elements"], Object.entries(a.distribution).map(([k, val]) => [k, val])));
    }).catch(fail(lod));

    const env = section("🧱 Envelope compliance (IECC)");
    void ctx.host.api.envelopeAudit(pid).then((a) => {
        env.textContent = "";
        const m = el("div", "meta");
        m.textContent = a.checked ? `${a.compliant}/${a.checked} assemblies compliant (${a.compliance_pct}%)`
            : "no envelope assemblies registered";
        env.appendChild(m);
        if (a.results.length) env.appendChild(table(["Assembly", "Type", "Result"],
            a.results.slice(0, 20).map((x) => [x.name, x.element_type,
                x.compliant == null ? "—" : (x.compliant ? "PASS" : "FAIL")])));
    }).catch(fail(env));

    const mep = section("🌀 MEP off the model");
    void ctx.host.api.mepModelExtract(pid).then((a) => {
        mep.textContent = "";
        if (!a.model_scored) { mep.textContent = "load a model to count MEP elements"; return; }
        const m = el("div", "meta"); m.textContent = `${a.mep_elements} MEP elements`;
        mep.append(m, table(["IFC class", "Type", "Count"], a.by_class.slice(0, 15).map((x) => [x.ifc_class, x.label, x.count])));
    }).catch(fail(mep));

    const nm = section("🔤 Naming compliance");
    void ctx.host.api.namingAudit(pid).then((a) => {
        nm.textContent = "";
        nm.appendChild(table(["Register", "Total", "Compliant", "%"], [
            ["Containers", a.containers.total, a.containers.compliant, a.containers.compliance_pct ?? "—"],
            ["Sheets", a.sheets.total, a.sheets.compliant, a.sheets.compliance_pct ?? "—"]]));
    }).catch(fail(nm));

    // Interop: inspect a VIM / G3D file (G2) — schema, buffers, geometry stats. Offline.
    const vim = section("🔗 Inspect VIM / G3D");
    vim.textContent = "";
    const vnote = el("div", "meta");
    vnote.textContent = "Open an Ara3D/VIM .vim or .g3d file to read its schema, buffers and geometry stats:";
    const vlab = el("label", "btn") as HTMLLabelElement; vlab.textContent = "📂 Choose .vim / .g3d";
    vlab.style.cssText = "cursor:pointer;margin-top:6px;display:inline-block";
    const vfile = el("input") as HTMLInputElement; vfile.type = "file"; vfile.accept = ".vim,.g3d";
    vfile.style.display = "none"; vlab.appendChild(vfile);
    const vout = el("div", "meta"); vout.style.marginTop = "6px";
    vfile.onchange = async () => {
        const f = vfile.files?.[0]; if (!f) return;
        vout.textContent = "inspecting…";
        try {
            const r = await ctx.host.api.inspectVim(f) as Record<string, unknown>;
            const geo = (r.geometry as Record<string, unknown>) || {};
            vout.innerHTML = `<b>${esc(String(r.format || "?"))}</b>`
                + (r.vim_version ? ` v${esc(String(r.vim_version))}` : "")
                + (r.schema ? ` · schema ${esc(String(r.schema))}` : "")
                + (Array.isArray(r.buffers) ? ` · ${(r.buffers as unknown[]).length} buffers` : "")
                + (geo.triangles != null ? ` · ${geo.vertices} verts / ${geo.triangles} tris` : "");
        } catch (e) { vout.textContent = `failed: ${(e as Error).message}`; }
    };
    vim.append(vnote, vlab, vout);
}

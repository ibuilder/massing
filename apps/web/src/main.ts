import "./style.css";
import { PortalUI } from "./portal/portal";   // eager: the default Construction/Developer workspace
import { ApiClient } from "./api/client";
import { toast, escapeHtml } from "./ui/feedback";
import { money } from "./ui/charts";
import { autoCheck, checkForUpdates, currentVersion } from "./ui/update";
import { maybeWelcome, showWelcome } from "./ui/onboarding";
import { mountChecklist, reopenChecklist } from "./ui/checklist";
import { FieldCapture } from "./field/field";
import { modalShell } from "./ui/modal";
import { showResult } from "./ui/result";
import { buildMenu, closeMenus } from "./ui/menus";
import { initCommandPalette, type Command } from "./ui/palette";
import { buildAuthControl } from "./account/accountUI";
import type { Settings, ViewerApp } from "./viewer/app";

// ---- shell DOM + shared state (no three/@thatopen here — those load lazily) --
const $ = <T extends HTMLElement>(id: string) => document.getElementById(id) as T;
const container = $("container");
const statusEl = $("status");
const toolbar = $("topbar");
const setStatus = (m: string) => (statusEl.textContent = m);
const notify = (m: string, kind: "info" | "success" | "error" = "info") => { setStatus(m); toast(m, kind); };
const api = new ApiClient();

let projectId: string | null = null;
let connected = false;
let projectName = "";

// ---- lazy viewer: the heavy 3D module loads on first Model-workspace use -----
let viewerApp: ViewerApp | null = null;
let viewerLoading: Promise<ViewerApp> | null = null;
async function ensureViewer(): Promise<ViewerApp> {
  if (viewerApp) return viewerApp;
  if (!viewerLoading) {
    viewerLoading = import("./viewer/app").then(({ initViewerApp }) => {
      viewerApp = initViewerApp({
        container, api, projectId, connected, projectName,
        setStatus, notify, getSettings: () => settings,
      });
      return viewerApp;
    });
  }
  return viewerLoading;
}
const withViewer = (fn: (v: ViewerApp) => void) => void ensureViewer().then(fn);

// ---- model file open: dialog first, heavy viewer in parallel -----------------
// The hidden <input>s live in index.html, so the native file dialog can open instantly on click
// (preserving the user-gesture) without waiting for the ~6 MB three/@thatopen viewer module. We
// warm the viewer in parallel and hand it the chosen File on `change`. Desktop (Tauri) uses its
// own native dialog via the viewer (the bundle is local, so init is fast).
const isTauriShell = () => "__TAURI_INTERNALS__" in window;
function openModelFile(kind: "ifc" | "frag" | "convert" | "ref") {
  // desktop (Tauri) uses native dialogs via the viewer for ifc/frag/convert; "ref" (mesh/point cloud)
  // always uses the plain <input> (works in the Tauri webview too) for the instant-dialog path.
  if (isTauriShell() && kind !== "ref") { withViewer((v) => v.triggerOpen(kind)); return; }
  void ensureViewer();                                   // warm the viewer while the user browses
  document.getElementById(`${kind}-input`)?.click();     // instant native file dialog
}
for (const kind of ["ifc", "frag", "convert", "ref"] as const) {
  document.getElementById(`${kind}-input`)?.addEventListener("change", (e) => {
    const inp = e.target as HTMLInputElement;
    const file = inp.files?.[0]; inp.value = "";
    if (!file) return;
    // .e57 has no in-browser parser: convert server-side to .xyz, then load as a point-cloud overlay
    if (kind === "ref" && file.name.toLowerCase().endsWith(".e57")) {
      void (async () => {
        try {
          const { toast } = await import("./ui/feedback");
          const st = await api.e57Status();
          if (!st.available) { toast(st.message, "info"); return; }
          toast("Converting E57 scan…", "info");
          const xyz = await api.convertE57(file);
          const xyzFile = new File([xyz], file.name.replace(/\.e57$/i, ".xyz"), { type: "text/plain" });
          const v = await ensureViewer(); await v.openFile("ref", xyzFile);
        } catch (err) {
          const { toast } = await import("./ui/feedback");
          toast(`E57 import failed: ${(err as Error).message}`, "error");
        }
      })();
      return;
    }
    // CityGML (.gml) has no in-browser parser: convert server-side to GeoJSON footprints, then load
    // as a GIS reference layer (city/site context — 3D City Database / Cesium tiles standard).
    if (kind === "ref" && /\.(gml|citygml)$/i.test(file.name)) {
      void (async () => {
        const { toast } = await import("./ui/feedback");
        try {
          toast("Converting CityGML…", "info");
          const fc = await api.convertCityGml(file);
          const gjFile = new File([JSON.stringify(fc)], file.name.replace(/\.(gml|citygml)$/i, ".geojson"),
            { type: "application/geo+json" });
          const v = await ensureViewer(); await v.openFile("ref", gjFile);
          toast(`Loaded ${fc.meta.buildings} building${fc.meta.buildings === 1 ? "" : "s"} from CityGML`, "success");
        } catch (err) { toast(`CityGML import failed: ${(err as Error).message}`, "error"); }
      })();
      return;
    }
    void ensureViewer().then((v) => v.openFile(kind, file));
  });
}

/**
 * Opt-in, offline-first basemap: prompts for a self-hosted XYZ tile-URL template + a focus lat/lon,
 * fetches a small tile grid and lays it on the ground as a reference overlay. Nothing loads unless the
 * operator supplies a tile server (honoring CLAUDE.md's "self-hosted tiles").
 */
async function addBasemapFlow() {
  const template = prompt(
    "Self-hosted tile URL template (XYZ), e.g. https://tiles.internal/{z}/{x}/{y}.png",
    "");
  if (!template || !/\{z\}.*\{x\}.*\{y\}/.test(template)) {
    if (template) { const { toast } = await import("./ui/feedback"); toast("template must contain {z}/{x}/{y}", "error"); }
    return;
  }
  const ll = prompt("Focus latitude, longitude (decimal degrees)", "40.7484, -73.9857");
  if (!ll) return;
  const [lat, lon] = ll.split(",").map((s) => parseFloat(s.trim()));
  if (!isFinite(lat) || !isFinite(lon)) { const { toast } = await import("./ui/feedback"); toast("invalid lat/lon", "error"); return; }
  const zoom = parseInt(prompt("Zoom level (1–22)", "17") || "17", 10);
  try {
    const { toast } = await import("./ui/feedback"); toast("Loading basemap tiles…", "info");
    const gis = await import("./viewer/gis");
    const res = await gis.loadBasemap({ template, lat, lon, zoom });
    const v = await ensureViewer(); v.addReferenceObject(res.object, res.info);
    toast(`basemap added — ${res.info}`, "success");
  } catch (e) {
    const { toast } = await import("./ui/feedback"); toast(`basemap failed: ${(e as Error).message}`, "error");
  }
}

// ---- Open / Save dropdown menus (extracted to ./ui/menus) -------------------
const dismissMenusIfOutside = (e: Event) => { if (!(e.target as HTMLElement).closest(".menu")) closeMenus(); };
document.addEventListener("pointerdown", dismissMenusIfOutside, true);
document.addEventListener("click", dismissMenusIfOutside, true);
window.addEventListener("blur", () => closeMenus());
document.addEventListener("keydown", (e) => { if (e.key === "Escape") closeMenus(); });
// pre-warm the viewer when the file menus open so triggerOpen/export resolve promptly
buildMenu("open-menu", "Open ▾", [
  { label: "Open Project (.mmproj)…", onClick: () => void openProjectBundle() },
  { label: "Open IFC…", onClick: () => openModelFile("ifc") },
  { label: "Open Fragments (.frag)…", onClick: () => openModelFile("frag") },
  { label: "Open mesh / point cloud / GIS…", onClick: () => openModelFile("ref") },
  { label: "Add basemap (self-hosted tiles)…", onClick: () => void addBasemapFlow() },
  { label: "Sample models", sep: true },
  { label: "School — Structural", onClick: () => withViewer((v) => void v.loadSample("/school_str.frag", "School (Structural)")) },
  { label: "School — Architectural", onClick: () => withViewer((v) => void v.loadSample("/school_arq.frag", "School (Architectural)")) },
  { label: "BasicHouse", onClick: () => withViewer((v) => void v.loadSample("/basichouse.frag", "BasicHouse")) },
  { label: "Import from Revit / CAD", sep: true },
  { label: "Free: export IFC from Revit (no bridge)…", onClick: () => showFreeImportHelp() },
  { label: "Revit (.rvt) — paid Autodesk bridge…", onClick: () => void importRvtFlow() },
  { label: "AutoCAD (.dwg) — paid bridge…", onClick: () => openModelFile("convert") },
  { label: "Navisworks (.nwc) — paid bridge…", onClick: () => openModelFile("convert") },
], () => void ensureViewer());
buildMenu("save-menu", "Save ▾", [
  { label: "Save Project (.mmproj)", onClick: () => saveProjectBundle() },
  { label: "Turnover", sep: true },
  { label: "Closeout package (.zip)", onClick: () => exportCloseoutPackage() },
  { label: "Geometry", sep: true },
  { label: "Export Fragments (.frag)", onClick: () => withViewer((v) => void v.exportFrag()) },
  { label: "Export source IFC (.ifc)", onClick: () => withViewer((v) => v.exportIfc()) },
], () => void ensureViewer());

/** Full turnover deliverable in one ZIP: as-built model + COBie/QTO/space workbooks + status report
 *  + closeout records (warranties, asset register, completion cert, punchlist). */
function exportCloseoutPackage() {
  if (!projectId) { toast("Open a project first", "info"); return; }
  window.open(api.url(`/projects/${projectId}/closeout/package.zip`), "_blank");
}

/** Report Center — a catalog of detailed reports, each exportable as PDF or Excel. */
async function openReportCenter() {
  if (!projectId) { toast("Open a project first", "info"); return; }
  const pid = projectId;
  let cat;
  try { cat = (await api.reports()).reports; } catch { toast("couldn't load reports (connect a project)", "error"); return; }
  const { card } = modalShell("Report Center", 420);
  card.append(Object.assign(document.createElement("div"), { className: "meta", textContent: "Detailed reports — download as PDF or Excel:" }));
  const groups = [...new Set(cat.map((r) => r.group))];
  for (const g of groups) {
    const h = document.createElement("div"); h.className = "section-title"; h.textContent = g; h.style.marginTop = "8px"; card.appendChild(h);
    for (const rep of cat.filter((r) => r.group === g)) {
      const row = document.createElement("div"); row.className = "layer-row";
      const name = document.createElement("span"); name.className = "name"; name.textContent = rep.name;
      const pdf = document.createElement("button"); pdf.className = "tool-btn"; pdf.textContent = "⬇ PDF";
      pdf.onclick = () => window.open(api.reportUrl(pid, rep.id, "pdf"), "_blank");
      const xls = document.createElement("button"); xls.className = "tool-btn"; xls.textContent = "⬇ Excel";
      xls.onclick = () => window.open(api.reportUrl(pid, rep.id, "xlsx"), "_blank");
      row.append(name, pdf, xls); card.appendChild(row);
    }
  }
  // interactive / parameterized analytics that aren't plain PDF reports
  const th = document.createElement("div"); th.className = "section-title"; th.textContent = "Project tools & analytics"; th.style.marginTop = "8px"; card.appendChild(th);
  const tool = (label: string, fn: () => void) => {
    const b = document.createElement("button"); b.className = "tool-btn"; b.textContent = label;
    b.style.cssText = "display:block;width:100%;text-align:left;margin:2px 0"; b.onclick = fn; card.appendChild(b);
  };
  const table = (body: HTMLElement, headers: string[], rows: (string | number)[][]) => {
    body.innerHTML += `<table class="fin-table" style="width:100%;font-size:12px"><tr>`
      + headers.map((h) => `<th style="text-align:left">${escapeHtml(h)}</th>`).join("") + "</tr>"
      + rows.map((r) => "<tr>" + r.map((c) => `<td>${escapeHtml(String(c))}</td>`).join("") + "</tr>").join("")
      + "</table>";
  };
  tool("🩺 Project health (executive rollup)", () => showResult("Project health", async (body) => {
    body.innerHTML = `<div class="meta">Loading…</div>`;
    try { const h = await api.projectHealth(pid);
      const dot = (s: string) => s === "red" ? "🔴" : s === "amber" ? "🟡" : s === "green" ? "🟢" : "⚪";
      body.innerHTML = `<div style="font-size:22px;font-weight:700">${dot(h.overall_status)} ${h.health_score ?? "—"}/100 · ${h.overall_status.toUpperCase()}</div>`
        + `<div class="meta">${h.open_items_total} open items · ${h.overdue_items_total} overdue across domains</div>`;
      table(body, ["Domain", "Status", "Summary", "Open", "Overdue"],
        h.domains.map((d) => [`${dot(d.status)} ${d.label}`, d.status.toUpperCase(), d.headline, d.open_count, d.overdue_count]));
      if (h.attention_items.length) {
        body.innerHTML += `<div class="section-title" style="margin-top:12px">Attention items</div>`;
        table(body, ["Status", "Domain", "Issue"], h.attention_items.map((a) => [`${dot(a.status)} ${a.status.toUpperCase()}`, a.domain, a.issue]));
      } }
    catch (e) { body.innerHTML = `<div class="meta">${escapeHtml((e as Error).message)}</div>`; }
  }));
  tool("🤖 Project assistant — ask about RFIs, budget, schedule…", () => showResult("Project assistant", (body) => {
    const inp = document.createElement("input"); inp.type = "text"; inp.placeholder = "e.g. how many open RFIs? what's the SPI?"; inp.style.cssText = "width:100%;padding:8px;box-sizing:border-box";
    const ans = document.createElement("div"); ans.style.cssText = "margin-top:10px;white-space:pre-wrap;line-height:1.5";
    const go = document.createElement("button"); go.className = "file-btn"; go.textContent = "Ask"; go.style.marginTop = "8px";
    const run = async () => { const q = inp.value.trim(); if (!q) return; ans.textContent = "Thinking…"; go.disabled = true;
      try { const r = await api.askProject(pid, q); ans.textContent = r.answer || ""; if (r.source !== "claude" && r.snapshot) ans.textContent = (r.answer || "") + "\n\n" + JSON.stringify(r.snapshot, null, 2); }
      catch (e) { ans.textContent = (e as Error).message; } finally { go.disabled = false; } };
    go.onclick = () => void run(); inp.addEventListener("keydown", (e) => { if (e.key === "Enter") void run(); });
    body.append(inp, go, ans); inp.focus();
  }));
  tool("💵 Certified payroll (WH-347)", () => showResult("Certified payroll (WH-347)", (body) => {
    body.innerHTML = `<div class="meta">Weekly Davis-Bacon certified payroll from timesheets × labor rates.</div>`;
    const wk = document.createElement("input"); wk.type = "date"; wk.style.cssText = "margin:8px 8px 8px 0;padding:6px";
    const open = document.createElement("button"); open.className = "file-btn"; open.textContent = "⬇ Open WH-347 PDF";
    open.onclick = () => window.open(api.wh347Url(pid, wk.value || undefined), "_blank");
    const sum = document.createElement("button"); sum.className = "file-btn"; sum.textContent = "Preview"; sum.style.marginLeft = "4px";
    const out = document.createElement("div"); out.style.marginTop = "10px";
    sum.onclick = async () => { try { const p = await api.payroll(pid, wk.value || undefined); out.innerHTML = `<div class="meta">Week ${p.week_ending} · ${p.worker_count} workers · ${p.total_hours} h · total ${money(p.total_gross)}</div>`;
      table(out, ["Worker", "Hours", "Gross"], p.rows.map((r: any) => [r.worker, r.total, money(r.gross)])); } catch (e) { out.textContent = (e as Error).message; } };
    body.append(wk, open, sum, out);
  }));
  tool("📐 Drawing-set register", () => showResult("Drawing-set register", async (body) => {
    body.innerHTML = `<div class="meta">Loading…</div>`;
    try {
      const d = await api.drawingSet(pid);
      body.innerHTML = `<div class="meta">${d.current_count} current · ${d.new_count} new · ${d.revised_count} revised · ${d.superseded_count} superseded · ${d.sheet_count} sheets</div>`;
      const xmit = document.createElement("a"); xmit.className = "file-btn"; xmit.textContent = "⬇ Transmittal (PDF)";
      xmit.href = api.drawingTransmittalUrl(pid); xmit.target = "_blank"; xmit.rel = "noopener"; xmit.style.margin = "6px 0";
      body.appendChild(xmit);
      table(body, ["Sheet", "Title", "Discipline", "Rev", "Status"], d.sheet_index.map((s: any) => [s.sheet_number, s.title ?? "", s.discipline ?? "", s.current_revision ?? "", s.change]));
    } catch (e) { body.innerHTML = `<div class="meta">${escapeHtml((e as Error).message)}</div>`; }
  }));
  tool("📋 ITB coverage (bid invitations)", () => showResult("ITB coverage", async (body) => {
    body.innerHTML = `<div class="meta">Loading…</div>`;
    try { const t = await api.itb(pid); body.innerHTML = `<div class="meta">${t.package_count} packages · ${t.total_responses}/${t.total_invited} responses · ${t.packages_without_bids} with no bids</div>`;
      table(body, ["Package", "Invited", "Responses", "Coverage"], t.rows.map((r: any) => [r.package, r.invited, r.responses, r.coverage])); }
    catch (e) { body.innerHTML = `<div class="meta">${escapeHtml((e as Error).message)}</div>`; }
  }));
  tool("💵 T&M / eTicket rollup", () => showResult("Time & Material rollup", async (body) => {
    body.innerHTML = `<div class="meta">Loading…</div>`;
    try { const s = await api.tmSummary(pid); body.innerHTML = `<div class="meta">${s.ticket_count} tickets · labor ${money(s.labor_total)} · material ${money(s.material_total)} · equipment ${money(s.equipment_total)} · <b>total ${money(s.grand_total)}</b> · unbilled ${money(s.unbilled_total)}</div>`;
      table(body, ["Ref", "Subject", "Total", "Status"], s.rows.map((r: any) => [r.ref ?? "", r.subject ?? "", money(r.total), r.status]));
      // T&M rolled up by the change event each ticket is linked to (field T&M -> CO -> billing)
      const bce = await api.tmByChangeEvent(pid);
      if (bce.groups.length) {
        body.insertAdjacentHTML("beforeend", `<div class="meta" style="margin-top:8px">By change event · linked ${money(bce.linked_total)} · unassigned ${money(bce.unassigned_total)}</div>`);
        table(body, ["Change event", "Subject", "Tickets", "Total"], bce.groups.map((g: any) => [g.ref ?? "—", g.subject ?? "", g.ticket_count, money(g.total)]));
      } }
    catch (e) { body.innerHTML = `<div class="meta">${escapeHtml((e as Error).message)}</div>`; }
  }));
  tool("▟ Site feasibility (zoning envelope)", () => showResult("Site feasibility / zoning envelope", async (body) => {
    body.innerHTML = `<div class="meta">Loading…</div>`;
    try { const f = await api.feasibility(pid);
      if (f.error) { body.innerHTML = `<div class="meta">${escapeHtml(f.error)} — add a <b>Zoning &amp; Site</b> record under Preconstruction.</div>`; return; }
      const sf = (v: number | null | undefined) => (typeof v === "number" ? `${Math.round(v).toLocaleString()} SF` : "—");
      const m = f.model;
      body.innerHTML = `<div class="meta">${escapeHtml(f.site ?? "Site")} · ${(f.site_area_sf ?? 0).toLocaleString()} SF (${f.site_area_acres ?? "—"} ac) · <b>allowed ${sf(f.allowed_gfa_sf)}</b> (binds on ${f.binding_constraint ?? "—"}) · ${f.max_floors ?? "—"} floors · yield ${f.unit_yield ?? "—"} units · parking ${f.parking_required ?? "—"}${m ? ` · model uses ${m.pct_of_allowed}% of allowed (${m.status})` : ""}</div>`;
      table(body, ["Constraint", "Limit GFA", "Basis"], (f.constraints ?? []).map((c) => [c.constraint, sf(c.limit_gfa_sf), c.basis]));
      if (m) table(body, ["Actual GFA", "FAR used", "% of allowed", "Headroom", "Status"], [[sf(m.actual_gfa_sf), String(m.far_used), `${m.pct_of_allowed}%`, sf(m.headroom_gfa_sf), m.status]]);
      if (f.warnings?.length) body.insertAdjacentHTML("beforeend", `<div class="meta" style="margin-top:8px">${f.warnings.map((w) => "• " + escapeHtml(w)).join("<br>")}</div>`); }
    catch (e) { body.innerHTML = `<div class="meta">${escapeHtml((e as Error).message)}</div>`; }
  }));
  tool("⤓ Import clash report (Solibri / Navisworks XLSX)", () => showResult("Import clash report", (body) => {
    body.innerHTML = `<div class="meta">Upload a Solibri or Navisworks clash/coordination report (.xlsx). Each row becomes a <b>coordination issue</b> (GUIDs anchor it on the model; issues round-trip to BCF). Columns are auto-detected.</div>`;
    const bar = document.createElement("div"); bar.style.cssText = "display:flex;gap:8px;margin-top:8px;align-items:center";
    const inp = document.createElement("input"); inp.type = "file"; inp.accept = ".xlsx"; inp.setAttribute("aria-label", "Clash report XLSX");
    const out = document.createElement("div"); out.style.marginTop = "8px";
    inp.onchange = async () => {
      const f = inp.files?.[0]; if (!f) return; out.innerHTML = `<div class="meta">Importing ${escapeHtml(f.name)}…</div>`;
      try { const r = await api.importClashXlsx(pid, f);
        out.innerHTML = `<div class="meta"><b>${r.imported}</b> coordination issue(s) imported from sheet “${escapeHtml(r.sheet)}” · columns: ${r.detected_columns.map(escapeHtml).join(", ") || "—"}</div>`; }
      catch (e) { out.innerHTML = `<div class="meta">${escapeHtml((e as Error).message)}</div>`; }
    };
    bar.append(inp); body.append(bar, out);
  }));
  tool("▟ Compare feasibility scenarios", () => showResult("Compare feasibility scenarios", async (body) => {
    body.innerHTML = `<div class="meta">Loading…</div>`;
    try { const c = await api.feasibilityCompare(pid);
      if (!c.count) { body.innerHTML = `<div class="meta">Add two or more <b>Zoning &amp; Site</b> records (one per scheme) to compare.</div>`; return; }
      const sf = (v: number | null | undefined) => (typeof v === "number" ? `${Math.round(v).toLocaleString()} SF` : "—");
      body.innerHTML = `<div class="meta"><b>${c.count} scheme(s)</b> ranked by buildable yield · best: ${escapeHtml(c.best_ref ?? "—")}</div>`;
      table(body, ["Scheme", "Site", "FAR", "Floors", "Allowed GFA", "Binds on", "Units", "Parking", "Δ units"],
        c.scenarios.map((s) => [s.ref ?? "", s.site ?? "", s.far ?? "—", s.max_floors ?? "—", sf(s.allowed_gfa_sf),
          s.binding_constraint ?? "—", s.unit_yield ?? "—", s.parking_required ?? "—",
          (s.delta_units ?? 0) === 0 ? "—" : String(s.delta_units)])); }
    catch (e) { body.innerHTML = `<div class="meta">${escapeHtml((e as Error).message)}</div>`; }
  }));
  tool("§ Spec submittal log (from specs)", () => showResult("Spec-driven submittal log", async (body) => {
    body.innerHTML = `<div class="meta">Loading…</div>`;
    try { const s = await api.specSubmittalLog(pid);
      body.innerHTML = `<div class="meta">${s.spec_count} spec sections · ${s.required_total} required submittals · ${s.logged_total} logged · <b>${s.missing_total} missing</b> · coverage ${s.coverage_pct ?? "—"}%</div>`;
      table(body, ["Section", "Title", "Required", "Logged", "Missing", "Responsible"], s.rows.map((r: any) => [r.section_number ?? "", r.title ?? "", r.required_count, r.logged_count, r.missing_count ? "⚠ " + r.missing_count : "0", r.responsible ?? ""])); }
    catch (e) { body.innerHTML = `<div class="meta">${escapeHtml((e as Error).message)}</div>`; }
  }));
  tool("✨ Extract submittals from a spec", () => showResult("Extract submittals from spec", (body) => {
    body.innerHTML = `<div class="meta">Paste a spec section (or its Part 1 “Submittals” article). Extraction uses AI when a key is set, else a built-in parser.</div>`;
    const ta = document.createElement("textarea"); ta.placeholder = "SECTION 03 30 00 — CAST-IN-PLACE CONCRETE\n1.3 SUBMITTALS\n  A. Product Data: for each mix design.\n  B. Shop Drawings: reinforcement placing drawings.\n  C. Samples: …";
    ta.setAttribute("aria-label", "Specification text"); ta.style.cssText = "width:100%;min-height:120px;margin-top:8px;font-family:monospace;font-size:12px";
    const bar = document.createElement("div"); bar.style.cssText = "display:flex;gap:8px;margin-top:8px;align-items:center";
    const ex = document.createElement("button"); ex.className = "file-btn"; ex.textContent = "Extract";
    const cr = document.createElement("button"); cr.className = "file-btn"; cr.textContent = "Extract + add to log";
    const out = document.createElement("div"); out.style.marginTop = "8px";
    const run = (create: boolean) => async () => {
      if (!ta.value.trim()) return; ex.disabled = cr.disabled = true; out.innerHTML = `<div class="meta">Extracting…</div>`;
      try { const r = await api.extractSubmittals(pid, ta.value, create);
        out.innerHTML = `<div class="meta">${r.items.length} submittal(s) · source: ${r.source}${r.created_submittals != null ? ` · ${r.created_submittals} added to the log` : ""}${r.message ? " · " + escapeHtml(r.message) : ""}</div>`;
        table(out, ["Section", "Submittal", "Type"], r.items.map((i) => [i.section_number ?? "", i.title, i.type])); }
      catch (e) { out.innerHTML = `<div class="meta">${escapeHtml((e as Error).message)}</div>`; }
      finally { ex.disabled = cr.disabled = false; }
    };
    ex.onclick = run(false); cr.onclick = run(true);
    bar.append(ex, cr); body.append(ta, bar, out);
  }));
  tool("🎯 Preconstruction alignment", () => showResult("Preconstruction alignment", async (body) => {
    body.innerHTML = `<div class="meta">Loading…</div>`;
    try { const a = await api.preconAlignment(pid);
      const varr = a.variance_to_budget == null ? "" : ` · ${a.variance_to_budget > 0 ? "OVER" : "under"} budget ${money(Math.abs(a.variance_to_budget))}`;
      body.innerHTML = `<div class="meta"><b>Alignment ${a.alignment_score ?? "—"}/100 · ${String(a.overall_status).toUpperCase()}</b> · latest ${money(a.latest_total)} (${a.latest_milestone ?? "—"})${varr} · VE accepted ${money(a.ve_accepted)} · ${a.open_decisions} open decisions · ${a.open_assumptions} open assumptions</div>`;
      table(body, ["Domain", "Status", "Detail"], a.domains.map((d: any) => [d.label, String(d.status).toUpperCase(), d.headline])); }
    catch (e) { body.innerHTML = `<div class="meta">${escapeHtml((e as Error).message)}</div>`; }
  }));
  tool("✔ Decision log", () => showResult("Decision log", async (body) => {
    body.innerHTML = `<div class="meta">Loading…</div>`;
    try { const s = await api.decisionLog(pid);
      body.innerHTML = `<div class="meta">${s.decision_count} decisions · ${s.open_count} open · ${s.disputed_count} disputed · cost exposure ${money(s.open_cost_exposure)} · ${s.open_schedule_exposure_days} sched days</div>`;
      table(body, ["Decision", "Category", "Alignment", "State", "Cost"], s.rows.map((r: any) => [r.subject ?? "", r.category ?? "", r.alignment ?? "", r.state ?? "", money(r.cost_impact)])); }
    catch (e) { body.innerHTML = `<div class="meta">${escapeHtml((e as Error).message)}</div>`; }
  }));
  tool("Σ Estimate continuity (preconstruction)", () => showResult("Estimate continuity", async (body) => {
    body.innerHTML = `<div class="meta">Loading…</div>`;
    try { const s = await api.estimateContinuity(pid);
      const drift = s.total_drift_pct != null ? ` (${s.total_drift_pct > 0 ? "+" : ""}${s.total_drift_pct}%)` : "";
      const varr = s.variance_to_budget == null ? "" : ` · <b>${s.over_budget ? "OVER" : "under"} budget ${money(Math.abs(s.variance_to_budget))}</b>`;
      body.innerHTML = `<div class="meta">${s.set_count} estimate sets · latest ${money(s.latest_total)} (${s.latest_milestone ?? "—"}${s.latest_psf ? `, ${money(s.latest_psf)}/SF` : ""}) · drift ${money(s.total_drift)}${drift} · budget ${s.budget != null ? money(s.budget) : "—"}${varr}</div>`;
      table(body, ["Milestone", "Total", "$/SF", "Δ vs prev", "Basis"], s.rows.map((r: any) => [r.milestone ?? "", money(r.total), r.psf != null ? money(r.psf) : "—", r.delta_total != null ? money(r.delta_total) : "—", r.basis ?? ""])); }
    catch (e) { body.innerHTML = `<div class="meta">${escapeHtml((e as Error).message)}</div>`; }
  }));
  tool("💲 Change-order log", () => showResult("Change-order log", async (body) => {
    body.innerHTML = `<div class="meta">Loading…</div>`;
    try { const s = await api.coLog(pid); body.innerHTML = `<div class="meta">${s.co_count} COs · total ${money(s.total_value)} · pending ${money(s.pending_value)} · approved ${money(s.approved_value)} · <b>executed ${money(s.executed_value)}</b> · ${s.total_schedule_days} sched days · CE ROM exposure ${money(s.change_event_rom_exposure)}</div>`;
      table(body, ["Ref", "Subject", "State", "Ball in court", "Reason", "Amount"], s.rows.map((r: any) => [r.ref ?? "", r.subject ?? "", r.state ?? "", r.ball_in_court ?? "", r.reason ?? "", money(r.amount)])); }
    catch (e) { body.innerHTML = `<div class="meta">${escapeHtml((e as Error).message)}</div>`; }
  }));
  tool("✅ Meeting action-item tracker", () => showResult("Meeting action-item tracker", async (body) => {
    body.innerHTML = `<div class="meta">Loading…</div>`;
    try { const s = await api.actionTracker(pid); body.innerHTML = `<div class="meta">${s.action_count} action items · ${s.open_count} open · ${s.overdue_count} overdue · <b>${s.completion_pct ?? "—"}% complete</b> · ${s.meeting_count} meetings · last ${s.last_meeting ?? "—"}</div>`;
      table(body, ["Ref", "Subject", "Assignee", "Priority", "Due", "State"], s.rows.map((r: any) => [r.ref ?? "", r.subject ?? "", r.assignee ?? "", r.priority ?? "", (r.overdue ? "OVERDUE " : "") + (r.due_date ?? ""), r.state ?? ""])); }
    catch (e) { body.innerHTML = `<div class="meta">${escapeHtml((e as Error).message)}</div>`; }
  }));
  tool("📑 Submittal register", () => showResult("Submittal register", async (body) => {
    body.innerHTML = `<div class="meta">Loading…</div>`;
    try { const s = await api.submittalRegister(pid); body.innerHTML = `<div class="meta">${s.submittal_count} submittals · ${s.open_count} open · ${s.overdue_count} overdue · avg turnaround ${s.avg_turnaround_days ?? "—"} d</div>`;
      table(body, ["Ref", "Spec", "Title", "Turn (d)", "Status"], s.rows.map((r: any) => [r.ref ?? "", r.spec_section ?? "", r.title ?? "", r.turnaround_days ?? "", (r.overdue ? "OVERDUE " : "") + r.status])); }
    catch (e) { body.innerHTML = `<div class="meta">${escapeHtml((e as Error).message)}</div>`; }
  }));
  tool("🏁 Closeout dashboard", () => showResult("Closeout dashboard", async (body) => {
    body.innerHTML = `<div class="meta">Loading…</div>`;
    try { const s = await api.closeoutSummary(pid); const p = s.punchlist, cx = s.commissioning, w = s.warranties, om = s.om_manuals;
      body.innerHTML = `<div class="meta">Punch <b>${p.complete_pct ?? "—"}% complete</b> (${p.open_count} open, ${p.overdue_count} overdue, ${money(p.open_cost)} open cost) · `
        + `Cx pass ${cx.pass_rate ?? "—"}% (${cx.cx_count} tests) · warranties ${w.active} active / ${w.expiring_soon} expiring / ${w.expired} expired · O&M ${om.accepted_pct ?? "—"}% accepted</div>`;
      table(body, ["Punch item", "Ball in court", "Trade", "Due", "Cost"], p.rows.map((r: any) => [r.description ?? "", r.ball_in_court ?? "", r.trade ?? "", (r.overdue ? "OVERDUE " : "") + (r.due_date ?? ""), money(r.cost)])); }
    catch (e) { body.innerHTML = `<div class="meta">${escapeHtml((e as Error).message)}</div>`; }
  }));
  tool("⚑ Safety dashboard (OSHA)", () => showResult("Safety dashboard (OSHA)", async (body) => {
    body.innerHTML = `<div class="meta">Loading…</div>`;
    try { const s = await api.safetySummary(pid); const i = s.incidents, o = s.observations, t = s.toolbox_talks;
      body.innerHTML = `<div class="meta">${i.incident_count} incidents · ${i.recordable_count} recordable · <b>TRIR ${i.trir ?? "—"}</b> · DART ${i.dart_rate ?? "—"} · LTIFR ${i.ltifr ?? "—"} · ${i.total_lost_days} lost days`
        + ` · ${o.observation_count} observations (safe:at-risk ${o.safe_to_at_risk ?? "—"}) · ${t.talk_count} toolbox talks`
        + `<br><span style="opacity:.7">on ${i.hours_worked.toLocaleString()} worker-hours${s.hours_estimated ? " (estimated from manpower)" : ""}</span></div>`;
      table(body, ["Incident", "Date", "OSHA class", "Recordable", "DART", "Lost d"], i.rows.map((r: any) => [r.subject ?? "", r.date ?? "", r.classification ?? "", r.recordable ? "yes" : "—", r.dart ? "yes" : "—", r.lost_days ?? ""])); }
    catch (e) { body.innerHTML = `<div class="meta">${escapeHtml((e as Error).message)}</div>`; }
  }));
  tool("☼ Field-log rollup", () => showResult("Field-log rollup", async (body) => {
    body.innerHTML = `<div class="meta">Loading…</div>`;
    try { const s = await api.fieldLogSummary(pid); body.innerHTML = `<div class="meta">${s.report_count} daily reports · coverage ${s.coverage_pct ?? "—"}% · total manpower ${s.total_manpower} · avg ${s.avg_manpower ?? "—"}/day · peak ${s.peak_manpower.count} (${s.peak_manpower.date ?? "—"}) · weather lost-days ${s.weather_lost_days} · ${s.delay_days} delay days</div>`;
      table(body, ["Date", "Weather", "Impact", "Manpower", "Delay"], s.rows.map((r: any) => [r.report_date ?? "", r.weather ?? "", r.weather_impact ?? "", r.manpower ?? "", r.has_delay ? "yes" : "—"])); }
    catch (e) { body.innerHTML = `<div class="meta">${escapeHtml((e as Error).message)}</div>`; }
  }));
  tool("❓ RFI register", () => showResult("RFI register", async (body) => {
    body.innerHTML = `<div class="meta">Loading…</div>`;
    try { const s = await api.rfiRegister(pid); body.innerHTML = `<div class="meta">${s.rfi_count} RFIs · ${s.open_count} open · ${s.overdue_count} overdue · avg response ${s.avg_response_days ?? "—"} d · ${s.cost_impacted_count} cost-impacting · ${s.schedule_impacted_count} schedule-impacting</div>`;
      table(body, ["Ref", "Subject", "Discipline", "Ball in court", "Due"], s.rows.map((r: any) => [r.ref ?? "", r.subject ?? "", r.discipline ?? "", r.ball_in_court ?? "", (r.overdue ? "OVERDUE " : "") + (r.due_date ?? "")])); }
    catch (e) { body.innerHTML = `<div class="meta">${escapeHtml((e as Error).message)}</div>`; }
  }));
  tool("🔍 Quality dashboard", () => showResult("Quality dashboard", async (body) => {
    body.innerHTML = `<div class="meta">Loading…</div>`;
    try { const q = await api.qualitySummary(pid); const i = q.inspections, n = q.ncrs, d = q.deficiencies;
      body.innerHTML = `<div class="meta">${i.total} inspections · pass rate <b>${i.pass_rate ?? "—"}%</b> · first-pass yield ${i.first_pass_yield ?? "—"}% · `
        + `NCRs ${n.open_count} open / ${n.overdue_count} overdue · deficiencies ${d.open_count} open / ${d.overdue_count} overdue</div>`;
      table(body, ["Deficiency", "Ball in court", "Trade", "Severity", "Due"],
        d.rows.map((r: any) => [r.description ?? "", r.ball_in_court ?? "", r.trade ?? "", r.severity ?? "", (r.overdue ? "OVERDUE " : "") + (r.due_date ?? "")])); }
    catch (e) { body.innerHTML = `<div class="meta">${escapeHtml((e as Error).message)}</div>`; }
  }));
  tool("✓ Field-verification coverage", () => showResult("Field-verification coverage", async (body) => {
    body.innerHTML = `<div class="meta">Loading…</div>`;
    try { const c = await api.verificationCoverage(pid); body.innerHTML =
      `<div style="font-size:22px;font-weight:700">${c.verified_pct}% verified · ${c.installed_pct}% installed</div>`
      + `<div class="meta">${c.verified} verified · ${c.installed} installed · ${c.deviations} deviations · of ${c.total_elements} elements</div>`; }
    catch (e) { body.innerHTML = `<div class="meta">${escapeHtml((e as Error).message)}</div>`; }
  }));
}

/**
 * The free, offline way to get a Revit/CAD model into the viewer — IFC is the source of truth, so
 * users don't need the paid Autodesk bridge: export IFC from Revit (built-in) or batch it with the
 * free, open-source pyRevit, then "Open IFC…". Surfaced so the mission's "free single-project"
 * promise is actually reachable from the UI, not just the paid path.
 */
function showFreeImportHelp() {
  const { card, msg } = modalShell("Import from Revit for free (no paid bridge)", 540);
  msg.innerHTML = `
    <p><b>IFC is the source of truth here</b> — you only need the paid Autodesk bridge if you want to
    drop a raw <code>.rvt</code> in directly. Three free ways in:</p>
    <ol style="margin:8px 0 8px 18px;line-height:1.5">
      <li><b>One‑click — the Massing Revit add‑in (pyRevit):</b> install our free
          <b>Massing for Revit</b> extension, then click <b>Massing ▸ Publish to Massing</b>. It exports
          IFC and publishes it here automatically — no manual export/upload. (Uses the REST API, so it
          needs a <b>Commercial</b> licence; see Settings ▸ Massing licence.)</li>
      <li><b>One model — Revit built‑in:</b> <i>File ▸ Export ▸ IFC</i>. Pick <b>IFC 4</b> (or IFC 2x3
          for older tools) and a coordinate base of <i>Project / Shared</i>, then <b>Open&nbsp;IFC…</b> here. Free on any plan.</li>
      <li><b>Many models / repeatable — pyRevit:</b> install <code>pyRevit</code> and batch‑export
          views/models to IFC, then <b>Open&nbsp;IFC…</b>.</li>
    </ol>
    <p class="meta">We pre‑convert IFC to Fragments on the server and stream it in. DWG/NWC: export to
    IFC from their host app the same way, or use the paid bridge.</p>`;
  card.appendChild(msg);
  const links = document.createElement("div");
  links.style.cssText = "display:flex;gap:10px;flex-wrap:wrap;margin-top:6px";
  for (const [t, href] of [
    ["Massing for Revit add-in", "https://github.com/ibuilder/massing/tree/main/integrations/pyrevit"],
    ["pyRevit (free)", "https://github.com/pyrevitlabs/pyRevit"],
    ["Revit IFC export docs", "https://help.autodesk.com/view/RVT/2024/ENU/?guid=GUID-6708CFD6-0AD7-4D85-8479-A2A8657C9181"],
  ] as const) {
    const a = document.createElement("a");
    a.href = href; a.target = "_blank"; a.rel = "noopener noreferrer";
    a.textContent = t; a.className = "btn-secondary"; a.style.textDecoration = "none";
    links.appendChild(a);
  }
  card.appendChild(links);
}

/** Paid Revit (.rvt) → IFC via the APS bridge. Off by default → routes to the free IFC-export help;
 *  when configured, warns about the per-conversion cost before picking a .rvt and converting. */
async function importRvtFlow() {
  if (!projectId) { toast("Open or create a project first", "info"); return; }
  let st;
  try { st = await api.rvtBridgeStatus(); } catch { toast("Couldn't reach the RVT bridge", "error"); return; }
  if (!st.enabled) { showFreeImportHelp(); return; }      // bridge off → the free path is the answer
  if (!confirm(`${st.cost_warning}\n\nPick a .rvt and convert it now?`)) return;
  const inp = document.createElement("input"); inp.type = "file"; inp.accept = ".rvt";
  inp.onchange = async () => {
    const f = inp.files?.[0]; if (!f || !projectId) return;
    toast(`Converting ${f.name} via Autodesk APS…`, "info");
    try {
      const r = await api.importRvt(projectId, f, true);
      toast(`Converted to IFC (${Math.round(r.size / 1024)} KB) — ${r.publish === "running" ? "publishing…" : "done"}`, "info");
    } catch (e) { toast(`RVT import: ${(e as Error).message}`, "error"); }
  };
  inp.click();
}

/** Save the whole project (geometry + all data + blobs) as a portable .mmproj bundle. */
function saveProjectBundle() {
  if (!projectId) { toast("Open a project first", "info"); return; }
  const a = document.createElement("a");
  a.href = api.bundleUrl(projectId); a.download = `${projectName || "project"}.mmproj`;
  document.body.appendChild(a); a.click(); a.remove();
  toast("Saving project bundle…", "info");
}

/** Open a .mmproj bundle as a new project, then switch to it. */
function openProjectBundle() {
  const inp = document.createElement("input");
  inp.type = "file"; inp.accept = ".mmproj,.zip,application/zip";
  inp.onchange = async () => {
    const f = inp.files?.[0]; if (!f) return;
    toast(`Opening ${f.name}…`, "info");
    try {
      const p = await api.importBundle(f);
      toast(`Opened "${p.name}"`, "info");
      window.location.search = `?project=${p.id}`;
    } catch { toast("Couldn't open that bundle (.mmproj expected)", "error"); }
  };
  inp.click();
}

// ---- workspaces + left icon rail --------------------------------------------
const appEl = document.getElementById("app")!;
// crisp inline SVG icons (currentColor) — replace the old cryptic ⌗/≣ glyphs
const RAIL_ICONS: Record<string, string> = {
  tree: `<svg viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.4" stroke-linecap="round" stroke-linejoin="round"><rect x="5.5" y="1.5" width="5" height="3.4" rx=".8"/><rect x="1.5" y="11.1" width="4.4" height="3.4" rx=".8"/><rect x="10.1" y="11.1" width="4.4" height="3.4" rx=".8"/><path d="M8 4.9v3.2M3.7 11.1V8.1h8.6v3"/></svg>`,
  layers: `<svg viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.4" stroke-linejoin="round"><path d="M8 1.6 14.6 5 8 8.4 1.4 5 8 1.6Z"/><path d="m1.4 8 6.6 3.4L14.6 8"/><path d="m1.4 11 6.6 3.4L14.6 11" opacity=".55"/></svg>`,
  issues: `<svg viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.4" stroke-linecap="round" stroke-linejoin="round"><path d="M3.6 14.6V1.8"/><path d="M3.6 2.6h8.4l-2 3 2 3H3.6"/></svg>`,
  tools: `<svg viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.3" stroke-linecap="round" stroke-linejoin="round"><circle cx="8" cy="8" r="2.2"/><path d="M8 1.4v2.1M8 12.5v2.1M1.4 8h2.1M12.5 8h2.1M3.3 3.3l1.5 1.5M11.2 11.2l1.5 1.5M3.3 12.7l1.5-1.5M11.2 4.8l1.5-1.5"/></svg>`,
};
const RAIL_ITEMS: { key: string; label: string; title: string }[] = [
  { key: "tree", label: "Tree", title: "Model tree" },
  { key: "layers", label: "Layers", title: "Layers" },
  { key: "issues", label: "Issues", title: "Issues / RFIs" },
  { key: "tools", label: "Tools", title: "Tools & analysis" },
];
const railEl = $("rail");
function showRail(key: string) {
  appEl.classList.remove("rail-collapsed");
  document.querySelectorAll(".rail-btn").forEach((b) => b.classList.toggle("active", (b as HTMLElement).dataset.rail === key));
  document.querySelectorAll(".rpanel").forEach((p) => p.classList.remove("active"));
  $(`panel-${key}`).classList.add("active");
}
for (const it of RAIL_ITEMS) {
  const b = document.createElement("button");
  b.className = "rail-btn"; b.dataset.rail = it.key;
  b.innerHTML = `<span class="rail-ic">${RAIL_ICONS[it.key]}</span><span class="rail-lbl">${it.label}</span>`;
  b.title = it.title; b.setAttribute("aria-label", it.title);
  b.onclick = () => {
    const isActive = b.classList.contains("active") && !appEl.classList.contains("rail-collapsed");
    if (isActive) appEl.classList.add("rail-collapsed");
    else showRail(it.key);
  };
  railEl.appendChild(b);
}
// expand / collapse the rail to show labels (VS Code activity-bar style), persisted
const railExpand = document.createElement("button");
railExpand.className = "rail-btn rail-expand";
const syncExpand = () => {
  const on = appEl.classList.contains("rail-labeled");
  railExpand.innerHTML = `<span class="rail-ic">${on ? "‹" : "›"}</span><span class="rail-lbl">Collapse</span>`;
  railExpand.title = on ? "Collapse the rail" : "Expand the rail (show labels)";
  railExpand.setAttribute("aria-label", railExpand.title);
  railExpand.setAttribute("aria-expanded", String(on));
};
railExpand.onclick = () => {
  appEl.classList.toggle("rail-labeled");
  localStorage.setItem("rail-labeled", appEl.classList.contains("rail-labeled") ? "1" : "0");
  syncExpand();
};
if (localStorage.getItem("rail-labeled") === "1") appEl.classList.add("rail-labeled");
syncExpand();
railEl.appendChild(railExpand);

const WORKSPACES: { key: string; label: string }[] = [
  { key: "model", label: "Model" }, { key: "drawings", label: "Drawings" },
  { key: "studio", label: "Studio" },
  { key: "design", label: "Design" },              // architect / engineer — the design-phase seat
  { key: "construction", label: "Construction" },
  { key: "developer", label: "Developer" }, { key: "finance", label: "Finance" },
];
let studioUI: import("./studio/nodeEditor").NodeEditor | null = null;
async function openStudioTab() {
  if (!studioUI) {
    const { NodeEditor } = await import("./studio/nodeEditor");   // lazy — only when Studio is opened
    studioUI = new NodeEditor($("panel-studio"), api, setStatus);
  }
  await studioUI.mount();
}
let currentWs = "model";
function setWorkspace(key: string) {
  currentWs = key;
  document.querySelectorAll(".ws-btn").forEach((b) => {
    const on = (b as HTMLElement).dataset.ws === key;
    b.classList.toggle("active", on);
    b.setAttribute("aria-selected", String(on));
  });
  document.querySelectorAll(".workspace").forEach((w) => w.classList.toggle("active", w.id === `ws-${key}`));
  if (key === "drawings") openDrawingsTab();
  if (key === "studio") void openStudioTab();
  if (key === "design") openDesignTab();
  if (key === "construction") openPortalTab();
  if (key === "developer") openDeveloperTab();
  if (key === "finance") openProformaTab();
  if (key === "model") void ensureViewer().then((v) => v.onModelShown());   // lazy-load the 3D app
  localStorage.setItem("workspace", key);
}
// deep-link from a tool section to the workspace that owns the full records (e.g. Cost → Construction)
window.addEventListener("aec:workspace", (e) => {
  const key = (e as CustomEvent<string>).detail;
  if (WORKSPACES.some((w) => w.key === key)) setWorkspace(key);
});
const wsEl = $("workspaces");
for (const w of WORKSPACES) {
  const b = document.createElement("button");
  b.className = "ws-btn"; b.dataset.ws = w.key; b.textContent = w.label;
  b.setAttribute("role", "tab"); b.setAttribute("aria-selected", "false");
  b.onclick = () => setWorkspace(w.key);
  wsEl.appendChild(b);
}

document.querySelectorAll<HTMLButtonElement>(".fintab").forEach((t) => {
  t.onclick = () => {
    document.querySelectorAll(".fintab").forEach((x) => { x.classList.remove("active"); x.setAttribute("aria-selected", "false"); });
    document.querySelectorAll("#ws-finance .fullpanel").forEach((p) => p.classList.remove("active"));
    t.classList.add("active"); t.setAttribute("aria-selected", "true");
    $(`panel-${t.dataset.fin}`).classList.add("active");
    if (t.dataset.fin === "proforma") openProformaTab();
    if (t.dataset.fin === "portfolio") openPortfolioTab();
  };
});

// ---- role-based navigation --------------------------------------------------
interface PersonaCfg { ws: string[] | null; rail: string[] | null; home: string; }
const PERSONAS: Record<string, PersonaCfg> = {
  all:           { ws: null, rail: null, home: "model" },
  developer:     { ws: ["developer", "finance", "model", "studio", "drawings", "design", "construction"], rail: ["issues", "tools", "tree"], home: "developer" },
  gc:            { ws: ["construction", "model", "drawings", "design", "finance"], rail: ["tree", "layers", "issues", "tools"], home: "construction" },
  // R1 — two GC flavors: the super lives in the field (model + construction), the PM in the office
  // (construction + finance). Same construction home; the portal nav opens each role's sections first.
  superintendent:  { ws: ["construction", "model", "drawings"], rail: ["issues", "tree", "layers", "tools"], home: "construction" },
  project_manager: { ws: ["construction", "design", "finance", "drawings", "model"], rail: ["tree", "issues", "layers", "tools"], home: "construction" },
  // architect/engineer home into the Design workspace (their design-phase seat); model + studio stay
  // one click away for authoring and the coordination/model-health tools.
  architect:     { ws: ["design", "model", "studio", "drawings", "construction"], rail: ["tree", "layers", "issues", "tools"], home: "design" },
  engineer:      { ws: ["design", "model", "studio", "drawings"], rail: ["tree", "layers", "tools", "issues"], home: "design" },
  subcontractor: { ws: ["construction", "model", "drawings"], rail: ["issues", "tools"], home: "construction" },
};
const personaSel = document.getElementById("persona") as HTMLSelectElement;
function applyPersona(p: string, goHome = false) {
  const cfg = PERSONAS[p] ?? PERSONAS.all;
  document.querySelectorAll<HTMLButtonElement>(".ws-btn").forEach((b) => { b.hidden = !!cfg.ws && !cfg.ws.includes(b.dataset.ws!); });
  document.querySelectorAll<HTMLButtonElement>(".rail-btn").forEach((b) => { b.hidden = !!cfg.rail && !cfg.rail.includes(b.dataset.rail!); });
  const allowedRail = cfg.rail ?? RAIL_ITEMS.map((r) => r.key);
  const activeRail = document.querySelector(".rail-btn.active") as HTMLElement | null;
  if (!activeRail || !allowedRail.includes(activeRail.dataset.rail!)) showRail(allowedRail[0]);
  if (goHome || (cfg.ws && !cfg.ws.includes(currentWs))) setWorkspace(cfg.home);
  localStorage.setItem("persona", p);
  document.body.dataset.persona = p;
  window.dispatchEvent(new CustomEvent("aec:persona", { detail: p }));   // reorder the tools panel
}
personaSel.value = localStorage.getItem("persona") || "all";
// a manual choice sticks — it stops membership auto-selecting a persona on the next project open
personaSel.onchange = () => { localStorage.setItem("persona-manual", "1"); applyPersona(personaSel.value, true); };

// ---- rail collapse + drag-to-resize (persisted) -----------------------------
function toggleRail() { appEl.classList.toggle("rail-collapsed"); }
(document.getElementById("rail-toggle") as HTMLButtonElement).onclick = toggleRail;
const savedW = localStorage.getItem("rail-w");
if (savedW) appEl.style.setProperty("--rail-w", savedW);
const resizer = document.createElement("div");
resizer.id = "rail-resize"; resizer.title = "Drag to resize";
$("rail-panel").appendChild(resizer);
resizer.addEventListener("pointerdown", (e) => {
  e.preventDefault();
  resizer.setPointerCapture(e.pointerId);
  const move = (ev: PointerEvent) => {
    const w = Math.min(Math.max(ev.clientX - 46, 200), 560);
    appEl.style.setProperty("--rail-w", `${w}px`);
  };
  const up = () => {
    resizer.removeEventListener("pointermove", move);
    resizer.removeEventListener("pointerup", up);
    localStorage.setItem("rail-w", getComputedStyle(appEl).getPropertyValue("--rail-w").trim());
  };
  resizer.addEventListener("pointermove", move);
  resizer.addEventListener("pointerup", up);
});

// ---- bottom settings bar ----------------------------------------------------
const SETTINGS_DEFAULTS: Settings = {
  theme: "dark", grid: true, projection: "Perspective", background: "dark",
  zoomCursor: true, nav: "orbit", units: "m", section: false, snap: 0,
};
const settings: Settings = { ...SETTINGS_DEFAULTS, ...JSON.parse(localStorage.getItem("aec-settings") || "{}") };
let savedTimer: number | undefined;
function flashSaved() {
  const el = document.getElementById("sb-saved"); if (!el) return;
  el.classList.add("show"); clearTimeout(savedTimer);
  savedTimer = window.setTimeout(() => el.classList.remove("show"), 1200);
}
function applyTheme() { document.documentElement.dataset.theme = settings.theme === "light" ? "light" : ""; }
function onSettingsChanged() { applyTheme(); if (viewerApp) viewerApp.applySettings(); localStorage.setItem("aec-settings", JSON.stringify(settings)); flashSaved(); }

function buildStatusBar() {
  const bar = $("statusbar");
  const sep = () => { const d = document.createElement("span"); d.className = "sb-sep"; return d; };
  const toggle = (label: string, key: "grid" | "section" | "zoomCursor") => {
    const b = document.createElement("button"); b.className = "sb-toggle"; b.textContent = label;
    const sync = () => b.classList.toggle("on", !!settings[key]);
    b.onclick = () => { settings[key] = !settings[key]; sync(); onSettingsChanged(); };
    sync(); return b;
  };
  const select = (label: string, key: "projection" | "theme" | "background" | "nav" | "units", opts: [string, string][]) => {
    const wrap = document.createElement("span"); wrap.className = "sb-group";
    const l = document.createElement("label"); l.textContent = label;
    const s = document.createElement("select"); s.className = "sb-sel";
    for (const [v, t] of opts) { const o = document.createElement("option"); o.value = v; o.textContent = t; s.appendChild(o); }
    s.value = String(settings[key]);
    s.onchange = () => { (settings[key] as string) = s.value; onSettingsChanged(); };
    wrap.append(l, s); return wrap;
  };
  const fit = document.createElement("button"); fit.className = "sb-toggle"; fit.textContent = "⤢ Fit";
  fit.title = "Fit to view (F)"; fit.onclick = () => withViewer((v) => void v.fitToModels());
  bar.append(
    fit, sep(),
    toggle("Grid", "grid"), toggle("Section", "section"),
    select("View", "projection", [["Perspective", "Perspective"], ["Orthographic", "Ortho"]]), sep(),
    select("Theme", "theme", [["dark", "Dark"], ["light", "Light"]]),
    select("Background", "background", [["dark", "Dark"], ["light", "Light"], ["none", "None"]]), sep(),
    select("Nav", "nav", [["orbit", "Orbit"], ["pan", "Pan (Revit)"], ["cad", "CAD (Navis)"]]),
    toggle("Zoom to cursor", "zoomCursor"),
    select("Units", "units", [["m", "m"], ["cm", "cm"], ["mm", "mm"], ["ft", "ft-in"]]), sep(),
  );
  // grid-snap increment for authoring placement (number, so not the string select helper)
  const snapWrap = document.createElement("span"); snapWrap.className = "sb-group";
  const snapL = document.createElement("label"); snapL.textContent = "Snap";
  const snapSel = document.createElement("select"); snapSel.className = "sb-sel";
  for (const [v, t] of [["0", "off"], ["0.1", "0.1m"], ["0.5", "0.5m"], ["1", "1m"]]) {
    const o = document.createElement("option"); o.value = v; o.textContent = t; snapSel.appendChild(o);
  }
  snapSel.value = String(settings.snap);
  snapSel.onchange = () => { settings.snap = Number(snapSel.value); onSettingsChanged(); };
  snapWrap.append(snapL, snapSel);
  bar.append(snapWrap, sep());
  const coords = document.createElement("span"); coords.id = "sb-coords"; coords.textContent = "—";
  const saved = document.createElement("span"); saved.id = "sb-saved"; saved.textContent = "✓ saved";
  bar.append(coords, saved);
}

showRail("tree");
buildStatusBar();
applyTheme();

// ---- portal / proforma (light — no 3D) --------------------------------------
// Two portals share one host config: the GC build portal (construction modules) and the developer
// portal (real-estate registers). Same config-driven engine, different workspace filter.
const portalHost = {
  api,
  projectId: () => projectId,
  anchorPoint: () => viewerApp?.anchorPoint() ?? null,
  selectedGuid: () => viewerApp?.selectedGuidValue() ?? null,
  onSelectGuids: (guids: string[]) => { if (guids[0]) { setWorkspace("model"); withViewer((v) => void v.selectByGuid(guids[0], true)); } },
  onPinsChanged: () => { if (viewerApp) void viewerApp.reloadModelPins(); },
  setStatus,
};
const portal = new PortalUI($("panel-portal"), portalHost);
portal.setWorkspace("construction");
let portalReady = false;
function openPortalTab() { if (portalReady) return; portalReady = true; void portal.init(); }

const developerPortal = new PortalUI($("panel-portal-dev"), portalHost);
developerPortal.setWorkspace("developer");
let developerReady = false;
function openDeveloperTab() { if (developerReady) return; developerReady = true; void developerPortal.init(); }

// Design workspace (architect / engineer) — same config-driven engine, "design" workspace filter.
const designPortal = new PortalUI($("panel-portal-design"), portalHost);
designPortal.setWorkspace("design");
let designReady = false;
function openDesignTab() { if (designReady) return; designReady = true; void designPortal.init(); }

// Developer portal's "Underwriting" shortcut → the proforma workspace
window.addEventListener("aec:goto-workspace", (e) => setWorkspace((e as CustomEvent).detail as string));

// Proforma (Finance) + Drawings are secondary workspaces — code-split so their code (and deps) load
// on first open instead of bloating the initial shell. Portal (default Construction) stays eager.
let proforma: import("./proforma/proforma").ProformaUI | null = null;
function openProformaTab() {
  if (proforma) return;
  void import("./proforma/proforma").then(({ ProformaUI }) => {
    proforma = new ProformaUI($("panel-proforma"), api, setStatus, () => projectId);
    void proforma.init();
  });
}

let drawings: import("./drawings/drawings").DrawingsUI | null = null;
function openDrawingsTab() {
  void import("./drawings/drawings").then(({ DrawingsUI }) => {
    if (!drawings) drawings = new DrawingsUI($("panel-drawings"), { api, projectId: () => projectId, setStatus });
    void drawings.open();   // re-loads the register each open (cheap)
  });
}

async function openPortfolioTab() {
  const panel = $("panel-portfolio");
  panel.innerHTML = `<div class="section-title">Portfolio roll-up</div><div class="meta">loading…</div>`;
  let p;
  try { p = await api.portfolio(); }
  catch { panel.innerHTML = `<div class="meta">portfolio unavailable (API offline)</div>`; return; }
  const t = p.totals;
  const m = (v: number | null) => (v == null ? "—" : "$" + Math.round(v).toLocaleString());
  const pc = (v: number | null) => (v == null ? "—" : (v * 100).toFixed(1) + "%");
  const kpis: [string, string][] = [
    ["Deals", String(p.deal_count)], ["Total cap", m(t.total_capitalization)],
    ["Total equity", m(t.total_equity)], ["Blended LTC", pc(t.blended_ltc)],
    ["Portfolio IRR", pc(t.portfolio_irr)], ["Portfolio EM", `${t.portfolio_equity_multiple ?? "—"}×`],
  ];
  const rows = p.deals.map((d) =>
    `<tr><th style="text-align:left">${d.name}</th><td>${m(d.total_uses)}</td>` +
    `<td>${m(d.equity)}</td><td>${pc(d.equity_irr)}</td><td>${d.equity_multiple ?? "—"}×</td></tr>`).join("");
  panel.innerHTML =
    `<div class="section-title">Portfolio roll-up — ${p.deal_count} deal(s)</div>` +
    `<div class="kpi-grid">` +
    kpis.map(([l, v]) => `<div class="kpi"><div class="kpi-v" style="font-size:15px">${v}</div><div class="kpi-l">${l}</div></div>`).join("") +
    `</div>` +
    (p.deal_count ? `<table class="sens-table"><tr><th>Deal</th><th>Cap</th><th>Equity</th><th>IRR</th><th>EM</th></tr>${rows}</table>`
                  : `<div class="meta" style="margin-top:8px">No solved scenarios yet — build one in the Proforma tab and it rolls up here.</div>`);

  // construction program roll-up (owner view): cost over/under + risk + safety across projects
  try {
    const cp = await api.constructionPortfolio();
    if (cp.project_count) {
      const ct = cp.totals;
      const prows = cp.projects.map((r) =>
        `<tr><th style="text-align:left">${r.name}</th><td style="color:${r.over_budget ? "#e2554a" : "var(--text)"}">${m(r.projected_over_under)}</td>` +
        `<td>${r.open_risks} (${m(r.risk_exposure)})</td><td>${r.recordables}</td><td>${r.open_rfis}</td></tr>`).join("");
      panel.insertAdjacentHTML("beforeend",
        `<div class="section-title" style="margin-top:14px">Construction program — ${cp.project_count} project(s)`
        + (ct.over_budget_count ? ` · <span style="color:#e2554a">${ct.over_budget_count} over budget</span>` : "") + `</div>`
        + `<table class="sens-table"><tr><th>Project</th><th>Over/Under</th><th>Open risks ($)</th><th>Recordables</th><th>Open RFIs</th></tr>${prows}`
        + `<tr style="font-weight:700"><th style="text-align:left">Total</th><td>${m(ct.projected_over_under)}</td><td>${ct.open_risks} (${m(ct.risk_exposure)})</td><td>${ct.recordables}</td><td>${ct.open_rfis}</td></tr></table>`);
    }
  } catch { /* program roll-up optional */ }
}

// loadable geometry per project -> the type tag shown in the picker. RVT/DWG/NWC origin isn't
// tracked (those need the paid Autodesk bridge and convert to IFC/frag first), so a project is
// only ever ".frag" (published tile), ".ifc" (source IFC on disk), or has no model yet.
const MODEL_TAG: Record<string, string> = { frag: " (.frag)", ifc: " (.ifc)" };
/** Onboarding quick-start actions, shared by the welcome modal and the empty state. */
function onboardCtx() {
  return {
    // the demo serves read-only sample data, so create/generate (which persist) stay disabled there
    connected: connected && !import.meta.env.VITE_PAGES,
    newProject: () => void newProject(),
    openSample: () => { setWorkspace("model"); withViewer((v) => void v.loadSample("/basichouse.frag", "BasicHouse")); },
    generate: () => {
      setWorkspace("finance");
      // let the proforma render, then reveal the "Generate from zoning" panel
      setTimeout(() => document.getElementById("pf-massing")?.scrollIntoView({ behavior: "smooth", block: "center" }), 400);
    },
  };
}

/** Create a blank project (no IFC) and switch to it — GC portal + proforma work immediately. */
async function newProject() {
  const name = prompt("New project name:");
  if (!name || !name.trim()) return;
  try { const p = await api.createProject(name.trim()); window.location.search = `?project=${p.id}`; }
  catch { toast("Couldn't create project (sign in as an editor?)", "error"); }
}

function buildProjectPicker(projects: { id: string; name: string; model_kind?: string | null }[]) {
  if (projects.length) {
    const sel = document.createElement("select");
    sel.className = "tool-btn"; sel.title = "Project"; sel.dataset.tour = "projects";
    for (const p of projects) {
      const o = document.createElement("option");
      o.value = p.id;
      o.textContent = p.name + (p.model_kind ? MODEL_TAG[p.model_kind] ?? "" : " (no model)");
      o.selected = p.id === projectId;
      sel.appendChild(o);
    }
    sel.onchange = () => { window.location.search = `?project=${sel.value}`; };
    toolbar.insertBefore(sel, statusEl);
  }
  // always available — create a blank project (no model required) from a cold start
  const add = document.createElement("button");
  add.className = "tool-btn"; add.style.marginLeft = "4px"; add.textContent = "＋ New"; add.title = "New project (no IFC needed)";
  add.onclick = () => void newProject();
  if (!projects.length) add.dataset.tour = "projects";   // anchor the tour here when there's no picker yet
  toolbar.insertBefore(add, statusEl);
  if (!projects.length) return;   // nothing more to render (no current project to delete)
  // delete the current project (rows + geometry); confirm, then reload to the next one
  const del = document.createElement("button");
  del.className = "tool-btn"; del.style.marginLeft = "4px"; del.textContent = "🗑"; del.title = "Delete current project";
  del.onclick = async () => {
    const cur = projects.find((p) => p.id === projectId);
    if (!cur || !confirm(`Delete project “${cur.name}” and all its data? This can't be undone.`)) return;
    try {
      await api.deleteProject(cur.id);
      toast(`Deleted “${cur.name}”`, "info");
      const next = projects.find((p) => p.id !== cur.id);
      window.location.search = next ? `?project=${next.id}` : "";
    } catch { toast("Couldn't delete project", "error"); }
  };
  toolbar.insertBefore(del, statusEl);
}

/** Settings panel: keyboard shortcuts (everyone) + integration API keys (admins only). */
function settingsModal() {
  const { ov, card, msg } = modalShell("Settings", 560);
  msg.style.color = "var(--err)";

  // capability status badges (what's wired) — visible to everyone
  const about = document.createElement("div");
  about.innerHTML = `<div class="section-title">Status</div>`;
  const badges = document.createElement("div"); badges.className = "meta"; badges.style.cssText = "display:flex;gap:6px;flex-wrap:wrap";
  badges.textContent = "checking…"; about.appendChild(badges); card.appendChild(about);
  const badge = (label: string, on: boolean) => {
    const b = document.createElement("span");
    b.textContent = `${on ? "●" : "○"} ${label}`;
    b.style.cssText = `padding:2px 8px;border-radius:10px;font-size:11px;border:1px solid var(--line);`
      + `color:${on ? "#33d17a" : "var(--muted)"}`;
    return b;
  };
  void api.capabilities().then((cap) => {
    badges.textContent = "";
    badges.append(badge("AI assist", cap.ai), badge("Email digests", cap.email),
      badge(`SSO${cap.sso.length ? " (" + cap.sso.join(", ") + ")" : ""}`, cap.sso.length > 0));
  }).catch(() => { badges.textContent = ""; });
  // Massing licence — plan tier + what it unlocks (everyone can see; admins enter the key below)
  const lic = document.createElement("div"); lic.className = "meta"; lic.style.cssText = "margin-top:8px;font-size:12px";
  lic.textContent = "checking licence…"; about.appendChild(lic);
  void api.license().then((l) => {
    const f = l.features;
    const unlocked = [f.exports.length ? `exports: ${f.exports.join(", ").toUpperCase()}` : "core exports",
      f.api_access ? "REST API" : null, f.sso ? "SSO" : null, f.navisworks ? "Navisworks" : null].filter(Boolean).join(" · ");
    const warn = l.key_configured && l.key_format_valid === false;
    if (!l.enforced) {
      // open mode: everything available, licence optional — don't nag, just inform
      lic.innerHTML = `<b>Licence:</b> open mode — all features available, a key is <b>optional</b>.`
        + (l.key_configured ? ` (key ${escapeHtml(l.key_masked || "set")}${warn ? ", invalid format" : ""})` : "")
        + ` <a class="ref-link" href="${l.manage_url}" target="_blank" rel="noopener">massing.cloud</a>`;
    } else {
      lic.innerHTML = `<b>Licence:</b> ${escapeHtml(l.tier_label)} plan`
        + (l.key_configured ? ` · key ${escapeHtml(l.key_masked || "set")}` : " · no key (Free)")
        + (warn ? ` · <span style="color:#e2554a">invalid key format</span>` : "")
        + `<br><span style="opacity:.75">Unlocks: ${escapeHtml(unlocked)}</span>`
        + ` — <a class="ref-link" href="${l.manage_url}" target="_blank" rel="noopener">manage at massing.cloud</a>`;
    }
  }).catch(() => { lic.textContent = ""; });
  const credit = document.createElement("div");
  credit.className = "meta"; credit.style.cssText = "margin-top:8px;font-size:11px";
  credit.innerHTML = `Massing <b>v${currentVersion()}</b> — created by <b>Matthew M. Emma</b>, built with Claude Code as AI assistant.`;
  about.appendChild(credit);
  const upRow = document.createElement("div"); upRow.style.cssText = "margin-top:6px;display:flex;gap:8px;align-items:center";
  const upBtn = document.createElement("button"); upBtn.className = "tool-btn"; upBtn.textContent = "Check for updates";
  const upMsg = document.createElement("span"); upMsg.className = "meta"; upMsg.style.fontSize = "11px";
  upBtn.onclick = async () => {
    upMsg.textContent = "checking…";
    const info = await checkForUpdates();
    if (info) { upMsg.innerHTML = `v${info.version} available — <a class="ref-link" href="${info.url}" target="_blank" rel="noopener">download</a>`; }
    else upMsg.textContent = "you're on the latest version";
  };
  upRow.append(upBtn, upMsg); about.appendChild(upRow);

  // keyboard shortcuts (amenity)
  const sc = document.createElement("div");
  sc.innerHTML = `<div class="section-title" style="margin-top:12px">Keyboard shortcuts</div>`;
  const scList = document.createElement("div"); scList.className = "meta"; scList.style.lineHeight = "1.9";
  scList.innerHTML = (SHORTCUTS + " · \\ panel").split("·").map((s) => `<code>${s.trim()}</code>`).join("&nbsp; ");
  sc.appendChild(scList); card.appendChild(sc);

  // integrations + API keys (admin) — loaded on demand; 403 for non-admins is handled gracefully
  const intWrap = document.createElement("div");
  intWrap.innerHTML = `<div class="section-title" style="margin-top:12px">Integrations &amp; API keys</div>`;
  const body = document.createElement("div"); body.className = "meta"; body.textContent = "loading…";
  intWrap.appendChild(body); card.appendChild(intWrap); card.appendChild(msg);

  void api.integrations().then(({ groups }) => {
    body.textContent = "";
    const inputs: Record<string, HTMLInputElement> = {};
    const clears: Record<string, HTMLInputElement> = {};
    for (const g of groups) {
      const h = document.createElement("div");
      h.style.cssText = "display:flex;align-items:center;gap:8px;font-weight:600;margin:10px 0 2px;color:var(--text);font-size:12px";
      const gname = document.createElement("span"); gname.textContent = g.group; h.appendChild(gname);
      // "Test connection" — instant ✓/✗ that the saved key actually works (no guessing)
      const testBtn = document.createElement("button"); testBtn.className = "tool-btn"; testBtn.textContent = "Test";
      testBtn.style.cssText = "font-size:11px;padding:1px 8px";
      const testMsg = document.createElement("span"); testMsg.className = "meta"; testMsg.style.fontSize = "11px";
      testBtn.onclick = async () => {
        testMsg.textContent = "testing…"; testMsg.style.color = "var(--muted)";
        try {
          const r = await api.testIntegration(g.group);
          testMsg.textContent = `${r.ok ? "✓" : "✗"} ${r.message}`;
          testMsg.style.color = r.ok ? "var(--status-good, #33d17a)" : "var(--status-crit, #e2554a)";
        } catch (e) { testMsg.textContent = `✗ ${(e as Error).message}`; testMsg.style.color = "var(--status-crit, #e2554a)"; }
      };
      h.append(testBtn, testMsg);
      body.appendChild(h);
      for (const k of g.keys) {
        const row = document.createElement("div"); row.style.cssText = "display:flex;align-items:center;gap:8px;margin:3px 0";
        const lab = document.createElement("label"); lab.textContent = k.label; lab.style.cssText = "min-width:120px;font-size:12px";
        const inp = document.createElement("input"); inp.className = "portal-filter"; inp.style.flex = "1"; inputs[k.key] = inp;
        if (k.secret) { inp.type = "password"; inp.placeholder = k.configured ? "configured — leave blank to keep" : "not set"; }
        else { inp.type = "text"; inp.value = k.value ?? ""; }
        row.append(lab, inp);
        if (k.secret && k.configured) {
          const cb = document.createElement("input"); cb.type = "checkbox"; cb.title = "clear this key"; clears[k.key] = cb;
          const cl = document.createElement("span"); cl.className = "meta"; cl.textContent = "clear"; cl.style.fontSize = "11px";
          row.append(cb, cl);
        }
        body.appendChild(row);
      }
    }
    const save = document.createElement("button"); save.className = "file-btn"; save.textContent = "Save"; save.style.marginTop = "10px";
    save.onclick = async () => {
      msg.textContent = "";
      const values: Record<string, string> = {};
      for (const [key, inp] of Object.entries(inputs)) {
        if (inp.type === "password") {
          if (inp.value.trim()) values[key] = inp.value.trim();
          else if (clears[key]?.checked) values[key] = "";
        } else values[key] = inp.value;
      }
      try { await api.saveIntegrations(values); ov.remove(); toast("Integration settings saved", "info"); }
      catch { msg.textContent = "could not save settings"; }
    };
    body.appendChild(save);
    const note = document.createElement("div"); note.className = "meta";
    note.style.cssText = "margin-top:8px;font-size:11px";
    note.textContent = "Keys override the matching env var. Secrets are write-only — never shown back.";
    body.appendChild(note);
  }).catch(() => { body.textContent = "Sign in as an admin to add API keys here — no code or config files to edit. "
    + "One place for AI, email, SSO, Speckle, Autodesk APS, and licensing."; });
}



// ---- per-project RBAC capability gating -------------------------------------
// Reflect the caller's project role in the UI: tag actionable controls with data-cap
// ("review" | "edit") and hide those above the caller's role. The API still enforces;
// this just removes the "click → 403" rough edge. Fully open when RBAC is off / offline.
const CAP_RANK: Record<string, number> = { viewer: 0, reviewer: 1, editor: 2, admin: 3 };
let isProjectAdmin = false;   // gates the "Project members…" account-menu item
// a member's workflow party → the persona (view) they land in, so their project role shapes what
// they see when they open the project (the point of multi-user). They can still switch it manually.
const PARTY_TO_PERSONA: Record<string, string> = {
  GC: "gc", Owner: "developer", OwnersRep: "developer",
  Consultant: "engineer", Subcontractor: "subcontractor",
};
let lastMembershipProject: string | null = null;
async function applyCapabilities() {
  let review = true, edit = true, admin = true;
  let party: string | null = null, rbac = false;
  if (connected && projectId) {
    try {
      const m = await api.myRole(projectId);
      rbac = m.rbac; party = m.party_role;
      if (m.rbac) {
        const r = m.role ? CAP_RANK[m.role] : -1;
        review = r >= CAP_RANK.reviewer; edit = r >= CAP_RANK.editor; admin = r >= CAP_RANK.admin;
      }
    } catch { /* keep defaults (don't hide on a transient error) */ }
  }
  isProjectAdmin = admin && !!projectId;
  const b = document.body;
  b.dataset.capReview = review ? "on" : "off";
  b.dataset.capEdit = edit ? "on" : "off";
  b.dataset.capAdmin = admin ? "on" : "off";
  // first time we see this project's membership, land the member in their party's view
  if (rbac && party && projectId && projectId !== lastMembershipProject) {
    const persona = PARTY_TO_PERSONA[party];
    if (persona && !localStorage.getItem("persona-manual")) { personaSel.value = persona; applyPersona(persona, true); }
  }
  lastMembershipProject = projectId;
}

// live notification badge on the Construction workspace tab (SSE)
function connectNotifications() {
  if (!projectId) return;
  const ws = document.querySelector<HTMLElement>('.ws-btn[data-ws="construction"]');
  if (!ws) return;
  let badge = ws.querySelector<HTMLElement>(".ws-badge");
  if (!badge) { badge = document.createElement("span"); badge.className = "ws-badge"; ws.appendChild(badge); }
  try {
    api.notificationStream(projectId, ({ count }) => {
      badge!.textContent = count > 0 ? String(count) : "";
      badge!.style.display = count > 0 ? "" : "none";
    });
  } catch { /* SSE unsupported / offline */ }
}

// ---- keyboard shortcuts -----------------------------------------------------
const SHORTCUTS = "F fit · Esc clear · M dist · A area · S section · H show all · ? help";
window.addEventListener("keydown", (e) => {
  const t = e.target as HTMLElement;
  if (t && /^(INPUT|TEXTAREA|SELECT)$/.test(t.tagName)) return;
  const k = e.key.toLowerCase();
  if (k === "\\") { toggleRail(); return; }
  if (k === "?") { toast(SHORTCUTS + " · \\ panel", "info", 6000); return; }
  if (["f", "escape", "m", "a", "s", "h"].includes(k) && viewerApp) viewerApp.handleKey(k);
});

// ---- startup ----------------------------------------------------------------
async function startup() {
  // viewer-only Pages/demo build has no backend — reads are served from the bundled demo snapshot
  // (api routes them via IS_DEMO), so treat it as "connected" to load the sample project + panels.
  const demo = !!import.meta.env.VITE_PAGES;
  connected = demo ? true : await api.health();
  let projects: { id: string; name: string; model_kind?: string | null }[] = [];
  if (connected) {
    projects = await api.projects();
    const wanted = new URLSearchParams(location.search).get("project");
    const chosen = projects.find((p) => p.id === wanted) ?? projects[0];
    projectId = chosen?.id ?? null;
    projectName = chosen?.name ?? "";
    setStatus(projectId ? `connected • ${projectName}` : "connected • no project — ＋ New to start");
    buildProjectPicker(projects);   // always (shows ＋ New even with zero projects)
  } else {
    setStatus(demo ? "demo — pick a sample from Open ▾ to view"
                   : "offline — open a .frag to view (API not reachable)");
  }
  if (projectId && !demo) connectNotifications();   // SSE needs a backend
  void applyCapabilities();
  if (!demo) void autoCheck();          // show a banner if a newer release is published
  if (!demo) {
    const conn = document.createElement("button");
    conn.className = "tool-btn"; conn.style.marginLeft = "6px"; conn.textContent = "🗄"; conn.title = "Data connections";
    conn.onclick = () => void import("./connections/connectionsUI").then((m) => m.openConnectionsModal(api, () => projectId));
    toolbar.insertBefore(conn, statusEl);
    const reports = document.createElement("button");
    reports.className = "tool-btn"; reports.style.marginLeft = "6px"; reports.textContent = "📊"; reports.title = "Report Center — exportable reports";
    reports.onclick = () => void openReportCenter();
    toolbar.insertBefore(reports, statusEl);
    const gear = document.createElement("button");
    gear.className = "tool-btn"; gear.style.marginLeft = "6px"; gear.textContent = "⚙"; gear.title = "Settings";
    gear.onclick = settingsModal;
    toolbar.insertBefore(gear, statusEl);
    // single-operator local build: no accounts — the operator owns the site, admin UI is open
    let localMode = false;
    try { localMode = (await api.capabilities()).local_mode === true; } catch { /* default off */ }
    if (!localMode) void buildAuthControl({
      api, toolbar, statusEl,
      getProjectId: () => projectId,
      getIsProjectAdmin: () => isProjectAdmin,
      openSettings: settingsModal,
    });
  }
  // Help (?) — relaunch the welcome / tour, the guides, or the getting-started checklist
  const help = document.createElement("button");
  help.className = "tool-btn"; help.style.marginLeft = "6px"; help.textContent = "?"; help.title = "Help, tour & guides";
  help.onclick = () => { reopenChecklist(); showWelcome(onboardCtx()); };
  toolbar.insertBefore(help, statusEl);
  // field capture (mobile-first quick capture with offline queue) — needs the backend
  if (!demo) {
    const fc = new FieldCapture(api, () => projectId); fc.mount();
    // PWA app-shortcut / deep link: ?capture=1 jumps straight to the field-capture sheet
    if (new URLSearchParams(location.search).get("capture")) setTimeout(() => fc.open(), 400);
  }
  // gamified getting-started checklist (feature discovery + activation)
  mountChecklist();
  // first run: welcome the user (skippable). Anchors must exist first, so defer a tick.
  setTimeout(() => maybeWelcome(onboardCtx()), 600);
}

function initNav() {
  applyPersona(personaSel.value);
  const savedWs = localStorage.getItem("workspace");
  const allowWs = PERSONAS[personaSel.value]?.ws ?? null;
  setWorkspace(savedWs && (!allowWs || allowWs.includes(savedWs)) ? savedWs : currentWs);
}

// Embeddable mode: `?embed=1` hides the app chrome (top bar, rails, tabs) and shows just the 3D
// viewer for the given ?project= — for an <iframe>/web-component embed (Teams tab, partner portal,
// a marketing site). Read-only by nature; pair with a signed link for unauthenticated sharing.
const _embed = new URLSearchParams(location.search).get("embed") === "1";
if (_embed) document.body.classList.add("embed");

// ---- command palette (Cmd/Ctrl-K) — jump to any workspace, module, action, or record -----------
function openModuleFromPalette(key: string) {
  setWorkspace("construction"); openPortalTab();
  const go = () => portal.openModuleByKey(key);
  if (portal.moduleList().length) go(); else setTimeout(go, 500);
}
const _palette = _embed ? null : initCommandPalette({
  commands: () => {
    const cmds: Command[] = [];
    for (const w of WORKSPACES) cmds.push({ id: "ws:" + w.key, label: "Go to " + w.label, hint: "Workspace", run: () => setWorkspace(w.key) });
    cmds.push(
      { id: "act:new", label: "New project", hint: "Action", run: () => void newProject() },
      { id: "act:ifc", label: "Open IFC…", hint: "Action", run: () => openModelFile("ifc") },
      { id: "act:ref", label: "Open mesh / point cloud / GIS…", hint: "Action", run: () => openModelFile("ref") },
      { id: "act:reports", label: "Open Report Center", hint: "Action", run: () => void openReportCenter() },
      { id: "act:save", label: "Save Project (.mmproj)", hint: "Action", run: () => saveProjectBundle() },
      { id: "act:help", label: "Keyboard shortcuts / help", hint: "Action", run: () => toast(SHORTCUTS + " · ⌘K palette", "info", 6000) },
    );
    for (const m of portal.moduleList())
      cmds.push({ id: "mod:" + m.key, label: m.name, hint: m.section || "Module", run: () => openModuleFromPalette(m.key) });
    return cmds;
  },
  search: async (q) => {
    if (!projectId) return [];
    try {
      const hits = await api.searchAll(projectId, q);
      return hits.slice(0, 8).map((h) => ({
        id: "rec:" + h.id, label: `${h.ref} ${h.title ?? ""}`.trim(), hint: h.module_name || "Record",
        run: () => { setWorkspace("construction"); openPortalTab();
          const go = () => portal.openRecordByKey(h.module, h.id);
          if (portal.moduleList().length) go(); else setTimeout(go, 500); },
      }));
    } catch { return []; }
  },
});

// Visible ⌘K affordance — the palette (jump to any workspace/module/record/action) is the fastest
// path through the app, but a keyboard-only shortcut is invisible to non-technical users. Put a
// labeled Search button in the header so it's discoverable + clickable.
if (_palette) {
  const search = document.createElement("button");
  search.id = "cmdk-btn"; search.className = "tool-btn"; search.type = "button";
  search.title = "Search / jump to anything (Ctrl/⌘-K)";
  search.innerHTML = `<span aria-hidden="true">🔍</span> Search <kbd class="cmdk-kbd">⌘K</kbd>`;
  search.onclick = () => _palette.open();
  document.getElementById("workspaces")?.insertAdjacentElement("beforebegin", search);
}

startup().finally(() => { initNav(); if (_embed) setWorkspace("model"); });

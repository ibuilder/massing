import "./style.css";
import { DrawingsUI } from "./drawings/drawings";
import { PortalUI } from "./portal/portal";
import { ProformaUI } from "./proforma/proforma";
import { ApiClient } from "./api/client";
import { toast } from "./ui/feedback";
import { autoCheck, checkForUpdates, currentVersion } from "./ui/update";
import { maybeWelcome, showWelcome } from "./ui/onboarding";
import { mountChecklist, reopenChecklist } from "./ui/checklist";
import { FieldCapture } from "./field/field";
import { modalShell } from "./ui/modal";
import { buildMenu, closeMenus } from "./ui/menus";
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

// ---- Open / Save dropdown menus (extracted to ./ui/menus) -------------------
const dismissMenusIfOutside = (e: Event) => { if (!(e.target as HTMLElement).closest(".menu")) closeMenus(); };
document.addEventListener("pointerdown", dismissMenusIfOutside, true);
document.addEventListener("click", dismissMenusIfOutside, true);
window.addEventListener("blur", () => closeMenus());
document.addEventListener("keydown", (e) => { if (e.key === "Escape") closeMenus(); });
// pre-warm the viewer when the file menus open so triggerOpen/export resolve promptly
buildMenu("open-menu", "Open ▾", [
  { label: "Open Project (.mmproj)…", onClick: () => void openProjectBundle() },
  { label: "Open IFC…", onClick: () => withViewer((v) => v.triggerOpen("ifc")) },
  { label: "Open Fragments (.frag)…", onClick: () => withViewer((v) => v.triggerOpen("frag")) },
  { label: "Sample models", sep: true },
  { label: "School — Structural", onClick: () => withViewer((v) => void v.loadSample("/school_str.frag", "School (Structural)")) },
  { label: "School — Architectural", onClick: () => withViewer((v) => void v.loadSample("/school_arq.frag", "School (Architectural)")) },
  { label: "BasicHouse", onClick: () => withViewer((v) => void v.loadSample("/basichouse.frag", "BasicHouse")) },
  { label: "Import from Revit / CAD", sep: true },
  { label: "Free: export IFC from Revit (no bridge)…", onClick: () => showFreeImportHelp() },
  { label: "Revit (.rvt) — paid Autodesk bridge…", onClick: () => withViewer((v) => v.triggerOpen("convert")) },
  { label: "AutoCAD (.dwg) — paid bridge…", onClick: () => withViewer((v) => v.triggerOpen("convert")) },
  { label: "Navisworks (.nwc) — paid bridge…", onClick: () => withViewer((v) => v.triggerOpen("convert")) },
], () => void ensureViewer());
buildMenu("save-menu", "Save ▾", [
  { label: "Save Project (.mmproj)", onClick: () => saveProjectBundle() },
  { label: "Geometry", sep: true },
  { label: "Export Fragments (.frag)", onClick: () => withViewer((v) => void v.exportFrag()) },
  { label: "Export source IFC (.ifc)", onClick: () => withViewer((v) => v.exportIfc()) },
], () => void ensureViewer());

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
    drop a raw <code>.rvt</code> in directly. The free path is to export IFC from Revit, then use
    <b>Open&nbsp;IFC…</b>:</p>
    <ol style="margin:8px 0 8px 18px;line-height:1.5">
      <li><b>One model — Revit built-in:</b> <i>File ▸ Export ▸ IFC</i>. Pick <b>IFC 4</b> (or IFC 2x3
          for older tools) and a coordinate base of <i>Project / Shared</i>. Save the <code>.ifc</code>.</li>
      <li><b>Many models / repeatable — pyRevit (free, open-source):</b> install
          <code>pyRevit</code>, then use its IFC export tools to batch-export views/models to IFC.</li>
      <li>Back here: <b>Open ▸ Open&nbsp;IFC…</b> — we pre-convert it to Fragments on the server and
          it streams in like any other model.</li>
    </ol>
    <p class="meta">DWG/NWC: export to IFC from their host app the same way, or use the paid bridge.</p>`;
  card.appendChild(msg);
  const links = document.createElement("div");
  links.style.cssText = "display:flex;gap:10px;flex-wrap:wrap;margin-top:6px";
  for (const [t, href] of [
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
const RAIL_ITEMS: { key: string; icon: string; title: string }[] = [
  { key: "tree", icon: "⌗", title: "Model tree" },
  { key: "layers", icon: "≣", title: "Layers" },
  { key: "issues", icon: "⚑", title: "Issues / RFIs" },
  { key: "tools", icon: "⚙", title: "Tools & analysis" },
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
  b.className = "rail-btn"; b.dataset.rail = it.key; b.textContent = it.icon;
  b.title = it.title; b.setAttribute("aria-label", it.title);
  b.onclick = () => {
    const isActive = b.classList.contains("active") && !appEl.classList.contains("rail-collapsed");
    if (isActive) appEl.classList.add("rail-collapsed");
    else showRail(it.key);
  };
  railEl.appendChild(b);
}

const WORKSPACES: { key: string; label: string }[] = [
  { key: "model", label: "Model" }, { key: "drawings", label: "Drawings" },
  { key: "construction", label: "Construction" }, { key: "finance", label: "Finance" },
];
let currentWs = "model";
function setWorkspace(key: string) {
  currentWs = key;
  document.querySelectorAll(".ws-btn").forEach((b) => b.classList.toggle("active", (b as HTMLElement).dataset.ws === key));
  document.querySelectorAll(".workspace").forEach((w) => w.classList.toggle("active", w.id === `ws-${key}`));
  if (key === "drawings") openDrawingsTab();
  if (key === "construction") openPortalTab();
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
  b.onclick = () => setWorkspace(w.key);
  wsEl.appendChild(b);
}

document.querySelectorAll<HTMLButtonElement>(".fintab").forEach((t) => {
  t.onclick = () => {
    document.querySelectorAll(".fintab").forEach((x) => x.classList.remove("active"));
    document.querySelectorAll("#ws-finance .fullpanel").forEach((p) => p.classList.remove("active"));
    t.classList.add("active");
    $(`panel-${t.dataset.fin}`).classList.add("active");
    if (t.dataset.fin === "proforma") openProformaTab();
    if (t.dataset.fin === "portfolio") openPortfolioTab();
  };
});

// ---- role-based navigation --------------------------------------------------
interface PersonaCfg { ws: string[] | null; rail: string[] | null; home: string; }
const PERSONAS: Record<string, PersonaCfg> = {
  all:           { ws: null, rail: null, home: "model" },
  developer:     { ws: ["finance", "model", "drawings", "construction"], rail: ["issues", "tools", "tree"], home: "finance" },
  gc:            { ws: ["construction", "model", "drawings", "finance"], rail: ["tree", "layers", "issues", "tools"], home: "construction" },
  architect:     { ws: ["model", "drawings", "construction"], rail: ["tree", "layers", "issues", "tools"], home: "model" },
  engineer:      { ws: ["model", "drawings"], rail: ["tree", "layers", "tools", "issues"], home: "model" },
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
personaSel.onchange = () => applyPersona(personaSel.value, true);

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
const portal = new PortalUI($("panel-portal"), {
  api,
  projectId: () => projectId,
  anchorPoint: () => viewerApp?.anchorPoint() ?? null,
  selectedGuid: () => viewerApp?.selectedGuidValue() ?? null,
  onSelectGuids: (guids) => { if (guids[0]) { setWorkspace("model"); withViewer((v) => void v.selectByGuid(guids[0], true)); } },
  onPinsChanged: () => { if (viewerApp) void viewerApp.reloadModelPins(); },
  setStatus,
});
let portalReady = false;
function openPortalTab() { if (portalReady) return; portalReady = true; void portal.init(); }

const proforma = new ProformaUI($("panel-proforma"), api, setStatus, () => projectId);
let proformaReady = false;
function openProformaTab() { if (proformaReady) return; proformaReady = true; void proforma.init(); }

const drawings = new DrawingsUI($("panel-drawings"), { api, projectId: () => projectId, setStatus });
function openDrawingsTab() { void drawings.open(); }   // re-loads the register each open (cheap)

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
    connected,
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

// ---- auth: sign-in control + modal ------------------------------------------
function loginModal() {
  const ov = document.createElement("div");
  ov.style.cssText = "position:fixed;inset:0;z-index:200;background:#000a;display:flex;align-items:center;justify-content:center";
  const card = document.createElement("div");
  card.style.cssText = "background:var(--panel);border:1px solid var(--line);border-radius:10px;padding:20px;min-width:280px;display:flex;flex-direction:column;gap:10px";
  const title = document.createElement("strong"); title.textContent = "Sign in"; title.style.fontSize = "15px";
  const u = document.createElement("input"); u.placeholder = "username"; u.className = "portal-filter";
  const p = document.createElement("input"); p.type = "password"; p.placeholder = "password"; p.className = "portal-filter";
  const msg = document.createElement("div"); msg.className = "meta"; msg.style.color = "#e2554a";
  const row = document.createElement("div"); row.style.cssText = "display:flex;gap:8px;justify-content:flex-end";
  const cancel = document.createElement("button"); cancel.className = "tool-btn"; cancel.textContent = "Cancel"; cancel.onclick = () => ov.remove();
  const go = document.createElement("button"); go.className = "file-btn"; go.textContent = "Sign in";
  const submit = async () => {
    if (!u.value.trim() || !p.value) { msg.textContent = "enter a username and password"; return; }
    try { const r = await api.login(u.value.trim(), p.value); api.setToken(r.token); ov.remove(); location.reload(); }
    catch { msg.textContent = "invalid username or password"; }
  };
  go.onclick = () => void submit();
  p.onkeydown = (e) => { if (e.key === "Enter") void submit(); };
  const resetLink = document.createElement("a");
  resetLink.textContent = "Have a reset token?"; resetLink.href = "#";
  resetLink.style.cssText = "font-size:12px;color:var(--muted);align-self:flex-start";
  resetLink.onclick = (e) => { e.preventDefault(); ov.remove(); resetModal(); };
  row.append(cancel, go); card.append(title, u, p, msg, row, resetLink); ov.append(card);
  // SSO buttons (only the providers configured on the server), shown above the password form
  void api.authProviders().then(({ providers }) => {
    if (!providers.length) return;
    const wrap = document.createElement("div"); wrap.style.cssText = "display:flex;flex-direction:column;gap:6px";
    for (const pv of providers) {
      const b = document.createElement("button"); b.className = "file-btn";
      b.textContent = `Continue with ${pv.label}`;
      b.onclick = () => { window.location.href = api.url(`/auth/oauth/${pv.id}/login`); };
      wrap.appendChild(b);
    }
    const div = document.createElement("div"); div.className = "meta"; div.textContent = "— or sign in with a password —";
    div.style.cssText = "text-align:center;margin:4px 0";
    card.insertBefore(div, u); card.insertBefore(wrap, div);
  }).catch(() => {});
  document.body.appendChild(ov); u.focus();
}

/** Set a new password using an admin-issued one-time reset token (no email infra). */
function resetModal() {
  const { ov, card, msg } = modalShell("Reset password with token");
  const tk = document.createElement("input"); tk.placeholder = "reset token"; tk.className = "portal-filter";
  const np = document.createElement("input"); np.type = "password"; np.placeholder = "new password (min 8)"; np.className = "portal-filter";
  msg.style.color = "#e2554a";
  const row = document.createElement("div"); row.style.cssText = "display:flex;gap:8px;justify-content:flex-end";
  const cancel = document.createElement("button"); cancel.className = "tool-btn"; cancel.textContent = "Cancel"; cancel.onclick = () => ov.remove();
  const go = document.createElement("button"); go.className = "file-btn"; go.textContent = "Set password";
  go.onclick = async () => {
    if (!tk.value.trim()) { msg.textContent = "paste your reset token"; return; }
    if (np.value.length < 8) { msg.textContent = "new password must be at least 8 characters"; return; }
    try { await api.resetWithToken(tk.value.trim(), np.value); ov.remove(); toast("Password set — please sign in", "info"); loginModal(); }
    catch { msg.textContent = "invalid or expired reset token"; }
  };
  row.append(cancel, go); card.append(tk, np, msg, row); tk.focus();
}

async function buildAuthControl() {
  const el = document.createElement("button");
  el.className = "tool-btn"; el.style.marginLeft = "6px"; el.dataset.tour = "account";
  if (api.authed) {
    let name = "account", platformAdmin = false, tier = "free";
    try {
      const m = await api.me();
      if (m.authenticated) { name = m.username; platformAdmin = !!m.platform_admin; tier = m.tier || "free"; }
      else api.setToken("");
    }
    catch { /* keep token; offline */ }
    el.textContent = `${name} ▾`; el.title = "Account";
    el.onclick = () => accountMenu(el, platformAdmin, tier);
  } else {
    el.textContent = "Sign in"; el.title = "Sign in";
    el.onclick = loginModal;
  }
  toolbar.insertBefore(el, statusEl);
}

/** Small dropdown anchored to the account button: self-service + (for platform admins/ops) the
 *  platform consoles. End users have no admin tier — they manage their own projects' members. */
function accountMenu(anchor: HTMLElement, platformAdmin = false, tier = "free") {
  document.querySelector(".acct-menu")?.remove();
  const menu = document.createElement("div");
  menu.className = "acct-menu";
  const r = anchor.getBoundingClientRect();
  menu.style.cssText = `position:fixed;top:${r.bottom + 4}px;right:${window.innerWidth - r.right}px;z-index:200;`
    + "background:var(--panel);border:1px solid var(--line);border-radius:8px;padding:5px;display:flex;flex-direction:column;min-width:160px";
  // tier badge (everyone is Free today; the seam is ready for paid plans)
  const badge = document.createElement("div");
  badge.className = "meta";
  badge.style.cssText = "padding:4px 8px;display:flex;justify-content:space-between;gap:8px;align-items:center";
  badge.innerHTML = `<span>Plan</span><span style="text-transform:capitalize;color:var(--text)">${tier}</span>`;
  menu.append(badge);
  const item = (label: string, fn: () => void) => {
    const b = document.createElement("button");
    b.className = "tool-btn"; b.textContent = label; b.style.cssText = "justify-content:flex-start;width:100%;text-align:left";
    b.onclick = () => { menu.remove(); fn(); };
    return b;
  };
  if (platformAdmin) menu.append(item("Manage users…", adminModal));
  if (platformAdmin) menu.append(item("Audit log…", auditModal));
  if (platformAdmin) menu.append(item("Data connections…", connectionsModal));
  if (isProjectAdmin && projectId) menu.append(item("Project members…", () => membersModal(projectId!)));
  menu.append(item("Settings…", settingsModal));
  menu.append(item("Change password…", passwordModal));
  menu.append(item("Sign out", async () => { await api.logout(); api.setToken(""); location.reload(); }));
  document.body.appendChild(menu);
  setTimeout(() => document.addEventListener("pointerdown", function off(e) {
    if (!menu.contains(e.target as Node)) { menu.remove(); document.removeEventListener("pointerdown", off); }
  }), 0);
}

/** Generic modal shell matching the sign-in dialog. */
// modalShell moved to ./ui/modal (shared shell + Esc-to-close, focus, ARIA). Imported at top.

/** Self-service password change (available to any signed-in user). */
function passwordModal() {
  const { ov, card, msg } = modalShell("Change password");
  const cur = document.createElement("input"); cur.type = "password"; cur.placeholder = "current password"; cur.className = "portal-filter";
  const nw = document.createElement("input"); nw.type = "password"; nw.placeholder = "new password (min 8)"; nw.className = "portal-filter";
  msg.style.color = "#e2554a";
  const row = document.createElement("div"); row.style.cssText = "display:flex;gap:8px;justify-content:flex-end";
  const cancel = document.createElement("button"); cancel.className = "tool-btn"; cancel.textContent = "Cancel"; cancel.onclick = () => ov.remove();
  const go = document.createElement("button"); go.className = "file-btn"; go.textContent = "Update";
  go.onclick = async () => {
    if (nw.value.length < 8) { msg.textContent = "new password must be at least 8 characters"; return; }
    try { await api.changePassword(cur.value, nw.value); ov.remove(); toast("Password updated", "info"); }
    catch { msg.textContent = "current password is incorrect"; }
  };
  row.append(cancel, go); card.append(cur, nw, msg, row); cur.focus();
}

/** Admin user management: create accounts, toggle role/active, reset passwords. */
function adminModal() {
  const { card, msg } = modalShell("Manage users", 460);
  const list = document.createElement("div"); list.style.cssText = "display:flex;flex-direction:column;gap:6px";
  msg.style.color = "#e2554a";

  const render = async () => {
    list.textContent = "";
    let users: import("./api/client").AccountUser[] = [];
    try { users = await api.listUsers(); } catch { msg.textContent = "could not load users"; return; }
    for (const u of users) {
      const row = document.createElement("div");
      row.style.cssText = "display:flex;align-items:center;gap:8px;padding:6px 8px;border:1px solid var(--line);border-radius:6px";
      const nm = document.createElement("span"); nm.textContent = u.username; nm.style.cssText = "font-weight:600;min-width:90px";
      const tags = document.createElement("span"); tags.className = "meta";
      tags.textContent = `${u.role}${u.active ? "" : " · deactivated"}${u.email ? " · " + u.email : ""}`;
      tags.style.color = u.active ? "var(--muted)" : "#e2554a";
      const spacer = document.createElement("span"); spacer.style.flex = "1";
      const act = (label: string, fn: () => Promise<unknown>) => {
        const b = document.createElement("button"); b.className = "tool-btn"; b.textContent = label;
        b.onclick = async () => { try { await fn(); await render(); } catch { msg.textContent = `action failed for ${u.username}`; } };
        return b;
      };
      const roleBtn = act(u.role === "admin" ? "Make user" : "Make admin",
        () => api.updateUser(u.username, { role: u.role === "admin" ? "user" : "admin" }));
      const activeBtn = act(u.active ? "Deactivate" : "Reactivate",
        () => api.updateUser(u.username, { active: !u.active }));
      const pwBtn = act("Reset password", async () => {
        const np = prompt(`New password for ${u.username} (min 8):`);
        if (np == null) return;
        if (np.length < 8) { msg.textContent = "password must be at least 8 characters"; return; }
        await api.resetUserPassword(u.username, np);
        toast(`Password reset for ${u.username}`, "info");
      });
      const linkBtn = act("Reset link", async () => {
        const { reset_token } = await api.issueResetToken(u.username);
        // hand the one-time token to the user (no email infra); they set their own password
        await navigator.clipboard?.writeText(reset_token).catch(() => {});
        prompt(`One-time reset token for ${u.username} (copied; expires in 1h). They paste it at Sign in → "Have a reset token?":`, reset_token);
      });
      const emailBtn = act("Email", async () => {
        const e = prompt(`Email for ${u.username} (blank to clear):`, u.email || "");
        if (e === null) return;
        await api.updateUser(u.username, { email: e.trim() });
        toast(`Email updated for ${u.username}`, "info");
      });
      row.append(nm, tags, spacer, roleBtn, activeBtn, pwBtn, linkBtn, emailBtn);
      list.append(row);
    }
  };

  // create-user form
  const form = document.createElement("div"); form.style.cssText = "display:flex;gap:6px;flex-wrap:wrap;align-items:center";
  const nu = document.createElement("input"); nu.placeholder = "new username"; nu.className = "portal-filter"; nu.style.flex = "1";
  const np = document.createElement("input"); np.type = "password"; np.placeholder = "password (min 8)"; np.className = "portal-filter"; np.style.flex = "1";
  const ne = document.createElement("input"); ne.type = "email"; ne.placeholder = "email (for digests, optional)"; ne.className = "portal-filter"; ne.style.flex = "1";
  const nr = document.createElement("select"); nr.className = "portal-filter";
  nr.innerHTML = '<option value="user">user</option><option value="admin">admin</option>';
  const add = document.createElement("button"); add.className = "file-btn"; add.textContent = "Add";
  add.onclick = async () => {
    msg.textContent = "";
    if (!nu.value.trim() || np.value.length < 8) { msg.textContent = "username + password (min 8) required"; return; }
    try {
      await api.createUser(nu.value.trim(), np.value, nr.value as "admin" | "user", ne.value.trim() || undefined);
      nu.value = ""; np.value = ""; ne.value = ""; await render();
    } catch { msg.textContent = "could not create user (name may be taken)"; }
  };
  form.append(nu, np, ne, nr, add);

  card.append(list, document.createElement("hr"), form, msg);
  void render();
}

/** Settings panel: keyboard shortcuts (everyone) + integration API keys (admins only). */
function settingsModal() {
  const { ov, card, msg } = modalShell("Settings", 560);
  msg.style.color = "#e2554a";

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
  const credit = document.createElement("div");
  credit.className = "meta"; credit.style.cssText = "margin-top:8px;font-size:11px";
  credit.innerHTML = `AEC BIM Platform <b>v${currentVersion()}</b> — created by <b>Matthew M. Emma</b>, built with Claude Code as AI assistant.`;
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
      const h = document.createElement("div"); h.textContent = g.group;
      h.style.cssText = "font-weight:600;margin:10px 0 2px;color:var(--text);font-size:12px";
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
  }).catch(() => { body.textContent = "Sign in as an admin to configure API keys (AI, email, SSO)."; });
}

/** Data-source connections (admin): the local app DB + external Postgres/Supabase/Procore. */
/** Auto-sync schedules for a Procore connection → the current project's modules. */
function schedulesModal(connectionId: string) {
  const pid = projectId; if (!pid) return;
  const { card, msg } = modalShell("Auto-sync schedules", 500);
  msg.style.color = "#e2554a";
  const list = document.createElement("div"); card.appendChild(list);
  const render = async () => {
    list.textContent = "";
    let scheds: import("./api/client").SyncScheduleItem[] = [];
    try { scheds = (await api.syncSchedules(pid)).filter((s) => s.connection_id === connectionId); }
    catch { list.innerHTML = `<div class="meta">admin only.</div>`; return; }
    if (!scheds.length) { const e = document.createElement("div"); e.className = "empty-state"; e.innerHTML = `No schedules yet<span class="es-hint">Add one below to auto-sync from Procore.</span>`; list.appendChild(e); }
    const act = (label: string, fn: () => Promise<unknown>) => { const b = document.createElement("button"); b.className = "tool-btn"; b.textContent = label; b.onclick = async () => { try { await fn(); await render(); } catch { msg.textContent = "action failed"; } }; return b; };
    for (const s of scheds) {
      const row = document.createElement("div"); row.style.cssText = "border:1px solid var(--line);border-radius:8px;padding:8px;display:flex;align-items:center;gap:8px;flex-wrap:wrap;margin-bottom:6px";
      const info = document.createElement("span"); info.className = "meta"; info.style.flex = "1";
      const lr = s.last_run ? new Date(s.last_run).toLocaleString() : "never";
      const tail = s.last_result?.imported_total != null ? ` (+${s.last_result.imported_total})` : s.last_result?.error ? " (error)" : "";
      info.innerHTML = `Procore #${s.procore_project_id} · every ${s.interval_minutes}m · ${s.kinds.join("/")}${s.push ? " · two-way ⇄" : ""}`
        + `<br><span style="font-size:11px">${s.enabled ? "enabled" : "disabled"} · last: ${lr}${tail}</span>`;
      row.append(info,
        act(s.enabled ? "Disable" : "Enable", () => api.updateSyncSchedule(pid, s.id, { enabled: !s.enabled })),
        act(s.push ? "Two-way ✓" : "Two-way", () => api.updateSyncSchedule(pid, s.id, { push: !s.push })),
        act("Run now", async () => { const r = await api.runSyncSchedule(pid, s.id); toast(r.error ? `error: ${r.error}` : `imported ${r.imported_total ?? 0}`, "info"); }),
        act("Delete", () => api.deleteSyncSchedule(pid, s.id)));
      list.appendChild(row);
    }
    const form = document.createElement("div"); form.style.cssText = "border:1px dashed var(--line);border-radius:8px;padding:10px;margin-top:6px;display:flex;gap:6px;flex-wrap:wrap;align-items:center";
    const pp = document.createElement("input"); pp.placeholder = "Procore project ID"; pp.className = "portal-filter"; pp.style.flex = "1";
    const iv = document.createElement("input"); iv.type = "number"; iv.value = "60"; iv.title = "interval (minutes, min 5)"; iv.className = "portal-filter"; iv.style.width = "80px";
    const tw = document.createElement("input"); tw.type = "checkbox"; tw.id = "sched-twoway";
    const twl = document.createElement("label"); twl.htmlFor = "sched-twoway"; twl.textContent = "two-way"; twl.className = "meta"; twl.style.fontSize = "12px";
    const add = document.createElement("button"); add.className = "file-btn"; add.textContent = "Add schedule";
    add.onclick = async () => {
      if (!pp.value.trim()) { msg.textContent = "Procore project ID required"; return; }
      try { await api.createSyncSchedule(pid, { connection_id: connectionId, procore_project_id: pp.value.trim(), interval_minutes: Math.max(5, parseInt(iv.value) || 60), push: tw.checked }); pp.value = ""; tw.checked = false; await render(); }
      catch { msg.textContent = "could not add schedule"; }
    };
    form.append(pp, iv, tw, twl, add); list.appendChild(form);
  };
  card.appendChild(msg); void render();
}

/** Field-mapping editor (admin): remap which Procore field feeds each module field, per kind.
 *  Blank input = use the default path shown as the placeholder. Closes the last-mile interop gap. */
function mappingModal(connectionId: string, name: string) {
  const { card, msg } = modalShell(`Field mapping — ${name}`, 560);
  msg.style.color = "#e2554a";
  const intro = document.createElement("div"); intro.className = "meta"; intro.style.marginBottom = "8px";
  intro.textContent = "Map each module field to a Procore source path (dotted, e.g. questions.0.body). Leave blank to use the default.";
  card.appendChild(intro);
  const body = document.createElement("div"); card.appendChild(body);
  const inputs: { kind: string; field: string; def: string; el: HTMLInputElement }[] = [];
  const render = async () => {
    body.textContent = ""; inputs.length = 0;
    let data: Awaited<ReturnType<typeof api.connectionMappings>>;
    try { data = await api.connectionMappings(connectionId); } catch { msg.textContent = "admin only — could not load mapping"; return; }
    for (const [kind, m] of Object.entries(data.mappings)) {
      const sec = document.createElement("div"); sec.style.cssText = "border:1px solid var(--line);border-radius:8px;padding:8px 10px;margin-bottom:8px";
      sec.innerHTML = `<div class="meta" style="font-weight:600;color:var(--text);margin-bottom:6px">${kind} <span style="font-weight:400">→ ${m.module}</span></div>`;
      for (const f of m.fields) {
        const r = document.createElement("div"); r.style.cssText = "display:flex;align-items:center;gap:8px;margin-bottom:4px";
        const lab = document.createElement("span"); lab.className = "meta"; lab.style.cssText = "width:130px;font-size:12px"; lab.textContent = f.label;
        const inp = document.createElement("input"); inp.className = "portal-filter"; inp.style.cssText = "flex:1;font-family:ui-monospace,monospace;font-size:12px";
        inp.placeholder = f.default; if (f.path !== f.default) inp.value = f.path;
        inputs.push({ kind, field: f.field, def: f.default, el: inp });
        r.append(lab, inp); sec.appendChild(r);
      }
      body.appendChild(sec);
    }
    const bar = document.createElement("div"); bar.style.cssText = "display:flex;gap:8px;margin-top:4px";
    const save = document.createElement("button"); save.className = "file-btn"; save.textContent = "Save mapping";
    save.onclick = async () => {
      const out: Record<string, Record<string, string>> = {};
      for (const i of inputs) { const v = i.el.value.trim(); if (v && v !== i.def) (out[i.kind] ||= {})[i.field] = v; }
      try { await api.saveConnectionMappings(connectionId, out); toast("Field mapping saved", "info"); await render(); }
      catch { msg.textContent = "could not save mapping"; }
    };
    const reset = document.createElement("button"); reset.className = "tool-btn"; reset.textContent = "Reset to defaults";
    reset.onclick = async () => { try { await api.saveConnectionMappings(connectionId, {}); toast("Mapping reset to defaults", "info"); await render(); } catch { msg.textContent = "could not reset"; } };
    bar.append(save, reset); body.appendChild(bar);
  };
  card.appendChild(msg); void render();
}

function connectionsModal() {
  const { card, msg } = modalShell("Data connections", 560);
  msg.style.color = "#e2554a";
  const list = document.createElement("div"); list.style.cssText = "display:flex;flex-direction:column;gap:8px";
  card.appendChild(list);

  const TYPE_FIELDS: Record<string, { key: string; label: string; secret?: boolean; placeholder?: string }[]> = {
    postgres: [{ key: "dsn", label: "Connection string", secret: true, placeholder: "postgresql://user:pass@host:5432/db" }],
    supabase: [{ key: "dsn", label: "Supabase DB URL", secret: true, placeholder: "postgresql://postgres:pass@db.xxx.supabase.co:5432/postgres" }],
    procore: [{ key: "access_token", label: "Access token", secret: true, placeholder: "Procore OAuth access token" }],
    acc: [{ key: "access_token", label: "Access token", secret: true, placeholder: "Autodesk (APS) 3-legged OAuth token" },
          { key: "account_id", label: "Account ID", placeholder: "ACC account / hub GUID (to list projects)" }],
    quickbooks: [{ key: "access_token", label: "Access token", secret: true, placeholder: "QuickBooks Online OAuth access token" },
                 { key: "realm_id", label: "Realm / Company ID", placeholder: "QuickBooks company (realm) id" }],
    sage: [{ key: "access_token", label: "Access token", secret: true, placeholder: "Sage API token" },
           { key: "base_url", label: "API base URL", placeholder: "https://api.your-sage-tenant.com" }],
    viewpoint: [{ key: "access_token", label: "Access token", secret: true, placeholder: "Viewpoint (Trimble) API token" },
                { key: "base_url", label: "API base URL", placeholder: "https://api.your-viewpoint-tenant.com" }],
  };

  const render = async () => {
    list.textContent = "";
    let data: { types: string[]; connections: import("./api/client").ConnectionItem[] };
    try { data = await api.connections(); } catch { msg.textContent = "sign in as an admin to manage connections"; return; }
    for (const cx of data.connections) {
      const row = document.createElement("div");
      row.style.cssText = "border:1px solid var(--line);border-radius:8px;padding:8px 10px;display:flex;align-items:center;gap:8px;flex-wrap:wrap";
      const dot = document.createElement("span"); dot.className = "conn-dot";
      const badge = (ok?: boolean) => { dot.style.background = ok === undefined ? "#9aa0a6" : ok ? "#33d17a" : "#e2554a"; };
      badge(cx.status?.ok);
      const nm = document.createElement("span"); nm.innerHTML = `<b>${cx.name}</b> <span class="meta">${cx.type}${cx.builtin ? " · built-in" : ""}</span>`;
      const detail = document.createElement("span"); detail.className = "meta"; detail.style.cssText = "flex:1;min-width:140px;font-size:11px";
      detail.textContent = cx.status?.detail ?? (cx.builtin ? "" : "not tested");
      const act = (label: string, fn: () => Promise<unknown>) => { const b = document.createElement("button"); b.className = "tool-btn"; b.textContent = label; b.onclick = async () => { try { await fn(); } catch { msg.textContent = `action failed`; } }; return b; };
      row.append(dot, nm, detail);
      if (["local", "postgres", "supabase"].includes(cx.type)) {
        row.append(act("Browse", async () => browseConnection(cx.id, cx.name)));
      }
      if (cx.type === "procore") {
        row.append(act("Sync now", async () => {
          if (!projectId) { msg.textContent = "open a project first to import into it"; return; }
          const pp = prompt("Procore project ID to import from (RFIs, submittals, change events):");
          if (!pp || !pp.trim()) return;
          const r = await api.syncProcore(projectId, cx.id, pp.trim());
          const by = Object.entries(r.results).map(([k, v]) => `${v.imported} ${k}`).join(", ");
          toast(`Procore: imported ${r.imported_total} record(s) (${by})`, "info");
        }));
        row.append(act("Push", async () => {
          if (!projectId) { msg.textContent = "open a project first"; return; }
          const pp = prompt("Procore project ID to push resolved RFIs (answer + status) to:");
          if (!pp || !pp.trim()) return;
          const r = await api.pushProcore(projectId, cx.id, pp.trim());
          toast(`Pushed ${r.pushed_total} RFI(s) back to Procore`, "info");
        }));
        row.append(act("Schedules", async () => {
          if (!projectId) { msg.textContent = "open a project first to schedule auto-sync"; return; }
          schedulesModal(cx.id);
        }));
        row.append(act("Mapping", async () => mappingModal(cx.id, cx.name)));
      }
      if (cx.type === "acc") {
        row.append(act("Issues", async () => {
          const pp = prompt("ACC project ID to list issues from:");
          if (!pp || !pp.trim()) return;
          const r = await api.accIssues(cx.id, pp.trim());
          if (r.error) { msg.textContent = `ACC: ${r.error}`; return; }
          toast(`ACC: ${r.count ?? 0} issue(s) on project ${pp.trim()}`, "info");
        }));
      }
      if (!cx.builtin) {
        row.append(
          act("Test", async () => { detail.textContent = "testing…"; const r = await api.testConnection(cx.id); badge(r.status.ok); detail.textContent = r.status.detail + (r.info.project_count ? ` · ${r.info.project_count} projects` : ""); }),
          act("Delete", async () => { if (confirm(`Delete connection “${cx.name}”?`)) { await api.deleteConnection(cx.id); await render(); } }));
      }
      list.appendChild(row);
    }
    // --- add form ---
    const form = document.createElement("div"); form.style.cssText = "border:1px dashed var(--line);border-radius:8px;padding:10px;margin-top:6px";
    form.innerHTML = `<div class="meta" style="font-weight:600;color:var(--text);margin-bottom:6px">Add connection</div>`;
    const nu = document.createElement("input"); nu.placeholder = "name"; nu.className = "portal-filter"; nu.style.cssText = "width:100%;margin-bottom:6px";
    const ty = document.createElement("select"); ty.className = "portal-filter"; ty.style.cssText = "width:100%;margin-bottom:6px";
    for (const t of ["postgres", "supabase", "procore", "acc", "quickbooks", "sage", "viewpoint"]) { const o = document.createElement("option"); o.value = o.textContent = t; ty.appendChild(o); }
    const fields = document.createElement("div");
    const inputs: Record<string, HTMLInputElement> = {};
    const renderFields = () => {
      fields.textContent = ""; for (const k of Object.keys(inputs)) delete inputs[k];
      for (const f of TYPE_FIELDS[ty.value] || []) {
        const inp = document.createElement("input"); inp.className = "portal-filter"; inp.style.cssText = "width:100%;margin-bottom:6px";
        inp.placeholder = f.placeholder || f.label; if (f.secret) inp.type = "password";
        inputs[f.key] = inp; fields.appendChild(inp);
      }
    };
    ty.onchange = renderFields; renderFields();
    const cfg = () => Object.fromEntries(Object.entries(inputs).map(([k, i]) => [k, i.value]));
    const bar = document.createElement("div"); bar.style.cssText = "display:flex;gap:6px";
    const testBtn = document.createElement("button"); testBtn.className = "tool-btn"; testBtn.textContent = "Test";
    const testOut = document.createElement("span"); testOut.className = "meta"; testOut.style.fontSize = "11px";
    testBtn.onclick = async () => { testOut.textContent = "testing…"; try { const r = await api.testConnectionConfig(ty.value, cfg()); testOut.style.color = r.ok ? "#33d17a" : "#e2554a"; testOut.textContent = r.detail; } catch { testOut.textContent = "test failed"; } };
    const saveBtn = document.createElement("button"); saveBtn.className = "file-btn"; saveBtn.textContent = "Add";
    saveBtn.onclick = async () => { msg.textContent = ""; if (!nu.value.trim()) { msg.textContent = "name required"; return; } try { await api.createConnection(nu.value.trim(), ty.value, cfg()); nu.value = ""; renderFields(); await render(); } catch { msg.textContent = "could not add connection"; } };
    bar.append(testBtn, saveBtn, testOut);
    form.append(nu, ty, fields, bar);
    list.appendChild(form);
  };
  card.appendChild(msg);
  void render();
}

/** Read-only data browser for a SQL connection (local / Postgres / Supabase): table list +
 *  a SELECT console with a results grid. Closes the interoperability gap — data, not just config. */
function browseConnection(id: string, name: string) {
  const { card, msg } = modalShell(`Browse — ${name}`, 720);
  msg.style.color = "#e2554a";
  const tablesBox = document.createElement("div"); tablesBox.className = "meta"; tablesBox.textContent = "loading tables…";
  const sql = document.createElement("textarea"); sql.className = "portal-filter";
  sql.style.cssText = "width:100%;height:60px;font-family:ui-monospace,monospace;margin:8px 0";
  sql.placeholder = "SELECT … (read-only; SELECT/WITH only)";
  const runRow = document.createElement("div"); runRow.style.cssText = "display:flex;gap:8px;align-items:center";
  const run = document.createElement("button"); run.className = "file-btn"; run.textContent = "Run";
  const info = document.createElement("span"); info.className = "meta";
  runRow.append(run, info);
  const grid = document.createElement("div"); grid.style.cssText = "overflow:auto;max-height:46vh;margin-top:8px";

  const renderGrid = (cols: string[], rows: unknown[][]) => {
    if (!cols.length) { grid.innerHTML = `<div class="meta">no columns</div>`; return; }
    const th = cols.map((c) => `<th>${c}</th>`).join("");
    const tr = rows.map((r) => `<tr>${r.map((v) => `<td>${v == null ? "<span class='meta'>null</span>" : String(v).slice(0, 120)}</td>`).join("")}</tr>`).join("");
    grid.innerHTML = `<table class="portal-table"><thead><tr>${th}</tr></thead><tbody>${tr}</tbody></table>`;
  };
  const runSql = async (q: string) => {
    sql.value = q; msg.textContent = ""; info.textContent = "running…";
    const r = await api.connectionQuery(id, q, 200);
    if (r.error) { info.textContent = ""; msg.textContent = r.error; grid.innerHTML = ""; return; }
    info.textContent = `${r.row_count} row${r.row_count === 1 ? "" : "s"}`;
    renderGrid(r.columns ?? [], r.rows ?? []);
  };
  run.onclick = () => { if (sql.value.trim()) void runSql(sql.value.trim()); };

  void api.connectionTables(id).then((t) => {
    if (t.error) { tablesBox.textContent = ""; msg.textContent = t.error; return; }
    const names = t.tables ?? [];
    tablesBox.textContent = "";
    const label = document.createElement("span"); label.className = "meta"; label.textContent = `${names.length} tables — click to preview: `;
    tablesBox.appendChild(label);
    for (const n of names) {
      const b = document.createElement("button"); b.className = "tool-btn"; b.textContent = n; b.style.margin = "2px";
      b.onclick = () => void runSql(`SELECT * FROM "${n}"`);
      tablesBox.appendChild(b);
    }
  }).catch(() => { tablesBox.textContent = "could not list tables"; });

  card.append(tablesBox, sql, runRow, grid, msg);
}

/** Project-member management (project admins): grant/change role + party, set company, remove.
 * Complements the global "Manage users" panel — that creates accounts; this assigns them to a
 * project with a capability role (viewer/reviewer/editor/admin) and a workflow party. */
const PROJECT_ROLES = ["viewer", "reviewer", "editor", "admin"] as const;
const PARTY_ROLES = ["", "GC", "Owner", "OwnersRep", "Consultant", "Subcontractor"];
function membersModal(pid: string) {
  const { card, msg } = modalShell("Project members", 520);
  const list = document.createElement("div"); list.style.cssText = "display:flex;flex-direction:column;gap:6px";
  msg.style.color = "#e2554a";
  const sel = (opts: readonly string[], value: string) => {
    const s = document.createElement("select"); s.className = "portal-filter";
    for (const o of opts) { const op = document.createElement("option"); op.value = o; op.textContent = o || "— party —"; s.appendChild(op); }
    s.value = value; return s;
  };

  const render = async () => {
    list.textContent = "";
    let members: import("./api/client").ProjectMember[] = [];
    try { members = await api.members(pid); } catch { msg.textContent = "could not load members"; return; }
    for (const m of members) {
      const row = document.createElement("div");
      row.style.cssText = "display:flex;align-items:center;gap:8px;padding:6px 8px;border:1px solid var(--line);border-radius:6px";
      const nm = document.createElement("span"); nm.textContent = m.user; nm.style.cssText = "font-weight:600;min-width:90px";
      const meta = document.createElement("span"); meta.className = "meta"; meta.style.flex = "1";
      meta.textContent = m.company || "";
      const roleSel = sel(PROJECT_ROLES, m.role);
      const partySel = sel(PARTY_ROLES, m.party_role ?? "");
      const save = async () => {
        try { await api.addMember(pid, { user: m.user, role: roleSel.value as import("./api/client").ProjectRole, party_role: partySel.value || null, company: m.company }); await render(); }
        catch { msg.textContent = `could not update ${m.user}`; }
      };
      roleSel.onchange = save; partySel.onchange = save;
      const rm = document.createElement("button"); rm.className = "tool-btn"; rm.textContent = "Remove";
      rm.onclick = async () => {
        if (!confirm(`Remove ${m.user} from this project?`)) return;
        try { await api.removeMember(pid, m.user); await render(); }
        catch { msg.textContent = `could not remove ${m.user} (last admin?)`; }
      };
      row.append(nm, roleSel, partySel, meta, rm);
      list.append(row);
    }
  };

  // add-member form
  const form = document.createElement("div"); form.style.cssText = "display:flex;gap:6px;flex-wrap:wrap;align-items:center";
  const nu = document.createElement("input"); nu.placeholder = "username"; nu.className = "portal-filter"; nu.style.flex = "1";
  const nrole = sel(PROJECT_ROLES, "viewer");
  const nparty = sel(PARTY_ROLES, "");
  const nco = document.createElement("input"); nco.placeholder = "company (optional)"; nco.className = "portal-filter"; nco.style.flex = "1";
  const add = document.createElement("button"); add.className = "file-btn"; add.textContent = "Add";
  add.onclick = async () => {
    msg.textContent = "";
    if (!nu.value.trim()) { msg.textContent = "enter a username"; return; }
    try {
      await api.addMember(pid, { user: nu.value.trim(), role: nrole.value as import("./api/client").ProjectRole, party_role: nparty.value || null, company: nco.value.trim() || null });
      nu.value = ""; nco.value = ""; await render();
    } catch { msg.textContent = "could not add member"; }
  };
  form.append(nu, nrole, nparty, nco, add);

  const hint = document.createElement("div"); hint.className = "meta";
  hint.textContent = "Role = capability (viewer→admin). Party = workflow side (GC, Owner, …). The account must already exist (Manage users).";
  card.append(list, document.createElement("hr"), form, hint, msg);
  void render();
}

/** Read-only audit-trail viewer (global admins): filter by action/actor/since, newest first. */
function auditModal() {
  const { card, msg } = modalShell("Audit log", 620);
  msg.style.color = "#e2554a";
  const filters = document.createElement("div"); filters.style.cssText = "display:flex;gap:6px;flex-wrap:wrap;align-items:center";
  const fAction = document.createElement("input"); fAction.placeholder = "action contains…"; fAction.className = "portal-filter";
  const fActor = document.createElement("input"); fActor.placeholder = "actor contains…"; fActor.className = "portal-filter";
  const fSince = document.createElement("input"); fSince.type = "date"; fSince.className = "portal-filter"; fSince.title = "since (date)";
  const apply = document.createElement("button"); apply.className = "tool-btn"; apply.textContent = "Filter";
  filters.append(fAction, fActor, fSince, apply);
  const table = document.createElement("div"); table.style.cssText = "max-height:55vh;overflow:auto;margin-top:8px";

  const render = async () => {
    table.innerHTML = '<div class="meta">loading…</div>'; msg.textContent = "";
    let rows: import("./api/client").AuditEntry[] = [];
    try {
      rows = await api.auditLog({ action: fAction.value.trim() || undefined, actor: fActor.value.trim() || undefined,
        since: fSince.value || undefined, limit: 200 });
    } catch { table.innerHTML = ""; msg.textContent = "could not load audit log (admin only)"; return; }
    if (!rows.length) { table.innerHTML = '<div class="meta">no matching entries</div>'; return; }
    const cell = (s: string) => `<td style="padding:4px 8px;border-bottom:1px solid var(--line);white-space:nowrap">${s}</td>`;
    const esc = (s: string) => s.replace(/[<&]/g, (c) => (c === "<" ? "&lt;" : "&amp;"));
    table.innerHTML = `<table class="sens-table" style="width:100%;font-size:12px"><tr>` +
      `<th style="text-align:left">When</th><th style="text-align:left">Actor</th><th style="text-align:left">Action</th><th style="text-align:left">Detail</th></tr>` +
      rows.map((r) => `<tr>` +
        cell(new Date(r.ts).toLocaleString()) + cell(esc(r.actor ?? "—")) + cell(esc(r.action)) +
        `<td style="padding:4px 8px;border-bottom:1px solid var(--line);color:var(--muted)">${esc(r.detail ? JSON.stringify(r.detail) : (r.path ?? ""))}</td>` +
        `</tr>`).join("") + `</table>`;
  };
  apply.onclick = () => void render();
  fAction.onkeydown = fActor.onkeydown = (e) => { if (e.key === "Enter") void render(); };
  card.append(filters, table, msg);
  void render();
}

// ---- per-project RBAC capability gating -------------------------------------
// Reflect the caller's project role in the UI: tag actionable controls with data-cap
// ("review" | "edit") and hide those above the caller's role. The API still enforces;
// this just removes the "click → 403" rough edge. Fully open when RBAC is off / offline.
const CAP_RANK: Record<string, number> = { viewer: 0, reviewer: 1, editor: 2, admin: 3 };
let isProjectAdmin = false;   // gates the "Project members…" account-menu item
async function applyCapabilities() {
  let review = true, edit = true, admin = true;
  if (connected && projectId) {
    try {
      const m = await api.myRole(projectId);
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
  // viewer-only Pages/demo build has no backend — skip API probes (avoids /api/* 404s)
  const demo = !!import.meta.env.VITE_PAGES;
  connected = demo ? false : await api.health();
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
  if (projectId) connectNotifications();
  void applyCapabilities();
  if (!demo) void autoCheck();          // show a banner if a newer release is published
  if (!demo) {
    const conn = document.createElement("button");
    conn.className = "tool-btn"; conn.style.marginLeft = "6px"; conn.textContent = "🗄"; conn.title = "Data connections";
    conn.onclick = connectionsModal;
    toolbar.insertBefore(conn, statusEl);
    const gear = document.createElement("button");
    gear.className = "tool-btn"; gear.style.marginLeft = "6px"; gear.textContent = "⚙"; gear.title = "Settings";
    gear.onclick = settingsModal;
    toolbar.insertBefore(gear, statusEl);
    // single-operator local build: no accounts — the operator owns the site, admin UI is open
    let localMode = false;
    try { localMode = (await api.capabilities()).local_mode === true; } catch { /* default off */ }
    if (!localMode) void buildAuthControl();
  }
  // Help (?) — relaunch the welcome / tour, the guides, or the getting-started checklist
  const help = document.createElement("button");
  help.className = "tool-btn"; help.style.marginLeft = "6px"; help.textContent = "?"; help.title = "Help, tour & guides";
  help.onclick = () => { reopenChecklist(); showWelcome(onboardCtx()); };
  toolbar.insertBefore(help, statusEl);
  // field capture (mobile-first quick capture with offline queue) — needs the backend
  if (!demo) new FieldCapture(api, () => projectId).mount();
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

startup().finally(initNav);

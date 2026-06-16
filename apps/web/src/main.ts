import * as THREE from "three";
import CameraControls from "camera-controls";
import "./style.css";
import { createViewer } from "./viewer/world";
import { ModelLoader } from "./viewer/loader";
import { type ModelIdMap } from "./viewer/modelIds";
import { SelectionSets } from "./viewer/selectionSets";
import { MeasureTool, type MeasureMode } from "./tools/measure";
import { SectionTool } from "./tools/section";
import { VisibilityTool } from "./tools/visibility";
import { ColorizeTool } from "./tools/colorize";
import { LayerManager } from "./tools/layers";
import { OriginTool } from "./tools/origin";
import { buildTree } from "./tree/tree";
import { PinOverlay, restoreCamera } from "./pins/pins";
import { PortalUI } from "./portal/portal";
import { ProformaUI } from "./proforma/proforma";
import { ApiClient, type ElementProps, type Topic } from "./api/client";
import { toast, withLoading } from "./ui/feedback";

// ---- DOM refs ---------------------------------------------------------------
const $ = <T extends HTMLElement>(id: string) => document.getElementById(id) as T;
const container = $("container");
const statusEl = $("status");
const propsPanel = $("props");
const propsBody = $("props-body");
const toolbar = $("topbar");
$("props-close").addEventListener("click", () => void selectMap(null));
document.addEventListener("keydown", (e) => { if (e.key === "Escape" && !propsPanel.hidden) void selectMap(null); });
const setStatus = (m: string) => (statusEl.textContent = m);
/** status bar + a transient toast for notable events */
const notify = (m: string, kind: "info" | "success" | "error" = "info") => { setStatus(m); toast(m, kind); };

// ---- viewer + tools ---------------------------------------------------------
const viewer = createViewer(container);
const loader = new ModelLoader(viewer);
const sets = new SelectionSets(viewer.components);
const measure = new MeasureTool(viewer.components, viewer.world);
const section = new SectionTool(viewer.components, viewer.world);
const visibility = new VisibilityTool(viewer.components);
const colorize = new ColorizeTool(viewer.components);
const layerMgr = new LayerManager(viewer.components);
const origin = new OriginTool();
const api = new ApiClient();

let projectId: string | null = null;
let connected = false;
let selection: ModelIdMap | null = null;
let lastPoint: THREE.Vector3 | null = null;
let selectedGuid: string | null = null;
let modelCount = 0;
const nextId = () => `model-${++modelCount}`;

const SELECT_MAT = (): import("@thatopen/fragments").MaterialDefinition => ({
  color: new THREE.Color("#33d17a"), opacity: 1, transparent: false,
  renderedFaces: 1, preserveOriginalMaterial: false,
});

// ---- selection (shared by 3D click + tree + issues) -------------------------
async function selectMap(map: ModelIdMap | null, opts: { guid?: string; fit?: boolean } = {}) {
  if (selection) await loader.fragments.resetHighlight(selection);
  selection = map;
  if (!map) { propsPanel.hidden = true; return; }
  await loader.fragments.highlight(SELECT_MAT(), map);
  await loader.fragments.core.update(true);
  if (opts.fit) await fitToItems(map);
  await showProps(map, opts.guid);
}

async function showProps(map: ModelIdMap, guid?: string) {
  // prefer the API (Phase 1 index) when connected; fall back to in-model data
  if (connected && projectId && guid) {
    try {
      const el = await api.element(projectId, guid);
      renderProps(el);
      return;
    } catch { /* fall through */ }
  }
  const [modelId, ids] = Object.entries(map)[0] ?? [];
  if (!modelId) return;
  const model = loader.fragments.list.get(modelId);
  const localId = [...ids][0];
  if (!model || localId === undefined) return;
  const [data] = await model.getItemsData([localId], {
    attributesDefault: true,
    relations: { IsDefinedBy: { attributes: true, relations: true } },
    relationsDefault: { attributes: false, relations: false },
  });
  propsPanel.hidden = false;
  propsBody.textContent = JSON.stringify(data, null, 2);
}

function renderProps(el: ElementProps) {
  propsPanel.hidden = false;
  const lines = [
    `${el.ifc_class}  —  ${el.name ?? "(unnamed)"}`,
    `GUID: ${el.guid}`,
    `Type: ${el.type_name ?? "-"}    Storey: ${el.storey ?? "-"}`,
    "",
    ...Object.entries(el.psets).flatMap(([ps, props]) => [
      `[${ps}]`,
      ...Object.entries(props).map(([k, v]) => `  ${k}: ${v}`),
    ]),
  ];
  propsBody.textContent = lines.join("\n");
}

async function selectByGuid(guid: string, fit = false) {
  selectedGuid = guid;
  const map = await sets.fromGuids([guid]);
  await selectMap(map, { guid, fit });
}

// ---- 3D click ---------------------------------------------------------------
const mouse = new THREE.Vector2();
container.addEventListener("click", async (e) => {
  if (measure.mode !== "off") { measure.create(); return; }
  mouse.set(e.clientX, e.clientY);
  const hit = await loader.fragments.raycast({
    camera: viewer.world.camera.three, mouse, dom: viewer.world.renderer!.three.domElement,
  });
  // wall authoring mode: capture two ground points, then author the wall server-side
  if (wallMode) { await captureWallPoint(e, hit?.point ?? null); return; }
  if (!hit) { await selectMap(null); return; }
  lastPoint = hit.point.clone();
  showCoords(lastPoint);
  const [guid] = await hit.fragments.getGuidsByLocalIds([hit.localId]);
  selectedGuid = guid ?? null;
  await selectMap({ [hit.fragments.modelId]: new Set([hit.localId]) }, { guid: guid ?? undefined });
  setStatus(`selected ${guid ?? hit.localId}`);
});
container.addEventListener("dblclick", () => { if (section.enabled) section.createPlane(); });

// ---- file loading -----------------------------------------------------------
$("ifc-input").addEventListener("change", (e) => loadFile(e.target as HTMLInputElement, (b, id) => loader.loadIfc(b, id), "converting"));
$("frag-input").addEventListener("change", (e) => loadFile(e.target as HTMLInputElement, (b, id) => loader.loadFragments(b, id), "loading"));
$("convert-input").addEventListener("change", (e) => convertAndLoad(e.target as HTMLInputElement));
async function loadFile(input: HTMLInputElement, load: (b: Uint8Array, id: string) => Promise<unknown>, verb: string) {
  const file = input.files?.[0];
  if (!file) return;
  await withLoading(container, `${verb} ${file.name}`, async () => {
    await load(new Uint8Array(await file.arrayBuffer()), nextId());
    await fitToModels();
    notify(`loaded ${file.name}`, "success");
  });
  input.value = "";
}

// load a sample model frag served from public/
async function loadSample(file: string, label: string) {
  await withLoading(container, `loading ${label}`, async () => {
    const res = await fetch(file);
    if (!res.ok) throw new Error(`${label} not found`);
    await loader.loadFragments(await res.arrayBuffer(), nextId());
    await fitToModels();
    notify(`loaded ${label}`, "success");
  });
}

// Autodesk import (RVT/DWG/NWC): convert to .frag server-side (paid APS bridge) + cache
async function convertAndLoad(input: HTMLInputElement) {
  const file = input.files?.[0];
  input.value = "";
  if (!file) return;
  await withLoading(container, `converting ${file.name} (Autodesk bridge)`, async () => {
    const fd = new FormData(); fd.append("file", file);
    const res = await fetch(api.url("/convert"), { method: "POST", body: fd });
    if (!res.ok) {
      const msg = await res.json().catch(() => ({ detail: res.statusText }));
      throw new Error(msg.detail || "conversion unavailable");
    }
    await loader.loadFragments(await res.arrayBuffer(), nextId());
    await fitToModels();
    notify(`converted + loaded ${file.name}`, "success");
  });
}

// export helpers
function download(blob: Blob, name: string) {
  const a = document.createElement("a");
  a.href = URL.createObjectURL(blob); a.download = name; a.click();
  setTimeout(() => URL.revokeObjectURL(a.href), 1000);
}
async function exportFrag() {
  const id = [...loader.fragments.list.keys()][0];
  if (!id) { notify("no model loaded", "error"); return; }
  const buf = await loader.fragments.list.get(id)!.getBuffer(false);
  download(new Blob([buf]), `${id}.frag`);
  notify(`exported ${id}.frag`, "success");
}
function exportIfc() {
  if (!projectId) { notify("connect a project to export its IFC", "error"); return; }
  window.open(api.url(`/projects/${projectId}/source.ifc`), "_blank");
}

// ---- Open / Save dropdown menus --------------------------------------------
interface MenuItem { label: string; sep?: boolean; onClick?: () => void; }
function buildMenu(mountId: string, label: string, items: MenuItem[]) {
  const mount = $(mountId);
  const btn = document.createElement("button");
  btn.className = "file-btn menu-btn"; btn.textContent = label;
  const panel = document.createElement("div"); panel.className = "menu-panel"; panel.hidden = true;
  for (const it of items) {
    if (it.sep) { const s = document.createElement("div"); s.className = "menu-sep"; s.textContent = it.label; panel.appendChild(s); continue; }
    const mi = document.createElement("button"); mi.className = "menu-item"; mi.textContent = it.label;
    mi.onclick = () => { panel.hidden = true; it.onClick?.(); };
    panel.appendChild(mi);
  }
  // position: fixed so the panel escapes the toolbar's overflow clip at any breakpoint
  const place = () => { const r = btn.getBoundingClientRect(); panel.style.left = `${r.left}px`; panel.style.top = `${r.bottom + 4}px`; };
  btn.onclick = (e) => { e.stopPropagation(); closeMenus(panel); const open = panel.hidden; if (open) place(); panel.hidden = !open; };
  mount.append(btn, panel);
}
/** Close every open dropdown except `keep`. */
function closeMenus(keep?: Element) {
  document.querySelectorAll(".menu-panel").forEach((p) => { if (p !== keep) (p as HTMLElement).hidden = true; });
}
// Robust dismissal: capture phase fires before the viewer's camera controls can
// stopPropagation, and covers click-drags on the canvas that never emit a "click".
// Listen on both pointerdown and click so a dropdown can never get stuck open.
const dismissMenusIfOutside = (e: Event) => { if (!(e.target as HTMLElement).closest(".menu")) closeMenus(); };
document.addEventListener("pointerdown", dismissMenusIfOutside, true);
document.addEventListener("click", dismissMenusIfOutside, true);
window.addEventListener("blur", () => closeMenus());
document.addEventListener("keydown", (e) => { if (e.key === "Escape") closeMenus(); });
buildMenu("open-menu", "Open ▾", [
  { label: "Open IFC…", onClick: () => $("ifc-input").click() },
  { label: "Open Fragments (.frag)…", onClick: () => $("frag-input").click() },
  { label: "Sample models", sep: true },
  { label: "School — Structural", onClick: () => loadSample("/school_str.frag", "School (Structural)") },
  { label: "School — Architectural", onClick: () => loadSample("/school_arq.frag", "School (Architectural)") },
  { label: "BasicHouse", onClick: () => loadSample("/basichouse.frag", "BasicHouse") },
  { label: "Import (Autodesk — paid bridge)", sep: true },
  { label: "Revit (.rvt)…", onClick: () => $("convert-input").click() },
  { label: "AutoCAD (.dwg)…", onClick: () => $("convert-input").click() },
  { label: "Navisworks (.nwc)…", onClick: () => $("convert-input").click() },
]);
buildMenu("save-menu", "Save ▾", [
  { label: "Export Fragments (.frag)", onClick: () => void exportFrag() },
  { label: "Export source IFC (.ifc)", onClick: exportIfc },
]);

// ---- toolbar ----------------------------------------------------------------
const viewerTools = $("viewer-tools");
function toolBtn(icon: string, title: string, onClick: (b: HTMLButtonElement) => void) {
  const b = document.createElement("button");
  b.textContent = icon; b.className = "tool-btn icon-btn"; b.title = title;
  b.setAttribute("aria-label", title);
  b.onclick = () => onClick(b);
  viewerTools.appendChild(b);   // floating toolbar over the 3D viewport, not the top bar
  return b;
}
const setMeasure = (m: MeasureMode) => {
  measure.setMode(m);
  setStatus(`measure: ${m}`);
  const ro = document.getElementById("measure-readout");
  if (ro) ro.textContent = m === "off" ? "mode: off — labels show values in 3D" : `mode: ${m} — click points; values appear as 3D labels`;
};
toolBtn("↔", "Measure distance (M)", (b) => { const on = measure.mode !== "length"; setMeasure(on ? "length" : "off"); b.classList.toggle("on", on); });
toolBtn("▱", "Measure area (A)", (b) => { const on = measure.mode !== "area"; setMeasure(on ? "area" : "off"); b.classList.toggle("on", on); });
toolBtn("✂", "Section plane (S) — dbl-click a face", (b) => { section.enabled = !section.enabled; b.classList.toggle("on", section.enabled); setStatus(`section ${section.enabled ? "on (dbl-click face)" : "off"}`); });
toolBtn("⊙", "Isolate selection", () => selection && visibility.isolate(selection));
toolBtn("◐", "Color selection", () => selection && colorize.color(selection, "#ffb000"));
toolBtn("⊞", "Show all (H)", async () => { await visibility.showAll(); await colorize.reset(); });

// ---- modeling: author a wall from two ground clicks (server-side ifcopenshell) ----
let wallMode = false;
const wallPts: THREE.Vector3[] = [];
const groundPlane = new THREE.Plane(new THREE.Vector3(0, 1, 0), 0);
const groundRay = new THREE.Raycaster();
const wallBtn = toolBtn("▭", "Add wall (click two points)", (b) => { setWallMode(!wallMode); b.classList.toggle("on", wallMode); });

function setWallMode(on: boolean) {
  wallMode = on; wallPts.length = 0;
  wallBtn.classList.toggle("on", on);
  if (on) notify("wall: click the start point on the floor/grid", "info");
}

/** Project a screen click onto the y=0 ground plane (fallback when no geometry was hit). */
function screenToGround(e: MouseEvent): THREE.Vector3 | null {
  const dom = viewer.world.renderer!.three.domElement;
  const r = dom.getBoundingClientRect();
  const ndc = new THREE.Vector2(((e.clientX - r.left) / r.width) * 2 - 1, -((e.clientY - r.top) / r.height) * 2 + 1);
  groundRay.setFromCamera(ndc, viewer.world.camera.three);
  const pt = new THREE.Vector3();
  return groundRay.ray.intersectPlane(groundPlane, pt) ? pt : null;
}

async function captureWallPoint(e: MouseEvent, hitPoint: THREE.Vector3 | null) {
  const p = hitPoint ?? screenToGround(e);
  if (!p) { notify("couldn't pick a point — click on the floor or grid", "error"); return; }
  wallPts.push(p.clone());
  if (wallPts.length === 1) { notify("wall: click the end point", "info"); return; }
  const [a, b] = wallPts;
  const height = Number(prompt("Wall height (m):", "3.0")) || 3.0;
  const thickness = Number(prompt("Wall thickness (m):", "0.2")) || 0.2;
  setWallMode(false);
  if (!projectId) { notify("connect a project with a source IFC to author walls", "error"); return; }
  // plan coordinates: E = world x, N = -world z (matches the origin/coords convention)
  await withLoading(container, "authoring wall + republishing", async () => {
    try {
      const r = await api.editIfc(projectId!, "add_wall",
        { start: [a.x, -a.z], end: [b.x, -b.z], height, thickness }, true);
      notify(`wall authored (${String(r.changed).slice(0, 8)}) — model republished`, "success");
      await reloadModelPins();
    } catch (err) { notify(`author failed: ${(err as Error).message}`, "error"); }
  });
}

// ---- workspaces + left icon rail (replaces the old tab strip) ---------------
const appEl = document.getElementById("app")!;

// Model-workspace rail: each icon toggles a slide-out panel
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
    if (isActive) appEl.classList.add("rail-collapsed");   // click the active icon to collapse
    else showRail(it.key);
  };
  railEl.appendChild(b);
}

// Workspace switcher: Model (viewer) / Construction (GC portal) / Finance (proforma)
const WORKSPACES: { key: string; label: string }[] = [
  { key: "model", label: "Model" },
  { key: "construction", label: "Construction" },
  { key: "finance", label: "Finance" },
];
let currentWs = "model";
function setWorkspace(key: string) {
  currentWs = key;
  document.querySelectorAll(".ws-btn").forEach((b) => b.classList.toggle("active", (b as HTMLElement).dataset.ws === key));
  document.querySelectorAll(".workspace").forEach((w) => w.classList.toggle("active", w.id === `ws-${key}`));
  if (key === "construction") openPortalTab();
  if (key === "finance") openProformaTab();
  // the viewer container resizes from 0 when Model comes back into view
  if (key === "model") setTimeout(() => { viewer.world.renderer?.resize(); void loader.fragments.core.update(true); }, 0);
  localStorage.setItem("workspace", key);
}
const wsEl = $("workspaces");
for (const w of WORKSPACES) {
  const b = document.createElement("button");
  b.className = "ws-btn"; b.dataset.ws = w.key; b.textContent = w.label;
  b.onclick = () => setWorkspace(w.key);
  wsEl.appendChild(b);
}

// Finance sub-tabs (Proforma / Portfolio)
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

// ---- role-based navigation: gate workspaces + rail panels per persona -------
interface PersonaCfg { ws: string[] | null; rail: string[] | null; home: string; }
const PERSONAS: Record<string, PersonaCfg> = {
  all:           { ws: null, rail: null, home: "model" },
  developer:     { ws: ["finance", "model", "construction"], rail: ["issues", "tools", "tree"], home: "finance" },
  gc:            { ws: ["construction", "model", "finance"], rail: ["tree", "layers", "issues", "tools"], home: "construction" },
  architect:     { ws: ["model", "construction"], rail: ["tree", "layers", "issues", "tools"], home: "model" },
  engineer:      { ws: ["model"], rail: ["tree", "layers", "tools", "issues"], home: "model" },
  subcontractor: { ws: ["construction", "model"], rail: ["issues", "tools"], home: "construction" },
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
}
personaSel.value = localStorage.getItem("persona") || "all";
personaSel.onchange = () => applyPersona(personaSel.value, true);  // jump to the role's home workspace

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
    const w = Math.min(Math.max(ev.clientX - 46, 200), 560);  // minus the 46px icon column
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

// ---- bottom settings bar: view options persisted across sessions ------------
type Settings = {
  theme: "dark" | "light"; grid: boolean; projection: "Perspective" | "Orthographic";
  background: "dark" | "light" | "none"; zoomCursor: boolean;
  nav: "orbit" | "pan" | "cad"; units: "m" | "cm" | "mm" | "ft"; section: boolean;
};
const SETTINGS_DEFAULTS: Settings = {
  theme: "dark", grid: true, projection: "Perspective", background: "dark",
  zoomCursor: true, nav: "orbit", units: "m", section: false,
};
const settings: Settings = { ...SETTINGS_DEFAULTS, ...JSON.parse(localStorage.getItem("aec-settings") || "{}") };
const UNIT_FACTOR: Record<string, number> = { m: 1, cm: 100, mm: 1000, ft: 3.28084 };
const BG: Record<string, number | null> = { dark: 0x1e1f22, light: 0xf0f1f3, none: null };
const ACT = CameraControls.ACTION;

let savedTimer: number | undefined;
function flashSaved() {
  const el = document.getElementById("sb-saved"); if (!el) return;
  el.classList.add("show"); clearTimeout(savedTimer);
  savedTimer = window.setTimeout(() => el.classList.remove("show"), 1200);
}
function saveSettings() { localStorage.setItem("aec-settings", JSON.stringify(settings)); flashSaved(); }

function applySettings() {
  document.documentElement.dataset.theme = settings.theme === "light" ? "light" : "";
  viewer.grid.visible = settings.grid;
  void viewer.world.camera.projection.set(settings.projection);
  const bg = BG[settings.background];
  viewer.world.scene.three.background = bg === null ? null : new THREE.Color(bg);
  const c = viewer.world.camera.controls;
  c.dollyToCursor = settings.zoomCursor;
  if (settings.nav === "orbit") { c.mouseButtons.left = ACT.ROTATE; c.mouseButtons.right = ACT.TRUCK; c.mouseButtons.wheel = ACT.DOLLY; }
  else if (settings.nav === "pan") { c.mouseButtons.left = ACT.TRUCK; c.mouseButtons.right = ACT.ROTATE; c.mouseButtons.wheel = ACT.DOLLY; }
  else { c.mouseButtons.left = ACT.ROTATE; c.mouseButtons.middle = ACT.TRUCK; c.mouseButtons.wheel = ACT.ZOOM; }
  section.enabled = settings.section;
  showCoords(lastPoint);
  void loader.fragments.core.update(true);
}

function showCoords(p: THREE.Vector3 | null) {
  const el = document.getElementById("sb-coords"); if (!el) return;
  if (!p) { el.textContent = "—"; return; }
  const f = UNIT_FACTOR[settings.units] ?? 1, u = settings.units, d = u === "mm" ? 0 : 2;
  // model Y is up; report E=x, N=-z, Z=y to match the origin tool
  el.textContent = `E ${(p.x * f).toFixed(d)} · N ${(-p.z * f).toFixed(d)} · Z ${(p.y * f).toFixed(d)} ${u}`;
}

function buildStatusBar() {
  const bar = $("statusbar");
  const sep = () => { const d = document.createElement("span"); d.className = "sb-sep"; return d; };
  const toggle = (label: string, key: "grid" | "section" | "zoomCursor") => {
    const b = document.createElement("button"); b.className = "sb-toggle"; b.textContent = label;
    const sync = () => b.classList.toggle("on", !!settings[key]);
    b.onclick = () => { settings[key] = !settings[key]; sync(); applySettings(); saveSettings(); };
    sync(); return b;
  };
  const select = (label: string, key: "projection" | "theme" | "background" | "nav" | "units", opts: [string, string][]) => {
    const wrap = document.createElement("span"); wrap.className = "sb-group";
    const l = document.createElement("label"); l.textContent = label;
    const s = document.createElement("select"); s.className = "sb-sel";
    for (const [v, t] of opts) { const o = document.createElement("option"); o.value = v; o.textContent = t; s.appendChild(o); }
    s.value = String(settings[key]);
    s.onchange = () => { (settings[key] as string) = s.value; applySettings(); saveSettings(); };
    wrap.append(l, s); return wrap;
  };
  const fit = document.createElement("button"); fit.className = "sb-toggle"; fit.textContent = "⤢ Fit";
  fit.title = "Fit to view (F)"; fit.onclick = () => void fitToModels();
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
  const coords = document.createElement("span"); coords.id = "sb-coords"; coords.textContent = "—";
  const saved = document.createElement("span"); saved.id = "sb-saved"; saved.textContent = "✓ saved";
  bar.append(coords, saved);
}

// build the settings bar now; navigation init is deferred to the end of the module
// (initNav) because setWorkspace/applyPersona can call openPortalTab/openProformaTab,
// which reference the `portal`/`proforma` consts declared later (temporal dead zone).
showRail("tree");
buildStatusBar();
applySettings();
function initNav() {
  applyPersona(personaSel.value);
  const savedWs = localStorage.getItem("workspace");
  const allowWs = PERSONAS[personaSel.value]?.ws ?? null;
  setWorkspace(savedWs && (!allowWs || allowWs.includes(savedWs)) ? savedWs : currentWs);
}

// ---- camera fit -------------------------------------------------------------
async function fitToModels() {
  const box = new THREE.Box3();
  viewer.world.scene.three.traverse((o) => { const m = o as THREE.Mesh; if (m.isMesh) box.expandByObject(m); });
  if (box.isEmpty()) return;
  await viewer.world.camera.controls.fitToSphere(box.getBoundingSphere(new THREE.Sphere()), true);
  await loader.fragments.core.update(true);
}

/** Fit the camera to a specific selection set (used by isolate / tree / issue selection). */
async function fitToItems(map: ModelIdMap) {
  const boxes = await loader.fragments.getBBoxes(map);
  const box = new THREE.Box3();
  for (const b of boxes) box.union(b);
  if (box.isEmpty()) return;
  await viewer.world.camera.controls.fitToSphere(box.getBoundingSphere(new THREE.Sphere()), true);
  await loader.fragments.core.update(true);
}

// ---- panels (populated when connected) --------------------------------------
async function buildPanels() {
  if (!projectId) return;
  // Tree
  const elements: ElementProps[] = await api.elements(projectId, { limit: 5000 });
  const treePanel = $("panel-tree");
  treePanel.innerHTML = "";
  treePanel.appendChild(buildTree(elements, (guid) => selectByGuid(guid, false)));

  // Layers (by IFC class)
  const meta = await api.meta(projectId);
  const layersPanel = $("panel-layers");
  layersPanel.innerHTML = `<div class="section-title">IFC classes</div>`;
  for (const cls of meta.facets.classes) {
    const row = document.createElement("div");
    row.className = "layer-row";
    const cb = document.createElement("input"); cb.type = "checkbox"; cb.checked = true;
    const name = document.createElement("span"); name.className = "name"; name.textContent = cls;
    const swatch = document.createElement("span"); swatch.className = "swatch"; swatch.style.background = colorFor(cls);
    let layerId: string | null = null;
    const ensure = async () => (layerId ??= (await layerMgr.addClassLayer(cls, cls)).id);
    cb.onchange = async () => { await ensure(); await layerMgr.setVisible(layerId!, cb.checked); };
    swatch.onclick = async () => { await ensure(); await layerMgr.setColor(layerId!, colorFor(cls)); };
    name.onclick = async () => {
      await ensure();
      const layer = layerMgr.layers.get(layerId!);
      await layerMgr.isolate(layerId!);
      if (layer) await fitToItems(layer.items);
      setStatus(`isolated ${cls}`);
    };
    row.append(cb, swatch, name);
    layersPanel.appendChild(row);
  }

  // Issues / pins (BCF topics) + GC module record pins
  await refreshIssues();
  await reloadModelPins();
}

async function reloadModelPins() {
  if (!projectId) return;
  await pins.load(projectId);
  await pins.loadModulePins(projectId, async (pin) => {
    if (pin.element_guids?.[0]) await selectByGuid(pin.element_guids[0], true);
    setStatus(`${pin.ref} · ${pin.module_name} · ${pin.status}`);
  });
}

function buildToolsPanel() {
  const panel = $("panel-tools");
  panel.innerHTML = "";

  // --- Origin / CRS ---
  const o = document.createElement("div");
  o.innerHTML = `<div class="section-title">Working origin (E / N / Z)</div>`;
  const inputs: Record<string, HTMLInputElement> = {};
  const cur = origin.getOrigin();
  for (const k of ["e", "n", "z"] as const) {
    const row = document.createElement("div");
    row.className = "layer-row";
    const label = document.createElement("span"); label.className = "name"; label.textContent = k.toUpperCase();
    const inp = document.createElement("input"); inp.type = "number"; inp.value = String(cur[k]);
    inp.style.width = "110px";
    inputs[k] = inp;
    row.append(label, inp);
    o.appendChild(row);
  }
  const fromPt = document.createElement("button");
  fromPt.className = "tool-btn"; fromPt.textContent = "Set from selected point";
  fromPt.onclick = () => {
    if (!lastPoint) { setStatus("click a point first"); return; }
    inputs.e.value = lastPoint.x.toFixed(3); inputs.n.value = (-lastPoint.z).toFixed(3); inputs.z.value = lastPoint.y.toFixed(3);
  };
  const apply = document.createElement("button");
  apply.className = "tool-btn"; apply.textContent = "Apply origin"; apply.style.marginLeft = "6px";
  apply.onclick = async () => {
    origin.setOrigin({ e: +inputs.e.value, n: +inputs.n.value, z: +inputs.z.value });
    for (const [, model] of loader.fragments.list) origin.applyTo(model);
    await loader.fragments.core.update(true);
    if (connected && projectId) {
      fetch(api.url(`/projects/${projectId}`), {
        method: "PATCH", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ origin: origin.getOrigin() }),
      }).catch(() => {});
    }
    setStatus(`origin set to E${inputs.e.value} N${inputs.n.value} Z${inputs.z.value}`);
  };
  o.append(fromPt, apply);
  panel.appendChild(o);

  // --- Measure readout ---
  const m = document.createElement("div");
  m.innerHTML = `<div class="section-title" style="margin-top:14px">Measure</div>`;
  const readout = document.createElement("div"); readout.id = "measure-readout";
  readout.className = "meta"; readout.textContent = "mode: off — labels show values in 3D";
  const clr = document.createElement("button");
  clr.className = "tool-btn"; clr.textContent = "Clear current"; clr.style.marginTop = "6px";
  clr.onclick = () => measure.deleteCurrent();
  m.append(readout, clr);
  panel.appendChild(m);

  // --- Exports (Phase 5) ---
  const ex = document.createElement("div");
  ex.innerHTML = `<div class="section-title" style="margin-top:14px">Exports</div>`;
  if (!projectId) {
    const note = document.createElement("div"); note.className = "meta";
    note.textContent = "connect a project to export";
    ex.appendChild(note);
  } else {
    for (const [label, file] of [["Quantity takeoff (QTO/5D)", "qto"], ["COBie", "cobie"],
                                 ["Space schedule", "spaces"], ["4D schedule", "schedule"]] as const) {
      const b = document.createElement("button");
      b.className = "tool-btn"; b.textContent = `↓ ${label}`;
      b.style.display = "block"; b.style.margin = "4px 0"; b.style.width = "100%"; b.style.textAlign = "left";
      b.onclick = () => window.open(api.url(`/projects/${projectId}/exports/${file}.xlsx`), "_blank");
      ex.appendChild(b);
    }
  }
  panel.appendChild(ex);

  // --- Cost / Pay Apps (GC portal financials) ---
  const cst = document.createElement("div");
  cst.innerHTML = `<div class="section-title" style="margin-top:14px">Cost / Pay Apps</div>`;
  const cstOut = document.createElement("div"); cstOut.className = "meta"; cstOut.id = "cost-out";
  if (!projectId) {
    cstOut.textContent = "connect a project for cost roll-up";
    cst.appendChild(cstOut);
  } else {
    const sumBtn = document.createElement("button");
    sumBtn.className = "tool-btn"; sumBtn.textContent = "Σ Cost Summary";
    sumBtn.style.cssText = "display:block;margin:4px 0;width:100%;text-align:left";
    sumBtn.onclick = async () => {
      cstOut.textContent = "computing…";
      const s = await api.costSummary(projectId!);
      const m = (v: number) => `$${v.toLocaleString()}`;
      cstOut.innerHTML = `Budget ${m(s.budget)}<br>Committed ${m(s.committed)} (${s.pct_committed}%)<br>` +
        `Actual ${m(s.actual)} (${s.pct_spent}%)<br>Forecast ${m(s.forecast)}<br>` +
        `<b>Over/Under ${m(s.projected_over_under)}</b>`;
    };
    const g702Btn = document.createElement("button");
    g702Btn.className = "tool-btn"; g702Btn.textContent = "↓ G702/G703 Pay App (PDF)";
    g702Btn.style.cssText = "display:block;margin:4px 0;width:100%;text-align:left";
    g702Btn.onclick = () => window.open(api.url(`/projects/${projectId}/cost/g702.pdf?app_no=1`), "_blank");
    cst.append(sumBtn, g702Btn, cstOut);
  }
  panel.appendChild(cst);

  // --- Schedule visuals (Gantt + Line-of-Balance) ---
  const sch = document.createElement("div");
  sch.innerHTML = `<div class="section-title" style="margin-top:14px">Schedule</div>`;
  if (!projectId) {
    const n = document.createElement("div"); n.className = "meta"; n.textContent = "connect a project for schedule";
    sch.appendChild(n);
  } else {
    for (const [label, file] of [["Gantt chart", "gantt"], ["Line of Balance", "lob"]] as const) {
      const b = document.createElement("button");
      b.className = "tool-btn"; b.textContent = `▤ ${label}`;
      b.style.cssText = "display:block;margin:4px 0;width:100%;text-align:left";
      b.onclick = () => window.open(api.url(`/projects/${projectId}/schedule/${file}.svg`), "_blank");
      sch.appendChild(b);
    }
  }
  panel.appendChild(sch);

  // --- Coordination & QA (clash + IDS validation) ---
  const qa = document.createElement("div");
  qa.innerHTML = `<div class="section-title" style="margin-top:14px">Coordination & QA</div>`;
  const qaOut = document.createElement("div"); qaOut.className = "meta"; qaOut.id = "qa-out";
  if (!projectId) {
    qaOut.textContent = "connect a project to run analysis";
    qa.appendChild(qaOut);
  } else {
    const clashBtn = document.createElement("button");
    clashBtn.className = "tool-btn"; clashBtn.textContent = "⚡ Run clash (struct)";
    clashBtn.style.cssText = "display:block;margin:4px 0;width:100%;text-align:left";
    clashBtn.onclick = () => withLoading(container, "Running clash detection", async () => {
      const r = await api.runClash(projectId!, { a: "IfcBeam,IfcSlab", b: "IfcColumn", min_volume: 0.05 });
      qaOut.textContent = `${r.count} clashes — ${r.created_topics} topics created (see Issues)`;
      toast(`Clash: ${r.count} found, ${r.created_topics} topics created`, r.count ? "info" : "success");
      await refreshIssues();
      await reloadModelPins();
    });
    const idsBtn = document.createElement("button");
    idsBtn.className = "tool-btn"; idsBtn.textContent = "✓ Validate (IDS)";
    idsBtn.style.cssText = "display:block;margin:4px 0;width:100%;text-align:left";
    idsBtn.onclick = () => withLoading(container, "Validating (IDS)", async () => {
      const r = await api.validate(projectId!);
      toast(`IDS ${r.status.toUpperCase()} — ${r.summary.passed} pass / ${r.summary.failed} fail`,
            r.status === "pass" ? "success" : "error");
      const failing = r.specifications.flatMap((s) => s.failed_guids);
      qaOut.innerHTML = `<b>IDS: ${r.status.toUpperCase()}</b> — ${r.summary.passed} pass / ${r.summary.failed} fail<br>` +
        r.specifications.map((s) => `${s.status === "pass" ? "✓" : "✗"} ${s.name} (${s.passed}/${s.applicable})`).join("<br>");
      if (failing.length) {
        const hl = document.createElement("button");
        hl.className = "tool-btn"; hl.textContent = `Highlight ${failing.length} failures`; hl.style.marginTop = "6px";
        hl.onclick = async () => { const m = await sets.fromGuids(failing); await selectMap(m, { fit: true }); };
        qaOut.appendChild(document.createElement("br"));
        qaOut.appendChild(hl);
      }
    });
    qa.append(clashBtn, idsBtn, qaOut);
  }
  panel.appendChild(qa);

  // --- Energy & MEP analysis ---
  const an = document.createElement("div");
  an.innerHTML = `<div class="section-title" style="margin-top:14px">Energy & MEP</div>`;
  const anOut = document.createElement("div"); anOut.className = "meta"; anOut.id = "an-out";
  if (!projectId) {
    anOut.textContent = "connect a project for analysis";
    an.appendChild(anOut);
  } else {
    const eBtn = document.createElement("button");
    eBtn.className = "tool-btn"; eBtn.textContent = "⚡ Energy analysis";
    eBtn.style.cssText = "display:block;margin:4px 0;width:100%;text-align:left";
    eBtn.onclick = () => withLoading(container, "Analyzing building envelope", async () => {
      const e = await api.energy(projectId!);
      anOut.innerHTML = `<b>EUI ${e.eui_kwh_m2_yr} kWh/m²·yr</b><br>` +
        `Heating ${e.loads.design_heating_kw} kW · Cooling ${e.loads.design_cooling_kw} kW<br>` +
        `UA ${e.ua_w_per_k.total} W/K · annual ${e.annual_kwh.total.toLocaleString()} kWh<br>` +
        `floor ${e.areas_m2.conditioned_floor_area} m² · WWR ${e.areas_m2.window_wall_ratio}`;
      toast(`Energy: EUI ${e.eui_kwh_m2_yr} kWh/m²·yr`, "success");
    });
    const mBtn = document.createElement("button");
    mBtn.className = "tool-btn"; mBtn.textContent = "⚙ MEP inventory";
    mBtn.style.cssText = "display:block;margin:4px 0;width:100%;text-align:left";
    mBtn.onclick = async () => {
      const m = await api.mep(projectId!);
      anOut.innerHTML = `<b>${m.total_distribution_elements} distribution elements</b><br>` +
        Object.entries(m.by_class).map(([k, v]) => `${k}: ${v}`).join("<br>");
    };
    an.append(eBtn, mBtn, anOut);
  }
  panel.appendChild(an);

  // --- Authoring round-trip (Phase 6) ---
  const au = document.createElement("div");
  au.innerHTML = `<div class="section-title" style="margin-top:14px">Authoring (round-trip)</div>`;
  const auOut = document.createElement("div"); auOut.className = "meta"; auOut.id = "au-out";
  if (!projectId) {
    auOut.textContent = "connect a project to author";
    au.appendChild(auOut);
  } else {
    const fixBtn = document.createElement("button");
    fixBtn.className = "tool-btn"; fixBtn.textContent = "✎ Fix slabs: set LoadBearing";
    fixBtn.style.cssText = "display:block;margin:4px 0;width:100%;text-align:left";
    fixBtn.onclick = async () => {
      auOut.textContent = "editing IFC + republishing…";
      const r = await api.editIfc(projectId!, "set_pset",
        { ifc_class: "IfcSlab", pset: "Pset_SlabCommon", prop: "LoadBearing", value: true, dtype: "bool" }, true);
      const v = await api.validate(projectId!);
      auOut.innerHTML = `edited ${r.changed} slabs · republished<br><b>IDS now: ${v.status.toUpperCase()}</b> ` +
        `(${v.summary.passed} pass / ${v.summary.failed} fail)`;
    };
    const pubBtn = document.createElement("button");
    pubBtn.className = "tool-btn"; pubBtn.textContent = "⟳ Republish (reconvert + reindex)";
    pubBtn.style.cssText = "display:block;margin:4px 0;width:100%;text-align:left";
    pubBtn.onclick = async () => {
      auOut.textContent = "publishing…";
      const r = await api.publish(projectId!);
      auOut.textContent = `reconverted=${r.reconverted} · reindexed ${r.reindexed} elements`;
    };
    au.append(fixBtn, pubBtn, auOut);
  }
  panel.appendChild(au);

  // --- 2D documentation (plans / sections) ---
  const dr = document.createElement("div");
  dr.innerHTML = `<div class="section-title" style="margin-top:14px">Drawings (2D)</div>`;
  const drBody = document.createElement("div"); drBody.className = "meta";
  dr.appendChild(drBody);
  panel.appendChild(dr);
  if (projectId) void buildDrawings(drBody);
  else drBody.textContent = "connect a project for plans/sections";
}

async function buildDrawings(host: HTMLElement) {
  if (!projectId) return;
  host.textContent = "";
  const open = (path: string) => window.open(api.url(path), "_blank");
  const drawingBtn = (label: string, path: string) => {
    const b = document.createElement("button");
    b.className = "tool-btn"; b.textContent = label;
    b.style.cssText = "display:block;margin:4px 0;width:100%;text-align:left";
    b.onclick = () => open(path);
    host.appendChild(b);
  };
  try {
    const storeys = await api.drawingStoreys(projectId);
    for (const s of storeys) {
      const t = encodeURIComponent(`PLAN - ${s.name}`);
      drawingBtn(`▦ Plan: ${s.name}`,
        `/projects/${projectId}/drawings/plan.svg?elevation=${s.elevation}&cut_height=1.2&title=${t}`);
    }
    drawingBtn("⌗ Section A-A (X=27)",
      `/projects/${projectId}/drawings/section.svg?axis=x&offset=27&title=SECTION%20A-A`);
    for (const d of ["north", "south", "east", "west"]) {
      drawingBtn(`◰ Elevation: ${d}`, `/projects/${projectId}/drawings/elevation.svg?direction=${d}`);
    }
    const sep = document.createElement("div"); sep.className = "section-title";
    sep.style.marginTop = "8px"; sep.textContent = "Sheet (all plans + section)";
    host.appendChild(sep);
    drawingBtn("⊞ Compose sheet (PDF)", `/projects/${projectId}/drawings/sheet.pdf?sheet=S-101`);
    drawingBtn("⊞ Compose sheet (SVG)", `/projects/${projectId}/drawings/sheet.svg?sheet=S-101`);
  } catch {
    host.textContent = "drawings unavailable (no source IFC)";
  }
}

function colorFor(s: string): string {
  let h = 0; for (const c of s) h = (h * 31 + c.charCodeAt(0)) % 360;
  return `hsl(${h} 65% 55%)`;
}

const pins = new PinOverlay(viewer.components, viewer.world, api, async (topic, vp) => {
  restoreCamera(viewer.world, vp);
  if (topic.element_guids?.[0]) await selectByGuid(topic.element_guids[0]);
  setStatus(`restored: ${topic.title}`);
});

// GC portal — config-driven module list/form/record UI
const portal = new PortalUI($("panel-portal"), {
  api,
  projectId: () => projectId,
  anchorPoint: () => (lastPoint ? { x: lastPoint.x, y: lastPoint.y, z: lastPoint.z } : null),
  selectedGuid: () => selectedGuid,
  onSelectGuids: (guids) => { if (guids[0]) void selectByGuid(guids[0], true); },
  onPinsChanged: () => void reloadModelPins(),
  setStatus,
});
let portalReady = false;
function openPortalTab() {
  if (portalReady) return;
  portalReady = true;
  void portal.init();
}

// Proforma — real-estate development underwriting (independent of the BIM model)
const proforma = new ProformaUI($("panel-proforma"), api, setStatus, () => projectId);
let proformaReady = false;
function openProformaTab() {
  if (proformaReady) return;
  proformaReady = true;
  void proforma.init();
}

// Portfolio — multi-deal roll-up across solved proforma scenarios
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
}

async function refreshIssues() {
  if (!projectId) return;
  const topics = await api.pins(projectId);
  const panel = $("panel-issues");
  panel.innerHTML = `<div class="section-title">Issues (${topics.length})</div>`;
  const newBtn = document.createElement("button");
  newBtn.className = "tool-btn"; newBtn.textContent = "+ RFI from selection";
  newBtn.style.marginBottom = "8px";
  newBtn.onclick = createRfiFromSelection;
  panel.appendChild(newBtn);
  for (const t of topics) panel.appendChild(issueCard(t));
}

function issueCard(t: Topic): HTMLElement {
  const el = document.createElement("div");
  el.className = "issue";
  el.innerHTML = `<div class="t">${t.title}</div>
    <div class="meta"><span class="badge ${t.type}">${t.type}</span>
    <span class="badge ${t.status}">${t.status}</span> ${t.assignee ?? ""}</div>`;
  el.onclick = async () => {
    const vps = projectId ? await api.viewpoints(projectId, t.id) : [];
    restoreCamera(viewer.world, vps[0] ?? null);
    if (t.element_guids?.[0]) await selectByGuid(t.element_guids[0]);
  };
  return el;
}

async function createRfiFromSelection() {
  if (!projectId || !selection) { setStatus("select an element first"); return; }
  const [modelId, ids] = Object.entries(selection)[0];
  const model = loader.fragments.list.get(modelId);
  const localId = [...ids][0];
  const [guid] = model ? await model.getGuidsByLocalIds([localId]) : [null];
  const title = prompt("RFI title:", "New RFI") || "New RFI";
  const topic = await api.createTopic(projectId, {
    type: "rfi", title, status: "open",
    anchor: lastPoint ? { x: lastPoint.x, y: lastPoint.y, z: lastPoint.z } : undefined,
    element_guids: guid ? [guid] : undefined,
  });
  if (lastPoint) {
    await api.addViewpoint(projectId, topic.id, {
      camera: { type: "perspective", position: cameraPos(), target: { x: lastPoint.x, y: lastPoint.y, z: lastPoint.z }, fov: 60 },
      components: guid ? [guid] : [],
    });
  }
  await refreshIssues();
  await pins.load(projectId);
  setStatus(`created RFI: ${title}`);
}

function cameraPos() {
  const p = new THREE.Vector3();
  viewer.world.camera.controls.getPosition(p);
  return { x: p.x, y: p.y, z: p.z };
}

// which demo frag(s) back each project (by name) — federation handled per project
function fragsForProject(name: string): [string, string][] {
  if (/basichouse/i.test(name)) return [["/basichouse.frag", "BasicHouse-ARCH"]];
  if (/school/i.test(name)) return [["/school_str.frag", "school-STR"], ["/school_arq.frag", "school-ARQ"]];
  return [];
}

function buildProjectPicker(projects: { id: string; name: string }[]) {
  const sel = document.createElement("select");
  sel.className = "tool-btn"; sel.title = "Project";
  for (const p of projects) {
    const o = document.createElement("option");
    o.value = p.id; o.textContent = p.name; o.selected = p.id === projectId;
    sel.appendChild(o);
  }
  sel.onchange = () => { window.location.search = `?project=${sel.value}`; };  // reload into project
  toolbar.insertBefore(sel, statusEl);
}

// ---- startup ----------------------------------------------------------------
async function startup() {
  connected = await api.health();
  let projects: { id: string; name: string }[] = [];
  let projectName = "";
  if (connected) {
    projects = await api.projects();
    const wanted = new URLSearchParams(location.search).get("project");
    const chosen = projects.find((p) => p.id === wanted) ?? projects[0];
    projectId = chosen?.id ?? null;
    projectName = chosen?.name ?? "";
    setStatus(projectId ? `connected • ${projectName}` : "connected • no project");
    if (projects.length) buildProjectPicker(projects);
  } else {
    setStatus("offline — open a .frag to view (API not reachable)");
  }
  // load the chosen project's model frag(s) from public/
  const frags = projectName ? fragsForProject(projectName) : [["/school_str.frag", "school-STR"], ["/school_arq.frag", "school-ARQ"]];
  await withLoading(container, `Loading ${projectName || "model"}`, async () => {
    for (const [file, id] of frags) {
      const res = await fetch(file);
      if (res.ok) await loader.loadFragments(await res.arrayBuffer(), id);
    }
    await fitToModels();
  });
  if (projectId) {
    try { await buildPanels(); }
    catch (e) { console.warn("panels:", e); setStatus("connected (no properties index for this project)"); }
    connectNotifications();
  }
  buildToolsPanel();  // always render Tools, even if the data panels fail
}

// live notification badge on the Construction workspace tab (server-sent events)
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
  if (t && /^(INPUT|TEXTAREA|SELECT)$/.test(t.tagName)) return;  // don't hijack typing
  switch (e.key.toLowerCase()) {
    case "f": fitToModels(); break;
    case "escape": selectMap(null); break;
    case "m": measure.setMode(measure.mode === "length" ? "off" : "length"); setStatus(`measure: ${measure.mode}`); break;
    case "a": measure.setMode(measure.mode === "area" ? "off" : "area"); setStatus(`measure: ${measure.mode}`); break;
    case "s": section.enabled = !section.enabled; setStatus(`section ${section.enabled ? "on (dbl-click face)" : "off"}`); break;
    case "h": visibility.showAll(); colorize.reset(); break;
    case "\\": toggleRail(); break;
    case "?": toast(SHORTCUTS + " · \\ panel", "info", 6000); break;
    default: return;
  }
});

// debug hook for automated/preview testing
(window as unknown as Record<string, unknown>).__viewer = { viewer, loader, fitToModels, selectByGuid, THREE };

// run nav init AFTER startup connects, so restoring a saved Construction/Finance
// workspace opens the portal/proforma with a live projectId (not "connect a project").
startup().finally(initNav);

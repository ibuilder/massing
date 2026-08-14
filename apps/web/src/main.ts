import "./style.css";
import { PortalUI } from "./portal/portal";   // eager: the default Construction/Developer workspace
import { ApiClient, type MassingParams } from "./api/client";
import { toast, escapeHtml, safeUrl } from "./ui/feedback";
import { showResult } from "./ui/result";
import { buildRoomTabs, renderRoomTabs, roomForWorkspace } from "./shell/roomTabs";
import { offersReturn, returnLabel, returnTarget, returnTitle } from "./shell/wsReturn";
import { headerAction, renderHeaderAction } from "./shell/nextAction";
import { pinnedItems, renderPinnedRail } from "./shell/pinnedRail";
import { ROOM_HOST, destRoom } from "./shell/spine";
import { renderVitals } from "./shell/vitalsBar";
import { setRoomOpen } from "./portal/prefs";
import { autoCheck, checkForUpdates, currentVersion } from "./ui/update";
import { maybeResumeTour, maybeRolePrompt, maybeWelcome, showWelcome, valueMomentPrompt } from "./ui/onboarding";
import { mountChecklist, reopenChecklist } from "./ui/checklist";
import { FieldCapture } from "./field/field";
import { modalShell, confirmModal } from "./ui/modal";
import { askText } from "./ui/prompt";
import { buildMenu, closeMenus } from "./ui/menus";
// R26-V-LIVE: the repeatable render audit. Lazy + dev-only — it attaches window.__liveAudit() and
// nothing else; no app behaviour depends on it, and it stays out of the production bundle.
if (import.meta.env.DEV) void import("./dev/liveAudit").then((m) => m.installLiveAudit());
import { initCommandPalette, type Command } from "./ui/palette";
import { askFallback, elementCommands, reportCommands, verbCommands, type VerbSpec } from "./ui/paletteProviders";
import { shortGuid } from "./ui/elementCard";
import { buildAuthControl } from "./account/accountUI";
import { icon } from "./ui/icons";
import { jobLabel, mountJobTray } from "./ui/jobTray";
import { showKeyHelp } from "./ui/keys";
import { installErrorReporting } from "./errorReporting";
import type { Settings, ViewerApp } from "./viewer/app";

// ---- shell DOM + shared state (no three/@thatopen here — those load lazily) --
const $ = <T extends HTMLElement>(id: string) => document.getElementById(id) as T;
const container = $("container");
const statusEl = $("status");
const toolbar = $("topbar");
const setStatus = (m: string) => (statusEl.textContent = m);
const notify = (m: string, kind: "info" | "success" | "error" = "info") => { setStatus(m); toast(m, kind); };
const api = new ApiClient();
// Capture uncaught browser errors + promise rejections → server error-log feed (best-effort).
installErrorReporting((e) => api.reportClientError(e));

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
    // .e57 reality-capture: try the in-browser reader first (offline, no server round-trip); if the
    // scan uses an encoding it can't decode it throws E57Unsupported → fall back to the server converter.
    if (kind === "ref" && file.name.toLowerCase().endsWith(".e57")) {
      void (async () => {
        const { toast } = await import("./ui/feedback");
        const v = await ensureViewer();
        try {
          const { loadReferenceModel } = await import("./viewer/referenceLoader");
          const res = await loadReferenceModel(file);          // in-browser E57 decode
          v.addReferenceObject(res.object, file.name);
          toast(`Loaded E57 scan — ${res.info}`, "success");
          return;
        } catch (err) {
          if ((err as Error).name !== "E57Unsupported") {
            toast(`E57 import failed: ${(err as Error).message}`, "error");
            return;
          }
          // unsupported encoding → fall through to the server-side pye57 conversion
        }
        try {
          const st = await api.e57Status();
          if (!st.available) {
            toast(`This E57 uses an encoding the offline reader can't decode. ${st.message}`, "info");
            return;
          }
          toast("Converting E57 on the server…", "info");
          const xyz = await api.convertE57(file);
          const xyzFile = new File([xyz], file.name.replace(/\.e57$/i, ".xyz"), { type: "text/plain" });
          await v.openFile("ref", xyzFile);
        } catch (err) {
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
    void ensureViewer().then(async (v) => {
      await v.openFile(kind, file);
      // R28-UNIFY: a model and a project are one act. Until now this line was the end of the story —
      // the model rendered and every data panel still said "No project open", which is the split the
      // whole ring exists to close. Reference models ("ref") are overlays on someone else's project
      // and deliberately do NOT trigger it.
      if (kind === "ifc" || kind === "frag") await unifyAfterModelOpen(file.name);
    });
  });
}

/**
 * Tie the model just opened to a project — join an existing one, propose a new one, or explain why
 * neither is possible. The DECISION lives in `shell/openUnify` as a pure function with its own tests;
 * this is only the part that talks to the user and the server, so the logic that is easy to get wrong
 * is not tangled with the part that needs a browser to exercise.
 */
async function unifyAfterModelOpen(fileName: string): Promise<void> {
  const [{ decideModelOpen }, { toast }, { askConfirm }] = await Promise.all([
    import("./shell/openUnify"), import("./ui/feedback"), import("./ui/prompt"),
  ]);
  let known: { id: string; name: string; source_ifc?: string | null }[] = [];
  if (connected) {
    // A failed lookup must not be read as "the server has no projects" — that would propose a new
    // project over the top of an existing one. Fall back to viewer-only and say so.
    try { known = await api.projects(); } catch {
      toast("Opened in the viewer — could not reach the project list, so nothing was created", "info");
      return;
    }
  }
  const d = decideModelOpen({ connected, openProjectId: projectId, fileName, projects: known });
  if (d.intent === "viewer-only") { toast(`Viewer only — ${d.reason}`, "info"); return; }
  if (d.intent === "load-into-open") return;                    // already where it belongs; stay quiet
  if (d.intent === "attach-existing" && d.projectId) {
    const hit = known.find((p) => p.id === d.projectId);
    const ok = await askConfirm("Open the project for this model?", {
      body: `${d.reason}.

Opening “${hit?.name ?? d.projectId}” brings its RFIs, costs, schedule `
          + "and documents with the model.",
      okLabel: "Open project", cancelLabel: "Just view the model",
    });
    if (ok) window.location.search = `?project=${d.projectId}`;
    return;
  }
  const ok = await askConfirm("Create a project for this model?", {
    body: `${d.reason}.

A project is where this model's RFIs, costs, schedule and documents live. `
        + `It will be called “${d.suggestedName}” — you can rename it later.`,
    okLabel: "Create project", cancelLabel: "Just view the model",
  });
  if (!ok) return;
  try {
    const p = await api.createProject(d.suggestedName || "Untitled project");
    window.location.search = `?project=${p.id}`;
  } catch (err) {
    toast(`Could not create the project: ${(err as Error).message}`, "error");
  }
}

/**
 * Opt-in, offline-first basemap: prompts for a self-hosted XYZ tile-URL template + a focus lat/lon,
 * fetches a small tile grid and lays it on the ground as a reference overlay. Nothing loads unless the
 * operator supplies a tile server (honoring CLAUDE.md's "self-hosted tiles").
 */
async function addBasemapFlow() {
  const template = await askText("Add Basemap", {
    label: "Self-hosted tile URL template (XYZ), e.g. https://tiles.internal/{z}/{x}/{y}.png",
    value: "",
  });
  if (!template || !/\{z\}.*\{x\}.*\{y\}/.test(template)) {
    if (template) { const { toast } = await import("./ui/feedback"); toast("template must contain {z}/{x}/{y}", "error"); }
    return;
  }
  const ll = await askText("Basemap Focus", { label: "Focus latitude, longitude (decimal degrees)", value: "40.7484, -73.9857" });
  if (!ll) return;
  const [lat, lon] = ll.split(",").map((s) => parseFloat(s.trim()));
  if (lat === undefined || lon === undefined || !isFinite(lat) || !isFinite(lon)) { const { toast } = await import("./ui/feedback"); toast("invalid lat/lon", "error"); return; }
  const zoom = parseInt((await askText("Basemap Zoom", { label: "Zoom level (1–22)", value: "17" })) || "17", 10);
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

/**
 * SITE-1: opt-in open-geodata site context — OSM building footprints (height-extruded), roads and
 * land-use parcels around the project, as a separate reference layer. The server fetches Overpass
 * ONCE and caches the GeoJSON, so the viewer stays offline-capable afterwards. OSM data is ODbL —
 * the attribution is shown with the layer.
 */
async function addSiteContextFlow() {
  const { toast } = await import("./ui/feedback");
  if (!projectId) { toast("Open a project first", "info"); return; }
  const ll = await askText("Site Context (OSM)", {
    label: "Site latitude, longitude — leave blank to use the model's georeference (IfcSite)",
    value: "",
  });
  if (ll === null) return;                                    // cancelled
  let lat: number | undefined, lon: number | undefined;
  if (ll.trim()) {
    const parts = ll.split(",").map((s) => parseFloat(s.trim()));
    if (parts.length !== 2 || parts.some((v) => v === undefined || !isFinite(v))) { toast("invalid lat/lon", "error"); return; }
    [lat, lon] = parts as [number, number];
  }
  const radius = parseFloat((await askText("Site Context Radius", { label: "Radius in metres (50–2000)", value: "300" })) || "300");
  try {
    toast("Fetching site context (OSM)…", "info");
    const res = await api.siteContext(projectId, { lat, lon, radius });
    const gis = await import("./viewer/gis");
    const built = gis.buildSiteContext(res.geojson, res.lat, res.lon);
    const v = await ensureViewer();
    v.addReferenceObject(built.object, `site context — ${built.info}`);
    toast(`Site context added — ${built.info} · ${res.attribution}`, "success");
  } catch (e) {
    toast(`site context failed: ${(e as Error).message}`, "error");
  }
}

// ---- Open / Save dropdown menus (extracted to ./ui/menus) -------------------
const dismissMenusIfOutside = (e: Event) => { if (!(e.target as HTMLElement).closest(".menu")) closeMenus(); };
document.addEventListener("pointerdown", dismissMenusIfOutside, true);
document.addEventListener("click", dismissMenusIfOutside, true);
window.addEventListener("blur", () => closeMenus());
document.addEventListener("keydown", (e) => { if (e.key === "Escape") closeMenus(); });
// pre-warm the viewer when the file menus open so triggerOpen/export resolve promptly
// Ordered by what the thing IS, not by how it arrives. A project is the unit of work — it carries
// geometry, quantities, cost, schedule and issues — so the three ways to get one come first. Geometry
// and context are things you add TO a project, and read as such. "Sample models" stopped being its own
// category when a sample became a real `.mass` project rather than a bare mesh.
buildMenu("open-menu", "Open ▾", [
  { label: "Project", sep: true },
  { label: "✏️ New model from scratch…", onClick: () => void startModeling() },
  { label: "Open Project (.mass)…", onClick: () => void openProjectBundle() },
  { label: "Load sample project…", onClick: () => void openSampleLibrary() },
  { label: "Model geometry", sep: true },
  { label: "Open IFC…", onClick: () => openModelFile("ifc") },
  { label: "Open Fragments (.frag)…", onClick: () => openModelFile("frag") },
  { label: "Open mesh / point cloud / GIS / reality capture…", onClick: () => openModelFile("ref") },
  { label: "Site context", sep: true },
  { label: "Add basemap (self-hosted tiles)…", onClick: () => void addBasemapFlow() },
  { label: "Add site context (OSM buildings)…", onClick: () => void addSiteContextFlow() },
  { label: "Import from Revit / CAD", sep: true },
  { label: "Free: export IFC from Revit (no bridge)…", onClick: () => showFreeImportHelp() },
  { label: "Revit (.rvt) — paid Autodesk bridge…", onClick: () => void importRvtFlow() },
  { label: "AutoCAD (.dwg) — paid bridge…", onClick: () => openModelFile("convert") },
  { label: "Navisworks (.nwc) — paid bridge…", onClick: () => openModelFile("convert") },
], () => void ensureViewer());
buildMenu("save-menu", "Save ▾", [
  { label: "Project", sep: true },
  { label: "Save Project (.mass)", onClick: () => saveProjectBundle() },
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
  if (!(await confirmModal(`${st.cost_warning}\n\nPick a .rvt and convert it now?`, ""))) return;
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

/** Save the whole project (geometry + all data + blobs) as a portable `.mass` container. */
function saveProjectBundle() {
  if (!projectId) { toast("Open a project first", "info"); return; }
  const a = document.createElement("a");
  a.href = api.bundleUrl(projectId); a.download = `${projectName || "project"}.mass`;
  document.body.appendChild(a); a.click(); a.remove();
  toast("Saving project bundle…", "info");
}

/** Open a `.mass` container as a new project, then switch to it. Legacy `.mmproj` files (the
 *  container's name through v1) are still accepted — a rename must not orphan saved work. */
function openProjectBundle() {
  const inp = document.createElement("input");
  inp.type = "file"; inp.accept = ".mass,.mmproj,.zip,application/zip";
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

/**
 * The sample library — one entry replacing three hard-coded `.frag` files.
 *
 * Those three shipped geometry and nothing else: you could orbit a school and see no estimate, no
 * schedule, no RFIs. A sample is now a `.mass` container that opens as a **project**, through the
 * same `import_bundle` path a user's own file takes.
 *
 * The list is fetched, never hard-coded — that is the point. A hard-coded list is a promise that
 * drifts from what is actually packaged; `GET /samples` describes each container from its own
 * manifest, so what you see is what is there.
 */
async function openSampleLibrary() {
  let items: Awaited<ReturnType<typeof api.samples>>["samples"] = [];
  try {
    items = (await api.samples()).samples || [];
  } catch {
    toast("Couldn't reach the sample library", "error");
    return;
  }
  if (!items.length) {
    toast("No samples are packaged in this build", "info");
    return;
  }
  showResult("Sample projects", (body) => {
    const list = document.createElement("div");
    list.style.cssText = "display:flex;flex-direction:column;gap:8px";
    for (const s of items) {
      const row = document.createElement("button");
      row.className = "tool-btn";
      row.style.cssText = "display:block;text-align:left;padding:10px 12px;width:100%";
      // Counts come from the container's manifest, so the card cannot overstate what is inside.
      const bits = [
        s.elements ? `${s.elements} elements` : null,
        s.contents?.topic ? `${s.contents.topic} issues` : null,
        `${Math.round(s.bytes / 1024)} KB`,
      ].filter(Boolean).join(" · ");
      row.innerHTML = `<strong>${escapeHtml(s.name)}</strong>` +
        `<div style="opacity:.7;font-size:12px;margin-top:3px">${escapeHtml(bits)}</div>` +
        (s.readable ? "" : `<div style="color:var(--warn,#c80);font-size:12px">unreadable container</div>`);
      row.onclick = async () => {
        toast(`Opening ${s.name}…`, "info");
        try {
          const p = await api.openSample(s.id);
          window.location.search = `?project=${p.id}`;
        } catch {
          toast("Couldn't open that sample", "error");
        }
      };
      list.appendChild(row);
    }
    body.appendChild(list);
  });
}

// ---- workspaces + left icon rail --------------------------------------------
const appEl = document.getElementById("app")!;
// crisp inline SVG icons (currentColor) — replace the old cryptic ⌗/≣ glyphs
/**
 * RAIL-ICONS — the rail draws from the **vendored set**, and hand-draws nothing.
 *
 * Two icon languages had grown up side by side: hand-drawn 16×16 glyphs here, and the vendored Lucide
 * set in `ui/icons.ts` on Lucide's own 24×24 grid. Public icon-system guidance is blunt about why that
 * hurts — one grid, one stroke weight, one style — and mixing weights is described as destroying
 * cohesion instantly. RAIL-SPLIT made it worse before it made it better, adding seven icons here at
 * *two* different stroke weights.
 *
 * `ui/icons.ts` already stated the rule this file was breaking: *"Path data is copied verbatim from
 * the upstream SVGs — never redrawn by hand, because an icon redrawn from memory is a different icon
 * wearing the same name."* So this is now a **name map, not artwork**. Every rail item names an icon
 * in the vendored set; four the rail needed (`list-tree`, `pencil-ruler`, `download`, `file-text`)
 * were copied verbatim into that file rather than approximated here.
 *
 * The payoff is not only consistency. Those icons are `stroke="currentColor"` with no fill, so they
 * inherit the rail's text colour and are *structurally incapable* of introducing a second meaning for
 * blue — which is what the colour contract enforces everywhere else.
 *
 * A key with no mapping renders its first letter (see `railIcon`), because the previous shape
 * interpolated `undefined` straight into innerHTML and printed the literal word in the rail.
 */
const RAIL_ICON_NAME: Record<string, string> = {
  tree: "list-tree",        // the project browser IS a tree
  layers: "layers",
  view: "eye",              // how you look at the model
  build: "pencil-ruler",    // draw + dimension: the authoring verbs
  library: "palette",       // the Library palette, by its own name
  detail: "focus",          // zoom in on one connection
  props: "info",
  sheets: "panel-top",      // a sheet with its titleblock
  annotate: "pencil",
  export: "download",
  specs: "file-text",
  review: "scan",           // sweep the model for problems
  analyse: "search",        // look INTO it for an answer, rather than sweep it for faults
  issues: "flag",
  clash: "triangle-alert",
  // the rail's own chrome, keyed like a destination so it cannot drift off the set
  __collapse__: "chevron-left",
  __expand__: "chevron-right",
};

/** Inline SVG for a rail key, or the first letter when nothing is mapped. */
function railIcon(key: string, label: string): string {
  const name = RAIL_ICON_NAME[key];
  const el = name ? icon(name, 16) : null;
  return el ? el.outerHTML : `<span class="rail-ic-fallback">${label.slice(0, 1)}</span>`;
}

// Rail toggles grouped into three workflow clusters (Navigate / Author / Coordinate) — the taxonomy
// every mature authoring/coordination tool converges on. A subtle group label separates them.
/**
 * The viewer rail.
 *
 * `launch` marks an entry that opens a **full-page surface** instead of a side panel. Drawings and
 * Specs are the two: a sheet set needs the whole canvas, not a 280px column, so cramming them into
 * an `.rpanel` would have been the wrong shape for the sake of a uniform mechanism.
 *
 * They belong here because this is where an architect already is. Until now the only route to the
 * drawing set was the legacy workspace bar — from inside the model there was no way to reach the
 * drawings it generates, or the specs that describe them, without leaving the room. Model, drawings
 * and specifications are one person's work; the rail is where that becomes true on screen.
 */
/**
 * RAIL-SPLIT — twelve items, four clusters. One item, one job.
 *
 * Measured live on 2026-08-03: `panel-tools` held **182 buttons and 11 inputs under 7 headings**.
 * RAIL-TOOLBOX contributed 28 of those; the other 154 were already there, doing about ten unrelated
 * jobs — an element palette (~40), analysis and QA (~30), fabrication detail (~15), exports (~12),
 * drawings and sheets (~10), grids and levels (~10), annotation, federation, and a row of
 * deep-links the room tabs already provide.
 *
 * "Tools" was therefore not a category. It was the place a control went when nobody decided — the
 * same failure `rooms.py` records about the retired `Engineering` section, arriving in the rail
 * instead of the module list. A junk-drawer is invisible until something groups by it; the moment
 * this rail item had to be readable as a list of jobs, it stopped being one.
 *
 * Three of the new items are load-bearing for the rest of the arc rather than merely tidier:
 *   · **Library** must be its own item to become the drag SOURCE for placing elements.
 *   · **View** is exactly the set of tools that needs a canvas, so the 2D/3D switch belongs there.
 *   · **Export** is where "print 2D or 3D" lands once the two canvases are genuine peers.
 */
const RAIL_ITEMS: { key: string; label: string; title: string; cluster: string; launch?: () => void }[] = [
  { key: "tree", label: "Tree", title: "Model tree", cluster: "Navigate" },
  { key: "layers", label: "Layers", title: "Layers & visibility", cluster: "Navigate" },
  { key: "view", label: "View", title: "How you look at the model — section, measure, isolate, render, walk", cluster: "Navigate" },
  { key: "build", label: "Build", title: "Draw and change the model — grids, levels, modify, advanced authoring", cluster: "Author" },
  { key: "library", label: "Library", title: "Element & content palette — walls, doors, furniture, families", cluster: "Author" },
  // Detail and Annotate earn their items now that RAIL-SPLIT ② separated the `gridlevels` section
  // at the source — it had grown to hold five jobs (levels, the document set, annotation, the
  // content library, fabrication detail) behind one heading. They were deliberately withheld until
  // they would have contents: shipping an empty rail item is the precise failure the Work room had.
  { key: "detail", label: "Detail", title: "Fabrication detail — connections, rebar, MEP fittings", cluster: "Author" },
  { key: "props", label: "Props", title: "Properties — selected element", cluster: "Author" },
  { key: "sheets", label: "Drawings", title: "Drawing set & sheets", cluster: "Document",
    launch: () => setWorkspace("drawings", "jump") },
  { key: "annotate", label: "Annotate", title: "Notes, dimensions, tags, revision clouds", cluster: "Document" },
  { key: "export", label: "Export", title: "Drawings, sheets, schedules and exports — IFC, COBie, quantities, closeout", cluster: "Document" },
  { key: "specs", label: "Specs", title: "Specification sections", cluster: "Document",
    launch: () => openSpecs() },
  // R24-TOOLS-SPLIT: Review held BOTH "is the model right" (clash, QA, health, rules) and "what does
  // it tell you" (code, egress, cost, 4D), because both arrived inside one 1087-line `qa` tool-group
  // with no internal structure. The group is now cut in two at the source, so Analyse is a real item
  // with real contents rather than the one-button shell it would have been before the cut.
  { key: "review", label: "Review", title: "Check the model — clash, QA, health, rules, hygiene", cluster: "Coordinate" },
  { key: "analyse", label: "Analyse", title: "What the model tells you — code, egress, cost, 4D sequence, ask", cluster: "Coordinate" },
  { key: "issues", label: "Issues", title: "Issues / RFIs", cluster: "Coordinate" },
  // RAIL-SPLIT dropped this item and orphaned a whole surface: `buildClashPanel` still renders into
  // `panel-clash` on every persona change, but nothing activated it, so clash detection became
  // unreachable while looking perfectly healthy in the code. Clash keeps its OWN item rather than
  // folding into Review — it is a distinct job with its own run/inspect/raise-an-issue loop, and
  // burying a distinct job inside a broader one is precisely how "Tools" grew to 182 controls.
  { key: "clash", label: "Clash", title: "Clash detection & coordination", cluster: "Coordinate" },
];
const railEl = $("rail");
// The 14 items scroll; the Collapse toggle is pinned outside that scroller so it stays reachable at
// any window height. Before this the rail was one flex column and the toggle's `margin-top:auto`
// pushed it past the viewport into the status bar once RAIL-SPLIT grew the list.
const railItemsEl = document.createElement("div");
railItemsEl.id = "rail-items";
railEl.appendChild(railItemsEl);
function showRail(key: string) {
  appEl.classList.remove("rail-collapsed");
  document.querySelectorAll(".rail-btn").forEach((b) => b.classList.toggle("active", (b as HTMLElement).dataset.rail === key));
  document.querySelectorAll(".rpanel").forEach((p) => p.classList.remove("active"));
  $(`panel-${key}`).classList.add("active");
}
let lastCluster = "";
for (const it of RAIL_ITEMS) {
  if (it.cluster !== lastCluster) {   // a small cluster divider/label so the rail reads Navigate/Author/Coordinate
    lastCluster = it.cluster;
    const lbl = document.createElement("span");
    lbl.className = "rail-cluster"; lbl.textContent = it.cluster; lbl.setAttribute("aria-hidden", "true");
    // Tag the divider with its cluster so persona filtering can hide it when every item under it is
    // hidden. Without this a persona that allows none of a cluster's buttons still gets its heading:
    // v0.3.772 shipped a DOCUMENT label with nothing beneath it, which reads as a broken menu rather
    // than an absent one.
    lbl.dataset.cluster = it.cluster;
    railItemsEl.appendChild(lbl);
  }
  const b = document.createElement("button");
  b.className = "rail-btn"; b.dataset.rail = it.key;
  // An unmapped key must not print the literal string "undefined" beside the label — which is what
  // it did, visibly, the moment RAIL-SPLIT added items ahead of their icons. Fall back to the
  // label's first letter so a new item is legible and obviously unfinished rather than broken.
  const ic = railIcon(it.key, it.label);
  b.innerHTML = `<span class="rail-ic">${ic}</span><span class="rail-lbl">${it.label}</span>`;
  b.title = `${it.cluster} · ${it.title}`; b.setAttribute("aria-label", `${it.cluster}: ${it.title}`);
  b.onclick = () => {
    // A launcher opens a full surface and never becomes the rail's active *panel* — marking it
    // active would claim a side panel is showing when none is, which is the same lie that made a
    // `goto` destination unlandable in v0.3.770.
    if (it.launch) { it.launch(); return; }
    const isActive = b.classList.contains("active") && !appEl.classList.contains("rail-collapsed");
    if (isActive) appEl.classList.add("rail-collapsed");
    else showRail(it.key);
  };
  railItemsEl.appendChild(b);
}
// expand / collapse the rail to show labels (VS Code activity-bar style), persisted
const railExpand = document.createElement("button");
railExpand.className = "rail-btn rail-expand";
const syncExpand = () => {
  const on = appEl.classList.contains("rail-labeled");
  // The chevron comes from the same vendored set as every other rail glyph. It was the last
  // text character in a column of SVGs — a different weight, a different metric, and the one
  // place the "one icon language" claim was still false.
  railExpand.innerHTML = `<span class="rail-ic">${railIcon(on ? "__collapse__" : "__expand__", "")}</span><span class="rail-lbl">Collapse</span>`;
  railExpand.title = on ? "Collapse the rail" : "Expand the rail (show labels)";
  railExpand.setAttribute("aria-label", railExpand.title);
  railExpand.setAttribute("aria-expanded", String(on));
};
railExpand.onclick = () => {
  appEl.classList.toggle("rail-labeled");
  localStorage.setItem("rail-labeled", appEl.classList.contains("rail-labeled") ? "1" : "0");
  syncExpand();
};
// Labels are ON unless the user has explicitly collapsed the rail. This used to be opt-in, which
// meant a first-run user saw six anonymous icons and had no way to know one of them ("Author ·
// Model tools & authoring") opens 150+ authoring tools. Discoverability of the primary authoring
// surface is worth ~100px of canvas; anyone who disagrees collapses it once and that sticks.
if (localStorage.getItem("rail-labeled") !== "0") appEl.classList.add("rail-labeled");
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
/**
 * Human label for a workspace key, read from the tab that already names it — never a second list.
 *
 * **Ask the DOM the app actually renders.** The first version queried `.ws-btn[data-ws]`, a class
 * that does not exist anywhere in the running shell: the tab strip is `[data-room]` since the room
 * spine landed. Every lookup missed and every label silently fell back to the raw key, so the button
 * read "← Back to design" — lowercase, live, while the unit test passed. The test had mounted a
 * fixture containing `.ws-btn` elements, so it was asserting against a shell I invented rather than
 * the one that ships. Caught by driving the real app, not by the suite.
 *
 * Rooms name themselves, so they are the source. Workspaces with no room tab (`model`, `drawings`)
 * have no rendered name to borrow, and a capitalised key is an honest rendering of the key rather
 * than a second table that can drift away from the first.
 */
function wsLabel(key: string): string {
  const tab = document.querySelector<HTMLElement>(`[data-room="${key}"]`)
    ?? document.querySelector<HTMLElement>(`.ws-btn[data-ws="${key}"]`);
  const named = (tab?.textContent || "").trim();
  return named || key.charAt(0).toUpperCase() + key.slice(1);
}

/**
 * Render the return affordance at the top of a dead-end workspace.
 *
 * It names its destination — "← Back to Design", not a bare arrow — because a control that does not
 * say where it goes is only marginally better than no control: the user still has to try it to find
 * out, and the cost of guessing wrong is landing somewhere else they have to escape from.
 *
 * Idempotent, and it re-renders on every entry because the destination changes with the route taken.
 */
function renderReturnBar(wsKey: string): void {
  const host = document.getElementById(`ws-${wsKey}`);
  if (!host) return;
  const dest = returnTarget(previousWs, wsKey);
  let bar = host.querySelector<HTMLElement>(".ws-return");
  if (!bar) {
    bar = document.createElement("div");
    bar.className = "ws-return";
    host.prepend(bar);
  }
  bar.textContent = "";
  const back = document.createElement("button");
  back.type = "button";
  back.className = "tool-btn ws-return-btn";
  back.textContent = returnLabel(dest, wsLabel);
  back.title = returnTitle(dest, wsKey, wsLabel);
  back.onclick = () => setWorkspace(dest);
  bar.appendChild(back);
}

let currentWs = "model";
/**
 * R36-DRAWINGS-RETURN — the workspace you were in before this one.
 *
 * Drawings and Specs are **dead ends**: `drawings.ts` renders into its own workspace with no back
 * control and no route into the viewer, and Specs behaves the same. The only way out is knowing that
 * the tabs along the top are navigation — which is a thing you know only if someone told you, and it
 * is not what a person does when a screen has trapped them. They look for a way *back*.
 *
 * "Back" has to mean something true, so it is the workspace actually left, not a guessed home. A user
 * who reached Drawings from Design should land in Design; one who came from the model should land in
 * the model. Sending everyone to one hard-coded destination is the kind of wrong-but-plausible
 * behaviour that teaches people not to trust the control.
 */
let previousWs: string | null = null;
/**
 * `jump` marks an arrival driven by a control somewhere else — a rail launch — as opposed to the
 * user choosing a workspace from the nav. It is the difference Specs needed: Design is not a dead
 * end, but being *carried* into it from the model rail still leaves you with no way back.
 */
function setWorkspace(key: string, arrival: "jump" | "nav" = "nav") {
  // `previousWs` only advances on a real move, so on a no-op re-entry it still names some OLDER
  // workspace. Passing it anyway offered "← Back to Model" to someone who had navigated to Design
  // deliberately and merely re-triggered it — a way out of a room they were not trapped in.
  const moved = key !== currentWs;
  if (moved) previousWs = currentWs;
  currentWs = key;
  document.querySelectorAll(".ws-btn").forEach((b) => {
    const on = (b as HTMLElement).dataset.ws === key;
    b.classList.toggle("active", on);
    b.setAttribute("aria-selected", String(on));
  });
  document.querySelectorAll(".workspace").forEach((w) => w.classList.toggle("active", w.id === `ws-${key}`));
  showProjectHomeSignpost(key);
  if (key === "drawings") openDrawingsTab();
  // Render OR remove — never just render. The bar is a claim that this visit was a jump, and it used
  // to live only in `drawings`, where the claim is permanently true. Now that a normal workspace can
  // carry one, a bar left behind from a previous visit tells the next arrival they were carried here
  // when they walked in themselves, and offers a way out of a room they are not trapped in. Caught in
  // the running app, not by the suite: each unit test mounts a fresh DOM, so nothing persisted.
  if (offersReturn(key, moved ? previousWs : null, arrival)) renderReturnBar(key);
  else document.getElementById(`ws-${key}`)?.querySelector(".ws-return")?.remove();
  if (key === "studio") void openStudioTab();
  if (key === "design") openDesignTab();
  if (key === "construction") openPortalTab();
  if (key === "developer") openDeveloperTab();
  if (key === "finance") void openFinanceHomeTab();
  if (key === "model") void ensureViewer().then((v) => {
    v.onModelShown();
    // just started a model from scratch → open the authoring rail so the Draft tools are front-and-centre
    if (sessionStorage.getItem("author-open") === "1") {
      sessionStorage.removeItem("author-open");
      // Draw tools live in Build since RAIL-SPLIT; this named the deleted "tools" key, so the
      // guard was permanently false and starting a model from scratch opened nothing.
      if (RAIL_ITEMS.some((r) => r.key === "build")) showRail("build");
      setTimeout(() => v.openAuthoring?.(), 300);
    }
  });
  localStorage.setItem("workspace", key);
  syncStatusBarMode();      // the viewport controls belong to the viewport
}
// deep-link from a tool section to the workspace that owns the full records (e.g. Cost → Construction)
// "jump", not "nav": a deep-link is by definition a control in ANOTHER workspace carrying the user
// here, which is exactly the journey R36-DRAWINGS-RETURN's return bar exists for.
window.addEventListener("aec:workspace", (e) => {
  const key = (e as CustomEvent<string>).detail;
  if (WORKSPACES.some((w) => w.key === key)) setWorkspace(key, "jump");
});
const wsEl = $("workspaces");

/**
 * Switch to a room: go to the workspace that hosts it, then TELL the portal which room is active.
 *
 * ROOM-NAV (2026-08-02): this used to simulate the landing — a 4s poll clicking `[data-dest]` nodes
 * in a rail the workspace switch was concurrently rebuilding. The poll raced the rebuild and lost
 * visibly: Planning and Schedule rendered empty, Cost and Work showed the previous room's content.
 * Three prior comment blocks here each documented a subtler failure of the same approach (waiting
 * for the node, clicking the outgoing rail, abandoning on room change) — the approach was the bug.
 * The portal now owns an explicit active-room state, scopes its rail to it, and invokes the room's
 * home destination directly; `aec:room` is the entire handoff. `ROOM_HOST` moved to spine.ts beside
 * the tables it inverts.
 */
function goToRoom(roomId: string) {
  const host = ROOM_HOST[roomId] ?? "construction";
  setRoomOpen(`${host}:${roomId}`, true);   // composite key — the shape `buildNav` actually reads
  setWorkspace(host);
  paintRoomTabs(roomId);
  window.dispatchEvent(new CustomEvent("aec:room", { detail: roomId }));
}

/**
 * Paint the pinned rail. Reads `readFavs()`/`readRecents()` directly — they are the state, and a
 * copy held here would be a second answer to "what is pinned".
 */
function paintPinnedRail() {
  const host = document.getElementById("pinned-rail");
  if (!host) return;
  renderPinnedRail(host, pinnedItems(), null, (key) => {
    // A pin points at a destination, and destinations live in rooms — so open the room that owns it
    // rather than guessing a workspace. `destRoom` is the same mapping the portal rail uses.
    // `destRoom` returns the room id or null — a destination the map does not place falls to Work,
    // which is where anything unclassified belongs rather than nowhere.
    goToRoom(destRoom(key) ?? "work");
    setTimeout(() => {
      // `.portal-nav` scope is load-bearing. The pinned rail's own buttons carry `data-dest`, and
      // before the rail buttons had the attribute at all they were the ONLY matches — so this line
      // found the pin the user had just clicked and clicked it again. It never navigated anywhere.
      document.querySelector<HTMLElement>(`.portal-nav [data-dest="${CSS.escape(key)}"]`)?.click();
    }, 200);
  });
}

let roomTabsActive = "model";
function paintRoomTabs(active?: string) {
  if (active) roomTabsActive = active;
  renderRoomTabs(wsEl, buildRoomTabs(null, workQueueCount), roomTabsActive, goToRoom);
}

/** Ball-in-your-court count for the Work badge — the one number the tab bar carries. */
let workQueueCount: number | null = null;

/**
 * Fetch the ball-in-your-court count and repaint the Work badge.
 *
 * Fail-open and fire-and-forget: a badge is the least important thing on screen, and a navigation
 * bar that cannot render because a count request failed would be an absurd trade. `null` on failure
 * renders no badge rather than a zero — "we do not know" and "nothing owed" are different claims,
 * and showing 0 for the first is how somebody misses work.
 */
async function refreshWorkBadge(pid: string | null) {
  const host = document.getElementById("next-action");
  if (!pid) {
    workQueueCount = null;
    paintRoomTabs();
    if (host) renderHeaderAction(host, null, () => {});
    return;
  }
  try {
    const q = await api.workQueue(pid);
    workQueueCount = typeof q?.total === "number" ? q.total : null;
    // ONE fetch feeds both the badge and the header CTA. Two requests would be two answers, and the
    // count disagreeing with the action it summarises is the contradiction this shell is meant to
    // remove — see the single-sourced-numbers rule the portal already follows.
    if (host) {
      renderHeaderAction(host, headerAction(q), (a) => {
        goToRoom("work");
        // The queue rebuilds on the room switch, so scroll to the row afterwards rather than
        // against a node that is about to be replaced.
        setTimeout(() => {
          document.querySelector<HTMLElement>(`[data-ref="${CSS.escape(a.ref)}"]`)
            ?.scrollIntoView({ block: "center" });
        }, 250);
      });
    }
  } catch {
    workQueueCount = null;
    if (host) renderHeaderAction(host, null, () => {});
  }
  paintRoomTabs();
}

// The rooms ARE the navigation. They already existed as a sub-rail inside three of seven
// workspaces; this promotes them, it does not invent them. The workspace-button rail this replaced
// was removed with the `?shell=classic` opt-out in v0.3.779.
paintRoomTabs(roomForWorkspace(localStorage.getItem("workspace") || "model"));
paintPinnedRail();

document.querySelectorAll<HTMLButtonElement>(".fintab").forEach((t) => {
  t.onclick = () => {
    document.querySelectorAll(".fintab").forEach((x) => { x.classList.remove("active"); x.setAttribute("aria-selected", "false"); });
    document.querySelectorAll("#ws-finance .fullpanel").forEach((p) => p.classList.remove("active"));
    t.classList.add("active"); t.setAttribute("aria-selected", "true");
    $(`panel-${t.dataset.fin}`).classList.add("active");
    if (t.dataset.fin === "home") void openFinanceHomeTab();
    if (t.dataset.fin === "proforma") openProformaTab();
    if (t.dataset.fin === "portfolio") void openPortfolioTab();
  };
});

// ---- role-based navigation --------------------------------------------------
interface PersonaCfg { ws: string[] | null; rail: string[] | null; home: string; }
// RAIL-SPLIT — these allowlists name RAIL ITEMS, so splitting one item into seven silently
// removed all seven from every persona.
//
// `applyPersona` hides any rail button whose key is not listed. "tools" used to carry the whole
// authoring surface, so listing it was enough; when it became view/build/library/detail/annotate/
// export/review, every persona except `all` lost the lot — it hid exactly the panels the tool groups
// had just been moved into, and `all` (the only persona with `rail: null`) is what testing used.
// A key list beside a key definition is a second source of truth: when one grows, the other must.
const SPLIT_RAIL = ["view", "build", "library", "detail", "annotate", "export", "review", "analyse", "props", "clash"];
// `props` and `clash` join the shared list rather than each persona list: Properties is how you
// inspect ANY element and Clash is coordination every role consumes. Both were defined and listed
// by nobody, so both were hidden for every persona except `all` — found by the gate, not by the
// review, because "defined but unreferenced" reads as fine in a diff.
const PERSONAS: Record<string, PersonaCfg> = {
  all:           { ws: null, rail: null, home: "model" },
  developer:     { ws: ["developer", "finance", "model", "studio", "drawings", "design", "construction"], rail: ["issues", ...SPLIT_RAIL, "tree", "sheets", "specs"], home: "developer" },
  gc:            { ws: ["construction", "model", "drawings", "design", "finance"], rail: ["tree", "layers", "issues", ...SPLIT_RAIL, "sheets", "specs"], home: "construction" },
  // R1 — two GC flavors: the super lives in the field (model + construction), the PM in the office
  // (construction + finance). Same construction home; the portal nav opens each role's sections first.
  superintendent:  { ws: ["construction", "model", "drawings"], rail: ["issues", "tree", "layers", ...SPLIT_RAIL, "sheets", "specs"], home: "construction" },
  project_manager: { ws: ["construction", "design", "finance", "drawings", "model"], rail: ["tree", "issues", "layers", ...SPLIT_RAIL, "sheets", "specs"], home: "construction" },
  // architect/engineer home into the Design workspace (their design-phase seat); model + studio stay
  // one click away for authoring and the coordination/model-health tools.
  architect:     { ws: ["design", "model", "studio", "drawings", "construction"], rail: ["tree", "layers", "issues", ...SPLIT_RAIL, "sheets", "specs"], home: "design" },
  engineer:      { ws: ["design", "model", "studio", "drawings"], rail: ["tree", "layers", ...SPLIT_RAIL, "issues", "sheets", "specs"], home: "design" },
  subcontractor: { ws: ["construction", "model", "drawings"], rail: ["issues", ...SPLIT_RAIL, "sheets", "specs"], home: "construction" },
};
const personaSel = document.getElementById("persona") as HTMLSelectElement;
function applyPersona(p: string, goHome = false) {
  const cfg = PERSONAS[p] ?? PERSONAS.all ?? { ws: null, rail: null, home: "model" };
  document.querySelectorAll<HTMLButtonElement>(".ws-btn").forEach((b) => { b.hidden = !!cfg.ws && !cfg.ws.includes(b.dataset.ws!); });
  document.querySelectorAll<HTMLButtonElement>(".rail-btn").forEach((b) => { b.hidden = !!cfg.rail && !cfg.rail.includes(b.dataset.rail!); });
  // ...and a cluster heading follows its items. A label over nothing is worse than no label: it says
  // a section exists and then does not deliver it.
  document.querySelectorAll<HTMLElement>(".rail-cluster").forEach((lbl) => {
    const cluster = lbl.dataset.cluster;
    lbl.hidden = !RAIL_ITEMS.some((it) => it.cluster === cluster
      && (!cfg.rail || cfg.rail.includes(it.key)));
  });
  const allowedRail = cfg.rail ?? RAIL_ITEMS.map((r) => r.key);
  const activeRail = document.querySelector(".rail-btn.active") as HTMLElement | null;
  if (!activeRail || !allowedRail.includes(activeRail.dataset.rail!)) { const first = allowedRail[0]; if (first) showRail(first); }
  if (goHome || (cfg.ws && !cfg.ws.includes(currentWs))) setWorkspace(cfg.home);
  localStorage.setItem("persona", p);
  document.body.dataset.persona = p;
  window.dispatchEvent(new CustomEvent("aec:persona", { detail: p }));   // reorder the tools panel
}
personaSel.value = localStorage.getItem("persona") || "all";
// a manual choice sticks — it stops membership auto-selecting a persona on the next project open
personaSel.onchange = () => { localStorage.setItem("persona-manual", "1"); applyPersona(personaSel.value, true); };

// ---- rail collapse + drag-to-resize (persisted) -----------------------------
/**
 * Show/hide the side panel, and *say* which state it is in.
 *
 * A user asked what the ☰ button does, which is the whole finding: its only explanation was a
 * tooltip reading "Toggle panel" — it never named the panel, never said whether it was about to open
 * or close, and its shortcut rendered as `(\\)` because `\\` in HTML is two literal backslashes.
 * A control whose label is a verb with no object cannot be understood before clicking it.
 *
 * `aria-expanded` matters beyond screen readers here: it is the only machine-readable statement of
 * the panel's state, so a test can assert the button and the panel agree. Toggling a class and
 * leaving the label frozen is how a control ends up lying about what it will do.
 */
function toggleRail() {
  const collapsed = appEl.classList.toggle("rail-collapsed");
  const btn = document.getElementById("rail-toggle");
  if (btn) {
    btn.setAttribute("aria-expanded", String(!collapsed));
    const label = collapsed ? "Show side panel" : "Hide side panel";
    btn.setAttribute("aria-label", label);
    btn.title = `${label} (\\)`;      // one backslash: the actual key
  }
}
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
// A corrupted stored value must never brick the app at boot (this runs at module top level) —
// fall back to defaults instead of throwing during module evaluation.
let savedSettings: Partial<Settings>;
try { savedSettings = JSON.parse(localStorage.getItem("aec-settings") || "{}"); } catch { savedSettings = {}; }
const settings: Settings = { ...SETTINGS_DEFAULTS, ...savedSettings };
let savedTimer: number | undefined;
function flashSaved() {
  const el = document.getElementById("sb-saved"); if (!el) return;
  el.classList.add("show"); clearTimeout(savedTimer);
  savedTimer = window.setTimeout(() => el.classList.remove("show"), 1200);
}
function applyTheme() { document.documentElement.dataset.theme = settings.theme === "light" ? "light" : ""; }
function onSettingsChanged() { applyTheme(); if (viewerApp) viewerApp.applySettings(); localStorage.setItem("aec-settings", JSON.stringify(settings)); flashSaved(); }

/**
 * The vitals strip, and the viewport controls that used to own this space alone.
 *
 * Audit finding 13: Fit / Grid / Section / Orbit / Snap / Units were pinned to the bottom of every
 * room — "ten permanent controls, irrelevant on four of seven tabs, occupying the most valuable
 * strip of the window". They now live in `#sb-viewport`, shown only where there is something to
 * orbit; the strip itself belongs to the six vitals, which are relevant everywhere and are the one
 * continuous proof that all of this describes a single model.
 */
const VIEWER_WORKSPACES = new Set(["model", "drawings", "studio", "design"]);
let vitalsSeq = 0;

function paintVitals() {
  const host = document.getElementById("sb-vitals");
  if (!host || !projectId) { if (host) renderVitals(host, null); return; }
  const seq = ++vitalsSeq;
  void api.vitals(projectId)
    // Ignore a response that arrived after the user moved on — the strip is polled on every project
    // and workspace change, so an out-of-order reply would render another project's numbers.
    .then((v) => { if (seq === vitalsSeq) renderVitals(host, v); })
    .catch(() => { if (seq === vitalsSeq) renderVitals(host, null); });
}

/** Viewport controls belong to the viewport. Everywhere else the strip is the vitals. */
function syncStatusBarMode() {
  const vp = document.getElementById("sb-viewport");
  if (vp) vp.hidden = !VIEWER_WORKSPACES.has(currentWs);
}

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
  // The vitals come FIRST — they are the strip's reason to exist, and they are relevant in every
  // room. The viewport controls follow, in their own container, hidden outside the viewer.
  const vitalsHost = document.createElement("div");
  vitalsHost.id = "sb-vitals"; vitalsHost.className = "sb-vitals";
  vitalsHost.setAttribute("aria-label", "Project vitals");
  bar.appendChild(vitalsHost);

  const vp = document.createElement("div");
  vp.id = "sb-viewport"; vp.className = "sb-viewport";

  const fit = document.createElement("button"); fit.className = "sb-toggle"; fit.textContent = "⤢ Fit";
  fit.title = "Fit to view (F)"; fit.onclick = () => withViewer((v) => void v.fitToModels());
  vp.append(
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
  for (const [v = "", t = ""] of [["0", "off"], ["0.1", "0.1m"], ["0.5", "0.5m"], ["1", "1m"]]) {
    const o = document.createElement("option"); o.value = v; o.textContent = t; snapSel.appendChild(o);
  }
  snapSel.value = String(settings.snap);
  snapSel.onchange = () => { settings.snap = Number(snapSel.value); onSettingsChanged(); };
  snapWrap.append(snapL, snapSel);
  vp.append(snapWrap, sep());
  bar.appendChild(vp);
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
  onSelectGuids: (guids: string[]) => { const g = guids[0]; if (g) { setWorkspace("model"); withViewer((v) => void v.selectByGuid(g, true)); } },
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
function openDeveloperTab() {
  // Latch on a SUCCESSFUL init, never on "we called it once". Visiting this tab before the
  // project has loaded used to set the latch anyway, freezing "No project open" in place for
  // the rest of the session even though the project arrived moments later — a workspace that
  // is permanently empty because it was opened half a second too early.
  if (developerReady) return;
  void developerPortal.init().then((ok) => { developerReady = ok; });
}

// Design workspace (architect / engineer) — same config-driven engine, "design" workspace filter.
const designPortal = new PortalUI($("panel-portal-design"), portalHost);
designPortal.setWorkspace("design");
let designReady = false;
/** The in-flight init, so callers can AWAIT readiness instead of polling the DOM for it. */
let designInit: Promise<boolean> | null = null;
function openDesignTab() {
  // Same latch-only-on-success rule as openDeveloperTab.
  if (designReady) return;
  designInit ??= designPortal.init().then((ok) => { designReady = ok; return ok; });
  void designInit;
}
/**
 * Resolve once the Design portal has its modules — the one real asynchrony behind `openSpecs`.
 *
 * A failed init does not latch (same rule as above), so the promise is cleared on failure and the
 * next caller retries rather than waiting forever on a portal that never loaded.
 */
function whenDesignReady(): Promise<boolean> {
  if (designReady) return Promise.resolve(true);
  openDesignTab();
  return (designInit ?? Promise.resolve(false)).then((ok) => {
    if (!ok) designInit = null;
    return ok;
  });
}

// Developer portal's "Underwriting" shortcut → the proforma workspace
// Every dispatcher of this event is a control somewhere else sending the user to a workspace — the
// portal's "Open underwriting" → finance, a margin panel → model, and six more. Wiring the rule at
// the two rail launches only (v0.3.913) left all of them stranding the user exactly as Specs did,
// while the roadmap called the item complete. The EVENT is the journey; it does not need a list.
window.addEventListener("aec:goto-workspace", (e) => setWorkspace((e as CustomEvent).detail as string, "jump"));

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
/**
 * Open the specification sections — the written half of the documents.
 *
 * Specs are a register, so they live in the portal rather than beside the viewport, and `design` is
 * one of the three portal workspaces. Reaching them from the model means switching to the Design
 * room's portal and opening the `spec_section` register.
 *
 * **This used to poll-click the DOM, and the DOM was the wrong thing to talk to.** It retried up to
 * forty times at 100ms, clicking `.portal-nav [data-mod="spec_section"]` and re-reading the node's
 * class to find out whether the click had worked. Three things were wrong with that:
 *
 *   - **The selector is ambiguous.** A register appears in its room's list *and* in `🕘 Recent` once
 *     you have opened it, so `querySelector` returns whichever the nav happens to render first.
 *     Measured live: two matching nodes, both marked active, and the register **fetched twice** —
 *     two round-trips for `?limit=101` and two for `/views`, on every open.
 *   - **Clicking rebuilds the thing you clicked.** The handler calls `buildNav()`, which replaces the
 *     nav — so the node under the cursor is detached mid-flight. That is what made the retry loop
 *     look necessary, and it cost two wrong fixes in v0.3.766 and a reverted release in v0.3.770.
 *   - **It asks the view what the model did.** A class name is a rendering artefact; reading it back
 *     to infer state is the same mistake as trusting a screenshot over the data.
 *
 * The portal has always exposed `openModuleByKey` for exactly this (command palette, deep links). It
 * sets `activeKey`, opens the module and rebuilds the nav — the operation the loop was trying to
 * reconstruct through the UI. One call, no retries, no ambiguity, one fetch.
 *
 * The only genuine asynchrony left is the portal's own `init()`, so this awaits readiness rather
 * than guessing at it with a timer.
 */
function openSpecs() {
  // "jump", because the rail carried the user here — Design is a normal workspace, so nothing else
  // would have offered them a route back to the model they pressed Specs from.
  setWorkspace("design", "jump");
  void whenDesignReady().then(() => designPortal.openModuleByKey("spec_section"));
}

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
    ["Deals", String(p.deal_count)], ["Total cap", m(t.total_capitalization ?? null)],
    ["Total equity", m(t.total_equity ?? null)], ["Blended LTC", pc(t.blended_ltc ?? null)],
    ["Portfolio IRR", pc(t.portfolio_irr ?? null)], ["Portfolio EM", `${t.portfolio_equity_multiple ?? "—"}×`],
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

// Finance home — a command-center landing for the finance persona (mirrors the Developer/Design
// homes): the deal's returns + capital stack from the latest saved scenario and Sources & Uses, with
// quick-launches to the proforma editor, portfolio roll-up, and the investor memo/deck PDFs.
function openFinanceHomeTab() {
  const panel = document.getElementById("panel-home");
  if (!panel) return;                                    // defensive: never throw to a blank panel
  const m = (v: number | null | undefined) => (v == null ? "—" : "$" + Math.round(v).toLocaleString());
  const pc = (v: number | null | undefined) => (v == null ? "—" : (v * 100).toFixed(1) + "%");
  const kpi = (v: string, l: string, tone?: string) =>
    `<div class="kpi"><div class="kpi-v" style="font-size:17px${tone ? `;color:${tone}` : ""}">${v}</div><div class="kpi-l">${l}</div></div>`;

  // Render the full shell SYNCHRONOUSLY first — so the panel is never blank while data loads (or if it
  // never resolves offline). Data fills in afterward. Actions are always present (they don't need data).
  const pid = projectId;
  panel.innerHTML =
    `<div class="section-title">Finance — command center</div>`
    + (pid
      ? `<div class="meta" id="fin-home-scenario" style="margin-bottom:6px">Loading the latest scenario…</div>`
        + `<div class="kpi-grid" id="fin-home-kpis">`
        + kpi("—", "Equity IRR") + kpi("—", "Equity multiple") + kpi("—", "Project IRR")
        + kpi("—", "Yield on cost") + kpi("—", "NPV") + `</div>`
        + `<div id="fin-home-stack"></div>`
      : `<div class="meta">Open or create a project to see its finance command center — returns, capital stack, and the investor documents.</div>`)
    + `<div class="section-title" style="margin-top:14px">Open</div>`
    + `<div id="fin-home-actions" style="display:flex;gap:6px;flex-wrap:wrap;margin-top:4px"></div>`;

  const goFin = (fin: string) => () => document.querySelector<HTMLButtonElement>(`.fintab[data-fin="${fin}"]`)?.click();
  const openPdf = (path: string, name: string) => async () => {
    const { openPdfUrl, saveToDocuments } = await import("./drawings/openPdf");
    await openPdfUrl(api, api.url(path), name, { saveLabel: "Save to Documents", onSave: saveToDocuments(api, pid!) });
  };
  const actions = document.getElementById("fin-home-actions")!;
  const btn = (label: string, cls: string, on: () => void) => {
    const b = document.createElement("button"); b.className = cls; b.textContent = label; b.onclick = on; actions.appendChild(b);
  };
  btn("Proforma →", "file-btn", goFin("proforma"));
  btn("Portfolio →", "tool-btn", goFin("portfolio"));
  if (pid) {
    btn("📄 Investment memo", "tool-btn", openPdf(`/projects/${pid}/investment-memo.pdf`, "investment-memo.pdf"));
    btn("📊 Pitch deck", "tool-btn", openPdf(`/projects/${pid}/investment-deck.pdf`, "pitch-deck.pdf"));
  }
  if (!pid) return;

  // fill in returns + capital stack asynchronously; any failure leaves the shell intact
  void (async () => {
    const [scen, su] = await Promise.all([
      api.listScenarios(pid).catch(() => [] as Awaited<ReturnType<typeof api.listScenarios>>),
      api.sourcesUses(pid).catch(() => null),
    ]);
    if (projectId !== pid) return;                       // the user switched projects mid-load — bail
    const latest = scen.length ? scen[scen.length - 1] : null;
    const r = latest?.returns ?? {};
    const irr = r.equity_irr ?? null;
    const scEl = document.getElementById("fin-home-scenario");
    if (scEl) scEl.innerHTML = latest
      ? `Latest scenario: <b>${latest.name}</b>`
      : "No solved scenario yet — build one in the Proforma tab and its returns land here.";
    const kEl = document.getElementById("fin-home-kpis");
    if (kEl) kEl.innerHTML =
      kpi(pc(irr), "Equity IRR", irr != null && irr >= 0.15 ? "var(--status-good)" : irr != null && irr < 0.08 ? "var(--status-warn)" : undefined)
      + kpi(r.equity_multiple == null ? "—" : `${r.equity_multiple.toFixed(2)}×`, "Equity multiple")
      + kpi(pc(r.project_irr), "Project IRR") + kpi(pc(r.yield_on_cost), "Yield on cost") + kpi(m(r.npv), "NPV");
    const total = su?.total_uses ?? null, debt = su?.debt ?? null, equity = su?.equity ?? null;
    const stEl = document.getElementById("fin-home-stack");
    if (stEl && total && (debt || equity)) {
      const dPct = Math.round(((debt ?? 0) / total) * 100), ePct = 100 - dPct;
      stEl.innerHTML = `<div class="section-title" style="margin-top:12px">Capital stack</div>`
        + `<div role="img" aria-label="Capital stack: ${dPct}% senior debt, ${ePct}% equity" style="display:flex;height:26px;border-radius:6px;overflow:hidden;margin:6px 0;font-size:11px;color:#fff">`
        + `<div style="flex:${dPct};background:#8aa0b8;display:flex;align-items:center;justify-content:center">Debt ${dPct}%</div>`
        + `<div style="flex:${ePct};background:#16324f;display:flex;align-items:center;justify-content:center">Equity ${ePct}%</div></div>`
        + `<div class="meta">${m(debt)} senior debt · ${m(equity)} equity · ${m(total)} total`
        + (su && su.balanced === false ? ` · <span style="color:var(--status-warn)">sources ≠ uses</span>` : "") + `</div>`;
    }
  })();
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
    // B1: the welcome LEADS with sign-in (never walls) — reuse the topbar's sign-in modal
    signedIn: api.authed,
    signIn: () => { void import("./account/accountUI").then((m) => m.openSignIn()); },
    newProject: () => void newProject(),
    startModeling: () => void startModeling(),
    // Was a hard-coded geometry-only fragment path. One entry point for samples now, so the
    // shortcut and the menu cannot disagree about what "a sample" means.
    openSample: () => { void openSampleLibrary(); },
    generate: () => {
      setWorkspace("finance");
      // finance now lands on the Home tab — switch to the Proforma tab, then reveal the
      // "Generate from zoning" panel once it renders
      document.querySelector<HTMLButtonElement>('.fintab[data-fin="proforma"]')?.click();
      setTimeout(() => document.getElementById("pf-massing")?.scrollIntoView({ behavior: "smooth", block: "center" }), 400);
    },
  };
}

/** Create a blank project (no IFC) and switch to it — GC portal + proforma work immediately. */
async function newProject() {
  const name = await askText("New Project", { label: "New project name:" });
  if (!name || !name.trim()) return;
  try { const p = await api.createProject(name.trim()); window.location.search = `?project=${p.id}`; }
  catch { toast("Couldn't create project (sign in as an editor?)", "error"); }
}

/** Author-ready starting points for a new model. "blank" is an empty canvas (levels + ground datum);
 *  the rest generate a small, real, fully-editable IFC via the massing engine so you begin with
 *  structure to build on instead of a blank void. All open in the Model workspace ready to draw. */
const MODEL_TEMPLATES: { key: string; icon: string; title: string; desc: string; params?: MassingParams }[] = [
  { key: "blank", icon: "▦", title: "Blank canvas", desc: "3 levels + a ground datum. Draw everything from scratch." },
  { key: "office", icon: "🏢", title: "Office bay", desc: "A small framed structural bay (columns + beams + envelope) over 3 levels.",
    params: { name: "Office bay", use_type: "commercial", lot_width: 24, lot_depth: 18, far: 2.5, height_limit: 14, floor_to_floor: 4, frame: true, bay_m: 6, envelope: true, wwr: 0.4 } },
  { key: "residential", icon: "🏠", title: "Residential floor", desc: "One residential floor, double-loaded corridor with unit demising walls.",
    params: { name: "Residential floor", use_type: "residential", lot_width: 44, lot_depth: 16, far: 1.0, height_limit: 4, units: true, unit_layout: "corridor", avg_unit_m2: 60, envelope: true } },
  { key: "warehouse", icon: "🏭", title: "Warehouse shell", desc: "A large single-storey enclosed shed — a clear-span shell to fit out.",
    params: { name: "Warehouse shell", use_type: "commercial", lot_width: 60, lot_depth: 40, far: 1.0, height_limit: 9, floor_to_floor: 9, envelope: true } },
];

function pickModelTemplate(): Promise<typeof MODEL_TEMPLATES[number] | null> {
  return new Promise((resolve) => {
    const { card, close } = modalShell("Start a new model", 420);
    const intro = document.createElement("div"); intro.className = "meta";
    intro.textContent = "Pick a starting point — a blank canvas, or a small editable model with structure to build on. Everything is authored openBIM (real IFC).";
    card.appendChild(intro);
    let chosen: typeof MODEL_TEMPLATES[number] | null = null;
    const grid = document.createElement("div"); grid.style.cssText = "display:grid;grid-template-columns:1fr 1fr;gap:8px;margin-top:4px";
    for (const t of MODEL_TEMPLATES) {
      const b = document.createElement("button"); b.className = "file-btn"; b.type = "button";
      b.style.cssText = "text-align:left;padding:10px;display:flex;flex-direction:column;gap:3px;align-items:flex-start;height:100%";
      b.innerHTML = `<span style="font-size:15px">${t.icon} <b>${escapeHtml(t.title)}</b></span><span class="meta" style="font-size:11px;white-space:normal">${escapeHtml(t.desc)}</span>`;
      b.onclick = () => { chosen = t; close(); resolve(t); };
      grid.appendChild(b);
    }
    card.appendChild(grid);
    const cancel = document.createElement("button"); cancel.className = "tool-btn"; cancel.textContent = "Cancel"; cancel.style.marginTop = "4px";
    cancel.onclick = () => { close(); resolve(chosen); };
    card.appendChild(cancel);
  });
}

/** Start a new MODEL: pick a template (blank or a small editable starter), create the project, author
 *  the model, and land in the Model workspace ready to draw. The "make a model" entry point. */
async function startModeling() {
  const tpl = await pickModelTemplate();
  if (!tpl) return;
  const name = await askText("New model", { label: "Name your model:", value: tpl.params?.name ?? "New Model" });
  if (!name || !name.trim()) return;
  try {
    toast("Creating your model…", "info");
    const p = await api.createProject(name.trim());
    if (tpl.key === "blank" || !tpl.params) await api.createBlankModel(p.id, { name: name.trim(), storeys: 3 });
    else await api.generateMassing(p.id, { ...tpl.params, name: name.trim() });
    localStorage.setItem("workspace", "model");   // land in the Model workspace, ready to author
    sessionStorage.setItem("author-open", "1");    // signal the viewer to open the Draft/Author panel
    window.location.search = `?project=${p.id}`;
  } catch { toast("Couldn't start a model (sign in as an editor?)", "error"); }
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
    if (!cur || !(await confirmModal(`Delete project “${cur.name}” and all its data? This can't be undone.`, "", "Delete", true))) return;
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
        + ` <a class="ref-link" href="${safeUrl(l.manage_url)}" target="_blank" rel="noopener">massing.cloud</a>`;
    } else {
      lic.innerHTML = `<b>Licence:</b> ${escapeHtml(l.tier_label)} plan`
        + (l.key_configured ? ` · key ${escapeHtml(l.key_masked || "set")}` : " · no key (Free)")
        + (warn ? ` · <span style="color:#e2554a">invalid key format</span>` : "")
        + `<br><span style="opacity:.75">Unlocks: ${escapeHtml(unlocked)}</span>`
        + ` — <a class="ref-link" href="${safeUrl(l.manage_url)}" target="_blank" rel="noopener">manage at massing.cloud</a>`;
    }
    // CLOUD-BRIDGE: when online validation is configured, offer a "validate now" action (admin-gated
    // server-side; non-admins get a graceful 403 message). The shared secret is never shown here.
    if (l.cloud?.online) {
      const row = document.createElement("div"); row.style.cssText = "margin-top:6px;display:flex;gap:8px;align-items:center";
      const b = document.createElement("button"); b.className = "tool-btn"; b.textContent = "☁ Validate online";
      b.title = "Validate the recorded licence key against massing.cloud and apply the returned plan.";
      const msg = document.createElement("span"); msg.className = "meta"; msg.style.fontSize = "11px";
      b.onclick = async () => {
        msg.textContent = "checking massing.cloud…";
        try {
          const r = await api.licenseCloudCheck();
          if (!r.checked_online) { msg.textContent = `offline — ${r.error || "unreachable"} (plan unchanged)`; return; }
          msg.textContent = r.valid
            ? (r.applied ? `✓ valid — plan set to ${r.tier_after}` : `✓ valid — already on ${r.tier_after}`)
            : `✗ ${r.reason || "invalid"} — plan now ${r.tier_after}`;
        } catch (e) { msg.textContent = (e as Error).message; }
      };
      row.append(b, msg); lic.appendChild(row);
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
  intWrap.appendChild(body); card.appendChild(intWrap);

  // CACHE-CLEAR — the way out of a bad cache. This app CacheFirsts the engine bundles, the WASM and
  // .frag geometry because they are content-hashed and immutable; that is right, and it is exactly
  // why an escape hatch has to exist. Without one, a half-written response or a badly-updated service
  // worker becomes "clear your browser data", which nobody should have to be told.
  const cacheWrap = document.createElement("div");
  cacheWrap.innerHTML = '<div class="section-title" style="margin-top:12px">Local data</div>';
  const cacheNote = document.createElement("div"); cacheNote.className = "meta";
  cacheNote.style.cssText = "font-size:12px;margin-bottom:6px";
  cacheNote.textContent = "Clears downloaded geometry, cached pages and offline data. Your sign-in "
    + "and preferences are kept.";
  const clearBtn = document.createElement("button");
  clearBtn.className = "mini-btn"; clearBtn.textContent = "Clear cached data";
  const cacheOut = document.createElement("div"); cacheOut.className = "meta";
  cacheOut.style.cssText = "font-size:12px;margin-top:6px";
  clearBtn.onclick = async () => {
    clearBtn.disabled = true; clearBtn.textContent = "Clearing…";
    const { clearCaches } = await import("./ui/clearCache");
    const r = await clearCaches();
    // Report the counts, not "Done!" — a number is checkable and a reassurance is not.
    cacheOut.textContent = r.detail;
    cacheOut.style.color = r.failed.length ? "var(--err)" : "var(--muted)";
    clearBtn.textContent = "Reload to finish";
    clearBtn.disabled = false;
    clearBtn.onclick = () => location.reload();
  };
  cacheWrap.append(cacheNote, clearBtn, cacheOut);
  card.appendChild(cacheWrap); card.appendChild(msg);

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
// R24-ROLE-EXPLAIN. Controls above the caller's project role are tagged `data-cap`
// ("review" | "edit" | "admin"). They used to be hidden outright, which removed the
// "click → 403" rough edge but bought it with a worse one: a control nobody can see is a
// control nobody can learn exists, or ask to be granted. They are now DISABLED AND EXPLAINED —
// a missing button is a support ticket; a dimmed button that says what it needs is onboarding.
// The API remains the enforcement point; this is legibility, not security.
const CAP_RANK: Record<string, number> = { viewer: 0, reviewer: 1, editor: 2, admin: 3 };

/** The project role a capability requires, in the words the invite dialog uses. */
const CAP_NEEDS: Record<string, string> = {
  review: "Reviewer", edit: "Editor", admin: "Project admin",
};
let capParty: string | null = null;

/** True when `cap` is currently withheld. Read from the SAME `<body>` attribute the CSS uses — a
 *  parallel JS copy would be a second source of truth for one fact, and the two would eventually
 *  disagree about whether a control is disabled while it still looks disabled. */
function capOff(cap: string): boolean {
  const key = `cap${cap.charAt(0).toUpperCase()}${cap.slice(1)}`;
  return document.body.dataset[key] === "off";
}

/** Which capability, if any, is currently blocking this element. */
function blockedCap(el: Element | null): string | null {
  const host = (el as HTMLElement | null)?.closest?.("[data-cap]") as HTMLElement | null;
  const cap = host?.dataset.cap;
  return cap && capOff(cap) ? cap : null;
}

// One capture-phase listener covers every gated control, including ones rendered later — cheaper
// and more reliable than annotating each on creation and re-annotating on every panel rebuild.
document.addEventListener("click", (e) => {
  const cap = blockedCap(e.target as Element);
  if (!cap) return;
  e.preventDefault();
  e.stopPropagation();
  const needs = CAP_NEEDS[cap] ?? cap;
  // name the party too when we know it — "who do I ask" is the actual question behind the click
  const who = capParty ? ` You are on this project as ${capParty}.` : "";
  toast(`Needs ${needs} on this project.${who} Ask a project admin to change your role.`,
        "info", 5200);
}, true);

// Panels render long after applyCapabilities() runs, so a control created later would carry no
// aria-disabled — and a screen-reader user needs that BEFORE they act, not after. Annotating on
// focus is the cheapest way to be correct at the only moment it matters.
document.addEventListener("focusin", (e) => {
  const host = (e.target as HTMLElement | null)?.closest?.("[data-cap]") as HTMLElement | null;
  if (host) annotateCap(host);
}, true);

/** Mark one capability-gated control as disabled-with-a-reason (or clear it when granted). */
function annotateCap(el: HTMLElement): void {
  const cap = el.dataset.cap;
  if (!cap) return;
  if (capOff(cap)) {
    el.setAttribute("aria-disabled", "true");
    el.title = `Needs ${CAP_NEEDS[cap] ?? cap} on this project`;
  } else {
    el.setAttribute("aria-disabled", "false");
    if (el.title.startsWith("Needs ")) el.removeAttribute("title");
  }
}

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
        const r = m.role ? (CAP_RANK[m.role] ?? 0) : -1;
        review = r >= (CAP_RANK.reviewer ?? 0); edit = r >= (CAP_RANK.editor ?? 0); admin = r >= (CAP_RANK.admin ?? 0);
      }
    } catch { /* keep defaults (don't hide on a transient error) */ }
  }
  isProjectAdmin = admin && !!projectId;
  capParty = party;
  const b = document.body;
  b.dataset.capReview = review ? "on" : "off";
  b.dataset.capEdit = edit ? "on" : "off";
  b.dataset.capAdmin = admin ? "on" : "off";
  // aria-disabled, not `disabled`: a disabled button is removed from the tab order, which would put
  // the explanation out of reach of exactly the keyboard user most likely to need it
  for (const el of document.querySelectorAll<HTMLElement>("[data-cap]")) annotateCap(el);
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
    const stream = api.notificationStream(projectId, ({ count }) => {
      badge!.textContent = count > 0 ? String(count) : "";
      badge!.style.display = count > 0 ? "" : "none";
    }, (s) => {
      // surface a silent disconnect instead of the badge just going stale
      ws.title = s === "reconnecting" ? "Live notifications disconnected — reconnecting…" : "";
      badge!.style.opacity = s === "reconnecting" ? "0.5" : "";
    });
    window.addEventListener("pagehide", () => stream.close(), { once: true });
  } catch { /* SSE unsupported / offline */ }
}

// ---- keyboard shortcuts -----------------------------------------------------
const SHORTCUTS = "F fit · Esc clear · M dist · A area · S section · H show all · ? help";
window.addEventListener("keydown", (e) => {
  const t = e.target as HTMLElement;
  if (t && /^(INPUT|TEXTAREA|SELECT)$/.test(t.tagName)) return;
  const k = e.key.toLowerCase();
  if (k === "\\") { toggleRail(); return; }
  // R24-KEYS — `?` used to be a six-second toast of six viewer keys, while the viewer's own `?`
  // opened a modal of fourteen draw codes. Which help you got depended on whether the 3D bundle had
  // loaded, and neither mentioned ⌘K. One surface now, and it stays up until dismissed.
  //
  // The draw codes are only offered once the viewer is in memory: importing them eagerly would pull
  // viewer code into the startup bundle to populate a list that cannot be used yet anyway.
  if (k === "?") {
    // AUTH-SNAP-OVERRIDE — the one-shot snap codes ride along with the draw codes, and for the same
    // reason they must: `keysDyn` installs its OWN `?` listener once the viewer is loaded, so both
    // handlers answer this key. While they published the same list that was invisible; the moment one
    // of them knows about a section the other does not, `?` gives two different answers again — which
    // is the precise defect `ui/keys.ts` was written to end. Gated on `viewerApp` like the draw codes,
    // because neither does anything without an armed tool.
    void import("./viewer/keysDyn")
      .then(({ KEY_SHORTCUTS, SNAP_HELP }) =>
        showKeyHelp(viewerApp ? KEY_SHORTCUTS : [], viewerApp ? SNAP_HELP : []))
      .catch(() => showKeyHelp());
    return;
  }
  if (["f", "escape", "m", "a", "s", "h"].includes(k) && viewerApp) viewerApp.handleKey(k);
});

// ---- startup ----------------------------------------------------------------
async function startup() {
  // viewer-only Pages/demo build has no backend — reads are served from the bundled demo snapshot
  // (api routes them via IS_DEMO), so treat it as "connected" to load the sample project + panels.
  const demo = !!import.meta.env.VITE_PAGES;
  connected = demo ? true : await api.health();
  if (connected) {
    const projects = await api.projects();
    const wanted = new URLSearchParams(location.search).get("project");
    const chosen = projects.find((p) => p.id === wanted) ?? projects[0];
    projectId = chosen?.id ?? null;
    projectName = chosen?.name ?? "";
    setStatus(projectId ? `connected • ${projectName}` : "connected • no project — open a sample or ＋ New");
    buildProjectPicker(projects);   // always (shows ＋ New even with zero projects)

    // A first run should never land on an empty canvas. With zero projects there is nothing to
    // render, nothing to price and nothing to coordinate — the product looks like a blank viewer,
    // which is exactly the impression the sample library exists to prevent.
    //
    // The picker OPENS; it does not auto-import. Importing writes a real project into the user's
    // database, and doing that unasked on first load is a side effect nobody consented to — the
    // difference between "here is something to look at" and "I made you something". They pick.
    // Deliberately only when the list is EMPTY: somebody with projects opening the app wants their
    // work, not a demo.
    if (!demo && projects.length === 0) {
      void openSampleLibrary();
    }
  } else {
    setStatus(demo ? "demo — pick a sample from Open ▾ to view"
                   : "offline — open a .frag to view (API not reachable)");
  }
  void refreshWorkBadge(projectId);
  // The job tray is hidden until it has something to show, so it needs one poke per project or it
  // never appears — a built feature with no path to it is the failure this codebase keeps re-finding.
  // The project picker reloads the page, so startup() is the only project-change path there is.
  refreshJobs();
  paintVitals();            // the six numbers, refreshed whenever the project changes
  syncStatusBarMode();
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
    reports.onclick = () => openReports();
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
  // B2: a sign-in from the welcome reloads the page — resume straight into the tour instead.
  // B3: first signed-in boot → offer the role list so the workspace tailors itself immediately.
  setTimeout(() => {
    if (!maybeResumeTour()) maybeWelcome(onboardCtx());
    maybeRolePrompt({
      authed: api.authed,
      roles: [...personaSel.options].filter((o) => o.value !== "all")
        .map((o) => ({ id: o.value, label: o.textContent || o.value })),
      apply: (id) => { localStorage.setItem("persona-manual", "1"); personaSel.value = id; applyPersona(id, true); },
    });
  }, 600);
  // C2: publishing a model edit while signed out is the clearest "work worth saving" moment — one
  // gentle, dismissible nudge (never a wall, never repeated).
  window.addEventListener("aec:model-published", () => {
    if (!api.authed) valueMomentPrompt(() => void import("./account/accountUI").then((m) => m.openSignIn()));
  });
}

/** The three workspaces that host the project home — the room rail lives in these. */
const PORTAL_WORKSPACES = ["construction", "developer", "design"] as const;

/**
 * A visible way back to the project home from anywhere that is not it.
 *
 * The room rail is the default shell and renders correctly, and it was still possible to open a
 * project, look at the screen, and ask where it had gone — because reaching it meant knowing to pick
 * Construction, Developer or Design, and nothing said so. Landing on the persona's home fixes the
 * first visit; this fixes every visit after someone navigates away.
 *
 * Deliberately a **link back, not a redirect**. Somebody in the Model workspace is authoring and
 * moving them would be worse than leaving them; the fix for "I cannot find it" is a sign, not a
 * shove. It hides itself in the portal workspaces, where the rail is already on screen, and when no
 * project is open, where there is no home to go to.
 */
function showProjectHomeSignpost(key: string) {
  const id = "project-home-signpost";
  document.getElementById(id)?.remove();
  const hasProject = !!new URLSearchParams(location.search).get("project");
  if (!hasProject || (PORTAL_WORKSPACES as readonly string[]).includes(key)) return;

  const cfg = PERSONAS[personaSel?.value ?? "all"];
  const dest = (cfg?.ws ?? []).find((w) => (PORTAL_WORKSPACES as readonly string[]).includes(w))
    ?? (PORTAL_WORKSPACES as readonly string[]).find((w) => cfg?.ws == null || cfg.ws.includes(w))
    ?? "construction";

  const bar = document.createElement("button");
  bar.id = id;
  bar.type = "button";
  bar.className = "home-signpost";
  bar.title = "The project home: Design, Planning, Cost, Schedule, Deal, Work";
  bar.innerHTML = `<span aria-hidden="true">←</span> Project home`;
  bar.onclick = () => { setWorkspace(dest); localStorage.setItem("workspace", dest); };
  const host = document.querySelector(".ws-tabs, [role=\"tablist\"]") ?? document.body;
  host.appendChild(bar);
}

function initNav() {
  applyPersona(personaSel.value);
  const savedWs = localStorage.getItem("workspace");
  const cfg = PERSONAS[personaSel.value];
  const allowWs = cfg?.ws ?? null;
  // No saved choice -> the persona's declared HOME, not the module-level `currentWs` default.
  //
  // Every persona already names its seat (`home`), and nothing used it on load: a first-time user
  // landed in the Model workspace whatever their role, and the project home — which is the
  // default shell and has been rendering correctly all along — was reachable only by knowing to pick
  // Construction, Developer or Design. A default nobody is shown is not a default. `currentWs` stays
  // the last-resort fallback for a persona with no home declared.
  const fallback = cfg?.home ?? currentWs;
  setWorkspace(savedWs && (!allowWs || allowWs.includes(savedWs)) ? savedWs : fallback);
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
// R24-CMDK-VERBS — Elements and Reports were headings the palette could never fill, and authoring
// verbs were not in it at all. The providers are pure and live in `ui/paletteProviders.ts`; this is
// where they meet the app. See that file for why verbs dispatch to the real toolbar button.

/** Open the Report Center, loading it on demand — it is a modal, so the import can wait for a click. */
const openReports = (focusId?: string): void => {
  void import("./reportCenter").then((m) => m.openReportCenter(api, projectId, focusId));
};

/**
 * The toolbar's tool table, loaded with the viewer chunk rather than the shell.
 *
 * `commands()` is synchronous, so this is memoised the same way the report catalog is: kick the
 * import off at startup and read whatever has landed. Before it lands the Do section is short, which
 * is the correct behaviour anyway — the toolbar buttons it dispatches to do not exist yet either.
 */
let _tools: VerbSpec[] = [];
void import("./viewer/toolbarLayout").then((m) => { _tools = m.TOOLS; }).catch(() => { /* Do stays short */ });

/** The server's report catalog, fetched once. Empty until it lands — the section simply has no rows. */
let _reportCatalog: { id: string; name: string; group: string }[] = [];
void api.reports().then((r) => { _reportCatalog = r.reports; }).catch(() => { /* section stays empty */ });

/** Every `title` currently on a button in the document — the toolbar is built late and rebuilt often. */
function _installedTitles(): Set<string> {
  return new Set([...document.querySelectorAll<HTMLElement>("button[title]")].map((b) => b.title));
}

/** Click the real tool button. `title` is `viewer/toolbarLayout`'s key, so this cannot drift from it. */
function _clickTool(title: string): void {
  const btn = [...document.querySelectorAll<HTMLElement>("button[title]")].find((b) => b.title === title);
  if (btn) btn.click(); else toast("That tool isn't available right now", "info");
}

function _openElementByGuid(guid: string): void {
  if (!projectId) { toast("Open a project first", "info"); return; }
  const pid = projectId;
  showResult("Element " + shortGuid(guid), (body) => {
    void import("./ui/elementCard").then((m) => m.mountElementCard(body, api, pid, guid));
  });
}

function _openElementsOfClass(ifcClass: string): void {
  if (!projectId) { toast("Open a project first", "info"); return; }
  const pid = projectId;
  showResult(ifcClass, (body) => {
    body.textContent = "Loading…";
    void api.elements(pid, { ifc_class: ifcClass, limit: 200 }).then((els) => {
      body.innerHTML = "";
      if (!els.length) { body.textContent = `No ${ifcClass} in this model.`; return; }
      const head = document.createElement("div");
      head.className = "meta";
      head.textContent = `${els.length} element(s)`;   // textContent: the class name came from the user
      body.appendChild(head);
      for (const e of els) {
        const row = document.createElement("button");
        row.className = "tool-btn";
        row.style.cssText = "display:block;width:100%;text-align:left;margin:2px 0";
        row.textContent = `${e.name ?? ifcClass} · ${shortGuid(e.guid)}`;
        row.onclick = () => _openElementByGuid(e.guid);
        body.appendChild(row);
      }
    }).catch((err: Error) => { body.textContent = `failed: ${err.message}`; });
  });
}

const _palette = _embed ? null : initCommandPalette({
  commands: () => {
    const cmds: Command[] = [];
    for (const w of WORKSPACES) cmds.push({ id: "ws:" + w.key, label: "Go to " + w.label, hint: "Workspace", run: () => setWorkspace(w.key) });
    // Authoring/measuring/analysing verbs, but not `look` or `collaborate`: those are states you
    // toggle while watching the model, and reaching them through an overlay that closes itself is a
    // worse interaction than the button already on screen.
    const installed = _installedTitles();
    cmds.push(...verbCommands(_tools, {
      groups: ["author", "measure", "analyse"],
      present: (t) => installed.has(t),
      run: _clickTool,
    }));
    cmds.push(...reportCommands(_reportCatalog, (id) => openReports(id)));
    cmds.push(
      { id: "act:new", label: "New project", hint: "Action", run: () => void newProject() },
      { id: "act:ifc", label: "Open IFC…", hint: "Action", run: () => openModelFile("ifc") },
      { id: "act:ref", label: "Open mesh / point cloud / GIS / reality capture…", hint: "Action", run: () => openModelFile("ref") },
      { id: "act:reports", label: "Open Report Center", hint: "Action", run: () => openReports() },
      { id: "act:runs", label: "Run history", hint: "Action", run: () => openRunsInbox() },
      { id: "act:save", label: "Save Project (.mmproj)", hint: "Action", run: () => saveProjectBundle() },
      { id: "act:help", label: "Keyboard shortcuts / help", hint: "Action", run: () => toast(SHORTCUTS + " · ⌘K palette", "info", 6000) },
    );
    for (const m of portal.moduleList())
      cmds.push({ id: "mod:" + m.key, label: m.name, hint: m.section || "Module", run: () => openModuleFromPalette(m.key) });
    return cmds;
  },
  search: async (q) => {
    // Element rows are decided from the query alone — no request, so they appear even with the
    // record search offline, and they are the section a GlobalId query is actually asking for.
    const els = elementCommands(q, { openGuid: _openElementByGuid, openClass: _openElementsOfClass });
    if (!projectId) return els;
    try {
      const hits = await api.searchAll(projectId, q);
      return els.concat(hits.slice(0, 8).map((h) => ({
        id: "rec:" + h.id, label: `${h.ref} ${h.title ?? ""}`.trim(), hint: h.module_name || "Record",
        run: () => { setWorkspace("construction"); openPortalTab();
          const go = () => portal.openRecordByKey(h.module, h.id);
          if (portal.moduleList().length) go(); else setTimeout(go, 500); },
      })));
    } catch { return els; }
  },
  // The last row, always. "Ask" dispatches to the model's own plain-English tool, so a query that
  // matched nothing — or matched twelve things badly — still has somewhere to go.
  fallback: (q) => askFallback(q, () => _clickTool("Ask the model — plain-English questions about the data")),
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

// R24-JOB-TRAY — heavy work you can walk away from. The queue (`routers/jobs.py`) has been there for
// a long time and nothing in this app had ever called it, which is why exports and compiled sets
// still felt like foreground work. The whole feature lives in `ui/jobTray.ts`; this is the mount.
const _jobs = _embed ? null : mountJobTray({
  host: toolbar,
  fetch: () => (projectId ? api.jobs(projectId, 25) : Promise.resolve([])),
  artifactUrl: (j) => api.jobArtifactUrl(projectId!, j.id),
  // The completion notice is the point of the tray: it is what makes leaving safe.
  onSettled: (j) => notify(
    j.state === "error" ? `${jobLabel(j.kind)} failed — ${j.error ?? "no detail"}` : `${jobLabel(j.kind)} finished`,
    j.state === "error" ? "error" : "success"),
  onHistory: () => openRunsInbox(),
});

// R24-RUNS-INBOX phase 1 — the tray answers "what is happening now"; this answers "what happened
// before, and what changed". Pure computation over the jobs the queue already records, in
// `ui/runs.ts`; the four analyses the audit named still run in the foreground and are not queued yet,
// which the empty state says out loud rather than leaving the reader to wonder.
function openRunsInbox(): void {
  if (!projectId) { toast("Open a project first", "info"); return; }
  const pid = projectId;
  showResult("Run history", (body) => {
    body.textContent = "Loading…";
    // 200, not the tray's 25: this is a history, and the whole point is reaching back past what the
    // tray shows. The server caps it well below anything that would hurt.
    // Lazy: the history is a modal nobody opens on most sessions, and `ui/runs.ts` +
    // `ui/runsInbox.ts` are dead weight in the shell until they do. The public Pages build measures
    // the shell against a 320 KB budget derived from the demo corpus ceiling, and an eager import
    // here spent 2 KB of it on a screen that had not been asked for.
    void Promise.all([import("./ui/runsInbox"), api.jobs(pid, 200)])
      .then(([mod, jobs]) => mod.renderRunsInbox(body, jobs, jobLabel))
      .catch((e: Error) => { body.textContent = `Couldn't load run history: ${e.message}`; });
  });
}
/** Call after enqueuing work so the badge appears immediately rather than at the next open. */
export const refreshJobs = (): void => _jobs?.poke();

void startup().finally(() => { initNav(); if (_embed) setWorkspace("model"); });

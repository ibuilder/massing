// Heavy viewer module — dynamically imported by main.ts on first Model-workspace open,
// so the ~6MB three + @thatopen bundle never loads for users who only use the
// Construction (GC portal) or Finance (proforma) workspaces.
import * as THREE from "three";
import CameraControls from "camera-controls";
import { createViewer, renderMode, positionSun } from "./world";
import { sunAltAz, sunSceneDir } from "./solar";
import { ModelLoader } from "./loader";
import { loadReferenceModel } from "./referenceLoader";
import { buildElementProps, buildRawProps } from "./propsView";
import { type ModelIdMap } from "./modelIds";
import { showQrModal } from "../ui/qr";
import { askText } from "../ui/prompt";
import { confirmModal } from "../ui/modal";
import { SelectionSets } from "./selectionSets";
import { MeasureTool, type MeasureMode } from "../tools/measure";
import { SectionTool } from "../tools/section";
import { VisibilityTool } from "../tools/visibility";
import { ColorizeTool } from "../tools/colorize";
import { LayerManager } from "../tools/layers";
import { OriginTool } from "../tools/origin";
import { buildTree } from "../tree/tree";
import { installDraftPanel, type ArmedDraft, type DraftPanelHandle } from "./draft/draftPanel";
import { type FamilyDef } from "./draft/draftCatalog";
import { GridOverlay } from "./draft/gridOverlay";
import { DraftProxyLayer } from "./draft/draftProxy";
import { PinOverlay, restoreCamera } from "../pins/pins";
import { type ApiClient, type ElementProps, type Topic } from "../api/client";
import { fetchArrayBufferWithProgress, setLoadingLabel, toast, withLoading } from "../ui/feedback";
import { showResult, kvTable, metricGrid, resultNote } from "../ui/result";

/** View options the settings bar owns (in main) and the viewer applies. */
export type Settings = {
  theme: "dark" | "light"; grid: boolean; projection: "Perspective" | "Orthographic";
  background: "dark" | "light" | "none"; zoomCursor: boolean;
  nav: "orbit" | "pan" | "cad"; units: "m" | "cm" | "mm" | "ft"; section: boolean;
  snap: number;   // grid-snap increment in metres (0 = off) for authoring placement
};

/** What main passes in. */
export interface ViewerCtx {
  container: HTMLElement;
  api: ApiClient;
  projectId: string | null;
  connected: boolean;
  projectName: string;
  setStatus: (m: string) => void;
  notify: (m: string, kind?: "info" | "success" | "error") => void;
  getSettings: () => Settings;
}

/** What main calls back into. */
export interface ViewerApp {
  applySettings(): void;
  selectByGuid(guid: string, fit?: boolean): Promise<void>;
  reloadModelPins(): Promise<void>;
  fitToModels(): Promise<void>;
  refreshIssues(): Promise<void>;
  anchorPoint(): { x: number; y: number; z: number } | null;
  selectedGuidValue(): string | null;
  triggerOpen(kind: "ifc" | "frag" | "convert"): void;
  openFile(kind: "ifc" | "frag" | "convert" | "ref", file: File): Promise<void>;
  addReferenceObject(object: import("three").Object3D, label: string): string;
  loadSample(file: string, label: string): Promise<void>;
  exportFrag(): Promise<void>;
  exportIfc(): void;
  handleKey(key: string): boolean;
  onModelShown(): void;
}

const $ = <T extends HTMLElement>(id: string) => document.getElementById(id) as T;

/** Build the whole 3D app: viewer, tools, selection, panels, authoring. Self-initialises
 *  (loads the project model + builds its rail panels) at the end. */
export function initViewerApp(ctx: ViewerCtx): ViewerApp {
  const { container, api, connected } = ctx;
  const projectId = ctx.projectId;
  const setStatus = ctx.setStatus;
  const notify = ctx.notify;
  const propsPanel = $("props");
  const propsBody = $("props-body");

  const viewer = createViewer(container);
  const loader = new ModelLoader(viewer);
  // keep the federation list in sync whenever a model registers (fires after load completes)
  loader.fragments.list.onItemSet.add(() => refreshFederation());
  const sets = new SelectionSets(viewer.components);
  const measure = new MeasureTool(viewer.components, viewer.world);
  const section = new SectionTool(viewer.components, viewer.world);
  const visibility = new VisibilityTool(viewer.components);
  const colorize = new ColorizeTool(viewer.components);
  const layerMgr = new LayerManager(viewer.components);
  const origin = new OriginTool();

  let selection: ModelIdMap | null = null;
  let lastPoint: THREE.Vector3 | null = null;
  let selectedGuid: string | null = null;
  let modelCount = 0;
  // track a human label per loaded model so the federation panel can list disciplines
  const modelLabels = new Map<string, string>();
  // view-only reference overlays (meshes / point clouds) added alongside the fragment models
  const referenceModels = new Map<string, { object: THREE.Object3D; label: string }>();
  let refCount = 0;
  const nextId = (label?: string) => {
    const id = `model-${++modelCount}`;
    if (label) modelLabels.set(id, label);
    return id;
  };

  const SELECT_MAT = (): import("@thatopen/fragments").MaterialDefinition => ({
    color: new THREE.Color("#33d17a"), opacity: 1, transparent: false,
    renderedFaces: 1, preserveOriginalMaterial: false,
  });

  // ---- selection -----------------------------------------------------------
  async function selectMap(map: ModelIdMap | null, opts: { guid?: string; fit?: boolean } = {}) {
    if (selection) await loader.fragments.resetHighlight(selection);
    selection = map;
    if (!map) { propsPanel.hidden = true; return; }
    await loader.fragments.highlight(SELECT_MAT(), map);
    await loader.fragments.core.update(true);
    if (opts.fit) await fitToItems(map);
    await showProps(map, opts.guid);
  }

  // 5D inspector — appended under the property panel; populated on selection
  const props5d = document.createElement("div"); props5d.id = "props-5d";
  props5d.style.cssText = "margin-top:6px;font-size:11px;line-height:1.5";
  propsPanel.appendChild(props5d);

  // field-verification — mark the selected element installed/verified/deviation (Argyle-style QA)
  const propsVerify = document.createElement("div"); propsVerify.id = "props-verify";
  propsVerify.style.cssText = "margin-top:6px;font-size:11px;line-height:1.6";
  propsPanel.appendChild(propsVerify);

  async function renderVerify(guid: string) {
    propsVerify.innerHTML = "";
    if (!connected || !projectId || !guid) return;
    const setBtn = (label: string, status: string, color: string) => {
      const b = document.createElement("button");
      b.className = "file-btn"; b.textContent = label;
      b.style.cssText = `font-size:11px;padding:2px 8px;border-color:${color}`;
      b.onclick = async () => {
        try {
          await api.setVerification(projectId!, guid, { status });
          lbl.textContent = ` ${label}`; lbl.style.color = color;
          setStatus(`element marked ${status}`);
        } catch (e) { setStatus("verify failed: " + (e as Error).message); }
      };
      return b;
    };
    const row = document.createElement("div");
    row.style.cssText = "border-top:1px solid var(--line);padding-top:6px";
    row.innerHTML = `<div style="font-weight:700">Field verification</div>`;
    const bar = document.createElement("div"); bar.style.cssText = "display:flex;gap:4px;align-items:center;flex-wrap:wrap;margin-top:3px";
    bar.append(setBtn("Installed", "installed", "#4a8cff"), setBtn("Verified", "verified", "#33d17a"),
               setBtn("Deviation", "deviation", "#e2554a"));
    const lbl = document.createElement("span"); lbl.className = "meta";
    bar.appendChild(lbl);
    row.appendChild(bar); propsVerify.appendChild(row);
  }

  async function render5D(guid: string) {
    props5d.innerHTML = "";
    if (!connected || !projectId) return;
    let d; try { d = await api.element5d(projectId, guid); } catch { return; }
    if (!d.schedule && !d.cost) return;
    const usd = (n: number) => "$" + Math.round(n).toLocaleString();
    let html = `<div style="font-weight:700;border-top:1px solid var(--line);padding-top:6px">5D — schedule &amp; cost</div>`;
    if (d.schedule) {
      const s = d.schedule;
      html += `<div>🗓 <b>${s.name}</b>${s.trade ? ` · ${s.trade}` : ""} · ${s.percent}% complete`
        + `${s.hard_tied ? "" : ` <span class="meta">(by trade)</span>`}</div>`;
      if (s.start || s.finish) html += `<div class="meta">${s.start ?? "?"} → ${s.finish ?? "?"}${s.state ? ` · ${s.state}` : ""}</div>`;
    }
    if (d.cost) {
      const c = d.cost; const vcol = c.variance < 0 ? "#e2554a" : "#33d17a";
      html += `<div>💰 <b>${c.code ?? c.name}</b> · budget ${usd(c.budget)} · committed ${usd(c.committed)} · actual ${usd(c.actual)}`
        + ` · <span style="color:${vcol}">var ${usd(c.variance)}</span></div>`;
    }
    props5d.innerHTML = html;
  }

  async function showProps(map: ModelIdMap, guid?: string) {
    if (guid) { void render5D(guid); void renderVerify(guid); } else { props5d.innerHTML = ""; propsVerify.innerHTML = ""; }
    if (connected && projectId && guid) {
      try { renderProps(await api.element(projectId, guid)); return; } catch { /* fall through */ }
    }
    const [modelId, ids] = Object.entries(map)[0] ?? [];
    if (!modelId) return;
    const model = loader.fragments.list.get(modelId);
    const localId = ids ? [...ids][0] : undefined;
    if (!model || localId === undefined) return;
    const [data] = await model.getItemsData([localId], {
      attributesDefault: true,
      relations: { IsDefinedBy: { attributes: true, relations: true } },
      relationsDefault: { attributes: false, relations: false },
    });
    propsPanel.hidden = false;
    propsBody.replaceChildren(buildRawProps(data));
  }

  function renderProps(el: ElementProps) {
    propsPanel.hidden = false;
    // structured property + classification editor — only when we can write (connected + project);
    // each edit applies a server recipe and re-publishes, then we re-fetch the element's props.
    const hooks = (connected && projectId) ? {
      setProp: async (pset: string, prop: string, value: string, dtype: string) => {
        await api.editIfc(projectId!, "set_element_pset", { guid: el.guid, pset, prop, value, dtype }, true);
        try { renderProps(await api.element(projectId!, el.guid)); } catch { /* index still rebuilding */ }
      },
      classify: async (system: string, code: string, name: string) => {
        await api.editIfc(projectId!, "set_classification", { guid: el.guid, system, code, name }, true);
        try { renderProps(await api.element(projectId!, el.guid)); } catch { /* index still rebuilding */ }
      },
    } : undefined;
    propsBody.replaceChildren(buildElementProps(el, hooks));
  }

  async function selectByGuid(guid: string, fit = false) {
    selectedGuid = guid;
    await selectMap(await sets.fromGuids([guid]), { guid, fit });
  }

  $("props-close").addEventListener("click", () => void selectMap(null));
  document.addEventListener("keydown", (e) => {
    if (e.key !== "Escape") return;
    if (armed) { disarmDraft(); notify("draft cancelled", "info"); return; }
    if (!propsPanel.hidden) void selectMap(null);
  });

  // ---- 3D click ------------------------------------------------------------
  const mouse = new THREE.Vector2();
  container.addEventListener("click", async (e) => {
    if (measure.mode !== "off") { measure.create(); return; }
    mouse.set(e.clientX, e.clientY);
    const hit = await loader.fragments.raycast({
      camera: viewer.world.camera.three, mouse, dom: viewer.world.renderer!.three.domElement,
    });
    if (armed) { await captureDraftPoint(e, hit ?? null); return; }
    if (placeMode) { await capturePlacePoint(e, hit ?? null); return; }
    if (!hit) { await selectMap(null); return; }
    lastPoint = hit.point.clone();
    showCoords(lastPoint);
    const [guid] = await hit.fragments.getGuidsByLocalIds([hit.localId]);
    selectedGuid = guid ?? null;
    await selectMap({ [hit.fragments.modelId]: new Set([hit.localId]) }, { guid: guid ?? undefined });
    setStatus(`selected ${guid ?? hit.localId}`);
  });
  container.addEventListener("dblclick", () => {
    if (armed && armed.points === "poly") {
      if (armPts.length >= 3) void finishDraft(); else notify("need at least 3 points to close", "error");
      return;
    }
    if (section.enabled) void section.createPlane();
  });

  // ---- file loading --------------------------------------------------------
  // The hidden file <input>s live in index.html and are opened + wired by main.ts, so the native
  // file dialog can appear instantly on click without waiting for this (heavy) module to finish
  // loading. main hands the chosen File straight to openFile() once the viewer is ready.
  async function openFile(kind: "ifc" | "frag" | "convert" | "ref", file: File) {
    if (kind === "frag") await loadFile(file, (b, id) => loader.loadFragments(b, id), "loading");
    else if (kind === "convert") await convertAndLoad(file);
    else if (kind === "ref") await openReference(file);
    else await openIfc(file);
  }
  // Register a pre-built THREE object (e.g. a basemap tile group) as a reference overlay.
  function addReferenceObject(object: THREE.Object3D, label: string) {
    const id = `ref-${++refCount}`;
    viewer.world.scene.three.add(object);
    referenceModels.set(id, { object, label });
    refreshFederation();
    void fitToModels();
    void loader.fragments.core.update(true);
    return id;
  }
  // Load a mesh / point cloud as a view-only reference overlay (IFC stays the source of truth).
  async function openReference(file: File) {
    try {
      const res = await withLoading(container, `loading ${file.name}`, () => loadReferenceModel(file));
      if (!res) return;
      const id = `ref-${++refCount}`;
      viewer.world.scene.three.add(res.object);
      referenceModels.set(id, { object: res.object, label: file.name });
      refreshFederation();
      await fitToModels();
      void loader.fragments.core.update(true);
      notify(`loaded ${file.name}${res.info ? ` — ${res.info}` : ""}`, "success");
    } catch (e) { notify(`couldn't load ${file.name}: ${(e as Error).message}`, "error"); }
  }
  // Above this, parsing the IFC in the browser (web-ifc WASM) is too slow / memory-heavy. When a
  // project + backend are available we skip the in-browser parse entirely and let the server convert
  // the IFC to Fragments off-thread, then stream the optimized result — the production large-model
  // path (CLAUDE.md: never parse a full IFC in the browser at runtime).
  const CLIENT_IFC_MAX = 60 * 1024 * 1024;   // ~60 MB
  const mb = (n: number) => (n / 1048576).toFixed(0);

  // Open an IFC: small files parse in-browser for an instant view (and, with a project open, also
  // upload so drawings / clash / IDS / energy / exports / authoring regenerate server-side). Large
  // files route straight to the server pipeline and stream back the published fragments.
  async function openIfc(file: File) {
    const pid = projectId;
    const big = file.size > CLIENT_IFC_MAX;

    // Large model + backend: server converts → we stream the published .frag. No in-browser parse.
    if (big && connected && pid) {
      let replace = true;
      try { if ((await api.project(pid)).has_source_ifc) replace = await confirmModal(`Replace this project's model with ${file.name} (${mb(file.size)} MB)? Drawings & analysis will regenerate.`, ""); }
      catch { /* offline check — proceed */ }
      if (!replace) { notify(`kept the current project model`, "info"); return; }
      notify(`${file.name} is large (${mb(file.size)} MB) — converting on the server for smooth streaming…`, "info");
      try {
        await api.uploadSourceIfc(pid, file);          // saves + sets source_ifc + publishes off-thread
        const state = await waitForPublish(pid, (s) => setStatus(`processing model: ${s}…`));
        if (state === "done") {
          await loadProjectModel();                    // stream the optimized fragments with progress
          void buildToolsPanel();
          notify(`${file.name} loaded — drawings, QA, energy & authoring are ready`, "success");
        } else {
          notify(`model uploaded; server processing: ${state}`, "info");
        }
      } catch (e) { notify(`couldn't process on the server: ${(e as Error).message}`, "error"); }
      return;
    }

    // Small file (or no backend): parse in-browser for an instant view.
    if (big) notify(`${file.name} is large (${mb(file.size)} MB) — in-browser parsing may be slow; open a project for server-side conversion.`, "info");
    await withLoading(container, `loading ${file.name}`, async () => {
      await loader.loadIfc(new Uint8Array(await file.arrayBuffer()), nextId(file.name));
      await fitToModels();
    });
    if (!connected || !pid) { notify(`loaded ${file.name} (no project — view only)`, "success"); return; }
    let replace = true;
    try { if ((await api.project(pid)).has_source_ifc) replace = await confirmModal(`Replace this project's model with ${file.name}? Drawings & analysis will regenerate.`, ""); }
    catch { /* offline check — proceed */ }
    if (!replace) { notify(`loaded ${file.name} (project model unchanged)`, "info"); return; }
    notify(`Adding ${file.name} to the project — generating drawings & analysis…`, "info");
    try {
      await api.uploadSourceIfc(pid, file);            // saves + sets source_ifc + publishes off-thread
      const state = await waitForPublish(pid, (s) => setStatus(`processing model: ${s}…`));
      void buildToolsPanel();                          // re-checks has_source_ifc → un-gates the tools
      notify(state === "done"
        ? `${file.name} is the project model — drawings, QA, energy & authoring are ready`
        : `model added; server processing: ${state}`, state === "done" ? "success" : "info");
    } catch (e) { notify(`couldn't add to project: ${(e as Error).message}`, "error"); }
  }
  async function loadFile(file: File, load: (b: Uint8Array, id: string) => Promise<unknown>, verb: string) {
    await withLoading(container, `${verb} ${file.name}`, async () => {
      await load(new Uint8Array(await file.arrayBuffer()), nextId(file.name));
      await fitToModels();
      notify(`loaded ${file.name}`, "success");
    });
  }
  async function loadSample(file: string, label: string) {
    await withLoading(container, `loading ${label}`, async () => {
      const mb = (n: number) => (n / 1048576).toFixed(1);
      const buffer = await fetchArrayBufferWithProgress(
        import.meta.env.BASE_URL + file.replace(/^\//, ""), {},   // respect the deploy base
        (loaded, total) => setLoadingLabel(container,
          `downloading ${label} ${Math.round(loaded / total * 100)}% (${mb(loaded)}/${mb(total)} MB)`));
      setLoadingLabel(container, "preparing geometry…");
      await loader.loadFragments(buffer, nextId(label));
      await fitToModels();
      notify(`loaded ${label}`, "success");
    });
  }
  async function convertAndLoad(file: File) {
    await withLoading(container, `converting ${file.name} (Autodesk bridge)`, async () => {
      const fd = new FormData(); fd.append("file", file);
      const res = await fetch(api.url("/convert"), { method: "POST", body: fd, headers: api.authHeaders() });
      if (!res.ok) { const msg = await res.json().catch(() => ({ detail: res.statusText })); throw new Error(msg.detail || "conversion unavailable"); }
      await loader.loadFragments(await res.arrayBuffer(), nextId(file.name));
      await fitToModels();
      notify(`converted + loaded ${file.name}`, "success");
    });
  }
  function download(blob: Blob, name: string) {
    const a = document.createElement("a");
    a.href = URL.createObjectURL(blob); a.download = name; a.click();
    setTimeout(() => URL.revokeObjectURL(a.href), 1000);
  }
  // running inside the Tauri desktop shell? then use native file dialogs + fs
  const isTauri = () => "__TAURI_INTERNALS__" in window;

  async function tauriOpen(kind: "ifc" | "frag" | "convert") {
    const { open } = await import("@tauri-apps/plugin-dialog");
    const { readFile } = await import("@tauri-apps/plugin-fs");
    const exts = kind === "ifc" ? ["ifc"] : kind === "frag" ? ["frag"] : ["rvt", "dwg", "nwc"];
    const path = await open({ multiple: false, filters: [{ name: kind.toUpperCase(), extensions: exts }] });
    if (!path || typeof path !== "string") return;
    const bytes = await readFile(path);
    const name = path.split(/[\\/]/).pop() || "model";
    await withLoading(container, `loading ${name}`, async () => {
      if (kind === "frag") await loader.loadFragments(bytes, nextId(name));
      else if (kind === "ifc") await loader.loadIfc(bytes, nextId(name));
      else {
        const fd = new FormData(); fd.append("file", new Blob([bytes as BlobPart]), name);
        const res = await fetch(api.url("/convert"), { method: "POST", body: fd, headers: api.authHeaders() });
        if (!res.ok) { const m = await res.json().catch(() => ({ detail: res.statusText })); throw new Error(m.detail || "conversion unavailable"); }
        await loader.loadFragments(await res.arrayBuffer(), nextId(name));
      }
      await fitToModels();
      notify(`loaded ${name}`, "success");
    });
  }
  function triggerOpen(kind: "ifc" | "frag" | "convert") {
    if (isTauri()) void tauriOpen(kind); else $(`${kind}-input`).click();
  }

  async function tauriSave(defaultName: string, ext: string, bytes: Uint8Array): Promise<boolean> {
    const { save } = await import("@tauri-apps/plugin-dialog");
    const { writeFile } = await import("@tauri-apps/plugin-fs");
    const path = await save({ defaultPath: defaultName, filters: [{ name: ext.toUpperCase(), extensions: [ext] }] });
    if (!path) return false;
    await writeFile(path, bytes); notify(`saved ${path}`, "success"); return true;
  }
  async function exportFrag() {
    const id = [...loader.fragments.list.keys()][0];
    if (!id) { notify("no model loaded", "error"); return; }
    const buf = new Uint8Array(await loader.fragments.list.get(id)!.getBuffer(false));
    if (isTauri()) { await tauriSave(`${id}.frag`, "frag", buf); return; }
    download(new Blob([buf]), `${id}.frag`);
    notify(`exported ${id}.frag`, "success");
  }
  async function exportIfc() {
    if (!projectId) { notify("connect a project to export its IFC", "error"); return; }
    if (isTauri()) {
      const res = await fetch(api.url(`/projects/${projectId}/source.ifc`), { headers: api.authHeaders() });
      if (!res.ok) { notify("no source IFC to export", "error"); return; }
      await tauriSave("model.ifc", "ifc", new Uint8Array(await res.arrayBuffer()));
      return;
    }
    window.open(api.url(`/projects/${projectId}/source.ifc`), "_blank");
  }

  // ---- floating toolbar ----------------------------------------------------
  const viewerTools = $("viewer-tools");
  function toolBtn(icon: string, title: string, onClick: (b: HTMLButtonElement) => void, cap?: "edit" | "review") {
    const b = document.createElement("button");
    b.textContent = icon; b.className = "tool-btn icon-btn"; b.title = title;
    b.setAttribute("aria-label", title);
    if (cap) b.dataset.cap = cap;   // hidden by CSS when the caller lacks the project capability
    b.onclick = () => onClick(b);
    viewerTools.appendChild(b);
    return b;
  }
  /** Visual separator between functional groups of toolbar buttons (legibility for the icon row). */
  function toolDivider(cap?: "edit" | "review") {
    const d = document.createElement("span"); d.className = "tool-sep";
    if (cap) d.dataset.cap = cap;   // hide the divider too when its group is capability-hidden
    viewerTools.appendChild(d);
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
  toolBtn("⌫", "Clear measurements", () => measure.deleteCurrent());
  toolBtn("⊞", "Show all (H)", async () => { await visibility.showAll(); await colorize.reset(); });
  toolBtn("✦", "Ask the model — plain-English questions about the data", () => {
    if (!connected || !projectId) { notify("open a project to ask about its model", "error"); return; }
    showResult("Ask the model", (body) => {
      body.innerHTML = `<div class="meta" style="margin-bottom:8px">Ask in plain English — e.g. “how many fire-rated doors on level 3?”, “total curtain-wall area”, “which storeys have the most elements?”. Answers are grounded in this model's property index.</div>`;
      const inp = document.createElement("input");
      inp.type = "text"; inp.placeholder = "Type a question…";
      inp.style.cssText = "width:100%;padding:8px;box-sizing:border-box";
      const ans = document.createElement("div"); ans.style.cssText = "margin-top:10px;white-space:pre-wrap;line-height:1.5";
      const go = document.createElement("button"); go.className = "file-btn"; go.textContent = "Ask"; go.style.marginTop = "8px";
      const run = async () => {
        const q = inp.value.trim(); if (!q) return;
        ans.textContent = "Thinking…"; go.disabled = true;
        try {
          const r = await api.askModel(projectId!, q);
          ans.textContent = r.answer || "";
          if (r.source !== "claude") {
            const note = r.source === "disabled" ? "AI key not set — showing the model snapshot the assistant would use." : "";
            ans.textContent = (r.answer || "") + (note ? "\n\n" + note : "")
              + (r.snapshot ? "\n\n" + JSON.stringify(r.snapshot, null, 2) : "");
          }
        } catch (e) { ans.textContent = "Couldn't ask: " + (e as Error).message; }
        finally { go.disabled = false; }
      };
      go.onclick = () => void run();
      inp.addEventListener("keydown", (e) => { if (e.key === "Enter") void run(); });
      body.append(inp, go, ans); inp.focus();
    });
  });
  toolDivider();   // ── measure / visibility ──┊── collaboration ──

  // ---- live presence + shared viewpoints ----------------------------------
  type Peer = { user: string; seconds_ago: number; viewpoint: { position: THREE.Vector3Like; target: THREE.Vector3Like; projection?: string; fov?: number } | null };
  let peers: Peer[] = [];
  function captureViewpoint() {
    const p = new THREE.Vector3(), t = new THREE.Vector3();
    viewer.world.camera.controls.getPosition(p); viewer.world.camera.controls.getTarget(t);
    // carry the projection + FOV so a section/elevation (orthographic) view restores faithfully and
    // round-trips through BCF (a viewpoint that only stored position/target lost the actual view).
    const proj = String(viewer.world.camera.projection.current || "Perspective");
    const cam = viewer.world.camera.three as THREE.PerspectiveCamera;
    return { position: { x: p.x, y: p.y, z: p.z }, target: { x: t.x, y: t.y, z: t.z },
             projection: proj, fov: typeof cam.fov === "number" ? cam.fov : undefined };
  }
  function jumpToViewpoint(vp: Peer["viewpoint"]) {
    if (!vp) return;
    if (vp.projection && String(viewer.world.camera.projection.current) !== vp.projection)
      void viewer.world.camera.projection.set(vp.projection as "Perspective" | "Orthographic");
    void viewer.world.camera.controls.setLookAt(
      vp.position.x, vp.position.y, vp.position.z, vp.target.x, vp.target.y, vp.target.z, true);
  }
  function updatePresence(active: Peer[]) {
    peers = active || [];
    presenceBtn.textContent = peers.length ? `👥 ${peers.length}` : "👥";
    presenceBtn.title = peers.length
      ? `Viewing: ${peers.map((p) => p.user).join(", ")} — click to jump to a shared view`
      : "Live presence — no one else viewing";
    presenceBtn.classList.toggle("on", peers.length > 0);
  }
  const presenceBtn = toolBtn("👥", "Live presence", () => {
    const shared = peers.find((p) => p.viewpoint);
    if (shared) { jumpToViewpoint(shared.viewpoint); notify(`jumped to ${shared.user}'s shared view`, "info"); }
    else notify(peers.length ? `Viewing: ${peers.map((p) => p.user).join(", ")}` : "no one else viewing this model", "info");
  });
  toolBtn("⤴", "Share your current view with everyone", async () => {
    if (!projectId) { notify("connect a project to share views", "error"); return; }
    try { const r = await api.presence(projectId, captureViewpoint()); updatePresence(r.active); notify("view shared with peers", "success"); }
    catch { notify("could not share view", "error"); }
  });
  toolBtn("📱", "Share via QR — open this project on a phone or tablet", () => {
    const base = location.origin + import.meta.env.BASE_URL;
    void showQrModal(projectId ? `${base}?project=${projectId}` : base, "Share via QR");
  });
  if (projectId) {
    const beat = async () => { try { updatePresence((await api.presence(projectId!)).active); } catch { /* offline */ } };
    void beat();
    window.setInterval(beat, 20000);   // heartbeat keeps presence live while the tab is open
  }
  toolDivider();   // ── collaboration ──┊── view aids ──

  // section box: 6 clipping planes shrunk inside the model bounds (renderer-level clip)
  let sectionBox: THREE.Plane[] | null = null;
  toolBtn("⬚", "Section box (clip to model bounds)", (b) => {
    const r = viewer.world.renderer!.three;
    if (sectionBox) { r.clippingPlanes = []; sectionBox = null; b.classList.remove("on"); void loader.fragments.core.update(true); return; }
    const box = new THREE.Box3();
    viewer.world.scene.three.traverse((o) => { const msh = o as THREE.Mesh; if (msh.isMesh) box.expandByObject(msh); });
    if (box.isEmpty()) { notify("no model to clip", "error"); return; }
    const c = box.getCenter(new THREE.Vector3());
    const s = box.getSize(new THREE.Vector3()).multiplyScalar(0.35);   // keep the middle ~70%
    const mn = c.clone().sub(s), mx = c.clone().add(s);
    sectionBox = [
      new THREE.Plane(new THREE.Vector3(1, 0, 0), -mn.x), new THREE.Plane(new THREE.Vector3(-1, 0, 0), mx.x),
      new THREE.Plane(new THREE.Vector3(0, 1, 0), -mn.y), new THREE.Plane(new THREE.Vector3(0, -1, 0), mx.y),
      new THREE.Plane(new THREE.Vector3(0, 0, 1), -mn.z), new THREE.Plane(new THREE.Vector3(0, 0, -1), mx.z),
    ];
    r.localClippingEnabled = true; r.clippingPlanes = sectionBox;
    b.classList.add("on"); void loader.fragments.core.update(true);
    setStatus("section box on (toggle to clear)");
  });

  // render mode: presentation lighting + soft shadows (off by default — flat is cheaper/faster)
  let renderOn = false;
  toolBtn("◓", "Render mode — sun, soft shadows & PBR lighting", (b) => {
    renderOn = !renderOn;
    renderMode(viewer.world, renderOn);
    b.classList.toggle("on", renderOn);
    setStatus(renderOn ? "render mode on — sun + soft shadows" : "render mode off (flat shading)");
    void loader.fragments.core.update(true);
  });

  // sun / shadow study: drive the render-mode sun by date · time · location (live shadows)
  let sunPanel: HTMLElement | null = null;
  function applySun(lat: number, lon: number, date: Date) {
    const pos = sunAltAz(date, lat, lon);
    const up = positionSun(viewer.world, sunSceneDir(pos));
    void loader.fragments.core.update(true);
    const compass = ["N", "NE", "E", "SE", "S", "SW", "W", "NW"][Math.round(pos.azimuth / 45) % 8];
    const out = document.getElementById("sun-readout");
    if (out) out.textContent = up
      ? `altitude ${pos.altitude.toFixed(0)}° · azimuth ${pos.azimuth.toFixed(0)}° (${compass})`
      : `sun below horizon — night (alt ${pos.altitude.toFixed(0)}°)`;
  }
  toolBtn("☀", "Sun & shadow study (date · time · location)", (b) => {
    if (sunPanel) { sunPanel.remove(); sunPanel = null; b.classList.remove("on"); return; }
    if (!renderOn) {   // the study drives the render-mode sun, so make sure it's on
      renderOn = true; renderMode(viewer.world, true);
      [...viewerTools.children].forEach((c) => { if ((c as HTMLElement).title?.startsWith("Render mode")) (c as HTMLElement).classList.add("on"); });
    }
    b.classList.add("on");
    const p = document.createElement("div");
    p.id = "sun-study-panel"; p.className = "floating-panel";
    p.style.cssText = "position:absolute;right:12px;top:64px;z-index:30;background:var(--panel);border:1px solid var(--line);"
      + "border-radius:10px;padding:12px;width:230px;display:flex;flex-direction:column;gap:8px;font-size:12px;box-shadow:0 6px 24px #0007";
    const today = new Date();
    p.innerHTML = `
      <div style="display:flex;justify-content:space-between;align-items:center">
        <strong>☀ Sun &amp; shadow study</strong>
        <button id="sun-close" class="icon-btn" title="Close" style="width:22px;height:22px">✕</button>
      </div>
      <label style="display:flex;justify-content:space-between;gap:6px">Lat
        <input id="sun-lat" type="number" step="0.1" value="40.7" style="width:80px"></label>
      <label style="display:flex;justify-content:space-between;gap:6px">Lon
        <input id="sun-lon" type="number" step="0.1" value="-74.0" style="width:80px"></label>
      <label style="display:flex;justify-content:space-between;gap:6px">Date
        <input id="sun-date" type="date" value="${today.toISOString().slice(0, 10)}" style="width:130px"></label>
      <label>Time of day <span id="sun-time" style="float:right">12:00</span>
        <input id="sun-hour" type="range" min="0" max="1439" step="5" value="720" style="width:100%"></label>
      <div id="sun-readout" class="meta" style="min-height:16px"></div>`;
    (viewer.container.parentElement || viewer.container).appendChild(p);
    sunPanel = p;
    const $$ = <T extends HTMLElement>(id: string) => p.querySelector(`#${id}`) as T;
    const recompute = () => {
      const lat = +$$<HTMLInputElement>("sun-lat").value, lon = +$$<HTMLInputElement>("sun-lon").value;
      const mins = +$$<HTMLInputElement>("sun-hour").value;
      const d = new Date($$<HTMLInputElement>("sun-date").value || today.toISOString().slice(0, 10));
      d.setHours(Math.floor(mins / 60), mins % 60, 0, 0);
      $$("sun-time").textContent = `${String(Math.floor(mins / 60)).padStart(2, "0")}:${String(mins % 60).padStart(2, "0")}`;
      applySun(lat, lon, d);
    };
    p.querySelectorAll("input").forEach((el) => el.addEventListener("input", recompute));
    $$("sun-close").addEventListener("click", () => { p.remove(); sunPanel = null; b.classList.remove("on"); });
    recompute();
  });

  // first-person walkthrough (Matterport-style): WASD to walk at eye height, drag to look. Movement
  // is locked horizontal (feet on the floor) while look can still pitch; cooperates with the orbit
  // controls rather than fighting them — when no key is held, normal drag-to-look is untouched.
  const EYE_HEIGHT = 1.6;   // metres (model units are METRE per project convention)
  let walkRAF = 0; const walkKeys = new Set<string>();
  let walkSaved: Peer["viewpoint"] = null;
  function onWalkKey(e: KeyboardEvent) {
    const k = e.key.toLowerCase();
    if (!["w", "a", "s", "d"].includes(k)) return;
    if (e.type === "keydown") walkKeys.add(k); else walkKeys.delete(k);
    e.preventDefault();
  }
  function setWalk(on: boolean) {
    const c = viewer.world.camera.controls;
    if (on) {
      walkSaved = captureViewpoint();
      void viewer.world.camera.projection.set("Perspective");   // ortho walk feels wrong
      const p = new THREE.Vector3(), t = new THREE.Vector3();
      c.getPosition(p); c.getTarget(t);
      const dir = new THREE.Vector3().subVectors(t, p); dir.y = 0;
      if (dir.lengthSq() < 1e-4) dir.set(0, 0, -1); dir.normalize();
      const eye = new THREE.Vector3(p.x, EYE_HEIGHT, p.z);
      const look = eye.clone().addScaledVector(dir, 6); look.y = EYE_HEIGHT;
      void c.setLookAt(eye.x, eye.y, eye.z, look.x, look.y, look.z, true);
      window.addEventListener("keydown", onWalkKey);
      window.addEventListener("keyup", onWalkKey);
      const sp = 0.07;   // metres per frame ≈ a brisk walk at 60fps
      const step = () => {
        walkRAF = requestAnimationFrame(step);
        if (!walkKeys.size) return;
        c.getPosition(p); c.getTarget(t);
        const fwd = new THREE.Vector3().subVectors(t, p); fwd.y = 0;
        if (fwd.lengthSq() < 1e-6) return; fwd.normalize();
        const right = new THREE.Vector3(-fwd.z, 0, fwd.x);   // 90° CW in plan
        let dx = 0, dz = 0;
        if (walkKeys.has("w")) { dx += fwd.x; dz += fwd.z; }
        if (walkKeys.has("s")) { dx -= fwd.x; dz -= fwd.z; }
        if (walkKeys.has("d")) { dx += right.x; dz += right.z; }
        if (walkKeys.has("a")) { dx -= right.x; dz -= right.z; }
        // keep eye at EYE_HEIGHT (feet on floor); shift the look-target by the same plan delta so
        // the view direction (incl. any pitch from dragging) is preserved as you walk.
        void c.setLookAt(p.x + dx * sp, EYE_HEIGHT, p.z + dz * sp,
          t.x + dx * sp, t.y, t.z + dz * sp, false);
      };
      step();
      notify("walk mode — W/A/S/D to move, drag to look. Toggle to exit.", "info");
    } else {
      cancelAnimationFrame(walkRAF); walkRAF = 0; walkKeys.clear();
      window.removeEventListener("keydown", onWalkKey);
      window.removeEventListener("keyup", onWalkKey);
      void viewer.world.camera.projection.set(ctx.getSettings().projection);
      if (walkSaved) jumpToViewpoint(walkSaved);
    }
  }
  toolBtn("🚶", "Walk through (first-person — W/A/S/D, drag to look)", (b) => {
    const on = !walkRAF;
    setWalk(on);
    b.classList.toggle("on", on);
    setStatus(on ? "walk mode on — W/A/S/D + drag" : "walk mode off");
  });

  // levels overlay: a horizontal grid + label at each storey elevation (from the API)
  const levelObjs: THREE.Object3D[] = [];
  toolBtn("☰", "Toggle storey levels overlay", async (b) => {
    if (levelObjs.length) { for (const o of levelObjs) viewer.world.scene.three.remove(o); levelObjs.length = 0; b.classList.remove("on"); void loader.fragments.core.update(true); return; }
    if (!projectId) { notify("connect a project for storey levels", "error"); return; }
    let storeys: { name: string; elevation: number }[] = [];
    try { storeys = await api.drawingStoreys(projectId); } catch { notify("no storeys (needs source IFC)", "error"); return; }
    const box = new THREE.Box3();
    viewer.world.scene.three.traverse((o) => { const msh = o as THREE.Mesh; if (msh.isMesh) box.expandByObject(msh); });
    const size = box.isEmpty() ? 20 : Math.max(box.getSize(new THREE.Vector3()).x, box.getSize(new THREE.Vector3()).z) * 1.1;
    const cx = box.isEmpty() ? 0 : box.getCenter(new THREE.Vector3()).x;
    const cz = box.isEmpty() ? 0 : box.getCenter(new THREE.Vector3()).z;
    for (const s of storeys) {
      const grid = new THREE.GridHelper(size, 10, 0x4a8cff, 0x33384a);
      grid.position.set(cx, s.elevation, cz);   // model Y is up; elevation in metres
      (grid.material as THREE.Material).opacity = 0.35; (grid.material as THREE.Material).transparent = true;
      viewer.world.scene.three.add(grid); levelObjs.push(grid);
    }
    b.classList.add("on"); void loader.fragments.core.update(true);
    setStatus(`levels: ${storeys.length} storeys`);
  });

  // ---- modeling: author walls / columns / beams / families from ground clicks
  type PlaceKind = "wall" | "column" | "beam" | "family";
  const PLACE_PTS: Record<PlaceKind, number> = { wall: 2, column: 1, beam: 2, family: 1 };
  let placeMode: PlaceKind | null = null;
  let familyType: { guid: string; name: string } | null = null;
  const placePts: THREE.Vector3[] = [];
  const placeBtns = {} as Record<PlaceKind, HTMLButtonElement>;
  const groundPlane = new THREE.Plane(new THREE.Vector3(0, 1, 0), 0);
  const groundRay = new THREE.Raycaster();
  // --- P0 Draft panel: parameter-driven placement (supersedes the prompt()-based buttons above) ----
  let armed: ArmedDraft | null = null;          // active Draft-panel element, or null
  const armPts: THREE.Vector3[] = [];
  let draftHandle: DraftPanelHandle | null = null;
  function disarmDraft() { armed = null; armPts.length = 0; draftHandle?.onArmCleared(); }
  // P1 grid/level drafting refs: the grid overlay + snap, and the active storey/work-plane.
  const gridOverlay = new GridOverlay(viewer.world.scene.three);
  const draftProxies = new DraftProxyLayer(viewer.world.scene.three);   // P6: optimistic placement feedback
  let activeStorey: string | null = null;       // name passed to Draft recipes; sets the work-plane Z
  let activeStoreyZ = 0;
  function setPlaceMode(kind: PlaceKind | null) {
    placeMode = kind; placePts.length = 0;
    (Object.keys(placeBtns) as PlaceKind[]).forEach((k) => placeBtns[k].classList.toggle("on", k === kind));
    if (kind) notify(`${kind}: click the ${PLACE_PTS[kind] === 1 ? "point" : "start point"} on the floor/grid`, "info");
  }
  toolDivider("edit");   // ── view aids ──┊── authoring (editors only) ──
  placeBtns.wall = toolBtn("▭", "Add wall (click two points)", () => setPlaceMode(placeMode === "wall" ? null : "wall"), "edit");
  placeBtns.column = toolBtn("▮", "Add column (click one point)", () => setPlaceMode(placeMode === "column" ? null : "column"), "edit");
  placeBtns.beam = toolBtn("▬", "Add beam (click two points)", () => setPlaceMode(placeMode === "beam" ? null : "beam"), "edit");
  placeBtns.family = toolBtn("❏", "Place a family/type (pick, then click a point)", () => {
    if (placeMode === "family") { setPlaceMode(null); return; }
    void openFamilyPicker();
  }, "edit");
  function pickFromList<T>(items: { label: string; value: T }[], title: string): Promise<T | null> {
    return new Promise((resolve) => {
      const ov = document.createElement("div");
      ov.style.cssText = "position:fixed;inset:0;z-index:300;background:#000a;display:flex;align-items:center;justify-content:center";
      const card = document.createElement("div");
      card.style.cssText = "background:var(--panel);border:1px solid var(--line);border-radius:10px;padding:16px;min-width:340px;max-height:70vh;display:flex;flex-direction:column;gap:8px";
      const h = document.createElement("strong"); h.textContent = title; h.style.fontSize = "14px";
      const search = document.createElement("input"); search.placeholder = "filter…"; search.className = "portal-filter";
      const list = document.createElement("div"); list.style.cssText = "overflow:auto;display:flex;flex-direction:column;gap:2px";
      const done = (v: T | null) => { ov.remove(); resolve(v); };
      const render = (q = "") => {
        list.textContent = "";
        for (const it of items.filter((i) => i.label.toLowerCase().includes(q.toLowerCase())).slice(0, 200)) {
          const b = document.createElement("button"); b.className = "tool-btn"; b.textContent = it.label;
          b.style.cssText = "justify-content:flex-start;text-align:left;width:100%"; b.onclick = () => done(it.value);
          list.appendChild(b);
        }
      };
      search.oninput = () => render(search.value);
      const cancel = document.createElement("button"); cancel.className = "tool-btn"; cancel.textContent = "Cancel"; cancel.onclick = () => done(null);
      render(); card.append(h, search, list, cancel); ov.append(card);
      ov.addEventListener("pointerdown", (e) => { if (e.target === ov) done(null); });
      document.body.appendChild(ov); search.focus();
    });
  }
  async function openFamilyPicker() {
    if (!projectId) { notify("connect a project with a source IFC to place families", "error"); return; }
    let types: { guid: string; name: string; ifc_class: string; has_geometry: boolean }[] = [];
    try { types = (await api.types(projectId)).types; } catch { notify("no type catalog (needs a source IFC)", "error"); return; }
    if (!types.length) { notify("no placeable types in this model", "error"); return; }
    void pickFromList(types.map((t) => ({ label: `${t.name}  ·  ${t.ifc_class.replace("Ifc", "").replace("Type", "")}`, value: t })), "Place family — pick a type")
      .then((t) => { if (!t) return; familyType = { guid: t.guid, name: t.name }; setPlaceMode("family"); notify(`click where to place “${t.name}”`, "info"); });
  }
  toolBtn("␡", "Delete selected element", async () => {
    if (!selectedGuid) { notify("select an element first", "error"); return; }
    if (!projectId) { notify("connect a project with a source IFC to edit", "error"); return; }
    if (!(await confirmModal(`Delete element ${selectedGuid.slice(0, 8)}? This re-authors the IFC.`, "", "Delete", true))) return;
    await authorAndReload("delete_element", { guid: selectedGuid }, "delete");
  }, "edit");
  const addOpening = async (kind: "door" | "window") => {
    if (!selectedGuid) { notify(`select a wall first, then add the ${kind}`, "error"); return; }
    if (!projectId) { notify("connect a project with a source IFC to author", "error"); return; }
    // use where you clicked the wall as the position (projected onto the wall axis); else centered
    const params: Record<string, unknown> = { host_guid: selectedGuid };
    if (lastPoint) params.position = [lastPoint.x, -lastPoint.z];
    await authorAndReload(kind === "window" ? "add_window" : "add_door", params, kind);
  };
  toolBtn("◧", "Add door to selected wall", () => void addOpening("door"), "edit");
  toolBtn("◨", "Add window to selected wall", () => void addOpening("window"), "edit");
  toolBtn("✥", "Move selected element (E,N,Z metres)", async () => {
    if (!selectedGuid) { notify("select an element first", "error"); return; }
    if (!projectId) { notify("connect a project with a source IFC to edit", "error"); return; }
    const v = await askText("Move element", { label: "Move by E, N, Z metres (comma-separated):", value: "1, 0, 0" });
    if (!v) return;
    const [dx, dy, dz] = v.split(",").map((n) => Number(n.trim()) || 0);
    await authorAndReload("move_element", { guid: selectedGuid, dx, dy, dz }, "move");
  }, "edit");
  toolBtn("⟲", "Rotate selected element (degrees about Z)", async () => {
    if (!selectedGuid) { notify("select an element first", "error"); return; }
    if (!projectId) { notify("connect a project with a source IFC to edit", "error"); return; }
    const a = Number(await askText("Rotate element", { label: "Rotate by degrees (about vertical axis):", value: "90" }));
    if (!a) return;
    await authorAndReload("rotate_element", { guid: selectedGuid, angle: a }, "rotate");
  }, "edit");
  toolBtn("✎", "Edit a property on the selected element", async () => {
    if (!selectedGuid) { notify("select an element first", "error"); return; }
    if (!projectId) { notify("connect a project with a source IFC to edit", "error"); return; }
    const pset = await askText("Edit property", { label: "Pset name:", value: "Pset_WallCommon" }); if (!pset) return;
    const propName = await askText("Edit property", { label: "Property:", value: "FireRating" }); if (!propName) return;
    const value = await askText("Edit property", { label: `Value for ${propName}:`, value: "" }); if (value === null) return;
    await authorAndReload("set_element_pset", { guid: selectedGuid, pset, prop: propName, value }, "property edit");
  }, "edit");
  toolBtn("⧉", "Copy selected element (offset E,N,Z metres)", async () => {
    if (!selectedGuid) { notify("select an element first", "error"); return; }
    if (!projectId) { notify("connect a project with a source IFC to edit", "error"); return; }
    const v = await askText("Copy element", { label: "Copy with offset E, N, Z metres:", value: "1, 0, 0" }); if (!v) return;
    const [dx, dy, dz] = v.split(",").map((n) => Number(n.trim()) || 0);
    await authorAndReload("copy_element", { guid: selectedGuid, dx, dy, dz }, "copy");
  }, "edit");

  /** Round a point's plan coords (x,z) to the grid-snap increment; leave height (y). */
  function snapPoint(p: THREE.Vector3): THREE.Vector3 {
    const inc = ctx.getSettings().snap;
    if (!inc) return p;
    return new THREE.Vector3(Math.round(p.x / inc) * inc, p.y, Math.round(p.z / inc) * inc);
  }

  type Hit = { point: THREE.Vector3; fragments: { modelId: string }; localId: number };
  /** Snap to the hit element's nearest mesh vertex within ~0.4 m (true endpoint/edge snap),
   *  falling back to its bounding-box corners, then to grid snap. */
  async function snapToGeometry(raw: THREE.Vector3, hit: Hit | null): Promise<THREE.Vector3 | null> {
    if (!hit) return null;
    const nearest = (pts: THREE.Vector3[]) => {
      let best: THREE.Vector3 | null = null, bd = 0.4;
      for (const v of pts) { const d = raw.distanceTo(v); if (d < bd) { bd = d; best = v; } }
      return best ? best.clone() : null;
    };
    try {
      const model = loader.fragments.list.get(hit.fragments.modelId);
      const verts = model ? await model.getPositions([hit.localId]) : null;
      if (verts?.length) { const v = nearest(verts); if (v) return v; }
    } catch { /* fall back to bbox corners */ }
    try {
      const boxes = await loader.fragments.getBBoxes({ [hit.fragments.modelId]: new Set([hit.localId]) });
      if (!boxes.length) return null;
      const bx = boxes[0]!; // safe: boxes.length checked above
      return nearest([bx.min.x, bx.max.x].flatMap((x) =>
        [bx.min.y, bx.max.y].flatMap((y) => [bx.min.z, bx.max.z].map((z) => new THREE.Vector3(x, y, z)))));
    } catch { return null; }
  }

  async function capturePlacePoint(e: MouseEvent, hit: Hit | null) {
    if (!placeMode) return;
    const raw = hit?.point ?? screenToGround(e);
    let p = raw ? (await snapToGeometry(raw, hit)) ?? snapPoint(raw) : null;
    // ortho lock: hold Shift on the 2nd point to constrain to H/V from the 1st
    if (p && e.shiftKey && placePts.length === 1) {
      const a = placePts[0]!; // safe: placePts.length === 1 checked above
      if (Math.abs(p.x - a.x) >= Math.abs(p.z - a.z)) p = new THREE.Vector3(p.x, p.y, a.z);
      else p = new THREE.Vector3(a.x, p.y, p.z);
    }
    if (!p) { notify("couldn't pick a point — click on the floor or grid", "error"); return; }
    showCoords(p);
    placePts.push(p.clone());
    if (placePts.length < PLACE_PTS[placeMode]) { notify(`${placeMode}: click the end point (hold Shift = ortho)`, "info"); return; }
    const kind = placeMode; setPlaceMode(null);
    if (!projectId) { notify("connect a project with a source IFC to author", "error"); return; }
    // plan coordinates: E = world x, N = -world z (matches the origin/coords convention)
    const pl = (v: THREE.Vector3) => [v.x, -v.z];
    let recipe = "add_wall"; let params: Record<string, unknown> = {};
    if (kind === "wall") {
      const a = placePts[0]!, b = placePts[1]!; // safe: PLACE_PTS.wall === 2, length >= it checked above
      params = { start: pl(a), end: pl(b), height: Number(await askText("Wall height", { label: "Wall height (m):", value: "3.0" })) || 3.0, thickness: Number(await askText("Wall thickness", { label: "Wall thickness (m):", value: "0.2" })) || 0.2 };
    } else if (kind === "column") {
      recipe = "add_column";
      params = { point: pl(placePts[0]!), height: Number(await askText("Column height", { label: "Column height (m):", value: "3.0" })) || 3.0 }; // safe: PLACE_PTS.column === 1
    } else if (kind === "family") {
      if (!familyType) { notify("no family selected", "error"); return; }
      recipe = "place_type";
      params = { type_guid: familyType.guid, position: pl(placePts[0]!) }; // safe: PLACE_PTS.family === 1
    } else {
      recipe = "add_beam";
      const a = placePts[0]!, b = placePts[1]!; // safe: PLACE_PTS.beam === 2, length >= it checked above
      params = { start: pl(a), end: pl(b), depth: Number(await askText("Beam depth", { label: "Beam depth (m):", value: "0.5" })) || 0.5 };
    }
    await authorAndReload(recipe, params, kind === "family" ? `family ${familyType?.name ?? ""}` : kind);
  }

  // --- P0 Draft placement: parameter-driven (params baked into `armed.build`), no prompt() --------
  async function captureDraftPoint(e: MouseEvent, hit: Hit | null) {
    const spec = armed;
    if (!spec) return;
    const raw = hit?.point ?? screenToGround(e);
    let p = raw ? (await snapToGeometry(raw, hit)) ?? snapPoint(raw) : null;
    if (p && e.shiftKey && armPts.length >= 1) {          // ortho lock from the previous point
      const a = armPts[armPts.length - 1]!; // safe: armPts.length >= 1 checked above
      if (Math.abs(p.x - a.x) >= Math.abs(p.z - a.z)) p = new THREE.Vector3(p.x, p.y, a.z);
      else p = new THREE.Vector3(a.x, p.y, p.z);
    }
    if (!p) { notify("couldn't pick a point — click the floor or grid", "error"); return; }
    // snap to the nearest grid intersection when the grid overlay is loaded (plan E=x, N=-z)
    if (gridOverlay.hasData) {
      const gs = gridOverlay.nearestSnap(p.x, -p.z, 0.6);
      if (gs) p = new THREE.Vector3(gs[0], p.y, -gs[1]);
    }
    showCoords(p); armPts.push(p.clone());
    if (spec.points === "poly") { notify(`${spec.label}: ${armPts.length} point(s) — double-click to close`, "info"); return; }
    if (armPts.length < spec.points) { notify(`${spec.label}: click the next point (Shift = ortho)`, "info"); return; }
    await finishDraft();
  }
  async function finishDraft() {
    if (!armed || !projectId) { disarmDraft(); return; }
    const a = armed;
    const planPts = armPts.map((v): [number, number] => [v.x, -v.z]);   // plan coords: E=x, N=-z
    const params = a.build(planPts);
    if (activeStorey && params.storey === undefined) params.storey = activeStorey;   // author onto the active level
    disarmDraft();
    draftProxies.fromParams(params, activeStoreyZ);                                   // instant optimistic proxy
    // incremental preview: real one-element geometry immediately (fail-open — keep the proxy on error)
    try {
      const pv = await api.editPreview(projectId, a.recipe, params);
      if (pv?.frag) { await loader.loadFragments(pv.frag, `preview-${pv.guid || Date.now()}`); draftProxies.clear(); }
    } catch { /* preview unavailable — the optimistic proxy stands until the full reload */ }
    await authorAndReload(a.recipe, params, a.label);
  }

  async function authorAndReload(recipe: string, params: Record<string, unknown>, label: string) {
    await withLoading(container, `authoring ${label} + republishing`, async () => {
      try {
        await api.editIfc(projectId!, recipe, params, true);
        notify(`${label} authored — converting…`, "info");
        const state = await waitForPublish(projectId!);
        if (state === "done") { const shown = await loadProjectModel(); draftProxies.clear(); notify(`${label} applied${shown ? " — shown" : ""}`, "success"); }
        else notify(`${label} authored — publish ${state}`, state === "error" ? "error" : "info");
        await reloadModelPins();
      } catch (err) { draftProxies.clear(); notify(`${label} failed: ${(err as Error).message}`, "error"); }
    });
  }

  async function waitForPublish(pid: string, onTick?: (s: string) => void): Promise<string> {
    const deadline = Date.now() + 12 * 60 * 1000;
    while (Date.now() < deadline) {
      let s: { state: string };
      try { s = await api.publishStatus(pid); } catch { return "error"; }
      onTick?.(s.state);
      if (s.state === "done" || s.state === "error") return s.state;
      await new Promise((r) => setTimeout(r, 1500));
    }
    return "running";
  }
  async function loadProjectModel(): Promise<boolean> {
    if (!projectId) return false;
    return (await withLoading(container, "loading model", async () => {
      const mb = (n: number) => (n / 1048576).toFixed(1);
      let buffer: ArrayBuffer;
      try {
        buffer = await fetchArrayBufferWithProgress(
          api.url(`/projects/${projectId}/model.frag`), { headers: api.authHeaders() },
          (loaded, total) => setLoadingLabel(container,
            `downloading model ${Math.round(loaded / total * 100)}% (${mb(loaded)}/${mb(total)} MB)`));
      } catch { return false; }                 // 404 / no published model yet — fall through to no-model
      // A metadata-only project (property index uploaded, geometry never published) has no .frag, so the
      // request 404s above. Guard the degenerate variants too: an empty body, or a non-.frag payload
      // (e.g. a proxy / SPA host that rewrites a 404 into a 200 HTML page) would otherwise reach the
      // Fragments worker, which can *hang* — not reject — on input it can't parse, leaving the
      // "loading model" overlay up forever. Fail open to the same graceful no-model state a brand-new
      // project already takes.
      if (buffer.byteLength === 0) return false;
      await loader.disposeAll();
      modelLabels.clear();
      const id = `project-${projectId}`;
      modelLabels.set(id, ctx.projectName || "project");
      setLoadingLabel(container, "preparing geometry…");
      try {
        await loader.loadFragments(buffer, id);
      } catch { modelLabels.delete(id); return false; }   // corrupt / non-.frag bytes — fall through
      refreshFederation();
      await fitToModels();
      return true;
    })) ?? false;
  }
  function screenToGround(e: MouseEvent): THREE.Vector3 | null {
    const dom = viewer.world.renderer!.three.domElement;
    const r = dom.getBoundingClientRect();
    const ndc = new THREE.Vector2(((e.clientX - r.left) / r.width) * 2 - 1, -((e.clientY - r.top) / r.height) * 2 + 1);
    groundRay.setFromCamera(ndc, viewer.world.camera.three);
    const pt = new THREE.Vector3();
    return groundRay.ray.intersectPlane(groundPlane, pt) ? pt : null;
  }
  // ---- settings application + coordinate readout ---------------------------
  const UNIT_FACTOR: Record<string, number> = { m: 1, cm: 100, mm: 1000, ft: 3.28084 };
  const BG: Record<string, number | null> = { dark: 0x1e1f22, light: 0xf0f1f3, none: null };
  const ACT = CameraControls.ACTION;
  function applySettings() {
    const settings = ctx.getSettings();
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
    const settings = ctx.getSettings();
    const f = UNIT_FACTOR[settings.units] ?? 1, u = settings.units, d = u === "mm" ? 0 : 2;
    el.textContent = `E ${(p.x * f).toFixed(d)} · N ${(-p.z * f).toFixed(d)} · Z ${(p.y * f).toFixed(d)} ${u}`;
  }

  // ---- camera fit ----------------------------------------------------------
  let fitPending = false;   // set when a fit was skipped because the viewport was hidden (0×0)
  async function fitToModels() {
    const box = new THREE.Box3();
    viewer.world.scene.three.traverse((o) => {
      const m = o as THREE.Mesh & THREE.Points;
      if (m.isMesh || m.isPoints) box.expandByObject(o);   // include reference point clouds, not just meshes
    });
    if (box.isEmpty()) return;
    // Defer when the viewport is hidden (0×0): fitting then divides by a zero aspect ratio and leaves
    // the camera at NaN, so the model is broken once the Model workspace is shown. onModelShown() runs
    // the pending fit once the container has real dimensions.
    const w = viewer.container.clientWidth, h = viewer.container.clientHeight;
    if (!w || !h) { fitPending = true; return; }   // hidden viewport → defer (fit would divide by 0 aspect)
    fitPending = false;
    const cam = viewer.world.camera.three as THREE.PerspectiveCamera;
    // OBC updates the camera aspect via an async ResizeObserver, so right after a workspace becomes
    // visible `cam.aspect` can still be 0/0 = NaN — and fitToSphere then bakes NaN into the position.
    // Force a valid aspect synchronously before fitting.
    viewer.world.renderer?.resize();
    if (cam.isPerspectiveCamera) { cam.aspect = w / h; cam.updateProjectionMatrix(); }
    // If the camera is already NaN (e.g. born while the container was hidden), camera-controls can't
    // recover via setLookAt alone — hard-reset the THREE camera object first, then re-seat the controls.
    if (Number.isNaN(cam.position.x)) {
      cam.position.set(12, 8, 12); cam.up.set(0, 1, 0); cam.quaternion.set(0, 0, 0, 1); cam.updateMatrixWorld(true);
      await viewer.world.camera.controls.setLookAt(12, 8, 12, 0, 0, 0, false);
    }
    if (renderOn) renderMode(viewer.world, true);   // newly loaded meshes need cast/receive flags set
    await viewer.world.camera.controls.fitToSphere(box.getBoundingSphere(new THREE.Sphere()), true);
    await loader.fragments.core.update(true);
  }
  async function fitToItems(map: ModelIdMap) {
    const boxes = await loader.fragments.getBBoxes(map);
    const box = new THREE.Box3();
    for (const b of boxes) box.union(b);
    if (box.isEmpty()) return;
    await viewer.world.camera.controls.fitToSphere(box.getBoundingSphere(new THREE.Sphere()), true);
    await loader.fragments.core.update(true);
  }

  // ---- rail panels ---------------------------------------------------------
  async function buildPanels() {
    if (!projectId) return;
    const elements: ElementProps[] = await api.elements(projectId, { limit: 5000 });
    const treePanel = $("panel-tree");
    treePanel.innerHTML = "";
    treePanel.appendChild(buildTree(elements, (guid) => selectByGuid(guid, false)));

    const meta = await api.meta(projectId);
    const layersPanel = $("panel-layers");
    layersPanel.innerHTML = `<div class="section-title">IFC classes</div>`;
    for (const cls of meta.facets.classes) {
      const row = document.createElement("div"); row.className = "layer-row";
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

  /** Federation list: every loaded model with a visibility toggle + remove. Repopulates the
   *  #fed-models container (if the Tools panel is built); models load additively via Open ▾. */
  function refreshFederation() {
    const host = document.getElementById("fed-models");
    if (!host) return;
    host.innerHTML = "";
    const ids = [...loader.fragments.list.keys()];
    if (!ids.length && !referenceModels.size) {
      host.innerHTML = `<div class="empty-state">No models loaded<span class="es-hint">Use Open ▾ to load an IFC, .frag, or a mesh / point cloud.</span></div>`;
      return;
    }
    for (const id of ids) {
      const model = loader.fragments.list.get(id) as { object: { visible: boolean } } | undefined;
      if (!model) continue;
      const row = document.createElement("div"); row.className = "layer-row";
      const cb = document.createElement("input"); cb.type = "checkbox"; cb.checked = model.object.visible !== false;
      cb.title = "Toggle visibility";
      cb.onchange = () => { model.object.visible = cb.checked; void loader.fragments.core.update(true); };
      const name = document.createElement("span"); name.className = "name"; name.textContent = modelLabels.get(id) || id;
      const rm = document.createElement("button"); rm.className = "tool-btn"; rm.textContent = "✕"; rm.title = "Remove model";
      rm.onclick = async () => {
        await loader.fragments.core.disposeModel(id); modelLabels.delete(id);
        await loader.fragments.core.update(true); refreshFederation();
      };
      row.append(cb, name, rm); host.appendChild(row);
    }
    // view-only reference overlays (meshes / point clouds)
    if (referenceModels.size) {
      const hdr = document.createElement("div"); hdr.className = "section-title"; hdr.textContent = "Reference models";
      host.appendChild(hdr);
      for (const [id, ref] of referenceModels) {
        const row = document.createElement("div"); row.className = "layer-row";
        const cb = document.createElement("input"); cb.type = "checkbox"; cb.checked = ref.object.visible !== false;
        cb.title = "Toggle visibility";
        cb.onchange = () => { ref.object.visible = cb.checked; void loader.fragments.core.update(true); };
        const name = document.createElement("span"); name.className = "name"; name.textContent = ref.label;
        const rm = document.createElement("button"); rm.className = "tool-btn"; rm.textContent = "✕"; rm.title = "Remove model";
        rm.onclick = () => { disposeReference(id); refreshFederation(); void loader.fragments.core.update(true); };
        const gear = document.createElement("button"); gear.className = "tool-btn"; gear.textContent = "⛭"; gear.title = "Align / transform";
        const panel = transformPanel(ref.object);
        gear.onclick = () => { panel.style.display = panel.style.display === "none" ? "block" : "none"; };
        row.append(cb, name, gear, rm); host.appendChild(row); host.appendChild(panel);
      }
    }
  }

  /** Per-model alignment controls (Navisworks-style): position offset, Z-up flip, uniform scale,
   *  move-to-picked-point and reset — applied directly to the reference object's transform. */
  function transformPanel(obj: THREE.Object3D): HTMLElement {
    const panel = document.createElement("div");
    panel.style.cssText = "display:none;padding:4px 0 8px 20px";
    const inputs: (() => void)[] = [];
    const refresh = () => { obj.updateMatrixWorld(true); void loader.fragments.core.update(true); };
    const numRow = (label: string, get: () => number, set: (v: number) => void) => {
      const r = document.createElement("div"); r.className = "layer-row";
      const l = document.createElement("span"); l.className = "name"; l.textContent = label;
      const i = document.createElement("input"); i.type = "number"; i.step = "0.5"; i.style.width = "88px";
      const sync = () => { i.value = String(+get().toFixed(3)); };
      sync(); inputs.push(sync);
      i.oninput = () => { set(+i.value || 0); refresh(); };
      r.append(l, i); panel.appendChild(r);
    };
    numRow("X", () => obj.position.x, (v) => { obj.position.x = v; });
    numRow("Y", () => obj.position.y, (v) => { obj.position.y = v; });
    numRow("Z", () => obj.position.z, (v) => { obj.position.z = v; });
    numRow("Scale", () => obj.scale.x, (v) => obj.scale.setScalar(v || 1));
    const zr = document.createElement("div"); zr.className = "layer-row";
    const zl = document.createElement("span"); zl.className = "name"; zl.textContent = "Z-up → Y-up";
    const zc = document.createElement("input"); zc.type = "checkbox";
    zc.checked = Math.abs(obj.rotation.x + Math.PI / 2) < 0.01;
    zc.onchange = () => { obj.rotation.x = zc.checked ? -Math.PI / 2 : 0; refresh(); };
    zr.append(zl, zc); panel.appendChild(zr);
    const btns = document.createElement("div"); btns.style.cssText = "display:flex;gap:6px;margin-top:4px";
    const move = document.createElement("button"); move.className = "tool-btn"; move.textContent = "Move to point";
    move.title = "Translate so the model's centre sits on the last picked point";
    move.onclick = () => {
      if (!lastPoint) { setStatus("click a point in the scene first"); return; }
      const c = new THREE.Box3().setFromObject(obj).getCenter(new THREE.Vector3());
      obj.position.add(lastPoint.clone().sub(c)); refresh(); inputs.forEach((f) => f());
    };
    const reset = document.createElement("button"); reset.className = "tool-btn"; reset.textContent = "Reset";
    reset.onclick = () => {
      obj.position.set(0, 0, 0); obj.rotation.set(0, 0, 0); obj.scale.setScalar(1);
      zc.checked = false; refresh(); inputs.forEach((f) => f());
    };
    btns.append(move, reset); panel.appendChild(btns);
    return panel;
  }

  /** Remove a reference overlay from the scene and free its GPU buffers. */
  function disposeReference(id: string) {
    const ref = referenceModels.get(id);
    if (!ref) return;
    viewer.world.scene.three.remove(ref.object);
    ref.object.traverse((o) => {
      const m = o as THREE.Mesh & THREE.Points;
      m.geometry?.dispose?.();
      const mat = (m as { material?: THREE.Material | THREE.Material[] }).material;
      if (Array.isArray(mat)) mat.forEach((x) => x.dispose()); else mat?.dispose?.();
    });
    referenceModels.delete(id);
  }

  // Which tool sections matter most per persona — primary ones sit on top, expanded; the rest
  // fold under a "More tools" divider, collapsed. `all` (no entry) keeps everything primary.
  const ALL_TOOLS = ["exports", "cost", "schedule", "qa", "energy", "authoring", "drawings"];
  const TOOLS_BY_PERSONA: Record<string, string[]> = {
    gc: ["cost", "schedule", "qa", "exports"],
    developer: ["cost", "schedule", "exports"],
    architect: ["drawings", "authoring", "exports"],
    engineer: ["qa", "energy", "authoring"],
  };
  const toolBtn2 = (label: string, onClick: () => void) => {
    const b = document.createElement("button");
    b.className = "tool-btn"; b.textContent = label;
    b.style.cssText = "display:block;margin:4px 0;width:100%;text-align:left";
    b.onclick = onClick;
    return b;
  };

  async function buildToolsPanel() {
    const panel = $("panel-tools");
    panel.innerHTML = "";
    const intro = document.createElement("div");
    intro.className = "meta"; intro.style.cssText = "margin:2px 2px 8px;font-size:11px;line-height:1.4";
    intro.textContent = "Model-derived analysis & exports. The full records live in the Construction & Finance workspaces.";
    panel.appendChild(intro);
    const goWorkspace = (key: string) => window.dispatchEvent(new CustomEvent("aec:workspace", { detail: key }));

    // model metadata gates IFC-only tools (drawings, QA, energy, authoring, exports)
    let hasIfc = false;
    if (projectId) { try { hasIfc = !!(await api.project(projectId)).has_source_ifc; } catch { /* offline */ } }
    const pid = projectId as string;   // tool builders below only run inside project-gated sections

    const persona = localStorage.getItem("persona") || "all";
    const primary = TOOLS_BY_PERSONA[persona];
    const order = primary ? [...primary, ...ALL_TOOLS.filter((t) => !primary.includes(t))] : ALL_TOOLS;
    let moreShown = false;

    /** Collapsible section. Returns the body to fill, or null when its precondition is unmet
     *  (in which case it renders one muted reason line and stays collapsed). */
    function section(key: string, title: string,
                     opts: { requires?: "project" | "sourceIfc"; tool?: boolean } = {}): HTMLElement | null {
      const ok = opts.requires === "project" ? !!projectId
        : opts.requires === "sourceIfc" ? (!!projectId && hasIfc) : true;
      const reason = opts.requires === "sourceIfc" ? "needs a source IFC"
        : opts.requires === "project" ? "needs a project" : "";
      const isPrimary = !opts.tool || !primary || primary.includes(key);
      if (opts.tool && primary && !isPrimary && !moreShown) {
        const sep = document.createElement("div"); sep.className = "tools-more"; sep.textContent = "More tools";
        panel.appendChild(sep); moreShown = true;
      }
      const group = document.createElement("section"); group.className = "tool-group"; group.dataset.tool = key;
      const head = document.createElement("button"); head.type = "button"; head.className = "tool-group-head";
      head.innerHTML = `<span class="chev">▸</span><span class="t">${title}</span>` + (ok ? "" : `<span class="why">${reason}</span>`);
      const body = document.createElement("div"); body.className = "tool-group-body";
      group.append(head, body);
      const saved = localStorage.getItem(`tools-open:${key}`);
      const open = saved == null ? (ok && isPrimary) : saved === "1";
      group.classList.toggle("open", open);
      head.setAttribute("aria-expanded", String(open));
      head.onclick = () => {
        const o = !group.classList.contains("open");
        group.classList.toggle("open", o); head.setAttribute("aria-expanded", String(o));
        localStorage.setItem(`tools-open:${key}`, o ? "1" : "0");
      };
      panel.appendChild(group);
      if (!ok) { const n = document.createElement("div"); n.className = "meta"; n.textContent = `${reason} to use this.`; body.appendChild(n); return null; }
      return body;
    }

    // --- always-on: model setup ----------------------------------------------
    const fedBody = section("models", "Models (federation)");
    if (fedBody) {
      const l = document.createElement("div"); l.id = "fed-models"; fedBody.appendChild(l); refreshFederation();
      if (projectId) fedBody.appendChild(toolBtn2("🕔 Version history", async () => {
        const h = await api.modelVersions(pid);
        showResult("Model version history", async (body) => {
          if (!h.length) { body.appendChild(resultNote("No versions yet — publish the model (Authoring) to snapshot one.")); return; }
          if (h.length >= 2) {
            const d = await api.versionDiff(pid, h[1]!.version, h[0]!.version); // safe: h.length >= 2 checked above
            body.appendChild(resultNote(`v${h[1]!.version} → v${h[0]!.version}: <b>+${d.added_count}</b> / <b>−${d.removed_count}</b> elements · ${d.unchanged_count} unchanged`, "ok"));
          }
          body.appendChild(kvTable(h.map((v) => ({
            k: `v${v.version}${v.note ? " (" + v.note + ")" : ""}`,
            v: `${v.element_count} elements · ${(v.created_at || "").slice(0, 10)}` }))));
        });
      }));
    }

    const ob = section("origin", "Working origin (E / N / Z)");
    if (ob) {
      const inputs: Record<string, HTMLInputElement> = {};
      const cur = origin.getOrigin();
      for (const k of ["e", "n", "z"] as const) {
        const row = document.createElement("div"); row.className = "layer-row";
        const label = document.createElement("span"); label.className = "name"; label.textContent = k.toUpperCase();
        const inp = document.createElement("input"); inp.type = "number"; inp.value = String(cur[k]); inp.style.width = "110px";
        inputs[k] = inp; row.append(label, inp); ob.appendChild(row);
      }
      const fromPt = toolBtn2("Set from selected point", () => {
        if (!lastPoint) { setStatus("click a point first"); return; }
        inputs.e!.value = lastPoint.x.toFixed(3); inputs.n!.value = (-lastPoint.z).toFixed(3); inputs.z!.value = lastPoint.y.toFixed(3); // safe: inputs.{e,n,z} populated by the loop above
      });
      fromPt.style.cssText = "";
      const apply = document.createElement("button");
      apply.className = "tool-btn"; apply.textContent = "Apply origin"; apply.style.marginLeft = "6px";
      apply.onclick = async () => {
        origin.setOrigin({ e: +inputs.e!.value, n: +inputs.n!.value, z: +inputs.z!.value }); // safe: inputs.{e,n,z} populated by the loop above
        for (const [, model] of loader.fragments.list) origin.applyTo(model.object as unknown as THREE.Object3D);
        await loader.fragments.core.update(true);
        if (connected && projectId) {
          fetch(api.url(`/projects/${projectId}`), { method: "PATCH", headers: { "Content-Type": "application/json", ...api.authHeaders() }, body: JSON.stringify({ origin: origin.getOrigin() }) }).catch(() => {});
        }
        setStatus(`origin set to E${inputs.e!.value} N${inputs.n!.value} Z${inputs.z!.value}`); // safe: inputs.{e,n,z} populated by the loop above
      };
      ob.append(fromPt, apply);
    }

    // --- Draft: parameter-driven family/element authoring (editors) ----------
    const draftBody = section("draft", "Draft — author elements", { requires: "sourceIfc" });
    if (draftBody) {
      draftHandle = installDraftPanel({
        body: draftBody,
        fetchFamilies: async () => {
          const cat = await api.familyCatalog();
          return Object.values(cat.categories).flat() as FamilyDef[];
        },
        arm: (a) => { setPlaceMode(null); armed = a; armPts.length = 0; },
        notify,
        canAuthor: () => !!projectId && hasIfc,
      });
    }

    // --- Grid & Levels: drafting reference frame (grid snap + active work-plane) ----------
    const glBody = section("gridlevels", "Grid & Levels", { requires: "sourceIfc" });
    if (glBody) {
      const status = document.createElement("div"); status.className = "meta";
      status.textContent = "Load the grid + levels to snap placement and set the active work-plane.";
      const levelSel = document.createElement("select"); levelSel.className = "portal-filter";
      levelSel.style.cssText = "width:100%;margin:4px 0"; levelSel.setAttribute("aria-label", "Active level");
      const applyLevel = () => {
        const opt = levelSel.selectedOptions[0]; if (!opt) return;
        activeStorey = opt.dataset.name || null; activeStoreyZ = Number(opt.dataset.z || 0);
        groundPlane.constant = -activeStoreyZ;                       // draft on the active level's plane
        if (gridOverlay.data) gridOverlay.set(gridOverlay.data, activeStoreyZ);
        setStatus(`active level: ${activeStorey ?? "—"} (Z ${activeStoreyZ.toFixed(2)} m)`);
      };
      levelSel.onchange = applyLevel;
      const load = toolBtn2("⊞ Load grid + levels", async () => {
        try {
          const g = await api.modelGrid(pid);
          gridOverlay.set(g.grid, activeStoreyZ); gridOverlay.visible = true;
          levelSel.innerHTML = "";
          for (const lv of g.levels) {
            const o = document.createElement("option");
            o.textContent = `${lv.name ?? "Level"} (${lv.elevation.toFixed(2)} m)`;
            o.dataset.name = lv.name ?? ""; o.dataset.z = String(lv.elevation); levelSel.appendChild(o);
          }
          if (g.levels.length) applyLevel();
          status.textContent = `grid: ${g.grid.source} · ${g.grid.axes.length} axes · `
            + `${g.grid.intersections.length} snap points · ${g.levels.length} level(s)`;
        } catch (e) { status.textContent = `failed: ${(e as Error).message}`; }
      });
      const toggle = toolBtn2("◻ Toggle grid overlay", () => {
        gridOverlay.visible = !gridOverlay.visible; setStatus(`grid ${gridOverlay.visible ? "shown" : "hidden"}`);
      });
      const addLvl = toolBtn2("➕ Add level", async () => {
        const name = await askText("Add level", { label: "Level name", value: "Level 2" }); if (!name) return;
        const elevS = await askText("Add level", { label: "Elevation (metres)", value: "3.0" });
        const elev = Number(elevS); await authorAndReload("add_storey",
          { name, elevation: Number.isFinite(elev) ? elev : 0 }, `level ${name}`);
      });
      glBody.append(status, levelSel, load, toggle, addLvl);
    }

    // --- persona-ordered tool sections ---------------------------------------
    const builders: Record<string, () => void> = {
      exports: () => {
        const b = section("exports", "Exports", { requires: "sourceIfc", tool: true });
        if (!b) return;
        for (const [label, file] of [["Quantity takeoff (QTO/5D)", "qto"], ["COBie", "cobie"], ["Space schedule", "spaces"], ["4D schedule", "schedule"]] as const)
          b.appendChild(toolBtn2(`↓ ${label}`, () => window.open(api.url(`/projects/${projectId}/exports/${file}.xlsx`), "_blank")));
        // gbXML — spaces + envelope areas for OpenStudio / EnergyPlus / IES energy modelling
        const gbx = toolBtn2("↓ gbXML (energy model)", () => window.open(api.url(`/projects/${projectId}/exports/model.gbxml`), "_blank"));
        gbx.title = "Green Building XML — spaces + areas/volumes from the IFC geometry, to seed an energy model (OpenStudio/EnergyPlus/IES). Simplified: building-level envelope, not per-space surfaces.";
        b.appendChild(gbx);
        // discipline quantities — reinforcement tonnage, MEP linear runs, structural volume (Koh rebar viz / WithRebar)
        b.appendChild(toolBtn2("🔩 Discipline quantities", async () => {
          if (!projectId) { notify("connect a project first", "error"); return; }
          try {
            const q = await api.disciplineQuantities(projectId);
            showResult("Discipline quantities", (body) => {
              body.appendChild(kvTable([
                { k: `Reinforcement${q.rebar.estimated ? " (est. from volume)" : ""}`, v: `${q.rebar.tonnes} t · ${q.rebar.count} bars` },
                { k: "Ductwork", v: `${q.mep.duct_m} m · ${q.mep.counts.duct} seg` },
                { k: "Piping", v: `${q.mep.pipe_m} m · ${q.mep.counts.pipe} seg` },
                { k: "Cable / carrier", v: `${q.mep.cable_m} m · ${q.mep.counts.cable} seg` },
                { k: "MEP fittings", v: String(q.mep.counts.fittings) },
                { k: "Structural element volume", v: `${q.structure.element_volume_m3} m³` },
              ]));
            });
          } catch (e) { notify(`quantities failed: ${(e as Error).message}`, "error"); }
        }));
        // full turnover deliverable: as-built IFC + COBie/QTO/spaces + status PDF + closeout records
        const pkg = toolBtn2("📦 Closeout package (.zip)", () => window.open(api.url(`/projects/${projectId}/closeout/package.zip`), "_blank"));
        pkg.title = "Everything for handover in one ZIP: as-built model, data workbooks, status report, closeout records";
        b.appendChild(pkg);
      },
      cost: () => {
        const b = section("cost", "Cost / Pay Apps", { requires: "project", tool: true });
        if (!b) return;
        const out = document.createElement("div"); out.className = "meta"; out.style.marginTop = "4px";
        b.appendChild(toolBtn2("Σ Cost Summary", async () => {
          out.textContent = "computing…";
          const s = await api.costSummary(pid);
          const fmt = (v: number) => `$${v.toLocaleString()}`;
          out.textContent = `Over/Under ${fmt(s.projected_over_under)} · spent ${s.pct_spent}%`;
          showResult("Cost summary", (body) => body.appendChild(kvTable([
            { k: "Budget", v: fmt(s.budget) },
            { k: "Committed", v: `${fmt(s.committed)} (${s.pct_committed}%)`, bar: s.pct_committed / 100 },
            { k: "Actual", v: `${fmt(s.actual)} (${s.pct_spent}%)`, bar: s.pct_spent / 100 },
            { k: "Forecast", v: fmt(s.forecast) },
            { k: "Projected over / under", v: fmt(s.projected_over_under), strong: true },
          ])));
        }));
        b.appendChild(toolBtn2("🖊 G702/G703 Pay App (PDF)", async () => {
          const { openPdfUrl, saveToDocuments } = await import("../drawings/openPdf");
          await openPdfUrl(api, api.url(`/projects/${projectId}/cost/g702.pdf?app_no=1`), "G702.pdf", { saveLabel: "Save to Documents", onSave: saveToDocuments(api, projectId!) });
        }));
        b.appendChild(toolBtn2("⚖ Lien waiver / release", () => {
          showResult("Lien waiver / release", (body) => {
            body.appendChild(resultNote("Generate a statutory waiver to accompany the pay application. "
              + "Use <b>conditional</b> before funds clear; <b>unconditional</b> only once paid."));
            const kinds: [string, string][] = [
              ["conditional_progress", "Conditional — progress payment"],
              ["unconditional_progress", "Unconditional — progress payment"],
              ["conditional_final", "Conditional — final payment"],
              ["unconditional_final", "Unconditional — final payment"],
            ];
            for (const [kind, label] of kinds) {
              const btn = document.createElement("button");
              btn.className = "tool-btn"; btn.style.cssText = "display:block;width:100%;margin:4px 0;text-align:left";
              btn.textContent = `↓ ${label}`;
              btn.onclick = async () => {
                const { openPdfUrl, saveToDocuments } = await import("../drawings/openPdf");
                await openPdfUrl(api, api.url(`/projects/${projectId}/cost/lien-waiver.pdf?kind=${kind}&app_no=1`), "lien-waiver.pdf", { saveLabel: "Save to Documents", onSave: saveToDocuments(api, projectId!) });
              };
              body.appendChild(btn);
            }
          });
        }));
        b.appendChild(toolBtn2("⚖ Bid leveling", async () => {
          out.textContent = "tabulating…";
          const r = await api.bidLeveling(pid);
          const money = (n: number | null) => n == null ? "—" : `$${Math.round(n).toLocaleString()}`;
          out.textContent = `${r.package_count} package(s) · ${r.bid_count} bid(s)`;
          showResult("Bid leveling", (body) => {
            if (!r.packages.length) { body.appendChild(resultNote("No bid packages yet — add them in Construction → Preconstruction.")); return; }
            for (const p of r.packages) {
              body.appendChild(resultNote(`<b>${p.package}</b> — ${p.bid_count} bids · low ${money(p.low)} · spread ${money(p.spread)}`));
              if (p.bids.length) body.appendChild(kvTable(p.bids.map((bd) => ({
                k: `${bd.is_low ? "★ " : ""}${bd.bidder || "—"}`, v: money(bd.amount), strong: bd.is_low }))));
            }
          });
        }));
        b.appendChild(toolBtn2("🩺 Model QA (integrity)", async () => {
          out.textContent = "scanning model…";
          let q;
          try { q = await api.modelQa(pid); }
          catch { out.textContent = "needs a source IFC (open one in Model)"; return; }
          out.textContent = q.clean ? "clean — no integrity issues" : `${q.total_issues} issue(s)`;
          showResult("Model integrity / hygiene", (body) => {
            body.appendChild(resultNote(q!.clean
              ? `<b>Clean</b> — no integrity issues across ${q!.element_count} elements.`
              : `<b>${q!.total_issues} issue(s)</b> across ${q!.element_count} elements.`, q!.clean ? "ok" : "bad"));
            const c = q!.checks;
            body.appendChild(kvTable([
              { k: "Duplicate GlobalIds", v: String(c.duplicate_guids.count), strong: c.duplicate_guids.count > 0 },
              { k: "Orphaned elements (no storey)", v: String(c.orphaned_elements.count), strong: c.orphaned_elements.count > 0 },
              { k: "Overlapping duplicates", v: String(c.overlapping_duplicates.count), strong: c.overlapping_duplicates.count > 0 },
              { k: `Unenclosed spaces (of ${c.unenclosed_spaces.total_spaces})`, v: String(c.unenclosed_spaces.count), strong: c.unenclosed_spaces.count > 0 },
              { k: `Blank names (of ${c.blank_names.of_elements})`, v: String(c.blank_names.count), strong: c.blank_names.count > 0 },
            ]));
          });
        }));
        b.appendChild(toolBtn2("📍 Georeferencing (survey basis)", async () => {
          out.textContent = "reading coordinates…";
          let g;
          try { g = await api.modelGeoreferencing(pid); }
          catch { out.textContent = "needs a source IFC (open one in Model)"; return; }
          out.textContent = g.level_label;
          showResult("Shared coordinates / setout basis", (body) => {
            body.appendChild(resultNote(`<b>${g!.level_label}</b>${g!.crs?.name ? ` · ${g!.crs.name}` : ""}`,
              g!.level >= 40 ? "ok" : "bad"));
            const rows: { k: string; v: string; strong?: boolean }[] = [];
            const mc = g!.map_conversion;
            if (mc) {
              if (mc.eastings != null) rows.push({ k: "Eastings / Northings", v: `${Math.round(mc.eastings).toLocaleString()} / ${Math.round(mc.northings ?? 0).toLocaleString()} m` });
              if (mc.orthogonal_height != null) rows.push({ k: "Orthogonal height", v: `${mc.orthogonal_height} m` });
              if (mc.true_north_bearing_deg != null) rows.push({ k: "True-north bearing", v: `${mc.true_north_bearing_deg}°` });
              rows.push({ k: "Scale", v: String(mc.scale) });
            }
            if (g!.crs) {
              if (g!.crs.map_projection) rows.push({ k: "Map projection", v: `${g!.crs.map_projection}${g!.crs.map_zone ? ` (zone ${g!.crs.map_zone})` : ""}` });
              if (g!.crs.geodetic_datum) rows.push({ k: "Geodetic datum", v: g!.crs.geodetic_datum });
              if (g!.crs.vertical_datum) rows.push({ k: "Vertical datum", v: g!.crs.vertical_datum });
            }
            if (g!.site?.ref_latitude) rows.push({ k: "Site lat / long", v: `${g!.site.ref_latitude.join(" ")} / ${(g!.site.ref_longitude ?? []).join(" ")}` });
            if (!rows.length) rows.push({ k: "Georeferencing", v: "none found — model is on a local origin" });
            body.appendChild(kvTable(rows));
          });
        }));
        b.appendChild(toolBtn2("📐 Estimate from model (takeoff)", async () => {
          out.textContent = "taking off…";
          let r;
          try { r = await api.estimateFromModel(pid); }
          catch { out.textContent = "needs a source IFC (open one in Model)"; return; }
          const money = (n: number) => `$${Math.round(n).toLocaleString()}`;
          out.textContent = `est. ${money(r.total)} · ${r.element_count} elements`;
          showResult("Conceptual estimate (from model takeoff)", (body) => {
            body.appendChild(resultNote(`<b>${money(r.total)}</b> across ${r.lines.length} priced trades · ${r.element_count} elements`
              + (r.unpriced.length ? ` · ${r.unpriced.length} class(es) unpriced` : ""), "ok"));
            body.appendChild(kvTable(r.lines.map((l) => ({
              k: `${l.ifc_class.replace("Ifc", "")} (${l.quantity} ${l.unit} @ ${money(l.rate)})`,
              v: money(l.amount) }))));
            const gaeb = document.createElement("div"); gaeb.className = "meta"; gaeb.style.marginTop = "8px";
            gaeb.textContent = "Export GAEB (X83), coded to a regional standard:";
            body.appendChild(gaeb);
            for (const [sys, label] of [["din276", "DIN 276"], ["nrm1", "NRM 1"], ["masterformat", "MasterFormat"]] as const)
              body.appendChild(toolBtn2(`↧ GAEB · ${label}`, () => window.open(api.url(`/projects/${pid}/estimate/gaeb.x83?system=${sys}`), "_blank")));
          });
        }));
        b.appendChild(toolBtn2("🧱 Resource estimate (labor·mat·equip)", async () => {
          out.textContent = "building up cost…";
          let r;
          try { r = await api.estimateResourceBased(pid); }
          catch { out.textContent = "needs a source IFC (open one in Model)"; return; }
          const money = (n: number) => `$${Math.round(n).toLocaleString()}`;
          const pct = (n: number) => r!.total ? `${Math.round(n / r!.total * 100)}%` : "0%";
          out.textContent = `est. ${money(r.total)} · ${Math.round(r.labor_hours).toLocaleString()} crew-hr`;
          showResult("Resource-based estimate (labor · material · equipment)", (body) => {
            body.appendChild(resultNote(`<b>${money(r!.total)}</b> across ${r!.lines.length} assemblies · `
              + `${Math.round(r!.labor_hours).toLocaleString()} crew-hours`
              + (r!.unmapped.length ? ` · ${r!.unmapped.length} class(es) unmapped` : ""), "ok"));
            // L/M/E split — the point of resource-based estimating
            body.appendChild(kvTable([
              { k: `Labor (${pct(r!.by_kind.labor)})`, v: money(r!.by_kind.labor) },
              { k: `Material (${pct(r!.by_kind.material)})`, v: money(r!.by_kind.material) },
              { k: `Equipment (${pct(r!.by_kind.equipment)})`, v: money(r!.by_kind.equipment), strong: true },
            ]));
            // labor demand by trade — the bridge to staffing / resource loading
            if (r!.by_trade.length) {
              const lh = document.createElement("div"); lh.className = "meta"; lh.style.marginTop = "8px";
              lh.textContent = "Labor demand by trade (crew-hours to staff / load the schedule):";
              body.appendChild(lh);
              body.appendChild(kvTable(r!.by_trade.map((t) => ({
                k: `${t.name} — ${Math.round(t.hours).toLocaleString()} hr`, v: money(t.cost) }))));
            }
            const h = document.createElement("div"); h.className = "meta"; h.style.marginTop = "8px";
            h.textContent = "By assembly (built up from a crew, not a blended rate):";
            body.appendChild(h);
            body.appendChild(kvTable(r!.lines.map((l) => ({
              k: `${l.assembly_name} · ${l.ifc_class.replace("Ifc", "")} (${l.quantity} ${l.unit} @ ${money(l.unit_cost)}, ${Math.round(l.labor_hours)} hr)`,
              v: money(l.total) }))));
          });
        }));
        b.appendChild(toolBtn2("▤ DXF takeoff (2D CAD)", () => {
          const inp = document.createElement("input"); inp.type = "file"; inp.accept = ".dxf"; inp.style.display = "none";
          inp.onchange = async () => {
            const f = inp.files?.[0]; if (!f) return;
            out.textContent = "reading DXF…";
            let r;
            try { r = await api.takeoffDxf(pid, f); }
            catch (e) { out.textContent = `DXF takeoff failed: ${(e as Error).message}`; return; }
            const num = (n: number) => n.toLocaleString(undefined, { maximumFractionDigits: 1 });
            out.textContent = `${r.layer_count} layers · ${num(r.total_length_m)} m · ${num(r.total_area_m2)} m²`;
            showResult("DXF takeoff (2D CAD, by layer)", (body) => {
              body.appendChild(resultNote(`<b>${num(r!.total_length_m)} m</b> linear · <b>${num(r!.total_area_m2)} m²</b> area · `
                + `${r!.entity_count} entities · units: ${r!.units}`, "ok"));
              body.appendChild(kvTable(r!.layers.filter((l) => l.length_m || l.area_m2 || l.inserts).map((l) => ({
                k: l.layer,
                v: [l.length_m ? `${num(l.length_m)} m` : "", l.area_m2 ? `${num(l.area_m2)} m²` : "", l.inserts ? `${l.inserts}×` : ""].filter(Boolean).join(" · ") }))));
              if (r!.blocks.length) {
                const bh = document.createElement("div"); bh.className = "meta"; bh.style.marginTop = "8px"; bh.textContent = "Blocks (counts):";
                body.appendChild(bh);
                body.appendChild(kvTable(r!.blocks.map((bl) => ({ k: bl.block, v: `${bl.count}×` }))));
              }
            });
          };
          inp.click();
        }));
        b.appendChild(toolBtn2("▦ Scan-to-BIM deviation (as-built QA)", () => {
          const inp = document.createElement("input"); inp.type = "file"; inp.accept = ".xyz,.txt,.csv,.pts"; inp.style.display = "none";
          inp.onchange = async () => {
            const f = inp.files?.[0]; if (!f) return;
            out.textContent = "comparing scan to model…";
            let r;
            try { r = await api.scanDeviation(pid, f, 0.05); }
            catch (e) { out.textContent = `scan deviation failed: ${(e as Error).message}`; return; }
            const num = (n: number) => n.toLocaleString(undefined, { maximumFractionDigits: 3 });
            const ok = (r.within_pct ?? 0) >= 90;
            out.textContent = `${r.within_pct}% within ${num(r.tolerance)} m · max ${num(r.max_deviation)} m`;
            showResult("Scan-to-BIM deviation (as-built vs model)", (body) => {
              body.appendChild(resultNote(`<b>${r!.within_pct}%</b> of ${r!.point_count.toLocaleString()} scan points within `
                + `<b>${num(r!.tolerance)} m</b> of the model surface · ${r!.out_of_tolerance.toLocaleString()} out of tolerance`,
                ok ? "ok" : "bad"));
              body.appendChild(kvTable([
                { k: "Mean deviation", v: `${num(r!.mean_deviation)} m` },
                { k: "95th-percentile deviation", v: `${num(r!.p95_deviation)} m` },
                { k: "Max deviation", v: `${num(r!.max_deviation)} m`, strong: r!.max_deviation > r!.tolerance * 3 },
                { k: "Reference surface points", v: r!.reference_count.toLocaleString() },
              ]));
              const h = document.createElement("div"); h.className = "meta"; h.style.marginTop = "8px";
              h.textContent = "Deviation histogram (share of points by tolerance band):";
              body.appendChild(h);
              body.appendChild(kvTable(r!.histogram.map((band) => ({
                k: band.band, v: `${band.count.toLocaleString()} (${r!.point_count ? Math.round(band.count / r!.point_count * 100) : 0}%)`,
                strong: band.band.startsWith(">") && band.count > 0 }))));
            });
          };
          inp.click();
        }));
        b.appendChild(toolBtn2("🏗 Raise 2D→BIM (DXF plan → model)", () => {
          const inp = document.createElement("input"); inp.type = "file"; inp.accept = ".dxf"; inp.style.display = "none";
          inp.onchange = async () => {
            const f = inp.files?.[0]; if (!f) return;
            out.textContent = "raising 2D plan to a model…";
            let r;
            try { r = await api.raisePlan(pid, f, { wallHeight: 3.0, wallThickness: 0.2 }); }
            catch (e) { out.textContent = `raise failed: ${(e as Error).message}`; return; }
            const num = (n: number) => n.toLocaleString(undefined, { maximumFractionDigits: 1 });
            out.textContent = `raised ${r.wall_count} walls · ${r.space_count ?? 0} rooms → "2D Raise" model`;
            showResult("2D → BIM raise (DXF plan → IFC model)", (body) => {
              body.appendChild(resultNote(`Raised <b>${r!.wall_count} walls</b> + <b>${r!.space_count ?? 0} rooms</b> `
                + `into a GUID-keyed IFC model, registered as a <b>2D Raise</b> discipline model — open it from the `
                + `federation panel to view or clash it.`, "ok"));
              body.appendChild(kvTable([
                { k: "Walls", v: String(r!.wall_count), strong: true },
                { k: "Rooms (IfcSpace)", v: String(r!.space_count ?? 0) },
                { k: "Total wall length", v: `${num(r!.total_wall_length_m)} m` },
                { k: "Total floor area", v: `${num(r!.total_floor_area_m2)} m²` },
                { k: "Wall height / thickness", v: `${r!.wall_height_m ?? 3} m / ${r!.wall_thickness_m ?? 0.2} m` },
                { k: "Drawing units", v: r!.units },
              ]));
            });
          };
          inp.click();
        }));
        b.appendChild(toolBtn2("✨ Draft BOQ from description", async () => {
          const desc = await askText("Draft BOQ from description",
            { label: "Describe the project (scope, size, structure, finishes):", multiline: true, okLabel: "Draft" });
          if (!desc || !desc.trim()) return;
          out.textContent = "drafting BOQ…";
          let r;
          try { r = await api.aiEstimate(pid, desc.trim()); }
          catch { out.textContent = "AI estimate failed"; return; }
          const money = (n: number) => `$${Math.round(n).toLocaleString()}`;
          if (!r.lines.length) { out.textContent = r.message || "no lines"; toast(r.message || "AI estimating not configured", "info"); return; }
          out.textContent = `BOQ ${money(r.total || 0)} · ${r.lines.length} lines`;
          showResult("AI-drafted Bill of Quantities", (body) => {
            body.appendChild(resultNote(`<b>${money(r!.total || 0)}</b> across ${r!.lines.length} lines (AI draft — review before use)`, "ok"));
            body.appendChild(kvTable(r!.lines.map((l) => ({
              k: `${l.division ? l.division + " · " : ""}${l.description} (${l.quantity} ${l.unit} @ ${money(l.rate)})`,
              v: money(l.amount ?? l.quantity * l.rate) }))));
          });
        }));
        b.appendChild(toolBtn2("▦ QTO by floor & discipline", async () => {
          out.textContent = "taking off by floor…";
          let q;
          try { q = await api.qtoByFloor(pid); }
          catch { out.textContent = "needs a source IFC (open one in Model)"; return; }
          const money = (n: number) => `$${Math.round(n).toLocaleString()}`;
          out.textContent = `QTO ${money(q.grand_total)} · ${q.storeys.length} floors`;
          showResult("Quantity takeoff — by floor & discipline", (body) => {
            body.appendChild(resultNote(`<b>${money(q.grand_total)}</b> across ${q.storeys.length} floors · ${q.element_count} elements`, "ok"));
            for (const s of q.storeys) {
              const h = document.createElement("div"); h.className = "section-title";
              h.style.cssText = "display:flex;justify-content:space-between;margin-top:8px";
              h.innerHTML = `<span>${s.storey}</span><span>${money(s.total)}</span>`;
              body.appendChild(h);
              body.appendChild(kvTable(s.lines.map((l) => ({
                k: `${l.ifc_class.replace("Ifc", "")} (${l.quantity} ${l.unit} @ ${money(l.rate)})`, v: money(l.amount) }))));
            }
            const dh = document.createElement("div"); dh.className = "section-title"; dh.style.marginTop = "10px";
            dh.textContent = "Discipline roll-up (all floors)"; body.appendChild(dh);
            body.appendChild(kvTable(q.by_discipline.map((l) => ({
              k: `${l.ifc_class.replace("Ifc", "")} · ${l.quantity} ${l.unit}`, v: money(l.amount) }))));
          });
        }));
        b.appendChild(out);
        const link = document.createElement("a"); link.href = "#"; link.className = "ref-link"; link.style.cssText = "display:inline-block;margin-top:6px;font-size:11px";
        link.textContent = "Manage budgets & change orders in Construction →";
        link.onclick = (e) => { e.preventDefault(); goWorkspace("construction"); };
        b.appendChild(link);
      },
      schedule: () => {
        const b = section("schedule", "Schedule", { requires: "project", tool: true });
        if (!b) return;
        for (const [label, file] of [["Gantt chart", "gantt"], ["Line of Balance", "lob"]] as const)
          b.appendChild(toolBtn2(`▤ ${label}`, () => window.open(api.url(`/projects/${projectId}/schedule/${file}.svg`), "_blank")));
        const out = document.createElement("div"); out.className = "meta"; out.style.marginTop = "4px";
        b.appendChild(toolBtn2("⛓ Critical path (CPM)", async () => {
          out.textContent = "computing…";
          const r = await api.scheduleCpm(pid);
          out.textContent = `${r.project_duration}d · ${r.critical_count}/${r.activity_count} critical`;
          showResult("Critical path (CPM)", (body) => {
            body.appendChild(resultNote(
              `Project duration <b>${r.project_duration} days</b> · <b>${r.critical_count}</b> of ${r.activity_count} activities critical`
              + (r.has_cycle ? " · ⚠ dependency cycle detected" : ""), r.has_cycle ? "bad" : "ok"));
            if (!r.activities.length) { body.appendChild(resultNote("No schedule activities yet — add some in Construction → Schedule.")); return; }
            body.appendChild(kvTable(r.activities.map((a) => ({
              k: `${a.critical ? "★ " : ""}${a.ref || ""} ${a.name || ""}`.trim(),
              v: `${a.duration}d · float ${a.total_float}`, strong: a.critical }))));
          });
        }));
        b.appendChild(toolBtn2("⏩ Accelerate (advisory)", async () => {
          out.textContent = "analyzing critical path…";
          const o = await api.scheduleOptimize(pid);
          const levers = o.crash.length + o.fast_track.length;
          out.textContent = o.has_cycle ? "⚠ dependency cycle — fix logic ties"
            : `${levers} lever(s) · best ~${o.best_single_lever_days}d`;
          showResult("Schedule acceleration — advisory", (body) => {
            body.appendChild(resultNote(o.headline, o.has_cycle ? "bad" : levers ? "ok" : ""));
            if (o.narrative) body.appendChild(resultNote(o.narrative + " <i>(AI)</i>"));
            if (o.crash.length) {
              const h = document.createElement("div"); h.className = "section-title"; h.style.marginTop = "10px";
              h.textContent = "Crash candidates (shorten the longest critical work)"; body.appendChild(h);
              body.appendChild(kvTable(o.crash.map((s) => ({
                k: `${s.ref || ""} ${s.name}`.trim(), v: `~${s.days_potential}d`, strong: true }))));
            }
            if (o.fast_track.length) {
              const h = document.createElement("div"); h.className = "section-title"; h.style.marginTop = "10px";
              h.textContent = "Fast-track candidates (overlap consecutive critical work)"; body.appendChild(h);
              body.appendChild(kvTable(o.fast_track.map((s) => ({
                k: `${s.name} ∥ ${s.predecessor}`, v: `~${s.days_potential}d` }))));
            }
            if (o.near_critical.length) {
              const h = document.createElement("div"); h.className = "section-title"; h.style.marginTop = "10px";
              h.textContent = "Near-critical watch (little float left)"; body.appendChild(h);
              body.appendChild(kvTable(o.near_critical.map((s) => ({
                k: `${s.ref || ""} ${s.name}`.trim(), v: `${s.total_float}d float` }))));
            }
            if (!levers && !o.near_critical.length)
              body.appendChild(resultNote("No acceleration levers — add a cost-loaded schedule with dependencies in Construction → Schedule."));
            body.appendChild(resultNote("<i>Advisory only — validate against logic ties, resources and cost before re-baselining.</i>"));
          });
        }));
        b.appendChild(toolBtn2("▤ Takt (line of balance)", () =>
          window.open(api.url(`/projects/${projectId}/schedule/takt.svg?floors=12`), "_blank")));
        // 4D construction sequence — scrub the takt timeline, isolating built-to-date elements
        const fourdBtn = toolBtn2("⏱ 4D sequence (scrub)", async () => {
          out.textContent = "loading 4D…";
          const seq = await api.schedule4d(pid);
          if (!seq.element_count) { out.textContent = "No published model elements to sequence — generate/publish a model first."; return; }
          out.textContent = "";
          const cf = await api.budgetCashflow(pid).catch(() => null);   // cost burn alongside the build
          const cfTotal = cf?.total ?? 0;
          const allGuids = [...new Set(seq.frames.flatMap((f) => f.new_guids))];
          const totalDays = seq.duration_days ?? seq.total_days ?? 0;
          const wrap = document.createElement("div"); wrap.style.marginTop = "4px";
          const lbl = document.createElement("div"); lbl.className = "meta";
          const slider = document.createElement("input"); slider.type = "range";
          slider.min = "0"; slider.max = String(totalDays); slider.value = String(totalDays);
          slider.style.width = "100%";
          const isoChk = document.createElement("label"); isoChk.className = "meta"; isoChk.style.cssText = "display:flex;gap:4px;align-items:center;cursor:pointer";
          const iso = document.createElement("input"); iso.type = "checkbox";
          isoChk.append(iso, document.createTextNode("isolate built (vs colour the whole model)"));
          const dateForDay = (day: number): string | null => {
            if (seq.source === "gc") { let d: string | null = null; for (const f of seq.frames) if (f.day <= day && f.date) d = f.date; return d; }
            if (seq.source === "p6" && seq.start_date && seq.finish_date && totalDays) {
              const s = new Date(seq.start_date).getTime(), e = new Date(seq.finish_date).getTime();
              return new Date(s + (e - s) * day / totalDays).toISOString().slice(0, 10);
            }
            return null;
          };
          const burnAt = (date: string | null): number => {   // cumulative cost up to the scrub date
            if (!cf || !date) return 0;
            const m = date.slice(0, 7); let burn = 0;
            for (const b of cf.series) { if (b.month <= m) burn = b.cumulative; }
            return burn;
          };
          const apply = async (day: number) => {
            const built = seq.frames.filter((f) => f.day <= day).flatMap((f) => f.new_guids);
            const done = built.length;
            const date = dateForDay(day);
            const burn = burnAt(date);
            lbl.innerHTML = `Day <b>${day}</b> / ${totalDays}${date ? ` · ${new Date(date).toLocaleDateString()}` : ""} · `
              + `built <b>${done}</b>/${seq.element_count} (${Math.round(done / seq.element_count * 100)}%)`
              + (cfTotal ? ` · 💰 burned <b>$${Math.round(burn).toLocaleString()}</b> (${Math.round(burn / cfTotal * 100)}% of $${Math.round(cfTotal).toLocaleString()})` : "");
            await colorize.reset();
            if (iso.checked) {
              if (built.length) await visibility.isolate(await sets.fromGuids(built)); else await visibility.showAll();
            } else {
              await visibility.showAll();
              const remaining = allGuids.filter((g) => !built.includes(g));
              if (remaining.length) await colorize.ghost(await sets.fromGuids(remaining), 0.12);
              if (built.length) await colorize.color(await sets.fromGuids(built), "#33d17a");   // built → green
            }
          };
          iso.onchange = () => void apply(+slider.value);
          slider.oninput = () => void apply(+slider.value);
          const reset = toolBtn2("⊞ Show all", async () => { await visibility.showAll(); await colorize.reset(); });
          const tag = document.createElement("div"); tag.className = "meta";
          if (seq.source === "gc") {                            // driven by the GC schedule (relational)
            const tied = seq.linked ? ` · ${seq.linked} elements hard-tied, ${seq.unlinked} by trade` : "";
            tag.textContent = `🗓 GC schedule: ${seq.activity_count ?? 0} activities${seq.start_date ? ` (${seq.start_date} → ${seq.finish_date})` : ""}${tied}`;
            wrap.append(tag);
          } else if (seq.source === "p6") {
            tag.textContent = `📅 P6 schedule: ${seq.start_date} → ${seq.finish_date} (${seq.p6_activities} activities)`;
            wrap.append(tag);
          }
          wrap.append(lbl, slider, isoChk, reset); out.appendChild(wrap);
          await apply(totalDays);
        });
        b.appendChild(fourdBtn);
        // 5D heatmap — color the whole model by schedule %-complete or cost variance
        const PROG_COLORS: Record<string, string> = { complete: "#33d17a", in_progress: "#ffd479", not_started: "#8aa0b8", unscheduled: "#5b6470" };
        const COST_COLORS: Record<string, string> = { over: "#e2554a", on_under: "#33d17a", unscheduled: "#5b6470" };
        const colorBy = async (mode: "progress" | "cost") => {
          if (!projectId) { notify("connect a project first", "error"); return; }
          out.textContent = "coloring model…";
          try {
            const map = await api.elements5dMap(projectId, mode);
            await colorize.reset();
            const palette = mode === "cost" ? COST_COLORS : PROG_COLORS;
            let legend = "";
            for (const [key, guids] of Object.entries(map.buckets)) {
              if (!guids.length) continue;
              const col = palette[key] ?? "#888";
              await colorize.color(await sets.fromGuids(guids), col);
              legend += `<span style="display:inline-flex;align-items:center;gap:3px;margin-right:8px">`
                + `<span style="width:9px;height:9px;border-radius:2px;background:${col};display:inline-block"></span>`
                + `${key.replace(/_/g, " ")} (${guids.length})</span>`;
            }
            out.innerHTML = `<div class="meta">5D heatmap — ${mode === "cost" ? "cost variance" : "% complete"}<br>${legend || "no elements resolved"}</div>`;
          } catch (e) { out.textContent = `color failed: ${(e as Error).message}`; }
        };
        b.appendChild(toolBtn2("🎨 Color by % complete", () => void colorBy("progress")));
        b.appendChild(toolBtn2("🎨 Color by cost variance", () => void colorBy("cost")));
        b.appendChild(toolBtn2("⊞ Reset colors", async () => { await colorize.reset(); out.textContent = ""; }));

        // Thematic "Color by property" — bucket the model by any IFC attribute / pset property
        // (built-world data-viz). Categorical buckets get distinct hues; numeric ranges a blue→red ramp.
        const hueColor = (i: number, n: number) => `hsl(${Math.round((i / Math.max(1, n)) * 320)}, 62%, 55%)`;
        const rampColor = (i: number, n: number) => `hsl(${Math.round((1 - (n <= 1 ? 0 : i / (n - 1))) * 210)}, 70%, 52%)`;
        const swatch = (col: string, label: string, count: number) =>
          `<span style="display:inline-flex;align-items:center;gap:3px;margin:0 8px 3px 0">`
          + `<span style="width:9px;height:9px;border-radius:2px;background:${col};display:inline-block"></span>${label} (${count})</span>`;
        b.appendChild(toolBtn2("🎨 Color by property…", async () => {
          if (!projectId) { notify("connect a project first", "error"); return; }
          out.textContent = "loading properties…";
          try {
            const fac = await api.colorFacets(projectId);
            const sel = document.createElement("select");
            sel.style.cssText = "width:100%;margin:2px 0;font-size:12px";
            const addGroup = (label: string, items: { prop: string; label: string; distinct: number }[]) => {
              if (!items.length) return;
              const og = document.createElement("optgroup"); og.label = label;
              for (const it of items) {
                const o = document.createElement("option"); o.value = it.prop;
                o.textContent = `${it.label} (${it.distinct})`; og.appendChild(o);
              }
              sel.appendChild(og);
            };
            addGroup("Attributes", fac.attributes);
            addGroup("Property sets", fac.properties);
            if (!sel.options.length) { out.textContent = "no colourable properties (upload a properties index first)"; return; }
            const legendEl = document.createElement("div"); legendEl.className = "meta"; legendEl.style.marginTop = "4px";
            const run = async () => {
              legendEl.textContent = "coloring…";
              const res = await api.colorBy(projectId!, sel.value);
              await colorize.reset();
              let legend = "";
              for (let i = 0; i < res.buckets.length; i++) {
                const bk = res.buckets[i]!; if (!bk.guids.length) continue; // safe: i < res.buckets.length loop bound
                const col = res.kind === "numeric" ? rampColor(i, res.buckets.length)
                  : (bk.label === "Other" ? "#5b6470" : hueColor(i, res.buckets.length));
                await colorize.color(await sets.fromGuids(bk.guids), col);
                legend += swatch(col, bk.label, bk.count);
              }
              legendEl.innerHTML = `<b>${res.kind}</b> · ${res.colored}/${res.total} coloured`
                + (res.unset ? ` · ${res.unset} unset` : "") + `<br>${legend}`;
            };
            sel.onchange = () => void run();
            const wrap = document.createElement("div"); wrap.append(sel, legendEl);
            out.innerHTML = ""; out.appendChild(wrap);
            await run();
          } catch (e) { out.textContent = `color-by failed: ${(e as Error).message}`; }
        }));

        // BIM data-QA — completeness check against required/recommended attributes, with a 3D highlight
        // of the non-compliant elements and a CSV export (Koh-inspired "asset data" QA).
        b.appendChild(toolBtn2("✅ Data QA (completeness)", async () => {
          if (!projectId) { notify("connect a project first", "error"); return; }
          out.textContent = "checking data completeness…";
          try {
            const qa = await api.dataQa(projectId);
            const tone = qa.compliant_pct >= 90 ? "var(--status-good,#33d17a)"
              : qa.compliant_pct >= 70 ? "var(--status-warn,#ffd479)" : "var(--status-crit,#e2554a)";
            let html = `<div class="meta"><b style="color:${tone};font-size:14px">${qa.compliant_pct}%</b> complete on required data`
              + ` · ${qa.noncompliant}/${qa.total} elements missing something</div>`;
            html += `<table style="font-size:11px;margin-top:4px;border-collapse:collapse">`;
            for (const r of qa.rules) {
              const okTone = r.missing ? "var(--status-warn,#ffd479)" : "var(--status-good,#33d17a)";
              html += `<tr><td style="padding:1px 8px 1px 0">${r.label}${r.severity === "recommended" ? " <span style='opacity:.55'>(rec.)</span>" : ""}</td>`
                + `<td style="padding:1px 6px">${r.present}/${qa.total}</td>`
                + `<td style="padding:1px 6px;color:${okTone}">${r.missing ? `${r.missing} missing` : "✓"}</td></tr>`;
            }
            html += `</table>`;
            out.innerHTML = html;
            if (qa.noncompliant_guids.length) {
              out.appendChild(toolBtn2(`🔺 Highlight ${qa.noncompliant} non-compliant`, async () => {
                await selectMap(await sets.fromGuids(qa.noncompliant_guids), { fit: true });
              }));
            }
            out.appendChild(toolBtn2("⬇ Export QA (CSV)", () => {
              const rows = [["rule", "severity", "present", "missing", "total"]];
              for (const r of qa.rules) rows.push([r.label, r.severity, String(r.present), String(r.missing), String(qa.total)]);
              const csv = rows.map((r) => r.map((c) => `"${c.replace(/"/g, '""')}"`).join(",")).join("\n");
              const url = URL.createObjectURL(new Blob([csv], { type: "text/csv" }));
              const a = document.createElement("a"); a.href = url; a.download = "data-qa.csv"; a.click();
              setTimeout(() => URL.revokeObjectURL(url), 1000);
            }));
          } catch (e) { out.textContent = `QA failed: ${(e as Error).message}`; }
        }));

        // Code-readiness check — does the model carry the data a plan review needs? (egress door
        // widths, fire ratings, space area/occupancy, egress stairs, classification). Property-level.
        b.appendChild(toolBtn2("🏛 Code-readiness check", async () => {
          if (!projectId) { notify("connect a project first", "error"); return; }
          out.textContent = "checking code-readiness…";
          try {
            const cc = await api.codeCheck(projectId);
            const tone = cc.readiness_pct >= 90 ? "var(--status-good,#33d17a)"
              : cc.readiness_pct >= 70 ? "var(--status-warn,#ffd479)" : "var(--status-crit,#e2554a)";
            let html = `<div class="meta"><b style="color:${tone};font-size:14px">${cc.readiness_pct}%</b> code-data ready`
              + ` · ${cc.passed}/${cc.checked} across ${cc.rules} rules <span class="meta">(${cc.code})</span></div>`;
            html += `<table style="font-size:11px;margin-top:4px;border-collapse:collapse">`;
            for (const r of cc.checks) {
              const st = r.status === "n/a" ? "<span style='opacity:.5'>n/a</span>"
                : r.failed ? `<span style="color:var(--status-warn,#ffd479)">${r.failed} to fix${r.below_min ? ` (${r.below_min} below min)` : ""}</span>`
                : `<span style="color:var(--status-good,#33d17a)">✓</span>`;
              const tt = `${r.note} — ${r.code}`.replace(/"/g, "&quot;");
              html += `<tr title="${tt}"><td style="padding:1px 8px 1px 0">${r.label} <span style="opacity:.5">${r.code}</span></td>`
                + `<td style="padding:1px 6px">${r.passed}/${r.checked}</td><td style="padding:1px 6px">${st}</td></tr>`;
            }
            html += `</table>`;
            out.innerHTML = html;
            if (cc.fail_guids.length) {
              out.appendChild(toolBtn2(`🔺 Highlight ${cc.fail_guids.length} to review`, async () => {
                await selectMap(await sets.fromGuids(cc.fail_guids), { fit: true });
              }));
            }
          } catch (e) { out.textContent = `code check failed: ${(e as Error).message}`; }
        }));
        // import a Primavera P6 export (.xer or .xml) so the 4D scrub shows real calendar dates
        const xerInput = document.createElement("input");
        xerInput.type = "file"; xerInput.accept = ".xer,.xml"; xerInput.style.display = "none";
        const xerBtn = toolBtn2("⬆ Import P6 schedule (.xer / .xml)", () => xerInput.click());
        xerBtn.dataset.cap = "edit";
        xerInput.addEventListener("change", async () => {
          const f = xerInput.files?.[0]; if (!f) return;
          out.textContent = `importing ${f.name}…`;
          try {
            const r = await api.importXer(pid, f);
            out.innerHTML = `imported <b>${r.count}</b> P6 activities (${r.start} → ${r.finish}) — open <b>⏱ 4D sequence</b> to scrub by date.`;
          } catch (e) { out.textContent = `import failed: ${(e as Error).message}`; }
          xerInput.value = "";
        });
        b.append(xerBtn, xerInput);
        b.appendChild(out);
      },
      qa: () => {
        const b = section("qa", "Coordination & QA", { requires: "sourceIfc", tool: true });
        if (!b) return;
        const out = document.createElement("div"); out.className = "meta"; out.style.marginTop = "4px";
        b.appendChild(toolBtn2("⚡ Run clash (struct)", () => withLoading(container, "Running clash detection", async () => {
          const r = await api.runClash(pid, { a: "IfcBeam,IfcSlab", b: "IfcColumn", min_volume: 0.05 });
          out.textContent = `${r.count} clashes · ${r.created_topics} topics`;
          toast(`Clash: ${r.count} found, ${r.created_topics} topics created`, r.count ? "info" : "success");
          await refreshIssues(); await reloadModelPins();
          showResult("Clash detection", (body) => {
            body.appendChild(resultNote(`<b>${r.count}</b> clashes found · <b>${r.created_topics}</b> RFI topics created.`, r.count ? "bad" : "ok"));
            body.appendChild(toolBtn2("Open Issues panel", () => (document.querySelector('.rail-btn[data-rail="issues"]') as HTMLElement)?.click()));
          });
        })));
        b.appendChild(toolBtn2("🔗 Coordinate clashes (grouped issues)", () => withLoading(container, "Running federated clash + coordination", async () => {
          let r;
          try { r = await api.clashFederated(pid, { coordinate: true }); }
          catch { toast("Federated clash needs ≥2 models — add one with “＋ Add discipline IFC”", "error"); return; }
          const co = r.coordination;
          out.textContent = co ? `${r.count} clashes → ${co.group_count} issues (${co.reduction}× reduction)` : `${r.count} clashes`;
          toast(co ? `${co.new} new · ${co.active} active · ${co.resolved} resolved · ${co.reappeared} reappeared` : "no clashes", r.count ? "info" : "success");
          await refreshIssues(); await reloadModelPins();
          showResult("Clash coordination", (body) => {
            if (!co) { body.appendChild(resultNote(`<b>${r!.count}</b> cross-model clashes.`, r!.count ? "bad" : "ok")); return; }
            body.appendChild(resultNote(`<b>${r!.count}</b> raw clashes grouped into <b>${co.group_count}</b> tracked coordination issues `
              + `(<b>${co.reduction}×</b> reduction) across <b>${r!.disciplines.join(" × ")}</b>.`, co.group_count ? "bad" : "ok"));
            body.appendChild(kvTable([
              { k: "New", v: String(co.new) }, { k: "Active (carried forward)", v: String(co.active) },
              { k: "Resolved (auto)", v: String(co.resolved) }, { k: "Reappeared (reopened)", v: String(co.reappeared) },
            ]));
            if (Object.keys(co.by_severity).length) {
              const h = document.createElement("div"); h.className = "meta"; h.style.cssText = "font-weight:700;margin:8px 0 2px"; h.textContent = "By severity"; body.appendChild(h);
              body.appendChild(kvTable(Object.entries(co.by_severity).map(([k, v]) => ({ k, v: String(v) }))));
            }
            if (Object.keys(co.by_discipline).length) {
              const h = document.createElement("div"); h.className = "meta"; h.style.cssText = "font-weight:700;margin:8px 0 2px"; h.textContent = "By discipline pair"; body.appendChild(h);
              body.appendChild(kvTable(Object.entries(co.by_discipline).map(([k, v]) => ({ k, v: String(v) }))));
            }
            body.appendChild(toolBtn2("📊 Coordination KPIs", () => withLoading(container, "Loading clash KPIs", async () => {
              const m = await api.clashMetrics(pid);
              showResult("Clash coordination KPIs", (kb) => {
                kb.appendChild(resultNote(`<b>${m.open}</b> open · <b>${m.closed}</b> closed · <b>${m.resolution_rate}%</b> resolved · `
                  + `reappearance <b>${m.reappearance_rate}%</b> over <b>${m.runs}</b> run(s).`, m.open ? "bad" : "ok"));
                kb.appendChild(kvTable([
                  { k: "Open aging 0–7d", v: String(m.aging["0-7"] ?? 0) }, { k: "8–14d", v: String(m.aging["8-14"] ?? 0) },
                  { k: "15–30d", v: String(m.aging["15-30"] ?? 0) }, { k: "30d+", v: String(m.aging["30+"] ?? 0) },
                ]));
                if (m.burn_down.length) {
                  const h = document.createElement("div"); h.className = "meta"; h.style.cssText = "font-weight:700;margin:8px 0 2px"; h.textContent = "Run burn-down"; kb.appendChild(h);
                  kb.appendChild(kvTable(m.burn_down.map((x) => ({ k: x.run, v: `+${x.new} / −${x.resolved}${x.reappeared ? ` / ↻${x.reappeared}` : ""}` }))));
                }
              });
            })));
            body.appendChild(toolBtn2("Open Issues panel", () => (document.querySelector('.rail-btn[data-rail="issues"]') as HTMLElement)?.click()));
          });
        })));
        b.appendChild(toolBtn2("📐 Alignment check (storey + origin)", () => withLoading(container, "Checking model alignment", async () => {
          let r;
          try { r = await api.modelAlignment(pid); }
          catch { toast("Alignment needs ≥2 models — add one with “＋ Add discipline IFC”", "error"); return; }
          out.textContent = r.aligned ? "Models aligned ✓" : `${r.issues.length} alignment issue(s)`;
          toast(r.message, r.aligned ? "success" : "info");
          const tone: Record<string, string> = { high: "var(--status-crit,#e2554a)", medium: "var(--status-warn,#ffd479)", low: "var(--muted)" };
          showResult("Model alignment", (body) => {
            body.appendChild(resultNote(r!.message, r!.aligned ? "ok" : "bad"));
            body.appendChild(kvTable(r!.models.map((m) => ({ k: m.name, v: m.error ? `error: ${m.error}` : `${m.storey_count} storeys${m.georef ? " · georef" : ""}` }))));
            for (const i of r!.issues) {
              const d = document.createElement("div"); d.style.cssText = `font-size:12px;margin:3px 0;border-left:3px solid ${tone[i.severity] || "var(--muted)"};padding-left:6px`;
              d.innerHTML = `<b>${i.model}</b> — ${i.detail}`;
              body.appendChild(d);
            }
          });
        })));
        b.appendChild(toolBtn2("＋ Add discipline IFC…", () => {
          const inp = document.createElement("input"); inp.type = "file"; inp.accept = ".ifc";
          inp.onchange = async () => {
            const file = inp.files?.[0]; if (!file) return;
            const disc = ((await askText("Add discipline IFC", { label: "Discipline (e.g. STR, MEP, ARCH):",
              value: file.name.replace(/\.ifc$/i, "").slice(0, 16) })) || "").trim();
            if (!disc) return;
            await withLoading(container, "adding discipline model", async () => {
              await api.addProjectModel(pid, file, disc);                                 // register server-side (for clash)
              await loader.loadIfc(new Uint8Array(await file.arrayBuffer()), nextId(disc)); // view it layered
              await fitToModels(); refreshFederation();
              toast(`added ${disc} discipline model — now in federated clash`, "success");
            });
          };
          inp.click();
        }));
        b.appendChild(toolBtn2("✓ Validate (IDS)", () => withLoading(container, "Validating (IDS)", async () => {
          const r = await api.validate(pid);
          out.textContent = `IDS ${r.status.toUpperCase()} — ${r.summary.passed}/${r.summary.passed + r.summary.failed}`;
          toast(`IDS ${r.status.toUpperCase()} — ${r.summary.passed} pass / ${r.summary.failed} fail`, r.status === "pass" ? "success" : "error");
          const failing = r.specifications.flatMap((s) => s.failed_guids);
          showResult("IDS validation", (body) => {
            body.appendChild(resultNote(`<b>IDS: ${r.status.toUpperCase()}</b> — ${r.summary.passed} pass / ${r.summary.failed} fail`, r.status === "pass" ? "ok" : "bad"));
            body.appendChild(kvTable(r.specifications.map((s) => ({
              k: `${s.status === "pass" ? "✓" : "✗"} ${s.name}`, v: `${s.passed}/${s.applicable}` }))));
            if (failing.length) {
              const hl = toolBtn2(`Highlight ${failing.length} failures in 3D`, async () => { await selectMap(await sets.fromGuids(failing), { fit: true }); });
              body.appendChild(hl);
            }
          });
        })));
        b.appendChild(out);
      },
      energy: () => {
        const b = section("energy", "Energy & MEP", { requires: "sourceIfc", tool: true });
        if (!b) return;
        const out = document.createElement("div"); out.className = "meta"; out.style.marginTop = "4px";
        b.appendChild(toolBtn2("⚡ Energy analysis", () => withLoading(container, "Analyzing building envelope", async () => {
          const e = await api.energy(pid);
          out.textContent = `EUI ${e.eui_kwh_m2_yr} kWh/m²·yr`;
          toast(`Energy: EUI ${e.eui_kwh_m2_yr} kWh/m²·yr`, "success");
          showResult("Energy analysis", (body) => body.appendChild(metricGrid([
            { label: "EUI (kWh/m²·yr)", value: String(e.eui_kwh_m2_yr) },
            { label: "Design heating", value: `${e.loads.design_heating_kw} kW` },
            { label: "Design cooling", value: `${e.loads.design_cooling_kw} kW` },
            { label: "UA", value: `${e.ua_w_per_k.total} W/K` },
            { label: "Annual energy", value: `${e.annual_kwh.total.toLocaleString()} kWh` },
            { label: "Conditioned floor", value: `${e.areas_m2.conditioned_floor_area} m²` },
            { label: "Window-wall ratio", value: String(e.areas_m2.window_wall_ratio) },
          ])));
        })));
        b.appendChild(toolBtn2("⚙ MEP inventory", async () => {
          const mep = await api.mep(pid);
          out.textContent = `${mep.total_distribution_elements} distribution elements`;
          showResult("MEP inventory", (body) => {
            body.appendChild(resultNote(`<b>${mep.total_distribution_elements}</b> distribution elements`));
            body.appendChild(kvTable(Object.entries(mep.by_class).map(([k, v]) => ({ k, v: String(v) }))));
          });
        }));
        b.appendChild(out);
      },
      authoring: () => {
        const b = section("authoring", "Authoring (round-trip)", { requires: "sourceIfc", tool: true });
        const group = panel.querySelector('.tool-group[data-tool="authoring"]') as HTMLElement | null;
        if (group) group.dataset.cap = "edit";   // whole section hidden for non-editors
        if (!b) return;
        const out = document.createElement("div"); out.className = "meta"; out.style.marginTop = "4px"; out.id = "au-out";
        const fix = toolBtn2("✎ Fix slabs: set LoadBearing", async () => {
          out.textContent = "editing IFC…";
          const r = await api.editIfc(pid, "set_pset", { ifc_class: "IfcSlab", pset: "Pset_SlabCommon", prop: "LoadBearing", value: true, dtype: "bool" }, true);
          const v = await api.validate(pid);
          out.innerHTML = `edited ${r.changed} slabs · IDS now: <b>${v.status.toUpperCase()}</b> · converting…`;
          const state = await waitForPublish(pid);
          if (state === "done") await loadProjectModel();
          out.innerHTML += `<br>publish: ${state}`;
        });
        fix.dataset.cap = "edit";
        const pub = toolBtn2("⟳ Republish (reconvert + reindex)", async () => {
          out.textContent = "publishing… (running in background)";
          await api.publish(pid);
          const state = await waitForPublish(pid, (s) => (out.textContent = `publish: ${s}…`));
          if (state === "done") await loadProjectModel();
          out.textContent = `publish ${state}`;
        });
        pub.dataset.cap = "edit";
        // Furnish & equip — add starter-library families (furniture / sanitary / appliances /
        // plants). Works on a generated massing model too, since the types are generated on demand.
        const furnish = document.createElement("div"); furnish.style.marginTop = "6px";
        const hint = document.createElement("div"); hint.className = "meta";
        hint.textContent = "Click a point in the model to set placement, then pick a family.";
        const sel = document.createElement("select"); sel.className = "tool-btn";
        sel.style.cssText = "display:block;width:100%;margin:4px 0"; sel.dataset.cap = "edit";
        sel.innerHTML = `<option value="">＋ Furnish & equip…</option>`;
        void api.familyLibrary().then((c) => {
          for (const [cat, items] of Object.entries(c.categories)) {
            const og = document.createElement("optgroup"); og.label = cat;
            for (const it of items) {
              const o = document.createElement("option"); o.value = it.key; o.textContent = it.label; og.appendChild(o);
            }
            sel.appendChild(og);
          }
          const ext = c.external.length ? ` · ${c.external.length} external` : "";
          hint.textContent = `${c.count} families in the library${ext}. Click a point to set placement, then pick a family — or import an IFC for more.`;
        }).catch(() => { hint.textContent = "Family library unavailable (API offline)."; });
        const place = toolBtn2("⊕ Place selected family", async () => {
          const key = sel.value;
          if (!key) { out.textContent = "pick a family first"; return; }
          const label = sel.options[sel.selectedIndex]?.text ?? key;
          const pos: [number, number] | null = lastPoint ? [lastPoint.x, -lastPoint.z] : null;
          out.textContent = `adding ${label}…`;
          await api.addFamily(pid, key, pos);
          out.textContent = `${label} added · converting…`;
          const state = await waitForPublish(pid);
          if (state === "done") await loadProjectModel();
          out.innerHTML = `added <b>${label}</b>${pos ? ` at ${pos[0].toFixed(1)}, ${pos[1].toFixed(1)} m` : " at origin"}<br>publish: ${state}`;
        });
        place.dataset.cap = "edit";
        // Import external IFC type content (manufacturer / 3rd-party families) into the project.
        const impInput = document.createElement("input");
        impInput.type = "file"; impInput.accept = ".ifc"; impInput.style.display = "none";
        const imp = toolBtn2("⇪ Import IFC families…", () => impInput.click());
        imp.dataset.cap = "edit";
        imp.title = "Import type content (families) from a manufacturer / 3rd-party IFC";
        impInput.addEventListener("change", async () => {
          const f = impInput.files?.[0]; if (!f) return;
          out.textContent = `importing families from ${f.name}…`;
          try {
            const r = await api.importFamilies(pid, f);
            if (!r.count) { out.textContent = "no new families found in that IFC"; impInput.value = ""; return; }
            const state = await waitForPublish(pid);
            if (state === "done") await loadProjectModel();
            out.innerHTML = `imported <b>${r.count}</b> famil${r.count === 1 ? "y" : "ies"} `
              + `(${r.imported.slice(0, 3).map((i) => i.name).join(", ")}${r.count > 3 ? "…" : ""}) · publish: ${state}`;
          } catch (e) { out.textContent = `import failed: ${(e as Error).message}`; }
          impInput.value = "";
        });
        furnish.append(hint, sel, place, imp, impInput);
        b.append(fix, pub, furnish, out);
      },
      drawings: () => {
        const b = section("drawings", "Drawings (2D)", { requires: "sourceIfc", tool: true });
        if (b) void buildDrawings(b);
      },
    };
    for (const key of order) builders[key]?.();
  }

  async function buildDrawings(host: HTMLElement) {
    if (!projectId) return;
    host.textContent = "";
    const open = async (path: string) => {
      const url = api.url(path);
      if (/\.pdf(\?|$)/.test(path)) {                       // PDF sheets → the in-app 2D editor (measure/markup)
        const { openPdfUrl, saveToDocuments } = await import("../drawings/openPdf");
        await openPdfUrl(api, url, "sheet.pdf", { saveLabel: "Save to Documents", onSave: saveToDocuments(api, projectId!) });
      } else { window.open(url, "_blank"); }                // SVG plans/elevations stay as native (vector)
    };
    const drawingBtn = (label: string, path: string) => {
      const b = document.createElement("button");
      b.className = "tool-btn"; b.textContent = label; b.style.cssText = "display:block;margin:4px 0;width:100%;text-align:left";
      b.onclick = () => open(path); host.appendChild(b);
    };
    try {
      const storeys = await api.drawingStoreys(projectId);
      for (const s of storeys) {
        const t = encodeURIComponent(`PLAN - ${s.name}`);
        const planQ = `elevation=${s.elevation}&cut_height=1.2&title=${t}`;
        drawingBtn(`▦ Plan: ${s.name}`, `/projects/${projectId}/drawings/plan.svg?${planQ}`);
        drawingBtn(`▦ Plan + callouts: ${s.name}`, `/projects/${projectId}/drawings/plan.svg?${planQ}&callouts=true`);
      }
      drawingBtn("⌗ Section A-A (X=27)", `/projects/${projectId}/drawings/section.svg?axis=x&offset=27&title=SECTION%20A-A`);
      for (const d of ["north", "south", "east", "west"]) drawingBtn(`◰ Elevation: ${d}`, `/projects/${projectId}/drawings/elevation.svg?direction=${d}`);
      const sep = document.createElement("div"); sep.className = "section-title"; sep.style.marginTop = "8px"; sep.textContent = "Sheet (all plans + section)";
      host.appendChild(sep);
      drawingBtn("⊞ Compose sheet (PDF)", `/projects/${projectId}/drawings/sheet.pdf?sheet=S-101`);
      drawingBtn("⊞ Compose sheet (SVG)", `/projects/${projectId}/drawings/sheet.svg?sheet=S-101`);
    } catch { host.textContent = "drawings unavailable (no source IFC)"; }
  }

  function colorFor(s: string): string {
    let h = 0; for (const c of s) h = (h * 31 + c.charCodeAt(0)) % 360;
    return `hsl(${h} 65% 55%)`;
  }

  // ---- issues / pins -------------------------------------------------------
  const pins = new PinOverlay(viewer.components, viewer.world, api, async (topic, vp) => {
    restoreCamera(viewer.world, vp);
    if (topic.element_guids?.[0]) await selectByGuid(topic.element_guids[0]);
    setStatus(`restored: ${topic.title}`);
  });

  async function refreshIssues() {
    if (!projectId) return;
    const topics = await api.pins(projectId);
    const panel = $("panel-issues");
    panel.innerHTML = `<div class="section-title">Issues (${topics.length})</div>`;
    const newBtn = document.createElement("button");
    newBtn.className = "tool-btn"; newBtn.dataset.cap = "review"; newBtn.textContent = "+ RFI from selection"; newBtn.style.marginBottom = "8px";
    newBtn.onclick = createRfiFromSelection;
    panel.appendChild(newBtn);
    for (const t of topics) panel.appendChild(issueCard(t));
  }
  function issueCard(t: Topic): HTMLElement {
    const el = document.createElement("div"); el.className = "issue";
    el.innerHTML = `<div class="t">${t.title}</div><div class="meta"><span class="badge ${t.type}">${t.type}</span> <span class="badge ${t.status}">${t.status}</span> ${t.assignee ?? ""}</div>`;
    el.onclick = async () => {
      const vps = projectId ? await api.viewpoints(projectId, t.id) : [];
      restoreCamera(viewer.world, vps[0] ?? null);
      if (t.element_guids?.[0]) await selectByGuid(t.element_guids[0]);
    };
    return el;
  }
  async function createRfiFromSelection() {
    if (!projectId || !selection) { setStatus("select an element first"); return; }
    const entry = Object.entries(selection)[0];
    if (!entry) { setStatus("select an element first"); return; }
    const [modelId, ids] = entry;
    const model = loader.fragments.list.get(modelId);
    const localId = [...ids][0];
    if (localId === undefined) { setStatus("select an element first"); return; }
    const [guid] = model ? await model.getGuidsByLocalIds([localId]) : [null];
    // AI/template draft from the selected element's context (Procore Draft-RFI parity)
    let suggestedTitle = "New RFI";
    let description: string | undefined;
    if (guid) {
      const note = (await askText("Describe the issue", { label: "Briefly describe the issue (optional — leave blank to let AI draft it):", value: "" })) || undefined;
      try {
        const el = await api.element(projectId, guid);
        const d = await api.draftRfi(projectId, el, note);
        suggestedTitle = d.subject || suggestedTitle;
        description = d.question;
        setStatus(d.source === "claude" ? `AI-drafted RFI (${d.discipline})` : `drafted RFI (${d.discipline})`);
      } catch { if (note) description = note; }
    }
    const title = (await askText("RFI title", { label: "RFI title:", value: suggestedTitle })) || suggestedTitle;
    const topic = await api.createTopic(projectId, {
      type: "rfi", title, description, status: "open",
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

  function fragsForProject(name: string): [string, string][] {
    if (/basichouse/i.test(name)) return [["/basichouse.frag", "BasicHouse-ARCH"]];
    if (/school/i.test(name)) return [["/school_str.frag", "school-STR"], ["/school_arq.frag", "school-ARQ"]];
    return [];
  }

  // ---- keyboard (viewer keys; nav keys stay in main) -----------------------
  function handleKey(key: string): boolean {
    switch (key) {
      case "f": void fitToModels(); return true;
      case "escape": void selectMap(null); return true;
      case "m": measure.setMode(measure.mode === "length" ? "off" : "length"); setStatus(`measure: ${measure.mode}`); return true;
      case "a": measure.setMode(measure.mode === "area" ? "off" : "area"); setStatus(`measure: ${measure.mode}`); return true;
      case "s": section.enabled = !section.enabled; setStatus(`section ${section.enabled ? "on (dbl-click face)" : "off"}`); return true;
      case "h": void visibility.showAll(); void colorize.reset(); return true;
      default: return false;
    }
  }

  // debug hook for automated/preview testing
  (window as unknown as Record<string, unknown>).__viewer = { viewer, loader, fitToModels, selectByGuid, openFile, referenceModels, THREE };

  // ---- self-initialise: load the project model + build panels --------------
  void (async () => {
    applySettings();
    await withLoading(container, `Loading ${ctx.projectName || "model"}`, async () => {
      if (projectId && await loadProjectModel()) return;
      const frags = ctx.projectName ? fragsForProject(ctx.projectName) : [["/school_str.frag", "school-STR"], ["/school_arq.frag", "school-ARQ"]];
      for (const [file, id] of frags) {
        if (!file || !id) continue;
        const res = await fetch(import.meta.env.BASE_URL + file.replace(/^\//, ""));
        if (res.ok) { await loader.loadFragments(await res.arrayBuffer(), id); modelLabels.set(id, id); }
      }
      refreshFederation();
      await fitToModels();
    });
    if (projectId) {
      try { await buildPanels(); } catch (e) { console.warn("panels:", e); }
    }
    void buildToolsPanel();
  })();

  // rebuild the tools panel when the persona changes (reorders primary vs "More tools")
  window.addEventListener("aec:persona", () => void buildToolsPanel());

  return {
    applySettings, selectByGuid, reloadModelPins, fitToModels, refreshIssues,
    anchorPoint: () => (lastPoint ? { x: lastPoint.x, y: lastPoint.y, z: lastPoint.z } : null),
    selectedGuidValue: () => selectedGuid,
    triggerOpen, openFile, addReferenceObject, loadSample, exportFrag, exportIfc, handleKey,
    onModelShown: () => {
      // Wait for the container to actually have dimensions (the workspace just toggled visible, so
      // layout may not have flushed yet) before resizing — resizing at 0×0 sets a NaN aspect.
      let tries = 60;
      const ready = () => {
        if ((!viewer.container.clientWidth || !viewer.container.clientHeight) && tries-- > 0) {
          requestAnimationFrame(ready); return;
        }
        viewer.world.renderer?.resize();   // container now has real dimensions → valid camera aspect
        const camNaN = Number.isNaN(viewer.world.camera.three.position.x);
        if (fitPending || camNaN) void fitToModels(); else void loader.fragments.core.update(true);
      };
      ready();
    },
  };
}

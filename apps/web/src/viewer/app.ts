// Heavy viewer module — dynamically imported by main.ts on first Model-workspace open,
// so the ~6MB three + @thatopen bundle never loads for users who only use the
// Construction (GC portal) or Finance (proforma) workspaces.
import * as THREE from "three";
import CameraControls from "camera-controls";
import { createViewer, renderMode, positionSun } from "./world";
import { sunAltAz, sunSceneDir } from "./solar";
import { ModelLoader } from "./loader";
import { loadReferenceModel } from "./referenceLoader";
import { type ModelIdMap } from "./modelIds";
import { showQrModal } from "../ui/qr";
import { SelectionSets } from "./selectionSets";
import { MeasureTool, type MeasureMode } from "../tools/measure";
import { SectionTool } from "../tools/section";
import { VisibilityTool } from "../tools/visibility";
import { ColorizeTool } from "../tools/colorize";
import { LayerManager } from "../tools/layers";
import { OriginTool } from "../tools/origin";
import { buildTree } from "../tree/tree";
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
    if (guid) void render5D(guid); else props5d.innerHTML = "";
    if (connected && projectId && guid) {
      try { renderProps(await api.element(projectId, guid)); return; } catch { /* fall through */ }
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
    propsBody.textContent = [
      `${el.ifc_class}  —  ${el.name ?? "(unnamed)"}`,
      `GUID: ${el.guid}`,
      `Type: ${el.type_name ?? "-"}    Storey: ${el.storey ?? "-"}`,
      "",
      ...Object.entries(el.psets).flatMap(([ps, props]) => [
        `[${ps}]`, ...Object.entries(props).map(([k, v]) => `  ${k}: ${v}`),
      ]),
    ].join("\n");
  }

  async function selectByGuid(guid: string, fit = false) {
    selectedGuid = guid;
    await selectMap(await sets.fromGuids([guid]), { guid, fit });
  }

  $("props-close").addEventListener("click", () => void selectMap(null));
  document.addEventListener("keydown", (e) => { if (e.key === "Escape" && !propsPanel.hidden) void selectMap(null); });

  // ---- 3D click ------------------------------------------------------------
  const mouse = new THREE.Vector2();
  container.addEventListener("click", async (e) => {
    if (measure.mode !== "off") { measure.create(); return; }
    mouse.set(e.clientX, e.clientY);
    const hit = await loader.fragments.raycast({
      camera: viewer.world.camera.three, mouse, dom: viewer.world.renderer!.three.domElement,
    });
    if (placeMode) { await capturePlacePoint(e, hit ?? null); return; }
    if (!hit) { await selectMap(null); return; }
    lastPoint = hit.point.clone();
    showCoords(lastPoint);
    const [guid] = await hit.fragments.getGuidsByLocalIds([hit.localId]);
    selectedGuid = guid ?? null;
    await selectMap({ [hit.fragments.modelId]: new Set([hit.localId]) }, { guid: guid ?? undefined });
    setStatus(`selected ${guid ?? hit.localId}`);
  });
  container.addEventListener("dblclick", () => { if (section.enabled) section.createPlane(); });

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
      try { if ((await api.project(pid)).has_source_ifc) replace = confirm(`Replace this project's model with ${file.name} (${mb(file.size)} MB)? Drawings & analysis will regenerate.`); }
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
    try { if ((await api.project(pid)).has_source_ifc) replace = confirm(`Replace this project's model with ${file.name}? Drawings & analysis will regenerate.`); }
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
  toolDivider();   // ── measure / visibility ──┊── collaboration ──

  // ---- live presence + shared viewpoints ----------------------------------
  type Peer = { user: string; seconds_ago: number; viewpoint: { position: THREE.Vector3Like; target: THREE.Vector3Like } | null };
  let peers: Peer[] = [];
  function captureViewpoint() {
    const p = new THREE.Vector3(), t = new THREE.Vector3();
    viewer.world.camera.controls.getPosition(p); viewer.world.camera.controls.getTarget(t);
    return { position: { x: p.x, y: p.y, z: p.z }, target: { x: t.x, y: t.y, z: t.z } };
  }
  function jumpToViewpoint(vp: Peer["viewpoint"]) {
    if (!vp) return;
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
    pickFromList(types.map((t) => ({ label: `${t.name}  ·  ${t.ifc_class.replace("Ifc", "").replace("Type", "")}`, value: t })), "Place family — pick a type")
      .then((t) => { if (!t) return; familyType = { guid: t.guid, name: t.name }; setPlaceMode("family"); notify(`click where to place “${t.name}”`, "info"); });
  }
  toolBtn("␡", "Delete selected element", async () => {
    if (!selectedGuid) { notify("select an element first", "error"); return; }
    if (!projectId) { notify("connect a project with a source IFC to edit", "error"); return; }
    if (!confirm(`Delete element ${selectedGuid.slice(0, 8)}? This re-authors the IFC.`)) return;
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
    const v = prompt("Move by E, N, Z metres (comma-separated):", "1, 0, 0");
    if (!v) return;
    const [dx, dy, dz] = v.split(",").map((n) => Number(n.trim()) || 0);
    await authorAndReload("move_element", { guid: selectedGuid, dx, dy, dz }, "move");
  }, "edit");
  toolBtn("⟲", "Rotate selected element (degrees about Z)", async () => {
    if (!selectedGuid) { notify("select an element first", "error"); return; }
    if (!projectId) { notify("connect a project with a source IFC to edit", "error"); return; }
    const a = Number(prompt("Rotate by degrees (about vertical axis):", "90"));
    if (!a) return;
    await authorAndReload("rotate_element", { guid: selectedGuid, angle: a }, "rotate");
  }, "edit");
  toolBtn("✎", "Edit a property on the selected element", async () => {
    if (!selectedGuid) { notify("select an element first", "error"); return; }
    if (!projectId) { notify("connect a project with a source IFC to edit", "error"); return; }
    const pset = prompt("Pset name:", "Pset_WallCommon"); if (!pset) return;
    const propName = prompt("Property:", "FireRating"); if (!propName) return;
    const value = prompt(`Value for ${propName}:`, ""); if (value === null) return;
    await authorAndReload("set_element_pset", { guid: selectedGuid, pset, prop: propName, value }, "property edit");
  }, "edit");
  toolBtn("⧉", "Copy selected element (offset E,N,Z metres)", async () => {
    if (!selectedGuid) { notify("select an element first", "error"); return; }
    if (!projectId) { notify("connect a project with a source IFC to edit", "error"); return; }
    const v = prompt("Copy with offset E, N, Z metres:", "1, 0, 0"); if (!v) return;
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
      const bx = boxes[0];
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
      const a = placePts[0];
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
      const [a, b] = placePts;
      params = { start: pl(a), end: pl(b), height: Number(prompt("Wall height (m):", "3.0")) || 3.0, thickness: Number(prompt("Wall thickness (m):", "0.2")) || 0.2 };
    } else if (kind === "column") {
      recipe = "add_column";
      params = { point: pl(placePts[0]), height: Number(prompt("Column height (m):", "3.0")) || 3.0 };
    } else if (kind === "family") {
      if (!familyType) { notify("no family selected", "error"); return; }
      recipe = "place_type";
      params = { type_guid: familyType.guid, position: pl(placePts[0]) };
    } else {
      recipe = "add_beam";
      const [a, b] = placePts;
      params = { start: pl(a), end: pl(b), depth: Number(prompt("Beam depth (m):", "0.5")) || 0.5 };
    }
    await authorAndReload(recipe, params, kind === "family" ? `family ${familyType?.name ?? ""}` : kind);
  }

  async function authorAndReload(recipe: string, params: Record<string, unknown>, label: string) {
    await withLoading(container, `authoring ${label} + republishing`, async () => {
      try {
        await api.editIfc(projectId!, recipe, params, true);
        notify(`${label} authored — converting…`, "info");
        const state = await waitForPublish(projectId!);
        if (state === "done") { const shown = await loadProjectModel(); notify(`${label} applied${shown ? " — shown" : ""}`, "success"); }
        else notify(`${label} authored — publish ${state}`, state === "error" ? "error" : "info");
        await reloadModelPins();
      } catch (err) { notify(`${label} failed: ${(err as Error).message}`, "error"); }
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
      } catch { return false; }                 // no published model yet
      await loader.disposeAll();
      modelLabels.clear();
      const id = `project-${projectId}`;
      modelLabels.set(id, ctx.projectName || "project");
      setLoadingLabel(container, "preparing geometry…");
      await loader.loadFragments(buffer, id);
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
            const d = await api.versionDiff(pid, h[1].version, h[0].version);
            body.appendChild(resultNote(`v${h[1].version} → v${h[0].version}: <b>+${d.added_count}</b> / <b>−${d.removed_count}</b> elements · ${d.unchanged_count} unchanged`, "ok"));
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
        inputs.e.value = lastPoint.x.toFixed(3); inputs.n.value = (-lastPoint.z).toFixed(3); inputs.z.value = lastPoint.y.toFixed(3);
      });
      fromPt.style.cssText = "";
      const apply = document.createElement("button");
      apply.className = "tool-btn"; apply.textContent = "Apply origin"; apply.style.marginLeft = "6px";
      apply.onclick = async () => {
        origin.setOrigin({ e: +inputs.e.value, n: +inputs.n.value, z: +inputs.z.value });
        for (const [, model] of loader.fragments.list) origin.applyTo(model.object as unknown as THREE.Object3D);
        await loader.fragments.core.update(true);
        if (connected && projectId) {
          fetch(api.url(`/projects/${projectId}`), { method: "PATCH", headers: { "Content-Type": "application/json", ...api.authHeaders() }, body: JSON.stringify({ origin: origin.getOrigin() }) }).catch(() => {});
        }
        setStatus(`origin set to E${inputs.e.value} N${inputs.n.value} Z${inputs.z.value}`);
      };
      ob.append(fromPt, apply);
    }

    // --- persona-ordered tool sections ---------------------------------------
    const builders: Record<string, () => void> = {
      exports: () => {
        const b = section("exports", "Exports", { requires: "sourceIfc", tool: true });
        if (!b) return;
        for (const [label, file] of [["Quantity takeoff (QTO/5D)", "qto"], ["COBie", "cobie"], ["Space schedule", "spaces"], ["4D schedule", "schedule"]] as const)
          b.appendChild(toolBtn2(`↓ ${label}`, () => window.open(api.url(`/projects/${projectId}/exports/${file}.xlsx`), "_blank")));
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
        b.appendChild(toolBtn2("↓ G702/G703 Pay App (PDF)", () => window.open(api.url(`/projects/${projectId}/cost/g702.pdf?app_no=1`), "_blank")));
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
              btn.onclick = () => window.open(api.url(`/projects/${projectId}/cost/lien-waiver.pdf?kind=${kind}&app_no=1`), "_blank");
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
        // import a Primavera P6 .xer so the 4D scrub shows real calendar dates
        const xerInput = document.createElement("input");
        xerInput.type = "file"; xerInput.accept = ".xer"; xerInput.style.display = "none";
        const xerBtn = toolBtn2("⬆ Import P6 schedule (.xer)", () => xerInput.click());
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
        void api.familyCatalog().then((c) => {
          for (const [cat, items] of Object.entries(c.categories)) {
            const og = document.createElement("optgroup"); og.label = cat;
            for (const it of items) {
              const o = document.createElement("option"); o.value = it.key; o.textContent = it.label; og.appendChild(o);
            }
            sel.appendChild(og);
          }
        }).catch(() => { hint.textContent = "Family library unavailable (API offline)."; });
        const place = toolBtn2("⊕ Place selected family", async () => {
          const key = sel.value;
          if (!key) { out.textContent = "pick a family first"; return; }
          const label = sel.options[sel.selectedIndex].text;
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
    const open = (path: string) => window.open(api.url(path), "_blank");
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
    const [modelId, ids] = Object.entries(selection)[0];
    const model = loader.fragments.list.get(modelId);
    const localId = [...ids][0];
    const [guid] = model ? await model.getGuidsByLocalIds([localId]) : [null];
    // AI/template draft from the selected element's context (Procore Draft-RFI parity)
    let suggestedTitle = "New RFI";
    let description: string | undefined;
    if (guid) {
      const note = prompt("Briefly describe the issue (optional — leave blank to let AI draft it):", "") || undefined;
      try {
        const el = await api.element(projectId, guid);
        const d = await api.draftRfi(projectId, el, note);
        suggestedTitle = d.subject || suggestedTitle;
        description = d.question;
        setStatus(d.source === "claude" ? `AI-drafted RFI (${d.discipline})` : `drafted RFI (${d.discipline})`);
      } catch { if (note) description = note; }
    }
    const title = prompt("RFI title:", suggestedTitle) || suggestedTitle;
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
    triggerOpen, openFile, loadSample, exportFrag, exportIfc, handleKey,
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

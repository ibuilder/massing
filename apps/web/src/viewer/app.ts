// Heavy viewer module — dynamically imported by main.ts on first Model-workspace open,
// so the ~6MB three + @thatopen bundle never loads for users who only use the
// Construction (GC portal) or Finance (proforma) workspaces.
import * as THREE from "three";
import CameraControls from "camera-controls";
import { createViewer } from "./world";
import { ModelLoader } from "./loader";
import { type ModelIdMap } from "./modelIds";
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
import { toast, withLoading } from "../ui/feedback";

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
  const nextId = () => `model-${++modelCount}`;

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

  async function showProps(map: ModelIdMap, guid?: string) {
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
  async function loadSample(file: string, label: string) {
    await withLoading(container, `loading ${label}`, async () => {
      const res = await fetch(import.meta.env.BASE_URL + file.replace(/^\//, ""));   // respect the deploy base
      if (!res.ok) throw new Error(`${label} not found`);
      await loader.loadFragments(await res.arrayBuffer(), nextId());
      await fitToModels();
      notify(`loaded ${label}`, "success");
    });
  }
  async function convertAndLoad(input: HTMLInputElement) {
    const file = input.files?.[0];
    input.value = "";
    if (!file) return;
    await withLoading(container, `converting ${file.name} (Autodesk bridge)`, async () => {
      const fd = new FormData(); fd.append("file", file);
      const res = await fetch(api.url("/convert"), { method: "POST", body: fd, headers: api.authHeaders() });
      if (!res.ok) { const msg = await res.json().catch(() => ({ detail: res.statusText })); throw new Error(msg.detail || "conversion unavailable"); }
      await loader.loadFragments(await res.arrayBuffer(), nextId());
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
      if (kind === "frag") await loader.loadFragments(bytes, nextId());
      else if (kind === "ifc") await loader.loadIfc(bytes, nextId());
      else {
        const fd = new FormData(); fd.append("file", new Blob([bytes as BlobPart]), name);
        const res = await fetch(api.url("/convert"), { method: "POST", body: fd, headers: api.authHeaders() });
        if (!res.ok) { const m = await res.json().catch(() => ({ detail: res.statusText })); throw new Error(m.detail || "conversion unavailable"); }
        await loader.loadFragments(await res.arrayBuffer(), nextId());
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
  function toolBtn(icon: string, title: string, onClick: (b: HTMLButtonElement) => void) {
    const b = document.createElement("button");
    b.textContent = icon; b.className = "tool-btn icon-btn"; b.title = title;
    b.setAttribute("aria-label", title);
    b.onclick = () => onClick(b);
    viewerTools.appendChild(b);
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

  // ---- modeling: author walls / columns / beams from ground clicks ---------
  type PlaceKind = "wall" | "column" | "beam";
  const PLACE_PTS: Record<PlaceKind, number> = { wall: 2, column: 1, beam: 2 };
  let placeMode: PlaceKind | null = null;
  const placePts: THREE.Vector3[] = [];
  const placeBtns = {} as Record<PlaceKind, HTMLButtonElement>;
  const groundPlane = new THREE.Plane(new THREE.Vector3(0, 1, 0), 0);
  const groundRay = new THREE.Raycaster();
  function setPlaceMode(kind: PlaceKind | null) {
    placeMode = kind; placePts.length = 0;
    (Object.keys(placeBtns) as PlaceKind[]).forEach((k) => placeBtns[k].classList.toggle("on", k === kind));
    if (kind) notify(`${kind}: click the ${PLACE_PTS[kind] === 1 ? "point" : "start point"} on the floor/grid`, "info");
  }
  placeBtns.wall = toolBtn("▭", "Add wall (click two points)", () => setPlaceMode(placeMode === "wall" ? null : "wall"));
  placeBtns.column = toolBtn("▮", "Add column (click one point)", () => setPlaceMode(placeMode === "column" ? null : "column"));
  placeBtns.beam = toolBtn("▬", "Add beam (click two points)", () => setPlaceMode(placeMode === "beam" ? null : "beam"));
  toolBtn("␡", "Delete selected element", async () => {
    if (!selectedGuid) { notify("select an element first", "error"); return; }
    if (!projectId) { notify("connect a project with a source IFC to edit", "error"); return; }
    if (!confirm(`Delete element ${selectedGuid.slice(0, 8)}? This re-authors the IFC.`)) return;
    await authorAndReload("delete_element", { guid: selectedGuid }, "delete");
  });
  const addOpening = async (kind: "door" | "window") => {
    if (!selectedGuid) { notify(`select a wall first, then add the ${kind}`, "error"); return; }
    if (!projectId) { notify("connect a project with a source IFC to author", "error"); return; }
    // use where you clicked the wall as the position (projected onto the wall axis); else centered
    const params: Record<string, unknown> = { host_guid: selectedGuid };
    if (lastPoint) params.position = [lastPoint.x, -lastPoint.z];
    await authorAndReload(kind === "window" ? "add_window" : "add_door", params, kind);
  };
  toolBtn("◧", "Add door to selected wall", () => void addOpening("door"));
  toolBtn("◨", "Add window to selected wall", () => void addOpening("window"));
  toolBtn("✥", "Move selected element (E,N,Z metres)", async () => {
    if (!selectedGuid) { notify("select an element first", "error"); return; }
    if (!projectId) { notify("connect a project with a source IFC to edit", "error"); return; }
    const v = prompt("Move by E, N, Z metres (comma-separated):", "1, 0, 0");
    if (!v) return;
    const [dx, dy, dz] = v.split(",").map((n) => Number(n.trim()) || 0);
    await authorAndReload("move_element", { guid: selectedGuid, dx, dy, dz }, "move");
  });
  toolBtn("⟲", "Rotate selected element (degrees about Z)", async () => {
    if (!selectedGuid) { notify("select an element first", "error"); return; }
    if (!projectId) { notify("connect a project with a source IFC to edit", "error"); return; }
    const a = Number(prompt("Rotate by degrees (about vertical axis):", "90"));
    if (!a) return;
    await authorAndReload("rotate_element", { guid: selectedGuid, angle: a }, "rotate");
  });
  toolBtn("✎", "Edit a property on the selected element", async () => {
    if (!selectedGuid) { notify("select an element first", "error"); return; }
    if (!projectId) { notify("connect a project with a source IFC to edit", "error"); return; }
    const pset = prompt("Pset name:", "Pset_WallCommon"); if (!pset) return;
    const propName = prompt("Property:", "FireRating"); if (!propName) return;
    const value = prompt(`Value for ${propName}:`, ""); if (value === null) return;
    await authorAndReload("set_element_pset", { guid: selectedGuid, pset, prop: propName, value }, "property edit");
  });
  toolBtn("⧉", "Copy selected element (offset E,N,Z metres)", async () => {
    if (!selectedGuid) { notify("select an element first", "error"); return; }
    if (!projectId) { notify("connect a project with a source IFC to edit", "error"); return; }
    const v = prompt("Copy with offset E, N, Z metres:", "1, 0, 0"); if (!v) return;
    const [dx, dy, dz] = v.split(",").map((n) => Number(n.trim()) || 0);
    await authorAndReload("copy_element", { guid: selectedGuid, dx, dy, dz }, "copy");
  });

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
    } else {
      recipe = "add_beam";
      const [a, b] = placePts;
      params = { start: pl(a), end: pl(b), depth: Number(prompt("Beam depth (m):", "0.5")) || 0.5 };
    }
    await authorAndReload(recipe, params, kind);
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
    try {
      const res = await fetch(api.url(`/projects/${projectId}/model.frag`), { headers: api.authHeaders() });
      if (!res.ok) return false;
      await loader.disposeAll();
      await loader.loadFragments(await res.arrayBuffer(), `project-${projectId}`);
      await fitToModels();
      return true;
    } catch { return false; }
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
  async function fitToModels() {
    const box = new THREE.Box3();
    viewer.world.scene.three.traverse((o) => { const m = o as THREE.Mesh; if (m.isMesh) box.expandByObject(m); });
    if (box.isEmpty()) return;
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

  function buildToolsPanel() {
    const panel = $("panel-tools");
    panel.innerHTML = "";

    const o = document.createElement("div");
    o.innerHTML = `<div class="section-title">Working origin (E / N / Z)</div>`;
    const inputs: Record<string, HTMLInputElement> = {};
    const cur = origin.getOrigin();
    for (const k of ["e", "n", "z"] as const) {
      const row = document.createElement("div"); row.className = "layer-row";
      const label = document.createElement("span"); label.className = "name"; label.textContent = k.toUpperCase();
      const inp = document.createElement("input"); inp.type = "number"; inp.value = String(cur[k]); inp.style.width = "110px";
      inputs[k] = inp; row.append(label, inp); o.appendChild(row);
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
        fetch(api.url(`/projects/${projectId}`), { method: "PATCH", headers: { "Content-Type": "application/json", ...api.authHeaders() }, body: JSON.stringify({ origin: origin.getOrigin() }) }).catch(() => {});
      }
      setStatus(`origin set to E${inputs.e.value} N${inputs.n.value} Z${inputs.z.value}`);
    };
    o.append(fromPt, apply); panel.appendChild(o);

    const m = document.createElement("div");
    m.innerHTML = `<div class="section-title" style="margin-top:14px">Measure</div>`;
    const readout = document.createElement("div"); readout.id = "measure-readout"; readout.className = "meta";
    readout.textContent = "mode: off — labels show values in 3D";
    const clr = document.createElement("button"); clr.className = "tool-btn"; clr.textContent = "Clear current"; clr.style.marginTop = "6px";
    clr.onclick = () => measure.deleteCurrent();
    m.append(readout, clr); panel.appendChild(m);

    const ex = document.createElement("div");
    ex.innerHTML = `<div class="section-title" style="margin-top:14px">Exports</div>`;
    if (!projectId) { const note = document.createElement("div"); note.className = "meta"; note.textContent = "connect a project to export"; ex.appendChild(note); }
    else {
      for (const [label, file] of [["Quantity takeoff (QTO/5D)", "qto"], ["COBie", "cobie"], ["Space schedule", "spaces"], ["4D schedule", "schedule"]] as const) {
        const b = document.createElement("button");
        b.className = "tool-btn"; b.textContent = `↓ ${label}`;
        b.style.cssText = "display:block;margin:4px 0;width:100%;text-align:left";
        b.onclick = () => window.open(api.url(`/projects/${projectId}/exports/${file}.xlsx`), "_blank");
        ex.appendChild(b);
      }
    }
    panel.appendChild(ex);

    const cst = document.createElement("div");
    cst.innerHTML = `<div class="section-title" style="margin-top:14px">Cost / Pay Apps</div>`;
    const cstOut = document.createElement("div"); cstOut.className = "meta"; cstOut.id = "cost-out";
    if (!projectId) { cstOut.textContent = "connect a project for cost roll-up"; cst.appendChild(cstOut); }
    else {
      const sumBtn = document.createElement("button");
      sumBtn.className = "tool-btn"; sumBtn.textContent = "Σ Cost Summary"; sumBtn.style.cssText = "display:block;margin:4px 0;width:100%;text-align:left";
      sumBtn.onclick = async () => {
        cstOut.textContent = "computing…";
        const s = await api.costSummary(projectId);
        const fmt = (v: number) => `$${v.toLocaleString()}`;
        cstOut.innerHTML = `Budget ${fmt(s.budget)}<br>Committed ${fmt(s.committed)} (${s.pct_committed}%)<br>Actual ${fmt(s.actual)} (${s.pct_spent}%)<br>Forecast ${fmt(s.forecast)}<br><b>Over/Under ${fmt(s.projected_over_under)}</b>`;
      };
      const g702Btn = document.createElement("button");
      g702Btn.className = "tool-btn"; g702Btn.textContent = "↓ G702/G703 Pay App (PDF)"; g702Btn.style.cssText = "display:block;margin:4px 0;width:100%;text-align:left";
      g702Btn.onclick = () => window.open(api.url(`/projects/${projectId}/cost/g702.pdf?app_no=1`), "_blank");
      cst.append(sumBtn, g702Btn, cstOut);
    }
    panel.appendChild(cst);

    const sch = document.createElement("div");
    sch.innerHTML = `<div class="section-title" style="margin-top:14px">Schedule</div>`;
    if (!projectId) { const n = document.createElement("div"); n.className = "meta"; n.textContent = "connect a project for schedule"; sch.appendChild(n); }
    else {
      for (const [label, file] of [["Gantt chart", "gantt"], ["Line of Balance", "lob"]] as const) {
        const b = document.createElement("button");
        b.className = "tool-btn"; b.textContent = `▤ ${label}`; b.style.cssText = "display:block;margin:4px 0;width:100%;text-align:left";
        b.onclick = () => window.open(api.url(`/projects/${projectId}/schedule/${file}.svg`), "_blank");
        sch.appendChild(b);
      }
    }
    panel.appendChild(sch);

    const qa = document.createElement("div");
    qa.innerHTML = `<div class="section-title" style="margin-top:14px">Coordination & QA</div>`;
    const qaOut = document.createElement("div"); qaOut.className = "meta"; qaOut.id = "qa-out";
    if (!projectId) { qaOut.textContent = "connect a project to run analysis"; qa.appendChild(qaOut); }
    else {
      const clashBtn = document.createElement("button");
      clashBtn.className = "tool-btn"; clashBtn.textContent = "⚡ Run clash (struct)"; clashBtn.style.cssText = "display:block;margin:4px 0;width:100%;text-align:left";
      clashBtn.onclick = () => withLoading(container, "Running clash detection", async () => {
        const r = await api.runClash(projectId, { a: "IfcBeam,IfcSlab", b: "IfcColumn", min_volume: 0.05 });
        qaOut.textContent = `${r.count} clashes — ${r.created_topics} topics created (see Issues)`;
        toast(`Clash: ${r.count} found, ${r.created_topics} topics created`, r.count ? "info" : "success");
        await refreshIssues(); await reloadModelPins();
      });
      const idsBtn = document.createElement("button");
      idsBtn.className = "tool-btn"; idsBtn.textContent = "✓ Validate (IDS)"; idsBtn.style.cssText = "display:block;margin:4px 0;width:100%;text-align:left";
      idsBtn.onclick = () => withLoading(container, "Validating (IDS)", async () => {
        const r = await api.validate(projectId);
        toast(`IDS ${r.status.toUpperCase()} — ${r.summary.passed} pass / ${r.summary.failed} fail`, r.status === "pass" ? "success" : "error");
        const failing = r.specifications.flatMap((s) => s.failed_guids);
        qaOut.innerHTML = `<b>IDS: ${r.status.toUpperCase()}</b> — ${r.summary.passed} pass / ${r.summary.failed} fail<br>` +
          r.specifications.map((s) => `${s.status === "pass" ? "✓" : "✗"} ${s.name} (${s.passed}/${s.applicable})`).join("<br>");
        if (failing.length) {
          const hl = document.createElement("button");
          hl.className = "tool-btn"; hl.textContent = `Highlight ${failing.length} failures`; hl.style.marginTop = "6px";
          hl.onclick = async () => { await selectMap(await sets.fromGuids(failing), { fit: true }); };
          qaOut.appendChild(document.createElement("br")); qaOut.appendChild(hl);
        }
      });
      qa.append(clashBtn, idsBtn, qaOut);
    }
    panel.appendChild(qa);

    const an = document.createElement("div");
    an.innerHTML = `<div class="section-title" style="margin-top:14px">Energy & MEP</div>`;
    const anOut = document.createElement("div"); anOut.className = "meta"; anOut.id = "an-out";
    if (!projectId) { anOut.textContent = "connect a project for analysis"; an.appendChild(anOut); }
    else {
      const eBtn = document.createElement("button");
      eBtn.className = "tool-btn"; eBtn.textContent = "⚡ Energy analysis"; eBtn.style.cssText = "display:block;margin:4px 0;width:100%;text-align:left";
      eBtn.onclick = () => withLoading(container, "Analyzing building envelope", async () => {
        const e = await api.energy(projectId);
        anOut.innerHTML = `<b>EUI ${e.eui_kwh_m2_yr} kWh/m²·yr</b><br>Heating ${e.loads.design_heating_kw} kW · Cooling ${e.loads.design_cooling_kw} kW<br>UA ${e.ua_w_per_k.total} W/K · annual ${e.annual_kwh.total.toLocaleString()} kWh<br>floor ${e.areas_m2.conditioned_floor_area} m² · WWR ${e.areas_m2.window_wall_ratio}`;
        toast(`Energy: EUI ${e.eui_kwh_m2_yr} kWh/m²·yr`, "success");
      });
      const mBtn = document.createElement("button");
      mBtn.className = "tool-btn"; mBtn.textContent = "⚙ MEP inventory"; mBtn.style.cssText = "display:block;margin:4px 0;width:100%;text-align:left";
      mBtn.onclick = async () => {
        const mep = await api.mep(projectId);
        anOut.innerHTML = `<b>${mep.total_distribution_elements} distribution elements</b><br>` + Object.entries(mep.by_class).map(([k, v]) => `${k}: ${v}`).join("<br>");
      };
      an.append(eBtn, mBtn, anOut);
    }
    panel.appendChild(an);

    const au = document.createElement("div");
    au.innerHTML = `<div class="section-title" style="margin-top:14px">Authoring (round-trip)</div>`;
    const auOut = document.createElement("div"); auOut.className = "meta"; auOut.id = "au-out";
    if (!projectId) { auOut.textContent = "connect a project to author"; au.appendChild(auOut); }
    else {
      const fixBtn = document.createElement("button");
      fixBtn.className = "tool-btn"; fixBtn.textContent = "✎ Fix slabs: set LoadBearing"; fixBtn.style.cssText = "display:block;margin:4px 0;width:100%;text-align:left";
      fixBtn.onclick = async () => {
        auOut.textContent = "editing IFC…";
        const r = await api.editIfc(projectId, "set_pset", { ifc_class: "IfcSlab", pset: "Pset_SlabCommon", prop: "LoadBearing", value: true, dtype: "bool" }, true);
        const v = await api.validate(projectId);
        auOut.innerHTML = `edited ${r.changed} slabs · IDS now: <b>${v.status.toUpperCase()}</b> (${v.summary.passed} pass / ${v.summary.failed} fail) · converting…`;
        const state = await waitForPublish(projectId);
        if (state === "done") await loadProjectModel();
        auOut.innerHTML += `<br>publish: ${state}`;
      };
      const pubBtn = document.createElement("button");
      pubBtn.className = "tool-btn"; pubBtn.textContent = "⟳ Republish (reconvert + reindex)"; pubBtn.style.cssText = "display:block;margin:4px 0;width:100%;text-align:left";
      pubBtn.onclick = async () => {
        auOut.textContent = "publishing… (running in background)";
        await api.publish(projectId);
        const state = await waitForPublish(projectId, (s) => (auOut.textContent = `publish: ${s}…`));
        if (state === "done") await loadProjectModel();
        auOut.textContent = `publish ${state}`;
      };
      au.append(fixBtn, pubBtn, auOut);
    }
    panel.appendChild(au);

    const dr = document.createElement("div");
    dr.innerHTML = `<div class="section-title" style="margin-top:14px">Drawings (2D)</div>`;
    const drBody = document.createElement("div"); drBody.className = "meta";
    dr.appendChild(drBody); panel.appendChild(dr);
    if (projectId) void buildDrawings(drBody);
    else drBody.textContent = "connect a project for plans/sections";
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
        drawingBtn(`▦ Plan: ${s.name}`, `/projects/${projectId}/drawings/plan.svg?elevation=${s.elevation}&cut_height=1.2&title=${t}`);
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
    newBtn.className = "tool-btn"; newBtn.textContent = "+ RFI from selection"; newBtn.style.marginBottom = "8px";
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
  (window as unknown as Record<string, unknown>).__viewer = { viewer, loader, fitToModels, selectByGuid, THREE };

  // ---- self-initialise: load the project model + build panels --------------
  void (async () => {
    applySettings();
    await withLoading(container, `Loading ${ctx.projectName || "model"}`, async () => {
      if (projectId && await loadProjectModel()) return;
      const frags = ctx.projectName ? fragsForProject(ctx.projectName) : [["/school_str.frag", "school-STR"], ["/school_arq.frag", "school-ARQ"]];
      for (const [file, id] of frags) {
        const res = await fetch(import.meta.env.BASE_URL + file.replace(/^\//, ""));
        if (res.ok) await loader.loadFragments(await res.arrayBuffer(), id);
      }
      await fitToModels();
    });
    if (projectId) {
      try { await buildPanels(); } catch (e) { console.warn("panels:", e); }
    }
    buildToolsPanel();
  })();

  return {
    applySettings, selectByGuid, reloadModelPins, fitToModels, refreshIssues,
    anchorPoint: () => (lastPoint ? { x: lastPoint.x, y: lastPoint.y, z: lastPoint.z } : null),
    selectedGuidValue: () => selectedGuid,
    triggerOpen, loadSample, exportFrag, exportIfc, handleKey,
    onModelShown: () => { setTimeout(() => { viewer.world.renderer?.resize(); void loader.fragments.core.update(true); }, 0); },
  };
}

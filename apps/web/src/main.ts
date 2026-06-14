import * as THREE from "three";
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
import { ApiClient, type ElementProps, type Topic } from "./api/client";

// ---- DOM refs ---------------------------------------------------------------
const $ = <T extends HTMLElement>(id: string) => document.getElementById(id) as T;
const container = $("container");
const statusEl = $("status");
const propsPanel = $("props");
const propsBody = $("props-body");
const toolbar = $("toolbar");
const setStatus = (m: string) => (statusEl.textContent = m);

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
  if (!hit) { await selectMap(null); return; }
  lastPoint = hit.point.clone();
  const [guid] = await hit.fragments.getGuidsByLocalIds([hit.localId]);
  await selectMap({ [hit.fragments.modelId]: new Set([hit.localId]) }, { guid: guid ?? undefined });
  setStatus(`selected ${guid ?? hit.localId}`);
});
container.addEventListener("dblclick", () => { if (section.enabled) section.createPlane(); });

// ---- file loading -----------------------------------------------------------
$("ifc-input").addEventListener("change", (e) => loadFile(e.target as HTMLInputElement, (b, id) => loader.loadIfc(b, id), "converting"));
$("frag-input").addEventListener("change", (e) => loadFile(e.target as HTMLInputElement, (b, id) => loader.loadFragments(b, id), "loading"));
async function loadFile(input: HTMLInputElement, load: (b: Uint8Array, id: string) => Promise<unknown>, verb: string) {
  const file = input.files?.[0];
  if (!file) return;
  try {
    setStatus(`${verb} ${file.name}…`);
    await load(new Uint8Array(await file.arrayBuffer()), nextId());
    await fitToModels();
    setStatus(`loaded ${file.name}`);
  } catch (err) { setStatus(`error: ${(err as Error).message}`); console.error(err); }
  finally { input.value = ""; }
}

// ---- toolbar ----------------------------------------------------------------
function toolBtn(label: string, onClick: (b: HTMLButtonElement) => void) {
  const b = document.createElement("button");
  b.textContent = label; b.className = "tool-btn"; b.onclick = () => onClick(b);
  toolbar.appendChild(b);
  return b;
}
const setMeasure = (m: MeasureMode) => {
  measure.setMode(m);
  setStatus(`measure: ${m}`);
  const ro = document.getElementById("measure-readout");
  if (ro) ro.textContent = m === "off" ? "mode: off — labels show values in 3D" : `mode: ${m} — click points; values appear as 3D labels`;
};
toolBtn("Dist", (b) => { const on = measure.mode !== "length"; setMeasure(on ? "length" : "off"); b.classList.toggle("on", on); });
toolBtn("Area", (b) => { const on = measure.mode !== "area"; setMeasure(on ? "area" : "off"); b.classList.toggle("on", on); });
toolBtn("Section", (b) => { section.enabled = !section.enabled; b.classList.toggle("on", section.enabled); setStatus(`section ${section.enabled ? "on (dbl-click face)" : "off"}`); });
toolBtn("Isolate", () => selection && visibility.isolate(selection));
toolBtn("Color", () => selection && colorize.color(selection, "#ffb000"));
toolBtn("Show all", async () => { await visibility.showAll(); await colorize.reset(); });

// ---- tabs -------------------------------------------------------------------
document.querySelectorAll<HTMLButtonElement>(".tab").forEach((tab) => {
  tab.onclick = () => {
    document.querySelectorAll(".tab").forEach((t) => t.classList.remove("active"));
    document.querySelectorAll(".panel").forEach((p) => p.classList.remove("active"));
    tab.classList.add("active");
    $(`panel-${tab.dataset.tab}`).classList.add("active");
  };
});

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

  // Issues / pins
  await refreshIssues();
  await pins.load(projectId);
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
    clashBtn.onclick = async () => {
      qaOut.textContent = "running clash…";
      const r = await api.runClash(projectId!, { a: "IfcBeam,IfcSlab", b: "IfcColumn", min_volume: 0.05 });
      qaOut.textContent = `${r.count} clashes — ${r.created_topics} topics created (see Issues)`;
      await refreshIssues();
      await pins.load(projectId!);
    };
    const idsBtn = document.createElement("button");
    idsBtn.className = "tool-btn"; idsBtn.textContent = "✓ Validate (IDS)";
    idsBtn.style.cssText = "display:block;margin:4px 0;width:100%;text-align:left";
    idsBtn.onclick = async () => {
      qaOut.textContent = "validating…";
      const r = await api.validate(projectId!);
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
    };
    qa.append(clashBtn, idsBtn, qaOut);
  }
  panel.appendChild(qa);

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

// ---- startup ----------------------------------------------------------------
async function startup() {
  connected = await api.health();
  if (connected) {
    const projects = await api.projects();
    projectId = projects[0]?.id ?? null;
    setStatus(connected && projectId ? `connected • project ${projects[0].name}` : "connected • no project");
  } else {
    setStatus("offline — open a .frag to view (API not reachable)");
  }
  // auto-load demo frag if present (served from public/)
  try {
    const res = await fetch("/school_str.frag");
    if (res.ok) {
      await loader.loadFragments(await res.arrayBuffer(), "school");
      await fitToModels();
    }
  } catch { /* no demo frag */ }
  if (projectId) await buildPanels();
  buildToolsPanel();
}

// debug hook for automated/preview testing
(window as unknown as Record<string, unknown>).__viewer = { viewer, loader, fitToModels, selectByGuid, THREE };

startup();

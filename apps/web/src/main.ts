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
const toolbar = $("toolbar");
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
  if (!hit) { await selectMap(null); return; }
  lastPoint = hit.point.clone();
  const [guid] = await hit.fragments.getGuidsByLocalIds([hit.localId]);
  selectedGuid = guid ?? null;
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
  await withLoading(container, `${verb} ${file.name}`, async () => {
    await load(new Uint8Array(await file.arrayBuffer()), nextId());
    await fitToModels();
    notify(`loaded ${file.name}`, "success");
  });
  input.value = "";
}

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

// ---- tabs -------------------------------------------------------------------
document.querySelectorAll<HTMLButtonElement>(".tab").forEach((tab) => {
  tab.onclick = () => {
    document.querySelectorAll(".tab").forEach((t) => t.classList.remove("active"));
    document.querySelectorAll(".panel").forEach((p) => p.classList.remove("active"));
    tab.classList.add("active");
    $(`panel-${tab.dataset.tab}`).classList.add("active");
    if (tab.dataset.tab === "portal") openPortalTab();
    if (tab.dataset.tab === "proforma") openProformaTab();
    if (tab.dataset.tab === "portfolio") openPortfolioTab();
  };
});

// ---- role-based navigation: show only the tabs relevant to a persona --------
const PERSONA_TABS: Record<string, string[] | null> = {
  all: null,
  developer: ["proforma", "portfolio", "issues", "tools", "portal"],
  gc: ["tree", "layers", "issues", "tools", "portal", "portfolio"],
  architect: ["tree", "layers", "issues", "tools", "portal"],
  engineer: ["tree", "layers", "tools", "issues"],
  subcontractor: ["portal", "issues", "tools"],
};
// each persona lands on the tab most relevant to their lifecycle stage
const PERSONA_HOME: Record<string, string> = {
  developer: "portfolio", gc: "portal", architect: "tree",
  engineer: "tools", subcontractor: "portal",
};
const personaSel = document.getElementById("persona") as HTMLSelectElement;
function applyPersona(p: string, goHome = false) {
  const allow = PERSONA_TABS[p] ?? null;
  let activeHidden = false;
  document.querySelectorAll<HTMLButtonElement>(".tab").forEach((t) => {
    const show = !allow || allow.includes(t.dataset.tab!);
    t.hidden = !show;
    if (!show && t.classList.contains("active")) activeHidden = true;
  });
  const home = goHome ? PERSONA_HOME[p] : null;
  if (home) {
    document.querySelector<HTMLButtonElement>(`.tab[data-tab="${home}"]`)?.click();
  } else if (activeHidden) {
    document.querySelector<HTMLButtonElement>(".tab:not([hidden])")?.click();
  }
  localStorage.setItem("persona", p);
}
personaSel.value = localStorage.getItem("persona") || "all";
personaSel.onchange = () => applyPersona(personaSel.value, true);  // jump to the role's home tab
applyPersona(personaSel.value);

// ---- collapsible / responsive sidebar ---------------------------------------
const appEl = document.getElementById("app")!;
function toggleSidebar() { appEl.classList.toggle("sidebar-collapsed"); }
(document.getElementById("sidebar-toggle") as HTMLButtonElement).onclick = toggleSidebar;

// drag-to-resize the side panel (persisted)
const savedW = localStorage.getItem("sidebar-w");
if (savedW) appEl.style.setProperty("--sidebar-w", savedW);
const resizer = document.createElement("div");
resizer.id = "sidebar-resize"; resizer.title = "Drag to resize";
$("sidebar").appendChild(resizer);
resizer.addEventListener("pointerdown", (e) => {
  e.preventDefault();
  resizer.setPointerCapture(e.pointerId);
  const move = (ev: PointerEvent) => {
    const w = Math.min(Math.max(ev.clientX, 220), 560);  // clamp 220–560px
    appEl.style.setProperty("--sidebar-w", `${w}px`);
  };
  const up = () => {
    resizer.removeEventListener("pointermove", move);
    resizer.removeEventListener("pointerup", up);
    localStorage.setItem("sidebar-w", getComputedStyle(appEl).getPropertyValue("--sidebar-w").trim());
  };
  resizer.addEventListener("pointermove", move);
  resizer.addEventListener("pointerup", up);
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
  }
  buildToolsPanel();  // always render Tools, even if the data panels fail
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
    case "\\": toggleSidebar(); break;
    case "?": toast(SHORTCUTS + " · \\ panel", "info", 6000); break;
    default: return;
  }
});

// debug hook for automated/preview testing
(window as unknown as Record<string, unknown>).__viewer = { viewer, loader, fitToModels, selectByGuid, THREE };

startup();

import * as THREE from "three";
import "./style.css";
import { createViewer } from "./viewer/world";
import { ModelLoader } from "./viewer/loader";
import { single, type ModelIdMap } from "./viewer/modelIds";
import { MeasureTool, type MeasureMode } from "./tools/measure";
import { SectionTool } from "./tools/section";
import { VisibilityTool } from "./tools/visibility";
import { ColorizeTool } from "./tools/colorize";

const container = document.getElementById("container")!;
const statusEl = document.getElementById("status")!;
const propsPanel = document.getElementById("props") as HTMLElement;
const propsBody = document.getElementById("props-body")!;
const toolbar = document.getElementById("toolbar")!;

const setStatus = (msg: string) => (statusEl.textContent = msg);

const viewer = createViewer(container);
const loader = new ModelLoader(viewer);

// Phase 3 tools, all reading from the shared World
const measure = new MeasureTool(viewer.components, viewer.world);
const section = new SectionTool(viewer.components, viewer.world);
const visibility = new VisibilityTool(viewer.components);
const colorize = new ColorizeTool(viewer.components);

let modelCount = 0;
const nextId = () => `model-${++modelCount}`;
let selection: ModelIdMap | null = null;

// ---- file loading -----------------------------------------------------------
const ifcInput = document.getElementById("ifc-input") as HTMLInputElement;
const fragInput = document.getElementById("frag-input") as HTMLInputElement;

ifcInput.addEventListener("change", () => handleFile(ifcInput, (b, id) => loader.loadIfc(b, id), "converting"));
fragInput.addEventListener("change", () => handleFile(fragInput, (b, id) => loader.loadFragments(b, id), "loading"));

async function handleFile(input: HTMLInputElement, load: (b: Uint8Array, id: string) => Promise<unknown>, verb: string) {
  const file = input.files?.[0];
  if (!file) return;
  try {
    setStatus(`${verb} ${file.name}…`);
    await load(new Uint8Array(await file.arrayBuffer()), nextId());
    setStatus(`loaded ${file.name}`);
  } catch (err) {
    console.error(err);
    setStatus(`error: ${(err as Error).message}`);
  } finally {
    input.value = "";
  }
}

// ---- click → select → properties (offline: reads from the model) ------------
const mouse = new THREE.Vector2();

container.addEventListener("click", async (event) => {
  if (measure.mode !== "off") { measure.create(); return; }

  mouse.set(event.clientX, event.clientY);
  const result = await loader.fragments.raycast({
    camera: viewer.world.camera.three,
    mouse,
    dom: viewer.world.renderer!.three.domElement,
  });

  if (!result) { selection = null; propsPanel.hidden = true; return; }

  selection = single(result.fragments.modelId, result.localId);
  const [data] = await result.fragments.getItemsData([result.localId], {
    attributesDefault: true,
    relations: { IsDefinedBy: { attributes: true, relations: true } },
    relationsDefault: { attributes: false, relations: false },
  });
  propsPanel.hidden = false;
  propsBody.textContent = JSON.stringify(data, null, 2);
  setStatus(`selected localId ${result.localId} in ${result.fragments.modelId}`);
});

container.addEventListener("dblclick", () => {
  if (section.enabled) section.createPlane();
});

// ---- toolbar ----------------------------------------------------------------
function button(label: string, onClick: () => void): HTMLButtonElement {
  const b = document.createElement("button");
  b.textContent = label;
  b.className = "tool-btn";
  b.onclick = onClick;
  toolbar.appendChild(b);
  return b;
}

function setMeasure(mode: MeasureMode) {
  measure.setMode(mode);
  setStatus(`measure: ${mode}`);
}

button("Measure: dist", () => setMeasure("length"));
button("Measure: area", () => setMeasure("area"));
button("Measure: off", () => setMeasure("off"));
button("Section", () => { section.enabled = !section.enabled; setStatus(`section ${section.enabled ? "on (dbl-click a face)" : "off"}`); });
button("Isolate sel", () => selection && visibility.isolate(selection));
button("Hide sel", () => selection && visibility.hide(selection));
button("Color sel", () => selection && colorize.color(selection, "#ffb000"));
button("Ghost sel", () => selection && colorize.ghost(selection));
button("Show all", async () => { await visibility.showAll(); await colorize.reset(); });

// debug hook for automated/preview testing (no effect on normal use)
async function fitToModels() {
  const box = new THREE.Box3();
  viewer.world.scene.three.traverse((o) => {
    const mesh = o as THREE.Mesh;
    if (mesh.isMesh) box.expandByObject(mesh);
  });
  if (box.isEmpty()) return null;
  const sphere = box.getBoundingSphere(new THREE.Sphere());
  await viewer.world.camera.controls.fitToSphere(sphere, true);
  await loader.fragments.core.update(true);
  return { center: sphere.center.toArray(), radius: sphere.radius };
}
(window as unknown as Record<string, unknown>).__viewer = { viewer, loader, nextId, fitToModels, THREE };

setStatus("ready — open an IFC or .frag file");

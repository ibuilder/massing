import type { ModelIdMap } from "@thatopen/components";
import * as THREE from "three";

import type { MeasureTool, MeasureMode } from "../tools/measure";
import type { SectionTool } from "../tools/section";

/** REL-4 leaf (split from `app.ts`): the measure / visibility toolbar group and the section-box
 *  tool. Pure extraction — behaviour, button order and DOM are unchanged; `app.ts` keeps the
 *  MeasureTool/SectionTool instances (click handlers, settings and keyboard shortcuts use them)
 *  and passes the seams it already owned. Two installers because the toolbar interleaves other
 *  groups between them. */

export interface MeasureSectionDeps {
  viewer: ReturnType<typeof import("./world").createViewer>;
  loader: import("./loader").ModelLoader;
  toolBtn: (icon: string, title: string, onClick: (b: HTMLButtonElement) => void, cap?: "edit" | "review") => HTMLButtonElement;
  setStatus: (m: string) => void;
  notify: (m: string, kind?: "info" | "success" | "error") => void;
  measure: MeasureTool;
  section: SectionTool;
  selection: () => ModelIdMap | null;
  visibility: { isolate: (sel: ModelIdMap) => Promise<void> | void; showAll: () => Promise<void> };
  colorize: { color: (sel: ModelIdMap, hex: string) => Promise<void> | void; reset: () => Promise<void> };
}

/** The measure / visibility button group (↔ ▱ ✂ ⊙ ◐ ⌫ ⊞), in the original order. */
export function installMeasureTools(d: MeasureSectionDeps): { setMeasure: (m: MeasureMode) => void } {
  const setMeasure = (m: MeasureMode) => {
    d.measure.setMode(m);
    d.setStatus(`measure: ${m}`);
    const ro = document.getElementById("measure-readout");
    if (ro) ro.textContent = m === "off" ? "mode: off — labels show values in 3D" : `mode: ${m} — click points; values appear as 3D labels`;
  };
  d.toolBtn("↔", "Measure distance (M)", (b) => { const on = d.measure.mode !== "length"; setMeasure(on ? "length" : "off"); b.classList.toggle("on", on); });
  d.toolBtn("▱", "Measure area (A)", (b) => { const on = d.measure.mode !== "area"; setMeasure(on ? "area" : "off"); b.classList.toggle("on", on); });
  d.toolBtn("✂", "Section plane (S) — dbl-click a face", (b) => { d.section.enabled = !d.section.enabled; b.classList.toggle("on", d.section.enabled); d.setStatus(`section ${d.section.enabled ? "on (dbl-click face)" : "off"}`); });
  d.toolBtn("⊙", "Isolate selection", () => { const sel = d.selection(); if (sel) void d.visibility.isolate(sel); });
  d.toolBtn("◐", "Color selection", () => { const sel = d.selection(); if (sel) void d.colorize.color(sel, "#ffb000"); });
  d.toolBtn("⌫", "Clear measurements", () => d.measure.deleteCurrent());
  d.toolBtn("⊞", "Show all (H)", async () => { await d.visibility.showAll(); await d.colorize.reset(); });
  return { setMeasure };
}

/** The section-box tool: 6 clipping planes shrunk inside the model bounds (renderer-level clip). */
export function installSectionBox(d: Pick<MeasureSectionDeps, "viewer" | "loader" | "toolBtn" | "setStatus" | "notify">): void {
  let sectionBox: THREE.Plane[] | null = null;
  d.toolBtn("⬚", "Section box (clip to model bounds)", (b) => {
    const r = d.viewer.world.renderer!.three;
    if (sectionBox) { r.clippingPlanes = []; sectionBox = null; b.classList.remove("on"); void d.loader.fragments.core.update(true); return; }
    const box = new THREE.Box3();
    d.viewer.world.scene.three.traverse((o) => { const msh = o as THREE.Mesh; if (msh.isMesh) box.expandByObject(msh); });
    if (box.isEmpty()) { d.notify("no model to clip", "error"); return; }
    const c = box.getCenter(new THREE.Vector3());
    const s = box.getSize(new THREE.Vector3()).multiplyScalar(0.35);   // keep the middle ~70%
    const mn = c.clone().sub(s), mx = c.clone().add(s);
    sectionBox = [
      new THREE.Plane(new THREE.Vector3(1, 0, 0), -mn.x), new THREE.Plane(new THREE.Vector3(-1, 0, 0), mx.x),
      new THREE.Plane(new THREE.Vector3(0, 1, 0), -mn.y), new THREE.Plane(new THREE.Vector3(0, -1, 0), mx.y),
      new THREE.Plane(new THREE.Vector3(0, 0, 1), -mn.z), new THREE.Plane(new THREE.Vector3(0, 0, -1), mx.z),
    ];
    r.localClippingEnabled = true; r.clippingPlanes = sectionBox;
    b.classList.add("on"); void d.loader.fragments.core.update(true);
    d.setStatus("section box on (toggle to clear)");
  });
}

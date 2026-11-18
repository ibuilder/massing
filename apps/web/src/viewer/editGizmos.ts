import * as THREE from "three";

import { type ModelIdMap } from "./modelIds";
import { TransformGizmo } from "./draft/transformGizmo";
import { PushPullGizmo } from "./draft/pushPull";

/**
 * R39-DECOMP-VIEWER — the direct-manipulation authoring gizmos, split from `app.ts`.
 *
 * Two edit-in-place gestures that live and die together: P5 drag-to-move (`move_element`) and
 * R38-PUSHPULL drag-the-top-handle (`set_extrusion_depth`). Both commit through a GUID-stable recipe
 * — never a transient viewer id, never arbitrary mesh — so the element survives the edit with every
 * reference intact, and the server refuses a gesture it cannot express through the normal recipe
 * error path (no client-side allowlist to drift).
 *
 * Pure extraction: behaviour, the "one gesture at a time" mutual exclusion, and the re-attach after a
 * commit are unchanged. `app.ts` kept the two `let` flags and the two lazy gizmo instances before;
 * they move here because nothing outside the gizmos reads them — the toolbar toggles, the selection
 * hook and the click guard all go through the handle below.
 */

export interface EditGizmoDeps {
  viewer: ReturnType<typeof import("./world").createViewer>;
  loader: import("./loader").ModelLoader;
  /** Current project, or null when disconnected — a gesture is a no-op without a source IFC to edit. */
  projectId: string | null;
  /** Grid-snap increment in metres for the move gizmo (0 = off); read live off the settings bar. */
  getSnap: () => number;
  setStatus: (m: string) => void;
  notify: (m: string, kind?: "info" | "success" | "error") => void;
  /** Author a GUID-stable recipe edit and reload; the gizmos ignore the outcome. */
  authorAndReload: (recipe: string, params: Record<string, unknown>, label: string) => Promise<unknown>;
  /** Re-select by GlobalId (re-attaches the gizmo on the edited element). */
  selectByGuid: (guid: string) => Promise<void>;
  /** The GlobalId of the current selection, read live at commit time. */
  selectedGuid: () => string | null;
  /** The current selection map, read live when a mode is toggled on. */
  selection: () => ModelIdMap | null;
}

export type EditMode = "move" | "pushpull" | "off";

export interface EditGizmos {
  /** On every selection change: attach the active gizmo (if any mode is on) to the new box. */
  onSelection(map: ModelIdMap): Promise<void>;
  /** Hide both gizmos (selection cleared). */
  hideAll(): void;
  /** True while a gizmo handle is being dragged — a drag is not a select/deselect click. */
  isDragging(): boolean;
  /** Toolbar ◈ handler: toggle edit-in-place (move) mode. */
  toggleMove(b: HTMLButtonElement): void;
  /** Toolbar ⇕ handler: toggle push/pull mode. */
  togglePushPull(b: HTMLButtonElement): void;
  /** Which gesture is armed (for tests and callers that need the current mode). */
  mode(): EditMode;
}

export function installEditGizmos(d: EditGizmoDeps): EditGizmos {
  let editInPlace = false;            // P5: show the move gizmo on the selected element
  let gizmo: TransformGizmo | null = null;
  let pushPullOn = false;             // R38-PUSHPULL: drag the top handle to deepen the extrusion
  let ppGizmo: PushPullGizmo | null = null;

  function ensureGizmo(): TransformGizmo {
    if (gizmo) return gizmo;
    const g = new TransformGizmo(
      d.viewer.world.camera.three,
      d.viewer.world.renderer!.three.domElement,
      d.viewer.world.scene.three,
      (enabled) => { d.viewer.world.camera.controls.enabled = enabled; },
    );
    g.onDrag = (delta) => d.setStatus(`move  ΔE ${delta.dx.toFixed(2)} · ΔN ${delta.dy.toFixed(2)} · ΔZ ${delta.dz.toFixed(2)} m`);
    g.onCommit = async (delta) => {
      const guid = d.selectedGuid();
      if (!guid || !d.projectId) return;
      await d.authorAndReload("move_element", { guid, dx: delta.dx, dy: delta.dy, dz: delta.dz }, "move");
      if (editInPlace && d.selectedGuid() === guid) await d.selectByGuid(guid);   // re-attach on the moved element
    };
    gizmo = g;
    return g;
  }

  /** Attach the move gizmo to a selection's world bounding box (edit-in-place mode). */
  async function attachGizmo(map: ModelIdMap) {
    const boxes = await d.loader.fragments.getBBoxes(map);
    const box = new THREE.Box3();
    for (const b of boxes) box.union(b);
    if (box.isEmpty()) return;
    const g = ensureGizmo();
    g.setSnap(d.getSnap());
    g.attach(box);
  }

  // R38-PUSHPULL: drag the top handle, the extrusion deepens.
  // The gesture commits through `set_extrusion_depth` — a recipe-parameter edit, GUID-stable, which
  // the server refuses for non-extrusions. No client-side allowlist: the refusal arrives through the
  // normal recipe error path and the A29 failure marker rules apply.
  function ensurePushPull(): PushPullGizmo {
    if (ppGizmo) return ppGizmo;
    const g = new PushPullGizmo(
      d.viewer.world.camera.three,
      d.viewer.world.renderer!.three.domElement,
      d.viewer.world.scene.three,
      (enabled) => { d.viewer.world.camera.controls.enabled = enabled; },
    );
    g.onDrag = (depth) => d.setStatus(`push/pull  depth ${depth.toFixed(2)} m`);
    g.onCommit = async (depth) => {
      const guid = d.selectedGuid();
      if (!guid || !d.projectId) return;
      await d.authorAndReload("set_extrusion_depth", { guid, depth }, "push/pull");
      if (pushPullOn && d.selectedGuid() === guid) await d.selectByGuid(guid);   // re-attach at the new height
    };
    ppGizmo = g;
    return g;
  }

  async function attachPushPull(map: ModelIdMap) {
    const boxes = await d.loader.fragments.getBBoxes(map);
    const box = new THREE.Box3();
    for (const b of boxes) box.union(b);
    if (box.isEmpty()) return;
    ensurePushPull().attach(box);
  }

  return {
    async onSelection(map: ModelIdMap) {
      if (editInPlace) await attachGizmo(map);
      else if (pushPullOn) await attachPushPull(map);
    },
    hideAll() { gizmo?.hide(); ppGizmo?.hide(); },
    isDragging() { return Boolean(gizmo?.dragging); },
    toggleMove(b: HTMLButtonElement) {
      editInPlace = !editInPlace;
      b.classList.toggle("on", editInPlace);
      if (editInPlace) {
        pushPullOn = false; ppGizmo?.hide();   // one gesture at a time — two gizmos on one box read as noise
        const sel = d.selection();
        if (sel) { void attachGizmo(sel); }
        d.notify("Edit-in-place on — select an element and drag the gizmo to move it", "info");
      } else {
        gizmo?.hide();
        d.setStatus("edit-in-place off");
      }
    },
    togglePushPull(b: HTMLButtonElement) {
      pushPullOn = !pushPullOn;
      b.classList.toggle("on", pushPullOn);
      if (pushPullOn) {
        editInPlace = false; gizmo?.hide();
        const sel = d.selection();
        if (sel) { void attachPushPull(sel); }
        d.notify("Push/pull on — select an element and drag its top handle; the base stays put", "info");
      } else {
        ppGizmo?.hide();
        d.setStatus("push/pull off");
      }
    },
    mode() { return editInPlace ? "move" : pushPullOn ? "pushpull" : "off"; },
  };
}

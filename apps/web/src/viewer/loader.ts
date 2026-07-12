import * as OBC from "@thatopen/components";
import * as FRAGS from "@thatopen/fragments";
// Local worker (offline). The package's getWorker() fetches from unpkg — we must NOT use
// it, per the offline non-negotiable in CLAUDE.md. Vite serves this from node_modules.
import workerUrl from "@thatopen/fragments/worker?url";
import type { Viewer } from "./world";

/**
 * Owns the FragmentsManager and IFC→Fragments conversion. In production, IFC is
 * pre-converted on the server (guide §4); this in-browser importer exists for the
 * Phase 0/1 smoke test and small files only.
 */
export class ModelLoader {
  readonly fragments: OBC.FragmentsManager;
  private importer = new FRAGS.IfcImporter();

  constructor(viewer: Viewer) {
    // local web-ifc WASM copied into public/wasm/ by scripts/copy-wasm.mjs
    this.importer.wasm = { absolute: true, path: import.meta.env.BASE_URL + "wasm/" };

    this.fragments = viewer.components.get(OBC.FragmentsManager);
    this.fragments.init(workerUrl);

    const { controls, three: camera } = viewer.world.camera;
    controls.addEventListener("rest", () => this.fragments.core.update(true));
    controls.addEventListener("update", () => this.fragments.core.update());

    // when any model is registered, hook it to the camera and add it to the scene
    this.fragments.list.onItemSet.add(({ value: model }) => {
      model.useCamera(camera);
      viewer.world.scene.three.add(model.object);
      void this.fragments.core.update(true);
    });
  }

  /** Convert a small IFC in-browser, then load the resulting fragments. */
  async loadIfc(bytes: Uint8Array, modelId: string) {
    const fragBytes = await this.importer.process({ bytes });
    return this.loadFragments(fragBytes, modelId);
  }

  /** Load pre-converted .frag bytes (the production path). */
  async loadFragments(buffer: ArrayBuffer | Uint8Array, modelId: string) {
    const model = await this.fragments.core.load(buffer, { modelId });
    await this.fragments.core.update(true);
    return model;
  }

  /** Remove every loaded model (used before reloading a republished project). */
  async disposeAll() {
    for (const id of [...this.fragments.list.keys()]) {
      await this.fragments.core.disposeModel(id);
    }
    await this.fragments.core.update(true);
  }
}

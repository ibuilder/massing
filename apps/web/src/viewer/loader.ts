import * as OBC from "@thatopen/components";
import * as FRAGS from "@thatopen/fragments";
// Local worker (offline). The package's getWorker() fetches from unpkg — we must NOT use
// it, per the offline non-negotiable in CLAUDE.md. Vite serves this from node_modules.
import workerUrl from "@thatopen/fragments/worker?url";
import { coalesced } from "./raf";
import { fitShadowFrustum } from "./world";
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
    // R23-UPDATE-COALESCE: `update` fires many times per frame while the camera moves, and this used
    // to run a full fragments pass on EVERY one — the textbook expensive-work-per-event mistake, and
    // strictly wasted since only the last one before the paint can affect what the user sees.
    // Coalescing to one pass per animation frame keeps the visual result identical while cutting the
    // work to at most once per painted frame. `rest` keeps its immediate full-quality pass: it fires
    // once when motion stops, which is exactly when the expensive version is worth paying for.
    const cheapPass = coalesced(() => void this.fragments.core.update());
    controls.addEventListener("rest", () => {
      cheapPass.cancel();                           // the full pass supersedes any pending cheap one
      void this.fragments.core.update(true);
    });
    controls.addEventListener("update", () => cheapPass.trigger());

    // when any model is registered, hook it to the camera and add it to the scene
    this.fragments.list.onItemSet.add(({ value: model }) => {
      model.useCamera(camera);
      viewer.world.scene.three.add(model.object);
      void this.fragments.core.update(true);
      // R23-SHADOW-COST: geometry is one of only two things that can change a shadow (the other is
      // the sun). With per-frame shadow updates off, refitting here is what keeps them correct — and
      // it also re-spends the shadow map's texels on the model that just arrived.
      fitShadowFrustum(viewer.world);
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

  /** Remove one loaded model by id (no-op if absent) — e.g. an orphaned draft preview. */
  async disposeOne(modelId: string) {
    if (!this.fragments.list.has(modelId)) return;
    await this.fragments.core.disposeModel(modelId);
    await this.fragments.core.update(true);
  }
}

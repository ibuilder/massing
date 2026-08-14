// R39-DECOMP-VIEWER ⑥ + R39-VIEWER-OBS — the published-model load, lifted out of `app.ts`.
//
// It moved because instrumenting it in place was impossible: `app.ts` sits on a per-file ratchet with
// zero headroom, and the ratchet's stated purpose is to force the question "should this live in a
// domain module instead?" rather than to be raised. For this routine the answer was plainly yes — it
// is a self-contained fetch → parse → show sequence that only touches `app.ts` state through a
// handful of callbacks.
//
// **Every capture here was `const` in `app.ts`**, checked rather than assumed, so by-value threading
// is safe and no accessor is needed. That is NOT the general rule in this decomposition — the
// `projectPanel` slice had `let` captures (`selectedGuid`, `lastPoint`) that had to cross as refs,
// because a value copy compiles cleanly and silently freezes whatever they held. See
// `tools/projectPanel.test.ts`. The distinction is per-slice and has to be re-checked each time.
import { fetchArrayBufferWithProgress, setLoadingLabel, withLoading } from "../ui/feedback";
import type { ApiClient } from "../api/client";
import type { ModelLoader } from "./loader";
import { trackModelLoad, type TrackerDeps } from "./loadTimings";
import { usd } from "../ui/charts";

export interface LoadProjectModelDeps {
  api: ApiClient;
  projectId: string | null;
  projectName?: string;
  container: HTMLElement;
  loader: ModelLoader;
  modelLabels: Map<string, string>;
  refreshFederation: () => void;
  fitToModels: () => Promise<void>;
  collabResync: () => Promise<void>;
  setStatus: (s: string) => void;
  /** The live canvas, read at first frame. Deliberately not the container — see below. */
  canvas: () => HTMLCanvasElement | null;
  /** R39-VIEWER-OBS transport. Omitted in tests that do not care about timings. */
  timings?: Pick<TrackerDeps, "send"> & Partial<TrackerDeps>;
}

export async function loadProjectModel(deps: LoadProjectModelDeps): Promise<boolean> {
  const { api, projectId, container, loader, modelLabels } = deps;
  if (!projectId) return false;

  // Armed before the fetch, so a load that dies downloading still produces a row.
  const track = deps.timings
    ? trackModelLoad(`project-${projectId}`, { now: () => performance.now(), ...deps.timings })
    : null;

  return (await withLoading(container, "loading model", async () => {
    const mb = (n: number) => (n / 1048576).toFixed(1);
    let buffer: ArrayBuffer;
    try {
      buffer = await fetchArrayBufferWithProgress(
        api.url(`/projects/${projectId}/model.frag`), { headers: api.authHeaders() },
        (loaded, total) => setLoadingLabel(container,
          `downloading model ${Math.round(loaded / total * 100)}% (${mb(loaded)}/${mb(total)} MB)`));
    } catch { track?.cancel(); return false; }   // 404 / no published model yet — fall through to no-model
    // A metadata-only project (property index uploaded, geometry never published) has no .frag, so the
    // request 404s above. Guard the degenerate variants too: an empty body, or a non-.frag payload
    // (e.g. a proxy / SPA host that rewrites a 404 into a 200 HTML page) would otherwise reach the
    // Fragments worker, which can *hang* — not reject — on input it can't parse, leaving the
    // "loading model" overlay up forever. Fail open to the same graceful no-model state a brand-new
    // project already takes.
    //
    // Both degenerate cases `cancel()` rather than reporting: a project with no geometry is not a
    // slow load, and filing it as one would fill the table with rows about projects that have
    // nothing to draw.
    track?.fetched(buffer.byteLength);
    if (buffer.byteLength === 0) { track?.cancel(); return false; }
    await loader.disposeAll();
    modelLabels.clear();
    const id = `project-${projectId}`;
    modelLabels.set(id, deps.projectName || "project");
    setLoadingLabel(container, "preparing geometry…");
    try {
      await loader.loadFragments(buffer, id);
    } catch { modelLabels.delete(id); track?.failed(); return false; }   // corrupt / non-.frag bytes
    track?.parsed();
    deps.refreshFederation();
    await deps.fitToModels();
    // First frame. Measured on the NEXT animation frame, after fitToModels has set the camera, and
    // read from the CANVAS rather than the container — that difference is the entire point: in the
    // CANVAS-RESIZE bug the container measured 830x572 while the canvas was 0x493, so a container
    // reading would have called a load nobody could see a healthy one.
    if (track) requestAnimationFrame(() => {
      const c = deps.canvas();
      track.firstFrame(c?.width ?? 0, c?.height ?? 0);
    });
    // COLLAB-1: we now hold the latest published model — sync the known version + clear any reload
    // banner, so this client's own publish never re-nags us to reload.
    await deps.collabResync();
    // E7: tell the paper views (Drawings workspace plans + schedules) the model changed — an open
    // sheet re-renders itself against the new geometry.
    window.dispatchEvent(new CustomEvent("aec:model-published"));
    // PROFORMA-LIVE: the finance numbers follow the model — after every (re)load, surface the
    // takeoff-priced cost + budget delta in the status line (server-cached per version; best-effort)
    void api.proformaLive(projectId).then((pl) => {
      const delta = pl.delta_vs_budget != null
        ? ` · ${pl.delta_vs_budget >= 0 ? "▲" : "▼"} ${usd(Math.abs(pl.delta_vs_budget))} vs budget` : "";
      deps.setStatus(`model cost ${usd(pl.est_construction_cost)} · GFA ${pl.gfa_m2} m²${delta}`);
    }).catch(() => { /* no source IFC / offline — the readout is optional */ });
    return true;
  })) ?? false;
}

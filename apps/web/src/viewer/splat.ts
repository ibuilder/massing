/**
 * Reality-capture walkthrough — 3D Gaussian splats (Wave 8 ③). Loads a `.splat` / `.ksplat` / `.ply`
 * splat scene captured on site (phone / drone photogrammetry → splat) as a **view-only overlay** next
 * to the BIM model, so the field team can walk the as-built reality against the design. The splat
 * renderer (`@mkkellogg/gaussian-splats-3d`, MIT) drops into the existing three.js scene as a
 * `THREE.Group` and self-sorts each frame via its internal `onBeforeRender` — no render-loop surgery.
 *
 * Offline-first (our non-negotiable): the library and its sort worker are bundled (the worker is an
 * inline blob, no CDN fetch), and the scene loads from an in-memory object URL, never the network.
 * The library is heavy, so it is dynamically imported here — Vite splits it into its own lazy chunk
 * that is fetched only when a user actually opens a reality-capture scene.
 *
 * Note: the blob-URL sort worker needs `worker-src blob:` when the opt-in strict CSP is enabled.
 */
import * as THREE from "three";

export interface SplatResult {
  object: THREE.Object3D;        // a THREE.Group (DropInViewer) ready to add to the scene
  info: string;                  // short human note
  dispose: () => void;           // frees GPU buffers + the sort worker
}

// extension → the library's SceneFormat enum value (Splat=0, KSplat=1, Ply=2), resolved at runtime.
function formatFor(ext: string, SceneFormat: { Splat: number; KSplat: number; Ply: number }): number {
  switch (ext) {
    case "ksplat": return SceneFormat.KSplat;
    case "ply": return SceneFormat.Ply;
    case "splat": default: return SceneFormat.Splat;
  }
}

export const SPLAT_EXTENSIONS = ["splat", "ksplat"] as const;   // .ply is routed by content, not here

/** True for a PLY that carries Gaussian-splat attributes (f_dc_0, scale_0, rot_0) rather than plain XYZ. */
export function isSplatPly(headerText: string): boolean {
  return /property\s+float\s+(f_dc_0|scale_0|rot_0|opacity)\b/.test(headerText);
}

export async function loadSplatScene(file: File): Promise<SplatResult> {
  const ext = (file.name.toLowerCase().split(".").pop() || "splat");
  // Dynamic import → its own lazy chunk; keeps the eager app shell within the bundle budget.
  const { DropInViewer, SceneFormat } = await import("@mkkellogg/gaussian-splats-3d");

  const viewer = new DropInViewer({
    // no SharedArrayBuffer → no COOP/COEP header requirement; CPU sort → widest device support
    sharedMemoryForWorkers: false,
    gpuAcceleratedSort: false,
  });

  const url = URL.createObjectURL(file);
  try {
    await viewer.addSplatScene(url, {
      format: formatFor(ext, SceneFormat),
      showLoadingUI: false,
      progressiveLoad: false,
      splatAlphaRemovalThreshold: 5,
    });
  } finally {
    URL.revokeObjectURL(url);          // the buffer is parsed into GPU memory; the blob URL is done
  }

  viewer.name = file.name;
  return {
    object: viewer,
    info: `Gaussian splat (${ext.toUpperCase()})`,
    dispose: () => { try { void viewer.dispose(); } catch { /* already gone */ } },
  };
}

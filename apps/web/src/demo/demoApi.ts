/**
 * Read-only demo data layer for the GitHub Pages (VITE_PAGES) viewer build, which has no backend.
 *
 * `demoData.json` is a snapshot of one seeded "Demo Tower" project (captured by
 * services/api/build_demo_data.py). When VITE_PAGES is set, ApiClient routes its reads here so the
 * GC portal, Budget/GMP, Schedule and Finance panels render with real sample data offline. Writes
 * are rejected with a friendly message — the demo is look-but-don't-touch.
 */
import demoData from "./demoData.json";

const MAP = demoData as Record<string, unknown>;

/** True in the viewer-only Pages/demo build. */
export const IS_DEMO = !!import.meta.env.VITE_PAGES;

const READONLY_MSG =
  "This is the read-only viewer demo — changes aren't saved here. Get the free app to edit live data.";

/** Serve a JSON read from the snapshot. Non-GET methods are rejected (read-only). Uncaptured GETs
 *  (a handful of model-derived endpoints that need a source IFC) degrade to an empty list so panels
 *  show an empty state rather than crash. */
export function demoJson<T>(path: string, init?: RequestInit): T {
  const method = (init?.method ?? "GET").toUpperCase();
  // a few reads are computed server-side via POST; serve their captured result so the demo's
  // Finance > Proforma tab still populates (the figures are static — editing won't re-solve).
  if (method === "POST") {
    const canned = MAP[`POST ${path}`];
    if (canned !== undefined) return canned as T;
    throw new Error(READONLY_MSG);
  }
  if (method !== "GET") throw new Error(READONLY_MSG);
  const hit = MAP[`GET ${path}`];
  if (hit !== undefined) return hit as T;
  if (import.meta.env.DEV) console.warn("[demo] no fixture for", path);
  return [] as unknown as T;
}

/** Serve a captured text read (e.g. an inline schedule SVG). Throws if absent. */
export function demoTextOr(path: string, fallback: string): string {
  const hit = MAP[`GET ${path}`];
  return typeof hit === "string" ? hit : fallback;
}

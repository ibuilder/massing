// R39-VIEWER-OBS — the viewer load journey, measured.
//
// "The viewer loads slowly" has only ever arrived as a feeling. This records it as a number: fetch →
// parse → first frame, bucketed by model size, posted to our own API. No third-party telemetry and
// nothing new for an operator to approve.
//
// **Two requirements that are not in the roadmap entry, and the instrument is not worth building
// without either of them.** Both come from `world.ts`'s CANVAS-RESIZE finding, which is the best
// evidence we have about how this viewer actually fails:
//
//  1. **Arriving is not the same as being seen.** In the bug that comment describes, the .frag fetch
//     returned 200, the worker parsed, the meshes existed and were visible — and the canvas was
//     0x493, so nothing appeared. A fetch/parse/first-frame timer would have reported that load as
//     entirely healthy. It was "recorded as an environment quirk and repeated as a verification
//     limitation for weeks" precisely because no instrument could tell *arrived* from *seen*. So the
//     canvas dimensions at first frame are recorded, and a zero one is a distinct OUTCOME rather
//     than a footnote on a green row.
//
//  2. **An instrument that only reports on success cannot measure the failure it exists for.** If
//     first frame never comes, the naive design emits nothing at all — so the load that hung, the
//     one worth knowing about, is the single load absent from the record, and the dataset is
//     survivorship-biased in exactly the direction that makes it useless. A stall must therefore
//     report itself, on a timer, as a first-class outcome.
//
// Best-effort throughout: a reporting failure must never disturb a load. The transport is injected
// rather than imported so this is testable without a network, matching `errorReporting.ts`.

/** Why a load stopped being interesting — never "no row". */
export type LoadOutcome =
  | "ok"          // first frame drawn into a canvas with real dimensions
  | "invisible"   // first frame drawn into a zero-sized canvas — geometry arrived, nobody saw it
  | "stalled"     // no first frame within the budget; the row exists BECAUSE the load did not finish
  | "failed";     // the loader rejected the bytes (corrupt / not a .frag)

/** The wire shape, defined once in `api/types.ts` — see the note there on why not here. */
export type { ViewerLoadTiming as LoadTimingPayload } from "../api/types";
import type { ViewerLoadTiming as LoadTimingPayload } from "../api/types";

type Send = (p: LoadTimingPayload) => void;

/**
 * Size bands. Boundaries are round numbers a human can hold, not percentiles of today's corpus:
 * a bucket that moves when the corpus changes makes last month's p95 incomparable with this
 * month's, which defeats the point of recording it.
 */
const BUCKETS: ReadonlyArray<readonly [number, string]> = [
  [1_000_000, "<1MB"],
  [10_000_000, "1-10MB"],
  [50_000_000, "10-50MB"],
  [200_000_000, "50-200MB"],
];

export function sizeBucket(bytes: number): string {
  if (!Number.isFinite(bytes) || bytes < 0) return "unknown";
  for (const [limit, label] of BUCKETS) if (bytes < limit) return label;
  return ">200MB";
}

/** How long a load may go without a first frame before it is recorded as stalled. */
export const STALL_BUDGET_MS = 60_000;

export interface TrackerDeps {
  send: Send;
  /** Monotonic clock. Injected so a test can advance it without waiting. */
  now: () => number;
  /** Deferred stall check. Injected for the same reason; returns a cancel handle. */
  setTimer?: (fn: () => void, ms: number) => unknown;
  clearTimer?: (h: unknown) => void;
  stallBudgetMs?: number;
}

/**
 * One tracker per model load.
 *
 * The caller marks phases as they happen and calls `firstFrame(w, h)` once geometry has actually been
 * drawn. Exactly one payload is emitted per tracker, whichever way the load ends — that "exactly one"
 * is what makes the resulting table countable: rows-per-load is 1, so a missing row means a load that
 * never started rather than one that went badly.
 */
export function trackModelLoad(modelId: string, deps: TrackerDeps) {
  const { send, now } = deps;
  const setTimer = deps.setTimer ?? ((fn: () => void, ms: number) => setTimeout(fn, ms));
  const clearTimer = deps.clearTimer ?? ((h: unknown) => clearTimeout(h as ReturnType<typeof setTimeout>));
  const budget = deps.stallBudgetMs ?? STALL_BUDGET_MS;

  const t0 = now();
  // Learned at `fetched()`, not at construction. The tracker has to be armed BEFORE the fetch — a
  // load that dies downloading is one of the failures this exists to catch — and at that moment
  // nobody knows the size yet. Hence the `unknown` bucket, which is load-bearing rather than
  // defensive: it is what a load that never got its bytes is honestly filed under.
  let bytes = Number.NaN;
  let tFetched: number | null = null;
  let tParsed: number | null = null;
  let done = false;

  const emit = (outcome: LoadOutcome, canvasW: number | null, canvasH: number | null) => {
    if (done) return;                 // exactly one row per load, even if a stall races a first frame
    done = true;
    clearTimer(handle);
    const t = now();
    try {
      send({
        modelId, bytes, bucket: sizeBucket(bytes), outcome,
        fetchMs: tFetched === null ? null : Math.round(tFetched - t0),
        parseMs: tParsed === null || tFetched === null ? null : Math.round(tParsed - tFetched),
        // Null on a stall even when parsing finished. Deriving this from `tParsed` alone reported
        // a first-frame duration for a frame that never happened — a fabricated measurement, which
        // is worse than a missing one because it looks like evidence. Caught by the stall test.
        firstFrameMs: outcome === "stalled" || tParsed === null ? null : Math.round(t - tParsed),
        totalMs: Math.round(t - t0),
        canvasW, canvasH,
      });
    } catch { /* a broken reporter must never break a load */ }
  };

  // Armed BEFORE any phase completes, deliberately: a load that dies during the fetch is as much a
  // stall as one that dies waiting for a frame, and arming later would miss the earliest failures.
  const handle = setTimer(() => emit("stalled", null, null), budget);

  return {
    /** Bytes are on the wire; `n` is how many. */
    fetched(n: number) { if (!done && tFetched === null) { tFetched = now(); bytes = n; } },
    /** The worker has produced meshes. */
    parsed() { if (!done && tParsed === null) tParsed = now(); },
    /**
     * Geometry has been drawn. Pass the CANVAS's own dimensions — not the container's, which is what
     * made the resize bug invisible: the container measured 830x572 while the canvas was 0x493.
     */
    firstFrame(canvasW: number, canvasH: number) {
      emit(canvasW > 0 && canvasH > 0 ? "ok" : "invisible", canvasW, canvasH);
    },
    /** The loader rejected the bytes. Distinct from a stall: this one ended, badly and quickly. */
    failed() { emit("failed", null, null); },
    /**
     * Abandoned before finishing — navigated away, or there was no model to load in the first place
     * (a metadata-only project 404s by design). Drop it: reporting these as stalls would fill the
     * table with rows about projects that have no geometry.
     */
    cancel() { done = true; clearTimer(handle); },
  };
}

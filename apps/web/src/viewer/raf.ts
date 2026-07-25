/**
 * R23 — frame-loop primitives.
 *
 * Two mistakes kept recurring in this codebase and both are cheap to make and expensive to find:
 *
 *  1. **Expensive work per event.** Camera controls emit `update` many times per frame; doing a full
 *     pass on each is strictly wasted, because only the last one before the paint can affect what the
 *     user sees. `coalesced()` collapses a burst to one call per animation frame.
 *  2. **An animation loop with no way to stop.** A `requestAnimationFrame` loop that re-arms itself
 *     unconditionally outlives whatever it was drawing for. `frameLoop()` returns its own stop, and
 *     also takes a liveness predicate so it terminates even when nobody remembers to call it.
 *
 * These live here rather than inline so they can be tested without a WebGL context — which is the
 * whole reason the perf work was previously unverifiable.
 */

type Raf = (cb: FrameRequestCallback) => number;
type Caf = (h: number) => void;

/** Injection seam for tests; production passes nothing and gets the real thing. */
export interface FrameApi { raf: Raf; caf: Caf }

const realFrames: FrameApi = {
  raf: (cb) => requestAnimationFrame(cb),
  caf: (h) => cancelAnimationFrame(h),
};

export interface Coalesced {
  /** Request a run. Repeated calls before the next frame collapse into one. */
  trigger(): void;
  /** Drop any pending run (e.g. because something better is about to run instead). */
  cancel(): void;
  /** True while a run is scheduled — exposed for assertions, not for control flow. */
  readonly pending: boolean;
}

/** Run `fn` at most once per animation frame however often `trigger()` is called. */
export function coalesced(fn: () => void, frames: FrameApi = realFrames): Coalesced {
  let handle = 0;
  return {
    trigger() {
      if (handle) return;                     // already scheduled for this frame
      handle = frames.raf(() => { handle = 0; fn(); });
    },
    cancel() {
      if (handle) { frames.caf(handle); handle = 0; }
    },
    get pending() { return handle !== 0; },
  };
}

/**
 * A self-terminating animation loop. Runs `fn` each frame while `alive()` holds; stops permanently
 * once it does not, or once `stop()` is called — whichever comes first.
 */
export function frameLoop(fn: () => void, alive: () => boolean,
                          frames: FrameApi = realFrames): () => void {
  let handle = 0;
  let stopped = false;
  const tick = () => {
    if (stopped || !alive()) { handle = 0; return; }
    fn();
    handle = frames.raf(tick);
  };
  handle = frames.raf(tick);
  return () => {
    stopped = true;
    if (handle) { frames.caf(handle); handle = 0; }
  };
}

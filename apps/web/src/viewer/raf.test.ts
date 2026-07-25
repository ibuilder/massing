import { describe, expect, it } from "vitest";
import { coalesced, frameLoop, type FrameApi } from "./raf";

/**
 * R23-PERF-TEST — the perf work was previously unverifiable: the repo has a bundle-size budget and
 * had *zero* runtime assertions. Asserting `renderer.info.render.calls` needs a real WebGL context,
 * which is not available in this environment — so what is tested here is the part that actually
 * changed and that is testable without one: the frame-scheduling logic itself.
 *
 * A controllable frame clock is what makes these assertions real rather than timing-dependent.
 */
function clock() {
  let next = 1;
  const q = new Map<number, FrameRequestCallback>();
  const api: FrameApi = {
    raf: (cb) => { const h = next++; q.set(h, cb); return h; },
    caf: (h) => { q.delete(h); },
  };
  return {
    api,
    /** Run exactly one frame's worth of callbacks (those queued before the frame began). */
    frame() {
      const due = [...q.entries()];
      for (const [h] of due) q.delete(h);
      for (const [, cb] of due) cb(performance.now());
    },
    get queued() { return q.size; },
  };
}

describe("coalesced — one pass per frame, not one per event", () => {
  it("collapses a burst of triggers into a single call", () => {
    const c = clock();
    let calls = 0;
    const p = coalesced(() => { calls++; }, c.api);
    for (let i = 0; i < 50; i++) p.trigger();     // a camera drag emits many per frame
    expect(calls).toBe(0);                        // nothing runs synchronously
    c.frame();
    expect(calls).toBe(1);                        // ...and 50 events cost exactly one pass
  });

  it("re-arms on the next frame, so continuous motion still updates every frame", () => {
    const c = clock();
    let calls = 0;
    const p = coalesced(() => { calls++; }, c.api);
    p.trigger(); c.frame();
    p.trigger(); c.frame();
    p.trigger(); c.frame();
    expect(calls).toBe(3);
  });

  it("cancel() drops the pending pass — the full-quality pass supersedes the cheap one", () => {
    const c = clock();
    let calls = 0;
    const p = coalesced(() => { calls++; }, c.api);
    p.trigger();
    expect(p.pending).toBe(true);
    p.cancel();
    expect(p.pending).toBe(false);
    c.frame();
    expect(calls).toBe(0);
    expect(c.queued).toBe(0);                     // and it left nothing scheduled behind it
  });

  it("cancel() on an idle scheduler is harmless", () => {
    const c = clock();
    const p = coalesced(() => {}, c.api);
    expect(() => { p.cancel(); p.cancel(); }).not.toThrow();
  });
});

describe("frameLoop — a loop that can always be stopped", () => {
  it("runs each frame while alive", () => {
    const c = clock();
    let ticks = 0;
    frameLoop(() => { ticks++; }, () => true, c.api);
    c.frame(); c.frame(); c.frame();
    expect(ticks).toBe(3);
  });

  it("stop() ends it and leaves nothing queued", () => {
    const c = clock();
    let ticks = 0;
    const stop = frameLoop(() => { ticks++; }, () => true, c.api);
    c.frame();
    stop();
    expect(c.queued).toBe(0);
    c.frame(); c.frame();
    expect(ticks).toBe(1);                        // no further work after stop
  });

  it("terminates itself when the thing it draws for is gone — the leak that was real", () => {
    // The bug this replaces had NO cancellation path: the loop outlived viewer teardown and kept
    // projecting pins for a world nobody was looking at. `dispose()` alone would not have caught it,
    // because the leaking path was the one where dispose() is never called.
    const c = clock();
    let ticks = 0;
    let attached = true;
    frameLoop(() => { ticks++; }, () => attached, c.api);
    c.frame(); c.frame();
    expect(ticks).toBe(2);
    attached = false;                             // container dropped; nobody calls dispose()
    c.frame();
    expect(ticks).toBe(2);                        // the tick did not run...
    expect(c.queued).toBe(0);                     // ...and the loop did not re-arm itself
    c.frame(); c.frame();
    expect(ticks).toBe(2);                        // permanently stopped, not merely paused
  });

  it("stop() is safe to call repeatedly and after self-termination", () => {
    const c = clock();
    const stop = frameLoop(() => {}, () => false, c.api);
    c.frame();
    expect(() => { stop(); stop(); }).not.toThrow();
  });
});

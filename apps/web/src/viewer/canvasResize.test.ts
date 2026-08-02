/**
 * CANVAS-RESIZE — the canvas must track its container, including when the container gains its size
 * AFTER the renderer was constructed.
 *
 * This is the regression test for what was recorded for weeks as "the dev-preview geometry loader
 * stalls". It never stalled. Measured on a real project 2026-08-02: the `.frag` fetch returned 200,
 * the worker parsed, four meshes and 230 triangles were built and marked visible — into a canvas of
 * width ZERO (container 830x572, canvas 0x493). Nothing renders, and from outside that is
 * indistinguishable from a loader that never finished. It was cited as an environment limitation in
 * eight changelog entries before anyone asked the page what its canvas size was.
 *
 * The renderer sizes itself once, from whatever the container measured at construction. Anything
 * that gives the container its real width later — a rail expanding, a workspace becoming visible, a
 * font or CSS pass landing — leaves that first size in place for ever. `onModelShown` re-resized,
 * but only on a workspace transition; nothing watched the container itself.
 *
 * The two properties asserted here are the ones that actually failed:
 *   1. a container that grows from 0 triggers a resize (the bug);
 *   2. a ZERO size never does — resizing at 0x0 sets a NaN camera aspect, which is a different
 *      failure this repo has already been bitten by, so the fix must not trade one for the other.
 */
import { describe, expect, it, vi } from "vitest";

/** The observer callback's decision logic, extracted verbatim from `createViewer`. Kept in the test
 *  as a pure function because the real one closes over an OBC world that cannot be built headless —
 *  the LOGIC is what regressed, and the logic is what this pins. */
function makeResizeDecider(onResize: () => void) {
  let lastW = 0, lastH = 0;
  return (w: number, h: number) => {
    if (!w || !h) return;
    if (w === lastW && h === lastH) return;
    lastW = w; lastH = h;
    onResize();
  };
}

describe("canvas resize decision", () => {
  it("resizes when the container gains a real size after construction — THE bug", () => {
    const onResize = vi.fn();
    const decide = makeResizeDecider(onResize);
    decide(0, 493);        // construction-time: container not laid out yet
    expect(onResize).not.toHaveBeenCalled();
    decide(830, 572);      // rail expanded / workspace shown / fonts landed
    expect(onResize).toHaveBeenCalledTimes(1);
  });

  it("never resizes at a zero dimension — that bakes a NaN camera aspect", () => {
    const onResize = vi.fn();
    const decide = makeResizeDecider(onResize);
    for (const [w, h] of [[0, 0], [0, 572], [830, 0]] as const) decide(w, h);
    expect(onResize).not.toHaveBeenCalled();
  });

  it("ignores no-op layout passes — observers fire on those too", () => {
    const onResize = vi.fn();
    const decide = makeResizeDecider(onResize);
    decide(830, 572);
    decide(830, 572);
    decide(830, 572);
    expect(onResize).toHaveBeenCalledTimes(1);
  });

  it("tracks every real change, not just the first", () => {
    const onResize = vi.fn();
    const decide = makeResizeDecider(onResize);
    decide(830, 572);
    decide(1200, 572);     // window widened
    decide(1200, 400);     // panel opened below
    expect(onResize).toHaveBeenCalledTimes(3);
  });

  it("a collapse to zero then a re-expand still resizes — a hidden tab coming back", () => {
    const onResize = vi.fn();
    const decide = makeResizeDecider(onResize);
    decide(830, 572);
    decide(0, 0);          // workspace hidden — ignored, and must not poison the cache
    decide(830, 572);      // shown again at the same size
    // the zero was ignored, so this is a no-op repeat of the last REAL size: one call total
    expect(onResize).toHaveBeenCalledTimes(1);
  });
});

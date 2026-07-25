import { describe, expect, it } from "vitest";
import {
  DEFAULT_OPTS, RATIO_STEPS, attachPixelGovernor, initialState, shadowFrustum, snapRatio,
  step, texelSize,
} from "./pixelGovernor";

/** Feed n identical frame samples through the governor. */
function run(frameMs: number, n: number, max = 2, s = initialState(max)) {
  for (let i = 0; i < n; i++) s = step(s, frameMs, max);
  return s;
}

describe("snapRatio", () => {
  it("snaps to an allowed step and never exceeds the device maximum", () => {
    expect(snapRatio(1.9, 2)).toBe(2);
    expect(snapRatio(1.1, 2)).toBe(1);
    expect(RATIO_STEPS).toContain(snapRatio(1.3, 2));
    // a 1× display must never be handed 1.5 or 2 — that would render MORE pixels than it can show
    expect(snapRatio(2, 1)).toBe(1);
    expect(snapRatio(1.7, 1)).toBe(1);
  });
});

describe("degrade — shed resolution when frames are slow", () => {
  it("steps down under sustained slow frames", () => {
    const s = run(40, 200);                       // 40 ms/frame ≈ 25 fps
    expect(s.ratio).toBeLessThan(2);
  });

  it("bottoms out at the lowest allowed step and stays there", () => {
    const s = run(80, 4000);
    expect(s.ratio).toBe(RATIO_STEPS[0]);
    const t = step(s, 80, 2);
    expect(t.ratio).toBe(RATIO_STEPS[0]);         // no step below the floor
  });

  it("starts at full resolution — the governor only intervenes once it has evidence", () => {
    expect(initialState(2).ratio).toBe(2);
    expect(initialState(1).ratio).toBe(1);
  });
});

describe("recover — but slowly, and only once it holds", () => {
  it("does not step back up on a single good frame", () => {
    const slow = run(40, 200);
    const one = step(slow, 5, 2);
    expect(one.ratio).toBe(slow.ratio);           // one fast frame proves nothing
  });

  it("steps back up after a sustained good run", () => {
    const slow = run(40, 200);
    const fast = run(5, 600, 2, slow);
    expect(fast.ratio).toBeGreaterThan(slow.ratio);
  });

  it("never exceeds the device maximum however long it stays fast", () => {
    expect(run(3, 5000, 2).ratio).toBe(2);
    expect(run(3, 5000, 1).ratio).toBe(1);
  });
});

describe("hysteresis — the property that makes it usable", () => {
  it("holds steady inside the dead band instead of pulsing", () => {
    // a frame time between recoverMs and degradeMs is neither good nor bad; the ratio must not move
    const mid = (DEFAULT_OPTS.recoverMs + DEFAULT_OPTS.degradeMs) / 2;
    const s = run(mid, 2000);
    expect(s.ratio).toBe(2);
    expect(s.streak).toBe(0);                     // and it accrues no progress toward a change
  });

  it("never reverses direction — pulsing is what a user sees, not movement", () => {
    // Alternate either side of the degrade threshold: the classic trap. What must NOT happen is the
    // ratio going down, then up, then down — that is the visible pulse. Walking steadily DOWN under
    // sustained pressure is correct: the machine is struggling and shedding resolution is the answer.
    let s = initialState(2);
    const path: number[] = [s.ratio];
    for (let i = 0; i < 3000; i++) {
      s = step(s, i % 2 ? DEFAULT_OPTS.degradeMs + 3 : DEFAULT_OPTS.degradeMs - 3, 2);
      if (s.ratio !== path[path.length - 1]) path.push(s.ratio);
    }
    const ups = path.filter((r, i) => i > 0 && r > path[i - 1]!).length;
    expect(ups).toBe(0);                          // monotonically non-increasing: no pulse
    expect(path.at(-1)!).toBeLessThan(2);         // and it did respond to the pressure
  });

  it("ignores a single huge hitch — a GC pause is not a rendering problem", () => {
    const good = run(8, 300);
    const after = step(good, 400, 2);             // one 400 ms stall
    expect(after.ratio).toBe(good.ratio);
    expect(after.ema).toBeCloseTo(good.ema, 5);   // the outlier does not even enter the average
  });
});

describe("attachPixelGovernor", () => {
  it("only calls setPixelRatio when the ratio actually changes, and stops cleanly", () => {
    const q: FrameRequestCallback[] = [];
    const frames = {
      raf: (cb: FrameRequestCallback) => { q.push(cb); return q.length; },
      caf: () => { q.length = 0; },
    };
    const calls: number[] = [];
    let t = 0;
    const now = () => (t += 50);                  // 50 ms frames — sustained slow
    const stop = attachPixelGovernor(
      { setPixelRatio: (r) => calls.push(r) }, frames, now, 2,
    );
    for (let i = 0; i < 400 && q.length; i++) { const cb = q.shift()!; cb(0); }
    expect(calls.length).toBeGreaterThan(0);
    // never the same ratio twice in a row — setPixelRatio reallocates the drawing buffer
    for (let i = 1; i < calls.length; i++) expect(calls[i]).not.toBe(calls[i - 1]);
    expect(calls.every((r) => (RATIO_STEPS as readonly number[]).includes(r))).toBe(true);
    const before = calls.length;
    stop();
    q.forEach((cb) => cb(0));
    expect(calls.length).toBe(before);            // nothing runs after stop
  });
});

describe("shadowFrustum — spend the shadow map on the model, not on empty space", () => {
  it("scales with the model instead of a fixed ±140 m box", () => {
    const house = shadowFrustum(30, 160);      // ~30 m diagonal
    const tower = shadowFrustum(220, 160);
    expect(house.right).toBeLessThan(tower.right);
    expect(tower.right).toBeGreaterThan(110);  // a 220 m diagonal must still fit inside
  });

  it("gives a small building a far finer shadow than the old fixed frustum did", () => {
    // the old box was ±140 m → 280 m / 2048 ≈ 13.7 cm per texel for EVERY model
    expect(texelSize(30)).toBeLessThan(0.137);
    expect(texelSize(30)).toBeLessThan(texelSize(220));
  });

  it("holds the bounding SPHERE, not a per-axis extent a low sun would shear out of", () => {
    // a long flat site: the diagonal, not the height, is what has to fit
    const f = shadowFrustum(200, 160);
    expect(f.right).toBeGreaterThanOrEqual(100);
  });

  it("never collapses to zero on a degenerate or empty model", () => {
    for (const d of [0, 0.001, -5, Number.NaN]) {
      const f = shadowFrustum(Number.isNaN(d) ? 0 : d, 0);
      expect(f.right).toBeGreaterThan(0);
      expect(f.far).toBeGreaterThan(f.near);
    }
  });

  it("far plane clears both the model and the sun's distance", () => {
    const f = shadowFrustum(100, 500);
    expect(f.far).toBeGreaterThan(500);
    expect(f.near).toBeGreaterThan(0);
  });
});

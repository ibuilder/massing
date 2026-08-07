import { describe, expect, it, vi } from "vitest";
import {
  sizeBucket, trackModelLoad, STALL_BUDGET_MS,
  type LoadTimingPayload,
} from "./loadTimings";

/**
 * R39-VIEWER-OBS — the two tests that matter here are `invisible` and `stalled`.
 *
 * The happy path is nearly self-evident and would pass against a dozen wrong implementations. The
 * value of this instrument rests entirely on the two cases a naive load timer gets wrong:
 *
 *  - a load that ARRIVED but was never SEEN (the CANVAS-RESIZE bug: fetch 200, meshes built, canvas
 *    0-width) must not be recorded as a healthy load;
 *  - a load that never finished must produce a row AT ALL, or the dataset is survivorship-biased
 *    against precisely the loads it exists to catch.
 *
 * Both are asserted below against a controlled clock and a controlled timer, so neither test waits
 * on real time.
 */

/**
 * A test harness with a hand-cranked clock and a single pending timer.
 *
 * The default budget is deliberately far larger than any journey below, so a test that is not about
 * stalling never trips the stall timer by accident. The stall tests set it explicitly. (This started
 * at 1,000ms and the happy path — a 1,050ms journey — began reporting `stalled`, correctly.)
 */
function harness(budget = 100_000) {
  const sent: LoadTimingPayload[] = [];
  let t = 0;
  let pending: { fn: () => void; at: number } | null = null;
  const deps = {
    send: (p: LoadTimingPayload) => { sent.push(p); },
    now: () => t,
    setTimer: (fn: () => void, ms: number) => { pending = { fn, at: t + ms }; return 1; },
    clearTimer: () => { pending = null; },
    stallBudgetMs: budget,
  };
  return {
    sent, deps,
    advance(ms: number) {
      t += ms;
      if (pending && t >= pending.at) { const f = pending.fn; pending = null; f(); }
    },
    get armed() { return pending !== null; },
  };
}

describe("size buckets", () => {
  it("bands by round numbers, and the boundary lands in the upper band", () => {
    expect(sizeBucket(0)).toBe("<1MB");
    expect(sizeBucket(999_999)).toBe("<1MB");
    expect(sizeBucket(1_000_000)).toBe("1-10MB");     // boundary is exclusive-below, not inclusive
    expect(sizeBucket(49_999_999)).toBe("10-50MB");
    expect(sizeBucket(200_000_000)).toBe(">200MB");
  });

  it("refuses to invent a band for a nonsense size", () => {
    // A negative or NaN byte count means the caller does not know the size. Bucketing it as "<1MB"
    // would put an unmeasured load into the fastest band and quietly improve every percentile.
    expect(sizeBucket(-1)).toBe("unknown");
    expect(sizeBucket(Number.NaN)).toBe("unknown");
  });
});

describe("the happy path", () => {
  it("records each phase as a duration, not a timestamp", () => {
    const h = harness();
    const tr = trackModelLoad("M1", h.deps);
    h.advance(300); tr.fetched(5_000_000);
    h.advance(700); tr.parsed();
    h.advance(50); tr.firstFrame(800, 600);

    expect(h.sent).toHaveLength(1);
    expect(h.sent[0]).toMatchObject({
      modelId: "M1", bucket: "1-10MB", outcome: "ok",
      fetchMs: 300, parseMs: 700, firstFrameMs: 50, totalMs: 1050,
      canvasW: 800, canvasH: 600,
    });
  });

  it("disarms the stall timer once the frame lands", () => {
    const h = harness();
    const tr = trackModelLoad("M1", h.deps);
    expect(h.armed, "the stall timer must be armed before any phase completes").toBe(true);
    tr.fetched(1_000); tr.parsed(); tr.firstFrame(800, 600);
    expect(h.armed).toBe(false);
    h.advance(10_000);
    expect(h.sent, "a disarmed timer must not add a second row later").toHaveLength(1);
  });
});

describe("arrived is not the same as seen", () => {
  it("a frame drawn into a zero-width canvas is `invisible`, not `ok`", () => {
    // This is the CANVAS-RESIZE bug, reproduced: container 830x572, canvas 0x493. Everything
    // upstream succeeded. A timer that only asked "did a frame happen?" reported it as healthy for
    // weeks, which is why the canvas dimensions are part of the row.
    const h = harness();
    const tr = trackModelLoad("M1", h.deps);
    h.advance(100); tr.fetched(2_000_000);
    h.advance(100); tr.parsed();
    h.advance(10); tr.firstFrame(0, 493);

    expect(h.sent).toHaveLength(1);
    expect(h.sent[0]!.outcome, "geometry arrived and nobody saw it — that is not a healthy load")
      .toBe("invisible");
    expect(h.sent[0]!.canvasW).toBe(0);
  });

  it("the same journey with a real canvas is `ok` — so the assertion above is not vacuous", () => {
    // The positive control. Without it, `outcome === "invisible"` could be true for every load and
    // the test above would still pass.
    const h = harness();
    const tr = trackModelLoad("M1", h.deps);
    tr.fetched(2_000_000); tr.parsed(); tr.firstFrame(830, 493);
    expect(h.sent[0]!.outcome).toBe("ok");
  });
});

describe("a load that never finishes still reports", () => {
  it("emits a `stalled` row when no frame arrives within the budget", () => {
    const h = harness(1_000);
    const tr = trackModelLoad("M1", h.deps);
    tr.fetched(100_000_000); tr.parsed();
    expect(h.sent, "nothing should be reported before the budget expires").toHaveLength(0);

    h.advance(1_000);
    expect(h.sent, "the load that hung is the one worth knowing about — it must not be absent")
      .toHaveLength(1);
    expect(h.sent[0]).toMatchObject({
      outcome: "stalled", bucket: "50-200MB", firstFrameMs: null, canvasW: null,
    });
  });

  it("stalls even if the fetch itself never completes", () => {
    // Armed before any phase, deliberately: a load that dies mid-fetch is still a stall, and arming
    // the timer at `parsed()` would have missed the earliest failures entirely.
    const h = harness(1_000);
    trackModelLoad("M1", h.deps);
    h.advance(1_000);
    expect(h.sent).toHaveLength(1);
    expect(h.sent[0]).toMatchObject({
      outcome: "stalled", fetchMs: null, parseMs: null,
      // The load died before anyone knew the size. Filing it under "<1MB" would drop an unmeasured
      // load into the fastest band and quietly improve that band's percentiles — so `unknown` is
      // the honest answer, and this is the case that makes that branch reachable.
      bucket: "unknown",
    });
  });

  it("a frame arriving after the stall does not add a second row", () => {
    const h = harness(1_000);
    const tr = trackModelLoad("M1", h.deps);
    h.advance(1_000);
    tr.firstFrame(800, 600);
    expect(h.sent, "exactly one row per load is what makes the table countable").toHaveLength(1);
    expect(h.sent[0]!.outcome).toBe("stalled");
  });

  it("a rejected .frag is `failed`, not `stalled` — it ended, badly and quickly", () => {
    // app.ts distinguishes these: corrupt bytes make loadFragments throw, but the same comment notes
    // the worker can *hang* on unparseable input instead. Those are different failures and conflating
    // them would hide which one is happening.
    const h = harness(1_000);
    const tr = trackModelLoad("M1", h.deps);
    tr.fetched(9_000); 
    tr.failed();
    expect(h.sent[0]!.outcome).toBe("failed");
    h.advance(10_000);
    expect(h.sent, "a failure must disarm the stall timer").toHaveLength(1);
  });

  it("cancelling reports nothing at all", () => {
    // An abandoned load is not a stall. Recording one would put navigation noise into the tail of
    // every percentile.
    const h = harness(1_000);
    const tr = trackModelLoad("M1", h.deps);
    tr.cancel();
    h.advance(10_000);
    expect(h.sent).toHaveLength(0);
  });
});

describe("best-effort", () => {
  it("a reporter that throws does not break the load", () => {
    const send = vi.fn(() => { throw new Error("network down"); });
    const tr = trackModelLoad("M1", { send, now: () => 0, stallBudgetMs: 1_000 });
    expect(() => tr.firstFrame(800, 600)).not.toThrow();
    expect(send).toHaveBeenCalledOnce();
  });

  it("ships a real default budget, not the test one", () => {
    // The harness passes its own budget everywhere above, so nothing else here would notice if the
    // shipped default were 0 (report every load as stalled) or Infinity (never report one).
    expect(STALL_BUDGET_MS).toBeGreaterThan(10_000);
    expect(STALL_BUDGET_MS).toBeLessThanOrEqual(120_000);
  });
});

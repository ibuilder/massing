import { describe, expect, it } from "vitest";

import {
  CLICK_ECHO, PANEL_LOAD, beginPanelLoad, installClickEcho, installPanelLoad,
  type ClickEchoDeps,
} from "./perfBeacon";

/**
 * The tracker is driven with an injected clock and an injected frame scheduler, so every timing
 * below is exact rather than raced. The production wiring uses `performance.now` and
 * `requestAnimationFrame`; what is asserted here is the SHAPE — how many frames are waited, what is
 * dropped, and what is reported.
 */
function harness(over: Partial<ClickEchoDeps> = {}) {
  const sent: Array<[string, number]> = [];
  let t = 1_000;
  const frames: Array<() => void> = [];
  const deps: ClickEchoDeps = {
    send: (b, ms) => sent.push([b, ms]),
    now: () => t,
    raf: (fn) => frames.push(fn),
    isUserEvent: () => true,        // happy-dom cannot forge isTrusted; the default is asserted below
    ...over,
  };
  return {
    deps, sent,
    advance: (ms: number) => { t += ms; },
    /** Run exactly one pending frame, as the browser would. */
    frame: () => { const f = frames.shift(); f?.(); },
    /**
     * Run frames until none are pending.
     *
     * Needed once a click and a panel are in flight together: a click schedules two frames of its
     * own, so counting `frame()` calls by hand silently spends the panel's budget on the click's and
     * the panel reports nothing. The first draft of the click-seeding test failed exactly that way,
     * and the failure looked like "the feature does not work" rather than "the test miscounted".
     */
    drain: () => { for (let i = 0; i < 20 && frames.length; i++) { const f = frames.shift(); f?.(); } },
    pending: () => frames.length,
  };
}

describe("installClickEcho — click to the paint that answers it", () => {
  it("reports the interval across TWO frames, not one", () => {
    const h = harness();
    const target = new EventTarget();
    installClickEcho(target, h.deps);

    target.dispatchEvent(new Event("click"));
    h.advance(30);
    h.frame();                                    // first frame: runs BEFORE the paint
    expect(h.sent, "reporting here would time the schedule, not the paint").toEqual([]);
    h.advance(20);
    h.frame();                                    // second frame: after the paint
    expect(h.sent).toEqual([[CLICK_ECHO, 50]]);
  });

  it("reports fast clicks too — a percentile over only the suspicious ones is not a percentile", () => {
    const h = harness();
    const target = new EventTarget();
    installClickEcho(target, h.deps);
    target.dispatchEvent(new Event("click"));
    h.advance(2); h.frame(); h.frame();
    expect(h.sent).toEqual([[CLICK_ECHO, 2]]);
  });

  it("measures each click independently when several are in flight", () => {
    const h = harness();
    const target = new EventTarget();
    installClickEcho(target, h.deps);

    target.dispatchEvent(new Event("click"));     // click A at t=1000
    h.advance(10);
    target.dispatchEvent(new Event("click"));     // click B at t=1010
    h.advance(10);
    h.frame(); h.frame(); h.frame(); h.frame();   // both pairs of frames
    expect(h.sent.map(([, ms]) => ms)).toEqual([20, 10]);
  });

  // The default predicate is the real guard: a synthetic click answers instantly because nothing was
  // waiting on a human, so counting them pulls the percentile down with intervals nobody experienced.
  it("BY DEFAULT ignores untrusted events — dispatched clicks are not user clicks", () => {
    const h = harness({ isUserEvent: undefined });
    const target = new EventTarget();
    installClickEcho(target, h.deps);
    target.dispatchEvent(new Event("click"));     // isTrusted is false for a dispatched event
    h.frame(); h.frame();
    expect(h.sent).toEqual([]);
    expect(h.pending(), "and no frame work was scheduled for it either").toBe(0);
  });

  it("drops an interval the clock cannot justify — a tab suspend is not a slow click", () => {
    const h = harness();
    const target = new EventTarget();
    installClickEcho(target, h.deps);
    target.dispatchEvent(new Event("click"));
    h.advance(-500);                              // clock moved backwards under us
    h.frame(); h.frame();
    expect(h.sent).toEqual([]);
  });

  it("caps reports per minute, so a click loop cannot bury a slow p95 under fast ones", () => {
    const h = harness({ maxPerMinute: 3 });
    const target = new EventTarget();
    installClickEcho(target, h.deps);
    for (let i = 0; i < 10; i++) {
      target.dispatchEvent(new Event("click"));
      h.advance(1); h.frame(); h.frame();
    }
    expect(h.sent.length).toBe(3);
  });

  it("the cap is a ROLLING window — it throttles, it does not switch off for ever", () => {
    const h = harness({ maxPerMinute: 2 });
    const target = new EventTarget();
    installClickEcho(target, h.deps);
    for (let i = 0; i < 5; i++) {
      target.dispatchEvent(new Event("click")); h.advance(1); h.frame(); h.frame();
    }
    expect(h.sent.length).toBe(2);
    h.advance(61_000);                            // a minute later
    target.dispatchEvent(new Event("click")); h.advance(1); h.frame(); h.frame();
    expect(h.sent.length, "reporting resumes once the window has passed").toBe(3);
  });

  it("a throwing reporter does not break the click", () => {
    const h = harness({ send: () => { throw new Error("sink down"); } });
    const target = new EventTarget();
    installClickEcho(target, h.deps);
    target.dispatchEvent(new Event("click"));
    h.advance(5);
    expect(() => { h.frame(); h.frame(); }).not.toThrow();
  });

  it("the disposer detaches — no reports after teardown", () => {
    const h = harness();
    const target = new EventTarget();
    const off = installClickEcho(target, h.deps);
    off();
    target.dispatchEvent(new Event("click"));
    h.frame(); h.frame();
    expect(h.sent).toEqual([]);
  });
});

/**
 * `panel_load` — the budget that stayed unmeasured for fourteen releases because it had no honest
 * moment, not because it had no beacon.
 *
 * The load-bearing assertion is the FIRST one: the interval is measured from the CLICK, not from the
 * call that starts the timer. Two dialogs in this app are handed their data by a caller that fetched
 * it first, so a timer starting at the modal shell would miss the user's entire wait and report DOM
 * construction in its place — a green budget measuring the wrong thing, which `perf_budget.py` calls
 * worse than an openly unmeasured one.
 */
describe("panel_load — click to the panel being usable", () => {
  it("MEASURES FROM THE CLICK, not from when the timer was started", () => {
    const h = harness();
    const target = new EventTarget();
    installClickEcho(target, h.deps);
    const off = installPanelLoad(h.deps);

    target.dispatchEvent(new Event("click"));      // t=1000
    h.advance(400);                                // the caller fetches for 400ms...
    const ready = beginPanelLoad();                // ...and only THEN opens the shell
    h.advance(100);
    ready();
    h.drain();

    const panel = h.sent.filter(([b]) => b === PANEL_LOAD);
    expect(panel, "starting the clock at the shell would report 100, losing the fetch")
      .toEqual([[PANEL_LOAD, 500]]);
    off();
  });

  it("a click seeds AT MOST ONE panel — a stale click cannot invent a slow load", () => {
    const h = harness();
    const target = new EventTarget();
    installClickEcho(target, h.deps);
    const off = installPanelLoad(h.deps);

    target.dispatchEvent(new Event("click"));
    h.advance(50);
    const first = beginPanelLoad();
    h.advance(30_000);                             // ...much later, something opens a panel itself
    const second = beginPanelLoad();
    h.advance(10);
    first(); second();
    h.drain();

    const panel = h.sent.filter(([b]) => b === PANEL_LOAD).map(([, ms]) => ms);
    expect(panel, "the second must fall back to now(), not re-use a 30s-old click")
      .toEqual([30_060, 10]);
    off();
  });

  it("falls back to the current time when no click preceded it", () => {
    const h = harness();
    const off = installPanelLoad(h.deps);
    const ready = beginPanelLoad();
    h.advance(75);
    ready();
    h.frame(); h.frame();
    expect(h.sent).toEqual([[PANEL_LOAD, 75]]);
    off();
  });

  it("is idempotent — a panel that re-renders reports only the load the user waited through", () => {
    const h = harness();
    const off = installPanelLoad(h.deps);
    const ready = beginPanelLoad();
    h.advance(40);
    ready(); ready(); ready();
    h.drain();
    expect(h.sent).toEqual([[PANEL_LOAD, 40]]);
    off();
  });

  it("waits TWO frames, so the number is the paint and not the schedule", () => {
    const h = harness();
    const off = installPanelLoad(h.deps);
    const ready = beginPanelLoad();
    h.advance(20);
    ready();
    h.frame();
    expect(h.sent, "one frame runs before the paint").toEqual([]);
    h.advance(5);
    h.frame();
    expect(h.sent).toEqual([[PANEL_LOAD, 25]]);
    off();
  });

  /**
   * The twin for the assertion above it. Without this, an implementation that reported nothing at
   * all — the easiest possible bug in a beacon — would satisfy every "it does not report X" check in
   * this file, and the budget would read `no_observations` for ever while looking wired.
   */
  it("REPORTS NOTHING when timing is not installed, rather than a wrong number", () => {
    const h = harness();
    const ready = beginPanelLoad();                // no installPanelLoad
    h.advance(100);
    ready();
    h.frame(); h.frame();
    expect(h.sent).toEqual([]);
    expect(h.pending(), "it must not even schedule frames it cannot report from").toBe(0);
  });

  it("drops an interval the clock cannot justify", () => {
    const h = harness();
    const off = installPanelLoad(h.deps);
    const ready = beginPanelLoad();
    h.advance(-500);                               // the clock moved backwards under us
    ready();
    h.frame(); h.frame();
    expect(h.sent).toEqual([]);
    off();
  });

  it("shares the rolling cap with click echo rather than keeping its own", () => {
    const h = harness();
    const off = installPanelLoad({ ...h.deps, maxPerMinute: 2 });
    for (let i = 0; i < 4; i++) {
      const ready = beginPanelLoad();
      h.advance(10);
      ready();
      h.frame(); h.frame();
    }
    expect(h.sent.length, "a modal-opening loop must not bury a slow p95").toBe(2);
    off();
  });

  it("the disposer stops it — no reports after teardown", () => {
    const h = harness();
    const off = installPanelLoad(h.deps);
    off();
    const ready = beginPanelLoad();
    h.advance(60);
    ready();
    h.frame(); h.frame();
    expect(h.sent).toEqual([]);
  });
});

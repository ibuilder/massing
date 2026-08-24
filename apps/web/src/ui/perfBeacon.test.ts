import { describe, expect, it } from "vitest";

import { CLICK_ECHO, installClickEcho, type ClickEchoDeps } from "./perfBeacon";

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

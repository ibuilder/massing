/**
 * R24-PERF-BUDGET — the client half of the budgets, measured in the only place that can see them.
 *
 * Two of the three stated budgets describe things no server can observe. `perf_budget.py` kept them
 * declared and `unmeasured` rather than asserting a server number in their place, on the grounds
 * that *"a budget file that lists three budgets and quietly checks one is how a green suite comes to
 * imply more than it tested"*. This module measures the one of the two that has an honest moment to
 * measure: **click echo — the interval between a user's click and the first paint that answers it.**
 *
 * `panel_load` is deliberately NOT here. The beacon it was waiting for now exists, but this app has
 * no single point at which a panel becomes usable: `ui/modal.ts` builds an empty shell and each
 * caller fills it afterwards, so timing that chokepoint would record a few hundred microseconds of
 * shell construction and file it as a panel load. A budget reported green against a measurement of
 * the wrong thing is worse than one openly unmeasured, so it stays unmeasured with that reason
 * written down.
 *
 * ## Why a capture-phase listener on the document
 *
 * One listener sees every click in the app. The alternative — instrumenting call sites — measures
 * whichever handlers someone remembered to wire, and a p95 over a remembered subset is a number
 * whose population nobody can state. Capture phase matters too: `t0` has to be taken *before* any
 * handler runs, or the interval excludes the work being measured.
 *
 * ## Why two frames
 *
 * A `requestAnimationFrame` callback runs BEFORE the browser paints. Measuring there would report
 * the time to *schedule* the answer rather than to show it — consistently short, consistently wrong,
 * and wrong in the flattering direction. The callback scheduled from inside that frame runs after
 * the paint has happened, so the second one is the first moment the user could have seen anything.
 *
 * ## Only trusted events
 *
 * `dispatchEvent` clicks from our own code are not user clicks, and they answer instantly because
 * nothing was waiting on a human. Counting them would pull the percentile down with intervals no
 * user ever experienced. The predicate is injectable purely so the tests can drive it — the default
 * measures real input only.
 */

/** What the click-echo tracker needs. Everything time-shaped is injected so a test can drive it. */
export interface ClickEchoDeps {
  /** Report one interval, in milliseconds. Must not throw; must not block. */
  send: (budget: string, ms: number) => void;
  /** Monotonic clock. `performance.now()` in production. */
  now: () => number;
  /** Schedule a callback for the next frame. `requestAnimationFrame` in production. */
  raf: (fn: () => void) => void;
  /** Is this a real user event? Defaults to `isTrusted`. */
  isUserEvent?: (e: Event) => boolean;
  /**
   * Ceiling on reports per rolling minute. A human clicks a few times a second at most, so this
   * never binds on real input; it exists so a stuck UI dispatching clicks in a loop cannot flood
   * the sink, and — more importantly — cannot bury a genuinely slow p95 under thousands of fast
   * synthetic ones.
   */
  maxPerMinute?: number;
}

export const CLICK_ECHO = "click_echo";
const DEFAULT_MAX_PER_MINUTE = 120;

/**
 * Attach the click-echo tracker. Returns a disposer.
 *
 * The interval is reported for every trusted click, including the ones that turn out to be fast:
 * a percentile computed only over clicks somebody suspected were slow is not a percentile.
 */
export function installClickEcho(target: EventTarget, deps: ClickEchoDeps): () => void {
  const isUser = deps.isUserEvent ?? ((e: Event) => e.isTrusted);
  const cap = deps.maxPerMinute ?? DEFAULT_MAX_PER_MINUTE;
  let sent: number[] = [];

  const onClick = (e: Event) => {
    if (!isUser(e)) return;
    const t0 = deps.now();
    // Two frames: the first callback runs before the paint, the second after it. See the header.
    deps.raf(() => deps.raf(() => {
      const t = deps.now();
      sent = sent.filter((x) => t - x < 60_000);
      if (sent.length >= cap) return;
      sent.push(t);
      const ms = t - t0;
      // A negative or absurd interval means the clock moved under us (tab suspend, clock change).
      // Dropping it is the same call the sink makes: a fabricated measurement looks like evidence,
      // and this one would be indistinguishable from a real fast click.
      if (!(ms >= 0 && ms <= 600_000)) return;
      try {
        deps.send(CLICK_ECHO, ms);
      } catch { /* a broken reporter must never break the click it measured */ }
    }));
  };

  target.addEventListener("click", onClick, true);   // capture: before any handler runs
  return () => target.removeEventListener("click", onClick, true);
}

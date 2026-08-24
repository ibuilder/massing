/**
 * R24-PERF-BUDGET — the client half of the budgets, measured in the only place that can see them.
 *
 * Two of the three stated budgets describe things no server can observe. `perf_budget.py` kept them
 * declared and `unmeasured` rather than asserting a server number in their place, on the grounds
 * that *"a budget file that lists three budgets and quietly checks one is how a green suite comes to
 * imply more than it tested"*. This module measures both of them:
 *
 * * **click echo** — the interval between a user's click and the first paint that answers it;
 * * **panel load** — the interval between that click and a panel becoming usable, added v0.3.1083.
 *
 * **This paragraph said `panel_load` was deliberately NOT here, and it was true for fourteen
 * releases.** The beacon existed from v0.3.1063; what was missing was a moment. `ui/modal.ts` builds
 * an empty shell and each caller fills it afterwards, so timing that chokepoint records DOM
 * construction. Closed by measuring from the CLICK and having each panel say when it is usable — see
 * the `panel_load` section at the bottom of this file for what that costs and why the population is
 * narrower than the click budget's.
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
/**
 * The send path both budgets share: a rolling per-minute cap, an implausible-interval drop, and a
 * reporter that cannot throw outward.
 *
 * Factored rather than copied when `panel_load` arrived. Copying it would have produced two sets of
 * these three rules, and the failure that follows is not a crash — it is the two budgets quietly
 * disagreeing about what counts as a measurement, which nobody notices because both keep reporting.
 */
function cappedSender(deps: { send: (b: string, ms: number) => void; now: () => number },
                      cap: number): (budget: string, t0: number) => void {
  let sent: number[] = [];
  return (budget, t0) => {
    const t = deps.now();
    sent = sent.filter((x) => t - x < 60_000);
    if (sent.length >= cap) return;
    sent.push(t);
    const ms = t - t0;
    // A negative or absurd interval means the clock moved under us (tab suspend, clock change).
    // Dropping it is the same call the sink makes: a fabricated measurement looks like evidence,
    // and this one would be indistinguishable from a real fast reading.
    if (!(ms >= 0 && ms <= 600_000)) return;
    try {
      deps.send(budget, ms);
    } catch { /* a broken reporter must never break the interaction it measured */ }
  };
}

export function installClickEcho(target: EventTarget, deps: ClickEchoDeps): () => void {
  const isUser = deps.isUserEvent ?? ((e: Event) => e.isTrusted);
  const report = cappedSender(deps, deps.maxPerMinute ?? DEFAULT_MAX_PER_MINUTE);

  const onClick = (e: Event) => {
    if (!isUser(e)) return;
    const t0 = deps.now();
    // A panel opened by this click is measured from HERE, not from when its shell is built. See
    // `beginPanelLoad`. Recorded before the frames below so an opener that runs synchronously in a
    // handler still finds it.
    notePanelClick(t0);
    // Two frames: the first callback runs before the paint, the second after it. See the header.
    deps.raf(() => deps.raf(() => report(CLICK_ECHO, t0)));
  };

  target.addEventListener("click", onClick, true);   // capture: before any handler runs
  return () => target.removeEventListener("click", onClick, true);
}

// ---------------------------------------------------------------------------------------------
// panel_load — the second client budget, and the one that stayed unmeasured for fourteen releases
// ---------------------------------------------------------------------------------------------
//
// **The blocker was never the beacon; it was the MOMENT.** `perf_budget.py` said so in its
// `why_unmeasured`: `ui/modal.ts` builds an empty shell and each caller fills it afterwards, so
// timing that chokepoint records a few hundred microseconds of DOM construction and files it as a
// panel load. A budget reported green against a measurement of the wrong thing is worse than one
// openly unmeasured.
//
// Two decisions make the moment honest:
//
// **Measured from the CLICK, not from the shell.** Two of these dialogs (`Estimate confidence`,
// `Compose Exhibit A`) are handed their data by a caller that fetched it first — so a timer starting
// at `modalShell` would miss the user's entire wait and report the DOM work instead. Checked by
// reading every call site, not inferred: an earlier pass of this work guessed from file names and
// was wrong about `qr.ts`, which awaits `QRCode.toCanvas` before its panel is usable.
//
// **Synchronous dialogs do not report at all.** Including them was tempting — the click budget's own
// docstring refuses to drop fast readings, on the grounds that "a percentile over only the
// suspicious ones is not a percentile". That reasoning does not carry: most modal opens in this app
// are trivial dialogs built from data already in hand, so counting them would let a healthy-looking
// p95 be produced entirely by dialogs that never load anything, no matter how slow the real panels
// are. `panelReady.test.ts` holds the classification per site so it is a declaration a reviewer can
// argue with, not a regex's guess.

export const PANEL_LOAD = "panel_load";

/** What panel timing needs. Same injected shape as `ClickEchoDeps`, minus the parts only clicks use. */
export interface PanelLoadDeps {
  send: (budget: string, ms: number) => void;
  now: () => number;
  raf: (fn: () => void) => void;
  maxPerMinute?: number;
}

/**
 * The click a panel open is measured from.
 *
 * `used` is what stops a stale click seeding a bogus interval: **a click seeds at most ONE panel
 * load.** Without it a modal opened by a timer or a socket message thirty seconds after the last
 * click reports thirty seconds — and one such reading moves a p95 further than any real regression.
 */
let lastClick: { t: number; used: boolean } | null = null;
let panelDeps: PanelLoadDeps | null = null;
let panelReport: ((budget: string, t0: number) => void) | null = null;

/** Record the click a subsequent panel open should be measured from. Called by the click tracker. */
export function notePanelClick(t: number): void {
  lastClick = { t, used: false };
}

/**
 * Enable panel-load timing. Returns a disposer.
 *
 * Separate from `installClickEcho` deliberately: one install doing both silently would make it
 * impossible to have one budget measured and the other not — which is exactly the state this repo
 * was in, on purpose, while the panel budget had no honest moment to measure.
 */
export function installPanelLoad(deps: PanelLoadDeps): () => void {
  panelDeps = deps;
  panelReport = cappedSender(deps, deps.maxPerMinute ?? DEFAULT_MAX_PER_MINUTE);
  return () => { panelDeps = null; panelReport = null; lastClick = null; };
}

/**
 * Start timing a panel open. Returns the `ready()` to call when the panel is USABLE.
 *
 * A no-op when timing is not installed, and that is the honest failure: the budget then reports
 * `no_observations`, which is a true statement. Inventing a number is the alternative.
 *
 * `ready()` is idempotent because panels re-render — the audit log refilters, the register repages —
 * and only the FIRST fill is the load the user waited through. Calling it from a `finally` is the
 * intended usage, so a panel that fails to load still ends its interval: the user's wait ended when
 * the error appeared, and dropping those would measure only the loads that succeeded.
 */
export function beginPanelLoad(): () => void {
  const d = panelDeps, report = panelReport;
  if (!d || !report) return () => { /* not installed: report nothing rather than a wrong number */ };
  const seed = lastClick && !lastClick.used ? lastClick : null;
  if (seed) seed.used = true;
  const t0 = seed ? seed.t : d.now();
  let done = false;
  return () => {
    if (done) return;
    done = true;
    // Two frames, for the same reason click echo uses them: the first rAF callback runs BEFORE the
    // paint, so measuring there reports the time to schedule the answer rather than to show it.
    d.raf(() => d.raf(() => report(PANEL_LOAD, t0)));
  };
}

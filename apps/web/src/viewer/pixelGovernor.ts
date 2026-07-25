/**
 * R23-PIXEL-GOVERNOR — trade resolution for frame rate, automatically.
 *
 * The engine sets `setPixelRatio(min(devicePixelRatio, 2))` once in its constructor and never revisits
 * it. On a 4K display that means every pixel of a thirty-storey tower is shaded at 2× for ever, however
 * badly the frame rate is doing — and dropping to 1× is a 4× reduction in fragment work, by far the
 * cheapest large win available on a heavy model.
 *
 * The decision is kept as a pure function because the hard part is not measuring, it is **not
 * oscillating**. A governor that flips between two ratios every few frames looks worse than one that
 * never adjusts at all: the resolution visibly pulses. So there is a dead band between the
 * degrade and the recover thresholds, and recovery additionally requires a sustained run of good
 * frames — degrade fast (the user is suffering now), recover slowly (be sure it will hold).
 */

/** Ratios we are willing to use, coarse on purpose — fine steps make pulsing more visible, not less. */
export const RATIO_STEPS: readonly number[] = [0.5, 0.75, 1, 1.5, 2];

export interface GovernorOpts {
  /** Above this smoothed frame time, shed resolution. ~22 ms ≈ below 45 fps. */
  degradeMs: number;
  /** Below this, consider restoring. The gap to `degradeMs` is the dead band that stops pulsing. */
  recoverMs: number;
  /** Consecutive good samples required before stepping back up. */
  recoverStreak: number;
}

export const DEFAULT_OPTS: GovernorOpts = { degradeMs: 22, recoverMs: 13, recoverStreak: 45 };

export interface GovernorState {
  ratio: number;
  ema: number;
  streak: number;
}

/** Snap an arbitrary ratio to the nearest allowed step, never exceeding `max`. */
export function snapRatio(r: number, max: number): number {
  const allowed = allowedSteps(max);
  return allowed.reduce((best, s) => (Math.abs(s - r) < Math.abs(best - r) ? s : best), allowed[0]!);
}

/** The steps usable on this display, never empty — a device below the smallest step still gets one. */
function allowedSteps(max: number): number[] {
  const a = RATIO_STEPS.filter((s) => s <= max + 1e-9);
  return a.length ? a : [Math.min(RATIO_STEPS[0]!, max)];
}

/**
 * Fold one frame sample into the state. Pure: same state + same sample → same next state, which is
 * what makes the hysteresis testable rather than something you squint at on a laptop.
 */
export function step(state: GovernorState, frameMs: number, max: number,
                     opts: GovernorOpts = DEFAULT_OPTS): GovernorState {
  // ignore absurd samples: a backgrounded tab or a GC pause is not a rendering problem, and letting
  // one 400 ms hitch drop the resolution for everyone is a worse experience than the hitch was
  const sample = frameMs > 0 && frameMs < 200 ? frameMs : state.ema;
  const ema = state.ema <= 0 ? sample : state.ema * 0.9 + sample * 0.1;
  const allowed = allowedSteps(max);
  const i = allowed.indexOf(snapRatio(state.ratio, max));

  if (ema > opts.degradeMs && i > 0) {
    return { ratio: allowed[i - 1]!, ema, streak: 0 };     // degrade immediately
  }
  if (ema < opts.recoverMs && i >= 0 && i < allowed.length - 1) {
    const streak = state.streak + 1;
    if (streak >= opts.recoverStreak) return { ratio: allowed[i + 1]!, ema, streak: 0 };
    return { ratio: state.ratio, ema, streak };            // recover only once it has held
  }
  // inside the dead band, or already at a limit: hold, and reset the run toward recovery
  return { ratio: state.ratio, ema, streak: 0 };
}

export function initialState(max: number): GovernorState {
  return { ratio: snapRatio(max, max), ema: 0, streak: 0 };
}

/**
 * Drive a renderer's pixel ratio from measured frame times. Returns a stop function.
 *
 * `setPixelRatio` is only called when the ratio actually changes — it reallocates the drawing buffer,
 * so calling it every frame would itself be the performance problem.
 */
export function attachPixelGovernor(
  renderer: { setPixelRatio(r: number): void },
  frames: { raf: (cb: FrameRequestCallback) => number; caf: (h: number) => void },
  now: () => number,
  max: number,
  opts: GovernorOpts = DEFAULT_OPTS,
): () => void {
  let state = initialState(max);
  let last = now();
  let handle = 0;
  let stopped = false;
  const tick = () => {
    if (stopped) { handle = 0; return; }
    const t = now();
    const next = step(state, t - last, max, opts);
    last = t;
    if (next.ratio !== state.ratio) renderer.setPixelRatio(next.ratio);
    state = next;
    handle = frames.raf(tick);
  };
  handle = frames.raf(tick);
  return () => { stopped = true; if (handle) { frames.caf(handle); handle = 0; } };
}

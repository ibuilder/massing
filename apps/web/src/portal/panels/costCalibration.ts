/**
 * COST-CALIBRATE — read this project's own cost history back as a calibration factor.
 *
 * `GET /projects/{pid}/cost/calibration` compares the model's takeoff estimate against what the
 * project has actually **committed** (awarded subcontract values) and **spent** (posted direct
 * costs), and returns `observed ÷ estimate` as a factor future estimates could apply. It is the
 * "learns from historical cost data" half of COST-AGENT, it has worked since v0.3.475, and **no
 * client has ever called it** — its leaf `calibration` was read as reachable by the route gate
 * because `apps/web/src/vendor/massingpdf/` uses the word 85 times for PDF *scale* calibration.
 * A different sense of the same word vouched for it.
 *
 * **Why this module exists rather than a direct render.** The factor is a ratio of two numbers that
 * mean different things at different points in a job, and the engine reports it through a clamp.
 * Printing `calibration_factor` on its own would state a measurement the engine did not make. The
 * rules here recover what it did: the raw ratio, whether the clamp moved it, and whether the basis
 * is finished enough to carry to another project.
 *
 * Pure rules only — no DOM, no fetch, no formatting. `budget.ts` renders these.
 */

/** The response of `GET /projects/{pid}/cost/calibration`. */
export interface Calibration {
  estimate_total: number;
  committed_total: number;
  actual_total: number;
  /** Which total the engine divided by the estimate — `null` when neither exists yet. */
  basis: "actual" | "committed" | null;
  /** `observed ÷ estimate`, **clamped to 0.5–2.0** and rounded to 3dp. Null without a basis. */
  calibration_factor: number | null;
  apply_hint: string;
  note: string;
}

/** The engine's clamp, mirrored here because recovering the raw ratio depends on knowing it. */
export const CLAMP_LOW = 0.5;
export const CLAMP_HIGH = 2.0;

/** The total the engine actually divided by — the one `basis` names. 0 when there is no basis. */
export function basisTotal(c: Calibration): number {
  if (c.basis === "actual") return c.actual_total;
  if (c.basis === "committed") return c.committed_total;
  return 0;
}

/**
 * `observed ÷ estimate` **before** the clamp — what the project's history actually says.
 *
 * The engine returns only the clamped figure, so this is the number nobody could see. It is
 * recoverable because the response carries all three totals, which is the one piece of luck here.
 */
export function rawRatio(c: Calibration): number | null {
  if (!c.basis || c.estimate_total <= 0) return null;
  return basisTotal(c) / c.estimate_total;
}

/**
 * Did the clamp move the reported factor?
 *
 * This matters more than it looks. `max(0.5, min(2.0, ratio))` turns a raw 0.05 — a job that has
 * barely started — into a reported **0.5**, which reads as a considered finding that the model
 * over-prices by half. *The clamp does not make an unreliable ratio safe; it makes it look
 * reliable.* A boundary value reported as a measurement is the failure this flag exists to prevent.
 */
export function clamped(c: Calibration): boolean {
  const raw = rawRatio(c);
  if (raw == null) return false;
  return raw < CLAMP_LOW || raw > CLAMP_HIGH;
}

/** Which way the factor points — the half an estimator is most likely to read backwards. */
export type Direction = "under-priced" | "over-priced" | "level";

/**
 * A factor above 1 means the project cost MORE than the model said, i.e. the model **under-prices**.
 * Stated as a named function with its own test because the inversion is silent: nothing downstream
 * would look wrong if this were the other way round.
 */
export function direction(factor: number | null): Direction {
  if (factor == null || factor === 1) return "level";
  return factor > 1 ? "under-priced" : "over-priced";
}

/**
 * How far to trust the factor. Ordered by what a reader must be told first.
 *
 * - `no-basis` — nothing committed and nothing spent; there is no factor at all.
 * - `unverifiable` — a factor arrived that this module cannot recompute, because there is no
 *   positive estimate to divide by. **It FAILS CLOSED**: every other verdict here rests on
 *   recovering the raw ratio, so a response where that is impossible gets no endorsement. The route
 *   guards `if basis and est_total > 0` and so should not produce one — which is the reason to
 *   handle it rather than to assume it away. *A screen that cannot check a number must not vouch
 *   for it.*
 * - `clamped` — the raw ratio fell outside 0.5–2.0, so the reported figure is a boundary the engine
 *   chose, not a ratio it measured.
 * - `partial` — the basis is posted ACTUALS while more is still committed than spent, so the job is
 *   not finished and the ratio is of a part against the whole.
 * - `usable` — a ratio inside the band, on a basis that is not visibly mid-job.
 */
export type Trust = "no-basis" | "unverifiable" | "clamped" | "partial" | "usable";

/**
 * `partial` is the case the engine cannot see and the one that bites first.
 *
 * `cost.py` picks `("actual", actual) if actual > 0 else ("committed", committed)` — **any** posted
 * direct cost, however small, outranks every awarded subcontract. That preference is right at
 * completion, where actuals are the truth and commitments are stale, and exactly wrong at the start,
 * where a single $500 invoice against a $10M estimate yields a raw 0.00005. *The preference that is
 * correct at the end is wrong at the beginning, and nothing in the route knows which end it is at.*
 *
 * Detected rather than guessed: while a job runs, more is committed than has been posted against it.
 * `actual < committed` is therefore "still running", and it is a fact about the response, not a
 * threshold somebody picked.
 */
export function trust(c: Calibration): Trust {
  if (!c.basis || c.calibration_factor == null) return "no-basis";
  // Fail closed before any verdict that depends on the raw ratio. `clamped()` returns false when it
  // cannot compute one, which is the right answer to "was it clamped?" and the wrong basis for
  // "is it usable?" — reaching `usable` through that false was this module's own first bug.
  if (rawRatio(c) == null) return "unverifiable";
  if (clamped(c)) return "clamped";
  if (c.basis === "actual" && c.committed_total > c.actual_total) return "partial";
  return "usable";
}

/** What the basis IS, in the estimator's terms — history or forecast. */
export function basisNote(basis: Calibration["basis"]): string {
  if (basis === "actual") return "posted direct costs — money the project has actually spent";
  if (basis === "committed") return "awarded subcontract values — money committed but not yet spent, "
    + "so this is a forecast of the outturn rather than a record of it";
  return "nothing committed and nothing posted yet — there is no history to calibrate against";
}

/** Why the factor should or should not be carried to the next project. */
export function trustNote(t: Trust, c: Calibration): string {
  if (t === "no-basis") return "Award a subcontract or post a direct cost to enable calibration.";
  if (t === "unverifiable") return "A factor arrived with no model estimate to divide by, so it "
    + "cannot be checked here. Do not act on it — price the model first.";
  if (t === "clamped") {
    const raw = rawRatio(c);
    const side = raw != null && raw < CLAMP_LOW ? "below" : "above";
    return `The underlying ratio falls ${side} the engine's 0.5–2.0 band, so the figure shown is that `
      + "boundary rather than a measurement. Do not carry it to another project — on a job this far "
      + "from its estimate the ratio is describing incompleteness, not pricing.";
  }
  if (t === "partial") return "More is committed than has been posted, so this job is still running "
    + "and the factor divides part of the spend by the whole estimate. It will rise as the job "
    + "completes; read it as provisional.";
  return "The basis is inside the plausible band. Reported for the estimator — never auto-applied.";
}

/**
 * Percent by which the model mis-prices, from the factor. 1.2 → 20, 0.8 → −20.
 *
 * Signed deliberately: "20% under-priced" and "20% over-priced" are different instructions, and a
 * bare magnitude beside a direction word invites reading one and not the other.
 */
export function misPricePct(factor: number | null): number | null {
  if (factor == null) return null;
  return Math.round((factor - 1) * 1000) / 10;
}

/** The headline an estimator reads: the factor, which way it points, and whether to believe it. */
export function summary(c: Calibration): {
  factor: number | null; raw: number | null; direction: Direction;
  trust: Trust; pct: number | null; usable: boolean;
} {
  const t = trust(c);
  return {
    factor: c.calibration_factor,
    raw: rawRatio(c),
    direction: direction(c.calibration_factor),
    trust: t,
    pct: misPricePct(c.calibration_factor),
    usable: t === "usable",
  };
}

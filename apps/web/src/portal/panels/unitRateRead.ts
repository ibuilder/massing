/**
 * UNITRATE-BASIS — the engine says *"Check `spread_ratio` and `per_project` before quoting a
 * median"*, and the card showed the median and withheld both.
 *
 * `unit_rate_memory.unit_rates` is unusually careful about what its own numbers are worth. It
 * returns three sentences the client type declared none of:
 *
 *   - **`basis`** — *"each rate is one PROJECT's cost divided by that project's installed quantity
 *     for one cost code and unit; the distribution is over projects. `pooled_rate` is the
 *     portfolio-wide blend and answers a different question."*
 *   - **`limitation`** — *"direct_cost and production_quantity accumulate independently, so a code
 *     whose invoices lead its field quantity reporting reads as expensive and the reverse reads as
 *     cheap. Check `spread_ratio` and `per_project` before quoting a median."*
 *   - **`excluded`** — mixed units, cost with no quantity, quantity with no cost, each with a count
 *     and a reason, *"never dropped — a project that could not be measured is not a project that
 *     cost zero."*
 *
 * The card printed `median`, `p25` and `p75`. **So it rendered the number the engine warns about and
 * hid the field the engine says to check first**, and the excluded codes — the ones that could not
 * be measured at all — appeared nowhere. *An engine that tells you what to check before quoting it
 * has done the hard part; dropping that sentence is the only way to get the quote wrong.*
 *
 * **One threshold, and it is the engine's own.** Its comment beside `spread_ratio` reads: *"A code
 * where one project is an order of magnitude off another is usually a reporting-lag artefact rather
 * than a price difference."* So 10× is the line, taken from there rather than invented, and there is
 * deliberately no second softer band — a threshold nobody stated is a judgement this module is not
 * entitled to make.
 *
 * Pure, plain text: cost codes and units are user data.
 */

export interface UnitRateCode {
  cost_code: string;
  unit: string;
  projects: number;
  below_threshold: boolean;
  low: number;
  p25: number;
  median: number;
  p75: number;
  high: number;
  pooled_rate: number | null;
  spread_ratio: number | null;
  total_cost?: number;
  total_quantity?: number;
  per_project?: { project_id: string; cost: number; quantity: number; rate: number }[];
}

export interface UnitRateExclusions {
  mixed_units?: { project_id: string; cost_code: string; units?: string[]; reason?: string }[];
  cost_without_quantity?: { project_id: string; cost_code: string; cost: number; reason?: string }[];
  quantity_without_cost?: { project_id: string; cost_code: string; reason?: string }[];
  note?: string;
}

export interface UnitRates {
  cost_codes: UnitRateCode[];
  code_count: number;
  usable_count: number;
  min_projects: number;
  message: string | null;
  basis?: string;
  limitation?: string;
  excluded?: UnitRateExclusions;
}

export type RateTone = "ok" | "warn" | "unknown";

export const RATE_CSS: Record<RateTone, string> = {
  ok: "var(--status-good)", warn: "var(--status-warn)", unknown: "var(--muted)",
};

/** The engine's own line for "usually a reporting-lag artefact rather than a price difference". */
export const ORDER_OF_MAGNITUDE = 10;

/**
 * How much the projects behind a median disagree, and whether the median is quotable.
 *
 * A `null` ratio means the low rate was zero, so high/low is undefined — reported as unknown rather
 * than as a narrow spread, which is what a missing number would look like if it rendered as a dash
 * in an otherwise reassuring row.
 */
export function spreadReading(c: UnitRateCode): { text: string; tone: RateTone; quotable: boolean } {
  const r = c.spread_ratio;
  if (r === null || r === undefined) {
    return { text: "—", tone: "unknown", quotable: false };
  }
  if (r >= ORDER_OF_MAGNITUDE) {
    return { text: `${r}×`, tone: "warn", quotable: false };
  }
  return { text: `${r}×`, tone: "ok", quotable: true };
}

/** The codes whose spread puts them past the engine's own order-of-magnitude line. */
export function unquotable(r: UnitRates): UnitRateCode[] {
  return r.cost_codes.filter((c) => !c.below_threshold && !spreadReading(c).quotable);
}

/**
 * What could not be measured at all, by reason.
 *
 * `null` only when the server sent no `excluded` block. A block with every list empty returns a
 * sentence saying so: *nothing excluded* and *we did not look* are different facts, and this is the
 * one place the difference is visible.
 */
export function exclusionLine(r: UnitRates): { text: string; tone: RateTone } | null {
  const e = r.excluded;
  if (!e) return null;
  const parts: string[] = [];
  const n = (xs?: unknown[]) => (xs ?? []).length;
  if (n(e.mixed_units)) parts.push(`${n(e.mixed_units)} recorded under two units`);
  if (n(e.cost_without_quantity)) parts.push(`${n(e.cost_without_quantity)} with cost but no installed quantity`);
  if (n(e.quantity_without_cost)) parts.push(`${n(e.quantity_without_cost)} with quantity but no cost`);
  if (!parts.length) {
    return { text: "Every project/code pair with cost or quantity produced a rate — nothing excluded.",
             tone: "ok" };
  }
  return {
    text: `Excluded from the rates above: ${parts.join(", ")}. A project that could not be measured `
      + "is not a project that cost zero, so these are reported rather than dropped.",
    tone: "warn",
  };
}

/** The portfolio blend beside the median, labelled as the different question it answers. */
export function pooledLine(c: UnitRateCode): string | null {
  if (c.pooled_rate === null || c.pooled_rate === undefined) return null;
  return `pooled ${c.pooled_rate} (Σcost ÷ Σquantity — one large project sets it)`;
}

/** Both numbers where the table stops, or `""` when it is the whole list. */
export function ratePageNote(shown: number, total: number): string {
  return shown < total ? `Showing ${shown} of ${total} usable cost codes.` : "";
}

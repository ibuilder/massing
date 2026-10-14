/**
 * ESTIMATE-BASIS — the conceptual estimator computes the number a developer should underwrite to,
 * and the card showed the other one.
 *
 * `conceptual_estimate.estimate` escalates to the **midpoint of construction** when it is given a
 * start year and a duration — which is the correct basis for a development budget, because money is
 * spent across the build and not on the day the estimate is made. Measured on an office at 120,000
 * sf, `us_average`, 20 storeys, a 2027 start and a 24-month build: base-year total **$49,476,000**,
 * `market.total_at_construction_midpoint` **$54,131,692** — **9.4%, $4.66M** apart. The card
 * rendered the first.
 *
 * It could not have rendered the second: `market` was undeclared on the client type, and the card
 * passed neither `start_year` nor `duration_months`, so the whole of Track M — regional labour
 * rate, sector temperature, escalation basis and the midpoint total — was computed on every call
 * and reachable from nothing.
 *
 * `year`, `region`, `height_factor` and `soft_cost_pct` were undeclared too, and they are the BASIS:
 * a $/SF number is a claim about a building type, a market, a year and a soft-cost assumption, and
 * a total shown without them cannot be reconciled against anything. `note` says the estimate is
 * **Class 5** — AACE's widest class, a directional signal rather than a takeoff — and that went
 * unrendered beside a low–high band of ±15/20%, which reads far tighter than Class 5 is.
 *
 * Pure, plain text. `sector_note` and `escalation_basis` are composed server-side.
 *
 * Money goes through `ui/charts.usd`, NOT a local helper. The first draft of this file had
 * `const money = …` and `apps/web/src/ui/charts.test.ts` refused it on the spot — the rule exists
 * because "eighteen local copies disagreed about how a negative renders, and ten of them put the
 * $ on the wrong side of the minus". A delta here can be negative.
 */

import { usd } from "../../ui/charts";


export interface ConceptualMarket {
  region: string;
  labour_usd_hr: number;
  sector_temperature: string;
  sector_note: string;
  /** Present only when a `start_year` was given. */
  escalation_basis?: string;
  midpoint_escalation_factor?: number;
  total_at_construction_midpoint?: number;
}

export interface ConceptualEstimate {
  building_type: string;
  gfa_sf: number;
  region?: string;
  region_index: number;
  year?: number;
  escalation_factor: number;
  height_factor?: number;
  soft_cost_pct?: number;
  hard_cost: number;
  soft_cost: number;
  total_cost: number;
  range: { low: number; base: number; high: number };
  metrics: Record<string, number>;
  market?: ConceptualMarket;
  note?: string;
  error?: string;
}

export type BasisTone = "ok" | "warn" | "unknown";

export const BASIS_CSS: Record<BasisTone, string> = {
  ok: "var(--status-good)", warn: "var(--status-warn)", unknown: "var(--muted)",
};


/**
 * What this number is a claim ABOUT.
 *
 * Every row is omitted when the server did not send it, rather than defaulted: a `height_factor` of
 * `1.0` is a real answer (no height premium) and an absent one is not knowable, and printing "1.0"
 * for both would state something nobody measured. The same reason `region_index` and
 * `escalation_factor` are shown as factors rather than folded into the total silently.
 */
export function basisRows(r: ConceptualEstimate): { label: string; value: string }[] {
  const rows: { label: string; value: string }[] = [
    { label: "Building type", value: r.building_type },
  ];
  if (r.region) rows.push({ label: "Region", value: `${r.region} (×${r.region_index})` });
  // A YEAR, ALWAYS, when the server sends one. The engine defaults it to its base year, so a total
  // with no year beside it is a base-year number presented as "the" cost.
  if (r.year !== undefined) {
    rows.push({ label: "Cost year", value: `${r.year} (escalation ×${r.escalation_factor})` });
  }
  if (r.height_factor !== undefined && r.height_factor !== 1) {
    rows.push({ label: "Height premium", value: `×${r.height_factor}` });
  }
  if (r.soft_cost_pct !== undefined) {
    rows.push({ label: "Soft costs", value: `${r.soft_cost_pct}% of hard` });
  }
  return rows;
}

/**
 * The number to underwrite to, or what is missing to compute it.
 *
 * Returns a `prompt` rather than `null` when no start year was given: the alternative is silence,
 * and silence over a figure that is materially lower than the right one is the defect this item is
 * named for. *A screen that cannot compute the better number should say which input it is waiting
 * for, not show the worse one unlabelled.*
 */
export function midpointReading(r: ConceptualEstimate): {
  kind: "escalated" | "prompt"; text: string; tone: BasisTone; total?: number; deltaPct?: number;
} {
  const m = r.market;
  const mid = m?.total_at_construction_midpoint;
  if (mid === undefined || !r.total_cost) {
    return {
      kind: "prompt",
      text: "This total is in today's money. Give a construction start year and duration to escalate "
        + "it to the MIDPOINT of the build, which is the basis a development budget is carried at.",
      tone: "unknown",
    };
  }
  // The delta is computed against the total this card is SHOWING, so the sentence is about the two
  // numbers a reader can see rather than about an intermediate the payload also carries.
  const deltaPct = Math.round(((mid - r.total_cost) / r.total_cost) * 1000) / 10;
  return {
    kind: "escalated",
    text: `${usd(mid)} at the construction midpoint — ${deltaPct >= 0 ? "+" : ""}${deltaPct}% on `
      + `today's ${usd(r.total_cost)}. Basis: ${m?.escalation_basis ?? "—"}`
      + (m?.midpoint_escalation_factor ? ` (×${m.midpoint_escalation_factor})` : "") + ".",
    tone: deltaPct >= 5 ? "warn" : "ok",
    total: mid,
    deltaPct,
  };
}

/** The market this is being built in: labour rate and how hot the sector is. */
export function sectorLine(r: ConceptualEstimate): { text: string; tone: BasisTone } | null {
  const m = r.market;
  if (!m) return null;
  const hot = /hot|overheat/i.test(m.sector_temperature);
  return {
    text: `${m.region}: labour $${m.labour_usd_hr}/hr · sector ${m.sector_temperature} — `
      + m.sector_note,
    tone: hot ? "warn" : "unknown",
  };
}

/**
 * The estimate class, said out loud.
 *
 * The band this card prints is −15%/+20%, which reads far tighter than a Class 5 estimate is, and
 * the engine's `note` is where it says so. Returned verbatim rather than paraphrased: it is the
 * engine's own caveat and a second wording of it is a second thing to keep in step.
 */
export function classNote(r: ConceptualEstimate): string | null {
  return r.note ?? null;
}

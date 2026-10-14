/**
 * LOD-UNREAD — the reading behind the card titled "LOD coverage", which rendered none.
 *
 * `lod.assess` is one of the most careful engines in this tree. It computes the achieved band as the
 * MINIMUM across the five ISO 7817-1 aspects, and then — because a minimum over aspects the index
 * cannot read is a floor rather than a reading — it also returns:
 *
 *   - `ceiling_distribution`: how high the same elements would reach if the aspects it could not
 *     read turned out to be met,
 *   - `elements_with_an_undecidable_aspect` and `elements_without_readable_geometry`: the exact
 *     per-element counts of why it could not read them,
 *   - `limited_by`: which aspect PROVED the cap that decided each element's band,
 *   - `compliance[phase].no_target`: the elements no target rule addresses, sitting beside
 *     `pct_meeting` rather than inside it.
 *
 * Its own note says the distinction in as many words: *"the gap is unread model, not missing
 * model."* The card rendered `distribution` and nothing else — one table of six bands — so a BIM
 * manager read "most elements at LOD 200" and concluded the model was under-modelled, when the
 * assessment may have been saying it could not see. **The card was literally named "LOD coverage"
 * and showed no coverage.**
 *
 * Found by RESPKEY-DELEGATED, which could not see this route until it learned to follow one hop into
 * the engine: `lod/assessment` was the largest single gap in the tree at ten undeclared keys, four
 * of them coverage. Same shape as CLASH-TRUNC and the eighteen entries above it — *the engine states
 * what it could not evaluate and the consumer renders the answer without the caveat.*
 *
 * Pure, so the reading is assertable without a DOM: the panel it serves has no test file.
 */

export interface LodCompliancePhase {
  meeting_target: number;
  short_of_target: number;
  no_target: number;
  pct_meeting: number | null;
  short_by_rule: Record<string, number>;
}

export interface LodAssessment {
  model_scored: boolean;
  elements: number;
  distribution: Record<string, number>;
  ceiling_distribution?: Record<string, number>;
  limited_by?: Record<string, number>;
  elements_with_an_undecidable_aspect?: number;
  elements_without_readable_geometry?: number;
  avg_information_score?: number;
  information_score_max?: number;
  compliance?: Record<string, LodCompliancePhase>;
}

/** The aspect keys as a reader says them. The engine's keys are ISO 7817-1 names in snake_case. */
const ASPECT_LABEL: Record<string, string> = {
  detail: "Level of detail",
  dimensionality: "Dimensionality",
  location: "Location",
  appearance: "Appearance",
  parametric_behavior: "Parametric behaviour",
};

export type Tone = "ok" | "warn" | "unknown";

/**
 * Achieved beside ceiling, per band.
 *
 * TWO COLUMNS, NOT A DIFFERENCE. An element sits in one achieved band and one ceiling band, and the
 * two aggregate distributions do not say which element moved where — so a per-band "headroom"
 * number would be arithmetic on populations that are not the same population. The exact counts of
 * *why* a band is a floor are `elements_with_an_undecidable_aspect` and
 * `elements_without_readable_geometry`, which are per-element and reported as themselves by
 * `readability` below. *A derived number that looks precise is worse than two honest columns.*
 */
export function bandRows(a: LodAssessment): { band: string; achieved: number; ceiling: number | null }[] {
  const ceil = a.ceiling_distribution;
  return Object.entries(a.distribution).map(([band, achieved]) => ({
    band,
    achieved,
    ceiling: ceil ? (ceil[band] ?? 0) : null,
  }));
}

/** Does the ceiling differ from the achieved distribution at all? If not, the band IS the reading. */
export function ceilingDiffers(a: LodAssessment): boolean {
  const ceil = a.ceiling_distribution;
  if (!ceil) return false;
  const bands = new Set([...Object.keys(a.distribution), ...Object.keys(ceil)]);
  for (const b of bands) if ((a.distribution[b] ?? 0) !== (ceil[b] ?? 0)) return true;
  return false;
}

/**
 * How much of the assessment is a READING and how much is a floor.
 *
 * `earned` is the tick, and it demands BOTH counts be zero — not "no elements flagged", which is
 * also true of a model with no elements. The empty case is therefore first and answers `unknown`,
 * because a green tick over nothing assessed is the defect this whole class is named for.
 */
export function readability(a: LodAssessment): {
  text: string; tone: Tone; earned: boolean; undecidable: number; unreadable: number;
} {
  const undecidable = a.elements_with_an_undecidable_aspect ?? 0;
  const unreadable = a.elements_without_readable_geometry ?? 0;
  if (!a.elements) {
    return { text: "No elements were assessed, so the bands below describe nothing.",
             tone: "unknown", earned: false, undecidable, unreadable };
  }
  // A response from before the coverage keys existed, or one that omitted them: say so rather than
  // treating an absent count as a zero. `?? 0` above is for the arithmetic; the VERDICT must not
  // claim a reading it was not given.
  if (a.elements_with_an_undecidable_aspect === undefined
      || a.elements_without_readable_geometry === undefined) {
    return { text: "This response carries no readability counts, so whether these bands are a "
                   + "reading or a floor is not knowable from it.",
             tone: "unknown", earned: false, undecidable, unreadable };
  }
  if (!undecidable && !unreadable) {
    return { text: `✓ Every one of the ${a.elements} elements was fully readable — these bands are `
                   + "a reading, not a floor.",
             tone: "ok", earned: true, undecidable, unreadable };
  }
  const parts: string[] = [];
  if (undecidable) parts.push(`${undecidable} have at least one aspect the index could not decide`);
  if (unreadable) parts.push(`${unreadable} have no readable geometry`);
  return {
    text: `⚠ Of ${a.elements} elements, ${parts.join(" and ")}. Their band is a FLOOR, not a `
          + "reading — the Ceiling column is how high they would reach if those aspects were met, "
          + "so a wide gap means unread model, not missing model.",
    tone: "warn", earned: false, undecidable, unreadable,
  };
}

/** Which aspect proved the cap, highest first. "Why" is the only part a team can act on. */
export function limitingRows(a: LodAssessment): { aspect: string; elements: number }[] {
  return Object.entries(a.limited_by ?? {})
    .filter(([, n]) => n > 0)
    .sort((x, y) => y[1] - x[1])
    .map(([k, n]) => ({ aspect: ASPECT_LABEL[k] ?? k, elements: n }));
}

/**
 * Target compliance per stage, with `no_target` BESIDE the percentage.
 *
 * The engine's own comment: *"A model element table that covers a third of the model and reports
 * 100% is the failure this whole item exists to remove."* It kept the uncovered count out of the
 * percentage; this keeps it on the screen, because a percentage whose denominator is unstated is
 * the same defect one layer along. A phase that scored nothing renders `—`, never `0%`.
 */
export function complianceRows(a: LodAssessment): {
  phase: string; met: number; short: number; noTarget: number; pct: string; tone: Tone;
}[] {
  return Object.entries(a.compliance ?? {}).map(([phase, c]) => {
    const scored = c.meeting_target + c.short_of_target;
    return {
      phase,
      met: c.meeting_target,
      short: c.short_of_target,
      noTarget: c.no_target,
      pct: c.pct_meeting == null ? "—" : `${c.pct_meeting}%`,
      // UNKNOWN, not OK, when no element was scored: `pct_meeting` is null there and a row reading
      // "0 short" would otherwise look like a pass. And a phase whose rules address fewer elements
      // than they miss is warned about however good its percentage is.
      tone: !scored ? "unknown" : c.short_of_target || c.no_target > scored ? "warn" : "ok",
    };
  });
}

/** Information-score line, which the old card also dropped. Stated with its maximum, never bare. */
export function infoScoreLine(a: LodAssessment): string | null {
  if (a.avg_information_score === undefined || !a.information_score_max) return null;
  return `LOIN facet completeness: ${a.avg_information_score} of ${a.information_score_max} facets `
    + "on average — a measure of how completely elements are DESCRIBED, which is a different "
    + "question from the geometry band above.";
}

export const TONE_CSS: Record<Tone, string> = {
  ok: "var(--status-good)",
  warn: "var(--status-warn)",
  unknown: "var(--muted)",
};

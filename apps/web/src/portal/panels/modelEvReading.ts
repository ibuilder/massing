import type { ApiClient } from "../../api/client";
import { usd } from "../../ui/charts";

/**
 * EVM-COVERAGE — reading the model-based earned value, and the coverage its verdict rests on.
 *
 * `front_loaded_flag` renders as *"Reported progress is running ahead of physical installation —
 * possible front-loaded SOV"*, in a panel with a PDF button. That is an allegation about a
 * contractor, and the card made it while reading `has_field_data` — a boolean that is true the
 * moment ONE element of the model has been surveyed. See `services/api/test_evm_coverage.py` for
 * the engine half; the flag now has to clear the ceiling the evidence allows before it is raised.
 *
 * This module is the consumer half, and it exists because **the card had no way to say "we only
 * walked 2% of the building"**: it printed `installed_elements of total_elements` and a single
 * percentage, so thin coverage and a genuinely stalled job produced the same sentence.
 *
 * `coverage_pct` is deliberately NOT the headline number. The engine rounds it to one decimal, so
 * 1 of 4,000 prints `0.0` — the same string an untouched job prints — and a card that leads with it
 * would re-commit the defect it is here to fix. The counts lead; the percentage follows them.
 */
export type ModelEv = Awaited<ReturnType<ApiClient["evmModelEv"]>>;

export interface ModelEvReading {
  /** `absent` — no model index. `unsurveyed` — nothing determined. `thin` — a partial survey.
   *  `front_loaded` — the accusation, which survived the ceiling. `tracking` — schedule agrees. */
  kind: "absent" | "unsurveyed" | "thin" | "front_loaded" | "tracking";
  /** Plain text; the caller escapes it. */
  headline: string;
  /** The second line: what the number is about, or what would make it mean more. */
  detail: string;
  tone: "ok" | "warn" | "bad" | "";
}

/** Is the install status of every element in the denominator actually known? */
export function fullyDetermined(m: ModelEv): boolean {
  const denom = m.total_elements || m.tracked_elements;
  return denom > 0 && m.determined_elements >= denom;
}

/**
 * What the card should say.
 *
 * The ORDER is the whole design. Coverage is answered before the verdict, because every verdict
 * below is a claim about the building and the coverage is what licenses it — the same ordering
 * `preconReadings.exposureCaveat` and `benchmarkScope` settled on. `front_loaded` therefore cannot
 * be reached while the survey is thin, which is not a presentation choice: the engine already
 * refuses to set the flag in that case, and this makes the screen agree rather than re-deriving it.
 */
export function modelEvReading(m: ModelEv): ModelEvReading {
  const denom = m.total_elements || m.tracked_elements;
  if (!denom) {
    return { kind: "absent", tone: "",
             headline: "No model elements and no field records yet.",
             detail: "Upload an IFC and log Field ▸ Verification records to earn value from the "
               + "building rather than from the billing percentage." };
  }
  // WHAT THE PERCENTAGE IS A SHARE OF, first — `basis` falls back from the model's element count to
  // the surveyed count, so the same eight installed elements read 80% or 0.2% under one field name.
  const of = `${denom} ${m.basis}`;
  if (!m.determined_elements) {
    return { kind: "unsurveyed", tone: "",
             headline: `Nothing verified in the field yet, of ${of}.`,
             detail: "Model EV is 0% by construction until elements are surveyed, so it is not yet "
               + "a check on reported progress — and no conclusion about the schedule follows from "
               + "it." };
  }
  if (!fullyDetermined(m)) {
    return {
      kind: "thin", tone: "warn",
      headline: `${m.determined_elements} of ${of} have a determined install status`
        + ` — physical progress is between ${m.model_percent_complete}%`
        + ` and ${m.model_percent_complete_max}%.`,
      detail: `EV from the model is somewhere in ${usd(m.ev_model)} … ${usd(m.ev_model_max)}, against`
        + ` ${usd(m.ev_schedule)} earned on the schedule. The range is survey coverage, not`
        + " disagreement: the band closes as elements are verified, and no front-loading finding can"
        + " be made while the schedule's figure sits inside it.",
    };
  }
  if (m.front_loaded_flag) {
    return {
      kind: "front_loaded", tone: "bad",
      headline: `Reported progress is ahead of the building: ${m.model_percent_complete}% installed`
        + ` against ${usd(m.ev_schedule)} earned on the schedule.`,
      detail: `${usd(m.divergence_unexplained)} of that gap survives the most favourable reading of`
        + ` the evidence (every undetermined element installed), over all ${of}. Often a`
        + " front-loaded schedule of values — worth reconciling before the next pay application.",
    };
  }
  return {
    kind: "tracking", tone: "ok",
    headline: `Schedule EV tracks physical installation across all ${of}.`,
    detail: `${m.model_percent_complete}% installed · EV(model) ${usd(m.ev_model)} vs`
      + ` EV(schedule) ${usd(m.ev_schedule)} (gap ${usd(m.divergence)}).`,
  };
}

/** The supporting rows: the counts the rounded percentage cannot carry. */
export function modelEvRows(m: ModelEv): { k: string; v: string }[] {
  const denom = m.total_elements || m.tracked_elements;
  const rows = [
    { k: `Denominator (${m.basis})`, v: String(denom) },
    { k: "Installed / verified", v: String(m.installed_elements) },
    { k: "Deviations recorded", v: String(m.deviated_elements) },
    // `tracked - determined` is the queued-but-unanswered set. Shown because it is the number that
    // closes the band, and a reader looking at a wide range wants to know whether the work is
    // already scheduled or has not been started.
    { k: "Awaiting inspection", v: String(Math.max(0, m.tracked_elements - m.determined_elements)) },
    { k: "Never looked at", v: String(Math.max(0, denom - m.tracked_elements)) },
  ];
  if (!fullyDetermined(m)) {
    rows.push({ k: "EV(model) range", v: `${usd(m.ev_model)} … ${usd(m.ev_model_max)}` });
  }
  return rows;
}

/**
 * The SECOND site, read the same way — `wipModelProgress`.
 *
 * `wip.model_progress` reports `installed ÷ total` over the whole model, so an element nobody has
 * walked is counted exactly like one inspected and found absent. The figure is therefore a FLOOR,
 * and `schedule(method="units-installed")` multiplies it by the contract value to get earned
 * revenue — which drives over/under-billing, which `accounting.journal_entries` posts back as the
 * WIP-ADJ line. *The EVM instance raises a banner; this one moves a number in a financial statement,
 * and it was found second.*
 *
 * Two consumers read it. `viewer/tools/qaSection.ts` renders the engine's `note` verbatim and so
 * gained the band without a change — **an unusual dividend of carrying a finding in prose as well
 * as in fields**, and the reason the engine's note was extended rather than only its keys.
 * `portal/panels/budget.ts` composes its own line and did not, which is what this exists for.
 */
export type ModelProgress = Awaited<ReturnType<ApiClient["wipModelProgress"]>>;

export interface ProgressReading {
  /** `absent` — no model. `floor` — a partial survey, so the percentage is a lower bound.
   *  `measured` — every element's install status is known. */
  kind: "absent" | "floor" | "measured";
  headline: string;
  detail: string;
  tone: "ok" | "warn" | "";
}

/**
 * What the budget panel should say about physical progress.
 *
 * Note what is NOT done here: the percentage is not re-derived, and `percent_complete_max` is taken
 * from the response rather than computed from the counts. Under quantity weighting the ceiling is
 * quantity-weighted — one unsurveyed 400 m³ pour is a single element and a quarter of the concrete —
 * so a consumer recomputing it from element counts would print a bound that is not one.
 */
export function modelProgressReading(w: ModelProgress): ProgressReading {
  if (!w.available) {
    return { kind: "absent", tone: "",
             headline: "Model progress is not available for this project.",
             detail: (w.note || "")
               + " That is not 0% complete — it needs a model with installed quantities to measure"
               + " against." };
  }
  const pct = w.percent_complete ?? w.percent_complete_count ?? 0;
  const total = w.total_elements ?? 0;
  const determined = w.determined_elements ?? total;
  // `fully_determined` is the engine's own answer and is preferred over re-deriving it; the count
  // comparison is the fallback for a response predating the field, not a second opinion.
  const full = w.fully_determined ?? determined >= total;
  if (full) {
    return {
      kind: "measured", tone: "ok",
      headline: `Model progress — ${pct}% complete.`,
      detail: `${w.installed_elements ?? 0} of ${total} element(s) installed, every one of them`
        + " inspected. Derived from installed quantity, not from a typed percentage.",
    };
  }
  const max = w.percent_complete_max ?? 100;
  return {
    kind: "floor", tone: "warn",
    headline: `Model progress — at least ${pct}%, at most ${max}%.`,
    detail: `${determined} of ${total} element(s) have a determined install status, so ${pct}% is a`
      + " FLOOR and not a measurement: an element nobody has walked counts here exactly like one"
      + " inspected and found absent. Verify more elements to close the band before this drives a"
      + " percentage-of-completion figure.",
  };
}

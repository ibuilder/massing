/** FIELDLOG-WINDOW — "coverage 100%" over three logged days of a 200-day job, every one a draft.
 *
 *  `services/api/src/aec_api/dailylog.py` computes
 *  `span_days = (max(dates) - min(dates)).days + 1` from the LOGGED report dates, and then
 *  `coverage_pct = 100 * logged_days / span_days`. **The denominator is derived from the answer.**
 *  It is coverage of the window the reports themselves define, never of the job. Measured on the
 *  engine:
 *
 *  | fixture | span | logged | coverage |
 *  |---|---|---|---|
 *  | one report | 1 | 1 | **100.0%** |
 *  | three contiguous days (on a 200-day build) | 3 | 3 | **100.0%** |
 *  | 20 of 31 days, with gaps | 31 | 20 | 64.5% |
 *
 *  *A superintendent who logged three days and stopped gets a clean 100%.*
 *
 *  **And drafts count toward everything.** Three reports all still `draft` report
 *  `coverage_pct: 100.0` with `submitted_count: 0` — the same percentage as three signed ones. The
 *  card printed `coverage ${s.coverage_pct}%` and rendered neither the window nor the split, and
 *  `submitted_count` was declared and never read. On a document that becomes evidence in a delay
 *  claim, "100% coverage, nothing submitted" and "100% coverage, all submitted" must not be the
 *  same sentence.
 *
 *  `span_days`, `logged_days`, `draft_count`, `first_date` and `last_date` were undeclared —
 *  RESPKEY-HOP2 made them visible — so the screen could not have shown the window even to a reader
 *  who wanted it.
 *
 *  **The percentage is NOT redefined**, and that is a decision rather than an omission: "how
 *  complete is the run I have" is a real question, while measuring against the schedule's span is a
 *  different one and a product call — the schedule may not exist or be unbaselined, and a field log
 *  legitimately starts after mobilisation. What changed is that the window travels with the figure.
 */
import type { ApiClient } from "./api/client";

/** Derived from the client method rather than redeclared — the idiom `coLogReadings.ts` and its
 *  siblings use, and a stricter answer to the same duplication question than a hand-written view. */
export type FieldLog = Awaited<ReturnType<ApiClient["fieldLogSummary"]>>;

/** What the coverage figure is worth. Three states, because the percentage alone has one. */
export type CoverageKind = "none" | "vacuous" | "windowed";

/**
 * `none` when nothing is dated, `vacuous` when the window cannot disagree with the reports
 * (a single day, or an unbroken run — `logged_days === span_days`), `windowed` otherwise.
 *
 * The vacuous case is the finding: it is 100% by construction, and it is the common shape on a job
 * where somebody logged a few days in a row.
 */
export function coverageKind(s: Pick<FieldLog, "span_days" | "logged_days" | "coverage_pct">): CoverageKind {
  if (!s.span_days || s.coverage_pct == null) return "none";
  return s.logged_days >= s.span_days ? "vacuous" : "windowed";
}

/** The headline figure, never a bare percentage on a window that cannot disagree with it. */
export function coverageLine(s: FieldLog): string {
  const kind = coverageKind(s);
  if (kind === "none") return "coverage — (no report carries a date)";
  const win = s.first_date && s.last_date ? ` ${s.first_date} → ${s.last_date}` : "";
  const of = `${s.logged_days} of ${s.span_days} day${s.span_days === 1 ? "" : "s"}`;
  if (kind === "vacuous") {
    return `coverage ${of} —${win} is the whole window these reports span, so 100% here means `
      + "unbroken, not complete";
  }
  return `coverage ${s.coverage_pct}% (${of} logged in${win})`;
}

/**
 * The draft split, or null when every report is submitted.
 *
 * Rendered whenever anything is unsigned, because every other figure on the card — manpower,
 * weather lost-days, delay days, coverage — counts drafts without saying so.
 */
export function draftLine(s: FieldLog): string | null {
  if (!s.draft_count) return null;
  const all = s.draft_count === s.report_count;
  return all
    ? `⚠ all ${s.report_count} report${s.report_count === 1 ? "" : "s"} are still DRAFT — every `
      + "figure here, coverage included, counts unsigned reports"
    : `⚠ ${s.draft_count} of ${s.report_count} reports still draft (${s.submitted_count} submitted) `
      + "— the figures here count both";
}

/** Whether the card should render its headline as a caveat rather than as a result. */
export function fieldLogSuspect(s: FieldLog): boolean {
  return coverageKind(s) !== "windowed" || s.draft_count > 0;
}

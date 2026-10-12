import type { ApiClient } from "../../api/client";

/**
 * BENCH-DARK — the portfolio space benchmark, and the exclusion its own response did not carry.
 *
 * `/benchmarks/space-utilization` compares every modelled project's m² per space against the
 * portfolio median, with a capacity total at a chosen m²/person standard. `spaceUtilBenchmarks` was
 * frozen in `apps/web/src/api/clientCallers.test.ts` as called by nothing, so a firm could not see
 * its own portfolio's space efficiency at all.
 *
 * ## The engine fix is the finding, and it was in a sentence
 *
 * `benchmarking.space_utilization` opens at most 12 models and the docstring said *"the projects
 * skipped for the cap are counted, never silently dropped"*. True of the cap, true of unreadable
 * files, and **false of the third exclusion**: a model that opens fine and models no `IfcSpace` hit
 * `continue` and appeared in no count at all. It is also the **common** one — a structural or
 * massing model has no spaces — so a portfolio of ten of them answered `projects: 0,
 * skipped_over_cap: 0, unreadable_models: 0`, which reads as *no projects* when the truth is *no
 * project has spaces modelled*. Those have different remedies: add projects, versus model your
 * spaces. *A claim that every exclusion is counted is exactly the kind that stops being true one
 * `continue` later.*
 *
 * So the engine now returns `no_spaces` and `candidates`, and the four counts **reconcile** —
 * `projects + skipped_over_cap + unreadable_models + no_spaces === candidates` — which is a property
 * a consumer can check rather than a promise it has to trust. This module checks it, and says so
 * when it fails, because a coverage line computed from counts that do not add up is worse than none.
 */
export type SpaceBenchmark = Awaited<ReturnType<ApiClient["spaceUtilBenchmarks"]>>;

export interface BenchmarkScope {
  /** `none` — nothing to compare. `no-spaces` — models exist and none carries a space.
   *  `partial` — some projects are excluded. `full` — every candidate is in the comparison. */
  kind: "none" | "no-spaces" | "partial" | "full";
  headline: string;
  detail: string;
  tone: "ok" | "warn" | "";
}

/** The excluded projects, by reason, in the order a reader can act on them. */
export function exclusions(b: SpaceBenchmark): { reason: string; n: number }[] {
  return [
    { reason: "model no spaces (IfcSpace) — the comparison cannot include them", n: b.no_spaces },
    { reason: "could not be read (missing or corrupt IFC)", n: b.unreadable_models },
    { reason: "were past this call's 12-model cap", n: b.skipped_over_cap },
  ].filter((e) => e.n > 0);
}

/** Do the engine's own counts add up? A coverage line over counts that do not is worse than none. */
export function reconciles(b: SpaceBenchmark): boolean {
  return b.projects + b.skipped_over_cap + b.unreadable_models + b.no_spaces === b.candidates;
}

/**
 * The coverage reading, in plain text — the caller escapes it.
 *
 * The `no-spaces` case is separated from `none` on purpose: *no project has spaces modelled* and
 * *you have no projects* look identical in `projects: 0` and call for opposite actions.
 */
export function benchmarkScope(b: SpaceBenchmark): BenchmarkScope {
  const ex = exclusions(b);
  const exText = ex.map((e) => `${e.n} ${e.reason}`).join("; ");
  const bad = !reconciles(b)
    ? " The server's own counts do not add up, so treat this coverage as unverified."
    : "";
  if (!b.candidates) {
    return {
      kind: "none", tone: "",
      headline: "No modelled projects",
      detail: "no project in this portfolio has a source IFC, so there is nothing to compare.",
    };
  }
  if (!b.projects) {
    return {
      kind: "no-spaces", tone: "warn",
      headline: `None of ${b.candidates} modelled project(s) is in the comparison`,
      detail: `${exText || "every one was excluded"}. This is not an empty portfolio — `
        + "it is a portfolio whose models carry no space data." + bad,
    };
  }
  if (ex.length) {
    return {
      kind: "partial", tone: "warn",
      headline: `${b.projects} of ${b.candidates} modelled project(s) compared`,
      detail: `the median and the totals are over those ${b.projects}: ${exText}.` + bad,
    };
  }
  return {
    kind: "full", tone: "ok",
    headline: `All ${b.candidates} modelled project(s) compared`,
    detail: `at ${b.area_per_person} m²/person.` + bad,
  };
}

/** One row per project, with its standing against the portfolio median rather than a bare number. */
export function benchmarkRows(b: SpaceBenchmark): { project: string; area: string; spaces: string;
  perSpace: string; capacity: string; vsMedian: string; top: string }[] {
  const med = b.portfolio.median_m2_per_space;
  return b.rows.map((r) => ({
    project: r.project,
    area: `${r.total_area_m2.toLocaleString()} m²`,
    spaces: String(r.space_count),
    perSpace: `${r.m2_per_space} m²`,
    capacity: String(r.capacity),
    // A median of one project is itself, so "0% vs median" would be a comparison with nothing.
    vsMedian: med == null || b.rows.length < 2
      ? "—"
      : `${r.m2_per_space > med ? "+" : ""}${Math.round(((r.m2_per_space - med) / med) * 100)}%`,
    top: r.top_type ? `${r.top_type}${r.top_type_area_m2 != null ? ` (${r.top_type_area_m2} m²)` : ""}` : "—",
  }));
}

/** The portfolio line — the three figures a reader compares a project against. */
export function portfolioLine(b: SpaceBenchmark): string {
  const p = b.portfolio;
  return `${p.total_area_m2.toLocaleString()} m² over ${b.projects} project(s) · capacity `
    + `${p.total_capacity.toLocaleString()} at ${b.area_per_person} m²/person · median `
    + (p.median_m2_per_space == null ? "—" : `${p.median_m2_per_space} m²`) + " per space"
    + (b.rows.length < 2 ? " (one project, so the median is itself)" : "");
}

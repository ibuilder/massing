/**
 * SCENARIO-SOURCES — which of a deal's assumptions carry a source, and which came from nowhere.
 *
 * `GET /proforma/scenarios/{sid}/provenance` is R22-PROVENANCE ②. It walks the numeric drivers under
 * `timing`/`debt`/`equity`/`operations`/`exit`/`waterfall` and reports, per dotted path, whether a
 * citation is recorded against it. It has had no client caller — its leaf `provenance` was read as
 * reachable by the route gate because `ProformaResult.provenance` is a FIELD of that name on a
 * different reply. A different sense of the same word vouched for it.
 *
 * **The engine's own docstring states the rule this screen has to honour:** *"A coverage figure with
 * no named gaps is the shape that gets quoted in a memo; the named list is the part that gets
 * fixed."* So the percentage is never the deliverable here — `uncited`, `orphaned_sources` and
 * `malformed_citation_paths` are.
 *
 * **THIS IS NOT THE SAME PROVENANCE AS `proforma/provenanceLine.ts`.** That one renders
 * DECLARED-vs-DEFAULTED from `POST /proforma/solve` — did the underwriter supply this number, or did
 * the engine default it. This is CITED-vs-UNCITED — is there a document behind it. A number can be
 * DECLARED and UNCITED, which is the ordinary and dangerous case: somebody typed it and nothing backs
 * it. Conflating the two would tell a reader a deal is sourced when it is merely filled in.
 *
 * Pure rules only — no DOM, no fetch. The panel is `scenarioSourcesPanel.ts`.
 */

/** One assumption path and what is recorded against it. */
export interface AssumptionRow {
  path: string;
  status: "cited" | "uncited";
  status_note: string;
  citation_count: number;
  /** Present only on a cited row: `cited_answer.provenance_confidence`, 0–1. */
  confidence?: number | null;
  /** Present only on a cited row, and **0 whenever no revision was supplied** — see `staleness()`. */
  stale_citations?: number;
  /** Entries recorded against this path that are not readable citations. */
  malformed_citations?: number;
}

/** The response of `GET /proforma/scenarios/{sid}/provenance`. */
export interface ScenarioProvenance {
  scenario_id: string | null;
  scenario_name: string | null;
  material_count: number;
  cited_count: number;
  uncited_count: number;
  coverage_pct: number;
  assumptions: AssumptionRow[];
  /** NAMED, not merely counted — the engine is explicit that this is the actionable half. */
  uncited: string[];
  /** Citations recorded against a path that is not a material assumption: a typo, or a citation left
   *  behind when an assumption was renamed. A citation nobody can reach is indistinguishable from no
   *  citation, and it inflates a naive count of `sources`. */
  orphaned_sources: string[];
  /** Paths whose recorded source is not a citation this contract can read. */
  malformed_citation_paths: string[];
  malformed_citation_count: number;
  stale_citation_count: number;
  /** Echoed back — `null` when the caller supplied no `?revision=`. Load-bearing; see `staleness()`. */
  current_revision: string | null;
  basis: string;
  note: string;
  message: string | null;
}

/**
 * Whether the staleness figure means anything.
 *
 * **`stale_citation_count: 0` is ambiguous and the screen must not print it as a finding.** The
 * engine computes staleness as `[c for c in cites if current_revision and c.revision != current_revision]`
 * — so with no `?revision=` supplied the list is empty and the count is zero **because nothing was
 * checked**, which is indistinguishable from zero because everything is current.
 *
 * The response echoes `current_revision`, which is the only thing that separates them. *A zero that
 * means "not evaluated" printed beside a zero that means "all current" is the same defect as a clamp
 * boundary printed as a measurement* — a number whose provenance the reader cannot see.
 */
export type Staleness = "not-checked" | "all-current" | "some-superseded";

export function staleness(p: ScenarioProvenance): Staleness {
  if (!p.current_revision) return "not-checked";
  return p.stale_citation_count > 0 ? "some-superseded" : "all-current";
}

export function stalenessNote(s: Staleness, p: ScenarioProvenance): string {
  if (s === "not-checked") return "Citation currency was not checked — no revision was supplied to "
    + "compare against, so this says nothing about whether the sources are up to date.";
  if (s === "some-superseded") return `${p.stale_citation_count} citation(s) point at a revision other `
    + `than ${p.current_revision} — the assumption is sourced, but to a superseded document.`;
  return `Every citation points at ${p.current_revision}.`;
}

/**
 * Does the coverage percentage deserve to be read as "this deal is sourced"?
 *
 * **A scenario can report 100% coverage while every citation is stale.** `STATUS_CITED` is assigned
 * whenever any readable citation exists, regardless of the revision it names, so coverage and
 * currency are different axes and the headline carries only one. Reporting the percentage without the
 * other axis is how a memo comes to say "fully sourced" about documents nobody has re-checked.
 */
export function coverageIsWhole(p: ScenarioProvenance): boolean {
  return p.uncited_count === 0 && p.malformed_citation_count === 0 && staleness(p) === "all-current";
}

/** What a reader must be told first, in the order it has to be said. */
export type Headline = "nothing-to-trace" | "gaps" | "unreadable-sources" | "superseded-sources" | "unchecked" | "whole";

/**
 * The single most important thing about this scenario's provenance.
 *
 * Ordered by what a reader can act on. Gaps outrank staleness because a missing source is a bigger
 * hole than an out-of-date one; unreadable sources outrank staleness for the same reason and are
 * separated from gaps because **they are a different action** — "go and find a source" versus "fix
 * the record you already made". The engine separates `uncited` and `malformed_citation_paths`
 * deliberately, and a path can be in both; collapsing them destroys the only actionable distinction.
 */
export function headline(p: ScenarioProvenance): Headline {
  if (!p.material_count) return "nothing-to-trace";
  if (p.uncited_count > 0) return "gaps";
  if (p.malformed_citation_count > 0) return "unreadable-sources";
  const s = staleness(p);
  if (s === "some-superseded") return "superseded-sources";
  if (s === "not-checked") return "unchecked";
  return "whole";
}

export function headlineNote(h: Headline, p: ScenarioProvenance): string {
  switch (h) {
    case "nothing-to-trace":
      return "This scenario carries no material assumptions to trace.";
    case "gaps":
      return `${p.uncited_count} of ${p.material_count} material assumptions have no recorded source. `
        + "That is the absence of provenance, not a finding that the values are wrong.";
    case "unreadable-sources":
      return `${p.malformed_citation_count} recorded source(s) are not readable citations. Somebody `
        + "believes these assumptions are sourced and they are not — a different fix from a missing source.";
    case "superseded-sources":
      return stalenessNote("some-superseded", p);
    case "unchecked":
      return "Every material assumption is sourced. Currency was NOT checked — supply a revision to "
        + "find out whether those sources are still the current ones.";
    case "whole":
      return "Every material assumption is sourced, and every citation names the current revision.";
  }
}

/**
 * Paths a reader should act on, in the order they should act.
 *
 * Uncited first, then recorded-but-unreadable. A path that is BOTH appears once, under the more
 * urgent heading, with `alsoMalformed` set — the engine allows both and the reader needs to know the
 * record is broken as well as absent.
 */
export interface ActionRow { path: string; kind: "uncited" | "malformed" | "orphaned"; alsoMalformed?: boolean }

export function actions(p: ScenarioProvenance): ActionRow[] {
  const malformed = new Set(p.malformed_citation_paths);
  const out: ActionRow[] = p.uncited.map((path) => ({
    path, kind: "uncited" as const, ...(malformed.has(path) ? { alsoMalformed: true } : {}),
  }));
  const uncited = new Set(p.uncited);
  for (const path of p.malformed_citation_paths) {
    if (!uncited.has(path)) out.push({ path, kind: "malformed" });
  }
  // Orphans are last and are about the SOURCES block rather than an assumption: a citation pointing
  // at a path that is not a material assumption. Listed because the caller believes it counts.
  for (const path of p.orphaned_sources) out.push({ path, kind: "orphaned" });
  return out;
}

export function actionNote(kind: ActionRow["kind"]): string {
  if (kind === "uncited") return "no source recorded — find one";
  if (kind === "malformed") return "a source is recorded but is not a readable citation — fix the record";
  return "a citation points at a path that is not a material assumption — a typo, or a renamed assumption";
}

/** The headline figures, with the second axis attached so the percentage cannot travel alone. */
export function summary(p: ScenarioProvenance): {
  coverage: number; cited: number; material: number;
  headline: Headline; staleness: Staleness; whole: boolean; actionCount: number;
} {
  return {
    coverage: p.coverage_pct,
    cited: p.cited_count,
    material: p.material_count,
    headline: headline(p),
    staleness: staleness(p),
    whole: coverageIsWhole(p),
    actionCount: actions(p).length,
  };
}

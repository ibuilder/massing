/**
 * PERMIT-BLIND — the permit pre-check's reading, which is where everything it could not know lives.
 *
 * Three findings, in the order they bite:
 *
 * **① `code_edition` was null on every call this route has ever served.** `permit_check.readiness`
 * read `analysis.get("edition") or analysis.get("code_edition")` and `code_analysis` has neither
 * key — the edition is at `code_context.ibc_edition`. The `or` is what made it look safe: two
 * spellings chained that way read as "try the obvious name, fall back to the other", a shape that
 * implies at least one is right. Fixed on the server; this renders it, with `resolved` beside it,
 * because **IBC 2021 because this state adopted it is a different claim from IBC 2021 as the
 * national baseline** and a permit screen showing the number without the basis invites a reader to
 * cite it.
 *
 * **② the route takes four declarations and nothing ever passed any of them.** The checklist item
 * *"Code-analysis summary complete (occupancy group + construction type declared)"* tests the
 * INPUTS, on purpose — `code_analysis` falls back to an occupancy group read off the model and a
 * construction type of `"II-B (verify with AHJ)"`, and neither is a declaration for permit
 * purposes. So that item was permanently unsatisfied and its deficiency permanently unclearable.
 * *The engine asked a correct question and its only caller gave it no way to answer.*
 *
 * **③ the disclaimer was undeclared and unrendered.** *"Pre-check assist with cited sections — NOT a
 * certified plan review. The authority having jurisdiction rules."* On a screen that prints READY
 * over a building, that sentence is the most important field in the payload.
 *
 * Pure and plain-text: `deficiency.item`, `.action` and `.source` reach an `innerHTML` and the old
 * line interpolated them raw.
 */

export interface PermitReadiness {
  verdict: string;
  readiness_pct: number;
  approvability_score: number;
  checklist: { requirement: string; satisfied: boolean; evidence: string }[];
  deficiencies: { item: string; severity: string; action: string; source?: string }[];
  code_edition?: number | null;
  code_context?: { jurisdiction: string | null; ibc_edition: number | null; resolved: boolean;
                   as_of: number | null; verify: string | null };
  declared?: { occupancy_group: string | null; construction_type: string | null;
               sprinklered: boolean; jurisdiction: string | null };
  sheet_series?: Record<string, number>;
  disclaimer?: string;
}

export type PermitTone = "ok" | "warn" | "unknown";

export const PERMIT_CSS: Record<PermitTone, string> = {
  ok: "var(--status-good)", warn: "var(--status-warn)", unknown: "var(--muted)",
};

/**
 * Which code this was checked against, and on whose authority.
 *
 * `resolved: false` with an edition is the national baseline — a real answer, and not the project's
 * adopted code. An absent `code_context` answers `unknown` rather than being read as unresolved,
 * because "this server did not say" and "nobody has set a jurisdiction" call for different actions.
 */
export function editionNote(r: PermitReadiness): { text: string; tone: PermitTone } {
  const c = r.code_context;
  if (!c) {
    return { text: "This response carries no code context, so which edition the check used is not "
                   + "knowable from it.", tone: "unknown" };
  }
  const ed = c.ibc_edition ?? r.code_edition;
  if (!ed) {
    return { text: "No IBC edition was resolved, so the occupant-load factors and the cited sections "
                   + "are the engine's defaults. Set a jurisdiction to check against the adopted code.",
             tone: "warn" };
  }
  if (!c.resolved) {
    return { text: `Checked against IBC ${ed} as the NATIONAL BASELINE — not this project's adopted `
                   + "code. Set a jurisdiction so the citations name the edition the AHJ enforces.",
             tone: "warn" };
  }
  const asOf = c.as_of ? `, as-of ${c.as_of}` : "";
  return { text: `Checked against IBC ${ed} — ${c.jurisdiction} adoption${asOf}.`
                 + (c.verify ? ` ${c.verify}` : ""),
           tone: "ok" };
}

/**
 * What the check was TOLD, versus what it inferred — the gap item ② exists for.
 *
 * Returns `null` when both declarations are present: there is nothing to warn about, and a line
 * saying "declared" on every healthy run is the reassurance that trains a reader to skip it.
 */
export function declarationGap(r: PermitReadiness): { text: string; missing: string[] } | null {
  const d = r.declared;
  if (!d) return null;                 // older server — `editionNote` already says it is silent
  const missing: string[] = [];
  if (!d.occupancy_group) missing.push("occupancy group");
  if (!d.construction_type) missing.push("construction type");
  if (!missing.length) return null;
  return {
    text: `⚠ ${missing.join(" and ")} not declared — the code analysis inferred ${missing.length > 1
      ? "them" : "it"} from the model, and an inferred classification is not a declaration for `
      + "permit purposes. That is why the checklist row below cannot be satisfied.",
    missing,
  };
}

/** Deficiency rows, with the SOURCE the old line dropped. */
export function deficiencyRows(r: PermitReadiness, cap = 6): {
  severity: string; item: string; action: string; source: string; tone: PermitTone;
}[] {
  return r.deficiencies.slice(0, cap).map((d) => ({
    severity: d.severity,
    item: d.item,
    action: d.action,
    source: d.source ?? "",
    tone: d.severity === "critical" ? "warn" : d.severity === "major" ? "warn" : "unknown",
  }));
}

/** Both numbers where the list stops, or `""` when it is the whole list. */
export function deficiencyPageNote(shown: number, total: number): string {
  return shown < total ? `Showing the ${shown} highest-severity of ${total} deficiencies.` : "";
}

/** Registered sheets per required series, as rows. Empty when the server did not send the counts. */
export function seriesRows(r: PermitReadiness): { series: string; sheets: number }[] {
  return Object.entries(r.sheet_series ?? {}).map(([series, sheets]) => ({ series, sheets }));
}

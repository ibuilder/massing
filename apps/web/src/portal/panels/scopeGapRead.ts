/** SCOPE-THIN — the bid-coverage card had two states and the engine has four.
 *
 *  `services/api/src/aec_api/scope_gap.py` answers *"does every element in the model land in
 *  someone's bid package?"* by matching an element's NCS discipline to a package that CLAIMS that
 *  discipline. It is explicit that this is a baseline — *"conceptual-grade, discipline-level …
 *  spec-section refinement and per-line sheet citation extend it"* — and it publishes a fourth
 *  state for the case the baseline cannot stand on:
 *
 *  > `covered_without_specs` flags disciplines covered by a package that cites no CSI spec section
 *  > (thin, non-traceable coverage).
 *
 *  **The only screen that calls the route read `gaps` and nothing else:**
 *
 *      g.gaps.length ? "⚠️ Scope gaps — … not in any bid package"
 *                    : "✅ Every model discipline is covered by a bid package"
 *
 *  So a job where every discipline is claimed by a package citing **no spec section at all** gets
 *  the green tick, and `covered_pct` reads 100%. `services/api/test_scope_gap.py` already asserts
 *  the engine flags that case (`covered_without_specs == {"Mechanical"}`) — *the engine was proven
 *  right and the screen was the only place the distinction did not reach.*
 *
 *  The same thing happened to the per-discipline `spec_sections`, which the engine attaches to every
 *  covered entry: the ROOT `spec_sections` was in `apps/web/src/api/responseUndeclared.test.ts`'s
 *  gap list and the nested one was invisible to it, which is that gate's root-only blind spot.
 */
import type { ScopeGapResult } from "../../api/procurement";

export type Tone = "good" | "warn" | "crit";

export const TONE_CSS: Record<Tone, string> = {
  good: "var(--status-good)",
  warn: "var(--status-warn)",
  crit: "var(--status-crit)",
};

/** FOUR states. The order is the order of severity, and a gap outranks thin coverage: quantities in
 *  nobody's bid cost more than quantities somebody is pricing without writing down what.
 *
 *  Returns `null` when there is no takeoff to rule on — the caller already skips an empty model, and
 *  a verdict over zero elements would be the vacuous kind this whole family of gates exists to
 *  refuse. */
export function coverageVerdict(g: ScopeGapResult): { text: string; tone: Tone } | null {
  if (g.element_count === 0) return null;
  const thin = g.covered_without_specs ?? [];
  if (g.gaps.length) {
    return {
      tone: "crit",
      text: `${g.gaps.length} discipline(s) are in no bid package: `
        + g.gaps.map((x) => `${x.discipline} (${x.element_count})`).join(" · ")
        + `. Those quantities are in nobody's bid.`
        + (thin.length ? ` A further ${thin.length} are covered by a package citing no spec `
                         + `section.` : ""),
    };
  }
  if (thin.length) {
    // THE STATE THE CARD COULD NOT SHOW. Not a gap — somebody is pricing it — and not coverage
    // anybody can trace either.
    const els = thin.reduce((n, t) => n + t.element_count, 0);
    return {
      tone: "warn",
      text: `Every discipline is claimed by a package — but ${thin.length} of them `
        + `(${els} element(s)) by a package that cites no CSI spec section. That is coverage at the `
        + `discipline level with nothing to trace it to, which is how a scope hole survives buyout.`,
    };
  }
  return {
    tone: "good",
    text: `Every model discipline is covered by a bid package, and every covering package cites at `
      + `least one CSI spec section.`,
  };
}

/** The thin disciplines, named with their packages — because the action is to go and ask that
 *  package which sections it is pricing. */
export function thinRows(g: ScopeGapResult): {
  discipline: string; elements: number; packages: string; guids: string[];
}[] {
  return (g.covered_without_specs ?? []).map((t) => ({
    discipline: t.discipline,
    elements: t.element_count,
    packages: t.packages.join(" · "),
    // GUIDs, so the viewer can highlight them. An IFC GlobalId is the only identity that survives
    // a reload or a re-tessellation — never a transient viewer id.
    guids: t.sample_guids,
  }));
}

/** The project-wide spec-section citation count. `0` is the sharpest single number on this card.
 *
 *  Returns `null` above zero rather than a reassuring count: a card that announces "7 sections
 *  cited" on every render teaches its reader to skip the line, and then the zero reads the same.
 *  (COMPTIER-DARK's always-on qualifier is the instance that cost most to learn.) */
export function specCitationNote(g: ScopeGapResult): string | null {
  const n = g.spec_section_count;
  if (n == null || n > 0) return null;
  return `No bid package on this project cites a CSI spec section. Coverage above is therefore `
    + `discipline-level throughout — every "covered" discipline is a claim with nothing behind it.`;
}

/** `covered_pct` with the qualification it needs.
 *
 *  The figure is right and it means less than it looks: it is the share of elements whose discipline
 *  a package claims, so 100% is compatible with no spec section anywhere. Stated beside it rather
 *  than left for the reader to infer from a note three lines down. */
export function coveredLine(g: ScopeGapResult): string {
  const thin = g.covered_without_specs ?? [];
  return `${g.covered_pct}% of ${g.element_count} element(s) are in a package by discipline`
    + (g.gap_element_count ? ` · ${g.gap_element_count} in none` : "")
    + (thin.length ? ` · ${thin.length} discipline(s) traceable to no spec section` : "");
}

/** Every covered discipline with the sections its packages cite — the refinement the engine
 *  computes and nothing displayed. An empty list renders as a warning rather than a blank.
 *
 *  Deliberately UNCAPPED, and that is a measurement rather than an oversight: the discipline axis is
 *  `classification.DISCIPLINES`, **eleven** NCS designators by construction, so `covered`, `gaps`
 *  and `covered_without_specs` can never exceed eleven rows between them. The `sample_guids` inside
 *  each one ARE capped — `scope_gap._MAX_SAMPLE = 20` — which is why this file says so about the
 *  GUIDs and says nothing about the rows. *A truncation note on a list that cannot be truncated
 *  teaches the reader to discount the ones that can.* */
export function coveredRows(g: ScopeGapResult): {
  discipline: string; elements: number; packages: string; sections: string; tone: Tone;
}[] {
  return g.covered.map((c) => {
    const sections = c.spec_sections ?? [];
    return {
      discipline: c.discipline,
      elements: c.element_count,
      packages: c.packages.join(" · "),
      sections: sections.length ? sections.join(", ") : "no section cited",
      tone: sections.length ? "good" : "warn",
    };
  });
}

/** Packages claiming a discipline the model does not carry. Over-scoped, nothing to price — and the
 *  mirror image of a gap, so it belongs beside one. */
export function overScopedNote(g: ScopeGapResult): string | null {
  const over = g.packages_without_model_scope;
  if (over.length === 0) return null;
  return `${over.length} package(s) claim a discipline the model has no elements for: `
    + `${over.join(" · ")}. Either the scope is real and the model is behind it, or the package is `
    + `pricing nothing.`;
}

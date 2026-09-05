import { HttpCore } from "./httpCore";
import type { SpineTraceability } from "./types";

/**
 * Coverage maps — **how completely is this project's chain of records linked, and exactly what is
 * missing.**
 *
 * SCALE-SEAM (104), and it is the affirmative half of a boundary (103) drew by exclusion.
 * `acceptanceGates.ts` groups the four methods that collapse the project to one accept/refuse
 * verdict. `spineTraceability` was named there as the closest miss and deliberately left behind,
 * because it *maps completeness for a human* rather than deciding anything. This is that shape,
 * given its home:
 *
 *   | method | what it counts complete | the gaps it names |
 *   |---|---|---|
 *   | `spineTraceability` | `specs_packaged_pct`, `packages_costed_pct`, `sheets_specced_pct`, `spec_to_budget_pct` | `specs_without_bid_package[]`, `bid_packages_without_cost_code[]`, `sheets_without_spec[]` |
 *   | `scopeRegister` | `pct_quantified`, `pct_allocated`, `pct_scheduled` | `gap_items[]`, and per item `gaps: string[]` with `status: "complete" \| "gap"` |
 *
 * Both answer one question — *what proportion of these records carry the link they need, and which
 * specific ones do not* — and a caller does the same thing with either: render a worklist of records
 * to go and connect. **Neither returns a verdict field**, which is exactly what separates them from
 * the acceptance gates, and it is the same test, run for inclusion this time rather than exclusion.
 *
 * ## Deriving the population needed named types resolved, and that is the lesson here
 *
 * A scan of method BODIES for coverage vocabulary (`gaps`, `coverage`, `pct_*`) returned
 * `scopeRegister`, `citedQuery` and `progressActuals` — and **missed `spineTraceability`, the
 * strongest member**, because its return is the named type `SpineTraceability` and its body
 * therefore contains none of those words. Resolving the named return types out of `types.ts` is what
 * found it.
 *
 * That is the mirror of the mistake (103) recorded. There, a body scan **over**-counted, matching the
 * doc comment of the *next* method and reporting `collabSnapshot` as verdict-shaped. Here the same
 * kind of scan **under**-counted, because a type alias hides the shape it names. *A textual scan of a
 * typed language reads neither the comments nor the types correctly — it is a way of finding
 * candidates, never a way of counting them.*
 *
 * ## What did NOT come
 *
 * **`citedQuery` stayed**, and it genuinely carries `coverage`, `uncited_claims` and `fully_cited`.
 * Its principal product is an `answer` with `claims` and `conflicts`; the coverage fields annotate
 * how well that answer is sourced. The caller renders a cited answer, not a worklist of records to
 * link, so the shape matches while the question does not.
 *
 * **`masterBuilderBrief` stayed, and it is the closest call in this slice** — closer than
 * `spineTraceability` was to the gates. It carries `readiness_pct`, `ready_steps`, `gap_steps` and a
 * `steps[]` list, so it does count completeness and does enumerate gaps. It stays because its
 * product is a *brief*: a narrative with a `reframe_prompt`, a `disclaimer` and guided steps to read,
 * where the percentages are a header on a document rather than the document. Recorded rather than
 * asserted, because a later reader may reasonably decide the other way.
 *
 * **`progressActuals` stayed.** Its `pct_complete` is physical progress of installed work against a
 * planned quantity, banded `ahead`/`on_track`/`behind`. That is variance against a plan over time,
 * not completeness of linkage between records — a different axis that happens to be spelled with a
 * percent sign.
 */
type Ctor<T> = new (...args: any[]) => T;

export function withCoverageMaps<TBase extends Ctor<HttpCore>>(Base: TBase) {
  return class CoverageMaps extends Base {
    /** Discipline Spine traceability: discipline → sheets → specs → bid packages → cost codes → budget. */
    spineTraceability(pid: string) {
      return this.json<SpineTraceability>(`/projects/${pid}/spine/traceability`);
    }

    /**
     * Scope register: every scope item checked for a quantity, an owner and a schedule slot, with
     * the ones missing any of the three named individually in `gap_items`.
     */
    scopeRegister(pid: string, body: {
      scope_items: Record<string, unknown>[]; qto_lines?: Record<string, unknown>[]; activities?: Record<string, unknown>[];
    }) {
      type Item = {
        id: string | null; name: string; cost_code: string | null; qty: number | null; value: number | null;
        responsible: string | null; package: string | null; start: string | null; finish: string | null;
        quantified: boolean; allocated: boolean; scheduled: boolean; gaps: string[]; status: "complete" | "gap";
      };
      return this.json<{
        item_count: number; complete: number; with_gaps: number; pct_quantified: number; pct_allocated: number;
        pct_scheduled: number; total_value: number; by_owner: { owner: string; value: number }[];
        gap_items: Item[]; items: Item[]; note: string;
      }>(`/projects/${pid}/scope/register`, { method: "POST", body: JSON.stringify(body) });
    }
  };
}

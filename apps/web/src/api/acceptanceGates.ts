import { HttpCore } from "./httpCore";
import type { DiligenceReadiness } from "./types";

/**
 * Acceptance gates — **will an outside party accept this project, and what is blocking it.**
 *
 * SCALE-SEAM (103). Four gates, four different outside parties, one question shape: a single
 * whole-project verdict plus the itemised list of what is standing in its way.
 *
 *   | method | who is deciding | the verdict field | what blocks it |
 *   |---|---|---|---|
 *   | `permitReadiness` | the AHJ | `verdict` | `checklist[].satisfied` + ranked `deficiencies[]` |
 *   | `diligenceReadiness` | an investor / acquirer | `go` | `high_risk[]` + `flagged` per category |
 *   | `handoverAcceptance` | the owner at turnover | `accepted` | `checks[].ok` |
 *   | `validate` | the IDS checker | `status: "pass" \| "fail"` | `specifications[].failed_guids` |
 *
 * ## The witness is that NEITHER the route nor the audience produces this grouping
 *
 * The four routes are `/permit/readiness`, `/diligence/readiness`, `/handover/acceptance` and
 * `/validate` — **four different prefixes**, so a prefix grouping takes one each and this set never
 * forms. The shared leaf word "readiness" reaches only two of the four, so that does not form it
 * either. And the deciding parties are an authority, an investor, an owner and a schema checker —
 * **four different audiences**, so grouping by who reads it fails as well.
 *
 * What does form it is the *shape of the return*: every one of them collapses the whole project to
 * a single accept/refuse verdict and then enumerates what is withholding it. That is a question a
 * caller acts on identically in all four cases — block, or proceed — and the remedy is always to
 * change the project and ask again.
 *
 * This is the second slice to be carried by return shape rather than by name, after (102), where
 * the prefix actively *disagreed* with the seam. Here the prefix does not disagree so much as say
 * nothing at all, which is the weaker but more common case: **four names that share no vocabulary
 * can still be one question.** (85) rejected "they are all multipart uploads", (89) "they are all
 * module records", and `annotate.ts` "they all call `editIfc`" — those are shared mechanisms
 * masquerading as questions. This is the inverse error to avoid: an unshared vocabulary
 * masquerading as unshared subject matter.
 *
 * ## What did NOT come, and why — the exclusions are the load-bearing part
 *
 * **`spineTraceability` stayed**, and it is the closest miss: same domain, same "is this project
 * complete" register, adjacent in the file, and its route `/spine/traceability` is as
 * project-scoped as the four above. It returns `coverage` percentages, `gaps` and a `chain` —
 * and **no verdict field of any kind**. Nothing in it says pass or fail, because it is not a gate:
 * it maps how completely one artefact links to another so a human can decide what to do. A
 * completeness map and an acceptance decision are different questions even when they cover
 * identical ground, and only reading the returns tells them apart.
 *
 * **`editPrecheck` stayed**, and this one is subtler because it genuinely returns a verdict —
 * `{ok, errors, warnings}`. Its SUBJECT is different: it judges a **pending action** ("may I run
 * this recipe with these params"), asked before acting, remedied by changing the parameters you
 * are about to submit, and consumed by enabling or disabling an Apply button. The four above judge
 * a **delivered state**, remedied by changing the project. It also sits beside `addCurtainWall` as
 * the precheck for `editIfc`, so moving it here would separate it from the thing it prechecks.
 * *A verdict about what you are about to do is not a verdict about what you have built.*
 *
 * **`collabSnapshot` was a false positive and is worth recording.** A scan for verdict-shaped
 * returns flagged it, but the match came from the doc comment introducing `permitReadiness` — the
 * next method — not from its own body, which has no verdict at all. A method-body splitter that
 * runs to the next header swallows the comment belonging to that header, so a population derived
 * that way silently inherits its neighbour's vocabulary. The count looked entirely reasonable at
 * six; only reading each candidate caught it. **Derive the complement, then read it — a plausible
 * count is not a checked one.**
 *
 * ## `handoverAcceptance` had been left explicitly unfiled
 *
 * A previous slice parked it under an "UNFILED" note in `client.ts` saying it "needs its home
 * decided by what it ANSWERS rather than by what it sits next to". This slice is that decision.
 * The note is narrowed rather than deleted, because the other two it names are still unfiled.
 */
// The mixin shape TS requires — same declaration as every other `with*` module in this directory.
type Ctor<T> = new (...args: any[]) => T;

export function withAcceptanceGates<TBase extends Ctor<HttpCore>>(Base: TBase) {
  return class AcceptanceGates extends Base {
    /** PERMIT-CHECK: submission-readiness — checklist + ranked deficiencies + verdict (409 without a model). */
    permitReadiness(pid: string) {
      return this.json<{
        verdict: string; readiness_pct: number; approvability_score: number;
        checklist: { requirement: string; satisfied: boolean; evidence: string }[];
        deficiencies: { item: string; severity: string; action: string }[];
      }>(`/projects/${pid}/permit/readiness`);
    }

    /** Investor/acquirer gate: `go` plus the diligence items and entitlements holding it back. */
    diligenceReadiness(pid: string) {
      return this.json<DiligenceReadiness>(`/projects/${pid}/diligence/readiness`);
    }

    /** Owner turnover gate: `accepted` plus the per-check breakdown of what is not ready. */
    handoverAcceptance(pid: string) {
      return this.json<{ accepted: boolean; checks: { key: string; label: string; ok: boolean }[];
        metrics: Record<string, number>; note: string }>(`/projects/${pid}/handover/acceptance`);
    }

    /**
     * IDS gate: `status` plus, per specification, the GUIDs that failed it.
     *
     * Uses bare `fetch` rather than `this.json` — kept exactly as it was, because changing the
     * transport of a method while moving it makes a behavioural change look like an extraction.
     */
    validate(pid: string) {
      return fetch(this.url(`/projects/${pid}/validate`), { method: "POST" })
        .then((r) => r.json() as Promise<ValidationResult>);
    }
  };
}

/**
 * The IDS validation report. Defined here rather than in `types.ts` because `validate` is its only
 * consumer in the tree — it moved out of `client.ts` with the method that returns it, so nothing is
 * left behind pointing at a method that is no longer there.
 */
export interface ValidationResult {
  title: string;
  status: "pass" | "fail";
  summary: { specifications: number; passed: number; failed: number };
  specifications: { name: string; status: "pass" | "fail"; applicable: number; passed: number; failed: number; failed_guids: string[] }[];
}

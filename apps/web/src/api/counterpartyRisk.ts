import { HttpCore } from "./httpCore";
import type { PrequalScores } from "./types";

/**
 * Counterparty risk — **which trade partner on this job is a risk, and why.**
 *
 * SCALE-SEAM (102). Three angles on one question, each returning per-counterparty rows carrying a
 * verdict about that counterparty:
 *
 *   | method | rows | the verdict it carries |
 *   |---|---|---|
 *   | `prequalScores` | `subs[]` `{company, trade, …}` | `score`, `risk_band`, `flags` — fit to be here at all |
 *   | `coiExpiry` | `expired[]` / `expiring_soon[]` `{vendor, …}` | `days` to expiry — is their cover still valid |
 *   | `lienExposure` | `vendors[]` `{vendor, …}` | `exposure`, `status`, `vendors_at_risk` — money that can become a lien |
 *
 * ## The witness is that the seam DISAGREES with the route prefix
 *
 * `prequalScores` and `coiExpiry` sit under `/prequal/`; `lienExposure` sits under
 * `/payapp/lien-exposure`. **Grouping by prefix would split this set** — which is the affirmative
 * form of the rule the earlier slices had to learn negatively: (85) rejected "they are all
 * multipart uploads", (89) rejected "they are all module records", and `annotate.ts` rejected "they
 * all call `editIfc`" after measuring 24 recipes across nine categories. A shared prefix is a
 * mechanism. Here the prefix actively argues against the grouping and the *shape of the returns*
 * argues for it, so the evidence is not something a name could have produced.
 *
 * The three answer the question a GC asks before and during a job, from the three places it can go
 * wrong: **are they qualified, are they insured, and do we owe them enough to be liened.**
 *
 * ## What did NOT come, and it sits immediately above them
 *
 * `benchmarkResponseRates` is the previous method in `client.ts` and stayed. It returns RFI and
 * submittal turnaround — `avg_turnaround_days`, `overdue_pct` — and **names no counterparty at
 * all**: it measures how responsive the *process* is, not who is a risk. Adjacency is not a
 * relationship; REL-4 recorded three separate times this cycle that it looked like one.
 */
type Ctor<T> = new (...args: any[]) => T;

export function withCounterpartyRisk<TBase extends Ctor<HttpCore>>(Base: TBase) {
  return class CounterpartyRisk extends Base {
  /** Prequalification scores per sub — 0–100 with the factors behind it, a risk band and flags. */
  prequalScores(pid: string, projectSize?: number) {
    const qs = projectSize ? `?project_size=${projectSize}` : "";
    return this.json<PrequalScores>(`/projects/${pid}/prequal/scores${qs}`);
  }
  /** Certificates of insurance already expired, and those inside `soonDays`, per vendor. */
  coiExpiry(pid: string, soonDays = 30) {
    return this.json<{ expired: { vendor?: string; coverage_type?: string; expires: string; days: number }[];
      expiring_soon: { vendor?: string; coverage_type?: string; expires: string; days: number }[];
      expired_count: number; expiring_count: number }>(`/projects/${pid}/prequal/coi-expiry?soon_days=${soonDays}`);
  }
  /** Lien exposure per vendor — billed vs paid vs retainage against the waivers actually on file. */
  lienExposure(pid: string) {
    return this.json<{ vendors: { vendor: string; billed: number; paid: number; retainage: number;
      waived_unconditional: number; waived_conditional: number; exposure: number; status: string }[];
      total_lien_exposure: number; vendors_at_risk: string[]; message?: string | null }>(
      `/projects/${pid}/payapp/lien-exposure`);
  }
  };
}

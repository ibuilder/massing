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

/** WAIVER-FLAT — one certificate of insurance that is expired or inside the horizon.
 *
 *  `carrier` and `ref` were sent and undeclared. They are NESTED, so
 *  `apps/web/src/api/responseUndeclared.test.ts` compares a route's top-level keys and could not
 *  see them — and `carrier` is who you telephone, which makes it the actionable field on the row. */
export interface CoiRow {
  vendor?: string;
  coverage_type?: string;
  carrier?: string;
  ref?: string;
  expires: string;
  /** Days from today to expiry. NEGATIVE for an already-expired certificate. */
  days: number;
}

/** WAIVER-FLAT — `GET /projects/{pid}/prequal/coi-expiry`. */
export interface CoiExpiry {
  expired: CoiRow[];
  expiring_soon: CoiRow[];
  expired_count: number;
  expiring_count: number;
  /** The horizon `expiring_soon` was computed against, echoed back. The card hard-coded "≤30d"
   *  beside this — correct only because the one caller passes the default. */
  soon_days: number;
}

/** WAIVER-FLAT — one vendor's billed/paid position against the lien waivers actually on file.
 *
 *  `status` is the engine's verdict on SECURITY and is the field the exposure card never read, so
 *  a vendor holding a conditional release rendered identically to one holding nothing. It is a
 *  closed set — `payapp.reconcile` produces exactly these three and
 *  `services/api/test_payapp.py` asserts all three are reachable in one response — so it is typed
 *  as a union rather than `string`, which is what lets a consumer be checked for exhaustiveness. */
export interface LienVendor {
  vendor: string;
  /** Approved or paid. Not the exposure basis — a lien attaches to what has been RELEASED or not. */
  billed: number;
  paid: number;
  retainage: number;
  waived_unconditional: number;
  /** A release that takes effect only once the payment clears. Declared, and read by nothing until
   *  WAIVER-FLAT: it is the entire difference between "chase a signature" and "unsecured". */
  waived_conditional: number;
  /** `max(0, paid - waived_unconditional)`, computed on exact Decimals before the float cast. */
  exposure: number;
  status: "clear" | "conditional_only" | "no_waiver";
  /** Nested, so invisible to the response-key gate. The counts behind the money. */
  paid_invoices: number;
  waivers: number;
}

/** WAIVER-FLAT — `GET /projects/{pid}/payapp/lien-exposure`. */
export interface LienExposure {
  vendors: LienVendor[];
  /** Every vendor on the register. The card filtered to `exposure > 0` and printed no population,
   *  so "at risk: B, C" stood over an unstated denominator. */
  vendor_count: number;
  total_lien_exposure: number;
  /** Derived from the per-vendor STATUS, not a second float comparison — so it includes the
   *  `conditional_only` vendors, which is why the distinction has to reach the screen. */
  vendors_at_risk: string[];
  /** The engine's own instruction when there is exposure. `null` when there is none. */
  message?: string | null;
}


export function withCounterpartyRisk<TBase extends Ctor<HttpCore>>(Base: TBase) {
  return class CounterpartyRisk extends Base {
  /** Prequalification scores per sub — 0–100 with the factors behind it, a risk band and flags. */
  prequalScores(pid: string, projectSize?: number) {
    const qs = projectSize ? `?project_size=${projectSize}` : "";
    return this.json<PrequalScores>(`/projects/${pid}/prequal/scores${qs}`);
  }
  /** Certificates of insurance already expired, and those inside `soonDays`, per vendor. */
  coiExpiry(pid: string, soonDays = 30) {
    return this.json<CoiExpiry>(`/projects/${pid}/prequal/coi-expiry?soon_days=${soonDays}`);
  }
  /** Lien exposure per vendor — billed vs paid vs retainage against the waivers actually on file. */
  lienExposure(pid: string) {
    return this.json<LienExposure>(`/projects/${pid}/payapp/lien-exposure`);
  }
  };
}

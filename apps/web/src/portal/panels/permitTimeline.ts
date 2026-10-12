import type { ApiClient } from "../../api/client";

/**
 * PERMIT-BASIS-DARK — the entitlement-duration estimate, and the field that says which permits it is
 * actually about.
 *
 * `/projects/{pid}/permits/timeline` computes days-to-issue (issued − filed) over the project's
 * cached permit records: p25 / median / p75 by jurisdiction × type × valuation band, a seasonal
 * profile, and — with a `target` — the pro-forma estimate, *"median = expected entitlement duration;
 * p75 = the conservative carry the pro-forma should underwrite"*. `permitsTimeline` was frozen in
 * `apps/web/src/api/clientCallers.test.ts` as called by nothing.
 *
 * ## The estimate BROADENS its cohort until the sample is stable, and says so in one field
 *
 * `permit_timeline.estimate` walks four cohorts — `jurisdiction × type × band` → `jurisdiction ×
 * type` → `jurisdiction` → **`all permits`** — and stops at the first with at least `_MIN_SAMPLE`
 * (5) observations. **The last one fires regardless of sample size.** So a target in one
 * jurisdiction for one permit type can come back with `basis: "all permits"` and an `expected_days`
 * computed from every permit in the cache, in any jurisdiction, of any type.
 *
 * **A consumer that prints `expected_days` without `basis` therefore reports a cross-jurisdiction
 * median as this jurisdiction's entitlement duration — into the carry line of a pro forma.** The
 * engine is scrupulous: it names the cohort, returns `sample_size`, and explains the broadening in
 * its own note. Everything needed to be honest is in the response and nothing read it.
 *
 * That is why `basis` is rendered as a *demotion*, not a footnote: the reading states what the
 * number is about **before** it states the number, whenever the cohort is not the one that was
 * asked for.
 *
 * ## And the distribution is over the permits that could be measured
 *
 * `measured` is the count with both dates; `permit_count` is every cached record. A median over 3 of
 * 40 is not this jurisdiction's typical duration either, and the two numbers sit side by side in the
 * response for exactly that reason.
 */
export type PermitTimeline = Awaited<ReturnType<ApiClient["permitsTimeline"]>>;

/** The cohort the engine settled on, in the caller's terms. `_MIN_SAMPLE` in the engine is 5. */
export const MIN_SAMPLE = 5;

export interface EstimateReading {
  /** `none` — no estimate (no target, or no data). `off-target` — the cohort broadened past what was
   *  asked for. `thin` — the right cohort, too few observations. `sound` — asked-for cohort, enough
   *  observations. */
  kind: "none" | "off-target" | "thin" | "sound";
  headline: string;
  detail: string;
  tone: "ok" | "warn" | "bad" | "";
}

/**
 * What the estimate is ABOUT, read before what it says.
 *
 * `asked` is the cohort the caller targeted, used only to decide whether the engine's `basis` is the
 * same question. Plain text; the panel escapes it.
 */
export function estimateReading(t: PermitTimeline, asked: { jurisdiction?: string; type?: string }):
  EstimateReading {
  const e = t.estimate;
  if (!e || e.expected_days == null) {
    return {
      kind: "none", tone: "",
      headline: "No entitlement estimate",
      detail: e?.basis === "no data"
        ? "no permit record carries both a filed and an issued date, so there is no duration to "
          + "measure. The estimate is absent rather than zero."
        : "no target jurisdiction and type were given, so the distribution above is reported "
          + "without a pro-forma estimate.",
    };
  }
  const months = e.expected_months == null ? "" : ` (${e.expected_months} months)`;
  const carry = e.conservative_days == null
    ? ""
    : ` · conservative ${e.conservative_days} days`
      + (e.conservative_months == null ? "" : ` (${e.conservative_months} months)`);
  const figure = `${e.expected_days} days${months}${carry}`;
  // The cohort the engine actually used, against the one that was asked for. `all permits` is the
  // unconditional fallback and is never the asked-for question when a target was given.
  const targeted = Boolean(asked.jurisdiction || asked.type);
  const broadened = targeted && (e.basis === "all permits"
    || (Boolean(asked.type) && !e.basis.includes("type")));
  if (broadened) {
    return {
      kind: "off-target", tone: "bad",
      headline: `NOT ${[asked.jurisdiction, asked.type].filter(Boolean).join(" ")}'s number`,
      detail: `the cohort broadened to "${e.basis}" (${e.sample_size} permit(s)) because the `
        + `targeted one had fewer than ${MIN_SAMPLE} observations, so ${figure} is a median over a `
        + "different population. Do not carry it as this jurisdiction's entitlement duration.",
    };
  }
  if (e.sample_size < MIN_SAMPLE) {
    return {
      kind: "thin", tone: "warn",
      headline: `${figure} — on ${e.sample_size} permit(s)`,
      detail: `the cohort is "${e.basis}", which is the question asked, but ${e.sample_size} `
        + `observation(s) is under the ${MIN_SAMPLE} the engine treats as stable. A median of that `
        + "few is a sample, not a rate.",
    };
  }
  return {
    kind: "sound", tone: "ok",
    headline: figure,
    detail: `over ${e.sample_size} permit(s) in the "${e.basis}" cohort. Median is the expected `
      + "entitlement duration; p75 is the carry a pro forma should underwrite.",
  };
}

/** How much of the cached permit record could be measured at all. `null` when nothing is cached. */
export function coverageLine(t: PermitTimeline): string | null {
  if (!t.permit_count) return null;
  if (t.measured === t.permit_count) {
    return `All ${t.permit_count} cached permit(s) carry both a filed and an issued date.`;
  }
  return `${t.measured} of ${t.permit_count} cached permit(s) carry both a filed and an issued date `
    + `— the distribution is over those ${t.measured}, and the other `
    + `${t.permit_count - t.measured} are in no percentile above.`;
}

/** The busiest cohorts, largest sample first — the engine already sorts by `n`. */
export function groupRows(t: PermitTimeline, limit = 8): { k: string; v: string }[] {
  return t.groups.slice(0, limit).map((g) => ({
    k: `${g.jurisdiction} · ${g.type} · ${g.band}`,
    v: `n=${g.n} · median ${g.median ?? "—"} d · p25 ${g.p25 ?? "—"} · p75 ${g.p75 ?? "—"}`
      + (g.n < MIN_SAMPLE ? " — thin" : ""),
  }));
}

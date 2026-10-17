import { readFileSync } from "node:fs";
import { describe, expect, it } from "vitest";

import type { PermitTimeline } from "./permitTimeline";
import { MIN_SAMPLE, coverageLine, estimateReading, groupRows } from "./permitTimeline";

/**
 * PERMIT-BASIS-DARK — the entitlement-duration estimate, and the field that says which permits it is
 * actually about.
 *
 * `permitsTimeline` was frozen as callerless. `permit_timeline.estimate` walks four cohorts —
 * `jurisdiction × type × band` → `jurisdiction × type` → `jurisdiction` → **`all permits`** — and
 * stops at the first with at least five observations. **The last fires regardless of sample size.**
 * So a target in one jurisdiction for one permit type can come back with `basis: "all permits"` and
 * an `expected_days` computed from every cached permit, anywhere, of any type.
 *
 * A consumer printing `expected_days` without `basis` therefore reports a cross-jurisdiction median
 * as this jurisdiction's entitlement duration — **into the carry line of a pro forma**, since the
 * engine's own note says the median *"= expected entitlement duration; p75 = the conservative carry
 * the pro-forma should underwrite"*. Everything needed to be honest is in the response; nothing read
 * it. That is why `basis` is a demotion rather than a footnote: the reading says what the number is
 * ABOUT before it says the number.
 */

const dist = (n: number, median: number | null) =>
  ({ n, p25: median, median, p75: median == null ? null : median + 30, min: median, max: median,
     mean: median });

function tl(over: Partial<PermitTimeline> = {}): PermitTimeline {
  return {
    permit_count: 40, measured: 40, overall: dist(40, 120), groups: [], seasonal: [],
    note: "Days-to-issue = issued − filed, over the cached permit records (no live fetch).",
    ...over,
  };
}

const est = (over: Partial<NonNullable<PermitTimeline["estimate"]>> = {}) => ({
  expected_days: 120, conservative_days: 180, expected_months: 3.9, conservative_months: 5.9,
  sample_size: 12, basis: "jurisdiction × type", note: "Median = expected entitlement duration",
  ...over,
});

describe("estimateReading — what the number is ABOUT, before the number", () => {
  it("is the SHARP CASE: the cohort broadened to `all permits`", () => {
    const t = tl({ estimate: est({ basis: "all permits", sample_size: 40 }) });
    const r = estimateReading(t, { jurisdiction: "Austin", type: "multifamily" });
    expect(r.kind).toBe("off-target");
    expect(r.tone).toBe("bad");
    expect(r.headline).toBe("NOT Austin multifamily's number");
    expect(r.detail).toContain('broadened to "all permits"');
    expect(r.detail).toContain("a median over a different population");
    expect(r.detail).toContain("Do not carry it");
    // the figure is still reported — the reading demotes it, it does not hide it
    expect(r.detail).toContain("120 days");
  });

  it("also catches the quieter broadening: the TYPE fell out of the cohort", () => {
    // `jurisdiction` alone is the third cohort. It is Austin's number and not multifamily's, which a
    // reader comparing permit types would take at face value.
    const t = tl({ estimate: est({ basis: "jurisdiction", sample_size: 22 }) });
    const r = estimateReading(t, { jurisdiction: "Austin", type: "multifamily" });
    expect(r.kind).toBe("off-target");
    expect(r.detail).toContain('broadened to "jurisdiction"');
  });

  it("does NOT cry broadening when nothing was targeted", () => {
    // With no target the engine still reports a cohort, and "all permits" is then the right answer
    // to the question actually asked rather than a substitution.
    const r = estimateReading(tl({ estimate: est({ basis: "all permits", sample_size: 40 }) }), {});
    expect(r.kind).toBe("sound");
    expect(r.tone).toBe("ok");
  });

  it("warns when the cohort IS the one asked for but the sample is thin", () => {
    const t = tl({ estimate: est({ basis: "jurisdiction × type", sample_size: 3 }) });
    const r = estimateReading(t, { jurisdiction: "Austin", type: "multifamily" });
    expect(r.kind).toBe("thin");
    expect(r.tone).toBe("warn");
    expect(r.detail).toContain("3 observation(s) is under the 5");
    expect(r.detail).toContain("a sample, not a rate");
  });

  it("is `ok` only for the asked-for cohort with a stable sample", () => {
    const r = estimateReading(tl({ estimate: est() }), { jurisdiction: "Austin", type: "multifamily" });
    expect(r.kind).toBe("sound");
    expect(r.headline).toBe("120 days (3.9 months) · conservative 180 days (5.9 months)");
    expect(r.detail).toContain('12 permit(s) in the "jurisdiction × type" cohort');
    expect(r.detail).toContain("p75 is the carry");
  });

  it("no data is ABSENT, not zero", () => {
    const r = estimateReading(tl({ estimate: { expected_days: null, sample_size: 0, basis: "no data" } }),
                              { jurisdiction: "Austin" });
    expect(r.kind).toBe("none");
    expect(r.tone).toBe("");
    expect(r.detail).toContain("absent rather than zero");
  });

  it("no estimate at all says why, rather than implying a missing figure", () => {
    const r = estimateReading(tl(), {});
    expect(r.kind).toBe("none");
    expect(r.detail).toContain("no target jurisdiction and type were given");
  });

  it("carries no markup — the panel escapes it", () => {
    for (const t of [tl({ estimate: est() }), tl(), tl({ estimate: est({ basis: "all permits" }) })]) {
      const r = estimateReading(t, { jurisdiction: "A", type: "B" });
      expect(`${r.headline}${r.detail}`).not.toMatch(/[<>]/);
    }
  });
});

describe("coverageLine — the distribution is over what could be measured", () => {
  it("names the permits with no pair of dates", () => {
    expect(coverageLine(tl({ permit_count: 40, measured: 3 })))
      .toBe("3 of 40 cached permit(s) carry both a filed and an issued date — the distribution is "
        + "over those 3, and the other 37 are in no percentile above.");
  });

  it("says so plainly when every permit is measured", () => {
    expect(coverageLine(tl({ permit_count: 9, measured: 9 }))).toContain("All 9 cached permit(s)");
  });

  it("is null when nothing is cached — there is no coverage to report", () => {
    expect(coverageLine(tl({ permit_count: 0, measured: 0 }))).toBeNull();
  });
});

describe("groupRows", () => {
  it("marks a thin cohort rather than presenting its median as a rate", () => {
    const t = tl({ groups: [
      { jurisdiction: "Austin", type: "multifamily", band: "$1M–10M", ...dist(12, 100) },
      { jurisdiction: "Austin", type: "retail", band: "<$100k", ...dist(2, 60) }] });
    const rows = groupRows(t);
    expect(rows[0]!.k).toBe("Austin · multifamily · $1M–10M");
    expect(rows[0]!.v).toContain("n=12 · median 100 d");
    expect(rows[0]!.v).not.toContain("thin");
    expect(rows[1]!.v).toContain("— thin");
  });

  it("caps the list", () => {
    const many = Array.from({ length: 20 }, (_, i) =>
      ({ jurisdiction: `J${i}`, type: "t", band: "b", ...dist(9, 50) }));
    expect(groupRows(tl({ groups: many }))).toHaveLength(8);
  });
});

/** **The engine side**, read rather than assumed: the broadening and its threshold live in Python. */
describe("the engine this reading is about", () => {
  const SRC = readFileSync("../../services/api/src/aec_api/permit_timeline.py", "utf8");

  it("broadens to `all permits` unconditionally — the reason for the whole module", () => {
    expect(SRC).toContain('("all permits", lambda r: True)');
    expect(SRC).toContain('if len(days) >= _MIN_SAMPLE or basis == "all permits":');
  });

  it("uses the threshold this reading quotes", () => {
    expect(SRC).toMatch(/_MIN_SAMPLE = 5\b/);
    expect(MIN_SAMPLE).toBe(5);
  });

  it("still returns the cohort it settled on, and the sample size", () => {
    expect(SRC).toContain('"sample_size": s["n"], "basis": basis,');
  });

  it("still reports `measured` beside `permit_count`", () => {
    expect(SRC).toContain('"permit_count": len(permits or []), "measured": len(rows),');
  });

  it("still says the median feeds a pro forma — which is why the basis matters", () => {
    expect(SRC).toContain("the conservative carry the ");
  });
});

/** The render, pinned at the source. */
describe("the reading reaches the Analytics panel", () => {
  const AN = readFileSync("src/portal/panels/analytics.ts", "utf8");

  it("calls the route and renders the reading", () => {
    expect(AN).toContain("api.permitsTimeline(pid, {})");
    expect(AN).toContain("const r = estimateReading(t, asked)");
    expect(AN).toContain("esc(r.headline)");
    expect(AN).toContain("esc(r.detail)");
    expect(AN).toContain("const cov = coverageLine(t)");
  });

  it("renders the cohort rows and the engine's own note", () => {
    expect(AN).toContain("const rows = groupRows(t)");
    expect(AN).toContain("esc(t.note)");
  });

  it("uses literal status tokens, not a name built at runtime", () => {
    // `cssVars.test.ts` refuses `var(--status-${…})`: a custom property assembled at runtime is
    // invisible to any check that the token exists. Learned one item ago.
    expect(AN).toContain('"3px solid var(--status-crit)"');
    expect(AN).toContain('"3px solid var(--status-warn)"');
    expect(AN).not.toMatch(/var\(--status-\$\{/);
  });

  it("handles the 409 with what to do about it", () => {
    expect(AN).toContain("No cached permit records for this project");
  });
});

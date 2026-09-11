import { describe, it, expect } from "vitest";
import {
  methodGate, refusal, claimHeadline, eventFinding, concurrencyNote, coverageNote,
  provenanceLine, sourcedRefusal, sourcedNeedsFinish, attributionSummary,
} from "./eotClaim";
import type { EotResult, EotSourced, EotEvent } from "../../api/schedule";

const OK: EotResult = {
  status: "analysed", method: "impacted_as_planned", method_basis: "additive",
  eot_days: 14, additive_days: 14, capped_by_actual_slip: false, over_claimed_days: 0,
  baseline_finish: "2026-06-01", actual_finish: null, events: [],
  concurrency: { pairs: [], count: 0, apportioned: false, note: "" },
};

const ABSORBED: EotEvent = {
  id: "e1", kind: "weather_delay", activity_id: "A10", days: 3,
  total_float: 5, absorbed_by_float: true, critical: false,
  impact_days: 0, eot_days: 0, entitlement: "excusable", reason: "",
};

describe("a claim cannot be computed without its method", () => {
  it("refuses with the reason, not a default", () => {
    const g = methodGate(null);
    expect(g.can).toBe(false);
    expect(g.why).toContain("different answers under different methods");
  });

  it("allows a chosen method", () => {
    expect(methodGate("windows")).toEqual({ can: true, why: "" });
  });
});

describe("the four refusals stay four refusals", () => {
  // Collapsing these into one "could not compute" is the defect this file exists to prevent: they
  // send a reader to four different places, and two are not fixable by supplying anything.
  it("says nothing when the analysis ran", () => {
    expect(refusal(OK)).toBeNull();
  });

  it("a missing baseline is an absent plan-of-record, NOT zero delay", () => {
    const r = refusal({ ...OK, status: "baseline_required", eot_days: null })!;
    expect(r).toContain("no baseline finish");
    expect(r).toContain("NOT a finding of zero delay");
  });

  it("a missing as-built says why the additive sum is not a substitute", () => {
    const r = refusal({ ...OK, status: "actual_finish_required", eot_days: null })!;
    expect(r).toContain("as-built finish is missing");
    expect(r).toContain("one method's number under another method's name");
  });

  it("a series method names who performs it when something does", () => {
    const r = refusal({ ...OK, status: "method_needs_schedule_updates", method: "windows",
                        eot_days: null, performed_by: "GET /projects/{pid}/schedule/windows" })!;
    expect(r).toContain("dated SERIES");
    expect(r).toContain("/schedule/windows");
  });

  it("and says nothing performs it when nothing does, rather than naming a near-miss", () => {
    const r = refusal({ ...OK, status: "method_needs_schedule_updates", method: "time_impact",
                        eot_days: null, performed_by: null })!;
    expect(r).toContain("Nothing here performs it yet");
    expect(r).not.toContain("/schedule/windows");
  });

  it("reports an UNKNOWN status as unknown rather than guessing which refusal it is", () => {
    const r = refusal({ ...OK, status: "some_new_status", eot_days: null })!;
    expect(r).toContain("does not know");
    expect(r).toContain("Do not read the absence of a figure as a finding");
  });

  it("the four refusals are all DIFFERENT strings", () => {
    const rs = ["method_required", "baseline_required", "actual_finish_required",
                "method_needs_schedule_updates"]
      .map((s) => refusal({ ...OK, status: s, eot_days: null }));
    expect(new Set(rs).size).toBe(4);
  });
});

describe("the number never travels without its method", () => {
  it("states the method in the headline", () => {
    const h = claimHeadline(OK);
    expect(h).toContain("14 days of extension");
    expect(h).toContain("impacted as planned");
  });

  it("surfaces over-claim, which is this method's published criticism", () => {
    const h = claimHeadline({ ...OK, over_claimed_days: 6 });
    expect(h).toContain("not bounded by what the job did");
    expect(h).toContain("6 days");
  });

  it("says when the figure was capped at the actual slip", () => {
    const h = claimHeadline({ ...OK, method: "as_planned_vs_as_built",
                              capped_by_actual_slip: true });
    expect(h).toContain("Capped at the movement of the completion date");
  });

  it("falls through to the refusal rather than printing a bare number", () => {
    expect(claimHeadline({ ...OK, status: "baseline_required", eot_days: null }))
      .toContain("NOT a finding of zero delay");
  });

  it("counts one day in the singular", () => {
    expect(claimHeadline({ ...OK, eot_days: 1 })).toContain("1 day of extension");
  });
});

describe("absorbed is not zero — the load-bearing row", () => {
  // A delay inside the activity's float earns no extension and DID happen. Reporting it as 0 days
  // is the reading that says nothing occurred, and the engine's own comment forbids exactly that.
  it("says the delay happened and float took it", () => {
    const f = eventFinding(ABSORBED);
    expect(f).toContain("ABSORBED");
    expect(f).toContain("The delay happened");
    expect(f).toContain("not the same as no delay");
  });

  it("never renders an absorbed row as a plain zero", () => {
    expect(eventFinding(ABSORBED)).not.toMatch(/^0 days/);
  });

  it("says unclassified is not non-excusable", () => {
    const f = eventFinding({ ...ABSORBED, absorbed_by_float: false, total_float: 0,
                             impact_days: 3, eot_days: 0, entitlement: "unclassified" });
    expect(f).toContain("NOT a finding of non-excusable");
    expect(f).toContain("nobody has read it against the contract");
  });

  it("reports a classified non-earning event as the classification it has", () => {
    const f = eventFinding({ ...ABSORBED, absorbed_by_float: false, total_float: 0,
                             impact_days: 4, eot_days: 0, entitlement: "non_excusable" });
    expect(f).toContain("non excusable");
    expect(f).not.toContain("ABSORBED");
  });

  it("reports an earning event with its class", () => {
    const f = eventFinding({ ...ABSORBED, absorbed_by_float: false, total_float: 0,
                             impact_days: 7, eot_days: 7,
                             entitlement: "excusable_compensable" });
    expect(f).toContain("7 days of extension");
    expect(f).toContain("excusable compensable");
  });
});

describe("concurrency is named, never apportioned", () => {
  it("says the split is deliberately not made, and why", () => {
    const n = concurrencyNote({ ...OK,
      concurrency: { pairs: [{}, {}], count: 2, apportioned: false, note: "" } });
    expect(n).toContain("2 concurrent pairs");
    expect(n).toContain("NOT split");
    expect(n).toContain("governed by the contract");
  });

  it("reports NO overlap as unexamined where the data was missing, not as clear", () => {
    const n = concurrencyNote(OK);
    expect(n).toContain("were NOT tested");
    expect(n).toContain("unexamined, not clear");
  });
});

describe("the figure is computed over a subset, and says so", () => {
  const base: EotSourced = {
    baseline: { id: "b1", name: "GMP", captured_at: "2026-01-04T00:00:00Z", count: 40 },
    attribution: { activities: [], attributed_days: 12, unattributed_days: 0, unattributed: [],
                   needs_duration: [], events_without_activity: 0, note: "" },
  };

  it("says nothing when everything was quantified and attributed", () => {
    expect(coverageNote(base)).toEqual([]);
  });

  it("names events excluded for having no stated duration", () => {
    const n = coverageNote({ ...base,
      attribution: { ...base.attribution!, needs_duration: [{}, {}] } });
    expect(n[0]).toContain("2 detected events have no stated duration");
    expect(n[0]).toContain("EXCLUDED from the figure");
    expect(n[0]).toContain("does not establish what the event cost");
  });

  it("reports unattributed slip as unattributed, NEVER as non-excusable", () => {
    const n = coverageNote({ ...base,
      attribution: { ...base.attribution!, unattributed_days: 9 } });
    expect(n[0]).toContain("9 days of measured slip have NO matching cause");
    expect(n[0]).toContain("NOT non-excusable");
    expect(n[0]).toContain("nobody demonstrated");
  });

  it("says proximity is not causation for events carrying no activity", () => {
    const n = coverageNote({ ...base,
      attribution: { ...base.attribution!, events_without_activity: 1 } });
    expect(n[0]).toContain("1 event carries no activity id");
    expect(n[0]).not.toContain("1 event carry ");
    expect(n[0]).toContain("proximity is not causation");
  });

  it("lists all three when all three apply", () => {
    const n = coverageNote({ ...base, attribution: { ...base.attribution!,
      needs_duration: [{}], unattributed_days: 4, events_without_activity: 2 } });
    expect(n).toHaveLength(3);
  });
});

describe("provenance says which of the two paths produced the number", () => {
  it("names the captured baseline for a sourced run", () => {
    const p = provenanceLine({
      baseline: { id: "b1", name: "GMP", captured_at: "2026-01-04T00:00:00Z" },
    });
    expect(p).toContain("GMP");
    expect(p).toContain("2026-01-04");
    expect(p).toContain("re-derivable");
  });

  it("calls the typed path unauditable, which its own docstring does", () => {
    const p = provenanceLine(null);
    expect(p).toContain("unauditable");
    expect(p).toContain("two people can produce different answers");
  });

  it("survives a sourced run whose baseline carries no name", () => {
    expect(provenanceLine({ baseline: null })).toContain("(unnamed)");
  });
});

describe("the sourced path's own refusal", () => {
  it("says nothing when a baseline was found", () => {
    expect(sourcedRefusal({ baseline: { id: "b1", name: "GMP" } })).toBeNull();
  });

  it("points at the available baselines when there are some", () => {
    const r = sourcedRefusal({ status: "baseline_required",
                               baselines_available: [{ id: "b1", name: "GMP" }] })!;
    expect(r).toContain("1 baseline is listed");
  });

  it("says capture one first when there are none, and why it matters", () => {
    const r = sourcedRefusal({ status: "baseline_required", baselines_available: [] })!;
    expect(r).toContain("Capture one first");
    expect(r).toContain("not auditable");
  });
});

describe("a sourced run that cannot compute the entitlement still measured the slip", () => {
  // Found in review on PR #530. Clicking "analyse from the captured baseline" with the finish date
  // blank DOES return baseline_required — the finding was right. The proposed remedy (have the
  // server derive the finish from the baseline) was declined: `eot_sourced` forbids it in its own
  // words, because a captured baseline snapshots PER-ACTIVITY dates and carries no project
  // completion date. There is nothing to read there, only something to invent.
  const refusedRun: EotSourced = {
    baseline: { id: "b1", name: "GMP", captured_at: "2026-01-04T00:00:00Z" },
    attribution: { activities: [], attributed_days: 12, unattributed_days: 4, unattributed: [],
                   needs_duration: [], events_without_activity: 0, note: "" },
    events_detected: 5, events_quantified: 3,
    analysis: { ...OK, status: "baseline_required", eot_days: null },
  };

  it("names the ONE missing input rather than letting the refusal read as a broken baseline", () => {
    const n = sourcedNeedsFinish(refusedRun)!;
    expect(n).toContain("GMP");
    expect(n).toContain("that half is done and auditable");
    expect(n).toContain("baseline COMPLETION date");
  });

  it("says why the server will not infer it, which is a refusal and not a gap", () => {
    const n = sourcedNeedsFinish(refusedRun)!;
    expect(n).toContain("will not");
    expect(n).toContain("invent the very input");
  });

  it("says nothing once the entitlement was computed", () => {
    expect(sourcedNeedsFinish({ ...refusedRun, analysis: OK })).toBeNull();
  });

  it("does not fire for a DIFFERENT refusal — those need something else", () => {
    expect(sourcedNeedsFinish({ ...refusedRun,
      analysis: { ...OK, status: "method_needs_schedule_updates", eot_days: null } })).toBeNull();
  });

  it("reports the measured figures, which stand whatever the entitlement did", () => {
    const a = attributionSummary(refusedRun)!;
    expect(a).toContain("12 days of slip attributed");
    expect(a).toContain("4 unattributed");
    expect(a).toContain("5 events detected, 3 carrying a duration");
  });

  it("omits the unattributed clause when there is none", () => {
    const a = attributionSummary({ ...refusedRun,
      attribution: { ...refusedRun.attribution!, unattributed_days: 0 } })!;
    expect(a).not.toContain("unattributed");
  });

  it("does NOT vouch for a number that was never computed", () => {
    // provenanceLine's "re-derivable" is scoped to what was actually derived.
    const p = provenanceLine(refusedRun);
    expect(p).toContain("Slip measured against the captured baseline GMP");
    expect(p).toContain("entitlement itself was NOT computed");
  });

  it("vouches plainly once the entitlement DID compute", () => {
    const p = provenanceLine({ ...refusedRun, analysis: OK });
    expect(p).toContain("re-derivable");
    expect(p).not.toContain("NOT computed");
  });
});

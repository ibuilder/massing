import { describe, expect, it } from "vitest";

import { countNarrative, deltaChip, kpiHeader, statusChip, toneFor } from "./chips";

describe("UX-CHIPS — the shared status/delta vocabulary", () => {
  it("maps workflow words to tones", () => {
    expect(toneFor("Approved")).toBe("ok");
    expect(toneFor("paid")).toBe("ok");
    expect(toneFor("In Review")).toBe("info");
    expect(toneFor("over_budget")).toBe("bad");
    expect(toneFor("At Risk")).toBe("warn");
    expect(toneFor("whatever")).toBe("neutral");
  });

  // Every distinct workflow state defined across the platform's module.json files. The chip
  // vocabulary exists to make state readable at a glance, so most of these must resolve to a real
  // tone — an earlier version recognised only 30 of them and rendered 73% of every register the
  // same grey. This list is the contract: adding a module state without a tone should fail here.
  const REAL_STATES = ("accepted acknowledged active adopted ae_review agenda agreed answered appealed "
    + "applied approved archived assessed assigned awarded billed captured cleared closed coming_soon "
    + "committed complete completed concept confirmed controlled corrected decided decommissioned "
    + "delivered demobilized denied deviated dispositioned done draft evidenced excluded executed "
    + "exited expired exported failed fieldwork flagged funded gc_review gc_signed hearing holdover "
    + "identified in_progress in_review inactive installed investigating issued leased logged "
    + "made_ready minutes missed mitigated mitigating not_done open ordered paid passed paused pending "
    + "planned priced programmed proposed prospect published pulled quotes_in ready received "
    + "reconciled recorded rejected renewed reported requested resolved retired returned reviewed "
    + "rfq_sent scheduled selected sent shared shortlisted signed_off sized sold submitted super_signed "
    + "superseded terminated tested under_contract under_revision verified void voided wip withdrawn"
  ).split(" ");

  it("gives almost every real module state a meaningful tone", () => {
    const grey = REAL_STATES.filter((s) => toneFor(s) === "neutral");
    // the only states that should read neutral are the ones that have LEFT the live set
    expect(grey.sort()).toEqual(["archived", "decommissioned", "demobilized", "exited", "inactive",
      "pulled", "retired", "superseded", "void", "voided"]);
    expect(grey.length / REAL_STATES.length).toBeLessThan(0.12);
  });

  it("separates 'left the live set' from 'went wrong'", () => {
    // a voided drawing is withdrawn from the set, not an error — it must not read red
    expect(toneFor("void")).toBe("neutral");
    expect(toneFor("superseded")).toBe("neutral");
    // …while a genuine refusal does
    expect(toneFor("rejected")).toBe("bad");
    expect(toneFor("not_done")).toBe("bad");
    expect(toneFor("withdrawn")).toBe("bad");
    // and the in-flight / needs-attention split holds
    expect(toneFor("gc_review")).toBe("info");
    expect(toneFor("issued")).toBe("ok");
    expect(toneFor("under_revision")).toBe("warn");
    expect(toneFor("signed_off")).toBe("ok");
    // separator and spacing normalisation
    expect(toneFor("SIGNED-OFF")).toBe("ok");
    expect(toneFor("  in_progress  ")).toBe("info");
  });

  it("renders a timestamped, escaped status chip", () => {
    const html = statusChip("Viewed <script>", { ts: "2026-07-24T10:00:00Z" });
    expect(html).toContain("chip2-info");
    expect(html).toContain("07/24");
    expect(html).not.toContain("<script>");            // esc() applied
    expect(html).toContain("&lt;script&gt;");
  });

  it("delta chips color by sign and flip for cost metrics", () => {
    expect(deltaChip(12, { pct: true })).toContain("chip2-ok");
    expect(deltaChip(12, { pct: true })).toContain("+12.0%");
    expect(deltaChip(-8.25, { pct: true })).toContain("chip2-bad");
    expect(deltaChip(14000, { currency: true, goodWhenNegative: true })).toContain("chip2-bad");
    expect(deltaChip(14000, { currency: true, goodWhenNegative: true })).toContain("$14K");
    expect(deltaChip(-2_500_000, { currency: true, goodWhenNegative: true })).toContain("chip2-ok");
    expect(deltaChip(-2_500_000, { currency: true })).toContain("$2.5M");
    expect(deltaChip(0)).toContain("chip2-neutral");
    expect(deltaChip(Number.NaN)).toBe("");
  });

  it("kpi header lays out tiles + the template narrative", () => {
    const html = kpiHeader(
      [{ label: "Budget", value: "$4.2M", delta: -3.1, deltaPct: true, goodWhenNegative: true },
       { label: "Open RFIs", value: "7" }],
      countNarrative([[3, "jobs on track"], [1, "over budget"], [0, "stalled"]]));
    expect(html).toContain("kpi-header");
    expect(html).toContain("$4.2M");
    expect(html).toContain("chip2-ok");                 // cost down = good
    expect(html).toContain("3 jobs on track, 1 over budget");
    expect(html).not.toContain("stalled");              // zero counts drop out
    expect(countNarrative([[0, "x"]])).toBe("Nothing needs attention");
  });
});

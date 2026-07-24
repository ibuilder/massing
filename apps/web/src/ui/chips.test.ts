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

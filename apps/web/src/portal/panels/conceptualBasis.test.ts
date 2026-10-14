import { describe, expect, it } from "vitest";

import {
  BASIS_CSS, basisRows, classNote, midpointReading, sectorLine, type ConceptualEstimate,
} from "./conceptualBasis";

/** The payload the engine actually returns for an office, 120k sf, us_average, 20 storeys. */
const E = (over: Partial<ConceptualEstimate> = {}): ConceptualEstimate => ({
  building_type: "office", gfa_sf: 120_000, region: "us_average", region_index: 1,
  year: 2026, escalation_factor: 1, height_factor: 1.064, soft_cost_pct: 25,
  hard_cost: 39_580_800, soft_cost: 9_895_200, total_cost: 49_476_000,
  range: { low: 42_054_600, base: 49_476_000, high: 59_371_200 },
  metrics: { cost_per_sf: 329.84, total_per_sf: 412.3 },
  market: {
    region: "North America", labour_usd_hr: 79.5, sector_temperature: "cold",
    sector_note: "Slower momentum — softer investor confidence; more competitive bidding may be available.",
    escalation_basis: "midpoint of a 24-month build starting 2027",
    midpoint_escalation_factor: 1.0941,
    total_at_construction_midpoint: 54_131_692,
  },
  note: "Conceptual (Class 5) estimate from parametric $/SF benchmarks — a directional signal for "
    + "the proforma, not a detailed takeoff. Refine as the design develops.",
  ...over,
});

describe("ESTIMATE-BASIS", () => {
  it("THE MEASURED GAP: the midpoint total is 9.4% above the one the card showed", () => {
    const m = midpointReading(E());
    expect(m.kind).toBe("escalated");
    expect(m.total).toBe(54_131_692);
    expect(m.deltaPct).toBe(9.4);
    expect(m.tone).toBe("warn");                       // ≥5% is a material difference
    expect(m.text).toContain("$54,131,692");
    expect(m.text).toContain("$49,476,000");           // both numbers, so the gap is readable
    expect(m.text).toContain("midpoint of a 24-month build starting 2027");
  });

  it("computes the delta against the total the CARD shows, not an intermediate", () => {
    // The payload also carries `hard_cost` and a pre-soft `base_total` the engine escalates from.
    // A percentage against either would be a true number about two things a reader cannot see.
    const m = midpointReading(E({ total_cost: 50_000_000 }));
    expect(m.deltaPct).toBe(Math.round(((54_131_692 - 50_000_000) / 50_000_000) * 1000) / 10);
  });

  it("PROMPTS for the missing input rather than going silent", () => {
    // Silence over a figure that is materially lower than the right one is the defect this item is
    // named for. The reading says which input it is waiting for.
    const m = midpointReading(E({ market: { region: "North America", labour_usd_hr: 79.5,
                                            sector_temperature: "cold", sector_note: "x" } }));
    expect(m.kind).toBe("prompt");
    expect(m.tone).toBe("unknown");
    expect(m.text).toContain("start year and duration");
    expect(m.text).toContain("today's money");
    // and with no market at all
    expect(midpointReading(E({ market: undefined })).kind).toBe("prompt");
  });

  it("does not claim an escalation when the total is zero", () => {
    // A 0% base would make the delta Infinity, and a card reading "+Infinity%" is worse than one
    // that asks for an input.
    expect(midpointReading(E({ total_cost: 0 })).kind).toBe("prompt");
  });

  it("states the year and the escalation factor together", () => {
    const rows = basisRows(E());
    expect(rows.find((r) => r.label === "Cost year")!.value).toBe("2026 (escalation ×1)");
    expect(rows.find((r) => r.label === "Region")!.value).toBe("us_average (×1)");
    expect(rows.find((r) => r.label === "Soft costs")!.value).toBe("25% of hard");
  });

  it("omits a row the server did not send rather than defaulting it", () => {
    // A `height_factor` of 1 is a real answer (no premium) and an absent one is not knowable;
    // printing "×1" for both states something nobody measured.
    const rows = basisRows(E({ year: undefined, soft_cost_pct: undefined, region: undefined,
                               height_factor: undefined }));
    expect(rows.map((r) => r.label)).toEqual(["Building type"]);
    // and an UNDEFINED height factor is dropped for a different reason from a factor of 1: one is
    // "not knowable", the other is "no premium". Both produce no row, and the next assertion keeps
    // the two cases from collapsing into one test that passes for either reason.
    expect(basisRows(E({ height_factor: undefined })).some((r) => r.label === "Height premium"))
      .toBe(false);
  });

  it("omits the height premium when it is exactly 1, because there is no premium to report", () => {
    expect(basisRows(E({ height_factor: 1 })).some((r) => r.label === "Height premium")).toBe(false);
    expect(basisRows(E()).find((r) => r.label === "Height premium")!.value).toBe("×1.064");
  });

  it("warns on a HOT sector and stays neutral on a cold one", () => {
    expect(sectorLine(E())!.tone).toBe("unknown");
    const hot = sectorLine(E({ market: { ...E().market!, sector_temperature: "hot" } }))!;
    expect(hot.tone).toBe("warn");
    expect(hot.text).toContain("labour $79.5/hr");
    expect(sectorLine(E({ market: undefined }))).toBeNull();
  });

  it("returns the engine's Class 5 caveat verbatim", () => {
    // Not paraphrased: it is the engine's own wording, and a second one is a second thing to keep
    // in step. The band this card prints is −15%/+20%, which reads far tighter than Class 5 is.
    expect(classNote(E())).toContain("Class 5");
    expect(classNote(E({ note: undefined }))).toBeNull();
  });

  it("maps every tone to a CSS variable", () => {
    for (const t of ["ok", "warn", "unknown"] as const) expect(BASIS_CSS[t]).toMatch(/^var\(--/);
  });
});

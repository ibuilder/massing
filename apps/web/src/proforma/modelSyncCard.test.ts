import { describe, expect, it } from "vitest";

import {
  basisNote, disciplineRows, SYNC_CSS, syncFailure, vintageNote, type ModelSyncResult,
} from "./modelSyncCard";

const R = (over: Partial<ModelSyncResult> = {}): ModelSyncResult => ({
  synced: true, hard_cost: 12_400_000,
  by_discipline: { Structural: 6_000_000, Architectural: 4_400_000, Mechanical: 2_000_000,
                   Electrical: 0 },
  basis: "per_discipline", discipline_total: 12_400_000,
  cost_vintage: { name: "RSMeans 2026", year: 2026, region: "us-west" },
  cost_adjustment: { combined_factor: 1.084 },
  ...over,
});

describe("MODELSYNC-DARK", () => {
  it("orders the breakdown biggest first and drops the zeros", () => {
    expect(disciplineRows(R()).map((d) => d.discipline))
      .toEqual(["Structural", "Architectural", "Mechanical"]);
  });

  it("says the committed cost IS the sum on the per-discipline branch", () => {
    const n = basisNote(R());
    expect(n.tone).toBe("ok");
    expect(n.text).toContain("sum of the priced element lines");
  });

  it("WARNS that the breakdown is not a decomposition on the benchmark branch", () => {
    // The route writes ONE lump line here, and `by_discipline` is still the element pricing. A
    // reader who takes the table as a decomposition of the headline is reading two different
    // estimates as one.
    const n = basisNote(R({ basis: "gfa_benchmark", hard_cost: 15_000_000,
                            discipline_total: 12_400_000 }));
    expect(n.tone).toBe("warn");
    expect(n.text).toContain("does NOT add up");
    expect(n.text).toContain("$12,400,000");     // the element sum, so the gap is visible
  });

  it("does NOT assume the reassuring basis when the server states none", () => {
    // An older server omits `basis`. Defaulting to `per_discipline` would assert that the
    // breakdown decomposes the headline, which is the one thing that cannot be known here.
    const n = basisNote(R({ basis: undefined }));
    expect(n.tone).toBe("warn");
    expect(n.text).toContain("did not state which basis");
  });

  it("names the vintage, the year and the region that priced it", () => {
    expect(vintageNote(R())).toContain("RSMeans 2026 · 2026 · us-west");
    expect(vintageNote(R())).toContain("×1.084");
  });

  it("treats a combined factor of exactly 1 as an ANSWER, not an absence", () => {
    // `1` is falsy nowhere in JS, but `a?.combined_factor && …` would still read a legitimate
    // "no adjustment" as "not stated" if the value were 0, and the distinction is the same one:
    // a factor of 1 means somebody computed it and it came to 1.
    expect(vintageNote(R({ cost_adjustment: { combined_factor: 1 } })))
      .toContain("no location or escalation adjustment applied");
    expect(vintageNote(R({ cost_adjustment: {} }))).not.toContain("adjustment");
    expect(vintageNote(R({ cost_adjustment: null }))).not.toContain("adjustment");
  });

  it("says the shipped rates applied when no vintage is installed", () => {
    const t = vintageNote(R({ cost_vintage: null }));
    expect(t).toContain("shipped benchmark unit rates");
    expect(t).toContain("not escalated");         // the two things a vintage would have added
  });

  it("keeps the two 409s apart, because only one is worth pressing again", () => {
    const race = syncFailure("the source IFC was republished while the takeoff ran; re-run the sync "
                             + "against the current model");
    expect(race.retryable).toBe(true);
    expect(race.text).toContain("Press it again");
    const noModel = syncFailure("project has no accessible source IFC");
    expect(noModel.retryable).toBe(false);
    expect(noModel.text).toContain("Upload or publish a model first");
    // and an unrecognised failure is relayed rather than guessed at — never offered as retryable
    const other = syncFailure("permission denied");
    expect(other.retryable).toBe(false);
    expect(other.text).toBe("Sync failed: permission denied");
  });

  it("maps every tone to a CSS variable", () => {
    for (const t of ["ok", "warn"] as const) expect(SYNC_CSS[t]).toMatch(/^var\(--/);
  });
});

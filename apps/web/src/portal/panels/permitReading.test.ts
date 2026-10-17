import { describe, expect, it } from "vitest";

import {
  declarationGap, deficiencyPageNote, deficiencyRows, editionNote, PERMIT_CSS, seriesRows,
  type PermitReadiness,
} from "./permitReading";

const R = (over: Partial<PermitReadiness> = {}): PermitReadiness => ({
  verdict: "NOT READY", readiness_pct: 62.5, approvability_score: 74,
  checklist: [{ requirement: "Computed egress capacity meets occupant load (IBC 1005)",
                satisfied: true, evidence: "no deficiencies" }],
  deficiencies: [
    { item: "Plan-reviewer pre-flight ≥ 80%", severity: "critical",
      action: "work the approvability checklist", source: "approvability score 74%" },
    { item: "Mechanical in the drawing register", severity: "major",
      action: "generate the M-series sheets", source: "no sheets in this series" },
  ],
  code_edition: 2021,
  code_context: { jurisdiction: "CA", ibc_edition: 2021, resolved: true, as_of: 2026,
                  verify: "Verify the adoption with the AHJ." },
  declared: { occupancy_group: "B", construction_type: "II-B", sprinklered: false,
              jurisdiction: "CA" },
  sheet_series: { G: 1, A: 2, S: 1, M: 0, E: 0, P: 0 },
  disclaimer: "Pre-check assist with cited sections — NOT a certified plan review.",
  ...over,
});

describe("PERMIT-BLIND", () => {
  it("names the edition AND whose adoption it is", () => {
    const n = editionNote(R());
    expect(n.tone).toBe("ok");
    expect(n.text).toContain("IBC 2021 — CA adoption, as-of 2026");
    expect(n.text).toContain("Verify the adoption with the AHJ");
  });

  it("will not let a BASELINE edition read as an adopted one", () => {
    // IBC 2021 because this state adopted it, and IBC 2021 as the national baseline, are different
    // claims — and a permit screen printing the number without the basis invites a reader to cite it.
    const n = editionNote(R({ code_context: { jurisdiction: null, ibc_edition: 2021,
                                              resolved: false, as_of: null, verify: null } }));
    expect(n.tone).toBe("warn");
    expect(n.text).toContain("NATIONAL BASELINE");
    expect(n.text).toContain("Set a jurisdiction");
  });

  it("distinguishes 'no edition resolved' from 'this server did not say'", () => {
    // The two call for different actions — set a jurisdiction, versus the response is incomplete —
    // and the shipped null `code_edition` would have looked like the first while being the second.
    const none = editionNote(R({ code_context: { jurisdiction: null, ibc_edition: null,
                                                 resolved: false, as_of: null, verify: null },
                                 code_edition: null }));
    expect(none.tone).toBe("warn");
    expect(none.text).toContain("No IBC edition was resolved");
    const silent = editionNote(R({ code_context: undefined, code_edition: null }));
    expect(silent.tone).toBe("unknown");
    expect(silent.text).toContain("not knowable");
  });

  it("falls back to the top-level `code_edition` when the context omits it", () => {
    // Both keys carry the same value by construction on the server; reading only one would make a
    // partial response look unresolved.
    const n = editionNote(R({ code_context: { jurisdiction: "WA", ibc_edition: null,
                                              resolved: true, as_of: 2025, verify: null },
                              code_edition: 2018 }));
    expect(n.text).toContain("IBC 2018 — WA adoption");
  });

  it("warns when a classification was INFERRED rather than declared", () => {
    const g = declarationGap(R({ declared: { occupancy_group: null, construction_type: null,
                                             sprinklered: false, jurisdiction: "CA" } }))!;
    expect(g.missing).toEqual(["occupancy group", "construction type"]);
    expect(g.text).toContain("not a declaration for permit purposes");
    // and it explains the checklist row the reader is looking at
    expect(g.text).toContain("cannot be satisfied");
  });

  it("names only the one that is missing", () => {
    const g = declarationGap(R({ declared: { occupancy_group: "B", construction_type: null,
                                             sprinklered: true, jurisdiction: null } }))!;
    expect(g.missing).toEqual(["construction type"]);
    expect(g.text).toContain("inferred it from the model");     // singular
  });

  it("says nothing when both are declared, and nothing when the server is silent", () => {
    // A "declared ✓" line on every healthy run is the reassurance that trains a reader to skip the
    // line that matters.
    expect(declarationGap(R())).toBeNull();
    expect(declarationGap(R({ declared: undefined }))).toBeNull();
  });

  it("carries the SOURCE of each deficiency, which the old line dropped", () => {
    const rows = deficiencyRows(R());
    expect(rows[0]!.source).toBe("approvability score 74%");
    expect(rows[1]!.source).toBe("no sheets in this series");
    // an absent source is "" rather than undefined, so a renderer cannot print "undefined"
    expect(deficiencyRows(R({ deficiencies: [{ item: "x", severity: "minor", action: "y" }] }))[0]!.source)
      .toBe("");
  });

  it("states both numbers where the deficiency list stops", () => {
    expect(deficiencyPageNote(6, 11)).toBe("Showing the 6 highest-severity of 11 deficiencies.");
    expect(deficiencyPageNote(2, 2)).toBe("");
  });

  it("reports the registered sheet counts including the zeros", () => {
    const rows = seriesRows(R());
    expect(rows).toHaveLength(6);
    // the ZEROS are the point: a series with no sheets is the deficiency, and dropping it would
    // leave the table showing only what is already done.
    expect(rows.filter((x) => x.sheets === 0).map((x) => x.series)).toEqual(["M", "E", "P"]);
    expect(seriesRows(R({ sheet_series: undefined }))).toEqual([]);
  });

  it("maps every tone to a CSS variable", () => {
    for (const t of ["ok", "warn", "unknown"] as const) expect(PERMIT_CSS[t]).toMatch(/^var\(--/);
  });
});

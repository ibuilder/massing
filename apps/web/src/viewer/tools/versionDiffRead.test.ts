import { describe, expect, it } from "vitest";

import {
  COVERAGE_CSS, coverageNote, modifiedPageNote, propertyChangeText, propertyClause,
  type DiffCoverage, type PropertyChange,
} from "./versionDiffRead";

const FULL: DiffCoverage = { modified_available: true, property_detail_available: true,
                             property_values_available: true, values_truncated: false };

describe("VERSION-VALUES", () => {
  it("renders a changed property as before → after", () => {
    expect(propertyChangeText({ property: "Pset_WallCommon.FireRating", status: "changed",
                                from: "1HR", to: "2HR" }))
      .toBe("Pset_WallCommon.FireRating: 1HR → 2HR");
  });

  it("puts `from` on the EARLIER side, which is the one mistake here that looks plausible", () => {
    // `versions.diff` reads `before = fa.get(g)` for version `a` and assigns `from` from `before`,
    // so `from` is the `a` side — even though the locals holding the snapshots are spelled `vb`/`va`,
    // which reads the other way round. A reversed render would be a correct-looking lie about which
    // direction the building moved in, so the direction is asserted rather than assumed.
    const t = propertyChangeText({ property: "Height", status: "changed", from: "3000", to: "3600" });
    expect(t.indexOf("3000")).toBeLessThan(t.indexOf("3600"));
  });

  it("shows only the side that exists for an added or removed property", () => {
    expect(propertyChangeText({ property: "IsExternal", status: "added", to: "true" }))
      .toBe("IsExternal: + true");
    expect(propertyChangeText({ property: "IsExternal", status: "removed", from: "true" }))
      .toBe("IsExternal: − true");
    // and names the status when the value is absent too
    expect(propertyChangeText({ property: "IsExternal", status: "added" })).toBe("IsExternal (added)");
  });

  it("distinguishes CAPPED values from a property it cannot name a value for", () => {
    // Both arrive as a `changed` row with no values, and they are different facts: the engine sets
    // `values_truncated` when `from` and `to` are both absent on a changed key. Rendering it as a
    // bare name would read like the no-snapshot case, and as "x → x" would be a false claim that
    // nothing moved.
    expect(propertyChangeText({ property: "Area", status: "changed" }))
      .toBe("Area (changed, values not stored)");
    expect(propertyChangeText({ property: "Area", status: "changed", from: null, to: null }))
      .toBe("Area (changed, values not stored)");
    // one side present is still a reading, with the missing side marked
    expect(propertyChangeText({ property: "Area", status: "changed", to: "12.5" }))
      .toBe("Area: — → 12.5");
  });

  it("COUNTS the properties it did not show instead of printing an ellipsis", () => {
    const props: PropertyChange[] = Array.from({ length: 9 }, (_, i) =>
      ({ property: `P${i}`, status: "changed" as const, from: "a", to: "b" }));
    const clause = propertyClause(props, 6);
    expect(clause).toContain("+3 more");
    expect(clause).not.toContain("…");          // "…" said there was more and not how much
    expect(clause.split(", ").length).toBe(6);  // the 6th carries the count, so 6 comma-separated
  });

  it("returns an empty clause for an element with no property detail", () => {
    expect(propertyClause(undefined)).toBe("");
    expect(propertyClause([])).toBe("");
  });

  it("keeps the three causes of missing detail DISTINCT, because the fixes differ", () => {
    const noFp = coverageNote({ ...FULL, modified_available: false })!;
    expect(noFp.text).toContain("before element fingerprints were stored");
    const noHash = coverageNote({ ...FULL, property_detail_available: false })!;
    expect(noHash.text).toContain("per-property");
    expect(noHash.text).not.toContain("fingerprints were stored");
    const noValues = coverageNote({ ...FULL, property_values_available: false })!;
    expect(noValues.text).toContain("NAMES only");
    const capped = coverageNote({ ...FULL, values_truncated: true })!;
    expect(capped.tone).toBe("warn");
    expect(capped.text).toContain("capped out of the version snapshot");
    // four distinct texts, so none of them is reachable only by accident
    expect(new Set([noFp.text, noHash.text, noValues.text, capped.text]).size).toBe(4);
  });

  it("checks the causes in order of how little is known", () => {
    // A version with no fingerprints has no hashes and no values either, so all three flags are
    // false at once. The note must name the ROOT cause — re-publish — not the last one tested.
    const bare = coverageNote({ modified_available: false })!;
    expect(bare.text).toContain("Re-publish");
  });

  it("says NOTHING when the detail is complete", () => {
    // No reassurance line. A card that prints "coverage: full" on every healthy diff trains the
    // reader to skip the line that matters.
    expect(coverageNote(FULL)).toBeNull();
  });

  it("states both numbers when the modified table is a page", () => {
    expect(modifiedPageNote(40, 112)).toBe("Showing the first 40 of 112 modified elements.");
    expect(modifiedPageNote(12, 12)).toBe("");
    expect(modifiedPageNote(0, 0)).toBe("");
  });

  it("maps every tone to a CSS variable", () => {
    for (const t of ["ok", "warn", "unknown"] as const) expect(COVERAGE_CSS[t]).toMatch(/^var\(--/);
  });
});

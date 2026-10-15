import { describe, expect, it } from "vitest";

import {
  areaRows, occupancyBasis, occupancyLine, occupancySuspect, occupancyText,
  type RentRollBasisFields,
} from "./rentRollBasis";

/** The two responses measured on the engine from IDENTICAL leases. */
const MEASURED: RentRollBasisFields = {
  total_rentable_sf: 20000, occupied_sf: 6000, vacant_sf: 14000, occupancy_pct: 30.0,
  occupancy_basis: "building", building_rentable_sf: 20000,
};
const UNSET: RentRollBasisFields = {
  total_rentable_sf: 6000, occupied_sf: 6000, vacant_sf: 0, occupancy_pct: 100.0,
  occupancy_basis: "leased", building_rentable_sf: null,
};
/** A genuinely full building — the case the derived fallback must NOT relabel. */
const FULL: RentRollBasisFields = {
  total_rentable_sf: 6000, occupied_sf: 6000, vacant_sf: 0, occupancy_pct: 100.0,
  occupancy_basis: "building", building_rentable_sf: 6000,
};

describe("occupancyBasis", () => {
  it("takes the server's answer", () => {
    expect(occupancyBasis(MEASURED)).toBe("building");
    expect(occupancyBasis(UNSET)).toBe("leased");
  });

  it("refuses to infer the basis from the numbers, because they are identical", () => {
    // UNSET and FULL agree on all four numeric fields. Deriving "leased" from
    // `total_rentable_sf === occupied_sf` would relabel every fully leased building as unmeasured.
    const strip = (r: RentRollBasisFields) => {
      const { occupancy_basis: _b, building_rentable_sf: _s, ...rest } = r;
      return rest as RentRollBasisFields;
    };
    expect(strip(UNSET)).toEqual(strip(FULL));
    expect(occupancyBasis(strip(UNSET))).toBe("unknown");
    expect(occupancyBasis(strip(FULL))).toBe("unknown");
  });

  it("treats an unrecognised basis string as unknown rather than as sound", () => {
    expect(occupancyBasis({ ...MEASURED, occupancy_basis: "something-new" })).toBe("unknown");
  });
});

describe("occupancyText", () => {
  it("prints the percentage when there is a real denominator", () => {
    expect(occupancyText(MEASURED)).toBe("30%");
    expect(occupancyText(FULL)).toBe("100%");
  });

  it("refuses to print 100% when the denominator IS the numerator", () => {
    expect(occupancyText(UNSET)).toBe("n/a");
  });

  it("marks an unknown basis rather than hiding or trusting it", () => {
    expect(occupancyText({ ...MEASURED, occupancy_basis: undefined })).toBe("30%†");
  });

  it("does not print undefined when the figure is absent", () => {
    expect(occupancyText({ occupancy_basis: "building" })).toBe("—");
  });

  it("gives the two measured responses different text", () => {
    // The whole defect: the same card rendered both as "100%" and "30%" respectively, and the
    // 100% was an artefact of an unfilled project field.
    expect(occupancyText(UNSET)).not.toBe(occupancyText(FULL));
  });
});

describe("occupancyLine", () => {
  it("is silent when the basis is sound — a correct card gets no banner", () => {
    expect(occupancyLine(MEASURED)).toBeNull();
    expect(occupancyLine(FULL)).toBeNull();
  });

  it("names the cause and the remedy when there is no building area", () => {
    const line = occupancyLine(UNSET)!;
    expect(line).toContain("no rentable building area");
    expect(line).toContain("6,000 sf");
    expect(line).toContain("100% of itself");
    expect(line).toContain("Rentable SF");
  });

  it("hedges, and says why it cannot do better, when the basis is unknown", () => {
    const line = occupancyLine({ ...UNSET, occupancy_basis: undefined })!;
    expect(line).toContain("did not say");
    expect(line).toContain("report the same numbers");
  });
});

describe("areaRows", () => {
  it("puts the denominator on screen when there is one", () => {
    expect(areaRows(MEASURED)).toEqual([
      { label: "Rentable area", value: "20,000 sf" },
      { label: "Leased area", value: "6,000 sf" },
      { label: "Vacant area", value: "14,000 sf" },
    ]);
  });

  it("shows no rentable or vacant figure when neither was measured", () => {
    // `vacant_sf: 0` is the engine's arithmetic on a fallback denominator, not a vacancy of zero.
    expect(areaRows(UNSET)).toEqual([
      { label: "Rentable area (not set)", value: "—" },
      { label: "Leased area", value: "6,000 sf" },
      { label: "Vacant area (unknown)", value: "—" },
    ]);
  });

  it("renders a genuinely full building's zero vacancy as zero", () => {
    expect(areaRows(FULL)[2]).toEqual({ label: "Vacant area", value: "0 sf" });
  });

  it("survives absent fields", () => {
    expect(areaRows({ occupancy_basis: "building" }).map((r) => r.value)).toEqual(["—", "—", "—"]);
  });
});

describe("occupancySuspect", () => {
  it("is false only on a measured basis", () => {
    expect(occupancySuspect(MEASURED)).toBe(false);
    expect(occupancySuspect(FULL)).toBe(false);
    expect(occupancySuspect(UNSET)).toBe(true);
    expect(occupancySuspect({ ...MEASURED, occupancy_basis: undefined })).toBe(true);
  });
});

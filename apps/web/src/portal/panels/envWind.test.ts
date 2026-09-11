import { describe, it, expect } from "vitest";
import {
  screenGate, unassessed, verdict, dimensionBasis, windBasis, mitigationLines, comfortLabel,
} from "./envWind";
import type { WindResult } from "../../api/designPerformance";

/** A 120 m tower on a 6 m/s site with a gap supplied — every mechanism looked at. */
const TOWER: WindResult = {
  inputs: { height_m: 120, width_m: 40, depth_m: 30, wind_ms: 6, gap_m: 20, podium_height_m: 0 },
  zones: [
    { zone: "open site (baseline)", factor: 1, speed_ms: 6, lawson: "B", comfort: "standing" },
    { zone: "corners", factor: 1.6, speed_ms: 9.6, lawson: "D", comfort: "brisk walking" },
    { zone: "base (downwash)", factor: 1.48, speed_ms: 8.9, lawson: "D", comfort: "brisk walking" },
    { zone: "passage (20 m gap)", factor: 1.33, speed_ms: 8, lawson: "D", comfort: "brisk walking" },
  ],
  worst: { zone: "corners", lawson: "D", speed_ms: 9.6 },
  acceptable_for_entrances: false,
  mitigations: ["chamfer/round the windward corners or add corner canopies"],
  disclaimer: "Approximate massing-stage screen … NOT CFD or a wind-tunnel study.",
};

/** A low calm building, screened with NO gap — the partial-screen case. */
const LOW: WindResult = {
  inputs: { height_m: 9, width_m: 20, depth_m: 15, wind_ms: 3, gap_m: null, podium_height_m: 0 },
  zones: [
    { zone: "open site (baseline)", factor: 1, speed_ms: 3, lawson: "A", comfort: "sitting" },
    { zone: "corners", factor: 1.24, speed_ms: 3.7, lawson: "A", comfort: "sitting" },
  ],
  worst: { zone: "corners", lawson: "A", speed_ms: 3.7 },
  acceptable_for_entrances: true,
  mitigations: [],
  disclaimer: "Approximate massing-stage screen … NOT CFD or a wind-tunnel study.",
};

describe("the screen refuses to run rather than surfacing a 409", () => {
  it("needs dimensions or a model", () => {
    const g = screenGate({}, "absent");
    expect(g.can).toBe(false);
    expect(g.why).toContain("height, width and depth");
    expect(g.why).toContain("bounding box");
  });

  it("runs on a model alone — the dims get derived", () => {
    expect(screenGate({}, "present")).toEqual({ can: true, why: "" });
  });

  it("runs on a full set of dimensions with no model at all", () => {
    expect(screenGate({ height_m: 30, width_m: 20, depth_m: 15 }, "absent").can).toBe(true);
  });

  it("refuses a PARTIAL set with a CONFIRMED absent model — the server 409s on exactly this", () => {
    expect(screenGate({ height_m: 30, width_m: 20 }, "absent").can).toBe(false);
  });

  it("does not count a zero or negative dimension as given", () => {
    expect(screenGate({ height_m: 30, width_m: 0, depth_m: 15 }, "absent").can).toBe(false);
    expect(screenGate({ height_m: 30, width_m: -4, depth_m: 15 }, "absent").can).toBe(false);
  });
});

describe("a gate that exists to relay a 409 must not invent one", () => {
  // Found in review on PR #529. The panel learns about the model from the design-metrics read, and
  // only its 409 is evidence there is NO model — that is the same `open_source_ifc` refusal the wind
  // route makes. A 500 in the daylight computation says nothing about it. Collapsing both into one
  // boolean refused the screen on a project that has a perfectly good model.
  it("lets an UNKNOWN model reach the server, which is the thing that knows", () => {
    expect(screenGate({}, "unknown").can).toBe(true);
    expect(screenGate({ height_m: 30 }, "unknown").can).toBe(true);
  });

  it("refuses only on a CONFIRMED absence", () => {
    expect(screenGate({}, "absent").can).toBe(false);
  });
});

describe("a check that did not run is never reported as a pass", () => {
  // THE load-bearing rule. Channelling is raised only when a gap is supplied, so a blank gap gives
  // `acceptable_for_entrances: true` having never looked at the passage — which is where pedestrian
  // wind complaints actually come from.
  it("names channelling as unchecked when no gap was given", () => {
    const u = unassessed(LOW);
    expect(u).toHaveLength(1);
    expect(u[0]).toContain("NOT checked");
    expect(u[0]).toContain("gap");
  });

  it("withholds the word 'acceptable' from a partial screen the server called acceptable", () => {
    expect(LOW.acceptable_for_entrances).toBe(true);
    const v = verdict(LOW);
    expect(v).not.toContain("Acceptable for entrances");
    expect(v).toContain("PARTIAL");
    expect(v).toContain("not a pass");
  });

  it("reports nothing unchecked once a passage zone is in the answer", () => {
    expect(unassessed(TOWER)).toEqual([]);
  });

  it("reports nothing unchecked when a gap was given and raised no passage zone", () => {
    // A wide gap does not channel. That is a mechanism LOOKED AT and found not to apply — a finding,
    // not a hole, and listing it would train the reader to skip the list.
    const wide = { ...LOW, inputs: { ...LOW.inputs, gap_m: 60 } };
    expect(unassessed(wide)).toEqual([]);
  });

  it("reads the ANSWER rather than re-deriving the server's applicability rule", () => {
    // A passage zone present with gap_m somehow absent is still an assessed channelling check. A
    // second copy of `gap < h/2 and h > 10` here would measure the copy, not the screen.
    const odd = { ...TOWER, inputs: { ...TOWER.inputs, gap_m: null } };
    expect(unassessed(odd)).toEqual([]);
  });

  it("says 'acceptable' plainly when every mechanism ran and none failed", () => {
    const full = { ...LOW, inputs: { ...LOW.inputs, gap_m: 60 } };
    const v = verdict(full);
    expect(v).toContain("Acceptable for entrances");
    expect(v).not.toContain("PARTIAL");
  });
});

describe("the verdict distinguishes discomfort from danger", () => {
  it("reports a failing comfort screen as a comfort failure", () => {
    const v = verdict(TOWER);
    expect(v).toContain("NOT acceptable");
    expect(v).toContain("9.6 m/s");
    expect(v).toContain("Lawson D");
    expect(v).not.toContain("UNSAFE");
  });

  it("calls the S grade a SAFETY threshold, not a worse comfort grade", () => {
    const gale: WindResult = { ...TOWER, worst: { zone: "corners", lawson: "S", speed_ms: 17.6 } };
    const v = verdict(gale);
    expect(v).toContain("UNSAFE");
    expect(v).toContain("15 m/s safety criterion");
    expect(v).toContain("not a comfort grade");
  });

  it("labels an S zone row the same way", () => {
    expect(comfortLabel({ zone: "corners", factor: 1.6, speed_ms: 17.6, lawson: "S",
                          comfort: "unsafe — exceeds the 15 m/s safety criterion" }))
      .toContain("safety criterion");
    expect(comfortLabel(TOWER.zones[1]!)).toBe("D · brisk walking");
  });
});

describe("a bounding box is not a building", () => {
  it("says so when every dimension was derived", () => {
    const b = dimensionBasis(TOWER, {});
    expect(b).toContain("BOUNDING BOX");
    expect(b).toContain("All three dimensions were");
    expect(b).toContain("site and context geometry");
  });

  it("names WHICH ones were derived on a partial form", () => {
    const b = dimensionBasis(TOWER, { height_m: 120 });
    expect(b).toContain("width and depth were");
    expect(b).toContain("BOUNDING BOX");
  });

  it("uses the singular for one derived dimension", () => {
    const b = dimensionBasis(TOWER, { height_m: 120, width_m: 40 });
    expect(b).toContain("depth was");
  });

  it("claims nothing about a bounding box when all three were typed in", () => {
    const b = dimensionBasis(TOWER, { height_m: 120, width_m: 40, depth_m: 30 });
    expect(b).toContain("the dimensions you gave");
    expect(b).not.toContain("BOUNDING BOX");
  });

  it("prints what was actually screened, so a context-inflated box is visible", () => {
    const wide = { ...TOWER, inputs: { ...TOWER.inputs, width_m: 412.5 } };
    expect(dimensionBasis(wide, {})).toContain("412.5");
  });
});

describe("the site wind is the multiplier, so its provenance is stated", () => {
  it("flags the default as a default, not a measurement", () => {
    const w = windBasis(null, 5);
    expect(w).toContain("DEFAULT");
    expect(w).toContain("not a measurement");
    expect(w).toContain("scales directly");
  });

  it("does not cry default when a figure was supplied", () => {
    const w = windBasis(6, 6);
    expect(w).not.toContain("DEFAULT");
    expect(w).toContain("6 m/s");
  });

  it("treats a zero as not supplied — the server substitutes its own floor for it", () => {
    expect(windBasis(0, 5)).toContain("DEFAULT");
  });
});

describe("mitigations are never rendered as a silent blank", () => {
  it("passes the server's list through", () => {
    expect(mitigationLines(TOWER)).toEqual(TOWER.mitigations);
  });

  it("says none is called for when the screen is clean AND complete", () => {
    const full = { ...LOW, inputs: { ...LOW.inputs, gap_m: 60 } };
    expect(mitigationLines(full)[0]).toContain("No mitigation is called for by this screen");
    expect(mitigationLines(full)[0]).toContain("every zone graded");
  });

  it("does NOT report a clean bill over a partial screen", () => {
    // Found in review on PR #529, and it is the file's own load-bearing rule failing one function
    // down: `verdict()` had just called this same result a PARTIAL screen, while this said no
    // mitigation was called for. "Every zone graded A–C" is false on its own terms too — a zone
    // that was never computed was never graded.
    const m = mitigationLines(LOW)[0]!;
    expect(unassessed(LOW)).toHaveLength(1);
    expect(m).toContain("mechanisms this screen DID check");
    expect(m).toContain("did not check");
    expect(m).not.toContain("every zone graded");
  });

  it("flags an EMPTY list on a FAILING screen rather than showing nothing", () => {
    const odd = { ...TOWER, mitigations: [] };
    expect(mitigationLines(odd)[0]).toContain("unexpected");
    expect(mitigationLines(odd)[0]).toContain("wind consultant");
  });
});

/**
 * R38-SYNC-VIEW — the plan pane's pure contract: what cut it asks for, and when it asks again.
 *
 * The refetch rule is the load-bearing one. The pane is meant to be left OPEN while modeling, so a
 * selection change — which happens on every click — must not cost a drawing round-trip. Only a
 * change to the CUT (storey or scale) may. A pane that refetched on selection would be quietly
 * unusable on any real model, and nothing in the UI would say why.
 */
import { describe, expect, it } from "vitest";
import { needsRefetch, planParams } from "./planPane";

describe("planParams — the cut being asked for", () => {
  it("always carries a scale, and the storey only when there is one", () => {
    expect(planParams("Level 1", 100).toString()).toBe("scale=100&storey=Level+1");
    expect(planParams(null, 100).toString()).toBe("scale=100");
  });

  it("carries the scale it was given, not a default", () => {
    expect(planParams("Level 2", 50).get("scale")).toBe("50");
    expect(planParams("Level 2", 200).get("scale")).toBe("200");
  });
});

describe("needsRefetch — only the cut costs a round-trip", () => {
  it("the first look always fetches", () => {
    expect(needsRefetch(null, { storey: "Level 1", scale: 100 })).toBe(true);
  });

  it("the same cut does not re-fetch — this is what makes the pane cheap to leave open", () => {
    const cut = { storey: "Level 1", scale: 100 };
    expect(needsRefetch(cut, { ...cut })).toBe(false);
  });

  it("a storey change re-fetches — the plan IS a cut at a level", () => {
    expect(needsRefetch({ storey: "Level 1", scale: 100 },
                        { storey: "Level 2", scale: 100 })).toBe(true);
  });

  it("a scale change re-fetches — the generator draws different detail per scale", () => {
    expect(needsRefetch({ storey: "Level 1", scale: 100 },
                        { storey: "Level 1", scale: 50 })).toBe(true);
  });

  it("whole-model and a named level are different cuts, in both directions", () => {
    expect(needsRefetch({ storey: null, scale: 100 }, { storey: "Level 1", scale: 100 })).toBe(true);
    expect(needsRefetch({ storey: "Level 1", scale: 100 }, { storey: null, scale: 100 })).toBe(true);
  });
});

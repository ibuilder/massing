import { describe, expect, it } from "vitest";
import { describePlan, planApply, type LockVariable } from "./dimLocks";

/**
 * R38-SOLVER-LOCKS — the mapping from solved scalars to element edits.
 *
 * The solver was never the missing piece; this was. Two behaviours carry the weight:
 *
 *  - **`move_element` takes deltas.** Passing a solved absolute as `dx` moves the element to
 *    `current + target` instead of `target` — plausible geometry in the wrong place, which is the one
 *    way this mapping can produce a wrong model rather than refuse.
 *  - **An unmappable variable is refused BY NAME and the rest still apply.** Silently dropping it
 *    yields a model that looks like it satisfies the locks and does not — the same shape as a reserve
 *    suggestion printed without its verification flag.
 */

const wall = (over: Partial<LockVariable> = {}): LockVariable => ({
  name: "w.thickness", current: 0.2, guid: "G-WALL", ifcClass: "IfcWall", param: "thickness", ...over,
});

describe("dimensional writes go through the existing guid-keyed recipes", () => {
  it("writes a wall thickness as an absolute", () => {
    const p = planApply([wall()], { "w.thickness": 0.3 });
    expect(p.refused).toEqual([]);
    expect(p.writes).toEqual([{
      op: "set_wall_thickness", params: { guid: "G-WALL", thickness: 0.3 },
      variable: "w.thickness", from: 0.2, to: 0.3,
    }]);
  });

  it("writes an extrusion depth on any class", () => {
    const v = wall({ name: "c.depth", param: "depth", ifcClass: "IfcColumn", current: 3, guid: "G-COL" });
    const p = planApply([v], { "c.depth": 4.5 });
    expect(p.writes[0]).toMatchObject({ op: "set_extrusion_depth", params: { guid: "G-COL", depth: 4.5 } });
  });

  it("refuses a thickness on a non-wall rather than writing it somewhere wrong", () => {
    // set_wall_thickness is wall-specific in the recipe table. Sending a column through it is not a
    // no-op server-side, so the refusal has to happen here.
    const v = wall({ ifcClass: "IfcColumn" });
    const p = planApply([v], { "w.thickness": 0.3 });
    expect(p.writes).toEqual([]);
    expect(p.refused[0]!.reason).toContain("only applies to walls");
  });
});

describe("move_element takes DELTAS — the one way this can produce a wrong model", () => {
  it("converts a solved absolute into a delta", () => {
    const v = wall({ name: "w.x", param: "x", current: 10 });
    const p = planApply([v], { "w.x": 13.5 });
    expect(p.writes[0]!.params, "an absolute passed as dx moves to current+target, not target")
      .toEqual({ guid: "G-WALL", dx: 3.5 });
  });

  it("produces a NEGATIVE delta when the target is behind the current value", () => {
    // The paired control. A mapping that passed the absolute through would still look right for a
    // move away from the origin; it only diverges visibly when the delta should be negative.
    const v = wall({ name: "w.y", param: "y", current: 10 });
    const p = planApply([v], { "w.y": 4 });
    expect(p.writes[0]!.params).toEqual({ guid: "G-WALL", dy: -6 });
  });

  it("maps each axis to its own delta key", () => {
    const vars = (["x", "y", "z"] as const).map((ax) =>
      wall({ name: `w.${ax}`, param: ax, current: 0 }));
    const p = planApply(vars, { "w.x": 1, "w.y": 2, "w.z": 3 });
    expect(p.writes.map((w) => w.params)).toEqual([
      { guid: "G-WALL", dx: 1 }, { guid: "G-WALL", dy: 2 }, { guid: "G-WALL", dz: 3 },
    ]);
  });
});

describe("refusals are named, and never silent", () => {
  it("refuses a parameter no recipe writes, and applies the others anyway", () => {
    const ok = wall();
    const bad = wall({ name: "w.area", param: "area" });
    const p = planApply([ok, bad], { "w.thickness": 0.3, "w.area": 12 });
    expect(p.writes).toHaveLength(1);
    expect(p.refused).toEqual([{ variable: "w.area", reason: "no edit recipe writes 'area' on IfcWall" }]);
  });

  it("refuses a variable the solver did not return", () => {
    // Not the same as unchanged. A missing key means the solve did not cover it, and treating that
    // as "nothing to do" reports success for a lock that was never considered.
    const p = planApply([wall()], {});
    expect(p.writes).toEqual([]);
    expect(p.refused[0]!.reason).toContain("no value");
  });

  it("refuses a non-finite value instead of writing NaN into the model", () => {
    const p = planApply([wall()], { "w.thickness": Number.NaN });
    expect(p.writes).toEqual([]);
    expect(p.refused).toHaveLength(1);
  });

  it("says so in the summary — a refusal the user cannot see is a silent drop", () => {
    const p = planApply([wall(), wall({ name: "w.area", param: "area" })],
      { "w.thickness": 0.3, "w.area": 12 });
    const s = describePlan(p);
    expect(s).toContain("Apply 1 change");
    expect(s).toContain("cannot be written");
    expect(s).toContain("w.area");
  });
});

describe("an unchanged variable is not an edit", () => {
  it("emits no write when the solver returns what was already there", () => {
    // A no-op edit still versions the model and triggers a publish, so "I only moved one wall"
    // becomes a reload banner for every other session.
    const p = planApply([wall()], { "w.thickness": 0.2 });
    expect(p.writes).toEqual([]);
    expect(p.refused).toEqual([]);
    expect(describePlan(p)).toBe("Nothing to apply.");
  });

  it("still writes a change just above the epsilon", () => {
    // The paired control: an epsilon that swallowed real edits would pass the test above forever.
    const p = planApply([wall()], { "w.thickness": 0.2 + 1e-3 });
    expect(p.writes).toHaveLength(1);
  });
});

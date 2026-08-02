/**
 * A29-SPATIAL-SELECT — the pure contract: how re-clicking widens, and what each scope selects.
 * The no-storey rule is the one worth pinning hardest: an element the model does not place on a
 * level must NEVER produce a pseudo-level selection that looks like a spatial fact.
 */
import { describe, expect, it } from "vitest";
import { nextScope, scopeSelection } from "./spatialSelect";

const ELEMENTS = [
  { guid: "W1", storey: "Level 1" },
  { guid: "W2", storey: "Level 1" },
  { guid: "S1", storey: "Level 1" },
  { guid: "W3", storey: "Level 2" },
  { guid: "P1", storey: null },          // site proxy — the model assigns it no level
];

describe("nextScope — the click-depth cycle", () => {
  it("item → storey → model → item, when the element has a level", () => {
    expect(nextScope("item", true)).toBe("storey");
    expect(nextScope("storey", true)).toBe("model");
    expect(nextScope("model", true)).toBe("item");
  });

  it("an element with NO level skips straight to model — no invented pseudo-level", () => {
    expect(nextScope("item", false)).toBe("model");
  });
});

describe("scopeSelection — what each scope actually names", () => {
  it("item is just the element", () => {
    expect(scopeSelection("W1", "item", ELEMENTS)).toEqual({ guids: ["W1"], label: "element" });
  });

  it("storey selects EVERY element of that level, labelled with the honest count", () => {
    const s = scopeSelection("W1", "storey", ELEMENTS);
    expect(s.guids.sort()).toEqual(["S1", "W1", "W2"]);
    expect(s.label).toBe("Level 1 — 3 elements");
  });

  it("a storey scope on a level-less element degrades to the element, and says so", () => {
    const s = scopeSelection("P1", "storey", ELEMENTS);
    expect(s.guids).toEqual(["P1"]);
    expect(s.label).toMatch(/no level assigned/);
  });

  it("model selects everything, counted", () => {
    const s = scopeSelection("W1", "model", ELEMENTS);
    expect(s.guids.length).toBe(5);
    expect(s.label).toBe("whole model — 5 elements");
  });

  it("an empty element list never selects nothing — the clicked element survives", () => {
    expect(scopeSelection("W1", "model", []).guids).toEqual(["W1"]);
  });

  it("singular grammar for a one-element level", () => {
    expect(scopeSelection("W3", "storey", ELEMENTS).label).toBe("Level 2 — 1 element");
  });
});

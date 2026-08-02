/**
 * A29-UNDO-LOCAL — the stroke-history contract. The rule worth pinning hardest: a NEW click
 * invalidates the redo branch, because restoring a point from an abandoned timeline would splice
 * it into the middle of the current polyline and draw a wall nobody clicked.
 */
import { describe, expect, it } from "vitest";
import { DraftPointHistory } from "./draftHistory";

describe("DraftPointHistory", () => {
  it("undo pops LIFO and mutates the caller's array — one array, one truth", () => {
    const h = new DraftPointHistory<string>();
    const pts = ["a", "b", "c"];
    expect(h.undo(pts)).toBe("c");
    expect(pts).toEqual(["a", "b"]);
    expect(h.undo(pts)).toBe("b");
    expect(pts).toEqual(["a"]);
  });

  it("redo restores in reverse order of the undos", () => {
    const h = new DraftPointHistory<string>();
    const pts = ["a", "b", "c"];
    h.undo(pts); h.undo(pts);                 // pts = [a], redo = [c, b]
    expect(h.redo(pts)).toBe("b");
    expect(h.redo(pts)).toBe("c");
    expect(pts).toEqual(["a", "b", "c"]);
    expect(h.redo(pts)).toBeNull();           // branch exhausted
  });

  it("a NEW click invalidates the redo branch — no splicing from an abandoned timeline", () => {
    const h = new DraftPointHistory<string>();
    const pts = ["a", "b"];
    h.undo(pts);                              // pts = [a], redo = [b]
    pts.push("x"); h.noteAdded();             // the drafter went a different way
    expect(h.redoDepth).toBe(0);
    expect(h.redo(pts)).toBeNull();
    expect(pts).toEqual(["a", "x"]);
  });

  it("undo on an empty draft is null, not a crash — and must not eat the keystroke's meaning", () => {
    const h = new DraftPointHistory<string>();
    expect(h.undo([])).toBeNull();
  });

  it("clear() ends both directions — commit and disarm discard the draft's history entirely", () => {
    const h = new DraftPointHistory<string>();
    const pts = ["a", "b"];
    h.undo(pts);
    h.clear();
    expect(h.redo(pts)).toBeNull();
    expect(pts).toEqual(["a"]);
  });
});

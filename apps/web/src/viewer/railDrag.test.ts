import { describe, expect, it } from "vitest";
import {
  DRAFT_DRAG_MIME, canAcceptDraftDrag, dropCompletion, readDraftDragKey, setDraftDragKey,
} from "./railDrag";
import { DRAFT_ELEMENTS } from "./draft/draftCatalog";

/**
 * A DataTransfer stub with a switchable **protected mode**, because that is the whole subtlety.
 *
 * The spec exposes `types` in every drag event but blanks `getData()` in all of them except
 * `dragstart` and `drop`. happy-dom's DataTransfer does not model that, so a test written against the
 * real class would pass while the browser silently refused every drop. Modelling it here is the only
 * way this suite can see the bug.
 */
function makeDT(entries: Record<string, string>, protectedMode = false): DataTransfer {
  const store = new Map(Object.entries(entries));
  return {
    // A GETTER, not a snapshot: the real `types` reflects `setData` calls made after construction,
    // and a stub that froze it at construction failed the round-trip test while the code was correct.
    get types() { return [...store.keys()]; },
    getData: (t: string) => (protectedMode ? "" : (store.get(t) ?? "")),
    setData: (t: string, v: string) => { store.set(t, v); },
    effectAllowed: "none",
    dropEffect: "none",
  } as unknown as DataTransfer;
}

describe("RAIL-DRAG — accepting the drag is decided from `types`, never from the payload", () => {
  // The failure this guards is invisible: read the value during dragover, get "" because of
  // protected mode, decide "not ours", skip preventDefault — and the browser refuses the drop with
  // no error. The feature just does nothing.
  it("accepts our drag during dragover even though the payload is unreadable there", () => {
    const dt = makeDT({ [DRAFT_DRAG_MIME]: "wall" }, true);   // protected, as in a real dragover
    expect(dt.getData(DRAFT_DRAG_MIME)).toBe("");             // the trap, made explicit
    expect(canAcceptDraftDrag(dt)).toBe(true);                // and we still accept it
  });

  it("does not accept a file drag — dragging a PDF onto the canvas must not arm a tool", () => {
    expect(canAcceptDraftDrag(makeDT({ Files: "" }, true))).toBe(false);
  });

  it("does not accept plain text dragged in from another app", () => {
    expect(canAcceptDraftDrag(makeDT({ "text/plain": "wall" }, true))).toBe(false);
  });

  it("survives a null or throwing DataTransfer rather than taking the canvas down mid-drag", () => {
    expect(canAcceptDraftDrag(null)).toBe(false);
    const hostile = { get types(): string[] { throw new Error("nope"); } } as unknown as DataTransfer;
    expect(canAcceptDraftDrag(hostile)).toBe(false);
  });
});

describe("RAIL-DRAG — reading the key at drop", () => {
  it("round-trips a catalog key through set → read", () => {
    const dt = makeDT({});
    setDraftDragKey(dt, "steel_column");
    expect(canAcceptDraftDrag(dt)).toBe(true);
    expect(readDraftDragKey(dt)).toBe("steel_column");
  });

  it("marks the drag as a copy, so the cursor says what will happen", () => {
    const dt = makeDT({});
    setDraftDragKey(dt, "wall");
    expect(dt.effectAllowed).toBe("copy");
  });

  it("returns null for a foreign drag rather than a truthy empty string", () => {
    expect(readDraftDragKey(makeDT({ "text/plain": "wall" }))).toBeNull();
    expect(readDraftDragKey(makeDT({ Files: "" }))).toBeNull();
    expect(readDraftDragKey(null)).toBeNull();
  });

  it("returns null for our MIME carrying nothing usable", () => {
    expect(readDraftDragKey(makeDT({ [DRAFT_DRAG_MIME]: "" }))).toBeNull();
    expect(readDraftDragKey(makeDT({ [DRAFT_DRAG_MIME]: "   " }))).toBeNull();
    expect(readDraftDragKey(makeDT({ [DRAFT_DRAG_MIME]: "x".repeat(500) }))).toBeNull();
  });

  it("keeps the namespaced keys the catalog actually uses intact", () => {
    // `mep:` and `family:` keys carry a colon; a parser that split on one would silently truncate.
    for (const key of ["mep:diffuser", "family:0c7f1a2b", "add_wall"]) {
      const dt = makeDT({});
      setDraftDragKey(dt, key);
      expect(readDraftDragKey(dt)).toBe(key);
    }
  });

  it("setDraftDragKey on a null DataTransfer is a no-op, not a throw", () => {
    expect(() => setDraftDragKey(null, "wall")).not.toThrow();
  });
});

describe("RAIL-DRAG — one drop is one point, and it says which elements that finishes", () => {
  it("a single-point element completes on the drop", () => {
    const r = dropCompletion(1, "Column");
    expect(r.completes).toBe(true);
    expect(r.message).toMatch(/placed/i);
  });

  it("a two-point element sets the first point and names the gesture that finishes it", () => {
    const r = dropCompletion(2, "Wall");
    expect(r.completes).toBe(false);
    expect(r.message).toMatch(/first point/i);
    expect(r.message).toMatch(/second point/i);
  });

  it("a poly element says how to close it", () => {
    const r = dropCompletion("poly", "Slab / floor");
    expect(r.completes).toBe(false);
    expect(r.message).toMatch(/double-click/i);
  });

  // Silence after a drop is indistinguishable from a drop that failed.
  it("always returns a message naming the element", () => {
    for (const p of [1, 2, "poly"] as const) {
      expect(dropCompletion(p, "Duct").message).toContain("Duct");
    }
  });

  /**
   * The partition, asserted against the real catalog rather than against three hand-picked cases.
   *
   * `points` is a closed union of 1 | 2 | "poly", and every catalog element must land on exactly one
   * side of "does a drop finish this". A fourth arity added to the catalog with no branch here would
   * otherwise fall through to the poly message and tell the user to double-click something that
   * cannot be closed.
   */
  it("every element in the real catalog gets a verdict, and only points:1 completes", () => {
    expect(DRAFT_ELEMENTS.length).toBeGreaterThan(10);   // not vacuous
    const arities = new Set(DRAFT_ELEMENTS.map((e) => e.points));
    expect([...arities].sort()).toEqual([1, 2, "poly"]); // the union really is closed
    for (const e of DRAFT_ELEMENTS) {
      const r = dropCompletion(e.points, e.label);
      expect(r.message, e.key).toBeTruthy();
      expect(r.completes, `${e.key} (points=${String(e.points)})`).toBe(e.points === 1);
    }
  });

  it("at least one element of each arity exists, so neither branch is dead in practice", () => {
    const byArity = (p: 1 | 2 | "poly") => DRAFT_ELEMENTS.filter((e) => e.points === p).length;
    expect(byArity(1), "no single-point element — the completing branch would be dead").toBeGreaterThan(0);
    expect(byArity(2)).toBeGreaterThan(0);
    expect(byArity("poly")).toBeGreaterThan(0);
  });
});

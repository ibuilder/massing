import { describe, expect, it } from "vitest";

import {
  forStorage,
  isStorable,
  modelIdMapFromRefs,
  refsFromModelIdMap,
  resolveGuids,
  sameElement,
  type ElementRef,
} from "./elementRef";

/** A stand-in for a loaded Fragments model: GlobalId → local id, null when absent. */
function model(table: Record<string, number>) {
  return {
    getLocalIdsByGuids: (guids: string[]) =>
      Promise.resolve(guids.map((g) => (g in table ? table[g]! : null))),
  };
}

const A = "2O2Fr$t4X7Zf8NOew3FLOH";
const B = "1kTvXnbbzCWw8lcMd1dR4o";
const MISSING = "3nOtInAnYmOdEl00000000";

describe("resolving GlobalIds reports what it could NOT resolve", () => {
  it("THE DEFECT: a GlobalId in no loaded model is named, not silently dropped", async () => {
    // `SelectionSets.fromGuids` filters the nulls away, so asking for three elements with one
    // missing returns two and says nothing. The caller cannot tell a partial answer from a complete
    // one, and a shorter selection reads as "the model changed" rather than "the lookup failed".
    const out = await resolveGuids([A, B, MISSING], [["m1", model({ [A]: 10, [B]: 11 })]]);
    expect(out.refs).toHaveLength(2);
    expect(out.unresolved).toEqual([MISSING]);
    expect(out.complete).toBe(false);
  });

  it("a fully resolved set says so, so `complete` is worth checking", async () => {
    const out = await resolveGuids([A, B], [["m1", model({ [A]: 10, [B]: 11 })]]);
    expect(out.complete).toBe(true);
    expect(out.unresolved).toEqual([]);
  });

  it("the same GlobalId in two federated models is AMBIGUOUS, not an error", async () => {
    // Federation makes this normal — the same element can appear in a discipline model and a
    // coordination model. Reporting it lets a caller choose; treating it as a failure would break
    // every federated project, and silently taking the first would be a coin toss.
    const out = await resolveGuids([A], [["arch", model({ [A]: 10 })], ["struct", model({ [A]: 77 })]]);
    expect(out.ambiguous).toEqual([A]);
    expect(out.complete).toBe(true);
    expect(out.refs.map((r) => r.modelId).sort()).toEqual(["arch", "struct"]);
  });

  it("duplicate input GlobalIds are collapsed, so counts mean what they look like", async () => {
    const out = await resolveGuids([A, A, A], [["m1", model({ [A]: 10 })]]);
    expect(out.refs).toHaveLength(1);
  });

  it("empty input resolves completely — nothing was asked for and nothing is missing", async () => {
    const out = await resolveGuids([], [["m1", model({ [A]: 10 })]]);
    expect(out.complete).toBe(true);
    expect(out.refs).toEqual([]);
  });

  it("no loaded models leaves everything unresolved rather than reporting success", async () => {
    const out = await resolveGuids([A], []);
    expect(out.unresolved).toEqual([A]);
    expect(out.complete).toBe(false);
  });
});

describe("the transient handle never reaches storage", () => {
  const ref: ElementRef = { modelId: "m1", globalId: A, localId: 41 };

  it("forStorage drops localId", () => {
    expect(forStorage(ref)).toEqual({ modelId: "m1", globalId: A });
    expect(isStorable(forStorage(ref))).toBe(true);
  });

  it("a ref still carrying a handle is NOT storable", () => {
    // The failure this prevents looks correct for the rest of the session and only surfaces after a
    // re-issue renumbers the handles — by which point the wrong element is already attached.
    expect(isStorable(ref)).toBe(false);
  });

  it("a stored and a live ref for the same element still compare equal", () => {
    expect(sameElement(forStorage(ref), ref)).toBe(true);
  });
});

describe("converting to and from the renderer's ModelIdMap", () => {
  it("round-trips a map through refs and back", () => {
    const map = { m1: new Set([10, 11]), m2: new Set([5]) };
    const guids: Record<string, string> = { "m1:10": A, "m1:11": B, "m2:5": A };
    const { refs, unnameable } = refsFromModelIdMap(map, (m, l) => guids[`${m}:${l}`] ?? null);
    expect(unnameable).toEqual([]);
    expect(modelIdMapFromRefs(refs)).toEqual(map);
  });

  it("geometry with no GlobalId is REPORTED, not dropped", () => {
    // Generated geometry can be drawn and cannot be referenced. Knowing that before somebody tries
    // to pin it is the difference between a clear message and a pin that never comes back.
    const { refs, unnameable } = refsFromModelIdMap({ m1: new Set([10, 99]) },
      (_m, l) => (l === 10 ? A : null));
    expect(refs).toHaveLength(1);
    expect(unnameable).toEqual([{ modelId: "m1", localId: 99 }]);
  });

  it("a ref with no localId cannot be drawn and is left out of the map", () => {
    expect(modelIdMapFromRefs([{ modelId: "m1", globalId: A }])).toEqual({});
  });
});

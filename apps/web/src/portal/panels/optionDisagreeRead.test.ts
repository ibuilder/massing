import { describe, expect, it } from "vitest";
import type { OptionAxis, OptionRecord, OptionRecordSet } from "../../api/types";
import { disagreeBanner, disagreeRows, returnsBasisNote, returnsCell, returnsCellTitle }
  from "./optionDisagreeRead";

const AXES: OptionAxis[] = ["geometry", "unit_mix", "cost", "carbon", "returns"];

const opt = (over: Partial<OptionRecord> & { name: string }): OptionRecord => ({
  id: over.name, state: null,
  axes: { geometry: 50000, unit_mix: 60, cost: 5_000_000, carbon: 400, returns: 32.16 },
  axis_status: { geometry: "present", unit_mix: "present", cost: "present", carbon: "present",
                 returns: "present" },
  carbon_basis: "benchmark", economics_basis: "derived",
  declared_returns: null, returns_agree: null, returns_delta_pct: null,
  missing_axes: [], comparable: true, note: "",
  ...over,
});

/** The two options measured against a live route: one typed nothing, one typed 45.0% against a
 *  solved 32.16%. Before this item both rendered `32.16% · economics: derived`. */
const LINKED = opt({ name: "A — linked" });
const OPTIMISTIC = opt({
  name: "B — optimistic", declared_returns: 45.0, returns_agree: false, returns_delta_pct: 12.84,
});

const set = (over: Partial<OptionRecordSet> = {}): OptionRecordSet => ({
  options: [LINKED, OPTIMISTIC], option_count: 2, comparable_count: 2, incomparable: [],
  axes: AXES,
  declared_disagrees: [{ id: "B — optimistic", name: "B — optimistic", declared_returns: 45.0,
                         derived_returns: 32.16, delta_pct: 12.84 }],
  declared_disagrees_count: 1,
  returns_basis_note: "basis sentence from the engine",
  note: "n", ...over,
});

describe("returnsCell — the two schemes that rendered identically", () => {
  it("DISTINGUISHES them, which is the live defect", () => {
    expect(returnsCell(LINKED)).not.toBe(returnsCell(OPTIMISTIC));
    expect(returnsCell(LINKED)).toBe("32.16%".replace("32.16", "32.2"));
    expect(returnsCell(OPTIMISTIC)).toContain("typed 45.0%");
  });

  it("states the gap in basis points, the unit a deal memo uses", () => {
    expect(returnsCell(OPTIMISTIC)).toContain("+1284 bps");
  });

  it("stays quiet when the typed figure AGREES — printing both would train the reader to skip it", () => {
    const agreeing = opt({ name: "C", declared_returns: 32.2, returns_agree: true,
                           returns_delta_pct: 0.04 });
    expect(returnsCell(agreeing)).toBe("32.2%");
    expect(returnsCell(agreeing)).not.toContain("typed");
  });

  it("stays quiet when there is nothing to compare against", () => {
    expect(returnsCell(LINKED)).not.toContain("typed");
  });

  it("is — for an absent return, which is not zero", () => {
    const none = opt({ name: "D", axes: { ...LINKED.axes, returns: null },
                       economics_basis: "unlinked" });
    expect(returnsCell(none)).toBe("—");
  });

  it("survives a disagreement with no delta recorded", () => {
    const d = opt({ name: "E", declared_returns: 45, returns_agree: false, returns_delta_pct: null });
    expect(returnsCell(d)).toBe("32.2% (typed 45.0%)");
  });

  it("survives a disagreement with no typed figure recorded", () => {
    const d = opt({ name: "F", declared_returns: null, returns_agree: false,
                    returns_delta_pct: 3 });
    expect(returnsCell(d)).toContain("typed ?");
  });

  it("is plain text — design.ts interpolates into innerHTML", () => {
    for (const o of [LINKED, OPTIMISTIC]) expect(returnsCell(o)).not.toMatch(/[<>]/);
  });
});

describe("returnsCellTitle", () => {
  it("names what the number is and what was typed, on a disagreement", () => {
    const t = returnsCellTitle(OPTIMISTIC);
    expect(t).toContain("Solved 32.2%");
    expect(t).toContain("45.0% was typed");
    expect(t).toContain("never used");
  });

  it("says the two agree when they do", () => {
    expect(returnsCellTitle(opt({ name: "C", declared_returns: 32.2, returns_agree: true })))
      .toContain("agrees with it");
  });

  it("says there was nothing to compare rather than implying agreement", () => {
    const t = returnsCellTitle(LINKED);
    expect(t).toContain("Nothing typed");
    expect(t).not.toContain("agrees");
  });

  it("says absent and not zero for a missing figure", () => {
    expect(returnsCellTitle(opt({ name: "D", axes: { ...LINKED.axes, returns: null } })))
      .toContain("not zero");
  });
});

describe("disagreeBanner", () => {
  it("is null when nothing disagrees — a 0 line is a tick for a check nobody ran", () => {
    expect(disagreeBanner(set({ declared_disagrees: [], declared_disagrees_count: 0 }))).toBeNull();
  });

  it("reports the measured case with both figures and the gap", () => {
    const b = disagreeBanner(set())!;
    expect(b).toContain("1 scheme is carrying a typed return");
    expect(b).toContain("B — optimistic");
    expect(b).toContain("45.0% typed");
    expect(b).toContain("32.2% solved");
    expect(b).toContain("+1284 bps");
  });

  it("agrees in number for several, and names the WIDEST", () => {
    const b = disagreeBanner(set({
      declared_disagrees_count: 2,
      declared_disagrees: [
        { id: "x", name: "Narrow", declared_returns: 33, derived_returns: 32.16, delta_pct: 0.84 },
        { id: "y", name: "Wide", declared_returns: 60, derived_returns: 32.16, delta_pct: 27.84 },
      ],
    }))!;
    expect(b).toContain("2 schemes are");
    expect(b).toContain("widest is Wide");
    expect(b).not.toContain("widest is Narrow");
  });

  it("picks the widest by MAGNITUDE, so a pessimistic typed figure is not ranked last", () => {
    // A scheme typed BELOW what its deal solves to is still a scheme quoted off its own model.
    const b = disagreeBanner(set({
      declared_disagrees_count: 2,
      declared_disagrees: [
        { id: "x", name: "Over", declared_returns: 35, derived_returns: 32.16, delta_pct: 2.84 },
        { id: "y", name: "Under", declared_returns: 12, derived_returns: 32.16, delta_pct: -20.16 },
      ],
    }))!;
    expect(b).toContain("widest is Under");
    expect(b).toContain("-2016 bps");
  });

  it("still reports the count when no delta is available to rank by", () => {
    const b = disagreeBanner(set({
      declared_disagrees: [{ id: "x", name: "X", declared_returns: null, derived_returns: null,
                             delta_pct: null }],
    }))!;
    expect(b).toContain("1 scheme is");
    expect(b).not.toContain("widest");
  });

  it("survives a response from a server that predates the field", () => {
    const old = { ...set() } as Record<string, unknown>;
    delete old.declared_disagrees_count; delete old.declared_disagrees;
    expect(disagreeBanner(old as unknown as OptionRecordSet)).toBeNull();
  });
});

describe("disagreeRows", () => {
  it("is empty when nothing disagrees", () => {
    expect(disagreeRows(set({ declared_disagrees: [], declared_disagrees_count: 0 }))).toEqual([]);
  });

  it("formats the measured row", () => {
    expect(disagreeRows(set())[0]).toEqual({
      name: "B — optimistic", typed: "45.0%", solved: "32.2%", delta: "+1284 bps",
    });
  });

  it("orders by magnitude, widest first, and breaks ties by name", () => {
    const rows = disagreeRows(set({
      declared_disagrees: [
        { id: "a", name: "Zeta", declared_returns: 35, derived_returns: 32, delta_pct: 3 },
        { id: "b", name: "Wide", declared_returns: 60, derived_returns: 32, delta_pct: 28 },
        { id: "c", name: "Alpha", declared_returns: 35, derived_returns: 32, delta_pct: 3 },
      ],
    }));
    expect(rows.map((x) => x.name)).toEqual(["Wide", "Alpha", "Zeta"]);
  });

  it("renders a missing figure as — rather than NaN", () => {
    const r = disagreeRows(set({
      declared_disagrees: [{ id: "x", name: "X", declared_returns: null, derived_returns: null,
                             delta_pct: null }],
    }))[0]!;
    expect(r).toEqual({ name: "X", typed: "—", solved: "—", delta: "—" });
  });

  it("survives a server that predates the field", () => {
    const old = { ...set() } as Record<string, unknown>;
    delete old.declared_disagrees;
    expect(disagreeRows(old as unknown as OptionRecordSet)).toEqual([]);
  });
});

describe("returnsBasisNote", () => {
  it("passes the engine's sentence through rather than restating it", () => {
    expect(returnsBasisNote(set())).toBe("basis sentence from the engine");
  });

  it("is empty, not undefined, on a server that predates it", () => {
    const old = { ...set() } as Record<string, unknown>;
    delete old.returns_basis_note;
    expect(returnsBasisNote(old as unknown as OptionRecordSet)).toBe("");
  });
});

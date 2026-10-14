/** COMPTIER-DARK — the readings the card makes, asserted without a DOM.
 *
 *  `services/api/test_cre_deal_desk.py` and `services/api/test_comp_tier_sources.py` cover the
 *  engine: the ladder agrees with the register's own `source` options, the band is a subset and
 *  names what it left out, and `conflicts_resolved` is field-scoped. This file covers the
 *  consumer, which is where every one of this session's comparable defects actually lived — *the
 *  engine was careful and the screen dropped the care.*
 */
import { describe, expect, it } from "vitest";
import type { TieredCompBand, TieredComps } from "../api/creDeal";
import {
  FIELDS, WEAK_FROM_TIER, bandHeadline, bandRow, blankNote, conflictNote, conflictRows,
  excludedNote, fieldSpec, setState, tierMix, unattributedNote, weakFrom,
} from "./compTierRead";

/** The engine's ladder, in the engine's order — the shape `from_project` publishes. */
const LADDER: TieredComps["ladder"] = [
  { tier: "recorded_sale", label: "Recorded sale", rank: 1 },
  { tier: "verified", label: "Party-verified", rank: 2 },
  { tier: "confirmed", label: "Vendor-confirmed", rank: 3 },
  { tier: "estimate", label: "Vendor estimate", rank: 4 },
  { tier: "listing", label: "Listing / asking", rank: 5 },
  { tier: "broker", label: "Broker package", rank: 6 },
  { tier: "unknown", label: "Unattributed", rank: 7 },
];

const band = (over: Partial<TieredCompBand> = {}): TieredCompBand => ({
  field: "price_psf", n: 3, of_comps: 3,
  without_value: { count: 0, comps: [], truncated: false },
  conflicts_resolved: 0, conflicts_in_set: 0,
  median: 210, p25: 207.5, p75: 235, min: 205, max: 260,
  worst_tier: "verified", worst_tier_label: "Party-verified", worst_rank: 2,
  best_tier: "recorded_sale", best_rank: 1,
  tier_counts: { recorded_sale: 1, verified: 2 }, unattributed: 0,
  note: "Band rests on 3 of 3 comp(s); the weakest contributing source is 'Party-verified'. "
      + "Strengthen that source before the number carries a decision.",
  ...over,
});

const set = (over: Partial<TieredComps> = {}): TieredComps => ({
  comps: [], comp_count: 3, conflicts: [], conflict_count: 0, note: "set note",
  ladder: LADDER, statistics: { price_psf: band() }, requested: band(),
  excluded_comparables: [], ...over,
});

describe("the weak-tier threshold is read from the ladder, never restated", () => {
  it("resolves WEAK_FROM_TIER against the response's own ranks", () => {
    expect(weakFrom(LADDER)).toBe(5);
    expect(LADDER.find((l) => l.tier === WEAK_FROM_TIER)?.rank).toBe(5);
  });

  it("fails to the WARNING side when the ladder no longer names that tier", () => {
    // A renamed or reordered ladder is one this file cannot interpret, and the safe reading of a
    // source hierarchy it cannot interpret is "do not rely on this band yet". The opposite default
    // blesses every band on the day somebody renames a tier — and nothing would go red, because
    // every assertion here would still pass against a stale integer.
    expect(weakFrom(LADDER.filter((l) => l.tier !== WEAK_FROM_TIER))).toBe(0);
    const h = bandHeadline(band({ worst_rank: 1, worst_tier: "recorded_sale" }),
                           LADDER.filter((l) => l.tier !== WEAK_FROM_TIER));
    expect(h.tone).toBe("warn");
  });

  it("a band on a recorded sale with full coverage is good, and on a listing is not", () => {
    expect(bandHeadline(band({ worst_rank: 1 }), LADDER).tone).toBe("good");
    expect(bandHeadline(band({ worst_rank: 5, worst_tier: "listing" }), LADDER).tone).toBe("warn");
    expect(bandHeadline(band({ worst_rank: 7, worst_tier: "unknown" }), LADDER).tone).toBe("warn");
  });
});

describe("the headline is the COVERAGE, not the median", () => {
  it("names n of of_comps, because n alone is not the coverage", () => {
    const h = bandHeadline(band({ n: 3, of_comps: 5,
      without_value: { count: 2, comps: [], truncated: false } }), LADDER);
    expect(h.text).toContain("3 of 5 comp(s)");
    expect(h.text).toContain("2 left blank");
    expect(h.tone).toBe("warn");
  });

  it("carries the weakest contributing source in the headline itself", () => {
    expect(bandHeadline(band(), LADDER).text).toContain("Party-verified");
  });

  it("an empty band is CRITICAL and says the gap is in the register, not in the market", () => {
    const h = bandHeadline(band({
      n: 0, of_comps: 4, median: null, worst_tier: null, worst_rank: undefined,
      p25: undefined, p75: undefined, min: undefined, max: undefined, note: undefined,
      tier_counts: undefined, unattributed: undefined,
      reason: "no comp carries a price_psf value",
      without_value: { count: 4, comps: [], truncated: false },
    }), LADDER);
    expect(h.tone).toBe("crit");
    expect(h.text).toContain("No band");
    expect(h.text).toContain("4 comp(s) are on file");
    // The distinction this card exists for, one level down: a blank field is a data-entry gap.
    expect(h.text).toContain("gap in the register");
  });

  it("full coverage on a strong source says nothing alarming", () => {
    const h = bandHeadline(band(), LADDER);
    expect(h.tone).toBe("good");
    expect(h.text).not.toContain("left blank");
  });
});

describe("the band renders in its FIELD's own units", () => {
  it("a $/SF band uses the rate helper, cents kept", () => {
    const r = bandRow(band({ field: "price_psf", median: 4.25, p25: 4, p75: 5, min: 4, max: 5 }));
    expect(r?.cells.find(([k]) => k === "median")?.[1]).toBe("$4.25");
  });

  it("a cap rate is a PERCENT and must not go through a currency helper", () => {
    const r = bandRow(band({ field: "cap_rate", median: 6.2, p25: 6, p75: 6.4, min: 6, max: 6.4 }));
    expect(r?.cells.find(([k]) => k === "median")?.[1]).toBe("6.20%");
    expect(r?.cells.find(([k]) => k === "median")?.[1]).not.toContain("$");
  });

  it("returns null rather than a row of em-dashes when there is no band", () => {
    // A row of dashes reads as a market whose numbers all happen to be missing, which is the
    // empty-versus-zero confusion the engine is otherwise careful about.
    expect(bandRow(band({ n: 0, median: null }))).toBeNull();
    expect(bandRow(band({ median: null }))).toBeNull();
  });

  it("every FIELD the engine bands has a spelling here", () => {
    // The engine builds `statistics` by comprehension over exactly these three keys. A fourth added
    // there without one here would render under its raw key.
    expect(FIELDS.map((f) => f.key)).toEqual(["price_psf", "cap_rate", "rent_psf"]);
    expect(fieldSpec("price_psf").label).toBe("$/SF");
    // An unknown field degrades to its own name rather than throwing.
    expect(fieldSpec("gba").label).toBe("gba");
    expect(fieldSpec("gba").fmt(12)).toBe("12");
  });
});

describe("the tier mix is rendered in the ladder's order, not the dict's", () => {
  it("orders by rank and drops the empty tiers", () => {
    const m = tierMix(band({ tier_counts: { unknown: 1, recorded_sale: 2, confirmed: 1 } }), LADDER);
    expect(m.map((x) => x.tier)).toEqual(["recorded_sale", "confirmed", "unknown"]);
    expect(m.map((x) => x.count)).toEqual([2, 1, 1]);
    // Seven rows mostly reading 0 buries the two that carry the band.
    expect(m).toHaveLength(3);
  });

  it("marks the weak tiers from the ladder's ranks", () => {
    const m = tierMix(band({ tier_counts: { recorded_sale: 1, listing: 1, unknown: 1 } }), LADDER);
    expect(m.map((x) => x.weak)).toEqual([false, true, true]);
  });

  it("is empty, not undefined, on a band with no tier counts", () => {
    expect(tierMix(band({ tier_counts: undefined }), LADDER)).toEqual([]);
  });
});

describe("what the band left out is NAMED", () => {
  it("names the comps with the field blank", () => {
    const n = blankNote(band({ without_value: { count: 2, truncated: false, comps: [
      { address: "400 Pine Ct", source: "CoStar", tier: "confirmed" },
      { address: "500 Ash Way", source: "Other", tier: "unknown" }] } }));
    expect(n).toContain("400 Pine Ct");
    expect(n).toContain("500 Ash Way");
    expect(n).toContain("in the register and out of this band");
  });

  it("says so when the NAMES are capped and the count is not", () => {
    // CLASH-TRUNC, one more time: a consumer handed a page and told it is a total treats it as one.
    const n = blankNote(band({ without_value: { count: 41, truncated: true, comps: [
      { address: "1 A St", source: null, tier: "unknown" }] } }));
    expect(n).toContain("41 comp(s)");
    expect(n).toContain("the count is exact");
  });

  it("is silent when nothing was left out", () => {
    expect(blankNote(band())).toBeNull();
  });

  it("renders an unnamed comp as such rather than as an empty gap", () => {
    const n = blankNote(band({ without_value: { count: 1, truncated: false,
      comps: [{ address: null, source: null, tier: "unknown" }] } }));
    expect(n).toContain("(unnamed)");
  });
});

describe("unattributed is a different fact from weak", () => {
  it("fires only when the band actually rests on an unattributed comp", () => {
    expect(unattributedNote(band({ unattributed: 0 }))).toBeNull();
    expect(unattributedNote(band({ unattributed: undefined }))).toBeNull();
    expect(unattributedNote(band({ unattributed: 1, n: 3 }))).toContain("1 of the 3 comp(s)");
  });

  it("a weak-but-attributed band gets no unattributed note", () => {
    // A `Broker package` band is weak and perfectly traceable; conflating the two would make the
    // note fire on a source somebody can go and check.
    const b = band({ worst_tier: "broker", worst_rank: 6, unattributed: 0,
                     tier_counts: { broker: 3 } });
    expect(unattributedNote(b)).toBeNull();
    expect(bandHeadline(b, LADDER).tone).toBe("warn");
  });
});

describe("the tie-break count is scoped to the field, and says so", () => {
  it("reports zero-for-this-field without hiding the register's count", () => {
    // The defect, from the consumer's side: a one-comp rent band reporting `1 conflict resolved`
    // for a disagreement about $/SF at a different address.
    const n = conflictNote(band({ field: "rent_psf", n: 1, conflicts_resolved: 0,
                                  conflicts_in_set: 1 }));
    expect(n).toContain("none of them about Rent $/SF/yr");
    expect(n).toContain("1 address conflict");
    expect(n).toContain("no number in this band is the survivor");
  });

  it("reports the field's own share when there is one", () => {
    expect(conflictNote(band({ conflicts_resolved: 1, conflicts_in_set: 2 })))
      .toContain("1 of 2 address conflict(s)");
  });

  it("is silent on a register with no conflicts at all", () => {
    expect(conflictNote(band({ conflicts_resolved: 0, conflicts_in_set: 0 }))).toBeNull();
  });
});

describe("the overruled values stay visible", () => {
  it("renders kept-over-outranked per field, in that field's units", () => {
    const rows = conflictRows(set({ conflicts: [{
      address: "100 Main St", kept_tier: "recorded_sale",
      outranked: [{ tier: "broker", source: "Broker" }],
      value_deltas: [
        { field: "price_psf", kept: 210, outranked: 250,
          kept_tier: "recorded_sale", outranked_tier: "broker" },
        { field: "cap_rate", kept: 6.2, outranked: 5.5,
          kept_tier: "recorded_sale", outranked_tier: "broker" }],
    }] }));
    expect(rows).toHaveLength(1);
    expect(rows[0]!.kept).toBe("recorded_sale");
    expect(rows[0]!.outranked).toBe("broker (Broker)");
    expect(rows[0]!.deltas[0]).toBe("$/SF: kept $210 over $250 (broker)");
    // The cap rate delta must NOT be spelled as money.
    expect(rows[0]!.deltas[1]).toBe("Cap rate: kept 6.20% over 5.50% (broker)");
  });

  it("survives an outranked row with no source text", () => {
    const rows = conflictRows(set({ conflicts: [{
      address: null, kept_tier: "verified",
      outranked: [{ tier: "unknown", source: null }], value_deltas: [] }] }));
    expect(rows[0]!.address).toBe("(unnamed)");
    expect(rows[0]!.outranked).toBe("unknown");
    expect(rows[0]!.deltas).toEqual([]);
  });
});

describe("the appraiser's exclusions are a decision, not a thinner market", () => {
  it("names them with their refs and says the sample was ruled down", () => {
    const n = excludedNote(set({ comp_count: 3, excluded_comparables: [
      { id: "x1", ref: "CMP-004", reason: "excluded by the appraiser" },
      { id: "x2", ref: null, reason: "excluded by the appraiser" }] }));
    expect(n).toContain("CMP-004");
    expect(n).toContain("x2");                 // falls back to the id when there is no ref
    expect(n).toContain("3 comp(s) because somebody decided so");
  });

  it("is silent when nothing was excluded, including when the key is absent", () => {
    expect(excludedNote(set())).toBeNull();
    expect(excludedNote({ ...set(), excluded_comparables: undefined as never })).toBeNull();
  });
});

describe("an empty register and an all-excluded register do not render the same", () => {
  it("an empty register asks for comps AND for their sources", () => {
    const s = setState(set({ comp_count: 0 }));
    expect(s?.empty).toBe(true);
    // The source is not optional metadata here — it is what decides a tie.
    expect(s?.text).toContain("Source");
  });

  it("an all-excluded register says the contents were ruled out", () => {
    const s = setState(set({ comp_count: 0, excluded_comparables: [
      { id: "x", ref: "CMP-001", reason: "excluded by the appraiser" }] }));
    expect(s?.empty).toBe(false);
    expect(s?.text).toContain("ruled out");
  });

  it("is null — not a state — once there is anything to band", () => {
    expect(setState(set({ comp_count: 1 }))).toBeNull();
  });
});

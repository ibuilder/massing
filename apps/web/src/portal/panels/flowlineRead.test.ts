/** FLOW-CLEAR — "whether anyone is in anyone's way", which the card promised and never answered.
 *
 *  Every fixture is a measured response. The clean and converging ones come from the same project
 *  shape with the trade durations swapped; the crossing one needs a negative `buffer_days`, which
 *  the adapter cannot yet request (FLOW-BUFFER) and which was measured directly against
 *  `massingplan/core/locations.compute`.
 */
import { describe, expect, it } from "vitest";
import type { FlowlineResult } from "../../api/schedule";
import {
  TONE_CSS, bufferNote, clearanceVerdict, flowIssueRows, flowUnavailableExtras, handoverRows,
  populationNote,
} from "./flowlineRead";

const fl = (over: Partial<FlowlineResult> = {}): FlowlineResult => ({
  available: true,
  locations: [{ id: "L01", name: "Level 1", sequence: 1 },
              { id: "L02", name: "Level 2", sequence: 2 },
              { id: "L03", name: "Level 3", sequence: 3 }],
  trades: ["Carpentry", "Mechanical"],
  duration_days: 32,
  continuity_cost_days: { Carpentry: 0, Mechanical: 0 },
  segments: [],
  interference_count: 1,
  converging_count: 0,
  interferences: [{ predecessor_id: "Carpentry", successor_id: "Mechanical",
                    location_id: "L01", gap_days: 0, converging: false }],
  issues: [],
  ...over,
});

/** Measured: the successor is faster and catches up by the top floor. */
const CONVERGING = fl({
  converging_count: 1,
  interferences: [{ predecessor_id: "Carpentry", successor_id: "Mechanical",
                    location_id: "L04", gap_days: 0, converging: true }],
});

/** Measured against the engine with `buffer_days: -3`. */
const CROSSING = fl({
  interferences: [{ predecessor_id: "Carpentry", successor_id: "Mechanical",
                    location_id: "L02", gap_days: -3, converging: false }],
  issues: [{ severity: "error", code: "LOB.OVERLAP",
             message: "Mechanical starts 3 days before Carpentry finishes in L02",
             action: "the buffer is negative, so the two trades share the space",
             table: null, row_key: "Mechanical", field: "buffer_days", raw_value: null }],
});

describe("the card's own promise is answered", () => {
  it("names the trades sharing the space, where, and by how many days", () => {
    const v = clearanceVerdict(CROSSING);
    expect(v?.tone).toBe("crit");
    expect(v?.text).toContain("1 of 1 handover(s) share the space");
    expect(v?.text).toContain("Mechanical starts 3 day(s) before Carpentry finishes in L02");
  });

  it("warns on a CONVERGING handover and says why it matters", () => {
    // The engine: "a slip in the predecessor is felt immediately at the far end, and it is
    // invisible on a bar chart." That is the sentence a line-of-balance view exists for.
    const v = clearanceVerdict(CONVERGING);
    expect(v?.tone).toBe("warn");
    expect(v?.text).toContain("CONVERGING");
    expect(v?.text).toContain("felt immediately at the far end");
    expect(v?.text).toContain("Carpentry → Mechanical at L04");
  });

  it("crossing outranks converging when both are present", () => {
    const v = clearanceVerdict(fl({ interferences: [
      { predecessor_id: "A", successor_id: "B", location_id: "L01", gap_days: -1, converging: false },
      { predecessor_id: "B", successor_id: "C", location_id: "L03", gap_days: 0, converging: true }] }));
    expect(v?.tone).toBe("crit");
  });

  it("says so affirmatively when every line holds its clearance", () => {
    const v = clearanceVerdict(fl());
    expect(v?.tone).toBe("good");
    expect(v?.text).toContain("hold their clearance");
    expect(v?.text).toContain("no trade catches the one in front");
  });

  it("explains a single-trade schedule rather than reporting it clean", () => {
    // One trade has no handover, so "no interference" would be true and uninformative.
    const v = clearanceVerdict(fl({ trades: ["Carpentry"], interferences: [] }));
    expect(v?.tone).toBe("");
    expect(v?.text).toContain("no handover to interfere with");
  });

  it("is null when nothing was computed, and against a server sending no interferences", () => {
    expect(clearanceVerdict(fl({ available: false }))).toBeNull();
    // An older server: two trades but no per-pair records. Saying "clear" would be a claim the
    // response does not support.
    expect(clearanceVerdict(fl({ interferences: undefined }))).toBeNull();
  });
});

describe("the count is named for what it measures", () => {
  it("says the figure is a population, not a finding", () => {
    // THE TRAP: `interference_count` is `trades.length - 1`. Rendering it as a tile would alarm
    // every reader of a perfectly coordinated schedule.
    const n = populationNote(fl());
    expect(n).toContain("1 handover(s) examined");
    expect(n).toContain("not a count of problems");
  });

  it("is silent when there is nothing to describe", () => {
    expect(populationNote(fl({ interferences: [] }))).toBeNull();
    expect(populationNote(fl({ available: false }))).toBeNull();
  });
});

describe("the zero-buffer caveat explains every 0d row", () => {
  it("fires when EVERY clearance is zero, which is the normal result today", () => {
    const n = bufferNote(fl());
    expect(n).toContain("computed with no buffer between trades");
    expect(n).toContain("cannot be requested through this view yet");
  });

  it("is silent as soon as any clearance is non-zero", () => {
    // Otherwise the caveat would contradict the number beside it.
    expect(bufferNote(CROSSING)).toBeNull();
    expect(bufferNote(fl({ interferences: [
      { predecessor_id: "A", successor_id: "B", location_id: "L01", gap_days: 2,
        converging: false }] }))).toBeNull();
  });

  it("is silent with no handovers at all", () => {
    expect(bufferNote(fl({ interferences: [] }))).toBeNull();
    expect(bufferNote(fl({ interferences: undefined }))).toBeNull();
  });
});

describe("each handover is a row in flow order", () => {
  it("renders the pair, the binding location, the clearance and the trend", () => {
    expect(handoverRows(CONVERGING)).toEqual([
      { pair: "Carpentry → Mechanical", at: "L04", clearance: "0d", trend: "catching up",
        tone: "warn" }]);
  });

  it("spells a negative clearance as an OVERLAP, not as a minus sign to parse", () => {
    expect(handoverRows(CROSSING)[0]).toEqual(
      { pair: "Carpentry → Mechanical", at: "L02", clearance: "3d OVERLAP", trend: "holding",
        tone: "crit" });
  });

  it("is empty against a server that sends no interferences", () => {
    expect(handoverRows(fl({ interferences: undefined }))).toEqual([]);
  });
});

describe("the engine's issue log reaches this screen too", () => {
  it("renders LOB.OVERLAP with the action the engine took", () => {
    const rows = flowIssueRows(CROSSING);
    expect(rows[0]!.code).toBe("LOB.OVERLAP");
    expect(rows[0]!.text).toContain("the two trades share the space");
    expect(rows[0]!.tone).toBe("crit");
  });

  it("orders error before warning before info", () => {
    const i = CROSSING.issues![0]!;
    expect(flowIssueRows(fl({ issues: [
      { ...i, severity: "info", code: "I" }, { ...i, severity: "error", code: "E" },
      { ...i, severity: "warning", code: "W" }] })).map((r) => r.code))
      .toEqual(["E", "W", "I"]);
  });

  it("is empty, not undefined, when the server sends none", () => {
    expect(flowIssueRows(fl({ issues: undefined }))).toEqual([]);
  });
});

describe("a refusal carries what the engine DID find", () => {
  it("names the locations and trades it saw", () => {
    const n = flowUnavailableExtras(fl({ available: false,
      reason: "the schedule's locations could not be arranged into a flow" }));
    expect(n).toContain("Level 1 · Level 2 · Level 3");
    expect(n).toContain("Carpentry · Mechanical");
  });

  it("falls back to the location id when it has no name", () => {
    expect(flowUnavailableExtras(fl({ available: false, trades: [],
      locations: [{ id: "L09", name: "", sequence: 1 }] }))).toContain("L09");
  });

  it("is null for an available result and for a refusal with nothing found", () => {
    expect(flowUnavailableExtras(fl())).toBeNull();
    expect(flowUnavailableExtras(fl({ available: false, locations: [], trades: [] }))).toBeNull();
  });
});

describe("the tone tokens are literal", () => {
  it("names properties the stylesheets define", () => {
    expect(TONE_CSS.crit).toBe("var(--status-crit)");
    expect(TONE_CSS.good).toBe("var(--status-good)");
    expect(TONE_CSS[""]).toBe("");
  });
});

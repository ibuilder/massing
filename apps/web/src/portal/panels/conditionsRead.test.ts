/** COND-REFUSED — a DENIED approval must not render as a satisfied one.
 *
 *  The defect, stated as the row it produced: a refused entitlement carrying five conditions came
 *  out of `services/api/src/aec_api/approval_conditions.py` with `status: "refused"`,
 *  `open_count: 0`, `unparsed_count: 0` and its five conditions intact — and the card's loop
 *  printed `` `${ref} — ${open_count} open` ``, i.e. **`ENT-003 — 0 open`**. The engine's zeroing
 *  was correct; the consumer read it as compliance.
 */
import { describe, expect, it } from "vitest";
import type { EntitlementConditions } from "../../api/types";
import {
  STATUS_REFUSED, entitlementRows, headline, reconciles, refusedNote,
} from "./conditionsRead";

type Ent = EntitlementConditions["entitlements"][number];

const cond = (seq: number, status = "open"): Ent["conditions"][number] => ({
  seq, text: `condition ${seq}`, topic: null, quantities: [], status, note: "",
});

const ent = (over: Partial<Ent> = {}): Ent => ({
  entitlement_id: "e1", ref: "ENT-001", workflow_state: "approved", status: "tracked",
  open_count: 2, unparsed_count: 0, discharged_count: 0, fully_discharged: false, note: "",
  conditions: [cond(1), cond(2)], ...over,
});

const read = (over: Partial<EntitlementConditions> = {}): EntitlementConditions => ({
  project_id: "p", unrecorded: [], note: "", entitlements: [ent()],
  entitlement_count: 1, live_count: 1, refused: [], total_open: 2, total_unparsed: 0, ...over,
});

/** The exact shape `assess()` returns for a DENIED entitlement — counts zeroed, conditions kept. */
const refusedEnt = ent({
  entitlement_id: "e3", ref: "ENT-003", workflow_state: "denied", status: STATUS_REFUSED,
  open_count: 0, unparsed_count: 0, discharged_count: 0, fully_discharged: false,
  conditions: [cond(1), cond(2), cond(3), cond(4), cond(5)],
  note: "this entitlement was DENIED…",
});

describe("a refused entitlement never reads as a satisfied one", () => {
  it("is labelled REFUSED, with its condition count, and never as a count of zero", () => {
    const rows = entitlementRows(read({ entitlements: [refusedEnt] }));
    expect(rows).toHaveLength(1);
    expect(rows[0]!.text).toContain("REFUSED");
    expect(rows[0]!.text).toContain("denied");
    expect(rows[0]!.text).toContain("5 condition(s) on file");
    // THE REGRESSION, pinned as the exact string the old loop produced for this row. Asserting
    // only that "REFUSED" is present would still pass a row reading `ENT-003 — 0 open · REFUSED`,
    // and the defect is that the reassuring half is there at all.
    expect(rows[0]!.text).not.toBe("ENT-003 — 0 open");
    expect(rows[0]!.text).not.toContain("0 open");
  });

  it("carries a CRITICAL tone — a denial is not a discharged obligation", () => {
    expect(entitlementRows(read({ entitlements: [refusedEnt] }))[0]!.tone).toBe("crit");
  });

  it("is listed even when it is the ONLY entitlement on file", () => {
    // Otherwise a project whose single approval was refused shows an empty card, which reads as
    // "nothing to worry about" on the one register where it certainly is not.
    const rows = entitlementRows(read({ entitlements: [refusedEnt], live_count: 0,
                                        entitlement_count: 1 }));
    expect(rows).toHaveLength(1);
  });

  it("is listed with no condition clause when the agency's terms were never typed", () => {
    const rows = entitlementRows(read({
      entitlements: [{ ...refusedEnt, conditions: [] }] }));
    expect(rows[0]!.text).toContain("REFUSED");
    expect(rows[0]!.text).not.toContain("condition(s) on file");
  });
});

describe("the refusal note says why those conditions count zero", () => {
  it("names each refused entitlement with its condition count", () => {
    const n = refusedNote(read({ refused: [
      { ref: "ENT-003", workflow_state: "denied", condition_count: 5 },
      { ref: "ENT-004", workflow_state: "denied", condition_count: 0 }] }));
    expect(n).toContain("2 refused");
    expect(n).toContain("ENT-003 (5 condition(s))");
    expect(n).toContain("ENT-004");
    expect(n).not.toContain("ENT-004 (0 condition(s))");   // a zero clause is noise
    expect(n).toContain("appeal puts them back in play");
    expect(n).toContain("NOT part of the open total");
  });

  it("is silent when nothing was refused, and when the key is absent", () => {
    // An always-on paragraph is one its reader learns to skip — the way COMPTIER-DARK's
    // weakest-source qualifier was defeated by firing on every band.
    expect(refusedNote(read())).toBeNull();
    expect(refusedNote(read({ refused: undefined }))).toBeNull();
  });
});

describe("the headline carries the population its totals cover", () => {
  it("names live of total when they differ", () => {
    expect(headline(read({ total_open: 2, total_unparsed: 1, live_count: 3,
                           entitlement_count: 5 })))
      .toBe("2 open · 1 unparsed across 3 of 5 entitlement(s)");
  });

  it("names one figure when nothing was refused, rather than '5 of 5'", () => {
    expect(headline(read({ live_count: 5, entitlement_count: 5 })))
      .toContain("across 5 entitlement(s)");
  });

  it("degrades to no scope at all against a server that does not send live_count", () => {
    // An unanswerable question is not a failed one: an older server gets the old sentence rather
    // than `across undefined of 5`.
    const h = headline(read({ live_count: undefined }));
    expect(h).toBe("2 open · 0 unparsed");
    expect(h).not.toContain("undefined");
  });

  it("still appends the unrecorded clause", () => {
    expect(headline(read({ unrecorded: ["ENT-009"] })))
      .toContain("1 approved with no conditions recorded");
  });
});

describe("the denominator is checked, not trusted", () => {
  it("reconciles when live + refused === total", () => {
    expect(reconciles(read({ live_count: 3, entitlement_count: 5, refused: [
      { ref: "a", workflow_state: "denied", condition_count: 0 },
      { ref: "b", workflow_state: "denied", condition_count: 0 }] }))).toBe(true);
  });

  it("reports false when it does not — the denominator is the thing that misleads", () => {
    expect(reconciles(read({ live_count: 3, entitlement_count: 5, refused: [] }))).toBe(false);
  });

  it("is null, not false, when a key needed to check it is missing", () => {
    expect(reconciles(read({ live_count: undefined }))).toBeNull();
    expect(reconciles(read({ entitlement_count: undefined }))).toBeNull();
    expect(reconciles(read({ refused: undefined }))).toBeNull();
  });
});

describe("the other statuses keep behaving as they did", () => {
  it("a tracked row shows open, unparsed and discharged", () => {
    const rows = entitlementRows(read({ entitlements: [ent({
      open_count: 1, unparsed_count: 2, discharged_count: 3,
      conditions: [cond(1), cond(2), cond(3), cond(4), cond(5), cond(6)] })] }));
    expect(rows[0]!.text).toBe("ENT-001 — 1 open, 2 unparsed, 3 discharged");
    // Unparsed outranks open: a condition nobody could read has not been assessed at all.
    expect(rows[0]!.tone).toBe("warn");
  });

  it("a fully discharged row says so and is not warned about", () => {
    const rows = entitlementRows(read({ entitlements: [ent({
      open_count: 0, discharged_count: 2, fully_discharged: true })] }));
    expect(rows[0]!.text).toContain("fully discharged");
    expect(rows[0]!.tone).toBe("");
  });

  it("an entitlement with no conditions is skipped here — the `unrecorded` line covers it", () => {
    expect(entitlementRows(read({ entitlements: [ent({ status: "unrecorded", conditions: [],
                                                       open_count: 0 })] }))).toEqual([]);
  });

  it("falls back to the id when there is no ref", () => {
    expect(entitlementRows(read({ entitlements: [ent({ ref: null })] }))[0]!.ref).toBe("e1");
  });
});

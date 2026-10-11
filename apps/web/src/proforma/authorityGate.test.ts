import { describe, expect, it } from "vitest";

import { FACT_TYPES } from "./authorityCard";
import {
  FACT_DEPENDENCIES, declaredFacts, gateFor, gateNote, withholds,
} from "./authorityGate";

/**
 * AUTHORITY-DOWNSTREAM. The engine says required facts "BLOCK downstream analysis — the point is to
 * stop the work, not to annotate it after the fact", and every CRE card computed regardless.
 *
 * The load-bearing test here is the FIRST one, not the behaviour: the dependency map is prose unless
 * something pins its vocabulary to the engine's. Rename a fact type on the Python side and a map
 * naming the old spelling silently stops blocking the card that depends on it — and the card still
 * calls `gateFor`, so it looks wired. *A map keyed on strings nobody checks is a comment.*
 */
const READ = (over: Record<string, unknown> = {}) => ({
  entries: [{ fact_type: "rent_roll", document: "RR.xlsx", as_of: "2026-09-01",
              authoritative: true, freshness_days: 45, supersedes: [] }],
  gate: { passes: true, blocking: [], advisory: [] },
  ...over,
});

describe("the dependency map is pinned to the engine's vocabulary", () => {
  it("every fact type it names exists in FACT_TYPES", () => {
    const known = new Set(FACT_TYPES.map(([k]) => k));
    const unknown = declaredFacts().filter((f) => !known.has(f));
    expect(unknown).toEqual([]);
  });

  it("and the map is not empty, so the check above cannot pass by having nothing to check", () => {
    expect(declaredFacts().length).toBeGreaterThanOrEqual(3);
    expect(Object.keys(FACT_DEPENDENCIES).length).toBeGreaterThanOrEqual(4);
  });

  it("residual land is deliberately NOT in it, and the TYPE now says so", () => {
    // `POST /proforma/residual-land` takes `Assumptions` and nothing else, so it consumes no
    // governed fact. The roadmap entry listed it; wiring it would have invented a dependency, and
    // a block nobody can act on teaches the reader to dismiss the ones they can.
    //
    // This started as `expect(FACT_DEPENDENCIES["residual_land"]).toBeUndefined()`, a runtime
    // check. Once the map became `as const satisfies`, that line stopped COMPILING — which is the
    // stronger statement, so it is kept in that form: the absence is enforced by the key type, and
    // only a deliberate cast can read past it.
    // @ts-expect-error — residual land is not a governed consumer.
    const absent = FACT_DEPENDENCIES["residual_land"];
    expect(absent).toBeUndefined();
    expect(Object.keys(FACT_DEPENDENCIES)).not.toContain("residual_land");
  });
});

describe("gateFor", () => {
  it("THE POINT: a blocking entry on a fact the card consumes withholds the verdict", () => {
    const state = gateFor(READ({ gate: { blocking: [
      { fact_type: "rent_roll", why: "authoritative document is 87 day(s) past its 45-day limit" },
    ] } }), "net_effective_rent");
    expect(state.kind).toBe("blocked");
    expect(withholds(state)).toBe(true);
    expect(gateNote(state)!.text).toContain("87 day(s)");
    expect(gateNote(state)!.text).toContain("Rent roll");
  });

  it("a blocking entry on a fact the card does NOT consume leaves it alone", () => {
    // The tax bill blocks the committee gate and has nothing to do with net effective rent.
    const state = gateFor(READ({ gate: { blocking: [
      { fact_type: "tax", why: "required fact type has no authoritative document" },
    ] } }), "net_effective_rent");
    expect(state.kind).toBe("clear");
    expect(withholds(state)).toBe(false);
    expect(gateNote(state)).toBeNull();
  });

  it("AN UNDECLARED TABLE IS NOT A BLOCKED ONE", () => {
    // `assess([])` reports every required fact as missing, so an empty table produces a full set of
    // blocking entries. Withholding on that would make a fresh project look like a governed one
    // that failed — the same empty-versus-zero confusion these cards exist to refuse.
    const state = gateFor({ entries: [], gate: { blocking: [
      { fact_type: "rent_roll", why: "required fact type has no authoritative document" },
      { fact_type: "operating_statement", why: "required fact type has no authoritative document" },
    ] } }, "net_effective_rent");
    expect(state.kind).toBe("undeclared");
    expect(withholds(state)).toBe(false);
    expect(gateNote(state)!.text).toContain("not governed by a source of record");
  });

  it("a gate that could not be read is UNKNOWN, never clear", () => {
    for (const bad of [null, undefined, {}, { entries: "nope" }]) {
      const state = gateFor(bad as never, "t12");
      expect(state.kind).toBe("unknown");
      expect(withholds(state)).toBe(false);
      expect(gateNote(state)!.text).toContain("ungoverned");
    }
  });

  it("a table with entries but no gate is UNKNOWN, not clear", () => {
    expect(gateFor({ entries: [{ fact_type: "tax" }] }, "t12").kind).toBe("unknown");
    expect(gateFor({ entries: [{ fact_type: "tax" }], gate: { blocking: "x" } }, "t12").kind)
      .toBe("unknown");
  });

  it("covenants depend on two facts and either one blocks them", () => {
    for (const ft of ["operating_statement", "loan"]) {
      const state = gateFor(READ({ gate: { blocking: [{ fact_type: ft, why: "stale" }] } }),
                            "covenants");
      expect(state.kind, ft).toBe("blocked");
    }
  });

  it("an explicit fact list works as well as a named consumer", () => {
    expect(gateFor(READ({ gate: { blocking: [{ fact_type: "survey", why: "stale" }] } }),
                   ["survey"]).kind).toBe("blocked");
  });

  it("an unknown consumer key is a COMPILE error, not a silently ungoverned card", () => {
    // An unknown key resolves to no facts and therefore to `clear`: the fail-OPEN direction, and a
    // card that quietly stops being governed. The non-empty pin above cannot catch it, because a
    // RENAME satisfies a count. `FACT_DEPENDENCIES` is `as const satisfies …`, so `keyof` is the
    // four literal keys and the call below only compiles behind a cast — which is the point: the
    // cast is what somebody would have to write on purpose.
    expect(gateFor(READ({ gate: { blocking: [{ fact_type: "rent_roll", why: "x" }] } }),
                   "typo_card" as unknown as keyof typeof FACT_DEPENDENCIES).kind).toBe("clear");
    // @ts-expect-error — the whole repair: this spelling no longer typechecks.
    gateFor(READ(), "typo_card");
  });

  it("a malformed blocking entry is skipped rather than crashing the card", () => {
    const state = gateFor(READ({ gate: { blocking: [null, 7, { why: "no fact_type" },
      { fact_type: "rent_roll", why: "stale" }] } }), "rent_roll_scrub");
    expect(state.kind).toBe("blocked");
    expect((state as { blocks: unknown[] }).blocks).toHaveLength(1);
  });

  it("a clear gate says NOTHING, on purpose", () => {
    // A card that narrates its own compliance trains the reader to skip the one that does not.
    expect(gateNote({ kind: "clear" })).toBeNull();
  });
});

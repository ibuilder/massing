import { describe, it, expect } from "vitest";
import {
  blockerLabel, registerHeadline, modelCaveat, scopeNote, driftLine, freezeGate,
  freezeConfirm, freezeSummary,
} from "./prefabKits";
import type { PrefabKit, PrefabRegister } from "../../api/prefab";

const kit = (over: Partial<PrefabKit> = {}): PrefabKit => ({
  id: 1, ref: "KIT-004", name: "Level 3 riser", trade: "mechanical", fabricator: null,
  state: "draft", scope_source: "selector",
  selector: { selector: "type=IfcPipeSegment", guids: ["a", "b"], matched: 2 },
  frozen_count: 0, elements: 2,
  bom: { lines: [], totals: {}, unresolved: [] },
  drift: null, blockers: [], ready: true, as_of: "2026-09-11",
  ...over,
});

const reg = (over: Partial<PrefabRegister> = {}): PrefabRegister => ({
  kits: [], total: 0, ready: 0, blocked: 0, blocker_counts: {},
  as_of: "2026-09-11", model_loaded: true, ...over,
});

describe("blockerLabel", () => {
  it("turns the server's codes into sentences a person can act on", () => {
    expect(blockerLabel("scope_drift")).toContain("no longer matches");
    expect(blockerLabel("released_without_freezing")).toContain("live query");
  });

  it("falls back to the CODE itself, never to 'unknown'", () => {
    // The server owns this list. A code added there must still reach the screen legibly on the day
    // it ships -- a generic "unknown blocker" would hide a real reason a kit cannot be released,
    // which is precisely the class of silence this panel exists to end.
    expect(blockerLabel("some_future_code")).toBe("some_future_code");
  });
});

describe("registerHeadline", () => {
  it("counts ready against blocked", () => {
    expect(registerHeadline(reg({ total: 7, ready: 2, blocked: 5 }))).toBe("7 kits — 2 ready, 5 blocked.");
  });
  it("says so when there are none, rather than rendering a zero", () => {
    expect(registerHeadline(reg())).toContain("No prefab kits");
  });
  it("does not pluralise a single kit", () => {
    expect(registerHeadline(reg({ total: 1, ready: 1, blocked: 0 }))).toContain("1 kit —");
  });
});

describe("modelCaveat", () => {
  it("is silent when a model is loaded", () => {
    expect(modelCaveat(reg({ model_loaded: true }))).toBeNull();
  });

  it("says the figures are UNVERIFIABLE, not zero, when no model is loaded", () => {
    // Without an index every scope resolves to nothing, so a register that just renders "0
    // elements" states a falsehood in the shape of a fact. The caveat has to say which it is.
    const m = modelCaveat(reg({ model_loaded: false }))!;
    expect(m).toContain("No model is loaded");
    expect(m).toContain("not what the model contains");
  });
});

describe("scopeNote — the distinction the whole panel exists for", () => {
  it("a selector-sourced kit is named as having nothing written down", () => {
    const s = scopeNote(kit({ scope_source: "selector", selector: { selector: "x", guids: [], matched: 9 } }));
    expect(s).toContain("Scope is the selector");
    expect(s).toContain("9 elements");
    expect(s).toContain("query rather than a list");
  });

  it("a frozen kit reports the WRITTEN count, not what the selector matches now", () => {
    // The two numbers differ exactly when the model has moved under a released kit, and reporting
    // the live one there would hide the drift this register is built to surface.
    const s = scopeNote(kit({
      scope_source: "frozen", frozen_count: 12,
      selector: { selector: "x", guids: ["a"], matched: 1 },
    }));
    expect(s).toContain("12 GlobalIds");
    expect(s).not.toContain("matching 1");
  });

  it("singularises one GlobalId and one element", () => {
    expect(scopeNote(kit({ scope_source: "frozen", frozen_count: 1 }))).toContain("1 GlobalId,");
    expect(scopeNote(kit({ selector: { selector: "x", guids: ["a"], matched: 1 } }))).toContain("1 element ");
  });
});

describe("driftLine", () => {
  it("is silent when nothing has drifted", () => {
    expect(driftLine(kit())).toBeNull();
    expect(driftLine(kit({ drift: { drifted: false, added: [], removed: [], means: "n/a" } }))).toBeNull();
  });
  it("counts both directions and carries the server's own explanation", () => {
    const d = driftLine(kit({
      drift: { drifted: true, added: ["x"], removed: ["y", "z"], means: "the frozen scope is stale" },
    }))!;
    expect(d).toContain("1 added, 2 removed");
    expect(d).toContain("the frozen scope is stale");
  });
});

describe("freezeGate — the button is absent, not offered-and-refused", () => {
  it("allows a kit whose selector matches something", () => {
    expect(freezeGate(kit(), true).can).toBe(true);
  });

  it("refuses with no model, because the selector cannot be resolved at all", () => {
    const g = freezeGate(kit(), false);
    expect(g.can).toBe(false);
    expect(g.why).toContain("loaded model");
  });

  it("refuses an empty match — writing nothing and calling it a released kit is THE failure", () => {
    const g = freezeGate(kit({ selector: { selector: "x", guids: [], matched: 0 } }), true);
    expect(g.can).toBe(false);
    expect(g.why).toContain("no elements");
  });

  it("refuses a TRUNCATED result, which would otherwise write a silently partial scope", () => {
    // This is the one a person would not notice: the selector matched, the count looks plausible,
    // and the list is short by however much the cap cut off.
    const g = freezeGate(kit({ selector: { selector: "x", guids: ["a"], matched: 5000, truncated: true } }), true);
    expect(g.can).toBe(false);
    expect(g.why).toContain("truncated");
  });

  it("refuses a selector that does not parse, and shows the server's own words", () => {
    const g = freezeGate(kit({ selector: { selector: "??", guids: [], matched: 0, error: "bad selector" } }), true);
    expect(g.can).toBe(false);
    expect(g.why).toBe("bad selector");
  });
});

describe("freezeConfirm", () => {
  it("a first write explains what happens next", () => {
    const c = freezeConfirm(kit());
    expect(c).toContain("Write 2 elements onto KIT-004");
    expect(c).toContain("the shop builds this list");
    expect(c).not.toContain("REPLACES");
  });

  it("a RE-write says it replaces what the shop may already be building from", () => {
    // Not a louder version of the first message: re-writing can change what is being fabricated,
    // and a confirmation that does not say so is how that happens by accident.
    const c = freezeConfirm(kit({ frozen_count: 12, scope_source: "frozen" }));
    expect(c).toContain("REPLACES the 12 GlobalIds");
    expect(c).toContain("changes it");
  });

  it("falls back to a neutral noun when the kit has no ref", () => {
    expect(freezeConfirm(kit({ ref: null }))).toContain("onto this kit");
  });
});

describe("freezeSummary", () => {
  it("reports what was written AND what the selector matched, so a mismatch is visible", () => {
    const s = freezeSummary({ ref: "KIT-004", matched: 12, selector: "x", frozen: 12, note: "written" });
    expect(s).toContain("KIT-004: 12 elements written");
    expect(s).toContain("selector matched 12");
  });
});

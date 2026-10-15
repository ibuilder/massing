import { describe, expect, it } from "vitest";
import type { ModuleBoard } from "../../api/types";
import { boardDepthNote, columnCount, columnCountTitle, extraStatesNote, noTransitionNote,
  workflowBasisNote } from "./boardRead";

const card = (i: number) => ({ id: `i${i}`, ref: `R-${i}`, title: `t${i}`, assignee: null,
                               party_owner: null });

/** The shape measured on a live route: 205 records in `draft`, the column capped at 200. */
const CAPPED: ModuleBoard = {
  states: ["draft", "open", "answered", "closed", "void"],
  declared_states: ["draft", "open", "answered", "closed", "void"],
  extra_states: [],
  columns: {
    draft: Array.from({ length: 200 }, (_, i) => card(i)),
    open: [card(900)], answered: [], closed: [], void: [],
  },
  counts: { draft: 205, open: 1 },
  transitions: [
    { from: "draft", to: "open", action: "submit" },
    { from: "open", to: "answered", action: "respond" },
    { from: "open", to: "void", action: "void" },
  ] as ModuleBoard["transitions"],
  workflow_overridden: false,
  per_state_cap: 200,
  counts_basis: "basis sentence",
};

describe("columnCount — the head printed a page length", () => {
  it("shows cards OF total when the column is deeper than the cap", () => {
    // Measured: 205 records in draft, 200 cards served. The head said 200.
    expect(columnCount(CAPPED, "draft")).toBe("200 of 205");
  });

  it("shows the plain total when everything fits", () => {
    expect(columnCount(CAPPED, "open")).toBe("1");
  });

  it("shows 0 for an empty column, from the count rather than the cards", () => {
    expect(columnCount(CAPPED, "closed")).toBe("0");
  });

  it("falls back to the card count on a server that predates `counts`", () => {
    const old = { ...CAPPED } as Record<string, unknown>;
    delete old.counts;
    expect(columnCount(old as unknown as ModuleBoard, "draft")).toBe("200");
  });

  it("is plain text", () => {
    expect(columnCount(CAPPED, "draft")).not.toMatch(/[<>]/);
  });
});

describe("columnCountTitle", () => {
  it("says which number is which, and names the cap", () => {
    const t = columnCountTitle(CAPPED, "draft");
    expect(t).toContain("205 record(s) in draft");
    expect(t).toContain("newest 200");
    expect(t).toContain("caps each column at 200");
  });

  it("says all shown when nothing is hidden", () => {
    expect(columnCountTitle(CAPPED, "open")).toContain("all shown");
  });
});

describe("boardDepthNote", () => {
  it("names the deep columns, worst gap first", () => {
    const n = boardDepthNote({
      ...CAPPED,
      columns: { ...CAPPED.columns, open: Array.from({ length: 200 }, (_, i) => card(i)) },
      counts: { draft: 205, open: 460 },
    })!;
    expect(n.indexOf("open")).toBeLessThan(n.indexOf("draft"));
    expect(n).toContain("open (200 of 460)");
    expect(n).toContain("draft (200 of 205)");
  });

  it("is null when every column fits", () => {
    expect(boardDepthNote({ ...CAPPED, counts: { draft: 200, open: 1 } })).toBeNull();
  });

  it("is null on a server that predates `counts` rather than guessing", () => {
    const old = { ...CAPPED } as Record<string, unknown>;
    delete old.counts;
    expect(boardDepthNote(old as unknown as ModuleBoard)).toBeNull();
  });

  it("caps the named list", () => {
    const states = ["a", "b", "c", "d", "e"];
    const n = boardDepthNote({
      ...CAPPED, states,
      columns: Object.fromEntries(states.map((s) => [s, [card(1)]])),
      counts: Object.fromEntries(states.map((s, i) => [s, 10 + i])),
    })!;
    expect(n).toContain("and 2 more");
  });
});

describe("extraStatesNote — a record in an undeclared state was invisible", () => {
  it("is null when the workflow covers every state holding records", () => {
    expect(extraStatesNote(CAPPED)).toBeNull();
  });

  it("names the states and says why they have a column at all", () => {
    // Measured: 3 records with one moved to `retired`; the board drew 2 of 3 before this.
    const n = extraStatesNote({ ...CAPPED, extra_states: ["retired"],
                                states: [...CAPPED.states, "retired"] })!;
    expect(n).toContain("1 state(s) hold records but are not in this module's workflow: retired");
    expect(n).toContain("nothing is hidden");
    expect(n).toContain("no transition leads out of them");
  });

  it("survives a server that predates the field", () => {
    const old = { ...CAPPED } as Record<string, unknown>;
    delete old.extra_states;
    expect(extraStatesNote(old as unknown as ModuleBoard)).toBeNull();
  });
});

describe("workflowBasisNote", () => {
  it("is null on the shipped workflow — there is nothing to disclose", () => {
    expect(workflowBasisNote(CAPPED)).toBeNull();
  });

  it("says the drags are the project's own when it overrides", () => {
    const n = workflowBasisNote({ ...CAPPED, workflow_overridden: true })!;
    expect(n).toContain("overrides the shipped workflow");
    expect(n).toContain("the server will honour");
  });
});

describe("noTransitionNote — the refusal, in terms of the workflow in force", () => {
  it("lists where the card CAN go instead of just refusing", () => {
    expect(noTransitionNote(CAPPED, "open", "closed"))
      .toBe("No direct transition open → closed. From open, the module's workflow allows: answered, void.");
  });

  it("says so when a state is a dead end", () => {
    expect(noTransitionNote(CAPPED, "closed", "open"))
      .toContain("leads nowhere out of closed");
  });

  it("attributes the rule to the PROJECT when the workflow is overridden", () => {
    // This is the sharp case: before the fix the board offered shipped transitions the engine
    // refused, so a refusal attributed to "the module's workflow" named the wrong authority.
    const over: ModuleBoard = {
      ...CAPPED, workflow_overridden: true,
      transitions: [{ from: "draft", to: "answered", action: "fast_answer" }] as ModuleBoard["transitions"],
    };
    expect(noTransitionNote(over, "draft", "open"))
      .toBe("No direct transition draft → open. From draft, this project's workflow allows: answered.");
  });

  it("de-duplicates targets reachable by more than one action", () => {
    const dup: ModuleBoard = {
      ...CAPPED,
      transitions: [{ from: "open", to: "void", action: "void" },
                    { from: "open", to: "void", action: "cancel" }] as ModuleBoard["transitions"],
    };
    expect(noTransitionNote(dup, "open", "closed")).toContain("allows: void.");
  });
});

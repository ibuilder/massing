import { readFileSync } from "node:fs";
import { resolve } from "node:path";

import { beforeEach, describe, expect, it, vi } from "vitest";

import type { WorkflowTransition } from "../../api/types";
import type { PanelContext } from "../panelContext";
import {
  type WorkflowWire, diffVsShipped, duplicatePairs, renderWorkflowConfig, strandedStates,
  undeclaredStates, unreachableStates,
} from "./workflowConfig";

const t = (from: string, action: string, to: string): WorkflowTransition =>
  ({ from, to, action, party: [] });

const wire = (over: Partial<WorkflowWire> = {}): WorkflowWire => ({
  module: "submittal", overridden: false,
  states: ["draft", "review", "approved", "closed"],
  initial: "draft",
  transitions: [t("draft", "submit", "review"), t("review", "approve", "approved"),
                t("approved", "close", "closed")],
  shipped_transitions: [t("draft", "submit", "review"), t("review", "approve", "approved"),
                        t("approved", "close", "closed")],
  record_counts: { draft: 1, review: 2 },
  ...over,
});

describe("strandedStates — the server's three conditions, in the server's order", () => {
  it("names a state with records and no way out", () => {
    // Drop review → approved and two submittals sit in `review` for ever.
    expect(strandedStates(wire(), [t("draft", "submit", "review"), t("approved", "close", "closed")]))
      .toEqual({ review: 2 });
  });

  it("does NOT name a state the shipped workflow also treats as terminal", () => {
    // `closed` has no exit in the shipped workflow either — "a genuinely terminal state SHOULD have
    // no exit". Without this condition the editor would warn about every closed state in the product.
    expect(strandedStates(wire({ record_counts: { closed: 9 } }), wire().transitions)).toEqual({});
  });

  it("does NOT name a state nobody is standing in", () => {
    // Legal: the workflow is a graph, and a dead end with no records is a design choice.
    expect(strandedStates(wire({ record_counts: {} }),
                          [t("draft", "submit", "review")])).toEqual({});
  });

  it("names several at once, with their counts", () => {
    expect(strandedStates(wire({ record_counts: { review: 2, approved: 5 } }),
                          [t("draft", "submit", "review")]))
      .toEqual({ review: 2, approved: 5 });
  });
});

describe("duplicatePairs", () => {
  it("catches two transitions on one (from, action), which the engine would resolve arbitrarily", () => {
    expect(duplicatePairs([t("review", "approve", "approved"), t("review", "approve", "closed")]))
      .toEqual(["review + approve"]);
  });

  it("allows the same ACTION from different states", () => {
    expect(duplicatePairs([t("draft", "cancel", "closed"), t("review", "cancel", "closed")]))
      .toEqual([]);
  });
});

describe("undeclaredStates", () => {
  it("rejects a state the module does not declare, in either position", () => {
    expect(undeclaredStates(wire(), [t("draft", "escalate", "legal_hold")])).toEqual(["legal_hold"]);
    expect(undeclaredStates(wire(), [t("invented", "x", "review")])).toEqual(["invented"]);
  });

  it("accepts a rewiring of the declared states", () => {
    expect(undeclaredStates(wire(), [t("draft", "fast-track", "approved")])).toEqual([]);
  });
});

describe("unreachableStates", () => {
  it("reports what the initial state can no longer get to", () => {
    expect(unreachableStates(wire(), [t("draft", "submit", "review")]))
      .toEqual(["approved", "closed"]);
  });

  it("is empty for the shipped chain", () => {
    expect(unreachableStates(wire(), wire().transitions)).toEqual([]);
  });

  it("tolerates a module with no initial state rather than reporting everything reachable", () => {
    // The negative half: with no initial state nothing is reachable, which is the honest answer and
    // the opposite of the one a `seen`-defaults-to-all implementation would give.
    expect(unreachableStates(wire({ initial: null }), wire().transitions))
      .toEqual(["draft", "review", "approved", "closed"]);
  });
});

describe("diffVsShipped", () => {
  it("names what the override adds and removes", () => {
    const d = diffVsShipped(wire(), [t("draft", "submit", "review"),
                                     t("review", "approve", "closed")]);
    expect(d.added).toEqual(["review|approve|closed"]);
    expect(d.removed).toEqual(["approved|close|closed", "review|approve|approved"]);
  });

  it("is empty when the override matches the shipped workflow", () => {
    expect(diffVsShipped(wire(), wire().transitions)).toEqual({ added: [], removed: [] });
  });
});

describe("the server still spells the rules this file mirrors", () => {
  // A CROSS-LANE TRIPWIRE. These helpers exist to show a problem before the round trip; if a rule
  // left `workflow_config.py` they would be enforcing a standard nobody holds, and every test above
  // would still pass.
  const py = readFileSync(
    resolve(process.cwd(), "../../services/api/src/aec_api/workflow_config.py"), "utf8");

  it("still refuses an override that strands live records", () => {
    expect(py).toContain("would strand live records with no way out");
  });

  it("still excludes states the shipped workflow treats as terminal", () => {
    expect(py).toContain("shipped_dead");
    expect(py).toContain("a genuinely terminal state SHOULD have no exit");
  });

  it("still refuses a duplicate (from, action) and an undeclared state", () => {
    expect(py).toContain("duplicate transition");
    expect(py).toContain("never invent new ones");
  });
});

// --- the editor ---------------------------------------------------------------------------------

function ctx(over: Record<string, unknown> = {}) {
  const api = {
    projectWorkflow: vi.fn().mockResolvedValue(wire()),
    saveProjectWorkflow: vi.fn().mockImplementation((_p: string, _k: string, tr: unknown[]) =>
      Promise.resolve({ module: "submittal", saved: tr.length, transitions: tr, reachable: [],
                        unreachable: [], unreachable_with_records: {}, dead_ends: [],
                        record_counts: {} })),
    resetProjectWorkflow: vi.fn().mockResolvedValue({ module: "submittal", removed: true,
                                                     overridden: false }),
    ...over,
  };
  const host = document.createElement("div");
  const mods = [{ key: "submittal", name: "Submittals",
                  workflow: { initial: "draft", states: ["draft", "review", "approved", "closed"],
                              transitions: [] } }];
  const c = { root: document.createElement("div"), mods,
              host: { projectId: () => "p1", api } } as unknown as PanelContext;
  return { c, api, host };
}
const flush = async () => { for (let i = 0; i < 5; i++) await Promise.resolve(); };
const btn = (h: HTMLElement, text: string) =>
  Array.from(h.querySelectorAll("button")).find((b) => (b.textContent ?? "").includes(text))!;

describe("renderWorkflowConfig", () => {
  beforeEach(() => vi.clearAllMocks());

  it("shows each state WITH the records sitting in it — the constraint on any change", async () => {
    const { c, host } = ctx();
    renderWorkflowConfig(c, host, "p1");
    await flush();
    const txt = host.textContent ?? "";
    expect(txt).toContain("draft");
    expect(txt).toContain("2 record(s) here");       // review holds two
    expect(txt).toContain("(initial)");
  });

  it("warns, with the counts, before a stranding save is attempted", async () => {
    const { c, host } = ctx();
    renderWorkflowConfig(c, host, "p1");
    await flush();
    // delete the review → approved transition
    const rows = Array.from(host.querySelectorAll("button")).filter((b) => b.textContent === "✕");
    rows[1]!.click();
    const txt = host.textContent ?? "";
    expect(txt).toContain("would strand live records");
    expect(txt).toContain("2 in “review”");
  });

  it("renders the server's refusal VERBATIM, because it names the states and the counts", async () => {
    const { c, host } = ctx({
      saveProjectWorkflow: vi.fn().mockRejectedValue(new Error(
        "this override would strand live records with no way out: 2 in 'review'. Add a transition "
        + "out of those states, or move the records first")),
    });
    renderWorkflowConfig(c, host, "p1");
    await flush();
    btn(host, "Save workflow").click();
    await flush();
    expect(host.textContent).toContain("2 in 'review'");
    expect(host.textContent).toContain("move the records first");
  });

  it("PRESERVES party and requires through an edit of something else", async () => {
    // `save` replaces the whole list, and this editor authors neither field — so a fresh object
    // would delete them from every transition touched, and only those. AUTHORITY-SUPERSEDE's shape.
    const kept = { from: "review", to: "approved", action: "approve", party: ["consultant"],
                   requires: ["stamp"] } as WorkflowTransition;
    const { c, api, host } = ctx({
      projectWorkflow: vi.fn().mockResolvedValue(wire({
        transitions: [t("draft", "submit", "review"), kept, t("approved", "close", "closed")] })),
    });
    renderWorkflowConfig(c, host, "p1");
    await flush();
    expect(host.textContent).toContain("carried through: consultant · stamp");
    const act = Array.from(host.querySelectorAll("input"))
      .find((i) => i.value === "submit")!;
    act.value = "issue"; act.dispatchEvent(new Event("input"));
    btn(host, "Save workflow").click();
    await flush();
    const sent = api.saveProjectWorkflow.mock.calls[0]![2] as WorkflowTransition[];
    expect(sent[0]!.action).toBe("issue");
    expect(sent[1]).toMatchObject({ party: ["consultant"], requires: ["stamp"] });
  });

  it("shows the diff against the shipped workflow, so the EDIT is visible", async () => {
    const { c, host } = ctx();
    renderWorkflowConfig(c, host, "p1");
    await flush();
    expect(host.textContent).toContain("identical to the shipped workflow");
    Array.from(host.querySelectorAll("button")).filter((b) => b.textContent === "✕")[2]!.click();
    expect(host.textContent).toContain("1 removed");
    expect(host.textContent).toContain("approved|close|closed");
  });

  it("offers reset only when an override exists", async () => {
    const { c, host } = ctx();
    renderWorkflowConfig(c, host, "p1");
    await flush();
    expect(btn(host, "reset to shipped").style.display).toBe("none");
    const o = ctx({ projectWorkflow: vi.fn().mockResolvedValue(wire({ overridden: true })) });
    renderWorkflowConfig(o.c, o.host, "p1");
    await flush();
    expect(btn(o.host, "reset to shipped").style.display).not.toBe("none");
    expect(o.host.textContent).toContain("overridden for this project");
  });

  it("reports a failed load as a reason, never as an empty workflow", async () => {
    const { c, host } = ctx({
      projectWorkflow: vi.fn().mockRejectedValue(new Error("403 forbidden")),
    });
    renderWorkflowConfig(c, host, "p1");
    await flush();
    expect(host.textContent).toContain("Workflow unavailable: 403 forbidden");
    expect(host.textContent).not.toContain("＋ transition");
  });
});

import { beforeEach, describe, expect, it } from "vitest";

import {
  type Command, GROUP_ORDER, groupOf, groupRank, inferGroup, noteCommandRun,
  orderForDisplay, readRecentCommands, recencyBoost, takePerGroup,
} from "./palette";

/**
 * R24-CMDK-GROUPS.
 *
 * The palette's failure was not that it was wrong — it was that `Command.group` existed on the
 * interface and nothing read it, so the audit's *"grouped by verb / record / element / report, never
 * a flat list"* was half-built and looked finished. These assertions pin the two properties that
 * make the grouping worth having: an existing call site gets grouped **without being edited**, and
 * what you typed always outranks what you happen to have run before.
 */

const C = (id: string, label: string, hint?: string, group?: string): Command =>
  ({ id, label, hint, group, run: () => {} });

beforeEach(() => localStorage.clear());

describe("a caller that never heard of groups still gets grouped", () => {
  it("infers the section from the hint every existing call site already sets", () => {
    expect(inferGroup("Workspace")).toBe("Go to");
    expect(inferGroup("Action")).toBe("Do");
    expect(inferGroup("Record")).toBe("Records");
    expect(inferGroup("Element")).toBe("Elements");
    expect(inferGroup("Report")).toBe("Reports");
  });

  it("a module's section hint is not forced into a bucket it does not belong in", () => {
    // Modules pass their section ("Cost", "Field", …) as the hint; that is the long tail.
    expect(inferGroup("Change Management")).toBe("Modules");
    expect(inferGroup(undefined)).toBe("Modules");
  });

  it("an explicit group always wins over the inference", () => {
    expect(groupOf(C("x", "l", "Workspace", "Do"))).toBe("Do");
    expect(groupOf(C("x", "l", "Workspace"))).toBe("Go to");
  });
});

describe("sections read in the order the question is asked", () => {
  it("verbs first, navigation last", () => {
    expect(groupRank("Do")).toBeLessThan(groupRank("Records"));
    expect(groupRank("Records")).toBeLessThan(groupRank("Modules"));
    expect(groupRank("Modules")).toBeLessThan(groupRank("Go to"));
  });

  it("an unrecognised group sorts after every known one rather than being reassigned", () => {
    expect(groupRank("Something New")).toBe(GROUP_ORDER.length);
    expect(groupRank("Something New")).toBeGreaterThan(groupRank("Go to"));
  });

  it("results come out grouped, and contiguous — one header per section", () => {
    const out = orderForDisplay([
      { c: C("m1", "Budget", "Cost"), s: 5 },
      { c: C("w1", "Go to Design", "Workspace"), s: 9 },
      { c: C("a1", "Open IFC…", "Action"), s: 5 },
      { c: C("m2", "Payapps", "Cost"), s: 7 },
    ]).map((c) => groupOf(c));
    expect(out).toEqual(["Do", "Modules", "Modules", "Go to"]);
  });

  it("inside a section the higher score leads; ties break by label, so nothing reshuffles", () => {
    const out = orderForDisplay([
      { c: C("b", "Beta", "Cost"), s: 3 },
      { c: C("a", "Alpha", "Cost"), s: 3 },
      { c: C("z", "Zulu", "Cost"), s: 9 },
    ]).map((c) => c.id);
    expect(out).toEqual(["z", "a", "b"]);
  });
});

/**
 * The regression grouping introduced, found in a browser and not by any of the tests above.
 *
 * `Go to` sorts last on purpose. With 130-plus modules ranked ahead of it, a flat 40-row cap removed
 * every workspace from the palette — sections gained, navigation silently lost. A per-section cap is
 * the fix, and this is the assertion that stops it coming back.
 */
describe("every section survives the cap", () => {
  const many = (group: string, n: number, hint: string) =>
    Array.from({ length: n }, (_, i) => ({ c: C(`${group}${i}`, `${group} ${i}`, hint), s: 1 }));

  it("workspaces still appear even when modules outnumber them 20 to 1", () => {
    const ranked = orderForDisplay([...many("mod", 130, "Cost"), ...many("ws", 6, "Workspace")]);
    // Reproduces the defect: the naive global slice loses "Go to" entirely.
    expect(ranked.slice(0, 40).some((c) => groupOf(c) === "Go to")).toBe(false);
    // The fix.
    const shown = takePerGroup(ranked, 8, 40);
    expect(shown.some((c) => groupOf(c) === "Go to")).toBe(true);
  });

  it("caps each section rather than the list, and still respects the overall limit", () => {
    const shown = takePerGroup(orderForDisplay([
      ...many("mod", 50, "Cost"), ...many("act", 50, "Action"), ...many("ws", 50, "Workspace"),
    ]), 8, 40);
    const counts = shown.reduce<Record<string, number>>((a, c) => {
      a[groupOf(c)] = (a[groupOf(c)] ?? 0) + 1; return a;
    }, {});
    expect(counts).toEqual({ Do: 8, Modules: 8, "Go to": 8 });
    expect(shown.length).toBeLessThanOrEqual(40);
  });

  it("a short list is not padded or truncated", () => {
    const cmds = [C("a", "A", "Action"), C("b", "B", "Workspace")];
    expect(takePerGroup(cmds, 8, 40).length).toBe(2);
  });
});

describe("recency ranks your own working set — without overriding what you typed", () => {
  it("records the last 20 runs, newest first, without duplicates", () => {
    noteCommandRun("a"); noteCommandRun("b"); noteCommandRun("a");
    expect(readRecentCommands()).toEqual(["a", "b"]);
  });

  it("keeps only 20", () => {
    for (let i = 0; i < 25; i++) noteCommandRun("c" + i);
    const r = readRecentCommands();
    expect(r.length).toBe(20);
    expect(r[0]).toBe("c24");
  });

  it("the newest run is worth the most and the oldest almost nothing", () => {
    const recent = ["first", "second", "third"];
    expect(recencyBoost("first", recent)).toBeGreaterThan(recencyBoost("third", recent));
    expect(recencyBoost("never-run", recent)).toBe(0);
  });

  it("the boost stays below the prefix-match bonus, so a typed match always wins", () => {
    // `fuzzy()` adds +5 for a prefix hit. If recency could exceed that, typing the exact name of a
    // command would surface something else — which is when people stop trusting the palette.
    expect(recencyBoost("x", ["x"])).toBeLessThan(5);
  });
});

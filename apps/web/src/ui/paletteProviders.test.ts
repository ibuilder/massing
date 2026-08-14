import { describe, expect, it, vi } from "vitest";
import {
  askFallback, canonicalIfcClass, elementCommands, isGlobalId, isIfcClass,
  reportCommands, verbCommands, type VerbSpec,
} from "./paletteProviders";
import { GROUP_ORDER, groupOf, groupRank, mergeResults, type Command } from "./palette";
import { TOOLS } from "../viewer/toolbarLayout";

const cmd = (id: string, group: string): Command => ({ id, label: id, group, run: () => {} });

describe("R24-CMDK-VERBS — the declared sections can now be filled", () => {
  /**
   * The vacuity guard for the whole file. `GROUP_ORDER` named six sections and only three could ever
   * contain anything; if a future edit removes `Elements` or `Reports` from the order, every
   * assertion below still passes while the rows sort into the unknown-group tail. Assert the
   * contract, not just the producers.
   */
  it("Elements and Reports are real sections, not strings this file invented", () => {
    expect(GROUP_ORDER).toContain("Elements");
    expect(GROUP_ORDER).toContain("Reports");
    expect(groupRank("Elements")).toBeLessThan(GROUP_ORDER.length);
    expect(groupRank("Reports")).toBeLessThan(GROUP_ORDER.length);
  });

  describe("isGlobalId", () => {
    it("accepts a real 22-char IFC GlobalId", () => {
      expect(isGlobalId("3vB2Yo1Vv4$eF_wq1nZ8lQ")).toBe(true);
      expect(isGlobalId("0000000000000000000000")).toBe(true);
    });

    it("refuses anything that is not exactly one", () => {
      // 21 and 23 both matter: an unanchored or length-loose test offers a broken element row for
      // any long word, and the row 404s against a GUID the user never typed.
      expect(isGlobalId("3vB2Yo1Vv4$eF_wq1nZ8l")).toBe(false);       // 21
      expect(isGlobalId("3vB2Yo1Vv4$eF_wq1nZ8lQQ")).toBe(false);     // 23
      expect(isGlobalId("3vB2Yo1Vv4$eF_wq1nZ8lQ extra")).toBe(false);
      expect(isGlobalId("wall")).toBe(false);
      expect(isGlobalId("")).toBe(false);
      expect(isGlobalId("3vB2Yo1Vv4-eF+wq1nZ8lQ")).toBe(false);      // - and + are not IFC base64
    });
  });

  describe("isIfcClass / canonicalIfcClass", () => {
    it("recognises a class however it was typed, and canonicalises it", () => {
      expect(isIfcClass("IfcWall")).toBe(true);
      expect(isIfcClass("ifcdoor")).toBe(true);
      expect(canonicalIfcClass("ifcwall")).toBe("IfcWall");
      expect(canonicalIfcClass("IFCDOOR")).toBe("IfcDoor");
      expect(canonicalIfcClass("IfcWall")).toBe("IfcWall");
    });

    it("does not treat every word starting with 'if' as a class", () => {
      expect(isIfcClass("if")).toBe(false);
      expect(isIfcClass("ifc")).toBe(false);          // bare prefix — nothing to list
      expect(isIfcClass("difference")).toBe(false);
      expect(isIfcClass("ifc wall")).toBe(false);
    });
  });

  describe("verbCommands", () => {
    const tools: VerbSpec[] = [
      { title: "Move selected element (E,N,Z metres)", label: "Move", group: "author" },
      { title: "Measure distance (M)", label: "Measure", group: "measure" },
      { title: "Toggle storey levels overlay", label: "Levels", group: "look" },
    ];

    it("offers only the requested groups, in the Do section", () => {
      const out = verbCommands(tools, { groups: ["author", "measure"], present: () => true, run: () => {} });
      expect(out.map((c) => c.label)).toEqual(["Move", "Measure"]);
      expect(out.every((c) => groupOf(c) === "Do")).toBe(true);
      expect(out[0]!.hint).toBe("Author");
    });

    it("OMITS a verb whose button is not installed — it never offers a dead row", () => {
      // The toolbar only exists once a model is loaded. A row that looks available and does nothing
      // is worse than a shorter palette, so absence is absence, not a disabled row.
      const out = verbCommands(tools, { groups: ["author"], present: () => false, run: () => {} });
      expect(out).toEqual([]);
    });

    it("dispatches by the button's title, so it cannot drift from the toolbar", () => {
      const run = vi.fn();
      const out = verbCommands(tools, { groups: ["author"], present: () => true, run });
      out[0]!.run();
      expect(run).toHaveBeenCalledWith("Move selected element (E,N,Z metres)");
    });

    /**
     * The tie to the real table. `viewer/toolbarLayout` keys tools on the DOM `title` verbatim and
     * already fails when an installed button is missing from it — reusing that key is what makes a
     * retitled button impossible to silently drop from the palette. If TOOLS ever stopped carrying
     * authoring verbs, this file would keep passing against its own three-row fixture.
     */
    it("the real TOOLS table actually yields authoring verbs", () => {
      const out = verbCommands(TOOLS, { groups: ["author"], present: () => true, run: () => {} });
      expect(out.length).toBeGreaterThan(5);
      expect(out.map((c) => c.label)).toContain("Move");
      expect(new Set(out.map((c) => c.id)).size).toBe(out.length);   // ids unique — titles are the key
    });
  });

  describe("elementCommands", () => {
    const opts = { openGuid: vi.fn(), openClass: vi.fn() };

    it("a GlobalId query becomes an exact element row", () => {
      const out = elementCommands("3vB2Yo1Vv4$eF_wq1nZ8lQ", opts);
      expect(out).toHaveLength(1);
      expect(groupOf(out[0]!)).toBe("Elements");
      expect(out[0]!.hint).toBe("GlobalId");
    });

    it("an IFC class query becomes a list row, canonicalised", () => {
      const openClass = vi.fn();
      const out = elementCommands("ifcwall", { openGuid: vi.fn(), openClass });
      expect(out).toHaveLength(1);
      out[0]!.run();
      expect(openClass).toHaveBeenCalledWith("IfcWall");
    });

    it("returns NOTHING for a plain search phrase rather than guessing", () => {
      // The section header only appears when there is a row under it. A speculative element row
      // promises a hit and then fails on click, which is the failure mode this avoids.
      expect(elementCommands("level 3 slab", opts)).toEqual([]);
      expect(elementCommands("", opts)).toEqual([]);
    });
  });

  describe("reportCommands", () => {
    const cat = [{ id: "cost-summary", name: "Cost summary", group: "Cost" }];

    it("maps the server catalog into the Reports section", () => {
      const open = vi.fn();
      const out = reportCommands(cat, open);
      expect(groupOf(out[0]!)).toBe("Reports");
      expect(out[0]!.label).toBe("Cost summary");
      out[0]!.run();
      expect(open).toHaveBeenCalledWith("cost-summary");
    });

    it("an empty catalog produces no rows, not a heading with nothing under it", () => {
      expect(reportCommands([], vi.fn())).toEqual([]);
    });
  });

  describe("askFallback", () => {
    it("sorts after every known section", () => {
      const fb = askFallback("how many doors", vi.fn());
      expect(groupRank(groupOf(fb))).toBe(GROUP_ORDER.length);
    });

    it("carries the query through to the assistant", () => {
      const ask = vi.fn();
      askFallback("how many doors", ask).run();
      expect(ask).toHaveBeenCalledWith("how many doors");
    });
  });
});

describe("mergeResults — late results fold INTO the sections, not underneath them", () => {
  /**
   * The regression this exists for. `refresh()` used to `concat` the async hits onto an
   * already-grouped list, so a Records hit landed below Modules and Go to under a **second**
   * `RECORDS` heading. The grouping was a property of the first paint only — and the section the
   * async provider exists to fill was the one it could never reach.
   */
  it("re-sorts merged results into GROUP_ORDER", () => {
    const base = [cmd("do1", "Do"), cmd("mod1", "Modules"), cmd("go1", "Go to")];
    const extra = [cmd("rec1", "Records"), cmd("el1", "Elements")];
    const out = mergeResults(base, extra).map((c) => c.id);
    expect(out).toEqual(["do1", "rec1", "el1", "mod1", "go1"]);
  });

  it("...and the naive concat it replaced would have failed that", () => {
    // The twin. Without it, the assertion above could pass on an implementation that happened to
    // receive its inputs in order — this pins that the ORDER CHANGED.
    const naive = [cmd("do1", "Do"), cmd("mod1", "Modules"), cmd("go1", "Go to"),
                   cmd("rec1", "Records"), cmd("el1", "Elements")].map((c) => c.id);
    expect(naive).not.toEqual(["do1", "rec1", "el1", "mod1", "go1"]);
  });

  it("preserves each side's own ranking within a section (stable sort)", () => {
    // Re-scoring here would throw away the server's relevance order, which the palette cannot
    // reconstruct — it does not know why one record outranked another.
    const extra = [cmd("recA", "Records"), cmd("recB", "Records"), cmd("recC", "Records")];
    expect(mergeResults([], extra).map((c) => c.id)).toEqual(["recA", "recB", "recC"]);
  });

  it("dedupes by id, keeping the static row", () => {
    const base = [cmd("x", "Do")];
    expect(mergeResults(base, [cmd("x", "Records")]).map((c) => groupOf(c))).toEqual(["Do"]);
  });

  it("caps per section, so one big section cannot starve the others", () => {
    const many = Array.from({ length: 30 }, (_, i) => cmd("mod" + i, "Modules"));
    const out = mergeResults(many, [cmd("rec1", "Records")], { perGroup: 8, total: 40 });
    expect(out.filter((c) => groupOf(c) === "Modules")).toHaveLength(8);
    expect(out.map((c) => c.id)).toContain("rec1");
  });

  it("a pinned row survives a full cap — a fallback the cap can delete is not a fallback", () => {
    const many = Array.from({ length: 60 }, (_, i) => cmd("mod" + i, "Modules"));
    const fb = askFallback("q", () => {});
    const out = mergeResults(many, [], { perGroup: 60, total: 5, pinned: [fb] });
    expect(out).toHaveLength(6);                       // 5 capped + the pinned row
    expect(out[out.length - 1]!.id).toBe(fb.id);
  });

  it("...and is not duplicated when it also arrived through the merge", () => {
    const fb = askFallback("q", () => {});
    const out = mergeResults([fb], [], { pinned: [fb] });
    expect(out.filter((c) => c.id === fb.id)).toHaveLength(1);
  });
});

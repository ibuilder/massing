import { describe, expect, it } from "vitest";

import type { LifecycleStrip } from "../api/types";
import {
  TAB_MARK, buildInspectorTabs, costBody, emptyBody, fieldBody, scheduleBody, tabStates,
  type Element5d, type InspectorData,
} from "./inspectorTabs";

const COST: Element5d["cost"] = {
  code: "03 30 00", ref: "CC-1", name: "Cast-in-place concrete", division: "03",
  budget: 100_000, committed: 80_000, actual: 42_000, eac: 105_000, variance: -5_000,
};
const SCHED: Element5d["schedule"] = {
  ref: "A-100", name: "Pour L2 slab", trade: "Concrete", percent: 42.4,
  start: "2026-08-01", finish: "2026-08-14", state: "in_progress", hard_tied: true,
};
const strip = (states: Array<[string, "done" | "none" | "unknown"]>,
               inconsistencies: string[] = []): LifecycleStrip => ({
  guid: "G1",
  states: states.map(([key, status]) => ({ key, status, means: `${key} means`, advance: null })) as never,
  reached: null, done_count: 0, unknown_count: 0, next: null, inconsistencies,
});

const data = (over: Partial<InspectorData> = {}): InspectorData =>
  ({ fived: { cost: COST, schedule: SCHED }, lifecycle: strip([["installed", "done"]]), ...over });

// --- the distinction the whole codebase keeps landing on -------------------------------------------
describe("`not loaded` and `nothing recorded` are different answers", () => {
  it("a failed or absent fetch is UNKNOWN, never `none`", () => {
    // Rendering an unmade request as "no cost" invents an absence nobody checked for.
    const s = tabStates({ fived: null, lifecycle: null });
    expect(s.cost).toBe("unknown");
    expect(s.schedule).toBe("unknown");
    expect(s.field).toBe("unknown");
  });
  it("a successful fetch that found nothing is NONE — a real finding", () => {
    const s = tabStates({ fived: { cost: null, schedule: null }, lifecycle: strip([]) });
    expect(s.cost).toBe("none");
    expect(s.schedule).toBe("none");
    expect(s.field).toBe("none");
  });
  it("properties is always ready — it needs no fetch that could fail", () => {
    expect(tabStates({ fived: null, lifecycle: null }).properties).toBe("ready");
  });
  it("the two empties render DIFFERENT bodies, so the distinction is visible not just modelled", () => {
    expect(emptyBody("cost", "unknown").textContent).toContain("Not loaded");
    expect(emptyBody("cost", "unknown").textContent).toContain("never asked");
    const none = emptyBody("cost", "none").textContent || "";
    expect(none).toContain("Nothing recorded");
    expect(none).toContain("unpriced");
    expect(none).not.toContain("Not loaded");
  });
});

describe("field state comes from the strip's later states only", () => {
  it("a designed-but-not-installed element has nothing to show in Field", () => {
    expect(tabStates(data({ lifecycle: strip([["designed", "done"], ["installed", "none"]]) })).field)
      .toBe("none");
  });
  it("an installed element does", () => {
    expect(tabStates(data({ lifecycle: strip([["installed", "done"]]) })).field).toBe("ready");
  });
  it("inconsistencies are surfaced in the tab, not buried in a tooltip", () => {
    const t = fieldBody(strip([["installed", "none"], ["verified", "done"]],
                              ["verified but never installed"])).textContent || "";
    expect(t).toContain("verified but never installed");
  });
  it("a state the server never sent reads as unknown, not as absent", () => {
    expect(fieldBody(strip([])).textContent).toContain("not reported by the server");
  });
});

// --- the tab bar states availability BEFORE you click ------------------------------------------------
describe("the tab bar does not make you click all four to learn three are empty", () => {
  it("each tab carries the strip's own mark for its state", () => {
    const host = buildInspectorTabs(document.createElement("div"),
                                    { fived: { cost: COST, schedule: null }, lifecycle: null });
    const mark = (k: string) =>
      host.querySelector(`.insp-tab[data-tab="${k}"] .insp-tab-mark`)?.textContent;
    expect(mark("cost")).toBe(TAB_MARK.ready);
    expect(mark("schedule")).toBe(TAB_MARK.none);
    expect(mark("field")).toBe(TAB_MARK.unknown);
  });
  it("reuses the strip's vocabulary rather than inventing a second one for the same three states", () => {
    expect([TAB_MARK.ready, TAB_MARK.none, TAB_MARK.unknown]).toEqual(["●", "○", "–"]);
  });
  it("an empty tab is never disabled — it holds the only statement of WHICH empty it is", () => {
    const host = buildInspectorTabs(document.createElement("div"), { fived: null, lifecycle: null });
    const tabs = [...host.querySelectorAll<HTMLButtonElement>(".insp-tab")];
    expect(tabs).toHaveLength(4);
    expect(tabs.every((b) => !b.disabled)).toBe(true);
  });
  it("clicking an empty tab explains itself instead of showing a blank pane", () => {
    const host = buildInspectorTabs(document.createElement("div"), { fived: null, lifecycle: null });
    host.querySelector<HTMLButtonElement>('.insp-tab[data-tab="schedule"]')!.click();
    expect(host.querySelector(".insp-tabbody")!.textContent).toContain("Not loaded");
  });
});

describe("bodies render the numbers the last two rings produced", () => {
  it("cost names the variance direction rather than leaving a sign to be interpreted", () => {
    const t = costBody({ cost: COST, schedule: null }).textContent || "";
    expect(t).toContain("03 30 00");
    expect(t).toContain("(over budget)");
  });
  it("under budget reads as under budget", () => {
    const t = costBody({ cost: { ...COST, variance: 5_000 }, schedule: null }).textContent || "";
    expect(t).toContain("(under budget)");
  });
  it("a zero variance claims neither direction", () => {
    const t = costBody({ cost: { ...COST, variance: 0 }, schedule: null }).textContent || "";
    expect(t).not.toContain("budget)");
  });
  it("schedule states whether the binding is IN the model or merely rule-matched", () => {
    expect(scheduleBody({ cost: null, schedule: SCHED }).textContent)
      .toContain("tied to this element in the model");
    expect(scheduleBody({ cost: null, schedule: { ...SCHED, hard_tied: false } }).textContent)
      .toContain("not bound in the model");
  });
});

describe("server- and model-derived text is never interpolated as markup", () => {
  it("a hostile activity name is rendered as text", () => {
    const evil = '<img src=x onerror="alert(1)">';
    const body = scheduleBody({ cost: null, schedule: { ...SCHED, name: evil } });
    expect(body.querySelector("img")).toBeNull();
    expect(body.textContent).toContain(evil);
  });
  it("...and so is a hostile cost-code name", () => {
    const body = costBody({ cost: { ...COST, name: "<script>x</script>" }, schedule: null });
    expect(body.querySelector("script")).toBeNull();
  });
});

describe("the properties view keeps its home", () => {
  it("properties is the default tab and holds the element the caller already built", () => {
    const props = document.createElement("div");
    props.textContent = "PROPS";
    const host = buildInspectorTabs(props, data());
    expect(host.querySelector(".insp-tabbody")!.textContent).toBe("PROPS");
    expect(host.querySelector(".insp-tab.active")?.getAttribute("data-tab")).toBe("properties");
  });
  it("an unknown requested tab falls back to properties rather than rendering nothing", () => {
    const props = document.createElement("div");
    props.textContent = "PROPS";
    const host = buildInspectorTabs(props, data(), { active: "nope" as never });
    expect(host.querySelector(".insp-tabbody")!.textContent).toBe("PROPS");
  });
  it("switching away and back re-renders properties", () => {
    const props = document.createElement("div");
    props.textContent = "PROPS";
    const host = buildInspectorTabs(props, data());
    host.querySelector<HTMLButtonElement>('.insp-tab[data-tab="cost"]')!.click();
    expect(host.querySelector(".insp-tabbody")!.textContent).toContain("03 30 00");
    host.querySelector<HTMLButtonElement>('.insp-tab[data-tab="properties"]')!.click();
    expect(host.querySelector(".insp-tabbody")!.textContent).toBe("PROPS");
  });
});

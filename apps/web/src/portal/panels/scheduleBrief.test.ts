import { describe, expect, it, vi } from "vitest";

import type { PanelContext } from "../panelContext";
import { SCHEDULE_BRIEF_QUESTIONS, renderScheduleBrief } from "./scheduleBrief";

function ctx(api: Record<string, unknown>): PanelContext {
  return {
    root: document.createElement("div"),
    host: { projectId: () => "p1", api } as unknown as PanelContext["host"],
    mods: [],
    activeKey: "__schedule__",
    bar: (title) => {
      const b = document.createElement("div");
      b.textContent = title;
      return b;
    },
    buildNav: () => undefined,
    renderHome: async () => undefined,
    openModule: async () => undefined,
    navigate: () => undefined,
    hasDest: () => true,
  };
}

describe("R36-ROOM-BRIEFS — Schedule", () => {
  it("names the three superintendent questions", () => {
    expect(SCHEDULE_BRIEF_QUESTIONS.map((q) => q.key)).toEqual(
      ["lookahead", "blockers", "variance"]);
  });

  it("renders those three answers from the existing engines", async () => {
    const host = ctx({
      scheduleLookahead: vi.fn().mockResolvedValue({
        count: 1,
        weeks_detail: [{
          week: "2026-08-17",
          activities: [{ name: "Pour L3 slab", trade: "concrete", status: "in_progress", percent: 40 }],
        }],
      }),
      scheduleAlerts: vi.fn().mockResolvedValue({
        alerts: [{ level: "high", title: "Rebar late", detail: "FS predecessor slipped", ref: "A-12" }],
        counts: { high: 1, medium: 0, low: 0 },
      }),
      scheduleVariance: vi.fn().mockResolvedValue({
        captured_at: "2026-08-18",
        baseline_count: 10,
        summary: { slipped: 1, max_slip_days: 4 },
        activities: [{ name: "MEP rough-in", finish_var: 4, status: "slipped" }],
      }),
    });
    const el = await renderScheduleBrief(host);
    expect(el.querySelectorAll("[data-brief]")).toHaveLength(3);
    expect(el.textContent).toContain("Pour L3 slab");
    expect(el.textContent).toContain("Rebar late");
    expect(el.textContent).toContain("MEP rough-in");
    expect(el.querySelector("[data-unavailable]")).toBeNull();
  });

  it("a failed engine is a reason, never a plausible zero", async () => {
    const host = ctx({
      scheduleLookahead: vi.fn().mockRejectedValue(new Error("lookahead down")),
      scheduleAlerts: vi.fn().mockRejectedValue(new Error("alerts down")),
      scheduleVariance: vi.fn().mockRejectedValue(new Error("no baseline set")),
    });
    const el = await renderScheduleBrief(host);
    const failed = [...el.querySelectorAll("[data-unavailable]")];
    expect(failed).toHaveLength(3);
    const text = el.textContent ?? "";
    expect(text).toContain("lookahead down");
    expect(text).toContain("alerts down");
    expect(text).toContain("no baseline set");
    expect(text).not.toMatch(/\b0 slipped\b/);
    expect(text).not.toMatch(/\b0 high\b/);
  });
});

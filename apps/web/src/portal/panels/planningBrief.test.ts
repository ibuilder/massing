import { describe, expect, it, vi } from "vitest";

import type { PanelContext } from "../panelContext";
import { PLANNING_BRIEF_QUESTIONS, renderPlanningBrief } from "./planningBrief";

function ctx(api: Record<string, unknown>): PanelContext {
  return {
    root: document.createElement("div"),
    host: { projectId: () => "p1", api } as unknown as PanelContext["host"],
    mods: [],
    activeKey: "__benchmarks__",
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

describe("R36-ROOM-BRIEFS — Planning", () => {
  it("names the three PM questions", () => {
    expect(PLANNING_BRIEF_QUESTIONS.map((q) => q.key)).toEqual(["rfi", "submittal", "costs"]);
  });

  it("renders those answers from existing engines", async () => {
    const host = ctx({
      benchmarkResponseRates: vi.fn().mockResolvedValue({
        rfi: { total: 12, open: 3, overdue: 1, overdue_pct: 8, avg_turnaround_days: 4.2 },
        submittal: { total: 20, open: 5, overdue: 2, overdue_pct: 10, avg_turnaround_days: 9 },
      }),
      benchmarkCosts: vi.fn().mockResolvedValue({
        cost_codes: [{ cost_code: "03 30 00", samples: 5, median: 142_000 }],
        code_count: 1, min_samples: 3,
      }),
    });
    const el = await renderPlanningBrief(host);
    expect(el.querySelectorAll("[data-brief]")).toHaveLength(3);
    expect(el.textContent).toContain("12 RFIs");
    expect(el.textContent).toContain("20 submittals");
    expect(el.textContent).toContain("03 30 00");
    expect(el.querySelector("[data-unavailable]")).toBeNull();
  });

  it("no history is a sentence, never a invented median", async () => {
    const host = ctx({
      benchmarkResponseRates: vi.fn().mockResolvedValue({
        rfi: { total: 0, open: 0, overdue: 0, overdue_pct: 0, avg_turnaround_days: null },
        submittal: { total: 0, open: 0, overdue: 0, overdue_pct: 0, avg_turnaround_days: null },
      }),
      benchmarkCosts: vi.fn().mockResolvedValue({ cost_codes: [], code_count: 0, min_samples: 3 }),
    });
    const el = await renderPlanningBrief(host);
    expect(el.textContent).toContain("No RFIs in the history yet");
    expect(el.textContent).toContain("No submittals in the history yet");
    expect(el.textContent).toContain("No cost history yet");
    expect(el.textContent).not.toMatch(/\bmedian \$0\b/);
  });

  it("a failed engine is a reason, never a plausible zero", async () => {
    const host = ctx({
      benchmarkResponseRates: vi.fn().mockRejectedValue(new Error("rates down")),
      benchmarkCosts: vi.fn().mockRejectedValue(new Error("costs down")),
    });
    const el = await renderPlanningBrief(host);
    expect(el.querySelectorAll("[data-unavailable]")).toHaveLength(3);
    const text = el.textContent ?? "";
    expect(text).toContain("rates down");
    expect(text).toContain("costs down");
    expect(text).not.toMatch(/\b0 overdue\b/);
  });
});

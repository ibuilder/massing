import { describe, expect, it, vi } from "vitest";

import type { PanelContext } from "../panelContext";
import { DEAL_BRIEF_QUESTIONS, renderDealBrief } from "./dealBrief";

function ctx(api: Record<string, unknown>): PanelContext {
  return {
    root: document.createElement("div"),
    host: { projectId: () => "p1", api } as unknown as PanelContext["host"],
    mods: [],
    activeKey: "__portfolio__",
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

describe("R36-ROOM-BRIEFS — Deal", () => {
  it("names the three developer questions", () => {
    expect(DEAL_BRIEF_QUESTIONS.map((q) => q.key)).toEqual(["returns", "diligence", "gate"]);
  });

  it("renders those answers from existing engines", async () => {
    const host = ctx({
      projectPulse: vi.fn().mockResolvedValue({
        deal: { irrPct: 14.2, band: [12, 18] },
      }),
      diligenceReadiness: vi.fn().mockResolvedValue({
        go: false,
        due_diligence: { total: 4, cleared: 2, flagged: 1 },
        entitlements: { pending: 1, approved: 0, denied: 0, total: 1 },
      }),
      masterBuilderBrief: vi.fn().mockResolvedValue({
        steps: [
          { n: 1, key: "place", title: "Place & context", dest: "__land__", status: "ready", gaps: [] },
          { n: 3, key: "feasibility", title: "Feasibility & the money", dest: "__uw__", status: "gap",
            gaps: ["No scenario approved"] },
        ],
      }),
    });
    const el = await renderDealBrief(host);
    expect(el.querySelectorAll("[data-brief]")).toHaveLength(3);
    expect(el.textContent).toContain("14.2%");
    expect(el.textContent).toContain("inside the 12–18% band");
    expect(el.textContent).toContain("1 flagged");
    expect(el.textContent).toContain("Feasibility & the money");
    expect(el.querySelector("[data-unavailable]")).toBeNull();
  });

  it("a failed engine is a reason, never a plausible zero", async () => {
    const host = ctx({
      projectPulse: vi.fn().mockRejectedValue(new Error("pulse down")),
      diligenceReadiness: vi.fn().mockRejectedValue(new Error("diligence down")),
      masterBuilderBrief: vi.fn().mockRejectedValue(new Error("brief down")),
    });
    const el = await renderDealBrief(host);
    expect(el.querySelectorAll("[data-unavailable]")).toHaveLength(3);
    const text = el.textContent ?? "";
    expect(text).toContain("pulse down");
    expect(text).not.toMatch(/0\.0%/);
    expect(text).not.toMatch(/\b0 flagged\b/);
  });
});

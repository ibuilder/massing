import { describe, expect, it, vi } from "vitest";

import type { PanelContext } from "../panelContext";
import { COST_BRIEF_QUESTIONS, renderCostBrief } from "./costBrief";

function ctx(api: Record<string, unknown>): PanelContext {
  return {
    root: document.createElement("div"),
    host: { projectId: () => "p1", api } as unknown as PanelContext["host"],
    mods: [],
    activeKey: "__budget__",
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

describe("R36-ROOM-BRIEFS — Cost", () => {
  it("names the three PM questions", () => {
    expect(COST_BRIEF_QUESTIONS.map((q) => q.key)).toEqual(["gmp", "unpriced", "buyout"]);
  });

  it("renders those answers from existing engines", async () => {
    const host = ctx({
      gmpBudget: vi.fn().mockResolvedValue({
        gmp: { contract_value: 10_000_000, computed: 10_000_000 },
        totals: { budget: 10_000_000 },
        completion: { eac: 10_400_000, projected_over_under: 400_000 },
        buyout: { packages: 8, bought_out: 3, budget: 7_000_000, awarded: 2_500_000, savings: 50_000 },
      }),
      projectPulse: vi.fn().mockResolvedValue({
        cost: { unpricedChanges: 2, exposurePct: 1.4 },
      }),
    });
    const el = await renderCostBrief(host);
    expect(el.querySelectorAll("[data-brief]")).toHaveLength(3);
    expect(el.textContent).toContain("EAC");
    expect(el.textContent).toContain("2 unpriced");
    expect(el.textContent).toContain("3 of 8 packages");
    expect(el.querySelector("[data-unavailable]")).toBeNull();
  });

  it("no GMP is a sentence, not 0% of a missing contract", async () => {
    const host = ctx({
      gmpBudget: vi.fn().mockResolvedValue({
        gmp: { contract_value: 0, computed: 0 },
        totals: { budget: 0 },
        completion: { eac: 0, projected_over_under: 0 },
        buyout: { packages: 0, bought_out: 0, budget: 0, awarded: 0, savings: 0 },
      }),
      projectPulse: vi.fn().mockResolvedValue({ cost: {} }),
    });
    const el = await renderCostBrief(host);
    expect(el.textContent).toContain("No GMP agreed yet");
    expect(el.textContent).toContain("Pulse has no unpriced-change count yet");
    expect(el.textContent).not.toMatch(/\bEAC \$0\b/);
  });

  it("a failed engine is a reason, never a plausible zero", async () => {
    const host = ctx({
      gmpBudget: vi.fn().mockRejectedValue(new Error("gmp down")),
      projectPulse: vi.fn().mockRejectedValue(new Error("pulse down")),
    });
    const el = await renderCostBrief(host);
    expect(el.querySelectorAll("[data-unavailable]")).toHaveLength(3);
    const text = el.textContent ?? "";
    expect(text).toContain("gmp down");
    expect(text).toContain("pulse down");
    expect(text).not.toMatch(/\b0 unpriced\b/);
  });
});

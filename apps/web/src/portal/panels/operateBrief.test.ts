import { describe, expect, it, vi } from "vitest";

import type { PanelContext } from "../panelContext";
import { OPERATE_BRIEF_QUESTIONS, renderOperateBrief } from "./operateBrief";

function ctx(api: Record<string, unknown>): PanelContext {
  return {
    root: document.createElement("div"),
    host: { projectId: () => "p1", api } as unknown as PanelContext["host"],
    mods: [],
    activeKey: "__operations__",
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

describe("R36-ROOM-BRIEFS — Operate", () => {
  it("names the three facility questions", () => {
    expect(OPERATE_BRIEF_QUESTIONS.map((q) => q.key)).toEqual(["overdue", "pm", "fci"]);
  });

  it("renders those answers from existing engines", async () => {
    const host = ctx({
      cmmsKpis: vi.fn().mockResolvedValue({
        total: 10, open: 4, completed: 6, overdue: 2,
        pm_compliance_pct: 81, mttr_days: 3.5,
      }),
      fcaIndex: vi.fn().mockResolvedValue({
        elements: 40, open_deficiencies: 5, fci_pct: 7.2, band: "fair", note: "",
      }),
    });
    const el = await renderOperateBrief(host);
    expect(el.querySelectorAll("[data-brief]")).toHaveLength(3);
    expect(el.textContent).toContain("2 overdue");
    expect(el.textContent).toContain("81%");
    expect(el.textContent).toContain("FCI 7.2%");
    expect(el.querySelector("[data-unavailable]")).toBeNull();
  });

  it("null PM compliance and no FCA elements are sentences, never 0%", async () => {
    const host = ctx({
      cmmsKpis: vi.fn().mockResolvedValue({
        total: 0, open: 0, completed: 0, overdue: 0, pm_compliance_pct: null, mttr_days: null,
      }),
      fcaIndex: vi.fn().mockResolvedValue({
        elements: 0, open_deficiencies: 0, fci_pct: 0, band: "unknown", note: "",
      }),
    });
    const el = await renderOperateBrief(host);
    expect(el.textContent).toContain("not scored yet");
    expect(el.textContent).toContain("No FCA elements scored");
    expect(el.textContent).not.toMatch(/\bFCI 0%/);
    expect(el.textContent).not.toMatch(/\b0% · MTTR/);
  });

  it("a failed engine is a reason, never a plausible zero", async () => {
    const host = ctx({
      cmmsKpis: vi.fn().mockRejectedValue(new Error("cmms down")),
      fcaIndex: vi.fn().mockRejectedValue(new Error("fca down")),
    });
    const el = await renderOperateBrief(host);
    expect(el.querySelectorAll("[data-unavailable]")).toHaveLength(3);
    const text = el.textContent ?? "";
    expect(text).toContain("cmms down");
    expect(text).toContain("fca down");
    expect(text).not.toMatch(/\bFCI 0%/);
  });
});

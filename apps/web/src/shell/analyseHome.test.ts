import { describe, expect, it } from "vitest";

import { ANALYSE_TASK_KEYS } from "./destinations";
import { ANALYSE_TASKS, renderAnalyseHome } from "./analyseHome";

describe("UX-DUP-DESTINATIONS — Analyse home", () => {
  it("names the three existing dests as tasks, not a fourth engine", () => {
    expect(ANALYSE_TASKS.map((t) => t.key)).toEqual([...ANALYSE_TASK_KEYS]);
  });

  it("renders three enabled tasks that navigate to those dests", () => {
    const host = document.createElement("div");
    const seen: string[] = [];
    renderAnalyseHome({
      root: host,
      activeKey: "__analyse__",
      bar: (title) => {
        const b = document.createElement("div");
        b.textContent = title;
        return b;
      },
      buildNav: () => undefined,
      renderHome: async () => undefined,
      hasDest: () => true,
      navigate: (k) => { seen.push(k); },
    });
    const buttons = [...host.querySelectorAll("button")];
    expect(buttons).toHaveLength(3);
    buttons[1]!.click();
    expect(seen).toEqual(["__modelanalysis__"]);
  });
});

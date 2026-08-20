import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { describe, expect, it, vi } from "vitest";

import {
  STEPS_BY_WORKSPACE, firstOpenStep, mountReadinessStrip, readinessStepKeys,
  type ReadinessBrief, type ReadinessStep,
} from "./readinessStrip";

const step = (over: Partial<ReadinessStep> & Pick<ReadinessStep, "key" | "status">): ReadinessStep => ({
  n: 1, title: over.key, dest: `__${over.key}__`, gaps: [], ...over,
});

const brief = (steps: ReadinessStep[], over: Partial<ReadinessBrief> = {}): ReadinessBrief => ({
  readiness_pct: 40, ready_steps: 2, gap_steps: 3, step_count: 8,
  grounded_in_place: true, steps, ...over,
});

describe("readinessStepKeys scopes the protocol, and never empties the strip", () => {
  it("a designer sees place/program/design/regulatory, not delivery", () => {
    expect(readinessStepKeys("design", "all")).toEqual(
      ["place", "program", "design", "regulatory"]);
    expect(readinessStepKeys("design", "architect")).toEqual(
      ["place", "program", "design", "regulatory"]);
  });

  it("a superintendent on the GC home sees field steps, not feasibility", () => {
    expect(readinessStepKeys("construction", "superintendent")).toEqual(
      ["delivery", "risk", "handover"]);
    expect(readinessStepKeys("design", "engineer")).toEqual(
      ["design", "regulatory", "place"]);
  });

  it("a superintendent browsing Design still sees Design's steps rather than nothing", () => {
    // Intersecting with delivery/risk/handover would empty the strip. An empty "what's next"
    // on a live project is worse than showing the workspace's own questions.
    expect(readinessStepKeys("design", "superintendent")).toEqual(
      ["place", "program", "design", "regulatory"]);
  });

  it("an unknown workspace falls back to the builder's set", () => {
    expect(readinessStepKeys("nonsense", "all")).toEqual(
      [...STEPS_BY_WORKSPACE.construction!]);
  });
});

describe("firstOpenStep is the gap the button names", () => {
  it("skips ready steps and returns the first partial or gap", () => {
    const steps = [
      step({ key: "place", status: "ready" }),
      step({ key: "design", status: "partial", title: "Design integration" }),
      step({ key: "regulatory", status: "gap" }),
    ];
    expect(firstOpenStep(steps)?.key).toBe("design");
  });

  it("is null when every scoped step is ready — the strip still renders, the hop does not", () => {
    expect(firstOpenStep([step({ key: "place", status: "ready" })])).toBeNull();
  });
});

describe("mountReadinessStrip", () => {
  it("fails open — a thrown brief names the gap instead of looking like nothing is next", async () => {
    const host = document.createElement("div");
    await mountReadinessStrip(host, {
      load: async () => { throw new Error("offline"); },
      workspace: "design", persona: "all", onOpen: () => {},
    });
    expect(host.querySelector("[data-readiness=unavailable]")?.textContent)
      .toMatch(/Readiness unavailable/);
    expect(host.querySelector("[data-readiness=strip]")).toBeNull();
  });

  it("renders scoped pills and hops to the first gap", async () => {
    const host = document.createElement("div");
    const onOpen = vi.fn();
    await mountReadinessStrip(host, {
      load: async () => brief([
        step({ n: 1, key: "place", title: "Place & context", status: "gap", dest: "__modelanalysis__",
          gaps: ["Jurisdiction"] }),
        step({ n: 5, key: "design", title: "Design integration", status: "ready", dest: "__modelqa__" }),
        step({ n: 6, key: "delivery", title: "Delivery strategy", status: "gap", dest: "__schedule__" }),
      ]),
      workspace: "design", persona: "all", onOpen,
    });
    expect(host.querySelector("[data-readiness=strip]")).toBeTruthy();
    expect(host.textContent).toContain("Place & context");
    expect(host.textContent).toContain("Design integration");
    expect(host.textContent).not.toContain("Delivery strategy"); // construction-only
    const close = [...host.querySelectorAll("button")].find((b) => b.textContent?.includes("Close this gap"));
    expect(close?.textContent).toMatch(/Place & context/);
    close!.click();
    expect(onOpen).toHaveBeenCalledWith("__modelanalysis__");
  });

  it("honours the server's scoped step order when present", async () => {
    const host = document.createElement("div");
    await mountReadinessStrip(host, {
      load: async () => brief([
        step({ key: "design", title: "Design integration", status: "ready" }),
        step({ key: "regulatory", title: "Regulatory path", status: "gap" }),
        step({ key: "place", title: "Place & context", status: "partial" }),
      ], { scope: { workspace: "design", persona: "engineer",
        keys: ["design", "regulatory", "place"] } }),
      workspace: "design", persona: "engineer", onOpen: () => {},
    });
    const labels = [...host.querySelectorAll("[data-readiness=strip] button.tool-btn")]
      .map((b) => b.textContent);
    expect(labels[0]).toMatch(/Design integration/);
    expect(labels[1]).toMatch(/Regulatory path/);
    expect(labels[2]).toMatch(/Place & context/);
  });

  it("says when the project is not grounded, rather than implying the score is enough", async () => {
    const host = document.createElement("div");
    await mountReadinessStrip(host, {
      load: async () => brief([step({ key: "place", status: "gap" })], { grounded_in_place: false }),
      workspace: "design", persona: "all", onOpen: () => {},
    });
    expect(host.textContent).toMatch(/Not grounded in place/);
  });

  it("portal.ts actually mounts it on home — defined-but-never-called is this repo's expensive miss", () => {
    const src = readFileSync(resolve(process.cwd(), "src/portal/portal.ts"), "utf8");
    expect(src).toMatch(/from "\.\/panels\/readinessStrip"/);
    expect(src).toContain("mountReadinessStrip");
    expect(src).toContain("masterBuilderBrief");
  });
});

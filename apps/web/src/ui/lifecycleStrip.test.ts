import { describe, expect, it } from "vitest";
import { buildLifecycleStrip } from "./lifecycleStrip";
import type { LifecycleStrip, StripState, StripStatus } from "../api/types";

/**
 * R26-INSPECTOR. The engine already refuses to conflate "no" with "we did not ask"; the risk is that
 * the *rendering* quietly re-conflates them by making unknown look like a paler failure. These tests
 * pin the three distinctions the strip exists to show.
 */
const ORDER = ["designed", "checked", "priced", "scheduled", "installed", "verified"] as const;

function state(key: string, status: StripStatus, detail = ""): StripState {
  return { key, label: key[0]!.toUpperCase() + key.slice(1), status,
    means: `what ${key} means`, detail, advance: status === "done" ? null : `do ${key}` };
}

function strip(over: Partial<LifecycleStrip> = {}): LifecycleStrip {
  return {
    guid: "1kP9x7Qa",
    states: ORDER.map((k) => state(k, k === "designed" ? "done" : "unknown")),
    reached: "designed", done_count: 1, unknown_count: 5,
    next: { key: "checked", advance: "Run Model Health and clear its findings" },
    inconsistencies: [],
    ...over,
  };
}

const pills = (root: HTMLElement) => [...root.querySelectorAll<HTMLElement>(".lcstrip-pill")];

describe("unknown is rendered as its own state, not as a failure", () => {
  it("marks each pill with its status so the three are distinguishable", () => {
    const p = pills(buildLifecycleStrip(strip()));
    expect(p.map((x) => x.dataset.status))
      .toEqual(["done", "unknown", "unknown", "unknown", "unknown", "unknown"]);
    expect(p[1]!.className).toContain("is-unknown");
    expect(p[1]!.className).not.toContain("is-none");
  });

  it("says in the tooltip that unknown is not no — the distinction has to be readable", () => {
    const p = pills(buildLifecycleStrip(strip()));
    expect(p[1]!.title).toMatch(/could not check/i);
    const told = strip({ states: ORDER.map((k) => state(k, k === "designed" ? "done" : "none")) });
    expect(pills(buildLifecycleStrip(told))[1]!.title).toMatch(/the answer is no/i);
  });

  it("counts the unknowns in the header rather than burying them", () => {
    expect(buildLifecycleStrip(strip()).querySelector(".lcstrip-unk")?.textContent).toBe("5 unknown");
    const none = strip({ unknown_count: 0 });
    expect(buildLifecycleStrip(none).querySelector(".lcstrip-unk")).toBeNull();
  });
});

describe("reached is contiguous, and a detached tick is marked as one", () => {
  it("reports the furthest contiguous state, not the count of ticks", () => {
    const gap = strip({
      states: [state("designed", "done"), state("checked", "done"), state("priced", "none"),
        state("scheduled", "done"), state("installed", "done"), state("verified", "done")],
      reached: "checked", done_count: 5, unknown_count: 0,
      inconsistencies: ["Scheduled is complete but Priced is not — one of them is wrong"],
    });
    const root = buildLifecycleStrip(gap);
    expect(root.querySelector(".lcstrip-reached")!.textContent).toBe("reached Checked");
    // the three later ticks are true, but must not read as progress the element has made
    const p = pills(root);
    expect(p.slice(3).every((x) => x.className.includes("is-detached"))).toBe(true);
    expect(p[1]!.className).not.toContain("is-detached");
  });

  it("shows an out-of-order strip's inconsistency rather than smoothing it", () => {
    const gap = strip({ inconsistencies: ["Verified is complete but Installed is not — one of them is wrong"] });
    expect(buildLifecycleStrip(gap).querySelector(".lcstrip-bad")!.textContent)
      .toContain("Verified is complete but Installed is not");
  });

  it("says so plainly when the element is not in the model at all", () => {
    const bare = strip({ reached: null });
    expect(buildLifecycleStrip(bare).querySelector(".lcstrip-reached")!.textContent)
      .toBe("reached not in the model");
  });
});

describe("the strip prescribes, it does not only diagnose", () => {
  it("names the next step", () => {
    expect(buildLifecycleStrip(strip()).querySelector(".lcstrip-next")!.textContent)
      .toBe("Next — Checked: Run Model Health and clear its findings");
  });

  it("stays quiet when there is nothing left to do", () => {
    const done = strip({
      states: ORDER.map((k) => state(k, "done")), reached: "verified",
      done_count: 6, unknown_count: 0, next: null,
    });
    const root = buildLifecycleStrip(done);
    expect(root.querySelector(".lcstrip-next")).toBeNull();
    expect(pills(root).every((p) => p.title.includes("→"))).toBe(false);
  });
});

describe("rendering is DOM construction, so element text cannot become markup", () => {
  it("escapes a hostile detail by never parsing it", () => {
    const evil = strip({
      states: [state("designed", "done", "<img src=x onerror=alert(1)>"),
        ...ORDER.slice(1).map((k) => state(k, "unknown"))],
    });
    const root = buildLifecycleStrip(evil);
    expect(root.querySelector("img")).toBeNull();
    expect(root.querySelector(".lcstrip-detail")!.textContent).toBe("<img src=x onerror=alert(1)>");
  });
});

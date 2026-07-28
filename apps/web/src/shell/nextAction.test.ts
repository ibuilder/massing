import { describe, expect, it } from "vitest";

import type { WorkQueue } from "../api/types";
import { candidatesFrom, daysUntil, headerAction, renderHeaderAction } from "./nextAction";

/**
 * NEXT BEST ACTION.
 *
 * The room tabs say how much is in your court; this says what to do about it. One button, one verb.
 *
 * The two judgement calls worth guarding are both about honesty rather than ranking (the ranking is
 * already tested in `pulse.test.ts`): an item you **cannot act on** must never be offered as the next
 * action, and a due date must not be turned into a lie by comparing instants instead of days.
 */

const NOW = new Date("2026-07-28T17:00:00Z");

function queue(items: Partial<WorkQueue["buckets"][0]["items"][0]>[]): WorkQueue {
  return {
    buckets: [{
      key: "b", label: "B", means: "", count: items.length,
      items: items.map((i, n) => ({
        module: "rfi", module_name: "RFI", icon: "?", id: String(n),
        ref: i.ref ?? `R-${n}`, title: i.title ?? "t", state: "open",
        assignee: null, reason: "yours", due: i.due ?? null, bucket: "b",
        actions: i.actions ?? ["Answer"], blocked_actions: i.blocked_actions ?? [],
      })),
    }],
    total: items.length, actionable: items.length, no_action: 0,
  };
}

describe("due dates are compared as days, not instants", () => {
  it("something due TODAY is not overdue at 5pm", () => {
    // Telling somebody they are late for something due today is how a queue loses credibility.
    expect(daysUntil("2026-07-28T09:00:00Z", NOW)).toBe(0);
  });

  it("counts forward and backward in whole days", () => {
    expect(daysUntil("2026-07-29T23:00:00Z", NOW)).toBe(1);
    expect(daysUntil("2026-07-27T01:00:00Z", NOW)).toBe(-1);
    expect(daysUntil("2026-08-04T12:00:00Z", NOW)).toBe(7);
  });

  it("no date and a bad date are both 'no date', never 0", () => {
    // 0 would read as "due today" — a fabricated deadline is worse than none.
    expect(daysUntil(null, NOW)).toBeNull();
    expect(daysUntil(undefined, NOW)).toBeNull();
    expect(daysUntil("not-a-date", NOW)).toBeNull();
    expect(daysUntil("", NOW)).toBeNull();
  });
});

describe("only offer what the caller can actually run", () => {
  it("an item with no runnable action is not a candidate", () => {
    const q = queue([{ ref: "A-1", actions: [] }, { ref: "A-2", actions: ["Review"] }]);
    expect(candidatesFrom(q, NOW).map((c) => c.ref)).toEqual(["A-2"]);
  });

  it("a blocked action does not become THE recommendation", () => {
    // blocked_actions need the record filled in first. Offering one sends somebody to a form and
    // calls it a recommendation.
    const q = queue([{ ref: "B-1", actions: [], blocked_actions: ["Certify"] }]);
    expect(candidatesFrom(q, NOW)).toEqual([]);
    expect(headerAction(q, NOW)).toBeNull();
  });

  it("the verb comes from the item, not from us", () => {
    const q = queue([{ ref: "C-1", actions: ["Price"] }]);
    expect(headerAction(q, NOW)!.label).toBe("Price C-1");
  });
});

describe("the one action", () => {
  it("picks the overdue item over one due today", () => {
    const q = queue([
      { ref: "SUB-1", due: "2026-07-28T00:00:00Z" },
      { ref: "RFI-118", due: "2026-07-27T00:00:00Z" },
    ]);
    const a = headerAction(q, NOW)!;
    expect(a.ref).toBe("RFI-118");
    expect(a.when).toBe("Overdue 1d");
    expect(a.urgent).toBe(true);
  });

  it("reads naturally across the three states", () => {
    expect(headerAction(queue([{ ref: "X", due: "2026-07-28T00:00:00Z" }]), NOW)!.when).toBe("Due today");
    expect(headerAction(queue([{ ref: "X", due: "2026-07-31T00:00:00Z" }]), NOW)!.when).toBe("Due in 3d");
    expect(headerAction(queue([{ ref: "X", due: null }]), NOW)!.when).toBeNull();
  });

  it("due-today counts as urgent; a future date does not", () => {
    expect(headerAction(queue([{ ref: "X", due: "2026-07-28T00:00:00Z" }]), NOW)!.urgent).toBe(true);
    expect(headerAction(queue([{ ref: "X", due: "2026-08-05T00:00:00Z" }]), NOW)!.urgent).toBe(false);
  });

  it("an empty or missing queue has no action, not a made-up one", () => {
    expect(headerAction(queue([]), NOW)).toBeNull();
    expect(headerAction(null, NOW)).toBeNull();
    expect(headerAction(undefined, NOW)).toBeNull();
    expect(headerAction({ buckets: [] } as never, NOW)).toBeNull();
  });
});

describe("rendering", () => {
  it("draws a caption and one button", () => {
    const host = document.createElement("div");
    renderHeaderAction(host, headerAction(queue([{ ref: "RFI-9", due: "2026-07-27T00:00:00Z" }]), NOW), () => {});
    expect(host.hidden).toBe(false);
    expect(host.querySelector(".nba-cap")!.textContent).toMatch(/next best action/i);
    expect(host.querySelectorAll(".nba-btn").length).toBe(1);
    expect(host.querySelector(".nba-btn")!.textContent).toMatch(/Answer RFI-9.*Overdue 1d/);
  });

  it("marks urgency on the button, so colour is decided once", () => {
    const host = document.createElement("div");
    renderHeaderAction(host, headerAction(queue([{ ref: "X", due: "2026-07-20T00:00:00Z" }]), NOW), () => {});
    expect(host.querySelector(".nba-btn")!.className).toContain("nba-urgent");
  });

  it("renders NOTHING when there is nothing to do", () => {
    // Not "Nothing to do" — a claim that ages badly between polls and teaches people to stop reading
    // the one place urgency lives.
    const host = document.createElement("div");
    renderHeaderAction(host, null, () => {});
    expect(host.hidden).toBe(true);
    expect(host.innerHTML).toBe("");
  });

  it("record text goes in as TEXT, never as markup", () => {
    const host = document.createElement("div");
    const q = queue([{ ref: '<img src=x onerror="alert(1)">', due: null }]);
    renderHeaderAction(host, headerAction(q, NOW), () => {});
    expect(host.querySelector("img")).toBeNull();
    expect(host.querySelector(".nba-btn")!.textContent).toContain("<img");
  });

  it("clicking reports the action", () => {
    const host = document.createElement("div");
    const seen: string[] = [];
    renderHeaderAction(host, headerAction(queue([{ ref: "Z-1" }]), NOW), (a) => seen.push(a.ref));
    host.querySelector<HTMLButtonElement>(".nba-btn")!.click();
    expect(seen).toEqual(["Z-1"]);
  });

  it("re-rendering replaces rather than stacking", () => {
    const host = document.createElement("div");
    renderHeaderAction(host, headerAction(queue([{ ref: "A" }]), NOW), () => {});
    renderHeaderAction(host, headerAction(queue([{ ref: "B" }]), NOW), () => {});
    expect(host.querySelectorAll(".nba-btn").length).toBe(1);
    expect(host.querySelector(".nba-btn")!.textContent).toContain("B");
  });
});

describe("the server's action id is not a label", () => {
  it("capitalises the verb for display", async () => {
    const { verbLabel } = await import("./nextAction");
    expect(verbLabel("close")).toBe("Close");
    expect(verbLabel("answer")).toBe("Answer");
    expect(verbLabel("Review")).toBe("Review");
  });

  it("turns snake_case into words, not shouting", async () => {
    const { verbLabel } = await import("./nextAction");
    expect(verbLabel("request_info")).toBe("Request info");
    expect(verbLabel("mark-complete")).toBe("Mark complete");
  });

  it("an empty verb yields an empty label rather than 'Undefined'", async () => {
    const { verbLabel } = await import("./nextAction");
    expect(verbLabel("")).toBe("");
    expect(verbLabel(null as never)).toBe("");
  });

  it("the header uses it — 'close ACT-001' reads like a typo", () => {
    const q = queue([{ ref: "ACT-001", actions: ["close"], due: null }]);
    expect(headerAction(q, NOW)!.label).toBe("Close ACT-001");
  });
});

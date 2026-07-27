import { describe, expect, it, beforeEach } from "vitest";
import { orderRooms, preselectedRoom, roomBadge, spineEnabled } from "./spine";
import type { RoomDef } from "../api/types";

/**
 * R26-SHELL. The audit found seven workspaces carrying four different left-rail taxonomies, so
 * nothing learned in one transferred to the next. The spine is one constant structure for every role.
 * What is tested here is the property that distinguishes a spine from another mode switch: a
 * workspace **weights** it and never **replaces** it.
 */
const ROOMS: RoomDef[] = [
  { id: "model", label: "Model", job: "Author, coordinate and document the building", count: 38, modules: ["rfi", "drawing"] },
  { id: "cost", label: "Cost", job: "Price it, buy it out, change it and pay for it", count: 37, modules: ["budget"] },
  { id: "schedule", label: "Schedule", job: "Sequence it, run the field, track what got built", count: 41, modules: ["activity"] },
  { id: "deal", label: "Deal", job: "Underwrite it, fund it, lease it and dispose of it", count: 16, modules: ["proforma"] },
  { id: "work", label: "Work", job: "Whatever is in your court right now", count: 0, modules: [] },
];

describe("the spine is weighted by a workspace, never replaced", () => {
  it("orders the workspace's room first", () => {
    expect(orderRooms(ROOMS, "construction")[0]!.id).toBe("schedule");
    expect(orderRooms(ROOMS, "finance")[0]!.id).toBe("deal");
    expect(orderRooms(ROOMS, "design")[0]!.id).toBe("model");
  });

  it("NEVER drops a room — that is the whole difference from a mode switch", () => {
    for (const ws of ["construction", "finance", "design", "model", "unknown", "", null]) {
      const ordered = orderRooms(ROOMS, ws);
      expect(ordered).toHaveLength(ROOMS.length);
      expect(new Set(ordered.map((r) => r.id))).toEqual(new Set(ROOMS.map((r) => r.id)));
    }
  });

  it("falls back to Work for an unknown workspace rather than guessing a domain", () => {
    expect(preselectedRoom("nonsense")).toBe("work");
    expect(preselectedRoom(null)).toBe("work");
    expect(preselectedRoom(undefined)).toBe("work");
  });

  it("maps every shipped workspace to a room", () => {
    for (const ws of ["model", "drawings", "studio", "design", "construction", "finance", "developer"]) {
      expect(preselectedRoom(ws)).not.toBe("work");
    }
  });
});

describe("the flag — the new shell is the front door, with a way back", () => {
  beforeEach(() => localStorage.clear());

  it("is ON by default as of v0.3.715 — the redesign is the product now", () => {
    expect(spineEnabled("")).toBe(true);
  });

  it("?shell=classic is still a way BACK, and it STICKS", () => {
    // A redesign nobody can back out of has to be perfect on the first try. This is the escape
    // hatch, and it has to survive a reload or it is not one.
    expect(spineEnabled("?shell=classic")).toBe(false);
    expect(spineEnabled("")).toBe(false);
  });

  it("?shell=spine opts back in after an opt-out", () => {
    spineEnabled("?shell=classic");
    expect(spineEnabled("?shell=spine")).toBe(true);
    expect(spineEnabled("")).toBe(true);
  });

  it("a deliberate opt-out is NOT overridden by the new default", () => {
    // THE trap in flipping this. The old scheme stored presence/absence, so "never expressed a
    // preference" and "chose classic" were the same absent key — inverting the default would have
    // silently dragged every opted-out user into the new shell, which is the one group that had
    // already said no. The value is explicit now, so the two states are distinguishable.
    localStorage.setItem("shell-spine", "0");
    expect(spineEnabled("")).toBe(false);
  });

  it("an existing opt-IN still reads as on", () => {
    localStorage.setItem("shell-spine", "1");
    expect(spineEnabled("")).toBe(true);
  });
});

describe("badges are ball-in-YOUR-court, not totals", () => {
  it("sums only the caller's items across the room's modules", () => {
    const room = ROOMS[0]!;
    expect(roomBadge(room, { rfi: 3, drawing: 1 })).toBe(4);
    // a module with nothing in your court contributes nothing — a badge you cannot act on is noise
    expect(roomBadge(room, { rfi: 0, drawing: 0 })).toBe(0);
    expect(roomBadge(room, {})).toBe(0);
  });

  it("ignores counts for modules that are not in the room", () => {
    expect(roomBadge(ROOMS[1]!, { rfi: 99, budget: 2 })).toBe(2);
  });
});

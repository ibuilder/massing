import { describe, expect, it, beforeEach } from "vitest";
import { FALLBACK_ROOMS, ROOM_HOME, ROOM_IDS, destRoom, orderRooms, preselectedRoom, roomBadge, spineEnabled } from "./spine";
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

describe("the rail degrades its badges, not the whole shell (v0.3.718)", () => {
  it("the fallback rooms are exactly the canonical five, in order", () => {
    // Two lists encoding one fact WILL drift. This is the assertion that stops it.
    expect(FALLBACK_ROOMS.map((r) => r.id)).toEqual([...ROOM_IDS]);
  });

  it("every fallback room carries a label and a job, so a degraded rail is still legible", () => {
    for (const r of FALLBACK_ROOMS) {
      expect(r.label.length, r.id).toBeGreaterThan(2);
      expect(r.job.length, r.id).toBeGreaterThan(20);
    }
  });

  it("fallback rooms carry NO counts — a badge nobody measured would be a lie", () => {
    // The allocation is what `GET /rooms` supplies. Rendering a zero badge from a failed request
    // would say "nothing is in your court", which is a claim, and one we cannot support.
    expect(FALLBACK_ROOMS.every((r) => r.count === 0 && r.modules.length === 0)).toBe(true);
  });

  it("they order the same way server rooms do", () => {
    const ordered = orderRooms([...FALLBACK_ROOMS], "construction");
    expect(ordered[0]?.id).toBe(preselectedRoom("construction"));
    expect(ordered).toHaveLength(FALLBACK_ROOMS.length);
  });
});

describe("every room opens onto something", () => {
  /**
   * The defect this locks down shipped in the primary navigation and survived every gate: Cost,
   * Schedule and Work all resolved to the same host workspace, so clicking any of them rendered the
   * identical screen. Nothing was broken in a way a unit test could see — each room had its
   * destinations, the tab bar built all five, the allocation endpoint placed 132 modules. The
   * missing piece was the one nobody had written down: *where a room opens*.
   */
  it("names a home for every room, so no tab can be decorative", () => {
    for (const id of ROOM_IDS) {
      expect(Object.prototype.hasOwnProperty.call(ROOM_HOME, id), `no ROOM_HOME entry for "${id}"`)
        .toBe(true);
    }
  });

  it("a room's home belongs to that room", () => {
    // The check that makes the table safe to keep. A home pointing into another room would navigate
    // somewhere real and look fine, while quietly making two tabs synonyms again.
    for (const [room, home] of Object.entries(ROOM_HOME)) {
      if (home === null) continue;
      expect(destRoom(home), `${room}'s home "${home}" is not in the ${room} room`).toBe(room);
    }
  });

  it("only Design has no destination home — because the viewer is the room", () => {
    const nulls = Object.entries(ROOM_HOME).filter(([, v]) => v === null).map(([k]) => k);
    expect(nulls).toEqual(["design"]);
  });

  it("no two rooms share a home", () => {
    const homes = Object.values(ROOM_HOME).filter((h): h is string => h !== null);
    expect(new Set(homes).size).toBe(homes.length);
  });
});

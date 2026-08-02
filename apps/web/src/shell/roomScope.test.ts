/**
 * ROOM-NAV — the rail is scoped to the ACTIVE room; the other rooms are the tab bar's job.
 *
 * Regression context (2026-08-02): the rail rendered all seven room groups in every workspace,
 * which read as "every module on every screen", and forced room switching to be a DOM
 * click-simulation (a 4s poll in main.ts) against a rail the workspace switch was rebuilding.
 * The poll lost visibly: Planning and Schedule rendered EMPTY content panes, and Cost and Work
 * displayed the previous room's rail — measured live before the fix. These tests pin the pure
 * selection logic the portal now renders from, and the host tables the dispatch relies on.
 */
import { describe, expect, it } from "vitest";

import { FALLBACK_ROOMS, ROOM_HOST, ROOM_IDS, portalRooms, preselectedRoom, visibleRooms } from "./spine";

const rooms = [...FALLBACK_ROOMS];

describe("visibleRooms — the rail's room selection", () => {
  it("scoped: exactly the active room, nothing else", () => {
    const v = visibleRooms(rooms, "construction", "planning", false);
    expect(v.map((r) => r.id)).toEqual(["planning"]);
  });

  it("escape hatch: active room first, then every other room — none lost", () => {
    const v = visibleRooms(rooms, "construction", "cost", true);
    expect(v[0]?.id).toBe("cost");
    expect(v.map((r) => r.id).sort()).toEqual([...ROOM_IDS].sort());
  });

  it("an unknown active room falls back to ALL rooms, never to an empty rail", () => {
    // A rail that renders nothing because a state string drifted is the worst version of the bug —
    // indistinguishable from a slow network, and the user stops looking.
    const v = visibleRooms(rooms, "construction", "no-such-room", false);
    expect(v.length).toBe(rooms.length);
  });

  it("every room can be the active one and selects itself", () => {
    for (const id of ROOM_IDS) {
      expect(visibleRooms(rooms, "developer", id, false).map((r) => r.id)).toEqual([id]);
    }
  });
});

describe("ROOM_HOST / portalRooms — the dispatch tables", () => {
  it("every room has a host workspace", () => {
    // A room with no host is a tab that switches to `construction` by accident.
    for (const id of ROOM_IDS) {
      expect(ROOM_HOST[id], `room "${id}" has no host workspace`).toBeTruthy();
    }
  });

  it("ROOM_HOST names no room that does not exist", () => {
    expect(Object.keys(ROOM_HOST).filter((r) => !(ROOM_IDS as readonly string[]).includes(r))).toEqual([]);
  });

  it("each portal claims a disjoint, non-empty set of rooms", () => {
    // The aec:room event is broadcast; exactly ONE portal instance must respond to each room, or a
    // hidden portal steals the navigation (two responders) / nobody lands (zero).
    const filters = ["construction", "developer", "design"] as const;
    const claimed = filters.flatMap((f) => portalRooms(f));
    expect(claimed.length).toBe(new Set(claimed).size);          // disjoint
    for (const f of filters) expect(portalRooms(f).length).toBeGreaterThan(0);
  });

  it("the construction portal hosts the four field rooms", () => {
    expect(portalRooms("construction").sort()).toEqual(["cost", "planning", "schedule", "work"]);
  });

  it("every portal's preselected room is one it actually claims", () => {
    // The default active room must be answerable by the portal that defaults to it — otherwise the
    // rail scopes to a room whose event handler would have rejected it.
    for (const f of ["construction", "developer", "design"] as const) {
      expect(portalRooms(f), `preselected room for ${f}`).toContain(preselectedRoom(f));
    }
  });
});

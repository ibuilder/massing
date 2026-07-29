import { describe, expect, it, beforeEach } from "vitest";
import { FALLBACK_ROOMS, ROOM_HOME, ROOM_IDS, destRoom, orderRooms, preselectedRoom, roomBadge } from "./spine";
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

describe("the shell has no opt-out — there is one front door (v0.3.779)", () => {
  beforeEach(() => localStorage.clear());

  it("exports no flag to read or set", async () => {
    // `?shell=classic` was the escape hatch while the spine proved itself. It became the default at
    // v0.3.715 and the hatch was deleted sixty-four releases later: two shells is two rails to
    // change, two places a bug can hide, and — as this repo actually managed — a render audit whose
    // verdict depends on which one it happened to measure. Asserting the exports are GONE is what
    // stops the flag being quietly reintroduced by a revert.
    const mod = await import("./spine") as Record<string, unknown>;
    expect(mod.spineEnabled, "spineEnabled must not come back").toBeUndefined();
    expect(mod.SPINE_FLAG, "the storage key must not come back").toBeUndefined();
  });

  it("the guarantee the two-shell period bought is still enforced elsewhere", async () => {
    // Deleting the comparison must not delete the property it protected. `parity.test` asserts the
    // room rail reaches every destination the lifecycle-stage catalog lists — that is what "nothing
    // became unreachable" now rests on, and it survives the shell that motivated it.
    const parity = await import("./parity.test?raw") as { default: string };
    expect(parity.default).toMatch(/unroomed|DEST_ROOM|destRoom/);
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

  it("a room's home RENDERS — it never carries `goto`", async () => {
    // The gate v0.3.770 needed and did not have.
    //
    // A `goto` destination hands off to another workspace and renders nothing in the portal, so a
    // landing check has nothing to observe. Pointing Deal at `__uw__` and faking the signal produced
    // exactly the defect the room work set out to kill: the tab lit, the marker said Underwriting,
    // and the content pane still showed Budget. Every gate passed, because the rationale forbidding
    // it lived in a COMMENT. It lives here now.
    const { ALL_DESTS } = await import("./destinations");
    const goto = new Set(ALL_DESTS.filter((d) => d.goto).map((d) => d.key));
    expect(goto.size, "if no destination hops workspaces this test is vacuous").toBeGreaterThan(0);
    for (const [room, home] of Object.entries(ROOM_HOME)) {
      if (home === null) continue;
      expect(goto.has(home), `${room}'s home "${home}" hops workspaces and cannot be landed on`)
        .toBe(false);
    }
  });

  it("no two rooms share a home", () => {
    const homes = Object.values(ROOM_HOME).filter((h): h is string => h !== null);
    expect(new Set(homes).size).toBe(homes.length);
  });
});

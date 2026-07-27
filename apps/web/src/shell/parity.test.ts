/**
 * LAYOUT PARITY — nothing the old rail reached became unreachable in the new one.
 *
 * `portal.ts` carries the comment "Both read the SAME destination catalog, so the two shells cannot
 * drift on what exists." That is a claim, and this session has been a long lesson in the difference
 * between a claim written in a comment and one a build enforces. The spine became the default at
 * v0.3.715; if a destination is reachable in the lifecycle-stage rail and reachable in **no room**,
 * it is not a cosmetic difference — it is a feature that silently left the product for everyone who
 * did not opt out.
 *
 * The comparison that matters is per workspace, because the two rails slice differently:
 *   - the STAGE rail shows `stagesFor(ws)` — that workspace's lifecycle slice;
 *   - the ROOM rail deliberately shows `[...shown, ...ALL_DESTS]` — everything the platform has, so
 *     a destination only the Developer rail used to surface is placed in a room rather than lost.
 * So the room rail should be a strict superset. This asserts that, rather than assuming it.
 */
import { describe, expect, it } from "vitest";

import { ALL_DESTS, STAGES_BY_WS, stagesFor } from "./destinations";
import { DEST_ROOM, ROOM_IDS, destRoom, unroomedDests } from "./spine";

const WORKSPACES = Object.keys(STAGES_BY_WS);
const HAS_EVERY_MODULE = () => true;

/** What the old rail surfaces for a workspace, with every module installed. */
function stageKeys(ws: string): string[] {
  return stagesFor(ws, HAS_EVERY_MODULE).flatMap(([, items]) => items.map((d) => d.key));
}

/** What the new rail files into rooms, given the same workspace. Mirrors portal.buildRoomRail. */
function roomedKeys(ws: string): string[] {
  const seen = new Set<string>();
  const out: string[] = [];
  for (const d of [...stagesFor(ws, HAS_EVERY_MODULE).flatMap(([, i]) => i), ...ALL_DESTS]) {
    if (seen.has(d.key)) continue;
    seen.add(d.key);
    if (destRoom(d.key)) out.push(d.key);
  }
  return out;
}

describe("every destination has a room", () => {
  it("no destination in the catalog is unroomed", () => {
    // A destination with no room is one nobody can reach in the default shell.
    expect(unroomedDests(ALL_DESTS.map((d) => d.key))).toEqual([]);
  });

  it("the room map has no entries for destinations that no longer exist", () => {
    // The other direction: a stale mapping is a room quietly promising something that is gone.
    const real = new Set(ALL_DESTS.map((d) => d.key));
    expect(Object.keys(DEST_ROOM).filter((k) => !real.has(k))).toEqual([]);
  });

  it("every room named in the map is a real room", () => {
    const bad = Object.entries(DEST_ROOM).filter(([, r]) => !(ROOM_IDS as readonly string[]).includes(r));
    expect(bad).toEqual([]);
  });
});

describe("the new rail is a superset of the old one, per workspace", () => {
  it.each(WORKSPACES)("%s loses nothing", (ws) => {
    const lost = stageKeys(ws).filter((k) => !roomedKeys(ws).includes(k));
    expect(lost, `destinations reachable in the ${ws} stage rail but in no room`).toEqual([]);
  });

  it("and it surfaces MORE than the stage rail did — that is the point of a spine", () => {
    // The old rail showed one workspace's slice; the spine's promise is that all of it stays
    // reachable, one click away, rather than hidden behind a mode switch.
    const gains = WORKSPACES.map((ws) => roomedKeys(ws).length - stageKeys(ws).length);
    expect(Math.min(...gains)).toBeGreaterThan(0);
  });

  it("every workspace reaches the whole catalog, not just its own stages", () => {
    for (const ws of WORKSPACES) {
      expect(roomedKeys(ws).sort()).toEqual(ALL_DESTS.map((d) => d.key).sort());
    }
  });
});

describe("the rooms are populated — none is a heading with nothing under it", () => {
  it.each([...ROOM_IDS])("%s has destinations", (room) => {
    // An empty room is worse than a missing one: it reads as "there is nothing here" rather than
    // "this lives elsewhere", and the user stops looking.
    const inRoom = ALL_DESTS.filter((d) => destRoom(d.key) === room);
    expect(inRoom.length, `room "${room}" is empty`).toBeGreaterThan(0);
  });

  it("the catalog is big enough that this test is measuring something", () => {
    // The vacuous-pass guard: if the catalog ever comes back empty, every assertion above passes.
    expect(ALL_DESTS.length).toBeGreaterThan(30);
    expect(WORKSPACES.length).toBeGreaterThan(2);
  });
});

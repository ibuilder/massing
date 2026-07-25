/**
 * R26-SHELL — the five-room spine.
 *
 * The audit's first finding: seven workspaces carry **four different left-rail taxonomies**, so
 * nothing a user learns in one transfers to the next, and modules land in more than one of them.
 * The spine replaces that with one constant structure — **Model · Cost · Schedule · Deal · Work** —
 * identical for every role. A workspace *weights and preselects* the spine; it never replaces it.
 *
 * Three properties matter more than the layout:
 *
 * 1. **The rooms come from the API, not from here.** `/rooms` derives the allocation from one
 *    section→room table. A shell that invents its own taxonomy is exactly how four of them came to
 *    exist, so this one refuses to guess: a module with no room is *reported*, never filed somewhere
 *    plausible.
 * 2. **Nothing is removed.** All 130+ modules stay reachable — from their room, from the element they
 *    are anchored to, from the work queue when it is your turn, and from ⌘K by name. The catalog
 *    survives as the fourth path rather than the only one.
 * 3. **It lives beside the current shell, not instead of it.** Behind a flag until it is demonstrably
 *    better, because replacing a working front door on the strength of a mock is how you lose the
 *    parts that were already right.
 */
import type { ApiClient } from "../api/client";
import type { RoomAllocation, RoomDef } from "../api/types";

/** Opt in with `?shell=spine`, or persistently via the stored preference. Off by default. */
export const SPINE_FLAG = "shell-spine";

export function spineEnabled(search: string = location.search): boolean {
  const q = new URLSearchParams(search).get("shell");
  if (q === "spine") { localStorage.setItem(SPINE_FLAG, "1"); return true; }
  if (q === "classic") { localStorage.removeItem(SPINE_FLAG); return false; }
  return localStorage.getItem(SPINE_FLAG) === "1";
}

/**
 * Which room a workspace opens in. This is the whole of what a workspace does to the spine — it
 * chooses a starting room and an ordering. It does not hide rooms: a PM who needs the model still has
 * Model, one click away, which is the point of a spine over a mode switch.
 */
const WORKSPACE_ROOM: Record<string, string> = {
  model: "model", drawings: "model", studio: "model", design: "model",
  construction: "schedule", finance: "deal", developer: "deal",
};

export function preselectedRoom(workspace: string | null | undefined): string {
  return WORKSPACE_ROOM[String(workspace || "").toLowerCase()] ?? "work";
}

/**
 * Order rooms for a workspace: its own room first, the rest in canonical order. Weighting rather than
 * filtering — a room that disappears is a room the user has to relearn where to find.
 */
export function orderRooms(rooms: RoomDef[], workspace: string | null | undefined): RoomDef[] {
  const first = preselectedRoom(workspace);
  const head = rooms.filter((r) => r.id === first);
  return [...head, ...rooms.filter((r) => r.id !== first)];
}

export interface SpineState {
  alloc: RoomAllocation;
  /** Modules the API could not place. Must be empty; surfaced rather than swallowed. */
  unplaced: { key: string; section: string }[];
}

/** Load the spine. A module with no room is a defect to report, not one to hide. */
export async function loadSpine(api: ApiClient): Promise<SpineState> {
  const alloc = await api.rooms();
  return { alloc, unplaced: alloc.unplaced ?? [] };
}

/** Count for a room's badge — ball-in-YOUR-court, not a total. A badge you cannot act on is noise. */
export function roomBadge(room: RoomDef, inCourt: Record<string, number>): number {
  return room.modules.reduce((n, key) => n + (inCourt[key] ?? 0), 0);
}

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

/** The five room ids, in canonical order. Mirrors `rooms.ROOMS` server-side. */
export const ROOM_IDS = ["model", "cost", "schedule", "deal", "work"] as const;

/**
 * Destination `__key__` → room.
 *
 * The API already rooms every *module*, by section. First-class destinations are panels rather than
 * modules, so they need their own table — and it follows the backend's rule exactly: a destination
 * with no room is **reported**, never filed somewhere plausible. Defaulting is what produced four
 * competing taxonomies in the first place; a mis-placed destination is invisible precisely because
 * it looks fine.
 *
 * Note `__uw__` is deliberately absent from `deal`'s panels and present here: it hops workspaces
 * rather than rendering, but the spine still has to say where it lives.
 */
export const DEST_ROOM: Record<string, string> = {
  // ── Model: the building and everything that describes it ──────────────────────────────────────
  __ids__: "model", __standards__: "model", __materials__: "model", __modulegraph__: "model",
  __spine__: "model", __modelqa__: "model", __modelanalysis__: "model", __bimkpi__: "model",
  __designmetrics__: "model", __spaceutil__: "model", __mepfittings__: "model",
  __program__: "model", __conceptrender__: "model", __documents__: "model",
  __masterbuilder__: "model", __responsibility__: "model", __resilience__: "model",
  // ── Cost: money against the building ──────────────────────────────────────────────────────────
  __budget__: "cost", __margin__: "cost", __selections__: "cost", __evm__: "cost",
  __wip__: "cost", __ledger__: "cost", __traceability__: "cost", __riskcost__: "cost",
  __benchmarks__: "cost",
  // ── Schedule: time, and the field that consumes it ────────────────────────────────────────────
  __schedule__: "schedule", __resload__: "schedule", __equipment__: "schedule",
  __topicboard__: "schedule", __turnover__: "schedule",
  // ── Deal: the asset as an investment ──────────────────────────────────────────────────────────
  __uw__: "deal", __land__: "deal", __massingopt__: "deal", __diligence__: "deal",
  __market__: "deal", __lifecycle__: "deal", __portfolio__: "deal",
  __operations__: "deal", __fca__: "deal", __energy__: "deal", __esg__: "deal",
  __assets__: "deal",
  // ── Work: whatever is in your court ───────────────────────────────────────────────────────────
  __workqueue__: "work", __review__: "work", __aiassist__: "work",
};

/** The room a destination belongs to, or null when it is unmapped — which is a defect, not a default. */
export function destRoom(key: string): string | null {
  const room = DEST_ROOM[key];
  return room && (ROOM_IDS as readonly string[]).includes(room) ? room : null;
}

/** Destination keys with no room. Must be empty; surfaced in the rail rather than swallowed. */
export function unroomedDests(keys: string[]): string[] {
  return keys.filter((k) => !destRoom(k));
}

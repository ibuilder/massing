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
 * 3. **It lived beside the old shell until it was demonstrably better** — behind a flag, because
 *    replacing a working front door on the strength of a mock is how you lose the parts that were
 *    already right. As of v0.3.715 it IS the front door: R26 is complete, and the live render audit
 *    passes against the spine specifically rather than against the classic shell it was once
 *    mistakenly run on. The flag survives inverted, as an opt-OUT, because a redesign nobody can
 *    back out of is a redesign that has to be perfect on the first try.
 */
import type { ApiClient } from "../api/client";
import type { RoomAllocation, RoomDef } from "../api/types";

/**
 * **On by default since v0.3.715.** `?shell=classic` opts out and the choice sticks; `?shell=spine`
 * opts back in.
 *
 * The stored value is now explicit — `"1"` on, `"0"` off — rather than present/absent. That detail
 * matters for the flip: under the old scheme "no preference" and "opted out" were the same absent
 * key, so inverting the default would have silently overridden every deliberate opt-out. Anyone who
 * had opted IN still has `"1"` and sees no change.
 */
export const SPINE_FLAG = "shell-spine";

export function spineEnabled(search: string = location.search): boolean {
  const q = new URLSearchParams(search).get("shell");
  if (q === "spine") { localStorage.setItem(SPINE_FLAG, "1"); return true; }
  if (q === "classic") { localStorage.setItem(SPINE_FLAG, "0"); return false; }
  return localStorage.getItem(SPINE_FLAG) !== "0";      // unset = the new default = on
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
 * The rooms with no server behind them (v0.3.718).
 *
 * The spine's *allocation* — which modules sit in which room, and the ball-in-your-court badges —
 * comes from `GET /rooms`. The rooms themselves are a fixed set that both sides already agree on, so
 * losing the request should cost the badges, not the shell.
 *
 * Before this existed, a failed allocation silently rebuilt the OLD rail. That was a defensible
 * trade while the spine was opt-in and a handful of people had chosen it; once it became the default
 * at v0.3.715 it meant anyone whose request failed got the previous shell with no explanation — and
 * from the outside that is indistinguishable from the redesign never having shipped. It is also how
 * an offline-first product quietly stops being offline-first.
 *
 * `label` and `job` mirror `rooms.ROOMS`; `spine.test` asserts the ids match `ROOM_IDS` so the two
 * lists cannot drift.
 */
export const FALLBACK_ROOMS: readonly RoomDef[] = [
  { id: "model", label: "Model", job: "Author, coordinate and document the building", count: 0, modules: [] },
  { id: "cost", label: "Cost", job: "Price it, buy it out, change it and pay for it", count: 0, modules: [] },
  { id: "schedule", label: "Schedule", job: "Sequence it, run the field, and track what got built", count: 0, modules: [] },
  { id: "deal", label: "Deal", job: "Underwrite it, fund it, lease it and dispose of it", count: 0, modules: [] },
  { id: "work", label: "Work", job: "Whatever is in your court right now", count: 0, modules: [] },
];

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

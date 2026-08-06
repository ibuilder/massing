/**
 * R26-SHELL — the room spine.
 *
 * The audit's first finding: seven workspaces carry **four different left-rail taxonomies**, so
 * nothing a user learns in one transfers to the next, and modules land in more than one of them.
 * The spine replaces that with one constant structure — **Deal · Design · Planning · Schedule · Cost
 * · Work · Operate** — identical for every role. (Model became **Design** in v0.3.766: the room was named for
 * one of its outputs, which left drawings and specifications looking like they belonged elsewhere —
 * and specifications actually had, filed under Preconstruction and therefore under Cost. **Planning**
 * split from Cost in the same change, so taking off and buying out stopped sharing a room with the
 * general ledger.) A workspace *weights and preselects* the spine; it never replaces it.
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
 *    already right. It became the default at v0.3.715 and the opt-out was **deleted at v0.3.779**,
 *    sixty-four releases later: two shells is two of everything — two rails to change, two paths for
 *    a bug to hide in, and a live audit whose result depends on which one it happened to measure
 *    (a mistake this repo actually made). The escape hatch earned its keep and then stopped being an
 *    escape hatch, because nobody was escaping.
 *
 *    What replaces it is not "trust us": `parity.test` still asserts the room rail reaches every
 *    destination the lifecycle-stage catalog lists, so the guarantee the two-shell period provided —
 *    *nothing became unreachable* — outlives the shell that motivated it.
 */
import type { ApiClient } from "../api/client";
import type { RoomAllocation, RoomDef } from "../api/types";

/**
 * Which room a workspace opens in. This is the whole of what a workspace does to the spine — it
 * chooses a starting room and an ordering. It does not hide rooms: a PM who needs the model still has
 * Model, one click away, which is the point of a spine over a mode switch.
 */
const WORKSPACE_ROOM: Record<string, string> = {
  model: "design", drawings: "design", studio: "design", design: "design",
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

/** The room ids, in canonical order. Mirrors `rooms.ROOMS` server-side. */
export const ROOM_IDS = ["deal", "design", "planning", "schedule", "cost", "work", "operate"] as const;

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
  { id: "deal", label: "Deal", job: "Underwrite it, fund it, lease it and dispose of it", count: 0, modules: [] },
  { id: "design", label: "Design", job: "Model it, draw it, specify it — the architect's and engineer's room", count: 0, modules: [] },
  { id: "planning", label: "Planning", job: "Take it off, estimate it, bid it, buy it out, contract it and get it approved", count: 0, modules: [] },
  { id: "schedule", label: "Schedule", job: "Sequence it, resource it and control it — the plan for time", count: 0, modules: [] },
  { id: "cost", label: "Cost", job: "Budget it, change it, bill it and account for it", count: 0, modules: [] },
  { id: "work", label: "Work", job: "Run the field — your court today, the log, safety, progress and the punch", count: 0, modules: [] },
  { id: "operate", label: "Operate", job: "Hand it over, maintain it, meter it and plan its renewal", count: 0, modules: [] },
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
  // ── Design: the building and everything that describes it ────────────────────────────────────
  __ids__: "design", __standards__: "design", __materials__: "design", __modulegraph__: "design",
  __spine__: "design", __modelqa__: "design", __modelanalysis__: "design", __bimkpi__: "design",
  __designmetrics__: "design", __spaceutil__: "design", __mepfittings__: "design",
  __program__: "design", __conceptrender__: "design", __documents__: "design",
  __drawings__: "design",   // the drawing set: generated from the model, so it lives with it
  // Moved into Design in v0.3.766. Energy is an engineering analysis run off the model geometry, and
  // an issue board records clashes and coordination questions raised *against* the model — neither
  // describes a deal or a sequence, which is where they had ended up.
  __energy__: "design", __topicboard__: "design",
  __masterbuilder__: "design", __responsibility__: "design", __resilience__: "design",
  // ── Cost: money against the building ──────────────────────────────────────────────────────────
  __budget__: "cost", __margin__: "cost", __selections__: "planning", __evm__: "cost",
  __wip__: "cost", __ledger__: "cost", __traceability__: "cost", __riskcost__: "cost",
  __benchmarks__: "planning",
  // Risk Review and AI Assist were filed under Work, whose job is "whatever is in your court right
  // now". Neither is: they are the panel cluster the source calls "preconstruction intelligence" —
  // read an incoming contract for risky clauses, find scope gaps, level bids. Work is a queue, and a
  // queue with tools in it stops reading as a list of things you owe someone.
  __review__: "planning", __aiassist__: "planning",
  // ── Schedule: the plan for time — the CPM, the crews, the controls, the closeout ──────────────
  __schedule__: "schedule", __resload__: "schedule",
  // Turnover follows Closeout into Operate (R41): a turnover panel over registers that live in
  // Operate would report on another room's records — the split surface the spine exists to prevent.
  __turnover__: "operate",
  // ── Work: running the field (R41-WORK-FIELD) ──────────────────────────────────────────────────
  // Equipment follows the records it summarises: `equipment_log` is a Daily Log register, and Daily
  // Log is now Work. A panel that reports on registers in another room is the split-surface shape
  // the spine exists to prevent.
  __equipment__: "work",
  // ── Operate: the asset in service (R30) ───────────────────────────────────────────────────────
  // These three were filed under Deal because facilities management was sectioned as "Operations"
  // and Operations meant the landlord. A technician opening a work order was landing in a room whose
  // stated job is underwriting and disposition. `__assets__` moves with them: the asset register is
  // the handover artifact the CMMS reads, and splitting it from the work orders is what severed the
  // COBie chain in the first place.
  __operations__: "operate", __fca__: "operate", __assets__: "operate",
  // ── Deal: the asset as an investment ──────────────────────────────────────────────────────────
  __uw__: "deal", __land__: "deal", __massingopt__: "deal", __optionrecord__: "deal",
  __diligence__: "deal",
  __market__: "deal", __lifecycle__: "deal", __portfolio__: "deal",
  __esg__: "deal",
  // ── Work: whatever is in your court ───────────────────────────────────────────────────────────
  __workqueue__: "work",
};

/**
 * Where a room opens. The tab's whole job.
 *
 * Until v0.3.766 the rooms were promoted to the primary navigation without this, and three of the
 * five tabs — Cost, Schedule, Work — all resolved to the same host workspace and therefore rendered
 * **byte-identical screens**. Clicking Cost highlighted the tab and changed nothing else, which is
 * indistinguishable from a broken app: the room's nine destinations existed the whole time, one
 * collapsed group away, with nothing routing to them.
 *
 * `null` for Model because the 3D viewer *is* that room — it is the one whose content is not a portal
 * destination. Every other room names a destination it opens, and `spine.test.ts` asserts each of
 * those actually belongs to the room that claims it, so this table cannot drift away from
 * `DEST_ROOM` the way a hand-kept second copy always does.
 */
export const ROOM_HOME: Record<string, string | null> = {
  design: null,
  planning: "__benchmarks__",
  cost: "__budget__",
  schedule: "__schedule__",
  // Portfolio, not Underwriting — and the constraint is real, not a preference.
  //
  // `__uw__` carries `goto`: it switches workspace instead of rendering a panel here, so there is
  // nothing for a landing check to observe. v0.3.770 tried to fake that signal by marking the
  // hand-off active; the marker never cleared, so the second Deal click reported "arrived" for a
  // navigation that never ran. Reverted in v0.3.771, and `spine.test.ts` now asserts that a room's
  // home never carries `goto` — the rule the old comment stated but nothing enforced.
  //
  // Deal reaching Underwriting needs `__uw__` to become a real portal panel. Tracked as R27-UW-PANEL.
  operate: "__operations__",
  deal: "__portfolio__",
  work: "__workqueue__",
};

/**
 * Which workspace hosts each room — the inverse of `WORKSPACE_ROOM`, and NOT a bijection: `cost`,
 * `planning` and `work` have no workspace of their own, they route at the construction portal.
 * Lived in main.ts until ROOM-NAV (2026-08-02); moved here beside the tables it inverts, because a
 * mapping split across two files is two mappings.
 */
export const ROOM_HOST: Record<string, string> = {
  design: "model", planning: "construction", cost: "construction",
  schedule: "construction", operate: "developer", deal: "developer",
  work: "construction",
};

/**
 * The rooms a portal instance can be ACTIVE in, by its workspace filter.
 *
 * `design` is special-cased: the design *room* is hosted by the viewer workspace (`model`), but the
 * design *portal* — the architect's register workspace — still renders that room's rail.
 */
export function portalRooms(wsFilter: string): string[] {
  if (wsFilter === "design") return ["design"];
  return (ROOM_IDS as readonly string[]).filter((r) => ROOM_HOST[r] === wsFilter);
}

/**
 * ROOM-NAV — which room groups the rail actually renders.
 *
 * The rail used to render all seven rooms in every workspace, collapsed. That reads as "every module
 * on every screen" (the user said exactly this), and it forced room *switching* to be a DOM
 * click-simulation against a rail that was about to be rebuilt — the poll visibly lost, leaving
 * Planning empty and Cost showing Schedule's content. Scoped to the active room, the rail IS the
 * room's menu, and switching rooms is the tab bar's job, where it always was.
 *
 * An unknown `active` falls back to every room rather than none: a rail that renders nothing because
 * a state string drifted is the worst version of this bug, and it would look exactly like a slow
 * network.
 */
export function visibleRooms(rooms: RoomDef[], workspace: string | null | undefined,
                             active: string, showAll: boolean): RoomDef[] {
  const ordered = orderRooms(rooms, workspace);
  const head = ordered.filter((r) => r.id === active);
  if (!head.length) return ordered;
  return showAll ? [...head, ...ordered.filter((r) => r.id !== active)] : head;
}

/** The room a destination belongs to, or null when it is unmapped — which is a defect, not a default. */
export function destRoom(key: string): string | null {
  const room = DEST_ROOM[key];
  return room && (ROOM_IDS as readonly string[]).includes(room) ? room : null;
}

/** Destination keys with no room. Must be empty; surfaced in the rail rather than swallowed. */
export function unroomedDests(keys: string[]): string[] {
  return keys.filter((k) => !destRoom(k));
}

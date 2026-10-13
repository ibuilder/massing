/**
 * The rooms as PRIMARY navigation — Design · Planning · Cost · Schedule · Deal · Work.
 *
 * The surprise, on going to build this: **the five tabs already existed.** `ROOM_IDS` has been
 * `["model","cost","schedule","deal","work"]` since the spine shipped, `GET /rooms` allocates every
 * module to one of them, and `parity.test.ts` proves no destination is left unroomed. What was
 * missing is that the rooms were rendered as a *sub-rail inside three of seven workspaces*, while
 * the top bar still showed the seven. The information architecture was right and buried under the
 * one it replaced.
 *
 * So this is promotion, not redesign — which is why it is small. `WORKSPACE_ROOM` already collapses
 * the seven into the five (model/drawings/studio/design → model, construction → schedule,
 * finance/developer → deal), so the mapping is not being invented here either.
 *
 * **Work carries a count and the others do not.** That asymmetry is the whole thesis of the design
 * this reconstructs: you never browse for work, work comes to you. A badge on every tab would be a
 * dashboard; a badge on one is a summons.
 */
import type { RoomDef } from "../api/types";
import { FALLBACK_ROOMS, ROOM_IDS } from "./spine";

export interface RoomTab {
  id: string;
  label: string;
  /** One line saying what the room is for — the tooltip, and the subtitle when a room opens. */
  job: string;
  /** Ball-in-your-court count. Only ever set for `work`; `null` renders no badge at all. */
  count: number | null;
  /** Unread live notifications for the room the notification stream belongs to (`construction`'s
   *  room, which `preselectedRoom` resolves to `schedule`). A SEPARATE chip from `count` on
   *  purpose: "items in your court" and "unread notifications" are different numbers, and
   *  overloading one badge with both would make neither readable. `null` renders nothing.
   *
   *  A plain COUNT, never a control — see `renderLiveRefusal` for why the refusal left this type. */
  live?: { count: number } | null;
}

/**
 * Build the tab model.
 *
 * `rooms` is what `GET /rooms` returned, or nothing. Losing that request must cost the **counts**,
 * never the tabs — an offline-first product whose navigation disappears with the network is not
 * offline-first. `FALLBACK_ROOMS` is the same five ids, so the shell is identical either way.
 */
export function buildRoomTabs(rooms?: readonly RoomDef[] | null, workCount?: number | null,
                              live?: { room: string; count: number } | null,
                             ): RoomTab[] {
  const byId = new Map<string, RoomDef>();
  for (const r of rooms?.length ? rooms : FALLBACK_ROOMS) byId.set(r.id, r);

  return ROOM_IDS.map((id) => {
    // Never index into the server's list positionally — a reordered response would silently relabel
    // every tab, and the labels are the one thing a user navigates by.
    const def = byId.get(id) ?? FALLBACK_ROOMS.find((r) => r.id === id)!;
    return {
      id,
      label: def.label,
      job: def.job,
      count: id === "work" ? (workCount ?? null) : null,
      live: live && live.room === id ? { count: live.count } : null,
    };
  });
}

/**
 * Reorder a built strip, putting the ids in `order` first and keeping everything else behind them.
 *
 * **Total by construction** — a `map` and a `sort`, never a `filter` — because the thing a persona
 * must not be able to do to this strip is shorten it. `personaRooms` is the only caller and already
 * returns all seven ids; this function would preserve the strip even if it stopped doing so, which
 * is the point of putting the property here rather than only there. An id `order` does not mention
 * keeps its existing position relative to the other unmentioned ones.
 */
export function orderRoomTabs(tabs: readonly RoomTab[], order: readonly string[]): RoomTab[] {
  const rank = new Map(order.map((id, i) => [id, i]));
  return tabs
    .map((t, i) => [t, rank.get(t.id) ?? order.length + i] as const)
    .sort((a, b) => a[1] - b[1])
    .map(([t]) => t);
}

/** Which tab a legacy workspace key belongs to, so a deep link into `?ws=construction` still lands. */
export { personaRooms, preselectedRoom as roomForWorkspace } from "./spine";

/**
 * Mark `active` as the selected room in an ALREADY-RENDERED strip, and return how many tabs it
 * marked.
 *
 * Split out of `renderRoomTabs` for WS-BTN-SELECT: navigating by any path other than a tab click
 * left the strip marking the room the user had come FROM, `aria-selected="true"` included. The
 * marking belonged to a loop in `main.ts` that toggled `.ws-btn`, a class nothing rendered, so there
 * was no marking at all — see `main.ts` `setWorkspace`. The class itself is gone with WS-BTN-DEAD.
 *
 * `renderRoomTabs` now calls this rather than setting the two attributes itself, so there is ONE
 * statement anywhere of what "selected" looks like in the DOM. Two copies would have been two
 * answers the moment either grew a third attribute.
 *
 * **It returns the count on purpose.** The host is a parameter and the id is a string, so the
 * natural failure of this function is doing nothing at all — an empty host, or a room id no tab
 * carries — and a `void` return makes that indistinguishable from success. A caller that cares can
 * assert `=== 1`; the tests do.
 */
export function markActiveRoom(host: HTMLElement, active: string): number {
  let marked = 0;
  for (const b of host.querySelectorAll<HTMLElement>("[data-room]")) {
    const on = b.dataset.room === active;
    b.classList.toggle("active", on);
    b.setAttribute("aria-selected", String(on));
    if (on) marked++;
  }
  return marked;
}

/**
 * Render the tab bar into `host`, replacing its contents.
 *
 * Buttons, not links: this switches an in-page view and does not navigate. `role="tab"` +
 * `aria-selected` so the active room is stated rather than only coloured — the same reason the side
 * panel toggle got `aria-expanded`.
 */
export function renderRoomTabs(
  host: HTMLElement,
  tabs: readonly RoomTab[],
  active: string,
  onPick: (id: string) => void,
): void {
  host.innerHTML = "";
  host.setAttribute("role", "tablist");
  for (const t of tabs) {
    const b = document.createElement("button");
    b.type = "button";
    b.className = "room-tab";
    b.dataset.room = t.id;
    b.setAttribute("role", "tab");
    b.title = t.job;                       // the room's job, not a restatement of its name
    b.textContent = t.label;
    // The count is the design's one piece of urgency, so it is a distinct element rather than text
    // baked into the label — a badge can be styled and read out; "Work 6" cannot.
    if (t.count != null && t.count > 0) {
      const badge = document.createElement("span");
      badge.className = "room-tab-count";
      badge.textContent = String(t.count);
      badge.setAttribute("aria-label", `${t.count} items in your court`);
      b.appendChild(badge);
    }
    // LIVE NOTIFICATIONS — a count, and nothing interactive. A `<span>` inside a `<button>` is
    // fine; a FOCUSABLE one is not, which is why the refusal control moved out (see below).
    if (t.live && t.live.count > 0) {
      const chip = document.createElement("span");
      chip.className = "room-tab-live";
      chip.textContent = String(t.live.count);
      chip.setAttribute("aria-label", `${t.live.count} unread notification(s)`);
      b.appendChild(chip);
    }
    b.onclick = () => onPick(t.id);
    host.appendChild(b);
  }
  markActiveRoom(host, active);        // one statement of what "selected" is, shared with re-marking
}

/**
 * The live-stream refusal control — a real `<button>`, OUTSIDE the tablist.
 *
 * **It started as a focusable `<span>` inside the tab `<button>`, which is invalid HTML**:
 * `<button>`'s content model permits no interactive content, so a nested control is not reliably
 * exposed or activatable by assistive technology however many ARIA attributes it carries. It also
 * needed `stopPropagation` to stop a retry from switching room — *a workaround for the nesting,
 * read at the time as a feature of the nesting.* And putting a plain `<button>` among `role="tab"`
 * children would have been the same mistake in ARIA instead of HTML.
 *
 * **The test could not see any of it.** It dispatched `click` and `keydown` straight at the span,
 * so it proved the handler runs when the event arrives — never that a person can make it arrive.
 * *A test that supplies the thing under test cannot notice it being unreachable*, which is the same
 * failure `test_mcp_attribution.py` records and the reason FIELD-POISON's escape hatch shipped
 * sending nothing.
 *
 * Moving it out also fixes the placement. The stream is APP-level: one subscription, not one per
 * room. A per-tab control said otherwise, and the first draft of this work noted that and put it on
 * a tab anyway.
 *
 * `host` is a sibling of the tablist, so this owns it entirely: no refusal renders nothing at all,
 * rather than an empty box holding a line of layout open.
 *
 * **THE REASON IS VISIBLE TEXT, not a `title`.** The first draft put the server's reason in `title`
 * and `aria-label` and labelled the button only *"Live updates stopped"* — so on a touch device,
 * where there is no hover, a sighted user could not read WHY. This product ships a tablet field
 * mode; that is exactly who loses. *A reason carried but not shown is the defect this whole branch
 * is about, committed in the control written to fix it.* It is also why the button's visible text
 * is now its accessible name: a separate `aria-label` that differs from the visible label is its
 * own failure (WCAG 2.5.3), so the reason sits in a sibling `<span>` and the button stays "Try
 * again".
 *
 * **`refused === null`, NOT truthiness.** `main.ts` builds this value with `why ?? "…"`, which
 * preserves an empty string, so `!refused` hid the control for a stream that IS refused — the
 * worst available outcome, silence about a refusal. Not reachable today (`permanentRejection`
 * returns non-empty on every branch) and fixed anyway, because it is the empty-versus-absent
 * confusion this branch has now corrected six times, and the type says `string | null`.
 */
export function renderLiveRefusal(host: HTMLElement, refused: string | null,
                                  onRetry: () => void): void {
  host.replaceChildren();
  host.hidden = refused === null;
  if (refused === null) return;
  const why = document.createElement("span");
  why.className = "live-refused-why";
  why.textContent = `Live updates stopped — ${refused || "refused by the server"}.`;
  const b = document.createElement("button");
  b.type = "button";
  b.className = "live-refused";
  b.textContent = "Try again";
  b.onclick = () => onRetry();
  host.append(why, b);
}

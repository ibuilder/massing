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
}

/**
 * Build the tab model.
 *
 * `rooms` is what `GET /rooms` returned, or nothing. Losing that request must cost the **counts**,
 * never the tabs — an offline-first product whose navigation disappears with the network is not
 * offline-first. `FALLBACK_ROOMS` is the same five ids, so the shell is identical either way.
 */
export function buildRoomTabs(rooms?: readonly RoomDef[] | null, workCount?: number | null): RoomTab[] {
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
    };
  });
}

/** Which tab a legacy workspace key belongs to, so a deep link into `?ws=construction` still lands. */
export { preselectedRoom as roomForWorkspace } from "./spine";

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
    const on = t.id === active;
    b.classList.toggle("active", on);
    b.setAttribute("aria-selected", String(on));
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
    b.onclick = () => onPick(t.id);
    host.appendChild(b);
  }
}

/**
 * The thin pinned rail — the last piece of the mockup's frame.
 *
 * Like the room tabs, this renders state that already exists rather than inventing any: `readFavs()`
 * has persisted starred destinations since the portal shipped, and `readRecents()` the last five
 * visited. The rail was the missing *surface*, not the missing data.
 *
 * **A new user has no favourites**, and an empty rail beside a populated app reads as broken rather
 * than as unconfigured. So an unpinned rail shows recents, labelled honestly as recents — the
 * alternative is either a blank column or pre-pinning things nobody chose, and inventing somebody's
 * preferences is worse than showing them where they have actually been.
 */
import { ALL_DESTS } from "./destinations";
import { readFavs, readRecents } from "../portal/prefs";

export interface PinnedItem {
  key: string;
  label: string;
  icon: string;
  /** True when the user starred it; false when it is only here because they visited it. */
  pinned: boolean;
}

/** Cap. Past this the rail stops being scannable, which is the only thing it is for. */
export const MAX_PINS = 8;

/**
 * What the rail shows: the user's pins, or their recents when nothing is pinned.
 *
 * Never both. Mixing them produces a list where two identical-looking rows mean different things —
 * "I chose this" and "I happened to be here" — and the user cannot tell which is which.
 */
export function pinnedItems(
  favs: ReadonlySet<string> = readFavs(),
  recents: readonly string[] = readRecents(),
): { items: PinnedItem[]; mode: "pinned" | "recent" } {
  const byKey = new Map(ALL_DESTS.map((d) => [d.key, d] as const));
  const build = (keys: readonly string[], pinned: boolean): PinnedItem[] =>
    keys
      // A key with no destination is a stale preference — a module that was removed, or a rename.
      // Dropping it silently is right: the rail is not the place to report that, and a row that
      // navigates nowhere is worse than one fewer row.
      .map((k) => byKey.get(k))
      .filter((d): d is NonNullable<typeof d> => !!d)
      .slice(0, MAX_PINS)
      .map((d) => ({ key: d.key, label: d.label, icon: d.icon, pinned }));

  const pins = build([...favs], true);
  if (pins.length) return { items: pins, mode: "pinned" };
  return { items: build(recents, false), mode: "recent" };
}

/**
 * Render into `host`, or hide it when there is nothing to show.
 *
 * Hidden rather than empty-with-a-heading: a "PINNED" caption over no rows is a promise the app has
 * not kept, and it costs horizontal space that the model or the queue can use.
 */
export function renderPinnedRail(
  host: HTMLElement,
  data: { items: readonly PinnedItem[]; mode: "pinned" | "recent" },
  active: string | null,
  onPick: (key: string) => void,
): void {
  host.innerHTML = "";
  host.hidden = data.items.length === 0;
  if (!data.items.length) return;

  const cap = document.createElement("div");
  cap.className = "pin-cap";
  // Say which list this is. A recents list labelled "PINNED" teaches the user that pinning does
  // nothing, because the rail looked the same before they ever pinned anything.
  cap.textContent = data.mode === "pinned" ? "PINNED" : "RECENT";
  host.appendChild(cap);

  for (const it of data.items) {
    const b = document.createElement("button");
    b.type = "button";
    b.className = "pin-item" + (it.key === active ? " active" : "");
    b.dataset.dest = it.key;
    b.title = it.label;
    if (it.key === active) b.setAttribute("aria-current", "page");

    const ic = document.createElement("span");
    ic.className = "pin-icon";
    ic.setAttribute("aria-hidden", "true");
    ic.textContent = it.icon;

    const lb = document.createElement("span");
    lb.className = "pin-label";
    // textContent: labels come from the destination catalog, and a rail that renders on every
    // screen is the last place to interpolate markup.
    lb.textContent = it.label;

    b.append(ic, lb);
    b.onclick = () => onPick(it.key);
    host.appendChild(b);
  }
}

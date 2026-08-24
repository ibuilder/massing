import { beforeEach, describe, expect, it } from "vitest";

import type { ApiClient, ModuleDef } from "../api/client";
import { type PortalHost, PortalUI } from "./portal";
import { readFavs } from "./prefs";

/**
 * A module can be pinned, and the pin is the only thing that can put the rail into "pinned" mode.
 *
 * ## The defect this was written from
 *
 * `toggleFav` had exactly ONE call site in the whole app: a `☆` button inside the dashboard module
 * catalog. Commit 9a61f4cc (2026-06-24) deleted that catalog's two mount lines deliberately — the
 * persistent nav rail had taken over module navigation — and left the implementation behind. Since
 * `catalogEl` was assigned only inside a `refreshCatalog()` that began `if (!this.catalogEl) return;`,
 * the catalog could never render.
 *
 * So for two months favourites could be **read** and never **written**:
 *
 *   * `buildNav` renders a "★ Favorites" group when `readFavs()` is non-empty;
 *   * `shell/pinnedRail.ts` returns `mode: "pinned"` when it is, and falls back to recents when not.
 *
 * Neither could ever fire. The pinned rail carries a careful docstring about why it never mixes pins
 * with recents — *"two identical-looking rows mean different things — 'I chose this' and 'I happened
 * to be here'"* — protecting a distinction that could not arise.
 *
 * ## Why this test drives the DOM instead of counting callers
 *
 * A reachability or uncalled-symbol check would not have caught it, and must not be what we rely on
 * now: every method in that catalog had a caller — *each other*. `renderModuleCatalog` was called by
 * `refreshCatalog`, which was called by a live event listener. The cycle looked wired from every
 * angle except the one that mattered, which is whether a person can reach it.
 *
 * So: build the real rail, click the real control, and read the real preference back. See also
 * [[a-gate-reads-the-declaration-not-the-use]] — the same confusion one level up.
 */

// `room` is load-bearing, not decoration: the rail lists registers INSIDE their room group
// (`m.room === room.id`), and the flat by-section list was removed in v0.3.767 because two taxonomies
// in one rail is what the spine exists to end. A fixture without a room renders no rows at all —
// which is how the first draft of this file failed, with a rail that built perfectly and was empty.
const ROOM = "schedule";
const MODS: ModuleDef[] = [
  { key: "rfi", name: "RFIs", section: "Coordination", room: ROOM, icon: "?", pinnable: true, fields: [] },
  { key: "submittal", name: "Submittals", section: "Coordination", room: ROOM, icon: "S", pinnable: true, fields: [] },
] as unknown as ModuleDef[];

/** The private surface this reaches for. `openModule` is reached the same way in registerEmpty.test.ts. */
type Inner = { nav?: HTMLElement; mods: ModuleDef[]; showAll: boolean; buildNav: () => void };

function mountRail() {
  const root = document.createElement("div");
  document.body.appendChild(root);
  const api = { url: (p: string) => p, listViews: async () => [] } as unknown as ApiClient;
  const host: PortalHost = {
    api,
    projectId: () => "p1",
    anchorPoint: () => null,
    selectedGuid: () => null,
    onSelectGuids: () => {},
    onPinsChanged: () => {},
    setStatus: () => {},
  };
  const ui = new PortalUI(root, host);
  const inner = ui as unknown as Inner;
  const nav = document.createElement("nav");
  nav.className = "portal-nav";
  root.appendChild(nav);
  inner.nav = nav;
  inner.mods = MODS;
  inner.showAll = true;              // every module visible, so the rail is not empty by workspace
  inner.buildNav.call(ui);
  return { nav, rebuild: () => inner.buildNav.call(ui) };
}

const stars = (nav: HTMLElement) => [...nav.querySelectorAll<HTMLButtonElement>(".mod-fav")];
const groups = (nav: HTMLElement) =>
  [...nav.querySelectorAll<HTMLElement>(".pnav-group")].map((d) => d.dataset.sec ?? "");

beforeEach(() => { document.body.innerHTML = ""; localStorage.clear(); });

describe("pinning a module from the nav rail", () => {
  it("renders a pin control on module rows — the affordance that went missing", () => {
    const { nav } = mountRail();
    expect(stars(nav).length,
      "no pin control anywhere in the rail: `toggleFav` is again unreachable, and the pinned rail's "
      + "entire 'pinned' mode with it").toBeGreaterThan(0);
  });

  it("CLICKING IT ACTUALLY PINS — the preference changes, not just the glyph", () => {
    const { nav } = mountRail();
    expect(readFavs().size, "precondition: nothing pinned").toBe(0);
    stars(nav)[0]?.click();
    expect([...readFavs()],
      "the star must call toggleFav. A control that only re-styles itself is the defect this file "
      + "exists for, wearing a different hat").toHaveLength(1);
  });

  it("...and the Favorites group then appears, which is what the user actually sees", () => {
    const { nav, rebuild } = mountRail();
    expect(groups(nav), "precondition: no Favorites group with nothing pinned")
      .not.toContain("★ Favorites");
    stars(nav)[0]?.click();
    rebuild();
    expect(groups(nav)).toContain("★ Favorites");
  });

  it("unpins too — a toggle that only adds is a trap, since nothing else can remove", () => {
    const { nav } = mountRail();
    stars(nav)[0]?.click();
    expect(readFavs().size).toBe(1);
    stars(nav)[0]?.click();
    expect(readFavs().size,
      "with the catalog gone this is the only unpin path in the app").toBe(0);
  });

  /**
   * The pin sits INSIDE a row whose other child is the open button, and clicking it must not also
   * navigate. That is why the two are siblings rather than a star nested in the button — a `<button>`
   * inside a `<button>` is invalid HTML and the inner one is unfocusable. The deleted catalog had
   * already worked this out; the shape is inherited, so the property it protects is asserted here.
   */
  it("the pin does not navigate: two sibling buttons, not one nested in the other", () => {
    const { nav } = mountRail();
    const star = stars(nav)[0];
    expect(star?.closest("button"), "the star must not be inside another button").toBe(star);
    expect(star?.parentElement?.classList.contains("pnav-row")).toBe(true);
    expect(star?.parentElement?.querySelector(".pnav-item"),
      "its sibling is the open button, so the row is a row").toBeTruthy();
  });

  it("says what it will do, for a control whose whole meaning is a glyph", () => {
    const { nav } = mountRail();
    const star = stars(nav)[0];
    expect(star?.getAttribute("aria-pressed")).toBe("false");
    expect(star?.getAttribute("aria-label")).toMatch(/Pin /);
    star?.click();
    const after = stars(mountRail().nav)[0];
    expect(after?.getAttribute("aria-pressed")).toBe("true");
    expect(after?.getAttribute("aria-label")).toMatch(/Unpin /);
  });
});

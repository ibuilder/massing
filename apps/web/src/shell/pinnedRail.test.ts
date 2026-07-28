import { describe, expect, it } from "vitest";

import { ALL_DESTS } from "./destinations";
import { MAX_PINS, pinnedItems, renderPinnedRail } from "./pinnedRail";

/**
 * The pinned rail.
 *
 * Like the room tabs before it, this renders state that already existed — `readFavs()` and
 * `readRecents()` have persisted since the portal shipped. The rail was a missing surface, not
 * missing data, which is why the tests here are about *honesty of presentation* rather than storage.
 *
 * The one that matters: a recents list must never be labelled PINNED. If it is, the rail looks
 * identical before and after a user pins anything, and they learn that pinning does nothing.
 */

const REAL = ALL_DESTS.slice(0, 12).map((d) => d.key);

describe("what the rail shows", () => {
  it("shows pins when there are pins", () => {
    const { items, mode } = pinnedItems(new Set([REAL[0]!, REAL[1]!]), []);
    expect(mode).toBe("pinned");
    expect(items.map((i) => i.key)).toEqual([REAL[0], REAL[1]]);
    expect(items.every((i) => i.pinned)).toBe(true);
  });

  it("falls back to recents when nothing is pinned", () => {
    // A new user has no favourites. An empty rail beside a populated app reads as broken.
    const { items, mode } = pinnedItems(new Set(), [REAL[2]!, REAL[3]!]);
    expect(mode).toBe("recent");
    expect(items.map((i) => i.key)).toEqual([REAL[2], REAL[3]]);
    expect(items.every((i) => i.pinned)).toBe(false);
  });

  it("never mixes the two", () => {
    // Two identical-looking rows meaning "I chose this" and "I happened to be here" is a list the
    // user cannot read.
    const { items, mode } = pinnedItems(new Set([REAL[0]!]), [REAL[5]!, REAL[6]!]);
    expect(mode).toBe("pinned");
    expect(items.map((i) => i.key)).toEqual([REAL[0]]);
    expect(items.some((i) => i.key === REAL[5])).toBe(false);
  });

  it("is empty only when there is genuinely nothing", () => {
    expect(pinnedItems(new Set(), []).items).toEqual([]);
  });

  it("drops stale keys rather than rendering a row that goes nowhere", () => {
    // A removed or renamed module leaves a preference behind. The rail is not the place to report
    // that, and a dead row is worse than one fewer row.
    const { items } = pinnedItems(new Set(["no-such-destination", REAL[0]!]), []);
    expect(items.map((i) => i.key)).toEqual([REAL[0]]);
  });

  it("caps at MAX_PINS, because a long rail is not scannable", () => {
    const many = ALL_DESTS.slice(0, MAX_PINS + 5).map((d) => d.key);
    expect(pinnedItems(new Set(many), []).items.length).toBe(MAX_PINS);
  });

  it("carries a real label and icon for every row", () => {
    for (const i of pinnedItems(new Set(REAL.slice(0, 4)), []).items) {
      expect(i.label.length, i.key).toBeGreaterThan(0);
      expect(i.icon.length, i.key).toBeGreaterThan(0);
    }
  });
});

describe("rendering", () => {
  const host = () => document.createElement("div");

  it("labels a recents list RECENT, never PINNED", () => {
    // The load-bearing assertion. Get this wrong and pinning appears to do nothing.
    const h = host();
    renderPinnedRail(h, pinnedItems(new Set(), [REAL[0]!]), null, () => {});
    expect(h.querySelector(".pin-cap")!.textContent).toBe("RECENT");
  });

  it("...and a pinned list PINNED", () => {
    const h = host();
    renderPinnedRail(h, pinnedItems(new Set([REAL[0]!]), []), null, () => {});
    expect(h.querySelector(".pin-cap")!.textContent).toBe("PINNED");
  });

  it("hides itself rather than showing a caption over nothing", () => {
    const h = host();
    renderPinnedRail(h, { items: [], mode: "pinned" }, null, () => {});
    expect(h.hidden).toBe(true);
    expect(h.innerHTML).toBe("");
  });

  it("marks the current destination for assistive tech, not just colour", () => {
    const h = host();
    renderPinnedRail(h, pinnedItems(new Set([REAL[0]!, REAL[1]!]), []), REAL[1]!, () => {});
    const cur = h.querySelectorAll('[aria-current="page"]');
    expect(cur.length).toBe(1);
    expect((cur[0] as HTMLElement).dataset.dest).toBe(REAL[1]);
  });

  it("labels are text, never markup", () => {
    const h = host();
    renderPinnedRail(h, {
      items: [{ key: "k", label: '<img src=x onerror="alert(1)">', icon: "•", pinned: true }],
      mode: "pinned",
    }, null, () => {});
    expect(h.querySelector("img")).toBeNull();
    expect(h.querySelector(".pin-label")!.textContent).toContain("<img");
  });

  it("clicking reports the destination key", () => {
    const h = host();
    const seen: string[] = [];
    renderPinnedRail(h, pinnedItems(new Set([REAL[0]!]), []), null, (k) => seen.push(k));
    h.querySelector<HTMLButtonElement>(".pin-item")!.click();
    expect(seen).toEqual([REAL[0]]);
  });

  it("re-rendering replaces rather than appending", () => {
    const h = host();
    const data = pinnedItems(new Set([REAL[0]!, REAL[1]!]), []);
    renderPinnedRail(h, data, null, () => {});
    renderPinnedRail(h, data, null, () => {});
    expect(h.querySelectorAll(".pin-item").length).toBe(2);
    expect(h.querySelectorAll(".pin-cap").length).toBe(1);
  });
});

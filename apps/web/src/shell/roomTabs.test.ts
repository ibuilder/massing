import { beforeEach, describe, expect, it } from "vitest";

import { ROOM_IDS } from "./spine";
import { buildRoomTabs, renderRoomTabs, roomForWorkspace } from "./roomTabs";

/**
 * The five rooms as primary navigation.
 *
 * Worth recording what building this actually found: **the five tabs already existed.** `ROOM_IDS`
 * has been `model/cost/schedule/deal/work` since the spine shipped, the server allocates every
 * module to one of them, and `parity.test.ts` proves none is left unroomed. They were rendered as a
 * sub-rail inside three of seven workspaces while the top bar still showed the seven — the right IA,
 * buried under the one it replaced. So these tests guard a promotion, not an invention.
 */

describe("the tab model", () => {
  it("is exactly the five rooms, in order", () => {
    expect(buildRoomTabs().map((t) => t.id)).toEqual([...ROOM_IDS]);
  });

  it("survives a lost /rooms request — the shell is not the network's to take", () => {
    // Losing the request must cost the counts, never the tabs. An offline-first product whose
    // navigation vanishes with the connection is not offline-first.
    for (const bad of [null, undefined, []]) {
      const tabs = buildRoomTabs(bad as never);
      expect(tabs.map((t) => t.id)).toEqual([...ROOM_IDS]);
      expect(tabs.every((t) => t.label.length > 0)).toBe(true);
    }
  });

  it("matches rooms by id, never by position", () => {
    // A reordered server response would silently relabel every tab under positional indexing, and
    // labels are the one thing a user navigates by.
    const shuffled = [
      { id: "work", label: "WORK!", job: "j", count: 0, modules: [] },
      { id: "model", label: "MODEL!", job: "j", count: 0, modules: [] },
    ];
    const tabs = buildRoomTabs(shuffled as never);
    expect(tabs.find((t) => t.id === "model")!.label).toBe("MODEL!");
    expect(tabs.find((t) => t.id === "work")!.label).toBe("WORK!");
    // the three the server omitted still appear, from the fallback
    expect(tabs.map((t) => t.id)).toEqual([...ROOM_IDS]);
  });

  it("every tab carries its job — a tooltip that restates the label helps nobody", () => {
    for (const t of buildRoomTabs()) {
      expect(t.job.length, t.id).toBeGreaterThan(10);
      expect(t.job.toLowerCase(), t.id).not.toBe(t.label.toLowerCase());
    }
  });
});

describe("only Work carries a count", () => {
  it("the badge is on Work and nowhere else", () => {
    const tabs = buildRoomTabs(null, 6);
    expect(tabs.find((t) => t.id === "work")!.count).toBe(6);
    for (const t of tabs.filter((x) => x.id !== "work")) {
      expect(t.count, `${t.id} must not carry a count`).toBeNull();
    }
  });

  it("that asymmetry IS the design — a badge on every tab is a dashboard", () => {
    // "You never browse for work, work comes to you." One summons, not five metrics.
    const counted = buildRoomTabs(null, 3).filter((t) => t.count != null);
    expect(counted.length).toBe(1);
  });

  it("no count and zero both render nothing", () => {
    expect(buildRoomTabs(null, null).find((t) => t.id === "work")!.count).toBeNull();
    const host = document.createElement("div");
    renderRoomTabs(host, buildRoomTabs(null, 0), "work", () => {});
    expect(host.querySelector(".room-tab-count")).toBeNull();
  });
});

describe("legacy workspace links still land", () => {
  it("the seven collapse into the five", () => {
    expect(roomForWorkspace("model")).toBe("model");
    expect(roomForWorkspace("drawings")).toBe("model");
    expect(roomForWorkspace("studio")).toBe("model");
    expect(roomForWorkspace("design")).toBe("model");
    expect(roomForWorkspace("construction")).toBe("schedule");
    expect(roomForWorkspace("finance")).toBe("deal");
    expect(roomForWorkspace("developer")).toBe("deal");
  });

  it("an unknown workspace lands in Work rather than nowhere", () => {
    expect(roomForWorkspace("nonsense")).toBe("work");
    expect(roomForWorkspace("")).toBe("work");
    expect(roomForWorkspace(null)).toBe("work");
  });

  it("every legacy workspace maps to a REAL room", () => {
    for (const ws of ["model", "drawings", "studio", "design", "construction", "developer", "finance"]) {
      expect(ROOM_IDS as readonly string[], ws).toContain(roomForWorkspace(ws));
    }
  });
});

describe("rendering", () => {
  let host: HTMLElement;
  beforeEach(() => { host = document.createElement("div"); });

  it("draws one button per room, as a tablist", () => {
    renderRoomTabs(host, buildRoomTabs(), "model", () => {});
    expect(host.getAttribute("role")).toBe("tablist");
    expect(host.querySelectorAll(".room-tab").length).toBe(ROOM_IDS.length);
    expect([...host.querySelectorAll(".room-tab")].every((b) => b.getAttribute("role") === "tab")).toBe(true);
  });

  it("states which room is active rather than only colouring it", () => {
    renderRoomTabs(host, buildRoomTabs(), "cost", () => {});
    const sel = [...host.querySelectorAll(".room-tab")].filter((b) => b.getAttribute("aria-selected") === "true");
    expect(sel.length).toBe(1);
    expect((sel[0] as HTMLElement).dataset.room).toBe("cost");
  });

  it("the tooltip is the room's job", () => {
    renderRoomTabs(host, buildRoomTabs(), "model", () => {});
    const cost = host.querySelector<HTMLElement>('[data-room="cost"]')!;
    expect(cost.title).toMatch(/price it/i);
  });

  it("clicking reports the room id", () => {
    const picked: string[] = [];
    renderRoomTabs(host, buildRoomTabs(), "model", (id) => picked.push(id));
    host.querySelector<HTMLButtonElement>('[data-room="deal"]')!.click();
    expect(picked).toEqual(["deal"]);
  });

  it("re-rendering replaces rather than appends", () => {
    renderRoomTabs(host, buildRoomTabs(), "model", () => {});
    renderRoomTabs(host, buildRoomTabs(), "work", () => {});
    expect(host.querySelectorAll(".room-tab").length).toBe(ROOM_IDS.length);
  });

  it("the count renders as a badge, readable and not baked into the label", () => {
    renderRoomTabs(host, buildRoomTabs(null, 6), "work", () => {});
    const badge = host.querySelector(".room-tab-count")!;
    expect(badge.textContent).toBe("6");
    expect(badge.getAttribute("aria-label")).toMatch(/in your court/i);
    // exactly one badge in the whole bar
    expect(host.querySelectorAll(".room-tab-count").length).toBe(1);
  });
});

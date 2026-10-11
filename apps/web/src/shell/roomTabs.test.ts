import { beforeEach, describe, expect, it } from "vitest";

import { ROOM_IDS } from "./spine";
import { buildRoomTabs, renderRoomTabs, roomForWorkspace } from "./roomTabs";

/**
 * The rooms as primary navigation.
 *
 * Worth recording what building this actually found: **the five tabs already existed.** `ROOM_IDS`
 * has been `model/cost/schedule/deal/work` since the spine shipped, the server allocates every
 * module to one of them, and `parity.test.ts` proves none is left unroomed. They were rendered as a
 * sub-rail inside three of seven workspaces while the top bar still showed the seven — the right IA,
 * buried under the one it replaced. So these tests guard a promotion, not an invention.
 */

describe("the tab model", () => {
  it("is exactly the rooms in ROOM_IDS, in order", () => {
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
      { id: "design", label: "DESIGN!", job: "j", count: 0, modules: [] },
    ];
    const tabs = buildRoomTabs(shuffled as never);
    expect(tabs.find((t) => t.id === "design")!.label).toBe("DESIGN!");
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
  it("the seven workspaces collapse into the rooms", () => {
    // All four authoring workspaces land in Design — which is the point of renaming it. Under the
    // old name a user in "drawings" arrived in a room called "Model" and had to infer that drawings
    // were a kind of model.
    expect(roomForWorkspace("model")).toBe("design");
    expect(roomForWorkspace("drawings")).toBe("design");
    expect(roomForWorkspace("studio")).toBe("design");
    expect(roomForWorkspace("design")).toBe("design");
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
    renderRoomTabs(host, buildRoomTabs(), "design", () => {});
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
    renderRoomTabs(host, buildRoomTabs(), "design", () => {});
    const cost = host.querySelector<HTMLElement>('[data-room="cost"]')!;
    expect(cost.title).toMatch(/budget it/i);
    // Cost stopped being the room that prices the job when Planning took the estimating with it.
    const planning = host.querySelector<HTMLElement>('[data-room="planning"]')!;
    expect(planning.title).toMatch(/estimate it/i);
  });

  it("clicking reports the room id", () => {
    const picked: string[] = [];
    renderRoomTabs(host, buildRoomTabs(), "design", (id) => picked.push(id));
    host.querySelector<HTMLButtonElement>('[data-room="deal"]')!.click();
    expect(picked).toEqual(["deal"]);
  });

  it("re-rendering replaces rather than appends", () => {
    renderRoomTabs(host, buildRoomTabs(), "design", () => {});
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

describe("FIELD-STREAM-POISON — the live-notification chip", () => {
  const strip = () => {
    const host = document.createElement("div");
    document.body.replaceChildren(host);
    return host;
  };
  const chip = (host: HTMLElement) => host.querySelector<HTMLElement>(".room-tab-live");

  it("lands on the room `construction` resolves to, not on a guessed tab", () => {
    // Derived, never a second list: the old consumer named the Construction WORKSPACE, and the
    // workspace→room map already answers where that went.
    const room = roomForWorkspace("construction");
    const host = strip();
    renderRoomTabs(host, buildRoomTabs(null, null, { room, count: 3, refused: null }), "model",
                   () => {});
    const on = host.querySelector<HTMLElement>(`.room-tab[data-room="${room}"] .room-tab-live`);
    expect(on?.textContent).toBe("3");
    expect(host.querySelectorAll(".room-tab-live")).toHaveLength(1);
  });

  it("is a SECOND chip — it never replaces the ball-in-your-court count", () => {
    // "Items in your court" and "unread notifications" are different numbers. Overloading one
    // badge with both would make neither readable.
    const host = strip();
    renderRoomTabs(host, buildRoomTabs(null, 6, { room: "work", count: 2, refused: null }),
                   "model", () => {});
    const work = host.querySelector<HTMLElement>('.room-tab[data-room="work"]')!;
    expect(work.querySelector(".room-tab-count")?.textContent).toBe("6");
    expect(work.querySelector(".room-tab-live")?.textContent).toBe("2");
  });

  it("renders nothing at zero unread — no permanent zero in the bar", () => {
    const host = strip();
    renderRoomTabs(host, buildRoomTabs(null, null, { room: "schedule", count: 0, refused: null }),
                   "model", () => {});
    expect(chip(host)).toBeNull();
  });

  it("THE POINT: a refused stream renders a CONTROL that carries the reason", () => {
    const host = strip();
    renderRoomTabs(host, buildRoomTabs(null, null,
                   { room: "schedule", count: 0, refused: "No longer permitted on this project" }),
                   "model", () => {});
    const c = chip(host)!;
    expect(c.textContent).toBe("!");
    expect(c.className).toContain("is-refused");
    expect(c.title).toContain("No longer permitted on this project");
    expect(c.getAttribute("role")).toBe("button");
    expect(c.getAttribute("tabindex")).toBe("0");
    expect(c.getAttribute("aria-label")).toContain("Try again");
  });

  it("activates by KEYBOARD as well as pointer, and does not switch room", () => {
    // An `onclick` on a `<span>` inside a `<button>` is pointer-only: Enter would switch room
    // instead of retrying. And a retry that also navigates is a retry nobody meant to press.
    let retried: string[] = [];
    let picked: string[] = [];
    const host = strip();
    renderRoomTabs(host, buildRoomTabs(null, null,
                   { room: "schedule", count: 0, refused: "Gone" }), "model",
                   (id) => picked.push(id), (id) => retried.push(id));
    const c = chip(host)!;
    c.dispatchEvent(new MouseEvent("click", { bubbles: true }));
    expect(retried).toEqual(["schedule"]);
    expect(picked).toEqual([]);
    retried = []; picked = [];
    for (const key of ["Enter", " "]) {
      c.dispatchEvent(new KeyboardEvent("keydown", { key, bubbles: true }));
    }
    expect(retried).toEqual(["schedule", "schedule"]);
    expect(picked).toEqual([]);
    // an unrelated key does nothing
    c.dispatchEvent(new KeyboardEvent("keydown", { key: "a", bubbles: true }));
    expect(retried).toHaveLength(2);
  });

  it("a healthy chip is not a control — nothing to activate", () => {
    const host = strip();
    renderRoomTabs(host, buildRoomTabs(null, null, { room: "schedule", count: 4, refused: null }),
                   "model", () => {});
    const c = chip(host)!;
    expect(c.getAttribute("role")).toBeNull();
    expect(c.getAttribute("tabindex")).toBeNull();
    expect(c.getAttribute("aria-label")).toContain("4 unread");
  });

  it("no live state at all leaves every tab exactly as before", () => {
    const host = strip();
    renderRoomTabs(host, buildRoomTabs(null, 6), "model", () => {});
    expect(host.querySelectorAll(".room-tab-live")).toHaveLength(0);
    expect(host.querySelectorAll(".room-tab")).toHaveLength(ROOM_IDS.length);
  });
});

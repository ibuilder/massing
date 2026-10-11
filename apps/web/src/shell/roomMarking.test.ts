/**
 * WS-BTN-SELECT — **the room strip marked the room you came FROM, on every path but one.**
 *
 * `setWorkspace` in `main.ts` maintained the selection by toggling `.active` and `aria-selected` on
 * `.ws-btn` — the class WS-BTN-DEAD measures as *queried from four places and rendered by none*. So
 * the marking was done by `goToRoom`, which repaints the strip afterwards, and by **none of the
 * other thirteen `setWorkspace` call sites**: the command palette's "Go to …", the return bar, the
 * project-home signpost, the `aec:workspace` and `aec:goto-workspace` deep links, a persona's home
 * jump, select-by-GUID, `withPortal`, the finance shortcut, the embed path and `initNav`.
 *
 * **`initNav` makes it a first-load defect, not a corner case.** Module scope marks the room derived
 * from `localStorage("workspace") || "model"` — `design` for a fresh profile — and `initNav` then
 * calls `setWorkspace(cfg.home)`, which for six of the ten personas is `construction` or
 * `developer`. A GC opening the app for the first time therefore saw the Schedule room's content
 * under a strip stating `aria-selected="true"` on Design. The attribute exists, in
 * `renderRoomTabs`' own words, "so the active room is stated rather than only coloured"; stating it
 * wrongly is worse than not stating it, because a screen reader has no colour to disagree with.
 *
 * *Dead code that merely does nothing is cheap. This one was holding a job* — the loop read as the
 * place selection is maintained, so nothing looked missing at any of the thirteen sites, and the
 * three audits that know `.ws-btn` is dead were all looking at it as dead code rather than as a
 * missing feature.
 *
 * **What this file does NOT reproduce is the rule.** `wsReturn.test.ts` reproduced `setWorkspace`'s
 * plumbing *and* its decisions, kept its own `DEAD_END_WS`, and that copy silently disagreed with
 * the shipped set for months while this very header described the gap in prose — *a test asserting
 * a reproduction cannot fail when the original is wrong.* So the decision is
 * `spine.roomForOpenWorkspace` and the DOM write is `roomTabs.markActiveRoom`, both imported, and
 * the source assertions at the bottom pin that `main.ts` really calls them.
 */
import { readFileSync } from "node:fs";
import { resolve } from "node:path";

import { beforeEach, describe, expect, it } from "vitest";

import { buildRoomTabs, markActiveRoom, renderRoomTabs } from "./roomTabs";
import { ROOM_HOST, ROOM_IDS, preselectedRoom, roomForOpenWorkspace } from "./spine";

const MAIN = readFileSync(resolve(__dirname, "../main.ts"), "utf8");

/** The strip as the app renders it, plus the three lines of `setWorkspace` that mark it. */
function makeNav(startRoom = "design") {
  const strip = document.createElement("div");
  document.body.replaceChildren(strip);
  renderRoomTabs(strip, buildRoomTabs(null, 6), startRoom, () => {});
  let roomTabsActive = startRoom;
  return {
    strip,
    room: () => roomTabsActive,
    /** `main.ts`'s `markRoomForWorkspace`, which after this change is only this. */
    setWorkspace(key: string) {
      roomTabsActive = roomForOpenWorkspace(roomTabsActive, key);
      markActiveRoom(strip, roomTabsActive);
    },
  };
}

const marked = (host: HTMLElement) =>
  [...host.querySelectorAll<HTMLElement>("[data-room]")]
    .filter((b) => b.getAttribute("aria-selected") === "true")
    .map((b) => b.dataset.room);

describe("markActiveRoom — moving the marker without rebuilding the strip", () => {
  let host: HTMLElement;
  beforeEach(() => {
    host = document.createElement("div");
    renderRoomTabs(host, buildRoomTabs(null, 6), "design", () => {});
  });

  it("marks exactly one tab, and says how many it marked", () => {
    expect(markActiveRoom(host, "cost")).toBe(1);
    expect(marked(host)).toEqual(["cost"]);
  });

  it("UNMARKS the one it left — a second aria-selected tab is a strip claiming two rooms", () => {
    markActiveRoom(host, "cost");
    markActiveRoom(host, "deal");
    expect(marked(host)).toEqual(["deal"]);
    expect(host.querySelectorAll(".room-tab.active").length).toBe(1);
  });

  it("keeps the SAME button nodes, with their badges — the reason it is not a repaint", () => {
    // The strip carries the Work count and the live-notification chip, and holds focus. A caller
    // that only changed workspace has no business rebuilding any of that.
    const before = [...host.querySelectorAll(".room-tab")];
    const badge = host.querySelector(".room-tab-count");
    expect(badge?.textContent).toBe("6");
    markActiveRoom(host, "work");
    expect([...host.querySelectorAll(".room-tab")]).toEqual(before);
    expect(host.querySelector(".room-tab-count")).toBe(badge);
  });

  it("A VACUOUS CALL IS VISIBLE: an unknown room, or an empty host, returns 0", () => {
    // The whole failure mode of this function is doing nothing — wrong host, or an id no tab
    // carries — and a `void` return would make that indistinguishable from having worked.
    expect(markActiveRoom(host, "no-such-room")).toBe(0);
    expect(marked(host)).toEqual([]);
    expect(markActiveRoom(document.createElement("div"), "cost")).toBe(0);
  });

  it("renderRoomTabs marks through this same function, so there is one answer not two", () => {
    const fresh = document.createElement("div");
    renderRoomTabs(fresh, buildRoomTabs(), "schedule", () => {});
    expect(marked(fresh)).toEqual(["schedule"]);
    expect(markActiveRoom(fresh, "schedule")).toBe(1);     // idempotent, and agrees with the render
    expect(marked(fresh)).toEqual(["schedule"]);
  });
});

describe("roomForOpenWorkspace — which room a workspace switch should mark", () => {
  it("THE DEFECT: entering a workspace moves the marker off the room you left", () => {
    const nav = makeNav("design");
    expect(marked(nav.strip)).toEqual(["design"]);
    nav.setWorkspace("construction");                      // the command palette's "Go to Construction"
    expect(nav.room()).toBe("schedule");
    expect(marked(nav.strip)).toEqual(["schedule"]);
  });

  it("the first-load case: a persona home jump re-marks the strip", () => {
    // Module scope marks `roomForWorkspace("model")` = design; `initNav` then sends a GC to
    // `construction`. Before this change the strip still said Design, with aria-selected="true".
    const nav = makeNav(preselectedRoom("model"));
    nav.setWorkspace("construction");
    expect(marked(nav.strip)).toEqual([preselectedRoom("construction")]);
  });

  it("KEEPS the open room when the workspace still hosts it — ROOM_HOST is not a bijection", () => {
    // Construction hosts planning, cost, schedule and work. Deriving from the workspace alone would
    // swap a marker stuck on the room you left for one contradicting what is on screen: the portal
    // goes on rendering Cost, because `portal.room()` is `activeRoom ?? preselectedRoom(wsFilter)`.
    for (const room of ["planning", "cost", "schedule", "work"]) {
      expect(roomForOpenWorkspace(room, "construction"), room).toBe(room);
    }
    const nav = makeNav("cost");
    nav.setWorkspace("construction");
    expect(nav.room()).toBe("cost");
    expect(marked(nav.strip)).toEqual(["cost"]);
  });

  it("four workspaces share the design room, and all four keep it", () => {
    // `ROOM_HOST.design` is only `model`, so for the other three this is the FALL-THROUGH agreeing
    // with the keep, not a keep. The rule had a `|| derived === cur` clause written for exactly
    // this case; mutation deleted it, because whenever that disjunct decides, the fall-through
    // returns the same room by construction. The case is real and worth asserting — the clause
    // claiming to be the reason it passes was not.
    for (const ws of ["model", "drawings", "studio", "design"]) {
      expect(roomForOpenWorkspace("design", ws), ws).toBe("design");
    }
  });

  it("falls through when the workspace cannot show the open room", () => {
    expect(roomForOpenWorkspace("cost", "model")).toBe("design");
    expect(roomForOpenWorkspace("design", "developer")).toBe("deal");
    expect(roomForOpenWorkspace("schedule", "finance")).toBe("deal");
  });

  it("no open room yet, or a junk one, derives from the workspace", () => {
    for (const open of [null, undefined, "", "not-a-room"]) {
      expect(roomForOpenWorkspace(open, "construction"), String(open)).toBe("schedule");
    }
  });

  it("an unknown workspace lands in Work rather than nowhere", () => {
    expect(roomForOpenWorkspace("cost", "wat")).toBe("work");
  });

  it("THE PROPERTY: the marker never names a room the open workspace does not show", () => {
    // Over every (open room, workspace) pair: the answer is a real room, and it is either hosted by
    // that workspace or the room that workspace preselects. A marker failing this is the defect in
    // its other direction — a strip stating a room whose content is not on screen.
    const workspaces = [...new Set([...Object.values(ROOM_HOST), "drawings", "studio", "design",
                                    "finance", "wat"])];
    for (const open of [...ROOM_IDS, "", "junk"]) {
      for (const ws of workspaces) {
        const r = roomForOpenWorkspace(open, ws);
        expect(ROOM_IDS as readonly string[], `${open} -> ${ws}`).toContain(r);
        expect(ROOM_HOST[r] === ws || preselectedRoom(ws) === r, `${open} -> ${ws} = ${r}`).toBe(true);
      }
    }
  });
});

describe("main.ts really calls them — the reproduction above is not the evidence", () => {
  const setWs = MAIN.slice(MAIN.indexOf("function setWorkspace("));
  const body = setWs.slice(0, setWs.indexOf("\n}\n"));

  it("setWorkspace marks the room strip", () => {
    expect(body).toContain("markRoomForWorkspace(key)");
  });

  it("and the marking goes through the imported rule and the imported DOM write", () => {
    expect(MAIN).toContain("roomTabsActive = roomForOpenWorkspace(roomTabsActive, key)");
    expect(MAIN).toContain("markActiveRoom(wsEl, roomTabsActive)");
  });

  it("THE DEAD LOOP IS GONE: no `.ws-btn` query sets aria-selected any more", () => {
    // The two remaining `.ws-btn` reads are WS-BTN-DEAD's, and neither marks anything: a documented
    // `??` fallback in `wsLabel`, and `applyPersona`'s hide loop, which is blocked on a behavioural
    // question (which rooms a subcontractor sees) rather than a rename. Asserted as "none of them
    // marks" rather than "there are two", so closing the persona half does not red this file.
    //
    // CODE lines only, and the first draft of this assertion did not do that — it red on the
    // comment in `setWorkspace` that explains the deletion, which mentions both `.ws-btn` and
    // `aria-selected` by name. *A check that cannot tell an explanation from the thing it explains
    // reds hardest on the commit that fixes the defect.* Four lines of lookahead, because the loop
    // this replaces spanned four.
    const code = MAIN.split("\n").map((l) => (/^\s*(\/\/|\*|\/\*)/.test(l) ? "" : l));
    expect(code.filter((l) => l.includes(".ws-btn")).length,
           "no .ws-btn read left in code at all — did this file stop looking?").toBeGreaterThan(0);
    code.forEach((line, i) => {
      if (!line.includes(".ws-btn")) return;
      const window = code.slice(i, i + 5).join("\n");
      expect(window, window).not.toContain("aria-selected");
    });
  });
});

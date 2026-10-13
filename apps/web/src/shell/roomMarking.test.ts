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
 * calls `setWorkspace(cfg.home)`, which for five of the eight personas is `construction` or
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
import {
  ROOM_HOST, ROOM_IDS, portalForRoom, portalForWorkspace, preselectedRoom, roomForOpenWorkspace,
} from "./spine";

const MAIN = readFileSync(resolve(__dirname, "../main.ts"), "utf8");

/** The strip as the app renders it, plus the three lines of `setWorkspace` that mark it. */
function makeNav(startRoom = "design") {
  const strip = document.createElement("div");
  document.body.replaceChildren(strip);
  renderRoomTabs(strip, buildRoomTabs(null, 6), startRoom, () => {});
  let roomTabsActive = startRoom;
  // CR-REVIEW-9 — keyed by PORTAL, like `main.ts`, and that keying IS the fix. The previous harness
  // held one `roomTabsActive` and fed it back in, which is what let the detour defect through: it
  // reproduced the broken shape faithfully and therefore could not fail on it.
  const roomByPortal = new Map<string, string>();
  const seed = portalForRoom(startRoom);
  if (seed) roomByPortal.set(seed, startRoom);
  return {
    strip,
    room: () => roomTabsActive,
    /** `main.ts`'s `goToRoom`, in the part that matters here: record, then switch workspace. */
    goToRoom(roomId: string) {
      const host = ROOM_HOST[roomId] ?? "construction";
      roomByPortal.set(portalForRoom(roomId) ?? portalForWorkspace(host), roomId);
      this.setWorkspace(host);
      roomTabsActive = roomId;
      markActiveRoom(strip, roomTabsActive);          // `paintRoomTabs(roomId)` in main.ts
    },
    /** `main.ts`'s `markRoomForWorkspace`, which after this change is only this. */
    setWorkspace(key: string) {
      roomTabsActive = roomForOpenWorkspace(roomByPortal.get(portalForWorkspace(key)), key);
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

  it("KEEPS the room this workspace's portal has open — a direct re-entry", () => {
    // Construction hosts planning, cost, schedule and work. Deriving from the workspace alone would
    // swap a marker stuck on the room you left for one contradicting what is on screen: the portal
    // goes on rendering Cost, because `portal.room()` is `activeRoom ?? preselectedRoom(wsFilter)`.
    const nav = makeNav("design");
    nav.goToRoom("cost");
    expect(nav.room()).toBe("cost");
    nav.setWorkspace("construction");
    expect(nav.room()).toBe("cost");
    expect(marked(nav.strip)).toEqual(["cost"]);
  });

  it("CR-REVIEW-9 — AND KEEPS IT ACROSS A DETOUR, which the first version did not", () => {
    // The regression, in the reviewer's own words: Cost is open, you go to Drawings and come back.
    // No `aec:room` fires on a workspace switch, so `PortalUI.activeRoom` is still `cost` the whole
    // time. The first rule tracked the LAST MARKER and re-derived on every switch, so Drawings
    // overwrote `cost` with `design` and the return leg derived `schedule` — a strip stating
    // Schedule over a portal rendering Cost.
    const nav = makeNav("design");
    nav.goToRoom("cost");
    nav.setWorkspace("drawings");
    expect(nav.room(), "the design portal has no room open, so Drawings preselects its own")
      .toBe("design");
    nav.setWorkspace("construction");
    expect(nav.room(), "the construction portal still has Cost open — the strip must say Cost")
      .toBe("cost");
    expect(marked(nav.strip)).toEqual(["cost"]);
  });

  it("each portal remembers its OWN room — one sticky value would collide", () => {
    const nav = makeNav("design");
    nav.goToRoom("cost");                 // construction portal
    nav.goToRoom("deal");                 // developer portal
    nav.setWorkspace("construction");
    expect(nav.room()).toBe("cost");
    nav.setWorkspace("developer");
    expect(nav.room()).toBe("deal");
  });

  it("four workspaces share the design room, and all four preselect it", () => {
    // `ROOM_HOST.design` is only `model`, and `portalRooms("design")` is `["design"]` — the design
    // portal is special-cased there. With nothing open, all four fall through to the same room.
    for (const ws of ["model", "drawings", "studio", "design"]) {
      expect(roomForOpenWorkspace(null, ws), ws).toBe("design");
      expect(portalForWorkspace(ws), ws).toBe("design");
    }
  });

  it("nothing open, or a junk value, derives from the workspace", () => {
    for (const open of [null, undefined, "", "not-a-room"]) {
      expect(roomForOpenWorkspace(open, "construction"), String(open)).toBe("schedule");
    }
  });

  it("an unknown workspace lands in Work rather than nowhere", () => {
    expect(roomForOpenWorkspace(null, "wat")).toBe("work");
    expect(portalForWorkspace("wat")).toBe("construction");   // Work's portal
  });

  it("portalForRoom covers every room, and no room belongs to two portals", () => {
    // The function is derived from `portalRooms` over the three filters rather than written as a
    // fourth table. If it ever returned null for a shipped room, `goToRoom` would record that room
    // under a fallback key and the detour defect would come back for it alone.
    const owners = ROOM_IDS.map((r) => [r, portalForRoom(r)] as const);
    for (const [r, o] of owners) expect(o, `${r} belongs to no portal`).not.toBeNull();
    expect(new Set(owners.map(([, o]) => o))).toEqual(new Set(["construction", "developer", "design"]));
  });

  it("THE PROPERTY: the marker is exactly what that workspace's portal would render", () => {
    // The old property here was weaker and it is why the detour got through: it asserted only that
    // the marker names a room the open workspace CAN show, which `schedule` does for construction
    // even while the portal renders Cost. The right invariant compares against the portal's own
    // expression, `activeRoom ?? preselectedRoom(wsFilter)`, over every (sticky room, workspace)
    // pair — including the pairs where the sticky room belongs to a DIFFERENT portal, which the
    // caller never produces and which must therefore not be asserted about.
    const workspaces = ["model", "drawings", "studio", "design", "construction", "developer",
                        "finance", "wat"];
    for (const ws of workspaces) {
      const owner = portalForWorkspace(ws);
      for (const open of [...ROOM_IDS.filter((r) => portalForRoom(r) === owner), "", "junk"]) {
        const got = roomForOpenWorkspace(open, ws);
        const portalWould = (ROOM_IDS as readonly string[]).includes(open)
          ? open : preselectedRoom(ws);
        expect(got, `${open || "(none)"} -> ${ws}`).toBe(portalWould);
        expect(ROOM_IDS as readonly string[], `${open} -> ${ws}`).toContain(got);
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
    expect(MAIN).toContain(
      "roomTabsActive = roomForOpenWorkspace(roomByPortal.get(portalForWorkspace(key)), key)");
    expect(MAIN).toContain("markActiveRoom(wsEl, roomTabsActive)");
  });

  it("CR-REVIEW-9: the remembered room is keyed by PORTAL, not by the last marker", () => {
    // The whole fix is this keying. Feeding `roomTabsActive` back in is what let a detour through
    // another workspace destroy the room the portal still had open, and the harness above cannot
    // catch a regression to that shape on its own — it would faithfully reproduce it.
    expect(MAIN).toContain("const roomByPortal = new Map<string, string>()");
    expect(MAIN).not.toContain("roomForOpenWorkspace(roomTabsActive,");
    // and `goToRoom` is where the portal's choice is recorded
    const g = MAIN.slice(MAIN.indexOf("function goToRoom("));
    expect(g.slice(0, g.indexOf("\n}\n"))).toContain("roomByPortal.set(");
  });

  it("THE DEAD LOOP IS GONE: no `.ws-btn` query sets aria-selected any more", () => {
    // CODE lines only, and the first draft of this assertion did not do that — it red on the
    // comment in `setWorkspace` that explains the deletion, which mentions both `.ws-btn` and
    // `aria-selected` by name. *A check that cannot tell an explanation from the thing it explains
    // reds hardest on the commit that fixes the defect.* Four lines of lookahead, because the loop
    // this replaces spanned four.
    const strip = (t: string) => t.split("\n").map((l) => (/^\s*(\/\/|\*|\/\*)/.test(l) ? "" : l));
    const marks = (lines: string[]) => lines.filter(
      (l, i) => l.includes(".ws-btn") && lines.slice(i, i + 5).join("\n").includes("aria-selected"));

    // THE PRECONDITION IS A PLANTED CANARY, NOT A COUNT OF THE LIVE FILE. It used to read
    // `expect(code.filter((l) => l.includes(".ws-btn")).length).toBeGreaterThan(0)` with the message
    // *"did this file stop looking?"* — and that set empties for TWO reasons: the derivation broke,
    // or `.ws-btn` was finally deleted from `main.ts` altogether. **WS-BTN-DEAD deleted it, and this
    // red with a message blaming the wrong cause** — the exact failure `clientCallers.test.ts`
    // recorded (*"an entry leaves that set for two reasons and the message asserted one"*) and the
    // one `test_scratch_ignored.py` answered by DERIVING its canary instead of naming it. The
    // comment two lines above the old assertion even claimed closing the persona half "does not red
    // this file": it reasoned about the half it expected, not about the class going entirely.
    // *A precondition written as a fact about today's tree is a prediction, and it was wrong.*
    expect(marks(strip('document.querySelectorAll(".ws-btn").forEach((b) => {\n'
                       + '  b.setAttribute("aria-selected", String(on));\n});'))).toHaveLength(1);
    expect(marks(strip(' * a loop over `.ws-btn` that set `aria-selected` — deleted'))).toEqual([]);

    expect(marks(strip(MAIN))).toEqual([]);
  });
});

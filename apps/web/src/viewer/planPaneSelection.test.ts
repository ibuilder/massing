/**
 * R36-VIEWER-SUBAPP ⑤ — the selection survives a change of canvas, carried as a GlobalId.
 *
 * WHY THIS FILE EXISTS EVEN THOUGH THE BEHAVIOUR ALREADY WORKS
 * -----------------------------------------------------------
 * Slice 5 asks that picking a door in 3D and switching to Sheets shows it on the drawing. Measured
 * against the shipped code, that already happens — but by three separate mechanisms lining up rather
 * than by anything asserting it:
 *
 *   1. `onSelectionChanged = (guid) => planPane.highlight(guid)` fires whether or not the pane is
 *      visible, and `highlight` stores `this.sel` before touching the DOM.
 *   2. `dock("full")` calls `refresh(true)`.
 *   3. `refresh` ends with `syncPlanHighlight(this.body, this.sel)`.
 *
 * Remove any one and the feature disappears silently: the plan renders, nothing is lit, and it looks
 * like the element simply is not on this level. Nothing in the suite would notice, because `PlanPane`
 * had **no instance-level tests at all** — only its pure exports were covered. So this is not new
 * behaviour, it is the first thing that will fail if the behaviour goes.
 *
 * The non-negotiable being pinned: the identity crossing the seam is the **IFC GlobalId**, never a
 * viewer id or a DOM node. That is why a selection made while the plan did not exist can still land
 * on markup fetched afterwards.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { PlanPane, type PlanPaneDeps, syncPlanHighlight } from "./planPane";

const SVG =
  '<svg><polyline data-guid="DOOR_5F" data-class="IfcDoor" points="0,0 1,1" stroke="#111" stroke-width="0.8"/>'
  + '<polyline data-guid="WALL_A" data-class="IfcWall" points="2,2 3,3" stroke="#111" stroke-width="0.8"/></svg>';

function pane(over: Partial<PlanPaneDeps> = {}): PlanPane {
  return new PlanPane({
    url: (path) => `http://api.test${path}`,
    projectId: () => "p1",
    activeStorey: () => "Level 1",
    notify: () => {},
    headers: () => ({}),
    ...over,
  });
}

let fetchMock: ReturnType<typeof vi.fn>;

beforeEach(() => {
  fetchMock = vi.fn(async () => new Response(SVG, { status: 200 }));
  vi.stubGlobal("fetch", fetchMock);
});
afterEach(() => vi.unstubAllGlobals());

describe("a selection made in 3D lands on the sheet after the switch", () => {
  it("remembers the GlobalId while the plan is not rendered, and applies it when it is", async () => {
    const p = pane();
    // Model mode: the pane is closed and its body is empty. The user picks a door in 3D.
    expect(p.isOpen).toBe(false);
    p.highlight("DOOR_5F");

    // Switch to Sheets. `dock` renders the plan for the first time — the markup carrying DOOR_5F
    // did not exist when the selection was made.
    p.dock("full");
    await vi.waitFor(() => expect(fetchMock).toHaveBeenCalled());
    await vi.waitFor(() => expect(p.el.querySelectorAll("polyline").length).toBeGreaterThan(0));

    const door = p.el.querySelector('polyline[data-guid="DOOR_5F"]:not([data-hit])');
    expect(door?.getAttribute("stroke"), "the element selected in 3D is not lit on the sheet — the "
      + "selection did not cross the mode change").toBe("#2563eb");

    const wall = p.el.querySelector('polyline[data-guid="WALL_A"]:not([data-hit])');
    expect(wall?.getAttribute("stroke"), "an unselected element must keep its own stroke").toBe("#111");
  });

  it("lights nothing, rather than erroring, when the selection is not on this cut", async () => {
    // The realistic case the moment levels exist: a 5th-floor door selected while the sheet shows
    // Level 1. "Nothing lit" is the correct answer and must not be a thrown error or a blank pane.
    const p = pane();
    p.highlight("NOT_ON_THIS_LEVEL");
    p.dock("full");
    await vi.waitFor(() => expect(p.el.querySelectorAll("polyline").length).toBeGreaterThan(0));
    expect(p.el.querySelectorAll('polyline[stroke="#2563eb"]')).toHaveLength(0);
    expect(p.el.querySelector('polyline[data-guid="WALL_A"]')?.getAttribute("stroke")).toBe("#111");
  });
});

describe("the dock styles are a mode, not a second visibility flag", () => {
  it("full occupies the whole canvas; side is the 38% strip; hidden yields it", () => {
    const p = pane();
    p.dock("full");
    expect(p.el.style.width).toBe("100%");
    expect(p.el.style.display).toBe("flex");
    expect(p.isOpen).toBe(true);

    p.dock("side");
    expect(p.el.style.width).toBe("38%");
    expect(p.isOpen).toBe(true);

    p.dock("hidden");
    expect(p.el.style.display).toBe("none");
    expect(p.isOpen).toBe(false);
  });

  it("hiding does not forget the selection — coming back must not need a re-pick", async () => {
    /**
     * The twin of the first test: if `hidden` cleared `sel`, Model -> Sheets -> Model -> Sheets would
     * lose the highlight on the second visit and read as intermittent.
     *
     * THIS TEST WAS VACUOUS ON ITS FIRST WRITING, and a mutation check is the only reason that is
     * known. It waited for the highlight after the second `dock("full")` — but the re-render is
     * async, so `waitFor` sampled the DOM still left over from the FIRST render, which was already
     * highlighted, and passed on the first poll. Adding `if (!this.open) this.sel = null;` to
     * `dock` — the exact defect this test names — did not fail it.
     *
     * The fix is to wait for the evidence that the NEW render happened (a further fetch) before
     * asserting anything about the markup. Waiting on the thing you are asserting about is how a
     * test ends up reading a stale value.
     */
    const p = pane();
    p.highlight("DOOR_5F");
    p.dock("full");
    await vi.waitFor(() => expect(p.el.querySelectorAll("polyline").length).toBeGreaterThan(0));

    // Serve DISTINCT markup for the second render, so "the new DOM has landed" is observable rather
    // than inferred. Waiting on the fetch COUNT is not enough — the mock is called when the request
    // starts, and the next poll still reads the previous render, which is already highlighted.
    fetchMock.mockImplementation(async () =>
      new Response(SVG.replace("</svg>",
        '<polyline data-guid="SECOND_RENDER" points="9,9 8,8" stroke="#111" stroke-width="0.8"/></svg>'),
        { status: 200 }));

    p.dock("hidden");
    p.dock("full");
    await vi.waitFor(() =>
      expect(p.el.querySelector('polyline[data-guid="SECOND_RENDER"]'),
        "the second render never landed — the assertion below would have read stale markup").not.toBeNull());

    expect(p.el.querySelector('polyline[data-guid="DOOR_5F"]:not([data-hit])')?.getAttribute("stroke"),
      "the selection was forgotten while the plan was hidden — returning to Sheets needs a re-pick")
      .toBe("#2563eb");
  });
});

describe("syncPlanHighlight is the seam, and it speaks GlobalId", () => {
  it("applies to markup it has never seen before — identity is the guid, not a node reference", () => {
    // Why the whole thing works: highlight state is a string, so it survives the DOM being replaced.
    const host = document.createElement("div");
    host.innerHTML = SVG;
    expect(syncPlanHighlight(host, "DOOR_5F")).toBe(1);
    // replace the markup entirely, as a refresh does, and re-apply the same guid
    host.innerHTML = SVG;
    expect(syncPlanHighlight(host, "DOOR_5F")).toBe(1);
  });

  it("clearing the selection restores the original stroke rather than a hardcoded default", () => {
    const host = document.createElement("div");
    host.innerHTML = SVG;
    syncPlanHighlight(host, "DOOR_5F");
    syncPlanHighlight(host, null);
    expect(host.querySelector('polyline[data-guid="DOOR_5F"]')?.getAttribute("stroke")).toBe("#111");
  });
});

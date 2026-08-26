/**
 * R38-SYNC-VIEW — the plan pane's pure contract: what cut it asks for, and when it asks again.
 *
 * The refetch rule is the load-bearing one. The pane is meant to be left OPEN while modeling, so a
 * selection change — which happens on every click — must not cost a drawing round-trip. Only a
 * change to the CUT (storey or scale) may. A pane that refetched on selection would be quietly
 * unusable on any real model, and nothing in the UI would say why.
 */
import { describe, expect, it, vi } from "vitest";
import { addHitTargets, needsRefetch, planParams, PlanPane, syncPlanHighlight } from "./planPane";

/** A served plan fragment: two loops of one wall (cut at a doorway) + one slab loop + a hit twin
 *  candidate. SVG namespace is irrelevant to the logic under test; happy-dom parses this fine. */
function planFixture(): HTMLElement {
  const host = document.createElement("div");
  host.innerHTML =
    '<svg><polyline data-guid="WALL_A" data-class="IfcWall" points="0,0 1,1" stroke="#111" stroke-width="0.8"/>'
    + '<polyline data-guid="WALL_A" data-class="IfcWall" points="2,2 3,3" stroke="#111" stroke-width="0.8"/>'
    + '<polyline data-guid="SLAB_B" data-class="IfcSlab" points="4,4 5,5" stroke="#111" stroke-width="0.8"/>'
    + "</svg>";
  return host;
}

describe("planParams — the cut being asked for", () => {
  it("always carries a scale, and the storey only when there is one", () => {
    expect(planParams("Level 1", 100).toString()).toBe("scale=100&storey=Level+1");
    expect(planParams(null, 100).toString()).toBe("scale=100");
  });

  it("carries the scale it was given, not a default", () => {
    expect(planParams("Level 2", 50).get("scale")).toBe("50");
    expect(planParams("Level 2", 200).get("scale")).toBe("200");
  });
});

describe("needsRefetch — only the cut costs a round-trip", () => {
  it("the first look always fetches", () => {
    expect(needsRefetch(null, { storey: "Level 1", scale: 100 })).toBe(true);
  });

  it("the same cut does not re-fetch — this is what makes the pane cheap to leave open", () => {
    const cut = { storey: "Level 1", scale: 100 };
    expect(needsRefetch(cut, { ...cut })).toBe(false);
  });

  it("a storey change re-fetches — the plan IS a cut at a level", () => {
    expect(needsRefetch({ storey: "Level 1", scale: 100 },
                        { storey: "Level 2", scale: 100 })).toBe(true);
  });

  it("a scale change re-fetches — the generator draws different detail per scale", () => {
    expect(needsRefetch({ storey: "Level 1", scale: 100 },
                        { storey: "Level 1", scale: 50 })).toBe(true);
  });

  it("whole-model and a named level are different cuts, in both directions", () => {
    expect(needsRefetch({ storey: null, scale: 100 }, { storey: "Level 1", scale: 100 })).toBe(true);
    expect(needsRefetch({ storey: "Level 1", scale: 100 }, { storey: null, scale: 100 })).toBe(true);
  });
});

describe("addHitTargets — every drawn line gets one invisible fat twin (R38-SYNC-SELECT)", () => {
  it("adds exactly one twin per identified polyline, and the twin keeps the guid", () => {
    const host = planFixture();
    expect(addHitTargets(host)).toBe(3);
    const twins = host.querySelectorAll('[data-hit]');
    expect(twins.length).toBe(3);
    twins.forEach((t) => {
      expect(t.getAttribute("stroke")).toBe("transparent");
      expect(t.getAttribute("data-guid")).toBeTruthy();
    });
  });

  it("is idempotent — a second pass (every refresh calls it) adds nothing", () => {
    const host = planFixture();
    addHitTargets(host);
    expect(addHitTargets(host)).toBe(0);
    expect(host.querySelectorAll("[data-hit]").length).toBe(3);
  });
});

describe("syncPlanHighlight — one element is MANY loops", () => {
  it("lights every loop of the guid, and reports how many", () => {
    const host = planFixture();
    expect(syncPlanHighlight(host, "WALL_A")).toBe(2);   // the wall cut at a doorway = two loops
    const lit = [...host.querySelectorAll("polyline")].filter((p) => p.getAttribute("stroke") === "#2563eb");
    expect(lit.length).toBe(2);
    expect(lit.every((p) => p.getAttribute("data-guid") === "WALL_A")).toBe(true);
  });

  it("moving the selection restores the previous element's own stroke, exactly", () => {
    const host = planFixture();
    syncPlanHighlight(host, "WALL_A");
    expect(syncPlanHighlight(host, "SLAB_B")).toBe(1);
    const walls = [...host.querySelectorAll('[data-guid="WALL_A"]')];
    expect(walls.every((p) => p.getAttribute("stroke") === "#111"
      && p.getAttribute("stroke-width") === "0.8")).toBe(true);
  });

  it("null clears everything back to the served styling", () => {
    const host = planFixture();
    syncPlanHighlight(host, "WALL_A");
    expect(syncPlanHighlight(host, null)).toBe(0);
    expect([...host.querySelectorAll("polyline")]
      .every((p) => p.getAttribute("stroke") === "#111")).toBe(true);
  });

  it("an element not on this storey's plan lights zero loops — a fact, not a crash", () => {
    const host = planFixture();
    expect(syncPlanHighlight(host, "NOT_ON_THIS_PLAN")).toBe(0);
  });

  it("hit twins never light — they exist only to be clicked", () => {
    const host = planFixture();
    addHitTargets(host);
    syncPlanHighlight(host, "WALL_A");
    host.querySelectorAll("[data-hit]").forEach((t) => {
      expect(t.getAttribute("stroke")).toBe("transparent");
    });
  });
});

describe("the markup key is the storey's GlobalId", () => {
  /**
   * R36 premise-check, 2026-08-26. This pane keyed its markups `plan:<activeStorey()>` — the human
   * level NAME — so renaming a level orphaned every pin on it. The GUID was already reachable:
   * `modelGrid` serves `levels[].guid` and its own type comment says why it matters, warning in
   * as many words against the `?? level.name` fallback that would put the bug back.
   */
  function keysFetched(deps: { storey: string | null; guid?: string | null }) {
    const asked: string[] = [];
    const svg = '<svg data-plan-scale="1" data-plan-ox="0" data-plan-oy="0" '
      + 'data-plan-minx="0" data-plan-miny="0" data-plan-drawh="10"></svg>';
    vi.stubGlobal("fetch", async () => new Response(svg, { status: 200 }));
    const pane = new PlanPane({
      url: (p) => p, projectId: () => "p1",
      activeStorey: () => deps.storey,
      activeStoreyGuid: deps.guid === undefined ? undefined : () => deps.guid ?? null,
      notify: () => {},
      markupApi: {
        drawingMarkup: async (_pid: string, id: string) => { asked.push(id); return []; },
        promoteDrawingMarkup: async () => ({ topic: { title: "t" } }),
        deleteDrawingMarkup: async () => undefined,
      },
    });
    document.body.appendChild(pane.el);
    pane.dock("full");
    return { pane, asked };
  }

  it("asks for the GUID key, not the name", async () => {
    const { pane, asked } = keysFetched({ storey: "Level 1", guid: "3aB7xQ" });
    await pane.refresh(true);
    expect(asked, "the key new markups are written under").toContain("plan:3aB7xQ");
    vi.unstubAllGlobals();
  });

  it("also reads the pre-GUID name key, so existing pins still show", async () => {
    const { pane, asked } = keysFetched({ storey: "Level 1", guid: "3aB7xQ" });
    await pane.refresh(true);
    expect(asked).toContain("plan:Level 1");
    vi.unstubAllGlobals();
  });

  // The important negative. A host that has not wired the GUID must show NOTHING rather than fall
  // back to the name — a fallback would be indistinguishable from the fixed code while carrying the
  // exact defect, and it is the one line the client type's comment predicted somebody would write.
  it("shows no pins at all when the host has not wired a GUID — it does not fall back to the name", async () => {
    const { pane, asked } = keysFetched({ storey: "Level 1" });
    await pane.refresh(true);
    expect(asked, "no markup fetch is better than one keyed on a renameable name").toEqual([]);
    vi.unstubAllGlobals();
  });
});

describe("ground cursor survives an SVG refresh", () => {
  it("re-paints the last ground point after the drawing is replaced", async () => {
    const svg = '<svg data-plan-scale="1" data-plan-ox="0" data-plan-oy="0" '
      + 'data-plan-minx="0" data-plan-miny="0" data-plan-drawh="10"></svg>';
    vi.stubGlobal("fetch", async () => new Response(svg, { status: 200 }));
    const pane = new PlanPane({
      url: (p) => p, projectId: () => "p1", activeStorey: () => "L1", notify: () => {},
    });
    document.body.appendChild(pane.el);
    pane.dock("full");
    await pane.refresh(true);
    pane.showGroundCursor({ x: 2, z: -3 });
    const mark = pane.el.querySelector("circle");
    expect(mark).toBeTruthy();
    expect(mark!.style.display).not.toBe("none");
    const cx = mark!.getAttribute("cx");
    await pane.refresh(true);
    const after = pane.el.querySelector("circle");
    expect(after!.style.display).not.toBe("none");
    expect(after!.getAttribute("cx")).toBe(cx);
    pane.showGroundCursor(null);
    expect(pane.el.querySelector("circle")!.style.display).toBe("none");
    vi.unstubAllGlobals();
    pane.el.remove();
  });
});

import { beforeEach, describe, expect, it } from "vitest";

import { MarkupLayer, placeable, type MarkupApi, type MarkupLayerDeps } from "./markupLayer";

/**
 * `drawings.test.ts` characterises the layer THROUGH the Drawings room, which is what proved the
 * extraction changed nothing. This tests the layer on its own terms, and in particular the property
 * the extraction exists for: **it can be mounted twice.** While it was private state on `DrawingsUI`
 * that was not a thing anyone could check, because there was only ever one of it.
 */
const item = (over: Record<string, unknown> = {}) => ({
  id: "m1", x: 10, y: 20, note: "check this", data: {}, ...over,
} as never);

function layer(over: {
  pins?: unknown[]; takeoff?: unknown[]; fail?: boolean;
  answer?: string | null; sheet?: string | null;
} = {}) {
  const host = document.createElement("div");
  const pinLayer = document.createElement("div");
  const svgHost = document.createElement("div");
  svgHost.innerHTML = '<svg xmlns="http://www.w3.org/2000/svg"></svg>';
  host.append(svgHost, pinLayer);

  const calls: string[] = [];
  const api: MarkupApi = {
    drawingMarkup: async (_pid, id) => {
      calls.push(`get:${id}`);
      if (over.fail) throw new Error("down");
      return ((id.endsWith("#pdf") ? over.takeoff : over.pins) ?? []) as never;
    },
    promoteDrawingMarkup: async (_pid, id) => { calls.push(`promote:${id}`); return { topic: { title: "RFI-1" } }; },
    deleteDrawingMarkup: async (_pid, id) => { calls.push(`delete:${id}`); return {}; },
  };
  const counts: number[] = [];
  const status: string[] = [];
  const deps: MarkupLayerDeps = {
    pinLayer, svgHost,
    getScale: () => 1,
    api,
    projectId: () => "p1",
    sheetId: () => (over.sheet === undefined ? "plan:L1" : over.sheet),
    setStatus: (m) => status.push(m),
    onCount: (n) => counts.push(n),
    prompt: (async () => over.answer ?? null) as MarkupLayerDeps["prompt"],
  };
  return { l: new MarkupLayer(deps), deps, pinLayer, svgHost, calls, counts, status };
}

const settle = async () => { for (let i = 0; i < 5; i++) await Promise.resolve(); };

beforeEach(() => { document.body.innerHTML = ""; });

describe("placeable", () => {
  it("keeps pins, and only the takeoffs that carry a normalised anchor", () => {
    const pins = [item({ id: "p1" })];
    const takeoff = [item({ id: "t1", kind: "area", data: { nx: 0.5, ny: 0.5 } }),
                     item({ id: "t2", kind: "area", data: {} })];
    expect(placeable(pins, takeoff).map((m) => m.id)).toEqual(["p1", "t1"]);
  });

  // Rendering an unanchored takeoff at 0,0 would put a measurement in the corner of an unrelated
  // drawing, which reads as a real annotation rather than a missing one.
  it("drops an unanchored takeoff rather than placing it at the origin", () => {
    expect(placeable([], [item({ id: "t", kind: "count", data: {} })])).toEqual([]);
  });
});

describe("loading", () => {
  it("asks for the sheet's pins AND the PDF editor's takeoffs", async () => {
    const h = layer();
    await h.l.load();
    expect(h.calls).toEqual(["get:plan:L1", "get:plan:L1#pdf"]);
  });

  it("renders nothing, and asks for nothing, when no sheet is on screen", async () => {
    const h = layer({ sheet: null });
    await h.l.load();
    expect(h.calls).toEqual([]);
    expect(h.pinLayer.children).toHaveLength(0);
  });

  it("a failure leaves the drawing usable and the layer empty", async () => {
    const h = layer({ fail: true, pins: [item()] });
    await h.l.load();
    expect(h.pinLayer.children).toHaveLength(0);
    expect(h.l.count).toBe(0);
  });

  it("reports its count to the host after every render", async () => {
    const h = layer({ pins: [item({ id: "a" }), item({ id: "b" })] });
    await h.l.load();
    expect(h.counts.at(-1)).toBe(2);
  });
});

describe("rendering", () => {
  it("numbers pins and marks the linked, carried and tied ones", async () => {
    const h = layer({
      pins: [item({ id: "a", topic_id: "t1" }),
             item({ id: "b", data: { carried_from: "R1" } }),
             item({ id: "c" })],
    });
    await h.l.load();
    const pins = [...h.pinLayer.children] as HTMLElement[];
    expect(pins).toHaveLength(3);
    expect(pins[0]!.textContent).toBe("1");
    expect(pins[0]!.classList.contains("linked")).toBe(true);
    expect(pins[1]!.classList.contains("carried")).toBe(true);
    expect(pins[2]!.className).toBe("dwg-pin");
  });

  it("a re-render replaces the pins rather than stacking them", async () => {
    const h = layer({ pins: [item()] });
    await h.l.load();
    await h.l.load();
    expect(h.pinLayer.children).toHaveLength(1);
  });
});

describe("pin actions", () => {
  it("raises an RFI when asked, and says so", async () => {
    const h = layer({ pins: [item({ id: "m9" })], answer: "rfi" });
    await h.l.load();
    (h.pinLayer.firstElementChild as HTMLElement).click();
    await settle();
    expect(h.calls).toContain("promote:m9");
    expect(h.status.some((m) => m.includes("RFI-1"))).toBe(true);
  });

  it("does not raise a second RFI for a markup that already has one", async () => {
    const h = layer({ pins: [item({ id: "m9", topic_id: "t1" })], answer: "rfi" });
    await h.l.load();
    (h.pinLayer.firstElementChild as HTMLElement).click();
    await settle();
    expect(h.calls.some((c) => c.startsWith("promote:"))).toBe(false);
  });

  it("deletes when asked, then reloads so the pin actually disappears", async () => {
    const h = layer({ pins: [item({ id: "m9" })], answer: "del" });
    await h.l.load();
    h.calls.length = 0;
    (h.pinLayer.firstElementChild as HTMLElement).click();
    await settle();
    expect(h.calls).toContain("delete:m9");
    expect(h.calls.filter((c) => c.startsWith("get:")).length, "reloaded after the change").toBeGreaterThan(0);
  });

  it("a dismissed prompt changes nothing", async () => {
    const h = layer({ pins: [item({ id: "m9" })], answer: null });
    await h.l.load();
    h.calls.length = 0;
    (h.pinLayer.firstElementChild as HTMLElement).click();
    await settle();
    expect(h.calls).toEqual([]);
  });
});

/**
 * THE POINT OF THE EXTRACTION. Two independent layers over two hosts, each with its own pins — which
 * is what lets the Sheets canvas show the markup the Drawings room writes, keyed by the same sheet id.
 */
describe("it can be mounted twice", () => {
  it("two layers render independently and do not share DOM", async () => {
    const a = layer({ pins: [item({ id: "a1" })] });
    const b = layer({ pins: [item({ id: "b1" }), item({ id: "b2" })] });
    await a.l.load();
    await b.l.load();
    expect(a.pinLayer.children).toHaveLength(1);
    expect(b.pinLayer.children).toHaveLength(2);
    expect(a.l.count).toBe(1);
    expect(b.l.count).toBe(2);
  });

  it("both ask for the SAME sheet key, which is what makes them one feature", async () => {
    const a = layer();
    const b = layer();
    await a.l.load();
    await b.l.load();
    expect(a.calls[0]).toBe(b.calls[0]);
  });
});

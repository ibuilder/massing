import { readFileSync } from "node:fs";
import { resolve } from "node:path";

import { describe, expect, it, vi } from "vitest";

import { CanvasModeSwitch, type CanvasMode, type ModeDef, MODE_ORDER, visibility } from "./canvasMode";

const REPO = resolve(__dirname, "../../../..");

function def(key: CanvasMode, over: Partial<ModeDef> = {}): ModeDef & { enter: ReturnType<typeof vi.fn>; leave: ReturnType<typeof vi.fn> } {
  return { key, label: key, enter: vi.fn(), leave: vi.fn(), ...over } as never;
}

describe("exactly one surface is the canvas", () => {
  it("enters the opening mode, so state and DOM agree from the first frame", () => {
    // Without this the switch believes it is in `model` while the DOM shows whatever it happened to
    // show — and the first click on Model would be a no-op that leaves the wrong thing on screen.
    const model = def("model");
    new CanvasModeSwitch([model]);
    expect(model.enter).toHaveBeenCalledTimes(1);
  });

  it("leaves the old surface BEFORE entering the new one", () => {
    const order: string[] = [];
    const model = def("model", { leave: vi.fn(() => order.push("model.leave")) as never });
    const sheets = def("sheets", { enter: vi.fn(() => order.push("sheets.enter")) as never });
    const s = new CanvasModeSwitch([model, sheets]);
    s.switchTo("sheets");
    // Both-visible is the state that looks like a rendering bug and is really an ordering bug.
    expect(order).toEqual(["model.leave", "sheets.enter"]);
  });

  it("visibility is derived from the mode, so two-visible and none-visible are unrepresentable", () => {
    const registered: CanvasMode[] = ["model", "sheets"];
    for (const m of registered) {
      const vis = visibility(m, registered);
      expect(Object.values(vis).filter(Boolean)).toHaveLength(1);
      expect(vis[m]).toBe(true);
    }
  });
});

describe("re-clicking the active tab does not rebuild the surface", () => {
  it("switching to the active mode is a successful no-op", () => {
    // Re-entering would reset the 3D camera or the plan's scroll and zoom on every click of the tab
    // the user is already on — the kind of bug that reads as "the app is jumpy".
    const model = def("model");
    const s = new CanvasModeSwitch([model]);
    model.enter.mockClear();
    expect(s.switchTo("model")).toEqual({ ok: true });
    expect(model.enter).not.toHaveBeenCalled();
    expect(model.leave).not.toHaveBeenCalled();
  });
});

describe("a refusal says why, and does not move", () => {
  it("a blocked mode refuses with a reason and leaves the active mode alone", () => {
    const model = def("model");
    const sheets = def("sheets", { blocked: () => "load a model first — a sheet needs geometry to cut" });
    const s = new CanvasModeSwitch([model, sheets]);
    const r = s.switchTo("sheets");
    expect(r.ok).toBe(false);
    expect(r.reason).toMatch(/load a model first/);
    expect(s.active).toBe("model");
    expect(model.leave).not.toHaveBeenCalled();
    expect(sheets.enter).not.toHaveBeenCalled();
  });

  it("an unregistered mode refuses rather than silently doing nothing", () => {
    // The twin of the test above. A tab that swallows the click is indistinguishable from a broken
    // one — this repo has already shipped "a tab that highlights but doesn't navigate".
    const s = new CanvasModeSwitch([def("model")]);
    const r = s.switchTo("specs");
    expect(r.ok).toBe(false);
    expect(r.reason).toBeTruthy();
    expect(s.active).toBe("model");
  });

  it("blocked is re-evaluated per switch, not captured at construction", () => {
    // A model loads after the switch is built. If `blocked` were read once, Sheets would stay
    // refused for the life of the session.
    let ready = false;
    const s = new CanvasModeSwitch([def("model"), def("sheets", { blocked: () => (ready ? null : "no model") })]);
    expect(s.switchTo("sheets").ok).toBe(false);
    ready = true;
    expect(s.switchTo("sheets").ok).toBe(true);
    expect(s.active).toBe("sheets");
  });
});

describe("a mode cannot exist without a surface", () => {
  it("modes() returns only what was registered, in MODE_ORDER", () => {
    const s = new CanvasModeSwitch([def("sheets"), def("model")]);   // deliberately out of order
    expect(s.modes()).toEqual(["model", "sheets"]);
    expect(s.modes()).not.toContain("specs");
  });

  it("refuses a duplicate registration instead of letting the last one win", () => {
    expect(() => new CanvasModeSwitch([def("model"), def("model")])).toThrow(/duplicate/);
  });

  it("refuses an empty registration — a switch with no modes is not a switch", () => {
    expect(() => new CanvasModeSwitch([])).toThrow();
  });

  it("SPECS IS DELIBERATELY ABSENT — and app.ts must not register it without a surface", () => {
    /**
     * The roadmap names Model ▸ Sheets ▸ Specs. Specs ships when it has a canvas renderer; today the
     * spec book is a modal only. This asserts the intent rather than leaving it in a comment: if
     * someone wires a `specs` mode, this fails until a spec surface exists in the viewer, at which
     * point they delete this test on purpose rather than discovering the gap in review.
     */
    const app = readFileSync(resolve(REPO, "apps/web/src/viewer/app.ts"), "utf8");
    const registers = /key:\s*"specs"/.test(app);
    const hasSurface = /class\s+SpecPane|specPane/.test(app);
    expect(registers && !hasSurface, "a `specs` mode is registered but no spec surface exists — that "
      + "is a tab which highlights and shows nothing").toBe(false);
    expect(MODE_ORDER).toContain("specs");   // the seat is reserved, so this stays a scoping choice
  });
});

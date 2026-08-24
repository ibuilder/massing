import { beforeEach, describe, expect, it, vi } from "vitest";

import { mountCadBar, type CadBarDeps } from "./cadBar";

/**
 * `promptLoop.test.ts` proves the reducer. This proves the WIRING — that the bar mounts, that a typed
 * line still applies, and that the prompted path reaches the same recipes.
 *
 * It exists because the bar was extracted out of `app.ts` as a block of DOM construction, and a mistake
 * in that move — a listener not attached, a handler that never calls `applyRecipe` — would leave every
 * reducer test green while the command line did nothing at all. The reducer being correct says nothing
 * about whether anything calls it.
 */
function harness(over: Partial<CadBarDeps> = {}) {
  const host = document.createElement("div");
  const applied: Array<{ recipe: string; params: Record<string, unknown>; last: boolean }> = [];
  const deps: CadBarDeps = {
    host,
    container: document.createElement("div"),
    applyRecipe: async (recipe, params, last) => { applied.push({ recipe, params, last }); },
    waitForPublish: async () => "done",
    reload: async () => true,
    reloadPins: async () => {},
    clearDrafts: () => {},
    notify: () => {},
    ...over,
  };
  const api = mountCadBar(deps);
  const input = host.querySelector("input")!;
  const status = host.querySelector("div.meta")!;
  const enter = () => input.dispatchEvent(new KeyboardEvent("keydown", { key: "Enter", bubbles: true }));
  const key = (k: string) => input.dispatchEvent(new KeyboardEvent("keydown", { key: k, bubbles: true }));
  const type = (text: string) => { input.value = text; enter(); };
  return { host, input, status, applied, api, enter, key, type };
}

/** Let the mount's async apply chain settle. */
const settle = () => new Promise((r) => setTimeout(r, 0));

beforeEach(() => { document.body.innerHTML = ""; });

describe("mounting", () => {
  it("puts a command input and a status line into the host", () => {
    const h = harness();
    expect(h.input).toBeTruthy();
    expect(h.input.getAttribute("aria-label")).toBe("CAD command line");
    expect(h.status).toBeTruthy();
  });
});

describe("the typed path still works after the extraction", () => {
  it("applies a complete line", async () => {
    const h = harness();
    h.type("WALL 0,0 5,0 3");
    await settle();
    expect(h.applied.map((a) => a.recipe)).toEqual(["add_wall"]);
    expect(h.applied[0]!.params).toMatchObject({ height: 3 });
    expect(h.applied[0]!.last).toBe(true);
  });

  it("shows an info response without applying anything", async () => {
    const h = harness();
    h.type("HELP");
    await settle();
    expect(h.applied).toEqual([]);
    expect(h.status.textContent).toMatch(/WALL/);
  });

  it("an incomplete TYPED line reports the usage rather than arming a prompt", async () => {
    const h = harness();
    h.type("WALL 0,0");
    await settle();
    expect(h.applied).toEqual([]);
    // Still the parser's message — the prompt loop only takes a bare verb.
    expect(h.status.textContent).toMatch(/two points/);
  });
});

describe("the prompted path", () => {
  it("a bare verb arms the command and asks for its first argument", () => {
    const h = harness();
    h.type("WALL");
    expect(h.status.textContent).toMatch(/WALL: Specify start point/);
    expect(h.input.value).toBe("");
  });

  it("collects typed arguments and applies the same recipe the typed line would", async () => {
    const h = harness();
    h.type("WALL");
    h.type("0,0");
    h.type("5,0");
    h.enter();                       // empty Enter skips the optional height and applies
    await settle();
    expect(h.applied.map((a) => a.recipe)).toEqual(["add_wall"]);
    expect(h.applied[0]!.params).toMatchObject({ start: [0, 0], end: [5, 0] });
  });

  // SPACE's only argument is optional, so it is committable the moment it is armed — but it still ASKS,
  // because the value is worth offering. One Enter skips it and applies at the default.
  it("a command whose only argument is optional still asks, then applies on Enter", async () => {
    const h = harness();
    h.type("SPACE");
    expect(h.status.textContent).toMatch(/Rooms per storey/);
    expect(h.applied).toEqual([]);
    h.enter();
    await settle();
    expect(h.applied.length).toBeGreaterThan(0);
  });

  // The bug this pins: completing the REQUIRED arguments used to apply straight away, so the optional
  // height could never be typed — the command committed at its default while the user was still typing.
  it("does NOT apply the moment the required arguments are in", async () => {
    const h = harness();
    h.type("WALL");
    h.type("0,0");
    h.type("5,0");
    await settle();
    expect(h.applied, "still asking for the height").toEqual([]);
    expect(h.status.textContent).toMatch(/Height/);
  });

  it("Escape cancels an armed command and applies nothing", async () => {
    const h = harness();
    h.type("WALL");
    h.type("0,0");
    h.key("Escape");
    await settle();
    expect(h.status.textContent).toBe("cancelled");
    expect(h.applied).toEqual([]);
  });

  it("a typo is reported and does not lose the collected points", async () => {
    const h = harness();
    h.type("WALL");
    h.type("0,0");
    h.type("5,0");
    h.type("tall");                  // height must be a number
    await settle();
    expect(h.applied).toEqual([]);   // not applied on a bad value
    expect(h.status.textContent).toMatch(/not a number/);
    h.type("2.4");                   // ...and the command still completes
    await settle();
    expect(h.applied[0]!.params).toMatchObject({ height: 2.4 });
  });

  it("Backspace on an empty line gives back the last collected value", () => {
    const h = harness();
    h.type("WALL");
    h.type("0,0");
    expect(h.status.textContent).toMatch(/Specify end point/);
    h.input.value = "";
    h.key("Backspace");
    expect(h.status.textContent).toMatch(/Specify start point/);
  });
});

describe("the pick feed", () => {
  // The click handler in `app.ts` returns early only when this says the click was consumed. A feed that
  // always claimed it would break selection everywhere the bar is mounted.
  it("declines a click when nothing is armed", () => {
    const h = harness();
    expect(h.api.pick([1, 2])).toBe(false);
  });

  it("takes a click when a point is being asked for, and applies once complete", async () => {
    const h = harness();
    h.type("WALL");
    expect(h.api.pick([0, 0])).toBe(true);
    expect(h.api.pick([5, 0])).toBe(true);
    h.enter();                       // both points placed; Enter skips the height and applies
    await settle();
    expect(h.applied.map((a) => a.recipe)).toEqual(["add_wall"]);
    expect(h.applied[0]!.params).toMatchObject({ start: [0, 0], end: [5, 0] });
  });

  it("stops taking clicks once the command has been applied", async () => {
    const h = harness();
    h.type("WALL");
    h.api.pick([0, 0]);
    h.api.pick([5, 0]);
    h.enter();
    await settle();
    expect(h.api.pick([9, 9]), "the command is done — this click belongs to selection").toBe(false);
  });
});

describe("failure is reported, not swallowed", () => {
  it("a failing recipe surfaces its message and notifies", async () => {
    const notify = vi.fn();
    const h = harness({
      applyRecipe: async () => { throw new Error("kernel refused"); },
      notify,
    });
    h.type("WALL 0,0 5,0");
    await settle();
    expect(h.status.textContent).toMatch(/kernel refused/);
    expect(notify).toHaveBeenCalled();
  });
});

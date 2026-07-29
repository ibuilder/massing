import { describe, expect, it } from "vitest";

import { KEY_SHORTCUTS } from "../viewer/keysDyn";
import { GLOBAL_KEYS, VIEWER_KEYS, keyContract, keysIn } from "./keys";

/**
 * The keyboard contract.
 *
 * The point of publishing one is that a user can trust it, so the only assertions worth writing are
 * the ones that catch it becoming false: a key printed that nothing dispatches, and a key dispatched
 * that nothing prints.
 */

describe("the published contract matches what is actually dispatched", () => {
  /** Straight from `main.ts`'s global handler — if that line changes, this list must too. */
  const DISPATCHED_GLOBAL = ["\\", "?"];
  const DISPATCHED_VIEWER = ["f", "escape", "m", "a", "s", "h"];

  it("every global key in the handler is published", () => {
    const published = GLOBAL_KEYS.map((e) => e.keys);
    for (const k of DISPATCHED_GLOBAL) expect(published).toContain(k);
    // ⌘K is bound inside the palette rather than the global handler, and is the single most valuable
    // key in the app — the audit's whole move 01. It must be first.
    expect(published[0]).toContain("⌘K");
  });

  /**
   * The published key is what a person types (`Esc`); the dispatched one is `KeyboardEvent.key`
   * (`escape`). The label is for humans and stays — this maps it to the event name so the two can be
   * compared, rather than renaming the UI to match an event constant.
   */
  const asEventKey = (label: string) => (label.toLowerCase() === "esc" ? "escape" : label.toLowerCase());

  it("every viewer key the handler forwards is published, and nothing extra is claimed", () => {
    const published = VIEWER_KEYS.map((e) => asEventKey(e.keys));
    expect([...published].sort()).toEqual([...DISPATCHED_VIEWER].sort());
  });
});

describe("the draw codes are not a second copy", () => {
  it("agrees with viewer/keysDyn in BOTH directions", () => {
    const contract = keysIn(keyContract(KEY_SHORTCUTS), "Draw tools");
    const source = KEY_SHORTCUTS.map(([code]) => code);
    // Set-equality both ways: a code added to the handler with no published key fails here, and so
    // does a published key for a tool that was removed. One direction would only catch half of it.
    expect([...contract].sort()).toEqual([...source].sort());
  });

  it("carries the real labels, not the internal element keys", () => {
    const drawn = keyContract(KEY_SHORTCUTS).find((s) => s.title === "Draw tools")!;
    const wall = drawn.entries.find((e) => e.keys === "WA");
    expect(wall?.does).toBe("Wall");          // the label a person reads, not "wall" the recipe key
  });
});

describe("the contract degrades honestly", () => {
  it("omits the Draw tools section entirely when the viewer has not loaded", () => {
    // Rather than showing fourteen codes that would do nothing if pressed.
    const titles = keyContract([]).map((s) => s.title);
    expect(titles).toEqual(["Anywhere", "In the 3D view"]);
  });

  it("says the 3D keys need a model rather than letting the user find out", () => {
    const view = keyContract([]).find((s) => s.title === "In the 3D view")!;
    expect(view.note).toMatch(/model is open/i);
  });

  it("does not publish the audit's unbuilt keys", () => {
    // The audit proposed `G then M`, `J`/`K` and `A` = answer. None of them exist. Publishing an
    // aspiration is how a contract stops being one.
    const all = keyContract(KEY_SHORTCUTS).flatMap((s) => s.entries.map((e) => e.keys));
    expect(all).not.toContain("G then M");
    expect(all).not.toContain("J / K");
  });
});

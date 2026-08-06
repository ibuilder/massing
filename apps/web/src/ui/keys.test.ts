import { describe, expect, it } from "vitest";
import { readFileSync } from "node:fs";
import { resolve } from "node:path";

import { KEY_SHORTCUTS, SNAP_HELP } from "../viewer/keysDyn";
import { OVERRIDE_CODES } from "../viewer/snapOverride";
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

describe("AUTH-SNAP-OVERRIDE — the one-shot snap codes are not a second copy either", () => {
  it("agrees with viewer/snapOverride in BOTH directions", () => {
    const contract = keysIn(keyContract(KEY_SHORTCUTS, SNAP_HELP), "Snap for one pick");
    expect([...contract].sort()).toEqual(Object.keys(OVERRIDE_CODES).sort());
  });

  it("publishes a human label per code, not the internal kind", () => {
    const sect = keyContract(KEY_SHORTCUTS, SNAP_HELP).find((s) => s.title === "Snap for one pick")!;
    expect(sect.entries.find((e) => e.keys === "PE")?.does).toBe("Perpendicular");
    expect(sect.entries.find((e) => e.keys === "NO")?.does).toBe("No snap");
  });

  // The one thing a reader of this section most needs to know, because it is what makes it usable
  // mid-draw and is the whole difference from a mode.
  it("says it applies to one click and that Esc leaves the tool armed", () => {
    const sect = keyContract(KEY_SHORTCUTS, SNAP_HELP).find((s) => s.title === "Snap for one pick")!;
    expect(sect.note).toMatch(/that click only/i);
    expect(sect.note).toMatch(/not a mode/i);
    expect(sect.note).toMatch(/leaves the tool armed/i);
  });
});

/**
 * Both `?` handlers must publish the same sections.
 *
 * `main.ts` answers `?` globally and `viewer/keysDyn.ts` installs a second `?` listener once the 3D
 * bundle is in memory, so with the viewer loaded BOTH run. That was harmless only while they passed
 * identical arguments. This module's whole origin story is `?` giving two different answers depending
 * on load state, and the cheapest way for it to come back is a new section added to one call site.
 *
 * Asserted against source text because the two call sites are in module top-level key handlers that
 * cannot be invoked without standing up the shell and the viewer. Resolved from `process.cwd()`
 * (= `apps/web`) — under happy-dom `import.meta.url` has no `file:` scheme.
 */
describe("the two `?` call sites publish the same sections", () => {
  const read = (rel: string) => readFileSync(resolve(process.cwd(), rel), "utf8");

  it("main.ts passes the snap codes, not just the draw codes", () => {
    const src = read("src/main.ts");
    expect(src).toMatch(/SNAP_HELP/);
    // and imports it from the same module it already takes KEY_SHORTCUTS from, rather than keeping
    // a second copy of the table
    expect(src).toMatch(/KEY_SHORTCUTS,\s*SNAP_HELP/);
  });

  it("keysDyn.ts passes both as well", () => {
    expect(read("src/viewer/keysDyn.ts")).toMatch(/showKeyHelp\(KEY_SHORTCUTS,\s*SNAP_HELP\)/);
  });
});

describe("the contract degrades honestly", () => {
  it("omits the Draw tools section entirely when the viewer has not loaded", () => {
    // Rather than showing fourteen codes that would do nothing if pressed.
    const titles = keyContract([]).map((s) => s.title);
    expect(titles).toEqual(["Anywhere", "In the 3D view"]);
  });

  it("omits the snap codes too — they need an armed draw tool, which needs the viewer", () => {
    expect(keyContract(KEY_SHORTCUTS, []).map((s) => s.title)).not.toContain("Snap for one pick");
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

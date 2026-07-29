import { existsSync, readdirSync } from "node:fs";
import { resolve } from "node:path";

import { describe, expect, it } from "vitest";

import { EMPTY_GUIDES, emptyGuideFor, emptyHint } from "./emptyGuide";

/**
 * R24-EMPTY-GUIDE ②.
 *
 * The guidance is hand-written prose about where a register's rows come from, keyed by module. Two
 * ways that goes wrong, and both are asserted here:
 *
 * 1. **A key that names no module.** Then the guidance is dead code that looks maintained. This is
 *    not hypothetical — the first draft of the table used `change_order` and `pay_app`, and neither
 *    exists (`change_event`, `owner_invoice`). The check caught two errors before it was committed.
 * 2. **Guidance that says nothing.** "Create your first record" restates the button. The value is
 *    entirely in naming the *upstream*, so the shape is asserted rather than left to review.
 */

const MODULES_DIR = resolve(__dirname, "../../../../services/api/modules");

function moduleKeys(): Set<string> {
  return new Set(readdirSync(MODULES_DIR, { withFileTypes: true })
    .filter((d) => d.isDirectory() && existsSync(resolve(MODULES_DIR, d.name, "module.json")))
    .map((d) => d.name));
}

describe("the module catalog is readable from disk", () => {
  it("finds a plausible number of modules", () => {
    // Guards the reader: if the layout changes this fails here rather than making every assertion
    // below vacuously pass against an empty set.
    const keys = moduleKeys();
    expect(keys.size).toBeGreaterThan(100);
    expect(keys.has("rfi")).toBe(true);
  });
});

describe("every guide points at a module that exists", () => {
  it("no key in EMPTY_GUIDES is orphaned", () => {
    const keys = moduleKeys();
    const orphans = Object.keys(EMPTY_GUIDES).filter((k) => !keys.has(k));
    expect(orphans, orphans.length
      ? `EMPTY_GUIDES names modules that do not exist under services/api/modules/: ${orphans.join(", ")}. `
        + "If a module was renamed there, rename it in apps/web/src/ui/emptyGuide.ts too — guidance "
        + "pointing at a removed register is dead copy that still looks maintained."
      : "").toEqual([]);
  });
});

describe("guidance says where rows come from, not how to click New", () => {
  it("every entry names an upstream rather than restating the button", () => {
    for (const [key, g] of Object.entries(EMPTY_GUIDES)) {
      expect(g.what.length, `${key}.what is too short to be a reason`).toBeGreaterThan(25);
      expect(g.from.length, `${key}.from is too short to be a next step`).toBeGreaterThan(20);
      // The whole point of the item: the hint must not be the button in different words.
      expect(g.from.toLowerCase(), `${key}.from just restates "+ New"`).not.toContain("+ new");
    }
  });

  it("the audit's own example reads the way the audit asked for", () => {
    const rfi = emptyGuideFor("rfi")!;
    expect(rfi.what).toMatch(/against a drawing|spec/i);
    expect(rfi.from).toMatch(/drawing|model/i);
  });
});

describe("an uncurated module is not given an invented workflow", () => {
  it("returns null rather than guessing", () => {
    // 133 modules, ~24 curated. The rest keep the generic line on purpose: a plausible-sounding
    // invented upstream is a confident wrong answer in a place the user cannot check it.
    expect(emptyGuideFor("no_such_module")).toBeNull();
  });

  it("falls back to the previous copy, so no module gets worse", () => {
    expect(emptyHint("no_such_module")).toBe("Use “+ New” to create the first one.");
    expect(emptyHint("rfi")).not.toBe("Use “+ New” to create the first one.");
  });

  it("is curated for a minority of modules, and that is the intended ratio", () => {
    const curated = Object.keys(EMPTY_GUIDES).length;
    expect(curated).toBeGreaterThan(15);
    expect(curated).toBeLessThan(moduleKeys().size / 2);
  });
});

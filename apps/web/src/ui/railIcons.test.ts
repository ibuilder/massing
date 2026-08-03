/**
 * RAIL-ICON-UNIFY — **one icon set, and no rail item without a glyph.**
 *
 * Two failures put this file here, and they are the same failure at two scales.
 *
 * The small one shipped and was visible: the rail rendered `undefinedView` and `undefinedBuild`. The
 * old map interpolated `RAIL_ICONS[key]` straight into `innerHTML`, so a rail item with no icon did
 * not fall back — it printed the literal string `undefined` welded to its label. The user saw
 * "jumbled words", which is exactly right and exactly not what it looked like from the code.
 *
 * The large one never errored at all: the rail was drawing hand-made 16×16 glyphs while `ui/icons.ts`
 * held a vendored Lucide set at 24×24, so the app ran **two icon languages** — and seven of the
 * hand-made ones were at two different stroke weights. Consistency has no error state. Nothing can
 * throw, nothing can 404; a set simply stops reading as a set, and only a person looking at it
 * notices. So it is asserted here instead.
 *
 * Both are now structural: every rail key names an icon that must EXIST in the vendored set, and the
 * name map may not contain artwork. That second one matters more than it looks — the easy way to
 * "fix" a missing icon under deadline is to paste an SVG into the map, which silently restores the
 * two-language problem this file exists to end.
 */
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, resolve } from "node:path";
import { describe, expect, it } from "vitest";

import { ICONS, hasIcon, icon } from "./icons";

const HERE = dirname(fileURLToPath(import.meta.url));
const read = (rel: string) => readFileSync(resolve(HERE, rel), "utf8");

/** The rail's key → icon-name map, parsed from source. */
function railIconNames(): Record<string, string> {
  const src = read("../main.ts");
  const block = src.split("const RAIL_ICON_NAME: Record<string, string> = {")[1]?.split("\n};")[0] ?? "";
  const out: Record<string, string> = {};
  for (const m of block.matchAll(/^\s*(\w+):\s*"([a-z0-9-]+)"/gm)) out[m[1]!] = m[2]!;
  return out;
}

/** Every key the rail actually renders a button for. */
function railKeys(): string[] {
  const src = read("../main.ts");
  const block = src.split("const RAIL_ITEMS")[1]?.split("\n];")[0] ?? "";
  return [...block.matchAll(/key:\s*"(\w+)"/g)].map((m) => m[1]!);
}

describe("the rail draws from the vendored set", () => {
  it("the parsers found real data — a regex that matches nothing passes everything", () => {
    expect(Object.keys(railIconNames()).length, "parsed no entries from RAIL_ICON_NAME")
      .toBeGreaterThan(8);
    expect(railKeys().length, "parsed no items from RAIL_ITEMS").toBeGreaterThan(8);
    expect(Object.keys(ICONS).length, "the vendored set came back empty").toBeGreaterThan(20);
  });

  it("EVERY rail item has an icon — the `undefinedView` defect cannot come back", () => {
    const named = railIconNames();
    const missing = railKeys().filter((k) => !named[k]);
    expect(missing, "rail items with no icon — these rendered the literal word 'undefined'")
      .toEqual([]);
  });

  it("every name resolves in the vendored set — a typo is a blank square, not an error", () => {
    const bad = Object.entries(railIconNames())
      .filter(([, name]) => !hasIcon(name))
      .map(([key, name]) => `${key} → "${name}"`);
    expect(bad, "named icons that are not vendored").toEqual([]);
  });

  it("the map holds NAMES, never artwork — the second icon language stays gone", () => {
    // The regression that would undo this file. Pasting an SVG here instead of vendoring it is the
    // path of least resistance, and it reintroduces exactly the mixed-grid, mixed-weight rail the
    // migration removed.
    const src = read("../main.ts");
    const block = src.split("const RAIL_ICON_NAME")[1]?.split("\n};")[0] ?? "";
    expect(/<svg|<path|<rect|<circle/.test(block), "inline SVG in the rail icon map").toBe(false);
  });

  it("the rendered icons carry no colour of their own", () => {
    // What makes the colour contract hold automatically: an icon that inherits `currentColor` cannot
    // introduce a second meaning for blue. Checked on the rendered element, not the source string.
    for (const [key, name] of Object.entries(railIconNames())) {
      const el = icon(name, 16)!;
      expect(el, `icon(${name}) returned null for rail item ${key}`).not.toBeNull();
      expect(el.getAttribute("stroke"), `${name} must inherit its colour`).toBe("currentColor");
      expect(el.getAttribute("fill"), `${name} must not be filled`).toBe("none");
      expect(el.getAttribute("viewBox"), `${name} must stay on the vendored 24×24 grid`)
        .toBe("0 0 24 24");
    }
  });

  it("no vendored path overrides the set's stroke weight", () => {
    // **This assertion was rewritten because the first version could not fail.** It read
    // `icon(n).getAttribute("stroke-width")` across every icon and asserted one distinct value — but
    // `icon()` stamps that attribute on the wrapper itself, identically, every time. It was reading
    // back its own constant, so the "one weight" it proved was a tautology: mutating the source did
    // not turn it red. The lesson this repo keeps relearning is that a check whose failure mode is
    // unreachable reads exactly like a check that passes.
    //
    // The set can only carry two weights one way: a path INSIDE a vendored body declaring its own
    // `stroke-width`, which wins over the inherited wrapper value. That is the breakable property, so
    // that is what is asserted. It also catches a paste from a non-Lucide source, since Lucide's own
    // path data never carries per-path stroke attributes.
    const offenders = Object.entries(ICONS)
      .filter(([, body]) => /stroke-width|stroke=/.test(body))
      .map(([name]) => name);
    expect(offenders, "vendored icons whose paths carry their own stroke").toEqual([]);
    // and the wrapper does supply one, so the paths have something to inherit
    expect(icon("box", 16)!.getAttribute("stroke-width")).toBeTruthy();
  });
});

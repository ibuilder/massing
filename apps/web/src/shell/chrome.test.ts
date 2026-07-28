import { describe, expect, it } from "vitest";

/**
 * The three chrome defects from the 2026-07-28 screenshot.
 *
 * All three were visible in one frame and none needed a server to reproduce, which is the useful
 * thing about them: they had survived every gate because no gate looked at the screen. These tests
 * are source-level assertions — the honest limit of what a unit test can hold about CSS and event
 * wiring — so each one names the *symptom* it prevents rather than restating the rule.
 */

// STATIC `?raw` specifiers. A templated one (`${path}?raw`) is invisible to Vite's analyser and
// resolves to an empty module — which made every assertion below pass-by-emptiness on the first
// draft, the exact vacuous-test shape this repo keeps finding.
import { readFileSync } from "node:fs";
import { resolve } from "node:path";

import menusSrc from "../ui/menus.ts?raw";
import toolbarSrc from "../viewer/toolbarView.ts?raw";
import worldSrc from "../viewer/world.ts?raw";

// vitest stubs CSS imports, so `../style.css?raw` resolves to an empty string and every assertion
// against it passes vacuously. Read it off disk instead — the test runs in Node, and the stylesheet
// is a build input like any other file.
// Resolved from the vitest root (apps/web), NOT from `import.meta.url`. That worked when this file
// ran alone and threw "The URL must be of scheme file" in the full suite, because Vite rewrites
// module URLs differently under a batch run — a test that passes in isolation and fails in company
// is worse than one that just fails.
const cssSrc = readFileSync(resolve(process.cwd(), "src/style.css"), "utf8");

/**
 * CSS with comments removed.
 *
 * Three times today a source-level assertion has matched the *comment explaining the fix* rather
 * than the code: a Python docstring naming `os.path.join`, a TS comment naming a `.frag` path, and
 * this file's own note quoting `overflow: auto`. Rewording the prose each time treats the symptom.
 * A test that reads code should be given code.
 */
function code(css: string): string {
  return css.replace(/\/\*[\s\S]*?\*\//g, "");
}

function loaded(src: string, what: string): string {
  expect(typeof src, `${what} did not load — the assertions below would be vacuous`).toBe("string");
  expect(src.length, what).toBeGreaterThan(200);
  return src;
}

describe("the More menu is a menu, not an overflow bin", () => {
  it("never scrolls sideways", () => {
    const css = loaded(cssSrc, "style.css");
    const c = code(css);
    const block = c.slice(c.indexOf(".vt-menu {"), c.indexOf(".vt-menu[hidden]"));
    // `overflow: auto` permits BOTH axes — that is what produced the horizontal scrollbar.
    expect(block, "vt-menu must not allow horizontal scrolling").not.toMatch(/overflow:\s*auto/);
    expect(block).toMatch(/overflow-x:\s*hidden/);
    expect(block).toMatch(/overflow-y:\s*auto/);
  });

  it("lets a row wrap, so the hint takes its own line", () => {
    const css = loaded(cssSrc, "style.css");
    const c = code(css);
    const row = c.slice(c.indexOf("#viewer-tools .vt-row {"), c.indexOf("#viewer-tools .vt-row:hover"));
    // `.vt-note` asks for `flex: 1 0 100%`. Without wrap that request is silently ignored and the
    // hint runs off the right edge, truncated mid-sentence.
    expect(row, "without flex-wrap the note cannot take its own line").toMatch(/flex-wrap:\s*wrap/);
  });

  it("breaks a long unbroken token instead of widening the panel", () => {
    const css = loaded(cssSrc, "style.css");
    const note = code(css).slice(code(css).indexOf(".vt-note {"));
    expect(note.slice(0, 220)).toMatch(/overflow-wrap:\s*anywhere/);
  });
});

describe("only one popup is open at a time", () => {
  it("there is a single shared close channel", () => {
    const menus = loaded(menusSrc, "menus.ts");
    // Two popup systems that cannot see each other will always allow two open at once. The fix is a
    // channel, not another selector bolted onto another querySelectorAll.
    expect(menus).toMatch(/export const CLOSE_POPUPS/);
    expect(menus, "closeMenus must announce, not just sweep .menu-panel").toMatch(/dispatchEvent/);
  });

  it("the viewer's More menu both announces and listens", () => {
    const tv = loaded(toolbarSrc, "toolbarView.ts");
    expect(tv, "opening must dismiss the others").toMatch(/closeMenus\(menu\)/);
    expect(tv, "another popup opening must dismiss this one").toMatch(/addEventListener\(CLOSE_POPUPS/);
  });

  it("the opener respects `keep`, or a menu would close itself on open", () => {
    const tv = loaded(toolbarSrc, "toolbarView.ts");
    expect(tv).toMatch(/detail\?\.keep !== menu/);
  });
});

describe("the viewport carries our branding, and the credit is paid elsewhere", () => {
  it("the third-party logo is off", () => {
    const world = loaded(worldSrc, "world.ts");
    expect(world).toMatch(/showLogo\s*=\s*false/);
  });

  it("...and the reason is recorded next to it, not left as a bare flag", async () => {
    // A silent `showLogo = false` reads as someone hiding an attribution. The comment is the
    // difference between a decision and a sleight of hand.
    const world = loaded(worldSrc, "world.ts");
    // The ASSIGNMENT, not the first mention — the first `showLogo` in this file is inside the
    // comment explaining it, so searching before that lands 900 characters of unrelated MSAA code.
    const i = world.indexOf("showLogo = false");
    expect(i, "no showLogo assignment found").toBeGreaterThan(-1);
    const context = world.slice(Math.max(0, i - 900), i);
    expect(context, "the trade-off must be stated where the flag is set").toMatch(/white-label|customer-branded/i);
    expect(context).toMatch(/credits\.md/);
  });
});

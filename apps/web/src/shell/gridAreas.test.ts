import { readFileSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, it } from "vitest";
import { areaUses, definedAreas, namedLineUsages, scanDeclarations, stripComments, verdict } from "./gridAreas";

/**
 * UX-4 SHELL-GRID. `#pinned-rail` asked for `grid-area: pins` and no `grid-template-areas` in the
 * tree ever defined a `pins` area, so from v0.3.764 (2026-07-28) the rail was auto-placed into
 * implicit tracks instead of beside the stage. Measured in Chromium at 1440x900, rail populated:
 * the rail landed at x=1368 y=774 (the bottom-RIGHT corner, while its own CSS gives it a
 * `border-right` and 72px of width — a LEFT rail), `#stage` shrank to 1368x698, and `#statusbar`
 * detached from the bottom of the window to y=742.
 *
 * **Nothing went red, and nothing could have**, which is the reason this exists rather than a
 * one-line CSS fix. The rail is `hidden` until the user has a favourite or a recent, so a first run
 * looks perfect; every run after it is wrong. There is no console error, no failing assertion, and
 * no rendered test in this suite — jsdom performs no layout, so a DOM test would have passed too.
 * What was checkable all along is the property that actually failed: a name used and never defined.
 *
 * Both directions are pinned, because a rule that only ever refuses is indistinguishable from one
 * that always refuses: an area used but undefined fails, and an area defined but claimed by nothing
 * fails as well. The second half is what would catch the reverse edit — renaming the element's
 * `grid-area` and leaving the template behind.
 */
const WEB = process.cwd();
const CSS = readFileSync(join(WEB, "src", "style.css"), "utf8");
const ALL_CSS = ["src/style.css", "src/field/fieldMode.css", "src/vendor/massingpdf/styles.css"];

describe("every grid-area names an area some grid-template-areas defines", () => {
  it("the live stylesheet has no orphaned area", () => {
    expect(verdict(CSS).orphans).toEqual([]);
  });

  it("and no area defined that nothing claims", () => {
    expect(verdict(CSS).unused).toEqual([]);
  });

  it("classifies every grid-area it finds — an UNKNOWN value means the answer is not trustworthy", () => {
    // Fail-closed. A parser that quietly drops what it cannot read is a check that can only report
    // good news, which is precisely the failure mode this gate exists to end.
    expect(verdict(CSS).unknown).toEqual([]);
  });

  it("covers every stylesheet in the tree, not just the shell's", () => {
    for (const rel of ALL_CSS) {
      const v = verdict(readFileSync(join(WEB, rel), "utf8"));
      expect({ file: rel, orphans: v.orphans, unused: v.unused, unknown: v.unknown })
        .toEqual({ file: rel, orphans: [], unused: [], unknown: [] });
    }
  });
});

describe("the analyser finds the defect it was written for", () => {
  // Mutate the LIVE file back to its pre-fix shape rather than asserting against a hand-made
  // fixture. A fixture proves the analyser can read a stylesheet somebody wrote for it; this proves
  // it reaches the real one. `test_seeding_sweep` shipped blind twice for want of exactly this.
  const PRE_FIX = CSS.replace(
    /grid-template-areas:\s*"topbar\s+topbar"\s*"pins\s+stage"\s*"statusbar\s+statusbar";/,
    'grid-template-areas: "topbar" "stage" "statusbar";',
  );

  it("the mutation actually applied — otherwise the check below is vacuous", () => {
    // Without this, a template reformatted past the regex turns the self-test green by doing
    // nothing at all, and the gate goes on reporting a clean tree it never examined.
    expect(PRE_FIX).not.toBe(CSS);
    expect(definedAreas(PRE_FIX).has("pins")).toBe(false);
  });

  it("reports `pins` as an orphan on the pre-fix stylesheet", () => {
    expect(verdict(PRE_FIX).orphans.map((o) => o.name)).toEqual(["pins"]);
  });

  it("still reads the other three areas as fine — it does not simply refuse everything", () => {
    expect(verdict(PRE_FIX).unused).toEqual([]);
    expect(verdict(PRE_FIX).unknown).toEqual([]);
  });
});

describe("the reader", () => {
  it("ignores line-based placement, which references no area name", () => {
    const css = "a { grid-area: 1 / 2 / 3 / 4; } b { grid-area: span 2 / auto; }";
    expect(areaUses(css)).toEqual({ uses: [], unknown: [] });
  });

  it("ignores the CSS-wide keywords", () => {
    expect(areaUses("a { grid-area: auto; } b { grid-area: inherit; }").uses).toEqual([]);
  });

  it("does not count a COMMENTED-OUT template as a definition", () => {
    // The fail-open direction: a commented example would define an area no browser has ever seen,
    // silencing the check on exactly the edit most likely to introduce the bug.
    const css = `/* grid-template-areas: "ghost"; */ #x { grid-area: ghost; }`;
    expect(definedAreas(css).size).toBe(0);
    expect(verdict(css).orphans.map((o) => o.name)).toEqual(["ghost"]);
  });

  it("keeps line numbers true across stripped comments", () => {
    const css = `/* one\n   two */\n#x { grid-area: ghost; }`;
    expect(stripComments(css).split("\n").length).toBe(3);
    expect(verdict(css).orphans[0]?.line).toBe(3);
  });

  it("treats a `.` cell as a hole, not as an area named `.`", () => {
    expect([...definedAreas(`x { grid-template-areas: "a ." ". b"; }`)].sort()).toEqual(["a", "b"]);
  });

  it("does not mistake a longhand like `grid-template-areas` for the `grid-area` shorthand", () => {
    expect(areaUses(`x { grid-template-areas: "a"; }`).uses).toEqual([]);
  });
});

describe("it reads CSS, not text that happens to contain CSS", () => {
  // Three regressions from review. Each was reproduced against the old regex parser BEFORE being
  // believed, and the first is the one that mattered: it was FAIL-OPEN, in the gate whose whole
  // purpose is to catch fail-open checks.

  it("a CUSTOM PROPERTY defines no area — `--grid-template-areas` is not `grid-template-areas`", () => {
    // The old parser matched the property name by substring, so this DEFINED a phantom `pins` area
    // and the orphan below went unreported. A check silenced by a declaration that changes nothing
    // in the browser is the worst shape available.
    const css = `:root { --grid-template-areas: "pins"; }  #x { grid-area: pins; }`;
    expect([...definedAreas(css)]).toEqual([]);
    expect(verdict(css).orphans.map((o) => o.name)).toEqual(["pins"]);
  });

  it("declaration text inside a STRING is not a declaration", () => {
    // Fails closed rather than open — a false orphan is noise, not silence — but a gate that cries
    // wolf gets switched off, which ends in the same place.
    const css = `#x { content: "grid-area: ghost;"; }`;
    expect(areaUses(css).uses).toEqual([]);
    expect(verdict(css).orphans).toEqual([]);
  });

  it("comment markers inside a STRING do not eat the declarations after them", () => {
    // `content: "/*"` anywhere above would otherwise blank every declaration until a `"*/"`.
    const css = `#a { content: "/*"; } #b { grid-template-areas: "real"; } `
      + `#c { content: "*/"; } #d { grid-area: real; }`;
    expect([...definedAreas(css)]).toEqual(["real"]);
    expect(verdict(css).orphans).toEqual([]);
  });

  it("ignores the colon in an at-rule prelude and in a selector", () => {
    // `@media (max-width: 900px)` and `a:hover` both contain a colon at a point where the text
    // before it is not a bare identifier inside a block. style.css is full of both.
    const css = `@media (max-width: 900px) { .x:hover { grid-area: pins; } } `
      + `y { grid-template-areas: "pins"; }`;
    expect(verdict(css).orphans).toEqual([]);
    expect(verdict(css).unused).toEqual([]);
  });

  it("a comment marker inside a SELECTOR's string does not swallow the rest of the file", () => {
    // Added because a mutation that removed string tracking from the scanner's main loop — the one
    // that runs OUTSIDE a declaration value — survived every other test here. All three regressions
    // above put their string in a VALUE, which a different code path handles, so the prelude branch
    // was never exercised and its removal looked harmless.
    //
    // Here it is not: without it the `/*` inside the attribute selector opens a comment that never
    // closes, and every declaration in the rest of the stylesheet is silently discarded.
    const css = `[title="/*"] { grid-template-areas: "pins"; } #x { grid-area: pins; }`;
    expect([...definedAreas(css)]).toEqual(["pins"]);
    expect(verdict(css).orphans).toEqual([]);
  });

  it("a `;` inside a string does not end the declaration early", () => {
    expect(scanDeclarations(`#x { content: "a;b"; grid-area: pins; }`).map((d) => d.prop))
      .toEqual(["content", "grid-area"]);
  });
});

describe("the scope claim in gridAreas.ts stays true", () => {
  it("no stylesheet references a NAMED grid line — the axis this gate does not cover is empty", () => {
    // The docstring says named lines are out of scope *because this tree uses none*. That is a
    // measurement, and a measurement written in prose drifts. If one ever appears, this fails and
    // the scope has to be widened or the exemption argued — it cannot lapse quietly.
    for (const rel of ALL_CSS) {
      expect({ file: rel, named: namedLineUsages(readFileSync(join(WEB, rel), "utf8")) })
        .toEqual({ file: rel, named: [] });
    }
  });
});

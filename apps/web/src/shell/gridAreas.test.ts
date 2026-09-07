import { readFileSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, it } from "vitest";
import { areaUses, definedAreas, namedLineUsages, stripComments, verdict } from "./gridAreas";

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

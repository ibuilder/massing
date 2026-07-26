import { readFileSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, it } from "vitest";
import { ACCENT_ALLOWED, accentSelectors } from "./colorContract";

/**
 * R26-COLOUR-DISCIPLINE. The audit found the primary blue marking eight unrelated things at once,
 * including every KPI number — at which point it marks nothing, and a dashboard has no emphasis left
 * for the figure that actually needs it.
 *
 * The rule is only worth stating if something enforces it, so this asserts the stylesheet against the
 * reviewed list **in both directions**. A new accent-coloured selector fails; a stale allowance fails
 * too. Both failures are the same instruction: decide whether this thing is something the user can
 * act on, and if it is not, use `--text`.
 */
const CSS = readFileSync(join(process.cwd(), "src", "style.css"), "utf8");

describe("blue means one thing: you can act on it", () => {
  const found = accentSelectors(CSS);

  it("colours nothing with the accent that has not been reviewed", () => {
    expect(found.filter((s) => !ACCENT_ALLOWED.includes(s))).toEqual([]);
  });

  it("keeps no stale allowances — a rule nobody uses stops describing the stylesheet", () => {
    expect(ACCENT_ALLOWED.filter((s) => !found.includes(s))).toEqual([]);
  });

  it("does NOT paint plain KPI numbers — that was the loudest misuse", () => {
    // A number you cannot click is not a control. `.kpi-v` is now plain text; only `.kpi-click .kpi-v`
    // stays blue, which makes the colour true rather than decorative: it means this figure goes
    // somewhere. Both halves matter — dropping the blue everywhere would lose the affordance, and
    // keeping it everywhere is what made a dashboard unreadable.
    expect(found).not.toContain(".kpi-v");
    expect(found).toContain(".kpi-click .kpi-v");
  });

  it("does not paint section headings — a label is not a control", () => {
    expect(found).not.toContain(".portal-fieldset-head");
    expect(found).not.toContain(".ball-badge");
  });
});

describe("the extractor looks at paint, not at interaction cues", () => {
  it("ignores borders, outlines and shadows — there the colour is doing its job", () => {
    expect(accentSelectors(".a { border: 1px solid var(--accent); }")).toEqual([]);
    expect(accentSelectors(".b:focus { outline: 2px solid var(--accent); }")).toEqual([]);
    expect(accentSelectors(".c { box-shadow: 0 0 4px var(--accent); }")).toEqual([]);
    expect(accentSelectors(".d { border-color: var(--accent); }")).toEqual([]);
  });

  it("catches text and background in every spelling", () => {
    expect(accentSelectors(".a { color: var(--accent); }")).toEqual([".a"]);
    expect(accentSelectors(".b { background: var(--accent); }")).toEqual([".b"]);
    expect(accentSelectors(".c { background-color: var(--accent); }")).toEqual([".c"]);
    expect(accentSelectors(".d { background: linear-gradient(var(--accent), #000); }")).toEqual([".d"]);
    expect(accentSelectors(".e { fill: var(--accent); }")).toEqual([".e"]);
  });

  it("does not mistake a commented-out rule for a live one", () => {
    expect(accentSelectors("/* .old { color: var(--accent); } */ .new { color: var(--text); }")).toEqual([]);
  });

  it("skips the token definitions themselves — :root DECLARES the colour, it does not spend it", () => {
    expect(accentSelectors(":root { --accent: #4a8cff; --x: var(--accent); }")).toEqual([]);
  });

  it("reports a selector once however many accent declarations it carries", () => {
    expect(accentSelectors(".a { color: var(--accent); background: var(--accent); }")).toEqual([".a"]);
  });
});

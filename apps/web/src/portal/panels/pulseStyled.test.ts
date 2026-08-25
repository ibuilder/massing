import { readFileSync } from "node:fs";
import { resolve } from "node:path";

import { describe, expect, it } from "vitest";

import { type PulseCard, pulseCardEl, pulseRailEl } from "./pulse";

/**
 * Every class the Pulse rail emits has a rule, and the three tones are visually DIFFERENT.
 *
 * ## The defect
 *
 * `pulse.ts` shipped in v0.3.749 and no stylesheet has ever contained the string `pulse`. The rail
 * rendered as bare HTML for ~330 releases: no card, no rule, no colour. `pulse.test.ts` was thorough
 * and green throughout, because it tests what `buildPulse` *computes* — and the computation was
 * always right.
 *
 * The part that mattered is the tone. `pulseCardEl` writes `pulse-card pulse-tone-${tone}`, where
 * tone is `good | watch | risk`, derived across five domains: a blocking model issue, cost variance,
 * negative float, overdue work, a failing reserve. **With no rule for those classes a risk card was
 * pixel-identical to a healthy one** — which is the entire thing an at-a-glance rail is for. The app
 * computed the distinction correctly and then threw it away at the last step.
 *
 * ## Why assert the stylesheet and not a screenshot
 *
 * happy-dom does not load `style.css`, so `getComputedStyle` here would report the same nothing for
 * every card and this file would agree with the bug. So it reads the stylesheet as text and asserts
 * against the classes the component actually emits — the two are joined by construction rather than
 * by someone remembering to update a list.
 *
 * The general rule, which is why this exists rather than a one-line CSS fix: **a class that encodes a
 * state distinction is a promise that the state is visible.** If nothing styles it, the distinction
 * is computed, tested, and invisible.
 */

const CSS = readFileSync(resolve(process.cwd(), "src/style.css"), "utf8");

const TONES: PulseCard["tone"][] = ["good", "watch", "risk"];

function card(tone: PulseCard["tone"]): PulseCard {
  return { key: "model", label: "Model", value: "90", tone, headline: "healthy", risk: "something" };
}

/** Every class the component puts in the DOM, gathered from the real elements it builds. */
function emittedClasses(): string[] {
  const out = new Set<string>();
  const rail = pulseRailEl(TONES.map(card));
  expect(rail, "the rail returned null for three cards — the fixture is wrong, not the CSS").not.toBeNull();
  const walk = (el: Element) => {
    for (const c of el.classList) out.add(c);
    for (const kid of el.children) walk(kid);
  };
  walk(rail!);
  return [...out];
}

describe("the Pulse rail is actually styled", () => {
  it("emits a plausible number of classes — else every check below is vacuous", () => {
    expect(emittedClasses().length).toBeGreaterThanOrEqual(8);
  });

  it("EVERY class it emits has a rule in the stylesheet", () => {
    const unstyled = emittedClasses().filter((c) => !CSS.includes(`.${c}`));
    expect(unstyled,
      "these classes are written into the DOM and nothing paints them. That is how this component "
      + "shipped for ~330 releases: the markup was right, the logic was right, and the user saw "
      + "unstyled HTML.").toEqual([]);
  });

  it("THE THREE TONES ARE VISUALLY DIFFERENT — the distinction the rail exists to show", () => {
    // Not just "each has a rule": all three could share one, which would be the same bug with extra
    // steps. Each tone must resolve to a DIFFERENT status token.
    const tokenFor = (tone: string): string | null => {
      const rule = new RegExp(String.raw`\.pulse-tone-${tone}\s*\{[^}]*\}`).exec(CSS)?.[0] ?? "";
      return /var\((--status-[a-z]+)\)/.exec(rule)?.[1] ?? null;
    };
    const tokens = TONES.map(tokenFor);
    expect(tokens.every(Boolean), `a tone resolves to no status token: ${JSON.stringify(tokens)}`).toBe(true);
    expect(new Set(tokens).size,
      `all three tones must differ, got ${JSON.stringify(tokens)} — a risk card that looks like a `
      + "healthy one is the defect this file was written from").toBe(3);
  });

  it("uses STATUS tokens, never --accent, per R26-COLOUR-DISCIPLINE", () => {
    const block = /\/\* PROJECT PULSE[\s\S]*?(?=\/\* R41-SCHEMA-STALE)/.exec(CSS)?.[0] ?? "";
    expect(block.length, "the Pulse block is gone from style.css").toBeGreaterThan(200);
    expect(block.includes("var(--accent)"),
      "accent means 'you can act on this'; a pulse card says 'this is how it is'. Colouring it accent "
      + "would also need an ACCENT_ALLOWED entry, and it would not fit that list's sentence.").toBe(false);
  });

  /**
   * The tone class must not collide with any other class the component emits. `pulse-${tone}` used to
   * produce `pulse-risk` for the risk tone — which was ALSO the class on the risk sentence inside the
   * card, so one selector matched both a card and a paragraph within it. Nothing depended on the
   * ambiguity only because nothing was styled; the moment a rule existed it would have painted both.
   */
  it("the tone class collides with nothing else the card emits", () => {
    const el = pulseCardEl(card("risk"));
    const own = [...el.classList];
    const inner = [...el.querySelectorAll("*")].flatMap((k) => [...k.classList]);
    expect(own.filter((c) => inner.includes(c)),
      "a class on both the card and something inside it means one rule paints two things").toEqual([]);
  });
});

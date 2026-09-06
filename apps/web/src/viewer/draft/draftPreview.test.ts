import { describe, expect, it } from "vitest";

import {
  contentToDraftElement, DRAFT_ELEMENTS, familyToDraftElement,
  type DraftElement, type ParamValues,
} from "./draftCatalog";
import { bandFor, noPreviewReason, NO_PREVIEW, previewElement, previewFor } from "./draftPreview";

/**
 * UX-3 — does the preview actually depend on what you typed?
 *
 * THE FAILURE THIS IS SHAPED AROUND, AND IT IS NOT COVERAGE
 *     The glyph test next door guards a coverage question: is there an entry for every class. This
 *     file guards a harder one. A preview that renders a plausible rectangle for every input is
 *     indistinguishable, in a passing test, from one that reads the form — and it is worthless,
 *     because its entire purpose is to make a mistyped 8.0 where 0.8 was meant *visible*. So the
 *     assertions below are about CHANGE and about RATIO: draw the same element at two values and
 *     require the drawing to differ, and require the difference to be proportional to the numbers.
 *
 *     `expect(previewFor(el, v)).toBeTruthy()` would pass against a function that ignores `v`
 *     entirely. That is the same hollow shape as catching a bare exception type or asserting "it
 *     ran" — four of those shipped in this repository in one evening and every one was found by
 *     mutation rather than by reading.
 *
 * AND THE BAND MUST NOT MOVE
 *     The mechanism is that the frame is fixed from the element's DEFAULTS while the shape scales
 *     inside it. If the frame rescaled to fit, an 8 m desk and a 0.8 m desk would draw identically
 *     and the feature would be decoration. `bandFor` is therefore asserted to be INDEPENDENT of the
 *     live values — the one property that, if it broke, would leave every other test here passing.
 *
 * POPULATION, DERIVED
 *     Every `DRAFT_ELEMENTS` entry, plus a family and a content item built through the same mappers
 *     the panel uses. Each must either produce a preview or carry a `NO_PREVIEW` reason; a new
 *     element that does neither reds the build rather than quietly rendering nothing.
 */

/** The element's own defaults, which is what the panel shows before anyone types. */
function defaults(el: DraftElement): ParamValues {
  const v: ParamValues = {};
  for (const p of el.params) v[p.key] = p.default;
  return v;
}

/** Total ink: the sum of every coordinate in the path, a cheap proxy for "the drawing changed". */
function inkOf(d: readonly string[]): number {
  return (d.join(" ").match(/-?\d+(\.\d+)?/g) ?? []).reduce((a, b) => a + Math.abs(Number(b)), 0);
}

/**
 * The drawn width and height of a RECT path, in svg units.
 *
 * Parsed from the exact shape `previewFor` emits — `M{x0} {y0}H{x1}V{y1}H{x0}Z` — rather than by
 * taking extremes over every number in the string. The first version did the latter and reported a
 * height ratio of 1 for a wall that had doubled, because the rect is narrow and centred so the
 * smallest number in the path was an X coordinate. *A helper that is approximately right about
 * geometry produces a test that is confidently wrong about behaviour.*
 */
function rectBox(d: readonly string[]): { w: number; h: number } {
  const m = /M(-?[\d.]+) (-?[\d.]+)H(-?[\d.]+)V(-?[\d.]+)/.exec(d[0] ?? "");
  if (!m) return { w: 0, h: 0 };
  const [x0, y0, x1, y1] = [Number(m[1]), Number(m[2]), Number(m[3]), Number(m[4])];
  return { w: Math.abs(x1 - x0), h: Math.abs(y0 - y1) };
}
const drawnHeight = (d: readonly string[]): number => rectBox(d).h;

const FAMILY = familyToDraftElement({
  key: "desk", label: "Desk", ifc_class: "IfcFurnitureType", category: "Furniture",
  dims: [1.4, 0.7, 0.75],
});
const MEP = DRAFT_ELEMENTS.find((e) => e.key.startsWith("mep:")) as DraftElement;
const COVERING = DRAFT_ELEMENTS.find((e) => e.key.startsWith("cov:")) as DraftElement;
const CONTENT = contentToDraftElement(
  { key: "desk", ifc_class: "IfcFurniture", phase: null, classification: "Pr_40", default_dims_m: [1.4, 0.7, 0.75] },
  "FF&E",
);

describe("draftPreview — every element previews or says why not", () => {
  it("each built-in element either draws or carries a stated NO_PREVIEW reason", () => {
    const unexplained: string[] = [];
    for (const el of DRAFT_ELEMENTS) {
      const drew = previewFor(el, defaults(el)) !== null;
      const excused = noPreviewReason(el) !== "";
      if (drew === excused) unexplained.push(`${el.key} (drew=${drew} excused=${excused})`);
    }
    expect(unexplained).toEqual([]);
  });

  it("a family from the server catalog draws, because its dims ARE the form values", () => {
    const p = previewFor(FAMILY, defaults(FAMILY));
    expect(p).not.toBeNull();
    expect(p?.caption).toContain("1.4");
  });

  it("an MEP terminal does not draw: it has no params, so nothing in the form can be wrong", () => {
    expect(MEP.params).toEqual([]);
    expect(previewFor(MEP, {})).toBeNull();
    expect(noPreviewReason(MEP)).toContain("add_mep_terminal");
  });

  it("a covering DOES draw — it has a thickness, which is exactly the value people mistype", () => {
    expect(previewFor(COVERING, { thickness: 0.02 })?.caption).toContain("0.02");
    expect(previewFor(COVERING, { thickness: 0.2 })?.caption).toContain("0.2");
  });

  it("a content item does not draw, and the reason names why rather than leaving a blank", () => {
    expect(previewFor(CONTENT, {})).toBeNull();
    expect(noPreviewReason(CONTENT)).toContain("place_content");
  });

  it("every NO_PREVIEW entry is a sentence, not a marker", () => {
    for (const [key, reason] of Object.entries(NO_PREVIEW)) {
      expect(reason.length, `${key} needs a reason someone can disagree with`).toBeGreaterThan(60);
    }
  });
});

describe("draftPreview — the drawing follows the values", () => {
  const wall = DRAFT_ELEMENTS.find((e) => e.key === "wall");

  it("a taller wall draws taller, and IN PROPORTION", () => {
    expect(wall).toBeDefined();
    if (!wall) return;
    const low = previewFor(wall, { height: 1, thickness: 0.2 });
    const high = previewFor(wall, { height: 2, thickness: 0.2 });
    expect(low).not.toBeNull();
    expect(high).not.toBeNull();
    if (!low || !high) return;
    // Doubling the metres doubles the drawn height. A preview that merely CHANGED could still be
    // arbitrary; the ratio is what says it is reading the number rather than reacting to it.
    expect(drawnHeight(high.d) / drawnHeight(low.d)).toBeCloseTo(2, 1);
  });

  it("the frame does NOT rescale with the value — that is the whole mechanism", () => {
    expect(wall).toBeDefined();
    if (!wall) return;
    const small = previewFor(wall, { height: 0.5, thickness: 0.2 });
    const huge = previewFor(wall, { height: 30, thickness: 0.2 });
    expect(small?.viewMetres).toBe(huge?.viewMetres);
    // ...and if it DID rescale, both would draw the same ink. They must not.
    expect(inkOf(small?.d ?? [])).not.toBeCloseTo(inkOf(huge?.d ?? []), 1);
  });

  it("a wildly wrong value is flagged oversize, and the default is not", () => {
    const p = previewFor(FAMILY, { width: 8, depth: 0.7, height: 0.75 });
    expect(p?.oversize).toBe(true);
    expect(previewFor(FAMILY, defaults(FAMILY))?.oversize).toBe(false);
  });

  /**
   * A shape can miss the frame DOWNWARDS, and the "too big" check could not see it.
   *
   * `extrusion`'s base offset is the only param that reaches a negative number: every other shape is
   * built at y = 0 (or cy = r), and `num()` substitutes the default for a negative — but `z` bypasses
   * `num()` on purpose, because 0 is a legitimate base offset and `num()` would reject it. The old
   * `top = Math.max(...bboxTop, 0.01)` then floored the bound to 0.01 and reported a fit, so a base
   * of -10 m drew the rect entirely below the viewBox while the panel said nothing was wrong.
   *
   * *That is a preview lying about the value it exists to show* — the same fail-open shape as a check
   * that can only report good news, one layer out from the code into the UI.
   */
  const extrusion = DRAFT_ELEMENTS.find((e) => e.key === "extrusion");

  it("a NEGATIVE base offset is flagged, because the shape is drawn off the bottom of the frame", () => {
    expect(extrusion).toBeDefined();
    if (!extrusion) return;
    const below = previewFor(extrusion, { height: 3, z: -10, ifc_class: "IfcWall" });
    expect(below).not.toBeNull();
    expect(below?.belowFrame).toBe(true);
    // ...and NOT as oversize, which would put "larger than this element usually is" under a number
    // that is not large. The two warnings say different things and must not be conflated.
    expect(below?.oversize).toBe(false);
  });

  it("a small negative offset is flagged too — invisible is invisible at any magnitude", () => {
    expect(extrusion).toBeDefined();
    if (!extrusion) return;
    expect(previewFor(extrusion, { height: 3, z: -0.5, ifc_class: "IfcWall" })?.belowFrame).toBe(true);
  });

  it("a legitimate offset of zero or above is not flagged, so the warning stays meaningful", () => {
    expect(extrusion).toBeDefined();
    if (!extrusion) return;
    for (const z of [0, 1, 2.5]) {
      const p = previewFor(extrusion, { height: 3, z, ifc_class: "IfcWall" });
      expect(p?.belowFrame, `z=${z} should sit inside the frame`).toBe(false);
    }
  });

  it("an oversize value is NOT reported as below-frame, and no element's defaults are either", () => {
    const big = previewFor(FAMILY, { width: 8, depth: 0.7, height: 0.75 });
    expect(big?.oversize).toBe(true);
    expect(big?.belowFrame).toBe(false);
    const sunken = DRAFT_ELEMENTS.concat([FAMILY])
      .map((el) => [el.key, previewFor(el, defaults(el))] as const)
      .filter(([, p]) => p?.belowFrame)
      .map(([k]) => k);
    expect(sunken).toEqual([]);
  });

  it("every element's default values sit INSIDE its own frame", () => {
    // The band is derived from the defaults, so this is close to a tautology — which is the point:
    // if it ever fails, the derivation has broken and every preview is framed wrongly at rest.
    const bad = DRAFT_ELEMENTS.concat([FAMILY])
      .map((el) => [el.key, previewFor(el, defaults(el))] as const)
      .filter(([, p]) => p?.oversize)
      .map(([k]) => k);
    expect(bad).toEqual([]);
  });

  it("a select-driven section reads its size from the name, so W24 draws deeper than W8", () => {
    const col = DRAFT_ELEMENTS.find((e) => e.key === "steel_column");
    expect(col).toBeDefined();
    if (!col) return;
    const shallow = previewFor(col, { section: "W8x31", height: 3.6 });
    const deep = previewFor(col, { section: "W24x76", height: 3.6 });
    // The section's DEPTH is the rect's width in this elevation, so that is what must grow. Ink
    // was the first comparison here and it is wrong for the same reason `drawnHeight` was: a deeper
    // section moves coordinates toward zero, which makes the sum SMALLER.
    expect(rectBox(deep?.d ?? []).w).toBeGreaterThan(rectBox(shallow?.d ?? []).w);
    expect(deep?.caption).toContain("609");            // 24 in ≈ 609 mm
  });

  it("a non-numeric or negative entry falls back to the default rather than drawing nothing", () => {
    expect(wall).toBeDefined();
    if (!wall) return;
    // The number input yields "" mid-edit and Number("") is 0; a frame that collapsed to a line
    // while someone was still typing would read as a bug in the model, not in the form.
    const mid = previewFor(wall, { height: 0, thickness: 0.2 });
    expect(mid).not.toBeNull();
    expect(drawnHeight(mid?.d ?? [])).toBeGreaterThan(0);
  });
});

describe("draftPreview — the band is stable and derived", () => {
  it("bandFor ignores live values entirely", () => {
    for (const el of DRAFT_ELEMENTS) {
      if (noPreviewReason(el)) continue;
      const wild: ParamValues = {};
      for (const p of el.params) wild[p.key] = typeof p.default === "number" ? Number(p.default) * 50 : p.default;
      expect(bandFor(el), `${el.key} band moved with its values`).toBe(bandFor(el));
      const withWild = previewFor(el, wild);
      expect(withWild?.viewMetres, `${el.key} frame moved with its values`).toBe(bandFor(el));
    }
  });

  it("a bigger element gets a bigger frame — the band tracks the class, not a constant", () => {
    const wall = DRAFT_ELEMENTS.find((e) => e.key === "wall");
    const pipe = DRAFT_ELEMENTS.find((e) => e.key === "pipe");
    expect(bandFor(wall as DraftElement)).toBeGreaterThan(bandFor(pipe as DraftElement));
  });
});

describe("draftPreview — the svg contributes no text", () => {
  it("previewElement renders no textContent at all", () => {
    const wall = DRAFT_ELEMENTS.find((e) => e.key === "wall");
    expect(wall).toBeDefined();
    if (!wall) return;
    const p = previewFor(wall, defaults(wall));
    expect(p).not.toBeNull();
    if (!p) return;
    const host = document.createElement("div");
    host.appendChild(previewElement(p));
    // The glyph's first draft put the name in an <svg><title>, which counts toward the enclosing
    // row's textContent — every palette row silently read "wallWall IfcWall". The caption lives in
    // a sibling node for exactly this reason, and this asserts the svg stays mute.
    expect(host.textContent).toBe("");
    expect(host.querySelector("svg")?.getAttribute("aria-hidden")).toBe("true");
  });
});

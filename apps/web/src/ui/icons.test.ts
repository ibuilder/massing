import { describe, expect, it } from "vitest";

import { ICONS, hasIcon, icon } from "./icons";

describe("the set is vendored, not fetched", () => {
  it("ships real path data, not placeholders", () => {
    // Copied verbatim from upstream. An icon redrawn from memory is a different icon wearing the
    // same name, so this asserts every entry actually contains drawing instructions.
    expect(Object.keys(ICONS).length).toBeGreaterThanOrEqual(12);
    for (const [name, body] of Object.entries(ICONS)) {
      expect(body, name).toMatch(/<(path|circle|rect|line|polyline|polygon)\b/);
      expect(body.length, name).toBeGreaterThan(20);
    }
  });
  it("contains no network reference of any kind", () => {
    // The viewer must run fully offline. An icon that reaches for a CDN breaks that silently, and
    // only on the machine that has no internet — which is the one that matters.
    for (const [name, body] of Object.entries(ICONS)) {
      expect(body, name).not.toMatch(/https?:|url\(|xlink:href/);
    }
  });
});

describe("an icon carries no colour of its own", () => {
  // This is the load-bearing property, not a detail: it makes the R26 colour contract govern icons
  // automatically, so an icon is structurally incapable of introducing another meaning for blue.
  it("strokes with currentColor and fills nothing", () => {
    const svg = icon("layers")!;
    expect(svg.getAttribute("stroke")).toBe("currentColor");
    expect(svg.getAttribute("fill")).toBe("none");
  });
  it("hard-codes no colour anywhere in the path data", () => {
    for (const [name, body] of Object.entries(ICONS)) {
      expect(body, name).not.toMatch(/#[0-9a-f]{3,8}\b|rgb\(|hsl\(/i);
      // Lucide uses fill="currentColor" for solid dots (e.g. the palette swatches). That still
      // inherits, so it is allowed — a literal colour is not.
      const fills = body.match(/fill="([^"]+)"/g) || [];
      for (const f of fills) expect(f, `${name} ${f}`).toBe('fill="currentColor"');
    }
  });
});

describe("an unknown name returns null rather than a hole", () => {
  it("null, not an empty box", () => {
    // A caller that asked for an icon we do not have should fall back to its own label. A blank
    // square looks like a rendering bug and gets investigated as one.
    expect(icon("no-such-icon")).toBeNull();
    expect(hasIcon("no-such-icon")).toBe(false);
    expect(hasIcon("layers")).toBe(true);
  });
  it("does not fall for inherited object properties", () => {
    expect(hasIcon("toString")).toBe(false);
    expect(icon("constructor")).toBeNull();
  });
});

describe("the element is built for the interface it sits in", () => {
  it("is decorative — the label beside it carries the meaning", () => {
    const svg = icon("sun")!;
    expect(svg.getAttribute("aria-hidden")).toBe("true");
    expect(svg.getAttribute("focusable")).toBe("false");
  });
  it("is one weight at any size", () => {
    // "One monoline set at a single weight" is the whole spec; scaling must not thin the stroke.
    for (const size of [12, 16, 24]) {
      const svg = icon("ruler", size)!;
      expect(svg.getAttribute("stroke-width")).toBe("2");
      expect(svg.getAttribute("width")).toBe(String(size));
      expect(svg.getAttribute("viewBox")).toBe("0 0 24 24");
    }
  });
  it("is a real SVG element in the SVG namespace", () => {
    expect(icon("box")!.namespaceURI).toBe("http://www.w3.org/2000/svg");
    expect(icon("box")!.childElementCount).toBeGreaterThan(0);
  });
});

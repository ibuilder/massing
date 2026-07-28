import { describe, expect, it } from "vitest";
import { safeUrl } from "./feedback";
import { sanitizeSvg } from "./sanitizeSvg";

/** Sheet SVG is generated from the project IFC, and IFC files arrive from consultants, subs and
 *  clients. These pin the viewer-side half of that defence: markup smuggled through the generator
 *  must not become script in the user's session. */
describe("sanitizeSvg", () => {
  const wrap = (inner: string) => `<svg xmlns="http://www.w3.org/2000/svg">${inner}</svg>`;

  it("strips <script> from model-derived SVG", () => {
    const out = sanitizeSvg(wrap('<script>window.__pwned = 1</script><rect width="1"/>'));
    expect(out).not.toContain("script");
    expect(out).toContain("rect");
  });

  it("strips <foreignObject>, which embeds arbitrary HTML", () => {
    const out = sanitizeSvg(wrap('<foreignObject><img src=x onerror="alert(1)"/></foreignObject>'));
    expect(out.toLowerCase()).not.toContain("foreignobject");
    expect(out).not.toContain("onerror");
  });

  it("removes event handlers at any depth and any casing", () => {
    const out = sanitizeSvg(wrap('<g><rect onload="alert(1)" ONCLICK="alert(2)"/></g>'));
    expect(out.toLowerCase()).not.toContain("onload");
    expect(out.toLowerCase()).not.toContain("onclick");
  });

  it("drops javascript: links but keeps same-document and http(s) ones", () => {
    expect(sanitizeSvg(wrap('<a href="javascript:alert(1)"><text>x</text></a>')))
      .not.toContain("javascript:");
    expect(sanitizeSvg(wrap('<a href="#detail-3"><text>x</text></a>'))).toContain("#detail-3");
    expect(sanitizeSvg(wrap('<a href="https://example.com/"><text>x</text></a>')))
      .toContain("https://example.com/");
  });

  it("preserves the drawing content it is meant to pass through", () => {
    const out = sanitizeSvg(wrap('<g class="disc"><rect x="1" y="2" fill="#333"/><text>A-101</text></g>'));
    expect(out).toContain("A-101");
    expect(out).toContain('fill="#333"');
  });

  it("returns empty string for a non-SVG or unparseable payload", () => {
    expect(sanitizeSvg("<html><body>nope</body></html>")).toBe("");
    expect(sanitizeSvg("not markup at all <<<")).toBe("");
  });
});

describe("safeUrl", () => {
  it("neutralises script-bearing schemes", () => {
    for (const bad of ["javascript:alert(1)", "JaVaScRiPt:alert(1)", "java\tscript:alert(1)",
                       " javascript:alert(1)", "data:text/html,<script>1</script>", "vbscript:x"]) {
      expect(safeUrl(bad)).toBe("#");
    }
  });

  it("keeps ordinary links, escaped for attribute context", () => {
    expect(safeUrl("https://massing.cloud/account")).toBe("https://massing.cloud/account");
    expect(safeUrl("/projects/1")).toBe("/projects/1");
    expect(safeUrl("mailto:a@b.com")).toBe("mailto:a@b.com");
  });

  it("escapes quotes so a value cannot break out of the attribute", () => {
    expect(safeUrl('https://x/" onmouseover="alert(1)')).not.toContain('"');
  });

  it("collapses empty/absent values to a harmless href", () => {
    expect(safeUrl(undefined)).toBe("#");
    expect(safeUrl("")).toBe("#");
  });
});

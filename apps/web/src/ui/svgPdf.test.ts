import { describe, expect, it } from "vitest";

import { MAX_PAGE_PT, pageSizeFromViewBox, pdfFromPng, viewBoxOf } from "./svgPdf";

// 1×1 white PNG
const DOT = Uint8Array.from(atob(
  "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg==",
), (c) => c.charCodeAt(0));

describe("R38-SHEET-MARKUP ③ ③ — generated sheet PDF", () => {
  it("caps the longest side so a full A1 does not freeze takeoff", () => {
    const p = pageSizeFromViewBox(10_000, 5_000);
    expect(Math.max(p.w, p.h)).toBe(MAX_PAGE_PT);
    expect(p.w / p.h).toBeCloseTo(2, 5);
  });

  it("a small sheet stays at its own size", () => {
    expect(pageSizeFromViewBox(200, 100)).toEqual({ w: 200, h: 100 });
  });

  it("viewBox wins over a missing width/height", () => {
    const svg = document.createElementNS("http://www.w3.org/2000/svg", "svg");
    svg.setAttribute("viewBox", "0 0 800 600");
    expect(viewBoxOf(svg)).toEqual({ w: 800, h: 600 });
  });

  it("pdfFromPng writes a real PDF, not an empty blob", async () => {
    const bytes = await pdfFromPng(DOT, 200, 100);
    const head = new TextDecoder().decode(bytes.slice(0, 5));
    expect(head).toBe("%PDF-");
    expect(bytes.length).toBeGreaterThan(50);
  });
});

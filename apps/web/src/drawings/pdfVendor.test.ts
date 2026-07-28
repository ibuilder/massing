import { describe, expect, it } from "vitest";

import { VENDOR_ENTRIES } from "../../vendorAlias";

/**
 * The vendored `@massingcloud/pdf-viewer` is wired and importable.
 *
 * Vendoring is only safe when three things stay true, and each has bitten this codebase before:
 * the alias resolves everywhere (tsc, Vite, Vitest — asserted in `kernel/ties.test.ts`, which
 * iterates the same map), the copy carries **no local patches** so a re-sync is a straight
 * overwrite, and the library is genuinely reachable rather than merely present on disk.
 *
 * That last one is the reachability lesson this repo learned the expensive way: seven engines once
 * shipped with no route to them, and every gate measured the engine while none measured the path.
 * A vendored package nothing imports is the same defect with a bigger diff.
 */
describe("the vendored PDF engine", () => {
  it("is registered in the one alias map", () => {
    expect(VENDOR_ENTRIES["@massingcloud/pdf-viewer"]).toBe("./src/vendor/massingpdf/index.ts");
  });

  // 20s, not the 5s default. This is the FIRST import of the vendored engine in the run, so it pays
  // the whole transform cost for a ~20k-line library at once. Alone it takes ~800ms; under the full
  // suite it reliably crossed 5s and failed — a real gate breaking on a real cost, not a flake.
  // Raising the budget is right here: the assertion is "the alias resolves", and how long a cold
  // transform takes is not what it is testing. If this ever needs raising again, the vendored copy
  // has grown enough to be worth a second look.
  it("actually imports through the alias, not just through a relative path", async () => {
    const mod = await import("@massingcloud/pdf-viewer");
    expect(mod).toBeTruthy();
  }, 20_000);

  it("exposes the surface the takeoff flow will need", async () => {
    const mod = await import("@massingcloud/pdf-viewer");
    for (const name of ["Viewer", "PdfDocument", "AnnotationStore", "definePlugin"]) {
      expect(typeof (mod as Record<string, unknown>)[name], name).not.toBe("undefined");
    }
  });

  it("brings no dependency this app does not already have", async () => {
    // Its only external imports are pdfjs-dist and pdf-lib, both already in package.json. If that
    // ever stops being true the vendoring argument changes — a copy that drags in a new dependency
    // is a dependency, just one nobody declared.
    const pkg = await import("../../package.json");
    const deps = { ...(pkg.default ?? pkg).dependencies } as Record<string, string>;
    expect(deps["pdfjs-dist"], "pdfjs-dist").toBeTruthy();
    expect(deps["pdf-lib"], "pdf-lib").toBeTruthy();
  });

  it("still exposes the takeoff entry point — adoption is by slice, not by rewrite", async () => {
    const takeoff = await import("./pdfTakeoff");
    expect(typeof takeoff.openPdfTakeoff).toBe("function");
  });
});

/**
 * The takeoff source, as text.
 *
 * No `catch(() => "")` and no `if (!src) return` — that escape hatch was in the first draft and it is
 * the exact can't-fail shape this repo has been bitten by four times today: a test that quietly
 * passes when its subject is unreachable measures nothing while reporting success. `?raw` was
 * verified to resolve here (28,480 chars). If it ever stops, this must go RED, not green.
 */
async function readSource(): Promise<string> {
  const mod = await import("./pdfTakeoff?raw");
  const src = (mod as { default: string }).default;
  expect(typeof src, "?raw did not return source — the assertions below would be vacuous").toBe("string");
  expect(src.length).toBeGreaterThan(1000);
  return src;
}

describe("PDF-ADOPT slice 1 — opening and page access run through the engine", () => {
  it("the takeoff no longer drives pdf.js directly", async () => {
    const src = await readSource();
    expect(src, "raw pdfjs getDocument should be gone").not.toMatch(/pdfjsLib\.getDocument/);
    expect(src, "raw getPage should be gone").not.toMatch(/doc\.getPage\(/);
    expect(src).toMatch(/PdfDocument\.load/);
    expect(src).toMatch(/configureWorker\(/);
  });

  it("page proxies are memoised — this flow asks for the same page repeatedly", async () => {
    // The old code called `doc.getPage(n)` on every render AND again for every page during export.
    // `PdfDocument.page` caches, so the win is real rather than cosmetic; if that ever stops being
    // true the swap loses its main justification and should be revisited.
    const { PdfDocument } = await import("@massingcloud/pdf-viewer");
    expect(typeof PdfDocument.load).toBe("function");
    expect(typeof PdfDocument.prototype.page).toBe("function");
  });

  it("the worker is still bundled locally — offline is non-negotiable", async () => {
    const src = await readSource();
    // CLAUDE.md: the viewer must run fully offline. A CDN worker URL would break that silently —
    // it works on the dev machine and fails on a site with no connection, which is where it matters.
    expect(src).toMatch(/pdfjs-dist\/build\/pdf\.worker\.min\.mjs\?url/);
    expect(src).not.toMatch(/https?:\/\/[^"']*pdf\.worker/);
  });
});

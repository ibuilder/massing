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

/**
 * The vendored engine, imported ONCE at module scope. Importing it is itself the assertion — if the
 * alias does not resolve, this module fails to load and every test below reports it.
 *
 * THIS WAS A 20s PER-TEST TIMEOUT, AND THE TIMEOUT WAS NOT ENOUGH
 *     The previous note here was right about the cause — the first import pays the whole transform
 *     for a ~20k-line library, ~800 ms alone — and chose to raise that one test's budget from 5 s to
 *     20 s, reasoning that a cold transform is not what the assertion tests. That reasoning is sound
 *     and the fix still failed: on 2026-08-07 it **timed out at 20 s**, and the next test failed at
 *     5 s in the same run, because when the first caller's import never resolves, everything else
 *     awaiting the same module dies with it. One slow first-caller takes the file down.
 *
 *     Raising a budget keeps the cliff and moves it somewhere less predictable — which is exactly
 *     what happened, and the second failure is the evidence. Hoisting removes it: the transform runs
 *     once during collection, outside any per-test budget, and no test inherits it.
 *
 *     Same remedy as `api/library.test.ts` (a `?raw` transform) and `tooling/deleteRatchet.test.ts`
 *     (a `git log` walk), from three different causes. The shared rule: **fixture cost does not
 *     belong inside a per-test timeout**, and a margin measured on an idle machine is a property of
 *     the machine, not of the test.
 */
const VENDOR = await import("@massingcloud/pdf-viewer");

describe("the vendored PDF engine", () => {
  it("is registered in the one alias map", () => {
    expect(VENDOR_ENTRIES["@massingcloud/pdf-viewer"]).toBe("./src/vendor/massingpdf/index.ts");
  });

  // The import is at module scope (see VENDOR above), so neither of these carries the transform.
  it("actually imports through the alias, not just through a relative path", () => {
    expect(VENDOR).toBeTruthy();
  });

  it("exposes the surface the takeoff flow will need", () => {
    for (const name of ["Viewer", "PdfDocument", "AnnotationStore", "definePlugin"]) {
      expect(typeof (VENDOR as Record<string, unknown>)[name], name).not.toBe("undefined");
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

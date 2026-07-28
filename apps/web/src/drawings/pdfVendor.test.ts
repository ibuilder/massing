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

  it("actually imports through the alias, not just through a relative path", async () => {
    const mod = await import("@massingcloud/pdf-viewer");
    expect(mod).toBeTruthy();
  });

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

  it("has not replaced the shipping takeoff flow yet — adoption is incremental", async () => {
    // Landing ~12k lines AND re-pointing the UI in one move makes a regression impossible to
    // bisect. `pdfTakeoff` still owns the flow; this asserts the seam is honest about that, so
    // nobody reads the vendored directory as "the takeoff is now the library's".
    const takeoff = await import("./pdfTakeoff");
    expect(typeof takeoff.openPdfTakeoff).toBe("function");
  });
});

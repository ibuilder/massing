import { describe, expect, it } from "vitest";

import pkg from "../../package.json";

/**
 * CVE-2026-16633 — pdf.js executes JavaScript embedded in a PDF in the hosting origin.
 *
 * THIS GATE ASSERTED THE WRONG THING FIRST, and the wrong thing looked more reassuring than the
 * right one. It required `enableScripting: false` at every `getDocument` call site. That option
 * does not exist on `getDocument`: it is a pdf.js **viewer** option, it appears nowhere in
 * `pdfjs-dist`'s `DocumentInitParameters` (`grep -r enableScripting node_modules/pdfjs-dist/types`
 * returns nothing), and the vendored fork read it nowhere either. It was a security control
 * consumed by no code — and a passing test saying "PDF scripting is disabled".
 *
 * **A gate vouching for a no-op is worse than no gate**, because it answers the question. Anyone
 * auditing this would have read a green check and moved on. It also did not typecheck against the
 * real `pdfjs-dist` types, which is how it surfaced — the compiler disagreed with the test.
 *
 * TWO THINGS ACTUALLY KEEP THIS SAFE, and both are asserted below:
 *
 *  1. **The exact version pin.** 6.2.108 is the patched release. A range (`^6.2.108`) would let a
 *     future install float, and the pin is the only thing standing between this app and the CVE,
 *     so it must not be a range.
 *  2. **No scripting engine is ever instantiated.** This app calls `getDocument` and renders pages;
 *     it never constructs pdf.js's viewer or its scripting layer, so document JavaScript has
 *     nothing to run in. That is a property of what we do NOT import, so it is asserted that way.
 */
describe("pdf.js cannot execute document scripts", () => {
  it("pins pdfjs-dist to an exact version — a range would let the patched release float away", () => {
    const spec = (pkg as { dependencies: Record<string, string> }).dependencies["pdfjs-dist"];
    expect(spec, "pdfjs-dist missing from dependencies").toBeTruthy();
    expect(spec, `pdfjs-dist is "${spec}" — a range, not a pin; CVE-2026-16633 is fixed in 6.2.108 `
      + "and a floating spec can resolve to something else").toMatch(/^\d+\.\d+\.\d+$/);
  });

  it("is pinned at or above the patched release", () => {
    const spec = (pkg as { dependencies: Record<string, string> }).dependencies["pdfjs-dist"]!;
    const [maj, min, patch] = spec.split(".").map(Number) as [number, number, number];
    const ok = maj > 6 || (maj === 6 && (min > 2 || (min === 2 && patch >= 108)));
    expect(ok, `pdfjs-dist ${spec} is older than the CVE-2026-16633 fix (6.2.108)`).toBe(true);
  });

  it("never instantiates pdf.js's viewer or scripting layer — the reason scripts have nowhere to run", () => {
    const SOURCES = import.meta.glob("../**/*.ts", { query: "?raw", import: "default", eager: true }) as Record<string, string>;
    const offenders = Object.entries(SOURCES)
      .filter(([path]) => !path.endsWith(".test.ts"))
      // `PDFScriptingManager` / `pdfjs-dist/web/pdf_viewer` are what would give document JS a home.
      .filter(([, src]) => /PDFScriptingManager|pdfjs-dist\/web\//.test(src))
      .map(([path]) => path);
    expect(offenders, "these pull in pdf.js's viewer/scripting layer, which is what makes "
      + "document-embedded JavaScript executable — the version pin alone would no longer be enough")
      .toEqual([]);
  });
});

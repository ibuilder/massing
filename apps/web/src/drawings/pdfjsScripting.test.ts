import { readFileSync } from "node:fs";
import { resolve } from "node:path";

import { describe, expect, it } from "vitest";

/**
 * CVE-2026-16633: pdf.js runs PDF-embedded JavaScript in the hosting origin when
 * `enableScripting` is left at its default (`true`). Both load sites in this app must refuse that.
 */
const ROOT = resolve(process.cwd(), "src");

describe("pdf.js does not execute document scripts", () => {
  it("every getDocument call site names enableScripting: false", () => {
    const files = [
      "vendor/massingpdf/core/document.ts",
      "drawings/drawings.ts",
    ];
    for (const rel of files) {
      const src = readFileSync(resolve(ROOT, rel), "utf8");
      expect(src, rel).toMatch(/getDocument\(/);
      expect(src, `${rel} must disable PDF scripting`).toMatch(/enableScripting:\s*false/);
    }
  });
});

import { describe, expect, it } from "vitest";

import { ApiClient } from "./client";

const api = new ApiClient("http://localhost:0");

describe("the elements client", () => {
  it("exposes inspector, list, colour, QA, and reverse deep-link", () => {
    for (const k of ["element", "elementLifecycle", "element5d", "elements", "colorFacets", "colorBy",
                     "elementsByDiscipline",
                     "dataQa", "codeCheck", "elementSources", "elementRecords", "elementCosts"]) {
      expect(typeof (api as unknown as Record<string, unknown>)[k], k).toBe("function");
    }
  });

  it("arrived as a mixin, so client.ts did not grow", async () => {
    const mod = await import("./elements");
    expect(typeof mod.withElements).toBe("function");
  });
});

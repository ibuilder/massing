import { describe, expect, it } from "vitest";

import { ApiClient } from "./client";

const api = new ApiClient("http://localhost:0");

describe("the drawing-set client", () => {
  it("exposes the register, issue, and transmittal calls", () => {
    for (const k of ["drawingSet", "drawingSetPlan", "generateDrawingSet", "issueDrawingSet",
                     "drawingIssuances", "drawingRevisions", "drawingTransmittalUrl"]) {
      expect(typeof (api as unknown as Record<string, unknown>)[k], k).toBe("function");
    }
  });

  it("arrived as a mixin, so client.ts did not grow", async () => {
    const mod = await import("./drawingSet");
    expect(typeof mod.withDrawingSet).toBe("function");
  });
});

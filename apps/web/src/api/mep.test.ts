import { describe, expect, it } from "vitest";

import { ApiClient } from "./client";

const api = new ApiClient("http://localhost:0");

describe("the mep client", () => {
  it("exposes summary, connectivity, sizing, fittings, and model extract", () => {
    for (const k of ["mepSummary", "mepConnectivity", "mepSizing", "sprinklerCoverage",
                     "mepFittings", "mep", "mepModelExtract", "mepPressureLoss", "mepTrayFill",
                     "mepThermalLoads"]) {
      expect(typeof (api as unknown as Record<string, unknown>)[k], k).toBe("function");
    }
  });

  it("arrived as a mixin, so client.ts did not grow", async () => {
    const mod = await import("./mep");
    expect(typeof mod.withMep).toBe("function");
  });
});

import { describe, expect, it } from "vitest";

import { ApiClient } from "./client";

const api = new ApiClient("http://localhost:0");

describe("the models client", () => {
  it("exposes health, QA, georeferencing, and federation CRUD", () => {
    for (const k of ["modelHealth", "modelQa", "normValid", "modelWarnings", "modelGeoreferencing",
                     "modelAlignment", "projectModels", "addProjectModel", "deleteProjectModel",
                     "exportQa", "schemaDiag", "footprintGeojsonUrl", "qualityTurnoverReadiness"]) {
      expect(typeof (api as unknown as Record<string, unknown>)[k], k).toBe("function");
    }
  });

  it("arrived as a mixin, so client.ts did not grow", async () => {
    const mod = await import("./models");
    expect(typeof mod.withModels).toBe("function");
  });
});

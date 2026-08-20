import { describe, expect, it } from "vitest";

import { ApiClient } from "./client";

const api = new ApiClient("http://localhost:0");

describe("the precon client", () => {
  it("exposes continuity, snapshot, decisions, assumptions, VE, and alignment", () => {
    for (const k of ["estimateContinuity", "preconSnapshot", "decisionLog",
                     "assumptionsRegister", "veLog", "preconAlignment"]) {
      expect(typeof (api as unknown as Record<string, unknown>)[k], k).toBe("function");
    }
  });

  it("arrived as a mixin, so client.ts did not grow", async () => {
    const mod = await import("./precon");
    expect(typeof mod.withPrecon).toBe("function");
  });
});

import { describe, expect, it } from "vitest";

import { ApiClient } from "./client";

const api = new ApiClient("http://localhost:0");

describe("the ai client", () => {
  it("exposes risk summary, ask, triage, estimate, author, and draft-rfi", () => {
    for (const k of ["riskSummary", "aiAsk", "triageRfi", "aiEstimate", "aiAuthor", "draftRfi"]) {
      expect(typeof (api as unknown as Record<string, unknown>)[k], k).toBe("function");
    }
  });

  it("arrived as a mixin, so client.ts did not grow", async () => {
    const mod = await import("./ai");
    expect(typeof mod.withAi).toBe("function");
  });
});

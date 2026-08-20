import { describe, expect, it } from "vitest";

import { ApiClient } from "./client";

const api = new ApiClient("http://localhost:0");

describe("the project-sync client", () => {
  it("exposes pull, push, and the schedule that runs them", () => {
    for (const k of ["syncProcore", "pushProcore", "syncSchedules", "createSyncSchedule",
                     "runSyncSchedule"]) {
      expect(typeof (api as unknown as Record<string, unknown>)[k], k).toBe("function");
    }
  });

  it("arrived as a mixin, so client.ts did not grow", async () => {
    const mod = await import("./sync");
    expect(typeof mod.withSync).toBe("function");
  });
});

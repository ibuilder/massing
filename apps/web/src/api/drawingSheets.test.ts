import { describe, expect, it } from "vitest";

import { ApiClient } from "./client";

const api = new ApiClient("http://localhost:0");

describe("the drawing-sheets client", () => {
  it("exposes schedules, storeys, markup, and the live stream", () => {
    for (const k of ["reviseDrawing", "drawingSchedules", "drawingStoreys", "drawingsSyncStatus",
                     "drawingMarkup", "promoteDrawingMarkup", "markupStream",
                     "drawingSchedulesCsvUrl"]) {
      expect(typeof (api as unknown as Record<string, unknown>)[k], k).toBe("function");
    }
  });

  it("arrived as a mixin, so client.ts did not grow", async () => {
    const mod = await import("./drawingSheets");
    expect(typeof mod.withDrawingSheets).toBe("function");
  });
});

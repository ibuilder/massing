import { describe, expect, it } from "vitest";

import { ApiClient } from "./client";

const api = new ApiClient("http://localhost:0");

describe("the documents client", () => {
  it("exposes tree, folder, health, upload, and download", () => {
    for (const k of ["documentsTree", "documentsFolder", "documentsByRole", "documentsHealth",
                     "documentsPhaseGaps", "uploadDocument", "moveDocument", "deleteDocument",
                     "documentDownloadUrl"]) {
      expect(typeof (api as unknown as Record<string, unknown>)[k], k).toBe("function");
    }
  });

  it("arrived as a mixin, so client.ts did not grow", async () => {
    const mod = await import("./documents");
    expect(typeof mod.withDocuments).toBe("function");
  });
});

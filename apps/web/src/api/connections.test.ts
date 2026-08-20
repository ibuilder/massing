import { describe, expect, it } from "vitest";

import { ApiClient } from "./client";

/**
 * SCALE-SEAM ⑫ — `/connections` is a mixin, so a later endpoint in this domain does not have to
 * open `client.ts` and fight the size pin. If `withConnections` ever disappears, the domain has
 * been folded back in and the extraction became a treadmill.
 */

const api = new ApiClient("http://localhost:0");

describe("the connections client", () => {
  it("exposes the route-group the admin screen needs", () => {
    for (const k of ["connections", "createConnection", "testConnection", "connectionTables",
                     "connectionQuery", "accIssues", "connectionMappings", "saveConnectionMappings"]) {
      expect(typeof (api as unknown as Record<string, unknown>)[k], k).toBe("function");
    }
  });

  it("arrived as a mixin, so client.ts did not grow", async () => {
    const mod = await import("./connections");
    expect(typeof mod.withConnections).toBe("function");
  });
});

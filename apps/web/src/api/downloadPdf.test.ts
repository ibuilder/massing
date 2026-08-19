import { describe, expect, it } from "vitest";

import { camStatementPath } from "./downloadPdf";

describe("CAM statement is a POST path, not a GET href", () => {
  it("names the lease PDF route the UI will POST", () => {
    expect(camStatementPath("p1", "lease-9")).toBe("/projects/p1/cam/statement/lease-9.pdf");
  });
});

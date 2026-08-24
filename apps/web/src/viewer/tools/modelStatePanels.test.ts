import { describe, expect, it } from "vitest";

import { parseDims, parsePitch } from "./modelStatePanels";

describe("parsePitch", () => {
  it("keeps a real zero rather than treating it as missing", () => {
    expect(parsePitch("1.5, 0")).toEqual([1.5, 0]);
  });

  it("refuses a typo instead of coercing it to 0", () => {
    expect(parsePitch("1.5, typo")).toBeNull();
  });
});

describe("parseDims", () => {
  it("needs three positive numbers", () => {
    expect(parseDims("1.8, 0.6, 0.9")).toEqual([1.8, 0.6, 0.9]);
    expect(parseDims("1.8, 0, 0.9")).toBeNull();
  });
});

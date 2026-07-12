import { describe, expect, it } from "vitest";
import { isSplatPly, SPLAT_EXTENSIONS } from "./splat";

describe("isSplatPly", () => {
  it("detects a Gaussian-splat PLY by its f_dc/scale/rot attributes", () => {
    const splatHeader = [
      "ply", "format binary_little_endian 1.0", "element vertex 1000",
      "property float x", "property float y", "property float z",
      "property float f_dc_0", "property float scale_0", "property float rot_0",
      "property float opacity", "end_header",
    ].join("\n");
    expect(isSplatPly(splatHeader)).toBe(true);
  });

  it("does not flag a plain geometry PLY (mesh / point cloud)", () => {
    const plainHeader = [
      "ply", "format ascii 1.0", "element vertex 3",
      "property float x", "property float y", "property float z",
      "property uchar red", "property uchar green", "property uchar blue",
      "element face 1", "property list uchar int vertex_indices", "end_header",
    ].join("\n");
    expect(isSplatPly(plainHeader)).toBe(false);
  });

  it("exposes the dedicated splat extensions", () => {
    expect(SPLAT_EXTENSIONS).toContain("splat");
    expect(SPLAT_EXTENSIONS).toContain("ksplat");
  });
});

import { describe, expect, it } from "vitest";
import { guidsFromSample, isGuid } from "./warningSample";

/**
 * WARN-1 — every shape below is taken from a real producer in
 * `services/api/src/aec_api/model_qa.py`, not invented. The feed types `sample` as `unknown[]`
 * because the producers genuinely disagree, so the fixtures are the point of this file.
 *
 * The case that carries the weight is `overlapping_duplicates`: its entries are `{class, location,
 * count}` with **no guid**, because a stack of duplicates is identified by where it is, not by which
 * element it is. A UI that offers that row a zoom affordance ships a click that does nothing.
 */

const GUID_A = "1a2B3c4D5e6F7g8H9i0JkL";   // 22 chars of the IFC base-64 alphabet
const GUID_B = "9z8Y7x6W5v4U3t2S1r0QpO";

describe("isGuid recognises an IFC GlobalId and not merely a string", () => {
  it("accepts a 22-character IFC id", () => {
    expect(isGuid(GUID_A)).toBe(true);
    // Length is the whole check, so the boundary needs a fixture that is genuinely short. My first
    // attempt here was 22 characters and asserted `false`; the test failed and the CODE was right.
    expect(isGuid("0$_zZ9876543210abcde")).toBe(false);    // 20 — too short
    expect(isGuid("0$_zZ9876543210abcdefGH")).toBe(false); // 23 — too long
  });

  it("rejects prose that happens to be in a sample", () => {
    // Samples carry labels and notes alongside offenders. Treating any string as a GUID would send
    // the viewer looking for an element called "Room is not enclosed".
    expect(isGuid("Room is not enclosed")).toBe(false);
    expect(isGuid("")).toBe(false);
    expect(isGuid(42)).toBe(false);
  });
});

describe("the real sample shapes", () => {
  it("duplicate_guids — plain strings", () => {
    expect(guidsFromSample([GUID_A, GUID_B])).toEqual([GUID_A, GUID_B]);
  });

  it("orphans / blank / unenclosed — objects carrying the guid", () => {
    expect(guidsFromSample([
      { class: "IfcWall", name: "W-1", guid: GUID_A },
      { class: "IfcSpace", name: null, guid: GUID_B },
    ])).toEqual([GUID_A, GUID_B]);
  });

  it("overlapping_duplicates — groups with NO guid yield nothing", () => {
    // The row exists and is worth showing; it simply cannot be zoomed to. Returning [] is what lets
    // the caller render it without a dead click.
    expect(guidsFromSample([
      { class: "IfcColumn", location: [0, 0, 0], count: 3 },
      { class: "IfcBeam", location: [1, 2, 0], count: 2 },
    ])).toEqual([]);
  });

  it("a mixed sample keeps the offenders and drops the rest", () => {
    expect(guidsFromSample([
      GUID_A,
      { class: "IfcColumn", location: [0, 0, 0], count: 3 },
      { guid: GUID_B },
      "not a guid",
      null,
      7,
    ])).toEqual([GUID_A, GUID_B]);
  });
});

describe("robustness the caller depends on", () => {
  it("de-duplicates while preserving order", () => {
    // Order follows the server's worst-first sort; re-sorting here would disagree with the row the
    // user clicked.
    expect(guidsFromSample([GUID_B, GUID_A, GUID_B])).toEqual([GUID_B, GUID_A]);
  });

  it("reads a guids[] list where a producer carries several", () => {
    expect(guidsFromSample([{ guids: [GUID_A, GUID_B] }])).toEqual([GUID_A, GUID_B]);
  });

  it("survives a sample that is not an array", () => {
    // The field is typed `unknown[]`, which is a promise the server makes and not one this code can
    // rely on — a 500-shaped body or an older build reaches here as whatever it is.
    for (const bad of [undefined, null, "guids", 3, {}]) {
      expect(guidsFromSample(bad)).toEqual([]);
    }
  });
});

/**
 * R38-STAIR-LIVE — the mirror must agree with the server, or it is worse than no readout.
 *
 * The constants are pinned to the values in services/data/src/aec_data/edit_enclosure.py
 * (MAX_RISER_M / MIN_TREAD_M / MAX_RAMP_SLOPE) and the sample cases reproduce the numbers the
 * server's own test (services/api/test_stair_ramp.py) asserts — a drifted mirror shows green for a
 * run the server reports as outside limits.
 */
import { describe, expect, it } from "vitest";
import {
  DEFAULT_RISE_M, MAX_RAMP_SLOPE, MAX_RISER_M, MIN_TREAD_M,
  rampReadout, runReadout, stairReadout,
} from "./stairLive";

describe("constants are pinned to the server's", () => {
  it("limits match edit_enclosure.py exactly", () => {
    expect(MAX_RISER_M).toBe(0.19);
    expect(MIN_TREAD_M).toBe(0.25);
    expect(MAX_RAMP_SLOPE).toBeCloseTo(1 / 12, 12);
    expect(DEFAULT_RISE_M).toBe(3.0);   // add_stair's rise when no target storey is sent
  });
});

describe("stairReadout mirrors stair_geometry", () => {
  it("a 3.0 m rise derives 16 risers @ 0.1875 — the server's own numbers", () => {
    const r = stairReadout(3.0, 4.8);
    expect(r.ok).toBe(true);
    expect(r.text).toContain("16 risers");
    expect(r.text).toContain("0.188");        // riser 0.1875 → toFixed(3)
    expect(r.text).toContain("0.300");        // tread 4.8/16
  });

  it("a run too short for the rise reads NOT ok and says the fix", () => {
    const r = stairReadout(3.0, 2.0);         // tread 0.125 < 0.25 — the server's failing case
    expect(r.ok).toBe(false);
    expect(r.text).toContain("lengthen the run");
  });

  it("no run yet → neither verdict (a report cannot fail before there is a run)", () => {
    expect(stairReadout(3.0, 0).ok).toBeNull();
    expect(stairReadout(0, 4).ok).toBeNull();
  });
});

describe("rampReadout mirrors ramp_geometry", () => {
  it("1:12 is within the accessible limit; 1:6 is not — the server's two cases", () => {
    expect(rampReadout(1.0, 12.0).ok).toBe(true);
    const steep = rampReadout(1.0, 6.0);
    expect(steep.ok).toBe(false);
    expect(steep.text).toContain("1:6");
    expect(steep.text).toContain("lengthen the run");
  });
});

describe("runReadout routes by tool key", () => {
  it("stair and ramp answer; every other tool stays silent", () => {
    expect(runReadout("stair", 3, 5)?.ok).toBe(true);
    expect(runReadout("ramp", 1, 12)?.ok).toBe(true);
    expect(runReadout("wall", 3, 5)).toBeNull();
  });
});

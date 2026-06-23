import { describe, expect, it } from "vitest";

import { sunAltAz, sunSceneDir } from "./solar";

describe("solar", () => {
  it("sun is high near solar noon on the equinox at the equator", () => {
    // 2024-03-20 equinox, equator, local solar noon (lon 0, tz 0) → sun ~overhead
    const p = sunAltAz(new Date("2024-03-20T12:00:00"), 0, 0, 0);
    expect(p.altitude).toBeGreaterThan(80);
  });

  it("sun is below the horizon at local midnight", () => {
    const p = sunAltAz(new Date("2024-06-21T00:00:00"), 40.7, -74, -5);
    expect(p.altitude).toBeLessThan(0);
  });

  it("morning sun sits in the east, afternoon sun in the west", () => {
    const am = sunAltAz(new Date("2024-06-21T08:00:00"), 40.7, -74, -5);
    const pm = sunAltAz(new Date("2024-06-21T16:00:00"), 40.7, -74, -5);
    expect(am.azimuth).toBeLessThan(180);   // east of south
    expect(pm.azimuth).toBeGreaterThan(180); // west of south
  });

  it("scene direction points up when the sun is above the horizon", () => {
    const noon = sunAltAz(new Date("2024-06-21T13:00:00"), 40.7, -74, -5);
    const dir = sunSceneDir(noon);
    expect(dir.y).toBeGreaterThan(0);
    // unit vector
    const len = Math.hypot(dir.x, dir.y, dir.z);
    expect(len).toBeCloseTo(1, 5);
  });

  it("northern-summer noon sun is to the south (azimuth near 180°)", () => {
    const p = sunAltAz(new Date("2024-06-21T12:00:00"), 40.7, -74, -5);
    expect(Math.abs(p.azimuth - 180)).toBeLessThan(35);
  });
});

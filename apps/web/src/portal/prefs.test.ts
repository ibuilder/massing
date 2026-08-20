import { afterEach, describe, expect, it } from "vitest";

import { DENSITY_ROW_PX, DENSITY_STEPS, cycleDensity, readDensity, setDensity } from "./prefs";

afterEach(() => localStorage.removeItem("portal-density"));

describe("R24-DENSITY ② — three named row heights", () => {
  it("Field is 56, Default 36, Compact 28", () => {
    expect(DENSITY_ROW_PX.field).toBe(56);
    expect(DENSITY_ROW_PX.comfortable).toBe(36);
    expect(DENSITY_ROW_PX.compact).toBe(28);
    expect(DENSITY_STEPS).toEqual(["field", "comfortable", "compact"]);
  });

  it("unknown storage is comfortable, never a silent compact", () => {
    localStorage.removeItem("portal-density");
    expect(readDensity()).toBe("comfortable");
    localStorage.setItem("portal-density", "nope");
    expect(readDensity()).toBe("comfortable");
  });

  it("cycles Field → comfortable → compact → Field", () => {
    setDensity("field");
    expect(cycleDensity()).toBe("comfortable");
    expect(cycleDensity()).toBe("compact");
    expect(cycleDensity()).toBe("field");
  });
});

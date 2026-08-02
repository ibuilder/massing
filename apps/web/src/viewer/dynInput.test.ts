import { describe, expect, it } from "vitest";
import { dynKeystroke, formatDynConstraint, isDynKey, parseDynConstraint } from "./dynInput";

describe("SNAP-KIT dynamic-input constraint parser", () => {
  it("parses distance-only, angle-only, and both", () => {
    expect(parseDynConstraint("6")).toEqual({ distance: 6 });
    expect(parseDynConstraint("2.5")).toEqual({ distance: 2.5 });
    expect(parseDynConstraint("<30")).toEqual({ angle: 30 });
    expect(parseDynConstraint("<-45")).toEqual({ angle: -45 });
    expect(parseDynConstraint("6<30")).toEqual({ distance: 6, angle: 30 });
  });

  it("rejects malformed buffers instead of guessing (strict, like the CAD polar tokens)", () => {
    expect(parseDynConstraint("")).toBeNull();
    expect(parseDynConstraint("6<")).toBeNull();       // angle started but missing
    expect(parseDynConstraint("6<30<45")).toBeNull();  // double '<'
    expect(parseDynConstraint("0")).toBeNull();        // zero-length
    expect(parseDynConstraint("-3")).toBeNull();       // negative distance
    expect(parseDynConstraint("abc")).toBeNull();
  });

  it("R38-DIM-INPUT — imperial input converts to metres (the model is metric; the keyboard isn't)", () => {
    expect(parseDynConstraint("12'6")?.distance).toBeCloseTo(3.81, 3);      // 12 ft 6 in
    expect(parseDynConstraint("12'")?.distance).toBeCloseTo(3.6576, 4);     // bare feet
    expect(parseDynConstraint('30"')?.distance).toBeCloseTo(0.762, 4);      // inches only
    expect(parseDynConstraint("12'6.5")?.distance).toBeCloseTo(3.8227, 3);  // decimal inches
    expect(parseDynConstraint('12\'6"')?.distance).toBeCloseTo(3.81, 3);    // explicit inch mark
    expect(parseDynConstraint("12'6<30")).toMatchObject({ angle: 30 });     // composes with angle
    expect(parseDynConstraint("12'6<30")?.distance).toBeCloseTo(3.81, 3);
  });

  it("rejects malformed imperial instead of guessing", () => {
    expect(parseDynConstraint("12'13")).toBeNull();   // 13 inches is not a thing
    expect(parseDynConstraint("'6")).toBeNull();      // feet part missing
    expect(parseDynConstraint("0'")).toBeNull();      // zero length
    expect(parseDynConstraint('12"6')).toBeNull();    // inch mark mid-token
  });

  it("the HUD echo is always metres, so the conversion is visible before the click commits it", () => {
    expect(formatDynConstraint({ distance: 3.81 })).toBe("3.81 m");
    expect(formatDynConstraint({ angle: 30 })).toBe("@ 30°");
    expect(formatDynConstraint({ distance: 6, angle: 30 })).toBe("6 m @ 30°");
  });

  it("keystroke buffer appends dyn keys, trims on Backspace, ignores the rest", () => {
    let b = "";
    for (const k of ["6", "<", "3", "0"]) b = dynKeystroke(b, k);
    expect(b).toBe("6<30");
    b = dynKeystroke(b, "Backspace");
    expect(b).toBe("6<3");
    expect(dynKeystroke(b, "x")).toBe("6<3");          // non-grammar key ignored
    expect(isDynKey("<")).toBe(true);
    expect(isDynKey("e")).toBe(false);
  });
});

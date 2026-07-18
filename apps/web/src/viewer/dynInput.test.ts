import { describe, expect, it } from "vitest";
import { dynKeystroke, isDynKey, parseDynConstraint } from "./dynInput";

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

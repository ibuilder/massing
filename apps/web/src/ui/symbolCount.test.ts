import { describe, expect, it } from "vitest";

import { countOnRgba, countSymbols, nccAt, nms, scanNcc, stamp } from "./symbolCount";

function plus(): { needle: Float64Array; nw: number; nh: number } {
  // 3×3 plus on black
  const n = new Float64Array([
    0, 1, 0,
    1, 1, 1,
    0, 1, 0,
  ]);
  return { needle: n, nw: 3, nh: 3 };
}

describe("R23-SYMBOL-COUNT ① — NCC", () => {
  it("a stamped copy scores ~1 at the stamp and less beside it", () => {
    const { needle, nw, nh } = plus();
    const hw = 10, hh = 10;
    const hay = new Float64Array(hw * hh);
    stamp(hay, hw, needle, nw, nh, 4, 5);
    expect(nccAt(hay, hw, hh, needle, nw, nh, 4, 5)).toBeCloseTo(1, 10);
    expect(nccAt(hay, hw, hh, needle, nw, nh, 5, 5)).toBeLessThan(0.8);
  });

  it("a needle larger than the sheet is zero hits, not a throw", () => {
    expect(scanNcc(new Float64Array(4), 2, 2, new Float64Array(9), 3, 3, 0.5)).toEqual([]);
  });

  it("a blank needle (zero variance) does not invent a match", () => {
    const hay = new Float64Array(16);
    hay[0] = 1;
    const needle = new Float64Array(4);
    expect(nccAt(hay, 4, 4, needle, 2, 2, 0, 0)).toBe(0);
  });
});

describe("R23-SYMBOL-COUNT ① — NMS + count", () => {
  it("two well-separated stamps both count", () => {
    const { needle, nw, nh } = plus();
    const hw = 16, hh = 8;
    const hay = new Float64Array(hw * hh);
    stamp(hay, hw, needle, nw, nh, 1, 2);
    stamp(hay, hw, needle, nw, nh, 10, 2);
    const r = countSymbols(hay, hw, hh, needle, nw, nh, { threshold: 0.9, radius: 2 });
    expect(r.count).toBe(2);
    expect(r.peaks.map((p) => `${p.x},${p.y}`).sort()).toEqual(["1,2", "10,2"]);
  });

  it("two peaks a pixel apart collapse to the stronger one", () => {
    const kept = nms(
      [{ x: 0, y: 0, score: 0.99 }, { x: 1, y: 0, score: 0.90 }],
      2,
    );
    expect(kept).toEqual([{ x: 0, y: 0, score: 0.99 }]);
  });

  it("threshold rejects a weak lookalike", () => {
    const { needle, nw, nh } = plus();
    const hw = 8, hh = 8;
    const hay = new Float64Array(hw * hh);
    // a 2×2 block is not a plus
    hay[0] = hay[1] = hay[hw] = hay[hw + 1] = 1;
    const r = countSymbols(hay, hw, hh, needle, nw, nh, { threshold: 0.85, radius: 2 });
    expect(r.count).toBe(0);
  });
});

function grayToRgba(gray: ArrayLike<number>, w: number, h: number): Uint8ClampedArray {
  const d = new Uint8ClampedArray(w * h * 4);
  for (let i = 0; i < w * h; i++) {
    const v = Math.round((gray[i] ?? 0) * 255);
    d[i * 4] = v; d[i * 4 + 1] = v; d[i * 4 + 2] = v; d[i * 4 + 3] = 255;
  }
  return d;
}

describe("R23-SYMBOL-COUNT ② — rgba page", () => {
  it("a 3 px box is a reason, never a guessed count", () => {
    const d = new Uint8ClampedArray(20 * 20 * 4);
    const r = countOnRgba(d, 20, 20, { x: 1, y: 1, w: 3, h: 3 });
    expect(r.count).toBe(0);
    expect(r.reason).toMatch(/larger instance/);
  });

  it("a region bigger than one symbol is refused", () => {
    const d = new Uint8ClampedArray(200 * 200 * 4);
    const r = countOnRgba(d, 200, 200, { x: 0, y: 0, w: 120, h: 10 });
    expect(r.count).toBe(0);
    expect(r.reason).toMatch(/too large/);
  });

  it("two stamped 6×6 pluses both come back in original pixel space", () => {
    const nw = 6, nh = 6;
    const needle = new Float64Array(nw * nh);
    for (let i = 0; i < nw; i++) { needle[2 * nw + i] = 1; needle[i * nw + 2] = 1; needle[i * nw + 3] = 1; }
    const hw = 40, hh = 20;
    const hay = new Float64Array(hw * hh);
    stamp(hay, hw, needle, nw, nh, 2, 4);
    stamp(hay, hw, needle, nw, nh, 24, 4);
    const r = countOnRgba(grayToRgba(hay, hw, hh), hw, hh, { x: 2, y: 4, w: nw, h: nh }, { threshold: 0.9 });
    expect(r.reason).toBeUndefined();
    expect(r.count).toBe(2);
    expect(r.peaks.map((p) => `${p.x},${p.y}`).sort()).toEqual(["2,4", "24,4"]);
  });
});

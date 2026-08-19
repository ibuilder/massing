/**
 * R23-SYMBOL-COUNT ① — normalised cross-correlation + non-maximum suppression.
 *
 * Mark one instance, find the others. No new dependencies, offline, auditable — quantities
 * that feed a bid cannot be a black-box detector. This file is the matcher. Wiring it into
 * the pdf.js takeoff worker is the next slice; a matcher nobody can unit-test on a known
 * patch is how a count becomes a guess.
 *
 * Buffers are row-major grayscale in 0..1. Coordinates are top-left of the needle.
 */
export type Peak = { x: number; y: number; score: number };

function meanPatch(
  buf: ArrayLike<number>, w: number, x: number, y: number, nw: number, nh: number,
): number {
  let s = 0;
  for (let j = 0; j < nh; j++) {
    const row = (y + j) * w + x;
    for (let i = 0; i < nw; i++) s += buf[row + i]!;
  }
  return s / (nw * nh);
}

/** NCC of `needle` against `hay` at top-left `(x, y)`. 1 is identical (up to scale). */
export function nccAt(
  hay: ArrayLike<number>, hw: number, hh: number,
  needle: ArrayLike<number>, nw: number, nh: number,
  x: number, y: number,
): number {
  if (x < 0 || y < 0 || x + nw > hw || y + nh > hh) return 0;
  const hm = meanPatch(hay, hw, x, y, nw, nh);
  const nm = meanPatch(needle, nw, 0, 0, nw, nh);
  let dot = 0, hn = 0, nn = 0;
  for (let j = 0; j < nh; j++) {
    const hr = (y + j) * hw + x;
    const nr = j * nw;
    for (let i = 0; i < nw; i++) {
      const hv = hay[hr + i]! - hm;
      const nv = needle[nr + i]! - nm;
      dot += hv * nv;
      hn += hv * hv;
      nn += nv * nv;
    }
  }
  const den = Math.sqrt(hn * nn);
  if (den === 0) return 0;
  return dot / den;
}

export function scanNcc(
  hay: ArrayLike<number>, hw: number, hh: number,
  needle: ArrayLike<number>, nw: number, nh: number,
  threshold: number,
): Peak[] {
  if (nw < 1 || nh < 1 || nw > hw || nh > hh) return [];
  const out: Peak[] = [];
  for (let y = 0; y <= hh - nh; y++) {
    for (let x = 0; x <= hw - nw; x++) {
      const score = nccAt(hay, hw, hh, needle, nw, nh, x, y);
      if (score >= threshold) out.push({ x, y, score });
    }
  }
  return out;
}

/** Keep the highest peak in each `radius` neighbourhood. */
export function nms(peaks: readonly Peak[], radius: number): Peak[] {
  const sorted = [...peaks].sort((a, b) => b.score - a.score || a.y - b.y || a.x - b.x);
  const kept: Peak[] = [];
  const r2 = radius * radius;
  for (const p of sorted) {
    if (kept.some((k) => {
      const dx = k.x - p.x, dy = k.y - p.y;
      return dx * dx + dy * dy <= r2;
    })) continue;
    kept.push(p);
  }
  return kept;
}

export function countSymbols(
  hay: ArrayLike<number>, hw: number, hh: number,
  needle: ArrayLike<number>, nw: number, nh: number,
  opts?: { threshold?: number; radius?: number },
): { count: number; peaks: Peak[] } {
  const threshold = opts?.threshold ?? 0.85;
  const radius = opts?.radius ?? Math.max(nw, nh) / 2;
  const peaks = nms(scanNcc(hay, hw, hh, needle, nw, nh, threshold), radius);
  return { count: peaks.length, peaks };
}

/** Stamp `needle` into `hay` at `(x, y)` — test helper and takeoff preview. */
export function stamp(
  hay: Float64Array, hw: number,
  needle: ArrayLike<number>, nw: number, nh: number,
  x: number, y: number,
): void {
  for (let j = 0; j < nh; j++) {
    const hr = (y + j) * hw + x;
    const nr = j * nw;
    for (let i = 0; i < nw; i++) hay[hr + i] = needle[nr + i]!;
  }
}

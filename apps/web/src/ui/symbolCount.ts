/**
 * R23-SYMBOL-COUNT — normalised cross-correlation + non-maximum suppression.
 *
 * Mark one instance, find the others. No new dependencies, offline, auditable — quantities
 * that feed a bid cannot be a black-box detector. ① is the matcher (unit-tested on known
 * patches). ② is the takeoff page: `countOnRgba` reads the pdf.js canvas, downsamples so a
 * sheet stays interactive, and returns peaks in the original pixel space.
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
  step = 1,
): Peak[] {
  if (nw < 1 || nh < 1 || nw > hw || nh > hh) return [];
  const stride = Math.max(1, Math.floor(step));
  const out: Peak[] = [];
  for (let y = 0; y <= hh - nh; y += stride) {
    for (let x = 0; x <= hw - nw; x += stride) {
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

/** Largest side we scan. A full-res A1 canvas is tens of billions of NCC ops; 480 keeps a sheet interactive. */
export const MAX_SCAN_DIM = 480;
export const MAX_NEEDLE_PX = 96;
export const MAX_MATCHES = 250;

export function rgbaToGray(data: ArrayLike<number>, w: number, h: number): Float64Array {
  const out = new Float64Array(w * h);
  for (let i = 0, p = 0; i < out.length; i++, p += 4) {
    out[i] = (data[p]! * 0.299 + data[p + 1]! * 0.587 + data[p + 2]! * 0.114) / 255;
  }
  return out;
}

export function cropGray(
  buf: ArrayLike<number>, w: number, x: number, y: number, nw: number, nh: number,
): Float64Array {
  const out = new Float64Array(nw * nh);
  for (let j = 0; j < nh; j++) {
    const src = (y + j) * w + x;
    const dst = j * nw;
    for (let i = 0; i < nw; i++) out[dst + i] = buf[src + i]!;
  }
  return out;
}

/** Average 2×2 blocks. Odd leftover columns/rows are dropped, not invented. */
export function downsample2(buf: ArrayLike<number>, w: number, h: number): { buf: Float64Array; w: number; h: number } {
  const nw = Math.floor(w / 2), nh = Math.floor(h / 2);
  const out = new Float64Array(nw * nh);
  for (let j = 0; j < nh; j++) {
    for (let i = 0; i < nw; i++) {
      const s = (j * 2) * w + (i * 2);
      out[j * nw + i] = (buf[s]! + buf[s + 1]! + buf[s + w]! + buf[s + w + 1]!) / 4;
    }
  }
  return { buf: out, w: nw, h: nh };
}

export type PixelRect = { x: number; y: number; w: number; h: number };

export type RgbaCount = { count: number; peaks: Peak[]; factor: number; reason?: string };

/**
 * Count a boxed template on an RGBA page. Peaks are top-left in the *original* pixel space.
 * A too-small or too-large box is a reason, never a guessed count.
 */
export function countOnRgba(
  data: ArrayLike<number>, w: number, h: number,
  rect: PixelRect,
  opts?: { threshold?: number },
): RgbaCount {
  const x = Math.max(0, Math.floor(rect.x));
  const y = Math.max(0, Math.floor(rect.y));
  const nw = Math.min(Math.floor(rect.w), w - x);
  const nh = Math.min(Math.floor(rect.h), h - y);
  if (nw < 4 || nh < 4) return { count: 0, peaks: [], factor: 1, reason: "box a larger instance" };
  if (nw > MAX_NEEDLE_PX || nh > MAX_NEEDLE_PX) {
    return { count: 0, peaks: [], factor: 1, reason: "template too large — box one symbol, not a region" };
  }

  let gray = rgbaToGray(data, w, h);
  let gw = w, gh = h, gx = x, gy = y, gnW = nw, gnH = nh, factor = 1;
  while (Math.max(gw, gh) > MAX_SCAN_DIM && gnW >= 6 && gnH >= 6) {
    const d = downsample2(gray, gw, gh);
    gray = d.buf; gw = d.w; gh = d.h;
    gx = Math.floor(gx / 2); gy = Math.floor(gy / 2);
    gnW = Math.floor(gnW / 2); gnH = Math.floor(gnH / 2);
    factor *= 2;
  }
  if (gnW < 3 || gnH < 3) return { count: 0, peaks: [], factor, reason: "box a larger instance" };

  const needle = cropGray(gray, gw, gx, gy, gnW, gnH);
  const threshold = opts?.threshold ?? 0.85;
  const found = countSymbols(gray, gw, gh, needle, gnW, gnH, {
    threshold, radius: Math.max(gnW, gnH) / 2,
  });
  const peaks = found.peaks.slice(0, MAX_MATCHES).map((p) => ({
    x: p.x * factor, y: p.y * factor, score: p.score,
  }));
  return { count: peaks.length, peaks, factor };
}

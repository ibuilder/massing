/**
 * Revision intelligence: overlay two sheets, align them, find what changed, and cloud it.
 *
 * The workflow this replaces is a light table and a highlighter. Two issues of the same sheet are
 * rasterised at a common scale, aligned (plot origins drift by a few points between issues, which
 * is enough to make a naive pixel diff report the entire drawing as changed), differenced, and the
 * changed regions clustered into boxes that become real revision clouds in the markup store — not a
 * throwaway picture, but markups that carry authorship, status and a migration record.
 */
import { definePlugin } from "../core/plugin";
import { PdfDocument, type PdfSource } from "../core/document";
import type { AnnotationDraft } from "../core/types";
import type { Viewer } from "../core/viewer";

export interface CompareOptions {
  /** Raster resolution for the diff, in pixels across the page's long edge. */
  resolution?: number;
  /** 0..1 luminance delta that counts as a change. Higher ignores anti-aliasing and scan noise. */
  threshold?: number;
  /** Ignore changed clusters smaller than this many pixels — kills scanner speckle. */
  minCluster?: number;
  /**
   * Also search for a uniform scale difference, for sheets re-plotted to another paper size.
   * Roughly ten times the alignment cost, so it is off unless asked for.
   */
  matchScale?: boolean;
  /** Supply the revision to compare against, e.g. from the host's drawing register. */
  loadPrevious?: (viewer: Viewer) => Promise<PdfSource | null>;
}

export interface DiffRegion {
  /** Bounds in page space of the *current* sheet. */
  x: number; y: number; w: number; h: number;
  /** Changed pixel count — a crude severity used to sort and to drop noise. */
  weight: number;
}

export interface CompareResult {
  /** Translation, in page points, that best aligns the previous sheet onto the current one. */
  offset: { x: number; y: number };
  /**
   * Uniform scale applied to the previous sheet before that translation. `1` for the usual case of
   * a re-issue at the same size; departs from 1 when a sheet was re-plotted to another paper size.
   */
  scale: number;
  regions: DiffRegion[];
  /** Fraction of the sheet that changed, 0..1. */
  changedFraction: number;
}

export function comparePlugin(options: CompareOptions = {}) {
  return definePlugin({
    id: "compare",
    order: 60,
    setup(ctx) {
      let previous: PdfDocument | null = null;
      let overlayEl: HTMLCanvasElement | null = null;
      let lastResult: CompareResult | null = null;

      ctx.onCleanup(() => { previous?.destroy(); overlayEl?.remove(); });

      const ensurePrevious = async (v: Viewer): Promise<PdfDocument | null> => {
        if (previous) return previous;
        const src = options.loadPrevious ? await options.loadPrevious(v) : await pickFile();
        if (!src) return null;
        previous = await PdfDocument.load(src);
        await previous.primeInfo();
        return previous;
      };

      ctx.registerAction({
        id: "compare.load", label: "Load previous revision", icon: "⧉", group: "compare",
        async run(v) {
          previous?.destroy();
          previous = null;
          const doc = await ensurePrevious(v);
          if (doc) v.bus.emit("notice", { level: "success", message: `Comparing against ${doc.name} (${doc.numPages} pages).` });
        },
      });

      ctx.registerAction({
        id: "compare.overlay", label: "Overlay revisions", icon: "◍", group: "compare",
        async run(v) {
          const prev = await ensurePrevious(v);
          if (!prev || !v.doc) return;
          if (overlayEl) { overlayEl.remove(); overlayEl = null; return; }
          try {
            overlayEl = await buildOverlay(v, prev, options);
          } catch (e) {
            v.bus.emit("notice", { level: "error", message: `Overlay failed: ${(e as Error).message}` });
          }
        },
      });

      ctx.registerAction({
        id: "compare.diff", label: "Find changes", icon: "⌕", group: "compare",
        async run(v) {
          const prev = await ensurePrevious(v);
          if (!prev || !v.doc) return;
          v.bus.emit("notice", { level: "info", message: "Comparing sheets…" });
          try {
            lastResult = await comparePages(v.doc, prev, v.page, Math.min(v.page, prev.numPages), options);
            const pct = (lastResult.changedFraction * 100).toFixed(1);
            v.bus.emit("notice", {
              level: lastResult.regions.length ? "success" : "info",
              message: lastResult.regions.length
                ? `${lastResult.regions.length} changed region${lastResult.regions.length === 1 ? "" : "s"} (${pct}% of the sheet). Use "Cloud changes" to mark them up.`
                : "No differences found on this sheet.",
            });
          } catch (e) {
            v.bus.emit("notice", { level: "error", message: `Compare failed: ${(e as Error).message}` });
          }
        },
      });

      ctx.registerAction({
        id: "compare.cloud", label: "Cloud changes", icon: "☁", group: "compare",
        enabled: () => Boolean(lastResult?.regions.length),
        run(v) {
          if (!lastResult) return;
          const page = v.page;
          const rev = v.store.sheet(page)?.revision;
          const drafts: AnnotationDraft[] = lastResult.regions.map((r, i) => ({
            kind: "cloud",
            page,
            points: [
              { x: r.x, y: r.y }, { x: r.x + r.w, y: r.y },
              { x: r.x + r.w, y: r.y + r.h }, { x: r.x, y: r.y + r.h },
            ],
            subject: `Change ${i + 1}`,
            note: "Auto-detected difference against the previous revision.",
            status: "in_review",
            labels: ["auto-diff"],
            style: { color: "#e2554a", width: 1.4 },
            ...(rev ? { revision: { rev, migration: "ok" as const } } : {}),
            ext: { diffWeight: r.weight },
          }));
          v.store.addMany(drafts);
          v.redraw(page);
          v.bus.emit("notice", { level: "success", message: `Clouded ${drafts.length} change${drafts.length === 1 ? "" : "s"}.` });
        },
      });

      ctx.registerAction({
        id: "compare.clearClouds", label: "Clear change clouds", icon: "⌫", group: "compare",
        enabled: (v) => v.store.all().some((a) => a.labels?.includes("auto-diff")),
        run(v) {
          const ids = v.store.all().filter((a) => a.labels?.includes("auto-diff")).map((a) => a.id);
          v.store.remove(ids);
        },
      });

      ctx.viewer.compare = {
        result: () => lastResult,
        run: async (v: Viewer) => {
          const prev = await ensurePrevious(v);
          if (!prev || !v.doc) return null;
          lastResult = await comparePages(v.doc, prev, v.page, Math.min(v.page, prev.numPages), options);
          return lastResult;
        },
      };
    },
  });
}

// ---- rasterisation ---------------------------------------------------------

interface Raster { data: Float32Array; w: number; h: number; scale: number }

/** Rasterise a page to a single-channel luminance buffer at roughly `resolution` px on the long edge. */
async function rasterise(doc: PdfDocument, page: number, resolution: number): Promise<Raster> {
  const info = await doc.pageInfo(page);
  const scale = resolution / Math.max(info.width, info.height);
  const w = Math.max(1, Math.round(info.width * scale));
  const h = Math.max(1, Math.round(info.height * scale));
  const canvas = document.createElement("canvas");
  canvas.width = w; canvas.height = h;
  const ctx = canvas.getContext("2d", { alpha: false, willReadFrequently: true });
  if (!ctx) throw new Error("2D canvas unavailable");
  ctx.fillStyle = "#fff";
  ctx.fillRect(0, 0, w, h);
  const pg = await doc.page(page);
  await pg.render({ canvas, canvasContext: ctx, viewport: pg.getViewport({ scale }) }).promise;
  const img = ctx.getImageData(0, 0, w, h).data;
  const out = new Float32Array(w * h);
  for (let i = 0, p = 0; i < img.length; i += 4, p++) {
    // Rec.601 luma. Drawings are near-binary, so channel weighting barely matters — but coloured
    // revision markup in the source should still register as ink rather than as white.
    out[p] = (0.299 * img[i]! + 0.587 * img[i + 1]! + 0.114 * img[i + 2]!) / 255;
  }
  return { data: out, w, h, scale };
}

/**
 * Resample a raster to a new pixel size with bilinear interpolation. Used to try a candidate
 * scale during alignment — a re-plot from ARCH C to ARCH D is a ~1.29× change that a
 * translation-only search cannot absorb.
 */
function resample(r: Raster, k: number): Raster {
  if (Math.abs(k - 1) < 1e-6) return r;
  const w = Math.max(1, Math.round(r.w * k));
  const h = Math.max(1, Math.round(r.h * k));
  const out = new Float32Array(w * h);
  for (let y = 0; y < h; y++) {
    const sy = Math.min(r.h - 1, y / k);
    const y0 = Math.floor(sy), y1 = Math.min(r.h - 1, y0 + 1), fy = sy - y0;
    for (let x = 0; x < w; x++) {
      const sx = Math.min(r.w - 1, x / k);
      const x0 = Math.floor(sx), x1 = Math.min(r.w - 1, x0 + 1), fx = sx - x0;
      const a = r.data[y0 * r.w + x0]!, b = r.data[y0 * r.w + x1]!;
      const c = r.data[y1 * r.w + x0]!, d = r.data[y1 * r.w + x1]!;
      out[y * w + x] = a * (1 - fx) * (1 - fy) + b * fx * (1 - fy) + c * (1 - fx) * fy + d * fx * fy;
    }
  }
  return { data: out, w, h, scale: r.scale * k };
}

/** Box-downsample by an integer factor, for the alignment pyramid. */
function downsample(r: Raster, factor: number): Raster {
  const w = Math.max(1, Math.floor(r.w / factor));
  const h = Math.max(1, Math.floor(r.h / factor));
  const out = new Float32Array(w * h);
  for (let y = 0; y < h; y++) {
    for (let x = 0; x < w; x++) {
      let sum = 0, n = 0;
      for (let dy = 0; dy < factor; dy++) {
        const sy = y * factor + dy;
        if (sy >= r.h) break;
        for (let dx = 0; dx < factor; dx++) {
          const sx = x * factor + dx;
          if (sx >= r.w) break;
          sum += r.data[sy * r.w + sx]!;
          n++;
        }
      }
      out[y * w + x] = n ? sum / n : 1;
    }
  }
  return { data: out, w, h, scale: r.scale / factor };
}

/** Mean absolute difference of `a` and `b` with `b` shifted by (ox, oy). Lower is better. */
function misfit(a: Raster, b: Raster, ox: number, oy: number): number {
  let sum = 0, n = 0;
  const x0 = Math.max(0, -ox), x1 = Math.min(a.w, b.w - ox);
  const y0 = Math.max(0, -oy), y1 = Math.min(a.h, b.h - oy);
  if (x1 <= x0 || y1 <= y0) return Infinity;
  // Sample every other pixel: at pyramid resolutions this halves the cost with no measurable
  // effect on the chosen offset.
  for (let y = y0; y < y1; y += 2) {
    for (let x = x0; x < x1; x += 2) {
      sum += Math.abs(a.data[y * a.w + x]! - b.data[(y + oy) * b.w + (x + ox)]!);
      n++;
    }
  }
  return n ? sum / n : Infinity;
}

/**
 * Coarse-to-fine translation search. Plot-origin drift between issues of the same sheet is small
 * but never zero; without this, a diff of two nearly identical sheets lights up every line on it.
 */
function alignTranslation(a: Raster, b: Raster): { x: number; y: number; score: number } {
  const levels = [8, 4, 2, 1];
  let best = { x: 0, y: 0 };
  let score = Infinity;
  for (const f of levels) {
    const da = f === 1 ? a : downsample(a, f);
    const db = f === 1 ? b : downsample(b, f);
    // At the coarsest level search a wide window; afterwards only refine around the current guess.
    const span = f === levels[0] ? 12 : 2;
    const cx = Math.round(best.x / f), cy = Math.round(best.y / f);
    let bestScore = Infinity, bx = cx, by = cy;
    for (let oy = cy - span; oy <= cy + span; oy++) {
      for (let ox = cx - span; ox <= cx + span; ox++) {
        const s = misfit(da, db, ox, oy);
        if (s < bestScore) { bestScore = s; bx = ox; by = oy; }
      }
    }
    best = { x: bx * f, y: by * f };
    score = bestScore;
  }
  return { ...best, score };
}

/**
 * Translation *and* uniform scale.
 *
 * Candidate scales are tried coarsely and the best one refined, because a full joint search over
 * scale and translation is quadratically more expensive and the answer is nearly always 1. The
 * candidates cover the paper-size ratios that actually occur (ARCH C↔D↔E, A1↔A0) plus a little
 * slack for scanner drift.
 *
 * Rotation is deliberately not searched: re-issues are essentially never rotated, and adding a
 * third parameter to a brute-force search costs more than it returns. A skewed *scan* needs proper
 * phase correlation rather than a wider grid.
 */
function alignSimilarity(a: Raster, b: Raster, trySize: boolean): { x: number; y: number; scale: number } {
  const flat = alignTranslation(a, b);
  if (!trySize) return { x: flat.x, y: flat.y, scale: 1 };

  let best = { x: flat.x, y: flat.y, scale: 1, score: flat.score };
  const coarse = [0.707, 0.773, 0.816, 0.94, 0.97, 1.03, 1.06, 1.225, 1.294, 1.414];
  for (const k of coarse) {
    const scaled = resample(b, k);
    const t = alignTranslation(a, scaled);
    if (t.score < best.score) best = { x: t.x, y: t.y, scale: k, score: t.score };
  }
  // Refine around whichever scale won, unless it was the identity.
  if (best.scale !== 1) {
    for (const d of [-0.02, -0.01, 0.01, 0.02]) {
      const k = best.scale + d;
      const t = alignTranslation(a, resample(b, k));
      if (t.score < best.score) best = { x: t.x, y: t.y, scale: k, score: t.score };
    }
  }
  return { x: best.x, y: best.y, scale: best.scale };
}

/** Union-find over a coarse grid of changed cells, so adjacent changes become one region. */
function clusterRegions(
  changed: Uint8Array, w: number, h: number, cell: number, minCluster: number,
): DiffRegion[] {
  const gw = Math.ceil(w / cell), gh = Math.ceil(h / cell);
  const weight = new Int32Array(gw * gh);
  for (let y = 0; y < h; y++) {
    for (let x = 0; x < w; x++) {
      if (changed[y * w + x]) weight[Math.floor(y / cell) * gw + Math.floor(x / cell)]!++;
    }
  }
  const seen = new Uint8Array(gw * gh);
  const out: DiffRegion[] = [];
  const stack: number[] = [];
  for (let i = 0; i < weight.length; i++) {
    if (seen[i] || !weight[i]) continue;
    // Flood fill this component, including diagonal neighbours so an L-shaped change is one region.
    stack.push(i);
    seen[i] = 1;
    let minX = gw, minY = gh, maxX = -1, maxY = -1, total = 0;
    while (stack.length) {
      const c = stack.pop()!;
      const cxi = c % gw, cyi = Math.floor(c / gw);
      total += weight[c]!;
      if (cxi < minX) minX = cxi; if (cxi > maxX) maxX = cxi;
      if (cyi < minY) minY = cyi; if (cyi > maxY) maxY = cyi;
      for (let dy = -1; dy <= 1; dy++) {
        for (let dx = -1; dx <= 1; dx++) {
          const nx = cxi + dx, ny = cyi + dy;
          if (nx < 0 || ny < 0 || nx >= gw || ny >= gh) continue;
          const ni = ny * gw + nx;
          if (seen[ni] || !weight[ni]) continue;
          seen[ni] = 1;
          stack.push(ni);
        }
      }
    }
    if (total < minCluster) continue;
    out.push({
      x: minX * cell, y: minY * cell,
      w: (maxX - minX + 1) * cell, h: (maxY - minY + 1) * cell,
      weight: total,
    });
  }
  return out.sort((p, q) => q.weight - p.weight);
}

/** Compare one page of `current` against one page of `previous`. */
export async function comparePages(
  current: PdfDocument,
  previous: PdfDocument,
  currentPage: number,
  previousPage: number,
  options: CompareOptions = {},
): Promise<CompareResult> {
  const resolution = options.resolution ?? 1400;
  const threshold = options.threshold ?? 0.28;
  const minCluster = options.minCluster ?? 24;

  const [a, rawB] = await Promise.all([
    rasterise(current, currentPage, resolution),
    rasterise(previous, previousPage, resolution),
  ]);
  const fit = alignSimilarity(a, rawB, options.matchScale ?? false);
  // Resample once with the winning scale, then treat the rest as a pure translation.
  const b = resample(rawB, fit.scale);
  const shift = { x: fit.x, y: fit.y };

  const changed = new Uint8Array(a.w * a.h);
  let count = 0;
  for (let y = 0; y < a.h; y++) {
    const sy = y + shift.y;
    for (let x = 0; x < a.w; x++) {
      const sx = x + shift.x;
      // Outside the overlap one sheet has no opinion; treat that as unchanged rather than as a
      // sheet-wide edge artefact.
      if (sx < 0 || sy < 0 || sx >= b.w || sy >= b.h) continue;
      if (Math.abs(a.data[y * a.w + x]! - b.data[sy * b.w + sx]!) > threshold) {
        changed[y * a.w + x] = 1;
        count++;
      }
    }
  }

  const cell = Math.max(4, Math.round(a.w / 120));
  const regions = clusterRegions(changed, a.w, a.h, cell, minCluster).map((r) => ({
    // Raster px → page points, with a small margin so the cloud sits outside the changed linework.
    x: r.x / a.scale - 4,
    y: r.y / a.scale - 4,
    w: r.w / a.scale + 8,
    h: r.h / a.scale + 8,
    weight: r.weight,
  }));

  return {
    offset: { x: shift.x / a.scale, y: shift.y / a.scale },
    scale: fit.scale,
    regions,
    changedFraction: count / (a.w * a.h),
  };
}

/**
 * The light-table view: the previous revision tinted and multiplied under the current sheet, so
 * removed content reads as one colour and added content as another.
 */
async function buildOverlay(v: Viewer, previous: PdfDocument, options: CompareOptions): Promise<HTMLCanvasElement> {
  const page = v.page;
  const prevPage = Math.min(page, previous.numPages);
  const [a, rawB] = await Promise.all([
    rasterise(v.doc!, page, options.resolution ?? 1400),
    rasterise(previous, prevPage, options.resolution ?? 1400),
  ]);
  const fit = alignSimilarity(a, rawB, options.matchScale ?? false);
  const b = resample(rawB, fit.scale);
  const shift = { x: fit.x, y: fit.y };

  const canvas = document.createElement("canvas");
  canvas.className = "mpdf-compare-overlay";
  canvas.width = a.w; canvas.height = a.h;
  const ctx = canvas.getContext("2d")!;
  const img = ctx.createImageData(a.w, a.h);
  for (let y = 0; y < a.h; y++) {
    for (let x = 0; x < a.w; x++) {
      const i = y * a.w + x;
      const cur = a.data[i]!;
      const sx = x + shift.x, sy = y + shift.y;
      const old = sx >= 0 && sy >= 0 && sx < b.w && sy < b.h ? b.data[sy * b.w + sx]! : 1;
      // Ink only in the old sheet → blue (removed); only in the new → red (added); both → grey.
      const p = i * 4;
      img.data[p] = Math.round(255 * Math.min(1, old + 0.15));
      img.data[p + 1] = Math.round(255 * Math.min(cur, old));
      img.data[p + 2] = Math.round(255 * Math.min(1, cur + 0.15));
      img.data[p + 3] = 255;
    }
  }
  ctx.putImageData(img, 0, 0);

  const wrap = v.el.pages.querySelector<HTMLElement>(`.mpdf-page-wrap[data-page="${page}"]`);
  if (!wrap) throw new Error(`page ${page} is not mounted`);
  canvas.style.cssText = "position:absolute;inset:0;width:100%;height:100%;pointer-events:none;opacity:0.85;z-index:2";
  wrap.appendChild(canvas);
  return canvas;
}

function pickFile(): Promise<File | null> {
  return new Promise((resolve) => {
    const input = document.createElement("input");
    input.type = "file";
    input.accept = ".pdf,application/pdf";
    input.onchange = () => resolve(input.files?.[0] ?? null);
    input.oncancel = () => resolve(null);
    input.click();
  });
}

declare module "../core/viewer" {
  interface Viewer {
    /** Present once the compare plugin is installed. */
    compare?: {
      result(): CompareResult | null;
      run(viewer: Viewer): Promise<CompareResult | null>;
    };
  }
}

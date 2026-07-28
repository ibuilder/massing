/**
 * Page rasterisation, with tiling.
 *
 * A D-size sheet at 800% is roughly 27k × 17k device pixels — an order of magnitude past the
 * ~16 384 px per-side and ~256 MP total limits browsers enforce on a single canvas, so the naive
 * "one canvas per page" approach silently produces a blank sheet exactly when an estimator zooms in
 * to read a dimension. Above a threshold this renders the *visible* region as a grid of modest
 * canvases and drops tiles that scroll away.
 *
 * pdf.js has no crop-aware operator list, but it does accept a pre-viewport `transform`, so each
 * tile replays the same operator list translated into its own origin. That is the documented way to
 * tile and it is what this does.
 */
import type { PdfDocument } from "./document";
import type { RenderTask } from "pdfjs-dist";

/** Per-side and total-area budgets. Conservative enough for mobile Safari, which is the tightest. */
const MAX_SIDE = 4096;
const MAX_AREA = 4096 * 4096;
/** Tile edge in device pixels. Big enough that a page needs few tiles, small enough to allocate fast. */
const TILE = 1024;
/** Render this much beyond the viewport so a slow scroll doesn't chase the raster. */
const OVERSCAN = 256;

export interface Rect { x: number; y: number; w: number; h: number }

interface Tile {
  key: string;
  canvas: HTMLCanvasElement;
  /** Tile box in CSS px within the scaled page. */
  box: Rect;
  task?: RenderTask;
  done: boolean;
}

export interface PageViewOpts {
  doc: PdfDocument;
  page: number;
  /** Device pixel ratio to raster at. Clamped — a 3× phone DPR on a 400% zoom is wasted work. */
  dpr?: number;
  onRendered?: (page: number, scale: number) => void;
}

/**
 * One page's raster surface. Owns a positioned `<div>` containing one or more canvases; the caller
 * positions that div and tells it which part is on screen.
 */
export class PageView {
  readonly el: HTMLDivElement;
  readonly page: number;

  private doc: PdfDocument;
  private tiles = new Map<string, Tile>();
  private scale = 1;
  private rotation = 0;
  /** CSS size of the scaled page. */
  private cssW = 0;
  private cssH = 0;
  private dpr: number;
  private onRendered: ((page: number, scale: number) => void) | undefined;
  private destroyed = false;
  /** Bumped whenever scale/rotation changes, so in-flight renders for a stale scale are discarded. */
  private generation = 0;

  constructor(o: PageViewOpts) {
    this.doc = o.doc;
    this.page = o.page;
    this.dpr = Math.min(o.dpr ?? (globalThis.devicePixelRatio || 1), 2);
    this.onRendered = o.onRendered;
    this.el = document.createElement("div");
    this.el.className = "mpdf-page";
    this.el.dataset.page = String(o.page);
  }

  /** CSS size of the page at the current scale/rotation. */
  get size(): { w: number; h: number } { return { w: this.cssW, h: this.cssH }; }

  /**
   * Set zoom and rotation. Discards every raster: the old tiles are the wrong resolution, and
   * keeping them stretched looks worse than a brief blank.
   */
  async setTransform(scale: number, rotation: number): Promise<void> {
    if (scale === this.scale && rotation === this.rotation && this.cssW) return;
    this.scale = scale;
    this.rotation = ((rotation % 360) + 360) % 360;
    this.generation++;
    this.clearTiles();
    const info = await this.doc.pageInfo(this.page);
    const swap = this.rotation === 90 || this.rotation === 270;
    this.cssW = (swap ? info.height : info.width) * scale;
    this.cssH = (swap ? info.width : info.height) * scale;
    this.el.style.width = `${this.cssW}px`;
    this.el.style.height = `${this.cssH}px`;
  }

  /** True when this page is small enough to live on one canvas. */
  private get single(): boolean {
    const w = this.cssW * this.dpr, h = this.cssH * this.dpr;
    return w <= MAX_SIDE && h <= MAX_SIDE && w * h <= MAX_AREA;
  }

  /**
   * Raster whatever of `visible` (CSS px, page-local) isn't already painted, and evict tiles well
   * outside it. Safe to call on every scroll frame — it is a no-op once the region is covered.
   */
  async update(visible: Rect): Promise<void> {
    if (this.destroyed || !this.cssW) return;
    const gen = this.generation;
    const want = this.single
      ? [{ x: 0, y: 0, w: this.cssW, h: this.cssH }]
      : tileBoxes(this.cssW, this.cssH, grow(visible, OVERSCAN), TILE / this.dpr);

    const wanted = new Set(want.map(boxKey));
    for (const [key, tile] of this.tiles) {
      if (wanted.has(key)) continue;
      tile.task?.cancel();
      tile.canvas.remove();
      this.tiles.delete(key);
    }
    await Promise.all(want.map((box) => this.renderTile(box, gen)));
    if (gen === this.generation && !this.destroyed) this.onRendered?.(this.page, this.scale);
  }

  private async renderTile(box: Rect, gen: number): Promise<void> {
    const key = boxKey(box);
    if (this.tiles.has(key)) return;

    const canvas = document.createElement("canvas");
    canvas.className = "mpdf-tile";
    canvas.style.position = "absolute";
    canvas.style.left = `${box.x}px`;
    canvas.style.top = `${box.y}px`;
    canvas.style.width = `${box.w}px`;
    canvas.style.height = `${box.h}px`;
    canvas.width = Math.max(1, Math.round(box.w * this.dpr));
    canvas.height = Math.max(1, Math.round(box.h * this.dpr));

    const tile: Tile = { key, canvas, box, done: false };
    this.tiles.set(key, tile);
    this.el.appendChild(canvas);

    const pg = await this.doc.page(this.page);
    if (gen !== this.generation || this.destroyed) { canvas.remove(); this.tiles.delete(key); return; }

    const ctx = canvas.getContext("2d", { alpha: false });
    if (!ctx) return;
    ctx.fillStyle = "#fff";
    ctx.fillRect(0, 0, canvas.width, canvas.height);

    const viewport = pg.getViewport({ scale: this.scale * this.dpr, rotation: this.rotation });
    // Shift the page so this tile's top-left lands at the canvas origin.
    const transform = [1, 0, 0, 1, -box.x * this.dpr, -box.y * this.dpr];

    try {
      const task = pg.render({ canvas, canvasContext: ctx, viewport, transform });
      tile.task = task;
      await task.promise;
      tile.done = true;
    } catch (e) {
      // A cancelled render is the normal outcome of scrolling; anything else is worth surfacing.
      if (!(e as { name?: string })?.name?.includes("Cancel")) {
        console.warn(`[massing-pdf] page ${this.page} tile render failed`, e);
      }
      canvas.remove();
      this.tiles.delete(key);
    }
  }

  private clearTiles(): void {
    for (const t of this.tiles.values()) { t.task?.cancel(); t.canvas.remove(); }
    this.tiles.clear();
  }

  /** Drop rasters but keep the element and its size — for pages scrolled far out of view. */
  release(): void { this.clearTiles(); }

  destroy(): void {
    this.destroyed = true;
    this.clearTiles();
    this.el.remove();
  }
}

const boxKey = (b: Rect): string => `${Math.round(b.x)}:${Math.round(b.y)}:${Math.round(b.w)}:${Math.round(b.h)}`;

const grow = (r: Rect, by: number): Rect => ({ x: r.x - by, y: r.y - by, w: r.w + by * 2, h: r.h + by * 2 });

/** The grid boxes covering `visible` within a `w × h` page, clipped to the page. */
export function tileBoxes(w: number, h: number, visible: Rect, tile: number): Rect[] {
  const out: Rect[] = [];
  const x0 = Math.max(0, Math.floor(visible.x / tile) * tile);
  const y0 = Math.max(0, Math.floor(visible.y / tile) * tile);
  const x1 = Math.min(w, visible.x + visible.w);
  const y1 = Math.min(h, visible.y + visible.h);
  for (let y = y0; y < y1; y += tile) {
    for (let x = x0; x < x1; x += tile) {
      const bw = Math.min(tile, w - x), bh = Math.min(tile, h - y);
      if (bw > 0 && bh > 0) out.push({ x, y, w: bw, h: bh });
    }
  }
  return out;
}

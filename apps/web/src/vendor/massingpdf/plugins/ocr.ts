/**
 * OCR for scanned sheets.
 *
 * Scanned drawings and archive material carry no text layer, so search, spec parsing and
 * title-block extraction all return nothing on them. They degrade gracefully — but they degrade to
 * empty, which is the single thing that most limits this engine on real archive work.
 *
 * **The engine is not bundled.** Two constraints pull opposite ways: the viewer must run fully
 * offline (so a server call is not always available), and it must stay a library you can drop into
 * an app (so several megabytes of WASM cannot be a default dependency). Resolving that by picking
 * one would be wrong for half of all consumers, so OCR is a *provider interface*: this plugin owns
 * the rasterisation, the coordinate mapping and the wiring into search and specs, and the host
 * supplies the recogniser — a server endpoint, a bundled WASM engine, or a cloud API.
 *
 * `tesseractProvider()` is included for the offline case and dynamically imports `tesseract.js`, so
 * a consumer that never calls it pays nothing.
 */
import { definePlugin } from "../core/plugin";
import type { TextItem } from "../core/document";
import type { Pt } from "../core/types";
import type { Viewer } from "../core/viewer";

/**
 * One rasterised tile handed to a recogniser.
 *
 * A tile, not a page: a 36×24" sheet at the 300 DPI that OCR needs is 78 megapixels, which exceeds
 * the canvas budget on mobile Safari and every cloud OCR service's per-image cap. Sheets are cut
 * into overlapping tiles and the results stitched back together.
 */
export interface OcrInput {
  page: number;
  /** The rasterised tile. Providers that need bytes can call `canvas.toBlob`. */
  canvas: HTMLCanvasElement;
  /** Tile size in pixels. */
  width: number;
  height: number;
  /** Pixels per PDF point, for mapping results back to page space. */
  scale: number;
  /** The tile's origin in page space, added back when results are mapped. */
  offset: Pt;
  /** Position in the grid, for progress reporting. */
  index: number;
  count: number;
}

/** One recognised word, in **raster pixels**. The plugin converts to page space. */
export interface OcrWord {
  text: string;
  x: number; y: number; w: number; h: number;
  /** 0..1. Words below `minConfidence` are dropped. */
  confidence?: number;
}

export interface OcrResult {
  words: OcrWord[];
}

export interface OcrProvider {
  id: string;
  recognise(input: OcrInput): Promise<OcrResult>;
  /** Release any engine resources. */
  dispose?(): Promise<void> | void;
}

export interface OcrOptions {
  provider?: OcrProvider;
  /**
   * Target resolution in DPI.
   *
   * 300 is the floor, not a nicety: recognition needs roughly 18–20 pixels of character height, and
   * the smallest lettering on a construction drawing is 1/8" — 37 px at 300 DPI, 9 px at the 72 DPI
   * a whole D sheet fits into. Raise to 400–600 for faint scans or 3/32" lettering.
   */
  dpi?: number;
  /**
   * Ceiling on a single tile, in megapixels. The default clears mobile Safari's canvas limit and
   * sits under the per-image caps of the major OCR services.
   */
  maxTileMegapixels?: number;
  /**
   * Overlap between tiles, in PDF points. A word straddling a seam has to appear whole in at least
   * one tile, so this wants to exceed the longest word you care about — roughly 1" of drawing.
   */
  overlapPoints?: number;
  /** Drop words the engine is less sure of than this. */
  minConfidence?: number;
  /** Recognise every text-less page as soon as a document loads. Off by default — it is expensive. */
  auto?: boolean;
}

export function ocrPlugin(options: OcrOptions = {}) {
  const minConfidence = options.minConfidence ?? 0.4;
  const dpi = options.dpi ?? 300;
  const maxTilePixels = (options.maxTileMegapixels ?? 12) * 1e6;
  const overlap = options.overlapPoints ?? 72;

  return definePlugin({
    id: "ocr",
    order: 12,
    setup(ctx) {
      const provider = options.provider;
      let busy = false;

      ctx.onCleanup(() => { void provider?.dispose?.(); });

      const recognisePage = async (v: Viewer, page: number): Promise<number> => {
        if (!provider || !v.doc) return 0;
        const plan = await planTiles(v, page, { dpi, maxTilePixels, overlap });
        const collected: TextItem[] = [];

        for (const spec of plan) {
          const input = await renderTile(v, page, spec);
          try {
            const { words } = await provider.recognise(input);
            collected.push(...toTextItems(words, input.scale, minConfidence, input.offset));
          } finally {
            // A D sheet at 300 DPI is ~78 MP across its tiles; holding them all would exhaust
            // memory long before the page finished.
            releaseCanvas(input.canvas);
          }
          if (plan.length > 1) {
            v.bus.emit("notice", {
              level: "info",
              message: `Reading page ${page}, tile ${spec.index + 1} of ${plan.length}…`,
            });
          }
        }

        const items = dedupeWords(collected);
        v.setRecognisedText(page, items);
        return items.length;
      };

      const run = async (v: Viewer, pages: number[]): Promise<void> => {
        if (!provider) {
          v.bus.emit("notice", {
            level: "warn",
            message: "No OCR engine configured — pass a provider to ocrPlugin() to read scanned sheets.",
          });
          return;
        }
        if (busy) return;
        busy = true;
        let total = 0;
        try {
          for (let i = 0; i < pages.length; i++) {
            const page = pages[i]!;
            v.bus.emit("notice", { level: "info", message: `Reading page ${page} (${i + 1} of ${pages.length})…` });
            total += await recognisePage(v, page);
          }
          v.bus.emit("notice", {
            level: total ? "success" : "warn",
            message: total
              ? `Recognised ${total} words across ${pages.length} page${pages.length === 1 ? "" : "s"}. Search and specifications now cover them.`
              : "No text recognised on those pages.",
          });
        } catch (e) {
          v.bus.emit("notice", { level: "error", message: `OCR failed: ${(e as Error).message}` });
        } finally {
          busy = false;
        }
      };

      /** Pages with neither a text layer nor recognised text. */
      const pending = async (v: Viewer): Promise<number[]> => {
        const out: number[] = [];
        for (let p = 1; p <= v.numPages; p++) if (await v.needsText(p)) out.push(p);
        return out;
      };

      ctx.registerAction({
        id: "ocr.page", label: "Read this page (OCR)", icon: "👁", group: "archive",
        enabled: (v) => Boolean(provider && v.doc),
        run: (v) => run(v, [v.page]),
      });

      ctx.registerAction({
        id: "ocr.document", label: "Read every scanned page (OCR)", icon: "👁▤", group: "archive",
        enabled: (v) => Boolean(provider && v.doc),
        async run(v) {
          const pages = await pending(v);
          if (!pages.length) {
            v.bus.emit("notice", { level: "info", message: "Every page already has text — nothing to recognise." });
            return;
          }
          await run(v, pages);
        },
      });

      if (options.auto) {
        ctx.bus.on("doc:loaded", () => {
          void (async () => {
            const pages = await pending(ctx.viewer);
            if (pages.length) await run(ctx.viewer, pages);
          })();
        });
      }

      ctx.viewer.ocr = {
        available: () => Boolean(provider),
        recognisePage: (page: number) => recognisePage(ctx.viewer, page),
        recogniseDocument: async () => { await run(ctx.viewer, await pending(ctx.viewer)); },
        pendingPages: () => pending(ctx.viewer),
      };
    },
  });
}

/** One tile to render: a page-space rectangle, plus where it sits in the grid. */
interface TileSpec {
  x: number; y: number; w: number; h: number;
  scale: number;
  index: number;
  count: number;
}

export interface TilePlanOptions {
  dpi: number;
  maxTilePixels: number;
  overlap: number;
}

/**
 * Work out how to cut a page into tiles that hit the target DPI without exceeding the per-tile
 * pixel budget.
 *
 * Exported and free of the DOM so the arithmetic — the part that decides whether OCR sees readable
 * characters at all — can be tested directly.
 */
export function planTileGrid(
  pageWidth: number,
  pageHeight: number,
  { dpi, maxTilePixels, overlap }: TilePlanOptions,
): TileSpec[] {
  // A PDF point is 1/72", so DPI converts straight into a raster scale.
  const scale = dpi / 72;
  const fullPixels = pageWidth * scale * pageHeight * scale;

  // How many tiles per axis, keeping them roughly square rather than long strips — a strip wastes
  // budget on one axis and multiplies seams on the other.
  const divisions = Math.max(1, Math.ceil(Math.sqrt(fullPixels / maxTilePixels)));
  const tileW = pageWidth / divisions;
  const tileH = pageHeight / divisions;

  const specs: TileSpec[] = [];
  for (let row = 0; row < divisions; row++) {
    for (let col = 0; col < divisions; col++) {
      // Grown by the overlap and clipped to the page, so a word on a seam is whole somewhere.
      const x = Math.max(0, col * tileW - overlap);
      const y = Math.max(0, row * tileH - overlap);
      const right = Math.min(pageWidth, (col + 1) * tileW + overlap);
      const bottom = Math.min(pageHeight, (row + 1) * tileH + overlap);
      specs.push({
        x, y, w: right - x, h: bottom - y,
        scale, index: specs.length, count: divisions * divisions,
      });
    }
  }
  return specs;
}

async function planTiles(v: Viewer, page: number, opts: TilePlanOptions): Promise<TileSpec[]> {
  const info = await v.doc!.pageInfo(page);
  return planTileGrid(info.width, info.height, opts);
}

/** Rasterise one tile at the planned scale. */
async function renderTile(v: Viewer, page: number, spec: TileSpec): Promise<OcrInput> {
  const doc = v.doc!;
  const width = Math.max(1, Math.round(spec.w * spec.scale));
  const height = Math.max(1, Math.round(spec.h * spec.scale));

  const canvas = document.createElement("canvas");
  canvas.width = width;
  canvas.height = height;
  const ctx = canvas.getContext("2d", { alpha: false, willReadFrequently: true });
  if (!ctx) throw new Error("2D canvas unavailable");
  ctx.fillStyle = "#fff";
  ctx.fillRect(0, 0, width, height);

  const pg = await doc.page(page);
  await pg.render({
    canvas,
    canvasContext: ctx,
    viewport: pg.getViewport({ scale: spec.scale }),
    // Shift the page so this tile's corner lands at the canvas origin — the same trick the screen
    // renderer uses, since pdf.js has no crop-aware operator list.
    transform: [1, 0, 0, 1, -spec.x * spec.scale, -spec.y * spec.scale],
  }).promise;

  return {
    page, canvas, width, height,
    scale: spec.scale,
    offset: { x: spec.x, y: spec.y },
    index: spec.index,
    count: spec.count,
  };
}

/** Drop a tile's backing store immediately rather than waiting for GC. */
function releaseCanvas(canvas: HTMLCanvasElement): void {
  canvas.width = 0;
  canvas.height = 0;
}

/**
 * Merge words recognised more than once because they fell in a tile overlap.
 *
 * Same text in nearly the same place is the same word; the copy the engine was more sure of wins,
 * which is usually the tile where it sat further from an edge.
 */
export function dedupeWords(items: readonly TextItem[]): TextItem[] {
  const kept: TextItem[] = [];
  for (const item of items) {
    const duplicate = kept.findIndex((k) =>
      k.str === item.str
      // Within half a character height counts as the same position: the two tiles rasterised the
      // same glyphs, so any difference is rounding.
      && Math.abs(k.x - item.x) < item.h * 0.5
      && Math.abs(k.y - item.y) < item.h * 0.5);
    if (duplicate < 0) { kept.push(item); continue; }
    // Wider box means the word was less clipped by the seam; prefer it.
    if (item.w > kept[duplicate]!.w) kept[duplicate] = item;
  }
  return kept;
}

/**
 * Recognised words → the same `TextItem` shape pdf.js produces, in page space.
 *
 * Emitting the *native* shape is the whole trick: search, spec parsing and title-block extraction
 * all consume `TextItem`, so once OCR output is in that shape none of them needs to know whether a
 * page's text came from the PDF or from a recogniser.
 */
export function toTextItems(
  words: readonly OcrWord[],
  scale: number,
  minConfidence = 0.4,
  offset: Pt = { x: 0, y: 0 },
): TextItem[] {
  return words
    .filter((w) => w.text.trim() && (w.confidence ?? 1) >= minConfidence)
    .map((w) => ({
      str: w.text,
      // Tile-relative pixels → page points, then back into the page's own coordinates.
      x: w.x / scale + offset.x,
      y: w.y / scale + offset.y,
      w: w.w / scale,
      h: w.h / scale,
    }));
}

/**
 * A Tesseract-backed provider, loaded on demand.
 *
 * `tesseract.js` is not a dependency of this package — install it in the host if you want offline
 * OCR. The dynamic import means a consumer who never calls this function never downloads it.
 */
export function tesseractProvider(opts: {
  lang?: string;
  workerPath?: string;
  corePath?: string;
  langPath?: string;
  /**
   * Supply the module yourself instead of letting this import it.
   *
   * The default import is opaque to bundlers so consumers who never call this do not need
   * `tesseract.js` installed — but that leaves the browser a bare specifier it cannot resolve. A
   * host that bundles the package, or a test that needs it to load for real, passes it in.
   */
  load?: () => Promise<unknown>;
} = {}): OcrProvider {
  /**
   * The shapes across tesseract.js versions.
   *
   * Word boxes moved. Up to v5 they were a flat `data.words`; from v6 they are nested inside
   * `blocks → paragraphs → lines → words`, and `blocks` is only populated when the third argument
   * asks for it. Requesting nothing returns plain text and no coordinates at all — which does not
   * throw, it just silently yields zero words, and looks exactly like an engine that failed to read
   * the page.
   */
  interface TessWord { text: string; confidence: number; bbox: { x0: number; y0: number; x1: number; y1: number } }
  interface TessPage {
    words?: TessWord[];
    blocks?: { paragraphs?: { lines?: { words?: TessWord[] }[] }[] }[] | null;
  }
  type TesseractWorker = {
    recognize(
      image: HTMLCanvasElement,
      options?: Record<string, unknown>,
      output?: Record<string, boolean>,
    ): Promise<{ data: TessPage }>;
    terminate(): Promise<void>;
  };
  let worker: TesseractWorker | null = null;

  const ensure = async (): Promise<TesseractWorker> => {
    if (worker) return worker;
    type TesseractModule = { createWorker: (lang?: string, oem?: number, config?: object) => Promise<TesseractWorker> };
    let mod: TesseractModule;
    try {
      // The specifier is indirect on purpose. `tesseract.js` is not a dependency of this package,
      // so a literal import would fail typecheck here and make bundlers try to resolve a module
      // most consumers will never install.
      const specifier = "tesseract.js";
      mod = (opts.load
        ? await opts.load()
        : await import(/* @vite-ignore */ specifier)) as TesseractModule;
      if (!mod?.createWorker) throw new Error("no createWorker export");
    } catch (e) {
      throw new Error(
        "tesseractProvider() could not load `tesseract.js`. Install it in the host application " +
        `(npm install tesseract.js), or pass \`load\` to supply the module yourself. Cause: ${(e as Error).message}`,
        { cause: e },
      );
    }
    worker = await mod.createWorker(opts.lang ?? "eng", 1, {
      ...(opts.workerPath ? { workerPath: opts.workerPath } : {}),
      ...(opts.corePath ? { corePath: opts.corePath } : {}),
      ...(opts.langPath ? { langPath: opts.langPath } : {}),
    });
    return worker;
  };

  /** Flatten whichever shape this version returned. */
  const wordsOf = (data: TessPage): TessWord[] => {
    if (data.words?.length) return data.words;
    const out: TessWord[] = [];
    for (const block of data.blocks ?? []) {
      for (const para of block.paragraphs ?? []) {
        for (const line of para.lines ?? []) {
          for (const word of line.words ?? []) out.push(word);
        }
      }
    }
    return out;
  };

  return {
    id: "tesseract",
    async recognise({ canvas }) {
      const w = await ensure();
      // `blocks: true` is what makes coordinates come back at all on v6+.
      const { data } = await w.recognize(canvas, {}, { blocks: true });
      return {
        words: wordsOf(data).map((word) => ({
          text: word.text,
          x: word.bbox.x0,
          y: word.bbox.y0,
          w: word.bbox.x1 - word.bbox.x0,
          h: word.bbox.y1 - word.bbox.y0,
          confidence: word.confidence > 1 ? word.confidence / 100 : word.confidence,
        })),
      };
    },
    async dispose() {
      await worker?.terminate();
      worker = null;
    },
  };
}
/**
 * A provider that posts the page image to a server endpoint. The response must be
 * `{ words: [{ text, x, y, w, h, confidence? }] }` in raster pixels.
 */
export function restOcrProvider(opts: {
  url: string;
  headers?: () => Record<string, string>;
  fieldName?: string;
}): OcrProvider {
  return {
    id: "rest",
    async recognise({ canvas, page }) {
      const blob = await new Promise<Blob | null>((resolve) => canvas.toBlob(resolve, "image/png"));
      if (!blob) throw new Error("could not encode the page image");
      const form = new FormData();
      form.append(opts.fieldName ?? "image", blob, `page-${page}.png`);
      form.append("page", String(page));
      const res = await fetch(opts.url, { method: "POST", body: form, headers: opts.headers?.() });
      if (!res.ok) throw new Error(`OCR service returned HTTP ${res.status}`);
      return (await res.json()) as OcrResult;
    },
  };
}

declare module "../core/viewer" {
  interface Viewer {
    /** Present once the OCR plugin is installed. */
    ocr?: {
      available(): boolean;
      recognisePage(page: number): Promise<number>;
      recogniseDocument(): Promise<void>;
      pendingPages(): Promise<number[]>;
    };
  }
}

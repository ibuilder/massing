/**
 * The pdf.js boundary. Everything that knows pdf.js exists lives in this file and `renderer.ts`;
 * the rest of the engine talks in page numbers, page boxes and page-space points.
 *
 * pdf.js is a *peer* dependency and its worker is never fetched from a CDN — the host bundles it
 * and calls `configureWorker()` once. That is what lets the viewer run in an air-gapped field
 * deployment, which is a hard requirement rather than a nice-to-have.
 */
import * as pdfjs from "pdfjs-dist";
import type { PDFDocumentLoadingTask, PDFDocumentProxy, PDFPageProxy } from "pdfjs-dist";

/**
 * Point the pdf.js worker at a bundled asset. Call once, before `PdfDocument.load`.
 *
 * ```ts
 * import workerUrl from "pdfjs-dist/build/pdf.worker.min.mjs?url";
 * configureWorker(workerUrl);
 * ```
 */
export function configureWorker(src: string): void {
  pdfjs.GlobalWorkerOptions.workerSrc = src;
}

export function workerConfigured(): boolean {
  return Boolean(pdfjs.GlobalWorkerOptions.workerSrc);
}

/**
 * Load options passed to every `getDocument`.
 *
 * `enableScripting: false` was here and is deliberately NOT: it is a pdf.js **viewer** option, not
 * a `getDocument` one — `grep -r enableScripting node_modules/pdfjs-dist/types` returns nothing,
 * and the vendored fork reads it nowhere either. It was a security control consumed by no code,
 * with a test asserting its presence, which is worse than absent: the gate read "PDF scripting is
 * disabled" while the real reason this app is safe is that it never instantiates the scripting
 * engine at all. CVE-2026-16633 is mitigated by the exact version pin, which is now what is gated.
 */
export const PDFJS_LOAD = { cMapPacked: true };

/** Where the bytes come from. */
export type PdfSource =
  | File
  | Blob
  | ArrayBuffer
  | Uint8Array
  | { url: string; name?: string; headers?: Record<string, string> };

export interface PageInfo {
  page: number;
  /** Page box in PDF points at scale 1, **after** the page's intrinsic /Rotate is applied. */
  width: number;
  height: number;
  /** The page's own rotation, degrees. Already folded into width/height. */
  rotation: number;
}

/** A word/line of extracted text with its page-space box — the search index unit. */
export interface TextItem {
  str: string;
  x: number; y: number; w: number; h: number;
}

/** A PDF outline entry, flattened with a depth. */
export interface OutlineItem {
  title: string;
  depth: number;
  page?: number;
}

export class PdfDocument {
  /** The original bytes, kept for the flatten/export path (pdf-lib needs its own copy). */
  readonly bytes: Uint8Array;
  readonly name: string;
  readonly fingerprint: string;

  private pageCache = new Map<number, Promise<PDFPageProxy>>();
  private infoCache = new Map<number, PageInfo>();
  private textCache = new Map<number, Promise<TextItem[]>>();

  private constructor(
    private doc: PDFDocumentProxy,
    private task: PDFDocumentLoadingTask,
    bytes: Uint8Array,
    name: string,
  ) {
    this.bytes = bytes;
    this.name = name;
    this.fingerprint = doc.fingerprints?.[0] ?? name;
  }

  static async load(source: PdfSource, signal?: AbortSignal): Promise<PdfDocument> {
    if (!workerConfigured()) {
      throw new Error(
        "pdf.js worker not configured — call configureWorker(url) with a bundled worker before loading a document.",
      );
    }
    const { bytes, name } = await readSource(source, signal);
    // pdf.js may transfer (and thus detach) the buffer it is handed. Give it a private copy so
    // `this.bytes` stays intact for the export path.
    const task = pdfjs.getDocument({ data: bytes.slice(0), ...PDFJS_LOAD });
    signal?.addEventListener("abort", () => void task.destroy(), { once: true });
    const doc = await task.promise;
    return new PdfDocument(doc, task, bytes, name);
  }

  get numPages(): number { return this.doc.numPages; }

  /** The pdf.js page proxy, memoised. */
  page(n: number): Promise<PDFPageProxy> {
    let p = this.pageCache.get(n);
    if (!p) {
      p = this.doc.getPage(n);
      this.pageCache.set(n, p);
    }
    return p;
  }

  /** Page box at scale 1. Async on first call per page, then served from `pageInfoSync`. */
  async pageInfo(n: number): Promise<PageInfo> {
    const hit = this.infoCache.get(n);
    if (hit) return hit;
    const pg = await this.page(n);
    const vp = pg.getViewport({ scale: 1 });
    const info: PageInfo = { page: n, width: vp.width, height: vp.height, rotation: pg.rotate ?? 0 };
    this.infoCache.set(n, info);
    return info;
  }

  /** Synchronous page box, once `primeInfo` (or a render) has warmed it. */
  pageInfoSync(n: number): PageInfo | undefined { return this.infoCache.get(n); }

  /** Warm the page-box cache for every page. Cheap: no rasterisation, just the viewport. */
  async primeInfo(pages?: number[]): Promise<PageInfo[]> {
    const list = pages ?? range(1, this.numPages);
    return Promise.all(list.map((n) => this.pageInfo(n)));
  }

  /**
   * Extracted text with page-space boxes. Feeds search, title-block detection and the OCR-free
   * path of spec clause anchoring.
   */
  textItems(n: number): Promise<TextItem[]> {
    let p = this.textCache.get(n);
    if (!p) {
      p = this.extractText(n);
      this.textCache.set(n, p);
    }
    return p;
  }

  private async extractText(n: number): Promise<TextItem[]> {
    const pg = await this.page(n);
    const info = await this.pageInfo(n);
    const content = await pg.getTextContent();
    const out: TextItem[] = [];
    for (const raw of content.items) {
      const it = raw as { str?: string; transform?: number[]; width?: number; height?: number };
      if (!it.str || !it.str.trim() || !it.transform) continue;
      const t = it.transform;
      // transform = [a,b,c,d,e,f]; e/f is the baseline origin in PDF space (bottom-left origin).
      const h = it.height ?? Math.abs(t[3] ?? 10);
      const x = t[4] ?? 0;
      const yBottom = t[5] ?? 0;
      out.push({
        str: it.str,
        x,
        y: info.height - yBottom - h,          // → top-left origin, our page space
        w: it.width ?? it.str.length * h * 0.5,
        h,
      });
    }
    return out;
  }

  /** Concatenated page text, for a quick full-text index. */
  async pageText(n: number): Promise<string> {
    return (await this.textItems(n)).map((t) => t.str).join(" ");
  }

  /** Flattened bookmarks, with resolved page numbers where pdf.js can resolve them. */
  async outline(): Promise<OutlineItem[]> {
    const raw = await this.doc.getOutline().catch(() => null);
    if (!raw) return [];
    const out: OutlineItem[] = [];
    const walk = async (nodes: typeof raw, depth: number): Promise<void> => {
      for (const n of nodes ?? []) {
        let page: number | undefined;
        try {
          const dest = typeof n.dest === "string" ? await this.doc.getDestination(n.dest) : n.dest;
          const ref = Array.isArray(dest) ? dest[0] : null;
          if (ref) page = (await this.doc.getPageIndex(ref as Parameters<typeof this.doc.getPageIndex>[0])) + 1;
        } catch { /* an unresolvable destination is still a usable label */ }
        out.push({ title: n.title, depth, ...(page !== undefined ? { page } : {}) });
        if (n.items?.length) await walk(n.items, depth + 1);
      }
    };
    await walk(raw, 0);
    return out;
  }

  /** Document metadata from the PDF info dictionary. */
  async metadata(): Promise<Record<string, string>> {
    try {
      const md = await this.doc.getMetadata();
      const info = (md.info ?? {}) as Record<string, unknown>;
      const out: Record<string, string> = {};
      for (const [k, v] of Object.entries(info)) if (typeof v === "string" && v) out[k] = v;
      return out;
    } catch { return {}; }
  }

  destroy(): void {
    this.pageCache.clear();
    this.textCache.clear();
    this.infoCache.clear();
    // Destroying the loading task tears down the transport *and* the worker port; destroying the
    // proxy alone would leak the worker across document switches.
    void this.task.destroy();
  }
}

/** Normalise every accepted source to bytes plus a display name. */
async function readSource(src: PdfSource, signal?: AbortSignal): Promise<{ bytes: Uint8Array; name: string }> {
  if (src instanceof Uint8Array) return { bytes: src, name: "document.pdf" };
  if (src instanceof ArrayBuffer) return { bytes: new Uint8Array(src), name: "document.pdf" };
  if (isBlobLike(src)) {
    const name = typeof File !== "undefined" && src instanceof File ? src.name : "document.pdf";
    return { bytes: new Uint8Array(await src.arrayBuffer()), name };
  }
  const { url, name, headers } = src;
  const res = await fetch(url, { headers, signal });
  if (!res.ok) throw new Error(`fetch failed: HTTP ${res.status} ${res.statusText}`);
  return {
    bytes: new Uint8Array(await res.arrayBuffer()),
    name: name || url.split("/").pop()?.split("?")[0] || "document.pdf",
  };
}

const isBlobLike = (v: PdfSource): v is Blob =>
  typeof Blob !== "undefined" && v instanceof Blob;

const range = (a: number, b: number): number[] =>
  Array.from({ length: Math.max(0, b - a + 1) }, (_, i) => a + i);

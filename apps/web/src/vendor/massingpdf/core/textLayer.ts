/**
 * A selectable text layer over the raster.
 *
 * Highlighting a specification paragraph by dragging a rectangle around it is a lie: the markup
 * records where the box was, not which words it covered, so it can't survive a re-flow, can't be
 * searched, and can't anchor a spec clause reference. Real text markup needs glyph geometry.
 *
 * This mirrors how pdf.js's own viewer does it: absolutely-positioned transparent spans over the
 * canvas, letting the browser handle selection natively (including double-click-to-word and
 * keyboard selection), then mapping the resulting DOM `Range` back to page-space quads.
 */
import type { PdfDocument, TextItem } from "./document";
import type { Box, Pt } from "./types";

/** A run of selected text with its page-space geometry. */
export interface TextQuad extends Box {
  page: number;
}

export interface TextSelection {
  text: string;
  page: number;
  quads: TextQuad[];
  /** Union of the quads — the anchor for a markup that needs a single box. */
  bounds: Box;
}

/** One word, with its page-space box. The unit the search index works in. */
export interface Word {
  str: string;
  x: number; y: number; w: number; h: number;
  /** Index of the source text item, so callers can recover the full run. */
  item: number;
}

/**
 * Split text items into words with estimated boxes.
 *
 * pdf.js reports geometry per *item*, which is usually a run of several words, so word boxes are
 * apportioned by character count. That is an approximation — proportional fonts make `illi` narrower
 * than `WWWW` — but it is accurate to within a character's width, which is enough for a search hit
 * to be findable and a highlight to land on the right line.
 */
export function splitWords(items: readonly TextItem[]): Word[] {
  const out: Word[] = [];
  items.forEach((item, i) => {
    const text = item.str;
    if (!text.trim()) return;
    const perChar = text.length ? item.w / text.length : 0;
    // Walk the run, emitting a Word for each whitespace-delimited token.
    let start = 0;
    const flush = (end: number) => {
      const str = text.slice(start, end);
      if (str.trim()) {
        out.push({
          str,
          x: item.x + start * perChar,
          y: item.y,
          w: str.length * perChar,
          h: item.h,
          item: i,
        });
      }
      start = end + 1;
    };
    for (let c = 0; c < text.length; c++) if (/\s/.test(text[c]!)) flush(c);
    flush(text.length);
  });
  return out;
}

/**
 * Merge quads that sit on the same line into one box per line, so a multi-line selection produces
 * one highlight per line rather than one per word.
 */
export function mergeByLine(quads: TextQuad[]): TextQuad[] {
  if (!quads.length) return [];
  const sorted = [...quads].sort((a, b) => a.y - b.y || a.x - b.x);
  const lines: TextQuad[] = [];
  for (const q of sorted) {
    const last = lines[lines.length - 1];
    // Same line when the vertical centres are within half a line height of each other.
    const sameLine = last
      && Math.abs((q.y + q.h / 2) - (last.y + last.h / 2)) < Math.max(q.h, last.h) * 0.5
      && q.page === last.page;
    if (sameLine) {
      const right = Math.max(last.x + last.w, q.x + q.w);
      const top = Math.min(last.y, q.y);
      const bottom = Math.max(last.y + last.h, q.y + q.h);
      last.x = Math.min(last.x, q.x);
      last.w = right - last.x;
      last.y = top;
      last.h = bottom - top;
    } else {
      lines.push({ ...q });
    }
  }
  return lines;
}

export const unionBox = (boxes: readonly Box[]): Box => {
  if (!boxes.length) return { x: 0, y: 0, w: 0, h: 0 };
  const x0 = Math.min(...boxes.map((b) => b.x));
  const y0 = Math.min(...boxes.map((b) => b.y));
  const x1 = Math.max(...boxes.map((b) => b.x + b.w));
  const y1 = Math.max(...boxes.map((b) => b.y + b.h));
  return { x: x0, y: y0, w: x1 - x0, h: y1 - y0 };
};

/**
 * The DOM text layer for one page.
 *
 * Spans are sized in page units and scaled by a CSS transform on the container, so a zoom change is
 * one style write rather than a rebuild of several thousand elements.
 */
export class TextLayer {
  readonly el: HTMLDivElement;
  readonly page: number;

  private doc: PdfDocument;
  private items: TextItem[] = [];
  private built = false;
  private scale = 1;

  constructor(doc: PdfDocument, page: number) {
    this.doc = doc;
    this.page = page;
    this.el = document.createElement("div");
    this.el.className = "mpdf-textlayer";
    this.el.dataset.page = String(page);
    // Off until a tool wants it: it must never swallow a click meant for a markup.
    this.el.style.pointerEvents = "none";
  }

  /** Build the spans. Idempotent and lazy — a page nobody selects on never pays for it. */
  async build(): Promise<void> {
    if (this.built) return;
    this.built = true;
    this.items = await this.doc.textItems(this.page);
    const frag = document.createDocumentFragment();
    for (const item of this.items) {
      const span = document.createElement("span");
      span.textContent = item.str;
      // Positioned in page units; the container's transform applies the zoom.
      span.style.cssText =
        `position:absolute;left:${item.x}px;top:${item.y}px;` +
        `height:${item.h}px;line-height:${item.h}px;font-size:${item.h}px;` +
        `transform-origin:0 0;white-space:pre;color:transparent;`;
      // Squeeze the span to the width pdf.js measured, so selection rectangles line up with the ink.
      const natural = item.str.length * item.h * 0.5;
      if (natural > 0 && item.w > 0) span.style.transform = `scaleX(${item.w / natural})`;
      frag.appendChild(span);
    }
    this.el.appendChild(frag);
    this.apply();
  }

  /** Update the zoom. Cheap — one transform on the container. */
  setScale(scale: number): void {
    this.scale = scale;
    this.apply();
  }

  private apply(): void {
    this.el.style.transform = `scale(${this.scale})`;
    this.el.style.transformOrigin = "0 0";
  }

  /** Turn selection on or off. Off by default so markup tools keep their clicks. */
  setSelectable(on: boolean): void {
    this.el.style.pointerEvents = on ? "auto" : "none";
    this.el.style.cursor = on ? "text" : "";
  }

  get isBuilt(): boolean { return this.built; }

  /**
   * The current DOM selection, mapped back to page space. Returns `null` when the selection is
   * empty or lies outside this page.
   */
  currentSelection(): TextSelection | null {
    const sel = document.getSelection();
    if (!sel || sel.isCollapsed || sel.rangeCount === 0) return null;
    const range = sel.getRangeAt(0);
    if (!this.el.contains(range.commonAncestorContainer)) return null;

    const origin = this.el.getBoundingClientRect();
    const quads: TextQuad[] = [];
    for (const rect of Array.from(range.getClientRects())) {
      if (rect.width < 0.5 || rect.height < 0.5) continue;
      quads.push({
        page: this.page,
        // Client px → page units: undo the element offset, then the zoom.
        x: (rect.left - origin.left) / this.scale,
        y: (rect.top - origin.top) / this.scale,
        w: rect.width / this.scale,
        h: rect.height / this.scale,
      });
    }
    if (!quads.length) return null;
    const merged = mergeByLine(quads);
    return {
      text: sel.toString(),
      page: this.page,
      quads: merged,
      bounds: unionBox(merged),
    };
  }

  /** Word boxes for this page, for search and clause anchoring. */
  async words(): Promise<Word[]> {
    if (!this.items.length) this.items = await this.doc.textItems(this.page);
    return splitWords(this.items);
  }

  destroy(): void {
    this.el.remove();
    this.items = [];
    this.built = false;
  }
}

/** Clear any live DOM selection — called when a tool takes over. */
export const clearSelection = (): void => { document.getSelection()?.removeAllRanges(); };

/** Does a page-space point fall inside a quad? Used to hit-test a clause anchor. */
export const quadContains = (q: Box, p: Pt): boolean =>
  p.x >= q.x && p.x <= q.x + q.w && p.y >= q.y && p.y <= q.y + q.h;

/**
 * Burn markups into a PDF with pdf-lib, producing a file anyone can open.
 *
 * The coordinate conversion is delegated to pdf.js's own `viewport.convertToPdfPoint`, rather than
 * hand-rolling a y-flip. That matters: a hand-rolled flip is correct only for pages whose CropBox
 * equals their MediaBox and whose `/Rotate` is 0 — which is most construction sheets but very much
 * not all of them, and the failure mode is markups silently landing in the wrong place on exactly
 * the scanned and re-plotted sheets that most need reviewing.
 *
 * `pdf-lib` is an optional peer dependency and is imported dynamically, so a host that only views
 * and never exports never pays for it.
 */
import { arrowHead, bbox } from "../core/geometry";
import { formatQuantity } from "../core/units";
import { resolveStyle } from "../render/svg";
import type { PdfDocument } from "../core/document";
import type { Annotation, Pt } from "../core/types";
// Type-only: erased at build time, so `pdf-lib` stays a genuinely optional runtime dependency.
import type * as PdfLib from "pdf-lib";
import type { PDFDocument, PDFFont, PDFPage, RGB } from "pdf-lib";

export interface FlattenOptions {
  /** Only these markups; defaults to all of them. */
  annotations?: readonly Annotation[];
  /** Draw the measured value beside each measurement. */
  labels?: boolean;
  feetInches?: boolean;
  /**
   * Append a markup summary as extra pages — the "markup report" that goes out with a review set.
   */
  summaryPage?: boolean;
  /** Title used on the summary page. */
  title?: string;
}

/** `#rrggbb` → pdf-lib rgb. */
function toRgb(hex: string | undefined, rgb: (r: number, g: number, b: number) => RGB): RGB {
  const m = /^#?([0-9a-f]{2})([0-9a-f]{2})([0-9a-f]{2})$/i.exec(hex ?? "");
  if (!m) return rgb(0.886, 0.333, 0.29);
  return rgb(parseInt(m[1]!, 16) / 255, parseInt(m[2]!, 16) / 255, parseInt(m[3]!, 16) / 255);
}

/**
 * Flatten the markups onto the document and return the new PDF bytes.
 * Throws with a clear message if `pdf-lib` is not installed.
 */
export async function flattenToPdf(doc: PdfDocument, options: FlattenOptions = {}): Promise<Uint8Array> {
  let lib: typeof PdfLib;
  try {
    lib = await import("pdf-lib");
  } catch {
    throw new Error("PDF export needs the optional peer dependency `pdf-lib` — install it to export marked-up PDFs.");
  }
  const { PDFDocument, StandardFonts, rgb, degrees } = lib;
  const annots = options.annotations ?? [];
  const out = await PDFDocument.load(doc.bytes.slice(0));
  const font = await out.embedFont(StandardFonts.Helvetica);
  const bold = await out.embedFont(StandardFonts.HelveticaBold);
  const pages = out.getPages();

  // One viewport per page, reused across that page's markups.
  const viewports = new Map<number, { convertToPdfPoint(x: number, y: number): number[] }>();
  const viewportFor = async (page: number) => {
    let vp = viewports.get(page);
    if (!vp) {
      vp = (await doc.page(page)).getViewport({ scale: 1 });
      viewports.set(page, vp);
    }
    return vp;
  };

  for (const a of annots) {
    const pg = pages[a.page - 1];
    if (!pg) continue;
    const vp = await viewportFor(a.page);
    /** page space → PDF user space. */
    const P = (p: Pt): { x: number; y: number } => {
      const [x, y] = vp.convertToPdfPoint(p.x, p.y);
      return { x: x ?? 0, y: y ?? 0 };
    };

    const st = resolveStyle(a);
    const color = toRgb(st.color, rgb);
    const fill = toRgb(st.fill ?? st.color, rgb);
    const width = Math.max(0.3, st.width);
    const pts = a.points.map(P);
    const stroke = { thickness: width, color, opacity: st.opacity } as const;

    const poly = (list: { x: number; y: number }[], close: boolean) => {
      const ring = close ? [...list, list[0]!] : list;
      for (let i = 1; i < ring.length; i++) {
        pg.drawLine({ start: ring[i - 1]!, end: ring[i]!, ...stroke });
      }
    };

    switch (a.kind) {
      case "rect": {
        if (pts.length < 2) break;
        const b = bbox(pts);
        pg.drawRectangle({
          x: b.x, y: b.y, width: b.w, height: b.h,
          borderColor: color, borderWidth: width,
          color: fill, opacity: st.fillOpacity, borderOpacity: st.opacity,
        });
        break;
      }
      case "highlight": case "underline": case "strikeout": {
        // Text-anchored markups carry one quad per selected line. Burning the union box instead
        // would put a three-line highlight's block over the margins — on screen it draws three
        // bands, and the exported PDF has to agree with what the reviewer saw.
        for (const q of textQuadsInPdfSpace(a, P) ?? boxQuads(pts)) {
          if (a.kind === "highlight") {
            pg.drawRectangle({
              x: q.x, y: q.y, width: q.w, height: q.h,
              color: fill, opacity: st.fillOpacity, borderWidth: 0,
            });
          } else {
            // pdf space is y-up, so "under" the text is the low edge of the quad.
            const y = a.kind === "underline" ? q.y + q.h * 0.06 : q.y + q.h * 0.45;
            pg.drawLine({ start: { x: q.x, y }, end: { x: q.x + q.w, y }, ...stroke });
          }
        }
        break;
      }
      case "ellipse": {
        if (pts.length < 2) break;
        const b = bbox(pts);
        pg.drawEllipse({
          x: b.x + b.w / 2, y: b.y + b.h / 2, xScale: b.w / 2, yScale: b.h / 2,
          borderColor: color, borderWidth: width, color: fill,
          opacity: st.fillOpacity, borderOpacity: st.opacity,
        });
        break;
      }
      case "polygon": case "area": case "volume": poly(pts, true); break;
      case "perimeter": poly(pts, true); break;
      case "polyline": case "line": case "distance": case "angle": case "radius": case "ink":
        poly(pts, false);
        break;
      case "arrow": {
        if (pts.length < 2) break;
        poly(pts, false);
        const tip = pts[pts.length - 1]!, prev = pts[pts.length - 2]!;
        const [w1, w2] = arrowHead(prev, tip, Math.max(5, width * 4));
        pg.drawLine({ start: w1, end: tip, ...stroke });
        pg.drawLine({ start: w2, end: tip, ...stroke });
        break;
      }
      case "cloud": {
        // pdf-lib has no arc primitive, so re-derive the scallops as short line segments. Sampled
        // finely enough that it reads as a cloud at plot resolution.
        for (const seg of sampleCloud(a.points, Math.max(4, width * 3))) {
          const from = P(seg[0]), to = P(seg[1]);
          pg.drawLine({ start: from, end: to, ...stroke });
        }
        break;
      }
      case "count": {
        for (const p of pts) pg.drawCircle({ x: p.x, y: p.y, size: Math.max(2.5, width * 2.2), color, opacity: 0.9 });
        break;
      }
      case "pin": {
        const p = pts[0];
        if (!p) break;
        pg.drawCircle({ x: p.x, y: p.y + 7, size: 7, color, opacity: 0.95 });
        pg.drawLine({ start: { x: p.x, y: p.y }, end: { x: p.x, y: p.y + 4 }, thickness: 1.5, color });
        const badge = a.ext?.["pinNumber"];
        if (badge !== undefined) {
          const label = String(badge);
          pg.drawText(label, {
            x: p.x - bold.widthOfTextAtSize(label, 8) / 2, y: p.y + 4.2,
            size: 8, font: bold, color: rgb(1, 1, 1),
          });
        }
        break;
      }
      case "text": case "callout": case "symbol": {
        if (a.kind === "callout" && pts.length >= 2) poly(pts, false);
        const anchor = a.kind === "callout" ? pts[pts.length - 1] : pts[0];
        if (!anchor || !(a.text ?? a.subject)) break;
        drawLines(pg, a.text ?? a.subject ?? "", anchor, st.fontSize, font, color, st.opacity, degrees(a.rotation ?? 0));
        break;
      }
      case "stamp": {
        const anchor = pts[0];
        if (!anchor || !a.text) break;
        const size = st.fontSize;
        const w = bold.widthOfTextAtSize(a.text, size) + size;
        const h = size * 1.7;
        pg.drawRectangle({
          x: anchor.x, y: anchor.y - h / 2, width: w, height: h,
          borderColor: color, borderWidth: Math.max(1, width), color, opacity: 0.08, borderOpacity: 1,
          rotate: degrees(a.rotation ?? 0),
        });
        pg.drawText(a.text, {
          x: anchor.x + size / 2, y: anchor.y - size * 0.35, size, font: bold, color,
          rotate: degrees(a.rotation ?? 0),
        });
        break;
      }
    }

    // The measured value, beside the markup.
    if (options.labels !== false && a.quantity) {
      const label = formatQuantity(a.quantity, { feetInches: options.feetInches ?? true });
      const anchor = labelAnchor(a, pts);
      if (label && anchor) {
        const size = 8;
        // A white plate keeps the number legible over dense linework.
        const w = bold.widthOfTextAtSize(label, size);
        pg.drawRectangle({ x: anchor.x - 1.5, y: anchor.y - 2, width: w + 3, height: size + 2, color: rgb(1, 1, 1), opacity: 0.8 });
        pg.drawText(label, { x: anchor.x, y: anchor.y, size, font: bold, color });
      }
    }
  }

  if (options.summaryPage && annots.length) {
    await addSummary(out, annots, { font, bold, rgb }, options);
  }
  return out.save();
}

/**
 * Per-line quads from a text selection, converted to PDF user space. Each quad is page-space
 * top-left, so both its corners go through the same viewport transform as any other geometry.
 */
function textQuadsInPdfSpace(
  a: Annotation,
  P: (p: Pt) => { x: number; y: number },
): { x: number; y: number; w: number; h: number }[] | null {
  const raw = a.ext?.["quads"];
  if (!Array.isArray(raw) || !raw.length) return null;
  return (raw as { x: number; y: number; w: number; h: number }[]).map((q) => {
    const a1 = P({ x: q.x, y: q.y });
    const a2 = P({ x: q.x + q.w, y: q.y + q.h });
    return {
      x: Math.min(a1.x, a2.x), y: Math.min(a1.y, a2.y),
      w: Math.abs(a2.x - a1.x), h: Math.abs(a2.y - a1.y),
    };
  });
}

/** Fallback for a markup dragged as a box rather than selected as text. */
function boxQuads(pts: { x: number; y: number }[]): { x: number; y: number; w: number; h: number }[] {
  return pts.length >= 2 ? [bbox(pts)] : [];
}

/** Where a measurement's value goes: inside a closed shape, at the midpoint of an open one. */
function labelAnchor(a: Annotation, pts: { x: number; y: number }[]): { x: number; y: number } | null {
  if (!pts.length) return null;
  if (a.kind === "area" || a.kind === "volume" || a.kind === "polygon") {
    const b = bbox(pts);
    return { x: b.x + b.w / 2, y: b.y + b.h / 2 };
  }
  const i = Math.floor((pts.length - 1) / 2);
  const p = pts[i]!, q = pts[i + 1] ?? p;
  return { x: (p.x + q.x) / 2 + 3, y: (p.y + q.y) / 2 + 3 };
}

/** Multi-line text, top-down from the anchor. */
function drawLines(
  pg: PDFPage,
  text: string,
  anchor: { x: number; y: number },
  size: number,
  font: PDFFont,
  color: RGB,
  opacity: number,
  rotate: ReturnType<typeof PdfLib.degrees>,
): void {
  text.split("\n").forEach((line, i) => {
    pg.drawText(line, { x: anchor.x, y: anchor.y - i * size * 1.25, size, font, color, opacity, rotate });
  });
}

/**
 * Re-derive a revision cloud's scallops as line segments. Mirrors `cloudPath`'s arc placement, then
 * samples each arc — pdf-lib has no arc operator, and a polyline approximation at this density is
 * indistinguishable at plot scale.
 */
function sampleCloud(pts: readonly Pt[], radius: number): [Pt, Pt][] {
  const segs: [Pt, Pt][] = [];
  if (pts.length < 2) return segs;
  const ring = [...pts, pts[0]!];
  for (let i = 1; i < ring.length; i++) {
    const a = ring[i - 1]!, b = ring[i]!;
    const len = Math.hypot(b.x - a.x, b.y - a.y);
    if (len < 1e-6) continue;
    const n = Math.max(1, Math.round(len / (radius * 1.8)));
    const step = len / n;
    const ux = (b.x - a.x) / len, uy = (b.y - a.y) / len;
    // Outward normal (left of travel), matching the SVG arc's sweep direction.
    const nx = uy, ny = -ux;
    for (let k = 0; k < n; k++) {
      const s = { x: a.x + ux * step * k, y: a.y + uy * step * k };
      const e = { x: a.x + ux * step * (k + 1), y: a.y + uy * step * (k + 1) };
      const r = step / 2;
      const mid = { x: (s.x + e.x) / 2, y: (s.y + e.y) / 2 };
      // 6 chords per bump: enough that the scallop reads as a curve on paper.
      const STEPS = 6;
      let prev = s;
      for (let t = 1; t <= STEPS; t++) {
        const ang = Math.PI * (t / STEPS);
        const along = -Math.cos(ang) * r;
        const outward = Math.sin(ang) * r;
        const p = { x: mid.x + ux * along + nx * outward, y: mid.y + uy * along + ny * outward };
        segs.push([prev, p]);
        prev = p;
      }
    }
  }
  return segs;
}

/** A markup schedule appended to the exported file — the review record that travels with the set. */
async function addSummary(
  out: PDFDocument,
  annots: readonly Annotation[],
  fonts: { font: PDFFont; bold: PDFFont; rgb: (r: number, g: number, b: number) => RGB },
  options: FlattenOptions,
): Promise<void> {
  const { font, bold, rgb } = fonts;
  const W = 612, H = 792, M = 42;
  const rowH = 14;
  let page = out.addPage([W, H]);
  let y = H - M;

  const header = () => {
    page.drawText(options.title ?? "Markup schedule", { x: M, y, size: 16, font: bold, color: rgb(0.1, 0.1, 0.12) });
    y -= 10;
    page.drawText(`${annots.length} markups · exported ${new Date().toISOString().slice(0, 10)}`, {
      x: M, y: y - 8, size: 8, font, color: rgb(0.42, 0.45, 0.5),
    });
    y -= 28;
    for (const [label, x] of [["#", M], ["Page", M + 26], ["Type", M + 60], ["Subject", M + 120], ["Status", M + 330], ["Qty", M + 400], ["Author", M + 460]] as [string, number][]) {
      page.drawText(label, { x, y, size: 8, font: bold, color: rgb(0.35, 0.38, 0.42) });
    }
    y -= 6;
    page.drawLine({ start: { x: M, y }, end: { x: W - M, y }, thickness: 0.6, color: rgb(0.8, 0.82, 0.85) });
    y -= rowH;
  };
  header();

  annots.forEach((a, i) => {
    if (y < M + rowH) {
      page = out.addPage([W, H]);
      y = H - M;
      header();
    }
    const cells: [string, number][] = [
      [String(i + 1), M],
      [String(a.page), M + 26],
      [a.kind, M + 60],
      [truncate(a.subject || a.text || a.note || "", 46), M + 120],
      [a.status, M + 330],
      [a.quantity ? formatQuantity(a.quantity, { feetInches: options.feetInches ?? true }) : "", M + 400],
      [truncate(a.author, 16), M + 460],
    ];
    for (const [text, x] of cells) {
      page.drawText(text, { x, y, size: 8, font, color: rgb(0.15, 0.16, 0.18) });
    }
    const swatch = toRgb(a.style?.color, rgb);
    page.drawRectangle({ x: M - 10, y: y - 1, width: 5, height: 8, color: swatch });
    y -= rowH;
  });
}

const truncate = (s: string, n: number): string => (s.length > n ? `${s.slice(0, n - 1)}…` : s);

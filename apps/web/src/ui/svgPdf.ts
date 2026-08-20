/**
 * R38-SHEET-MARKUP ③ ③ — a generated sheet becomes a PDF the takeoff tools can open.
 *
 * Composed sheets already have `sheet.pdf`. Plans/elevations/sections are SVG-only (no Cairo
 * SVG→PDF in prod). Wrap a PNG of the live sheet in pdf-lib so ⌘ Match / stamps / persist
 * work on the room's own drawings, not only the titleblock sheet.
 */
export const MAX_PAGE_PT = 1440;

export function pageSizeFromViewBox(w: number, h: number): { w: number; h: number } {
  const aw = Math.max(1, w);
  const ah = Math.max(1, h);
  const scale = Math.min(1, MAX_PAGE_PT / Math.max(aw, ah));
  return { w: aw * scale, h: ah * scale };
}

export function viewBoxOf(svg: SVGSVGElement): { w: number; h: number } {
  const vb = svg.viewBox?.baseVal;
  if (vb && vb.width > 0 && vb.height > 0) return { w: vb.width, h: vb.height };
  const w = Number(svg.getAttribute("width")) || svg.clientWidth || 1000;
  const h = Number(svg.getAttribute("height")) || svg.clientHeight || 800;
  return { w: Math.max(1, w), h: Math.max(1, h) };
}

export async function pdfFromPng(png: Uint8Array, w: number, h: number): Promise<Uint8Array> {
  const { PDFDocument } = await import("pdf-lib");
  const doc = await PDFDocument.create();
  const img = await doc.embedPng(png);
  const size = pageSizeFromViewBox(w, h);
  const page = doc.addPage([size.w, size.h]);
  page.drawImage(img, { x: 0, y: 0, width: size.w, height: size.h });
  return doc.save();
}

/** Rasterise the live SVG. Empty paper is refused rather than a blank PDF that looks like a sheet. */
export async function pngFromSvgElement(svg: SVGSVGElement): Promise<{ png: Uint8Array; w: number; h: number }> {
  const { w, h } = viewBoxOf(svg);
  const xml = new XMLSerializer().serializeToString(svg);
  if (!xml.includes("<svg")) throw new Error("not a sheet");
  const blob = new Blob([xml], { type: "image/svg+xml;charset=utf-8" });
  const url = URL.createObjectURL(blob);
  try {
    const img = await new Promise<HTMLImageElement>((resolve, reject) => {
      const el = new Image();
      el.onload = () => resolve(el);
      el.onerror = () => reject(new Error("couldn't rasterise the sheet"));
      el.src = url;
    });
    const canvas = document.createElement("canvas");
    const size = pageSizeFromViewBox(w, h);
    canvas.width = Math.max(1, Math.round(size.w));
    canvas.height = Math.max(1, Math.round(size.h));
    const ctx = canvas.getContext("2d");
    if (!ctx) throw new Error("couldn't rasterise the sheet");
    ctx.fillStyle = "#fff";
    ctx.fillRect(0, 0, canvas.width, canvas.height);
    ctx.drawImage(img, 0, 0, canvas.width, canvas.height);
    const blobOut = await new Promise<Blob>((resolve, reject) => {
      canvas.toBlob((b) => (b ? resolve(b) : reject(new Error("couldn't rasterise the sheet"))), "image/png");
    });
    return { png: new Uint8Array(await blobOut.arrayBuffer()), w, h };
  } finally {
    URL.revokeObjectURL(url);
  }
}

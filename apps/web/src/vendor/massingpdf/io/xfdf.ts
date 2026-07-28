/**
 * XFDF import/export — the lingua franca of PDF markup exchange.
 *
 * XFDF is what Bluebeam, Acrobat, Foxit and PDF-XChange all read, so it is the format that lets a
 * markup set leave this tool without leaving the workflow. Two things it is worth being careful
 * about:
 *
 * 1. **Coordinates are bottom-left origin PDF user space**, while everything here is top-left. The
 *    flip needs the page height, so export requires the page boxes.
 * 2. **XFDF cannot express the structured half of the record** — status, discipline, quantity,
 *    revision context. Rather than lose it, each annotation also carries a namespaced `<massing>`
 *    payload that other readers ignore and this one round-trips losslessly.
 */
import { bbox } from "../core/geometry";
import type { Annotation, AnnotationDraft, Pt } from "../core/types";

const XFDF_NS = "http://ns.adobe.com/xfdf/";
const MASSING_NS = "https://massing.cloud/ns/pdf-markup";

export interface XfdfPageBox { width: number; height: number }

export interface XfdfExportOptions {
  /** Page boxes by 1-based page number — needed for the y-flip. */
  pages: Map<number, XfdfPageBox> | ((page: number) => XfdfPageBox | undefined);
  /** The `<f href>` the markups belong to. */
  href?: string;
  /** Include the lossless `<massing>` payload. Off produces a plainer file for picky readers. */
  includeExtensions?: boolean;
}

/** Which XFDF element each of our kinds maps to. */
function xfdfTag(kind: Annotation["kind"]): string {
  switch (kind) {
    case "rect": case "highlight": case "volume": return kind === "highlight" ? "square" : "square";
    case "ellipse": case "radius": return "circle";
    case "line": case "arrow": case "distance": return "line";
    case "polyline": case "perimeter": case "angle": return "polyline";
    case "polygon": case "area": case "cloud": return "polygon";
    case "ink": return "ink";
    case "text": case "callout": case "stamp": case "symbol": return "freetext";
    case "count": case "pin": return "text";           // sticky note — the only single-point primitive
    case "strikeout": return "strikeout";
    case "underline": return "underline";
    default: return "square";
  }
}

const esc = (s: string): string =>
  s.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");

/** `#rrggbb`, lower-cased and normalised; XFDF wants an uppercase `#RRGGBB`. */
const hex = (c: string | undefined, fallback = "#E2554A"): string => {
  if (!c) return fallback;
  const m = /^#?([0-9a-f]{6})$/i.exec(c.trim());
  return m ? `#${m[1]!.toUpperCase()}` : fallback;
};

/** PDF date string, e.g. `D:20260726143000Z`. */
function pdfDate(iso: string): string {
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "";
  const p = (n: number) => String(n).padStart(2, "0");
  return `D:${d.getUTCFullYear()}${p(d.getUTCMonth() + 1)}${p(d.getUTCDate())}${p(d.getUTCHours())}${p(d.getUTCMinutes())}${p(d.getUTCSeconds())}Z`;
}

function parsePdfDate(s: string | null): string | undefined {
  if (!s) return undefined;
  const m = /^D:(\d{4})(\d{2})(\d{2})(\d{2})?(\d{2})?(\d{2})?/.exec(s.trim());
  if (!m) {
    const d = new Date(s);
    return Number.isNaN(d.getTime()) ? undefined : d.toISOString();
  }
  const [, y, mo, da, h = "00", mi = "00", se = "00"] = m;
  return new Date(Date.UTC(+y!, +mo! - 1, +da!, +h, +mi, +se)).toISOString();
}

/** Serialise a markup set to an XFDF document. */
export function toXfdf(annots: readonly Annotation[], options: XfdfExportOptions): string {
  const pageBox = typeof options.pages === "function"
    ? options.pages
    : (p: number) => (options.pages as Map<number, XfdfPageBox>).get(p);

  const parts: string[] = [
    `<?xml version="1.0" encoding="UTF-8"?>`,
    `<xfdf xmlns="${XFDF_NS}" xmlns:massing="${MASSING_NS}" xml:space="preserve">`,
  ];
  if (options.href) parts.push(`<f href="${esc(options.href)}"/>`);
  parts.push("<annots>");

  for (const a of annots) {
    const box = pageBox(a.page);
    if (!box) continue;
    const H = box.height;
    const flip = (p: Pt): Pt => ({ x: p.x, y: H - p.y });
    const pts = a.points.map(flip);
    const b = bbox(pts);
    const tag = xfdfTag(a.kind);
    const color = hex(a.style?.color);

    const attrs: string[] = [
      `page="${a.page - 1}"`,                       // XFDF pages are 0-based
      `rect="${r(b.x)},${r(b.y)},${r(b.x + b.w)},${r(b.y + b.h)}"`,
      `color="${color}"`,
      `width="${a.style?.width ?? 1.8}"`,
      `opacity="${a.style?.opacity ?? 1}"`,
      `title="${esc(a.author)}"`,
      `subject="${esc(a.subject ?? a.kind)}"`,
      `name="${esc(a.id)}"`,
      `creationdate="${pdfDate(a.createdAt)}"`,
      `date="${pdfDate(a.updatedAt ?? a.createdAt)}"`,
      `flags="print"`,
    ];
    if (a.style?.fill) attrs.push(`interior-color="${hex(a.style.fill)}"`);

    // Geometry attributes differ per element type.
    if (tag === "line" && pts.length >= 2) {
      const s = pts[0]!, e = pts[pts.length - 1]!;
      attrs.push(`start="${r(s.x)},${r(s.y)}"`, `end="${r(e.x)},${r(e.y)}"`);
      if (a.kind === "arrow") attrs.push(`head="None"`, `tail="OpenArrow"`);
    } else if (tag === "polygon" || tag === "polyline") {
      attrs.push(`vertices="${pts.map((p) => `${r(p.x)},${r(p.y)}`).join(";")}"`);
      if (a.kind === "cloud") attrs.push(`intent="PolygonCloud"`);
    }

    const children: string[] = [];
    const body = a.note ?? a.text ?? a.subject;
    if (body) children.push(`<contents>${esc(body)}</contents>`);
    if (tag === "freetext" && a.text) {
      children.push(`<contents-richtext><body xmlns="http://www.w3.org/1999/xhtml"><p>${esc(a.text)}</p></body></contents-richtext>`);
      attrs.push(`rotation="${a.rotation ?? 0}"`);
    }
    if (tag === "ink") {
      children.push(`<inklist><gesture>${pts.map((p) => `${r(p.x)},${r(p.y)}`).join(";")}</gesture></inklist>`);
    }
    if (options.includeExtensions !== false) {
      children.push(`<massing:record>${esc(JSON.stringify(structuredPayload(a)))}</massing:record>`);
    }

    parts.push(`<${tag} ${attrs.join(" ")}>${children.join("")}</${tag}>`);

    // Replies are *siblings* in `<annots>` carrying `inreplyto`, not children of the markup they
    // answer. Nesting them produces a file Acrobat and Bluebeam both silently drop the replies from.
    for (const reply of a.replies ?? []) {
      parts.push(
        `<text page="${a.page - 1}" inreplyto="${esc(a.id)}" replytype="R" title="${esc(reply.author)}" ` +
        `name="${esc(reply.id)}" date="${pdfDate(reply.createdAt)}" ` +
        `rect="${r(b.x)},${r(b.y)},${r(b.x + 20)},${r(b.y + 20)}">` +
        `<contents>${esc(reply.body)}</contents></text>`,
      );
    }
  }

  parts.push("</annots>", "</xfdf>");
  return parts.join("\n");
}

/**
 * The local part of a node's name, lower-cased.
 *
 * DOM implementations disagree about namespace prefixes on parsed XML: browsers split
 * `massing:record` into a `record` localName, some server-side parsers leave the prefix attached.
 * Taking the segment after the last colon is correct under both.
 */
const localName = (node: Element): string => {
  const raw = node.localName || node.nodeName;
  return raw.slice(raw.lastIndexOf(":") + 1).toLowerCase();
};

/** The half of the record XFDF has no vocabulary for. */
function structuredPayload(a: Annotation) {
  return {
    kind: a.kind, status: a.status, priority: a.priority, discipline: a.discipline, trade: a.trade,
    labels: a.labels, quantity: a.quantity, links: a.links, revision: a.revision,
    provenance: a.provenance, sheetId: a.sheetId, version: a.version, org: a.org,
    points: a.points, style: a.style, ext: a.ext, text: a.text, rotation: a.rotation,
  };
}

export interface XfdfImportOptions {
  /** Page boxes by 1-based page number — needed to flip back to top-left origin. */
  pages: Map<number, XfdfPageBox> | ((page: number) => XfdfPageBox | undefined);
  /** Author to attribute markups that carry no `title`. */
  defaultAuthor?: string;
}

/** Parse an XFDF document into annotation drafts. */
export function fromXfdf(xml: string, options: XfdfImportOptions): AnnotationDraft[] {
  const pageBox = typeof options.pages === "function"
    ? options.pages
    : (p: number) => (options.pages as Map<number, XfdfPageBox>).get(p);

  const doc = new DOMParser().parseFromString(xml, "application/xml");
  // Browsers report a malformed document as a `parsererror` element; more lenient parsers just
  // return something odd — so validate the root element too rather than trusting one signal.
  const err = doc.querySelector("parsererror");
  if (err) throw new Error(`XFDF is not well-formed: ${err.textContent?.slice(0, 200)}`);
  // Look for the `<xfdf>` element rather than asserting it is the document element: strict parsers
  // make it the root, but lenient ones wrap parsed XML in an implicit `<html>` and would fail a
  // root check on a perfectly good file.
  const root = doc.documentElement;
  const isXfdf = (root && localName(root) === "xfdf") || doc.getElementsByTagName("xfdf").length > 0;
  if (!isXfdf) throw new Error("not an XFDF document — no <xfdf> element found");

  const out: AnnotationDraft[] = [];
  const annots = doc.getElementsByTagName("annots")[0];
  if (!annots) return out;

  for (const node of Array.from(annots.children)) {
    const tag = localName(node);
    // Replies are attached to their parent below, not imported as top-level markups.
    if (node.getAttribute("inreplyto")) continue;

    const page = Number(node.getAttribute("page") ?? 0) + 1;
    const box = pageBox(page);
    if (!box) continue;
    const H = box.height;
    const unflip = (p: Pt): Pt => ({ x: p.x, y: H - p.y });

    // The lossless payload wins when present — it round-trips everything XFDF drops.
    const payloadNode = Array.from(node.children).find((c) => localName(c) === "record");
    let payload: Record<string, unknown> | null = null;
    if (payloadNode?.textContent) {
      try { payload = JSON.parse(payloadNode.textContent) as Record<string, unknown>; } catch { /* fall through to geometry parsing */ }
    }

    const rect = numbers(node.getAttribute("rect"));
    let points: Pt[];
    if (payload && Array.isArray(payload["points"])) {
      points = (payload["points"] as Pt[]).map((p) => ({ x: p.x, y: p.y }));   // already top-left
    } else if (node.getAttribute("vertices")) {
      points = pairs(node.getAttribute("vertices")!).map(unflip);
    } else if (tag === "line") {
      points = [...pairs(node.getAttribute("start") ?? ""), ...pairs(node.getAttribute("end") ?? "")].map(unflip);
    } else if (tag === "ink") {
      const gesture = node.getElementsByTagName("gesture")[0]?.textContent ?? "";
      points = pairs(gesture).map(unflip);
    } else if (rect.length >= 4) {
      points = [unflip({ x: rect[0]!, y: rect[3]! }), unflip({ x: rect[2]!, y: rect[1]! })];
    } else {
      continue;
    }
    if (!points.length) continue;

    const contents = node.getElementsByTagName("contents")[0]?.textContent ?? undefined;
    const author = node.getAttribute("title") || options.defaultAuthor || "imported";
    const created = parsePdfDate(node.getAttribute("creationdate") ?? node.getAttribute("date"));

    const draft: AnnotationDraft = {
      kind: (payload?.["kind"] as Annotation["kind"]) ?? kindFromTag(tag, node),
      page,
      points,
      author,
      ...(node.getAttribute("name") ? { id: node.getAttribute("name")! } : {}),
      ...(created ? { createdAt: created } : {}),
      ...(contents ? { note: contents } : {}),
      ...(node.getAttribute("subject") ? { subject: node.getAttribute("subject")! } : {}),
      style: {
        color: node.getAttribute("color") ?? undefined,
        width: numberOr(node.getAttribute("width"), 1.8),
        opacity: numberOr(node.getAttribute("opacity"), 1),
        ...(node.getAttribute("interior-color") ? { fill: node.getAttribute("interior-color")! } : {}),
      },
    };

    if (payload) {
      Object.assign(draft, {
        status: payload["status"], priority: payload["priority"], discipline: payload["discipline"],
        trade: payload["trade"], labels: payload["labels"], quantity: payload["quantity"],
        links: payload["links"], revision: payload["revision"], provenance: payload["provenance"],
        sheetId: payload["sheetId"], org: payload["org"], text: payload["text"],
        rotation: payload["rotation"], ext: payload["ext"],
        style: { ...(draft.style ?? {}), ...(payload["style"] as object ?? {}) },
      });
      // A record re-imported into a different document starts a fresh version line.
      draft.version = typeof payload["version"] === "number" ? payload["version"] : 1;
    }

    // Attach replies addressed to this annotation.
    const id = node.getAttribute("name");
    if (id) {
      const replies = Array.from(annots.children)
        .filter((c) => c.getAttribute("inreplyto") === id)
        .map((c) => ({
          id: c.getAttribute("name") ?? `${id}-reply-${Math.random().toString(36).slice(2, 8)}`,
          author: c.getAttribute("title") ?? "imported",
          body: c.getElementsByTagName("contents")[0]?.textContent ?? "",
          createdAt: parsePdfDate(c.getAttribute("date")) ?? new Date().toISOString(),
        }));
      if (replies.length) draft.replies = replies;
    }

    out.push(draft);
  }
  return out;
}

function kindFromTag(tag: string, node: Element): Annotation["kind"] {
  switch (tag) {
    case "square": return "rect";
    case "circle": return "ellipse";
    case "line": return node.getAttribute("tail") || node.getAttribute("head") ? "arrow" : "line";
    case "polygon": return node.getAttribute("intent") === "PolygonCloud" ? "cloud" : "polygon";
    case "polyline": return "polyline";
    case "ink": return "ink";
    case "freetext": return "text";
    case "text": return "pin";
    case "highlight": return "highlight";
    case "strikeout": return "strikeout";
    case "underline": return "underline";
    default: return "rect";
  }
}

const r = (n: number): number => Math.round(n * 100) / 100;

const numbers = (s: string | null): number[] =>
  (s ?? "").split(/[,\s]+/).map(Number).filter((n) => Number.isFinite(n));

const numberOr = (s: string | null, fallback: number): number => {
  const n = Number(s);
  return Number.isFinite(n) ? n : fallback;
};

/** `x,y;x,y` → points. */
function pairs(s: string): Pt[] {
  const out: Pt[] = [];
  for (const chunk of s.split(";")) {
    const [x, y] = chunk.split(",").map(Number);
    if (Number.isFinite(x) && Number.isFinite(y)) out.push({ x: x!, y: y! });
  }
  return out;
}

/**
 * The default markup renderer: `Annotation` → SVG, in page space.
 *
 * The overlay's `viewBox` is the page box, so everything emitted here is in PDF points and zoom is
 * free — a 2pt cloud stays 2pt on the sheet at 50% and at 800%, exactly as it would if it had been
 * drawn into the PDF. The only things that compensate for zoom are the affordances (handles, pin
 * badges, hit-test padding), which must stay a constant *screen* size to be usable.
 */
import {
  arrowHead, bbox, centroid, cloudPath, linePath, rectCorners, smoothPath,
} from "../core/geometry";
import { formatQuantity } from "../core/units";
import { DISCIPLINE_COLORS, STATUS_COLORS } from "../core/types";
import type { Annotation, AnnotStyle, Pt } from "../core/types";

export const SVG_NS = "http://www.w3.org/2000/svg";

/**
 * Create an SVG element with attributes. `undefined` values are skipped rather than stringified,
 * so conditional attribute spreads (`...(dash ? {…} : {})`) compose without a cast at every call.
 */
export function el<K extends keyof SVGElementTagNameMap>(
  tag: K,
  attrs: Record<string, string | number | undefined> = {},
): SVGElementTagNameMap[K] {
  const node = document.createElementNS(SVG_NS, tag);
  for (const [k, v] of Object.entries(attrs)) if (v !== undefined) node.setAttribute(k, String(v));
  return node;
}

/** Default presentation for a markup, from its discipline then its kind. */
export function resolveStyle(a: Annotation): Required<Pick<AnnotStyle, "color" | "width" | "opacity" | "fillOpacity" | "fontSize">> & AnnotStyle {
  const s = a.style ?? {};
  const base = s.color ?? (a.discipline ? DISCIPLINE_COLORS[a.discipline] : undefined) ?? kindColor(a);
  return {
    ...s,
    color: base,
    width: s.width ?? (a.kind === "cloud" ? 1.6 : 1.8),
    opacity: s.opacity ?? 1,
    fillOpacity: s.fillOpacity ?? (a.kind === "highlight" ? 0.35 : 0.12),
    fontSize: s.fontSize ?? (a.kind === "stamp" ? 16 : 11),
  };
}

function kindColor(a: Annotation): string {
  switch (a.kind) {
    case "area": case "volume": case "perimeter": return "#33d17a";
    case "distance": case "radius": case "angle": return "#ffb02e";
    case "count": return "#4a8cff";
    case "stamp": return "#e2554a";
    case "pin": return STATUS_COLORS[a.status];
    case "highlight": return "#ffe14d";
    default: return "#e2554a";
  }
}

export interface DrawOpts {
  zoom: number;
  selected?: boolean;
  /** Suppress the quantity/label text — used by the thumbnail and the compare overlay. */
  labels?: boolean;
  /** Formatting for measured quantities. */
  feetInches?: boolean;
}

/**
 * Render one markup. Returns a `<g>` carrying `data-annot` so hit-testing and the list can find it.
 */
export function drawAnnotation(a: Annotation, o: DrawOpts): SVGGElement {
  const g = el("g", { "data-annot": a.id, "data-kind": a.kind, class: "mpdf-annot" });
  const st = resolveStyle(a);
  const stroke = { stroke: st.color, "stroke-width": st.width, "stroke-opacity": st.opacity, fill: "none" };
  const filled = { ...stroke, fill: st.fill ?? st.color, "fill-opacity": st.fillOpacity };
  const dash = st.dash?.length ? { "stroke-dasharray": st.dash.join(" ") } : {};
  const pts = a.points;
  /** Screen-constant size expressed in page units. */
  const px = (n: number) => n / o.zoom;

  switch (a.kind) {
    case "rect": {
      if (pts.length < 2) break;
      const b = bbox([pts[0]!, pts[1]!]);
      g.append(el("rect", { x: b.x, y: b.y, width: b.w, height: b.h, ...filled, ...dash }));
      break;
    }
    case "highlight": {
      // A text-anchored highlight carries one quad per line, so a selection spanning three lines
      // draws three bands rather than one block swallowing the margins.
      for (const q of textQuads(a) ?? boxQuad(pts)) {
        g.append(el("rect", { x: q.x, y: q.y, width: q.w, height: q.h, ...filled, stroke: "none" }));
      }
      break;
    }
    case "ellipse": {
      if (pts.length < 2) break;
      const b = bbox([pts[0]!, pts[1]!]);
      g.append(el("ellipse", { cx: b.x + b.w / 2, cy: b.y + b.h / 2, rx: b.w / 2, ry: b.h / 2, ...filled, ...dash }));
      break;
    }
    case "line":
    case "distance": {
      if (pts.length < 2) break;
      g.append(el("path", { d: linePath(pts), ...stroke, ...dash }));
      if (a.kind === "distance") appendTicks(g, pts, st.color, st.width);
      break;
    }
    case "arrow": {
      if (pts.length < 2) break;
      g.append(el("path", { d: linePath(pts), ...stroke, ...dash }));
      const tip = pts[pts.length - 1]!, prev = pts[pts.length - 2]!;
      const [w1, w2] = arrowHead(prev, tip, Math.max(6, st.width * 4));
      g.append(el("path", { d: `M${w1.x},${w1.y}L${tip.x},${tip.y}L${w2.x},${w2.y}Z`, fill: st.color, stroke: "none" }));
      break;
    }
    case "polyline":
    case "perimeter": {
      g.append(el("path", { d: linePath(pts, a.kind === "perimeter"), ...stroke, ...dash }));
      break;
    }
    case "polygon":
    case "area":
    case "volume": {
      g.append(el("path", { d: linePath(pts, true), ...filled, ...dash }));
      break;
    }
    case "cloud": {
      g.append(el("path", { d: cloudPath(pts, Math.max(4, st.width * 3)), ...stroke, fill: st.fill ?? "none", "fill-opacity": st.fill ? st.fillOpacity : 0 }));
      break;
    }
    case "ink": {
      g.append(el("path", { d: smoothPath(pts), ...stroke, "stroke-linecap": "round", "stroke-linejoin": "round" }));
      break;
    }
    case "count": {
      const r = Math.max(3, px(6));
      for (const p of pts) {
        g.append(el("circle", { cx: p.x, cy: p.y, r, fill: st.color, "fill-opacity": 0.85, stroke: "#fff", "stroke-width": px(1) }));
      }
      break;
    }
    case "angle": {
      if (pts.length < 3) break;
      g.append(el("path", { d: linePath(pts.slice(0, 3)), ...stroke }));
      break;
    }
    case "radius": {
      if (pts.length < 3) break;
      g.append(el("path", { d: linePath(pts.slice(0, 3)), ...stroke, "stroke-dasharray": `${px(4)} ${px(3)}` }));
      break;
    }
    case "underline":
    case "strikeout": {
      for (const q of textQuads(a) ?? boxQuad(pts)) {
        // Underline sits just below the baseline box; strikeout crosses the x-height.
        const y = a.kind === "underline" ? q.y + q.h * 0.94 : q.y + q.h * 0.55;
        g.append(el("line", { x1: q.x, y1: y, x2: q.x + q.w, y2: y, ...stroke }));
      }
      break;
    }
    case "text": {
      appendText(g, a, st);
      break;
    }
    case "callout": {
      // points: [anchor(tip), …elbow, textBox]
      if (pts.length >= 2) {
        g.append(el("path", { d: linePath(pts), ...stroke }));
        const [w1, w2] = arrowHead(pts[1]!, pts[0]!, Math.max(6, st.width * 4));
        g.append(el("path", { d: `M${w1.x},${w1.y}L${pts[0]!.x},${pts[0]!.y}L${w2.x},${w2.y}Z`, fill: st.color, stroke: "none" }));
      }
      appendText(g, a, st, pts[pts.length - 1]);
      break;
    }
    case "stamp": {
      appendStamp(g, a, st);
      break;
    }
    case "pin": {
      appendPin(g, a, o);
      break;
    }
    case "symbol": {
      const p = pts[0]; if (!p) break;
      const r = Math.max(6, px(10));
      g.append(el("path", { d: `M${p.x - r},${p.y}L${p.x},${p.y - r}L${p.x + r},${p.y}L${p.x},${p.y + r}Z`, ...filled }));
      appendText(g, a, st);
      break;
    }
  }

  if (o.labels !== false) appendQuantityLabel(g, a, st, o);
  if (o.selected) appendSelection(g, a, o);
  return g;
}

/** Perpendicular end ticks on a dimension line — the convention that makes it read as a dimension. */
function appendTicks(g: SVGGElement, pts: readonly Pt[], color: string, width: number): void {
  const ends: [Pt, Pt][] = [];
  if (pts.length >= 2) {
    ends.push([pts[1]!, pts[0]!]);
    ends.push([pts[pts.length - 2]!, pts[pts.length - 1]!]);
  }
  const len = Math.max(3, width * 3);
  for (const [from, at] of ends) {
    const ang = Math.atan2(at.y - from.y, at.x - from.x) + Math.PI / 2;
    const dx = Math.cos(ang) * len, dy = Math.sin(ang) * len;
    g.append(el("line", { x1: at.x - dx, y1: at.y - dy, x2: at.x + dx, y2: at.y + dy, stroke: color, "stroke-width": width }));
  }
}

function appendText(g: SVGGElement, a: Annotation, st: ReturnType<typeof resolveStyle>, at?: Pt): void {
  const p = at ?? a.points[0];
  const body = a.text ?? a.subject;
  if (!p || !body) return;
  const lines = body.split("\n");
  const fs = st.fontSize;
  const t = el("text", {
    x: p.x, y: p.y, fill: st.color, "font-size": fs, "font-family": "Helvetica, Arial, sans-serif",
    "font-weight": st.fontWeight ?? 500, "fill-opacity": st.opacity,
    ...(a.rotation ? { transform: `rotate(${a.rotation} ${p.x} ${p.y})` } : {}),
  });
  lines.forEach((line, i) => {
    const span = el("tspan", { x: p.x, dy: i === 0 ? 0 : fs * 1.25 });
    span.textContent = line;
    t.append(span);
  });
  // A halo keeps text legible over dense linework without hiding the drawing behind a fill.
  const halo = t.cloneNode(true) as SVGTextElement;
  halo.setAttribute("stroke", "#fff");
  halo.setAttribute("stroke-width", String(Math.max(1.5, fs * 0.18)));
  halo.setAttribute("stroke-linejoin", "round");
  halo.setAttribute("fill", "none");
  halo.setAttribute("stroke-opacity", "0.85");
  g.append(halo, t);
}

function appendStamp(g: SVGGElement, a: Annotation, st: ReturnType<typeof resolveStyle>): void {
  const p = a.points[0];
  const txt = a.text ?? "";
  if (!p || !txt) return;
  const fs = st.fontSize;
  const w = txt.length * fs * 0.58 + fs;
  const h = fs * 1.7;
  const rot = a.rotation ?? 0;
  const wrap = el("g", rot ? { transform: `rotate(${rot} ${p.x} ${p.y})` } : {});
  wrap.append(
    el("rect", {
      x: p.x, y: p.y - h / 2, width: w, height: h, rx: 2,
      fill: st.color, "fill-opacity": 0.08, stroke: st.color, "stroke-width": Math.max(1.2, st.width),
    }),
    (() => {
      const t = el("text", {
        x: p.x + fs / 2, y: p.y + fs * 0.36, fill: st.color, "font-size": fs,
        "font-family": "Helvetica, Arial, sans-serif", "font-weight": 700, "letter-spacing": fs * 0.04,
      });
      t.textContent = txt;
      return t;
    })(),
  );
  g.append(wrap);
}

/**
 * An issue pin: a teardrop with a sequence badge. Sized in *screen* units so it stays tappable at
 * any zoom — the one place where a markup deliberately does not scale with the sheet.
 */
function appendPin(g: SVGGElement, a: Annotation, o: DrawOpts): void {
  const p = a.points[0];
  if (!p) return;
  const s = 14 / o.zoom;                       // pin half-width in page units ≈ 14 screen px
  const color = a.style?.color ?? STATUS_COLORS[a.status];
  const g2 = el("g", { transform: `translate(${p.x} ${p.y})` });
  g2.append(el("path", {
    d: `M0,0 C${-s * 0.9},${-s * 1.1} ${-s},${-s * 2.1} 0,${-s * 2.6} C${s},${-s * 2.1} ${s * 0.9},${-s * 1.1} 0,0 Z`,
    fill: color, stroke: "#fff", "stroke-width": s * 0.12,
  }));
  const badge = a.ext?.["pinNumber"];
  if (badge !== undefined && badge !== null) {
    const t = el("text", {
      x: 0, y: -s * 1.5, fill: "#fff", "font-size": s * 0.95, "text-anchor": "middle",
      "font-family": "Helvetica, Arial, sans-serif", "font-weight": 700,
    });
    t.textContent = String(badge);
    g2.append(t);
  }
  g.append(g2);
}

/** The measured value, drawn beside the markup. */
function appendQuantityLabel(g: SVGGElement, a: Annotation, st: ReturnType<typeof resolveStyle>, o: DrawOpts): void {
  if (!a.quantity) return;
  const txt = formatQuantity(a.quantity, { feetInches: o.feetInches ?? true });
  if (!txt) return;
  const anchor = a.kind === "area" || a.kind === "volume" || a.kind === "polygon"
    ? centroid(a.points)
    : midpoint(a.points);
  const fs = Math.max(8, 11 / Math.max(0.35, Math.min(o.zoom, 1.6)));
  const t = el("text", {
    x: anchor.x, y: anchor.y - fs * 0.4, fill: st.color, "font-size": fs, "text-anchor": "middle",
    "font-family": "Helvetica, Arial, sans-serif", "font-weight": 700, "paint-order": "stroke",
    stroke: "#fff", "stroke-width": fs * 0.22, "stroke-linejoin": "round",
  });
  t.textContent = txt;
  g.append(t);
}

/** Selection chrome: a dashed bounds box plus square vertex handles, both screen-constant. */
function appendSelection(g: SVGGElement, a: Annotation, o: DrawOpts): void {
  const pad = 6 / o.zoom;
  const b = bbox(a.points);
  g.append(el("rect", {
    x: b.x - pad, y: b.y - pad, width: b.w + pad * 2, height: b.h + pad * 2,
    fill: "none", stroke: "#4a8cff", "stroke-width": 1.2 / o.zoom,
    "stroke-dasharray": `${4 / o.zoom} ${3 / o.zoom}`, class: "mpdf-sel-box",
  }));
  const hs = 4 / o.zoom;
  const handles = a.points.length === 2 && HANDLE_AS_BOX.has(a.kind)
    ? rectCorners(a.points[0]!, a.points[1]!)
    : a.points;
  handles.forEach((p, i) => {
    g.append(el("rect", {
      x: p.x - hs, y: p.y - hs, width: hs * 2, height: hs * 2,
      fill: "#fff", stroke: "#4a8cff", "stroke-width": 1 / o.zoom,
      class: "mpdf-handle", "data-handle": i,
    }));
  });
}

const HANDLE_AS_BOX = new Set(["rect", "ellipse", "highlight", "underline", "strikeout"]);

/** Per-line quads recorded by a text-select tool, if this markup came from a text selection. */
function textQuads(a: Annotation): { x: number; y: number; w: number; h: number }[] | null {
  const q = a.ext?.["quads"];
  return Array.isArray(q) && q.length ? (q as { x: number; y: number; w: number; h: number }[]) : null;
}

/** Fallback for a markup dragged as a box rather than selected as text. */
function boxQuad(pts: readonly Pt[]): { x: number; y: number; w: number; h: number }[] {
  if (pts.length < 2) return [];
  return [bbox([pts[0]!, pts[1]!])];
}

function midpoint(pts: readonly Pt[]): Pt {
  if (!pts.length) return { x: 0, y: 0 };
  if (pts.length === 1) return pts[0]!;
  const i = Math.floor((pts.length - 1) / 2);
  const a = pts[i]!, b = pts[i + 1] ?? a;
  return { x: (a.x + b.x) / 2, y: (a.y + b.y) / 2 };
}

/** The in-progress gesture preview. Deliberately plain: blue, dashed, no labels. */
export function drawDraft(kind: string, pts: readonly Pt[], zoom: number): SVGGElement {
  const g = el("g", { class: "mpdf-draft", "pointer-events": "none" });
  if (!pts.length) return g;
  const stroke = { stroke: "#4a8cff", "stroke-width": 1.6, fill: "none", "stroke-dasharray": `${5 / zoom} ${4 / zoom}` };
  const closed = kind === "area" || kind === "polygon" || kind === "volume" || kind === "cloud";
  if (kind === "rect" || kind === "ellipse" || kind === "highlight") {
    if (pts.length >= 2) {
      const b = bbox([pts[0]!, pts[1]!]);
      g.append(kind === "ellipse"
        ? el("ellipse", { cx: b.x + b.w / 2, cy: b.y + b.h / 2, rx: b.w / 2, ry: b.h / 2, ...stroke })
        : el("rect", { x: b.x, y: b.y, width: b.w, height: b.h, ...stroke }));
    }
  } else if (kind === "cloud" && pts.length >= 2) {
    g.append(el("path", { d: cloudPath(pts, 6, false), ...stroke }));
  } else if (kind === "ink") {
    g.append(el("path", { d: smoothPath(pts), stroke: "#4a8cff", "stroke-width": 1.6, fill: "none", "stroke-linecap": "round" }));
  } else {
    g.append(el("path", { d: linePath(pts, closed), ...stroke }));
  }
  const r = 3 / zoom;
  for (const p of pts) g.append(el("circle", { cx: p.x, cy: p.y, r, fill: "#4a8cff" }));
  return g;
}

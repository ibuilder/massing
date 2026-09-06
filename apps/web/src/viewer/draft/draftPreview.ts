/**
 * Draft preview — a scaled elevation of the element you are about to place, drawn from the values
 * in the form.
 *
 * ## Why this is not the glyph, and why the glyph could not become this
 *
 * `draftGlyph.ts` draws a line-art icon per IFC **class**, so every wall in the palette wears the
 * same drawing whatever the form says. That makes a ~90-row list scannable; it cannot tell you that
 * the desk you are about to place is eight metres wide, because the glyph never sees the numbers.
 *
 * This does. A preview is proportioned from the current parameter values, so **a mistyped dimension
 * is visible before you place it** rather than after you look at the model and wonder.
 *
 * ## The band is derived from the DEFAULTS, and that is the whole mechanism
 *
 * If the view rescaled to fit whatever you typed, an 8 m desk and a 0.8 m desk would draw
 * identically — a preview that always looks right is worth nothing, which is the same failure as a
 * check that always passes. So the view's height in metres is computed **once, from the element's
 * own default values**, and the shape is then drawn to true scale inside it. Type ten times the
 * default and the drawing runs off the top of the frame, which is the signal.
 *
 * The band is derived rather than tabulated: it is the element's bounding box at its defaults,
 * padded, snapped up to a round number of metres. A new element in `draftCatalog.ts` therefore gets
 * a sensible frame with no entry anywhere — nothing to forget to update.
 *
 * A metre grid is drawn behind the shape at every whole metre. It is the constant that makes the
 * scale readable: without a reference, "big rectangle" carries no information.
 *
 * ## What has no preview, and why that is a list rather than a silence
 *
 * `NO_PREVIEW` names every element that cannot have one, each with a reason.
 * `draftPreview.test.ts` derives the population from `DRAFT_ELEMENTS` and the family catalog and
 * fails when something is in neither — the same shape as `draftGlyph.test.ts`, for the same reason:
 * a table that silently omits a row reports full coverage over whatever it happens to contain.
 */
import type { DraftElement, ParamValues } from "./draftCatalog";

/** A shape in metre space, elevation view: x rightwards, y UP from the ground line. */
export type Shape =
  | { kind: "rect"; x: number; y: number; w: number; h: number }
  | { kind: "circle"; cx: number; cy: number; r: number };

export interface Preview {
  /** SVG path commands in a 0..100 × 0..100 viewBox, y already flipped to screen coordinates. */
  readonly d: readonly string[];
  /** The metre grid, separate so it can be drawn in a lighter stroke. */
  readonly grid: readonly string[];
  /** Metres represented by the full frame height — fixed for the element, from its defaults. */
  readonly viewMetres: number;
  /** The dimensions this drawing is of, for the caption beside it. Never rendered INSIDE the svg. */
  readonly caption: string;
  /** True when the shape does not fit the frame: the value is far from what the element expects. */
  readonly oversize: boolean;
}

/** Elements that cannot have a preview, each with the reason. Read by the test, not just by people. */
export const NO_PREVIEW: Record<string, string> = {
  mep: "`add_mep_terminal` bakes its width/depth/height into the recipe closure and exposes NO "
    + "params, so the form has nothing to get wrong and there is nothing to proportion a drawing "
    + "from. Reading the dims would mean changing the catalog to expose them; that is worth doing "
    + "if these ever become editable, and pointless while they are not.",
  content: "`place_content` takes {category, point} and sizes the item from its own catalog entry — "
    + "the element has no params at all, so there is nothing in the form to proportion a drawing "
    + "from. Sizing them client-side would mean duplicating the server's catalog, and a preview "
    + "drawn from a second copy of the numbers is a preview that can disagree with what is placed.",
  add_grid: "A grid datum has no extent of its own: `add_grid` authors lines across the whole "
    + "storey, so there is no shape whose size a value could get wrong.",
};

/** Nominal W-shape depth in metres, read from the name: W12x26 is nominally 12 inches deep.
 *
 *  Nominal, not actual — a W12 is about 12.2 in — and that is the right precision here: the preview
 *  answers "roughly how deep is this section", and carrying the real AISC table into the browser to
 *  refine a thumbnail by 2% would duplicate `services/data/.../steel.py` for no gain. */
function wShapeDepth(section: string): number | null {
  const m = /^W(\d+)x/.exec(String(section));
  return m?.[1] ? (Number(m[1]) * 0.0254) : null;
}

/** Imperial rebar: #5 is 5/8 inch diameter. The number IS the size in eighths. */
function rebarDiameter(size: string): number | null {
  const m = /^#(\d+)$/.exec(String(size));
  return m?.[1] ? (Number(m[1]) / 8) * 0.0254 : null;
}

const num = (v: unknown, fallback: number): number => {
  const n = Number(v);
  return Number.isFinite(n) && n > 0 ? n : fallback;
};

/** A run of "wall" or "beam" long enough to read as one, for elements whose length comes from the
 *  clicked points rather than the form. Drawn dashed at the ends by `shapesFor`'s callers? No — kept
 *  simple: the run is just drawn, and the caption names only the dimensions the form controls, so
 *  nothing claims the length is a value anyone typed. */
const RUN = 2.0;

/** The shapes and caption for one element at one set of values, in metres. */
function shapesFor(el: DraftElement, v: ParamValues): { shapes: Shape[]; caption: string } | null {
  const key = el.key;
  if (key.startsWith("family:")) {
    const w = num(v.width, 1), h = num(v.height, 1);
    return { shapes: [{ kind: "rect", x: 0, y: 0, w, h }], caption: `${w} × ${h} m (w × h)` };
  }
  if (key.startsWith("cov:")) {
    const t = num(v.thickness, 0.02);
    return { shapes: [{ kind: "rect", x: 0, y: 0, w: RUN, h: t }], caption: `${t} m thick` };
  }
  switch (key) {
    case "wall": {
      const h = num(v.height, 3), t = num(v.thickness, 0.2);
      // A SECTION, not an elevation: both numbers the form controls are in it, and the length is
      // not, so the drawing cannot imply a length nobody chose.
      return { shapes: [{ kind: "rect", x: 0, y: 0, w: t, h }], caption: `${h} m high · ${t} m thick` };
    }
    case "slab":
    case "roof": {
      const t = num(v.thickness, 0.2);
      return { shapes: [{ kind: "rect", x: 0, y: 0, w: RUN, h: t }], caption: `${t} m thick` };
    }
    case "extrusion": {
      const h = num(v.height, 3), z = Number(v.z) || 0;
      return { shapes: [{ kind: "rect", x: 0, y: z, w: RUN, h }],
               caption: `${h} m high${z ? ` · base at ${z} m` : ""}` };
    }
    case "railing": {
      const h = num(v.height, 1.1);
      return { shapes: [{ kind: "rect", x: 0, y: 0, w: 0.05, h },
                        { kind: "rect", x: 0, y: h - 0.05, w: RUN, h: 0.05 },
                        { kind: "rect", x: RUN - 0.05, y: 0, w: 0.05, h }],
               caption: `${h} m high` };
    }
    case "stair":
    case "ramp": {
      const w = num(v.width, 1.2);
      // A plan swathe: width is the only value, so the frame shows it across a run.
      return { shapes: [{ kind: "rect", x: 0, y: 0, w: RUN, h: w }], caption: `${w} m wide` };
    }
    case "column": {
      const h = num(v.height, 3), w = num(v.width, 0.4);
      return { shapes: [{ kind: "rect", x: 0, y: 0, w, h }], caption: `${h} m high · ${w} m wide` };
    }
    case "beam": {
      const w = num(v.width, 0.3), d = num(v.depth, 0.5);
      return { shapes: [{ kind: "rect", x: 0, y: 0, w, h: d }], caption: `${w} × ${d} m section` };
    }
    case "steel_column": {
      const h = num(v.height, 3.6), d = wShapeDepth(String(v.section)) ?? 0.3;
      return { shapes: [{ kind: "rect", x: 0, y: 0, w: d, h }],
               caption: `${h} m high · ${String(v.section)} (~${(d * 1000) | 0} mm deep)` };
    }
    case "steel_beam": {
      const d = wShapeDepth(String(v.section)) ?? 0.3;
      return { shapes: [{ kind: "rect", x: 0, y: 0, w: RUN, h: d }],
               caption: `${String(v.section)} · ~${(d * 1000) | 0} mm deep` };
    }
    case "rebar": {
      const r = (rebarDiameter(String(v.size)) ?? 0.016) / 2;
      return { shapes: [{ kind: "circle", cx: r, cy: r, r }],
               caption: `${String(v.size)} · ~${(r * 2000) | 0} mm diameter` };
    }
    case "footing": {
      const w = num(v.width, 1.5), t = num(v.thickness, 0.4);
      return { shapes: [{ kind: "rect", x: 0, y: 0, w, h: t }], caption: `${w} m wide · ${t} m thick` };
    }
    case "duct":
    case "cable_tray": {
      const s = num(v.size, 0.3);
      return { shapes: [{ kind: "rect", x: 0, y: 0, w: s, h: s }], caption: `${s} m section` };
    }
    case "pipe":
    case "wire": {
      const s = num(v.size, 0.05);
      return { shapes: [{ kind: "circle", cx: s / 2, cy: s / 2, r: s / 2 }],
               caption: `${s} m diameter` };
    }
    default:
      return null;
  }
}

/** The reason this element has no preview, or "" when it should have one. */
export function noPreviewReason(el: DraftElement): string {
  if (el.key.startsWith("content:")) return NO_PREVIEW.content ?? "";
  if (el.key.startsWith("mep:")) return NO_PREVIEW.mep ?? "";
  return NO_PREVIEW[el.key] ?? "";
}

const BANDS = [0.25, 0.5, 1, 2, 3, 5, 8, 12, 20, 40];

/** The frame height in metres for an element — computed from its DEFAULTS, never from live values. */
export function bandFor(el: DraftElement): number {
  const defaults: ParamValues = {};
  for (const p of el.params) defaults[p.key] = p.default;
  const at = shapesFor(el, defaults);
  const extent = at ? Math.max(...at.shapes.map(bboxTop), ...at.shapes.map(bboxRight), 0.1) : 1;
  const want = extent * 1.6;
  return BANDS.find((b) => b >= want) ?? BANDS[BANDS.length - 1] ?? 40;
}

const bboxTop = (s: Shape): number => (s.kind === "rect" ? s.y + s.h : s.cy + s.r);
const bboxRight = (s: Shape): number => (s.kind === "rect" ? s.x + s.w : s.cx + s.r);

/**
 * The preview for `el` at `values`, or null when the element is one of the `NO_PREVIEW` cases.
 *
 * The frame is 100×100 units; `viewMetres` is what its height represents. Shapes are drawn to true
 * scale and CENTRED horizontally, so a wide value grows in both directions rather than sliding off
 * one side — the eye reads "too wide for the frame" faster than "gone".
 */
export function previewFor(el: DraftElement, values: ParamValues): Preview | null {
  if (noPreviewReason(el)) return null;
  const built = shapesFor(el, values);
  if (!built) return null;
  const viewMetres = bandFor(el);
  const k = 100 / viewMetres;                       // units per metre
  const width = Math.max(...built.shapes.map(bboxRight), 0.01);
  const top = Math.max(...built.shapes.map(bboxTop), 0.01);
  const offX = 50 - (width * k) / 2;                // centre the shape horizontally
  const y = (m: number) => 100 - m * k;             // metres up  ->  svg y down

  const d: string[] = [];
  for (const s of built.shapes) {
    if (s.kind === "rect") {
      const x0 = offX + s.x * k, x1 = offX + (s.x + s.w) * k;
      d.push(`M${r(x0)} ${r(y(s.y))}H${r(x1)}V${r(y(s.y + s.h))}H${r(x0)}Z`);
    } else {
      const cx = offX + s.cx * k, cy = y(s.cy), rr = Math.max(s.r * k, 0.5);
      d.push(`M${r(cx - rr)} ${r(cy)}a${r(rr)} ${r(rr)} 0 1 0 ${r(rr * 2)} 0`
             + `a${r(rr)} ${r(rr)} 0 1 0 ${r(-rr * 2)} 0Z`);
    }
  }
  const grid: string[] = [];
  const step = viewMetres <= 1 ? 0.25 : viewMetres <= 3 ? 0.5 : 1;
  for (let m = step; m < viewMetres + 1e-9; m += step) grid.push(`M0 ${r(y(m))}H100`);

  return { d, grid, viewMetres, caption: built.caption, oversize: top > viewMetres || width > viewMetres };
}

/** 2 decimal places, without a trailing ".00" — keeps the path strings short and comparable. */
const r = (n: number): string => String(Math.round(n * 100) / 100);

/**
 * Build the preview as SVG nodes.
 *
 * `createElementNS` and never `innerHTML`, and **no `<text>` or `<title>` anywhere**: an `<svg>` with
 * a `<title>` contributes to the enclosing element's `textContent`, which is how every palette row
 * silently came to read "wallWall IfcWall" the first time a glyph carried its name. The caption is
 * the caller's job, in a sibling node.
 */
export function previewElement(p: Preview): SVGSVGElement {
  const NS = "http://www.w3.org/2000/svg";
  const svg = document.createElementNS(NS, "svg");
  svg.setAttribute("viewBox", "0 0 100 100");
  svg.setAttribute("width", "104");
  svg.setAttribute("height", "104");
  svg.setAttribute("aria-hidden", "true");
  svg.setAttribute("focusable", "false");
  svg.style.cssText = "display:block;border:1px solid var(--line,#3a3a3a);border-radius:3px";

  const gridPath = document.createElementNS(NS, "path");
  gridPath.setAttribute("d", p.grid.join(" "));
  gridPath.setAttribute("fill", "none");
  gridPath.setAttribute("stroke", "currentColor");
  gridPath.setAttribute("stroke-width", "0.5");
  gridPath.setAttribute("opacity", "0.25");
  svg.appendChild(gridPath);

  const shape = document.createElementNS(NS, "path");
  shape.setAttribute("d", p.d.join(" "));
  shape.setAttribute("fill", "currentColor");
  shape.setAttribute("fill-opacity", p.oversize ? "0.25" : "0.45");
  shape.setAttribute("stroke", "currentColor");
  shape.setAttribute("stroke-width", "1.5");
  shape.setAttribute("stroke-linejoin", "round");
  svg.appendChild(shape);
  return svg;
}

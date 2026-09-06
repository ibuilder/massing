/**
 * UX-3 — a line-art glyph for every element the Draft palette can list, so a 90-row list is
 * scannable by shape instead of only by reading.
 *
 * **These are CLASS GLYPHS, not rendered previews, and the difference is the point.** The roadmap
 * item asks for "thumbnails"; a real thumbnail would render the actual parametric geometry at the
 * user's current parameter values. This does not do that. It maps the IFC class to a fixed piece of
 * line art — a wall reads as a wall whether it is 3 m or 30 m long. That is genuinely less than the
 * item names, and saying so here is cheaper than a future reader discovering it from the code.
 * *(The roadmap entry is corrected in the same change rather than ticked.)*
 *
 * WHY A DESCRIPTOR AND NOT AN SVG STRING
 *     The obvious shape is `glyph(cls): string` returning `<svg>…</svg>` and an `innerHTML =`.
 *     That is what the palette row did for its label, and it is the reason this file returns DATA:
 *     `draftPanel` now builds every node with `createElementNS` + `textContent`, so no string from
 *     the server — a family label, an IFC class — is ever parsed as markup. **This is a latent
 *     hardening, not a live fix, and the distinction matters**: `/families/catalog` serves
 *     `families.catalog()`, a static parametric list, and `/content/catalog` a static dict, so
 *     nothing attacker-controlled reaches that row TODAY. But `import_types_from_ifc` copies
 *     `IfcTypeProduct.Name` verbatim out of an uploaded third-party IFC, and the palette exists to
 *     grow with server-supplied content. The row is one route-change away from being live, and
 *     building it out of data costs nothing.
 *
 * OFFLINE BY CONSTRUCTION
 *     No icon font, no sprite sheet, no fetch — path data compiled into the bundle. The viewer's
 *     offline non-negotiable has already been broken once by a CDN import (v0.3.1113); an icon set
 *     is exactly the kind of dependency that reintroduces it.
 *
 * THE POPULATION IS DERIVED, NOT LISTED BY EYE
 *     `draftGlyph.test.ts` reads the three catalogs that can put a row in this list — the TS
 *     `DRAFT_ELEMENTS`, `services/data/src/aec_data/content.py` and `.../families.py` — normalises
 *     each `ifc_class`, and fails if any lacks an EXPLICIT entry below. Adding a draft element with
 *     a new class reds the build rather than silently drawing the fallback. Server-supplied classes
 *     outside those three (a future route) fall back deliberately; that is a documented degradation,
 *     not a gap in the table.
 */

/**
 * One glyph: the SVG path `d` strings drawn in a 16×16 box, plus a human name.
 *
 * **`title` is metadata and is NOT rendered.** It names the entry in the gate's failure messages and
 * documents what each row of the table is meant to depict. The first draft did render it as an
 * `<svg><title>`, and `draftPanel.test.ts` went red: a `<title>` node counts toward the row's
 * `textContent`, so every palette row silently began with "wall" / "planting" before its label.
 * Nothing about the drawing was wrong — the row's TEXT was, and only an existing test that read it
 * said so. The glyph is `aria-hidden` and the row already names the element twice in text, so there
 * was nothing for the tooltip to add.
 */
export interface Glyph {
  readonly d: readonly string[];
  readonly title: string;
}

/** The box every path below is authored in. Kept here so the panel cannot disagree with the data. */
export const GLYPH_VIEWBOX = "0 0 16 16";

/**
 * `IfcWallType` → `Wall`. Families arrive as `Ifc…Type` (they are type products) and built-ins as
 * `Ifc…`; a door type and a door want the same glyph, so the table is keyed by the stripped name.
 */
export function normaliseIfcClass(ifcClass: string): string {
  const bare = ifcClass.startsWith("Ifc") ? ifcClass.slice(3) : ifcClass;
  return bare.endsWith("Type") ? bare.slice(0, -4) : bare;
}

/**
 * Drawn when a class has no explicit entry: a plain box with a centre dot. Deliberately the only
 * glyph in the file that is a bare rectangle — every real one carries a second path — so an
 * unrecognised class is visibly unrecognised rather than quietly wearing someone else's shape.
 */
export const FALLBACK_GLYPH: Glyph = {
  d: ["M3 3h10v10H3z", "M8 8h0.01"],
  title: "element",
};

/**
 * Explicit, keyed by the normalised class. Several classes share a shape on purpose (an elbow is an
 * elbow whether it carries air or water); nothing is inferred from the name at runtime.
 */
export const GLYPHS: Readonly<Record<string, Glyph>> = {
  // --- architectural shell ---
  Wall: { title: "wall", d: ["M2 6h12M2 10h12", "M2 6v4M14 6v4"] },
  Slab: { title: "slab", d: ["M8 4l6 3.5-6 3.5-6-3.5z"] },
  Roof: { title: "roof", d: ["M1.5 12L8 4.5 14.5 12", "M4 12h8"] },
  Covering: { title: "covering", d: ["M2 8.5h12M2 11.5h12", "M4.5 8.5v3M8 8.5v3M11.5 8.5v3"] },
  CurtainWall: { title: "curtain wall", d: ["M2.5 2.5h11v11h-11z", "M6.2 2.5v11M9.8 2.5v11", "M2.5 8h11"] },
  Door: { title: "door", d: ["M4 13.5V3.5h1.4v10z", "M5.4 3.5A10 10 0 0114 12.6", "M4 13.5h10"] },
  Window: { title: "window", d: ["M2.5 4.5h11v7h-11z", "M8 4.5v7"] },
  Stair: { title: "stair", d: ["M2 13.5v-2.5h3v-2.5h3V6h3V3.5h3"] },
  Ramp: { title: "ramp", d: ["M2 13.5h12", "M2 13.5L14 4.5"] },
  Railing: { title: "railing", d: ["M2 5h12M2 12.5h12", "M4.5 5v7.5M8 5v7.5M11.5 5v7.5"] },
  BuildingElementProxy: { title: "mass", d: ["M8 2.5l5.5 3v5L8 13.5 2.5 10.5v-5z", "M8 2.5v5l5.5 3M8 7.5l-5.5 3"] },
  Annotation: { title: "annotation", d: ["M2 4.5h8l4 3.5-4 3.5H2z", "M4.5 8h5"] },

  // --- structure ---
  Column: { title: "column", d: ["M6 3.5h4v9H6z", "M4 3.5h8M4 12.5h8"] },
  Beam: { title: "beam", d: ["M3 4h10M3 12h10", "M8 4v8"] },
  Footing: { title: "footing", d: ["M6.5 3h3v5h-3z", "M2.5 8h11v5h-11z"] },
  ReinforcingBar: { title: "rebar", d: ["M2.5 12.5h6a2.5 2.5 0 002.5-2.5V3.5", "M4.5 11v3M7 11v3", "M9 5h4M9 8h4"] },

  // --- MEP distribution ---
  DuctSegment: { title: "duct", d: ["M2 5.5h12v5H2z", "M6 5.5v5M10 5.5v5"] },
  DuctFitting: { title: "duct fitting", d: ["M2 4.5h5.5a4 4 0 014 4V14", "M2 9.5h1a2 2 0 012 2V14"] },
  PipeSegment: { title: "pipe", d: ["M2 6h12M2 10h12", "M10 5v6"] },
  PipeFitting: { title: "pipe fitting", d: ["M2 5h4.5A4.5 4.5 0 0111 9.5V14", "M2 9h1.5a3 3 0 013 3V14"] },
  CableCarrierSegment: { title: "cable tray", d: ["M2 4.5v7h12v-7", "M5 4.5v7M8 4.5v7M11 4.5v7"] },
  CableSegment: { title: "cable", d: ["M2 11c3 0 3-6 6-6s3 6 6 6"] },

  // --- MEP devices and terminals ---
  AirTerminal: { title: "air terminal", d: ["M3 3h10v10H3z", "M3 3l10 10M13 3L3 13"] },
  SanitaryTerminal: { title: "sanitary fixture", d: ["M3 6.5h10v2.5a5 5 0 01-10 0z", "M8 3v3.5"] },
  WasteTerminal: { title: "drain", d: ["M8 3a5 5 0 100 10 5 5 0 000-10z", "M5 8h6M8 5v6"] },
  LightFixture: { title: "light fixture", d: ["M8 5.5a3 3 0 00-2 5.2v1.3h4v-1.3A3 3 0 008 5.5z", "M8 2v1.5M3 8h1.5M11.5 8H13"] },
  Outlet: { title: "outlet", d: ["M8 2.5a5.5 5.5 0 100 11 5.5 5.5 0 000-11z", "M6.5 6.5v3M9.5 6.5v3"] },
  ElectricDistributionBoard: { title: "panel", d: ["M3 2.5h10v11H3z", "M5.5 5h5M5.5 8h5M5.5 11h5"] },
  ElectricAppliance: { title: "appliance", d: ["M3 3h10v10H3z", "M10.5 5.2a1.4 1.4 0 100 2.8 1.4 1.4 0 000-2.8z", "M5 10.5h3"] },
  UnitaryEquipment: { title: "equipment", d: ["M2.5 4h11v8h-11z", "M6 8h4M8 6v4", "M4.5 4v8"] },
  Alarm: { title: "alarm", d: ["M5 11.5a3 4.5 0 016 0z", "M8 3v1.5", "M6.8 11.5a1.2 1.2 0 002.4 0"] },
  Sensor: { title: "sensor", d: ["M4.5 11.5a3.5 3.5 0 017 0z", "M2.5 8.5A6 6 0 018 5a6 6 0 015.5 3.5"] },
  CommunicationsAppliance: { title: "comms outlet", d: ["M8 13V7.5", "M5.5 6A4 4 0 0110.5 6", "M3.5 4a7 7 0 019 0"] },

  // --- content ---
  Furniture: { title: "furniture", d: ["M2.5 6h11v1.5h-11z", "M4 7.5v5.5M12 7.5v5.5"] },
  GeographicElement: { title: "planting", d: ["M8 3a3.5 3.5 0 100 7 3.5 3.5 0 000-7z", "M8 10v3.5", "M6 13.5h4"] },
  TransportElement: { title: "transport", d: ["M3 2.5h10v11H3z", "M8 2.5v11", "M5.5 7l0-2 1.5 2M9 9l1.5 2 1.5-2"] },
};

/** The glyph for an IFC class — the explicit entry, or the documented fallback. */
export function draftGlyph(ifcClass: string): Glyph {
  return GLYPHS[normaliseIfcClass(ifcClass)] ?? FALLBACK_GLYPH;
}

/** True when the class has an explicit glyph. Used by the gate; also lets callers spot degradation. */
export function hasExplicitGlyph(ifcClass: string): boolean {
  return normaliseIfcClass(ifcClass) in GLYPHS;
}

/**
 * Build the `<svg>` for a glyph with `createElementNS` — no markup string is parsed anywhere on this
 * path. `aria-hidden`: the row already names the element in text, so a second announcement of the
 * same thing is noise to a screen reader. No `<title>` child — see the note on `Glyph.title`.
 */
export function glyphElement(g: Glyph, doc: Document = document): SVGSVGElement {
  const NS = "http://www.w3.org/2000/svg";
  const svg = doc.createElementNS(NS, "svg");
  svg.setAttribute("viewBox", GLYPH_VIEWBOX);
  svg.setAttribute("width", "15");
  svg.setAttribute("height", "15");
  svg.setAttribute("fill", "none");
  svg.setAttribute("stroke", "currentColor");
  svg.setAttribute("stroke-width", "1.2");
  svg.setAttribute("stroke-linecap", "round");
  svg.setAttribute("stroke-linejoin", "round");
  svg.setAttribute("aria-hidden", "true");
  svg.setAttribute("focusable", "false");
  svg.style.flex = "0 0 auto";
  svg.style.opacity = "0.8";
  for (const d of g.d) {
    const path = doc.createElementNS(NS, "path");
    path.setAttribute("d", d);
    svg.appendChild(path);
  }
  return svg;
}

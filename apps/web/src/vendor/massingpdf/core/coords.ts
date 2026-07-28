/**
 * The coordinate spaces, and the transforms between them. Three spaces, and confusing them is the
 * single richest source of bugs in a markup tool:
 *
 * - **page space** — PDF user units (1/72"), top-left origin, y down, *unrotated*. All geometry is
 *   stored here. Zoom- and rotation-independent.
 * - **display space** — page space with the viewer's rotation applied, still in PDF units.
 * - **client space** — CSS pixels on screen. `display × zoom`, offset by the element's box.
 */
import type { Pt } from "./types";

export type Rotation = 0 | 90 | 180 | 270;

export const normalizeRotation = (r: number): Rotation =>
  ((((Math.round(r / 90) * 90) % 360) + 360) % 360) as Rotation;

/** Display box for a page of `w × h` under `rotation`. */
export function displaySize(w: number, h: number, rotation: Rotation): { w: number; h: number } {
  return rotation === 90 || rotation === 270 ? { w: h, h: w } : { w, h };
}

/** page → display. */
export function pageToDisplay(p: Pt, w: number, h: number, rotation: Rotation): Pt {
  switch (rotation) {
    case 90: return { x: h - p.y, y: p.x };
    case 180: return { x: w - p.x, y: h - p.y };
    case 270: return { x: p.y, y: w - p.x };
    default: return { x: p.x, y: p.y };
  }
}

/** display → page. The inverse of `pageToDisplay`. */
export function displayToPage(d: Pt, w: number, h: number, rotation: Rotation): Pt {
  switch (rotation) {
    case 90: return { x: d.y, y: h - d.x };
    case 180: return { x: w - d.x, y: h - d.y };
    case 270: return { x: w - d.y, y: d.x };
    default: return { x: d.x, y: d.y };
  }
}

/**
 * The SVG group transform that maps page-space geometry into a display-space viewBox, so the
 * renderer can keep emitting unrotated page coordinates regardless of view rotation.
 */
export function rotationTransform(w: number, h: number, rotation: Rotation): string | null {
  switch (rotation) {
    case 90: return `translate(${h} 0) rotate(90)`;
    case 180: return `translate(${w} ${h}) rotate(180)`;
    case 270: return `translate(0 ${w}) rotate(270)`;
    default: return null;
  }
}

/** A pointer event → page space, given the overlay element's box. */
export function eventToPage(
  ev: { clientX: number; clientY: number },
  rect: { left: number; top: number },
  zoom: number,
  pageW: number,
  pageH: number,
  rotation: Rotation,
): Pt {
  const d = { x: (ev.clientX - rect.left) / zoom, y: (ev.clientY - rect.top) / zoom };
  return displayToPage(d, pageW, pageH, rotation);
}

/**
 * Units, drawing scales and quantity formatting.
 *
 * Two things generic annotators get wrong and every estimator notices: a drawing scale is a *named*
 * thing (`1/4" = 1'-0"`, `1:50`) that can be declared without drawing a calibration line, and an
 * imperial length is read as `12'-6 1/2"`, not `12.54 ft`.
 */
import type { Calibration, Pt, Quantity } from "./types";
import { angleAt, circumradius, pathLength, perimeter, polygonArea } from "./geometry";

/** Length units the engine knows, expressed in metres. */
export const LENGTH_UNITS = {
  mm: 0.001, cm: 0.01, m: 1, km: 1000,
  in: 0.0254, ft: 0.3048, yd: 0.9144, mi: 1609.344,
} as const;

export type LengthUnit = keyof typeof LENGTH_UNITS;

export const isLengthUnit = (u: string): u is LengthUnit => u in LENGTH_UNITS;

export const IMPERIAL: readonly string[] = ["in", "ft", "yd", "mi"];

/** Convert a length between units. */
export function convertLength(v: number, from: LengthUnit, to: LengthUnit): number {
  return (v * LENGTH_UNITS[from]) / LENGTH_UNITS[to];
}

/**
 * A named drawing scale. `unitsPerPoint` is what a calibration needs: how many real-world `unit`
 * one PDF point represents when the sheet is plotted at its intended size.
 *
 * A PDF point is 1/72". At `1/4" = 1'-0"`, one plotted inch is 4 feet, so one point is 4/72 ft.
 */
export interface ScalePreset {
  label: string;
  unit: LengthUnit;
  unitsPerPoint: number;
  system: "imperial" | "metric";
}

/** `denomInches` real feet per plotted inch → units-per-point in feet. */
const imperialScale = (label: string, feetPerInch: number): ScalePreset =>
  ({ label, unit: "ft", unitsPerPoint: feetPerInch / 72, system: "imperial" });

/** `1:n` → n mm of reality per plotted mm; a point is 25.4/72 mm. */
const metricScale = (n: number): ScalePreset =>
  ({ label: `1:${n}`, unit: "m", unitsPerPoint: (n * 25.4) / 72 / 1000, system: "metric" });

/** The scales that actually appear in a title block. Ordered coarse → fine within each system. */
export const SCALE_PRESETS: readonly ScalePreset[] = [
  imperialScale(`1" = 100'-0"`, 100),
  imperialScale(`1" = 50'-0"`, 50),
  imperialScale(`1" = 40'-0"`, 40),
  imperialScale(`1" = 30'-0"`, 30),
  imperialScale(`1" = 20'-0"`, 20),
  imperialScale(`1" = 10'-0"`, 10),
  imperialScale(`1/16" = 1'-0"`, 16),
  imperialScale(`3/32" = 1'-0"`, 32 / 3),
  imperialScale(`1/8" = 1'-0"`, 8),
  imperialScale(`3/16" = 1'-0"`, 16 / 3),
  imperialScale(`1/4" = 1'-0"`, 4),
  imperialScale(`3/8" = 1'-0"`, 8 / 3),
  imperialScale(`1/2" = 1'-0"`, 2),
  imperialScale(`3/4" = 1'-0"`, 4 / 3),
  imperialScale(`1" = 1'-0"`, 1),
  imperialScale(`1 1/2" = 1'-0"`, 2 / 3),
  imperialScale(`3" = 1'-0"`, 1 / 3),
  metricScale(2500), metricScale(1250), metricScale(1000), metricScale(500),
  metricScale(200), metricScale(100), metricScale(50), metricScale(20),
  metricScale(10), metricScale(5), metricScale(2), metricScale(1),
];

export const findPreset = (label: string): ScalePreset | undefined =>
  SCALE_PRESETS.find((p) => p.label === label);

/** Build a calibration from a named preset. */
export function calibrationFromPreset(label: string, page = 0): Calibration | null {
  const p = findPreset(label);
  if (!p) return null;
  return { unitsPerPoint: p.unitsPerPoint, unit: p.unit, label: p.label, source: "preset", page };
}

/**
 * Build a calibration from a drawn line of known real length.
 * `pagePoints` is the line's length in PDF points; `real` its length in `unit`.
 */
export function calibrationFromMeasure(pagePoints: number, real: number, unit: string, page = 0): Calibration | null {
  if (!(pagePoints > 0) || !(real > 0)) return null;
  const upp = real / pagePoints;
  // Report the nearest named scale when the drawn line lands within 1.5% of one — a reviewer who
  // calibrated by hand still wants to see "≈ 1/8\" = 1'-0\"" rather than a raw ratio.
  const near = isLengthUnit(unit)
    ? SCALE_PRESETS.find((p) => p.unit === unit && Math.abs(p.unitsPerPoint - upp) / p.unitsPerPoint < 0.015)
    : undefined;
  return { unitsPerPoint: upp, unit, label: near?.label, source: "measured", page };
}

/**
 * Parse a typed length. Understands `5`, `5m`, `5 ft`, `12'`, `6"`, `12'-6"`, `12' 6 1/2"`, `3/4"`.
 * Returns metres-agnostic `{ value, unit }` in whatever unit the user implied.
 */
export function parseLength(input: string, fallbackUnit = "m"): { value: number; unit: string } | null {
  const s = input.trim().toLowerCase().replace(/[–—]/g, "-");
  if (!s) return null;

  // Feet-and-inches: 12'-6 1/2"  |  12' 6"  |  12'  |  6 1/2"  |  3/4"
  const ftIn = s.match(/^(?:(\d+(?:\.\d+)?)\s*(?:'|ft|feet|foot))?\s*(?:-|\s)?\s*(?:(\d+(?:\.\d+)?)?\s*(?:(\d+)\/(\d+))?\s*(?:"|in|inch|inches))?$/);
  if (ftIn && (ftIn[1] || ftIn[2] || ftIn[3])) {
    const feet = ftIn[1] ? parseFloat(ftIn[1]) : 0;
    const inches = ftIn[2] ? parseFloat(ftIn[2]) : 0;
    const frac = ftIn[3] && ftIn[4] ? parseInt(ftIn[3], 10) / parseInt(ftIn[4], 10) : 0;
    const total = feet + (inches + frac) / 12;
    return total > 0 ? { value: total, unit: "ft" } : null;
  }

  // Decimal with an optional unit suffix.
  const m = s.match(/^(-?\d+(?:\.\d+)?)\s*([a-z]*)$/);
  if (!m) return null;
  const value = parseFloat(m[1]!);
  if (!isFinite(value)) return null;
  const raw = m[2] || fallbackUnit;
  const alias: Record<string, string> = {
    "": fallbackUnit, m: "m", meter: "m", meters: "m", metre: "m", metres: "m",
    mm: "mm", cm: "cm", km: "km", ft: "ft", feet: "ft", foot: "ft",
    in: "in", inch: "in", inches: "in", yd: "yd", yard: "yd", yards: "yd", mi: "mi",
  };
  return { value, unit: alias[raw] ?? raw };
}

/** Round a decimal inch value to the nearest `1/den` and render as `6 1/2`. */
function inchFraction(inches: number, den = 16): string {
  const whole = Math.floor(inches);
  let num = Math.round((inches - whole) * den);
  let d = den;
  if (num === 0) return String(whole);
  if (num === den) return String(whole + 1);
  while (num % 2 === 0 && d % 2 === 0) { num /= 2; d /= 2; }
  return whole ? `${whole} ${num}/${d}` : `${num}/${d}`;
}

/** Feet-and-inches display: `12'-6 1/2"`. */
export function formatFeetInches(feet: number, den = 16): string {
  const neg = feet < 0;
  const abs = Math.abs(feet);
  const ft = Math.floor(abs + 1e-9);
  const inches = (abs - ft) * 12;
  const roundedUp = Math.abs(inches - 12) < 1 / (2 * den);
  const f = roundedUp ? ft + 1 : ft;
  const inPart = roundedUp ? "0" : inchFraction(inches, den);
  return `${neg ? "-" : ""}${f}'-${inPart}"`;
}

export interface FormatOpts {
  /** Decimal places for metric and for non-length quantities. */
  precision?: number;
  /** Render imperial lengths as feet-and-inches instead of decimal feet. */
  feetInches?: boolean;
  /** Denominator for the inch fraction (8, 16, 32). */
  denominator?: number;
}

/** Format a measured quantity for the sheet label and the markup list. */
export function formatQuantity(q: Quantity | undefined, opts: FormatOpts = {}): string {
  if (!q) return "";
  const { precision = 2, feetInches = true, denominator = 16 } = opts;
  const u = q.unit;
  if (u === "ea") return `${Math.round(q.value)} ea`;
  if (u === "°") return `${q.value.toFixed(1)}°`;
  if (u === "ft" && feetInches) return formatFeetInches(q.value, denominator);
  if (u === "ft²" && feetInches) return `${q.value.toFixed(precision)} SF`;
  if (u === "ft³" && feetInches) return `${q.value.toFixed(precision)} CF`;
  return `${q.value.toFixed(precision)} ${u}`;
}

/** Human label for a calibration, for the status bar. */
export function formatCalibration(c: Calibration | undefined): string {
  if (!c) return "Not calibrated";
  if (c.label) return c.label;
  const perUnit = 1 / c.unitsPerPoint;
  return `1 ${c.unit} = ${perUnit.toFixed(1)} pt`;
}

/**
 * Derive the quantity for a measurement from its page-space geometry and the page calibration.
 * Returns `null` when the kind needs a calibration and none is set — the caller surfaces that as
 * "calibrate first" rather than silently reporting a meaningless number.
 */
export function measure(
  kind: string,
  pts: readonly Pt[],
  cal: Calibration | undefined,
  depth?: number,
): Quantity | null {
  if (kind === "count") return { value: pts.length || 1, unit: "ea", raw: pts.length || 1 };
  if (kind === "angle") {
    if (pts.length < 3) return null;
    return { value: angleAt(pts[0]!, pts[1]!, pts[2]!), unit: "°" };
  }
  if (!cal || !(cal.unitsPerPoint > 0)) return null;
  const k = cal.unitsPerPoint;
  switch (kind) {
    case "distance": {
      const raw = pathLength(pts);
      return { value: raw * k, unit: cal.unit, raw };
    }
    case "perimeter": {
      const raw = perimeter(pts);
      return { value: raw * k, unit: cal.unit, raw };
    }
    case "radius": {
      if (pts.length < 3) return null;
      const raw = circumradius(pts[0]!, pts[1]!, pts[2]!);
      return { value: raw * k, unit: cal.unit, raw };
    }
    case "area": {
      const raw = polygonArea(pts);
      return { value: raw * k * k, unit: `${cal.unit}²`, raw };
    }
    case "volume": {
      const raw = polygonArea(pts);
      const d = depth ?? 0;
      return { value: raw * k * k * d, unit: `${cal.unit}³`, raw, depth: d };
    }
    default:
      return null;
  }
}

/** Recompute a stored quantity against a new calibration, using the retained `raw` magnitude. */
export function recalculate(q: Quantity, kind: string, cal: Calibration): Quantity {
  if (q.raw === undefined || q.unit === "ea" || q.unit === "°") return q;
  const k = cal.unitsPerPoint;
  if (kind === "area") return { ...q, value: q.raw * k * k, unit: `${cal.unit}²` };
  if (kind === "volume") return { ...q, value: q.raw * k * k * (q.depth ?? 0), unit: `${cal.unit}³` };
  return { ...q, value: q.raw * k, unit: cal.unit };
}

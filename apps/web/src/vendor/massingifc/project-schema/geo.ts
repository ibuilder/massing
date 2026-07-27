import type { IsoTimestamp, Matrix4, Vec3 } from "./common.js";

/**
 * Georeferencing.
 *
 * Shared rather than owned by any one family: a reference model, a laser scan, a Gaussian splat and
 * a site boundary all need to say where on Earth they are, and they need to say it the same way. A
 * transform alone is not georeferencing — it places geometry relative to a project origin nobody
 * else knows, which is why a scan aligned only by matrix cannot be checked against a survey or
 * dropped into a GIS scene.
 */

/**
 * An authority-qualified CRS code, e.g. `"EPSG:27700"`.
 *
 * Kept as a string rather than an enum because the useful set is the EPSG registry, which is tens
 * of thousands of entries and changes without this codebase being rebuilt.
 */
export type CrsCode = string;

export type LinearUnit = "m" | "mm" | "cm" | "ft" | "us-ft";

/** Metres per unit. Note `ft` and `us-ft` differ — by ~2ppm, which is metres over a large site. */
export const METRES_PER_UNIT: Readonly<Record<LinearUnit, number>> = Object.freeze({
  m: 1,
  mm: 0.001,
  cm: 0.01,
  ft: 0.3048,
  "us-ft": 1200 / 3937,
});

/** Splits `"EPSG:27700"` into its parts. Returns `undefined` for anything not authority-qualified. */
export function parseCrsCode(code: CrsCode): { readonly authority: string; readonly code: string } | undefined {
  const match = /^([A-Za-z][A-Za-z0-9_-]*):([A-Za-z0-9._-]+)$/.exec(code.trim());
  if (!match) return undefined;
  const [, authority, identifier] = match;
  if (authority === undefined || identifier === undefined) return undefined;
  return { authority: authority.toUpperCase(), code: identifier };
}

/** Converts a length between linear units, via metres. */
export function convertLength(value: number, from: LinearUnit, to: LinearUnit): number {
  if (from === to) return value;
  return (value * METRES_PER_UNIT[from]) / METRES_PER_UNIT[to];
}

export type GeoReferenceMethod =
  /** Established by a surveyor against known control. */
  | "survey"
  /** From GNSS on the capture device. */
  | "gps"
  /** Solved from matched control points. */
  | "control-points"
  /** Stated by a human without independent verification. */
  | "declared"
  /** Nothing verified it. Present so the absence of evidence is recorded rather than implied. */
  | "assumed";

export interface GeoAccuracy {
  /** Metres, 1-sigma. */
  readonly horizontal?: number;
  readonly vertical?: number;
}

export interface GeoReference {
  /** CRS the source data is expressed in. */
  readonly sourceCrs: CrsCode;
  /** CRS the project works in. Absent means the source CRS is also the working one. */
  readonly targetCrs?: CrsCode;
  /**
   * Vertical datum, e.g. `"EGM2008"`, `"ODN"`, `"NAVD88"`.
   *
   * Separate from the horizontal CRS because they are genuinely independent: two datasets can
   * agree exactly in plan and be a metre apart in height, which is the difference between a slab
   * that clashes and one that does not.
   */
  readonly verticalDatum?: string;
  readonly units: LinearUnit;
  /**
   * Offset subtracted from world coordinates to keep scene values near the origin.
   *
   * Projected coordinates run to six or seven digits (a British National Grid easting is ~530000).
   * A 32-bit float holds about seven significant digits, so geometry rendered at true coordinates
   * jitters visibly and z-fights. Every renderer works in a local frame; recording the offset is
   * what makes that frame reversible instead of a lossy fudge.
   */
  readonly originOffset?: Vec3;
  /** Local frame to georeferenced frame, when the data was captured in an engineering grid. */
  readonly localToGlobal?: Matrix4;
  /** Rotation from project north to true north, degrees clockwise. */
  readonly trueNorthAngle?: number;
  readonly method?: GeoReferenceMethod;
  readonly accuracy?: GeoAccuracy;
  readonly establishedAt?: IsoTimestamp;
}

/** Axis-aligned bounds. `z` is optional because plan-only extents are common in GIS sources. */
export interface Extent {
  readonly xmin: number;
  readonly ymin: number;
  readonly zmin?: number;
  readonly xmax: number;
  readonly ymax: number;
  readonly zmax?: number;
}

export function extentIsValid(extent: Extent): boolean {
  if (extent.xmax < extent.xmin || extent.ymax < extent.ymin) return false;
  if (extent.zmin !== undefined && extent.zmax !== undefined && extent.zmax < extent.zmin) {
    return false;
  }
  return true;
}

/** Longest horizontal span, in the extent's own units. Used for plausibility checks. */
export function extentSpan(extent: Extent): number {
  return Math.max(extent.xmax - extent.xmin, extent.ymax - extent.ymin);
}

/**
 * Products derived from the same capture as a reality dataset.
 *
 * Held as links rather than embedded because they arrive at different times — an orthomosaic can
 * take hours of external processing after the splat is already viewable — and because they are
 * usually large files a project references rather than owns.
 */
export interface RealityDerivatives {
  readonly sourceImageryUri?: string;
  readonly orthomosaicUri?: string;
  readonly pointCloudUri?: string;
  readonly meshUri?: string;
  /** Digital surface model. */
  readonly dsmUri?: string;
  /** Digital terrain model. */
  readonly dtmUri?: string;
}

/**
 * What a dataset may legitimately be used for.
 *
 * A Gaussian splat is superb for looking at and unsuitable for measuring: it is a view-dependent
 * radiance representation, not a surface. Recording intent lets the platform refuse to measure
 * against one instead of silently returning a number that looks like a dimension.
 */
export type DatasetPurpose = "visualization" | "inspection" | "context" | "analysis";

/** Purposes for which a dataset may back a measurement or a derived authored object. */
export const ANALYSIS_PURPOSES: readonly DatasetPurpose[] = ["analysis"];

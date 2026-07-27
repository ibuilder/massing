import type { ElementRef, Id, IsoTimestamp, Matrix4, Provenance, Vec3 } from "./common.js";
import type { DatasetPurpose, Extent, GeoReference, RealityDerivatives } from "./geo.js";

export type TwinObjectKind =
  | "three-group"
  | "gltf"
  | "point-cloud"
  /**
   * A radiance-field scene of oriented Gaussians.
   *
   * Kept a first-class kind rather than folded into "mesh-scan" because it is not a surface: it
   * renders convincingly and measures badly, and the platform needs to be able to tell them apart.
   */
  | "gaussian-splat"
  | "mesh-scan"
  | "image-anchor"
  | "sensor"
  | "equipment"
  | "other";

/**
 * An observed or generated object living alongside the BIM models.
 *
 * Twin records stay deliberately loose about BIM semantics. A scan, a sensor and a generated
 * `THREE.Group` are evidence about the world, not authored building elements — forcing them into
 * IFC semantics on arrival destroys information and blocks the workflows that make twins useful.
 * Promotion into authored geometry is an explicit, later decision (`TwinPromotionRecord`).
 */
export interface TwinObjectRecord {
  readonly id: Id;
  readonly name: string;
  readonly kind: TwinObjectKind;
  /** Where the runtime object comes from — a URI, or a factory id for generated content. */
  readonly sourceUri?: string;
  readonly factoryId?: string;
  readonly transform: Matrix4;
  /** Alignment quality, 0..1. Distinct from `provenance.confidence`, which is about the source. */
  readonly alignmentConfidence?: number;
  readonly aligned: boolean;
  readonly visible?: boolean;
  /**
   * Where on Earth this sits.
   *
   * Distinct from `transform`, which only places it relative to the project origin. Without this a
   * scan cannot be checked against a survey, combined with GIS layers, or re-registered after the
   * project origin moves.
   */
  readonly geoReference?: GeoReference;
  readonly extent?: Extent;
  /** Products from the same capture — orthomosaic, point cloud, derived mesh, source imagery. */
  readonly derivatives?: RealityDerivatives;
  /** What this dataset may legitimately be used for. Defaults to context when unstated. */
  readonly purpose?: DatasetPurpose;
  readonly provenance: Provenance;
  readonly capturedAt?: IsoTimestamp;
  readonly createdAt: IsoTimestamp;
  /** BIM elements this twin object is understood to correspond to. */
  readonly linkedElements?: readonly ElementRef[];
  readonly metadata?: Readonly<Record<string, unknown>>;
}

/** Why a dataset may not back a measurement. */
export type UnmeasurableReason =
  /** Declared for looking at, not for taking numbers off. */
  | "visualization-only"
  /** A radiance field with no mesh derived from it — there is no surface to measure against. */
  | "no-surface";

/**
 * Whether a dataset may back a measurement or a derived authored object.
 *
 * Lives on the schema rather than in the twin service because it is a property of the record, and
 * everything that consumes twin records has to agree about it — the promotion gate, a measurement
 * tool, an engine exporter marking a layer as collidable. A second copy of this rule anywhere is a
 * place where a splat quietly becomes measurable.
 */
export function measurabilityReason(record: TwinObjectRecord): UnmeasurableReason | undefined {
  if (record.purpose === "visualization") return "visualization-only";
  if (record.kind === "gaussian-splat" && record.derivatives?.meshUri === undefined) {
    return "no-surface";
  }
  return undefined;
}

export function isMeasurable(record: TwinObjectRecord): boolean {
  return measurabilityReason(record) === undefined;
}

/** A registration attempt that moved a twin object into project coordinates. */
export interface TwinAlignmentRecord {
  readonly id: Id;
  readonly twinObjectId: Id;
  readonly method: "manual" | "three-point" | "icp" | "survey" | "gps";
  readonly transform: Matrix4;
  /** Root-mean-square residual in project units. Lower is better. */
  readonly rmsError?: number;
  readonly controlPoints?: readonly { readonly source: Vec3; readonly target: Vec3 }[];
  readonly appliedAt: IsoTimestamp;
  readonly appliedBy: Id;
}

/** A time-stamped measurement or state reading attached to a twin object. */
export interface TwinObservationRecord {
  readonly id: Id;
  readonly twinObjectId: Id;
  readonly metric: string;
  readonly value: number | string | boolean;
  readonly unit?: string;
  readonly observedAt: IsoTimestamp;
  readonly provenance?: Provenance;
  readonly quality?: "good" | "suspect" | "bad";
}

/** An ordered series used for playback and trend review. */
export interface TwinTimelineRecord {
  readonly id: Id;
  readonly twinObjectId: Id;
  readonly metric: string;
  readonly from: IsoTimestamp;
  readonly to: IsoTimestamp;
  readonly observationIds: readonly Id[];
}

/**
 * Record of a twin object being turned into authored content.
 *
 * Kept as its own record so the link back to the observation survives. Once a scan becomes a wall,
 * the question "what evidence produced this?" is exactly the one people ask six months later.
 */
export interface TwinPromotionRecord {
  readonly id: Id;
  readonly twinObjectId: Id;
  readonly target: "authoring" | "family" | "asset";
  readonly targetId: Id;
  readonly promotedAt: IsoTimestamp;
  readonly promotedBy: Id;
  readonly notes?: string;
}

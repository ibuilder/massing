import type { ElementRef, Id, IsoTimestamp, Matrix4, Provenance, Vec3 } from "./common.js";

export type TwinObjectKind =
  | "three-group"
  | "gltf"
  | "point-cloud"
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
  readonly provenance: Provenance;
  readonly capturedAt?: IsoTimestamp;
  readonly createdAt: IsoTimestamp;
  /** BIM elements this twin object is understood to correspond to. */
  readonly linkedElements?: readonly ElementRef[];
  readonly metadata?: Readonly<Record<string, unknown>>;
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

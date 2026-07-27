import type { Id, IsoTimestamp, Vec3 } from "./common.js";

/**
 * A closed sketch outline that a mass is extruded from.
 *
 * Held separately from the mass so several options can share one footprint, and so editing the
 * footprint updates every option built on it — the common case in early design.
 */
export interface ProfileRecord {
  readonly id: Id;
  readonly name?: string;
  /** Outer boundary, in project coordinates. Implicitly closed; do not repeat the first point. */
  readonly points: readonly Vec3[];
  /** Openings — courtyards, light wells, atria. */
  readonly holes?: readonly (readonly Vec3[])[];
  /** Elevation of the sketch plane. */
  readonly baseElevation?: number;
  readonly closed: boolean;
}

/**
 * A conceptual volume.
 *
 * Shape follows the platform specification exactly. `storyHeights` is authoritative over
 * `totalHeight` — a mass with per-story heights is the normal case, and a single overall height
 * cannot express a taller ground floor, which is close to universal in real buildings.
 */
export interface MassingObjectRecord {
  id: string;
  name: string;
  profileId: string;
  storyCount: number;
  storyHeights: number[];
  totalHeight: number;
  color?: string;
  opacity?: number;
  area?: number;
  grossFloorArea?: number;
  volume?: number;
  optionSetId?: string;
  familyTemplateId?: string;
  editable: boolean;
}

/** One level of a mass, derived from the mass's profile and story heights. */
export interface MassingStoryRecord {
  readonly id: Id;
  readonly massingObjectId: Id;
  /** 0-based from the base of the mass. */
  readonly index: number;
  readonly name?: string;
  readonly elevation: number;
  readonly height: number;
  /** Per-story override; falls back to the parent mass's profile when absent. */
  readonly profileId?: Id;
  readonly area?: number;
  readonly grossFloorArea?: number;
  readonly programme?: string;
  readonly excludedFromGfa?: boolean;
}

/** Named design alternative grouping several masses for side-by-side comparison. */
export interface OptionSetRecord {
  readonly id: Id;
  readonly name: string;
  readonly description?: string;
  readonly massingObjectIds: readonly Id[];
  readonly active?: boolean;
  readonly createdAt: IsoTimestamp;
}

/** Derived quantities. Recomputed from geometry, never hand-edited. */
export interface MassingMetrics {
  readonly massingObjectId: Id;
  readonly footprintArea: number;
  readonly grossFloorArea: number;
  readonly volume: number;
  readonly envelopeArea: number;
  readonly storyCount: number;
  readonly height: number;
  /** GFA divided by site area, when a site boundary is known. */
  readonly floorAreaRatio?: number;
  readonly computedAt: IsoTimestamp;
}

export interface LevelRecord {
  readonly id: Id;
  readonly name: string;
  readonly elevation: number;
  readonly isStructural?: boolean;
}

export interface GridLineRecord {
  readonly id: Id;
  readonly label: string;
  readonly start: Vec3;
  readonly end: Vec3;
}

export interface SiteBoundaryRecord {
  readonly id: Id;
  readonly name?: string;
  readonly points: readonly Vec3[];
  readonly area?: number;
  /** Planning limits that massing option studies are checked against. */
  readonly maxFloorAreaRatio?: number;
  readonly maxHeight?: number;
  readonly setbacks?: readonly { readonly edgeIndex: number; readonly distance: number }[];
}

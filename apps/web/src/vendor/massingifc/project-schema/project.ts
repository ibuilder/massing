import type { Id, IsoTimestamp, Matrix4, Provenance } from "./common.js";

export type ModelRole =
  /** Published, read-only reference from another discipline or consultant. */
  | "reference"
  /** Editable model this team authors. */
  | "working"
  /** Generated from massing, twin promotion, or another derivation. */
  | "derived";

export type ModelFormat = "ifc" | "fragments" | "gltf" | "obj" | "point-cloud" | "other";

/**
 * A model participating in the federation.
 *
 * `version` is a string rather than a number because it usually comes from somebody else's
 * issue-sheet ("C03", "2026-04-17-P2") and normalising that to an integer loses the only
 * identifier the wider project team actually recognises.
 */
export interface ModelRecord {
  readonly id: Id;
  readonly name: string;
  readonly role: ModelRole;
  readonly format: ModelFormat;
  readonly version: string;
  readonly sourceUri?: string;
  /** Location of the converted `.frag` payload, when conversion has happened. */
  readonly fragmentsUri?: string;
  readonly discipline?: string;
  /** Placement relative to the project origin, for models delivered on a different datum. */
  readonly transform?: Matrix4;
  readonly visible?: boolean;
  readonly loadByDefault?: boolean;
  readonly elementCount?: number;
  readonly importedAt?: IsoTimestamp;
  readonly provenance?: Provenance;
}

/** Georeferencing, kept separate so a project can be relocated without touching model records. */
export interface ProjectLocation {
  readonly latitude?: number;
  readonly longitude?: number;
  readonly elevation?: number;
  /** Rotation from project north to true north, in degrees clockwise. */
  readonly trueNorthAngle?: number;
  readonly epsgCode?: string;
  readonly address?: string;
}

export interface ProjectUnits {
  readonly length: "m" | "mm" | "ft" | "in";
  readonly area: string;
  readonly volume: string;
  readonly currency: string;
}

/**
 * The container everything else hangs off.
 *
 * Domain collections are referenced by id rather than embedded. A federated project accumulates
 * tens of thousands of markups, quantities and observations; embedding them would mean rewriting
 * the whole project document on every pin drop, and would make per-plugin schema versioning
 * impossible.
 */
export interface ProjectRecord {
  readonly id: Id;
  readonly name: string;
  readonly number?: string;
  readonly description?: string;
  readonly client?: string;
  readonly phase?: string;
  readonly units: ProjectUnits;
  readonly location?: ProjectLocation;
  readonly modelIds: readonly Id[];
  /** Repositories this project may resolve family content from. */
  readonly familyRepositoryIds?: readonly Id[];
  readonly createdAt: IsoTimestamp;
  readonly createdBy: Id;
  readonly updatedAt?: IsoTimestamp;
}

/**
 * A saved session: which models were loaded and what the user was looking at.
 *
 * Reopening a federated project should not mean reloading twelve models and re-hiding nine of
 * them, so load state is persisted explicitly rather than reconstructed.
 */
export interface SessionStateRecord {
  readonly id: Id;
  readonly projectId: Id;
  readonly loadedModelIds: readonly Id[];
  readonly activeViewpointId?: Id;
  readonly openPanels?: readonly string[];
  readonly savedAt: IsoTimestamp;
  readonly savedBy: Id;
}

/** Primitives shared by every record family. */

/** Opaque identifier. Stable across sessions and safe to persist and cross-reference. */
export type Id = string;

/** ISO-8601 timestamp, always UTC. Stored as a string so records stay JSON-round-trippable. */
export type IsoTimestamp = string;

export type Vec3 = readonly [x: number, y: number, z: number];

/** Row-major 4x4 transform, matching the convention used by three.js `Matrix4.toArray`. */
export type Matrix4 = readonly number[];

export interface Authored {
  readonly createdAt: IsoTimestamp;
  readonly createdBy: Id;
  readonly updatedAt?: IsoTimestamp;
  readonly updatedBy?: Id;
}

/**
 * Where a record came from.
 *
 * Carried by anything that can originate outside the authored model — twin observations, imported
 * schedules, external cost libraries. Without provenance a federated project quickly loses track of
 * which numbers are measured, which are assumed, and which are somebody else's.
 */
export interface Provenance {
  readonly source: string;
  readonly importedAt?: IsoTimestamp;
  /** 0..1 where meaningful — sensor accuracy, scan registration quality, mapping confidence. */
  readonly confidence?: number;
  readonly externalId?: string;
}

/**
 * Reference to an element inside a model.
 *
 * `globalId` is the identity — the IFC `IfcGloballyUniqueId` carried by the element itself. It
 * survives re-export, re-conversion, a different viewer, and a new session.
 *
 * `localId` is a *transient runtime handle* (a Fragments local id, an express id). It is valid only
 * for one load of one model in one session: re-converting the same IFC can renumber it. It exists
 * here purely so runtime code can avoid a lookup on hot paths.
 *
 * **Never persist or compare `localId` across sessions, and never anchor a record to it.** Markup,
 * clashes, 4D links, takeoff and field status all reference elements this way; a transient identity
 * in this type would propagate silently into every one of them and only surface as "all the pins
 * moved" after somebody re-issued a model.
 */
export interface ElementRef {
  readonly modelId: Id;
  /** IFC GlobalId. Stable, persistable identity. */
  readonly globalId: string;
  /** Session-scoped runtime handle. Cache, never store. */
  readonly localId?: number | string;
}

/** Compares element references by their stable identity, ignoring transient handles. */
export function sameElement(a: ElementRef, b: ElementRef): boolean {
  return a.modelId === b.modelId && a.globalId === b.globalId;
}

/** Stable key for maps and sets. Built from identity only, deliberately. */
export function elementKey(element: ElementRef): string {
  return `${element.modelId}/${element.globalId}`;
}

export interface UnitizedValue {
  readonly value: number;
  /** Unit symbol, e.g. `m`, `m2`, `m3`, `kg`, `each`. */
  readonly unit: string;
}

/** Money kept as minor units plus a currency code — never as a float. */
export interface Money {
  readonly amount: number;
  readonly currency: string;
}

export interface SavedViewpoint {
  readonly id: Id;
  readonly name?: string;
  readonly position: Vec3;
  readonly target: Vec3;
  readonly up?: Vec3;
  readonly projection?: "perspective" | "orthographic";
  /** Element visibility overrides captured with the view. */
  readonly hidden?: readonly ElementRef[];
  readonly isolated?: readonly ElementRef[];
  readonly sectionPlanes?: readonly { readonly normal: Vec3; readonly constant: number }[];
  readonly createdAt: IsoTimestamp;
}

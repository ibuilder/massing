import type { Id, IsoTimestamp, Matrix4, Provenance } from "./common.js";

export type FamilyRepositoryKind =
  | "git"
  | "local"
  | "cloud-api"
  | "enterprise-registry"
  | "project-local";

/**
 * A content source.
 *
 * Deliberately descriptive rather than behavioural: the record says *where* content lives and the
 * matching adapter knows *how* to fetch it. That split is what lets a new repository kind be added
 * as a plugin instead of a change to the schema.
 */
export interface FamilyRepositoryRecord {
  readonly id: Id;
  readonly name: string;
  readonly kind: FamilyRepositoryKind;
  readonly uri: string;
  readonly branch?: string;
  readonly readOnly: boolean;
  /** Whether this repository may receive newly published packages. */
  readonly publishable?: boolean;
  readonly trusted?: boolean;
  readonly lastSyncedAt?: IsoTimestamp;
}

export type FamilyParameterType = "number" | "string" | "boolean" | "length" | "area" | "enum";

export interface FamilyParameterDefinition {
  readonly name: string;
  readonly type: FamilyParameterType;
  readonly unit?: string;
  readonly defaultValue?: unknown;
  readonly options?: readonly string[];
  readonly min?: number;
  readonly max?: number;
  readonly required?: boolean;
  readonly description?: string;
}

/** A versioned unit of reusable content. */
export interface FamilyPackageRecord {
  readonly id: Id;
  readonly repositoryId: Id;
  readonly name: string;
  /** Stable identifier within its repository, e.g. `massingcloud/tower-typology`. */
  readonly slug: string;
  readonly version: string;
  readonly category?: string;
  readonly description?: string;
  readonly tags?: readonly string[];
  readonly parameters: readonly FamilyParameterDefinition[];
  readonly previewUri?: string;
  /** Content locations, resolved by the owning repository adapter. */
  readonly assets?: readonly { readonly kind: string; readonly uri: string }[];
  /** Platform API range this package is built against. */
  readonly apiVersion?: string;
  readonly license?: string;
  readonly publishedAt?: IsoTimestamp;
  readonly provenance?: Provenance;
}

/** A placed instance of a family package. */
export interface FamilyInstanceRecord {
  readonly id: Id;
  readonly packageId: Id;
  /**
   * The package's stable slug, captured at placement.
   *
   * Package *ids* are catalogue entries and do not survive a repository re-sync; the slug is the
   * identity that does. Without it, re-syncing a library orphans every instance placed from it.
   */
  readonly packageSlug?: string;
  readonly packageVersion: string;
  readonly name?: string;
  readonly transform: Matrix4;
  readonly parameters: Readonly<Record<string, unknown>>;
  /** Model the instance was placed into, when it has been realised as geometry. */
  readonly modelId?: Id;
  readonly hostElementId?: number | string;
  readonly levelId?: Id;
  readonly createdAt: IsoTimestamp;
  readonly createdBy: Id;
}

/**
 * Result of checking a package against the running platform.
 *
 * User-created content is explicitly in scope for this platform, so packages are treated as
 * untrusted input: a package must be able to fail validation and be refused rather than being
 * loaded and hoping.
 */
export interface FamilyValidationResult {
  readonly packageId: Id;
  readonly version: string;
  readonly compatible: boolean;
  readonly errors: readonly string[];
  readonly warnings: readonly string[];
  readonly checkedAt: IsoTimestamp;
}

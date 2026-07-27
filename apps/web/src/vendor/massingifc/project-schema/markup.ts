import type { Id, IsoTimestamp, Vec3 } from "./common.js";

export type MarkupKind =
  | "pin"
  | "redline"
  | "cloud"
  | "note"
  | "measurement-ref"
  | "snapshot-link";

export type MarkupStatus = "open" | "in-review" | "resolved" | "closed";

/**
 * A single piece of markup.
 *
 * Shape follows the platform specification exactly — markup is consumed by coordination, review
 * and field plugins, so its contract is one of the few that must not drift.
 */
export interface MarkupRecord {
  id: string;
  kind: MarkupKind;
  viewpointId?: string;
  modelId?: string;
  /** IFC GlobalIds. Not viewer-local ids — a markup anchored to a transient id is a lost markup. */
  elementIds?: string[];
  worldPosition?: [number, number, number];
  screenSpace?: { x: number; y: number };
  text?: string;
  status?: MarkupStatus;
  assignee?: string;
  createdAt: string;
  createdBy: string;
}

/**
 * How a markup stays attached to what it is about.
 *
 * Separated from `MarkupRecord` because anchoring is the part that degrades: a pin placed on an
 * element that a later model revision deletes must become *orphaned*, not silently relocate to the
 * origin. `resolved` records whether the anchor still binds.
 */
export interface AnchorReference {
  readonly id: Id;
  readonly markupId: Id;
  readonly modelId?: Id;
  /** IFC GlobalId of the anchored element. Never a transient viewer id — see `ElementRef`. */
  readonly globalId?: string;
  readonly worldPosition?: Vec3;
  /** Position relative to the anchored element, so the markup survives the element moving. */
  readonly localOffset?: Vec3;
  readonly resolved: boolean;
  readonly resolvedAt?: IsoTimestamp;
}

export type IssuePriority = "low" | "medium" | "high" | "critical";

export interface IssueRecord {
  readonly id: Id;
  readonly title: string;
  readonly description?: string;
  readonly status: MarkupStatus;
  readonly priority?: IssuePriority;
  readonly assignee?: Id;
  readonly reporter: Id;
  readonly dueDate?: IsoTimestamp;
  readonly markupIds: readonly Id[];
  readonly viewpointId?: Id;
  /** Discipline or package this issue is routed to, e.g. `"MEP"`, `"Structure"`. */
  readonly responsibility?: string;
  readonly labels?: readonly string[];
  readonly createdAt: IsoTimestamp;
  readonly createdBy: Id;
  readonly closedAt?: IsoTimestamp;
}

export interface CommentRecord {
  readonly id: Id;
  readonly body: string;
  readonly authorId: Id;
  readonly createdAt: IsoTimestamp;
  readonly editedAt?: IsoTimestamp;
  readonly attachments?: readonly { readonly name: string; readonly uri: string }[];
}

export interface CommentThread {
  readonly id: Id;
  /** Record this thread hangs off — an issue, a markup, a clash, a cost line. */
  readonly subjectId: Id;
  readonly subjectKind: string;
  readonly comments: readonly CommentRecord[];
  readonly resolved: boolean;
  readonly createdAt: IsoTimestamp;
}

/**
 * A frozen record of what the model looked like at review time.
 *
 * The stored `modelVersions` are what make a snapshot evidential rather than decorative: reopening
 * a six-month-old review must show the geometry the reviewer actually saw, not today's.
 */
export interface ReviewSnapshot {
  readonly id: Id;
  readonly name?: string;
  readonly viewpointId: Id;
  readonly imageUri?: string;
  readonly modelVersions: readonly { readonly modelId: Id; readonly version: string }[];
  readonly markupIds: readonly Id[];
  readonly createdAt: IsoTimestamp;
  readonly createdBy: Id;
}

export interface ReviewSession {
  readonly id: Id;
  readonly name: string;
  readonly participants: readonly Id[];
  readonly snapshotIds: readonly Id[];
  readonly issueIds: readonly Id[];
  readonly startedAt: IsoTimestamp;
  readonly endedAt?: IsoTimestamp;
}

import type { ElementRef, Id, IsoTimestamp, Vec3 } from "./common.js";

export type ClashKind = "hard" | "clearance" | "duplicate" | "workflow";

export type ClashStatus = "new" | "active" | "reviewed" | "approved" | "resolved" | "ignored";

export interface ClashRecord {
  readonly id: Id;
  readonly testId: Id;
  readonly kind: ClashKind;
  readonly status: ClashStatus;
  readonly a: ElementRef;
  readonly b: ElementRef;
  readonly point?: Vec3;
  /** Penetration depth or shortfall against the required clearance, in project units. */
  readonly distance?: number;
  readonly issueId?: Id;
  readonly assignee?: Id;
  /**
   * Stable hash of the participating elements and geometry.
   *
   * This is what makes a clash test re-runnable: without it every run produces fresh ids and the
   * triage work done last week is lost, which is the single most common way clash workflows fail
   * in practice.
   */
  readonly signature: string;
  readonly firstSeenAt: IsoTimestamp;
  readonly lastSeenAt: IsoTimestamp;
}

export interface ClashTestRecord {
  readonly id: Id;
  readonly name: string;
  readonly selectionA: readonly Id[];
  readonly selectionB: readonly Id[];
  readonly kind: ClashKind;
  /** Minimum separation for a clearance test, in project units. */
  readonly tolerance: number;
  readonly lastRunAt?: IsoTimestamp;
  readonly clashCount?: number;
}

export type ValidationSeverity = "info" | "warning" | "error";

export interface ValidationRuleRecord {
  readonly id: Id;
  readonly name: string;
  readonly description?: string;
  readonly severity: ValidationSeverity;
  /** Rule source — a standard, a company handbook, or a custom check. */
  readonly standard?: string;
  readonly enabled: boolean;
}

export interface ValidationResultRecord {
  readonly id: Id;
  readonly ruleId: Id;
  readonly severity: ValidationSeverity;
  readonly message: string;
  readonly element?: ElementRef;
  readonly issueId?: Id;
  readonly checkedAt: IsoTimestamp;
}

export type ChangeKind = "added" | "removed" | "modified" | "moved";

/** One element's difference between two model revisions. */
export interface RevisionDiffEntry {
  readonly element: ElementRef;
  readonly kind: ChangeKind;
  readonly changedProperties?: readonly string[];
  /** Quantity delta, when the change affects measured quantities — the 5D hand-off. */
  readonly quantityDelta?: Readonly<Record<string, number>>;
}

export interface RevisionDiffRecord {
  readonly id: Id;
  readonly modelId: Id;
  readonly fromVersion: string;
  readonly toVersion: string;
  readonly entries: readonly RevisionDiffEntry[];
  readonly computedAt: IsoTimestamp;
}

/** Who answers for a scope. Drives issue routing and package ownership. */
export interface ResponsibilityRecord {
  readonly id: Id;
  readonly scope: string;
  readonly discipline: string;
  readonly organisation?: string;
  readonly responsibleId?: Id;
  readonly accountableId?: Id;
  readonly consultedIds?: readonly Id[];
  readonly informedIds?: readonly Id[];
}

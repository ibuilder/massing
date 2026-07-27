import type { ElementRef, Id, IsoTimestamp, Money } from "./common.js";

export type PackageStatus =
  | "draft"
  | "issued"
  | "tendering"
  | "awarded"
  | "in-progress"
  | "complete";

/** A scope of work bought as one unit — the bridge from estimate to execution. */
export interface ProcurementPackageRecord {
  readonly id: Id;
  readonly code: string;
  readonly name: string;
  readonly status: PackageStatus;
  readonly boqLineIds: readonly Id[];
  readonly elements?: readonly ElementRef[];
  readonly taskIds?: readonly Id[];
  readonly budget?: Money;
  readonly awardedValue?: Money;
  readonly vendorId?: Id;
  readonly requiredOnSite?: IsoTimestamp;
  readonly leadTimeDays?: number;
  readonly createdAt: IsoTimestamp;
}

export interface VendorRecord {
  readonly id: Id;
  readonly name: string;
  readonly trade?: string;
  readonly contactEmail?: string;
  readonly prequalified?: boolean;
  readonly rating?: number;
}

export interface VendorScopeRecord {
  readonly id: Id;
  readonly packageId: Id;
  readonly vendorId: Id;
  readonly inclusions: readonly string[];
  readonly exclusions: readonly string[];
  readonly quotedValue?: Money;
  readonly submittedAt?: IsoTimestamp;
}

export type FieldState =
  | "not-started"
  | "in-progress"
  | "installed"
  | "inspected"
  | "accepted"
  | "rework";

/**
 * Observed state of real work on real elements.
 *
 * The point at which 5D stops being an estimate: quantities installed here are what earned value
 * and progress claims are computed from, so this record is deliberately element-level rather than
 * a percentage typed against a task.
 */
export interface FieldStatusRecord {
  readonly id: Id;
  readonly element: ElementRef;
  readonly state: FieldState;
  readonly packageId?: Id;
  readonly taskId?: Id;
  readonly quantityInstalled?: number;
  readonly unit?: string;
  readonly observedAt: IsoTimestamp;
  readonly observedBy: Id;
  readonly photoUris?: readonly string[];
  readonly notes?: string;
}

export type InspectionOutcome = "pass" | "fail" | "pass-with-comments" | "not-inspected";

export interface InspectionRecord {
  readonly id: Id;
  readonly name: string;
  readonly checklistId?: Id;
  readonly packageId?: Id;
  readonly elements?: readonly ElementRef[];
  readonly outcome: InspectionOutcome;
  readonly issueIds?: readonly Id[];
  readonly inspectedAt: IsoTimestamp;
  readonly inspectedBy: Id;
  readonly signatureUri?: string;
}

export interface InstallProgressRecord {
  readonly id: Id;
  readonly packageId: Id;
  readonly dataDate: IsoTimestamp;
  readonly quantityInstalled: number;
  readonly quantityTotal: number;
  readonly unit: string;
  readonly earnedValue?: Money;
  readonly percentComplete: number;
}

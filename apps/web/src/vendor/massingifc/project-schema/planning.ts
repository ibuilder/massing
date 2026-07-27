import type { ElementRef, Id, IsoTimestamp } from "./common.js";

export type TaskConstraint = "asap" | "start-no-earlier-than" | "finish-no-later-than" | "must-start-on";

export interface ScheduleTaskRecord {
  readonly id: Id;
  /** Id from the source programme (P6, MS Project, XER). Kept for round-tripping. */
  readonly externalId?: string;
  readonly name: string;
  readonly wbsCode?: string;
  readonly parentId?: Id;
  readonly plannedStart: IsoTimestamp;
  readonly plannedFinish: IsoTimestamp;
  readonly actualStart?: IsoTimestamp;
  readonly actualFinish?: IsoTimestamp;
  /** 0..1. Distinct from earned quantity, which lives on the 5D side. */
  readonly percentComplete?: number;
  readonly constraint?: TaskConstraint;
  readonly critical?: boolean;
  readonly totalFloat?: number;
  readonly resourceIds?: readonly Id[];
}

export type DependencyType = "FS" | "SS" | "FF" | "SF";

export interface TaskDependencyRecord {
  readonly id: Id;
  readonly predecessorId: Id;
  readonly successorId: Id;
  readonly type: DependencyType;
  /** Lag in days; negative expresses a lead. */
  readonly lag?: number;
}

export type TaskLinkBehaviour = "construct" | "demolish" | "temporary" | "existing";

/**
 * How the link maps to IFC when exported.
 *
 * `IfcRelAssignsToProduct` is the correct relationship for the products a task **produces** — the
 * task appears in `RelatedObjects` and the constructed product is the `RelatingProduct`.
 *
 * `IfcRelAssignsToProcess` is for what a task **consumes**: labour, plant, materials as resources.
 * The two are easy to transpose and the result still validates, so the intended meaning is recorded
 * explicitly rather than inferred at export time.
 */
export type TaskIfcRelationship = "IfcRelAssignsToProduct" | "IfcRelAssignsToProcess";

/**
 * Binds model elements to a schedule activity.
 *
 * Selection is stored as a *rule* as well as a resolved element list. Re-issuing a model would
 * otherwise break every link — the rule lets the link re-resolve against the new revision instead
 * of being rebuilt by hand. Resolved elements carry IFC GlobalIds, so re-resolution is a
 * correctness backstop rather than the only thing holding the link together.
 */
export interface TaskModelLinkRecord {
  readonly id: Id;
  readonly taskId: Id;
  readonly behaviour: TaskLinkBehaviour;
  readonly elements: readonly ElementRef[];
  /**
   * Defaults to `IfcRelAssignsToProduct`: a 4D link almost always names a task's *output*.
   * Resource assignment is the exception and must be stated.
   */
  readonly ifcRelationship?: TaskIfcRelationship;
  readonly selectionRule?: {
    readonly modelId: Id;
    readonly filter: Readonly<Record<string, unknown>>;
  };
  readonly resolvedAt?: IsoTimestamp;
  /** How the link was made — hand-picked, rule-matched, or imported with the programme. */
  readonly linkSource?: "manual" | "rule" | "imported";
}

export interface SimulationSettings {
  readonly id: Id;
  readonly name: string;
  readonly from: IsoTimestamp;
  readonly to: IsoTimestamp;
  readonly stepUnit: "day" | "week" | "month";
  readonly showPlanned: boolean;
  readonly showActual: boolean;
}

/** Planned-versus-actual comparison for a single activity. */
export interface ProgressComparisonRecord {
  readonly id: Id;
  readonly taskId: Id;
  readonly dataDate: IsoTimestamp;
  readonly plannedPercent: number;
  readonly actualPercent: number;
  /** Positive means ahead of programme, in days. */
  readonly scheduleVarianceDays?: number;
  readonly earnedQuantity?: number;
  readonly notes?: string;
}

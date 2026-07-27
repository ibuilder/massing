import type { ElementRef, Id, IsoTimestamp, Money, Provenance, UnitizedValue } from "./common.js";

/**
 * Where a number came from.
 *
 * Carried rather than implied. A quantity read off the model and a quantity somebody typed in are
 * both "1,240 m²" on screen, and the difference only becomes visible — expensively — when the model
 * is re-issued and one of them silently fails to move.
 */
export interface QuantitySource {
  readonly kind: "model-takeoff" | "manual" | "imported" | "assumed";
  /** Takeoff rule and its version, when the quantity was measured. */
  readonly ruleId?: Id;
  readonly ruleVersion?: number;
  /** Model revision measured against — what makes a re-run comparable. */
  readonly modelVersion?: string;
  readonly enteredBy?: Id;
  readonly note?: string;
}

/** Where a rate came from. Same reasoning as `QuantitySource`, applied to money. */
export interface RateSource {
  readonly kind: "library" | "assembly" | "quotation" | "manual" | "benchmark" | "assumed";
  readonly libraryId?: Id;
  readonly libraryVersion?: string;
  readonly assemblyId?: Id;
  readonly vendorId?: Id;
  readonly quotedAt?: IsoTimestamp;
  readonly enteredBy?: Id;
  readonly note?: string;
}

/**
 * A measured quantity taken from the model.
 *
 * `elements` is retained rather than just the total. An estimator's first question about any
 * number is "which elements is that?", and a takeoff that cannot answer it is not auditable and
 * will not be trusted.
 */
export interface QuantityRecord {
  readonly id: Id;
  readonly modelId: Id;
  /** What was measured, e.g. `NetVolume`, `GrossArea`, `Length`, `Count`. */
  readonly metric: string;
  readonly quantity: UnitizedValue;
  readonly elements: readonly ElementRef[];
  readonly classificationCode?: string;
  /** Required: a quantity whose origin is unknown cannot be defended or re-measured. */
  readonly source: QuantitySource;
  readonly takenAt: IsoTimestamp;
  readonly provenance?: Provenance;
}

/** A rule that turns model elements into quantities. Versioned, because rates depend on it. */
export interface TakeoffRuleRecord {
  readonly id: Id;
  readonly name: string;
  readonly version: number;
  /** Element filter — IFC class, property values, classification. */
  readonly filter: Readonly<Record<string, unknown>>;
  readonly metric: string;
  readonly unit: string;
  /** Expression evaluated per element, e.g. `Width * Height`. */
  readonly expression?: string;
  readonly enabled: boolean;
}

export interface ClassificationSystemRecord {
  readonly id: Id;
  /** e.g. `Uniclass 2015`, `MasterFormat`, `NRM1`, `OmniClass`. */
  readonly name: string;
  readonly version?: string;
}

/** Maps model elements or takeoff output into an estimator's coding structure. */
export interface ClassificationMappingRecord {
  readonly id: Id;
  readonly systemId: Id;
  readonly code: string;
  readonly title?: string;
  readonly filter?: Readonly<Record<string, unknown>>;
  readonly quantityIds?: readonly Id[];
  readonly confidence?: number;
}

export interface ResourceRecord {
  readonly id: Id;
  readonly name: string;
  readonly type: "labour" | "material" | "plant" | "subcontract" | "other";
  readonly unit: string;
  readonly rate: Money;
  readonly effectiveFrom?: IsoTimestamp;
  readonly supplier?: string;
}

/** A composite unit rate: what it costs to do one unit of work, broken into resources. */
export interface CostAssemblyRecord {
  readonly id: Id;
  readonly code: string;
  readonly name: string;
  readonly unit: string;
  readonly components: readonly {
    readonly resourceId: Id;
    /** Resource units consumed per one unit of the assembly. */
    readonly factor: number;
    readonly wastePercent?: number;
  }[];
  readonly overheadPercent?: number;
  readonly profitPercent?: number;
  readonly libraryId?: Id;
  readonly version?: number;
  readonly rateSource?: RateSource;
}

export interface BoqLineRecord {
  readonly id: Id;
  readonly boqId: Id;
  readonly itemNumber: string;
  readonly description: string;
  readonly classificationCode?: string;
  readonly quantity: UnitizedValue;
  readonly assemblyId?: Id;
  readonly rate?: Money;
  /** Present whenever `rate` is. A priced line with no rate origin is not reviewable. */
  readonly rateSource?: RateSource;
  readonly total?: Money;
  /** Quantities this line was measured from — the audit trail back to the model. */
  readonly quantityIds?: readonly Id[];
  /** Mirrors the quantities' origin so a line can be triaged without dereferencing each one. */
  readonly quantitySource?: QuantitySource;
  readonly parentId?: Id;
}

export interface BoqRecord {
  readonly id: Id;
  readonly name: string;
  readonly currency: string;
  readonly revision: string;
  readonly lineIds: readonly Id[];
  readonly createdAt: IsoTimestamp;
  readonly createdBy: Id;
}

export type EstimateStatus = "draft" | "issued" | "superseded" | "awarded";

export interface EstimateRecord {
  readonly id: Id;
  readonly name: string;
  /**
   * The bill this estimate reports. Once issued, this points at a **frozen copy** — regenerating
   * the working bill afterwards must not rewrite a document somebody has already acted on.
   */
  readonly boqId: Id;
  /** The live bill it was generated from. Revisions re-price against this, not the frozen copy. */
  readonly workingBoqId?: Id;
  readonly status: EstimateStatus;
  readonly currency: string;
  readonly subtotal: Money;
  readonly contingencyPercent?: number;
  readonly total: Money;
  /** Model revisions this estimate was measured against. Required for change control. */
  readonly basisModelVersions: readonly { readonly modelId: Id; readonly version: string }[];
  readonly createdAt: IsoTimestamp;
  readonly createdBy: Id;
  readonly supersedesId?: Id;
}

export interface CashflowPeriodRecord {
  readonly periodStart: IsoTimestamp;
  readonly periodEnd: IsoTimestamp;
  readonly plannedSpend: Money;
  readonly actualSpend?: Money;
  readonly cumulativePlanned?: Money;
  readonly cumulativeActual?: Money;
}

export interface CashflowForecastRecord {
  readonly id: Id;
  readonly estimateId: Id;
  /** Forecast is driven by the schedule; without it a cashflow is just a total in a bar chart. */
  readonly scheduleBasis?: Id;
  readonly currency: string;
  readonly periods: readonly CashflowPeriodRecord[];
  readonly generatedAt: IsoTimestamp;
}

/** Cost consequence of a model change, linking a revision diff to money. */
export interface ChangeImpactRecord {
  readonly id: Id;
  readonly diffId: Id;
  readonly estimateId: Id;
  readonly deltaQuantities: readonly {
    readonly metric: string;
    readonly delta: UnitizedValue;
  }[];
  readonly deltaCost: Money;
  /**
   * Changed elements no priced line could be found for.
   *
   * Newly added elements have not been measured yet, so nothing prices them. Reporting them beats
   * a delta that silently covers only the part of the change that happened to be measurable.
   */
  readonly unpricedElements?: readonly ElementRef[];
  readonly scheduleImpactDays?: number;
  readonly status: "identified" | "estimated" | "approved" | "rejected";
  readonly identifiedAt: IsoTimestamp;
}

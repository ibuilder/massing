import { MigrationRegistry } from "./versioning.js";

/**
 * Stable schema identifiers.
 *
 * These strings are written into every persisted document and are therefore permanent: renaming
 * one orphans existing data. New capability families add entries; they do not repurpose them.
 */
export const SCHEMA = {
  project: "massingifc.project",
  session: "massingifc.session",
  model: "massingifc.model",

  markup: "massingifc.markup",
  issue: "massingifc.issue",
  commentThread: "massingifc.comment-thread",
  reviewSnapshot: "massingifc.review-snapshot",
  reviewSession: "massingifc.review-session",
  viewpoint: "massingifc.viewpoint",

  massingObject: "massingifc.massing.object",
  massingProfile: "massingifc.massing.profile",
  massingStory: "massingifc.massing.story",
  massingOptionSet: "massingifc.massing.option-set",
  level: "massingifc.level",
  grid: "massingifc.grid",
  siteBoundary: "massingifc.site-boundary",

  familyRepository: "massingifc.family.repository",
  familyPackage: "massingifc.family.package",
  familyInstance: "massingifc.family.instance",

  twinObject: "massingifc.twin.object",
  twinAlignment: "massingifc.twin.alignment",
  twinObservation: "massingifc.twin.observation",
  twinPromotion: "massingifc.twin.promotion",

  clash: "massingifc.coordination.clash",
  clashTest: "massingifc.coordination.clash-test",
  validationRule: "massingifc.coordination.validation-rule",
  validationResult: "massingifc.coordination.validation-result",
  revisionDiff: "massingifc.coordination.revision-diff",
  responsibility: "massingifc.coordination.responsibility",

  scheduleTask: "massingifc.planning.task",
  taskDependency: "massingifc.planning.dependency",
  taskModelLink: "massingifc.planning.model-link",
  progressComparison: "massingifc.planning.progress",

  quantity: "massingifc.cost.quantity",
  takeoffRule: "massingifc.cost.takeoff-rule",
  classificationSystem: "massingifc.cost.classification-system",
  classificationMapping: "massingifc.cost.classification-mapping",
  resource: "massingifc.cost.resource",
  costAssembly: "massingifc.cost.assembly",
  boq: "massingifc.cost.boq",
  boqLine: "massingifc.cost.boq-line",
  estimate: "massingifc.cost.estimate",
  cashflow: "massingifc.cost.cashflow",
  changeImpact: "massingifc.cost.change-impact",

  procurementPackage: "massingifc.procurement.package",
  vendor: "massingifc.procurement.vendor",
  vendorScope: "massingifc.procurement.vendor-scope",
  fieldStatus: "massingifc.field.status",
  inspection: "massingifc.field.inspection",
  installProgress: "massingifc.field.install-progress",
} as const;

export type SchemaId = (typeof SCHEMA)[keyof typeof SCHEMA];

/**
 * Current version of every schema the platform ships.
 *
 * Everything starts at 1. The value of declaring them now — rather than when the first migration
 * is written — is that the forward-incompatibility guard works from the first release: a document
 * written by a future build is refused instead of being silently misread.
 */
export const CURRENT_VERSION: Readonly<Record<SchemaId, number>> = Object.freeze(
  Object.fromEntries(Object.values(SCHEMA).map((id) => [id, 1])) as Record<SchemaId, number>,
);

/**
 * A registry with every shipped schema declared at its current version and no migrations yet.
 *
 * Plugins add their own schemas and migration steps to the same instance during activation, which
 * is why this returns a fresh, mutable registry rather than a frozen singleton.
 */
export function createDefaultMigrationRegistry(): MigrationRegistry {
  const registry = new MigrationRegistry();
  for (const [schema, version] of Object.entries(CURRENT_VERSION)) {
    registry.declare(schema, version);
  }
  return registry;
}

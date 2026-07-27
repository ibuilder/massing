/**
 * `@massingifc/project-schema` — the platform's persisted contracts.
 *
 * Types only, plus the migration engine that moves documents between versions. No runtime
 * behaviour and no dependency on a viewer, so these records are equally usable in a browser
 * session, a desktop shell, a server-side converter, or a migration script.
 */

export * from "./common.js";
export * from "./project.js";
export * from "./markup.js";
export * from "./massing.js";
export * from "./families.js";
export * from "./twin.js";
export * from "./coordination.js";
export * from "./planning.js";
export * from "./cost.js";
export * from "./procurement.js";
export {
  MigrationRegistry,
  type MigrationDefinition,
  type MigrationPlan,
} from "./versioning.js";
export { createDefaultMigrationRegistry, CURRENT_VERSION, SCHEMA, type SchemaId } from "./schemas.js";

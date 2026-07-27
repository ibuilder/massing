import {
  attempt,
  err,
  KernelError,
  ok,
  type DocumentMigrator,
  type Result,
  type VersionedDocument,
} from "@massingifc/core-kernel";

export interface MigrationDefinition {
  /** Schema identifier this migration applies to, e.g. `"massingifc.massing.object"`. */
  readonly schema: string;
  readonly from: number;
  readonly to: number;
  /** Human-readable note. Surfaced in migration reports and logs. */
  readonly description?: string;
  /** Pure transform. Must not mutate its input — the caller may still hold the original. */
  readonly migrate: (data: unknown) => unknown;
}

export interface MigrationPlan {
  readonly schema: string;
  readonly from: number;
  readonly to: number;
  readonly steps: readonly MigrationDefinition[];
}

/**
 * The platform's upgrade path.
 *
 * Every persisted format in the platform carries a schema id and an integer version, and this
 * registry owns the rules for moving one forward. Keeping it separate from the persistence engine
 * matters: the kernel must not know what a massing object is, and plugins must be able to register
 * migrations for their own records at load time without patching the backbone.
 *
 * Implements the kernel's `DocumentMigrator`, so handing an instance to `createKernel` is all the
 * wiring required.
 */
export class MigrationRegistry implements DocumentMigrator {
  /** schema -> fromVersion -> definition */
  readonly #steps = new Map<string, Map<number, MigrationDefinition>>();
  readonly #latest = new Map<string, number>();

  /**
   * Declares the current version of a schema that has no migrations yet.
   *
   * Needed because "latest" cannot always be inferred: a brand-new v1 schema has no steps, and
   * without an explicit declaration the engine would treat it as unknown and skip version checks
   * entirely — including the forward-incompatibility guard.
   */
  declare(schema: string, version: number): this {
    const current = this.#latest.get(schema) ?? 0;
    if (version > current) this.#latest.set(schema, version);
    return this;
  }

  register(definition: MigrationDefinition): this {
    if (definition.to <= definition.from) {
      throw new KernelError(
        "MIGRATION_FAILED",
        `Migration for "${definition.schema}" must move forward (got v${definition.from} -> v${definition.to}).`,
        { schema: definition.schema, from: definition.from, to: definition.to },
      );
    }
    const bySchema = this.#steps.get(definition.schema) ?? new Map<number, MigrationDefinition>();
    if (bySchema.has(definition.from)) {
      // Two routes out of the same version make the upgrade non-deterministic — which one runs
      // would depend on registration order, and the two could disagree about the result.
      throw new KernelError(
        "MIGRATION_FAILED",
        `Duplicate migration from v${definition.from} for "${definition.schema}".`,
        { schema: definition.schema, from: definition.from },
      );
    }
    bySchema.set(definition.from, definition);
    this.#steps.set(definition.schema, bySchema);
    this.declare(definition.schema, definition.to);
    return this;
  }

  registerAll(definitions: readonly MigrationDefinition[]): this {
    for (const definition of definitions) this.register(definition);
    return this;
  }

  latestVersion(schema: string): number | undefined {
    return this.#latest.get(schema);
  }

  knownSchemas(): readonly string[] {
    return [...this.#latest.keys()].sort();
  }

  /** Resolves the chain of steps from `from` to the schema's latest version. */
  plan(schema: string, from: number): Result<MigrationPlan> {
    const target = this.#latest.get(schema);
    if (target === undefined) {
      return err(
        new KernelError("MIGRATION_PATH_MISSING", `Unknown schema "${schema}".`, { schema }),
      );
    }
    const steps: MigrationDefinition[] = [];
    let version = from;
    const bySchema = this.#steps.get(schema);

    while (version < target) {
      const step = bySchema?.get(version);
      if (!step) {
        return err(
          new KernelError(
            "MIGRATION_PATH_MISSING",
            `No migration from "${schema}" v${version} towards v${target}.`,
            { schema, from: version, target },
          ),
        );
      }
      steps.push(step);
      version = step.to;
    }
    return ok({ schema, from, to: version, steps });
  }

  migrate(document: VersionedDocument): Result<VersionedDocument> {
    const target = this.#latest.get(document.schema);
    if (target === undefined || document.version === target) return ok(document);
    if (document.version > target) {
      return err(
        new KernelError(
          "SCHEMA_VERSION_UNSUPPORTED",
          `"${document.schema}" v${document.version} is newer than the supported v${target}.`,
          { schema: document.schema, found: document.version, supported: target },
        ),
      );
    }

    const plan = this.plan(document.schema, document.version);
    if (!plan.ok) return err(plan.error);

    let data = document.data;
    let version = document.version;
    for (const step of plan.value.steps) {
      // A migration is third-party code with a long tail of edge cases (a field that was optional
      // in practice but not in the type, a null where an array was assumed). Failing this one
      // document with the step named beats an unhandled throw that loses the whole project.
      const applied = attempt(
        () => step.migrate(data),
        "MIGRATION_FAILED",
        `Migration "${document.schema}" v${step.from} -> v${step.to} failed.`,
      );
      if (!applied.ok) {
        return err(
          new KernelError(
            "MIGRATION_FAILED",
            `Migration "${document.schema}" v${step.from} -> v${step.to} failed: ${applied.error.message}`,
            { schema: document.schema, from: step.from, to: step.to },
            { cause: applied.error },
          ),
        );
      }
      data = applied.value;
      version = step.to;
    }
    return ok({ ...document, version, data });
  }

  /**
   * Whether a document can be brought to the current version.
   *
   * Cheap, side-effect-free check for a compatibility screen — a host can tell a user which files
   * in a project directory will open before opening any of them.
   */
  isCompatible(schema: string, version: number): boolean {
    const target = this.#latest.get(schema);
    if (target === undefined) return false;
    if (version > target) return false;
    if (version === target) return true;
    return this.plan(schema, version).ok;
  }
}

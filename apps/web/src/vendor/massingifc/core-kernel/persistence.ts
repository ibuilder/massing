import { KernelError } from "./errors.js";
import { attemptAsync, err, ok, type Result } from "./result.js";
import { NOOP_TELEMETRY, type TelemetrySink } from "./telemetry.js";

/**
 * Byte-agnostic key/value persistence.
 *
 * Kept this narrow so the same engine works over IndexedDB in the browser, the filesystem in a
 * desktop shell, and an object store on a server — the kernel never learns which.
 */
export interface StorageAdapter {
  get(key: string): Promise<unknown | undefined>;
  put(key: string, value: unknown): Promise<void>;
  delete(key: string): Promise<void>;
  keys(prefix?: string): Promise<string[]>;
}

/** Structured-clone if the runtime has it, JSON round-trip otherwise. */
function clone<T>(value: T): T {
  if (typeof structuredClone === "function") return structuredClone(value);
  return JSON.parse(JSON.stringify(value)) as T;
}

/**
 * In-memory adapter for tests and ephemeral sessions.
 *
 * Clones on both read and write. Handing back a live reference would let a caller mutate stored
 * state without saving — a bug that only shows up once a real adapter is swapped in, which is the
 * worst time to find it.
 */
export class MemoryStorageAdapter implements StorageAdapter {
  readonly #entries = new Map<string, unknown>();

  async get(key: string): Promise<unknown | undefined> {
    const value = this.#entries.get(key);
    return value === undefined ? undefined : clone(value);
  }

  async put(key: string, value: unknown): Promise<void> {
    this.#entries.set(key, clone(value));
  }

  async delete(key: string): Promise<void> {
    this.#entries.delete(key);
  }

  async keys(prefix = ""): Promise<string[]> {
    return [...this.#entries.keys()].filter((key) => key.startsWith(prefix)).sort();
  }

  get size(): number {
    return this.#entries.size;
  }
}

/**
 * Every persisted payload carries its schema identity and version inline.
 *
 * Storing the version *with* the data rather than alongside it is what makes migration possible
 * years later: a file recovered from a backup, an email attachment, or a different deployment is
 * still self-describing.
 */
export interface VersionedDocument<T = unknown> {
  readonly schema: string;
  readonly version: number;
  readonly savedAt: string;
  readonly data: T;
}

export function isVersionedDocument(value: unknown): value is VersionedDocument {
  if (typeof value !== "object" || value === null) return false;
  const candidate = value as Partial<VersionedDocument>;
  return (
    typeof candidate.schema === "string" &&
    typeof candidate.version === "number" &&
    Number.isInteger(candidate.version)
  );
}

/**
 * Upgrades documents to the current schema version.
 *
 * The kernel defines the interface but ships no implementation — migration rules belong with the
 * records they migrate (see `@massingifc/project-schema`), not in the backbone.
 */
export interface DocumentMigrator {
  /** Current version for a schema, or `undefined` if the schema is unknown to this migrator. */
  latestVersion(schema: string): number | undefined;
  migrate(document: VersionedDocument): Result<VersionedDocument>;
}

export interface BackupEntry {
  readonly id: string;
  readonly key: string;
  readonly createdAt: string;
}

export interface PersistenceOptions {
  readonly adapter: StorageAdapter;
  readonly migrator?: DocumentMigrator;
  readonly telemetry?: TelemetrySink;
  readonly now?: () => Date;
  /** Backups retained per key before the oldest is pruned. Defaults to 5. */
  readonly maxBackups?: number;
}

export interface SaveOptions {
  /** Snapshot the existing value before overwriting. Defaults to `false`. */
  readonly backup?: boolean;
  /** Override the version stamp. Defaults to the migrator's latest for the schema, else 1. */
  readonly version?: number;
}

const BACKUP_MARKER = "::backup::";

/**
 * Versioned document store with migration and rollback.
 *
 * Reads are pure: `load` migrates the value it returns but does not write the upgraded form back.
 * A read that silently rewrites storage is a surprising and occasionally destructive side effect —
 * opening a project to look at it should not mutate it. Callers that *want* the upgrade persisted
 * ask for it explicitly via `migrateInPlace`, which takes a backup first.
 */
export class PersistenceEngine {
  readonly #adapter: StorageAdapter;
  readonly #migrator: DocumentMigrator | undefined;
  readonly #telemetry: TelemetrySink;
  readonly #now: () => Date;
  readonly #maxBackups: number;
  #backupCounter = 0;

  constructor(options: PersistenceOptions) {
    this.#adapter = options.adapter;
    this.#migrator = options.migrator;
    this.#telemetry = options.telemetry ?? NOOP_TELEMETRY;
    this.#now = options.now ?? (() => new Date());
    this.#maxBackups = Math.max(0, options.maxBackups ?? 5);
  }

  async save<T>(
    key: string,
    schema: string,
    data: T,
    options: SaveOptions = {},
  ): Promise<Result<VersionedDocument<T>>> {
    if (options.backup) {
      const backup = await this.backup(key);
      if (!backup.ok && backup.error.code !== "STORAGE_FAILED") return err(backup.error);
    }
    const version = options.version ?? this.#migrator?.latestVersion(schema) ?? 1;
    const document: VersionedDocument<T> = {
      schema,
      version,
      savedAt: this.#now().toISOString(),
      data,
    };
    const written = await attemptAsync(
      () => this.#adapter.put(key, document),
      "STORAGE_FAILED",
      `Failed to write "${key}".`,
    );
    if (!written.ok) {
      this.#telemetry.error(written.error, { key, schema });
      return err(written.error);
    }
    this.#telemetry.counter("persistence.save", 1, { schema });
    return ok(document);
  }

  /**
   * Load and migrate. Resolves to `undefined` for a key that was never written — absence is a
   * normal outcome (a first run), not a failure.
   */
  async load<T>(key: string): Promise<Result<VersionedDocument<T> | undefined>> {
    const read = await attemptAsync(
      () => this.#adapter.get(key),
      "STORAGE_FAILED",
      `Failed to read "${key}".`,
    );
    if (!read.ok) return err(read.error);
    if (read.value === undefined || read.value === null) return ok(undefined);

    if (!isVersionedDocument(read.value)) {
      return err(
        new KernelError("MIGRATION_FAILED", `Value at "${key}" is not a versioned document.`, { key }),
      );
    }
    const migrated = this.#applyMigration(read.value, key);
    return migrated.ok ? ok(migrated.value as VersionedDocument<T>) : err(migrated.error);
  }

  /** Migrate the stored value and write it back, snapshotting the original first. */
  async migrateInPlace(key: string): Promise<Result<VersionedDocument | undefined>> {
    const current = await this.load(key);
    if (!current.ok) return err(current.error);
    if (!current.value) return ok(undefined);

    const backup = await this.backup(key);
    if (!backup.ok) return err(backup.error);

    const written = await attemptAsync(
      () => this.#adapter.put(key, current.value),
      "STORAGE_FAILED",
      `Failed to write migrated "${key}".`,
    );
    return written.ok ? ok(current.value) : err(written.error);
  }

  async delete(key: string): Promise<Result<void>> {
    const removed = await attemptAsync(
      () => this.#adapter.delete(key),
      "STORAGE_FAILED",
      `Failed to delete "${key}".`,
    );
    return removed.ok ? ok(undefined) : err(removed.error);
  }

  async keys(prefix = ""): Promise<string[]> {
    const all = await this.#adapter.keys(prefix);
    return all.filter((key) => !key.includes(BACKUP_MARKER));
  }

  async backup(key: string): Promise<Result<BackupEntry | undefined>> {
    const existing = await attemptAsync(
      () => this.#adapter.get(key),
      "STORAGE_FAILED",
      `Failed to read "${key}" for backup.`,
    );
    if (!existing.ok) return err(existing.error);
    if (existing.value === undefined) return ok(undefined); // nothing to snapshot yet

    const createdAt = this.#now().toISOString();
    // The counter disambiguates snapshots taken inside the same millisecond, which is entirely
    // possible during a batch migration and would otherwise silently overwrite the previous one.
    const id = `${createdAt}-${(this.#backupCounter++).toString(36)}`;
    const backupKey = `${key}${BACKUP_MARKER}${id}`;
    const written = await attemptAsync(
      () => this.#adapter.put(backupKey, existing.value),
      "STORAGE_FAILED",
      `Failed to write backup for "${key}".`,
    );
    if (!written.ok) return err(written.error);

    await this.#prune(key);
    this.#telemetry.counter("persistence.backup", 1);
    return ok({ id, key, createdAt });
  }

  async listBackups(key: string): Promise<BackupEntry[]> {
    const keys = await this.#adapter.keys(`${key}${BACKUP_MARKER}`);
    return keys
      .map((backupKey) => {
        const id = backupKey.slice(key.length + BACKUP_MARKER.length);
        return { id, key, createdAt: id.slice(0, id.lastIndexOf("-")) };
      })
      .sort((a, b) => a.id.localeCompare(b.id));
  }

  async rollback(key: string, backupId: string): Promise<Result<VersionedDocument | undefined>> {
    const backupKey = `${key}${BACKUP_MARKER}${backupId}`;
    const snapshot = await attemptAsync(
      () => this.#adapter.get(backupKey),
      "STORAGE_FAILED",
      `Failed to read backup "${backupId}".`,
    );
    if (!snapshot.ok) return err(snapshot.error);
    if (snapshot.value === undefined) {
      return err(
        new KernelError("STORAGE_FAILED", `No backup "${backupId}" for "${key}".`, { key, backupId }),
      );
    }
    // Snapshot what we are about to replace, so a rollback is itself reversible.
    const safety = await this.backup(key);
    if (!safety.ok) return err(safety.error);

    const written = await attemptAsync(
      () => this.#adapter.put(key, snapshot.value),
      "STORAGE_FAILED",
      `Failed to restore "${key}".`,
    );
    if (!written.ok) return err(written.error);
    this.#telemetry.counter("persistence.rollback", 1);
    return ok(isVersionedDocument(snapshot.value) ? snapshot.value : undefined);
  }

  /** A view whose keys are transparently prefixed. Used to sandbox each plugin's stored data. */
  namespaced(prefix: string): NamespacedPersistence {
    return new NamespacedPersistence(this, prefix);
  }

  #applyMigration(document: VersionedDocument, key: string): Result<VersionedDocument> {
    if (!this.#migrator) return ok(document);
    const latest = this.#migrator.latestVersion(document.schema);
    if (latest === undefined) return ok(document); // schema owned by nobody currently loaded
    if (document.version === latest) return ok(document);

    if (document.version > latest) {
      // Written by a newer release. Guessing at a downgrade risks destroying fields this build does
      // not know about, so refuse and let the host tell the user to upgrade.
      return err(
        new KernelError(
          "SCHEMA_VERSION_UNSUPPORTED",
          `"${key}" is at schema ${document.schema} v${document.version}, newer than the supported v${latest}.`,
          { key, schema: document.schema, found: document.version, supported: latest },
        ),
      );
    }

    const migrated = this.#migrator.migrate(document);
    if (!migrated.ok) {
      this.#telemetry.error(migrated.error, { key });
      return migrated;
    }
    this.#telemetry.counter("persistence.migrate", 1, {
      schema: document.schema,
      from: document.version,
      to: migrated.value.version,
    });
    return migrated;
  }

  async #prune(key: string): Promise<void> {
    if (this.#maxBackups === 0) return;
    const backups = await this.listBackups(key);
    const excess = backups.length - this.#maxBackups;
    for (let i = 0; i < excess; i++) {
      const entry = backups[i];
      if (!entry) continue;
      try {
        await this.#adapter.delete(`${key}${BACKUP_MARKER}${entry.id}`);
      } catch {
        // Pruning is housekeeping — failing to drop an old snapshot must not fail the save.
      }
    }
  }
}

/** Key-prefixed facade over a `PersistenceEngine`. */
export class NamespacedPersistence {
  readonly #engine: PersistenceEngine;
  readonly #prefix: string;

  constructor(engine: PersistenceEngine, prefix: string) {
    this.#engine = engine;
    this.#prefix = prefix.endsWith(":") ? prefix : `${prefix}:`;
  }

  #scoped(key: string): string {
    return `${this.#prefix}${key}`;
  }

  save<T>(key: string, schema: string, data: T, options?: SaveOptions) {
    return this.#engine.save<T>(this.#scoped(key), schema, data, options);
  }

  load<T>(key: string) {
    return this.#engine.load<T>(this.#scoped(key));
  }

  delete(key: string) {
    return this.#engine.delete(this.#scoped(key));
  }

  backup(key: string) {
    return this.#engine.backup(this.#scoped(key));
  }

  listBackups(key: string) {
    return this.#engine.listBackups(this.#scoped(key));
  }

  rollback(key: string, backupId: string) {
    return this.#engine.rollback(this.#scoped(key), backupId);
  }

  async keys(): Promise<string[]> {
    const keys = await this.#engine.keys(this.#prefix);
    return keys.map((key) => key.slice(this.#prefix.length));
  }
}

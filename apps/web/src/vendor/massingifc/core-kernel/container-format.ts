import { toDisposable, type Disposable } from "./disposable.js";
import { KernelError } from "./errors.js";
import type { EventBus } from "./events.js";
import {
  isVersionedDocument,
  type DocumentMigrator,
  type StorageAdapter,
  type VersionedDocument,
} from "./persistence.js";
import { attemptAsync, err, ok, type Result } from "./result.js";
import { NOOP_TELEMETRY, type TelemetrySink } from "./telemetry.js";

/**
 * Containers: a project as a single addressable package.
 *
 * `PersistenceEngine` stores individual versioned documents against a key/value adapter. That is
 * the right mechanism for settings and per-plugin state, and the wrong one for a *project* — which
 * is one thing a user opens, saves and sends, holding models, records and binary payloads together.
 *
 * Without this, "open a project package" has to be invented later by whichever plugin needs it
 * first, and every other plugin then reaches around it. A container is a mechanism, not a business
 * capability, so it belongs in the kernel by the same rule that keeps massing and markup out of it.
 *
 * The unity property matters as much as the packaging: a container opens as a whole. Models and the
 * records that reference them cannot be opened separately, because there is no API that opens one
 * without the other. Formats plug in as adapters — a native project package, ISO 21597, whatever
 * comes next — and the kernel never learns what any of them contain.
 */

export type ContainerEntryKind = "document" | "blob";

export interface ContainerEntry {
  /** Path within the container, `/`-separated, no leading slash. */
  readonly path: string;
  readonly kind: ContainerEntryKind;
  /** Schema id, for documents. Enables migration without opening every entry. */
  readonly schema?: string;
  readonly version?: number;
  readonly mediaType?: string;
  readonly byteLength?: number;
  readonly modifiedAt?: string;
}

export interface ContainerManifest {
  readonly containerId: string;
  /** Identifies the adapter that owns this format, e.g. `"massingifc.project"`. */
  readonly formatId: string;
  readonly formatVersion: number;
  readonly name: string;
  readonly createdAt: string;
  readonly modifiedAt?: string;
  /** Application and version that last wrote it. Invaluable when a file will not open. */
  readonly producer?: string;
  readonly entries: readonly ContainerEntry[];
}

/**
 * A container that is currently open.
 *
 * Documents and blobs are deliberately separate operations. A model payload is megabytes of opaque
 * bytes and a markup record is a small JSON object; treating them alike would force one of them
 * through the wrong path — parsing blobs, or base64-ing geometry into a document.
 */
export interface OpenContainer extends Disposable {
  readonly manifest: ContainerManifest;
  /** True when there are unsaved changes. */
  readonly dirty: boolean;

  entries(kind?: ContainerEntryKind): readonly ContainerEntry[];
  has(path: string): boolean;

  readDocument<T = unknown>(path: string): Promise<Result<VersionedDocument<T> | undefined>>;
  writeDocument<T>(path: string, schema: string, data: T): Promise<Result<VersionedDocument<T>>>;

  readBlob(path: string): Promise<Result<Uint8Array | undefined>>;
  writeBlob(path: string, bytes: Uint8Array, mediaType?: string): Promise<Result<void>>;

  remove(path: string): Promise<Result<void>>;
}

/** Where a container is being opened from. Adapters interpret whichever fields they support. */
export interface ContainerSource {
  readonly uri?: string;
  readonly name?: string;
  readonly bytes?: Uint8Array;
  /** Key/value store, for adapters backed by one rather than by a file. */
  readonly storage?: StorageAdapter;
}

export interface ContainerCreateInit {
  readonly containerId: string;
  readonly name: string;
  readonly producer?: string;
  readonly storage?: StorageAdapter;
}

export interface ContainerAdapterOptions {
  /**
   * Applied by the adapter when reading documents.
   *
   * Passed in rather than assumed: a container may be years old, and migration is the difference
   * between opening it and refusing it.
   */
  readonly migrator?: DocumentMigrator;
  readonly now?: () => Date;
}

export interface ContainerAdapter {
  readonly formatId: string;
  readonly displayName: string;
  /** File extensions this adapter claims, without the dot. */
  readonly extensions: readonly string[];
  canOpen(source: ContainerSource): boolean;
  open(source: ContainerSource, options?: ContainerAdapterOptions): Promise<Result<OpenContainer>>;
  create(init: ContainerCreateInit, options?: ContainerAdapterOptions): Promise<Result<OpenContainer>>;
  /** Persists the container. `target` overrides where it goes; omit to save in place. */
  save(container: OpenContainer, target?: ContainerSource): Promise<Result<ContainerManifest>>;
}

export interface ContainerServiceOptions {
  readonly events?: EventBus;
  readonly telemetry?: TelemetrySink;
  readonly migrator?: DocumentMigrator;
  readonly now?: () => Date;
}

/**
 * Opens, holds and saves the active container.
 *
 * Exactly one container is active at a time. That is the enforcement point for project/model
 * unity: there is no path that opens a model on its own, so the class of bug where a project and
 * its model drift apart because app code opened them separately cannot be written.
 *
 * Note this does *not* legislate how many models a container holds. That is a product decision —
 * a single-model authoring tool and a federated coordination project are both legitimate — and
 * baking either into the kernel would be exactly the feature-in-the-backbone mistake the
 * architecture exists to prevent.
 */
export class ContainerService {
  readonly #adapters = new Map<string, ContainerAdapter>();
  readonly #events: EventBus | undefined;
  readonly #telemetry: TelemetrySink;
  readonly #migrator: DocumentMigrator | undefined;
  readonly #now: () => Date;
  #active: OpenContainer | undefined;
  #activeAdapter: ContainerAdapter | undefined;

  constructor(options: ContainerServiceOptions = {}) {
    this.#events = options.events;
    this.#telemetry = options.telemetry ?? NOOP_TELEMETRY;
    this.#migrator = options.migrator;
    this.#now = options.now ?? (() => new Date());
  }

  registerAdapter(adapter: ContainerAdapter): Disposable {
    if (this.#adapters.has(adapter.formatId)) {
      throw new KernelError(
        "SERVICE_DUPLICATE",
        `A container adapter for "${adapter.formatId}" is already registered.`,
        { formatId: adapter.formatId },
      );
    }
    this.#adapters.set(adapter.formatId, adapter);
    return toDisposable(() => void this.#adapters.delete(adapter.formatId));
  }

  adapters(): readonly ContainerAdapter[] {
    return [...this.#adapters.values()];
  }

  get active(): OpenContainer | undefined {
    return this.#active;
  }

  #options(): ContainerAdapterOptions {
    return {
      ...(this.#migrator ? { migrator: this.#migrator } : {}),
      now: this.#now,
    };
  }

  async create(formatId: string, init: ContainerCreateInit): Promise<Result<OpenContainer>> {
    const adapter = this.#adapters.get(formatId);
    if (!adapter) return err(this.#unknownFormat(formatId));

    const closed = await this.close();
    if (!closed.ok) return err(closed.error);

    const created = await attemptAsync(
      () => adapter.create(init, this.#options()),
      "STORAGE_FAILED",
      `Adapter "${formatId}" failed to create a container.`,
    );
    if (!created.ok) return err(created.error);
    if (!created.value.ok) return created.value;

    this.#adopt(created.value.value, adapter, "created");
    return created.value;
  }

  /** Opens a container, selecting an adapter by `formatId` or by asking each one. */
  async open(source: ContainerSource, formatId?: string): Promise<Result<OpenContainer>> {
    const adapter = formatId
      ? this.#adapters.get(formatId)
      : this.adapters().find((candidate) => {
          try {
            return candidate.canOpen(source);
          } catch {
            // A adapter that throws while sniffing is simply not a match.
            return false;
          }
        });

    if (!adapter) {
      return err(
        formatId
          ? this.#unknownFormat(formatId)
          : new KernelError("STORAGE_FAILED", "No container adapter recognised this source.", {
              uri: source.uri,
            }),
      );
    }

    const closed = await this.close();
    if (!closed.ok) return err(closed.error);

    const opened = await attemptAsync(
      () => adapter.open(source, this.#options()),
      "STORAGE_FAILED",
      `Adapter "${adapter.formatId}" failed to open the container.`,
    );
    if (!opened.ok) return err(opened.error);
    if (!opened.value.ok) return opened.value;

    this.#adopt(opened.value.value, adapter, "opened");
    return opened.value;
  }

  async save(target?: ContainerSource): Promise<Result<ContainerManifest>> {
    if (!this.#active || !this.#activeAdapter) return err(this.#noActive());

    const saved = await attemptAsync(
      () => this.#activeAdapter!.save(this.#active!, target),
      "STORAGE_FAILED",
      "Failed to save the container.",
    );
    if (!saved.ok) return err(saved.error);
    if (!saved.value.ok) return saved.value;

    this.#telemetry.counter("container.saved", 1, { formatId: this.#activeAdapter.formatId });
    this.#events?.emit("container.saved", { manifest: saved.value.value });
    return saved.value;
  }

  /**
   * Closes the active container.
   *
   * Refuses when there are unsaved changes unless `force` is set. Silently discarding a user's work
   * to satisfy an "open" call is not a trade the kernel gets to make on their behalf.
   */
  async close(options: { readonly force?: boolean } = {}): Promise<Result<void>> {
    const container = this.#active;
    if (!container) return ok(undefined);

    if (container.dirty && !options.force) {
      return err(
        new KernelError("STORAGE_FAILED", "The container has unsaved changes.", {
          containerId: container.manifest.containerId,
        }),
      );
    }

    const manifest = container.manifest;
    this.#active = undefined;
    this.#activeAdapter = undefined;
    try {
      container.dispose();
    } catch {
      // Teardown failure must not leave the service holding a half-closed container.
    }
    this.#events?.emit("container.closed", { manifest });
    return ok(undefined);
  }

  #adopt(container: OpenContainer, adapter: ContainerAdapter, reason: "opened" | "created"): void {
    this.#active = container;
    this.#activeAdapter = adapter;
    this.#telemetry.counter(`container.${reason}`, 1, { formatId: adapter.formatId });
    // One event carrying the whole manifest: consumers learn about the project and everything in
    // it at the same instant, which is what makes partial-open states unrepresentable.
    this.#events?.emit(`container.${reason}`, { manifest: container.manifest });
  }

  #unknownFormat(formatId: string): KernelError {
    return new KernelError("SERVICE_NOT_FOUND", `No container adapter for "${formatId}".`, {
      formatId,
      available: [...this.#adapters.keys()],
    });
  }

  #noActive(): KernelError {
    return new KernelError("STORAGE_FAILED", "No container is open.", {});
  }
}

// ---------------------------------------------------------------------------------------------
// Built-in adapter
// ---------------------------------------------------------------------------------------------

const NATIVE_FORMAT_ID = "massingifc.project";
const NATIVE_FORMAT_VERSION = 1;

interface Entry {
  meta: ContainerEntry;
  document?: VersionedDocument;
  blob?: Uint8Array;
}

class InMemoryContainer implements OpenContainer {
  #manifest: ContainerManifest;
  readonly #entries = new Map<string, Entry>();
  readonly #migrator: DocumentMigrator | undefined;
  readonly #now: () => Date;
  #dirty = false;
  #disposed = false;

  constructor(manifest: ContainerManifest, options: ContainerAdapterOptions = {}) {
    this.#manifest = manifest;
    this.#migrator = options.migrator;
    this.#now = options.now ?? (() => new Date());
    for (const entry of manifest.entries) this.#entries.set(entry.path, { meta: entry });
  }

  get manifest(): ContainerManifest {
    return { ...this.#manifest, entries: [...this.#entries.values()].map((entry) => entry.meta) };
  }

  get dirty(): boolean {
    return this.#dirty;
  }

  entries(kind?: ContainerEntryKind): readonly ContainerEntry[] {
    const all = [...this.#entries.values()].map((entry) => entry.meta);
    return kind ? all.filter((entry) => entry.kind === kind) : all;
  }

  has(path: string): boolean {
    return this.#entries.has(path);
  }

  async readDocument<T>(path: string): Promise<Result<VersionedDocument<T> | undefined>> {
    this.#assertLive();
    const entry = this.#entries.get(path);
    if (!entry?.document) return ok(undefined);
    if (!this.#migrator) return ok(entry.document as VersionedDocument<T>);

    const latest = this.#migrator.latestVersion(entry.document.schema);
    if (latest === undefined || latest === entry.document.version) {
      return ok(entry.document as VersionedDocument<T>);
    }
    if (entry.document.version > latest) {
      return err(
        new KernelError(
          "SCHEMA_VERSION_UNSUPPORTED",
          `"${path}" is at ${entry.document.schema} v${entry.document.version}, newer than the supported v${latest}.`,
          { path, found: entry.document.version, supported: latest },
        ),
      );
    }
    const migrated = this.#migrator.migrate(entry.document);
    return migrated.ok ? ok(migrated.value as VersionedDocument<T>) : err(migrated.error);
  }

  async writeDocument<T>(path: string, schema: string, data: T): Promise<Result<VersionedDocument<T>>> {
    this.#assertLive();
    const version = this.#migrator?.latestVersion(schema) ?? 1;
    const document: VersionedDocument<T> = {
      schema,
      version,
      savedAt: this.#now().toISOString(),
      data,
    };
    this.#entries.set(path, {
      document: document as VersionedDocument,
      meta: {
        path,
        kind: "document",
        schema,
        version,
        modifiedAt: document.savedAt,
      },
    });
    this.#dirty = true;
    return ok(document);
  }

  async readBlob(path: string): Promise<Result<Uint8Array | undefined>> {
    this.#assertLive();
    return ok(this.#entries.get(path)?.blob);
  }

  async writeBlob(path: string, bytes: Uint8Array, mediaType?: string): Promise<Result<void>> {
    this.#assertLive();
    this.#entries.set(path, {
      blob: bytes,
      meta: {
        path,
        kind: "blob",
        byteLength: bytes.byteLength,
        modifiedAt: this.#now().toISOString(),
        ...(mediaType === undefined ? {} : { mediaType }),
      },
    });
    this.#dirty = true;
    return ok(undefined);
  }

  async remove(path: string): Promise<Result<void>> {
    this.#assertLive();
    if (this.#entries.delete(path)) this.#dirty = true;
    return ok(undefined);
  }

  /** Called by the adapter after a successful save. */
  markSaved(modifiedAt: string): ContainerManifest {
    this.#manifest = { ...this.#manifest, modifiedAt };
    this.#dirty = false;
    return this.manifest;
  }

  snapshot(): readonly Entry[] {
    return [...this.#entries.values()];
  }

  dispose(): void {
    this.#disposed = true;
    this.#entries.clear();
  }

  #assertLive(): void {
    if (this.#disposed) throw new KernelError("CONTAINER_DISPOSED", "The container is closed.", {});
  }
}

const MANIFEST_KEY = (containerId: string): string => `container:${containerId}:manifest`;
const ENTRY_KEY = (containerId: string, path: string): string => `container:${containerId}:entry:${path}`;

/**
 * Reference container adapter backed by a `StorageAdapter`.
 *
 * Real enough to build and test against — it round-trips documents and blobs through whatever
 * key/value store the host supplies, including the in-memory one. A file-backed `.mass` adapter and
 * the ISO 21597 adapter implement the same interface; nothing above `ContainerAdapter` changes when
 * they arrive.
 */
export class StorageContainerAdapter implements ContainerAdapter {
  readonly formatId = NATIVE_FORMAT_ID;
  readonly displayName = "MassingIFC project";
  // `.mass` is the current project-file extension; `.mmproj` is its predecessor and stays readable
  // so containers written before the rename still open. Order matters — the first entry is what a
  // host offers when saving.
  readonly extensions = ["mass", "mmproj"] as const;

  readonly #storage: StorageAdapter | undefined;

  constructor(storage?: StorageAdapter) {
    this.#storage = storage;
  }

  canOpen(source: ContainerSource): boolean {
    if (source.storage ?? this.#storage) {
      return source.uri === undefined
        || this.extensions.some((ext) => source.uri!.endsWith(`.${ext}`));
    }
    return false;
  }

  #resolve(source: ContainerSource | ContainerCreateInit): StorageAdapter | undefined {
    return ("storage" in source ? source.storage : undefined) ?? this.#storage;
  }

  async create(
    init: ContainerCreateInit,
    options: ContainerAdapterOptions = {},
  ): Promise<Result<OpenContainer>> {
    const now = options.now ?? (() => new Date());
    const manifest: ContainerManifest = {
      containerId: init.containerId,
      formatId: this.formatId,
      formatVersion: NATIVE_FORMAT_VERSION,
      name: init.name,
      createdAt: now().toISOString(),
      entries: [],
      ...(init.producer === undefined ? {} : { producer: init.producer }),
    };
    return ok(new InMemoryContainer(manifest, options));
  }

  async open(
    source: ContainerSource,
    options: ContainerAdapterOptions = {},
  ): Promise<Result<OpenContainer>> {
    const storage = this.#resolve(source);
    if (!storage) return err(new KernelError("STORAGE_FAILED", "No storage adapter supplied.", {}));

    const containerId = source.name ?? source.uri;
    if (!containerId) {
      return err(new KernelError("STORAGE_FAILED", "Container source names no container.", {}));
    }

    const raw = await storage.get(MANIFEST_KEY(containerId));
    if (raw === undefined) {
      return err(
        new KernelError("STORAGE_FAILED", `No container stored as "${containerId}".`, { containerId }),
      );
    }
    const manifest = raw as ContainerManifest;
    if (manifest.formatVersion > NATIVE_FORMAT_VERSION) {
      return err(
        new KernelError(
          "SCHEMA_VERSION_UNSUPPORTED",
          `Container format v${manifest.formatVersion} is newer than the supported v${NATIVE_FORMAT_VERSION}.`,
          { containerId, found: manifest.formatVersion },
        ),
      );
    }

    const container = new InMemoryContainer(manifest, options);
    for (const entry of manifest.entries) {
      const value = await storage.get(ENTRY_KEY(containerId, entry.path));
      if (value === undefined) continue;
      if (entry.kind === "document" && isVersionedDocument(value)) {
        await container.writeDocument(entry.path, value.schema, value.data);
      } else if (entry.kind === "blob") {
        await container.writeBlob(
          entry.path,
          value as Uint8Array,
          ...(entry.mediaType === undefined ? [] : [entry.mediaType]),
        );
      }
    }
    // Loading is not editing: a freshly-opened container must not look unsaved.
    container.markSaved(manifest.modifiedAt ?? manifest.createdAt);
    return ok(container);
  }

  async save(container: OpenContainer, target?: ContainerSource): Promise<Result<ContainerManifest>> {
    const storage = this.#resolve(target ?? {});
    if (!storage) return err(new KernelError("STORAGE_FAILED", "No storage adapter supplied.", {}));
    if (!(container instanceof InMemoryContainer)) {
      return err(
        new KernelError("STORAGE_FAILED", "Container was not produced by this adapter.", {}),
      );
    }

    const containerId = target?.name ?? container.manifest.containerId;
    const savedAt = new Date().toISOString();

    for (const entry of container.snapshot()) {
      const value = entry.meta.kind === "document" ? entry.document : entry.blob;
      if (value === undefined) continue;
      await storage.put(ENTRY_KEY(containerId, entry.meta.path), value);
    }
    const manifest = container.markSaved(savedAt);
    await storage.put(MANIFEST_KEY(containerId), { ...manifest, containerId });
    return ok(manifest);
  }
}

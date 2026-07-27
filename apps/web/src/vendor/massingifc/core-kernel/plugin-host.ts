import type {
  CapabilityProvider,
  CapabilityRegistry,
  CapabilityToken,
  ProvideOptions,
  RequireOptions,
} from "./capabilities.js";
import type { CommandBus, CommandDefinition, CommandInfo, ExecuteOptions } from "./commands.js";
import { ServiceContainer } from "./container.js";
import { DisposableStore, type Disposable } from "./disposable.js";
import { KernelError } from "./errors.js";
import type { EmitReport, EventBus, EventHandler, EventMap } from "./events.js";
import { createLogger, type Logger } from "./logging.js";
import type { PermissionService } from "./permissions.js";
import type { NamespacedPersistence, PersistenceEngine } from "./persistence.js";
import { attemptAsync, err, ok, type Result } from "./result.js";
import { satisfies } from "./semver.js";
import type { Slice, StateStore } from "./state.js";
import type { TelemetrySink } from "./telemetry.js";
import type { UIContribution, UIExtensionRegistry } from "./ui-registry.js";

export interface PluginDependency {
  readonly id: string;
  /** Semver range the dependency must satisfy. Defaults to any version. */
  readonly version?: string;
  /** Missing optional dependencies are skipped rather than failing activation. */
  readonly optional?: boolean;
}

export interface PluginManifest {
  readonly id: string;
  readonly name?: string;
  readonly version: string;
  /**
   * Kernel API range this plugin was built against, e.g. `"^1.0.0"`.
   *
   * Checked before activation so an out-of-date plugin is refused with a clear message instead of
   * failing later at an arbitrary call site with a `TypeError`.
   */
  readonly apiVersion: string;
  readonly description?: string;
  readonly dependencies?: readonly PluginDependency[];
  /** Permission actions the plugin intends to use. Advisory — surfaced for review and governance. */
  readonly permissions?: readonly string[];
}

export interface PluginCommands {
  register<P, R>(definition: CommandDefinition<P, R>): Disposable;
  execute<R = unknown, P = unknown>(
    commandId: string,
    params: P,
    options?: ExecuteOptions,
  ): Promise<Result<R>>;
  has(commandId: string): boolean;
  /**
   * Every registered command.
   *
   * Read-only enumeration, for plugins whose job *is* the command surface — a palette, a keyboard
   * binding editor, a diagnostics view. Without it such a plugin has to reach past the context to
   * the kernel bus, which is exactly the coupling the context exists to prevent.
   */
  list(): readonly CommandInfo[];
}

export interface PluginEvents<TEvents extends EventMap = EventMap> {
  on<K extends keyof TEvents & string>(type: K, handler: EventHandler<TEvents[K]>): Disposable;
  once<K extends keyof TEvents & string>(type: K, handler: EventHandler<TEvents[K]>): Disposable;
  emit<K extends keyof TEvents & string>(type: K, payload: TEvents[K]): EmitReport;
}

export interface PluginState {
  /** Defines a slice under this plugin's namespace. Released automatically on deactivate. */
  defineSlice<T>(name: string, initial: T): Slice<T>;
  /** Reads another namespace, for cross-plugin composition. Fully qualified name required. */
  getSlice<T>(namespace: string): Slice<T> | undefined;
}

export interface PluginCapabilities {
  provide<T>(token: CapabilityToken<T>, value: T, options?: ProvideOptions): Disposable;
  get<T>(token: CapabilityToken<T>, options?: RequireOptions): T | undefined;
  require<T>(token: CapabilityToken<T>, options?: RequireOptions): Result<T>;
  /**
   * Every provider of a capability, highest priority first.
   *
   * Some capabilities are inherently many-to-one — validation rules, import adapters, metric
   * providers — where the consumer aggregates rather than chooses. Without this, such a plugin has
   * to reach past the context to the kernel registry, defeating the tracked-registration contract.
   */
  getAll<T>(token: CapabilityToken<T>): readonly CapabilityProvider<T>[];
  has(token: CapabilityToken<unknown>): boolean;
}

export interface PluginUI<THost = unknown> {
  register(contribution: Omit<UIContribution<THost>, "pluginId">): Disposable;
}

/**
 * Everything a plugin is allowed to touch.
 *
 * The context is the *entire* API surface — a plugin never imports the kernel's singletons
 * directly. That is what makes deactivation reliable: every registration made through this object
 * is tracked in `subscriptions` and released together, so a plugin cannot leave a command, panel
 * or listener behind after it unloads.
 */
export interface PluginContext<THost = unknown, TEvents extends EventMap = EventMap> {
  readonly pluginId: string;
  readonly manifest: PluginManifest;
  readonly services: ServiceContainer;
  readonly commands: PluginCommands;
  readonly events: PluginEvents<TEvents>;
  readonly state: PluginState;
  readonly capabilities: PluginCapabilities;
  readonly ui: PluginUI<THost>;
  readonly storage: NamespacedPersistence;
  readonly permissions: PermissionService;
  readonly telemetry: TelemetrySink;
  readonly logger: Logger;
  /** Add teardown for anything the plugin creates outside the tracked registries. */
  readonly subscriptions: DisposableStore;
}

export interface Plugin<THost = unknown, TEvents extends EventMap = EventMap> {
  readonly manifest: PluginManifest;
  activate(context: PluginContext<THost, TEvents>): void | Promise<void>;
  deactivate?(): void | Promise<void>;
}

export type PluginStatus =
  | "registered"
  | "active"
  | "inactive"
  | "failed"
  /** Failed and will not be retried automatically until `reset` is called. */
  | "quarantined";

export interface PluginRecord {
  readonly manifest: PluginManifest;
  readonly status: PluginStatus;
  readonly error: KernelError | undefined;
  readonly activatedAt: string | undefined;
}

export interface ActivationReport {
  readonly activated: readonly string[];
  readonly failed: readonly { id: string; error: KernelError }[];
  /** Not attempted because a required dependency failed or was missing. */
  readonly skipped: readonly { id: string; reason: string }[];
}

export interface PluginHostDependencies<THost = unknown> {
  readonly container: ServiceContainer;
  readonly commands: CommandBus;
  readonly events: EventBus;
  readonly state: StateStore;
  readonly capabilities: CapabilityRegistry;
  readonly ui: UIExtensionRegistry<THost>;
  readonly persistence: PersistenceEngine;
  readonly permissions: PermissionService;
  readonly telemetry: TelemetrySink;
  /** Version the kernel reports to plugins, matched against each manifest's `apiVersion`. */
  readonly apiVersion: string;
  readonly now?: () => Date;
}

interface PluginEntry {
  readonly plugin: Plugin<never, never>;
  status: PluginStatus;
  error: KernelError | undefined;
  activatedAt: string | undefined;
  store: DisposableStore | undefined;
  scope: ServiceContainer | undefined;
}

/**
 * Registers, orders, activates and isolates plugins.
 *
 * The hard requirement is that no plugin can take down the kernel. Three things enforce it:
 * activation runs inside `attemptAsync` so a throw or rejection becomes a `Result`; every
 * registration the plugin made is rolled back when it fails, so a half-activated plugin leaves no
 * live commands or panels; and the failure is recorded as `quarantined` so an automatic retry
 * cannot turn one broken plugin into an activation loop.
 */
export class PluginHost<THost = unknown> {
  readonly #deps: PluginHostDependencies<THost>;
  readonly #entries = new Map<string, PluginEntry>();
  readonly #now: () => Date;

  constructor(dependencies: PluginHostDependencies<THost>) {
    this.#deps = dependencies;
    this.#now = dependencies.now ?? (() => new Date());
  }

  register(plugin: Plugin<THost>): Result<void> {
    const { id, apiVersion } = plugin.manifest;
    if (this.#entries.has(id)) {
      return err(
        new KernelError("PLUGIN_DUPLICATE", `Plugin "${id}" is already registered.`, { pluginId: id }),
      );
    }
    if (!satisfies(this.#deps.apiVersion, apiVersion)) {
      return err(
        new KernelError(
          "PLUGIN_API_INCOMPATIBLE",
          `Plugin "${id}" requires kernel API "${apiVersion}"; this kernel is ${this.#deps.apiVersion}.`,
          { pluginId: id, required: apiVersion, actual: this.#deps.apiVersion },
        ),
      );
    }
    this.#entries.set(id, {
      plugin: plugin as unknown as Plugin<never, never>,
      status: "registered",
      error: undefined,
      activatedAt: undefined,
      store: undefined,
      scope: undefined,
    });
    return ok(undefined);
  }

  list(): readonly PluginRecord[] {
    return [...this.#entries.values()].map((entry) => ({
      manifest: entry.plugin.manifest,
      status: entry.status,
      error: entry.error,
      activatedAt: entry.activatedAt,
    }));
  }

  status(pluginId: string): PluginStatus | undefined {
    return this.#entries.get(pluginId)?.status;
  }

  isActive(pluginId: string): boolean {
    return this.#entries.get(pluginId)?.status === "active";
  }

  /** Clears a quarantine so the plugin becomes eligible for activation again. */
  reset(pluginId: string): Result<void> {
    const entry = this.#entries.get(pluginId);
    if (!entry) return err(this.#notFound(pluginId));
    if (entry.status === "active") return ok(undefined);
    entry.status = "registered";
    entry.error = undefined;
    return ok(undefined);
  }

  async activate(pluginId: string): Promise<Result<void>> {
    const entry = this.#entries.get(pluginId);
    if (!entry) return err(this.#notFound(pluginId));
    if (entry.status === "active") return ok(undefined);
    if (entry.status === "quarantined") {
      return err(
        new KernelError("PLUGIN_QUARANTINED", `Plugin "${pluginId}" is quarantined after a failure.`, {
          pluginId,
          cause: entry.error?.message,
        }),
      );
    }

    const dependencies = this.#checkDependencies(entry.plugin.manifest);
    if (!dependencies.ok) {
      entry.status = "failed";
      entry.error = dependencies.error;
      return err(dependencies.error);
    }

    const store = new DisposableStore();
    const scope = this.#deps.container.createScope(`plugin:${pluginId}`);
    store.add(scope);
    entry.store = store;
    entry.scope = scope;

    const context = this.#createContext(entry.plugin.manifest, scope, store);
    const outcome = await attemptAsync(
      () => entry.plugin.activate(context as never),
      "PLUGIN_ACTIVATION_FAILED",
      `Plugin "${pluginId}" failed to activate.`,
    );

    if (!outcome.ok) {
      // Roll back everything the plugin managed to register before it failed. A partially-activated
      // plugin is worse than an absent one: its commands and panels are live but its own invariants
      // are not, so leaving them wired up guarantees a second, more confusing failure later.
      store.disposeCollecting();
      entry.store = undefined;
      entry.scope = undefined;
      entry.status = "quarantined";
      entry.error = outcome.error;
      this.#deps.telemetry.error(outcome.error, { pluginId });
      this.#deps.events.emit("plugin.failed", { pluginId, error: outcome.error });
      return err(outcome.error);
    }

    entry.status = "active";
    entry.error = undefined;
    entry.activatedAt = this.#now().toISOString();
    this.#deps.telemetry.counter("plugin.activated", 1, { pluginId });
    this.#deps.events.emit("plugin.activated", { pluginId });
    return ok(undefined);
  }

  async deactivate(pluginId: string): Promise<Result<void>> {
    const entry = this.#entries.get(pluginId);
    if (!entry) return err(this.#notFound(pluginId));
    if (entry.status !== "active") return ok(undefined);

    const dependents = this.#activeDependentsOf(pluginId);
    if (dependents.length > 0) {
      return err(
        new KernelError(
          "PLUGIN_DEPENDENCY_MISSING",
          `Cannot deactivate "${pluginId}" while ${dependents.join(", ")} depend on it.`,
          { pluginId, dependents },
        ),
      );
    }

    // The plugin's own teardown runs first, then the kernel drains its registrations. Order
    // matters: `deactivate` may want to flush state through services that the store is about to
    // dispose. A throw here is recorded but does not stop the drain — otherwise a plugin could
    // make itself permanently unloadable.
    const outcome = await attemptAsync(
      () => entry.plugin.deactivate?.(),
      "PLUGIN_ACTIVATION_FAILED",
      `Plugin "${pluginId}" failed to deactivate cleanly.`,
    );

    this.#deps.state.removeSlice(`${pluginId}`);
    for (const namespace of this.#sliceNamespacesOf(pluginId)) {
      this.#deps.state.removeSlice(namespace);
    }
    entry.store?.disposeCollecting();
    entry.store = undefined;
    entry.scope = undefined;
    entry.status = "inactive";
    entry.activatedAt = undefined;

    this.#deps.events.emit("plugin.deactivated", { pluginId });
    if (!outcome.ok) {
      entry.error = outcome.error;
      this.#deps.telemetry.error(outcome.error, { pluginId });
      return err(outcome.error);
    }
    return ok(undefined);
  }

  /** Activates every registered plugin in dependency order, isolating individual failures. */
  async activateAll(): Promise<ActivationReport> {
    const activated: string[] = [];
    const failed: { id: string; error: KernelError }[] = [];
    const skipped: { id: string; reason: string }[] = [];

    const order = this.#topologicalOrder();
    if (!order.ok) {
      return {
        activated,
        failed: [{ id: "*", error: order.error }],
        skipped: [...this.#entries.keys()].map((id) => ({ id, reason: order.error.message })),
      };
    }

    const broken = new Set<string>();
    for (const id of order.value) {
      const entry = this.#entries.get(id);
      if (!entry || entry.status === "active") continue;

      const blocking = (entry.plugin.manifest.dependencies ?? []).filter(
        (dependency) => !dependency.optional && broken.has(dependency.id),
      );
      if (blocking.length > 0) {
        broken.add(id);
        skipped.push({
          id,
          reason: `dependency unavailable: ${blocking.map((d) => d.id).join(", ")}`,
        });
        continue;
      }

      const result = await this.activate(id);
      if (result.ok) activated.push(id);
      else {
        broken.add(id);
        failed.push({ id, error: result.error });
      }
    }
    return { activated, failed, skipped };
  }

  /** Deactivates every active plugin, dependents before their dependencies. */
  async deactivateAll(): Promise<void> {
    const order = this.#topologicalOrder();
    const ids = order.ok ? [...order.value].reverse() : [...this.#entries.keys()];
    for (const id of ids) {
      if (this.#entries.get(id)?.status === "active") await this.deactivate(id);
    }
  }

  #createContext(
    manifest: PluginManifest,
    scope: ServiceContainer,
    store: DisposableStore,
  ): PluginContext<THost> {
    const { commands, events, state, capabilities, ui, persistence, permissions, telemetry } = this.#deps;
    const pluginId = manifest.id;

    // Every registration below is added to `store`, which is what deactivation drains. Returning
    // the disposable as well lets a plugin release something early if it wants to.
    const track = <T extends Disposable>(disposable: T): T => {
      store.add(disposable);
      return disposable;
    };

    return {
      pluginId,
      manifest,
      services: scope,
      permissions,
      telemetry,
      logger: createLogger(telemetry, pluginId),
      subscriptions: store,
      storage: persistence.namespaced(pluginId),
      commands: {
        register: (definition) => track(commands.register(definition)),
        execute: (commandId, params, options) => commands.execute(commandId, params, options),
        has: (commandId) => commands.has(commandId),
        list: () => commands.list(),
      },
      events: {
        on: (type, handler) => track(events.on(type, handler)),
        once: (type, handler) => track(events.once(type, handler)),
        emit: (type, payload) => events.emit(type, payload),
      },
      state: {
        defineSlice: <T>(name: string, initial: T) =>
          state.defineSlice<T>(`${pluginId}/${name}`, initial),
        getSlice: <T>(namespace: string) => state.getSlice<T>(namespace),
      },
      capabilities: {
        provide: (token, value, options) =>
          track(capabilities.provide(token, value, { pluginId, ...options })),
        get: (token, options) => capabilities.get(token, options),
        require: (token, options) => capabilities.require(token, options),
        getAll: (token) => capabilities.getAll(token),
        has: (token) => capabilities.has(token),
      },
      ui: {
        register: (contribution) => track(ui.register({ ...contribution, pluginId })),
      },
    };
  }

  #sliceNamespacesOf(pluginId: string): string[] {
    const prefix = `${pluginId}/`;
    return Object.keys(this.#deps.state.snapshot()).filter((namespace) =>
      namespace.startsWith(prefix),
    );
  }

  #checkDependencies(manifest: PluginManifest): Result<void> {
    for (const dependency of manifest.dependencies ?? []) {
      const entry = this.#entries.get(dependency.id);
      if (!entry) {
        if (dependency.optional) continue;
        return err(
          new KernelError(
            "PLUGIN_DEPENDENCY_MISSING",
            `Plugin "${manifest.id}" requires "${dependency.id}", which is not registered.`,
            { pluginId: manifest.id, dependency: dependency.id },
          ),
        );
      }
      if (dependency.version && !satisfies(entry.plugin.manifest.version, dependency.version)) {
        return err(
          new KernelError(
            "PLUGIN_DEPENDENCY_MISSING",
            `Plugin "${manifest.id}" requires "${dependency.id}@${dependency.version}"; found ${entry.plugin.manifest.version}.`,
            { pluginId: manifest.id, dependency: dependency.id, required: dependency.version },
          ),
        );
      }
      if (!dependency.optional && entry.status !== "active") {
        return err(
          new KernelError(
            "PLUGIN_DEPENDENCY_MISSING",
            `Plugin "${manifest.id}" requires "${dependency.id}" to be active (it is ${entry.status}).`,
            { pluginId: manifest.id, dependency: dependency.id, status: entry.status },
          ),
        );
      }
    }
    return ok(undefined);
  }

  #activeDependentsOf(pluginId: string): string[] {
    return [...this.#entries.values()]
      .filter(
        (entry) =>
          entry.status === "active" &&
          (entry.plugin.manifest.dependencies ?? []).some(
            (dependency) => dependency.id === pluginId && !dependency.optional,
          ),
      )
      .map((entry) => entry.plugin.manifest.id);
  }

  /**
   * Depth-first topological sort. Reports the actual cycle rather than a generic failure — with a
   * dozen plugins loaded, "there is a cycle" is not a debuggable message.
   */
  #topologicalOrder(): Result<string[]> {
    const sorted: string[] = [];
    const state = new Map<string, "visiting" | "done">();
    const path: string[] = [];

    const visit = (id: string): KernelError | undefined => {
      const current = state.get(id);
      if (current === "done") return undefined;
      if (current === "visiting") {
        const cycle = [...path.slice(path.indexOf(id)), id].join(" -> ");
        return new KernelError("PLUGIN_DEPENDENCY_CYCLE", `Plugin dependency cycle: ${cycle}`, {
          cycle,
        });
      }
      const entry = this.#entries.get(id);
      if (!entry) return undefined; // unregistered dependency; reported by #checkDependencies

      state.set(id, "visiting");
      path.push(id);
      for (const dependency of entry.plugin.manifest.dependencies ?? []) {
        const failure = visit(dependency.id);
        if (failure) return failure;
      }
      path.pop();
      state.set(id, "done");
      sorted.push(id);
      return undefined;
    };

    for (const id of this.#entries.keys()) {
      const failure = visit(id);
      if (failure) return err(failure);
    }
    return ok(sorted);
  }

  #notFound(pluginId: string): KernelError {
    return new KernelError("PLUGIN_NOT_FOUND", `No plugin registered as "${pluginId}".`, {
      pluginId,
    });
  }
}

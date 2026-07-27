import { CapabilityRegistry } from "./capabilities.js";
import { CommandBus } from "./commands.js";
import { ContainerService, StorageContainerAdapter } from "./container-format.js";
import { createServiceToken, ServiceContainer, type ServiceToken } from "./container.js";
import type { Disposable } from "./disposable.js";
import { EventBus } from "./events.js";
import { createLogger, type Logger } from "./logging.js";
import {
  ALLOW_ALL,
  PermissionService,
  type Identity,
  type PermissionEvaluator,
} from "./permissions.js";
import {
  MemoryStorageAdapter,
  PersistenceEngine,
  type DocumentMigrator,
  type StorageAdapter,
} from "./persistence.js";
import { PluginHost, type ActivationReport, type Plugin, type PluginRecord } from "./plugin-host.js";
import type { Result } from "./result.js";
import { StateStore } from "./state.js";
import { NOOP_TELEMETRY, type TelemetrySink } from "./telemetry.js";
import { UIExtensionRegistry } from "./ui-registry.js";

/**
 * The kernel's own API version.
 *
 * Plugins declare a range against this. Bump the major only for a breaking change to
 * `PluginContext` or to a kernel service's contract — the whole point of the number is that a
 * plugin built today keeps working, or fails loudly at load with an actionable message.
 */
export const KERNEL_API_VERSION = "1.0.0";

export const EventBusToken = createServiceToken<EventBus>("kernel.events");
export const CommandBusToken = createServiceToken<CommandBus>("kernel.commands");
export const StateStoreToken = createServiceToken<StateStore>("kernel.state");
export const CapabilityRegistryToken = createServiceToken<CapabilityRegistry>("kernel.capabilities");
export const PersistenceToken = createServiceToken<PersistenceEngine>("kernel.persistence");
export const PermissionsToken = createServiceToken<PermissionService>("kernel.permissions");
export const TelemetryToken = createServiceToken<TelemetrySink>("kernel.telemetry");
export const LoggerToken = createServiceToken<Logger>("kernel.logger");
export const ContainerServiceToken = createServiceToken<ContainerService>("kernel.containers");

export interface KernelOptions {
  readonly storage?: StorageAdapter;
  readonly migrator?: DocumentMigrator;
  readonly telemetry?: TelemetrySink;
  readonly permissionEvaluator?: PermissionEvaluator;
  readonly identity?: Identity;
  readonly historyLimit?: number;
  readonly maxBackups?: number;
  /** Override the advertised API version. Intended for tests of compatibility handling. */
  readonly apiVersion?: string;
  readonly now?: () => Date;
}

export interface KernelDiagnostics {
  readonly apiVersion: string;
  readonly plugins: readonly PluginRecord[];
  readonly capabilities: readonly string[];
  readonly commands: number;
  readonly uiPoints: readonly string[];
  readonly history: { undo: number; redo: number };
  readonly stateNamespaces: readonly string[];
}

/**
 * The assembled backbone.
 *
 * Everything here is a *mechanism*, never a feature: there is no viewer, no markup, no massing in
 * this object or anywhere it imports. Business capability arrives exclusively through plugins, so
 * the kernel can be versioned and kept stable while the platform above it changes freely.
 */
export interface Kernel<THost = unknown> extends Disposable {
  readonly apiVersion: string;
  readonly services: ServiceContainer;
  readonly events: EventBus;
  readonly commands: CommandBus;
  readonly state: StateStore;
  readonly capabilities: CapabilityRegistry;
  readonly ui: UIExtensionRegistry<THost>;
  readonly persistence: PersistenceEngine;
  /**
   * Project containers.
   *
   * A container is the unit a user opens, saves and sends. Holding it in the kernel is what makes
   * a project and the models inside it inseparable — there is no API that opens one without the
   * other — while leaving the *format* to adapters.
   */
  readonly containers: ContainerService;
  readonly permissions: PermissionService;
  readonly telemetry: TelemetrySink;
  readonly plugins: PluginHost<THost>;
  readonly logger: Logger;

  /** Register a plugin. Does not activate it — call `start`, or `plugins.activate(id)`. */
  use(plugin: Plugin<THost>): Result<void>;
  /** Activate every registered plugin in dependency order. */
  start(): Promise<ActivationReport>;
  /** Deactivate everything, dependents first. The kernel stays usable afterwards. */
  stop(): Promise<void>;
  diagnostics(): KernelDiagnostics;
}

export function createKernel<THost = unknown>(options: KernelOptions = {}): Kernel<THost> {
  const apiVersion = options.apiVersion ?? KERNEL_API_VERSION;
  const telemetry = options.telemetry ?? NOOP_TELEMETRY;
  const logger = createLogger(telemetry, "kernel");

  const services = new ServiceContainer("kernel");
  const events = new EventBus();
  const state = new StateStore();
  const capabilities = new CapabilityRegistry();
  const ui = new UIExtensionRegistry<THost>();

  const permissions = new PermissionService();
  permissions.setEvaluator(options.permissionEvaluator ?? ALLOW_ALL);
  if (options.identity) permissions.setIdentity(options.identity);

  // One storage adapter serves both the per-document engine and the container service, so a host
  // that swaps in IndexedDB or a filesystem gets both at once rather than half a persisted app.
  const storage = options.storage ?? new MemoryStorageAdapter();

  const persistence = new PersistenceEngine({
    adapter: storage,
    ...(options.migrator ? { migrator: options.migrator } : {}),
    telemetry,
    ...(options.maxBackups === undefined ? {} : { maxBackups: options.maxBackups }),
    ...(options.now ? { now: options.now } : {}),
  });

  const containers = new ContainerService({
    events,
    telemetry,
    ...(options.migrator ? { migrator: options.migrator } : {}),
    ...(options.now ? { now: options.now } : {}),
  });
  // The reference adapter is registered by default so a host has a working container format from
  // the first line of code; a real `.mmproj` or ISO 21597 adapter simply registers alongside it.
  containers.registerAdapter(new StorageContainerAdapter(storage));

  const commands = new CommandBus({
    permissions,
    telemetry,
    ...(options.historyLimit === undefined ? {} : { historyLimit: options.historyLimit }),
    ...(options.now ? { now: () => options.now!().getTime() } : {}),
  });

  const plugins = new PluginHost<THost>({
    container: services,
    commands,
    events,
    state,
    capabilities,
    ui,
    persistence,
    permissions,
    telemetry,
    apiVersion,
    ...(options.now ? { now: options.now } : {}),
  });

  // Core services are also resolvable through the container, so a plugin's own services can take
  // them as constructor dependencies rather than closing over the context object.
  services.registerValue(EventBusToken, events);
  services.registerValue(CommandBusToken, commands);
  services.registerValue(StateStoreToken, state);
  services.registerValue(CapabilityRegistryToken, capabilities);
  services.registerValue(PersistenceToken, persistence);
  services.registerValue(ContainerServiceToken, containers);
  services.registerValue(PermissionsToken, permissions);
  services.registerValue(TelemetryToken, telemetry);
  services.registerValue(LoggerToken, logger);

  return {
    apiVersion,
    services,
    events,
    commands,
    state,
    capabilities,
    ui,
    persistence,
    containers,
    permissions,
    telemetry,
    plugins,
    logger,

    use(plugin) {
      return plugins.register(plugin);
    },

    async start() {
      const report = await plugins.activateAll();
      telemetry.event("kernel.started", {
        activated: report.activated.length,
        failed: report.failed.length,
        skipped: report.skipped.length,
      });
      events.emit("kernel.started", report);
      return report;
    },

    async stop() {
      await plugins.deactivateAll();
      events.emit("kernel.stopped", {});
    },

    diagnostics() {
      return {
        apiVersion,
        plugins: plugins.list(),
        capabilities: capabilities.tokens(),
        commands: commands.list().length,
        uiPoints: ui.points(),
        history: commands.historySize,
        stateNamespaces: Object.keys(state.snapshot()),
      };
    },

    dispose() {
      // Synchronous teardown for host shutdown. Callers wanting orderly plugin `deactivate` hooks
      // should `await stop()` first; this is the last-resort path that guarantees release.
      events.clear();
      commands.clearHistory();
      services.dispose();
    },
  };
}

export type { ServiceToken };

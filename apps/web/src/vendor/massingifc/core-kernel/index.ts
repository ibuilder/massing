/**
 * `@massingifc/core-kernel` — the permanent backbone.
 *
 * Contains mechanisms only. Nothing here knows what an IFC model, a markup pin, a massing story or
 * a cost assembly is; those arrive as plugins. Keeping the kernel feature-free is what lets it be
 * versioned and held stable while the platform above it changes.
 */

export { KernelError, toKernelError, type KernelErrorCode } from "./errors.js";
export {
  attempt,
  attemptAsync,
  err,
  isErr,
  isOk,
  mapErr,
  mapOk,
  ok,
  unwrap,
  unwrapOr,
  type Err,
  type Ok,
  type Result,
} from "./result.js";
export {
  DisposableStore,
  NOOP_DISPOSABLE,
  toDisposable,
  type Disposable,
} from "./disposable.js";
export {
  createServiceToken,
  ServiceContainer,
  type ServiceFactory,
  type ServiceLifetime,
  type ServiceRegistrationOptions,
  type ServiceToken,
} from "./container.js";
export {
  EventBus,
  type EmitReport,
  type EventHandler,
  type EventMap,
} from "./events.js";
export {
  CommandBus,
  type CommandBusOptions,
  type CommandDefinition,
  type CommandExecutionContext,
  type CommandInfo,
  type CommandInvocation,
  type CommandMiddleware,
  type ExecuteOptions,
} from "./commands.js";
export {
  StateStore,
  type Slice,
  type StateChange,
  type StateListener,
} from "./state.js";
export {
  CapabilityRegistry,
  createCapabilityToken,
  type CapabilityProvider,
  type CapabilityToken,
  type ProvideOptions,
  type RequireOptions,
} from "./capabilities.js";
export {
  UIExtensionRegistry,
  type UIContribution,
  type UIContributionPoint,
  type UIMount,
  type UIMountContext,
} from "./ui-registry.js";
export {
  ALLOW_ALL,
  ANONYMOUS_IDENTITY,
  createRoleEvaluator,
  PermissionService,
  type Identity,
  type PermissionEvaluator,
  type PermissionRequest,
} from "./permissions.js";
export {
  CompositeTelemetrySink,
  InMemoryTelemetrySink,
  NOOP_TELEMETRY,
  type TelemetryRecord,
  type TelemetrySink,
  type TelemetryTags,
} from "./telemetry.js";
export { createLogger, type LogLevel, type Logger } from "./logging.js";
export {
  isVersionedDocument,
  MemoryStorageAdapter,
  NamespacedPersistence,
  PersistenceEngine,
  type BackupEntry,
  type DocumentMigrator,
  type PersistenceOptions,
  type SaveOptions,
  type StorageAdapter,
  type VersionedDocument,
} from "./persistence.js";
export {
  ContainerService,
  StorageContainerAdapter,
  type ContainerAdapter,
  type ContainerAdapterOptions,
  type ContainerCreateInit,
  type ContainerEntry,
  type ContainerEntryKind,
  type ContainerManifest,
  type ContainerServiceOptions,
  type ContainerSource,
  type OpenContainer,
} from "./container-format.js";
export {
  PluginHost,
  type ActivationReport,
  type Plugin,
  type PluginCapabilities,
  type PluginCommands,
  type PluginContext,
  type PluginDependency,
  type PluginEvents,
  type PluginHostDependencies,
  type PluginManifest,
  type PluginRecord,
  type PluginState,
  type PluginStatus,
  type PluginUI,
} from "./plugin-host.js";
export {
  CapabilityRegistryToken,
  CommandBusToken,
  ContainerServiceToken,
  createKernel,
  EventBusToken,
  KERNEL_API_VERSION,
  LoggerToken,
  PermissionsToken,
  PersistenceToken,
  StateStoreToken,
  TelemetryToken,
  type Kernel,
  type KernelDiagnostics,
  type KernelOptions,
} from "./kernel.js";
export { compareSemVer, parseSemVer, satisfies, type SemVer } from "./semver.js";

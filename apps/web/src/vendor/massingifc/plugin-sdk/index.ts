/**
 * `@massingifc/plugin-sdk` — what a plugin author imports.
 *
 * Re-exports the kernel surface a plugin legitimately needs, so plugins depend on the SDK's
 * versioned facade rather than reaching into the kernel's internals. That indirection is what
 * makes it possible to evolve the kernel without breaking every plugin in the ecosystem.
 */

export { definePlugin, type PluginDefinition } from "./define-plugin.js";
export { createTestHarness, type TestHarness, type TestHarnessOptions } from "./testing.js";
export {
  createRecordStore,
  type Identified,
  type RecordStore,
  type RecordStoreHost,
} from "./record-store.js";
export {
  createCountingIdFactory,
  createFixedClock,
  createUuidIdFactory,
  systemClock,
  type Clock,
  type IdFactory,
} from "./runtime.js";

export {
  createCapabilityToken,
  createServiceToken,
  DisposableStore,
  err,
  isErr,
  isOk,
  KERNEL_API_VERSION,
  KernelError,
  ok,
  toDisposable,
  type CapabilityToken,
  type CommandDefinition,
  type Disposable,
  type EventMap,
  type Identity,
  type Kernel,
  type Logger,
  type Plugin,
  type PluginContext,
  type PluginDependency,
  type PluginManifest,
  type Result,
  type ServiceToken,
  type UIContribution,
  type UIContributionPoint,
} from "@massingifc/core-kernel";

import {
  createKernel,
  InMemoryTelemetrySink,
  MemoryStorageAdapter,
  type Identity,
  type Kernel,
  type PermissionEvaluator,
  type Plugin,
  type Result,
} from "@massingifc/core-kernel";
import { createDefaultMigrationRegistry, type MigrationRegistry } from "@massingifc/project-schema";

export interface TestHarnessOptions {
  readonly identity?: Identity;
  readonly permissionEvaluator?: PermissionEvaluator;
  readonly migrator?: MigrationRegistry;
}

export interface TestHarness<THost = unknown> {
  readonly kernel: Kernel<THost>;
  readonly telemetry: InMemoryTelemetrySink;
  readonly storage: MemoryStorageAdapter;
  readonly migrator: MigrationRegistry;
  /** Register and activate one plugin, returning the activation result. */
  load(plugin: Plugin<THost>): Promise<Result<void>>;
  dispose(): Promise<void>;
}

/**
 * A fully-wired kernel with in-memory storage and a capturing telemetry sink.
 *
 * Plugin tests should exercise the plugin through a *real* kernel rather than a hand-rolled mock
 * context: the behaviour most worth testing — that a failure is contained, that deactivation
 * releases every registration — lives in the host, and a mock would assert nothing about it.
 */
export function createTestHarness<THost = unknown>(
  options: TestHarnessOptions = {},
): TestHarness<THost> {
  const telemetry = new InMemoryTelemetrySink();
  const storage = new MemoryStorageAdapter();
  const migrator = options.migrator ?? createDefaultMigrationRegistry();

  const kernel = createKernel<THost>({
    telemetry,
    storage,
    migrator,
    ...(options.identity ? { identity: options.identity } : {}),
    ...(options.permissionEvaluator ? { permissionEvaluator: options.permissionEvaluator } : {}),
  });

  return {
    kernel,
    telemetry,
    storage,
    migrator,
    async load(plugin) {
      const registered = kernel.use(plugin);
      if (!registered.ok) return registered;
      return kernel.plugins.activate(plugin.manifest.id);
    },
    async dispose() {
      await kernel.stop();
      kernel.dispose();
    },
  };
}

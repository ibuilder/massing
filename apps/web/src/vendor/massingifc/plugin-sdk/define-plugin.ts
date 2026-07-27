import {
  KERNEL_API_VERSION,
  type EventMap,
  type Plugin,
  type PluginContext,
  type PluginDependency,
  type PluginManifest,
} from "@massingifc/core-kernel";

export interface PluginDefinition<THost = unknown, TEvents extends EventMap = EventMap> {
  readonly id: string;
  readonly version: string;
  readonly name?: string;
  readonly description?: string;
  /**
   * Kernel API range. Defaults to caret-compatibility with the kernel this SDK was built against,
   * which is the correct answer for almost every plugin — pin it only to work around a specific
   * incompatibility.
   */
  readonly apiVersion?: string;
  readonly dependencies?: readonly PluginDependency[];
  readonly permissions?: readonly string[];
  readonly activate: (context: PluginContext<THost, TEvents>) => void | Promise<void>;
  readonly deactivate?: () => void | Promise<void>;
}

/**
 * Builds a `Plugin` from a flat definition.
 *
 * The value over writing the object literal by hand is the manifest defaults — chiefly
 * `apiVersion`. A plugin that forgets it would either be rejected at load or, worse, silently
 * claim compatibility it has not been tested for.
 */
export function definePlugin<THost = unknown, TEvents extends EventMap = EventMap>(
  definition: PluginDefinition<THost, TEvents>,
): Plugin<THost, TEvents> {
  const manifest: PluginManifest = {
    id: definition.id,
    version: definition.version,
    apiVersion: definition.apiVersion ?? `^${KERNEL_API_VERSION}`,
    ...(definition.name === undefined ? {} : { name: definition.name }),
    ...(definition.description === undefined ? {} : { description: definition.description }),
    ...(definition.dependencies === undefined ? {} : { dependencies: definition.dependencies }),
    ...(definition.permissions === undefined ? {} : { permissions: definition.permissions }),
  };

  return {
    manifest,
    activate: definition.activate,
    ...(definition.deactivate ? { deactivate: definition.deactivate } : {}),
  };
}

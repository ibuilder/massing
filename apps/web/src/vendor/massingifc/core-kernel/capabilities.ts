import { toDisposable, type Disposable } from "./disposable.js";
import { KernelError } from "./errors.js";
import { err, ok, type Result } from "./result.js";
import { satisfies } from "./semver.js";

declare const CAPABILITY_TYPE: unique symbol;

/**
 * A named, versioned extension point.
 *
 * Capabilities are how a business feature attaches without the kernel knowing it exists. The
 * kernel ships the *token* (a contract) and never an implementation; a plugin supplies the
 * implementation; consumers ask for the token. Nothing in the kernel imports a feature package,
 * which is the property that keeps it small and stable across releases.
 */
export interface CapabilityToken<T> {
  readonly id: string;
  readonly [CAPABILITY_TYPE]?: T;
}

export function createCapabilityToken<T>(id: string): CapabilityToken<T> {
  return { id };
}

export interface CapabilityProvider<T = unknown> {
  readonly token: string;
  readonly value: T;
  /** Semantic version of the *implementation*, matched against consumer ranges. */
  readonly version: string;
  readonly pluginId: string | undefined;
  /** Higher wins when several plugins provide the same capability. Defaults to 0. */
  readonly priority: number;
}

export interface ProvideOptions {
  readonly version?: string;
  readonly pluginId?: string;
  readonly priority?: number;
}

export interface RequireOptions {
  /** Semver range the provider must satisfy, e.g. `"^1.2.0"`. */
  readonly version?: string;
}

/**
 * Registry of capability implementations.
 *
 * Several providers may register against one token — two family-repository adapters, say — so
 * lookups return the highest-priority match and `getAll` exposes the rest for hosts that want to
 * aggregate rather than choose.
 */
export class CapabilityRegistry {
  readonly #providers = new Map<string, CapabilityProvider[]>();
  readonly #listeners = new Set<(tokenId: string) => void>();

  provide<T>(token: CapabilityToken<T>, value: T, options: ProvideOptions = {}): Disposable {
    const provider: CapabilityProvider<T> = {
      token: token.id,
      value,
      version: options.version ?? "1.0.0",
      pluginId: options.pluginId,
      priority: options.priority ?? 0,
    };
    const list = this.#providers.get(token.id) ?? [];
    list.push(provider as CapabilityProvider);
    // Sorted on write so every read is O(1) — capability lookup sits on hot UI paths.
    list.sort((a, b) => b.priority - a.priority);
    this.#providers.set(token.id, list);
    this.#notify(token.id);

    return toDisposable(() => {
      const current = this.#providers.get(token.id);
      if (!current) return;
      const index = current.indexOf(provider as CapabilityProvider);
      if (index >= 0) current.splice(index, 1);
      if (current.length === 0) this.#providers.delete(token.id);
      this.#notify(token.id);
    });
  }

  has(token: CapabilityToken<unknown>): boolean {
    return (this.#providers.get(token.id)?.length ?? 0) > 0;
  }

  /** Highest-priority implementation satisfying the optional version range, or `undefined`. */
  get<T>(token: CapabilityToken<T>, options: RequireOptions = {}): T | undefined {
    const list = this.#providers.get(token.id);
    if (!list) return undefined;
    const range = options.version;
    const match = range
      ? list.find((provider) => satisfies(provider.version, range))
      : list[0];
    return match?.value as T | undefined;
  }

  /** Like `get`, but reports *why* it failed — absent versus present-but-incompatible. */
  require<T>(token: CapabilityToken<T>, options: RequireOptions = {}): Result<T> {
    const list = this.#providers.get(token.id);
    if (!list || list.length === 0) {
      return err(
        new KernelError("CAPABILITY_NOT_FOUND", `No provider for capability "${token.id}".`, {
          capability: token.id,
        }),
      );
    }
    const value = this.get(token, options);
    if (value === undefined) {
      return err(
        new KernelError(
          "CAPABILITY_VERSION_MISMATCH",
          `No provider for "${token.id}" satisfies "${options.version}".`,
          {
            capability: token.id,
            requested: options.version,
            available: list.map((provider) => provider.version),
          },
        ),
      );
    }
    return ok(value);
  }

  getAll<T>(token: CapabilityToken<T>): readonly CapabilityProvider<T>[] {
    return (this.#providers.get(token.id) ?? []) as readonly CapabilityProvider<T>[];
  }

  /** Every token that currently has at least one provider. Used by the diagnostics surface. */
  tokens(): readonly string[] {
    return [...this.#providers.keys()];
  }

  onDidChange(listener: (tokenId: string) => void): Disposable {
    this.#listeners.add(listener);
    return toDisposable(() => void this.#listeners.delete(listener));
  }

  #notify(tokenId: string): void {
    for (const listener of [...this.#listeners]) {
      try {
        listener(tokenId);
      } catch {
        // Registry bookkeeping must not fail because a listener did.
      }
    }
  }
}

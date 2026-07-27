import { DisposableStore, toDisposable, type Disposable } from "./disposable.js";
import { KernelError } from "./errors.js";
import { err, ok, type Result } from "./result.js";

declare const SERVICE_TYPE: unique symbol;

/**
 * A typed key for a service.
 *
 * Tokens are nominal (backed by a fresh `symbol`), so two unrelated packages that both want a
 * `"logger"` cannot collide, and the phantom `T` lets `resolve` infer the service type without a
 * cast at the call site.
 */
export interface ServiceToken<T> {
  readonly key: symbol;
  readonly name: string;
  readonly [SERVICE_TYPE]?: T;
}

export function createServiceToken<T>(name: string): ServiceToken<T> {
  return { key: Symbol(name), name };
}

export type ServiceFactory<T> = (container: ServiceContainer) => T;

export type ServiceLifetime =
  /** Built at most once per owning container, then cached and reused. */
  | "singleton"
  /** Rebuilt on every `resolve`. The container never caches or disposes these. */
  | "transient";

export interface ServiceRegistrationOptions {
  readonly lifetime?: ServiceLifetime;
  /**
   * Whether the container disposes a singleton instance that implements `Disposable`.
   * Defaults to `true`. Set `false` when registering a value the container does not own.
   */
  readonly disposeOnRelease?: boolean;
}

interface Registration {
  readonly factory: ServiceFactory<unknown>;
  readonly lifetime: ServiceLifetime;
  readonly disposeOnRelease: boolean;
}

/**
 * Hierarchical service registry.
 *
 * Child scopes are the isolation mechanism the plugin host relies on: each plugin resolves through
 * its own scope, so it can override or add services for itself without mutating the kernel's
 * registry, and disposing the scope releases exactly what that plugin created.
 *
 * Lookup walks to the parent, but a singleton is cached on the container that *owns* the
 * registration — so a kernel-level service stays a genuine singleton no matter how many plugin
 * scopes resolve it.
 */
export class ServiceContainer implements Disposable {
  readonly label: string;
  readonly #parent: ServiceContainer | undefined;
  readonly #registrations = new Map<symbol, Registration>();
  readonly #instances = new Map<symbol, unknown>();
  readonly #owned = new DisposableStore();
  /** Shared across the whole container tree so a cycle spanning parent and child is still caught. */
  readonly #resolving: symbol[];
  #disposed = false;

  constructor(label = "root", parent?: ServiceContainer) {
    this.label = label;
    this.#parent = parent;
    this.#resolving = parent ? parent.#resolving : [];
  }

  get disposed(): boolean {
    return this.#disposed;
  }

  register<T>(
    token: ServiceToken<T>,
    factory: ServiceFactory<T>,
    options: ServiceRegistrationOptions = {},
  ): Disposable {
    this.#assertLive();
    if (this.#registrations.has(token.key)) {
      throw new KernelError(
        "SERVICE_DUPLICATE",
        `Service "${token.name}" is already registered in scope "${this.label}".`,
        { service: token.name, scope: this.label },
      );
    }
    this.#registrations.set(token.key, {
      factory: factory as ServiceFactory<unknown>,
      lifetime: options.lifetime ?? "singleton",
      disposeOnRelease: options.disposeOnRelease ?? true,
    });
    return toDisposable(() => {
      this.#releaseInstance(token.key);
      this.#registrations.delete(token.key);
    });
  }

  /** Register an already-constructed value. The container does not take ownership of its lifetime. */
  registerValue<T>(token: ServiceToken<T>, value: T): Disposable {
    return this.register(token, () => value, { lifetime: "singleton", disposeOnRelease: false });
  }

  /** True if this container or any ancestor can supply the token. */
  has(token: ServiceToken<unknown>): boolean {
    return this.#registrations.has(token.key) || (this.#parent?.has(token) ?? false);
  }

  resolve<T>(token: ServiceToken<T>): T {
    this.#assertLive();
    const owner = this.#ownerOf(token.key);
    if (!owner) {
      throw new KernelError("SERVICE_NOT_FOUND", `No service registered for "${token.name}".`, {
        service: token.name,
        scope: this.label,
      });
    }
    return owner.#instantiate(token) as T;
  }

  /** Non-throwing `resolve`, for callers that treat a missing service as an ordinary branch. */
  tryResolve<T>(token: ServiceToken<T>): Result<T> {
    try {
      return ok(this.resolve(token));
    } catch (thrown) {
      return err(
        thrown instanceof KernelError
          ? thrown
          : new KernelError("SERVICE_NOT_FOUND", `Failed to resolve "${token.name}".`, {
              service: token.name,
            }),
      );
    }
  }

  createScope(label: string): ServiceContainer {
    this.#assertLive();
    const scope = new ServiceContainer(label, this);
    this.#owned.add(scope);
    return scope;
  }

  dispose(): void {
    if (this.#disposed) return;
    this.#disposed = true;
    for (const key of [...this.#instances.keys()]) this.#releaseInstance(key);
    this.#instances.clear();
    this.#registrations.clear();
    this.#owned.dispose();
  }

  #ownerOf(key: symbol): ServiceContainer | undefined {
    if (this.#registrations.has(key)) return this;
    // Written long-hand: an optional chain may not contain a private identifier.
    const parent = this.#parent;
    return parent ? parent.#ownerOf(key) : undefined;
  }

  #instantiate<T>(token: ServiceToken<T>): unknown {
    const registration = this.#registrations.get(token.key);
    if (!registration) {
      throw new KernelError("SERVICE_NOT_FOUND", `No service registered for "${token.name}".`, {
        service: token.name,
      });
    }

    if (registration.lifetime === "singleton" && this.#instances.has(token.key)) {
      return this.#instances.get(token.key);
    }

    // A factory that resolves its own token — directly or through a chain — would otherwise recurse
    // until the stack blows, producing a `RangeError` with none of the useful context. Reporting the
    // actual cycle is the difference between a two-minute fix and an afternoon.
    if (this.#resolving.includes(token.key)) {
      const cycle = [...this.#resolving, token.key]
        .map((key) => key.description ?? "anonymous")
        .join(" -> ");
      throw new KernelError("SERVICE_CIRCULAR", `Circular service dependency: ${cycle}`, { cycle });
    }

    this.#resolving.push(token.key);
    let instance: unknown;
    try {
      instance = registration.factory(this);
    } finally {
      this.#resolving.pop();
    }

    if (registration.lifetime === "singleton") {
      this.#instances.set(token.key, instance);
      if (registration.disposeOnRelease && isDisposable(instance)) {
        this.#owned.add(instance);
      }
    }
    return instance;
  }

  #releaseInstance(key: symbol): void {
    const registration = this.#registrations.get(key);
    const instance = this.#instances.get(key);
    this.#instances.delete(key);
    if (registration?.disposeOnRelease && isDisposable(instance)) {
      try {
        instance.dispose();
      } catch {
        // A service that throws on teardown must not block the rest of the container from closing.
      }
    }
  }

  #assertLive(): void {
    if (this.#disposed) {
      throw new KernelError("CONTAINER_DISPOSED", `Container "${this.label}" is disposed.`, {
        scope: this.label,
      });
    }
  }
}

function isDisposable(value: unknown): value is Disposable {
  return (
    typeof value === "object" &&
    value !== null &&
    typeof (value as Disposable).dispose === "function"
  );
}

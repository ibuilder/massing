/**
 * Deterministic teardown.
 *
 * Every kernel subsystem hands back a `Disposable` instead of an ad-hoc `off()`/`remove()` pair.
 * That matters most for plugins: deactivating a plugin must reliably release its subscriptions,
 * commands, panels and services, and the only way to guarantee that is for the plugin host to hold
 * a single store it can drain.
 */
export interface Disposable {
  dispose(): void;
}

export function toDisposable(fn: () => void): Disposable {
  let done = false;
  return {
    dispose() {
      if (done) return; // idempotent: double-dispose is a no-op, not a second side effect
      done = true;
      fn();
    },
  };
}

/** A `Disposable` that does nothing. Useful as a safe return from a no-op registration path. */
export const NOOP_DISPOSABLE: Disposable = Object.freeze({ dispose(): void {} });

/**
 * An ordered collection of disposables, drained in reverse registration order.
 *
 * Reverse order is deliberate — later registrations may depend on earlier ones (a panel registered
 * after the service it renders), so tearing down newest-first mirrors construction and avoids
 * disposing something still in use.
 */
export class DisposableStore implements Disposable {
  #items: Disposable[] = [];
  #disposed = false;

  get disposed(): boolean {
    return this.#disposed;
  }

  get size(): number {
    return this.#items.length;
  }

  /**
   * Adds a disposable. If the store is already disposed the item is disposed immediately rather
   * than retained — otherwise a late registration during teardown would leak forever.
   */
  add<T extends Disposable>(item: T): T {
    if (this.#disposed) {
      item.dispose();
      return item;
    }
    this.#items.push(item);
    return item;
  }

  /**
   * Disposes everything, collecting rather than propagating failures.
   *
   * One badly-behaved disposable must not strand the rest — a plugin whose panel teardown throws
   * would otherwise leave its event subscriptions live and keep receiving kernel traffic after
   * deactivation. Errors are returned so the caller (the plugin host) can quarantine and report.
   */
  dispose(): void {
    void this.disposeCollecting();
  }

  disposeCollecting(): unknown[] {
    if (this.#disposed) return [];
    this.#disposed = true;
    const errors: unknown[] = [];
    for (let i = this.#items.length - 1; i >= 0; i--) {
      try {
        this.#items[i]?.dispose();
      } catch (thrown) {
        errors.push(thrown);
      }
    }
    this.#items = [];
    return errors;
  }
}

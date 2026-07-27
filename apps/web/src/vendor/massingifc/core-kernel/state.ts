import { toDisposable, type Disposable } from "./disposable.js";
import { KernelError } from "./errors.js";

export type StateListener<T> = (next: T, previous: T) => void;

/**
 * A namespaced, independently-subscribable region of application state.
 *
 * State is deliberately partitioned rather than held as one global object: a plugin owns its own
 * namespace, subscribers only wake for changes to the slice they asked about, and persistence can
 * version each namespace's payload separately (which is what makes per-plugin schema migration
 * possible at all).
 */
export interface Slice<T> {
  readonly namespace: string;
  get(): T;
  set(next: T): void;
  update(recipe: (current: T) => T): void;
  subscribe(listener: StateListener<T>): Disposable;
  /** Subscribe to a derived value, notified only when the projection actually changes. */
  select<U>(
    selector: (state: T) => U,
    listener: StateListener<U>,
    equals?: (a: U, b: U) => boolean,
  ): Disposable;
}

interface SliceRecord {
  value: unknown;
  readonly listeners: Set<StateListener<never>>;
}

export interface StateChange {
  readonly namespace: string;
  readonly next: unknown;
  readonly previous: unknown;
}

/**
 * The central store.
 *
 * Values are treated as immutable — `update` must return a new value rather than mutating in
 * place. That is what lets `select` compare with `Object.is` and what makes a snapshot safe to
 * hand to the persistence engine without cloning.
 */
export class StateStore {
  readonly #slices = new Map<string, SliceRecord>();
  /**
   * State restored before its owning slice exists.
   *
   * Persistence loads a whole project up front, but a plugin's slice only appears when that plugin
   * activates — which may be seconds later, or never. Parking the value here means load order stops
   * mattering: whoever arrives second finds the other waiting.
   */
  readonly #pending = new Map<string, unknown>();
  readonly #observers = new Set<(change: StateChange) => void>();
  #transactionDepth = 0;
  #dirty = new Map<string, unknown>();

  defineSlice<T>(namespace: string, initial: T): Slice<T> {
    if (this.#slices.has(namespace)) {
      throw new KernelError(
        "STATE_NAMESPACE_CONFLICT",
        `State namespace "${namespace}" is already defined.`,
        { namespace },
      );
    }
    const restored = this.#pending.has(namespace);
    const record: SliceRecord = {
      value: restored ? this.#pending.get(namespace) : initial,
      listeners: new Set(),
    };
    this.#pending.delete(namespace);
    this.#slices.set(namespace, record);
    return this.#makeHandle<T>(namespace, record);
  }

  hasSlice(namespace: string): boolean {
    return this.#slices.has(namespace);
  }

  getSlice<T>(namespace: string): Slice<T> | undefined {
    const record = this.#slices.get(namespace);
    return record ? this.#makeHandle<T>(namespace, record) : undefined;
  }

  /** Releases a slice and its listeners. Used when a plugin deactivates. */
  removeSlice(namespace: string): void {
    const record = this.#slices.get(namespace);
    if (!record) return;
    record.listeners.clear();
    this.#slices.delete(namespace);
  }

  /** A plain object of every live slice, suitable for handing to persistence. */
  snapshot(): Record<string, unknown> {
    const out: Record<string, unknown> = {};
    for (const [namespace, record] of this.#slices) out[namespace] = record.value;
    for (const [namespace, value] of this.#pending) out[namespace] = value;
    return out;
  }

  /**
   * Restore a snapshot. Namespaces with no live slice are parked (see `#pending`) rather than
   * dropped, so a plugin activating later still receives its persisted state.
   */
  restore(snapshot: Readonly<Record<string, unknown>>): void {
    this.transaction(() => {
      for (const [namespace, value] of Object.entries(snapshot)) {
        const record = this.#slices.get(namespace);
        if (record) {
          this.#commit(namespace, record, value);
        } else {
          this.#pending.set(namespace, value);
        }
      }
    });
  }

  /**
   * Batch writes so subscribers see one notification per slice at the end.
   *
   * Without this, a command touching five slices produces five render passes; with it, one. Nested
   * transactions are counted, not re-entered, so a composite command can safely wrap sub-commands
   * that transact on their own.
   */
  transaction(fn: () => void): void {
    this.#transactionDepth++;
    try {
      fn();
    } finally {
      this.#transactionDepth--;
      if (this.#transactionDepth === 0) this.#flush();
    }
  }

  observe(observer: (change: StateChange) => void): Disposable {
    this.#observers.add(observer);
    return toDisposable(() => void this.#observers.delete(observer));
  }

  #makeHandle<T>(namespace: string, record: SliceRecord): Slice<T> {
    const store = this;
    return {
      namespace,
      get: () => record.value as T,
      set(next: T) {
        store.#commit(namespace, record, next);
      },
      update(recipe: (current: T) => T) {
        store.#commit(namespace, record, recipe(record.value as T));
      },
      subscribe(listener: StateListener<T>): Disposable {
        record.listeners.add(listener as StateListener<never>);
        return toDisposable(() => void record.listeners.delete(listener as StateListener<never>));
      },
      select<U>(
        selector: (state: T) => U,
        listener: StateListener<U>,
        equals: (a: U, b: U) => boolean = Object.is,
      ): Disposable {
        let current = selector(record.value as T);
        return this.subscribe((next) => {
          const projected = selector(next);
          if (equals(projected, current)) return;
          const previous = current;
          current = projected;
          listener(projected, previous);
        });
      },
    };
  }

  #commit(namespace: string, record: SliceRecord, next: unknown): void {
    const previous = record.value;
    if (Object.is(previous, next)) return; // no-op writes must not wake subscribers
    record.value = next;

    if (this.#transactionDepth > 0) {
      // Keep the *earliest* previous value: at flush time a subscriber cares about the state
      // before the transaction opened, not about intermediate steps it never observed.
      if (!this.#dirty.has(namespace)) this.#dirty.set(namespace, previous);
      return;
    }
    this.#notify(namespace, record, next, previous);
  }

  #flush(): void {
    if (this.#dirty.size === 0) return;
    const dirty = this.#dirty;
    this.#dirty = new Map();
    for (const [namespace, previous] of dirty) {
      const record = this.#slices.get(namespace);
      if (record) this.#notify(namespace, record, record.value, previous);
    }
  }

  #notify(namespace: string, record: SliceRecord, next: unknown, previous: unknown): void {
    for (const listener of [...record.listeners]) {
      try {
        (listener as StateListener<unknown>)(next, previous);
      } catch {
        // A throwing subscriber must not prevent the remaining subscribers from seeing the change,
        // nor unwind the command that performed the write.
      }
    }
    for (const observer of [...this.#observers]) {
      try {
        observer({ namespace, next, previous });
      } catch {
        // Observers are diagnostics only.
      }
    }
  }
}

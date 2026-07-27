import { toDisposable, type Disposable } from "./disposable.js";
import { toKernelError, type KernelError } from "./errors.js";

/** Event topic -> payload type. Plugins widen this via declaration merging on `KernelEvents`. */
export type EventMap = Record<string, unknown>;

export type EventHandler<T> = (payload: T) => void;

export interface EmitReport {
  readonly type: string;
  readonly delivered: number;
  /** Failures raised by individual handlers. Empty on a clean emit. */
  readonly errors: readonly KernelError[];
}

/**
 * Synchronous, typed publish/subscribe.
 *
 * Two properties the rest of the kernel depends on:
 *
 *  1. **`emit` never throws.** A subscriber is frequently plugin code, and one plugin throwing in a
 *     `selection.changed` handler must not abort delivery to the other nine or unwind the caller
 *     that published the event. Failures are collected into the report and surfaced through
 *     telemetry instead.
 *  2. **The handler list is snapshotted before dispatch.** Handlers routinely subscribe or
 *     unsubscribe in response to an event; without a snapshot that mutates the array mid-iteration,
 *     which silently skips handlers or delivers to one that just unsubscribed.
 */
export class EventBus<TEvents extends EventMap = EventMap> {
  readonly #handlers = new Map<string, Set<EventHandler<never>>>();
  readonly #observers = new Set<(type: string, payload: unknown) => void>();

  on<K extends keyof TEvents & string>(type: K, handler: EventHandler<TEvents[K]>): Disposable {
    let set = this.#handlers.get(type);
    if (!set) {
      set = new Set();
      this.#handlers.set(type, set);
    }
    set.add(handler as EventHandler<never>);
    return toDisposable(() => {
      const current = this.#handlers.get(type);
      if (!current) return;
      current.delete(handler as EventHandler<never>);
      if (current.size === 0) this.#handlers.delete(type);
    });
  }

  once<K extends keyof TEvents & string>(type: K, handler: EventHandler<TEvents[K]>): Disposable {
    const subscription = this.on(type, (payload) => {
      subscription.dispose();
      handler(payload);
    });
    return subscription;
  }

  /**
   * Observe every event regardless of topic. Intended for diagnostics, recording and telemetry —
   * observers cannot alter delivery and their failures are swallowed, so this is never a
   * back-channel for business logic.
   */
  observe(observer: (type: string, payload: unknown) => void): Disposable {
    this.#observers.add(observer);
    return toDisposable(() => void this.#observers.delete(observer));
  }

  emit<K extends keyof TEvents & string>(type: K, payload: TEvents[K]): EmitReport {
    const errors: KernelError[] = [];
    const snapshot = this.#handlers.get(type);
    let delivered = 0;

    if (snapshot) {
      for (const handler of [...snapshot]) {
        try {
          (handler as EventHandler<TEvents[K]>)(payload);
          delivered++;
        } catch (thrown) {
          errors.push(
            toKernelError(thrown, "COMMAND_FAILED", `Event handler for "${type}" failed.`),
          );
        }
      }
    }

    for (const observer of [...this.#observers]) {
      try {
        observer(type, payload);
      } catch {
        // Diagnostics must never influence delivery.
      }
    }

    return { type, delivered, errors };
  }

  listenerCount(type: string): number {
    return this.#handlers.get(type)?.size ?? 0;
  }

  clear(): void {
    this.#handlers.clear();
    this.#observers.clear();
  }
}

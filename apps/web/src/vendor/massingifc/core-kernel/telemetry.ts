import { toDisposable, type Disposable } from "./disposable.js";
import type { KernelError } from "./errors.js";

export type TelemetryTags = Readonly<Record<string, string | number | boolean>>;

/**
 * Where diagnostics go.
 *
 * The kernel emits telemetry unconditionally and lets the host decide whether it is discarded,
 * kept in memory, or shipped somewhere. Nothing in the kernel reads telemetry back, so a sink is
 * always safe to replace with `NoopTelemetrySink`.
 */
export interface TelemetrySink {
  counter(name: string, value?: number, tags?: TelemetryTags): void;
  timing(name: string, milliseconds: number, tags?: TelemetryTags): void;
  event(name: string, data?: Readonly<Record<string, unknown>>): void;
  error(error: KernelError, context?: Readonly<Record<string, unknown>>): void;
}

export const NOOP_TELEMETRY: TelemetrySink = Object.freeze({
  counter(): void {},
  timing(): void {},
  event(): void {},
  error(): void {},
});

export interface TelemetryRecord {
  readonly kind: "counter" | "timing" | "event" | "error";
  readonly name: string;
  readonly value?: number;
  readonly tags?: TelemetryTags;
  readonly data?: Readonly<Record<string, unknown>>;
  readonly error?: KernelError;
}

/**
 * Retains a bounded ring of recent records.
 *
 * Bounded on purpose: this backs the diagnostics panel and long-running sessions would otherwise
 * grow it without limit — a memory leak dressed up as observability.
 */
export class InMemoryTelemetrySink implements TelemetrySink {
  readonly #records: TelemetryRecord[] = [];
  readonly #limit: number;

  constructor(limit = 1000) {
    this.#limit = Math.max(1, limit);
  }

  get records(): readonly TelemetryRecord[] {
    return this.#records;
  }

  counter(name: string, value = 1, tags?: TelemetryTags): void {
    this.#push({ kind: "counter", name, value, ...(tags ? { tags } : {}) });
  }

  timing(name: string, milliseconds: number, tags?: TelemetryTags): void {
    this.#push({ kind: "timing", name, value: milliseconds, ...(tags ? { tags } : {}) });
  }

  event(name: string, data?: Readonly<Record<string, unknown>>): void {
    this.#push({ kind: "event", name, ...(data ? { data } : {}) });
  }

  error(error: KernelError, context?: Readonly<Record<string, unknown>>): void {
    this.#push({ kind: "error", name: error.code, error, ...(context ? { data: context } : {}) });
  }

  clear(): void {
    this.#records.length = 0;
  }

  #push(record: TelemetryRecord): void {
    this.#records.push(record);
    if (this.#records.length > this.#limit) this.#records.shift();
  }
}

/** Fans out to several sinks, isolating each so one failing sink cannot suppress the others. */
export class CompositeTelemetrySink implements TelemetrySink {
  readonly #sinks = new Set<TelemetrySink>();

  add(sink: TelemetrySink): Disposable {
    this.#sinks.add(sink);
    return toDisposable(() => void this.#sinks.delete(sink));
  }

  counter(name: string, value?: number, tags?: TelemetryTags): void {
    this.#each((s) => s.counter(name, value, tags));
  }

  timing(name: string, milliseconds: number, tags?: TelemetryTags): void {
    this.#each((s) => s.timing(name, milliseconds, tags));
  }

  event(name: string, data?: Readonly<Record<string, unknown>>): void {
    this.#each((s) => s.event(name, data));
  }

  error(error: KernelError, context?: Readonly<Record<string, unknown>>): void {
    this.#each((s) => s.error(error, context));
  }

  #each(fn: (sink: TelemetrySink) => void): void {
    for (const sink of [...this.#sinks]) {
      try {
        fn(sink);
      } catch {
        // Telemetry is strictly best-effort; a broken sink must never surface as an app failure.
      }
    }
  }
}

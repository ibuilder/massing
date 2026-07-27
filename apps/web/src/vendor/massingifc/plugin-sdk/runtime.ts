import type { IsoTimestamp } from "@massingifc/project-schema";

/**
 * Time, as a port.
 *
 * Every record in the platform is timestamped, and a great many behaviours are time-dependent —
 * issue due dates, backup ids, schedule variance, observation windows. Reading the clock directly
 * would make all of that untestable without freezing global time, so the clock is injected and
 * tests supply a deterministic one.
 */
export interface Clock {
  now(): Date;
  timestamp(): IsoTimestamp;
}

export const systemClock: Clock = {
  now: () => new Date(),
  timestamp: () => new Date().toISOString(),
};

/** A clock that starts at a fixed instant and advances only when told to. */
export function createFixedClock(start: string | Date = "2026-01-01T00:00:00.000Z"): Clock & {
  advance(milliseconds: number): void;
} {
  let current = new Date(start).getTime();
  return {
    now: () => new Date(current),
    timestamp: () => new Date(current).toISOString(),
    advance(milliseconds) {
      current += milliseconds;
    },
  };
}

/**
 * Identifier generation, also a port.
 *
 * The default is a monotonic per-prefix counter rather than a UUID. Records here are scoped to a
 * project document, not a distributed system, and readable ids (`mass-3`, `issue-12`) make test
 * failures and persisted files far easier to read. Hosts needing globally-unique ids install a
 * UUID factory instead.
 */
export interface IdFactory {
  next(prefix: string): string;
}

export function createCountingIdFactory(): IdFactory {
  const counters = new Map<string, number>();
  return {
    next(prefix) {
      const value = (counters.get(prefix) ?? 0) + 1;
      counters.set(prefix, value);
      return `${prefix}-${value}`;
    },
  };
}

export function createUuidIdFactory(): IdFactory {
  // Reached through `globalThis` rather than the bare `crypto` binding: this package targets
  // browsers, Node and workers alike, and only the DOM lib declares the global.
  const host = globalThis as { crypto?: { randomUUID?: () => string } };
  return {
    next(prefix) {
      const randomUUID = host.crypto?.randomUUID;
      const uuid = randomUUID
        ? randomUUID.call(host.crypto)
        : `${Date.now().toString(36)}-${Math.floor(Math.random() * 1e9).toString(36)}`;
      return `${prefix}-${uuid}`;
    },
  };
}

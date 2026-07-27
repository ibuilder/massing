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
  const host = globalThis as {
    crypto?: { randomUUID?: () => string; getRandomValues?: (a: Uint8Array) => Uint8Array };
  };
  return {
    next(prefix) {
      const randomUUID = host.crypto?.randomUUID;
      if (randomUUID) return `${prefix}-${randomUUID.call(host.crypto)}`;

      // LOCAL PATCH (see VENDOR.md): the fallback was `Date.now()` + `Math.random()`, which CodeQL
      // flags as js/insecure-randomness at high severity — correctly. `Math.random()` is seeded, not
      // cryptographic, so ids drawn from it are predictable. This is a general-purpose id factory:
      // it cannot know whether a caller will use an id as a mere key or as a capability, and one
      // that turns out to be a share token is unguessable only by accident.
      const values = host.crypto?.getRandomValues;
      if (values) {
        const bytes = values.call(host.crypto, new Uint8Array(16));
        return `${prefix}-${Array.from(bytes, (b) => b.toString(16).padStart(2, "0")).join("")}`;
      }

      // Neither API present: REFUSE. Silently returning a weak id would be indistinguishable from a
      // strong one at every call site, and would only be discovered by whatever it failed to protect.
      throw new Error(
        "createUuidIdFactory: no cryptographic randomness available (crypto.randomUUID and "
        + "crypto.getRandomValues are both missing). Supply an explicit IdFactory — a predictable "
        + "id is not a safe default.",
      );
    },
  };
}

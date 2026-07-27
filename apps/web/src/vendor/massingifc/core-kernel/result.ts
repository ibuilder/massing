import { KernelError, toKernelError, type KernelErrorCode } from "./errors.js";

/**
 * Explicit success/failure values.
 *
 * The kernel's non-negotiable is that *no plugin can crash the base viewer*. Exceptions propagate
 * by default and satisfy that only if every call site remembers to guard; a `Result` inverts this,
 * making the failure branch visible in the type. Kernel APIs that invoke plugin-supplied code
 * return `Result` rather than throwing.
 */
export type Result<T, E = KernelError> = Ok<T> | Err<E>;

export interface Ok<T> {
  readonly ok: true;
  readonly value: T;
}

export interface Err<E> {
  readonly ok: false;
  readonly error: E;
}

export const ok = <T>(value: T): Ok<T> => ({ ok: true, value });
export const err = <E>(error: E): Err<E> => ({ ok: false, error });

export function isOk<T, E>(result: Result<T, E>): result is Ok<T> {
  return result.ok;
}

export function isErr<T, E>(result: Result<T, E>): result is Err<E> {
  return !result.ok;
}

/** Unwrap a success, or throw the failure. Use at trust boundaries, not in plugin code. */
export function unwrap<T, E>(result: Result<T, E>): T {
  if (result.ok) return result.value;
  throw result.error;
}

/** Unwrap a success, or fall back. Never throws. */
export function unwrapOr<T, E>(result: Result<T, E>, fallback: T): T {
  return result.ok ? result.value : fallback;
}

export function mapOk<T, U, E>(result: Result<T, E>, fn: (value: T) => U): Result<U, E> {
  return result.ok ? ok(fn(result.value)) : result;
}

export function mapErr<T, E, F>(result: Result<T, E>, fn: (error: E) => F): Result<T, F> {
  return result.ok ? result : err(fn(result.error));
}

/** Run a synchronous function, converting any throw into an `Err<KernelError>`. */
export function attempt<T>(
  fn: () => T,
  code: KernelErrorCode,
  message: string,
): Result<T, KernelError> {
  try {
    return ok(fn());
  } catch (thrown) {
    return err(toKernelError(thrown, code, message));
  }
}

/**
 * Run a possibly-async function, converting a synchronous throw *or* a rejected promise into an
 * `Err<KernelError>`. Plugin entry points are `unknown`-returning by nature — a plugin may declare
 * `activate()` as sync and still return a rejecting promise — so both paths need catching.
 */
export async function attemptAsync<T>(
  fn: () => T | Promise<T>,
  code: KernelErrorCode,
  message: string,
): Promise<Result<T, KernelError>> {
  try {
    return ok(await fn());
  } catch (thrown) {
    return err(toKernelError(thrown, code, message));
  }
}

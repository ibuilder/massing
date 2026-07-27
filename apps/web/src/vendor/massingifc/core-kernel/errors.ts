/**
 * Kernel error taxonomy.
 *
 * Every failure the kernel can produce carries a stable machine-readable `code`. Host applications
 * and plugins branch on the code, never on the message text — messages are for humans and are free
 * to change, codes are part of the kernel's contract and are not.
 */

export type KernelErrorCode =
  | "SERVICE_NOT_FOUND"
  | "SERVICE_DUPLICATE"
  | "SERVICE_CIRCULAR"
  | "CONTAINER_DISPOSED"
  | "COMMAND_NOT_FOUND"
  | "COMMAND_DUPLICATE"
  | "COMMAND_FAILED"
  | "PERMISSION_DENIED"
  | "CAPABILITY_NOT_FOUND"
  | "CAPABILITY_VERSION_MISMATCH"
  | "PLUGIN_DUPLICATE"
  | "PLUGIN_NOT_FOUND"
  | "PLUGIN_DEPENDENCY_MISSING"
  | "PLUGIN_DEPENDENCY_CYCLE"
  | "PLUGIN_API_INCOMPATIBLE"
  | "PLUGIN_ACTIVATION_FAILED"
  | "PLUGIN_QUARANTINED"
  | "STORAGE_FAILED"
  | "MIGRATION_FAILED"
  | "MIGRATION_PATH_MISSING"
  | "SCHEMA_VERSION_UNSUPPORTED"
  | "STATE_NAMESPACE_CONFLICT";

export class KernelError extends Error {
  readonly code: KernelErrorCode;
  /** Arbitrary structured context. Safe to log; must never contain secrets. */
  readonly details: Readonly<Record<string, unknown>>;

  constructor(
    code: KernelErrorCode,
    message: string,
    details: Record<string, unknown> = {},
    options?: { cause?: unknown },
  ) {
    super(message, options as ErrorOptions);
    this.name = "KernelError";
    this.code = code;
    this.details = Object.freeze({ ...details });
  }
}

/**
 * Coerce anything thrown into a `KernelError`.
 *
 * Plugin code is third-party by definition and can `throw` a string, `undefined`, or an object with
 * a getter that throws again. Everything crossing the kernel boundary funnels through here so the
 * rest of the system only ever handles one error shape.
 */
export function toKernelError(
  value: unknown,
  fallbackCode: KernelErrorCode,
  fallbackMessage: string,
): KernelError {
  if (value instanceof KernelError) return value;
  if (value instanceof Error) {
    return new KernelError(fallbackCode, value.message || fallbackMessage, {}, { cause: value });
  }
  let described: string;
  try {
    described = typeof value === "string" ? value : JSON.stringify(value);
  } catch {
    described = String(value);
  }
  return new KernelError(fallbackCode, described || fallbackMessage, { thrown: described });
}

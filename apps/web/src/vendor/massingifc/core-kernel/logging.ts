import { toKernelError } from "./errors.js";
import type { TelemetrySink } from "./telemetry.js";

export type LogLevel = "debug" | "info" | "warn" | "error";

export interface Logger {
  debug(message: string, data?: Readonly<Record<string, unknown>>): void;
  info(message: string, data?: Readonly<Record<string, unknown>>): void;
  warn(message: string, data?: Readonly<Record<string, unknown>>): void;
  error(message: string, cause?: unknown, data?: Readonly<Record<string, unknown>>): void;
}

/**
 * A scoped logger backed by the telemetry sink.
 *
 * Logging routes through telemetry rather than `console` so a host can capture plugin output the
 * same way it captures everything else — and so a headless or embedded deployment has somewhere
 * for it to go other than a terminal nobody is reading.
 */
export function createLogger(telemetry: TelemetrySink, scope: string): Logger {
  const emit = (level: LogLevel, message: string, data?: Readonly<Record<string, unknown>>): void => {
    telemetry.event(`log.${level}`, { scope, message, ...(data ?? {}) });
  };
  return {
    debug: (message, data) => emit("debug", message, data),
    info: (message, data) => emit("info", message, data),
    warn: (message, data) => emit("warn", message, data),
    error: (message, cause, data) => {
      telemetry.error(toKernelError(cause, "PLUGIN_ACTIVATION_FAILED", message), {
        scope,
        message,
        ...(data ?? {}),
      });
    },
  };
}

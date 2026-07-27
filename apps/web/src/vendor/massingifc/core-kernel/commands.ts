import { toDisposable, type Disposable } from "./disposable.js";
import { KernelError } from "./errors.js";
import type { Identity, PermissionService } from "./permissions.js";
import { attemptAsync, err, type Result } from "./result.js";
import { NOOP_TELEMETRY, type TelemetrySink } from "./telemetry.js";

export interface CommandInvocation<P = unknown> {
  readonly commandId: string;
  readonly params: P;
}

export interface CommandExecutionContext {
  readonly commandId: string;
  readonly identity: Identity;
  readonly signal: AbortSignal | undefined;
  /** 0 for a user-initiated command; higher when one command invokes another. */
  readonly depth: number;
}

export interface CommandDefinition<P = void, R = void> {
  readonly id: string;
  readonly title?: string;
  readonly description?: string;
  /** Permission action checked before the handler runs. Omit for unrestricted commands. */
  readonly permission?: string;
  readonly handler: (params: P, context: CommandExecutionContext) => R | Promise<R>;
  /**
   * Builds the invocation that reverses this one. Defining it is what makes a command undoable.
   *
   * Expressing undo as *another command* rather than as a closure keeps the history serializable
   * and replayable, and means undo goes through the same permission and middleware path as the
   * original action instead of quietly bypassing it.
   */
  readonly createInverse?: (params: P, result: R) => CommandInvocation | undefined;
}

export interface CommandInfo {
  readonly id: string;
  readonly title: string | undefined;
  readonly description: string | undefined;
  readonly permission: string | undefined;
  readonly undoable: boolean;
}

export type CommandMiddleware = (
  invocation: CommandInvocation,
  next: () => Promise<Result<unknown>>,
) => Promise<Result<unknown>>;

export interface CommandBusOptions {
  readonly permissions?: PermissionService;
  readonly telemetry?: TelemetrySink;
  readonly historyLimit?: number;
  readonly now?: () => number;
}

export interface ExecuteOptions {
  readonly signal?: AbortSignal;
  /** Set false to keep a command out of the undo history even though it defines an inverse. */
  readonly record?: boolean;
}

type HistoryMode = "normal" | "undo" | "redo";

/**
 * The single path through which UI actions reach application logic.
 *
 * Routing everything through one bus is what makes cross-cutting behaviour possible without
 * touching feature code: permissions, telemetry, undo history and audit are all implemented once,
 * here, rather than being re-remembered at every button handler.
 *
 * `execute` returns a `Result` and never throws — a plugin's handler blowing up is an ordinary,
 * reportable outcome, not something that should unwind the caller.
 */
export class CommandBus {
  readonly #commands = new Map<string, CommandDefinition<never, never>>();
  readonly #middlewares: CommandMiddleware[] = [];
  readonly #undoStack: CommandInvocation[] = [];
  readonly #redoStack: CommandInvocation[] = [];
  readonly #permissions: PermissionService | undefined;
  readonly #telemetry: TelemetrySink;
  readonly #historyLimit: number;
  readonly #now: () => number;
  #mode: HistoryMode = "normal";
  #depth = 0;

  constructor(options: CommandBusOptions = {}) {
    this.#permissions = options.permissions;
    this.#telemetry = options.telemetry ?? NOOP_TELEMETRY;
    this.#historyLimit = Math.max(0, options.historyLimit ?? 100);
    this.#now = options.now ?? (() => Date.now());
  }

  register<P, R>(definition: CommandDefinition<P, R>): Disposable {
    if (this.#commands.has(definition.id)) {
      throw new KernelError("COMMAND_DUPLICATE", `Command "${definition.id}" is already registered.`, {
        commandId: definition.id,
      });
    }
    this.#commands.set(definition.id, definition as unknown as CommandDefinition<never, never>);
    return toDisposable(() => {
      this.#commands.delete(definition.id);
      // History entries naming a command that no longer exists would fail on undo with a confusing
      // "not found". Dropping them when the plugin unregisters keeps the stacks honest.
      this.#purgeHistory(definition.id);
    });
  }

  use(middleware: CommandMiddleware): Disposable {
    this.#middlewares.push(middleware);
    return toDisposable(() => {
      const index = this.#middlewares.indexOf(middleware);
      if (index >= 0) this.#middlewares.splice(index, 1);
    });
  }

  has(commandId: string): boolean {
    return this.#commands.has(commandId);
  }

  list(): CommandInfo[] {
    return [...this.#commands.values()].map((definition) => ({
      id: definition.id,
      title: definition.title,
      description: definition.description,
      permission: definition.permission,
      undoable: typeof definition.createInverse === "function",
    }));
  }

  async execute<R = unknown, P = unknown>(
    commandId: string,
    params: P,
    options: ExecuteOptions = {},
  ): Promise<Result<R>> {
    const definition = this.#commands.get(commandId) as CommandDefinition<P, R> | undefined;
    if (!definition) {
      const error = new KernelError("COMMAND_NOT_FOUND", `No command registered as "${commandId}".`, {
        commandId,
      });
      this.#telemetry.error(error);
      return err(error);
    }

    const invocation: CommandInvocation<P> = { commandId, params };
    const started = this.#now();
    this.#depth++;
    const depth = this.#depth - 1;

    try {
      const core = async (): Promise<Result<unknown>> => {
        if (definition.permission && this.#permissions) {
          const allowed = await this.#permissions.require({ action: definition.permission });
          if (!allowed.ok) return allowed;
        }
        const context: CommandExecutionContext = {
          commandId,
          identity: this.#permissions?.identity ?? { id: "anonymous", roles: [] },
          signal: options.signal,
          depth,
        };
        const outcome = await attemptAsync(
          () => definition.handler(params, context),
          "COMMAND_FAILED",
          `Command "${commandId}" failed.`,
        );
        if (outcome.ok) {
          this.#recordHistory(definition, params, outcome.value as R, depth, options.record ?? true);
        }
        return outcome;
      };

      // Middleware is third-party too, so the whole composed chain is guarded rather than just the
      // handler — a middleware that throws is a failed command, not a failed application.
      const chained = await attemptAsync(
        () => this.#compose(invocation, core)(),
        "COMMAND_FAILED",
        `Command middleware for "${commandId}" failed.`,
      );
      const result = (chained.ok ? chained.value : chained) as Result<R>;

      this.#telemetry.timing("command.duration", this.#now() - started, { commandId });
      this.#telemetry.counter(result.ok ? "command.ok" : "command.error", 1, { commandId });
      if (!result.ok) this.#telemetry.error(result.error, { commandId });
      return result;
    } finally {
      this.#depth--;
    }
  }

  get canUndo(): boolean {
    return this.#undoStack.length > 0;
  }

  get canRedo(): boolean {
    return this.#redoStack.length > 0;
  }

  /** Depth of the undo and redo stacks — surfaced for diagnostics and UI affordances. */
  get historySize(): { undo: number; redo: number } {
    return { undo: this.#undoStack.length, redo: this.#redoStack.length };
  }

  async undo(): Promise<Result<unknown>> {
    return this.#replay(this.#undoStack, "undo");
  }

  async redo(): Promise<Result<unknown>> {
    return this.#replay(this.#redoStack, "redo");
  }

  clearHistory(): void {
    this.#undoStack.length = 0;
    this.#redoStack.length = 0;
  }

  async #replay(stack: CommandInvocation[], mode: HistoryMode): Promise<Result<unknown>> {
    const entry = stack.pop();
    if (!entry) {
      return err(
        new KernelError("COMMAND_NOT_FOUND", `Nothing to ${mode}.`, { mode }),
      );
    }
    this.#mode = mode;
    try {
      const result = await this.execute(entry.commandId, entry.params);
      // Put it back if the reversal did not take, otherwise the action is stranded: neither applied
      // nor undoable.
      if (!result.ok) stack.push(entry);
      return result;
    } finally {
      this.#mode = "normal";
    }
  }

  #recordHistory<P, R>(
    definition: CommandDefinition<P, R>,
    params: P,
    result: R,
    depth: number,
    record: boolean,
  ): void {
    // Only top-level commands enter the history. A composite command that internally executes
    // sub-commands must be undone as one step, so its children are deliberately not recorded —
    // otherwise a single user action would need several undos to reverse.
    if (!record || depth !== 0 || !definition.createInverse) return;

    let inverse: CommandInvocation | undefined;
    try {
      inverse = definition.createInverse(params, result);
    } catch (thrown) {
      this.#telemetry.error(
        new KernelError("COMMAND_FAILED", `createInverse for "${definition.id}" threw.`, {
          commandId: definition.id,
        }, { cause: thrown }),
      );
      return;
    }
    if (!inverse) return;

    if (this.#mode === "undo") {
      this.#push(this.#redoStack, inverse);
    } else if (this.#mode === "redo") {
      this.#push(this.#undoStack, inverse);
    } else {
      this.#push(this.#undoStack, inverse);
      // A fresh action invalidates the redo branch — replaying it would apply an inverse computed
      // against a state that no longer exists.
      this.#redoStack.length = 0;
    }
  }

  #push(stack: CommandInvocation[], invocation: CommandInvocation): void {
    if (this.#historyLimit === 0) return;
    stack.push(invocation);
    while (stack.length > this.#historyLimit) stack.shift();
  }

  #purgeHistory(commandId: string): void {
    for (const stack of [this.#undoStack, this.#redoStack]) {
      for (let i = stack.length - 1; i >= 0; i--) {
        if (stack[i]?.commandId === commandId) stack.splice(i, 1);
      }
    }
  }

  #compose(
    invocation: CommandInvocation,
    core: () => Promise<Result<unknown>>,
  ): () => Promise<Result<unknown>> {
    let next = core;
    for (let i = this.#middlewares.length - 1; i >= 0; i--) {
      const middleware = this.#middlewares[i];
      if (!middleware) continue;
      const downstream = next;
      next = () => middleware(invocation, downstream);
    }
    return next;
  }
}

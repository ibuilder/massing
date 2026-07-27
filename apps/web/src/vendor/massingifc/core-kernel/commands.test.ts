import { describe, expect, it, vi } from "vitest";
import { CommandBus } from "./commands.js";
import { createRoleEvaluator, PermissionService } from "./permissions.js";
import { InMemoryTelemetrySink } from "./telemetry.js";

describe("CommandBus", () => {
  it("executes a handler and returns its value", async () => {
    const bus = new CommandBus();
    bus.register<{ a: number; b: number }, number>({
      id: "math.add",
      handler: ({ a, b }) => a + b,
    });

    const result = await bus.execute<number>("math.add", { a: 2, b: 3 });

    expect(result).toEqual({ ok: true, value: 5 });
  });

  it("reports an unknown command instead of throwing", async () => {
    const bus = new CommandBus();
    const result = await bus.execute("nope", {});

    expect(result.ok).toBe(false);
    if (!result.ok) expect(result.error.code).toBe("COMMAND_NOT_FOUND");
  });

  it("converts a throwing handler into an error result", async () => {
    const bus = new CommandBus();
    bus.register({
      id: "bad",
      handler: () => {
        throw new Error("handler exploded");
      },
    });

    const result = await bus.execute("bad", undefined);

    expect(result.ok).toBe(false);
    if (!result.ok) {
      expect(result.error.code).toBe("COMMAND_FAILED");
      expect(result.error.message).toBe("handler exploded");
    }
  });

  it("converts a rejected promise into an error result", async () => {
    const bus = new CommandBus();
    bus.register({ id: "async-bad", handler: async () => Promise.reject(new Error("async boom")) });

    const result = await bus.execute("async-bad", undefined);
    expect(result.ok).toBe(false);
  });

  it("rejects a duplicate command id", () => {
    const bus = new CommandBus();
    bus.register({ id: "dup", handler: () => undefined });
    expect(() => bus.register({ id: "dup", handler: () => undefined })).toThrowError();
  });

  describe("permissions", () => {
    it("blocks a command whose permission is not granted", async () => {
      const permissions = new PermissionService();
      permissions.setEvaluator(createRoleEvaluator({ "massing.edit": ["author"] }));
      permissions.setIdentity({ id: "u1", roles: ["viewer"] });
      const bus = new CommandBus({ permissions });

      const handler = vi.fn();
      bus.register({ id: "massing.create", permission: "massing.edit", handler });

      const result = await bus.execute("massing.create", {});

      expect(handler).not.toHaveBeenCalled();
      expect(result.ok).toBe(false);
      if (!result.ok) expect(result.error.code).toBe("PERMISSION_DENIED");
    });

    it("allows the command once the identity holds the role", async () => {
      const permissions = new PermissionService();
      permissions.setEvaluator(createRoleEvaluator({ "massing.edit": ["author"] }));
      permissions.setIdentity({ id: "u1", roles: ["author"] });
      const bus = new CommandBus({ permissions });
      bus.register({ id: "massing.create", permission: "massing.edit", handler: () => "made" });

      expect(await bus.execute("massing.create", {})).toEqual({ ok: true, value: "made" });
    });
  });

  describe("middleware", () => {
    it("wraps execution in registration order", async () => {
      const bus = new CommandBus();
      const order: string[] = [];
      bus.use(async (_i, next) => {
        order.push("outer:before");
        const r = await next();
        order.push("outer:after");
        return r;
      });
      bus.use(async (_i, next) => {
        order.push("inner:before");
        return next();
      });
      bus.register({ id: "x", handler: () => void order.push("handler") });

      await bus.execute("x", undefined);

      expect(order).toEqual(["outer:before", "inner:before", "handler", "outer:after"]);
    });

    it("treats a throwing middleware as a failed command, not a failed app", async () => {
      const bus = new CommandBus();
      bus.use(() => {
        throw new Error("middleware broke");
      });
      bus.register({ id: "x", handler: () => 1 });

      const result = await bus.execute("x", undefined);
      expect(result.ok).toBe(false);
    });

    it("lets middleware short-circuit a command", async () => {
      const bus = new CommandBus();
      const handler = vi.fn();
      bus.use(async () => ({ ok: false, error: new Error("blocked") as never }));
      bus.register({ id: "x", handler });

      const result = await bus.execute("x", undefined);

      expect(handler).not.toHaveBeenCalled();
      expect(result.ok).toBe(false);
    });
  });

  describe("undo history", () => {
    /** A tiny store whose set/undo pair is expressed as two invocations of the same command. */
    const makeBus = () => {
      const bus = new CommandBus();
      const store = { value: 0 };
      bus.register<{ to: number; from?: number }, number>({
        id: "set",
        handler: ({ to }) => {
          const previous = store.value;
          store.value = to;
          return previous;
        },
        createInverse: (params, previous) => ({ commandId: "set", params: { to: previous } }),
      });
      return { bus, store };
    };

    it("undoes and redoes a recorded command", async () => {
      const { bus, store } = makeBus();
      await bus.execute("set", { to: 42 });
      expect(store.value).toBe(42);
      expect(bus.canUndo).toBe(true);

      await bus.undo();
      expect(store.value).toBe(0);
      expect(bus.canRedo).toBe(true);

      await bus.redo();
      expect(store.value).toBe(42);
    });

    it("does not record commands with no inverse", async () => {
      const bus = new CommandBus();
      bus.register({ id: "read-only", handler: () => 1 });
      await bus.execute("read-only", undefined);

      expect(bus.canUndo).toBe(false);
    });

    it("records a composite as one step, not one per child", async () => {
      const { bus, store } = makeBus();
      bus.register<void, void>({
        id: "set-twice",
        handler: async () => {
          await bus.execute("set", { to: 1 });
          await bus.execute("set", { to: 2 });
        },
        createInverse: () => ({ commandId: "set", params: { to: 0 } }),
      });

      await bus.execute("set-twice", undefined);
      expect(store.value).toBe(2);
      // One user action must cost one undo — nested executions are deliberately not recorded.
      expect(bus.historySize.undo).toBe(1);

      await bus.undo();
      expect(store.value).toBe(0);
    });

    it("clears the redo branch when a new action is performed", async () => {
      const { bus } = makeBus();
      await bus.execute("set", { to: 1 });
      await bus.undo();
      expect(bus.canRedo).toBe(true);

      await bus.execute("set", { to: 5 });
      expect(bus.canRedo).toBe(false);
    });

    it("keeps the entry when a reversal fails, so the action is not stranded", async () => {
      const bus = new CommandBus();
      let failNext = false;
      bus.register<{ to: number }, number>({
        id: "set",
        handler: ({ to }) => {
          if (failNext) throw new Error("cannot reverse");
          return to;
        },
        createInverse: () => ({ commandId: "set", params: { to: 0 } }),
      });
      await bus.execute("set", { to: 1 });

      failNext = true;
      const result = await bus.undo();

      expect(result.ok).toBe(false);
      expect(bus.canUndo).toBe(true);
    });

    it("drops history entries for a command that unregisters", async () => {
      const { bus } = makeBus();
      const registration = bus.register<{ to: number }, number>({
        id: "temp",
        handler: ({ to }) => to,
        createInverse: () => ({ commandId: "temp", params: { to: 0 } }),
      });
      await bus.execute("temp", { to: 3 });
      expect(bus.canUndo).toBe(true);

      registration.dispose();
      expect(bus.canUndo).toBe(false);
    });

    it("honours the history limit", async () => {
      const bus = new CommandBus({ historyLimit: 2 });
      bus.register<{ to: number }, number>({
        id: "set",
        handler: ({ to }) => to,
        createInverse: () => ({ commandId: "set", params: { to: 0 } }),
      });
      for (const to of [1, 2, 3, 4]) await bus.execute("set", { to });

      expect(bus.historySize.undo).toBe(2);
    });
  });

  it("records timing and outcome telemetry", async () => {
    const telemetry = new InMemoryTelemetrySink();
    const bus = new CommandBus({ telemetry });
    bus.register({ id: "x", handler: () => 1 });

    await bus.execute("x", undefined);

    expect(telemetry.records.some((r) => r.kind === "timing" && r.name === "command.duration")).toBe(true);
    expect(telemetry.records.some((r) => r.name === "command.ok")).toBe(true);
  });

  it("lists registered commands with their undoable flag", () => {
    const bus = new CommandBus();
    bus.register({ id: "a", title: "A", handler: () => undefined });
    bus.register({
      id: "b",
      handler: () => undefined,
      createInverse: () => ({ commandId: "a", params: undefined }),
    });

    const list = bus.list();
    expect(list.find((c) => c.id === "a")?.undoable).toBe(false);
    expect(list.find((c) => c.id === "b")?.undoable).toBe(true);
  });
});

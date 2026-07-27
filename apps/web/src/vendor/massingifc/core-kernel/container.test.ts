import { describe, expect, it } from "vitest";
import { createServiceToken, ServiceContainer } from "./container.js";
import type { Disposable } from "./disposable.js";
import { KernelError } from "./errors.js";

interface Counter {
  value: number;
}

const CounterToken = createServiceToken<Counter>("counter");
const OtherToken = createServiceToken<Counter>("other");

describe("ServiceContainer", () => {
  it("builds a singleton once and reuses it", () => {
    const container = new ServiceContainer();
    let built = 0;
    container.register(CounterToken, () => {
      built++;
      return { value: built };
    });

    expect(container.resolve(CounterToken)).toBe(container.resolve(CounterToken));
    expect(built).toBe(1);
  });

  it("rebuilds a transient on every resolve", () => {
    const container = new ServiceContainer();
    let built = 0;
    container.register(CounterToken, () => ({ value: ++built }), { lifetime: "transient" });

    expect(container.resolve(CounterToken).value).toBe(1);
    expect(container.resolve(CounterToken).value).toBe(2);
  });

  it("rejects a duplicate registration in the same scope", () => {
    const container = new ServiceContainer();
    container.register(CounterToken, () => ({ value: 1 }));
    expect(() => container.register(CounterToken, () => ({ value: 2 }))).toThrowError(KernelError);
  });

  it("tokens are nominal, so same-named tokens do not collide", () => {
    const container = new ServiceContainer();
    const a = createServiceToken<Counter>("dup");
    const b = createServiceToken<Counter>("dup");
    container.register(a, () => ({ value: 1 }));
    container.register(b, () => ({ value: 2 }));

    expect(container.resolve(a).value).toBe(1);
    expect(container.resolve(b).value).toBe(2);
  });

  describe("scopes", () => {
    it("resolves through to the parent", () => {
      const root = new ServiceContainer("root");
      root.register(CounterToken, () => ({ value: 7 }));
      const scope = root.createScope("plugin:a");

      expect(scope.resolve(CounterToken).value).toBe(7);
    });

    it("keeps a parent singleton shared across sibling scopes", () => {
      const root = new ServiceContainer("root");
      root.register(CounterToken, () => ({ value: 1 }));

      const a = root.createScope("a").resolve(CounterToken);
      const b = root.createScope("b").resolve(CounterToken);

      // The instance is cached on the container that OWNS the registration, not on the resolver —
      // otherwise every plugin would silently get its own copy of a kernel service.
      expect(a).toBe(b);
    });

    it("lets a scope shadow the parent without mutating it", () => {
      const root = new ServiceContainer("root");
      root.register(CounterToken, () => ({ value: 1 }));
      const scope = root.createScope("plugin");
      scope.register(CounterToken, () => ({ value: 99 }));

      expect(scope.resolve(CounterToken).value).toBe(99);
      expect(root.resolve(CounterToken).value).toBe(1);
    });

    it("disposes child scopes when the parent goes", () => {
      const root = new ServiceContainer("root");
      const scope = root.createScope("child");
      root.dispose();

      expect(scope.disposed).toBe(true);
    });
  });

  describe("failure handling", () => {
    it("reports the cycle when a factory depends on itself", () => {
      const container = new ServiceContainer();
      container.register(CounterToken, (c) => c.resolve(OtherToken));
      container.register(OtherToken, (c) => c.resolve(CounterToken));

      try {
        container.resolve(CounterToken);
        expect.unreachable("expected a circular dependency error");
      } catch (thrown) {
        expect(thrown).toBeInstanceOf(KernelError);
        expect((thrown as KernelError).code).toBe("SERVICE_CIRCULAR");
        expect(String((thrown as KernelError).details["cycle"])).toContain("counter");
      }
    });

    it("does not leave the resolution stack dirty after a failed build", () => {
      const container = new ServiceContainer();
      container.register(CounterToken, () => {
        throw new Error("boom");
      });

      expect(() => container.resolve(CounterToken)).toThrowError("boom");
      // A leaked stack entry would make the *next*, unrelated resolve look circular.
      expect(() => container.resolve(CounterToken)).toThrowError("boom");
    });

    it("reports a missing service rather than returning undefined", () => {
      const container = new ServiceContainer();
      const result = container.tryResolve(CounterToken);

      expect(result.ok).toBe(false);
      if (!result.ok) expect(result.error.code).toBe("SERVICE_NOT_FOUND");
    });

    it("refuses to register into a disposed container", () => {
      const container = new ServiceContainer();
      container.dispose();
      expect(() => container.register(CounterToken, () => ({ value: 1 }))).toThrowError(KernelError);
    });
  });

  describe("ownership", () => {
    it("disposes singletons it constructed", () => {
      const container = new ServiceContainer();
      let disposed = false;
      const token = createServiceToken<Disposable>("closeable");
      container.register(token, () => ({ dispose: () => void (disposed = true) }));
      container.resolve(token);

      container.dispose();
      expect(disposed).toBe(true);
    });

    it("does not dispose values it was merely handed", () => {
      const container = new ServiceContainer();
      let disposed = false;
      const token = createServiceToken<Disposable>("external");
      container.registerValue(token, { dispose: () => void (disposed = true) });
      container.resolve(token);

      container.dispose();
      expect(disposed).toBe(false);
    });

    it("survives a service that throws on teardown", () => {
      const container = new ServiceContainer();
      const bad = createServiceToken<Disposable>("bad");
      const good = createServiceToken<Disposable>("good");
      let goodDisposed = false;

      container.register(bad, () => ({
        dispose: () => {
          throw new Error("teardown failed");
        },
      }));
      container.register(good, () => ({ dispose: () => void (goodDisposed = true) }));
      container.resolve(bad);
      container.resolve(good);

      expect(() => container.dispose()).not.toThrow();
      expect(goodDisposed).toBe(true);
    });
  });
});

import { describe, expect, it, vi } from "vitest";
import { createCapabilityToken } from "./capabilities.js";
import { createKernel, KERNEL_API_VERSION, type Kernel } from "./kernel.js";
import type { Plugin, PluginContext, PluginManifest } from "./plugin-host.js";
import { InMemoryTelemetrySink } from "./telemetry.js";

const manifest = (id: string, overrides: Partial<PluginManifest> = {}): PluginManifest => ({
  id,
  version: "1.0.0",
  apiVersion: `^${KERNEL_API_VERSION}`,
  ...overrides,
});

const plugin = (
  id: string,
  activate: (context: PluginContext) => void | Promise<void> = () => {},
  overrides: Partial<PluginManifest> = {},
  deactivate?: () => void | Promise<void>,
): Plugin => ({
  manifest: manifest(id, overrides),
  activate,
  ...(deactivate ? { deactivate } : {}),
});

describe("PluginHost", () => {
  it("activates a registered plugin", async () => {
    const kernel = createKernel();
    const activate = vi.fn();
    kernel.use(plugin("a", activate));

    const report = await kernel.start();

    expect(report.activated).toEqual(["a"]);
    expect(activate).toHaveBeenCalledOnce();
    expect(kernel.plugins.isActive("a")).toBe(true);
  });

  it("rejects a duplicate plugin id", () => {
    const kernel = createKernel();
    kernel.use(plugin("a"));

    const result = kernel.use(plugin("a"));
    expect(result.ok).toBe(false);
    if (!result.ok) expect(result.error.code).toBe("PLUGIN_DUPLICATE");
  });

  it("refuses a plugin built for an incompatible kernel API", () => {
    const kernel = createKernel();
    const result = kernel.use(plugin("old", () => {}, { apiVersion: "^0.5.0" }));

    // Caught at registration, not at some arbitrary call site later.
    expect(result.ok).toBe(false);
    if (!result.ok) expect(result.error.code).toBe("PLUGIN_API_INCOMPATIBLE");
  });

  describe("crash isolation", () => {
    it("survives a plugin that throws during activation", async () => {
      const kernel = createKernel();
      const healthy = vi.fn();
      kernel.use(
        plugin("bad", () => {
          throw new Error("plugin exploded");
        }),
      );
      kernel.use(plugin("good", healthy));

      const report = await kernel.start();

      expect(report.failed.map((f) => f.id)).toEqual(["bad"]);
      expect(report.activated).toEqual(["good"]);
      expect(healthy).toHaveBeenCalledOnce();
      expect(kernel.plugins.status("bad")).toBe("quarantined");
    });

    it("survives a plugin whose activation rejects", async () => {
      const kernel = createKernel();
      kernel.use(plugin("bad", async () => Promise.reject(new Error("async failure"))));

      const report = await kernel.start();
      expect(report.failed).toHaveLength(1);
    });

    it("rolls back everything a failing plugin registered before it threw", async () => {
      const kernel = createKernel();
      kernel.use(
        plugin("bad", (context) => {
          context.commands.register({ id: "bad.command", handler: () => 1 });
          context.ui.register({ id: "bad.panel", point: "panel" });
          throw new Error("failed after registering");
        }),
      );

      await kernel.start();

      // A half-activated plugin is worse than an absent one: live commands, broken invariants.
      expect(kernel.commands.has("bad.command")).toBe(false);
      expect(kernel.ui.byPoint("panel")).toHaveLength(0);
    });

    it("does not retry a quarantined plugin on the next start", async () => {
      const kernel = createKernel();
      const activate = vi.fn(() => {
        throw new Error("always fails");
      });
      kernel.use(plugin("bad", activate));

      await kernel.start();
      await kernel.start();

      expect(activate).toHaveBeenCalledOnce();
    });

    it("becomes eligible again after reset", async () => {
      const kernel = createKernel();
      let shouldFail = true;
      kernel.use(
        plugin("flaky", () => {
          if (shouldFail) throw new Error("first attempt fails");
        }),
      );

      await kernel.start();
      expect(kernel.plugins.status("flaky")).toBe("quarantined");

      shouldFail = false;
      kernel.plugins.reset("flaky");
      await kernel.start();

      expect(kernel.plugins.isActive("flaky")).toBe(true);
    });

    it("records the failure in telemetry", async () => {
      const telemetry = new InMemoryTelemetrySink();
      const kernel = createKernel({ telemetry });
      kernel.use(
        plugin("bad", () => {
          throw new Error("boom");
        }),
      );

      await kernel.start();

      expect(telemetry.records.some((r) => r.kind === "error")).toBe(true);
    });
  });

  describe("teardown", () => {
    const withRegistrations = (kernel: Kernel) =>
      kernel.use(
        plugin("p", (context) => {
          context.commands.register({ id: "p.do", handler: () => 1 });
          context.ui.register({ id: "p.panel", point: "panel" });
          context.events.on("something", () => {});
          context.state.defineSlice("data", { n: 1 });
        }),
      );

    it("releases every registration the plugin made", async () => {
      const kernel = createKernel();
      withRegistrations(kernel);
      await kernel.start();

      expect(kernel.commands.has("p.do")).toBe(true);
      await kernel.plugins.deactivate("p");

      expect(kernel.commands.has("p.do")).toBe(false);
      expect(kernel.ui.byPoint("panel")).toHaveLength(0);
      expect(kernel.events.listenerCount("something")).toBe(0);
      expect(kernel.state.hasSlice("p/data")).toBe(false);
    });

    it("namespaces plugin state under the plugin id", async () => {
      const kernel = createKernel();
      withRegistrations(kernel);
      await kernel.start();

      expect(kernel.state.hasSlice("p/data")).toBe(true);
    });

    it("completes teardown even when the plugin's deactivate throws", async () => {
      const kernel = createKernel();
      kernel.use(
        plugin(
          "p",
          (context) => void context.commands.register({ id: "p.do", handler: () => 1 }),
          {},
          () => {
            throw new Error("teardown failed");
          },
        ),
      );
      await kernel.start();

      const result = await kernel.plugins.deactivate("p");

      expect(result.ok).toBe(false);
      // The failure is reported, but the plugin must not be able to make itself unloadable.
      expect(kernel.commands.has("p.do")).toBe(false);
      expect(kernel.plugins.status("p")).toBe("inactive");
    });

    it("isolates each plugin's stored data", async () => {
      const kernel = createKernel();
      const seen: unknown[] = [];
      kernel.use(
        plugin("a", async (context) => {
          await context.storage.save("settings", "settings", { from: "a" });
        }),
      );
      kernel.use(
        plugin("b", async (context) => {
          await context.storage.save("settings", "settings", { from: "b" });
          const loaded = await context.storage.load<{ from: string }>("settings");
          if (loaded.ok) seen.push(loaded.value?.data);
        }),
      );

      await kernel.start();
      expect(seen).toEqual([{ from: "b" }]);
    });
  });

  describe("dependencies", () => {
    it("activates dependencies before dependents", async () => {
      const kernel = createKernel();
      const order: string[] = [];
      kernel.use(plugin("consumer", () => void order.push("consumer"), {
        dependencies: [{ id: "provider" }],
      }));
      kernel.use(plugin("provider", () => void order.push("provider")));

      await kernel.start();

      // Registration order is deliberately the reverse of dependency order here.
      expect(order).toEqual(["provider", "consumer"]);
    });

    it("skips a dependent when its dependency fails", async () => {
      const kernel = createKernel();
      const consumer = vi.fn();
      kernel.use(
        plugin("provider", () => {
          throw new Error("provider failed");
        }),
      );
      kernel.use(plugin("consumer", consumer, { dependencies: [{ id: "provider" }] }));

      const report = await kernel.start();

      expect(consumer).not.toHaveBeenCalled();
      expect(report.skipped.map((s) => s.id)).toEqual(["consumer"]);
    });

    it("reports a missing required dependency", async () => {
      const kernel = createKernel();
      kernel.use(plugin("consumer", () => {}, { dependencies: [{ id: "absent" }] }));

      const result = await kernel.plugins.activate("consumer");

      expect(result.ok).toBe(false);
      if (!result.ok) expect(result.error.code).toBe("PLUGIN_DEPENDENCY_MISSING");
    });

    it("tolerates a missing optional dependency", async () => {
      const kernel = createKernel();
      kernel.use(plugin("consumer", () => {}, {
        dependencies: [{ id: "absent", optional: true }],
      }));

      expect((await kernel.plugins.activate("consumer")).ok).toBe(true);
    });

    it("enforces a dependency version range", async () => {
      const kernel = createKernel();
      kernel.use(plugin("provider", () => {}, { version: "1.0.0" }));
      kernel.use(plugin("consumer", () => {}, { dependencies: [{ id: "provider", version: "^2.0.0" }] }));

      const report = await kernel.start();
      expect(report.failed.map((f) => f.id)).toContain("consumer");
    });

    it("detects a dependency cycle and names it", async () => {
      const kernel = createKernel();
      kernel.use(plugin("a", () => {}, { dependencies: [{ id: "b" }] }));
      kernel.use(plugin("b", () => {}, { dependencies: [{ id: "a" }] }));

      const report = await kernel.start();

      expect(report.failed[0]?.error.code).toBe("PLUGIN_DEPENDENCY_CYCLE");
      expect(String(report.failed[0]?.error.details["cycle"])).toContain("a -> b");
    });

    it("refuses to deactivate a plugin that others still depend on", async () => {
      const kernel = createKernel();
      kernel.use(plugin("provider"));
      kernel.use(plugin("consumer", () => {}, { dependencies: [{ id: "provider" }] }));
      await kernel.start();

      const result = await kernel.plugins.deactivate("provider");

      expect(result.ok).toBe(false);
      expect(kernel.plugins.isActive("provider")).toBe(true);
    });

    it("deactivates dependents before dependencies", async () => {
      const kernel = createKernel();
      const order: string[] = [];
      kernel.use(plugin("provider", () => {}, {}, () => void order.push("provider")));
      kernel.use(
        plugin("consumer", () => {}, { dependencies: [{ id: "provider" }] }, () =>
          void order.push("consumer"),
        ),
      );
      await kernel.start();

      await kernel.stop();

      expect(order).toEqual(["consumer", "provider"]);
    });
  });

  describe("capabilities", () => {
    interface Estimator {
      rate(code: string): number;
    }
    const EstimatorToken = createCapabilityToken<Estimator>("estimating.rates");

    it("lets one plugin consume another's capability", async () => {
      const kernel = createKernel();
      kernel.use(
        plugin("rates", (context) => {
          context.capabilities.provide(EstimatorToken, { rate: () => 42 }, { version: "1.2.0" });
        }),
      );

      let observed = 0;
      kernel.use(
        plugin(
          "boq",
          (context) => {
            const estimator = context.capabilities.require(EstimatorToken, { version: "^1.0.0" });
            if (estimator.ok) observed = estimator.value.rate("C10");
          },
          { dependencies: [{ id: "rates" }] },
        ),
      );

      await kernel.start();
      expect(observed).toBe(42);
    });

    it("withdraws a capability when its provider deactivates", async () => {
      const kernel = createKernel();
      kernel.use(
        plugin("rates", (context) =>
          void context.capabilities.provide(EstimatorToken, { rate: () => 1 }),
        ),
      );
      await kernel.start();
      expect(kernel.capabilities.has(EstimatorToken)).toBe(true);

      await kernel.plugins.deactivate("rates");
      expect(kernel.capabilities.has(EstimatorToken)).toBe(false);
    });

    it("reports a version mismatch distinctly from an absent capability", async () => {
      const kernel = createKernel();
      kernel.use(
        plugin("rates", (context) =>
          void context.capabilities.provide(EstimatorToken, { rate: () => 1 }, { version: "1.0.0" }),
        ),
      );
      await kernel.start();

      const result = kernel.capabilities.require(EstimatorToken, { version: "^2.0.0" });
      expect(result.ok).toBe(false);
      if (!result.ok) expect(result.error.code).toBe("CAPABILITY_VERSION_MISMATCH");
    });
  });

  it("exposes diagnostics for the whole kernel", async () => {
    const kernel = createKernel();
    kernel.use(
      plugin("p", (context) => {
        context.commands.register({ id: "p.do", handler: () => 1 });
        context.ui.register({ id: "p.panel", point: "panel" });
      }),
    );
    await kernel.start();

    const diagnostics = kernel.diagnostics();

    expect(diagnostics.apiVersion).toBe(KERNEL_API_VERSION);
    expect(diagnostics.plugins).toHaveLength(1);
    expect(diagnostics.commands).toBe(1);
    expect(diagnostics.uiPoints).toEqual(["panel"]);
  });
});

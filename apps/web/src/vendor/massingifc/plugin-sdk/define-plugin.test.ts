import { createCapabilityToken, KERNEL_API_VERSION } from "@massingifc/core-kernel";
import { SCHEMA } from "@massingifc/project-schema";
import { describe, expect, it } from "vitest";
import { definePlugin } from "./define-plugin.js";
import { createTestHarness } from "./testing.js";

interface MassingLike {
  create(name: string): { id: string; name: string };
}
const MassingToken = createCapabilityToken<MassingLike>("massing.service");

describe("definePlugin", () => {
  it("defaults apiVersion to caret-compatibility with the kernel", () => {
    const plugin = definePlugin({ id: "p", version: "1.0.0", activate: () => {} });

    expect(plugin.manifest.apiVersion).toBe(`^${KERNEL_API_VERSION}`);
  });

  it("keeps an explicit apiVersion", () => {
    const plugin = definePlugin({
      id: "p",
      version: "1.0.0",
      apiVersion: "^1.2.0",
      activate: () => {},
    });

    expect(plugin.manifest.apiVersion).toBe("^1.2.0");
  });

  it("omits absent optional manifest fields rather than setting them undefined", () => {
    const plugin = definePlugin({ id: "p", version: "1.0.0", activate: () => {} });

    expect("name" in plugin.manifest).toBe(false);
    expect("dependencies" in plugin.manifest).toBe(false);
    expect(plugin.deactivate).toBeUndefined();
  });
});

describe("end-to-end plugin lifecycle", () => {
  /** A minimal capability plugin, written the way a real one would be. */
  const massingPlugin = definePlugin({
    id: "massing",
    version: "0.1.0",
    name: "Massing",
    permissions: ["massing.edit"],
    activate(context) {
      const slice = context.state.defineSlice<{ objects: { id: string; name: string }[] }>(
        "objects",
        { objects: [] },
      );

      const service: MassingLike = {
        create(name) {
          const record = { id: `m${slice.get().objects.length + 1}`, name };
          slice.update((s) => ({ objects: [...s.objects, record] }));
          return record;
        },
      };

      context.capabilities.provide(MassingToken, service, { version: "0.1.0" });

      context.commands.register<{ name: string }, { id: string }>({
        id: "massing.create",
        title: "Create mass",
        permission: "massing.edit",
        handler: ({ name }) => service.create(name),
        createInverse: (_params, created) => ({
          commandId: "massing.remove",
          params: { id: created.id },
        }),
      });

      context.commands.register<{ id: string }, void>({
        id: "massing.remove",
        handler: ({ id }) => {
          slice.update((s) => ({ objects: s.objects.filter((o) => o.id !== id) }));
        },
      });

      context.ui.register({
        id: "massing.panel",
        point: "panel",
        title: "Massing",
        placement: "left",
        commandId: "massing.create",
      });
    },
  });

  it("registers commands, capabilities, state and UI through one activation", async () => {
    const harness = createTestHarness();
    const loaded = await harness.load(massingPlugin);

    expect(loaded.ok).toBe(true);
    expect(harness.kernel.commands.has("massing.create")).toBe(true);
    expect(harness.kernel.capabilities.has(MassingToken)).toBe(true);
    expect(harness.kernel.state.hasSlice("massing/objects")).toBe(true);
    expect(harness.kernel.ui.byPoint("panel").map((c) => c.pluginId)).toEqual(["massing"]);

    await harness.dispose();
  });

  it("executes the plugin's command and supports undo", async () => {
    const harness = createTestHarness();
    await harness.load(massingPlugin);

    const created = await harness.kernel.commands.execute<{ id: string }>("massing.create", {
      name: "Tower A",
    });
    expect(created.ok).toBe(true);

    const slice = harness.kernel.state.getSlice<{ objects: unknown[] }>("massing/objects");
    expect(slice?.get().objects).toHaveLength(1);

    await harness.kernel.commands.undo();
    expect(slice?.get().objects).toHaveLength(0);

    await harness.dispose();
  });

  it("enforces the command's permission through the kernel", async () => {
    const harness = createTestHarness({
      identity: { id: "viewer", roles: ["viewer"] },
      permissionEvaluator: { evaluate: (identity) => identity.roles.includes("author") },
    });
    await harness.load(massingPlugin);

    const result = await harness.kernel.commands.execute("massing.create", { name: "Tower" });

    expect(result.ok).toBe(false);
    if (!result.ok) expect(result.error.code).toBe("PERMISSION_DENIED");

    await harness.dispose();
  });

  it("persists through the plugin's own namespace and migrates on load", async () => {
    const harness = createTestHarness();
    harness.migrator.declare("massing.settings", 2).register({
      schema: "massing.settings",
      from: 1,
      to: 2,
      migrate: (data) => ({ ...(data as object), unit: "m" }),
    });

    let loadedSettings: unknown;
    await harness.load(
      definePlugin({
        id: "settings-user",
        version: "1.0.0",
        async activate(context) {
          // Simulate data written by an older release.
          await harness.storage.put("settings-user:prefs", {
            schema: "massing.settings",
            version: 1,
            savedAt: "2025-01-01T00:00:00.000Z",
            data: { theme: "dark" },
          });
          const loaded = await context.storage.load("prefs");
          if (loaded.ok) loadedSettings = loaded.value?.data;
        },
      }),
    );

    expect(loadedSettings).toEqual({ theme: "dark", unit: "m" });

    await harness.dispose();
  });

  it("ships every platform schema declared, so version guards work from day one", () => {
    const harness = createTestHarness();

    expect(harness.migrator.latestVersion(SCHEMA.massingObject)).toBe(1);
    expect(harness.migrator.latestVersion(SCHEMA.markup)).toBe(1);
  });

  it("contains a failing plugin without disturbing a healthy one", async () => {
    const harness = createTestHarness();
    await harness.load(massingPlugin);

    const broken = await harness.load(
      definePlugin({
        id: "broken",
        version: "1.0.0",
        activate() {
          throw new Error("bad plugin");
        },
      }),
    );

    expect(broken.ok).toBe(false);
    // The healthy plugin is untouched — the whole point of the isolation contract.
    expect(harness.kernel.commands.has("massing.create")).toBe(true);
    expect(harness.kernel.plugins.status("broken")).toBe("quarantined");
    expect(harness.kernel.plugins.isActive("massing")).toBe(true);

    await harness.dispose();
  });
});

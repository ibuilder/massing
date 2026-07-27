import { describe, expect, it } from "vitest";
import {
  MemoryStorageAdapter,
  PersistenceEngine,
  type DocumentMigrator,
  type VersionedDocument,
} from "./persistence.js";
import { err, ok } from "./result.js";
import { KernelError } from "./errors.js";

/** Migrates `project` v1 -> v2 by renaming `title` to `name`. */
const migrator: DocumentMigrator = {
  latestVersion: (schema) => (schema === "project" ? 2 : undefined),
  migrate: (document) => {
    if (document.schema !== "project") return ok(document);
    if (document.version === 1) {
      const data = document.data as { title: string };
      return ok({ ...document, version: 2, data: { name: data.title } });
    }
    return err(
      new KernelError("MIGRATION_PATH_MISSING", `No path from v${document.version}.`, {}),
    );
  },
};

const engine = (options: { migrator?: DocumentMigrator; maxBackups?: number } = {}) => {
  const adapter = new MemoryStorageAdapter();
  let tick = 0;
  return {
    adapter,
    persistence: new PersistenceEngine({
      adapter,
      ...(options.migrator ? { migrator: options.migrator } : {}),
      ...(options.maxBackups === undefined ? {} : { maxBackups: options.maxBackups }),
      now: () => new Date(Date.UTC(2026, 0, 1, 0, 0, tick++)),
    }),
  };
};

describe("PersistenceEngine", () => {
  it("saves and loads a versioned document", async () => {
    const { persistence } = engine();
    await persistence.save("p1", "project", { name: "Tower" });

    const loaded = await persistence.load<{ name: string }>("p1");

    expect(loaded.ok).toBe(true);
    if (loaded.ok) {
      expect(loaded.value?.data).toEqual({ name: "Tower" });
      expect(loaded.value?.schema).toBe("project");
      expect(loaded.value?.savedAt).toBe("2026-01-01T00:00:00.000Z");
    }
  });

  it("treats a missing key as absent, not as an error", async () => {
    const { persistence } = engine();
    const loaded = await persistence.load("never-written");

    expect(loaded).toEqual({ ok: true, value: undefined });
  });

  it("rejects a stored value that is not a versioned document", async () => {
    const { adapter, persistence } = engine();
    await adapter.put("raw", { name: "no envelope" });

    const loaded = await persistence.load("raw");
    expect(loaded.ok).toBe(false);
    if (!loaded.ok) expect(loaded.error.code).toBe("MIGRATION_FAILED");
  });

  it("does not alias stored objects", async () => {
    const { persistence } = engine();
    const data = { name: "Tower" };
    await persistence.save("p1", "project", data);

    data.name = "mutated after save";
    const loaded = await persistence.load<{ name: string }>("p1");

    if (loaded.ok) expect(loaded.value?.data.name).toBe("Tower");
  });

  describe("migration", () => {
    it("stamps new saves with the migrator's latest version", async () => {
      const { persistence } = engine({ migrator });
      const saved = await persistence.save("p1", "project", { name: "Tower" });

      if (saved.ok) expect(saved.value.version).toBe(2);
    });

    it("upgrades an old document on load", async () => {
      const { adapter, persistence } = engine({ migrator });
      const legacy: VersionedDocument = {
        schema: "project",
        version: 1,
        savedAt: "2020-01-01T00:00:00.000Z",
        data: { title: "Old Tower" },
      };
      await adapter.put("p1", legacy);

      const loaded = await persistence.load<{ name: string }>("p1");

      expect(loaded.ok).toBe(true);
      if (loaded.ok) {
        expect(loaded.value?.version).toBe(2);
        expect(loaded.value?.data).toEqual({ name: "Old Tower" });
      }
    });

    it("leaves storage untouched when loading migrates", async () => {
      const { adapter, persistence } = engine({ migrator });
      await adapter.put("p1", {
        schema: "project",
        version: 1,
        savedAt: "2020-01-01T00:00:00.000Z",
        data: { title: "Old" },
      });

      await persistence.load("p1");

      // Reading a project must not rewrite it — opening a file to look at it is not an edit.
      const raw = (await adapter.get("p1")) as VersionedDocument;
      expect(raw.version).toBe(1);
    });

    it("writes the upgrade back only when asked, keeping a backup", async () => {
      const { adapter, persistence } = engine({ migrator });
      await adapter.put("p1", {
        schema: "project",
        version: 1,
        savedAt: "2020-01-01T00:00:00.000Z",
        data: { title: "Old" },
      });

      await persistence.migrateInPlace("p1");

      expect((await adapter.get("p1") as VersionedDocument).version).toBe(2);
      expect(await persistence.listBackups("p1")).toHaveLength(1);
    });

    it("refuses a document written by a newer release", async () => {
      const { adapter, persistence } = engine({ migrator });
      await adapter.put("p1", {
        schema: "project",
        version: 99,
        savedAt: "2030-01-01T00:00:00.000Z",
        data: {},
      });

      const loaded = await persistence.load("p1");

      // Guessing at a downgrade would silently discard fields this build knows nothing about.
      expect(loaded.ok).toBe(false);
      if (!loaded.ok) expect(loaded.error.code).toBe("SCHEMA_VERSION_UNSUPPORTED");
    });

    it("passes through schemas the migrator does not own", async () => {
      const { persistence } = engine({ migrator });
      await persistence.save("x", "unknown-schema", { a: 1 }, { version: 7 });

      const loaded = await persistence.load("x");
      if (loaded.ok) expect(loaded.value?.version).toBe(7);
    });

    it("surfaces a failing migration as an error", async () => {
      const { adapter, persistence } = engine({ migrator });
      await adapter.put("p1", { schema: "project", version: 0, savedAt: "", data: {} });

      const loaded = await persistence.load("p1");
      expect(loaded.ok).toBe(false);
    });
  });

  describe("backup and rollback", () => {
    it("restores a previous value", async () => {
      const { persistence } = engine();
      await persistence.save("p1", "project", { name: "v1" });
      const backup = await persistence.backup("p1");
      await persistence.save("p1", "project", { name: "v2" });

      expect(backup.ok && backup.value).toBeTruthy();
      if (backup.ok && backup.value) await persistence.rollback("p1", backup.value.id);

      const loaded = await persistence.load<{ name: string }>("p1");
      if (loaded.ok) expect(loaded.value?.data).toEqual({ name: "v1" });
    });

    it("makes a rollback itself reversible", async () => {
      const { persistence } = engine();
      await persistence.save("p1", "project", { name: "v1" });
      const first = await persistence.backup("p1");
      await persistence.save("p1", "project", { name: "v2" });

      if (first.ok && first.value) await persistence.rollback("p1", first.value.id);

      // The rollback snapshots what it replaced, so v2 is still recoverable.
      const backups = await persistence.listBackups("p1");
      expect(backups.length).toBeGreaterThanOrEqual(2);
    });

    it("reports an unknown backup id", async () => {
      const { persistence } = engine();
      await persistence.save("p1", "project", {});

      const result = await persistence.rollback("p1", "no-such-backup");
      expect(result.ok).toBe(false);
    });

    it("returns undefined when there is nothing to snapshot", async () => {
      const { persistence } = engine();
      expect(await persistence.backup("absent")).toEqual({ ok: true, value: undefined });
    });

    it("prunes to the retention limit", async () => {
      const { persistence } = engine({ maxBackups: 2 });
      await persistence.save("p1", "project", { n: 0 });
      for (let i = 1; i <= 4; i++) {
        await persistence.save("p1", "project", { n: i }, { backup: true });
      }

      expect(await persistence.listBackups("p1")).toHaveLength(2);
    });

    it("keeps backups out of the key listing", async () => {
      const { persistence } = engine();
      await persistence.save("p1", "project", {});
      await persistence.backup("p1");

      expect(await persistence.keys()).toEqual(["p1"]);
    });
  });

  describe("namespacing", () => {
    it("keeps two plugins' identical keys apart", async () => {
      const { persistence } = engine();
      const markup = persistence.namespaced("markup");
      const massing = persistence.namespaced("massing");

      await markup.save("settings", "settings", { colour: "red" });
      await massing.save("settings", "settings", { colour: "blue" });

      const loaded = await markup.load<{ colour: string }>("settings");
      if (loaded.ok) expect(loaded.value?.data).toEqual({ colour: "red" });
      expect(await markup.keys()).toEqual(["settings"]);
    });
  });
});

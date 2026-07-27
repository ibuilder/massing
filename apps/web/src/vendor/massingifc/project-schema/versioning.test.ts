import { MemoryStorageAdapter, PersistenceEngine, type VersionedDocument } from "@massingifc/core-kernel";
import { describe, expect, it } from "vitest";
import { createDefaultMigrationRegistry, SCHEMA } from "./schemas.js";
import { MigrationRegistry } from "./versioning.js";

const SCHEMA_ID = "test.record";

/** v1 {title} -> v2 {name} -> v3 {name, tags} */
const registry = (): MigrationRegistry =>
  new MigrationRegistry()
    .register({
      schema: SCHEMA_ID,
      from: 1,
      to: 2,
      description: "rename title to name",
      migrate: (data) => ({ name: (data as { title: string }).title }),
    })
    .register({
      schema: SCHEMA_ID,
      from: 2,
      to: 3,
      description: "add tags",
      migrate: (data) => ({ ...(data as object), tags: [] }),
    });

const doc = (version: number, data: unknown): VersionedDocument => ({
  schema: SCHEMA_ID,
  version,
  savedAt: "2026-01-01T00:00:00.000Z",
  data,
});

describe("MigrationRegistry", () => {
  it("reports the latest version from the registered steps", () => {
    expect(registry().latestVersion(SCHEMA_ID)).toBe(3);
  });

  it("runs the full chain from the oldest version", () => {
    const result = registry().migrate(doc(1, { title: "Tower" }));

    expect(result.ok).toBe(true);
    if (result.ok) {
      expect(result.value.version).toBe(3);
      expect(result.value.data).toEqual({ name: "Tower", tags: [] });
    }
  });

  it("resumes from an intermediate version", () => {
    const result = registry().migrate(doc(2, { name: "Tower" }));

    if (result.ok) {
      expect(result.value.version).toBe(3);
      expect(result.value.data).toEqual({ name: "Tower", tags: [] });
    }
  });

  it("passes an already-current document through untouched", () => {
    const original = doc(3, { name: "Tower", tags: ["a"] });
    const result = registry().migrate(original);

    expect(result.ok && result.value).toBe(original);
  });

  it("leaves the input document unmutated", () => {
    const original = doc(1, { title: "Tower" });
    registry().migrate(original);

    expect(original.data).toEqual({ title: "Tower" });
    expect(original.version).toBe(1);
  });

  it("ignores schemas it does not own", () => {
    const original = doc(1, {});
    const result = new MigrationRegistry().migrate(original);

    expect(result.ok && result.value).toBe(original);
  });

  describe("failure handling", () => {
    it("reports a gap in the chain rather than migrating half-way", () => {
      const gapped = new MigrationRegistry()
        .register({ schema: SCHEMA_ID, from: 2, to: 3, migrate: (d) => d })
        .declare(SCHEMA_ID, 3);

      const result = gapped.migrate(doc(1, {}));

      expect(result.ok).toBe(false);
      if (!result.ok) expect(result.error.code).toBe("MIGRATION_PATH_MISSING");
    });

    it("names the step that failed", () => {
      const broken = new MigrationRegistry().register({
        schema: SCHEMA_ID,
        from: 1,
        to: 2,
        migrate: () => {
          throw new Error("field was null");
        },
      });

      const result = broken.migrate(doc(1, {}));

      expect(result.ok).toBe(false);
      if (!result.ok) {
        expect(result.error.code).toBe("MIGRATION_FAILED");
        expect(result.error.message).toContain("v1 -> v2");
        expect(result.error.message).toContain("field was null");
      }
    });

    it("refuses a document newer than the code", () => {
      const result = registry().migrate(doc(99, {}));

      expect(result.ok).toBe(false);
      if (!result.ok) expect(result.error.code).toBe("SCHEMA_VERSION_UNSUPPORTED");
    });

    it("rejects a backwards migration at registration time", () => {
      expect(() =>
        new MigrationRegistry().register({ schema: SCHEMA_ID, from: 3, to: 2, migrate: (d) => d }),
      ).toThrowError();
    });

    it("rejects two migrations out of the same version", () => {
      const r = new MigrationRegistry().register({
        schema: SCHEMA_ID,
        from: 1,
        to: 2,
        migrate: (d) => d,
      });

      // Ambiguity here would make the upgrade depend on registration order.
      expect(() => r.register({ schema: SCHEMA_ID, from: 1, to: 3, migrate: (d) => d })).toThrowError();
    });
  });

  describe("compatibility checks", () => {
    it("answers without performing the migration", () => {
      const r = registry();

      expect(r.isCompatible(SCHEMA_ID, 1)).toBe(true);
      expect(r.isCompatible(SCHEMA_ID, 3)).toBe(true);
      expect(r.isCompatible(SCHEMA_ID, 4)).toBe(false);
      expect(r.isCompatible("unknown.schema", 1)).toBe(false);
    });

    it("exposes the planned steps", () => {
      const plan = registry().plan(SCHEMA_ID, 1);

      expect(plan.ok).toBe(true);
      if (plan.ok) {
        expect(plan.value.steps.map((s) => `${s.from}->${s.to}`)).toEqual(["1->2", "2->3"]);
        expect(plan.value.to).toBe(3);
      }
    });
  });
});

describe("default registry", () => {
  it("declares every shipped schema at version 1", () => {
    const r = createDefaultMigrationRegistry();

    expect(r.latestVersion(SCHEMA.project)).toBe(1);
    expect(r.latestVersion(SCHEMA.massingObject)).toBe(1);
    expect(r.latestVersion(SCHEMA.estimate)).toBe(1);
    expect(r.knownSchemas().length).toBeGreaterThan(40);
  });

  it("guards against future documents from the first release", () => {
    const r = createDefaultMigrationRegistry();

    // The reason to declare v1 up front: without it this document would load and be misread.
    const result = r.migrate({
      schema: SCHEMA.project,
      version: 2,
      savedAt: "2027-01-01T00:00:00.000Z",
      data: {},
    });

    expect(result.ok).toBe(false);
  });
});

describe("integration with the kernel persistence engine", () => {
  it("upgrades a legacy document on load", async () => {
    const adapter = new MemoryStorageAdapter();
    const persistence = new PersistenceEngine({ adapter, migrator: registry() });
    await adapter.put("r1", doc(1, { title: "Old Tower" }));

    const loaded = await persistence.load<{ name: string; tags: string[] }>("r1");

    expect(loaded.ok).toBe(true);
    if (loaded.ok) {
      expect(loaded.value?.version).toBe(3);
      expect(loaded.value?.data).toEqual({ name: "Old Tower", tags: [] });
    }
  });

  it("stamps new saves with the registry's current version", async () => {
    const persistence = new PersistenceEngine({
      adapter: new MemoryStorageAdapter(),
      migrator: registry(),
    });

    const saved = await persistence.save("r1", SCHEMA_ID, { name: "New", tags: [] });
    expect(saved.ok && saved.value.version).toBe(3);
  });
});

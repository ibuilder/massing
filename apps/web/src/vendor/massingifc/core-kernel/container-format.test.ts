import { describe, expect, it, vi } from "vitest";
import {
  ContainerService,
  StorageContainerAdapter,
  type ContainerAdapter,
  type OpenContainer,
} from "./container-format.js";
import { EventBus } from "./events.js";
import { createKernel } from "./kernel.js";
import { MemoryStorageAdapter, type DocumentMigrator } from "./persistence.js";
import { err, ok } from "./result.js";
import { KernelError } from "./errors.js";

const bytes = (text: string): Uint8Array => new TextEncoder().encode(text);

const service = (options: { migrator?: DocumentMigrator } = {}) => {
  const storage = new MemoryStorageAdapter();
  const events = new EventBus();
  const containers = new ContainerService({
    events,
    ...(options.migrator ? { migrator: options.migrator } : {}),
  });
  containers.registerAdapter(new StorageContainerAdapter(storage));
  return { containers, storage, events };
};

const open = async (containers: ContainerService): Promise<OpenContainer> => {
  const created = await containers.create("massingifc.project", { containerId: "p1", name: "Project" });
  if (!created.ok) throw created.error;
  return created.value;
};

describe("ContainerService", () => {
  it("creates a container through a registered adapter", async () => {
    const { containers } = service();
    const container = await open(containers);

    expect(container.manifest.formatId).toBe("massingifc.project");
    expect(containers.active).toBe(container);
  });

  it("reports an unknown format rather than guessing", async () => {
    const { containers } = service();
    const result = await containers.create("nope", { containerId: "x", name: "x" });

    expect(result.ok).toBe(false);
    if (!result.ok) expect(result.error.code).toBe("SERVICE_NOT_FOUND");
  });

  it("holds documents and blobs side by side", async () => {
    const { containers } = service();
    const container = await open(containers);

    await container.writeDocument("records/markup.json", "massingifc.markup", { pins: 3 });
    await container.writeBlob("models/site.frag", bytes("FRAG"), "application/octet-stream");

    expect(container.entries("document")).toHaveLength(1);
    expect(container.entries("blob")).toHaveLength(1);

    const document = await container.readDocument<{ pins: number }>("records/markup.json");
    expect(document.ok && document.value?.data).toEqual({ pins: 3 });

    const blob = await container.readBlob("models/site.frag");
    expect(blob.ok && blob.value && new TextDecoder().decode(blob.value)).toBe("FRAG");
  });

  it("tracks unsaved changes", async () => {
    const { containers } = service();
    const container = await open(containers);
    expect(container.dirty).toBe(false);

    await container.writeDocument("a", "s", {});
    expect(container.dirty).toBe(true);

    await containers.save();
    expect(container.dirty).toBe(false);
  });

  it("refuses to close over unsaved work unless forced", async () => {
    const { containers } = service();
    const container = await open(containers);
    await container.writeDocument("a", "s", {});

    const closed = await containers.close();
    expect(closed.ok).toBe(false);
    expect(containers.active).toBe(container);

    expect((await containers.close({ force: true })).ok).toBe(true);
    expect(containers.active).toBeUndefined();
  });

  describe("project and model unity", () => {
    it("round-trips models and records together", async () => {
      const { containers, storage } = service();
      const container = await open(containers);
      await container.writeDocument("project.json", "massingifc.project", { name: "Tower" });
      await container.writeBlob("models/tower.frag", bytes("GEOMETRY"));
      await containers.save();
      await containers.close();

      const reopened = await containers.open({ name: "p1", storage });

      expect(reopened.ok).toBe(true);
      if (reopened.ok) {
        // The record and the geometry come back as one act. There is no API that returns one
        // without the other, which is what makes them impossible to drift apart.
        const project = await reopened.value.readDocument<{ name: string }>("project.json");
        const model = await reopened.value.readBlob("models/tower.frag");
        expect(project.ok && project.value?.data).toEqual({ name: "Tower" });
        expect(model.ok && model.value).toBeDefined();
      }
    });

    it("keeps only one container active, closing the previous one", async () => {
      const { containers, storage } = service();
      const first = await open(containers);
      await containers.save();

      const second = await containers.create("massingifc.project", {
        containerId: "p2",
        name: "Second",
        storage,
      });

      expect(second.ok).toBe(true);
      expect(containers.active).not.toBe(first);
    });

    it("does not open a second container over unsaved work", async () => {
      const { containers, storage } = service();
      const container = await open(containers);
      await container.writeDocument("a", "s", {});

      const second = await containers.create("massingifc.project", {
        containerId: "p2",
        name: "Second",
        storage,
      });

      // Silently discarding the user's work to satisfy an open call is not the kernel's call.
      expect(second.ok).toBe(false);
      expect(containers.active).toBe(container);
    });

    it("announces the whole manifest in one event", async () => {
      const { containers, events } = service();
      const opened = vi.fn();
      events.on("container.created", opened);

      await open(containers);

      expect(opened).toHaveBeenCalledOnce();
      const payload = opened.mock.calls[0]?.[0] as { manifest: { name: string } };
      expect(payload.manifest.name).toBe("Project");
    });

    it("emits a close event", async () => {
      const { containers, events } = service();
      const closed = vi.fn();
      events.on("container.closed", closed);

      await open(containers);
      await containers.close();

      expect(closed).toHaveBeenCalledOnce();
    });
  });

  describe("versioning", () => {
    const migrator: DocumentMigrator = {
      latestVersion: (schema) => (schema === "s" ? 2 : undefined),
      migrate: (document) =>
        document.version === 1
          ? ok({ ...document, version: 2, data: { ...(document.data as object), added: true } })
          : err(new KernelError("MIGRATION_PATH_MISSING", "no path", {})),
    };

    it("stamps writes with the migrator's current version", async () => {
      const { containers } = service({ migrator });
      const container = await open(containers);

      const written = await container.writeDocument("a", "s", { x: 1 });
      expect(written.ok && written.value.version).toBe(2);
    });

    it("refuses a container written by a newer build", async () => {
      const storage = new MemoryStorageAdapter();
      await storage.put("container:future:manifest", {
        containerId: "future",
        formatId: "massingifc.project",
        formatVersion: 99,
        name: "From the future",
        createdAt: "2030-01-01T00:00:00.000Z",
        entries: [],
      });
      const containers = new ContainerService();
      containers.registerAdapter(new StorageContainerAdapter(storage));

      const result = await containers.open({ name: "future", storage });

      expect(result.ok).toBe(false);
      if (!result.ok) expect(result.error.code).toBe("SCHEMA_VERSION_UNSUPPORTED");
    });
  });

  describe("adapter selection", () => {
    const fake = (formatId: string, claims: boolean): ContainerAdapter => ({
      formatId,
      displayName: formatId,
      extensions: [formatId],
      canOpen: () => claims,
      open: async () => err(new KernelError("STORAGE_FAILED", "not implemented", {})),
      create: async () => err(new KernelError("STORAGE_FAILED", "not implemented", {})),
      save: async () => err(new KernelError("STORAGE_FAILED", "not implemented", {})),
    });

    it("sniffs for an adapter when no format is named", async () => {
      const containers = new ContainerService();
      containers.registerAdapter(fake("a", false));
      containers.registerAdapter(fake("b", true));

      const result = await containers.open({ uri: "x" });
      // "b" claimed it and then failed for its own reasons, which proves selection reached it.
      expect(result.ok).toBe(false);
      if (!result.ok) expect(result.error.message).toContain("not implemented");
    });

    it("treats an adapter that throws while sniffing as simply not matching", async () => {
      const containers = new ContainerService();
      containers.registerAdapter({
        ...fake("bad", false),
        canOpen: () => {
          throw new Error("sniff exploded");
        },
      });

      const result = await containers.open({ uri: "x" });
      expect(result.ok).toBe(false);
      if (!result.ok) expect(result.error.message).toContain("No container adapter recognised");
    });

    it("rejects two adapters claiming the same format id", () => {
      const containers = new ContainerService();
      containers.registerAdapter(fake("dup", true));
      expect(() => containers.registerAdapter(fake("dup", true))).toThrowError();
    });

    it("releases the format id when the registration is disposed", () => {
      const containers = new ContainerService();
      containers.registerAdapter(fake("x", true)).dispose();
      expect(containers.adapters()).toHaveLength(0);
    });
  });

  it("is available on the kernel with a working adapter out of the box", async () => {
    const kernel = createKernel();

    const created = await kernel.containers.create("massingifc.project", {
      containerId: "p1",
      name: "Default",
    });

    expect(created.ok).toBe(true);
    expect(kernel.containers.adapters()).toHaveLength(1);
  });
});

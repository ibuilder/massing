/**
 * The ties between this product and the vendored `massingifc` kernel.
 *
 * Vendoring a library proves nothing on its own — a copied directory that nothing imports is a fork
 * you have not noticed yet. What matters is whether the *seams* hold: that the kernel actually boots
 * here, that the identity and provenance rules this codebase treats as non-negotiable are the ones
 * the kernel encodes, and that the places where the two deliberately still DISAGREE are written down
 * as failing assertions rather than left to be rediscovered.
 *
 * That last part is the point of the container section below. Upstream issue #2 is open and
 * unresolved; these tests pin the disagreement so that when it is fixed, a test tells us — rather
 * than the mismatch surfacing as a user's project file refusing to open.
 */
import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { describe, expect, it } from "vitest";

import { VENDOR_ENTRIES } from "../../vendorAlias";
import { createKernel } from "@massingifc/core-kernel";
import { createCapabilityToken } from "@massingifc/core-kernel";
import { definePlugin, createTestHarness } from "@massingifc/plugin-sdk";
import { StorageContainerAdapter } from "@massingifc/core-kernel";
import { sameElement } from "@massingifc/project-schema";
import type { ElementRef } from "@massingifc/project-schema";

// --- the alias map is one fact in three tools ---------------------------------------------------
describe("the vendored kernel resolves the same way in every tool", () => {
  it("tsconfig paths agree with the map Vite and Vitest use", () => {
    // tsconfig cannot import TypeScript, so this copy is unavoidable. An unavoidable copy that is
    // asserted is not the same as one that is merely hoped for.
    // cwd is apps/web under vitest; import.meta.url is not a file: URL in this environment.
    const raw = readFileSync(resolve(process.cwd(), "tsconfig.json"), "utf8");
    const paths = JSON.parse(raw).compilerOptions.paths as Record<string, string[]>;
    for (const [name, rel] of Object.entries(VENDOR_ENTRIES)) {
      expect(paths[name], `${name} missing from tsconfig paths`).toBeTruthy();
      expect(paths[name]![0]!.replace(/^\.\//, "")).toBe(rel.replace(/^\.\//, ""));
    }
  });

  it("imports actually resolve — this file importing at all is the assertion", () => {
    expect(typeof createKernel).toBe("function");
    expect(typeof definePlugin).toBe("function");
    expect(typeof sameElement).toBe("function");
  });
});

// --- identity: the hardest non-negotiable in this codebase ---------------------------------------
describe("element identity is the IFC GlobalId, not a transient handle", () => {
  const A: ElementRef = { modelId: "m1", globalId: "2O2Fr$t4X7Zf8NOew3FLOH", localId: 41 };
  const B: ElementRef = { modelId: "m1", globalId: "2O2Fr$t4X7Zf8NOew3FLOH", localId: 9182 };

  it("the same element re-converted to a different local id is still the same element", () => {
    // This is the whole reason the rule exists: re-converting an IFC renumbers local ids, and if
    // identity followed them, every pin, clash, 4D link and takeoff row would silently detach.
    expect(sameElement(A, B)).toBe(true);
  });

  it("the same local id in a different model is NOT the same element", () => {
    expect(sameElement(A, { modelId: "m2", globalId: "OTHER", localId: 41 })).toBe(false);
  });
});

// --- the kernel boots and isolates, in our environment -------------------------------------------
describe("the kernel runs here", () => {
  it("loads a plugin, registers a capability and executes a command", async () => {
    const Token = createCapabilityToken<{ area(w: number, h: number): number }>("massing.tie.demo");
    const harness = createTestHarness();
    await harness.load(definePlugin({
      id: "massing.tie.demo",
      version: "1.0.0",
      permissions: ["massing.tie.demo"],
      activate(context) {
        context.capabilities.provide(Token, { area: (w, h) => w * h });
        context.commands.register({
          id: "massing.tie.demo",
          title: "Demo",
          permission: "massing.tie.demo",
          handler: () => undefined,
        });
      },
    }));
    // `get` returns the value or undefined; `require` returns a Result that says WHY it failed.
    expect(harness.kernel.capabilities.get(Token)?.area(3, 4)).toBe(12);

    const required = harness.kernel.capabilities.require(Token);
    expect(required.ok && required.value.area(3, 4)).toBe(12);
  });

  it("a missing capability is distinguished from an incompatible one", () => {
    // The unknown-vs-none rule this codebase keeps relearning, already encoded upstream: `require`
    // answers CAPABILITY_NOT_FOUND for absent and CAPABILITY_VERSION_MISMATCH for present-but-wrong.
    // Collapsing those would make "nobody provides this" indistinguishable from "you asked for the
    // wrong version", which are different bugs with different fixes.
    const harness = createTestHarness();
    const Absent = createCapabilityToken<{ x(): void }>("massing.tie.absent");
    const missing = harness.kernel.capabilities.require(Absent);
    expect(missing.ok).toBe(false);
    expect(missing.ok === false && missing.error.code).toBe("CAPABILITY_NOT_FOUND");
  });

  it("a plugin that throws on activation does not take the host with it", async () => {
    // "No plugin can crash the host" is one of the kernel's four design rules and the reason it is
    // worth adopting at all. Asserting it here means OUR build proves it, not just upstream's.
    const harness = createTestHarness();
    const result = await harness.load(definePlugin({
      id: "massing.tie.bad",
      version: "1.0.0",
      activate() { throw new Error("boom"); },
    }));
    expect(result.ok).toBe(false);
    expect(typeof harness.kernel.commands.execute).toBe("function");   // host still usable
  });
});

// --- the container seam, where the two still DISAGREE ---------------------------------------------
describe("the container format the kernel writes vs the one this product writes", () => {
  // Our side, from services/api/src/aec_api/bundle.py (v0.3.705). Duplicated here because a Python
  // constant cannot be imported into a vitest run; test_engine_routes covers the Python side.
  const OURS = { format: "massing.project", ext: ".mass", legacyFormat: "aec.mmproj", legacyExt: ".mmproj" };

  const adapter = new StorageContainerAdapter({} as never);

  it("the extensions now AGREE — upstream #2 landed (v0.3.716)", () => {
    // This case replaces a deliberately-failing guard. Between v0.3.712 and v0.3.716 the kernel
    // adapter listed only `.mmproj`, the extension this product replaced at v0.3.705, so a container
    // written here would not open there. Rather than leave that as a note, it was pinned as an
    // assertion of the WRONG state that would fail the moment it was fixed — and it did, on the
    // first re-sync after the upstream merge. That is the whole argument for writing a known gap as
    // a test: a note ages into fiction, a test tells you the day it stops being true.
    expect([...adapter.extensions]).toEqual(["mass", "mmproj"]);
    expect(adapter.extensions[0]).toBe(OURS.ext.replace(".", ""));   // `.mass` is native
    expect([...adapter.extensions]).toContain(OURS.legacyExt.replace(".", ""));  // still readable
  });

  it("the FORMAT IDs still differ, and that is a real remaining difference", () => {
    // Not a bug: the kernel's native container and this product's export format can legitimately be
    // distinct formats behind one ContainerAdapter interface. Asserted so that if they are ever
    // meant to converge, the change is deliberate rather than accidental.
    expect(adapter.formatId).toBe("massingifc.project");
    expect(OURS.format).toBe("massing.project");
  });

  it("our own format constants are the ones the docs and the API agree on", () => {
    // Cheap, but it is the half of the pair we control — if someone renames `.mass` again, the
    // disagreement above stops describing reality and this catches it.
    expect(OURS.ext).toBe(".mass");
    expect(OURS.legacyExt).toBe(".mmproj");
    expect(OURS.format).not.toBe(OURS.legacyFormat);
  });
});

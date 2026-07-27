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

  it("REGRESSION GUARD for upstream #2 — the extensions do not yet agree", () => {
    // This asserts the CURRENT, WRONG state on purpose. `.mmproj` was superseded by `.mass` in this
    // product at v0.3.705, and the kernel adapter still lists only the old one — so a container we
    // write today is not recognised. Writing that down as a failing-when-fixed assertion is the
    // difference between a known gap and a bug waiting to be rediscovered by a user whose project
    // will not open.
    //
    // WHEN UPSTREAM #2 LANDS this test fails. That is the intended signal: delete this case, enable
    // the one below, and drop the `.mass` disagreement from vendor/massingifc/VENDOR.md.
    expect([...adapter.extensions]).toEqual(["mmproj"]);
    expect([...adapter.extensions]).not.toContain("mass");
    expect(adapter.formatId).toBe("massingifc.project");
    expect(adapter.formatId).not.toBe(OURS.format);
  });

  it.skip("what it should be once #2 lands: .mass native, .mmproj still readable", () => {
    expect([...adapter.extensions]).toEqual(["mass", "mmproj"]);
    expect(adapter.extensions[0]).toBe(OURS.ext.replace(".", ""));
  });

  it("our own format constants are the ones the docs and the API agree on", () => {
    // Cheap, but it is the half of the pair we control — if someone renames `.mass` again, the
    // disagreement above stops describing reality and this catches it.
    expect(OURS.ext).toBe(".mass");
    expect(OURS.legacyExt).toBe(".mmproj");
    expect(OURS.format).not.toBe(OURS.legacyFormat);
  });
});

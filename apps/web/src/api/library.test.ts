import { describe, expect, it } from "vitest";

import { ApiClient } from "./client";

/**
 * The sample library client, and the menu that uses it.
 *
 * Three hard-coded `.frag` entries used to sit in the Open menu — geometry and nothing else, so the
 * demo showed the viewer and hid the platform. They are replaced by one entry that **fetches** the
 * library, which is the substantive change: a hard-coded list is a promise that drifts from what is
 * actually packaged, while `GET /samples` describes each container from its own manifest.
 *
 * The reachability check at the bottom is not ceremony. This codebase's most expensive recurring
 * defect is a correct thing nothing calls — seven engines once shipped with no route, and `pulse.ts`
 * sat imported-by-nobody for a release. A client method with no call site is the same defect.
 */

const api = new ApiClient("http://localhost:0");

describe("the library client", () => {
  it("exposes both calls the library needs", () => {
    expect(typeof (api as unknown as Record<string, unknown>).samples).toBe("function");
    expect(typeof (api as unknown as Record<string, unknown>).openSample).toBe("function");
  });

  it("arrived as a mixin, so client.ts did not grow", async () => {
    // The seam only helps if NEW work goes through it. If this import ever fails, the domain has
    // been folded back into client.ts and the extraction became a treadmill.
    const mod = await import("./library");
    expect(typeof mod.withLibrary).toBe("function");
  });

  it("still composes onto HttpCore's transport", () => {
    for (const k of ["url", "authHeaders", "setToken"]) {
      expect(typeof (api as unknown as Record<string, unknown>)[k], k).toBe("function");
    }
  });
});

/** Source of `main.ts`, for the wiring assertions below. */
async function mainSource(): Promise<string> {
  const mod = await import("../main.ts?raw");
  const src = (mod as { default: string }).default;
  expect(typeof src, "?raw did not resolve — the assertions below would be vacuous").toBe("string");
  expect(src.length).toBeGreaterThan(1000);
  return src;
}

describe("the Open menu uses the library, not a hard-coded list", () => {
  it("the three hard-coded .frag samples are gone", async () => {
    const src = await mainSource();
    // These shipped geometry with no project behind it — the exact thing the library replaces.
    expect(src, "school_str.frag should no longer be a menu entry").not.toMatch(/school_str\.frag/);
    expect(src, "school_arq.frag should no longer be a menu entry").not.toMatch(/school_arq\.frag/);
    expect(src, "basichouse.frag should no longer be hard-coded").not.toMatch(/basichouse\.frag/);
  });

  it("the menu calls the library instead", async () => {
    const src = await mainSource();
    expect(src).toMatch(/openSampleLibrary/);
    expect(src, "the list must be fetched, not literal").toMatch(/api\.samples\(\)/);
    expect(src, "opening must go through the server's import path").toMatch(/api\.openSample\(/);
  });

  it("there is exactly ONE way in, so shortcut and menu cannot disagree", async () => {
    const src = await mainSource();
    // `openSampleLibrary` is defined once and referenced by both the menu item and the command
    // shortcut. Two entry points would be two definitions of what "a sample" means.
    const defs = src.match(/async function openSampleLibrary/g) || [];
    expect(defs.length).toBe(1);
    const uses = src.match(/openSampleLibrary\(\)/g) || [];
    expect(uses.length, "menu + shortcut should both route here").toBeGreaterThanOrEqual(2);
  });

  it("sample names are escaped — they come from a container's manifest", async () => {
    const src = await mainSource();
    // Manifest text is file-derived, which is exactly the js/xss-through-dom path this repo has a
    // standing rule about. The picker builds innerHTML, so the name must pass through escapeHtml.
    expect(src).toMatch(/escapeHtml\(s\.name\)/);
  });
});

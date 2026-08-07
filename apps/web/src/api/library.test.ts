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

/**
 * Sources of `main.ts` and the viewer, read ONCE at module scope.
 *
 * WHY NOT LAZILY INSIDE THE TESTS, WHICH IS WHERE THEY USED TO BE
 *     `?raw` makes Vite transform the whole file, and `main.ts` and `viewer/app.ts` are two of the
 *     largest in the repo. Imported from inside a test, that cost lands entirely in **whichever test
 *     happens to call it first** — an ordering artifact, not a property of the assertion. Measured
 *     idle: the first caller took 160 ms while every other test in this file took 0–3 ms.
 *
 *     Under a loaded suite that one test is the one that dies. It timed out at vitest's 5 s default
 *     on 2026-08-07 while the other ten passed, which reads as "that assertion is slow" and is really
 *     "that assertion drew the short straw". Several sessions run suites in this clone, so contention
 *     is the normal condition, not an edge case.
 *
 *     At module scope the transform happens during collection, outside the per-test budget, and no
 *     single test inherits it. This is the same remedy `tooling/deleteRatchet.test.ts` settled on for
 *     a different cause — there the per-test cost was a `git log` walk, here it is a Vite transform.
 *     The shared rule is that **fixture cost does not belong inside a per-test timeout**, and the
 *     shared anti-pattern is raising the timeout, which keeps the cliff and moves it somewhere less
 *     predictable.
 *
 * The vacuity guards stay: a `?raw` that silently resolved to undefined would make every assertion
 * below pass against an empty string.
 */
const MAIN_SRC = ((await import("../main.ts?raw")) as { default: string }).default;
const VIEWER_SRC = ((await import("../viewer/app.ts?raw")) as { default: string }).default;

async function mainSource(): Promise<string> {
  expect(typeof MAIN_SRC, "?raw did not resolve — the assertions below would be vacuous").toBe("string");
  expect(MAIN_SRC.length).toBeGreaterThan(1000);
  return MAIN_SRC;
}

async function viewerSource(): Promise<string> {
  expect(typeof VIEWER_SRC, "?raw did not resolve — the assertions below would be vacuous").toBe("string");
  expect(VIEWER_SRC.length).toBeGreaterThan(1000);
  return VIEWER_SRC;
}

describe("the Open menu uses the library, not a hard-coded list", () => {
  it("the three hard-coded .frag samples are gone", async () => {
    // Scoped to main.ts, this assertion passed for releases while `viewer/app.ts` kept all three —
    // and used them as its DEFAULT, picked by a regex on the project's name, so a project called
    // "…School…" with no published model rendered an unrelated demo's geometry. A check scoped to
    // one file measures that file, not the behaviour. Both files, now.
    for (const src of [await mainSource(), await viewerSource()]) {
      expect(src, "school_str.frag must not be hard-coded").not.toMatch(/school_str\.frag/);
      expect(src, "school_arq.frag must not be hard-coded").not.toMatch(/school_arq\.frag/);
      expect(src, "basichouse.frag must not be hard-coded").not.toMatch(/basichouse\.frag/);
    }
  });

  it("the viewer does not choose geometry by matching the project's NAME", async () => {
    const src = await viewerSource();
    // The specific shape of the defect: a name regex deciding which model to load. Two projects can
    // share a word in their names and share nothing else — the only correct key is the project id.
    expect(src, "no name-regex model picker").not.toMatch(/fragsForProject/);
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

describe("first load never lands on an empty canvas", () => {
  it("offers the library when there are zero projects", async () => {
    const src = await mainSource();
    expect(src).toMatch(/projects\.length === 0/);
    expect(src).toMatch(/if \(!demo && projects\.length === 0\)[\s\S]{0,120}openSampleLibrary\(\)/);
  });

  it("OPENS the picker rather than auto-importing", async () => {
    const src = await mainSource();
    // Importing writes a real project into the user's database. Doing that unasked on first load is
    // a side effect nobody consented to. The startup path must reach the picker, never openSample().
    const startup = src.slice(src.indexOf("async function startup"));
    const guard = startup.slice(0, startup.indexOf("connectNotifications"));
    expect(guard, "startup must not import a sample by itself").not.toMatch(/api\.openSample\(/);
    expect(guard).toMatch(/openSampleLibrary\(\)/);
  });

  it("does not interrupt somebody who already has projects", async () => {
    const src = await mainSource();
    // `=== 0`, not `< 2` or a truthiness check: a user with work opening the app wants their work.
    expect(src).not.toMatch(/projects\.length\s*<\s*[12][\s\S]{0,80}openSampleLibrary/);
  });
});

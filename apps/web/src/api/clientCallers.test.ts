import { readFileSync } from "node:fs";
import { readdirSync, statSync } from "node:fs";
import { join, resolve } from "node:path";

import { describe, expect, it } from "vitest";

import { ApiClient } from "./client";

/**
 * Which API-client methods does the APPLICATION actually call?
 *
 * **The gap this closes.** `surface.test.ts` pins the client's method surface and asserts a floor on
 * its size. That answers "does the method exist", which is a different question from "can a user
 * reach it", and the two had already come apart. Its own comment introduces a list with *"the methods
 * the rest of the app actually calls … chosen because each has real call sites in the shell, the
 * viewer or the portal"* — and three of the names under that sentence (`proformaRenovation`,
 * `proformaRollover`, `proformaIncomeBasis`) have **no caller anywhere but that test**. They were
 * added to give server endpoints a client caller, which made the *endpoint* reachable and left the
 * *screen* exactly as absent as before. The prose claimed the stronger property; nothing checked it.
 *
 * That is the shape the backend already guards with a route-reachability ratchet, applied one layer
 * up: **a client method with no caller is a feature nobody can use**, and counting client methods
 * reports it as covered.
 *
 * **A ratchet, not a ban.** A client method may legitimately land before its screen — that is a
 * normal order of work, and this file's job is to stop the set growing silently, not to forbid the
 * first commit of a pair. The number below is a ceiling that only ever goes DOWN. Raising it is a
 * deliberate act that says "I am shipping another endpoint no user can reach yet", and it should be
 * argued for in the commit message.
 *
 * **The blind spot, and it was not hypothetical.** A first draft matched only static call text
 * (`.foo(`) and its docstring asserted "there is no computed dispatch in the app today". That was
 * wrong within one grep: `portal/portal.ts` fans out over
 * `["modelHealth", "costSummary", "scheduleVariance", …].map(call)`, dispatching by string name. The
 * draft therefore reported `costSummary` unreachable while the project home calls it on every load
 * — a confident false positive, produced by a checker whose comment asserted its own soundness.
 *
 * So a method counts as reached if the app either CALLS it (`.foo(`) or NAMES it as a string
 * literal. The second is deliberately loose: a bare `"foo"` might be a label rather than a
 * dispatch. That is the correct direction to fail for this particular gate — over-reporting
 * unreachability sends someone hunting a screen that already exists, while under-reporting merely
 * leaves the ceiling higher than it could be, and the ceiling is a ratchet that can be lowered
 * later.
 */

const SRC = resolve(process.cwd(), "src");

/** Every callable on the instance and its prototype chain, excluding Object's own. */
function surfaceOf(obj: object): Set<string> {
  const names = new Set<string>();
  for (let o = obj; o && o !== Object.prototype; o = Object.getPrototypeOf(o)) {
    for (const k of Object.getOwnPropertyNames(o)) {
      if (k === "constructor" || k.startsWith("_")) continue;
      const d = Object.getOwnPropertyDescriptor(o, k);
      if (d && typeof d.value === "function") names.add(k);
    }
  }
  return names;
}

function walk(dir: string, out: string[] = []): string[] {
  for (const e of readdirSync(dir)) {
    const p = join(dir, e);
    if (statSync(p).isDirectory()) {
      if (e === "vendor" || e === "node_modules" || e === "demo") continue;
      walk(p, out);
    } else if (/\.(ts|tsx)$/.test(e)) {
      out.push(p);
    }
  }
  return out;
}

/**
 * Files that COUNT as an application caller.
 *
 * Excludes `src/api/**` itself — a client method calling another client method keeps the pair
 * alive in each other's eyes and tells a user nothing — and excludes every test, for the same
 * reason the three proforma methods slipped through: their only caller was a test asserting they
 * were callable.
 */
const appFiles = walk(SRC).filter((p) => {
  const rel = p.replace(/\\/g, "/");
  if (/\.(test|spec)\.tsx?$/.test(rel)) return false;
  return !rel.includes("/src/api/");
});

const appText = appFiles.map((p) => readFileSync(p, "utf8")).join("\n");

const api = new ApiClient("http://localhost:0");
const surface = [...surfaceOf(api)].sort();

/** Transport plumbing and lifecycle helpers — not endpoints, and not expected to have screens. */
const NOT_ENDPOINTS = new Set([
  "setToken", "url", "json", "health", "token", "base", "headers", "fetch", "request",
]);

function reached(m: string): boolean {
  // A direct call: `api.foo(`, `this.api.foo(`, `client.foo(`. The leading `.` keeps
  // `proformaRenovation` from being matched inside `xproformaRenovation`.
  if (new RegExp(`\\.${m}\\s*\\(`).test(appText)) return true;
  // A dispatch by name: `["modelHealth", "costSummary", …].map(call)` in portal.ts. Quoted on both
  // sides so a substring of a longer identifier does not count.
  if (new RegExp(`["'\`]${m}["'\`]`).test(appText)) return true;
  return false;
}

const uncalled = surface.filter((m) => !NOT_ENDPOINTS.has(m) && !reached(m));

//: CEILING — only ever revised DOWN. The measured value on 2026-08-07, so the set cannot grow
//: quietly. Wiring a method to a screen lowers it; adding an unreachable endpoint raises it and has
//: to say so out loud in the commit message.
const UNCALLED_CEILING = 132;

describe("client methods the application actually calls", () => {
  it("agrees with a hand-checked sample in BOTH directions", () => {
    // Self-testing the instrument. A reachability checker that only ever reports "uncalled" is
    // indistinguishable from a broken matcher, and the first draft of this file WAS one for
    // `costSummary` — it is dispatched by string name from the project home and read as unreachable.
    // Each name below was verified by hand with a plain grep; the pairing is the point, because a
    // one-sided sample cannot catch a matcher that is too loose OR too tight.
    for (const m of ["costSummary", "modules", "publish"]) {
      expect(uncalled.includes(m), `${m} has app call sites but reads as uncalled`).toBe(false);
    }
    for (const m of ["colorFacets", "addBasePlate"]) {
      expect(uncalled.includes(m), `${m} has NO app call site but reads as reached`).toBe(true);
    }
  });

  it("counts an app caller, not merely a method definition", () => {
    // Guards the instrument before its verdict: if the scan found no callers at all it would report
    // every method uncalled and look like a catastrophic finding rather than a broken matcher.
    expect(appFiles.length, "no application files were scanned").toBeGreaterThan(50);
    expect(surface.length, "the client surface came back empty").toBeGreaterThan(600);
    expect(uncalled.length, "EVERY method reads as uncalled — the matcher is broken, not the app")
      .toBeLessThan(surface.length);
  });

  it("does not grow the set of client methods no screen can reach", () => {
    expect(uncalled.length,
      `${uncalled.length} client methods have no caller outside src/api and tests. ` +
      `Wire one to a screen (lowers the ceiling) or say in the commit why another unreachable ` +
      `endpoint is worth shipping. First 25: ${uncalled.slice(0, 25).join(", ")}`)
      .toBeLessThanOrEqual(UNCALLED_CEILING);
  });

  it("names the three that prompted this check, so their status cannot drift silently", () => {
    // `surface.test.ts` lists these under "the methods the rest of the app actually calls".
    // That was false when written. This records which of them is still true, so wiring one up
    // fails here and forces the list to be corrected rather than left to rot.
    const trio = ["proformaRenovation", "proformaRollover", "proformaIncomeBasis"];
    const stillUncalled = trio.filter((m) => uncalled.includes(m));
    expect(stillUncalled.sort()).toEqual([...trio].sort());
  });
});

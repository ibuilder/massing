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

/**
 * Methods that should NOT have a screen, with the condition under which that stops being true.
 *
 * This is deliberately not a suppression list for work nobody has got to yet — those belong in the
 * ceiling, where they stay visible and countable. An entry here is a positive argument that wiring
 * the method would be a mistake, and it carries the condition that would retire the entry, so it
 * cannot quietly become permanent.
 */
const KNOWN_UNCALLED: Record<string, string> = {
  // Deletes a captured schedule baseline. R40-EOT ② has just made the NAMED baseline the auditable
  // input to an extension-of-time figure that ends up in arbitration — slip is measured against it,
  // and the whole point of sourcing it from the record was that a typed date is unauditable. A
  // one-click destroy beside that is a footgun, and "it has no caller" is not a reason to give it
  // one. EXPIRY: wire it once baseline deletion is behind a confirm-and-audit step.
  clearBaseline: "until baseline deletion is behind a confirm-and-audit step",
};

const uncalled = surface.filter((m) => !NOT_ENDPOINTS.has(m) && !reached(m));
/** The countable set: deliberate exclusions are held separately so they cannot pad the ceiling. */
const uncalledCountable = uncalled.filter((m) => !(m in KNOWN_UNCALLED));

//: CEILING — only ever revised DOWN. The measured value on 2026-08-07, so the set cannot grow
//: quietly. Wiring a method to a screen lowers it; adding an unreachable endpoint raises it and has
//: to say so out loud in the commit message.
//:
//: 132 -> 131 when PULSE-FINDINGS wired `proformaRenovation` into the home pulse. It was expected to
//: drop by TWO, for `reserveStudy` as well — that was wrong, and the number is why it was caught:
//: `reserveStudy` already had a caller in `src/proforma/proforma.ts`, so it was never in this set.
//: Measured by probing rather than derived from what the wiring touched.
//: 129 -> 128 on 2026-08-07 (BOE-REACH): `estimateBoe` gained a caller — Basis of estimate on the
//: budget panel. Measured by re-running the scan, which reports exactly one fewer; nothing became
//: newly uncalled.
//:
//: 131 -> 129 on 2026-08-07 (UNCALLED-SWEEP, Lane C/G/I). The drop is TWO and was MEASURED by
//: re-running the reachability scan before and after, not derived from what was wired — the
//: `reserveStudy` note above is exactly why. `portfolioCompare` gained a caller (the returns spread
//: on the portfolio panel) and `clearBaseline` moved into KNOWN_UNCALLED, which the countable set
//: now excludes. Nothing became newly uncalled.
//:
//: HOW THIS NUMBER WAS OBTAINED, because it matters for trusting it: `vitest` is not installed in
//: `apps/web` and the shared clone's `src/api` differs from `origin/main` by ~795 deletions, so this
//: file could not be executed to produce it. The delta was measured with a static reproduction of
//: the same predicate against a clean `origin/main` worktree, which counts ~127 where this file
//: counts 131 — a different population, so its ABSOLUTE is not a valid ceiling input. The DELTA is
//: sound because both affected methods are present in both populations. If this run reports anything
//: other than 129, trust this file and not the reasoning above.
const UNCALLED_CEILING = 128;

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
    expect(uncalledCountable.length,
      `${uncalledCountable.length} client methods have no caller outside src/api and tests. ` +
      `Wire one to a screen (lowers the ceiling) or say in the commit why another unreachable ` +
      `endpoint is worth shipping. First 25: ${uncalledCountable.slice(0, 25).join(", ")}`)
      .toBeLessThanOrEqual(UNCALLED_CEILING);
  });

  it("names the three that prompted this check, so their status cannot drift silently", () => {
    // `surface.test.ts` lists these under "the methods the rest of the app actually calls".
    // That was false when written. This records which of them is still true, so wiring one up
    // fails here and forces the list to be corrected rather than left to rot.
    //
    // It did exactly that: PULSE-FINDINGS wired `proformaRenovation` into the home pulse and this
    // assertion went red on the same run, which is the whole reason it names them individually
    // instead of counting them.
    const trio = ["proformaRenovation", "proformaRollover", "proformaIncomeBasis"];
    const stillUncalled = trio.filter((m) => uncalled.includes(m));
    expect(stillUncalled.sort()).toEqual(["proformaIncomeBasis", "proformaRollover"]);
  });

  it("proformaRenovation is reached from a SCREEN, not from another api module", () => {
    // The pairing that makes the line above mean something. Moving a call into `src/api` would also
    // take a method out of `uncalled` without any human ever seeing its result — so assert the thing
    // that was actually wanted: a file outside `src/api` calls it.
    expect(uncalled.includes("proformaRenovation")).toBe(false);
    const callers = appFiles.filter((f) => /proformaRenovation/.test(readFileSync(f, "utf8")));
    expect(callers.length, "no screen calls it — it left `uncalled` for the wrong reason")
      .toBeGreaterThan(0);
  });
});

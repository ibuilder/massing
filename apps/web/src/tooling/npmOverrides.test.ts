import { existsSync, readFileSync } from "node:fs";
import { resolve } from "node:path";

import { describe, expect, it } from "vitest";

/**
 * An npm `overrides` entry may not silently disagree with the dependency it overrides.
 *
 * Written from a live failure this repo already paid for. `CHANGELOG.md` records
 * `EOVERRIDE: Override for eslint@10.8.0 conflicts with direct dependency` — the root manifest
 * pinned eslint through `overrides` while a workspace declared a range that no longer admitted that
 * pin. npm refuses the install outright, which is the GOOD case and the reason it was caught: the
 * bad case is an override that still *satisfies* the declared range while being a different version
 * from the one the manifest advertises, so `npm run lint` runs a linter nobody declared and every
 * document describing the toolchain is quietly wrong.
 *
 * That rule has lived only in a changelog entry ever since. Nothing read it, which is the same
 * failure mode `toolchainDocs.test.ts` exists for one layer up: **prose does not run**.
 *
 * SCOPE IS DERIVED, NOT LISTED. The population is every key in the root `overrides` block that is
 * ALSO declared as a dependency somewhere in the workspace — today exactly one (eslint); the other
 * three overrides (fast-uri, js-yaml, postcss) pin transitive packages nothing here declares, so
 * there is no pair to disagree and they are correctly outside the population rather than exempted.
 * Add a fourth overridden package that IS declared and it joins automatically.
 *
 * IT FAILS CLOSED. `satisfies` understands exact, `^`, `~` and `>=` and returns `null` for anything
 * else; a `null` reds the build rather than passing. A comparator that quietly returns "fine" for a
 * range shape it cannot read is the fail-open shape this repo keeps finding — the gate would go
 * green precisely when it stopped understanding its own subject.
 */

// Walk up to a MARKER rather than counting directories, for the reason `toolchainDocs.test.ts`
// records: `resolve(cwd, "..", "..")` resolves somewhere useless when vitest is invoked from the
// repo root instead of from `apps/web`, and the suite then fails with ENOENT rather than saying so.
function repoRoot(): string {
  let dir = process.cwd();
  for (let i = 0; i < 8; i += 1) {
    if (existsSync(resolve(dir, ".github/workflows/ci.yml"))) return dir;
    const up = resolve(dir, "..");
    if (up === dir) break;
    dir = up;
  }
  throw new Error("repo root not found — no ancestor holds .github/workflows/ci.yml");
}

const REPO = repoRoot();

type Manifest = {
  dependencies?: Record<string, string>;
  devDependencies?: Record<string, string>;
  overrides?: Record<string, string>;
};

function manifest(rel: string): Manifest {
  const text = readFileSync(resolve(REPO, rel), "utf8");
  expect(text.length, `${rel} did not load — every assertion below would pass vacuously`)
    .toBeGreaterThan(200);
  return JSON.parse(text) as Manifest;
}

/** The manifests that can declare a dependency an override could contradict. */
const MANIFESTS = ["package.json", "apps/web/package.json"] as const;

const parts = (v: string): [number, number, number] | null => {
  const m = /^(\d+)\.(\d+)\.(\d+)$/.exec(v.trim());
  return m ? [Number(m[1]), Number(m[2]), Number(m[3])] : null;
};

const cmp = (a: [number, number, number], b: [number, number, number]): number =>
  a[0] - b[0] || a[1] - b[1] || a[2] - b[2];

/**
 * Does the exact version `pin` satisfy the declared range `range`?
 *
 * Returns `null` — NOT `false` — for a shape this cannot read, so the caller can tell "violates the
 * range" apart from "I do not know what this range means". Those deserve different messages and
 * both must red the build; collapsing them is how a gate starts lying.
 *
 * Deliberately hand-rolled rather than importing `semver`. `semver` is present in `node_modules`
 * only as a transitive dependency of other tooling, and CLAUDE.md's `test_declared_imports` lesson
 * is exactly this: a package our own source imports is a DIRECT dependency however else it happens
 * to arrive, and leaning on somebody else's metadata means a release nobody here reviews can delete
 * it. The four shapes below are the ones these manifests actually use.
 */
export function satisfies(pin: string, range: string): boolean | null {
  const p = parts(pin);
  if (!p) return null;
  const r = range.trim();
  const op = /^(\^|~|>=)?\s*(\d+\.\d+\.\d+)$/.exec(r);
  // `noUncheckedIndexedAccess` is on, so a matched group is `string | undefined` to the compiler
  // even though this regex cannot match without group 2. Re-parse rather than assert with `!`: a
  // non-null assertion here would be a claim about the regex that the next edit to it could
  // silently falsify, and this function's whole contract is that it never guesses.
  const floor = op ? parts(op[2] ?? "") : null;
  if (!op || !floor) return null;
  if (cmp(p, floor) < 0) return false;
  switch (op[1]) {
    case undefined: return cmp(p, floor) === 0;
    case ">=": return true;
    case "^": return p[0] === floor[0];
    case "~": return p[0] === floor[0] && p[1] === floor[1];
    default: return null;
  }
}

/**
 * One override paired with one declaration of the same package.
 *
 * `sameFile` is the whole reason this is not a flat list: npm applies TWO DIFFERENT RULES depending
 * on where the declaration sits, and a gate that applied one rule to both would be wrong in one
 * direction or the other. See `verdict` below.
 */
type Pair = { pkg: string; pin: string; where: string; range: string; sameFile: boolean };

function population(): Pair[] {
  const root = manifest("package.json");
  const overrides = root.overrides ?? {};
  const out: Pair[] = [];
  for (const rel of MANIFESTS) {
    const m = rel === "package.json" ? root : manifest(rel);
    for (const field of ["dependencies", "devDependencies"] as const) {
      for (const [pkg, range] of Object.entries(m[field] ?? {})) {
        const pin = overrides[pkg];
        if (pin !== undefined) {
          out.push({ pkg, pin, where: `${rel} ${field}`, range, sameFile: rel === "package.json" });
        }
      }
    }
  }
  return out;
}

/**
 * Is this override/declaration pair one npm will accept? `null` means "cannot tell" and reds the build.
 *
 * **THE RULE IS NOT THE SAME IN BOTH POSITIONS, and getting that wrong in either direction breaks
 * something.** `overrides` is only read from the ROOT manifest, and npm's constraint is scoped to
 * "a package already listed as a direct dependency IN THE SAME package.json", where the two specs
 * must then match *as raw strings* — not merely be semver-compatible.
 *
 * - **Root's own dependencies (`sameFile`): raw-string equality.** `">=10.9.0"` beside an override
 *   of `"10.10.0"` is semver-compatible and npm still refuses it with EOVERRIDE. A `satisfies()`
 *   check here is LOOSER than npm and would pass an install that cannot happen. This is the pair
 *   that produced `Override for eslint@10.8.0 conflicts with direct dependency`.
 * - **A workspace's dependencies: semver compatibility.** The override is not in that file, so the
 *   raw-string rule does not reach it; npm resolves the declared range and rewrites it to the
 *   override. Measured in this repository: `apps/web/package.json` declares `^10.10.0`, the root
 *   override pins `10.10.0`, and `package-lock.json` records `apps/web`'s resolved devDependency as
 *   `10.10.0`. npm produced that lock. Demanding raw equality here would red a configuration that
 *   demonstrably installs.
 *
 * `$name` is npm's own escape hatch — an override of `"$foo"` means "whatever the direct dependency
 * declares", so it cannot disagree with it by construction and is accepted wherever it appears.
 */
export function verdict(p: Pair): boolean | null {
  if (p.pin.startsWith("$")) return p.pin === `$${p.pkg}` ? true : null;
  return p.sameFile ? p.pin.trim() === p.range.trim() : satisfies(p.pin, p.range);
}

describe("an npm override agrees with the dependency it overrides", () => {
  const PAIRS = population();

  it("the comparator reads the shapes these manifests use, and refuses the ones it cannot", () => {
    // The historical failure, as an assertion: the override this repo shipped against the range it
    // shipped beside. If this ever returns true the gate has stopped being able to see its own
    // founding defect.
    expect(satisfies("10.8.0", "^10.9.1"), "the EOVERRIDE case must be REJECTED").toBe(false);
    expect(satisfies("10.10.0", "^10.10.0")).toBe(true);
    expect(satisfies("10.10.0", "10.10.0")).toBe(true);
    expect(satisfies("10.10.1", "10.10.0"), "an exact pin means exact").toBe(false);
    expect(satisfies("11.0.0", "^10.9.1"), "a caret does not cross a major").toBe(false);
    expect(satisfies("10.11.0", "~10.10.0"), "a tilde does not cross a minor").toBe(false);
    expect(satisfies("10.11.0", ">=10.10.0")).toBe(true);
    // Fail-closed: unreadable shapes are `null`, never a quiet pass.
    expect(satisfies("10.10.0", "workspace:*"), "unreadable range must be null").toBeNull();
    expect(satisfies("10.10.0", "10.9.x"), "unreadable range must be null").toBeNull();
    expect(satisfies("latest", "^10.9.1"), "unreadable pin must be null").toBeNull();
  });

  it("there is something to check — otherwise every assertion below is vacuous", () => {
    // If the root overrides block is emptied, or every overridden package stops being declared,
    // this gate proves nothing and should say so rather than going green.
    expect(PAIRS.length, "no overridden package is also a declared dependency").toBeGreaterThan(0);
  });

  it("the two rules are actually different, and each is applied in its own position", () => {
    const p = (over: Partial<Pair>): Pair =>
      ({ pkg: "eslint", pin: "10.10.0", where: "t", range: "^10.10.0", sameFile: false, ...over });

    // The pair this repository ships. A workspace declares a caret, the root override pins exact,
    // and `package-lock.json` records apps/web resolving to 10.10.0 — npm produced that lock, so
    // this MUST be accepted. Demanding raw equality here would red a working configuration.
    expect(verdict(p({ sameFile: false })), "workspace caret vs exact override is fine").toBe(true);

    // ...and the SAME two strings in the root manifest are refused, because npm compares raw specs
    // there. This is the asymmetry: one rule per position, not one rule.
    expect(verdict(p({ sameFile: true })), "root raw-spec mismatch is EOVERRIDE").toBe(false);

    // The hole the loose rule left: semver-compatible but not raw-equal, in the root file.
    expect(verdict(p({ sameFile: true, pin: "10.10.0", range: ">=10.9.0" })),
      "root: compatible is NOT enough").toBe(false);
    expect(verdict(p({ sameFile: true, pin: "10.10.0", range: "10.10.0" })),
      "root: raw equality passes").toBe(true);

    // npm's own escape hatch, accepted in both positions because it cannot disagree.
    expect(verdict(p({ sameFile: true, pin: "$eslint" })), "$name self-reference").toBe(true);
    expect(verdict(p({ sameFile: false, pin: "$eslint" })), "$name self-reference").toBe(true);
    // A `$` pointing at a DIFFERENT package resolves elsewhere; this gate cannot follow it.
    expect(verdict(p({ pin: "$other" })), "cross-package $ reference is unreadable").toBeNull();
  });

  it("no override contradicts a declaration npm will check it against, and none is unreadable", () => {
    const violations: string[] = [];
    const unknown: string[] = [];
    for (const pair of PAIRS) {
      const { pkg, pin, where, range, sameFile } = pair;
      const ok = verdict(pair);
      const rule = sameFile ? "must match RAW (same file as the overrides block)" : "must satisfy";
      if (ok === null) unknown.push(`${pkg}: override "${pin}" vs ${where} "${range}"`);
      else if (!ok) violations.push(`${pkg}: override "${pin}" ${rule} ${where} "${range}"`);
    }
    expect(unknown, "a spec shape the comparator cannot read — teach it, do not exempt it")
      .toEqual([]);
    expect(violations, "npm will refuse this install with EOVERRIDE, or run a version nobody declared")
      .toEqual([]);
  });
});

import { existsSync, readFileSync } from "node:fs";
import { resolve } from "node:path";

import { describe, expect, it } from "vitest";

/**
 * Prose may not name a toolchain version the manifests disagree with.
 *
 * Written from a live failure. Four documents told the reader that `apps/web` pins **eslint 9.39.5**
 * "until the local Node bump", and that **CI runs Node 22**. By the time anyone read that, the root
 * `package.json` carried `"overrides": {"eslint": "10.8.0"}`, every workflow pinned `node-version:
 * "24"`, and the local Node had been 24.18.0 for a week. Every one of those sentences was written
 * true and became false without anything failing — which is the whole point: **nothing reads prose**.
 *
 * The specific harm is not untidiness. A pin is an instruction. A reader who hits a lint error and
 * finds "eslint pinned 9.39.5" in the engineering standards has been told, by the document whose job
 * is to be authoritative, that the fix is to go backwards. Stale guidance is worse than absent
 * guidance because it is confidently actionable.
 *
 * THE TRAP THIS FILE HAS TO AVOID is the one `docsCurrent.test.ts` names: writing the expectation
 * twice, once in the doc and once in the assertion, so the pair agrees with itself while both drift
 * away from the product. So there is **no version literal anywhere below**. Every expected value is
 * read out of `package.json` or `ci.yml` at run time. Bump eslint and this test moves with it; the
 * only way to fail is for a document to disagree with the manifest.
 *
 * Scope is deliberately narrow — eslint and Node, in four named files — because those are the two
 * versions this repo has actually drifted on, and a gate that tried to police every number in every
 * document would need an exemption list, which is the tell that a gate's population is wrong.
 */

// Find the repo root by a MARKER, not by counting directories up from cwd. `resolve(cwd, "..", "..")`
// is what the neighbouring doc gates do, and it silently resolves to `C:\` when vitest is invoked
// from the repo root instead of from `apps/web` — the suite then fails with ENOENT on `C:\CLAUDE.md`,
// which reads like a missing file rather than a wrong assumption about the working directory.
// Walking up to a known marker is correct from any cwd, including a worktree.
function repoRoot(): string {
  let dir = process.cwd();
  for (let i = 0; i < 8; i += 1) {
    if (existsSync(resolve(dir, ".github/workflows/ci.yml"))) return dir;
    const up = resolve(dir, "..");
    if (up === dir) break;
    dir = up;
  }
  throw new Error(`could not locate the repo root above ${process.cwd()}`);
}

const REPO = repoRoot();

function read(rel: string): string {
  const text = readFileSync(resolve(REPO, rel), "utf8");
  expect(text.length, `${rel} did not load — every assertion below would pass vacuously`)
    .toBeGreaterThan(500);
  return text;
}

/** Documents that give toolchain instructions. All tracked; all read by a human before running a command. */
const GOVERNED = [
  "CLAUDE.md",
  "docs/engineering/web-standards.md",
  ".claude/skills/verify-frontend/SKILL.md",
  ".claude/skills/ship-release/SKILL.md",
] as const;

const DOCS = GOVERNED.map((rel) => [rel, read(rel)] as const);

// ---- the truths, derived ---------------------------------------------------------------------
const webPkg = JSON.parse(read("apps/web/package.json")) as {
  devDependencies: Record<string, string>;
  engines: { node: string };
};

/** `^10.8.0` → `10.8.0`. The range operator is not part of what prose should be claiming. */
const ESLINT = (webPkg.devDependencies.eslint ?? "").replace(/^[\^~>=<\s]+/, "");
/** `>=24` → 24. */
const NODE_FLOOR = Number(/(\d+)/.exec(webPkg.engines.node)?.[1]);
/** Every workflow pins the same major; take it from the one that runs the web gate. */
const CI_NODE = Number(
  /node-version:\s*"?(\d+)/.exec(read(".github/workflows/ci.yml"))?.[1],
);

describe("the toolchain versions in prose are the ones the manifests declare", () => {
  it("the derived truths parsed — otherwise every check below compares against NaN", () => {
    // A gate whose expected value silently became `undefined` passes everything. This is the
    // mutation-check written as an assertion: break the parse and this fails first, loudly.
    expect(ESLINT, "apps/web devDependencies.eslint did not parse").toMatch(/^\d+\.\d+\.\d+$/);
    expect(NODE_FLOOR, "apps/web engines.node did not parse").toBeGreaterThan(0);
    expect(CI_NODE, "ci.yml node-version did not parse").toBeGreaterThan(0);
  });

  it("no document attributes a version to eslint that apps/web does not declare", () => {
    // `@eslint/js` is a DIFFERENT package on a different major (it is what dependabot #236 bumps),
    // so a match must not be counted when the word is part of that scoped name.
    const bad: string[] = [];
    let seen = 0;
    for (const [rel, text] of DOCS) {
      for (const m of text.matchAll(/(?<!@)\beslint\b(?!\/)(.{0,45}?)(\d+\.\d+\.\d+)/gi)) {
        seen += 1;
        if (m[2] !== ESLINT) bad.push(`${rel}: "…eslint${m[1]}${m[2]}" — declared is ${ESLINT}`);
      }
    }
    expect(seen, "no document names an eslint version — this check proved nothing")
      .toBeGreaterThan(0);
    expect(bad, `prose names an eslint version that apps/web does not declare`).toEqual([]);
  });

  it("no document claims CI runs a Node major that the workflow does not pin", () => {
    const bad: string[] = [];
    let seen = 0;
    for (const [rel, text] of DOCS) {
      for (const m of text.matchAll(/\bCI\s+(?:runs|is on|pins|uses)\s+Node\s*v?(\d+)/gi)) {
        seen += 1;
        if (Number(m[1]) !== CI_NODE) bad.push(`${rel}: "${m[0]}" — ci.yml pins ${CI_NODE}`);
      }
    }
    expect(seen, "no document states which Node CI runs — this check proved nothing")
      .toBeGreaterThan(0);
    expect(bad, "prose states a CI Node version the workflows contradict").toEqual([]);
  });

  it("no document instructs the reader to use a Node below the engines floor", () => {
    // A version named as the one that BREAKS the build is not an instruction, it is a warning, and
    // it is supposed to be below the floor — `CLAUDE.md` has said "v18 BREAKS the web build" for
    // months and is right to. Excluded by what the sentence does with the number, not by a list of
    // allowed numbers: an exemption list would have to be maintained, and would rot the same way.
    const bad: string[] = [];
    let seen = 0;
    for (const [rel, text] of DOCS) {
      // The window stops at a clause boundary. Unbounded, it reached PAST the claim into the next
      // one: `Node 20 (Node 18 breaks the build)` saw "breaks" from the parenthetical and excused the
      // "Node 20" instruction sitting right in front of it. That silently exempted both skill files —
      // the gate reported one offender and looked like it was working.
      for (const m of text.matchAll(/\bNode\s*v?(\d+)(?:\.\d+\.\d+)?([^;(),\n]{0,40})/gi)) {
        // `?? ""` and not `!`: an empty trailing window means "nothing excused this match", which is
        // the safe reading. Asserting non-null here would make a regex change fail at runtime instead.
        if (/break|not supported|too old|fails|refuses/i.test(m[2] ?? "")) continue;
        seen += 1;
        if (Number(m[1]) < NODE_FLOOR) {
          bad.push(`${rel}: "Node ${m[1]}" — engines.node requires >=${NODE_FLOOR}`);
        }
      }
    }
    expect(seen, "no document names a Node version to use — this check proved nothing")
      .toBeGreaterThan(0);
    expect(bad, "prose tells the reader to use a Node the manifest rejects").toEqual([]);
  });

  it("no document names a full Node build below the engines floor", () => {
    // The check above only sees `Node 24` — a bare major with the word attached. CLAUDE.md writes its
    // Node versions as `v24.18.0`, with the word several tokens away, so that check could not see the
    // one line in this repo with the worst drift record: CLAUDE.md says of it that it "has now been
    // wrong in two different ways" across three edits, and tells the reader to trust `node -v` over
    // the sentence. A gate that stops just short of the most drift-prone line in the repo has a scope
    // that quietly contradicts its name.
    const bad: string[] = [];
    let seen = 0;
    for (const [rel, text] of DOCS) {
      for (const m of text.matchAll(/node.{0,60}?\bv?(\d+)\.\d+\.\d+/gi)) {
        const end = (m.index ?? 0) + m[0].length;
        if (/break|not supported|too old|fails|refuses/i.test(text.slice(end, end + 40))) continue;
        seen += 1;
        if (Number(m[1]) < NODE_FLOOR) {
          bad.push(`${rel}: "${m[0].trim().slice(-40)}" — engines.node requires >=${NODE_FLOOR}`);
        }
      }
    }
    expect(seen, "no document names a full Node build — this check proved nothing")
      .toBeGreaterThan(0);
    expect(bad, "prose names a Node build below the floor without marking it broken").toEqual([]);
  });
});

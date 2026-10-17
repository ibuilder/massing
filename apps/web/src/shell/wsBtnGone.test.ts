import { readFileSync, readdirSync, statSync } from "node:fs";
import { dirname, join, relative, resolve } from "node:path";
import { fileURLToPath } from "node:url";

import { describe, expect, it } from "vitest";

/**
 * WS-BTN-DEAD's gate: `.ws-btn` and `data-ws` may be WRITTEN ABOUT, never used.
 *
 * The class was queried from four places in `main.ts`, styled by six rules in `style.css`, and
 * listed in `ui/colorContract.ts`'s `ACCENT_ALLOWED` — and rendered by nothing. `data-ws` had no
 * writer anywhere in the tree, which is the shortest proof that none of it could work, and it took
 * four separate slices across two months to find all of it (NOTIF-BADGE-DEAD, WS-BTN-SELECT,
 * `wsLabel`'s "documented fallback", and `applyPersona`'s persona allowlist) because **a dead
 * branch beside a live one is not read as dead**: `applyPersona` filtered `.ws-btn` and `.rail-btn`
 * in two adjacent lines, and `.rail-btn` really is rendered.
 *
 * ### Why this is not "assert the string is absent"
 *
 * Six files still *mention* the class, on purpose — the docstrings recording what it cost are the
 * most valuable thing the episode produced, and `style.css` says in a comment why four rules are
 * missing from a block that still has a live `#workspaces`. A gate forbidding the string outright
 * would instruct the next reader to delete that record, which is the failure
 * `test_gap_records.py` describes as *a check whose failure message can misdiagnose*.
 *
 * So the rule is positional: an occurrence on a **comment** line is prose and passes; an occurrence
 * anywhere else is a use and fails. It is deliberately conservative about what counts as a comment
 * — a leading `*`, `//`, `/*` or an HTML comment — rather than parsing the languages, because the
 * two ways to be wrong here are not symmetric. Over-stripping (treating code as prose) makes the
 * gate blind, which is the whole class of failure the backend's gates keep paying for; a trailing
 * comment on a code line — or a continuation line of a block comment — reads as a use and FAILS
 * CLOSED, costing somebody one reword.
 *
 * **It red on its author's own comment on its first run**: a block-comment continuation line in
 * `style.css` explaining which rules had just been deleted. That is better evidence than any
 * fixture — the self-check below is a claim about planted text, and this was the live walk finding
 * something nobody planted.
 *
 * ### Three self-checks, because a gate whose expected answer is zero breaks silently
 *
 * The population is floored, a planted USE must be found, and a planted PROSE line must NOT be —
 * that third one is the gate proving it is not the string ban it would be easy to mistake it for.
 */

// Anchored on this file, never on `process.cwd()`. `test_schema_types_agree.py` shipped a scan
// relative to the working directory, which `run_tests.py` and `ci.yml` set differently, so it would
// have reported a clean tree under CI and nowhere else. *A relative path is a question about where
// somebody stood.*
const SRC = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const WEB = resolve(SRC, "..");

const DEAD = /ws-btn|data-ws\b|\.ws-badge|dataset\.ws\b/;

/** A line that is unambiguously prose. Narrow on purpose — see the docstring. */
function isComment(line: string): boolean {
  const t = line.trim();
  return t.startsWith("*") || t.startsWith("//") || t.startsWith("/*") || t.startsWith("<!--");
}

function scanned(): string[] {
  const out: string[] = [];
  const walk = (dir: string) => {
    for (const name of readdirSync(dir)) {
      if (name === "vendor" || name === "node_modules") continue;
      const p = join(dir, name);
      if (statSync(p).isDirectory()) { walk(p); continue; }
      if (name.endsWith(".test.ts")) continue;          // a test is not a producer of app DOM
      if (/\.(ts|css)$/.test(name)) out.push(p);
    }
  };
  walk(SRC);
  out.push(join(WEB, "index.html"));                     // static markup lives OUTSIDE src/
  return out;
}

/** The verdict, separate from the walk so it can be mutated directly on fixture text. */
export function uses(text: string): string[] {
  return text.split("\n")
    .map((l, i) => [l, i + 1] as const)
    .filter(([l]) => DEAD.test(l) && !isComment(l))
    .map(([l, n]) => `${n}: ${l.trim()}`);
}

describe("WS-BTN-DEAD stays dead", () => {
  const files = scanned();

  it("scans a real population — a wrong question returns a confident zero", () => {
    // Floored rather than pinned: the exact count moves with every new file, and a floor still
    // fails if the walk resolves nowhere, which is the only failure this check exists for.
    expect(files.length).toBeGreaterThan(200);
    expect(files.map((f) => relative(WEB, f))).toContain("index.html");
    expect(files.map((f) => relative(WEB, f))).toContain(join("src", "style.css"));
  });

  it("finds a planted USE — the gate is not vacuous", () => {
    expect(uses('document.querySelectorAll(".ws-btn").forEach((b) => b.hidden = true);')).toHaveLength(1);
    expect(uses('  const tab = el.querySelector(`[data-ws="${key}"]`);')).toHaveLength(1);
    expect(uses(".ws-btn.active { background: var(--accent); }")).toHaveLength(1);
    expect(uses('  <div class="ws-btn" data-ws="model"></div>')).toHaveLength(1);
  });

  it("does NOT flag the historical record — this is not a string ban", () => {
    expect(uses(" * `applyPersona` filtered `.ws-btn`, a class nothing renders.")).toEqual([]);
    expect(uses("// WS-BTN-DEAD — this line used to read `.ws-btn`")).toEqual([]);
    expect(uses("/* the six `.ws-btn` rules that used to sit here */")).toEqual([]);
    expect(uses("<!-- the `.ws-btn` strip was replaced by `[data-room]` -->")).toEqual([]);
  });

  it("uses the class nowhere in shipped code", () => {
    const found = files.flatMap((f) => uses(readFileSync(f, "utf8")).map((u) => `${relative(WEB, f)}:${u}`));
    expect(found).toEqual([]);
  });
});

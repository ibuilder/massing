import { readFileSync, readdirSync, statSync } from "node:fs";
import { join, relative, resolve } from "node:path";

import { describe, expect, it } from "vitest";

import { CACHE_KEY_PREFIXES, isKeeper } from "./clearCache";

/**
 * Every localStorage key this app writes is enumerated, and "Clear cached data" is measured against
 * the real ones rather than an invented namespace.
 *
 * ## The defect
 *
 * `clearCache.ts` removed every key for which `isKeeper()` was false, and its keep-list named
 * `aec_token`, `aec_user`, `shell-spine`, `aec_persona`, `aec_ws`, `prefs:` and `aec_pref_`. **The
 * session key is `aec-token`, with a hyphen**, and the other six strings appear nowhere in this
 * repository outside that file and its test. `aec_user` matched exactly and has never been written by
 * any commit.
 *
 * So the button signed the user out, wiped every preference, and deleted `aec-field-queue` — unsynced
 * field captures — while reporting *"Kept your sign-in and preferences (0 settings)"* beneath a
 * Settings note reading "Your sign-in and preferences are kept".
 *
 * ## Why an enumeration and not more examples
 *
 * The old test had six examples and all six were fictional; adding correct ones would fix today and
 * drift again on the next rename, silently, because nothing tied the list to the app. This walks the
 * source instead: **a key that exists must be classified, and a prefix that is declared must match
 * something that exists.** The second direction is the one that would have caught the original list
 * on the day it rotted.
 *
 * Same shape as `panelReady.test.ts`, and the same reasoning: a population you cannot enumerate is a
 * population you cannot make claims about.
 */

const SRC = resolve(process.cwd(), "src");

/** Keys assembled at runtime from a variable, e.g. `portal-cols:${m.key}` — matched by their stem. */
const TEMPLATE_STEMS = ["portal-cols:", "tools-open:", "massing.selsets."];

function tsFiles(dir: string, out: string[] = []): string[] {
  for (const name of readdirSync(dir)) {
    const p = join(dir, name);
    if (statSync(p).isDirectory()) { tsFiles(p, out); continue; }
    if (p.endsWith(".ts") && !p.endsWith(".d.ts") && !p.endsWith(".test.ts")) out.push(p);
  }
  return out;
}

/**
 * Every localStorage key the app can write.
 *
 * Two forms are collected, because collecting only the first is how a scan like this quietly covers
 * less than it claims: a **literal** in the call (`localStorage.getItem("aec-token")`), and a
 * **constant** referenced there and declared in the same file (`const QKEY = "aec-field-queue"`).
 * Thirteen of the app's keys are the second form, including the field queue.
 */
function keys(): { found: { key: string; file: string }[]; unresolved: string[] } {
  const found = new Map<string, string>();
  const unresolved: string[] = [];
  const call = /localStorage\.(?:get|set|remove)Item\(\s*([^,)]+)/g;
  for (const file of tsFiles(SRC)) {
    const text = readFileSync(file, "utf8");
    const where = relative(SRC, file).replace(/\\/g, "/");
    for (const m of text.matchAll(call)) {
      const arg = (m[1] ?? "").trim();
      const lit = /^["'`]([^"'`$]+)["'`]$/.exec(arg);
      if (lit?.[1]) { found.set(lit[1], where); continue; }
      const tmpl = /^`([^`$]+)\$\{/.exec(arg);
      if (tmpl?.[1]) { found.set(tmpl[1], where); continue; }
      // The call regex stops at the first `)`, so a builder call arrives as `keyFor(pid` — take the
      // name before the paren, not the whole thing squashed. The first draft did the latter and
      // looked for a constant called `keyForpid`, which found nothing and reported nothing.
      const ident = (/^(\w+)/.exec(arg)?.[1]) ?? "";
      if (!ident) { unresolved.push(`${arg} (${where})`); continue; }
      // A bare identifier: a string constant declared in the same file.
      const named = new RegExp(String.raw`const\s+${ident}\s*=\s*["']([^"']+)["']`).exec(text);
      if (named?.[1]) { found.set(named[1], where); continue; }
      // A constant holding a TEMPLATE literal: `const RECENT_KEY = ` + backtick + `lib-recent:${pid}`.
      // This form is why the check exists rather than a hand-written list: `lib-recent:` is a real key
      // that my own manual enumeration of this app missed, and the scan surfaced it by refusing to
      // skip what it could not read.
      const namedTmpl = new RegExp(
        String.raw`const\s+${ident}\s*=\s*` + String.fromCharCode(96) + `([^${String.fromCharCode(96)}$]+)` + String.raw`\$\{`,
      ).exec(text);
      if (namedTmpl?.[1]) { found.set(namedTmpl[1], where); continue; }
      // A key BUILDER: `const keyFor = (pid: string) => ` then a template literal. Resolved to its
      // stem, because an unread key is an unclassified one — this file's own failure mode, one level
      // down. `String.raw` does NOT decode escapes, so the backtick is spliced in as a char rather
      // than written `\x60`, which the first draft did and silently matched nothing.
      const BT = String.fromCharCode(96);
      const built = new RegExp(
        String.raw`const\s+${ident}\s*=\s*\([^)]*\)\s*=>\s*` + BT + `([^${BT}$]+)` + String.raw`\$\{`,
      ).exec(text);
      if (built?.[1]) { found.set(built[1], where); continue; }
      unresolved.push(`${arg} (${where})`);
    }
  }
  return { found: [...found].map(([key, file]) => ({ key, file })), unresolved };
}

const { found: KEYS, unresolved: UNRESOLVED } = keys();

describe("clear-cache is measured against the keys the app really writes", () => {
  it("found the app's localStorage keys — a short list would make every check below vacuous", () => {
    expect(KEYS.length, `found ${KEYS.length} keys: ${KEYS.map((k) => k.key).join(", ")}`)
      .toBeGreaterThanOrEqual(25);
    // The two that cost the most if lost, named so a rename of either fails here rather than in
    // someone's browser. `aec-token` is the session; `aec-field-queue` is unsynced field work.
    const names = new Set(KEYS.map((k) => k.key));
    expect(names.has("aec-token"), "the session key moved — update clearCache and this test").toBe(true);
    expect(names.has("aec-field-queue"), "the field queue key moved").toBe(true);
  });

  /**
   * Silence is not coverage. An argument the scan cannot resolve is simply not seen, so every check
   * below would pass while saying nothing about that key — the original defect's shape, one level
   * down and inside the check meant to catch it. So an unresolved argument FAILS rather than skips.
   */
  it("resolved EVERY localStorage argument — an unread key is an unclassified key", () => {
    expect(UNRESOLVED,
      "teach `keys()` this form, or give the key a literal. Leaving it unread means Clear cached data "
      + "makes a decision about it that nothing here has checked.").toEqual([]);
  });

  it("EVERY declared cache prefix matches a key that exists", () => {
    const orphans = CACHE_KEY_PREFIXES.filter(
      (p) => !KEYS.some(({ key }) => key === p || key.startsWith(p)),
    );
    expect(orphans,
      "a prefix matching nothing is how the previous list came to hold five strings that had no "
      + "writer anywhere, for months, while reading as authoritative. Delete it, or fix its spelling.")
      .toEqual([]);
  });

  it("every key the app writes is classified, and nothing is cleared by accident", () => {
    const cleared = KEYS.filter(({ key }) => !isKeeper(key)).map(({ key, file }) => `${key} (${file})`);
    expect(cleared,
      "these would be DELETED by Clear cached data. That is correct only for a regenerable cache — "
      + "if it is a preference, a session or pending work, remove the prefix that matches it.")
      .toEqual([]);
  });

  /**
   * The anti-vacuity twin. With `CACHE_KEY_PREFIXES` empty, "nothing is cleared by accident" is
   * satisfied trivially — so this proves the scan can SEE a key that would be cleared, rather than
   * passing because it found nothing at all.
   */
  it("...and the scan can actually see a key it would clear", () => {
    const probe = (key: string) => ["portal-"].some((p) => key.startsWith(p));
    const wouldMatch = KEYS.filter(({ key }) => probe(key));
    expect(wouldMatch.length,
      "a hypothetical `portal-` cache prefix must match real keys; if it matches none, this scan is "
      + "not reading the source it thinks it is").toBeGreaterThan(3);
  });

  it("templated keys are collected by their stem, not skipped", () => {
    const names = new Set(KEYS.map((k) => k.key));
    for (const stem of TEMPLATE_STEMS) {
      expect(names.has(stem), `${stem}\${…} was not collected — the scan is blind to templated keys`)
        .toBe(true);
    }
  });
});

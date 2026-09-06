import { readFileSync, readdirSync } from "node:fs";
import { resolve } from "node:path";
import { describe, expect, it } from "vitest";

/**
 * LEVEL-PLACE — every placement call must say WHICH LEVEL, because omitting it is not neutral.
 *
 * `edit_core._first_storey(model, None)` returns the LOWEST storey, and `edit.place_type` containers
 * the occurrence there and sets its Z to that storey's elevation. So a placement with no `storey`
 * lands on the ground floor whatever level the user is working on.
 * `services/api/test_level_placement.py` pins that engine contract on a three-storey model.
 *
 * This is the other half: the engine can only honour a level the CALLER names. Two of the three
 * authoring paths always did — `finishDraft()` in `app.ts` injects `activeStorey`, and
 * `nl_ai._fill_context()` injects it server-side for the AI planner — while the library palette and
 * the "⊕ Place selected family" button sent none, so everything placed from the library went to the
 * ground floor.
 *
 * ## The population is DERIVED, from the client's own signatures
 *
 * The list of placement methods is read out of `src/api/authoring.ts` by looking for a method whose
 * parameter list declares a `storey`. A hand-written list would go stale the first time somebody adds
 * a placer — and a gate that names its own subjects can only ever check the ones its author
 * remembered. Deriving it means a new placement method is covered the day it is written.
 *
 * ## The check is on ARITY, not on the word "storey"
 *
 * A call site that passes the level through a lambda parameter — `(e, n, st) => api.placeFamily(pid,
 * key, [e, n], st)` — contains no literal "storey" anywhere. Grepping for the word would report that
 * correct call as a violation and pass a call that merely mentioned the word in a comment. So the
 * check counts ARGUMENTS: a call must reach at least the position at which its method declares
 * `storey`. That is what "the caller named a level" actually means at a call site.
 */

const WEB = resolve(process.cwd(), "src");
const AUTHORING = resolve(WEB, "api/authoring.ts");

/** Strip comments — a gate that greps source must, or its own documentation becomes a finding. */
const code = (src: string) => src.replace(/\/\*[\s\S]*?\*\//g, "").replace(/\/\/.*$/gm, "");

/** Methods declaring a `storey` parameter → the 1-based position it sits at. */
function placementMethods(): Map<string, number> {
  const src = code(readFileSync(AUTHORING, "utf8"));
  const found = new Map<string, number>();
  // `name(a: T, b: U, storey?: string | null) {` — the method-shorthand form the client uses.
  for (const m of src.matchAll(/^\s{2,}(?:async\s+)?([A-Za-z_$][\w$]*)\s*\(([^)]*)\)\s*[:{]/gm)) {
    const [, name, params] = m;
    if (!name || params === undefined) continue;
    const parts = splitArgs(params);
    // A parameter NAMED storey is positional. A parameter that merely CONTAINS one in its type is the
    // options-object form — `importContent(pid, file, opts: { …; storey?: string })` — where arity
    // says nothing at all, because the call passes three arguments whether or not the object names a
    // level. Anchoring on the parameter's own name is what separates the two; a test that matched
    // "storey" anywhere in the part derived importContent as arity-3 and then passed on every call,
    // which a mutation check caught and a green run would not have.
    const at = parts.findIndex((p) => /^storey\s*[?:]/.test(p.trim()));
    if (at >= 0) found.set(name, at + 1);
    else if (/\bstorey\s*\?\s*:/.test(params)) found.set(name, -1);
  }
  return found;
}

/** Split a parameter/argument list on top-level commas — brackets, braces, parens and strings held. */
function splitArgs(s: string): string[] {
  const out: string[] = [];
  let depth = 0, quote = "", cur = "";
  for (let i = 0; i < s.length; i++) {
    const c = s[i]!;
    if (quote) { cur += c; if (c === quote && s[i - 1] !== "\\") quote = ""; continue; }
    if (c === '"' || c === "'" || c === "`") { quote = c; cur += c; continue; }
    if ("([{<".includes(c)) depth++;
    if (")]}>".includes(c)) depth--;
    if (c === "," && depth === 0) { out.push(cur.trim()); cur = ""; continue; }
    cur += c;
  }
  if (cur.trim()) out.push(cur.trim());
  return out;
}

/** Every non-test .ts under src/viewer, recursively. */
function viewerFiles(dir: string, acc: string[] = []): string[] {
  for (const e of readdirSync(dir, { withFileTypes: true })) {
    const p = resolve(dir, e.name);
    if (e.isDirectory()) viewerFiles(p, acc);
    else if (e.name.endsWith(".ts") && !e.name.endsWith(".test.ts")) acc.push(p);
  }
  return acc;
}

/** Argument lists of every `…<method>(…)` call in `src`, brackets balanced. */
function callsTo(src: string, method: string): string[][] {
  const out: string[][] = [];
  const re = new RegExp(`\\.${method}\\s*\\(`, "g");
  for (let m = re.exec(src); m; m = re.exec(src)) {
    let depth = 1, i = m.index + m[0].length, quote = "";
    const start = i;
    for (; i < src.length && depth > 0; i++) {
      const c = src[i]!;
      if (quote) { if (c === quote && src[i - 1] !== "\\") quote = ""; continue; }
      if (c === '"' || c === "'" || c === "`") { quote = c; continue; }
      if (c === "(") depth++;
      else if (c === ")") depth--;
    }
    out.push(splitArgs(src.slice(start, i - 1)));
  }
  return out;
}

describe("LEVEL-PLACE — a placement names the level it lands on", () => {
  const methods = placementMethods();

  it("derived the placement methods from the client — else this measures nothing", () => {
    // The vacuity guard. A broken regex finds zero methods, then zero violations, and reports a
    // clean bill of health for a check that ran on an empty set.
    expect([...methods.keys()].sort(),
      "no client method declares a `storey` — the derivation broke, the code did not").not.toHaveLength(0);
    // The four the fix threaded, asserted PRESENT so the derivation cannot silently narrow.
    for (const n of ["placeFamily", "placeContent", "addFamily", "importContent"]) {
      expect([...methods.keys()], `${n} must be derived as a placement method`).toContain(n);
    }
  });

  it("every viewer call site passes the level", () => {
    const files = viewerFiles(resolve(WEB, "viewer"));
    expect(files.length).toBeGreaterThan(20);
    const bad: string[] = [];
    for (const f of files) {
      const src = code(readFileSync(f, "utf8"));
      const rel = f.slice(WEB.length + 1);
      for (const [method, pos] of methods) {
        for (const args of callsTo(src, method)) {
          if (pos === -1) {
            // options-object form: the last argument must mention a storey key.
            if (!/\bstorey\b/.test(args[args.length - 1] || "")) bad.push(`${rel}: ${method}(…) — no storey in its options`);
          } else if (args.length < pos || !args[pos - 1]) {
            bad.push(`${rel}: ${method}(…) passes ${args.length} args, storey is #${pos}`);
          }
        }
      }
    }
    expect(bad, "a placement with no level lands on the LOWEST storey, not on the one the user is on")
      .toEqual([]);
  });
});

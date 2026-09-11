import { execFileSync } from "node:child_process";
import { resolve } from "node:path";

import ts from "typescript";
import { describe, expect, it } from "vitest";

/**
 * RESPONSE-UNDECLARED — fields the server sends that the client never declares.
 *
 * The inverse of DEAD-FIELD, and the worse of the two: a field the client does not declare is
 * invisible to the compiler, the linter, and every audit built on these interfaces — including
 * `deadFieldScope.test.ts` next door, which can only reason about fields that are written down.
 *
 * ### Why this is type-aware, and why that is not a preference
 *
 * The roadmap records FOUR regex derivations of this axis that were each wrong in a way that looked
 * rigorous. The two that matter here are duals of one another, and a textual scan gets both wrong in
 * opposite directions:
 *
 * - **A type NAME can mean two things.** `MassingMetrics` is declared twice — the API response in
 *   `api/authoring.ts` (15 properties) and an unrelated vendor schema under `vendor/massingifc/`
 *   (9 properties, no field names in common). Matching by name conflates them.
 * - **A field NAME can live on two types.** `forecast_returns` is declared in `api/types.ts` for a
 *   different route entirely, so a tree-wide token scan sees the name, concludes "declared", and
 *   silently drops the real gap on `/draw-package`. The roadmap records exactly that miss.
 *
 * The call shape matched is `this.json<T>(path, opts?)`, which is every API method in `api/`. An
 * earlier draft also matched `.req`, a method that does not exist on `HttpCore` and never has: zero
 * call sites, so the branch could not have been exercised and its presence only widened the scan's
 * apparent scope. A branch with no occupant is a branch nobody has run.
 *
 * So the client half resolves each call site's type argument through the TypeScript checker —
 * `getPropertiesOfType` handles nested literals, named types and unions, none of which a scan can
 * follow — and the server half is a Python AST (`services/api/response_keys.py`), invoked here
 * because this is where the checker lives. That script is stdlib-only so it runs in the web CI job,
 * which installs no Python dependencies.
 *
 * ### It fails CLOSED
 *
 * A call site whose path or type the analyser cannot resolve is reported and FAILS, never skipped —
 * "found nothing" and "did not look" must not be the same output. `EXEMPT` is the one carve-out and
 * it is itself checked: an exemption that no longer matches a real call site fails too, so it cannot
 * outlive its reason.
 *
 * **The first draft of the path resolver handled only a single template literal**, and reported two
 * perfectly resolvable call sites as UNRESOLVED — a concatenation and a conditional query suffix.
 * That is this axis's own lesson occurring inside its own checker, which is why `pathOf` handles
 * `+` and `?:` and why `analyses a concatenated path` below exists.
 */

const WEB = resolve(process.cwd());                  // apps/web under vitest
const REPO = resolve(WEB, "../..");

/** Call sites the analyser cannot resolve, with the reason each is legitimately unresolvable.
 *  Asserted to still EXIST below — a stale exemption is a hole nobody is watching. */
const EXEMPT: Record<string, string> = {
  "src/api/httpCore.ts": "the `postJson` callback handed to the resumable uploader — a transport "
    + "shim whose path comes from its caller, so it has no route identity of its own",
};

/** The one route whose keys were reconciled by hand when this axis was opened. Both halves are
 *  derived independently, so a non-empty result here means the DERIVATION broke, not the product. */
const CONTROL = "GET /projects/{}/verification/coverage";

/** Every gap in the tree today. Asserted EXACTLY, in both directions: a new gap fails the build, and
 *  so does an entry here that is no longer a gap — which forces this list to shrink as they are
 *  fixed rather than rotting into a freeze-list nobody re-checked. (`KNOWN_UNCALLED` is the
 *  cautionary tale this shape is built against.) */
const KNOWN_GAPS: Record<string, string[]> = {
  "GET /reference/disciplines": ["disciplines", "masterformat_divisions", "uniformat_crosswalk"],
  "POST /projects/{}/modules/{}/views": ["mine", "owner", "scope"],
  "POST /proforma/scenarios": ["name", "result"],
  "POST /proforma/scenarios/{}/draw-package": ["forecast_returns", "g703_totals"],
  "DELETE /projects/{}/schedule/import-xer": ["removed_activities"],
  "GET /asset-rights/status": ["public_key"],
  "GET /auth/providers": ["saml"],
  "GET /cost/datasets": ["available_public"],
  "GET /projects/{}/publish/status": ["at"],
  "GET /projects/{}/safety/metrics": ["by_class"],
  "POST /proforma/solve": ["provenance"],
  "POST /projects/{}/bidding/packages/{}/invite": ["package"],
  "POST /projects/{}/models/from-upload": ["from_upload"],
  "POST /projects/{}/progress/actuals": ["source"],
  "PUT /projects/{}/view-templates": ["templates"],
};

/** A route path as the SERVER writes it, or null when it genuinely cannot be known statically. */
export function pathOf(n: ts.Node): string | null {
  if (ts.isStringLiteral(n) || ts.isNoSubstitutionTemplateLiteral(n)) return n.text;
  if (ts.isTemplateExpression(n)) {
    let out = n.head.text;
    for (const s of n.templateSpans) out += "{}" + s.literal.text;
    return out;
  }
  if (ts.isBinaryExpression(n) && n.operatorToken.kind === ts.SyntaxKind.PlusToken) {
    const l = pathOf(n.left), r = pathOf(n.right);
    return l === null || r === null ? null : l + r;
  }
  if (ts.isConditionalExpression(n)) {
    const a = pathOf(n.whenTrue), b = pathOf(n.whenFalse);
    if (a === null || b === null) return null;
    if (a === b) return a;
    // A branch contributing only a QUERY STRING does not change route identity, and the query is
    // stripped below anyway — so the two branches agree about the path even when they differ.
    const queryOnly = (s: string) => s === "" || s.startsWith("?") || s.startsWith("&");
    return queryOnly(a) && queryOnly(b) ? "" : null;
  }
  if (ts.isParenthesizedExpression(n)) return pathOf(n.expression);
  return null;
}

/** GET unless an options object literal names a string `method`. A computed method is UNKNOWN and
 *  fails, never assumed — assuming GET would compare a POST's keys against a GET's declaration. */
export function methodOf(arg: ts.Expression | undefined): string {
  if (arg === undefined) return "GET";
  if (!ts.isObjectLiteralExpression(arg)) return "UNKNOWN";
  for (const p of arg.properties) {
    if (ts.isPropertyAssignment(p) && p.name.getText() === "method") {
      const v = p.initializer;
      if (ts.isStringLiteral(v) || ts.isNoSubstitutionTemplateLiteral(v)) return v.text.toUpperCase();
      return "UNKNOWN";
    }
  }
  return "GET";
}

interface Site { rel: string; line: number; key: string; keys: string[]; opaque: boolean }
interface Unresolved { rel: string; line: number; why: string }

/** Walk one program's api call sites. Separated from the program build so the self-tests below can
 *  run it over a synthetic source without paying for the whole web tree. */
export function extract(program: ts.Program, root: string, relBase = root):
    { rows: Site[]; unresolved: Unresolved[] } {
  const checker = program.getTypeChecker();
  const rows: Site[] = [], unresolved: Unresolved[] = [];
  for (const sf of program.getSourceFiles()) {
    if (sf.isDeclarationFile || !sf.fileName.startsWith(root)) continue;
    if (sf.fileName.includes("/vendor/") || sf.fileName.endsWith(".test.ts")) continue;
    const visit = (node: ts.Node): void => {
      if (ts.isCallExpression(node) && ts.isPropertyAccessExpression(node.expression)
          && node.expression.name.text === "json"
          && node.arguments.length >= 1) {
        const rel = sf.fileName.slice(relBase.length).replace(/^\//, "");
        const line = sf.getLineAndCharacterOfPosition(node.getStart()).line + 1;
        const raw = pathOf(node.arguments[0]);
        const method = methodOf(node.arguments[1]);
        if (!node.typeArguments?.length) unresolved.push({ rel, line, why: "no type argument" });
        else if (raw === null) unresolved.push({ rel, line, why: "path not resolvable" });
        else if (method === "UNKNOWN") unresolved.push({ rel, line, why: "method not a literal" });
        else {
          const t = checker.getTypeFromTypeNode(node.typeArguments[0]);
          const keys = checker.getPropertiesOfType(t).map((p) => p.getName()).sort();
          // `Record<string, unknown>` resolves to ZERO named properties. That is neither "declares
          // nothing" nor "declares everything": it type-checks while naming nothing, so a field
          // under it is still invisible to every audit built on these interfaces. Its own bucket.
          const opaque = keys.length === 0 && !!(checker.getIndexTypeOfType(t, ts.IndexKind.String)
            ?? checker.getIndexTypeOfType(t, ts.IndexKind.Number));
          rows.push({ rel, line, key: `${method} ${raw.split("?")[0]}`, keys, opaque });
        }
      }
      ts.forEachChild(node, visit);
    };
    visit(sf);
  }
  return { rows, unresolved };
}

/** A one-file program over synthetic source, for the self-tests. */
function syntheticProgram(source: string): { program: ts.Program; root: string } {
  const root = "/synthetic";
  const file = `${root}/probe.ts`;
  const sf = ts.createSourceFile(file, source, ts.ScriptTarget.ES2022, true);
  const host: ts.CompilerHost = {
    getSourceFile: (name) => (name === file ? sf : undefined),
    getDefaultLibFileName: () => "lib.d.ts",
    writeFile: () => undefined,
    getCurrentDirectory: () => root,
    getCanonicalFileName: (f) => f,
    useCaseSensitiveFileNames: () => true,
    getNewLine: () => "\n",
    fileExists: (name) => name === file,
    readFile: (name) => (name === file ? source : undefined),
  };
  return { program: ts.createProgram([file], { noLib: true, noResolve: true }, host), root };
}

describe("RESPONSE-UNDECLARED", () => {
  // The whole-tree program is built once: ~11s, 1,892 source files.
  const cfg = ts.readConfigFile(`${WEB}/tsconfig.json`, ts.sys.readFile);
  const parsed = ts.parseJsonConfigFileContent(cfg.config, ts.sys, WEB);
  const program = ts.createProgram(parsed.fileNames, parsed.options);
  // Filter on src/, but report paths from apps/web — so a failure names `src/api/x.ts`, which is
  // what a reader greps for, and what EXEMPT is keyed on.
  const { rows, unresolved } = extract(program, `${WEB}/src`, WEB);

  const server: Record<string, { keys: string[]; literal: boolean }> = JSON.parse(
    execFileSync("python3", [resolve(REPO, "services/api/response_keys.py")],
                 { cwd: REPO, encoding: "utf8", maxBuffer: 64 * 1024 * 1024 }));

  const declared = new Map<string, Set<string>>();
  const opaque = new Set<string>();
  for (const r of rows) {
    if (!declared.has(r.key)) declared.set(r.key, new Set());
    for (const k of r.keys) declared.get(r.key)!.add(k);
    if (r.opaque) opaque.add(r.key);
  }

  const dictRoutes = Object.entries(server).filter(([, v]) => v.literal);
  const gaps = new Map<string, string[]>();
  for (const [route, v] of dictRoutes) {
    const decl = declared.get(route);
    if (!decl || opaque.has(route)) continue;           // no typed caller, or opaque by declaration
    const missing = v.keys.filter((k) => !decl.has(k)).sort();
    if (missing.length) gaps.set(route, missing);
  }

  // THE VACUITY GUARDS. Every assertion below is a statement about two populations; without them
  // there is nothing to compare and a pass would mean "did not look".
  it("both halves of the derivation found their subject", () => {
    expect(rows.length, "typed client call sites").toBeGreaterThan(400);
    expect(dictRoutes.length, "server routes returning a dict literal").toBeGreaterThan(150);
  }, 120_000);

  it("every client call site resolves, or is a named exemption that still exists", () => {
    const unexpected = unresolved.filter((u) => !(u.rel in EXEMPT));
    expect(unexpected, `unresolved call sites — the analyser must not silently skip a site:\n`
      + unexpected.map((u) => `  ${u.rel}:${u.line} (${u.why})`).join("\n")).toEqual([]);
    // and the other direction: an exemption whose site is gone is a hole nobody is watching
    for (const rel of Object.keys(EXEMPT))
      expect(unresolved.some((u) => u.rel === rel),
             `EXEMPT names ${rel}, which no longer has an unresolvable call site — delete it`).toBe(true);
  }, 120_000);

  it("the hand-reconciled control route has no undeclared keys", () => {
    expect(server[CONTROL]?.literal, `${CONTROL} must still return a dict literal`).toBe(true);
    expect(declared.get(CONTROL), `${CONTROL} must still have a typed client call site`).toBeDefined();
    expect(gaps.get(CONTROL) ?? [], "the two halves disagree on a route reconciled by hand — the "
      + "derivation is broken, not the product").toEqual([]);
  }, 120_000);

  it("the tree's undeclared keys are exactly the known ones", () => {
    const actual = Object.fromEntries([...gaps.entries()].sort());
    const known = Object.fromEntries(Object.entries(KNOWN_GAPS).map(([k, v]) => [k, [...v].sort()]).sort());
    expect(actual, "a route's response keys and its client declaration disagree. If you ADDED a key "
      + "to a route, declare it on the client type too; if you FIXED one, delete it from KNOWN_GAPS.")
      .toEqual(known);
  }, 120_000);

  // SELF-TESTS. The four assertions above all pass if `extract` silently stops finding anything, so
  // these run it over synthetic source where the answer is known. They survive fixing every real gap.
  it("detects an undeclared key", () => {
    const { program: p, root } = syntheticProgram(
      `declare const c: any;\nfunction f() { return c.json<{ a: number }>("/x"); }\n`);
    const { rows: r } = extract(p, root);
    expect(r.map((x) => x.key)).toEqual(["GET /x"]);
    expect(r[0].keys).toEqual(["a"]);                   // `b` returned by a server would be a gap
  });

  it("analyses a concatenated path, which the first draft reported as unresolvable", () => {
    const { program: p, root } = syntheticProgram(
      "declare const c: any;\ndeclare const q: string;\n"
      + "function f() { return c.json<{ a: number }>(`/p/${q}/r` + `?k=1`); }\n");
    const { rows: r, unresolved: u } = extract(p, root);
    expect(u).toEqual([]);
    expect(r.map((x) => x.key)).toEqual(["GET /p/{}/r"]);
  });

  it("reports a non-literal path rather than guessing one", () => {
    const { program: p, root } = syntheticProgram(
      "declare const c: any;\ndeclare const p: string;\nfunction f() { return c.json<{ a: 1 }>(p); }\n");
    const { rows: r, unresolved: u } = extract(p, root);
    expect(r).toEqual([]);
    expect(u.map((x) => x.why)).toEqual(["path not resolvable"]);
  });

  it("refuses to assume GET when the method is computed", () => {
    const { program: p, root } = syntheticProgram(
      "declare const c: any;\ndeclare const m: string;\n"
      + 'function f() { return c.json<{ a: 1 }>("/x", { method: m }); }\n');
    const { unresolved: u } = extract(p, root);
    expect(u.map((x) => x.why)).toEqual(["method not a literal"]);
  });
});

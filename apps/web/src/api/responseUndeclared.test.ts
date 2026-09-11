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
};

/** Routes the gate compares whose server key set is a LOWER BOUND — the response literal carries a
 *  `**spread` or a computed key, so not every key it sends can be named statically. Their
 *  declared-key gaps below are still real; what is NOT knowable is whether there are MORE.
 *
 *  Pinned exactly, both ways, for the same reason as `KNOWN_GAPS`: a new one must fail rather than
 *  join a silent majority, and one that becomes fully knowable must fail so it leaves this list.
 *  Closing a route's spread is therefore a visible improvement, not a no-op. */
const INCOMPLETE_LOWER_BOUND: string[] = [
  "GET /agent-packs/runs",
  // Added 2026-09-11 by giving `/cost/datasets/import` its first client method: the route returns
  // `{**cost_db.dataset_dict(ds), "warning": ...}`, so only `warning` can be named statically. It
  // appears here for a good reason — this gate can only see a route that HAS a typed call site, and
  // until now it had none at all.
  "POST /cost/datasets/import",
  // Added 2026-09-11 with LOD-PROXY, the same shape one route over: the handler returns
  // `{**report, "stored": ..., "key": ..., "next": ...}` on success and `{**report, "stored": False}`
  // on a refusal, so only the four literal keys can be named. `report` comes from
  // `lod.build_storey_proxy`, whose shape differs between those two branches — which is the
  // reason the client types `elements_replaced`, `storeys_proxied` and `reason` as OPTIONAL
  // rather than pretending one branch's keys are present in both.
  "POST /projects/{}/model/lod/proxy",
  "GET /projects/{}/agent-packs",
  "GET /projects/{}/ai/risk-summary",
  "GET /projects/{}/compliance/expiring",
  "GET /projects/{}/drawings/sync-status",
  "GET /projects/{}/elements/color-by",
  "GET /projects/{}/model/lod/census",
  "POST /proforma/scenarios/{}/review",
  "POST /proforma/solve",
  "POST /projects/{}/ai/ask",
  "POST /projects/{}/ai/draft-rfi",
  "POST /projects/{}/ai/estimate",
  "POST /projects/{}/ai/triage-rfi",
  "POST /projects/{}/cost/tm",
  "POST /projects/{}/edit/graph",
  "POST /projects/{}/model/equipment/spec-check",
  "POST /projects/{}/proforma/solve",
  "POST /projects/{}/progress/actuals",
];

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

/** GET unless an options object literal names a string `method`. Anything the analyser cannot read
 *  statically is UNKNOWN and FAILS, never assumed — a POST silently recorded as GET would be
 *  compared against a GET route's declaration, or match no route at all and be skipped, which is
 *  undeclared POST keys walking straight past the gate.
 *
 *  Two shapes the first draft got wrong, neither with an occupant in the tree today. That is the
 *  argument for fixing them rather than against it: a fail-open with no current occupant is one
 *  ordinary commit away from having one, and nothing would go red when it arrives.
 *
 *  * A QUOTED key. `p.name.getText()` on `{"method": "POST"}` returns the six characters
 *    `"method"` INCLUDING the quotes, so it never equalled `method` and fell through to GET.
 *    The name node is read by kind now, not by source text.
 *  * A SPREAD. `{...opts}` is a `SpreadAssignment`, which is not a `PropertyAssignment`, so the
 *    loop skipped it and returned GET — while the spread may both introduce `method` and overwrite
 *    one written literally beside it. Any spread makes the method unknowable here. */
export function methodOf(arg: ts.Expression | undefined): string {
  if (arg === undefined) return "GET";
  if (!ts.isObjectLiteralExpression(arg)) return "UNKNOWN";
  let found: string | null = null;
  for (const p of arg.properties) {
    if (ts.isSpreadAssignment(p)) return "UNKNOWN";       // can introduce or overwrite `method`
    if (!ts.isPropertyAssignment(p)) continue;            // getter/setter/shorthand: names nothing
    const name = ts.isIdentifier(p.name) || ts.isStringLiteral(p.name) ? p.name.text : null;
    if (name === null) return "UNKNOWN";                  // computed key — may BE `method`
    if (name !== "method") continue;
    const v = p.initializer;
    if (!ts.isStringLiteral(v) && !ts.isNoSubstitutionTemplateLiteral(v)) return "UNKNOWN";
    found = v.text.toUpperCase();                         // keep scanning: a later spread still wins
  }
  return found ?? "GET";
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
      const pathArg = ts.isCallExpression(node) ? node.arguments[0] : undefined;
      if (ts.isCallExpression(node) && ts.isPropertyAccessExpression(node.expression)
          && node.expression.name.text === "json" && pathArg !== undefined) {
        const rel = sf.fileName.slice(relBase.length).replace(/^\//, "");
        const line = sf.getLineAndCharacterOfPosition(node.getStart()).line + 1;
        const raw = pathOf(pathArg);
        const method = methodOf(node.arguments[1]);
        // Bound once rather than indexed twice: `typeArguments.length` does not narrow
        // `typeArguments[0]` under `noUncheckedIndexedAccess`, and a checker that indexes blind
        // is the shape this whole file argues against.
        const typeArg = node.typeArguments?.[0];
        if (typeArg === undefined) unresolved.push({ rel, line, why: "no type argument" });
        else if (raw === null) unresolved.push({ rel, line, why: "path not resolvable" });
        else if (method === "UNKNOWN") unresolved.push({ rel, line, why: "method not a literal" });
        else {
          const t = checker.getTypeFromTypeNode(typeArg);
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

  const server: Record<string, { keys: string[]; literal: boolean; complete: boolean }> = JSON.parse(
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
  // Routes whose key set is a LOWER BOUND, not the whole truth: the literal carries a `**spread` or
  // a computed key, so `response_keys.py` marks it `complete: false`. Comparing only the keys it
  // COULD name would let `{**extra, "id": id}` pass whenever `id` is declared, while `extra` sends
  // anything at all — the exact fail-open this gate exists to catch, inside the gate. They are
  // tracked, not silently compared as if complete.
  const incomplete = dictRoutes
    .filter(([route, v]) => !v.complete && declared.has(route) && !opaque.has(route))
    .map(([route]) => route).sort();
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

  it("every route whose key set is only a lower bound is tracked as one", () => {
    expect(incomplete, "a route's response literal carries a `**spread` or a computed key, so the "
      + "gate can compare only the keys it can NAME. If you ADDED a spread, add the route here; if "
      + "you REMOVED one, delete it — the comparison became complete and that is worth recording.")
      .toEqual([...INCOMPLETE_LOWER_BOUND].sort());
  }, 120_000);

  // SELF-TESTS. The four assertions above all pass if `extract` silently stops finding anything, so
  // these run it over synthetic source where the answer is known. They survive fixing every real gap.
  it("detects an undeclared key", () => {
    const { program: p, root } = syntheticProgram(
      `declare const c: any;\nfunction f() { return c.json<{ a: number }>("/x"); }\n`);
    const { rows: r } = extract(p, root);
    // Asserted as one row rather than `r[0].keys` — the index is only safe because of the line
    // above, and a test that leans on that ordering is a test that breaks for the wrong reason.
    expect(r.map((x) => ({ key: x.key, keys: x.keys })))
      .toEqual([{ key: "GET /x", keys: ["a"] }]);       // `b` returned by a server would be a gap
  });

  it("analyses a concatenated path, which the first draft reported as unresolvable", () => {
    const { program: p, root } = syntheticProgram(
      "declare const c: any;\ndeclare const q: string;\n"
      + "function f() { return c.json<{ a: number }>(`/p/${q}/r` + `?k=1`); }\n");
    const { rows: r, unresolved: u } = extract(p, root);
    expect(u).toEqual([]);
    expect(r.map((x) => x.key)).toEqual(["GET /p/{}/r"]);
  });

  it("reads a QUOTED method key, which the first draft defaulted to GET", () => {
    const { program: p, root } = syntheticProgram(
      'declare const c: any;\n'
      + 'function f() { return c.json<{ a: 1 }>("/x", { "method": "POST" }); }\n');
    const { rows: r, unresolved: u } = extract(p, root);
    expect(u).toEqual([]);
    expect(r.map((x) => x.key)).toEqual(["POST /x"]);   // was "GET /x": quotes are part of getText()
  });

  it("refuses to guess when the options object SPREADS, which can introduce or overwrite method", () => {
    const { program: p, root } = syntheticProgram(
      'declare const c: any;\ndeclare const o: any;\n'
      + 'function f() { return c.json<{ a: 1 }>("/x", { method: "POST", ...o }); }\n');
    const { rows: r, unresolved: u } = extract(p, root);
    expect(r).toEqual([]);
    expect(u.map((x) => x.why)).toEqual(["method not a literal"]);
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

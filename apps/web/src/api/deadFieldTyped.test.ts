import { readFileSync, readdirSync, statSync } from "node:fs";
import { join, resolve } from "node:path";

import ts from "typescript";
import { describe, expect, it } from "vitest";

/**
 * DEAD-FIELD, type-aware — the pass `deadFieldScope.test.ts` names as its own unblocking step.
 *
 * That file measures the IDENTIFIER-based derivation and argues it cannot support a gate: it matches
 * a field by NAME across the tree, so `SpatialNode.elevation` counts as read because storeys, drawing
 * grids, GIS overlays and draft gizmos all happen to have an `elevation`. Its closing instruction is
 * to rewrite it *"rather than relaxing the assertion"* once a type-aware derivation exists. This is
 * that derivation. It resolves every property access, destructuring binding and string-keyed element
 * access through the TypeScript checker to the `PropertySignature` that declares it — so a reader
 * counts only when it is reading THAT interface's field.
 *
 * ### Neither method bounds the population, and saying so is the point
 *
 * The typed pass is not simply better. Measured across both:
 *
 * | | |
 * |---|---|
 * | identifier-unread that the checker finds READ | **0** — the old bucket was a sound LOWER BOUND |
 * | typed-unread that the identifier method called "read" | ~556 — pure name collisions |
 * | of those, leaf name present as a STRING LITERAL outside `api/` | ~308 |
 *
 * There is a THIRD limit that no checker can remove: a field read through `Object.entries(resp)` or
 * a spread never has its name appear at all. That residual is measured below rather than described,
 * because a caveat held only in prose is the thing this repository keeps paying for.
 *
 * That first row is the typed pass's OWN blind spot, in the opposite direction: this codebase reads
 * plenty of fields through string keys in column configs, and no checker can see those. So the honest
 * output is a PARTITION, not a number — and the sound candidate set is the intersection: no typed
 * reader AND no string-literal reader. Reporting the typed count alone would have been the same
 * mistake the identifier method makes, with the sign flipped.
 *
 * ### The positive control is not optional
 *
 * Every derivation in this repository that reported a clean tree did so because a predicate quietly
 * excluded the thing it was looking for. So this asserts a KNOWN-RENDERED field resolves to a reader
 * before it is allowed to report anything unread: if the checker stops resolving — a moved tsconfig,
 * a changed API, a typo in the walk — every field would look unread and the population would balloon
 * rather than vanish, which is the failure mode that looks like a finding.
 */

const WEB = resolve(process.cwd(), "src");
const API = resolve(WEB, "api");
const isApiDecl = (f: string) =>
  f.startsWith(API) && !f.endsWith("schema.d.ts") && !f.endsWith(".test.ts");
const isTest = (f: string) => f.endsWith(".test.ts") || f.endsWith(".test.tsx");

/** One typed derivation over the whole program. Built once — `createProgram` is the expensive part. */
function derive() {
  const cfgPath = ts.findConfigFile(process.cwd(), ts.sys.fileExists, "tsconfig.json");
  if (!cfgPath) throw new Error("no tsconfig.json — the derivation cannot run, which is not 'clean'");
  const parsed = ts.parseJsonConfigFileContent(
    ts.readConfigFile(cfgPath, ts.sys.readFile).config, ts.sys, process.cwd());
  const program = ts.createProgram(parsed.fileNames, parsed.options);
  const checker = program.getTypeChecker();

  /** declaring node -> "Interface.path", including NESTED object literals and array element types.
   *  Anchoring on top-level members only is how the identifier version missed
   *  `ResponsibilityMatrix.validation.*`, this axis's one load-bearing defect. */
  const nodeToKey = new Map<ts.Node, string>();
  const keyToFile = new Map<string, string>();
  const collect = (members: ts.NodeArray<ts.TypeElement>, path: string, file: string) => {
    for (const m of members) {
      if (!ts.isPropertySignature(m) || !m.name) continue;
      const key = `${path}.${m.name.getText()}`;
      nodeToKey.set(m, key);
      if (!keyToFile.has(key)) keyToFile.set(key, file);
      const t = m.type;
      if (t && ts.isTypeLiteralNode(t)) collect(t.members, key, file);
      else if (t && ts.isArrayTypeNode(t) && ts.isTypeLiteralNode(t.elementType))
        collect(t.elementType.members, `${key}[]`, file);
    }
  };
  for (const sf of program.getSourceFiles()) {
    if (!isApiDecl(sf.fileName)) continue;
    const visit = (n: ts.Node): void => {
      if (ts.isInterfaceDeclaration(n)
          && n.modifiers?.some((m) => m.kind === ts.SyntaxKind.ExportKeyword))
        collect(n.members, n.name.text, sf.fileName);
      ts.forEachChild(n, visit);
    };
    visit(sf);
  }

  const readers = new Map<string, Set<string>>();
  const note = (sym: ts.Symbol | undefined, f: string) => {
    for (const d of sym?.declarations ?? []) {
      const k = nodeToKey.get(d);
      if (k === undefined) continue;
      if (!readers.has(k)) readers.set(k, new Set());
      readers.get(k)!.add(f);
    }
  };
  // TWO OF THE THREE READ SHAPES BELOW CURRENTLY RESOLVE NOTHING, and saying so is better than
  // letting them look load-bearing. Measured by removing each and re-counting: the read population is
  // **999 with all three, 999 without the destructuring branch, and 999 without the string-key element
  // access** — every destructured or bracket-indexed read in this tree also has a dotted read
  // somewhere, so neither branch clears a field on its own today. They stay because their value is
  // PROSPECTIVE: a future field read *only* by `const { x } = resp` would otherwise be reported unread,
  // which is a false candidate rather than a missed defect. Neither is covered by a mutation, and that
  // is a disclosure, not an oversight — an unexercised branch presented as tested is how a check rots.
  for (const sf of program.getSourceFiles()) {
    const f = sf.fileName;
    if (!f.startsWith(WEB) || f.includes("node_modules")) continue;
    const visit = (n: ts.Node): void => {
      if (ts.isPropertyAccessExpression(n)) note(checker.getSymbolAtLocation(n.name), f);
      else if (ts.isElementAccessExpression(n) && n.argumentExpression
               && ts.isStringLiteralLike(n.argumentExpression))
        note(checker.getSymbolAtLocation(n.argumentExpression), f);
      else if (ts.isBindingElement(n)) {
        const nm = n.propertyName ?? n.name;
        if (ts.isIdentifier(nm) || ts.isStringLiteralLike(nm)) note(checker.getSymbolAtLocation(nm), f);
      }
      ts.forEachChild(n, visit);
    };
    visit(sf);
  }
  return { keyToFile, readers };
}

/** Every string literal appearing outside `api/` — the typed pass's blind spot, made measurable. */
function stringLiterals(): Set<string> {
  const walk = (dir: string, out: string[] = []): string[] => {
    for (const e of readdirSync(dir)) {
      const p = join(dir, e);
      if (statSync(p).isDirectory()) walk(p, out);
      else if (p.endsWith(".ts") || p.endsWith(".tsx")) out.push(p);
    }
    return out;
  };
  const out = new Set<string>();
  for (const f of walk(WEB)) {
    if (f.startsWith(API) || isTest(f)) continue;
    for (const m of readFileSync(f, "utf-8").matchAll(/["'`]([A-Za-z_]\w*)["'`]/g)) out.add(m[1]!);
  }
  return out;
}

/** Interfaces named in a file that ALSO reads objects dynamically — `Object.keys/entries/values` or
 *  a spread. No static analysis can clear a field consumed that way: the property name never appears.
 *  This is the derivation's SECOND blind spot, and unlike the first it cannot be narrowed by a better
 *  checker — it is a limit of static reading, not of this implementation. */
function dynamicallyReadInterfaces(): Set<string> {
  const walk = (dir: string, out: string[] = []): string[] => {
    for (const e of readdirSync(dir)) {
      const p = join(dir, e);
      if (statSync(p).isDirectory()) walk(p, out);
      else if (p.endsWith(".ts") || p.endsWith(".tsx")) out.push(p);
    }
    return out;
  };
  const out = new Set<string>();
  for (const f of walk(WEB)) {
    if (f.startsWith(API) || isTest(f)) continue;
    const src = readFileSync(f, "utf-8");
    if (!/Object\.(keys|entries|values)|\.\.\./.test(src)) continue;
    for (const m of src.matchAll(/\b([A-Z]\w+)\b/g)) out.add(m[1]!);
  }
  return out;
}

const { keyToFile, readers } = derive();
const lits = stringLiterals();
const dynIfaces = dynamicallyReadInterfaces();
const readersOutsideDecl = (k: string) =>
  [...(readers.get(k) ?? [])].filter((r) => r !== keyToFile.get(k));

describe("DEAD-FIELD: the type-aware derivation", () => {
  it("RESOLVES — a field the app demonstrably renders comes back READ (the positive control)", () => {
    // Before any unread count may be believed. `Appraisal.reconciliation.value` is the opinion of
    // value printed at the top of the valuation tab; if the checker stopped resolving, this reports
    // unread and every other field would too — a broken derivation that looks like a huge finding.
    expect(keyToFile.has("Appraisal.reconciliation.value"),
      "the declaration walk no longer finds a known interface member").toBe(true);
    expect(readersOutsideDecl("Appraisal.reconciliation.value").length,
      "the checker resolved NO reader for a field the valuation panel renders — the derivation is "
      + "broken, and an unread count taken from it would be fiction").toBeGreaterThan(0);
  });

  it("sees NESTED members, which the identifier derivation's two-space anchor could not", () => {
    // `ResponsibilityMatrix.validation.*` is this axis's one load-bearing defect and it was nested.
    const nested = [...keyToFile.keys()].filter((k) => k.split(".").length >= 3);
    expect(nested.length).toBeGreaterThan(100);
    expect(keyToFile.has("Appraisal.reconciliation.approaches_used")).toBe(true);
  });

  it("SpatialNode.elevation has no typed reader — the collision the old derivation could not see", () => {
    // `deadFieldScope.test.ts` asserts the mirror of this: >10 files reference the IDENTIFIER. Both
    // are true at once, and that pair IS the argument for the type-aware pass.
    expect(keyToFile.has("SpatialNode.elevation")).toBe(true);
    expect(readersOutsideDecl("SpatialNode.elevation")).toEqual([]);
  });

  it("reports a PARTITION, not a number — the typed pass has its own blind spot", () => {
    const all = [...keyToFile.keys()];
    const typedUnread = all.filter((k) => readersOutsideDecl(k).length === 0);
    const leaf = (k: string) => k.split(".").pop()!.replace(/\[\]$/, "");
    const alsoNoLiteral = typedUnread.filter((k) => !lits.has(leaf(k)));

    // Bands, not pins: ordinary work adds interfaces and must not fail the build. What these catch
    // is the derivation itself breaking — a silently-empty population reporting a clean axis.
    expect(all.length, "declared members").toBeGreaterThan(1_000);
    expect(typedUnread.length).toBeGreaterThan(100);
    expect(typedUnread.length).toBeLessThan(all.length * 0.6);

    // The blind spot is REAL and is asserted so it cannot be quietly forgotten: a large share of the
    // typed-unread set has its leaf name as a string literal outside api/, which is how this codebase's
    // column configs read a field. Those are candidates the checker cannot clear.
    expect(alsoNoLiteral.length).toBeLessThan(typedUnread.length);
    expect(alsoNoLiteral.length,
      "the sound set is the INTERSECTION of both methods, and it is smaller than either")
      .toBeGreaterThan(50);

    // THE SECOND BLIND SPOT, measured rather than described. A reviewer asked whether this audit
    // overstates unused fields when values are read through dynamic paths. It can, it is bounded
    // here, and unlike the string-literal gap this one CANNOT be closed by a better checker: a field
    // consumed via `Object.entries(resp)` or a spread never has its name appear anywhere.
    const iface = (k: string) => k.split(".")[0]!;
    const atRisk = alsoNoLiteral.filter((k) => dynIfaces.has(iface(k)));
    expect(atRisk.length,
      "no candidate's interface is touched by a dynamic reader — that is implausible in this "
      + "codebase and means the dynamic-read scan stopped matching, which would make the sound set "
      + "look cleaner than it is").toBeGreaterThan(0);
    expect(atRisk.length,
      "the residual is now most of the candidate set, so the sound set is no longer sound — "
      + "re-derive before quoting it").toBeLessThan(alsoNoLiteral.length);
  });

  it("the six fields the valuation panel was fixed to render now resolve to a reader", () => {
    // The defects this derivation found, pinned as READ so a future edit that drops one of them from
    // the panel fails HERE as well as in proforma.render.test.ts. Two independent derivations must
    // now be evaded, which is the argument the seeding-sweep pair already made.
    for (const k of ["Appraisal.reconciliation.approaches_used",
                     "Appraisal.sales_comparison.implied_cap_rate",
                     "Appraisal.sales_comparison.median_price_per_unit",
                     "Appraisal.cost.depreciation_pct",
                     "Appraisal.inputs.has_proforma",
                     "Appraisal.excluded_comparables"]) {
      expect(keyToFile.has(k), `${k} is no longer declared — re-derive before trusting this`).toBe(true);
      expect(readersOutsideDecl(k).length, `${k} lost its reader`).toBeGreaterThan(0);
    }
  });
});

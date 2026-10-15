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

/** TypeScript reports every `sf.fileName` with forward slashes on every OS, while `resolve` and
 *  `join` return backslashes on Windows — so every path compared below goes through this first.
 *  Before it, `startsWith(WEB)` was false for EVERY source file on Windows and the derivation found
 *  nothing; the positive control caught it, which is the case for having one. (`ts.sys.resolvePath`
 *  does not help: it hands the backslashed path back unchanged.) */
const posix = (p: string) => p.replace(/\\/g, "/");
const WEB = posix(resolve(process.cwd(), "src"));
const API = `${WEB}/api`;
const isApiDecl = (f: string) =>
  f.startsWith(API) && !f.endsWith("schema.d.ts") && !f.endsWith(".test.ts");
const isTest = (f: string) => f.endsWith(".test.ts") || f.endsWith(".test.tsx");

/** Prefix marking a key that came from an inline `this.json<{…}>` type argument rather than a named
 *  declaration. Deliberately dot-free: the partition below splits keys on "." to get the declaring
 *  shape and the leaf field name, and a prefix carrying a dot would break both. */
const INLINE = "INLINE:";
const isInline = (k: string) => k.startsWith(INLINE);

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
  // DEADFIELD-INLINE. Until 2026-10-14 this walk took EXPORTED INTERFACE declarations and nothing
  // else, and the population that came out was reported as the axis's number. Measured: 562 of 706
  // `this.json<T>` call sites declare their response as an inline type literal rather than by
  // reference, so **5,999 of the tree's 8,603 declared response-field keys were outside the
  // population entirely** — 2,696 of them with no typed reader, 1,203 sound candidates against the
  // 269 this file reported. WAIVER-FLAT's `status` and `waived_conditional` sat in exactly that
  // gap: declared on the client type, read by nothing, and flattening a three-state release verdict
  // into one column on a lien screen.
  //
  // *A population derived from one declaration FORM reports confidently on whatever happens to use
  // that form.* The walk now takes three forms and labels where each key came from, because the two
  // buckets are not interchangeable: a named interface is a shape somebody intends to share, and an
  // inline type literal is one route's response. The partition assertions below stay scoped to
  // NAMED keys so their meaning does not shift under them, and the inline bucket gets its own
  // ratchet — converting a response type from inline to named lowers it, and adding to the blind
  // spot costs an explicit number change rather than nothing.
  for (const sf of program.getSourceFiles()) {
    if (!isApiDecl(sf.fileName)) continue;
    const base = sf.fileName.split("/").pop()!.replace(/\.ts$/, "");
    const visit = (n: ts.Node): void => {
      const exported = ts.canHaveModifiers(n)
        && !!ts.getModifiers(n)?.some((m) => m.kind === ts.SyntaxKind.ExportKeyword);
      if (ts.isInterfaceDeclaration(n) && exported)
        collect(n.members, n.name.text, sf.fileName);
      // An exported `type X = { … }` is as named and as shared as an interface, and was excluded
      // for being a different node kind. Seven in the tree.
      else if (ts.isTypeAliasDeclaration(n) && exported && ts.isTypeLiteralNode(n.type))
        collect(n.type.members, n.name.text, sf.fileName);
      if (ts.isCallExpression(n) && ts.isPropertyAccessExpression(n.expression)
          && String(n.expression.name.escapedText || "") === "json"
          && n.typeArguments?.length === 1) {
        // `escapedText`, not `getText()`: a synthesized node from a .d.ts has no source file and
        // `getText()` throws on it, which killed the first draft of the measurement.
        const ta = n.typeArguments[0]!;
        const line = sf.getLineAndCharacterOfPosition(n.getStart(sf)).line + 1;
        // No dot in the prefix, so `k.split(".")[0]` still yields one token and `leaf()` still
        // yields the field name — both are relied on by the partition below.
        const label = `${INLINE}${base}:${line}`;
        if (ts.isTypeLiteralNode(ta)) collect(ta.members, label, sf.fileName);
        else if (ts.isArrayTypeNode(ta) && ts.isTypeLiteralNode(ta.elementType))
          collect(ta.elementType.members, `${label}[]`, sf.fileName);
      }
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

/** Every .ts/.tsx under src/, in TypeScript's slash form so `startsWith(API)` below compares like
 *  with like. The two scans that read it once walked separately and un-normalised, which matched
 *  only because `API` was backslashed too; normalising one side alone lets api/ into both scans and
 *  every assertion still passes — which is why the exclusion's reach is asserted below. */
const walk = (dir: string, out: string[] = []): string[] => {
  for (const e of readdirSync(dir)) {
    const p = join(dir, e);
    if (statSync(p).isDirectory()) walk(p, out);
    else if (p.endsWith(".ts") || p.endsWith(".tsx")) out.push(posix(p));
  }
  return out;
};
const webFiles = walk(WEB);

/** Every string literal appearing outside `api/` — the typed pass's blind spot, made measurable. */
function stringLiterals(): Set<string> {
  const out = new Set<string>();
  for (const f of webFiles) {
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
  const out = new Set<string>();
  for (const f of webFiles) {
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

  it("the scans' api/ exclusion reaches every file the declarations came from", () => {
    // The two scans walk the FILESYSTEM; the declarations come from the CHECKER. Unless both spell a
    // path the same way, `startsWith(API)` excludes nothing from the scans and api/'s own literals
    // clear candidates they should not — measured on Windows with the walk left un-normalised: the
    // sound set fell 386 → 348 and every other assertion in this file still passed.
    const declFiles = new Set(keyToFile.values());
    const excluded = new Set(webFiles.filter((f) => f.startsWith(API)));
    expect(declFiles.size).toBeGreaterThan(0);
    expect([...declFiles].filter((f) => !excluded.has(f)),
      "declaring files the scans' api/ exclusion does not match").toEqual([]);
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
    // NAMED keys only. DEADFIELD-INLINE widened the walk to inline response literals, and folding
    // 5,999 of them into these bands would have left every assertion green while changing what the
    // partition is a partition OF — the quietest way for a check to stop meaning what it says.
    const all = [...keyToFile.keys()].filter((k) => !isInline(k));
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

  it("the inline blind spot is bounded, and shrinking it is the only free direction", () => {
    // DEADFIELD-INLINE. A response declared in the `this.json<{…}>` type argument has no named
    // shape, so until 2026-10-14 none of its fields were in this axis's population at all.
    // Measured that day: 5,999 keys across 562 call sites, 2,696 with no typed reader, 1,200 of
    // those with no string-literal reader either — against the 2,650-key named bucket the bands
    // above are about. WAIVER-FLAT's `status` and `waived_conditional` were two of them.
    //
    // A CEILING, not a pin, and it ratchets one way. Naming a response type moves its keys into
    // the named bucket and lowers this; a new inline-declared route raises it. Either is fine, and
    // the number has to change deliberately — which is the point, because nothing else in this
    // tree makes the blind spot's size visible.
    //
    // **5,999/562 → 5,983/560 → 5,976/559 → 5,931/558 on the day it was added, and that is the
    // ratchet working rather than bookkeeping.** It redirected four changes that day, each time
    // from *raise the number* to *declare it properly*. LOD-TARGET-INERT added four keys to `lodAssessment`'s INLINE
    // declaration,
    // this check went red at 6,015, and its message named the useful option first — so the response
    // type was NAMED instead of the number raised, which moved all of its fields into the bucket
    // the bands above are about. *A gate that only reports a number gets the number raised; one
    // that states the better action gets the better action.* CAPTABLE-PIPELINE then took it from
    // 5,983 to 5,976 by naming `capTable`'s response — whose `rows` had been
    // `Record<string, unknown>[]`, the OPAQUE bucket, so its row fields were in neither population.
    // PREFIX-RANKED took it to 5,931/558 the same way, by naming `/portfolio/risk`, and
    // SEQ-UNSCHED to 5,883/557 by naming `/clash/sequence` — 48 keys out of ONE call site, which
    // is why the site count is a second assertion rather than the only one: a route whose response
    // nests four record shapes contributes one site and fifty keys, and a ceiling on sites alone
    // would have scored that conversion at almost nothing.
    //
    // **5,883/557 -> 5,805/545 on 2026-10-15, and the twelve sites are the more interesting half.**
    // TM-UNBILLED named `tmSummary`'s response; the other eleven were named by SQL-CAP, CPM-SILENT,
    // RENTROLL-BASIS and FIELDLOG-WINDOW over the preceding days, each of which declared a response
    // interface and left this ceiling where it was. A `toBeLessThanOrEqual` is SATISFIED by
    // progress, so those gains banked silently and the ratchet stopped ratcheting — *a one-way gate
    // only moves when somebody re-measures it, which makes "lower it when you convert one" part of
    // the work rather than a courtesy.*
    // 5,805/545 -> 5,789/544 the same day: PRICE-MATCHED named `pricingReconcile`'s response,
    // 16 keys out of one call site. Lowered in the same edit as the conversion, which is the rule
    // the paragraph above had to learn.
    // 5,789/544 -> 5,782/543: SET-REVISED named `drawingSet`'s response, whose `sheet_index` had
    // additionally been `Record<string, unknown>[]` -- the OPAQUE bucket, in neither population --
    // so `revisions`, `change` and every other per-sheet field were outside every audit built on
    // declarations. That is the shape CAPTABLE-PIPELINE paid for too: an opaque row list costs more
    // than an inline one, because its fields are not even counted as a blind spot.
    const keys = [...keyToFile.keys()];
    const inline = keys.filter(isInline);
    const named = keys.filter((k) => !isInline(k));
    const sites = new Set(inline.map((k) => k.split(".")[0]!));
    const leaf = (k: string) => k.split(".").pop()!.replace(/\[\]$/, "");
    const unread = inline.filter((k) => readersOutsideDecl(k).length === 0);
    const sound = unread.filter((k) => !lits.has(leaf(k)));

    // THE VACUITY GUARD COMES FIRST, and here it carries more weight than usual: a ceiling is
    // satisfied by a walk that finds NOTHING, and a shrinking blind spot is exactly what progress
    // looks like. So a broken walk would read as the work being done.
    expect(inline.length, "the inline walk found no keys — a broken walk reports a shrinking blind "
      + "spot, which is indistinguishable from the work being done").toBeGreaterThan(1_000);
    expect(sites.size, "the inline walk found almost no call sites").toBeGreaterThan(100);
    expect(unread.length, "no inline key is unread, which is implausible at this population and "
      + "means the reader resolution stopped reaching this bucket").toBeGreaterThan(100);

    // The two buckets must not bleed into one another, or the bands above drift without moving.
    expect(named.some(isInline)).toBe(false);
    expect(inline.every((k) => k.startsWith(INLINE))).toBe(true);
    expect(isInline("Appraisal.reconciliation.value"),
      "a named interface key is being counted as inline").toBe(false);

    expect(inline.length, `inline-declared response fields outside the named population: `
      + `${inline.length} keys across ${sites.size} call sites, ${unread.length} with no typed `
      + `reader and ${sound.length} with no string-literal reader either. If you ADDED an inline `
      + `response type, declare it as a named interface instead — that is what moves its fields `
      + `into every audit built on these declarations. If you must add one, raise this number and `
      + `say why. If you CONVERTED one, lower it.`).toBeLessThanOrEqual(5_782);
    expect(sites.size, "inline `this.json<{…}>` call sites — same rule as the key count above")
      .toBeLessThanOrEqual(543);
  });

  it("CLASH-TRUNC's two fields resolve to a reader — one of them was unread for a measurable reason",
    () => {
      // `ClashResult.truncated` was returned by the server and read by NOBODY, and the reason is
      // visible in this derivation's own method: the clash panel re-spelled the response shape as
      // an inline cast instead of using the declared interface, so no property access anywhere
      // resolved to this member. Declaring the shape once and using it is what makes the field
      // reachable AND what makes this check meaningful — pin both so a future inline cast reds here.
      for (const k of ["ClashResult.truncated", "FederatedClashResult.pair_counts",
                       "FederatedClashResult.truncated"]) {
        expect(keyToFile.has(k), `${k} is no longer declared — re-derive before trusting this`)
          .toBe(true);
        expect(readersOutsideDecl(k).length, `${k} lost its reader`).toBeGreaterThan(0);
      }
    });

  it("the three SCREEN-VS-REPORT fields fixed in this change resolve to a reader", () => {
    // The asymmetric sub-population — declared here, rendered by `report_builders/`, read by
    // nothing — is 52 candidates today. Two of them are the only ones whose OWN declaring doc
    // comment states the invariant they belong to (`spec_count === coverage.specs +
    // withdrawn_excluded.length`), and that is what separated a defect from the forty-odd fields
    // that are merely not displayed: the author had already written down that the number on screen
    // is a subset, and the screen did not say so. The third is the PDF's Loan fees row.
    //
    // *A candidate set of fifty-two is triage; the filter that ranks it is the finding.*
    for (const k of ["SpineTraceability.spec_count", "SpineTraceability.withdrawn_excluded",
                     "ProformaResult.sources_uses.loan_fees"]) {
      expect(keyToFile.has(k), `${k} is no longer declared — re-derive before trusting this`).toBe(true);
      expect(readersOutsideDecl(k).length, `${k} lost its reader`).toBeGreaterThan(0);
    }
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

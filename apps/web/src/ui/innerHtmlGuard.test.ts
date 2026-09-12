/**
 * SEC — an IDENTITY ratchet on unescaped `innerHTML` interpolation.
 *
 * The 2026-07 audit found user-controlled text reaching `innerHTML` unescaped: a submittal title
 * lifted from an UPLOADED document, a `trade` parameter echoed straight back, an upload filename,
 * and server error strings. Each was one missed `esc()` away from stored XSS, and the surrounding
 * code in those very functions already used `textContent` — the defect was inconsistency, not
 * ignorance.
 *
 * **THIS GATE USED TO COUNT, AND A COUNT HAS NO IDENTITY.** The baseline was a per-file NUMBER, so
 * a file sitting inside its allowance was never looked at again: you could remove a safe sink and
 * add a live XSS sink in the same file and the gate stayed green both times. On 2026-09-12 it was
 * doing exactly that. `register.ts` was allowed 6 and had 4, and two of the four were
 * `${a.filename}` — the raw multipart filename, unsanitised from `routers/modules.py`, persisted
 * verbatim, and rendered into `innerHTML`. A reviewer role could upload `<img src=x onerror=…>.pdf`
 * and every viewer of that record ran it. The gate had counted it for months, on the exact vector
 * its own docstring names.
 *
 * There was headroom at the top level too: BASELINE_TOTAL was 85 against 77 actual, and SEVEN files
 * the baseline had never heard of were sitting in that slack, passing silently.
 *
 * **AND IT WAS BLIND TO HALF ITS OWN POPULATION, which is the worse of the two defects.** The rule
 * required `innerHTML` and `${` on the SAME LINE, so a statement wrapped across lines — the normal
 * shape for any non-trivial row — was scanned only as far as its first chunk. Measured 2026-09-12
 * while converting this file: 62 sinks visible to the line-scoped rule, and **58 more sitting on
 * continuation lines it could not see**, among them `v.vendor`, `s.company`, `r.text`, `t.title`
 * and `cert.ref`. *A ratchet's SCOPE is a separate question from its RULE, and a green ratchet is
 * exactly what makes a scope error invisible* — the lesson `services/api/test_ruff_scope.py` paid
 * for, repeated here in a different file. `hotSinks` now accumulates the whole statement.
 *
 * **So the baseline is now keyed on IDENTITY — `file :: expression` — and the count is derived,
 * never asserted.** An expression this list has not seen fails even when the total is flat or under.
 * A substitution can no longer hide inside an allowance, because there is no allowance.
 *
 * **Down is still always fine, and that is deliberate.** An entry that VANISHES never fails. An
 * earlier draft of the counting version failed when a file dropped below its baseline, which
 * punished the exact behaviour it wanted — a contributor who escaped one interpolation got a red
 * build. Improving the code must never fail a build. Prune vanished entries when convenient;
 * nothing forces it.
 *
 * WHAT THE ENTRIES ARE. Most are helper PARAMETERS — `card(label, value)` in `operations.ts:53` and
 * its ~14 siblings — whose callers today all pass string literals and `String(n)`. That is safe by
 * accident of caller, not by construction: the parameter is typed `string`, so the day a caller
 * passes server text this gate sees NO CHANGE, because the identity is already frozen. Identity
 * keying closes substitution within a file; it cannot see an argument's source change. The durable
 * fix for those is `esc()` INSIDE each helper, which deletes ~30 entries at once and cannot rot.
 * That is follow-up work, and it can only ever remove entries from this list.
 */
import { readdirSync, readFileSync, statSync } from "node:fs";
import { join, relative } from "node:path";

import ts from "typescript";
import { describe, expect, it } from "vitest";

import { escapeHtml } from "./feedback";

const SRC = join(__dirname, "..");

/** Escapers that make an interpolation safe. Tested per `${…}`, never per line. */
const SAFE = /\b(esc|escapeHtml|sanitizeSvg|safeUrl)\s*\(/;
/**
 * Identifiers that carry free text a user or a third-party document controls.
 *
 * `assignee`, `ref`, `owner`, `party` and `recipient` were added on 2026-09-12. They cost NOTHING —
 * zero new entries — because the sites carrying them were escaped in the same change; what they buy
 * is that re-introducing `${c.assignee}` unescaped now fails. `status` was CONSIDERED AND REJECTED:
 * it added 14 hits of which ~12 were CSS-variable ternaries (`good ? "var(--status-good)" : …`) and
 * `statusColor(a.status)`, all of which produce colour literals. *A detector that mostly reports
 * false positives makes the frozen list worse, because it buries the real entries in it.*
 */
const HOT =
  /(name|title|desc|description|message|label|file|filename|user|author|comment|note|text|trade|source|summary|subject|company|vendor|email|address|code|mark|tag|reason|detail|question|answer|value|key|spec_section|type|assignee|ref|owner|party|recipient|requirement|section|body|content|remark|scope|clause)\b/i;
/** Structurally safe to interpolate: loop counters, lengths, numbers. */
const COLD = /^(i|idx|j|n|k|len|count|total|pct|num|\d+)$/i;

/**
 * Known unescaped interpolations, as `file -> expressions`. Every entry is a place a future reader
 * should CHECK rather than trust — which is what the counting version claimed and could not deliver,
 * because a number does not say which sink it is describing.
 */
// SIX of these entries are the class that must NOT be escaped, and they are all one shape: a
// ternary whose branches are LITERAL MARKUP or a literal glyph — `row.gap ? ' <span …>⚠️</span>' :
// ""`, `s.name === r.best ? " ★" : ""`, `s.daylight_limited ? ' title="…"' : ""` — plus `mark`
// (a ✓/✗/– glyph) and `discColorByName[disc]` (a colour constant from a lookup). They match HOT on
// their CONDITION, not on their value. Wrapping any of them in esc() would render the markup as
// visible text. They are baselined rather than fixed because the fix would be the bug.
const BASELINE: Record<string, readonly string[]> = {
  "main.ts": [
    "it.label",
  ],
  "portal/panels/aiassist.ts": [
    "(p.title || p.ref || p.id) as string",
    "mark",
    "r.message || \"No bids to level.\"",
    "r.recommendation.missing_scope.length ? \"var(--status-warn)\" : \"var(--status-good)\"",
    "r.recommendation.note",
    "r.source === \"claude\" ? \"AI\" : \"extract\"",
    "r.source === \"claude\" ? \"AI\" : \"rules\"",
    "r.source === \"claude\" ? \"AI\" : \"rules\"",
    "row.gap ? ' <span title=\"scope gap\">⚠️</span>' : \"\"",
  ],
  "portal/panels/analytics.ts": [
    "c.cost_code",
    "cb.message || \"No cost history yet.\"",
    "o.compliant ? \"✓\" : `<span style=\"color:var(--status-crit)\" title=\"${o.violations.join(\"; \")}\">✗</span>`",
    "o.label",
    "o.label === s.recommended ? \"★ \" : \"\"",
    "o.label === s.recommended ? ' style=\"background:var(--hover)\"' : \"\"",
    "r.label",
    "r.label",
    "r.message || \"No material quantities.\"",
    "r.message || \"No reclassification suggestions (load a model in the Model workspace).\"",
    "r.pricing_source",
    "r.pricing_source",
    "s.note",
  ],
  "portal/panels/budget.ts": [
    "g.contract_value ? \" · \" : \"\"",
    "usd(g.contract_value)",
    "usd(s.contract_value)",
    "usd(t.contract_value)",
  ],
  "portal/panels/design.ts": [
    "x.label",
  ],
  "portal/panels/masterBuilder.ts": [
    "st.label",
  ],
  "portal/panels/operations.ts": [
    "d.code ?? \"\"",
  ],
  "portal/panels/portfolio.ts": [
    "usd(w.weighted_value)",
  ],
  "portal/panels/schedule.ts": [
    "mi.name",
    "title.toLowerCase()",
  ],
  "portal/panels/selections.ts": [
    "dirLabel",
  ],
  "portal/panels/standards.ts": [
    "cov.complete ? \"✅ core documents on file (EIR, BEP, AIR)\"\n        : `⏳ missing core: ${cov.missing.map(esc).join(\", \")}`",
    "dp.next_deliverable.ref ?? \"\"",
    "dp.next_deliverable.type",
    "els.map((e) => e.label).join(\", \")",
    "m.parent_type",
    "m.type",
    "n.ref ?? n.title ?? \"?\"",
    "o.ref ?? \"\"",
    "o.type",
  ],
  "portal/panels/topicBoard.ts": [
    "e.detail?.reply_to ? \"↳ \" : \"\"",
    "e.kind === \"comment\" ? \"💬 \" : \"\"",
  ],
  "portal/panels/wip.ts": [
    "flagText",
  ],
  "portal/portal.ts": [
    "n.reason === \"assigned\" ? \"rfi\" : \"open\"",
    "rs.source === \"claude\" ? \"AI\" : \"rules\"",
    "top.reason",
  ],
  "portal/register/register.ts": [
    "c.geo ? \"\" : \" (text search only)\"",
  ],
  "proforma/proforma.ts": [
    "cd.by_cost_code.length - top.length",
    "cipNote",
    "e.source === \"cip\" ? \" <span class=\\\"meta\\\">(CIP)</span>\" : \"\"",
    "money(pf.terminal_value)",
    "money(rec.value)",
    "money(v.cost.value)",
    "money(v.income.value)",
    "money(v.sales_comparison.value)",
    "row(\"Plus land\", money(v.cost.land_value))",
    "x.code",
  ],
  "proforma/testfitTab.ts": [
    "s.daylight_limited ? ' title=\"deep plate — dark interior earns no rent\"' : \"\"",
    "s.name === r.best ? \" ★\" : \"\"",
    "s.name === r.best ? ' style=\"font-weight:700\"' : \"\"",
  ],
  "reportCenter.ts": [
    "money(s.approved_value)",
    "money(s.executed_value)",
    "money(s.pending_value)",
    "money(s.total_value)",
  ],
  "studio/nodeEditor.ts": [
    "spec.label",
  ],
  "ui/checklist.ts": [
    "isDone ? \"text-decoration:line-through\" : \"\"",
    "it.label",
  ],
  "ui/onboarding.ts": [
    "s.body",
    "s.title",
  ],
  "ui/result.ts": [
    "m.label",
    "m.value",
  ],
  "viewer/app.ts": [
    "discColorByName[disc]",
    "reason",
  ],
  "viewer/tools/authoringSection.ts": [
    "r.imported.slice(0, 3).map((i) => i.name).join(\", \")",
  ],
  "viewer/tools/contentLibrarySection.ts": [
    "it.label",
  ],
  "viewer/tools/modelReviewPanel.ts": [
    "statusChip(LABEL[r.review_status], { tone: TONE[r.review_status] })",
  ],
  "viewer/tools/qaSection.ts": [
    "a.r_value",
  ],
};

function walk(dir: string, out: string[] = []): string[] {
  for (const entry of readdirSync(dir)) {
    const p = join(dir, entry);
    if (statSync(p).isDirectory()) walk(p, out);
    else if (entry.endsWith(".ts") && !entry.endsWith(".test.ts")) out.push(p);
  }
  return out;
}

/**
 * Every interpolation that reaches an `innerHTML` assignment, via the TYPESCRIPT PARSER.
 *
 * Three hand-rolled scanners preceded this, and each one drew a review finding that was correct:
 *
 *  1. `/\$\{([^}]*)\}/g` on a single LINE — blind to any statement wrapped across lines, which was
 *     58 of ~120 sinks.
 *  2. The same regex over an accumulated statement — truncated at the first `}`, so an object
 *     literal or nested template was frozen as a FRAGMENT. This file's own baseline carried one.
 *  3. A brace-depth scanner with an 8-line span — still blind to `}` inside a regex literal
 *     (`/}/`) or a comment (`/* } *\/`, `// }`), still capped by an arbitrary line budget, and
 *     still returning only the OUTER expression of a nested template, so an outer `esc(...)` made
 *     `SAFE` accept an unescaped inner value.
 *
 * *Each fix made the scanner more elaborate and left a narrower version of the same gap.* The
 * convergent answer is not a fourth scanner: `typescript` is already a dependency and
 * `api/responseUndeclared.test.ts` already parses with it. The real parser handles nesting,
 * comments, regex literals and statement spans by construction, and cannot be wrong about them in
 * the way a character scanner is wrong.
 *
 * Nested spans are returned INDEPENDENTLY, which is the security-relevant part: an unescaped inner
 * value is judged on its own rather than hidden behind an outer `esc(`.
 */
export function interpolations(src: string): string[] {
  const sf = ts.createSourceFile("x.ts", src, ts.ScriptTarget.Latest, true);
  const out: string[] = [];
  const collect = (node: ts.Node): void => {
    if (ts.isTemplateExpression(node)) {
      for (const span of node.templateSpans) {
        out.push(span.expression.getText(sf).trim());
        collect(span.expression);            // nested templates yield their own spans
      }
      return;
    }
    ts.forEachChild(node, collect);
  };
  const bound = new Set<string>();                 // names reaching innerHTML as a bare identifier
  const walk = (node: ts.Node): void => {
    const isInnerHtmlWrite =
      ts.isBinaryExpression(node)
      && (node.operatorToken.kind === ts.SyntaxKind.EqualsToken
          || node.operatorToken.kind === ts.SyntaxKind.PlusEqualsToken)
      && ((ts.isPropertyAccessExpression(node.left) && node.left.name.text === "innerHTML")
          || (ts.isElementAccessExpression(node.left)
              && ts.isStringLiteral(node.left.argumentExpression)
              && node.left.argumentExpression.text === "innerHTML"));
    if (isInnerHtmlWrite) {
      const before = out.length;
      collect(node.right);
      for (let i = before; i < out.length; i++) if (/^[A-Za-z_$][\w$]*$/.test(out[i]!)) bound.add(out[i]!);
    }
    ts.forEachChild(node, walk);
  };
  walk(sf);

  // ONE LEVEL OF INDIRECTION — the blind spot a review finding on #544 exposed through
  // `main.ts`'s `${d.name}`. Markup is very often assembled into a local FIRST and only then
  // interpolated:
  //
  //     const rows = p.deals.map((d) => `<tr><th>${d.name}</th>…`).join("");
  //     panel.innerHTML = `…${rows}…`;
  //
  // The walk above only sees spans lexically inside the `innerHTML =` expression, so `${d.name}`
  // was invisible to BOTH rules in this file — not baselined, not flagged, live. It reached
  // innerHTML through exactly one hop, and 15 hot interpolations across 8 files sat behind that
  // hop. A sink one assignment away from the write is still a sink; the scanner was measuring
  // syntax where the question is reachability.
  //
  // Only one hop is followed, deliberately. Two hops would need real dataflow, and the honest
  // statement of a bounded rule beats a rule that quietly stops somewhere undocumented: a local
  // built from ANOTHER local that then reaches innerHTML is still not covered.
  const followBuilders = (n: ts.Node): void => {
    if (ts.isVariableDeclaration(n) && ts.isIdentifier(n.name) && bound.has(n.name.text)
        && n.initializer) collect(n.initializer);
    ts.forEachChild(n, followBuilders);
  };
  followBuilders(sf);
  return out;
}

/** Every hot, unescaped interpolation reaching innerHTML, as its expression text. */
export function hotSinks(src: string): string[] {
  return interpolations(src).filter((e) => !SAFE.test(e) && !COLD.test(e) && HOT.test(e));
}


/**
 * THE SECOND RULE, and the reason the first one is not enough.
 *
 * The identity ratchet above freezes `file :: expression`. That works when the expression NAMES its
 * source — `${a.filename}` tells you a filename is being rendered, so a caller cannot change what
 * flows in without changing the identity. It does NOT work when the interpolation is a bare value
 * binding:
 *
 *     const card = (label: string, value: string) => {
 *       c.innerHTML = `<div>${value}</div><div class="meta">${label}</div>`;   // identity: "value"
 *     };
 *
 * `value` is the identity whatever the caller passes. Every caller could switch from a literal to a
 * user-controlled field and the baseline would not move — the sink goes live while the gate stays
 * green. That is the SAME defect this file was built to fix (a frozen key that does not vary with
 * the thing it is supposed to constrain), one level up: there the key was a count with no identity,
 * here it is an identity with no source.
 *
 * So this rule takes no baseline and admits no exemption: a bare value binding reaching innerHTML
 * must be escaped. The fix is always available and always correct — wrap it in `esc()` — which is
 * why there is nothing to grandfather.
 *
 * WHAT COUNTS AS A VALUE BINDING: a function PARAMETER, or a name bound by a DESTRUCTURING pattern
 * (`for (const [label, val] of cards)`). Both are values handed in from elsewhere.
 *
 * WHAT DOES NOT, and why the line is drawn there: a plain `const x = …` local. 134 of those reach
 * innerHTML in this tree and most hold HTML assembled earlier in the same function — `rows`,
 * `thead`, `bars`, `cells`, `pts`. Escaping those would destroy the markup, so the rule would have
 * to carry judgement about which locals are values, and a rule with judgement in it is a rule that
 * can be argued with. The exclusion is stated here rather than left implicit: a local assigned from
 * user data and interpolated bare is NOT caught by either rule in this file.
 *
 * THAT EXCLUSION WAS TRIAGED, NOT ASSUMED — because an exclusion nobody measures is just a blind
 * spot with a justification attached. All 134 were classified by their declaration's initialiser
 * (41 build markup, 39 literal, 15 numeric, 1 already escaped, 36 suspect, 2 unresolvable) and
 * every suspect and unresolvable one was read. Exactly ONE was a real sink: `schedule.ts`'s
 * critical-path line, where the server builds `critical_path` as `[r["ref"] or r["id"] …]` — stored,
 * user-entered activity refs — and the panel joined and interpolated them raw. It is escaped now.
 *
 * Two things that triage is worth recording. **The classifier's first draft resolved declarations
 * file-wide and kept the LAST match**, so `design.ts`'s `gap` (a number, `p.eui_gap_pct`) was
 * attributed to an unrelated `el("div")` hundreds of lines away and reported suspect; the lookup is
 * scope-aware now, and the bug surfaced only because the suspects were READ rather than counted.
 * And the one real finding was a LOCAL — so the gap this comment describes was live, not
 * theoretical, which is the argument for measuring an exclusion instead of asserting it.
 *
 * Deliberately NOT filtered by HOT/COLD. `budget.ts` interpolated a bare `val` and `evm.ts` a bare
 * `sub`; neither matches HOT, so both were invisible to the ratchet above while being exactly the
 * shape this rule exists to catch. A term list derived from what someone happened to be looking at
 * cannot bound a population — the SHAPE can.
 */
export function valueBindingSinks(src: string): string[] {
  const sf = ts.createSourceFile("x.ts", src, ts.ScriptTarget.Latest, true);
  // Constructors and setters carry parameters like any other callable, and leaving them out made
  // this a coverage gap in a security gate rather than a style question (review finding on #544).
  const isFn = (n: ts.Node): boolean =>
    ts.isFunctionDeclaration(n) || ts.isFunctionExpression(n)
    || ts.isArrowFunction(n) || ts.isMethodDeclaration(n)
    || ts.isConstructorDeclaration(n) || ts.isSetAccessorDeclaration(n);

  const bindNames = (name: ts.BindingName, into: Set<string>): void => {
    if (ts.isIdentifier(name)) { into.add(name.text); return; }
    for (const el of name.elements) if (ts.isBindingElement(el)) bindNames(el.name, into);
  };
  const paramsOf = (fn: ts.Node): Set<string> => {
    const out = new Set<string>();
    for (const p of (fn as ts.SignatureDeclaration).parameters ?? []) bindNames(p.name, out);
    return out;
  };
  // LEXICALLY SCOPED. The first version collected destructured names file-wide and justified it as
  // "a false positive only costs one esc() that was already correct". That reasoning was WRONG, and
  // a review finding on #544 said so: a destructured `rows` in one function made an unrelated plain
  // local `rows` in a SIBLING function fail the plain-local exclusion — and that exclusion exists
  // precisely because those locals hold assembled markup, so the "harmless" fix would have escaped
  // HTML and broken the page. A false positive is only cheap when the suggested fix is safe.
  // Same for the upward parameter walk: a nearer local shadowing an outer parameter was reported.
  // So resolve each interpolation to its NEAREST binding and report only when that binding is a
  // parameter or a destructuring element.
  const isScope = (n: ts.Node): boolean =>
    isFn(n) || ts.isBlock(n) || ts.isSourceFile(n)
    || ts.isForOfStatement(n) || ts.isForInStatement(n) || ts.isForStatement(n)
    || ts.isCaseClause(n) || ts.isCatchClause(n);

  /** The nearest binding of `name` visible at `use`: "param", "destructured", "local", or null. */
  const nearestBinding = (name: string, use: ts.Node): string | null => {
    for (let scope: ts.Node | undefined = use.parent; scope; scope = scope.parent) {
      if (!isScope(scope)) continue;
      if (isFn(scope) && paramsOf(scope).has(name)) return "param";
      // Variable declarations belonging to THIS scope only — never descend into a nested
      // function, whose locals are not visible here (that descent is what made a sibling
      // function's `rows` shadow this one's).
      let found: string | null = null;
      const look = (n: ts.Node): void => {
        if (found) return;
        if (ts.isVariableDeclaration(n)) {
          const names = new Set<string>();
          bindNames(n.name, names);
          if (names.has(name)) found = ts.isIdentifier(n.name) ? "local" : "destructured";
        }
        if (n !== scope && isFn(n)) return;
        ts.forEachChild(n, look);
      };
      look(scope);
      if (found) return found;
    }
    return null;
  };

  const out: string[] = [];
  const collect = (node: ts.Node, into: ts.Expression[]): void => {
    if (ts.isTemplateExpression(node)) {
      for (const span of node.templateSpans) { into.push(span.expression); collect(span.expression, into); }
      return;
    }
    ts.forEachChild(node, (c) => collect(c, into));
  };
  const walk = (node: ts.Node): void => {
    const isInnerHtmlWrite =
      ts.isBinaryExpression(node)
      && (node.operatorToken.kind === ts.SyntaxKind.EqualsToken
          || node.operatorToken.kind === ts.SyntaxKind.PlusEqualsToken)
      && ((ts.isPropertyAccessExpression(node.left) && node.left.name.text === "innerHTML")
          || (ts.isElementAccessExpression(node.left)
              && ts.isStringLiteral(node.left.argumentExpression)
              && node.left.argumentExpression.text === "innerHTML"));
    if (isInnerHtmlWrite) {
      const exprs: ts.Expression[] = [];
      collect(node.right, exprs);
      for (const e of exprs) {
        if (!ts.isIdentifier(e) || SAFE.test(e.text)) continue;
        const binding = nearestBinding(e.text, e);
        if (binding === "param" || binding === "destructured") out.push(e.text);
      }
    }
    ts.forEachChild(node, walk);
  };
  walk(sf);
  return out;
}


/**
 * THE VERDICT, separate from the reporting, and mutated directly by the self-tests below.
 *
 * `mixinStaging.test.ts` records why: a check that asserts a site was REPORTED is not asserting how
 * it was CLASSIFIED, and an analyser mutated to call everything safe can still pass a
 * "was it reported?" test. So this returns the failing set and the tests mutate this function's
 * input, not the file walker's.
 */
export function unknownIdentities(
  actual: Record<string, readonly string[]>,
  baseline: Record<string, readonly string[]>,
): string[] {
  const out: string[] = [];
  for (const [file, exprs] of Object.entries(actual)) {
    // OCCURRENCE BUDGET, not set membership. With a Set, a file baselined for ONE `${user.name}`
    // silently accepted a second one — the identity was "known", so duplicating a sink was free.
    // That is the counting version's hole in miniature, reintroduced one level down.
    const budget = new Map<string, number>();
    for (const e of baseline[file] ?? []) budget.set(e, (budget.get(e) ?? 0) + 1);
    for (const e of exprs) {
      const left = budget.get(e) ?? 0;
      if (left > 0) budget.set(e, left - 1);
      else out.push(`${file} :: ${e}`);
    }
  }
  return out.sort();
}

const ADVICE =
  "Wrap the interpolated value in esc()/escapeHtml() — an uploaded document's title, a filename, " +
  "or a 422 detail quoting the caller's own input is attacker-controlled text. If it is genuinely " +
  "a local literal, add the exact expression to BASELINE with a note saying why.";

const actual: Record<string, string[]> = {};
for (const file of walk(SRC)) {
  const hits = hotSinks(readFileSync(file, "utf8"));
  if (hits.length) actual[relative(SRC, file).replace(/\\/g, "/")] = hits;
}
const sinkCount = Object.values(actual).reduce((a, b) => a + b.length, 0);

describe("innerHTML escaping ratchet (identity-keyed)", () => {
  it("is reading a real source tree", () => {
    // Without this, a walker returning nothing reports a clean tree — "found nothing" and "did not
    // look" must not be the same output.
    expect(Object.keys(actual).length, "no files with hot sinks at all — the walker is broken")
      .toBeGreaterThan(15);
    expect(sinkCount, "no sinks at all — the matcher is broken").toBeGreaterThan(40);
  });

  it("introduces no interpolation this list has not seen", () => {
    expect(unknownIdentities(actual, BASELINE).join("\n") || "none", ADVICE).toBe("none");
  });

  it("never fails because an entry VANISHED — improving the code must not red the build", () => {
    // SYNTHETIC `actual`, deliberately not the live tree. The first draft of this asserted
    // `unknownIdentities(actual, {...BASELINE, ghost}) === []` against the real scan, which mixes
    // two questions: it fails whenever ANY new sink exists, with a message blaming the ghost
    // ("improving the code must not red the build") while the real cause is that somebody ADDED an
    // interpolation. *A failure message that can misdiagnose is worse than one that stays silent,
    // because somebody acts on it* — the lesson `test_scratch_ignored.py` paid for. Caught here by
    // mutating a real file and reading BOTH failures instead of only the expected one.
    const fixture = { "a.ts": ["kept.name"] };
    const withGhosts = { "a.ts": ["kept.name", "gone.title"], "no/such/file.ts": ["ghost.name"] };
    expect(unknownIdentities(fixture, withGhosts), "a vanished entry must be silent").toEqual([]);
    // ...while the opposite direction still fires: no baseline at all means every sink is unknown.
    expect(unknownIdentities(fixture, {})).toEqual(["a.ts :: kept.name"]);
  });

  it("CATCHES A SUBSTITUTION, which the counting version could not", () => {
    // This is the whole argument for the rewrite. Take a real baselined file, DELETE one known sink
    // and ADD a different unescaped one. The count is unchanged, so the old rule stayed green.
    // The fixture is DERIVED, not named. It used to hardcode `portal/panels/evm.ts` / "value" —
    // and HELPER-ESCAPE escaped every sink in that file, so a legitimate improvement red this test
    // with a message about a missing baseline entry rather than about the substitution it guards.
    // A failure message that can misdiagnose is worse than one that stays silent, because somebody
    // acts on it (test_scratch_ignored.py, the same lesson). Pick any file with ≥ 2 known sinks.
    const file = Object.keys(BASELINE).find((f) => (BASELINE[f] ?? []).length >= 2);
    expect(file, "no baselined file has two sinks left — pick a different fixture shape").toBeTruthy();
    const known = BASELINE[file!]!;
    const victim = known[0]!;

    const before = { [file!]: [...known] };
    const after = { [file!]: known.filter((e) => e !== victim).concat("attacker.name") };

    // The mutation must actually have applied — a mutation that does not apply is a test that was
    // never exercised, and it reports green exactly like a passing one (mixinStaging.test.ts, #542).
    expect(after[file!]).not.toEqual(before[file!]);
    expect(after[file!]!.length, "substitution must keep the COUNT identical").toBe(before[file!]!.length);

    // Old rule: count <= allowance. Same length, so it passed.
    expect(after[file!]!.length <= before[file!]!.length).toBe(true);
    // New rule: the identity is unknown, so it fails.
    expect(unknownIdentities(after, BASELINE)).toEqual([`${file} :: attacker.name`]);
  });

  it("detects the filename sink this gate used to count", () => {
    // register.ts's `${a.filename}` was a LIVE stored XSS sitting inside a count allowance. It is
    // escaped now, so it must NOT appear — and the matcher must still be able to see its shape.
    expect(hotSinks('x.innerHTML = `<span>${a.filename}</span>`;')).toEqual(["a.filename"]);
    expect(hotSinks('x.innerHTML = `<span>${esc(a.filename)}</span>`;')).toEqual([]);
    expect(BASELINE["portal/register/register.ts"] ?? []).not.toContain("a.filename");
  });

  it("parses NESTED braces in an interpolation, not up to the first `}`", () => {
    // Review finding on #543, and this file's own baseline was the evidence: the entry for
    // modelReviewPanel.ts had been frozen as `statusChip(LABEL[...], { tone: TONE[...]` — cut at
    // the inner brace by `/\$\{([^}]*)\}/g`. A TRUNCATED identity is worse than a missing one: it
    // is a string that can later match a different real expression.
    // NB the fixture must carry a HOT term: the first draft used `T[s.status]`, and `status` was
    // deliberately excluded from HOT for being mostly CSS ternaries — so it returned [] and the
    // test was wrong, not the parser.
    expect(hotSinks('e.innerHTML = `<b>${chip(x, { tone: T[s.name] })}</b>`;'))
      .toEqual(["chip(x, { tone: T[s.name] })"]);
    // a `}` inside a string literal must not close the interpolation. NB the fixture has to be a
    // complete `innerHTML` assignment now: the AST walker collects from innerHTML WRITES, so a bare
    // `${...}` fragment correctly yields nothing — the first draft of this line passed a fragment
    // and read as a parser failure.
    expect(interpolations('x.innerHTML = `${f("a}b")}`;')).toEqual(['f("a}b")']);
    // A nested template returns the outer expression AND the inner span, independently. The
    // earlier draft asserted the outer ONLY, which is the hole a reviewer then found: `SAFE`
    // matches `esc(` anywhere in the outer text, so an outer escape made an unescaped INNER value
    // invisible. Judging each span on its own is the security-relevant behaviour.
    expect(interpolations("x.innerHTML = `${xs.map((i) => `<i>${i.name}</i>`).join(\"\")}`;"))
      .toEqual(['xs.map((i) => `<i>${i.name}</i>`).join("")', "i.name"]);
    // ...so an outer esc() no longer launders an inner unescaped value
    expect(hotSinks("x.innerHTML = `${esc(a) + xs.map((i) => `${i.name}`).join(\"\")}`;"))
      .toEqual(["i.name"]);
    // `}` inside a regex literal or a comment does not terminate the interpolation
    expect(interpolations("x.innerHTML = `${v && /}/ ? a.name : b.name}`;"))
      .toEqual(["v && /}/ ? a.name : b.name"]);
    expect(interpolations("x.innerHTML = `${v /* } */ .label}`;")).toEqual(["v /* } */ .label"]);
    expect(interpolations("x.innerHTML = `${v // }\n .label}`;")).toEqual(["v // }\n .label"]);
    // and no baselined entry may be a truncated fragment ending mid-expression
    for (const [file, exprs] of Object.entries(BASELINE)) {
      for (const e of exprs) {
        const open = (e.match(/\{/g) ?? []).length, close = (e.match(/\}/g) ?? []).length;
        expect(open, `${file} :: ${e} — unbalanced braces, likely a truncated capture`).toBe(close);
      }
    }
  });

  it("counts DUPLICATE identities, so a second copy of a known sink is not free", () => {
    // Review finding on #543. With Set membership a file baselined for one `${user.name}` accepted
    // a second silently — the counting version's hole, reintroduced one level down.
    const baseline = { "a.ts": ["user.name"] };
    expect(unknownIdentities({ "a.ts": ["user.name"] }, baseline)).toEqual([]);
    expect(unknownIdentities({ "a.ts": ["user.name", "user.name"] }, baseline))
      .toEqual(["a.ts :: user.name"]);
  });

  // ---- THE SECOND RULE: no bare value binding reaches innerHTML unescaped. No baseline. --------

  it("finds the pre-fix helper shape — the derivation is proved to REACH, not just to run", () => {
    // This is `card` from portal/panels/operations.ts EXACTLY as it stood before this change. The
    // gate must find it. test_seeding_sweep.py paid for this rule twice: a sweep whose own first
    // draft reported the tree clean, because its predicate never looked at the site. So the checker
    // runs against the known-bad text first, and a mutation that makes it lenient fails HERE.
    const preFix = `
      const card = (label: string, value: string) => {
        const c = el("div", "dash-card");
        c.innerHTML = \`<div style="font-size:20px">\${value}</div><div class="meta">\${label}</div>\`;
        return c;
      };`;
    expect(valueBindingSinks(preFix).sort()).toEqual(["label", "value"]);
  });

  it("finds a DESTRUCTURED binding, which a parameter-only rule missed", () => {
    // The first draft of this rule tested only for parameters and reported the tree clean at 85
    // fixed sites. 23 more were live, in this shape — `label`/`val` are values handed in from
    // elsewhere exactly as a parameter is, and the name says nothing about the source either way.
    // A predicate that decides what to LOOK at hides everything it excludes from its own count.
    const loop = `
      for (const [label, val] of cards) {
        c.innerHTML = \`<div class="kpi-v">\${val}</div><div class="kpi-l">\${label}</div>\`;
      }`;
    expect(valueBindingSinks(loop).sort()).toEqual(["label", "val"]);
  });

  it("catches names HOT cannot see — which is why this rule is not term-filtered", () => {
    // `val` and `sub` match no HOT term, so the identity ratchet above was blind to both while they
    // sat unescaped in budget.ts and evm.ts. Shape bounds a population; a keyword list does not.
    for (const name of ["val", "sub", "color", "icon", "recipe"]) {
      expect(hotSinks("const f = (" + name + ") => { e.innerHTML = `<b>${" + name + "}</b>`; };"),
        `${name} is invisible to HOT — that is the point`).toEqual([]);
      expect(valueBindingSinks("const f = (" + name + ") => { e.innerHTML = `<b>${" + name + "}</b>`; };"))
        .toEqual([name]);
    }
  });

  it("accepts the escaped form, so the fix actually clears the gate", () => {
    expect(valueBindingSinks(
      "const f = (label) => { e.innerHTML = `<b>${esc(label)}</b>`; };")).toEqual([]);
    expect(valueBindingSinks(
      "const f = (label) => { e.innerHTML = `<b>${escapeHtml(label)}</b>`; };")).toEqual([]);
  });

  it("does NOT flag a plain local — the stated exclusion, asserted rather than described", () => {
    // 157 bare locals reach innerHTML in this tree and most hold markup built a few lines earlier.
    // Escaping those would destroy it, so they are out of scope BY DESIGN. Asserting the exclusion
    // keeps it honest: if someone later widens the rule to all bare identifiers, this test says so
    // rather than the build going red 157 times with no explanation.
    const local = `
      function render(items) {
        const rows = items.map((r) => \`<tr><td>\${esc(r.name)}</td></tr>\`).join("");
        tbl.innerHTML = \`<tbody>\${rows}</tbody>\`;
      }`;
    expect(valueBindingSinks(local)).toEqual([]);
  });

  it("has ZERO value-binding sinks across the tree, with no baseline to grandfather into", () => {
    const found: string[] = [];
    for (const file of walk(SRC)) {
      const hits = valueBindingSinks(readFileSync(file, "utf8"));
      for (const h of hits) found.push(`${relative(SRC, file).replace(/\\/g, "/")} :: ${h}`);
    }
    expect(found.sort().join("\n") || "none",
      "A bare parameter or destructured binding reached innerHTML unescaped. Wrap it in esc(). "
      + "There is no baseline for this rule: the identity is the binding NAME, which does not move "
      + "when a caller starts passing user data, so grandfathering one would freeze a sink open.")
      .toBe("none");
  });

  // ---- Review findings on #544, each pinned so it cannot come back silently -------------------

  it("FOLLOWS ONE HOP through a builder local — the blind spot that hid a live sink", () => {
    // Markup is usually assembled into a local first and only then interpolated. The scanner walked
    // only the spans lexically inside the `innerHTML =` expression, so `${d.name}` in main.ts was
    // invisible to BOTH rules here: not baselined, not flagged, live. A reviewer found the symptom;
    // the cause was that the scanner measured SYNTAX where the question is REACHABILITY.
    const builder = `
      const rows = p.deals.map((d) => \`<tr><th>\${d.name}</th></tr>\`).join("");
      panel.innerHTML = \`<table>\${rows}</table>\`;`;
    expect(hotSinks(builder)).toEqual(["d.name"]);
    // ...and the escaped form clears it, so the fix is reachable.
    expect(hotSinks(builder.replace("${d.name}", "${esc(d.name)}"))).toEqual([]);
  });

  it("stops at ONE hop, and says so rather than pretending to do dataflow", () => {
    // A local built from another local is NOT covered. Asserting the limit keeps it honest: a
    // silent boundary is how a gate ends up reporting good news about ground it never walked.
    const twoHops = `
      const inner = items.map((r) => \`<td>\${r.name}</td>\`).join("");
      const outer = \`<tr>\${inner}</tr>\`;
      el.innerHTML = \`<table>\${outer}</table>\`;`;
    expect(hotSinks(twoHops), "two hops is a known, documented gap").toEqual([]);
  });

  it("sees parameters of CONSTRUCTORS and SETTERS, not just functions and methods", () => {
    // Review finding: `isFn` omitted both, so a parameter in either body passed the guard. A
    // coverage hole in a security gate, not a style question.
    expect(valueBindingSinks(
      "class A { constructor(label) { this.el.innerHTML = `<b>${label}</b>`; } }")).toEqual(["label"]);
    expect(valueBindingSinks(
      "class A { set title(value) { this.el.innerHTML = `<b>${value}</b>`; } }")).toEqual(["value"]);
  });

  it("resolves bindings LEXICALLY, so a sibling scope cannot make a plain local look unsafe", () => {
    // Review finding, and my own rationale for the file-wide set was wrong: I argued a false
    // positive "costs one esc() that was already correct". For THIS exclusion it costs the opposite
    // — the plain-local carve-out exists because those locals hold assembled markup, so the
    // "harmless" fix would have escaped HTML and broken the page. A false positive is only cheap
    // when the fix it suggests is safe.
    const siblings = `
      function a([label, rows]) { x.innerHTML = \`<i>\${rows}</i>\`; }
      function b(items) { const rows = items.map((r) => "<td></td>").join(""); y.innerHTML = \`<i>\${rows}</i>\`; }`;
    // `rows` is destructured in a(), a plain local in b(). Only a()'s may be reported.
    expect(valueBindingSinks(siblings)).toEqual(["rows"]);

    // And a nearer local shadowing an outer parameter resolves to the LOCAL, so it is not reported.
    const shadowed = `
      function outer(value) {
        function inner() { const value = "<b>x</b>"; z.innerHTML = \`<i>\${value}</i>\`; }
      }`;
    expect(valueBindingSinks(shadowed)).toEqual([]);
  });

  it("escapes an option VALUE as well as its text, so the value round-trips", () => {
    // Review finding on schedule.ts. `esc` turns `&` into `&amp;`; the old `.replace(/"/g, …)` did
    // not, so a milestone literally named `A &amp; B` came back out of the attribute as `A & B` and
    // the next request queried the wrong milestone. Escaping only the TEXT made the two disagree.
    // Asserted through a real DOM parse rather than by eyeballing the template.
    const name = 'A &amp; B "quoted" <b>';
    const sel = document.createElement("select");
    sel.innerHTML = `<option value="${escapeHtml(name)}">${escapeHtml(name)}</option>`;
    expect(sel.value, "the value must survive innerHTML parsing unchanged").toBe(name);
    expect(sel.options[0]!.textContent).toBe(name);

    // the old shape did not round-trip — this is the regression being pinned
    const bad = document.createElement("select");
    bad.innerHTML = `<option value="${name.replace(/"/g, "&quot;")}">${escapeHtml(name)}</option>`;
    expect(bad.value).not.toBe(name);
  });

  it("sees the free-text identifiers added with this change", () => {
    // The widened HOT terms, asserted directly: re-introducing any of these unescaped must fail.
    for (const expr of ["c.assignee", "c.ref", "s.vendor", "lane.trade", "x.owner", "p.recipient"]) {
      expect(hotSinks("e.innerHTML = `<b>${" + expr + "}</b>`;"), `${expr} must be detected`)
        .toEqual([expr]);
    }
  });
});

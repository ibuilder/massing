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
const BASELINE: Record<string, readonly string[]> = {
  "main.ts": [
    "it.label",
  ],
  "portal/homes/developerHome.ts": [
    "label",
  ],
  "portal/panels/aiassist.ts": [
    "(p.title || p.ref || p.id) as string",
    "r.message || \"No bids to level.\"",
    "r.recommendation.missing_scope.length ? \"var(--status-warn)\" : \"var(--status-good)\"",
    "r.recommendation.note",
    "r.source === \"claude\" ? \"AI\" : \"extract\"",
    "r.source === \"claude\" ? \"AI\" : \"rules\"",
    "r.source === \"claude\" ? \"AI\" : \"rules\"",
    "title",
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
    "title",
  ],
  "portal/panels/budget.ts": [
    "g.contract_value ? \" · \" : \"\"",
    "label",
    "usd(g.contract_value)",
    "usd(s.contract_value)",
    "usd(t.contract_value)",
  ],
  "portal/panels/design.ts": [
    "label",
    "value",
    "x.label",
  ],
  "portal/panels/evm.ts": [
    "label",
    "value",
  ],
  "portal/panels/masterBuilder.ts": [
    "st.label",
  ],
  "portal/panels/operations.ts": [
    "d.code ?? \"\"",
    "label",
    "label",
    "title",
    "value",
    "value",
  ],
  "portal/panels/portfolio.ts": [
    "label",
    "t.cross_project ? ` <span style=\"color:${col}\" title=\"on ${t.project_count} projects — can be double-booked\">⇄</span>` : \"\"",
    "usd(w.weighted_value)",
  ],
  "portal/panels/resourceLoading.ts": [
    "label",
    "value",
  ],
  "portal/panels/schedule.ts": [
    "mi.name",
    "title",
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
    "label",
    "label",
    "label",
    "m.parent_type",
    "m.type",
    "n.ref ?? n.title ?? \"?\"",
    "o.ref ?? \"\"",
    "o.type",
    "value",
    "value",
  ],
  "portal/panels/topicBoard.ts": [
    "e.detail?.reply_to ? \"↳ \" : \"\"",
    "e.kind === \"comment\" ? \"💬 \" : \"\"",
  ],
  "portal/panels/traceability.ts": [
    "label",
    "value",
  ],
  "portal/panels/wip.ts": [
    "flagText",
    "label",
    "value",
  ],
  "portal/portal.ts": [
    "label",
    "label",
    "label",
    "n.reason === \"assigned\" ? \"rfi\" : \"open\"",
    "rs.source === \"claude\" ? \"AI\" : \"rules\"",
    "top.reason",
  ],
  "portal/register/register.ts": [
    "c.geo ? \"\" : \" (text search only)\"",
  ],
  "proforma/massingTab.ts": [
    "label",
  ],
  "proforma/proforma.ts": [
    "cd.by_cost_code.length - top.length",
    "cipNote",
    "e.source === \"cip\" ? \" <span class=\\\"meta\\\">(CIP)</span>\" : \"\"",
    "label",
    "label",
    "label",
    "label",
    "label",
    "label",
    "label",
    "money(pf.terminal_value)",
    "money(rec.value)",
    "money(v.cost.value)",
    "money(v.income.value)",
    "money(v.sales_comparison.value)",
    "row(\"Plus land\", money(v.cost.land_value))",
    "title",
    "title",
    "x.code",
  ],
  "proforma/testfitTab.ts": [
    "label",
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
    "desc",
    "s.body",
    "s.title",
    "title",
  ],
  "ui/result.ts": [
    "m.label",
    "m.value",
  ],
  "viewer/app.ts": [
    "reason",
    "title",
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
    "label",
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
  const walk = (node: ts.Node): void => {
    const isInnerHtmlWrite =
      ts.isBinaryExpression(node)
      && (node.operatorToken.kind === ts.SyntaxKind.EqualsToken
          || node.operatorToken.kind === ts.SyntaxKind.PlusEqualsToken)
      && ((ts.isPropertyAccessExpression(node.left) && node.left.name.text === "innerHTML")
          || (ts.isElementAccessExpression(node.left)
              && ts.isStringLiteral(node.left.argumentExpression)
              && node.left.argumentExpression.text === "innerHTML"));
    if (isInnerHtmlWrite) collect(node.right);
    ts.forEachChild(node, walk);
  };
  walk(sf);
  return out;
}

/** Every hot, unescaped interpolation reaching innerHTML, as its expression text. */
export function hotSinks(src: string): string[] {
  return interpolations(src).filter((e) => !SAFE.test(e) && !COLD.test(e) && HOT.test(e));
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
    const file = "portal/panels/evm.ts";
    const known = BASELINE[file]!;
    expect(known, "fixture file must still be baselined").toContain("value");

    const before = { [file]: [...known] };
    const after = { [file]: known.filter((e) => e !== "value").concat("attacker.name") };

    // The mutation must actually have applied — a mutation that does not apply is a test that was
    // never exercised, and it reports green exactly like a passing one (mixinStaging.test.ts, #542).
    expect(after[file]).not.toEqual(before[file]);
    expect(after[file]!.length, "substitution must keep the COUNT identical").toBe(before[file]!.length);

    // Old rule: count <= allowance. Same length, so it passed.
    expect(after[file]!.length <= before[file]!.length).toBe(true);
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

  it("sees the free-text identifiers added with this change", () => {
    // The widened HOT terms, asserted directly: re-introducing any of these unescaped must fail.
    for (const expr of ["c.assignee", "c.ref", "s.vendor", "lane.trade", "x.owner", "p.recipient"]) {
      expect(hotSinks("e.innerHTML = `<b>${" + expr + "}</b>`;"), `${expr} must be detected`)
        .toEqual([expr]);
    }
  });
});

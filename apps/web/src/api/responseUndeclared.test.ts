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
 *  cautionary tale this shape is built against.)
 *
 *  **It was EMPTY until 2026-10-14, and that was a measurement of this gate's reach, not of the
 *  tree.** RESPKEY-DELEGATED taught `response_keys.py` to follow one hop from a route into the
 *  engine it delegates to, and 303 routes that had never been compared became comparable. 48 of
 *  them disagreed with their client type (47 after one proved to be the gate's own defect, see
 *  below). *They are newly VISIBLE, not new* — every one of them
 *  predates this change, and `no_expiry` (EXPIRY-UNDATED, closed hours earlier) sat in exactly this
 *  blind spot: 605 of 1016 routes `return engine.func(...)`, so the majority of the surface was
 *  never read by the gate that exists to read it.
 *
 *  **One of the 49 was never a gap at all, and finding that out cost nothing but asking.** The
 *  entry for `POST /projects/{}/supply/competitive` carried fourteen keys of which thirteen were
 *  phantoms: that method returns a UNION, and `checker.getPropertiesOfType` on a union returns the
 *  INTERSECTION — the TypeScript-correct answer to "what may I read without narrowing" and the
 *  wrong one to "is this key named anywhere in the client's declarations". *A derivation that asks
 *  a subtly different question produces a confident list, and a list reads as evidence.* The
 *  extractor unions the branches now, with two self-tests; the removed entry is recorded in place
 *  rather than deleted, because a seeded ratchet whose first measurement was partly wrong is worth
 *  saying out loud. 47 remain.
 *
 *  **NOBODY HAS TRIAGED THESE 47 (LOD-UNREAD took the largest one the same day).** They are seeded as a measured ratchet that may only go DOWN —
 *  the instrument `KNOWN_UNCALLED` and the unowned-file ceiling already use here — because the
 *  alternative was to declare ~130 fields across 48 client types in one unreviewed sweep, and a
 *  declaration added to silence a gate is a declaration nobody checked against its engine. Stating
 *  the number and refusing to let it grow is a true claim; declaring the fields would have been a
 *  false one. Delete an entry when you have READ the engine and declared what it sends.
 *
 *  **The measured shape, because it decides where triage is worth starting:** the overwhelming
 *  majority are QUALIFIER keys — `unassessed`, `refused`, `excluded`, `limitation`,
 *  `reasons_not_recorded`, `limited_by`, `orphans`, `values_truncated`, `unmatched_guids`,
 *  `partially_scored`, `disclaimer`, `data_date`. That is not a coincidence and it is the same
 *  finding as CLASH-TRUNC and VERDICT-COVERAGE one layer along: *an engine states what it could not
 *  evaluate, and the client type declares the answer without the caveat.* Only the engine knows the
 *  caveat exists, so dropping it from the type makes the screen look complete.
 *
 *  **49 were measured and one was FIXED rather than seeded**, which is the argument for triaging the
 *  rest: `POST /projects/{}/design/options/score` was the OPTION-BOARD-DARK card, shipped in this
 *  same session hours before this gate could see it. It dropped `partially_scored`,
 *  `partially_scored_note`, `carbon_basis` and `carbon_basis_mixed` — so the card ranked
 *  quantity-derived carbon against typology benchmarks in one column while the engine's own
 *  sentence, "⚠ CARBON BASES ARE MIXED … the carbon ranking across this set is not like-for-like",
 *  went unrendered; and a partially-scored option topped the table with no star and no explanation.
 *  The deck was worse: `board_pdf` drew `note[:180]` and the engine APPENDS that warning to a
 *  boilerplate 480 characters long, so the warning was past the cut on every render there has ever
 *  been. *The first defect this gate found was its own author's, and the gate found it in hours.*
 */
const KNOWN_GAPS: Record<string, string[]> = {
  // `basis`, `limitation`, `excluded` — what the rate is and is not.
  "GET /benchmarks/unit-rates": ["basis", "excluded", "limitation"],
  "GET /interop/speckle/status": ["server_version"],
  "GET /portfolio/risk": ["weights"],
  "GET /projects/{}/action-items/tracker": ["by_priority", "by_state"],
  "GET /projects/{}/bidding/scope-gap": ["covered_without_specs", "spec_section_count", "spec_sections"],
  "GET /projects/{}/cap-table": ["pipeline_commitment", "workflow_in_use"],
  "GET /projects/{}/change-orders/log": ["by_state", "change_events_by_scope", "rejected_value"],
  // `support_unscheduled` — the 4D pairs with no date to clash on.
  "GET /projects/{}/clash/sequence": ["support_unscheduled"],
  // `excluded_comparables` — the comps a valuation did NOT use.
  "GET /projects/{}/comps/tiered": ["excluded_comparables", "requested"],
  "GET /projects/{}/cost/lien-waiver": [
    "application_no", "claimant", "customer", "exceptions", "signature_block", "through_date",
  ],
  "GET /projects/{}/cx/matrix": ["note"],
  // `orphans` — documents attached to nothing.
  "GET /projects/{}/documents/health": ["note", "orphans"],
  "GET /projects/{}/elements/{}/records": ["note"],
  // `refused` — conditions the engine would not rule on.
  "GET /projects/{}/entitlements/conditions": ["live_count", "refused"],
  "GET /projects/{}/envelope/audit": ["note"],
  "GET /projects/{}/estimate/resource-based": ["source"],
  "GET /projects/{}/feasibility/compare": ["error"],
  "GET /projects/{}/info-requirements/cascade": ["children", "nodes"],
  // **SHRUNK 2026-10-14 under PPC-UNASSESSED, and the undeclared keys were the SYMPTOM.**
  // `reasons_not_recorded` and `unassessed` are declared and rendered now; `note` stays because
  // nothing branches on prose. The defect was in the two keys that WERE declared: `ppc: number` and
  // `rating: string`, when the engine returns `null` for both while the period is unmeasurable — so
  // the health strip printed "Lean PPC: 0%" in critical red on a team mid-week (`null * 100` is
  // `0`, and a `null` rating fell through a two-literal ternary to its default branch). *No key-set
  // comparison can see a nullability that is simply wrong — this gate asks which keys are NAMED,
  // never whether the names are TRUE*, which is the limit of the instrument and worth writing here
  // rather than discovering twice.
  "GET /projects/{}/lean/ppc": ["note"],
  // **TRIAGED AND LARGELY CLOSED the same day, under LOD-UNREAD — this is what a ratchet going
  // down looks like.** It was the largest gap in the tree at ten keys, four of them coverage, over
  // an LOD verdict the screen rendered as a bare band table titled "LOD coverage". Seven are now
  // declared and rendered (`apps/web/src/portal/panels/lodCoverage.ts`).
  //
  // The three left are NOT undeclared by omission. `targets` and `default` are the target matrix,
  // which has its own route (`/lod/targets`) and its own card — declaring it here a second time
  // would make two screens able to disagree about it, which is the defect
  // `apps/web/src/api/noRespelledShapes.test.ts` exists to forbid. `note` is the engine's prose; no
  // consumer branches on it and a declared `note` invites one to. *An entry that shrinks for a
  // stated reason is a different thing from one that shrinks to zero.*
  "GET /projects/{}/lod/assessment": ["default", "note", "targets"],
  "GET /projects/{}/mep/model-extract": ["by_discipline", "note"],
  "GET /projects/{}/model/columnar/stats": [
    "est_interned_bytes", "est_naive_string_bytes", "note", "string_references",
  ],
  "GET /projects/{}/models/health": ["note"],
  "GET /projects/{}/modules/{}/board": ["counts"],
  "GET /projects/{}/naming/audit": ["conventions"],
  "GET /projects/{}/payapp/lien-exposure": ["vendor_count"],
  // `disclaimer`, and `code_edition`, which decides what the check MEANT.
  "GET /projects/{}/permit/readiness": ["code_edition", "disclaimer", "egress", "sheet_series"],
  "GET /projects/{}/precon/decisions": ["by_category", "by_status", "decided_count"],
  "GET /projects/{}/prequal/coi-expiry": ["soon_days"],
  "GET /projects/{}/procurement/gate": ["note"],
  "GET /projects/{}/schedule/flowline": ["interferences", "issues"],
  // `data_date` — without it, every date verdict on this payload is relative to nothing.
  "GET /projects/{}/schedule/health": ["activity_count", "data_date", "issues", "relationship_count"],
  "GET /projects/{}/standards/check": ["supported"],
  // `values_truncated` — the property diff is a PAGE and says so in a key no client declares.
  "GET /projects/{}/versions/diff": ["property_values_available", "values_truncated"],
  "GET /projects/{}/view-templates/{}/graphics": [
    "cut_count", "graphics", "hidden_count", "name", "note", "template",
  ],
  "GET /projects/{}/vitals": ["area", "cost_sf", "float", "health", "irr", "lod"],
  "GET /rooms": ["note"],
  "POST /connections/{}/query": ["limit"],
  "POST /projects/{}/drawing-set/generate": ["register"],
  "POST /projects/{}/drawings/{}/revise": ["markups_carried"],
  "POST /projects/{}/estimate/conceptual": [
    "height_factor", "market", "note", "region", "soft_cost_pct", "year",
  ],
  // `unmatched_guids`/`t1`/`t2`. PROGRESS-DARK closed the engine's half of exactly this
  // ("never silently dropped" and it dropped); the client type still cannot see the counts.
  "POST /projects/{}/progress/capture-diff": ["unmatched_guids", "unmatched_t1", "unmatched_t2"],
  "POST /projects/{}/schedule/level": ["caps", "issues", "mode"],
  "POST /projects/{}/specialty/monte-carlo": ["seed", "variables"],
  // **REMOVED 2026-10-14, AND IT WAS NEVER A GAP.** This entry was seeded with fourteen keys and
  // thirteen of them were phantoms: `competitiveSupply` returns
  // `SupplyAssessment | SupplyIndexResult`, and `checker.getPropertiesOfType` on a UNION returns
  // the INTERSECTION — `{note}` — so every branch-specific field read as undeclared. The fix is in
  // `extract` above. *The gate's first measurement included a confident list of fields that were
  // fully declared*, which is the cost of seeding a ratchet from a derivation before asking whether
  // it asks the right question — and the reason the entry is recorded here rather than silently
  // deleted. One route, thirteen keys, found by reading the type rather than the list.
  "POST /projects/{}/sync/procore/push": ["direction", "source"],
  "POST /projects/{}/waterfall": ["gp_contrib", "lp_contrib"],
  "POST /test-fit/compare": ["plate"],
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
  // Added 2026-10-12 by CLASSIFY-DARK giving the route its first client method. The handler returns
  // `{**{k: v for k, v in result.items() if k != "rows"}, "rows": ..., "returned": ..., ...}` — the
  // whole coverage block arrives through a comprehension, so only the five pagination keys can be
  // named statically. The client declares the coverage fields by EXTENDING `ClassifyCoverage`,
  // which `/classify/coverage` does declare in full, so the keys are checked — one route over.
  "GET /projects/{}/classify/proposals",
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
  // Added 2026-10-13 by WORKFLOW-DARK giving `PUT /projects/{pid}/workflow/{key}` its first client
  // method: the route returns `{"module": key, "saved": len(...), **result}`, where `result` is
  // `workflow_config.validate`'s dict, so only `module` and `saved` can be named statically. Same
  // arrival as `/cost/datasets/import` above — *this gate can only see a route that HAS a typed call
  // site, so wiring a dark route is what makes its response comparable at all*, and the entry is the
  // price of the comparison rather than a defect. The declared type enumerates `validate`'s six keys,
  // which is complete against today's engine and unverifiable by a static walk over the literal.
  "PUT /projects/{}/workflow/{}",
  // --- RESPKEY-DELEGATED, 2026-10-14: the 14 that arrived with the one-hop resolver ------------
  // These are not new spreads. They are routes whose body is `return engine.func(...)`, so until
  // the resolver followed the hop this gate had no key set for them at all and could not ask the
  // question — and the ENGINE's return literal is where the `**spread` lives. Each is a lower
  // bound for the same reason as the entries above: the keys below can be named, whether there are
  // MORE cannot. *A route moving from "invisible" to "lower bound" is this list getting longer
  // because the gate got better, which is the opposite of a regression.*
  "GET /connections/{}/tables",
  "GET /projects/{}/comps/tiered",
  "GET /projects/{}/deal-room/authority",
  "GET /projects/{}/resilience/weather",
  "GET /projects/{}/schedule/health",
  "GET /projects/{}/schedule/windows",
  "POST /estimate/assembly/price",
  "POST /license/cloud-check",
  "POST /projects/{}/concept-render/request",
  "POST /projects/{}/coordination/stale/recheck",
  // The five schedule engines, all one shape: `scheduler`/`schedule_compress` return
  // `{**result, ...}` over a dict the optimiser builds, so the literal names the envelope and the
  // payload arrives through the spread.
  "POST /projects/{}/schedule/collapsed",
  "POST /projects/{}/schedule/compress",
  "POST /projects/{}/schedule/impacted",
  "POST /projects/{}/schedule/portfolio",
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
  // `sf.fileName` is forward-slashed on every OS; a caller's `path.resolve` is backslashed on
  // Windows. Compared raw, `startsWith` failed for every file there and the walk found an empty tree.
  const posix = (p: string) => p.replace(/\\/g, "/");
  const rootTs = posix(root), baseTs = posix(relBase);
  for (const sf of program.getSourceFiles()) {
    if (sf.isDeclarationFile || !sf.fileName.startsWith(rootTs)) continue;
    if (sf.fileName.includes("/vendor/") || sf.fileName.endsWith(".test.ts")) continue;
    const visit = (node: ts.Node): void => {
      const pathArg = ts.isCallExpression(node) ? node.arguments[0] : undefined;
      if (ts.isCallExpression(node) && ts.isPropertyAccessExpression(node.expression)
          && node.expression.name.text === "json" && pathArg !== undefined) {
        const rel = sf.fileName.slice(baseTs.length).replace(/^\//, "");
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
          // A UNION DECLARES EVERY BRANCH'S KEYS, AND `getPropertiesOfType` RETURNS THE
          // INTERSECTION. That is the TypeScript-correct answer to a different question — what you
          // may read without narrowing — and the wrong one here, where the question is whether a
          // key the server sends is NAMED anywhere in the client's declarations. On
          // `SupplyAssessment | SupplyIndexResult` the intersection is `{note}`, so the gate
          // reported 13 fully-declared fields as undeclared, and **those 13 were seeded into
          // `KNOWN_GAPS` as measured gaps before this was found** — a confident list of phantoms
          // that would have sent the next reader looking for a defect that was never there. *A
          // number with a list attached reads as evidence*, which is the whole reason the ratchet
          // has to be measured by a derivation that asks the right question.
          //
          // It is a weaker check than an exact shape, and deliberately so: a union does not say
          // WHICH branch carries a key, so a key named only on an irrelevant branch passes here.
          // That is this gate's scope — declaration VISIBILITY, which is what every audit built on
          // these interfaces depends on. Branch correctness belongs to the consumer's own test.
          const parts = t.isUnion() ? t.types : [t];
          const named = new Set<string>();
          for (const part of parts)
            for (const sym of checker.getPropertiesOfType(part)) named.add(sym.getName());
          const keys = [...named].sort();
          // `Record<string, unknown>` resolves to ZERO named properties. That is neither "declares
          // nothing" nor "declares everything": it type-checks while naming nothing, so a field
          // under it is still invisible to every audit built on these interfaces. Its own bucket.
          // `every`, not `some`: one opaque branch beside a named one still names those keys, and
          // `keys.length === 0` already means no branch named anything.
          const opaque = keys.length === 0 && parts.every((part) =>
            !!(checker.getIndexTypeOfType(part, ts.IndexKind.String)
              ?? checker.getIndexTypeOfType(part, ts.IndexKind.Number)));
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

  const server: Record<string, { keys: string[]; literal: boolean; complete: boolean;
                                 hops: string[] }> = JSON.parse(
    execFileSync("python3", [resolve(REPO, "services/api/response_keys.py")],
                 { cwd: REPO, encoding: "utf8", maxBuffer: 64 * 1024 * 1024 }));

  const declared = new Map<string, Set<string>>();
  const opaque = new Set<string>();
  for (const r of rows) {
    if (!declared.has(r.key)) declared.set(r.key, new Set());
    for (const k of r.keys) declared.get(r.key)!.add(k);
    if (r.opaque) opaque.add(r.key);
  }

  // RESPKEY-DELEGATED: a route that hands off to an engine is now comparable too. `literal` alone
  // described 279 of 1016 routes, because 605 of them `return engine.func(...)` — so this gate had
  // no view of the MAJORITY of the surface, and `no_expiry` (EXPIRY-UNDATED) hid in exactly that
  // blind spot. `hops` names where a delegated key set came from, so a reader knows which function
  // to go and look at rather than searching the route body for a literal that is not there.
  //
  // **EXTENDING THE PRODUCER WAS NOT ENOUGH, and that is worth recording**: `response_keys.py`
  // emitted the new keys and this line dropped every one of them, so the gate went green over 303
  // newly-resolved routes while reading none of them. *A derivation whose consumer still filters
  // it out is a derivation that did not happen.*
  const dictRoutes = Object.entries(server)
    .filter(([, v]) => v.literal || v.hops.length > 0);
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

  it("reads EVERY branch of a union, not the intersection", () => {
    // The defect this gate shipped with for one commit. `getPropertiesOfType` on a union returns
    // only the shared members — the TypeScript-correct answer to "what can I read without
    // narrowing", and the wrong one for "is this key named anywhere in the client's declarations".
    // Measured on the real tree: 13 declared fields of `competitiveSupply` reported as gaps.
    const { program: p, root } = syntheticProgram(
      "interface A { a: number; note: string }\ninterface B { b: number; note: string }\n"
      + "declare const c: any;\nfunction f() { return c.json<A | B>(\"/x\"); }\n");
    const { rows: r, unresolved: u } = extract(p, root);
    expect(u).toEqual([]);
    // the intersection would be ["note"] alone — that is the mutation this assertion refuses
    expect(r.map((x) => x.keys)).toEqual([["a", "b", "note"]]);
    expect(r[0]!.opaque).toBe(false);
  });

  it("calls a union of two opaque branches opaque, and a mixed union NOT opaque", () => {
    // `every`, not `some`: a named branch beside a `Record` one still names those keys, so the
    // route is comparable and must not fall into the bucket that skips comparison entirely —
    // which is the fail-OPEN direction of the same bug.
    // Index signatures written out rather than `Record<…>`: `syntheticProgram` runs with
    // `noLib: true`, so `Record` does not resolve and silently becomes `any` — which is neither
    // branch of this check. *A fixture that cannot express the case under test passes for the
    // wrong reason*, and the first draft of this assertion did exactly that.
    const both = syntheticProgram(
      "interface O1 { [k: string]: unknown }\ninterface O2 { [k: string]: number }\n"
      + "declare const c: any;\nfunction f() { return c.json<O1 | O2>(\"/x\"); }\n");
    expect(extract(both.program, both.root).rows[0]!.opaque).toBe(true);
    const mixed = syntheticProgram(
      "interface A { a: number }\ninterface O1 { [k: string]: unknown }\ndeclare const c: any;\n"
      + "function f() { return c.json<A | O1>(\"/x\"); }\n");
    const row = extract(mixed.program, mixed.root).rows[0]!;
    expect(row.opaque).toBe(false);
    expect(row.keys).toEqual(["a"]);
  });

  it("accepts a BACKSLASHED root, which is what `path.resolve` returns on Windows", () => {
    // The whole-tree run above builds its root with `path.resolve`, which on Linux never contains a
    // backslash — so CI could not see this. On Windows every file failed the prefix test: four tree
    // assertions went red, and the fifth, `exactly the known ones`, PASSED — `KNOWN_GAPS` is empty,
    // and so is a walk that looked at nothing. Only the vacuity guard stood between that and a green
    // gate. Pinned here, where it runs on every OS.
    const { program: p } = syntheticProgram(
      `declare const c: any;\nfunction f() { return c.json<{ a: number }>("/x"); }\n`);
    const { rows: r } = extract(p, "\\synthetic");
    expect(r.map((x) => ({ rel: x.rel, key: x.key }))).toEqual([{ rel: "probe.ts", key: "GET /x" }]);
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

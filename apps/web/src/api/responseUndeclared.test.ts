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
/** Routes whose client type names some properties AND carries a string index signature, so a key
 *  the server sends type-checks whether or not anybody named it. Pinned exactly: adding one is a
 *  declaration escape hatch and should be a decision, not a drift. Measured at 4.
 *
 *  Three of the four have no disagreement to report. The fourth is `BY_INDEX_SIGNATURE` below. */
const INDEXED_ROUTES = [
  "GET /connections/{}/{}/{}",
  "GET /projects/{}/drawings/sheet-regions",
  "GET /projects/{}/vitals",
  "POST /projects/{}/proforma/renovation",
];

/** Keys the server sends that the client declares THROUGH a string index signature rather than by
 *  name — so they type-check, and `getPropertiesOfType` cannot see them.
 *
 *  **This is not a backlog and that is why it is not in `KNOWN_GAPS`.** That list's own header says
 *  it exists "to shrink as they are fixed rather than rotting into a freeze-list nobody re-checked"
 *  and says to "delete an entry when you have READ the engine and declared what it sends" — and
 *  these cannot shrink, because the index signature is the chosen declaration and naming the six
 *  keys individually would *contradict* it. An entry no action can remove is the freeze-list that
 *  header warns about, arriving by a door the header did not anticipate.
 *
 *  Each entry is asserted to still BE index-signature-declared, so it cannot outlive its reason —
 *  the same shape as `EXEMPT` above. Delete the index signature and these become real gaps. */
const BY_INDEX_SIGNATURE: Record<string, { keys: string[]; why: string }> = {
  // `VitalsPayload` is `{ order: string[]; [key: string]: Vital | string[] | undefined }`. The six
  // keys ARE the vitals, and the set is data-driven: `aec_api.vitals` builds it from the literal
  // `["lod", "area", "cost_sf", "float", "irr", "health"]` and `apps/web/src/shell/vitalsBar.ts`
  // renders by iterating `data.order` rather than by reaching for a field, so no named property
  // would be read even if one existed.
  "GET /projects/{}/vitals": {
    keys: ["area", "cost_sf", "float", "health", "irr", "lod"],
    why: "the vitals set is data-driven — the server sends `order` and the bar iterates it",
  },
};

const KNOWN_GAPS: Record<string, string[]> = {
  // **CLOSED 2026-10-14 under UNITRATE-BASIS.** The three keys were the three sentences that say
  // what the median is worth — and `limitation` is literally an instruction the screen was not
  // following: *"Check `spread_ratio` and `per_project` before quoting a median."* The table printed
  // the median, p25 and p75 and withheld the spread. *An engine that tells you what to check before
  // quoting it has done the hard part.*
  "GET /interop/speckle/status": ["server_version"],
  "GET /portfolio/risk": ["weights"],
  "GET /projects/{}/action-items/tracker": ["by_priority", "by_state"],
  // **CLOSED 2026-10-14 under SCOPE-THIN, and `covered_without_specs` was a live defect.** The
  // engine matches an element's NCS discipline to a package that CLAIMS that discipline, and flags
  // separately what its own note calls *"thin, non-traceable coverage"* — a discipline covered by a
  // package citing no CSI spec section. The only screen that calls the route read `gaps` and
  // nothing else, so its else-branch printed **"✅ Every model discipline is covered by a bid
  // package"** over a job where every covering package cited nothing, with `covered_pct` at 100%.
  // `services/api/test_scope_gap.py` already asserted the engine flags that case — *the engine was
  // proven right and the screen was the only place the distinction did not reach.*
  // The per-discipline `spec_sections` on each `covered` entry was undeclared too and is NOT in the
  // list above: this gate compares a route's top-level keys, so the root `spec_sections` was
  // visible to it and the nested one was not — the same root-only blind spot MC-UNDEFINED records.
  // **CLOSED 2026-10-14 under CAPTABLE-PIPELINE, and the two keys were the reconciliation of an
  // EQUITY table.** `total_commitment` is committed capital — the denominator ownership is computed
  // against — and `pipeline_commitment` is the uncommitted interest the engine keeps on screen at
  // 0% rather than dropping. The Investors tab rendered a Commit column of `row.commitment` under a
  // Total row of `total_commitment`, so on the engine's own docstring scenario the column summed to
  // **$16,000,000** under a total of **$6,000,000** — measured live. *A total whose own parts do
  // not sum to it leaves the reader to invent the difference*, which is CO-REJECTED on equity
  // instead of change orders, and on the one table where the invented difference reads as dilution.
  //
  // `workflow_in_use` is the engine's own distinction and a 0% row means two different things
  // without it: `investor` stamps `initial: prospect`, so until somebody runs `commit` that state
  // carries no information and EVERY row counts.
  //
  // **Nothing could see the row surface at all**: `rows` was declared `Record<string, unknown>[]`,
  // the OPAQUE bucket in `apps/web/src/api/deadFieldTyped.test.ts` (it names nothing), so
  // `counts_toward_ownership` and `status` — which the engine carries on the row *deliberately*,
  // because "seven call sites read this table" — were outside every audit here, and this gate skips
  // an opaque route. The consumer then cast to `any`. *An opaque row type is a field list nobody can
  // audit and every consumer must guess at.* Both are named interfaces now.
  // **CLOSED 2026-10-14 under CO-REJECTED, and `rejected_value` was the arithmetic.** `total_value`
  // counts every COR raised, REJECTED ONES INCLUDED, while `total_schedule_days` already excluded
  // their days — the same refusal, two treatments, one function. The report printed four of the five
  // money figures, so on a four-COR fixture it read **total $575,000** beside pending/approved/
  // executed of $175,000, and the $400,000 residue was the refused COR with no name on the screen.
  // *A total whose own parts do not sum to it leaves the reader to invent the difference*, and on a
  // change-order report the invented difference reads as exposure.
  // `services/api/test_refusal_readers.py` gained this as instance 6 — it said it *"covers the
  // remaining five and is the gate that keeps the class from re-opening"*, over a hand-made list,
  // and **26 of 139 modules declare a refusal-shaped state.**
  // `support_unscheduled` — the 4D pairs with no date to clash on.
  "GET /projects/{}/clash/sequence": ["support_unscheduled"],
  // **CLOSED 2026-10-14 under COMPTIER-DARK.** `requested` is the band for the field the `field`
  // parameter exists to choose, so the one statistic the route is parameterised on was unreachable
  // from TypeScript; `excluded_comparables` is the appraiser's own decision, which the engine names
  // on purpose (*"a sample that shrank without saying so reads as a thinner market rather than as a
  // decision somebody made"*) and which no client could read. The route had no caller at all, so
  // the fix was a screen — and writing one surfaced two engine defects that reading the key list
  // could not: `comparable.source` is a SELECT whose options the tier ladder had never been shown
  // (four of seven fell to the weakest tier), and `conflicts_resolved` reported the whole
  // register's count while sitting among keys that are all properties of one band.
  // *A dark route's undeclared keys are the cheapest thing wrong with it.*
  // **CLOSED 2026-10-14 under LIEN-PLACEHOLDER, and this was the highest-stakes entry in the
  // list.** The six undeclared keys were every field that says WHO is releasing WHAT, through WHEN,
  // and what is carved out — `claimant`, `customer`, `through_date`, `application_no`, `exceptions`,
  // `signature_block` — on a STATUTORY lien waiver. The screen declared `amount` and showed it in a
  // status line, and *the amount is the least legally consequential number in a release.*
  //
  // The gap also sat beside something no key comparison could reach: the routes take `claimant`,
  // `customer` and `through_date` and nothing passed them, so the PDF a subcontractor would sign
  // read `[Claimant]`, `[Customer]`, `[Owner]` and `through [date]` literally — measured end to
  // end against a live server.
  "GET /projects/{}/cx/matrix": ["note"],
  // `orphans` — documents attached to nothing.
  "GET /projects/{}/documents/health": ["note", "orphans"],
  "GET /projects/{}/elements/{}/records": ["note"],
  // `refused` — conditions the engine would not rule on.
  // **CLOSED 2026-10-14 under COND-REFUSED, and this pair was a live defect rather than a gap.**
  // `refused` is the DENIED entitlements and `live_count` is the population the totals beside it
  // cover. `approval_conditions.assess` zeroes a refused row's counts so it *"cannot read '3 open'
  // while contributing 0 to the total"* — correct, and the card read only the counts, so a denied
  // variance with five unaddressed conditions printed as `ENT-002 — 0 open`: the most reassuring
  // row the card can produce, for a permission the agency refused. Measured live, not reasoned.
  // `services/api/test_refusal_readers.py` already proved the engine honours the refusal, including
  // `live_count + len(refused) == entitlement_count` — *its subject was the engine, and nothing
  // asked the same question of the reader.*
  // **CLOSED 2026-10-14 under BASIS-UNREAD, and `note` was the smallest part of it.** The engine's
  // sentence — *"Representative prescriptive values — a first-pass screen, not a stamped energy
  // model"* — was unreachable from TypeScript, and so were `required_min_r`/`provided_r`,
  // `required_max_u`/`provided_u`, `margin` and the per-assembly `issue`, none of which this gate
  // could see: they are NESTED on `results[]`, and this gate compares a route's TOP-LEVEL keys.
  // *The one key it could see was the one with the least consequence.* The live defect was in two
  // keys that were both declared: `checked` is the assemblies the engine could rule on and `total`
  // is every one registered, and the card read the first and never the second — `4/4 assemblies
  // compliant (100.0%)` over a 40-row register, measured; and with `checked` at 0 the card took an
  // empty-state branch reading **"no envelope assemblies registered"** over forty of them.
  "GET /projects/{}/estimate/resource-based": ["source"],
  // **CLOSED 2026-10-14 under DRAFT-BASELINE, and the top-level key was the smaller half.**
  // `error` is the module-not-installed refusal, which arrives beside an empty `scenarios` and is
  // otherwise indistinguishable from a bare register. The live defect was NESTED and therefore
  // invisible to this gate, which compares a route's top-level keys: `workflow_state` on every
  // scenario. `compare` ranks by unit yield and measures every delta against whichever scheme
  // wins, and its own note enforces the rule for one state — *"a replaced scheme cannot be the
  // baseline the live ones are measured against"* — then says, correctly, *"Drafts ARE ranked: an
  // unapproved scheme is a real option to test."* Both right; the reader was never told which it
  // is. Measured on two schemes on one 20,000 SF site: a DRAFT FAR-8 scheme ranked first and the
  // APPROVED FAR-4 scheme came back at **−68 units / −72,000 SF** against it, with no state column
  // and `delta_gfa_sf` computed and never rendered. *The fix belongs on the screen, not in the
  // ranking*, which is why the engine is untouched.
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
  // **CLOSED 2026-10-14 under LOD-TARGET-INERT, and the three keys were the BASIS of a compliance
  // table.** `targets` is the firm's authored matrix, `default` is the built-in RIBA/AIA stage
  // matrix, and `using_default` (declared since LOD-UNREAD, read by nothing) says which was in
  // force — while the table's own header read "Against the target matrix, per stage" and never
  // named it. *A compliance percentage whose threshold the reader cannot see cannot be checked.*
  //
  // Two live defects sat behind them. The `note` promised *"With no targets registered the
  // RIBA/AIA stage defaults apply"* and they did NOT: `assess` derived its stages from the authored
  // list, so a project with no targets got `compliance: {}` with `using_default` true — measured on
  // a 3-element index. And the register's only REQUIRED field, `element_category`, is free text and
  // is not one of the three matching keys, so the obvious authoring was accepted and resolved
  // against nothing: `no_target: 3` of 3 with an empty `short_by_rule`.
  // `targets_matching_nothing` now separates those, and the response type is NAMED — which is what
  // the inline ceiling in `apps/web/src/api/deadFieldTyped.test.ts` asked for when this change
  // added four keys to an inline declaration.
  "GET /projects/{}/mep/model-extract": ["by_discipline", "note"],
  "GET /projects/{}/model/columnar/stats": [
    "est_interned_bytes", "est_naive_string_bytes", "note", "string_references",
  ],
  "GET /projects/{}/models/health": ["note"],
  "GET /projects/{}/modules/{}/board": ["counts"],
  "GET /projects/{}/naming/audit": ["conventions"],
  // **CLOSED 2026-10-14 under WAIVER-FLAT, and `vendor_count` was the LEAST of it.** This gate
  // compares a route's top-level keys, so the one undeclared key here was the population; the live
  // defect was two keys that were DECLARED and read by nothing. `status` is the engine's verdict on
  // whether money paid out has been released — `clear` · `conditional_only` · `no_waiver` — and
  // `waived_conditional` is the amount behind it. The card rendered Vendor / Paid / Unconditional
  // waived / Exposure, so a vendor holding a signed conditional release for the whole balance and
  // one holding nothing at all came out as the SAME ROW, both in `--status-crit`, measured at
  // $200,000 each on a live server. On a lien screen those are two different decisions: chase a
  // signature, or withhold the next payment.
  //
  // **No gate in this tree could have seen it, and that is DEADFIELD-INLINE.**
  // `apps/web/src/api/deadFieldTyped.test.ts` builds its population from exported INTERFACE
  // declarations under `api/`, and this response was declared inline in the `this.json<{…}>` type
  // argument — 562 of 706 call sites are, covering 5,999 of the 8,649 declared field keys. *Naming
  // the response type is what makes it auditable*, which is why the fix names it.
  // `services/api/test_payapp.py` had already asserted `conditional_only` on a $100k exposure; its
  // fixture simply never had a `no_waiver` vendor beside it, so the pair that renders identically
  // was never both present in one response.
  // **CLOSED 2026-10-14 under PERMIT-BLIND, and the entry pointed at the right route for the wrong
  // reason.** `code_edition` was undeclared on the client AND **null in every response this route
  // has ever served** — the server read `analysis.get("edition") or analysis.get("code_edition")`
  // and `code_analysis` has neither key. *A gap in this list means "the client does not name what
  // the server sends"; it cannot mean "and the server sends something true."* Two more findings sat
  // behind it that no key comparison could reach: the route takes FOUR declarations and nothing
  // passed any of them, so one checklist row was permanently unsatisfiable; and `disclaimer` — "NOT
  // a certified plan review. The authority having jurisdiction rules" — went unrendered on a screen
  // that prints READY over a building.
  "GET /projects/{}/precon/decisions": ["by_category", "by_status", "decided_count"],
  // **CLOSED 2026-10-14 under WAIVER-FLAT.** `soon_days` is the horizon `expiring_soon` was
  // computed against, and the card printed `expiring ≤30d` as LITERAL TEXT beside it — true only
  // because the one caller passes the default, so the label was a restatement of a parameter rather
  // than a reading of the answer. `carrier` and `ref` were undeclared on the rows and invisible to
  // this gate for being nested, and `carrier` is who you telephone about an expired certificate.
  "GET /projects/{}/procurement/gate": ["note"],
  // **CLOSED 2026-10-14 under FLOW-CLEAR.** The card is subtitled *"Where each crew is, and whether
  // anyone is in anyone's way"* and rendered four tiles answering none of the second half:
  // `interference_count` was declared and unread, `interferences` and `issues` undeclared. Worse,
  // the adapter projected the `Interference` dataclass with
  // `{k: getattr(i, k) for k in ("task_id", "location_id") if hasattr(i, k)}` — and `task_id` is
  // not a field of `Interference` at all — so FOUR of its five fields never left the server:
  // measured, `[{"location_id": "L01"}]`. It calls `to_dict()` now, which the `issues` line beside
  // it had always called. And `interference_count` is NOT a count of collisions (it is
  // `trades.length - 1`), so the one key the card could have reached for is the one that would have
  // alarmed every reader of a coordinated schedule.
  // **CLOSED 2026-10-14 under SCHEDHEALTH-PARITY.** All four declared and rendered. Three of them
  // were also MISSING FROM BOTH of the engine's refusal shapes, while its own docstring promised
  // "every key the assessed shape carries is present and empty, so a caller reading `checks` or
  // `failed` does not need to special-case this" — and the test asserting that had SUBTRACTED
  // exactly those keys from its comparison and kept the universal label. *This gate cannot see a
  // key that is absent only on a branch, because it compares one shape.* Fourth limit of the
  // instrument in a day.
  "GET /projects/{}/standards/check": ["supported"],
  // **CLOSED 2026-10-14 under VERSION-VALUES, and the top-level keys were the smaller half.** Both
  // are declared and rendered now. What this gate could NOT see is that `from` and `to` were
  // missing from `changed_properties` — a shape one level down — so `versions.diff` had been
  // computing `FireRating: 1HR → 2HR` since VERSION-COMPARE while the only screen that compares two
  // versions printed `FireRating`. *A key-set comparison at the ROOT cannot see a shape that is
  // wrong one level down*, which is the second limit of this instrument found in a day: its entries
  // are a place to LOOK, never a list of what is wrong.
  "GET /projects/{}/view-templates/{}/graphics": [
    "cut_count", "graphics", "hidden_count", "name", "note", "template",
  ],
  // **MOVED 2026-10-14 to `BY_INDEX_SIGNATURE`, which is a reclassification and not a fix.** The
  // six keys are declared — through `VitalsPayload`'s string index signature, which
  // `getPropertiesOfType` does not report. *An entry no action can remove is a freeze-list entry,
  // and this list's header is written against exactly that.* The derivation that identifies the
  // bucket is pinned at 4 routes and each entry's index signature is now asserted.
  "GET /rooms": ["note"],
  "POST /connections/{}/query": ["limit"],
  "POST /projects/{}/drawing-set/generate": ["register"],
  // **CLOSED 2026-10-14 under REVISE-DARK, and the key was WRONG as well as undeclared.**
  // Slip-sheeting tags every markup on the revised sheet `carried_from` so a reviewer re-checks it,
  // and `revise_sheet` incremented the counter in the loop while `db.commit()` sat inside the
  // `except Exception: pass` that exists so tagging can never block a revision. Measured by
  // injecting a failure on that commit: `201 {"revision":"1","delta_count":1,"markups_carried":3}`
  // with **0 of 3 markups actually tagged**. *A count computed before the write that persists it is
  // a count of intentions*, and it ran in the reassuring direction on the one operation where a
  // stale markup is the hazard. The count now follows the commit, `markups_to_carry` and
  // `markups_carry_failed` are published beside it, and the partial mutations are rolled back
  // rather than left pending. The whole route was also callerless — see `clientCallers.test.ts`.
  // **CLOSED 2026-10-14 under ESTIMATE-BASIS.** Five of the six were the BASIS — `region`, `year`,
  // `height_factor`, `soft_cost_pct` and `note` — and a $/SF total shown without them cannot be
  // reconciled against anything; `note` is also where the engine says the estimate is Class 5,
  // beside a band of −15%/+20% that reads far tighter.
  //
  // **`market` was the one that cost money**, and it cost it in a way this gate cannot see: the
  // engine escalates to the midpoint of construction when given `start_year` and `duration_months`,
  // and the card passed neither, so the key was undeclared AND the number was never computed.
  // Measured at $54,131,692 against the $49,476,000 the card showed — 9.4%, $4.66M. *An undeclared
  // key can mean "nobody reads it"; it can also mean "nobody asked for it", and only reading the
  // route tells you which.*
  // **CLOSED 2026-10-14 — and this is the one entry closed WITHOUT giving the route a screen.**
  // PROGRESS-DARK fixed the engine's half (the note promised "never silently dropped" and the
  // filter dropped); the three counts are declared now, which is free and makes them visible to
  // every audit built on these declarations. The route still has no caller, and that is a different
  // problem with a measured cause: it needs two TIMESTAMPED sets of installed GUIDs and nothing in
  // this product persists a capture. Filed as CAPTURE-SESSION; the reason is recorded beside the
  // freeze in `apps/web/src/api/clientCallers.test.ts` rather than left as a date. *Declaring what
  // a route sends and being able to reach it are two different kinds of done, and conflating them
  // is how a gate starts reporting the wrong one.*
  // **CLOSED 2026-10-14 under LEVEL-UNREAD.** `issues` is the engine's `IssueLog`, whose own module
  // docstring is the rule this whole class of defect violates — *"every coercion, drop or fallback
  // emits one of these. A silent default produces a plausible schedule that is wrong, with nothing
  // in the output to look at."* A mistyped predecessor arrived as `MASSING.PREDECESSOR_UNRESOLVED`
  // with `action: "relationship dropped"`, and the screen was where the indication stopped. `caps`
  // is the server's echo and `mode` the only evidence for the client's own "advisory, never writes"
  // claim. The card now also reads the three keys this change ADDED — `within_caps`, `over_cap`,
  // `coverage` — because the response reported the moves it made and the peaks before and after and
  // never compared the second peak to the cap: measured at 26 against a limit of 8, with
  // `move_count: 0` and `finish_moved_days: 0`, *the three figures the card printed are the same
  // three a perfect run produces.*
  // **CLOSED 2026-10-14 under MC-UNDEFINED, and the roots were the lesser half.** `seed` is the
  // only thing that makes a quoted P50 comparable between two readers; `variables` is the engine's
  // echo of what it sampled. Both are now declared and rendered. The real defect was two levels
  // DOWN, in `metrics[*]`, where `undefined` and `prob_at_least_of_defined` were undeclared —
  // *this gate compares a route's top-level keys, which is its known blind spot (b): "a root-only
  // comparison blind to a shape wrong one level down."* Its entry for this route named the two
  // roots and said nothing about the nested pair that made both risk cards caption a percentile
  // with the draws it had excluded.
  // **REMOVED 2026-10-14, AND IT WAS NEVER A GAP.** This entry was seeded with fourteen keys and
  // thirteen of them were phantoms: `competitiveSupply` returns
  // `SupplyAssessment | SupplyIndexResult`, and `checker.getPropertiesOfType` on a UNION returns
  // the INTERSECTION — `{note}` — so every branch-specific field read as undeclared. The fix is in
  // `extract` above. *The gate's first measurement included a confident list of fields that were
  // fully declared*, which is the cost of seeding a ratchet from a derivation before asking whether
  // it asks the right question — and the reason the entry is recorded here rather than silently
  // deleted. One route, thirteen keys, found by reading the type rather than the list.
  "POST /projects/{}/sync/procore/push": ["direction", "source"],
  // **CLOSED 2026-10-14 under WF-BASIS, and these two were the capital base every figure rests on.**
  // `distwaterfall.scenario` computes `lp_contrib = sum(contributed) or lp_commit`, so the pref
  // accrues on that figure, the return-of-capital tier returns it, and both IRRs and both equity
  // multiples are computed against it — with a SILENT fallback to the commitment. Measured on an
  // $8m LP / $2m GP cap table at a $20m exit: nothing contributed returns LP $18,302,056 / IRR
  // 17.99% / GP $1,697,944, **byte-identical to the fully funded deal**; half called gives IRR
  // 33.78% and $1.15m more promote. The card rendered the distributions, both IRRs, both multiples,
  // the pref and the style — and not the base. *An IRR without the capital it is a return on is
  // not a return, it is a ratio.* The two sides also fall back independently, so one waterfall can
  // run on two bases. `lp_basis`/`gp_basis` now say which, and the per-investor shares are both
  // published because the split runs on commitments while the waterfall may not (WF-SPLIT holds
  // that decision — it is an operating-agreement term, not an arithmetic one).
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

interface Site { rel: string; line: number; key: string; keys: string[]; opaque: boolean;
                 indexed: boolean }
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
          // THE THIRD BUCKET, and it is the one `KNOWN_GAPS` mis-filed: a type that NAMES some
          // properties *and* carries a string index signature. `VitalsPayload` is
          // `{ order: string[]; [key: string]: Vital | string[] | undefined }`, so `keys` is
          // `["order"]` — not zero, therefore not `opaque` — while every other key the server
          // sends type-checks through the index signature. Those keys are reported as undeclared
          // and **declaring them is not the fix**: the index signature IS the declaration, chosen
          // because the vitals set is data-driven (`vitalsBar.ts` iterates `data.order`).
          //
          // STRING only. `ts.IndexKind.Number` matches every array-returning route — an array
          // carries a number index AND all 35 `Array.prototype` members as named properties —
          // which measured at a large fraction of the surface and says nothing about declaration.
          // *A predicate that decides what to LOOK at is more dangerous than one that decides what
          // to report*, so this one only labels; the comparison still runs.
          const indexed = parts.every((part) =>
            !!checker.getIndexTypeOfType(part, ts.IndexKind.String));
          rows.push({ rel, line, key: `${method} ${raw.split("?")[0]}`, keys, opaque, indexed });
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
  const indexed = new Set<string>();
  for (const r of rows) {
    if (!declared.has(r.key)) declared.set(r.key, new Set());
    for (const k of r.keys) declared.get(r.key)!.add(k);
    if (r.opaque) opaque.add(r.key);
    // ANY call site, as with `opaque`: one declaration carrying an escape hatch is enough for a
    // key to arrive, type-check, and still be invisible to the field audits.
    if (r.indexed && r.keys.length > 0) indexed.add(r.key);
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

  it("every route declared through a string index signature is tracked as one", () => {
    expect([...indexed].sort(), "a client type both NAMES properties and carries a string index "
      + "signature, so any key the server sends type-checks unnamed. If you ADDED one, record it "
      + "here and say why the escape hatch is right; if you REMOVED one, delete it.")
      .toEqual([...INDEXED_ROUTES].sort());
    // and each BY_INDEX_SIGNATURE entry's reason must still hold — remove the index signature and
    // its keys become real gaps that belong in KNOWN_GAPS, loudly.
    for (const route of Object.keys(BY_INDEX_SIGNATURE))
      expect(indexed.has(route), `BY_INDEX_SIGNATURE names ${route}, whose client type no longer `
        + `carries a string index signature — its keys are undeclared now, not index-declared`)
        .toBe(true);
  }, 120_000);

  it("the tree's undeclared keys are exactly the known ones", () => {
    const actual = Object.fromEntries([...gaps.entries()].sort());
    const known = Object.fromEntries([
      ...Object.entries(KNOWN_GAPS).map(([k, v]) => [k, [...v].sort()] as const),
      ...Object.entries(BY_INDEX_SIGNATURE).map(([k, v]) => [k, [...v.keys].sort()] as const),
    ].sort());
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

  it("separates an index signature from opacity — a named property beside one is NOT opaque", () => {
    // The third bucket, on synthetic source where the answer is known. `opaque` and `indexed` are
    // different questions about the same declaration and the real tree only exhibits one of the
    // four combinations, so the tree pin alone could not tell them apart.
    const mixed = syntheticProgram(
      "interface V { order: string[]; [k: string]: unknown }\ndeclare const c: any;\n"
      + "function f() { return c.json<V>(\"/x\"); }\n");
    const row = extract(mixed.program, mixed.root).rows[0]!;
    expect(row.keys).toEqual(["order"]);
    expect(row.indexed).toBe(true);
    expect(row.opaque, "a type that names a property is not opaque, index signature or not")
      .toBe(false);
    // and the negative: a plain interface is neither.
    const plain = syntheticProgram(
      "interface A { a: number }\ndeclare const c: any;\n"
      + "function f() { return c.json<A>(\"/x\"); }\n");
    expect(extract(plain.program, plain.root).rows[0]!.indexed).toBe(false);
    // A NUMBER index signature is not a declaration escape hatch for a key — it is what every
    // array has, alongside 35 `Array.prototype` members, and matching it swept the surface.
    const arr = syntheticProgram(
      "interface N { [k: number]: string }\ndeclare const c: any;\n"
      + "function f() { return c.json<N>(\"/x\"); }\n");
    expect(extract(arr.program, arr.root).rows[0]!.indexed).toBe(false);
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

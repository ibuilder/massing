# Roadmap

The single product roadmap — **open items only**. Everything shipped lives in
[roadmap-completed.md](roadmap-completed.md); per-release detail is in [CHANGELOG.md](../CHANGELOG.md).
Supporting detail: [gc-portal.md](gc-portal.md) · [ops-dr.md](ops-dr.md) · [mobile.md](mobile.md).
Documentation for readers rather than for planning lives in [README.md](README.md) — the docs index.
Closed-out audits and unbuilt plans moved to [internal/](internal/README.md) on 2026-07-29; that
directory is **not** published to the site.

Three pillars on one IFC-keyed model: **BIM authoring/viewer** · **GC portal** ·
**developer/finance**. All three have depth — finance and CRE from R19 + R20, authoring from R18, the
5D/4D spine from R25, the interaction surface from R26. **What is thin now is the drawing**: the sheet
is still handled as an image with text behind it rather than as data (📐 R27).

**Status — reconciled 2026-08-25 at v0.3.1089.** Backend **628/628** suites green (1,242 s wall, 3
parallel) · vitest **2,006** tests across **196** files · `test_reachable` **358/364** modules
reachable from a route/MCP tool/main (5 entry points reached another way, 1 declared gap) ·
open items **28** · typecheck, eslint and the production build all clean · single-source version in
`apps/web/package.json` · all 7 workflows green on `ee90b2c9`.

**CodeQL: NOT MEASURED HERE, and that is deliberately not the same as zero.** The previous block
claimed "**0** open (queried from the alerts API, not inferred from a green run)" — the right
standard, and it is the standard this pass could not meet: no code-scanning-alerts tool was
available in this session, so all that is known is that the CodeQL *runs* are green.
[`docs/roadmap-directions.md`](roadmap-directions.md) §7 carries the rule in as many words — *"a
green *run* is not zero alerts; query the alerts API"* — and
carrying an unverified **0** forward would have been the exact failure the parenthesis was written
to prevent. **A number nobody re-derived is worse than an admitted gap**, because it reads as
evidence.

*The block this replaces was reconciled at v0.3.778 — **311 releases stale**, and it had already
carried the note that its own predecessor was thirty-eight releases stale. Twice in a row is not
bad luck; it is what a hand-written measurement does. The counts above are the ones this file can
already fail on (`roadmapLanes.test.ts` extracts the item count, `run_tests.py` prints the suite
total) — prefer re-running them to reading this line.*

**The seven-room shell is the ONLY shell.** It renders in the Construction, Developer and Design
workspaces; opening a project lands on the persona's home and every other workspace carries a
`← Project home` signpost (v0.3.739). The `?shell=classic` opt-out was **deleted in v0.3.779** —
`spine.test` now asserts `spineEnabled` and `SPINE_FLAG` are absent, so a revert fails a test rather
than quietly restoring a second rail.

**Read the gating honestly.** A large block of what remains is genuinely blocked — see
[⛔ Gated](#-gated--each-entry-names-its-unblocking-event). The ▶ NOW list below is **only non-gated
work**.

> **Housekeeping note, 2026-07-28.** This file had accumulated **three duplicate NOW sections** with
> contradictory content — items shipped hours earlier still listed as pending, numbering running
> 1, 2, 1, 5, 6, and a header claiming the new shell was opt-in after it had been made default. Cause:
> scripted edits that *inserted* a NOW section instead of replacing one, repeated over several
> releases. Rebuilt by hand here. **If you are editing this file with a script, replace between the
> section markers — never splice at a matched string.**

---
## 📌 START HERE

1. **[roadmap-directions.md](roadmap-directions.md)** — non-negotiables, how to verify, shared-clone
   hazards, lanes, testing, release discipline, what "done" means. **Read before touching anything.**
2. **[What is left, prioritised](#-what-is-left--prioritised)** — the ranked view, below.
3. **[The lanes](#-now--parallel-lanes)** — who owns which paths, so two agents do not collide.
4. **[roadmap-completed.md](roadmap-completed.md)** — what shipped, and why it was built that way.

*This file is the list of work. It is not the place for working conventions — those drifted into it
over several months and were moved out on 2026-07-31 so this could stay readable.*

> ### How to read this file — and what a 2026-08-13 audit found wrong with it
>
> **There are three organising schemes over one set of items, and an item can appear in all three.**
> Bands rank by *consequence*, lanes assign by *path ownership*, rings group by *when someone scanned*.
> That is not redundancy to remove — the bands answer "what next", the lanes answer "can I take it",
> and the rings hold the evidence — but it means **the ring sections are a reference, not a work list.
> Pick from the bands or the lane table; read the ring for why the item exists.**
>
> What the audit changed, all of it verified against the tree first:
>
> - **19 completed items were still listed, 9 of them advertised in the lane table as available work.**
>   A second agent reading "take any item in your lane" could have picked up something already shipped.
>   Removed here; their records are in [`roadmap-completed.md`](roadmap-completed.md).
> - **Five rings held no open work at all** — R27, R29 in part, AUTHORING-GESTURE, R24-TOOLS-SPLIT,
>   R42 and the Reach sweep — 239 lines of research narrative whose conclusions had already shipped.
>   Archived whole. R28 and R29 stayed: both still hold live entries, which an item-regex missed and
>   the lane gate caught.
> - **The file was 3,193 lines for 42 open items.** Roughly one line in fifty was a piece of available
>   work. It is now ~2,830, and the ratio is still the thing to watch when adding a ring.
>
> **What was NOT fixed, and is a judgement call rather than a defect:** most items carry no size, so
> "ranked by consequence-if-wrong" cannot be weighed against cost — the ranking is half a decision.
> And **R24 is the largest open ring by a distance**; an interface backlog that only accumulates is
> usually a sign the ring needs closing and re-cutting, not extending.

---
## 🥇 What is left — prioritised

**Open items: count them, do not read them here.** This line said "49" while the file's own extractor
found 51 and the lane table named 48 — three numbers for one quantity, and the prose one had no way to
notice it was wrong. **A hardcoded total in prose is the drift this roadmap keeps re-learning**, so it
is replaced by its method: `roadmapLanes.test.ts` extracts open items with the `ITEM` regex (bullets
carrying no ✅) and asserts every one is in a lane or explicitly Parked, so the lane table and the item
list cannot disagree without failing a build. Run it for today's number.

Ranked by consequence-if-wrong, then by whether the thing is *reachable* rather than merely *built*.
Sizes are the roadmap's own. ⭐ marks the highest-value item in a band.

### Band 1 — correctness and safety (do first; each is a live wrong answer or an open door)

**EMPTY as of 2026-08-25, and that is a real state rather than a gap in the writing.** Both entries
that occupied this band — **R39-UPLOAD-CAP-APP ①** (v0.3.941–942) and **R41-UPLOAD-WARK**
(v0.3.1069, the content-addressed resumable handshake) — are complete and their full records are in
[`roadmap-completed.md`](roadmap-completed.md). FIN-SUITE-BLIND closed here on 2026-08-01 and is
archived beside them.

**Read that as "nothing is currently KNOWN to be wrong", never as "nothing is wrong."** Every item
this band has ever held arrived from a sweep — the R35 race sweep, the FIN suite audit — and not one
of them arrived from a failing test, because a defect the suite can catch never reaches a roadmap.
So an empty Band 1 measures how long it has been since someone last went looking.

**Three sweeps ran on 2026-08-25 — authz, concurrency and money — and they are recorded below.** Two
of the three found a live defect, and both were fixed in the same release rather than filed here, so
this band is empty *because someone looked*, which is a different state from the one the paragraph
above warns about. **The date to re-derive this from is 2026-08-25, not the 2026-08-01 this passage
carried until the sweeps landed** — a staleness clock that does not get wound when the work happens
is the same defect as A29-GUIDE-UNDERLAY's "(in flight, PR #199)", which read as current for 214
releases.

**The next entry here will still come from a sweep**, and the three axes named in the sweep records
are now spent for this round. The honest next action for this band is therefore *not* another sweep
immediately: it is to pick the next axis deliberately when the surface has moved again — the
concurrency record names the specific thing to watch, a fourth sign-in path.

> ### ✅ AUTHZ SWEEP RUN 2026-08-25 (v0.3.1091) — **no live hole; the gate is the finding**
>
> Axis chosen before starting, per the sprint row's own premise-check: **authorisation**, because two
> of the three subsystems added since the last sweep are auth-adjacent.
>
> **Every one of the four existing authz gates says the same thing about its own limit** — a route
> with no `{pid}` in the PATH is outside `test_route_authz`'s remit. Each closed one way the project
> id arrives by another route: `test_global_authz` (global mutating), `test_body_pid_authz` (a `pid`
> in the BODY), `test_protected_prefix_coverage` (a new top-level prefix). **The remaining one is
> that the id in the path is not the project's, it is the RESOURCE's** — `/attachments/{aid}`,
> `/proforma/scenarios/{sid}`. `require_role` cannot be applied, because there is no `{pid}` for it
> to read.
>
> Enumerated from the live app: **43 routes** in that shape. **All 43 are correctly protected today**
> — 20 by a real admin/scim dependency, 11 by a check in the handler body, 4 by identity as a
> recorded decision, 8 deliberately public. Each of the 11 and each of the 8 was read, not inferred.
>
> **So the sweep found no defect, and that is the result rather than a disappointment.** What it
> found is that the 11 are correct only because of hand-written call-site checks that **no gate can
> see** — and this exact class has failed here twice in three weeks: six of the eight
> `/proforma/scenarios/{sid}` routes "fetched by id and acted, with no ownership check at all"
> (fixed 2026-08-13), and the massing.cloud sign-in door (PR #339, today). `_scenario_for`'s
> docstring says it exists "so that a ninth route cannot be added without answering the question" —
> **which is a convention, and a convention is what has just failed twice.**
>
> `services/api/test_resource_id_authz.py` freezes the four buckets and pins each in-handler route to
> the helper it calls. Mutation-checked three ways: dropping `_scenario_for` from `clone`, adding an
> unguarded route, and leaving a deleted route in the list. **It names its own limit** — it cannot
> tell `_can_read` from `_can_write`, and `_can_write`'s docstring is about precisely that confusion,
> so that distinction stays with review.
>
> **Band 1 is still empty, and the sweep is why that now means something.** It was last defensible
> on 2026-08-01; it is defensible again on the authz axis as of today.

> ### ⚠️ CONCURRENCY SWEEP RUN 2026-08-25 (v0.3.1092) — **this one found a live defect**
>
> Second of the three axes. `test_race_conditions` names the shape its own two defects share —
> *"read state, decide, write, with nothing holding the world still in between"*. Scanned for that
> shape across `services/api/src` (a lookup, an if-absent branch, an INSERT inside it, no
> savepoint): **36 candidates**, against only **3** savepoints in the entire tree.
>
> **Three of them are the sign-in doors, and all three were unguarded.** OAuth, SAML and the
> massing.cloud broker each auto-provision on first sign-in; `User.username` is the primary key, so
> two concurrent first sign-ins both read `None`, both INSERT, and the loser gets a **500 on a
> legitimate login**. Fixed through one shared helper, `auth.get_or_create_sso_user`, using the
> savepoint idiom `modules._next_ref` and `rbac.consume_stepup` already carry.
>
> **The same "one rule, some of the doors" shape as PR #339**, which is the second time in two days
> this subsystem has produced it. That is worth watching: a fourth sign-in path is the risk.
>
> `services/api/test_sso_provision_race.py` holds it. **Its first two drafts were worthless and the
> mutation run is the only thing that said so** — draft 1 passed against the broken code, draft 2
> deadlocked on SQLite's single writer. The entry in `CHANGELOG.md` records why, because the failure
> mode is generic: *a test that cannot fail is not evidence, however many PASS lines it prints.*
>
> **The remaining 33 candidates are NOT all defects** and were not converted — most are get-or-create
> against non-unique rows, where a duplicate is harmless or already impossible. They are a
> population to read, not a work list; the same warning R39-UPLOAD-CAP-APP's entry carries about its
> own count of 34.
>
> ### ⚠️ MONEY SWEEP RUN 2026-08-25 (v0.3.1094) — **a live defect, and a different method**
>
> Third and last of the axes. **It could not be swept the way the other two were, and noticing that
> was most of the work.** `round(x, 2)` appears **732 times** under `services/api/src` — against 43
> routes for authz and 36 sites for concurrency. Converting them would be the mistake
> R39-UPLOAD-CAP-APP's entry names in as many words: *a count is not a work list.* Most are display
> figures where half-even versus half-up changes nothing anyone can act on.
>
> So it was swept **by a property rather than by a population**: *where money is SPLIT, do the parts
> still add up?* That has a yes/no answer, needs no reading of 732 sites, and is the exact boundary
> where a rounding difference stops being cosmetic and becomes a wrong document.
>
> **The JV waterfall failed it.** `run_waterfall` rounded `distributable`, `lp` and `gp`
> independently, though every tier allocates out of the same `cash` — so the parts drifted from the
> total they came from. Measured: **52 of 399 distribution periods (13%) had `lp + gp !=
> distributable`**, a penny out in both directions. A partner reading a statement whose parts do not
> add up to its own total has found an error in the document; this is real money, and it is what a
> promote is argued from. `money.allocate` exists for precisely this and had **no caller here**.
> The capital-call branch had the same shape and the same fix.
>
> `accounting.py` was put to the same question first and is sound — each journal entry debits and
> credits the same figure, so there is no asymmetry to drift.
>
> `services/api/test_waterfall_cents.py` holds it, over a sweep of awkward fractions rather than
> frozen figures. Mutation-checked twice, and **the second matters more**: satisfying the sum by
> *collapsing the split* — handing the LP everything — is caught by a separate assertion that the GP
> still receives a real promote. A gate that only checked "the parts add up" would have applauded a
> waterfall that pays the GP nothing.
>
> **BAND 1 NOW HAS ALL THREE AXES SWEPT** — authz (v0.3.1091, no defect), concurrency (v0.3.1092, one
> defect), money (v0.3.1094, one defect). That is the first time the band's emptiness rests on
> something measured rather than on nobody having looked. **It decays from here**: the next
> subsystem to ship re-opens all three, and the date above is what to compare against.
>
> **The three sweeps did not want the same method, and assuming they would was the thing to avoid.**


### Band 2 — built but unreachable (cheapest real value in the file)

Seven of eleven engines once shipped with no route. The R32 filing-spine entries that occupied this
band are all closed and recorded in [`roadmap-completed.md`](roadmap-completed.md). The current
instances:

- ✅ ⭐ **REFUSAL-READERS — a record in a refused state still counts** *(M — Lane C; population
  DERIVED 2026-08-30, **CLOSED v0.3.1124** — 3 releases, 14 readers, one behavioural gate)*

  **This is a defect CLASS, not a bug.** Between 2026-08-29 and 2026-08-30 five separate fixes landed
  that are all the same mistake: an engine reads records of a type whose workflow carries a refusal
  state and computes as though the refusal never happened — a rejected sub invoice posted to the
  ledger and exported to QuickBooks, a rejected invoice holding a PO in permanent review, an excluded
  comparable still valuing a property, a compliance gate reading the oldest prequalification, and (in
  v0.3.1122) a rejected OWNER invoice booked as Accounts Receivable and Contract Revenue.

  Each was found one at a time, by a proxy the procurement fix itself described as unreliable. So the
  population was derived instead:

  | | |
  |---|---|
  | record types carrying a refusal state | **27** of 139 modules |
  | `list_records` sites against those types | **44** |
  | of those, with no state reference in scope | **17** |
  | ├ real, **fixed in v0.3.1122** | **3** (`owner_invoice`) |
  | ├ **correct as-is**, reasoned | **5** |
  | └ **real and still open** | **9** → **5** → **0** *(4 closed v0.3.1123, 5 closed v0.3.1124)* |
  | *plus* aggregate reads the derivation never counted | **5** (`sum_field` 3 · `count_records` 2) |
  | of those, real and **fixed in v0.3.1122** | **2** (`billed_to_date`, `wip.schedule`) |

  **THE POPULATION WAS DERIVED WRONG THE FIRST TIME, and the error is the most useful thing here.**
  The 17 unfiltered sites break down as 3 + 5 + 9, but v0.3.1122 fixed **five** `owner_invoice`
  readers. The two extra are `project_budget.billed_to_date` and `wip.schedule`, and they were
  **never in the population at all**: the derivation matched `list_records(db, "<type>"` and nothing
  else, while those two read the same records through `sum_field` — a SQL aggregate. Counting the
  other accessors afterwards: `sum_field` 3, `count_records` 2, so 49 reads rather than 44.

  So **two of the five defects that release fixed lived in the 5 sites the derivation could not
  see** — they were found by reading the module, not by the sweep that was supposed to be
  exhaustive. A derived population is only as complete as its list of accessors, and a completeness
  claim computed over one accessor is confident and wrong in exactly the way this entry warns about
  everywhere else. *(Found by review, not by us: the counts did not add up, and the reason they did
  not add up was the finding.)*

  **The nine open ones**, each verified to have no state filter anywhere in its path (the reader *and*
  its downstream helper were both read):

  - ✅ **`design_options.compare`, `option_carbon.compare_carbon`, `option_economics.compare_economics`
    — CLOSED v0.3.1123.** A REJECTED option was named best-in-class on all four populated metrics,
    was `lowest_total` for carbon, and was `best_irr` at 30% against a live 12% — while the same
    `compare` response reported `rejected: 1` in `by_state`. One rule,
    `design_options.DESIGN_OPTION_NOT_IN_CONTENTION`, now shared by all three; each still LISTS the
    option and names it in `not_in_contention`.
  - ✅ **`feasibility.compare` — CLOSED v0.3.1123.** A SUPERSEDED scheme ranked #1 at 240,000 GFA
    against a live 80,000, and the top scheme is the BASELINE every delta is measured against, so a
    live scheme read as a 160,000 SF shortfall against an envelope nobody can build. It also dropped
    `workflow_state` before returning, so no caller could filter even in principle; rows now carry
    it, and `superseded_excluded` names what left. Drafts are still ranked on purpose.
  - ✅ **`rfi.rfi_register` — CLOSED v0.3.1124, but NOT for the reason written here.** This entry
    said a void RFI "counts in the open and overdue totals and in ball-in-court". Measured through
    the route: **all three were already correct** — `void` is in `CLOSED_STATES` and has its own
    ball-in-court bucket. The real defects were two numbers this line never named:
    `cost_impacted_count` and `schedule_impacted_count`, which both read **1** on a register whose
    only impacted RFI had been withdrawn. They are now asserted, along with the three that were
    already right, so a future "fix" cannot double-count them.
  - ✅ **`prequalification.score_project` — CLOSED v0.3.1124.** `high_risk: 1` on a project whose
    only high-risk sub had been rejected. **`score_record` already noticed** — through
    `data["status"]`, a typed free-text field, while ignoring `workflow_state`, the field the reject
    transition sets. It raised a "marked rejected" flag and then scored and counted the record
    anyway: the state read from the wrong field, and acted on in no way that changed a number.
  - ✅ **`approval_conditions.for_project` — CLOSED v0.3.1124.** `total_open: 5`, three of them the
    terms of a DENIED variance. Conditions stay LISTED (an appeal puts them back in play) and count
    zero. **The consumer needed the same fix**: `/entitlements/condition-checks` was model-checking
    those conditions and reporting the misses in `total_not_checkable` — the defect recurring one
    level up, exactly as `feasibility.compare` did inside its own file.
  - ✅ **`specs.submittal_log` and `spine.traceability` — CLOSED v0.3.1124.** `required_total: 5` and
    `missing_total: 5` where three were demanded by a VOID section, and `specs_packaged_pct: 50.0`
    with that same section named in the gap list as a broken link for somebody to go fix. One shared
    rule, `specs.SPEC_SECTION_WITHDRAWN`, asserted to be shared rather than copied.

  **A DEAD METRIC found underneath the RFI fix, and it changed the fix.** `rfi.register` computed
  turnaround from `updated_at`; a module row's timestamp column is `modified_at`. `avg_response_days`
  was therefore permanently `None` — so filtering void RFIs out of it would have been a **vacuous**
  guard over a number that could never compute. Fixed first, then filtered. `quality.py`'s
  `avg_days_to_close` carried the identical typo and is fixed with it (`ncr` declares no refusal
  state, so that one is only the dead-metric half). *A wrong key name degrades to None, and None
  renders as an em-dash on a report — a metric can be dead for as long as nobody expects a number.*

  **THE GATE — `services/api/test_refusal_readers.py`.** Per record type: drive the real route,
  transition into refusal, assert the consuming number does not move. Every exclusion carries a
  **positive control** (the subject drove that number while live) and a **reconciliation** assertion
  (filtered population + excluded list == the total the same response reports). It also asserts the
  class's own invariant — every refusal rule is a named constant, not an inline literal — because a
  record type with several readers is a rule with several places to rot: `owner_invoice` had five,
  `design_option` three, `spec_section` two.

  **A redundant guard, caught by mutation testing and deleted.** The first entitlement patch filtered
  refused records twice: in `assess`, and again in `for_project`'s sums. **No assertion could tell
  the second filter's presence from its absence**, because `assess` had already zeroed the record.
  *A guard whose removal nothing detects is not defence in depth; it is a second place to rot.* The
  same instinct that makes duplicated rules dangerous makes duplicated guards untestable.

  **A FIFTH count that did not move with its filter — and it was on the release that states the
  rule.** `submittal_log.logged_total` is summed submittal-side (over `logged_by_section`), not over
  the rows, so filtering the rows left it behind: a submittal logged against a WITHDRAWN section
  still counted as logged while that section's `required` did not. Found in review, not here.
  *The other four counts accumulate inside the row loop, so filtering the loop moved them for free;
  this one is derived from a DIFFERENT COLLECTION, and a filter on one collection does nothing to a
  total derived from another.* The rule now has a second half: **look for the counts built somewhere
  else.** (The suggested patch was not taken as written — accumulating per enforced row would also
  have dropped ORPHAN submittals, logged against a section number no row matches, which count today.)

  **The size ratchet caught the release too, and the pin came down.** Eighteen lines of new response
  fields went into `apps/web/src/api/client.ts`, under an extraction ratchet at 2,752; the build went
  red at 2,769. The four response shapes moved to `apps/web/src/api/types.ts` as named interfaces —
  what that file exists for — taking the client to 2,731, twenty lines below `main`. *A ratchet that
  makes new code go somewhere better is doing its job; the pin only ever moves down.*

  **What the class cost, and what it taught.** Three releases, 14 readers across 8 record types.
  The derivation named candidates; **reading each one is what separated defect from correct-as-is**,
  and it was wrong in both directions — it missed 5 reads (wrong accessor list) and it mis-named 3
  of the 5 sub-numbers in the RFI entry. *A derived population is a search list, never a finding.*

  **A tenth finding was adjacent and NOT a refusal-reader; it is now its own item, `PORTAL-STATUS`
  (below).** It is recorded there rather than here because this entry is closed, and an open slice
  parked inside a ✅ item is a slice nobody will read again.

  **The five that are CORRECT as-is are the point of the entry, not a footnote.** A pattern-matching
  gate would have "fixed" all five and broken two of them:

  - `rentroll.rent_roll`, `leasemgmt.lease_management`, `proforma` rollover — all three load leases
    unfiltered and filter in the *summarizer* (`rentroll.ACTIVE_STATES`), one call away and outside
    any window a grep would use. `renewal_pipeline` includes expired leases **on purpose** — they are
    its subject.
  - `opendata.py` — one reader builds the DEDUPLICATION set for permit import, so it must see expired
    permits or it re-imports them; the other is a historical permit-timeline benchmark, where expired
    permits are the data.

  *A count is not a population.* The procurement fix said so in its own message — "the population
  needs reading, not just counting" — and this sweep proves the cost both ways: 9 real defects a count
  would have missed the reasons for, and 5 correct readers a count would have broken.

  **When you filter a computation, every count derived from that set must move with it.** This class
  has now produced that corollary three times. v0.3.1122 excluded refused invoices from
  `billed_to_date` and left `invoice_count` unfiltered, so one payload reported money from N
  invoices beside a count of N+1. v0.3.1123 excluded refused options from `priced` and left
  `unpriced_count` derived from all options, so an option WITH an IRR was reported as unpriced; and
  carbon's `measured` + `unavailable` stopped summing to `count`. Both fixed by taking the counts
  against the ranked population and returning `in_contention_count` so the response reconciles.
  *Check this explicitly on each of the remaining five — it is the second-order defect this whole
  class generates, and it has now escaped local verification twice.*

  **A vacuity found by mutation-testing, worth more than the four fixes.** The first `option_carbon`
  mutation did not fire: reverting the fix broke nothing, because the rejected option carried no
  carbon figure and could never have won that ranking. Adding one exposed a SECOND vacuity — with the
  rejected option excluded, nothing was measured at all, so `lowest_total` went `None` and the
  assertion passed for a new wrong reason. Two vacuous checks stacked in one assertion, neither
  visible from a green run. Every exclusion assertion here now carries a **positive control** (the
  subject leads while live), so none can pass merely because its subject was uncompetitive. *Apply
  the same to the remaining five: an exclusion test whose subject could not have won proves nothing.*

  **GATED v0.3.1124, and the obvious gate was the wrong one.** A check that every reader of a
  refusal-bearing type mentions the state produces false positives on all five correct readers, and a
  gate that cries wolf trains people to append to its allowlist without thinking — worse than none.
  The gate that shipped is BEHAVIOURAL: per record type, drive the real route, move the record into
  its refusal state, and assert the consuming number does not move. That is a property rather than a
  pattern, and it cannot be satisfied by a filter in the wrong place — which is the whole point,
  because two of the fixes in this class put the filter somewhere a pattern check would have
  accepted. `services/api/test_refusal_readers.py`.

- ✅ **PORTAL-STATUS — the owner's payment schedule shows a status nobody sets** *(S — Lane C;
  split out of REFUSAL-READERS 2026-08-31, **CLOSED v0.3.1125** the same day)*

  **Measured, and worse than this entry described.** Not "a certified application reads as a draft":
  `paid` was **structurally unreachable**. On `/shared/{token}/digest` with three invoices driven
  through the real transitions — two of them `submit` → `mark_paid`, one of those also carrying the
  select's own capitalised `"Paid"` — the owner's page reported **billed 650,000 / paid 0 /
  outstanding 650,000**, and the invoice paid through the workflow displayed as **`draft`**. The
  comparison was lowercase against a select whose every option is capitalised, so the only value
  that could match was one written straight into the blob, which nothing in the product does — **and
  the only thing that did was the test.** Now 350,000 / 300,000.

  Two readers, one rule (`invoice_status_key`): the JSON, and `_payments_html`'s green "paid" colour,
  which never once fired. The response carries `status_key` beside `status` so the page and its
  totals cannot disagree.

  **The scope finding matters more than the fix.** 17 modules declare both a workflow and a typed
  `status`; a `get("status")` grep returns ~25 hits; **two were the defect.** The rule: the blob is
  wrong only where the workflow can express the same thing (`owner_invoice`, `permit`,
  `prequalification`, `value_engineering`, `weekly_plan`); where the workflow LACKS the concept the
  blob is the authority and reading it is correct — `bid_submission`'s workflow is only
  `[open, closed]`, so `project_budget.py` reading `"Awarded"` is right. Most other hits were never
  module data: computed RAG dicts, a project field, a snapshot, and an external open-data payload.
  *REFUSAL-READERS' population was derived too NARROW and missed five real reads; this one is too
  WIDE and flags twenty-three non-defects. Neither a match nor a miss is evidence — only reading is.*

  **Follow-on — CLOSED v0.3.1126, and it was not harmless.** This entry guessed that the flag merely
  went missing on a workflow-rejected sub. Measured: the flag and the pool were **inverted** — it
  fired on the sub still IN the pool (blob typed "Rejected", workflow `submitted`) and was silent on
  the one the team had refused. The flag now reads `workflow_state`, the same authority as `in_pool`,
  and a typed value the workflow contradicts is reported as a **disagreement** rather than believed
  or dropped. *Predicting which way a defect points is not the same as measuring it — this one was
  worse than the guess, as `/rfi/register` was in v0.3.1124.*

  `client_portal._payment_schedule` renders `str(d.get("status") or "draft")` — the free-text `data`
  blob — instead of `workflow_state`, the field the transitions actually set. A certified pay
  application whose blob was never written reads to the **owner** as a *draft*. `paid` is totalled
  from that same string, so the client-facing paid/outstanding split can be wrong independently of
  any refusal.

  **Adjacent to REFUSAL-READERS but a different defect**, and deliberately not ridden along on
  v0.3.1122: that release fixed which invoices the schedule *counts*; this is which status it
  *shows*. `prequalification.score_record` turned out to have the identical shape — a `data["status"]`
  read standing in for `workflow_state` — which is the argument for treating "engine reads the blob
  where a workflow state exists" as its own small sweep rather than a one-file fix.

  Shape: prefer `workflow_state`, fall back to the blob only when the state is absent, and drive the
  **real transitions** in the test. It changes a contract the portal tests encode
  (`services/api/test_portal_txn.py` seeds `status` in the blob), so the test must move with it.

- ◧ **CITE-RECORD — the citation contract checked that a source was NAMED, never that it was
  REAL** *(XS — Lane C; measured 2026-08-29, **re-scoped 2026-08-31 after measuring the premise**)*

  `cited_answer` exposes four builders. `cite_ifc`, `cite_rule` and `cite_doc` each have production
  callers; **`cite_record` has none.** So the platform can cite an IFC element, a rule and a document,
  and can never cite a *data-platform record* — `module/{key}/{rid}`, which is the bulk of what this
  product stores.

  R37's contract fix already named the cause without closing it: *"Nothing ever had to build a record
  citation because anything counted as one"* — `Assumptions.sources` was typed loosely enough that an
  empty dict scored 100% provenance. That fix made `is_citation` strict; it did not give the record
  citation a producer. One of four missing from a set of four is a gap, not a design.

  Bundled here because the same sweep found it, and it is genuinely extra-small: `owner_of` in
  `folder_template.py` has no callers either, but only because `docmanager.py` **reimplements its
  one-line body inline at three sites** (122, 192, 220) rather than calling it. Nothing is missing —
  the owner role does reach the client — but three copies of an accessor will not follow the accessor
  if its semantics ever change. R37-CONSOLIDATE shipped exactly this fix three times on 2026-08-28.

  ---

  **THE `owner_of` HALF IS DONE (v0.3.1129), AND IT WAS HIDING DEAD CODE.** The three inline copies
  were *not* identical, which the entry did not say: `list_folder` matched `owner_of` exactly,
  `upload` used `node.get(...)` with no None-guard (safe only because `is_valid()` raises above it),
  and `move` carried a **different rule** — keep the file's existing owner when the destination is
  off-taxonomy. Preserving that third rule as `owner_of(new) or f.get("owner_role")` passed every
  test, and **the mutation check showed why: deleting the fallback broke nothing.** `move` raises on
  an invalid destination in its first two lines, so the branch was unreachable — in the original code
  too. All three sites are now the same call. *An unreachable branch and a well-guarded one look
  identical from the call site; only the mutation tells them apart.* Held by
  `services/api/test_folder_owner.py`.

  **THE `cite_record` HALF IS NOT A WIRING TASK, and the entry above is wrong to imply it is.**
  Measured 2026-08-31: `ask()` routes only to the model, the docgraph and `doc_text` and **never
  reads a module record**, so the QA leg has nothing to cite. Nothing server-side populates
  `Assumptions.sources` — it is entirely client-supplied. The web client only *types* the citation
  shape, it never builds one. So "give the record builder a producer" means **building record-aware
  QA**: a feature and a product decision, not the extra-small consolidation this entry describes.
  *"One of four missing from a set of four is a gap, not a design"* was a reasonable inference and it
  was wrong — the other three are wired because something answers from an element, a rule and a
  document, and nothing yet answers from a record.

  **WHAT THE SEARCH FOUND INSTEAD, and it is worse than the gap it was looking for.** `is_citation`
  required the identifying field to be *present*, never to have the right *shape*. Measured through
  the contract:

  | citation | before | after |
  |---|---|---|
  | `cite_ifc("3Rb$mtGnf8kQm0Xy1_ZzAB")` — a real GlobalId | 0.733 | 0.733 |
  | `cite_ifc("the north wall")` — a display name | **0.733** | **0.000** |
  | `cite_record("budget", 7)` | 0.667 | 0.667 |
  | `{"record_ref": "banana"}` | **0.667** | **0.000** |

  A display name where a GlobalId belongs scored **the contract's highest confidence tier**, equal to
  the real thing — and that is this repository's first non-negotiable (*reference a model element by
  GlobalId, never a transient id*) being credited without being met. It is also exactly the dead end
  `R31-CITE-HIGHLIGHT` fixed for documents — *"display names render fine and cannot be opened"* —
  never applied to elements or records. The rule was not even new: `module_schema.IFC_GUID_RE` already
  existed and is now **imported rather than copied**. `rule` and `doc` stay presence-only, because a
  rule id and a document id have no canonical shape, and a positive control asserts they still pass —
  otherwise tightening everything would look identical to tightening the two kinds that have a format.

- ◧ **SOFT-CLASH-RULES — six of seven sourced clearances are never checked** *(S — Lane C;
  measured 2026-08-29)*

  `soft_clash.CLEARANCE_RULES` is a curated table of seven classes, each carrying a **`basis`** — NEC
  110.26(A)(1) electrical working space, manufacturer coil-withdrawal and seal-service clearances,
  hand-wheel reach. `rule_for` is its accessor, and its docstring states the design: *"Returning None
  rather than a default distance is deliberate. A made-up clearance produces confident findings
  nobody can defend, and the whole point of the `basis` field is that every number here can be traced
  to something."*

  **`rule_for` has zero callers.** Nothing consults the table. The clearance check the product
  actually runs is `geometric_rules.check_clearance`, driven by `_GEO_DEFAULTS` in
  `routers/standards.py` — which the viewer gets because `qaSection.ts` calls `rulesGeometryRun(pid)`
  with no `checks` argument. That default set contains **one** clearance entry:

      {"kind": "clearance", "name": "Door approach clearance", "scope": "IfcDoor",
       "distance_m": 0.9, "severity": "high"}

  and `routers/standards.py` references `soft_clash` **zero** times.

  **No wrong number ships, and that is why nothing has caught it.** `ifcdoor` is 0.9 in the table and
  0.9 in the default, so the one rule that runs happens to agree. The other six — including the NEC
  working space, which is a *code* requirement rather than a preference — are defined, sourced, and
  never evaluated against any model. A user running "Geometry check (clearance/egress)" gets doors
  checked and every piece of MEP equipment silently unchecked.

  Two smaller things fall out of the same measurement. `geometric_rules` falls back to
  `float(c.get("distance_m") or 0.9)` when a check omits the distance — a default with no basis, in an
  engine whose sibling table exists to prevent exactly that. And
  `/projects/{pid}/clash/clearance-rules`, which publishes the table, is in
  `test_route_reachability.py`'s frozen uncalled list: the rules are exposed to nobody and applied by
  nothing.

  **The fix is a behaviour change, not a wiring task, which is why this is filed rather than done.**
  Deriving the default set from `CLEARANCE_RULES` would start raising `severity: high` findings on
  MEP equipment across every existing project — correct, and not something to switch on inside an
  unrelated commit. The sequencing question is whether the six arrive as `high` beside doors or enter
  at a lower severity first.

- ✅ **ASSET-VERIFY — a release you can sign and cannot check** *(S — Lane C; measured 2026-08-29,
  the day the feature merged; **SHIPPED v0.3.1130**)*

  `asset_rights.py` ships both halves of a signed release manifest. **Only the sealing half is
  reachable.** Counted against `services/api/src`, `services/data/src` and `apps/web/src`, excluding
  the module itself:

  | function | production callers | tests |
  |---|---|---|
  | `verify_release` | **0** | 13 |
  | `verify_signature` | **0** | 6 |
  | `verify_content_hash` · `verify_manifest_hash` | **0** | 4 |
  | `public_key_b64` | **0** | 8 |
  | `generate_seed` | **0** | 4 |
  | `sign_manifest` · `build_manifest` · `new_asset_id` | 1 each | — |

  **The unreachable half is the half the feature exists for.** A manifest's purpose is that *someone
  else* can confirm a release is authentic and unaltered; sealing alone gives a file nobody can check.
  Three things are missing and none is a big build: nothing verifies a manifest, nothing publishes the
  **public** key a verifier needs — `/asset-rights/status` returns `enabled`, `signing` and `issuer`,
  and not the key — and nothing exposes `generate_seed`, so an operator has no supported way to mint a
  signing key at all. The last one means the *signed* path is unreachable from a clean deployment
  except by generating a key out of band.

  **No gate can see this, and that is the point rather than an aside.**
  `test_dead_code_population` reports **0 unreferenced** on this exact tree, because it counts the
  test tree as callers deliberately — the 877 → 13 correction its header describes. So a function with
  thirteen tests and no product caller is invisible to it *by construction*, which is the whole reason
  R37-TESTED-UNWIRED existed. **That item closed on 2026-08-28 and this landed on 2026-08-29**: the
  class does not stay closed, it recurs whenever code lands, and the twenty it found were a snapshot
  rather than a population. The standing lesson is the one that entry already carried — a module can
  be reachable and its whole reason for existing still be unreachable.

  Sequencing note: exposing the public key is the cheap, obviously-correct half (it is public by
  definition — `public_key_b64`'s own docstring says "safe to publish; this is what verifiers need").
  What a verify endpoint should *take* — an uploaded `.mass`, or a manifest document — is a real API
  shape question and worth deciding rather than guessing.

  **SHIPPED v0.3.1130.** The shape question resolved to **the manifest document**: `asset_rights.json`
  is what the container already carries, a verifier extracting one file is cheaper than re-uploading a
  whole `.mass`, and it lets someone check a release they hold without handing it back to us.

  * `POST /asset-rights/verify` → `verify_release`, reporting findings separately rather than one
    boolean, because *"the content was altered"* and *"it carries no signature"* need different
    responses.
  * `GET /asset-rights/status` now serves `public_key`. Its docstring said *"never the key itself"*,
    which read as a rule against publishing **any** key and left signed releases uncheckable;
    withholding the public half protected nothing, since the same key is embedded in every signed
    manifest we emit.
  * `python -m aec_api.asset_rights --generate` mints a seed — a command, **not** a route. Minting a
    private key is an operator action at the machine, and no request-authorisation gate is worth
    trusting more than shell access to the host.

  **The design error worth keeping, because it was caught by writing the test and not by reading.**
  The plan was to default `public_key` to this deployment's key "so `trusted_key` means something".
  That is backwards: a release signed by anyone else would then be checked against *our* key, fail,
  and be reported as `signature_ok: false` — a valid third-party release described as a bad
  signature. The key is the caller's to supply; omitted, the check falls back to the key inside the
  document, which is exactly what `trusted_key: false` already means.

  **A client method was written and then deleted.** `verifyRelease()` had no UI calling it, so it
  would have been an unwired client method added to satisfy a reachability gate — the very defect
  this item exists to remove, introduced while removing it. The verifier is whoever received the
  `.mass`, with their own tooling, like `/auth/cloud/callback`.

  **And the gate cannot see the new route, in either direction** — recorded in
  `services/api/test_route_reachability.py` beside its other documented blind spot rather than worked
  around. The leaf `verify` occurs in 25 unrelated web files, so the substring rule reads it as
  called; for the same reason it cannot be frozen as uncalled. Measured alternatives for whoever
  takes the matcher on: `/leaf` flags 43 more routes, a word-boundary match flags 5.

  Held by `services/api/test_asset_verify.py` — 20 checks, four mutations, and a positive control on
  the refusal branch that the first draft was missing: without it, a `--public-key` that *crashed*
  was indistinguishable from one that refused cleanly.

#### ✅ R46 — THE SECOND SYNC, ONE DAY LATER *(measured 2026-08-15; **COMPLETE v0.3.967**, re-verified against the gate 2026-08-29)*

> **This heading carried Band 2's ⭐ — "the highest-value item in a band" — while its own
> closing line read "R46 IS COMPLETE … 29 of 29 reachable, allowlist empty." So the file's
> priority ranking pointed a reader at finished work, and the two halves of one entry
> disagreed. `test_vendor_reachable.py` settles it in a second: 29/29, 0 unreached.**

R45 finished on 2026-08-14 with **all 21 vendored modules reachable** and `UNREACHED` empty for the
first time. Upstream shipped again the next day. `a740241c` brings **eight new modules and 2,986
lines**, plus a rewritten MSPDI writer and an injection audit across every writer — and
`test_massingplan_vendor` stayed green through all of it, because the copy is faithful. It is
`test_vendor_reachable` that failed the build.

**That is the argument for the second gate, demonstrated on the very next sync rather than argued
for.** Faithfulness and usefulness are different claims about a vendor drop; a digest check can only
ever make the first, and an engine can double in size behind a green one.

`xmlsafe.py` (113 lines) is the exception and is already **live**: the parse-bomb and XML-entity
hardening reaches us transitively through `mspdi` and `xer`, so it took effect the moment the files
landed. No adapter needed, and none of the schedule suites moved.

The seven that need one, in the order they are worth building — none of them duplicates anything we
have, so unlike R45 there is no de-duplication decision hiding in this list:

| Module | Lines | What it answers that nothing here does |
|---|---|---|
| ~~`windows`~~ | 300 | **SHIPPED v0.3.965** — `schedule_windows.py`, over the captured baseline library |
| ~~`modelled`~~ | 477 | **SHIPPED v0.3.965** — `schedule_modelled.py`. Collapsed as-built refuses on our data and says why; the refusal is the finding |
| ~~`p6xml`~~ | 760 | **SHIPPED v0.3.1041** — and the reachability gate was green the whole time, which is the point. `p6xml` was imported by `schedule_import.py`, so `test_vendor_reachable` counted it among 29/29. But the import path called `read_p6xml` (ONE project) while `read_p6xml_all` — the function whose own docstring says it *"is the entry point that makes P6 XML worth having"*, because baselines arrive as extra `<Project>` elements — had **zero callers**. Measured: a two-project export imported the first and reported `activities: 2` with no mention of the baseline anywhere. Now every project is listed in `report.projects`, dropping the rest is a `PMXML_MULTI_PROJECT` **error** naming them, and `project_id` on `POST /schedule/import-xer` loads a chosen one. **A module can be reachable and its whole reason for existing still be unreachable** |
| ~~`earned`~~ | 302 | **SHIPPED v0.3.966** — `schedule_earned.py`. Measured 0.556 on a job SPI would call 1.0 |
| ~~`compression`~~ | 439 | **SHIPPED v0.3.967** — and it measured `/schedule/optimize` overstating: advisory 5d, finish moves 3d |
| ~~`weather`~~ | 250 | **SHIPPED v0.3.967** — `schedule_weather.py`; refuses to invent an allowance |
| ~~`portfolio`~~ | 345 | **SHIPPED v0.3.967** — membership checked per project, proven 403/200 |

**⚠ AND THE WHOLE EOT SURFACE IS DARK — measured 2026-08-20.** Both routes exist and **no client
code references either**: `POST /schedule/eot` (caller-typed baseline) and `POST /schedule/eot/sourced`
(R40-EOT ②, derived from a *captured* baseline and detected events). `test_route_reachability` could
not report it — its leaf, `eot`, is 3 characters and the rule skips anything under 5, because short
leaves match unrelated text constantly. A longer needle was tried and rejected with numbers; see the
`MIN_SEGMENT` note in that file.

**Not wired here on purpose.** The entry below reserves the EOT *semantics* as a domain decision, and
which of the two a screen should show is the same question wearing different clothes: `sourced` is the
auditable one — its own docstring says a caller-typed baseline "is unauditable… two people can produce
different EOTs from one project by typing different dates" — but putting an extension-of-time figure
in front of a user is a decision about what the product asserts in an arbitration, not a wiring task.

**⚠ CORRECTED 2026-08-31 — the paragraph that stood here was FALSE, and false on the day it was
written.** It said `eot.py` "names four AACE methods and performs none of them. All four return an
identical number on the same input." Measured through `eot.analyse` on one job (baseline finish
2026-01-31, two excusable events totalling 20 days):

| actual finish | `impacted_as_planned` | `as_planned_vs_as_built` | `time_impact` | `windows` |
|---|---|---|---|---|
| 2026-02-10 (slip 10) | **20.0** | **10.0** *(capped)* | *refuses* | *refuses* |
| 2026-03-12 (slip 40) | 20.0 | 20.0 *(cap idle)* | *refuses* | *refuses* |

Three distinct outcomes where the cap binds, two where it does not — and **the series pair never
returns a number at all**, refusing with `method_needs_schedule_updates`. So "all four return an
identical number" is untrue on *every* input, not merely on some.

**The fix predates the claim.** `v0.3.971` shipped **2026-08-16** under the title *"four delay
methods, one number, and a label that said otherwise"* — it is the release that ended this. The
paragraph above was dated *"measured 2026-08-20"*, four days later. **A claim can be stale on the day
it is written**, and this one carried a measurement date, which is exactly what stops a reader
re-checking it.

**Its own citation contradicted it.** It cited `services/api/test_schedule_windows.py` as the pin;
that test asserts `windows` and `time_impact` return `None` — *"which is now the REASON they refuse"*.
The gate had been green on the corrected behaviour the whole time. **A citation is not evidence of
what it is cited for** — nobody re-read the test the sentence pointed at.

**AND IT IS NOT A CLASS — swept 2026-08-31, four of five accurate.** The obvious next inference from
the correction above is *"if one roadmap claim was stale, sweep them all"*. That was checked instead
of assumed, and the answer is no. **Population:** the 21 `⚠` markers in this file, of which exactly
**five** assert present-tense runtime behaviour that can be executed and falsified; the rest are
SHIPPED rows, sweep-run headers, prior corrections and the 18-findings table, and one more
(`takt.py`'s name) is a semantics decision with nothing to falsify.

| claim | verdict |
|---|---|
| the EOT surface is dark, no client references it | **accurate** — re-verified the same day |
| `eot.py` performs none of the four methods | **FALSE** — the correction above |
| `/schedule/risk` and `/schedule/montecarlo` disagree by 38 days | **accurate, and resolved** — the alias calls `schedule_risk_mc.for_project`, the same engine |
| three PPC implementations disagree | **accurate, and resolved** — one rule since v0.3.974, held by `services/api/test_ppc_divergence.py` |
| `/schedule/compare` returns `finish_move_working_days` and `calendar_vs_working_gap_days` | **accurate** — both fields present, gate green |

**The negative result is the point, and it is recorded so nobody runs this sweep again.** Every
defect class this repository has found by sweeping — the refusal-state readers, `PORTAL-STATUS`,
the status/workflow drift — showed **several** instances on the first probe. This one showed one, and
four counter-examples. *A sample of one is a finding, not a pattern*, and the cost of the mistake runs
the other way from the usual: generalising from it would have spent days confirming that
well-maintained entries are well maintained.

**What was NOT swept, stated so the gap is not mistaken for coverage.** Only the falsifiable five.
A roadmap sentence that misdescribes something unexecutable — an intent, a plan, a reason — cannot be
caught this way, and no gate proposed here would catch it either. The 103 test-file citations in this
file were considered as a population and rejected: filtering them mechanically cannot separate a
citation *describing what a test asserts* (self-consistent, the overwhelming majority) from one
offered as *corroboration of a live defect* (the failing shape). That separation needs reading.

**What survives is the real decision, and it is unchanged:** `schedule_windows` and
`schedule_modelled` perform three of the four for real. **Whether `/schedule/eot` should delegate to
them, or keep its own number and cite theirs, is a domain decision** — the EOT figure ends up in
arbitration, and changing what it means is not a refactor. Both still ship.

**R46 IS COMPLETE (v0.3.967): 29 of 29 reachable, allowlist empty.** Recorded in `services/api/test_vendor_reachable.py`, which fails the build until each is either wired
or argued for. **The `mspdi` rewrite and the `xer` injection audit landed with no adapter change and
no test movement** — checked by running the schedule suites, not assumed from the diff being large.

#### ⭐ R45 — THE VENDORED SCHEDULE ENGINE *(measured 2026-08-14 at the `d1e4bf16` re-sync)*

The vendored `massingplan` engine was re-synced from pin `b703dca4` → `d1e4bf16`, which brought two
new modules and deepened seven. Measured immediately after: **9 of the 21 vendored core modules —
3,904 lines — have no path from the API at all.**

The number is *transitive*, not a grep. A direct-import scan said 12 modules were unwired; three of
those (`cpm`, `progress_logic`, `units`) are reached through `schedule.py`, so they are load-bearing
and the grep would have had us "wire" code that already runs. The nine below are genuinely
unreachable — no direct import, and nothing reachable imports them either.

| Vendored module | Lines | Our counterpart | The real question |
|---|---|---|---|
| ~~`health`~~ | 634 | ✅ `aec_api/schedule_health.py` | **WIRED v0.3.950**, routed v0.3.951 — DCMA 14-point |
| ~~`compare`~~ | 555 | `schedule_baselines.compute_variance` | **SHIPPED v0.3.961** — the blocker was the SNAPSHOT, and it was fixable |
| ~~`levelling`~~ | 587 | ✅ `aec_api/schedule_levelling.py` | **SHIPPED v0.3.954** — `POST /schedule/level`; pulled `resources` in transitively |
| ~~**`locations`**~~ | 477 | ✅ `aec_api/schedule_locations.py` | **SHIPPED v0.3.952** — line of balance + crew continuity, `GET /schedule/flowline` |
| ~~`resources`~~ | 254 | ✅ *(via `schedule_levelling`)* | **reachable v0.3.954** — `levelling` imports it |
| ~~`takt`~~ | 444 | ⚠ `aec_api/takt.py` **163** | **SHIPPED v0.3.953** as `schedule_takt.py` — and they are *different methods*, see the decision below |
| ~~`lastplanner`~~ | 436 | ⚠ `pull_plan.py` + `lean.py` | **SHIPPED v0.3.960** — and it found THREE disagreeing PPCs; see below |
| ~~`risk`~~ | 303 | ⚠ "aec_api/schedule_risk.py" **195** *(DELETED v0.3.972)* | **SHIPPED v0.3.959** — and the two disagreed by 37–38 days, which is what settled it; see below |
| `progress` | 214 | `aec_api/progress_rollup.py` **134** | overlapping |

**The split matters more than the total — and this table was wrong three times before it was right.**

The count went **5 pure gain → 3 → 1**. Each correction came from a different bad shortcut, and the
sequence is the reusable part:

1. **Matched on filenames.** No `aec_api` file is named `compare`, so `compare` was filed as having
   no counterpart. `schedule_baselines.compute_variance` is one.
2. **Matched on grep patterns I guessed.** Searching `levell|resource_level|resource_assign` missed
   `resource_loading.py`, which defines `level()` and `loading()` — 221 lines covering *both*
   `levelling` and `resources`. The capability was there; the words I guessed were not.
3. **Matched on docstring keywords.** Too loose in the other direction: "level" matched
   `bid_leveling`, which is subcontractor bid levelling, an unrelated domain.

**The only method that worked was opening both modules and reading them.** Automated matching failed
three times in three different ways, twice while explicitly trying to correct the previous failure.
For a question of the form *"do we already have this?"*, a grep can prove a string absent and can
never prove a capability absent.

The verified picture:

* **One is pure gain** — `locations`. Verified by reading it and then searching our tree for the
  domain's own terms (*flowline*, *line of balance*, *location-based*): nothing. It answers the
  question CPM cannot — *"where is each crew, and does anyone get in anyone else's way"* — and the
  thing it models that CPM structurally cannot is **crew continuity**: a forward pass gives every
  activity its earliest start, which is exactly what fragments a gang into work-a-floor-then-wait. On
  a tower that is the same twelve trades on forty floors, and a subcontractor cannot price it.
  **This is the whole of ① now, and it is the most differentiating item in the ring.**
* **Seven already have ours beside them** — `compare`, `levelling`, `resources`, `takt`,
  `lastplanner`, `risk`, `progress`. (`health` was the only other pure gain and shipped v0.3.950.)

**All four overlaps share one shape, and naming it settles the sprint.** Ours are *renderers and
persistence layers that grew a bit of engine*; theirs are engines. `pull_plan.py` is `board` /
`metrics` / `pdf` / `signature`; `takt.py` is `plan` / `progress` / `takt_svg`;
`progress_rollup.py` is `capture_diff` / `rollup`. `takt` is the sharpest case because both define
`plan()` — theirs also has `crews_for`, `minimum_takt` and `to_network` (crew sizing, minimum
feasible takt, conversion to a CPM network); ours has `takt_svg`, which theirs does not. **Keep our
rendering, take their engine, delete ours** — in all four, one at a time.

**Correction, made on the same day the table was written.** `compare` was filed as "no
counterpart" because no `aec_api` file is *named* compare. `schedule_baselines.compute_variance`
already computes a baseline-to-current diff, so the classification was made on a filename rather than
on a capability — the exact error this ring exists to stop, committed while writing the ring.

Having read both, they are **complementary rather than duplicated**, and the distinction is worth
more than the correction:

* **Ours matches on the internal record id.** That is right for a baseline *captured in the app*,
  where ids are stable, and it is what `compute_variance` is for.
* **Theirs matches on the planner's activity code**, with `NAME_AND_WBS` as a fallback and ambiguous
  pairs deliberately left unmatched. Its docstring names exactly why: a re-baseline exported from P6
  carries entirely new `task_id` values, so an id-match "finds nothing in common and reports every
  activity as removed-and-added — a diff that is technically correct and completely useless."

**So our variance is silently useless in the one case a GC needs it most: comparing against a
schedule somebody else exported.** It does not error; it reports total churn. That is the finding,
and it is bigger than the wiring. Theirs also carries link changes, criticality gained/lost, a
driving-path delta and delay *attribution* — the forensic half, which is where a delay argument is
actually won and which we have nothing for.

Wiring it needs one user-facing decision first — which identity key is the default — so it is **not**
a drop-in adapter like `health` was.

**⚠ THREE PPC IMPLEMENTATIONS, ONE DASHBOARD, AND THEY DISAGREE.** The table named two;
reading all three found a third. On one week — 1 done, 1 missed, 3 still unanswered:

| | denominator | reads |
|---|---|---|
| `lean.ppc` | every record | **20%** — the unanswered count as failures |
| `pull_plan.metrics` | assessed only | **50%** — the unanswered are not in the denominator |
| `core/lastplanner` | frozen at commit | **unmeasurable** — `null` until every commitment is answered |

`lean.ppc` reads artificially **low** mid-week (on Wednesday every team looks like it is failing);
`pull_plan.metrics` reads artificially **high** (one answered of twenty, and done, reads 100%). **The
portal renders the flattering one.** `lean.ppc` additionally reports `0.0` and a rating of *"needs
work"* for a project with **no commitments at all**, and defaults a missing variance reason to
`"Unspecified"` — quietly filling the learning loop with a value nobody entered.

**DECIDED 2026-08-16: the vendored engine's rule wins, and v0.3.974 applied it.**

One rule everywhere: met or not met with no partial credit; an **unanswered commitment makes the
period unmeasurable**, so PPC is `None` rather than a number; and nothing promised is `None` too,
because a team that made no commitments has not broken any.

There are still **three functions, because there are two registers and a route** — `lean.ppc` scores
`weekly_plan`, `pull_plan.metrics` scores `pull_plan_task`, `schedule_lastplanner` scores the same
records through the vendored engine. Collapsing them would merge two registers holding different
work. What had to agree was the RULE. `services/api/test_ppc_divergence.py` now asserts the
agreement, with a **closed** week as the twin — three engines that always answered `None` would look
consolidated and be broken.

**Two findings the consolidation turned up, neither of which this table knew about.**

*The engine could not read its own register.* `schedule_lastplanner` grouped on a field called
`week`. `pull_plan_task/module.json` declares **`planned_week`**; `week` is `weekly_plan`'s field, a
different register. So `GET /schedule/reliability` answered *"none of the N pull-plan tasks carry a
week"* on **every real project**, while its only test passed on a hand-written fixture supplying
`week`. A fixture cannot catch this by construction — it is written from the same wrong belief as the
reader, so it agrees with the reader and disagrees with the database.
`services/api/test_ppc_field_conformance.py` asserts the engine's field names against the register's
own `module.json`, a reader neither of them wrote. Mutation-checked: 4 named FAILs, and the gate
reproduces the exact pre-fix refusal.

*`pull_plan.metrics` disagreed with itself.* The trend line divided by every commitment including
unanswered ones; the headline divided by the assessed only. On a week with 1 done, 1 missed and 3
still open that is **20% in the chart and 50% in the tile, on the same panel**. The existing test
could not see it: its fixture had no unanswered commitment, so both forms happened to agree.

The web chart also stopped plotting `?? 0` for a null week — drawing "not measurable yet" as a zero
bar is the confusion the null exists to remove, and worse in a chart, because a reader sees a
collapse rather than a gap.

**⚠ `/schedule/risk` and `/schedule/montecarlo` disagree by 38 days on a 100-working-day chain, and
the older one is the optimistic answer.** `schedule_risk._network` is FS-only, lag-free and
**calendar-free** — checked, not assumed: the module contains zero occurrences of "calendar" — and it
turns a duration into a date with `start + timedelta(days=round(days))`, i.e. *calendar* days. The CPM
beside it reports *working*-day dates. Measured on the test fixture: ours `2026-06-22`, the vendored
engine `2026-07-30`.

A P80 that counts Saturdays is not a conservative estimate, it is a different question's answer.
**Retiring `/schedule/risk` is a user-facing removal and therefore your call**, the same as the
`takt.py` naming decision — the replacement is shipped and carries our PPC calibration forward, so
nothing is lost by retiring it.

**DECIDED 2026-08-16: keep the alias.** The path stays, serving `/schedule/montecarlo` verbatim
with a `deprecated` note; `scheduleRisk` stays as a one-line client alias, recorded in
`KNOWN_UNCALLED` as deliberately callerless. **This question is closed — do not re-open it as a
cleanup.**

**It nearly went the other way in v0.3.972.** That release deleted the wrong ENGINE, which
the ring's rule authorises, and in the same stroke deleted the PATH, which this paragraph had
reserved for you. The path was put back the same day as a **deprecated alias** serving
`/schedule/montecarlo` verbatim, so nothing 404s and the wrong number is still gone. The response
SHAPE did change — dates rather than day counts — which is unavoidable, because the old shape was the
wrong answer's shape. The decision left to you is narrow: **delete the path, or keep the alias.**

The lesson is not "read the roadmap harder". It is that *an item authorising a deletion does not
authorise every deletion it touches*: R45-SCHED-DEDUPE ② says "delete the loser", and the loser had
two halves with different owners.

The vendored engine also reports two things ours cannot: `confidence_in_deterministic` (on that
fixture, the programme date had a **9%** chance) and `duration_sensitivity` per activity — whether an
activity's duration actually *moves* the finish, as opposed to merely sitting on the critical path
often.

**The `progress` row was the fifth wrong classification, and the only one caught before acting.**
`progress_rollup.py` measures **the building** — percent complete from as-built element presence,
keyed by GlobalId, by class / discipline / level, by count *and* by value. `core/progress.py` measures
**the schedule** — BEI, variance and slippage of activities against baseline dates. A tower can be 60%
erected and four weeks late; neither number substitutes for the other, and reading one as the other is
how a report reassures somebody wrongly. They share the word and nothing else.

It also shows the `compare` blocker is specific rather than general: **`progress` needs only dates**,
which `_snapshot` has, so it shipped. `compare` needs predecessors, which `_snapshot` does not.

**✅ `compare` SHIPPED (v0.3.961) — and the blocker turned out to be one field, not a decision.**

The diagnosis above was right and the conclusion was wrong. `compare()` does need both **networks**,
and `schedule_baselines._snapshot` did freeze only `ref`, `name`, `start`, `finish` and `budget`. But
"changes what every existing stored baseline means" is exactly what a **schema version** exists to
avoid. `_snapshot` now also freezes `duration`, `predecessors`, `calendar`, `constraint` and `wbs`,
under `schema: 2`; a v1 baseline keeps meaning precisely what it always meant, and variance against it
is untouched.

**The version number is the whole safety argument, and it is not bureaucracy.** A v1 snapshot and a v2
snapshot of a schedule that genuinely has no relationships are *indistinguishable from the data*.
Rebuild a v1 one as a network and it comes back as a set of 1-day tasks with no predecessors — a
fully-parallel plan that finishes on day one — which then diffs against the real schedule into a
large, precisely-attributed delay caused by logic nobody removed. Measured, not argued: the twin in
`services/api/test_schedule_compare.py` forces one through and gets **53 days against a true 14**,
attributed with total confidence to named activities. So a v1 baseline is refused, with a sentence
that says to capture a new one.

Deliberately **not** frozen into a baseline: progress (`actual_start`, `actual_finish`, `percent`,
`remaining_duration`). A baseline that already knows how the job went under-reports every later slip
by exactly the progress recorded on the day it was captured.

**⚠ A finding in the vendored engine, surfaced rather than fixed.** Its delay contributions are in
**working** days; its `finish_move_days` total is in **calendar** days. The invariant still holds —
the contributions sum to the move exactly — but only because the `UNEXPLAINED` bucket absorbs the
difference, and a residual labelled *unexplained* sends a planner looking for a cause that does not
exist. On a ten-working-day growth it is four days of weekend, every time. `/schedule/compare` now
returns `finish_move_working_days` and `calendar_vs_working_gap_days` so the reader can subtract it.
Not patched in `massingplan/core/` — that is a re-synced vendor drop and the fix belongs upstream.

**All 21 vendored modules are now reachable.** `test_vendor_reachable.py`'s `UNREACHED` allowlist is
empty for the first time. Its vacuity twin was rewritten in the same commit: the old one read
`reach != mods or not UNREACHED`, which can never fail once the list empties — a check whose failing
branch is unreachable is not a check. It now asserts the closure is **derived**, by recomputing it
from a strictly smaller entry-point set and requiring a strictly smaller answer.

**⚠ DECISION NEEDED — `takt.py` is a line-of-balance engine wearing the name "takt".**

The table filed `takt` as "two implementations, same `plan()`". Reading both says they are **two
different methods**, and the vendored module's own docstring draws the line: *"Line of balance lets
every trade run at its own natural pace and then shifts the lines apart until nobody trespasses. Takt
does the opposite, and the difference is a decision, not a detail: every wagon occupies exactly one
zone for exactly one takt. The crew sizes move so the durations do not."*

Our `aec_api/takt.py` gives each trade its **own** `takt_days` — `Structure 5, Envelope 5, MEP 6,
Interiors 8, Finishes 6` — and lets them chase each other up the building. Trades at *different* rates
is the definition of line of balance. **So real takt was missing entirely**, and now that
`locations.py` ships as `/schedule/flowline` and *is* line of balance, the product would otherwise
offer that method twice under two names and still not offer takt.

`schedule_takt.py` + `GET /schedule/takt-train` (v0.3.953) add the missing method. **Nothing was
renamed or removed** — `takt.py` backs a shipped, user-facing panel, and that is your call, not a
cleanup. The three options:

1. **Rename ours to "lineofbalance.py"** (plain quotes: it does not exist yet) and let the Takt panel become a Line-of-Balance panel. Most
   honest, and it is a user-visible label change.
2. **Keep both names** and treat our `takt.py` as the *charting* layer (it has `progress()` and
   `takt_svg()`, which the vendored engine does not), pointing it at whichever engine the user picked.
3. **Leave it.** The names stay wrong; a planner asking for takt gets line of balance.

The engine work is done either way; only the naming is open.


- ◧ **R43-VIEWER-CONFORMANCE** *(S — Lane E; MassingViewer issue #512; **RUN 2026-08-13**, full
  result in [`docs/internal/viewer-conformance-2026-08-13.md`](internal/viewer-conformance-2026-08-13.md))*
  — **run their conformance suite against our live API.**

  **BOTH ABSENT ENDPOINTS SHIPPED v0.3.1055** — `GET /projects/{pid}/spatial-tree` and
  `POST /projects/{pid}/elements/properties`, held by `services/api/test_spatial_tree.py`. What
  remains is the three renames/rescopes and the `/edit` body shape, every one of which is a
  *decision about which side moves*, not code. **This item stays ◧ for that reason and not because
  work is left undone here.**

  **The report was wrong twice, and re-deriving it before building is what found both.**
  `elements/properties` is a **POST**, not the GET the table records: the run probed with GET, hit
  `/elements/{guid}` with `guid="properties"`, correctly concluded the route was absent, and quietly
  carried the wrong method into the conclusion. A GET-shaped endpoint would have satisfied every
  check in that file and been unreachable from the adapter forever — *the answer to "does our
  service speak it" is in the client's source, not in a probe of ours.* And the population was
  **nine calls, not seven**: `snapCandidates` (`/snap`) and `drawing` (`/drawings/{kind}.svg`) are
  called by the same adapter and appear in no row, so "1 of 7" was measured against a denominator
  nobody derived. Neither of the two is fixed here; each is its own question.

  **The tree is built from `IfcRelAggregates`, never from the `storey` NAME.** Grouping on the name
  string is a five-line function that yields a plausible tree with no GlobalIds in it — against the
  first non-negotiable — and merges two buildings that each have a "Level 2", which is the ordinary
  case on any campus. Our own model browser gained "By spatial structure" off the same endpoint: the
  first grouping in it keyed on a GlobalId rather than a label. An index predating `index_schema: 2`
  is **refused (422) with the remedy in the sentence** rather than answered with a null, because a
  v1 index and a model with genuinely no `IfcProject` are the same absence and different answers.
  `elementProperties` was deliberately **not** added to the web client: our tree already gets psets
  inline from `/elements`, so a typed method with no caller would exist only to satisfy the
  reachability gate — the gate measuring itself. Recorded in `apps/web/src/api/elements.ts` next to
  where it would have gone, along with the fact that `test_route_reachability` does not flag that
  route at all (its leaf `properties` already appears in the client for `/properties/index`), so it
  passes by coincidence rather than by judgement.

  **Done: :8093 up, real project, real model.** `samples/school_str.ifc` (8.6 MB) uploaded, converted
  to `frag`, **500 elements queryable**. `/health` checked before use, because a stale server also
  answers 200.

  **1 of the 7 endpoints `RemoteKernel` calls works as-is.** Two are absent (`spatial-tree`,
  `elements/properties`); three differ by path or scoping (`export.ifc` sits under `/model/`, `jobs`
  is project-scoped not global, `geometry` is a rules runner); one — `/edit` — exists and takes
  `recipe` where the kernel sends `{op, params}`. That last is the only item with real design content,
  because `recipe` is our GUID-stable edit vocabulary. **Narrow and mechanical, not architectural.**

  **This entry was unfair to them and the correction is worth keeping.** It said their suite "has only
  ever passed against a stub its own author wrote, so it is a green check with no subject." Their file
  says in its own header that it runs against cassettes and proves the adapter satisfies *the protocol
  as documented, not that massing's service speaks it* — and their `docs/kernels/authoring.md` records
  the live run as outstanding. It is a correctly-scoped test that names its own gap; the missing half
  was ours, and it is now supplied.

  **One refusal read as a match and was not.** `elements/properties` answered `404 "element not
  found"` — a domain message, which normally means a route matched and rejected the input. There is no
  such route: `/elements/{guid}` matched with `guid="properties"`. Resolved against the OpenAPI table
  rather than the status line, because probing alone gets this one wrong.

### Band 3 — gap-checks (hours, not days; each may close for free)

**All three checked 2026-08-07. Two were real, one closed for free — the band's thesis held for the
eighth time running.** The record is below; the previous five are in
[`roadmap-completed.md`](roadmap-completed.md).

**Re-checked 2026-08-13: both "REAL" findings are now CLOSED**, wired by PULSE-FINDINGS into the home
pulse's deal card. Neither entry was updated when the work landed, so the band read as carrying two
open gaps that no longer existed. **The band's own thesis is why this matters** — these entries exist
to say "a value is computed and nobody can see it", and an entry that keeps saying so after the
screen ships is the same defect pointed the other way.

## ▶ NOW — parallel lanes *(rebuilt 2026-07-29 at v0.3.785; bands re-seated 2026-08-01 at v0.3.818)*

**How to work here lives in [roadmap-directions.md](roadmap-directions.md), not in this file.** Claim a
lane rather than an item, premise-check before building, announce before a full suite, and land what
you finish. Those rules and the reasons behind them are in the directions; this section is only the
lane assignment.

**Organised by LANE rather than by priority**, because several sessions work concurrently and a single
ranked list serialises work with no reason to be serial. For a ranked view of the same items, see
**[What is left, prioritised](#-what-is-left--prioritised)** above.

### Proposed next three sprints *(re-cut 2026-08-25 — a PROPOSAL, not a decision)*

**This is the agent's ordering, not the user's.** Reorder it freely; the reasoning is given so
disagreeing with it is cheap. The previous cut (2026-08-17) ran as sprints 1–3 in v0.3.978–980 and
is kept below, because its *predictions* are the part worth checking.

**What the last cut got wrong, and it was the same mistake twice.** Two of its three rows were
mis-sized, both because a written number was trusted instead of re-derived — a stale size ceiling in
row 2, a stale dead-code population in row 3. The one that was correctly sized is the one whose
entry demanded a premise-check before starting. **That is now the first line of every row below.**

| # | Sprint | Why here | Size | Premise to check FIRST |
|---|---|---|---|---|
| 1 | ~~**A correctness sweep** — refill Band 1~~ **DONE 2026-08-25 (v0.3.1091–1095)** | **Struck rather than deleted, because the prediction is the part worth checking.** All three axes it named were run: **authz** (43 routes, no live hole, `services/api/test_resource_id_authz.py` is the finding), **concurrency** (a 500 on concurrent first sign-in at all three SSO doors), **money** (52 of 399 JV distribution periods whose parts did not sum to their own total). Its premise-check was the load-bearing part — "pick the axis before starting" is what made two of the three produce a defect. Records in §Band 1 above. | M | — |
| 2 | ~~**R22-REPORT-BUILDER — items 2–5**~~ **COMPLETE 2026-08-26 (v0.3.1101–1105)** | All four remaining items shipped: a validated config schema (which exposed a live alert miscount), shareable views, cross-module reports along declared reference edges, and one report catalog. **The premise-check this row demanded is what found that FOUR remained rather than three** — the row was written when the entry listed four items and was never re-derived after it grew to five. Full record in [`roadmap-completed.md`](roadmap-completed.md). | S/M → M/L | — |
| 3 | ~~**R36-VIEWER-SUBAPP** — the canvas switches 2D/3D in place, including PRINT~~ **COMPLETE 2026-08-27 (v0.3.1106–1111)** | **Struck rather than deleted: this row was sized L and the work left in it was days, which is worth recording.** Its premise-check found the subject half-shipped and then found three live defects in what had shipped — a markup key on the storey NAME against the first non-negotiable, a spec manual answering in a system no tracked model uses, and a keynote with nothing to cite. The row's own stated premise (the R43 collision) was never the thing that mattered; **the entry's description of its own state was**. The last slice — the live DOM verification this entry had flagged for 190 versions — found the viewer did not mount offline at all. Record in [`roadmap-completed.md`](roadmap-completed.md). | L | — |

**Why not the obvious candidates.** Stated so that disagreeing with the omission is as cheap as
disagreeing with the inclusion. *(Each bullet deliberately opens with "Not X" rather than with the
item code: a bullet shaped `- **CODE** …` parses as an ITEM, so the first draft of this list minted
four phantom entries — one of them a bare `SCALE-SEAM` with its `㉘` silently dropped, which is the
exact failure `roadmapLanes.test.ts` documents in its `MARKS` note. The gates caught all four.)*

* **Not R39-DECOMP-VIEWER ③.** It ranked second last time on a size-ceiling argument that had
  already gone false. `app.ts` is decomposing steadily (5,064 → 3,444 → and thirteen slices since), the ratchet
  is pinned, and it moves on its own whenever a feature pushes it. It does not need a sprint; it
  needs to keep being interleaved. **Re-measure the ceiling before ever promoting it again** — that
  is the specific error row 2 made.
* **Not the next SCALE-SEAM slice.** ㉘ is genuinely next in a series that has shipped twenty-six
  increments, but the series is now cutting into `client.ts` at 2,837 lines from a 3,600-odd start. The marginal slice
  is worth less than it was. *(㉘ also needed `MARKS` widened; that shipped in v0.3.1112.)* The vocabulary lives in
  `apps/web/src/shell/roadmapLanes.test.ts` — a vocabulary change to a population check, which that
  file's own docstring calls a real change and not housekeeping.
* **Not R22-ENTITLEMENT.** It led the last cut and two of its three parts shipped. What is left is the part
  its own entry warns about: two name collisions (`tiers.py` is *subscription* tiers;
  `proforma/approval_risk.py` scores risk and runs no workflow) that have produced a naming-based
  false blocker **four times**. It is not a bad sprint — it is one that must not be started from
  the entry alone, and that makes it a worse fit for a proposed sequence than for a deliberate pick.
* **Archived 2026-08-29 — the QTO-TRADE bullet that stood here.** This bullet argued it was a poor
  sprint pick because the remainder was "three screens that need *returned quotes* — an input the
  model cannot produce". All three are wired: a paste-and-level control supplies the quotes, and
  `buyoutSchedule` turned out not to need them at all — it was blocked on a backend defect the entry
  had already declared closed. **The reason it was not pickable was itself wrong**, which is the
  argument for the premise-check rather than against it.


#### The previous cut, 2026-08-17 — kept for its outcomes

**All three ran, v0.3.978–980.** Kept below with outcomes, because the *predictions* are the part
worth checking: two of the three were mis-sized, and both in the same direction.

| # | Sprint | Why here | Size | Outcome |
|---|---|---|---|---|
| 1 | **R22-ENTITLEMENT** | The only genuinely open R22 item, and the largest hole in the product's own story: the mission is acquisition → construction and **nothing spans approval**. Everything else on this list improves what already exists. | M/L | ✅ ③ shipped v0.3.978 — `review_cycle` + `approval_cycles.py`. ✅ **comment round-tripping shipped v0.3.1042** — a resubmittal now carries the review that asked for it, labelled with the revision it was written against. **Submittal *packages*: the inbound half was ALREADY SHIPPED and this row did not say so — see the note under the entry.** |
| 2 | **R39-DECOMP-VIEWER ③** — split `apps/web/src/viewer/app.ts` | Not a preference — but **not the alarm an earlier version of this cell made it sound like, either.** Re-measured 2026-08-27: the file was 2,865 lines against a pin of 2,865, and it is **2,570 after slices ⑭⑮⑯**, with the pin lowered each time — **and then raised back to 2,865 the same afternoon by an unrelated lane's commit to the same shared file, which no gate could see. Re-measured again 2026-08-29 and restored; see the entry.** That is the fourth consecutive time this row's number was wrong, and the first time the *pin* was the thing that had moved rather than the prose. Zero headroom is the ratchet's DESIGNED state, not a regression: it pins each file at (or one line above) its current size — `client.ts` sits at 2,836/2,837 the same way — and `test_file_sizes.py` says so itself, that the threshold is set just above the worst offender and tightening it is part of the work. So the next line added here reds the build, permanently, and **the remedy is always extraction, never waiting for room**. That is the mechanism, working. This cell said *"97%, ~136 lines of headroom"* until today, which was the third consecutive time this row's number was stale: the ratchet has come down twice since (2,944 → 2,885 → 2,865) and the prose never followed. The note in the outcome column already says a justification was *"copied forward without re-measuring"* — and then the correction itself was copied forward without re-measuring. **Re-derive it before quoting it:** `wc -l apps/web/src/viewer/app.ts` against its entry in `services/api/test_file_sizes.py`. | L | ✅ ⑦ shipped v0.3.978 (3,444 → 3,311). **The "why" was already false when written** — six slices had landed and the ceiling had moved with them. A justification copied forward without re-measuring. |
| 3 | ~~**R37-TRIAGE tail**~~ — **CLOSED 2026-08-29, before this sprint was taken.** `services/api/test_dead_code_population.py` reports 0 unreferenced and an empty `DELIBERATELY_UNCALLED`; the 12 candidates this row proposes reading are gone. *A proposed sprint is a status line too, and this one had gone stale in the same way the item it names had.* | — | ✅ shipped v0.3.980, and **"lowest value" was wrong**: 8 of the 12 were live, one of them holding both PyInstaller builds together. The reading was the value, not the deletions. *(That sentence is restored here: the first draft of the strikethrough above deleted it, and a status correction that takes a recorded finding with it costs more than the stale status did.)* |
**What the outcomes say about the sizing.** Both misjudgements came from trusting a written number
instead of re-deriving it — a stale ceiling in row 2, a stale population in row 3. The sprint that
*was* correctly sized is the one whose entry demanded a premise-check before starting.

**Sprint 1 carries a warning its own entry already gives:** two name collisions sit on
R22-ENTITLEMENT. `tiers.py` is *subscription* tiers and makes the item look shipped;
`proforma/approval_risk.py` scores approval risk but runs no submittal workflow, and stopping at the
first collision means never noticing the second. **Premise-check on semantics, not names** — this
ring has produced a naming-based false blocker four times.

### The lanes

**Nine lanes, and every open item is assigned to exactly one.** `shell/roadmapLanes.test.ts` asserts
that: it extracts the item codes from this file and fails if any is missing from the table below, or if
the table names a code that no longer exists. **Pick a lane, read its row, take any item in it** — no
two rows share a path, so two agents in different rows cannot collide.

| Lane | Owns these paths — disjoint | Open items in this lane |
|---|---|---|
| **A · Shell & IA** | `apps/web/src/shell/`, `apps/web/src/account/`, `apps/web/src/portal/portal.ts`, `apps/web/src/portal/favourites.test.ts`, `apps/web/src/portal/homes/`, `main.ts` | REL-4 · R40-RIBBON ② · R43-CRUD-FRAGMENTS *(⛔ CLOSED UNBUILT — rescoped 2026-08-11 before any code)* · R22-AGENT-PACKS *(moved from C 2026-08-16 — what remains is the governance CONSOLE, which is shell work. Its own entry said Lane A/E and the cell had not followed. The item stays ◧: the console is real work and this cell does not claim otherwise)* |
| **B · UI & panels** | `apps/web/src/ui/`, `portal/panels/`, `portal/register/`, `field/`, `reportCenter.ts` | R24-REPORTS-BY-MOMENT · R24-TERMS · R24-FIELD-MODE |
| **C · Backend engines** | `services/api/src/aec_api/`, `!services/api/src/aec_api/routers/`, `!services/api/src/aec_api/main.py` | R22-ENTITLEMENT · R22-PIPELINE *(Lane C remainder is the resourcing engine only)* · PERF-WORKERS ① · R43-MASSINGBILL-CORE · SOFT-CLASH-RULES *(six of seven sourced clearances never evaluated; see Band 2)* · CITE-RECORD *(what remains is whether anything should answer FROM a stored record, which is a product decision; see Band 2)* |
| **D · Geometry & drawings** | `services/data/src/aec_data/`, `apps/web/src/drawings/` | — |
| **E · Authoring feel & viewer** | `apps/web/src/viewer/`, `inference.ts`, `apps/web/src/tree/` | R28-VIEWER ④ · R39-DECOMP-VIEWER ③ *(ratchet pinned; seams measured — see entry)* · R43-VIEWER-CONFORMANCE · UX-3 *(library depth — `apps/web/src/viewer/tools/authoringSection.ts`)* · SITE-1 *(parcel overlays — `apps/web/src/viewer/gis.ts`)* |
| **F · Docs & demo** | `README.md`, `docs/`, `apps/web/src/demo/` | keep the shipped surface honest (below) — no coded items. **`demoData.test.ts` now gates the shell's startup endpoints**; re-run `build_demo_data.py` and that test after adding one |
| **G · API surface** | `services/api/src/aec_api/routers/`, `main.py` | no standalone items: **every lane routes its own work**, which is why this is a lane rather than a shared file |
| **H · Registers** | `services/api/modules/*/module.json` | — |
| **I · API client** | `apps/web/src/api/` | SCALE-SEAM ㉙ *(the only open slice; ②–㉘ have shipped. This cell named ⑬–⑳ until 2026-08-24 — eight slices whose extractions had already landed — because the item regex could not see `㉒` at all, so nothing required this row to be right)* |
| **J · Build & tooling** | `apps/web/scripts/`, `apps/web/vite.config.ts`, `apps/web/src/style.css`, `apps/web/src/tooling/`, `services/api/test_file_sizes.py`, `services/api/run_tests.py` | R39-TSC-CACHE *(local typecheck once diverged from CI; cause unknown, prior explanation retracted — an OBSERVATION, not a defect with a known fix. Read the entry before "fixing" it: the proposed fix is named there and rejected)* |

**Parked — not available to pick up.** These are decisions or multi-release commitments, listed so
nobody starts one thinking it is a sprint item: QUALITY-ROOM · R26-V-TIMING · R24-PERSONA-SHAPE ·
R24-IDENTITY · R32-TAXONOMY-LIFECYCLE (all five need the user's call) · PHOTO-PIN · CMMS-OPS (BIG-TICKET: open **one**, slice
it) · REL-7 (gated on RT-KNIP) · R35-SANDBOX-ISOLATION (process/container isolation for snippet execution — a genuine design change, needs the user's call on deployment shape) · R35-PREFLIGHT-CI (run the prod-config validator against the **actual deploy overlay** in CI — still needs a decision on where the deploy env template lives. **Split 2026-08-02:** the half that needs NO decision — smoke the validator against a *synthetic* safe posture → exit 0 and an unsafe one → exit 1, catching a validator crash, a check regressed to a no-op, or a FAIL demoted — is unparked as a ~10-line CI step; the security session has claimed it).

**A fourth was wrong until 2026-08-07, and it is wrong in the way the table could not see.**
`roadmapLanes.test.ts` asserts the rows are **disjoint** — no two lanes claim the same path — and it
is right to. But **disjointness and coverage are two different claims, and only the first was
tested.** A table that is perfectly disjoint and owns 62% of the tree passes every assertion, and the
rest is invisible: not contested, simply unclaimed.

Measured: **152 of 390 tracked files under `apps/web/src` belonged to no lane — 53 once vendored code
and ambient type declarations are set aside.** The unowned set includes `proforma/`, `drawings/`,
`kernel/`, `pins/`, `studio/`, `tools/`, `tree/`, `connections/`, `account/`, `deploy/`, and the loose
files in `portal/` that are neither `portal.ts` (A) nor `panels/`/`register/` (B) — `offlineQueue.ts`,
`prefs.ts`, `panelContext.ts`, sitting between the two lanes least likely to be watching each other.
That is the same shape as the 2026-07-30 nested overlap, one level up.

This is not theoretical: Lane J's own note records three sessions in one day hitting a path belonging
to no lane, and on 2026-08-07 a real defect in `apps/web/src/proforma/proforma.ts` — a reserve
contribution presented as a recommendation without reading the flag that says whether it verified —
had to be fixed under a one-change lane assignment because there was no row to point at.

**It is now a ratchet rather than a proposal.** `roadmapLanes.test.ts` counts unowned files against a
ceiling that only ever goes down, and the way down is adding a row here. Rows still to agree:
`proforma/` · `drawings/` · `kernel/` · `pins/` · `studio/` · `tools/` · the loose `portal/`
files · `dev/` · `account/` · `connections/` · `deploy/`.

**`tree/` came off that list on 2026-08-21, and it was DERIVED rather than agreed.** The paragraph
above warns that guessing an owner for a directory is how the register problem was made, so the
question asked was not "where does this feel like it belongs" but *who imports it*:
`apps/web/src/tree/tree.ts` has exactly **one** importer in the whole tree,
`apps/web/src/viewer/tools/projectPanel.ts`, which is Lane E's. No second lane reaches it, so there is
no boundary to negotiate and nothing to agree — the import graph had already answered. `tooling/` left
the list the same way at v0.3.1017 (Lane J). The remaining names are still open, and the ones with
several importers across lanes are the ones that will actually need a decision.

**CORRECTED 2026-08-07, and the correction found a real overlap the original claim would not have.**
This said the disjointness check "compares the strings raw", so `field/` and `apps/web/src/field/` in
two lanes would read as disjoint. **That was false** — the check already stripped `apps/web/src/`, and
planting exactly that duplicate proved it caught it, naming both lanes.

The real gap was the *asymmetry*: it normalised **one** prefix, `apps/web/src/`, so it was blind on the
services side — and that is where a live overlap was sitting. Lane G claims bare `main.py`, which is
`services/api/src/aec_api/main.py`; Lane C claims `services/api/src/aec_api/` and carved out only
`routers/`. **The FastAPI entry point belonged to two lanes at once**, and those two strings never
compared. `main.py` is now carved out of C, and the check resolves every claim to a repo-relative path
against `git ls-files` instead of stripping one hard-coded prefix.

**Two lane boundaries were wrong until 2026-07-30 and are worth naming.** Lane A used to own
`apps/web/src/portal/` *wholesale* while B owned `portal/panels/` — a nested overlap, so the two lanes
least likely to notice each other shared a directory. And `routers/` sat inside C's path with no owner
of its own, which is how a route can be added twice. **A lane table whose paths overlap is not a lane
table**; the new `roadmapLanes.test.ts` asserts disjointness so this cannot come back.

**A third was wrong until 2026-08-03, and it is a different KIND of wrong — worth more than the other
two.** Lane A owned `portal/portal.ts`; Lane B owned the register-shaped items. Those paths are
perfectly disjoint and `roadmapLanes.test.ts` was perfectly green, because the generic **register
renderer** — the config-driven engine behind every register's list, filters, table, form, record and
board — lived inside `portal.ts`. So every Lane B item aimed at a register had to edit a Lane A file
to do its work, and the table said nothing was wrong.

Three items hit it before anyone named it. `R36-EMPTY-STATE` shipped that way (v0.3.849) and avoided a
collision only because the Lane A session happened to be elsewhere that hour. `R24-MONO-DATA` gave up
on its `portal.ts` hunk and left the reason in `ui/monoData.test.ts` — "held by another session's
in-flight work". `R24-DENSITY ②`, whose whole point is *"applied to registers, not just the
dashboards"*, was pointed at the same wall.

**The lane check cannot see this class of defect and no version of it can.** It asserts a property of
*paths*; this is a mismatch between a path and the *work*. Two fixes were available and only one was
honest:

* *Move the register items to Lane A.* **Rejected** — it relabels the collision instead of removing
  it. `R36-EMPTY-STATE` genuinely edited `ui/empty.ts` **and** `portal.ts`; under Lane A it would have
  straddled in the other direction. While one file holds both jobs there is no assignment of the items
  that makes them stop straddling.
* *Make the boundary statable.* A carve-out is written `!path` and a path is a file, so "the register
  methods of `portal.ts`" cannot be expressed at all — and §4 of the directions is explicit that a
  prose exclusion is not a boundary. So the renderer became a file: **`apps/web/src/portal/register/`
  belongs to Lane B**, and `portal.ts` is the shell (nav rail, room spine, dashboards, destination
  dispatch) and stays Lane A's. Shipped v0.3.850; a behaviour-preserving move, 1149/1149 web green.

Two checks hold it. `roadmapLanes.test.ts` now asserts the two paths are owned by *different* lanes —
the failure that matters is someone dropping `portal/register/` and leaving it unowned. And
`portal/register/registerOwnership.test.ts` asserts the code side: no register internal may reappear
in `portal.ts`, and the six members the shell reaches through are enumerated, because a seam holds
only while crossing it is inconvenient and `this.reg.` is not inconvenient at all.

**The general lesson, and it is not about registers.** *A lane's paths and a lane's items are two
claims, and only the first one is tested.* Before starting an item, check that the file you will
actually edit is inside your lane — the table's own greenness is not evidence of that.

**Unowned paths — found while fixing the above, 2026-08-03. NOT decided here.** The lane check asserts
that lanes do not *overlap*; nothing asserts they *cover*, and they do not. `apps/web/src/drawings/`,
`proforma/`, `studio/`, `tools/`, `tree/`, `pins/`, `kernel/`, `account/`, `connections/` and the
`portal/` root files (`prefs.ts`, `offlineQueue.ts`, `panelContext.ts`) belong to no lane, which the
carve-out check in `roadmapLanes.test.ts` correctly calls "editable by everyone" when it happens
deliberately. The live case: **`R36-DRAWINGS-RETURN` is Lane A and lands in
`apps/web/src/drawings/`**, so `drawings/` remains unowned rather than assigned by guess.
It needs its own premise-check; guessing an owner for a directory a lane is already aimed at
is how the register problem was made.

**Shared files that need a heads-up before editing.** Every multi-session conflict so far has been one
of these: `services/api/run_tests.py` · `services/api/src/aec_api/main.py` · `docs/roadmap.md` ·
`CHANGELOG.md` · the three version files (`apps/web/package.json`, `src-tauri/tauri.conf.json`, and
`package-lock.json` — which is regenerated, never hand-edited).

*`apps/web/src/api/` is a lane now rather than a shared file.* Until v0.3.800 it was one 4,956-line
`client.ts` that every lane had to open, which made it the single worst collision point in the repo.
SCALE-SEAM split it by domain (`schedule.ts`, `model.ts`, `modules.ts`, `estimate.ts`, `authoring.ts`,
`library.ts` over `httpCore.ts`), so adding an endpoint now touches the one domain file that matches
it. `client.ts` itself is **composition only** — if your change adds a line there, say so.

### Lane F — the shipped surface is behind the product

Unglamorous and the most consistently wrong thing in the repo: **the docs describe an older app.**
Three staleness bugs were fixed on 2026-07-29 alone — the README claiming `?shell=spine` turned the
shell *on* (default for 50 releases by then), the roadmap status block quoting suite counts 38 releases
old, and both README and roadmap still offering a `?shell=classic` opt-out that had been deleted. Each
was caught by accident rather than by a gate.

**Re-measured 2026-07-29 after v0.3.786/796 — two of the three items below were fixed while this
section still described them as broken.** That is the same defect the section is about, one level up:
a list of stale claims that had itself gone stale. Measured, not assumed:

* **The Pages demo snapshot is CURRENT.** ✅ Fixed in `90783da7` (v0.3.786), which added
  `grab(c, "/rooms")` to `build_demo_data.py` and re-captured. `demoData.json` now carries **133
  modules** across the populated rooms — `design` 32 · `schedule` 38 · `planning` 25 · `cost` 18 ·
  `operate` 12 · `deal` 8 — and `GET /rooms` is in the capture for the first time. `work` is absent
  because it legitimately holds 0 modules, not because it is missing. The previous entry's "132
  modules across exactly four rooms, 38 pointing at a room id the shell cannot render" is no longer
  true of any file in the repo.
  **The root cause is worth keeping even though the symptom is gone:** `/rooms` was never in the crawl
  at all, so the demo rail always rendered from `FALLBACK_ROOMS` — and the fallback drew something
  *plausible*, which is why a taxonomy change rotted it silently. See
  [[the-dangerous-default-is-the-plausible-one]].
* **`docs/walkthrough.md` and `README.md` carry no stale shell flag.** ✅ Neither mentions
  `?shell=spine` or `?shell=classic` at all (grep: 0 occurrences each). The walkthrough names rooms
  (10×), the vitals strip (2×), `.mass` (3×) and samples (4×); the README names rooms (11×),
  received-sheet regions and firm standards. The R26-era gap this entry described has been closed by
  the doc gates plus ordinary release notes.
* ✅ **CLOSED 2026-08-01 (v0.3.815).** The walkthrough was read end-to-end against the seven-room
  spine, and the gap was worse than "unread": the existing membership gate is satisfied by a **single
  headline enumeration**, and that is exactly what the doc had. Measured, `planning`, `work` and
  `operate` appeared **once each** — in the room list — and **nowhere else**, while `cost` appeared
  eleven times. Three of seven rooms were named and never explained: the doc-level form of a tab that
  highlights but does not navigate. The click-through now visits Planning, Work and Operate with their
  shipped job statements.

  Both missing gates are now in `docsCurrent.test.ts`, mutation-checked: **room ORDER** (a doc that
  *lists* the rooms must list them in `ROOM_IDS` order) and **room SUBSTANCE** (every room must appear
  in the walkthrough beyond the enumeration). The order gate's first draft used a proximity window and
  failed on correct prose — it read the click-through's *route* ("Schedule → Budget … back in Design …
  the Cost room") as a claim about tab order. It now matches only verb-free lists, because **a gate
  answered by rewriting good writing is worse than no gate.**

`docsCurrent.test.ts` gates **10** assertions across `README.md` and `docs/walkthrough.md` — shell
flags in both directions, every room appearing in the README, the retired three-tab nav, the vitals
strip, what a sample *is*, deleted samples, and rooms the product does not have. That is more than
"a handful", and it is why two of the three items above closed themselves. **It should still gate
more:** every doc sentence naming a flag, a count or a room is a claim that can rot, and the ones
that rotted were all sentences no test read. Note for whoever extends it — the file lives in
`apps/web/src/shell/`, which is **Lane A**, not Lane F.

### Decisions, not effort — these want your call

- **A prospect investor dilutes every real one, and the obvious fix empties the cap table.**
  *(measured 2026-08-29; money-bearing, and NOT a filter fix — read the second half before touching it)*

  `capital.cap_table` sums `commitment` across **every** investor regardless of state. It even reads
  `workflow_state` — to display as `status` — and never filters on it. Measured against the real
  function: two funded LPs at $6M and $4M, plus one `prospect` carrying a $10M interest and $0
  contributed, and the prospect takes **50% of the cap table**, halves Anchor LP from **60% to 30%**,
  and sorts to the top as the largest apparent owner.

  It does not stop at display. `distwaterfall` allocates
  `share = lp_total * (commitment / lp_commit)` off these rows, so the prospect draws a real
  distribution share; and `lp_contrib = sum(contributed) or lp_commit` falls back to commitment when
  nothing was contributed, which is exactly a prospect's position. Seven call sites consume
  `cap_table`, including the `/cap-table` route, two finance report builders and the securities bridge.

  **The obvious fix is wrong, and this is the part worth recording.** Excluding `prospect` looks
  correct and is not: `investor`'s workflow declares `initial: prospect`, and `modules.py` stamps the
  initial state on every record at creation. So *every investor entered through the product is a
  prospect* until somebody runs the `commit` transition. I implemented the filter, and
  `test_distwaterfall` — which creates three investors through the real API and expects a $2,000,000
  distribution — returned **0.0**. Not a stale fixture: that is the product's own default path. A
  filter would empty the cap table of every project whose investors were never transitioned.

  So the question is which signal means "this commitment is real", and it is a domain decision rather
  than a code change: (a) make `committed` the initial state, or require the transition before a
  record counts — a data migration for existing projects; (b) key the math on `contributed > 0`
  instead of state, which changes what a *commitment* means in an uncalled fund; or (c) keep the rows
  and exclude them from the denominator, showing prospects at 0% with the pipeline named separately.
  Each is defensible and they produce different ownership numbers, which is why this is yours.

- **Asset-rights stopped at signing, on purpose, and going further is your call — not effort.**
  Shipped 2026-08-29: a stable asset identity that survives a `.mass` round-trip, an opt-in release
  manifest citing the container's existing digest rather than re-implementing it, and Ed25519 sign +
  verify. That is authenticity, provenance and tamper-evidence with **no chain, no wallet, no new
  dependency and no legal gate** — steps 1–3 of the sequencing in
  [`docs/internal/asset-rights-nft-design.md`](internal/asset-rights-nft-design.md), which says
  *"Stopped here, as planned."*

  Steps 4 (provider abstraction + mock, still no chain) and 5 (contract, testnet, wallet proof) are
  **Not built**, and they are blocked on five questions that study explicitly refuses to pre-empt.
  Three matter most: whether this repo's prior *"token-last, integrate-don't-build"* decision governs
  provenance at all; whether the goal is **transferability** specifically, given `ShareToken` already
  delivers revocable scoped entitlement and the shipped signature already proves a release is
  authentic and unaltered; and whether **Solidity belongs in this repository** — there is no
  contract toolchain here and CI runs none, so Hardhat/Foundry plus contract tests is a separate
  infrastructure commitment, not a feature increment.

  Recorded here because the shipped half reads as a finished feature, and a reader would have no
  reason to look in an internal design note for the half that is waiting on them.

- ~~**CC0-1.0 on the permitted licence list.**~~ — **settled 2026-08-19 (v0.3.987): add it.** The
  Python classifier already accepted CC0-1.0 from 2026-08-10 (gated by `test_licence_allowlist.py`);
  the *written* non-negotiable and this open-decision bullet had not followed. Operator confirmed.
  Directions, the npm title table, and this row now match the classifier. CC0 is a public-domain
  dedication, strictly more permissive than MIT; 59 files under
  `services/data/families/external/` already declared it.
- **The EOT surface is dark, and deliberately so — but the decision has been pending since 2026-08-20.**
  `POST /schedule/eot` and `POST /schedule/eot/sourced` both exist and **no client code references
  either**. R46 reserves this as a domain decision rather than a wiring task, and it is the right call:
  `sourced` is the auditable one — its own docstring says a caller-typed baseline *"is unauditable… two
  people can produce different EOTs from one project by typing different dates"* — but **an
  extension-of-time figure ends up in arbitration**, so which one a screen shows is a statement about
  what the product asserts, not a UI choice. Surfaced here by the 2026-08-29 sweep because it was
  recorded inside a ring entry that now reads ✅, where a reader looking for open decisions would not
  find it.
- **Whether `/schedule/eot` should delegate its analysis to `schedule_windows` and
  `schedule_modelled`, or keep its own number and cite theirs.** *(This bullet used to open by
  claiming `eot.py` "names four AACE methods and performs none of them. All four return an identical
  number on the same input." **That was false, and false when written** — `v0.3.971` had ended it four
  days earlier, on 2026-08-16. Measured 2026-08-31: three distinct outcomes where the as-built cap
  binds, and the two series methods refuse outright rather than returning any number. The full
  measurement and the reason the error survived a cited test are in the R46 entry above.)* The
  decision itself is untouched by that correction: `schedule_windows` and `schedule_modelled` perform
  three of the four for real, **an EOT figure ends up in arbitration**, and changing what one means is
  a domain call rather than a refactor. Both still ship today.
- **The three renames and the `/edit` body shape in R43-VIEWER-CONFORMANCE.** *(Again not opening
  with the code — `roadmapStale.test.ts` reads an unmarked bullet headed by an item id as a second,
  contradicting copy of that item, which is exactly what this would have been.)* Every one is *which side
  moves*, ours or MassingViewer's. Its entry says so explicitly and stays ◧ for that reason, "not
  because work is left undone here."
- **The requisition half of R43-MASSINGBILL-CORE.** *(Worded so it does not OPEN with the item code:
  a bullet that starts with one is parsed as an item, which is how that same code was counted twice
  until 2026-08-25. Caught here by `roadmapSelfConsistent.test.ts` within a minute of writing it.)*
  The money half closed in v0.3.969; this half "still
  needs the per-site decision" the entry describes.
- **`massingviser` vs modelmaker — which is *the* platform?** Its own description is a federated AEC
  platform in pure Python with a plugin kernel. MassingViewer raised this because both are about to
  grow a federation manager, and two federation managers is the expensive version of this question.
- ~~**ROOM-NAMING**~~ — **settled 2026-07-29 (v0.3.779): professional terms.** Design · Planning ·
  Cost · Schedule · Deal · Work, not the prototype's Building · Budget · Timeline · Money · My
  to-do. These are the words the work already has — an architect issues a *design*, a contractor
  runs a *schedule*, a developer works a *deal*. A plain label reads friendlier until someone must
  decide whether "Money" is the budget, the commitment, the pay app or the equity draw, at which
  point it is a second vocabulary on top of the real one. The reasoning lives in `rooms.py`, and
  `roomNames.test.ts` asserts the Python and TypeScript tables agree label-for-label — they had been
  duplicated across the language boundary with nothing checking them, and the TS copy is what renders
  when `/rooms` fails.
- ~~**Delete `?shell=classic`**~~ — **done v0.3.779.** Default since v0.3.715, deleted sixty-four
  releases later. Two shells is two rails to keep in step, two places a defect can hide, and a render
  audit whose verdict depends on which one it measured — a mistake this repo actually made. What the
  two-shell period bought is kept: `parity.test` still asserts the room rail reaches every
  destination the lifecycle-stage catalog lists, so *nothing became unreachable* outlives the shell
  that motivated it.
- ⛔ **QUALITY-ROOM** — inspections/ITP sit in Design because an inspection checks the built thing
  against the design. Answered 2026-07-28: the *task* already reaches Work via the queue
  (`INS-001`, `DEF-001`, `NCR-001` are in it now), so the *register* stays with its discipline.
  Revisit only if that stops feeling right in use.
- **Branch protection** — `main` is unprotected and public. Blocking force-push and deletion costs
  nothing and is not reversible after an accident.
- **R26-V-TIMING** — needs real users. **Plugin pricing** — needs customers. Both correctly parked.

### External analysis tools — reviewed 2026-07-29, mostly NOT actionable *(CodeFlow · Repowise)*

Two third-party analyses were reviewed in full. **Neither produced work worth doing**, and the reason
is worth recording so the next person does not re-run the exercise or, worse, act on the numbers.

**CodeFlow — REMOVED by the user, 2026-07-30. Decision made; nothing here is actionable any more.**
Kept as a record of *why*, because the failure mode is generic to bolt-on analysers and the next
one will look the same. The measured history: **0 successes across 30 `main` commits and all 10
PRs**, every one reporting `"CodeFlow was not able to perform analysis"` — the analyser never ran.

* Its own report says **"Processing of this commit timed out"** and **"Tool timed out: pylint"**. The
  commit it was asked to analyse was never fully analysed.
* Its 2,350 issues are dominated by **TSLint-era rules**: `max-line-length` 960 · `CodeDuplication` 526
  · `jsdoc-format` 402 · `one-variable-per-declaration` 200 · `no-shadowed-variable` 78 · `no-bitwise`
  18 · `variable-name` 7 · `max-classes-per-file` 5. **TSLint was deprecated in 2019.** This repo lints
  with **ESLint 9.39.5** and **ruff**, both configured, both **clean**. So CodeFlow is not measuring our
  standards — it is measuring its defaults, and disagreeing with the linters we actually chose.
* Its one structural finding is **wrong**: *"Avoid storing generated files in GIT
  (apps/web/src-tauri/Cargo.lock)"*. Rust's own guidance is to **commit `Cargo.lock` for binaries**, and
  a Tauri desktop app is a binary. CI already guards it with `cargo metadata --locked`.
* **It failed on every PR, and that is the durable lesson.** A permanently-red check is worse than no
  check: it teaches everyone to scroll past red, which is how a real failure gets waved through. It
  nearly did here — five PRs read as failing when only #98 carried a genuine CodeQL HIGH. It also
  **saturated the aggregate signal**: GitHub's legacy commit-status `state` is the OR of its contexts,
  so while CodeFlow sat there red, `state` was pinned at `failure` and a *new* status context going red
  would have been invisible. A monitor was changed to report contexts individually rather than trust
  the aggregate — worth keeping if another external checker is ever added.

**[Repowise](https://www.repowise.dev/s/5ad6b7549ac4/overview) — reading a snapshot 426 releases old.**

It has indexed **`f3b171f` = v0.3.363**; main is **v0.3.789**. Every count it reports (881 files, 6,587
symbols, 2,771 findings, 45 dead exports) describes a codebase that no longer exists. Same failure as
the demo snapshot: **a capture rots and nothing fails when it does.** Re-index before quoting any figure.

**UPDATE 2026-07-30 — re-indexed and now CURRENT, and the verdict changes shape.** Connected as an MCP
connector and re-indexed: 1,488 files / 12,064 symbols (was 881 / 6,587). Freshness confirmed the only
way that can't be fooled — `create_stepup_token`, a symbol ~24 h old, resolves. So the staleness
objection above is **closed**.

The findings still do not survive verification, but for a different and more useful reason: three
**systematic** confounds, each checked against this repo rather than argued:

| layer | what it reports | why it is wrong here |
|---|---|---|
| `untested_hotspot` (64) | `has_test_file: false` on `main.py`, `models.py`, `db.py` — and on **`run_tests.py`** | looks for a *paired* test file; our Python tests live at `services/api/test_*.py`, not beside the source. `proforma.ts` correctly reports `true`, so the heuristic works for TS only |
| `dead_code` (8, all `safe_to_delete: true`) | incl. `plugins/example-wall-brand/plugin.py::register` | that IS the plugin contract — `plugin_registry.py:143` does `mod.register(PluginApi(...))` after a `hasattr` check. The editor-bridge recipes are dispatched by name via `f"recipes.{recipe}(...)"` at `bridge.py:70`. Every one sits at a **dynamic-dispatch boundary** the analyser cannot see |
| `import cycles` (3) | 20 files in `aec_api`, 15 in `aec_data`, 1 TS pair | `test_import_cycles.py` passes: *no* top-level cycles across 493 modules. It counts **deferred/function-local** imports — which are the *fix* for cycles. The TS pair is `import type` on **both** sides, erased at compile time |

**Do not action any of those three layers.** Acting on the dead-code list would delete the plugin API.

What IS worth reading: `get_risk` in PR-review mode. Its `missing_cochanges` correctly caught that a
change touching `main.py` had not updated `CHANGELOG.md` or `apps/web/package.json` — the version bump
this very release then made. Its `defect_profile` also flags `routers/drawings.py` as a `bug_magnet`
(4 fixes / 6 months, naming `pdf_seal`), which matches where the v0.3.807 findings actually were. The
history-derived layers are sound; the static-analysis layers are not.

`get_security` (CVEs, secrets, SBOM) is **Pro-gated** and returns `upgrade_required` — unavailable, not
empty. Do not read a missing security section as a clean one.

Its **"45 dead exports"** does not survive verification, and that is the useful part of this review.
Re-derived against current code: 1,097 exported symbols, **231** referenced nowhere outside their own
file — but split by kind that is **153 interfaces + 45 types + 17 consts + 16 functions**. Dead *types*
are not dead code; they are a client's published shape. And of the 16 functions, the alarming-looking
ones were checked by hand and are all **called inside their own module**:

| candidate | actually called at |
|---|---|
| `startTour` | `ui/onboarding.ts:25` and `:125` |
| `showUpdateBanner` | `ui/update.ts:74` |
| `renderCostSpine` | `portal/panels/margin.ts:115` |
| `readEntry` | `api/recordCache.ts:105` |

So **there is no unreachable feature** — the finding is an unnecessary `export` keyword, which is a
tidy, not a defect. Roughly seven more sit in `vendor/massingifc` and `vendor/massingpdf`, where a
library's public API is *supposed* to look unused from inside this repo.

Left undone deliberately: dropping ~20 stray `export` keywords is churn in the highest-churn files in
the repo, and would collide with three active lanes for no behavioural gain.

**What Repowise did contribute — independent confirmation of the hotspots**, mined from git history
rather than from the code:

| file | percentile | prior fixes | commits 90d |
|---|---|---|---|
| `portal/portal.ts` | 99.9th | 4 | 143 |
| `viewer/app.ts` | 99.7th | 7 | 161 |
| `main.ts` | 99.6th | 12 | 136 |
| `api/client.ts` | 99.4th | 8 | 325 |
| `services/data/src/aec_data/edit.py` | 99.3th | 5 | 59 |

That is **exactly** the god-file list already tracked in [[web-godfile-decomposition]] and
[[god-module-decomposition]], and exactly the collision set named in the NOW lanes. An outside tool
reaching the same five files by a different method is worth more than the finding itself — it is
evidence the decomposition plan is aimed at the right place. **Its "bus factor 1" flag is an artifact,
not a risk:** every commit here is authored by one identity whether a human or an agent wrote it.

### Practice note — verify before carrying
Three sections in this file were wrong about their own state on 2026-07-28: **A2-CONSTRAINTS**,
**A2-SHEET-REGIONS** and **A2-ICON-RENDER** were all listed as built-but-unrouted, and all three are
routed and consumed (`analysis.py:542`, `analysis.py:572` + a live 200, `toolbarView.ts:15`). The
roadmap is a claim like any other. Check the premise before spending a release on it — see
[[check-the-blocker-premise]].

**2026-07-29 — the shape those errors take, now that there are enough of them to name.** Six R22/R23
items were implemented in one day and **two of the six had premises that did not survive contact**,
both of the same form: *"it already is X, just formalise it."* `R23-RECIPE-ARTIFACT` said the edit
log already was a CAD operation timeline (the parameters were nowhere). `R22-ENTITLE-RISK` read as
"add two inputs" (`Timing` had no pre-construction period and `monte_carlo` could not express a
binary event — there was nowhere to put either). The same day, three more entries were open in prose
and closed in code: **A2** above, **R22-GOLDEN-THREAD**, and the IfcClass half of classify assist.

So: **"it already is X, just formalise it" is the most expensive sentence in this file, because it
sets the estimate before anyone opens the file.** It reads as a small item, is written by whoever
last skimmed the area, and is never re-checked precisely because it sounds like the check already
happened. Two rules follow — open the file before accepting an estimate that rests on an "already",
and when a premise turns out wrong, **correct the entry rather than only the code**, or the next
reader inherits the same wrong estimate.

A second, sharper pattern from the same day: a roadmap entry that describes a **visible** failure
often conceals a **silent** one, and the silent one is worse. `R22-CLASSIFY-AI` said an unclassified
import "gets nothing" — it actually prices everything as *01 00 00 General Requirements* while
reporting a complete takeoff. Same shape as [[qto-measured-area]] and the entitlement draw that must
not be solved: **a fabricated value survives review that a missing one would not**, because nothing
downstream can tell. When an entry claims a feature is absent, check whether it is instead *wrong and
confident*.
## 🧩 R43 — SIBLING INTEGRATION & THE UI-STRATEGY RING *(measured 2026-08-09/10; see [plan-2026-08-10.md](internal/plan-2026-08-10.md))*

The framework question that opened this ring is **closed, and the answer was neither candidate** —
not React (the facade we would consume, `@massing/embed`, has zero React dependency and an external
runtime closure of exactly `three`), and not Reflex (it compiles to React + Next.js, needs Redis for
per-session state in production, and round-trips every interaction, which the 60fps canvas cannot do
and the offline non-negotiable forbids). What survived the analysis is the *measured* part, and it is
the only item here with real scope.

- ⛔️ **R43-CRUD-FRAGMENTS — RESCOPED 2026-08-11 before any code was written; as originally written it
  was not executable.** The entry said "do ONE register first with a before/after and let that number
  decide whether the others follow". **There is no one register.** `apps/web/src/portal/register/
  register.ts` is a single generic 2,546-line `RegisterUI`, schema-driven, with **zero** per-module
  branches, serving **206** `module.json` modules. Converting "a register" converts all 206 at once.

  That is a different risk profile from the one the ring was approved on: not an incremental trial
  that a measurement can halt, but a single swap across every register in the product, with no
  intermediate state to compare against. **The measurement the entry asks for cannot be taken**, and
  the plan's own logic — let the number decide — has nothing to decide with.

  The LOC split it rested on is confirmed, re-measured recursively: `portal` 11,123 + `proforma`
  1,891 = **13,014 of 46,693 hand-written lines (27%)**, against `viewer`+`drawings` 16,904 (36%).
  So the *thesis* stands — the register third is thin over FastAPI JSON and is where server-side
  composition would pay. What does not stand is the delivery plan.

  **Before this restarts, someone must answer: what is the smallest reversible slice?** Candidates,
  none costed: one field TYPE rather than one module; the read-only table only, leaving inline edit
  on the client; or one module behind a per-module flag the generic renderer honours — which is
  itself a change to the generic renderer. Until one of those is scoped, this is a plan, not a task.

  *Method note, because it nearly went the other way:* a re-check of the 13k figure using
  `portal/*.ts` returned 1,673 and I almost published a correction saying the ring rested on a 3.6×
  error. The glob is non-recursive and caught 10 of 43 files — `portal/panels/` and `portal/register/`
  are subdirectories. **The re-check was sloppier than the thing it checked**, and a wrong correction
  is worse than a wrong original because it arrives wearing a verification badge.

- ◧ **R43-MASSINGBILL-CORE** *(M — Lane C; **money half CLOSED v0.3.969, and not the way this entry said**)* —

  **The premise below was stale by the time it was acted on, and checking it found a live defect.**
  This entry recommends taking "core/money.py" to fix a float path in `payapp.py`. v0.3.927 had
  already replaced that path with exact `Decimal` quantized HALF-UP. But it fixed **one file**: the
  other G702 sites this entry itself names kept `round(amount * pct / 100, 2)` on floats —
  `cost.py` twice, `routers/cost.py` once — and `round()` is ROUND_HALF_EVEN where an invoice rounds
  half away from zero. **Four of six sampled cases differed by a penny** (2.50 @ 5% → 0.12 vs 0.13).
  Two conventions inside one G702; a pay app out by a penny is rejected.

  Closed by pointing the three float sites at `services/api/src/aec_api/money.py`, which has carried
  the half-up quantize since v0.3.191 — additive, `payapp.py` untouched, the five existing G702
  suites as the parity gate, and
  `services/api/test_money_spine.py` pinning both the convergence and the divergence it replaced.

  **Neither "massingbill/core/money.py" nor a new module was adopted** (plain quotes: it is upstream's file, and a backtick reads as a citation into this tree). The correct implementation was already here; three sites had simply never been pointed at it. Integer cents is not more correct than quantized `Decimal`, it is a
  different correct answer, and swapping one for the other on a shipped billing path is risk without
  reward.

  **The requisition half is untouched** and still needs the per-site decision described below.

- ◧ **The original R43-MASSINGBILL-CORE review** *(kit reviewed 2026-08-10 at their pin `3af9124c`;
  **not a second item** — this is the evidence the entry above rests on, and it opened with the
  item code until 2026-08-25, so the extractor parsed one item as two. It could not FAIL on it:
  `itemCodes()` collects into a `Set`, so a duplicated code collapses silently and the count is
  right for the wrong reason. v0.3.1073 shipped under the title "two entries for one item,
  again"; this is the same shape a third time, surviving because the check that would see it
  de-duplicates before it counts)* —
  **the core now exists and is MIT; their "pure addition" claim does NOT survive checking.** They
  shipped `massingbill/core/` — four stdlib-only modules (`money`, `retainage`, `requisition`,
  `enums`) with a CI job that pip-installs nothing at all, so "zero deps" is measured rather than
  asserted. Licence read from their `LICENSE` file: MIT.

  **Verified on our side, and this is the part that changes the plan.** Their message said there is
  *"no G702 header math, retainage engine or change-order handling on your side to supersede"*. Both
  halves of that are wrong: `payapp.py:49` computes `amt * retainage_pct / 100.0` — retainage
  arithmetic, in floats, on billable amounts — and `G702` appears in **six** of our files
  (`cost.py`, `report.py`, `rooms.py`, `routers/closeout.py`, `routers/cost.py`,
  `routers/proforma.py`). So the requisition half is **not an addition, it is a potential duality**,
  which is the shape that produced "two objects both called an RFI". It needs a per-site decision,
  not a drop-in.

  **What they got right, confirmed:** `payapp.py:23` is a single `float(str(v).replace(",", "")
  .replace("$", ""))` that every billed amount flows through, and summing a 200-line schedule that
  way drifts. `sov_build.py` derives an SOV *from a model estimate* and theirs never does, so that
  one is genuinely ours and they compose.

  **Recommended split (the user's call, see the decisions section):** take "core/money.py" first and
  fix the float path alone, with the existing G702 suite as the **parity gate** — the new code must
  reproduce the old numbers before it replaces them. Treat the requisition half as its own ring once
  the six G702 sites are mapped.

  *Their environment claim was also wrong in our favour to catch:* they assumed we run 3.12. CI does;
  the api venv is **3.10.6**, where `from enum import StrEnum` raises. Their guard commit is the
  difference between a clear message and a baffling one on the first local run.

## 🏗 R21 — LOD 400→500 DOCUMENTATION RING *(from a real LOD 400 shop-drawing set, 2026-07-25)*

Measured against an actual issued wall-section + detail package (13 sheets, 1:100 → 1:10) rather than
against a description of one. The mission is **acquisition → turnover at LOD 500**, and LOD 500 is
field-verified as-built — but a project only *reaches* verification through an issuable LOD 400 set.
These are the gaps between what the platform draws today and what that package contains.

**Tier 1 — the set cannot be issued without these**

- ~~**R21-MULTISCALE**~~ *(S)* — several viewports at **different scales** on one sheet (1:100 overall +
  1:50 parts), each with its own title/scale block. `sheet_layout.py` composes viewports; per-viewport
  scale is the missing parameter.
## 🎯 R22 — COMPETITIVE GAP RING *(13 platforms scanned 2026-07-25; acquisition→turnover mission)*

**The finding that orders this ring:** across every platform scanned — agent bureaus, procurement AI,
document intelligence, field capture, ERP, and the category leader's twenty-agent library — **not one
competitor's AI touches geometry.** They all read documents *about* the building. Massing's agents can
read the building. Items marked ⭐ are the ones that convert that into product; the rest are table
stakes we are missing.

> **Read every entry in this ring against the code before sizing it.** Four in a row on 2026-07-29
> turned out to be wrong in the same direction — the machinery existed and only its **reach** was
> missing (R22-MEMORY: cross-project cost-code distributions existed, per-*unit* did not.
> R22-CARBON-OPTION: three carbon paths existed, the option card had none), or nothing was missing at
> all (R22-ACCT-SEAM: the whole seam shipped, including an exact double-entry assertion; the correct
> deliverable was *reporting that*, not adding a redundant gate). The entries over-estimate because
> they were written from a competitive scan rather than from the files, and they are never re-read
> **precisely because they sound like the check already happened**. An entry that says "build X" and
> means "extend X by 20%" costs more than an entry that says nothing — a named prerequisite is not
> evidence of a missing one.

**Tier 1 — closes the mission's own gaps**

- ◧ **R22-ENTITLEMENT** *(M/L — ①②③ shipped: `approval_conditions.py`, `condition_checks.py`,
  `approval_cycles.py` + the `review_cycle` register)* — **permit & entitlement workflow**: jurisdiction
  submittal packages, review cycles, comment responses, and **conditions of approval carried into the
  model as constraints**. Today there is a hole between "acquisition" and "construction" in our own
  mission statement — we underwrite the deal and we build it, and nothing spans approval.

  ④ **comment round-tripping, shipped v0.3.1042.** `revise()` writes a new record with a new id and
  comments are keyed by `record_id`, so a resubmittal showed an empty thread: measured, 2 comments on
  SUB-001 and **0** on SUB-001.1. Generic across the fifteen `revisable` modules — a reissued RFI lost
  its discussion identically. Inherited comments are labelled with the revision they were written
  against rather than merged flat, because a rev-0 comment presented as current is a confident wrong
  answer rather than a missing one.

  ④ **submittal PACKAGES — the inbound half was already shipped, and this entry did not say so.**
  `GET /projects/{pid}/modules/{key}/{rid}/related` returns `{outgoing, incoming}`, and
  `register.ts` already renders the incoming side as *"Referenced by — Records that point to this
  one"*. Verified on 2026-08-20: a transmittal with `purpose: "For Review"` and three submittals
  returns all three as `incoming`. **A duplicate engine, route, client method and DTO were written
  before that check and reverted unshipped.**

  The premise-check that failed is worth more than the code that was thrown away. The entry's own
  warning — *"premise-check on semantics, not names; this ring has produced a naming-based false
  blocker four times"* — was read first, and the check still went wrong, because it asked the
  question of the **wrong surface**: the submittal/transmittal module fields (prose textareas) and
  the `GET .../{rid}` response (`links: []`, no inbound). Both answers were accurate and both were
  about a surface that does not own the capability. **Checking one endpoint does not check the API**;
  when the question is "can the product answer X", the population to search is every route on the
  record, not the one whose name matches the noun.

  ③ **review cycles, shipped v0.3.978.** The premise-check is worth keeping: both registers existed
  (`entitlement`, `permit`) and neither modelled **rounds** — `permit` has a single `under_review`
  state, so a third round is indistinguishable from a first and the only recoverable duration was
  `applied_date → issued_date`. One number, for a process that is a back-and-forth. That number cannot
  answer the question a seven-month permit actually raises, which is never *how long* but **whose court
  did it sit in**: an agency holding three rounds for 40 days and an applicant taking 55 to answer them
  produce identical elapsed time and opposite remedies. `approval_cycles.cycles()` splits
  `days_with_agency` from `days_with_applicant` and states the share. An open round is **counted and
  named, never scored** — treating a missing comments-received date as zero would report a submission
  the agency has held for ninety days as instantaneous, which is the most flattering possible lie
  about the party you are about to argue with. Days are **calendar**, stated on the response, because
  a statutory review clock does not pause for a weekend and construction durations elsewhere here are
  working days.
  **Remaining:** submittal *packages* (the documents that go to the authority) and comment-response
  round-tripping into RFI/issue records.

  ⚠️ **Two name collisions sit on this item; gap-check on SEMANTICS before touching it.**
  `tiers.py` is **subscription tiers** (free/pro/enterprise), nothing to do with land use — it was
  "entitlements.py" until v0.3.847 renamed the two squatters so only the land-use register keeps the
  word. The warning below is kept because it is what made the collision findable, not because it is
  still live.
  `proforma/approval_risk.py` is genuinely adjacent — but it *scores risk*, it does not run a
  submittal workflow, so it neither closes this nor is irrelevant to it. A name-based sweep gets this
  item wrong in **both** directions: `tiers.py` makes it look shipped, and stopping there means
  never noticing `approval_risk.py`, which the eventual build should probably feed. Third
  collision found on 2026-07-31, after `report_builders/` (five hardcoded builders, not the no-code
  builder R22-REPORT-BUILDER describes).
- ◧ **R22-AGENT-PACKS** *(M — **Lane C part COMPLETE**: `agent_packs.py` shipped, audit half CLOSED
  2026-08-06, attribution fixed at the call site. **Dropped from the Lane C cell 2026-08-16** —
  its own text already said the remainder is the governance console, which is Lane A/E. Leaving a
  code in a lane that cannot finish it makes the lane look busier than it is)* — **named agent packs + org "Skills" + a governance console** over the
  MCP layer we already ship. We expose raw capability; the market ships "Submittal Review Agent",
  which a superintendent understands. Pure packaging of existing tools, plus per-run audit logging —
  the gating factor for enterprise adoption. Our version reads the IFC, so a submittal check can test
  the submitted product against the element's *specified properties* rather than against a PDF.

  **The audit half is done, and the last gap was in the caller, not the callee.** `dispatch` audits
  every run, success and failure — but it can only record the identity it is *given*, and the stdio
  transport (`services/api/mcp_server.py`, the one path every real agent run takes) passed none. Every
  row read actor `mcp`, no user, no pack: the trail answered *which tools ran* and not *whose agent
  ran them*, which is the half an enterprise actually asks for, both before granting access and after
  an incident. `test_agent_packs.py` asserted attribution "to the effective user, not the transport"
  and passed the whole time, because **the test supplied a user the transport never did** — a test
  that provides a caller's arguments cannot notice the caller omitting them. The transport now reads
  `AEC_MCP_USER` / `AEC_MCP_ACTOR` / `AEC_MCP_PACK`, warns at startup when runs will be unattributable
  rather than recording them silently, and refuses to invent a person-shaped default (an unverified
  name in an audit trail is worse than an honest "the transport ran this").
  `services/api/test_mcp_attribution.py` asserts the **call site** forwards all three, mutation-checked
  against the original defect. **What remains is the governance console itself — Lane A/E, not C.**

**Tier 2 — evidence, provenance and procurement**

- ◧ **R22-PIPELINE** *(M → S — premise-checked 2026-08-07; the backend is built, the remainder is mostly viz)* — **multi-site pipeline dashboard** above the project workspace. Acquisition
  is a funnel, not a project.

  **PREMISE-CHECKED (no build). Both halves the entry describes already exist.**
  The acquisition funnel is `deal_funnel.py` — stage conversion, weighted value, cycle times, and a
  `data_quality` guard that refuses to report a conversion rate off too few closed samples. The
  roll-up *above the project workspace* is `GET /portfolio/executive`: cross-project SPI, % complete,
  lookahead, late milestones, GMP / EAC / variance-at-completion, an overall status per project,
  portfolio totals and a status tally, plus the latest solved scenario's IRR/EM per project.
  `/portfolio/construction`, `/portfolio/prioritization`, `/wip/portfolio` and `/fca/portfolio` sit
  beside it.
  Against the spec reference this entry cites, that already covers **multi-project KPI strip, EVM
  SPI/CPI, milestone tracking and cost-by-project**.
  **Genuinely missing is three items, and two of them are not Lane C:** a *cross-project* Gantt
  (`schedule_viz.py` is per-project), a portfolio **risk heat map**, and **resource allocation by
  department**. The near-misses were checked rather than counted: the "heat" matches in
  `element_5d.py` and `scan_deviation.py` are different domains (5D element heat, scan deviation), and
  the `department` matches in `rooms.py` and `scope_clauses.py` are incidental rather than resourcing.
  So this is not an M of backend work. Size the resourcing engine on its own and route the two
  visualisation items to the lane that owns them.
## ⚡ R23 — ENGINEERING UPGRADE RING *(technical scan 2026-07-25; file:line evidence)*

**A THIRD false blocker, and the biggest one.** **W10-9 dimensional constraints** has sat gated for
months behind *"planegcs, LGPL — sidecar-solved, baked to IFC"*. The licence survey confirms the hard
blocks (CAD_Sketcher and py-slvs/SolveSpace are **GPL-3**, correctly excluded) — but it also found
that **we never needed a full geometric constraint solver.** `kiwisolver` (Cassowary) is
**Modified BSD-3**, a ~60–100 KB prebuilt wheel, already a transitive dependency of matplotlib, and
its inequalities-plus-strengths model covers what BIM dimensional locks actually are: axis distance
locks, alignment, offsets, equal spacing of grids/columns/mullions, level-height chains, sill/head
heights — **and clearance minimums as ≥ constraints**, which wires straight into code-check.
Over-constrained models degrade gracefully and unsatisfiable constraints are named, which is the DOF
feedback the UX needs. The nonlinear tail (angles, tangency, arcs) is residuals through
`scipy.optimize.least_squares` (**BSD-3**, already present) — structurally what planegcs does inside.
**W10-9 moves out of Gated and becomes ordinary work with a BSD-3 dependency.**

*Three gates disproved in one day — dev API, geometry stall, and now this. The lesson is now a rule:
a gate is a hypothesis until someone tests it.* See [[check-the-blocker-premise]].

**Tier 1 — measure, then take the cheap wins.** *Every item below is unverifiable until R23-PERF-TEST
exists: the repo has a 220 KB bundle budget and **zero** runtime perf assertions.*

- ~~**R23-CONSTRAINTS**~~ *(L)* — W10-9 via **scipy's `least_squares`, which is already a dependency**
  (`services/api/requirements.in:27` and `services/data/requirements.txt:8`, both `scipy>=1.11`).
  This entry said "via kiwisolver + least_squares" until 2026-07-29. **`kiwisolver` is NOT a
  dependency of this repo** — so the entry pointed at a package someone would have had to add, in a
  repo where a new dependency needs explicit sign-off, to get a solver scipy already provides. Checked
  because a named prerequisite is exactly the kind of claim that turns out to be a past reading rather
  than a property of the code.
  **Dependency taken 2026-07-25.** `kiwisolver` is **Modified BSD-3** — squarely on the approved
  licence list — a ~60–100 KB prebuilt wheel, and already a transitive dependency of matplotlib, so
  it adds a *declaration* rather than new surface area. Trivially reversible. Proceeding on the
  standing delegation; flagged here so it can be objected to in one line.
- ⛔️ **R23-PICKING** *(M)* — **CLOSED UNBUILT 2026-07-31, on a measurement. Do not reopen without a
  new one.** Raycast latency was measured directly on `loader.fragments.raycast()` against a generated
  **35,030-element** fixture (19× the densest sample), 300 samples after a discarded warm-up:

  | | n | min | p50 | p90 | p95 | p99 | max |
  |---|---|---|---|---|---|---|---|
  | **hits** | 143 | 0.7 | 1.6 | 3.0 | 3.8 | **4.8** | **5.4** ms |
  | **misses** | 157 | 0.0 | 0.3 | 0.8 | 1.2 | 2.0 | 6.0 ms |

  **Single-digit ms across the entire distribution, p99 and max included.** The 1500 ms fallback the
  prose justifies has ~**250× headroom** over the worst observed sample. Hits and misses are reported
  separately because they are different code paths and a mean would have hidden that misses are ~5×
  cheaper. **The comment at `app.ts:389` — *"Normal raycasts answer in ms"* — is correct, and now has a
  number behind it instead of a claim.** GPU ID-buffer picking would optimise something that is not slow.

  *Fixture is generated and LOCAL; `samples/*.ifc` are gitignored, so the reproducible artefact is the
  recipe, not the file:* `generate_blank_ifc(storeys=20, storey_height=3.5)`, then per storey 250×
  `edit_struct.add_wall` + 250× `add_column` → 10,000 products / 35,030 local ids / 10.9 MB IFC →
  1.1 MB frag. **Generation is superlinear**: 10,000 elements took 407 s where a linear extrapolation
  from 2,400-in-21.6 s predicted ~90 s. Budget from that, not from the linear estimate.

  *Original premise correction, kept because it is why the item survived to be measured:*
  The scan read the 1500 ms `Promise.race` at `viewer/app.ts:337` as "an admission that picking latency
  already hurts". The source says the opposite, in its own comment: the race guards against *a stalled
  Fragments worker (hidden tab / heavy load)* silently eating clicks, and states plainly that **normal
  raycasts answer in ms**. It is a resilience guard, not a latency workaround, and there is currently
  **no measurement showing picking is slow at all**.
  GPU ID-buffer picking (scissored 1×1 target, O(1) in polygon count) remains a real technique and
  three-mesh-bvh is present transitively (MIT) — but this is now gated on **measuring raycast latency
  on a genuinely large model first**. If the measurement does not justify it, the correct outcome is to
  close this item unbuilt. *Fourth false premise found this session; see [[check-the-blocker-premise]].*
  **Blocked on a fixture, checked 2026-07-31 — the measurement cannot currently be taken.** Picking goes
  through `loader.fragments.raycast()` (`viewer/app.ts:391`, not `:337` — the file moved), which is the
  Fragments runtime's own call, so only a **live** measurement answers this; a bare `THREE.Raycaster`
  benchmark would be a different reader answering a different question. Two things are missing: the dev
  API is down (`curl :8093/health` → `000`) and **there is no genuinely large model anywhere in the
  repo** — the biggest fragment set in `preview_storage/` is 3.6 MB, against a gate reading "a genuinely
  large model".

  ⚠️ **CORRECTION 2026-07-31 — my own prescription here was wrong, and inverted.** I first wrote that
  the fix was to *convert one of the 50 MB `samples/*.ifc`*. Measured, that produces the second-smallest
  model in the repo. **File size is anti-correlated with element count in these samples**, because the
  50 MB files are large as *text*, not as geometry:

  | fixture | elements | IFC MB | frag MB |
  |---|---|---|---|
  | `basichouse` (the 50 MB one) | **154** | 50.3 | 3.6 |
  | `school_str` | 1,536 | 8.2 | 0.6 |
  | `vertical_farm` (densest) | **1,840** | 1.5 | — |
  | generated, 10 storeys | 2,401 | 2.5 | 0.3 |

  `basichouse.ifc` was converted rather than argued about: 52.7 MB → 3.6 MB frag in 7.0 s, i.e. *exactly
  the size of the set we already had*. **Following the instruction lands you back where you started.**

  So this is not blocked on converting a fixture; it is blocked on **a fixture that does not exist**.
  The repo maximum is 1,840 elements and picking needs 10k–100k+ — not within an order of magnitude.
  The fixture step is therefore **generate, not convert**, and must be specified in **elements**, never
  megabytes: `generate_blank_ifc` + `edit_struct` produced 2,401 elements in 21.6 s, extrapolating to
  ~20k in roughly 3 minutes. Unlike the samples this is reproducible from a clean clone, since
  `samples/*.ifc` are gitignored.

  **Worth measuring rather than closing**, for one specific reason: `app.ts:389` already asserts in a
  comment that *"Normal raycasts answer in ms"*, and that prose is load-bearing — it justifies the
  1500 ms timeout fallback. Replacing a prose performance claim with a number is precisely what this
  ring exists to do. If the number comes back single-digit ms, **close the item unbuilt** and keep the
  measurement.
## 🎛 R24 — INTERFACE RING *(external design audit 2026-07-25; see [design-audit.md](internal/archive/design-audit.md))*

**The thesis, and it is not "add features".** Adoption is the binding constraint, not capability.
**47%** of contractors name *getting people to use new technology* their biggest challenge (AGC 2024);
**12%** of features carry 80% of daily use (Pendo, 615 subscriptions). With ~130 modules shipped, about
**ten** matter to any one person on a given day — and which ten depends entirely on who they are. A
catalog with favourites and a filter treats that as a **browsing** problem. It is a **routing** problem.

The payoff is specific to us: every record, geometry and cost line shares one IFC GlobalId, so the
platform can answer *"where did this number come from"* in one hop. **The interface does not cash that
in.** R24 is about making the engine's one real advantage visible.

### Re-verified 2026-07-29 at v0.3.778 — read this before picking up an item

The ring was transferred from the audit in one sitting and **never re-checked against the code**. It
has been now, item by item, and three things came out of it that change what to work on.

**① The audit's own evidence base was stale on arrival.** Its header reads `v0.3.4 · 566 commits` and
"~80 modules"; we were near v0.3.67x with ~130. `internal/archive/design-audit.md` corrected the module count without
recording the provenance problem. Consequence for anyone using it: its *diagnoses* are sound, its
**"today the app does X" claims are not evidence** — verify against the file before acting. That is
also why two findings had to be retro-marked "already true before the audit landed".

**② Six items in the audit never became roadmap items at all** — they are reinstated below as
`R24-CHARTS-GRAMMAR`, `R24-REPORTS-BY-MOMENT`, `R24-TOOLS-SPLIT`, `R24-BASELINE`, `R24-KEYS` and
`R24-PERF-BUDGET`. The largest of those is `R24-BASELINE`: the audit's phase 0 said *instrument
before you redesign*, listed six metrics with targets, and none of it was carried. **R26 replaced the
entire shell and nothing in the stack can say whether it worked.**

**③ One finding was deliberately reversed and never recorded as one.** The audit prescribed a
*persona-scoped* rail; `spine.ts` ships rooms "identical for every role" on purpose. That may well be
the better call — but it is an unrecorded reversal of the source document, unlike ROOM-NAMING which
is recorded. Filed under Decisions below.

**Verified status of all 18 findings** — `✅` closed · `🟡` partial · `❌` open · `⚠️` reversed:

| # | finding | item | status, with the evidence |
|---|---|---|---|
| 01 | catalog is the wrong front door | R24-SPINE | ✅ rooms are primary nav (`shell/roomTabs.ts`), default since v0.3.715 |
| 02 | pillars are a mode switch | R24-SPINE | ✅ workspaces demoted to weighting, `shell/spine.ts` `WORKSPACE_ROOM` |
| 03 | roles gate the UI invisibly | R24-ROLE-EXPLAIN | ✅ v0.3.685 |
| 04 | long jobs, foreground UI | R24-JOB-TRAY | ✅ **shipped; this row was stale** — `apps/web/src/ui/jobTray.ts` is 373 lines, mounted at `apps/web/src/main.ts:2052`, 28 tests. The ❌ survived its own implementation |
| 05 | analyses are modals → no history | R24-RUNS-INBOX | ✅ **history v0.3.947 · routing this PR** — clash / IDS / cost / envelope energy enqueue as jobs; the inbox lists them. Direct GET/POST routes remain for scripts |
| 06 | the single-GUID advantage is invisible | R24-ELEMENT-CARD | ✅ **SHIPPED v0.3.1000** — `apps/web/src/ui/elementCard.ts` on the viewer, cost trace, and every register record that names a GUID (`apps/web/src/portal/register/tiedElements.ts`). There is no `pay_app` module (SOV line is the G703 row) and no COBie worksheet UI (asset register is the in-app Component row) |
| 07 | onboarding teaches the chrome | FIRST-RUN | 🟡 improved v0.3.777; still not the lot → building → deal chain |
| 08 | persona picker only relabels | *(none)* | ⚠️ reversed on purpose — see Decisions |
| 09 | tools panel mixes verbs with analyses | *(none)* | ✅ **v0.3.848** — `R24-TOOLS-SPLIT` cut the 1087-line `qa` section in two; Analyse is its own rail item |
| 10 | finance numbers have no provenance | R24-TRACE-UI | 🟡 v0.3.775 shipped trace for *cost coverage*; the proforma chain (IRR ← NOI ← rent roll ← area ← GUID) — the audit's actual demo — is not built |
| 11 | density | R24-DENSITY | ✅ **SHIPPED v0.3.996** — three steps on registers (`DENSITY_ROW_PX`), not dashboards only |
| 12 | mobile is a bottom sheet in a desktop IA | R24-FIELD-MODE | ◧ **v0.3.1001–1008** — mode, 56 px, strip, dictation, capture landing, **room tabs hidden in field mode**. Portal home rewrite still Lane A |
| 13 | search is scoped to modules | R24-CMDK-VERBS | ✅ **v0.3.946** — verbs, elements, reports and an assistant fallback; `apps/web/src/ui/paletteProviders.ts`. Fixed a second defect on the way: async hits were `concat`ed onto an already-grouped list, so a record landed under a **second** RECORDS heading below Modules |
| 14 | empty states | R24-EMPTY-GUIDE | ✅ **verified done 2026-08-14** — the "24 lines, 'no project' only" reading is stale by a wide margin. `apps/web/src/ui/empty.ts` is 156 lines and R36-EMPTY-STATE shipped the hard part: a register with no rows distinguishes **none / filtered / failed**, because those send a reader to three different places and rendering them identically was the defect. Plus acronym-safe nouns ("No rfis yet" was the bug), `textContent` throughout since the name and the error body are untrusted, and `data-empty` so a test can assert WHICH kind was decided. Curated hints in `apps/web/src/ui/emptyGuide.ts` (157 lines), wired at two `register.ts` call sites, covered by `apps/web/src/ui/empty.test.ts` and `apps/web/src/ui/emptyGuide.test.ts` |
| 15 | charts have no grammar | *(none)* | ✅ **SHIPPED v0.3.1002** — no-data, ticks/legend/currency, then series vs status (`SERIES_PALETTE` / `STATUS_*` in `apps/web/src/ui/charts.ts`) |
| 16 | Report Center is a list of nouns | *(none)* | ❌ dropped → `R24-REPORTS-BY-MOMENT` |
| 17 | three vocabularies collide | R24-TERMS | 🟡 **storey/floor settled v0.3.945** — `storey` was already canonical in the API, QUERY-DSL and both table headers; three chrome strings disagreed, one of them with its own tooltip. Gated by `apps/web/src/shell/storeyVocabulary.test.ts`, which permits *gross floor area* and *floor plan*. The element/component and estimate/budget/cost pairs are NOT settled and are a user decision, not a cleanup |
| 18 | site promises a lifecycle, app opens on a shell | *(none)* | 🟡 R26-VITALS (v0.3.773) is arguably a **better** answer than the audit's lifecycle strip — treat as closed |

**External corroboration** (13-platform UI scan, 2026-07-29). One major construction-management
platform's design system evaluates office and field as **separate** UX, not one responsive layout —
independent support for #12. Among model-checking tools, the ones that lead on IFC do so by making
rulesets and checks **durable first-class objects**, and the leading common-data-environment answer
to breadth is **saved, re-runnable, shareable** searches — both are the same shape as
`R24-RUNS-INBOX`, and it is the most externally validated item in the ring. One 2026 drawing-layout
tray redesign drew open backlash ("bulky, less legible and inefficient", broken shortcuts) — density
is a **regression risk**, not a taste call, which is why `R24-DENSITY` ships as a user switch and why
`R24-KEYS` is not optional. A major PDF review tool's most recent release deliberately did **not**
restyle and invested in customizable profiles instead. And two conclusions worth keeping: **no
incumbent ships a command palette as a primary entry point** — a real opening, and a warning that ⌘K
must be *taught*, not just bound — and **none of them can trace a number to a GlobalId**. That is the
moat and it is still uncashed.

---

### Sprint 1 — instrument, then decide *(the audit's phase 0, never built)*

Everything after this sprint is a claim about adoption. Nothing in the stack can currently confirm or
refute one, so this goes first even though it is the least visible.


### Sprint 2 — cash the moat *(the differentiation no competitor can copy)*

- ~~**R24-TRACE-UI ②**~~ *(**L, and BACKEND** — re-scoped 2026-07-29 after a premise check)* — make the
  **proforma emit its own derivation**: each headline figure carrying its inputs and a
  **model-derived / overridden / market-assumption** tag, terminating in a GlobalId where one exists.
  `proforma/solve.py` · `returns.py` · `operations.py`. The UI half is genuinely small once the data
  exists, and the v0.3.791 element card is already the right terminus.

  **This entry read as a ready-to-build M and was not.** It said *"`traceability.py` already walks
  model→cost→GL by GlobalId; this is the surface for it"* — true of **cost**, false of the proforma.
  Measured on `e653473b`: `traceability.py` is cost-only (its docstring scopes it to `element_costs`
  / `summary`; **0** mentions of proforma/IRR/NOI/rent), and `proforma/*.py` contains **zero**
  `GlobalId` / `guid` references, so no figure links to a model element at any layer. The lone
  `"basis"` string in `approval_risk.py` names which population was averaged — not a chain.

  Building the UI first would have meant **inventing provenance in the client**: a trace that looks
  like it walks to a GlobalId while actually asserting one. That is the fabrication shape this repo
  has spent a day naming, and it would have been shipped as the on-stage demo. Whoever picked up
  Sprint 2 would have started in the client and found nothing to render.
### Sprint 3 — the front door earns its keyboard


### Sprint 4 — field, and the long tail

- ◧ **R24-FIELD-MODE** *(L — **① v0.3.1001 · ② v0.3.1004 · ③ v0.3.1006 · ④ v0.3.1008**)* — a mode, not a breakpoint.
  `?field=1` / `aec-field-mode`, 56 px targets and ~7:1 on field chrome only (`apps/web/src/field/fieldMode.css`),
  always-visible sync strip, dictation when the browser has SpeechRecognition (`apps/web/src/field/dictate.ts`).
  Slice ②: field-mode CSS beats the FAB's inline 52 px. Slice ③: with a project open, field mode
  **lands on the capture sheet** (`shouldOpenCaptureHome`). Slice ④: `#workspaces` is hidden while
  the mode is on, so the seven-room tablist is not field home. Replacing the portal shell is Lane A.
- 🟡 **R24-REPORTS-BY-MOMENT** — **grouping SHIPPED v0.3.785; assemble SHIPPED v0.3.1015; scheduling still open.** The catalog was
  **56 reports under 18 group headings, six holding a single report**. Seven packages now sit above
  them — owner monthly · lender draw · IC · precon/GMP · design issue · closeout · ownership quarter —
  each stating who asks and when, collapsed by default, with every report still under its noun
  heading below. `reportMoments.test.ts` reads `reports.py` and fails the build if a package names an
  id the server no longer defines; without that, a renamed report shortens a package silently on the
  Friday it is due.
  **Still open: "scheduled and shared, not just downloaded."** Assemble is a job
  (`report_package` in `services/api/src/aec_api/jobs.py`, **Assemble** in `apps/web/src/reportCenter.ts`).
  Making it a *scheduled deliverable* — sent to a recipient on a date — still wants a delivery surface
  and SMTP. The Job row is already the record that a pack ran.
- **R24-TERMS** *(S)* — the remaining long tail (element/component and estimate/budget/cost pairs
  are a user decision; storey/floor settled v0.3.945).

**Explicitly NOT in scope: the audit's visual identity** (ink canvas `#080C12`, IBM Plex Sans/Mono,
the 24 px/192 px brand grid at 5–7%). It is the most seductive item in the document and the least
defensible right now: a full restyle with no measurement behind it, immediately after a shell
replacement that also has none. Colour *discipline* shipped and is test-enforced; colour *identity*
did not, and `style.css:20` is still a generic dark-app grey. Revisit once `R24-BASELINE` has numbers,
or settle it as a decision — do not let it ride in on the back of another item.

### Decisions this ring needs from the user

- **R24-PERSONA-SHAPE** — the audit prescribed a persona-scoped rail; `spine.ts` ships rooms identical
  for every role. Which is right for a superintendent who needs four rooms and an underwriter who
  needs one? The sibling question, **ROOM-NAMING**, was settled on professional terms at v0.3.779 —
  this one is *shape* rather than vocabulary and is still open. Settle it with a real user.
- **R24-IDENTITY** — is the visual identity in scope at all, or does the current grey stay?

### Re-audit — scoped, not a redo

The 18 diagnoses hold. But the three surfaces the audit judged hardest — the spine, the room tabs and
the vitals bar — have all been **replaced** since it was written, so its verdict on the front door
describes a door that no longer exists. Questions to hand a re-auditor verbatim: **(1)** rooms vs
personas, per the decision above; **(2)** does the vitals bar prove the one-model claim or is it six
numbers nobody can act on — it holds the most valuable strip of the window on the strength of a
prototype, unmeasured; **(3)** what is the register experience at 500 rows — every density finding in
the original was about dashboards and it never opened a table; **(4)** where does ⌘K get *taught*,
given no competitor ships one; **(5)** what are the six metrics' actual baselines; **(6)** is the
offline/field path trustworthy on one bar of signal, judged from a phone rather than a desktop.

### Working lanes — for a second agent picking this up

Four sessions are live in this repo. R24 is **`apps/web` outside `src/shell/`**. Specifically:

- **Owned elsewhere, do not edit:** `apps/web/src/shell/*` (Massing Core session). **`services/api` +
  `services/data`** carried six backend PRs; **#94 #95 #96 #97 #99 merged** on 2026-07-29 (by the
  user, not by an agent), **#98 R23-RECIPE-ARTIFACT** open, plus **#100** fixing the alert below.
  *Status stated with its method rather than its conclusion, which is the habit worth copying:*
  #94/#96/#99 API gates **PASS**; 15/15 pairwise clean **by `git merge-tree`**, which is *not* a
  merged-and-tested result and must not be read as one ([[tests-that-cannot-reach-the-failure]]).
- **How to count CodeQL alerts, because a wrong zero was reported here twice on one day.**
  ```bash
  gh api "repos/{owner}/{repo}/code-scanning/alerts?state=open&per_page=100" --paginate -q '.[].number' | wc -l
  ```
  **`--paginate` applies a `-q` filter PER PAGE and prints one result per page**, so
  `--paginate -q 'length'` emits `1\n0\n…` and anything reading the first line reports the first
  page's count as the total. Count *lines of ids*, never a per-page `length`. A bare
  `--jq 'length'` without `--paginate` is correct only while there are ≤100 alerts — it degrades
  silently past that, which is the worst moment for it to.
  **And a green CodeQL *run* is not zero alerts** — that was already in memory
  ([[codeql-monitoring]], [[ci-green-means-the-ci-job]]); the new half is that a *badly counted alerts
  query* is not zero alerts either.
- **Read the alert's own `start_line` before applying a remembered fix.** Alert #108
  (`py/stack-trace-exposure`) named `routers/prefab.py:64-67` — the `return pk.assess(...)` in the GET
  detail route. It was diagnosed here as line 87's `raise HTTPException(422, str(e))` **because that
  matched the pattern in memory**, and the memory won over the data the alert supplied. The real
  source was `prefab_kit.resolve()` returning `{"error": f"bad selector: {e}"}` — a *dict field*, not
  a raise — feeding **three** response paths (`register`, `assess`, `freeze`). Fixing the raise would
  have left two tainted and the alert open. *Recalling a known fix is what stopped the reading.*
  **Merge protocol, agreed between sessions and binding:** whoever merges pings the release lane
  first and waits for *"not mid-release"* before the first merge. The window that bites is
  **bump → tag** — a merge landing inside it yields a tag and a `package.json` that disagree, and
  nothing fails until somebody reads the update banner. Every push here is race-guarded on
  `origin/main == HEAD~1`, so the guard catches it, but do not rely on the guard alone.
  `main.ts` and `portal/portal.ts` were held through the classic-shell removal and
  **released at v0.3.779** — check `git status` before assuming either is free, since both are large
  enough that two sessions in one is a guaranteed conflict.
- **`docs/roadmap.md`, `CHANGELOG.md` and the three version files are a single lane, held by whoever
  is shipping.** This was agreed rather than assumed: the backend-PR session deliberately touches none
  of them on any branch, precisely because they are the high-conflict files. If you take a lane,
  say so — a session message costs nothing and a merge conflict in this file costs an hour.
- **The version lives in THREE files**, not the two the `ship-release` skill names: `apps/web/package.json`,
  `apps/web/src-tauri/tauri.conf.json`, **and `package-lock.json` under the `packages["apps/web"].version` key**. *Located by key, not by line: it sat at line 23 until the R41-BUNDLER-SPLIT dedupe added a root devDependency and pushed it to 24. `apps/web/src/shell/versionConsistency.test.ts` already reads it structurally, which is why the move broke nothing — a line number in prose is the part that rots.*
  `shell/versionConsistency.test.ts` fails the web suite if the lockfile disagrees.
- **The web app's three escaping layers have DISTINCT scopes.** Stated once, because assuming one
  covers another is how the gap between them gets used:

  | layer | watches | baseline |
  |---|---|---|
  | `ui/innerHtmlGuard.test.ts` | unescaped `${…}` interpolated into `.innerHTML` | ratchet at **88** |
  | `ui/hrefGuard.test.ts` | an **external field** (`info.url`, `d.html_url`, `att.fileUrl`) assigned straight to a URL attribute | **zero** |
  | `safeUrl` / `safeHref` (`ui/feedback`) | the helpers both gates point you at | — |

  **None of them sees `textContent`, and that is correct** — nothing needs to.
  * `innerHtmlGuard` red = you added an unescaped interpolation. Wrap it in `esc()` (`ui/charts`) or
    `escapeHtml()`. **Only on lines assigning to `.innerHTML`.** Never escape into `toast()`,
    `notify()`, `setStatus()` or `.textContent` — `toast` sets `textContent`, so escaping there makes
    users read `&amp;lt;` literally. Worst offenders if you are in them anyway: `proforma/proforma.ts` 16 ·
    `portal/portal.ts` 14 · `portal/panels/standards.ts` 8 · `portal/panels/analytics.ts` 6 ·
    `viewer/app.ts` 6.
  * `safeUrl` **HTML-escapes** (for interpolation into a string); `safeHref` **does not** (for
    `el.href = …`). Using `safeUrl` on a DOM property rewrites `?a=1&b=2` into `&amp;` — a broken link
    that still looks defended.
  * **Known blind spot, deliberately:** `hrefGuard` does not cover `img.src` / `audio.src` fed a
    *local variable*, because a line-local regex cannot do dataflow and a zero-baseline version of
    that flagged **eleven safe sites**. Eleven false alarms is how a check gets switched off, and then
    the real twelfth goes through. So `safeMediaUrl` in the vendored attachment plugin is doing real
    work that **no gate backs up** — keep it if that file is ever refactored.
- **Free for R24:** `apps/web/src/ui/*`, `apps/web/src/api/client.ts`, `apps/web/src/field/*`,
  `apps/web/src/reportCenter.ts`, and any new file.
- **Sequencing rule:** prefer a new self-contained module plus one small mount point over an edit
  inside a large shared file. `ui/jobTray.ts` is the template — the whole feature lands in a new file
  and the mount is three lines.
- Run the backend suite **from `services/api`** (the repo root exits 127 and reports "0 failures",
  which reads exactly like a pass). Never run `npm run build` while the suite is running — it rewrites
  `apps/web/dist`, which `test_desktop` reads.
## 🏗 R38 — DESIGN ROOM RING *(user-approved plan 2026-08-02; tool research + measured room inventory)*

**The thesis, from research and our own R29 finding: the room is not behind on features — it is
behind on the first ten minutes.** The measured inventory is deep (14 draw tools, families with
sized variants, groups/arrays, constraints, phasing, curtain walls, MEP, server-generated
plans/sections/sheets, a full markup engine, node canvas + NL authoring). What the beginner-friendly
tools prove is that a new user must see a shape respond **in the same frame** and must be able to
learn the whole app from the cursor. What the parametric tools prove is that **parameters must stay
alive after creation**. What the document-first tools prove is that the sheet is a working surface,
not an export. Three waves, one per lesson. The server recipe stays writer of record throughout; no
second renderer, no new dependency without sign-off (Manifold, Apache-2.0, is the one pre-cleared
candidate if face-CSG is ever pursued — see the R29 licence table).

### Wave 1 — the first ten minutes *(Lane E unless noted)*

**Three of Wave 1's four items shipped 2026-08-02** (v0.3.819–820; details in
[roadmap-completed.md](roadmap-completed.md)): A29-LOCAL-PREVIEW (a pending edit looks pending — the
amber marker stays over the incremental preview; failure turns it red and keeps its location),
R38-DIM-INPUT (the typed-constraint box is visible as a hint the moment a run is in progress, and
the grammar accepts imperial — 12'6 echoes back 3.81 m before the click commits), and R38-STAIR
(server recipes add_stair/add_ramp in `services/data/src/aec_data/edit_enclosure.py` — placed
exactly where drawn, riser/tread/slope compliance REPORTED by stair_geometry/ramp_geometry, never
enforced by moving the run — plus the stair and ramp draw tools, SR/RP shortcuts). **R38-PUSHPULL
shipped v0.3.821** — a single top handle on the selected element, base-anchored ghost, committed
through the pre-existing set_extrusion_depth recipe (never mesh; non-extrusions refused
server-side). **Wave 1 is complete.** Carried forward:

**R38-STAIR-LIVE shipped v0.3.822** — live riser/tread (and ramp slope) readout while dragging the
run, constants pinned by test to the server's (`apps/web/src/viewer/draft/stairLive.ts`); the
server's report stays authoritative on the authored element. Wave 1 and its follow-on are done.

- A29-PLACE-VALID ② · A29-UNDO-LOCAL ③ · A29-GUIDE-UNDERLAY ③ — as already coded in Lane E.

### Wave 2 — parameters stay alive *(Lane E + C)*

### Wave 3 — model and documents in one room *(Lane B + E)*

- ◧ **split by premise-check 2026-08-02 — un-archived 2026-08-10, the ✅ was wrong.** Only
  **R38-SYNC-SELECT** of the four children shipped; the other three are open, and archiving the
  parent took them with it — caught by `roadmapLanes.test.ts`, which names lane items with no
  entry left in the file. **A ✅ on a parent is not a claim about its children.**
  Original heading — split by premise-check 2026-08-02** — R38-SYNC-2D3D. The plans are server-generated, but
  the pipeline **discards element identity at bake time**: `drawings._bake_uncached` has
  `shape.guid` in hand and keeps only `(cls, mesh)`, so `cut_baked` emits anonymous polylines and
  `cut_baked_classed` adds back the class but never the GUID. Nothing in a plan can name what it
  draws. Hence:
- Consumes: R24-ELEMENT-CARD ② and R31-CITE-HIGHLIGHT (both already coded) as the "everything
  about this thing" surface.

**Sequence: Wave 1 before all; within a wave, listed order.** Quick wins to fold in when adjacent:
a material paint tool, orbit-around-selection.
## 🎀 R40 — OPERATOR RESEARCH RING *(7-image requirements survey, 2026-08-02; premise-checked, split across lanes)*

Source images used as a **requirements survey only** — nothing copied, no vendor names in repo docs
(standing directive). Two proposals from the same drop were **recommended against and declined**,
recorded so nobody re-proposes them: an ML training-data pipeline built from bid history (cuts
against deterministic/offline/no-silent-LLM — a strategy decision, not a task), and a BIM-interop
expansion (IFC already covers the named authoring tools; the image is a landscape, not a gap).

- **R40-RIBBON ②** *(M, Lane A/E)* — the flat glyph bar presented as tabs. Measured before accepting:
  `apps/web/src/viewer/toolbarLayout.ts` defines **27 tools in 5 groups** (look · measure · author ·
  analyse · collaborate) with `MAX_PRIMARY = 8`, so **19 live in overflow**. The five groups already
  map nearly one-to-one onto the surveyed tabs (look→View, author→Author, analyse→Analyze,
  collaborate→Share, measure folding into Analyze) — this is a **presentation of a taxonomy we
  already have**, not a re-taxonomy, which is what makes it cheap. **The constraint that outranks the
  arrangement:** `toolbarLayout.test.ts` exists because R26-TOOLBAR's audit found 25 unlabeled
  glyphs, and its tests are mostly about *nothing disappearing* and only then about the bar being
  short. A ribbon inherits that gate — `unlaidTitles()` staying empty matters more than any tab
  layout. Design question before build.
**R22-PIPELINE — scan note (the item itself is in Band 3).** No rewrite needed; a **spec reference now exists** from the same drop (portfolio
  dashboard: multi-project KPI strip, cross-project Gantt, EVM PV/EV/AC + SPI/CPI, risk heat map,
  milestone tracking, resource allocation by department, cost-by-project).
## 🔬 R41 — EXTERNAL SCAN *(27 sources, 2026-08-06; licences read from the LICENSE file, not the README)*

**Why this ring reads differently from the others.** Three of the six code repositories examined carry
a licence that **differs from what their README or badge claims**, and two of those are hard exclusions
for us specifically. The scan's most reusable output is therefore a process change rather than a
feature: **a machine-enforced licence allowlist in CI would have caught them mechanically instead of
requiring a manual read** — filed below as R41-LICENCE-GATE.

### ⛔ Excluded — do not vendor, copy, or depend on

* **Two Claude-skill repositories** (a BIM health scorecard, a spec indexer). Their READMEs say "free,
  self-hosted" and never mention licensing; the LICENSE file is a custom source-available licence whose
  second clause forbids distribution **"as part of a paid service"** — which is exactly what this
  product is. Internal use on our own models would be permitted; shipping any part is not, and the
  rulebook cannot be copied. **Two of their ideas are free to adopt**, since ideas are not
  copyrightable: an **evidence-tier ledger** grading each claim *verified / sourced / chosen* with a
  dated primary-source read log recording what was opened and **what it did not contain**; and
  **stage-aware rule severity**, where a missing field is informational at schematic design and a
  failure at fabrication.
* **A hosted AutoLISP script library** — no LICENSE, no repository, no named author, so all rights are
  reserved by default. **An exclusion by absence, which is easier to misread as permissive than a bad
  licence is.** Its twelve command names remain a field-validated requirements checklist for the R27
  drawing-is-data ring: delete duplicates, fillet-to-zero to close corners, straighten near-axis
  linework, split lines at intersections, and select by length, orientation, overlap or layer.
  Behaviour from a published description is fine; implementation is not.
* **A browser-local IFC viewer and clash tool licensed SSPL** — source-available, not open source, and
  aggressively copyleft for hosted services. Do not read its source with intent to copy. Commercially
  it is worth knowing that it is free and needs no signup, which makes it real pressure on a *viewer*
  wedge and none at all on authoring, cost, scheduling or finance; its own comparison page concedes it
  has no coordination workflow, **which we lead on**.
* **A closed-access Automation in Construction paper** on a joint-embedding predictive architecture for
  3D BIM geometry (DOI 10.1016/j.autcon.2026.107169, vol 191, art 107169). Title, authors and DOI
  confirmed; **the abstract is deposited nowhere public and was deliberately not inferred.** A
  technique to watch rather than act on: no released weights or code were found, and we have no ML
  training pipeline. Re-check whether the authors later publish code.

### Capability items

- ~~**R41-MODEL-ALIGN**~~ *(**the remaining half is Lane D, not Lane E, and bigger than M** — the defect half was Lane E and is DONE, see below. What is left is the OBB feature, and it lives in `services/data/src/aec_data/` (Lane D · Geometry & drawings) with a route in Lane G and a per-model transform that needs an Alembic revision — `ProjectModel` has no transform column today. **Lanes are assigned by directory**, so an agent taking this under a Lane E label would write straight into another lane's files.)* — **align a federated model that arrived with wrong, missing or
  unit-mismatched georeferencing, without touching the source file.** This is the daily reality of GC
  federation and is *not* the same problem as our standing set-origin note. Two techniques, both
  reimplement-from-description — the reference source carries an object-code-only header despite an MIT
  root, so **do not paste it**:
  **(a) a yaw-only oriented bounding box** fitted to drawn geometry
  *[PREMISE-CHECKED 2026-08-06: HOLDS — nothing aligns anything today — but (a) is substantially
  cheaper than written. `georef.py` exposes one function, `georeferencing(model)`, which **reads** and
  returns; there is no yaw fitting, no unit-mismatch handling and no alignment anywhere in `services/`.
  What lowers the cost: **shapely is already a declared dependency** (`services/data/requirements.txt`,
  `>=2.1.2`, pulled in for trimesh planar paths) and `drawings.py` already uses `MultiPoint(...)
  .convex_hull`. Shapely ships `minimum_rotated_rectangle`, verified in the pinned version — so the
  hull-and-fit half is a call, not an implementation, and needs no new dependency and no pasted
  reference code. **What must still be written by hand is the part the entry says is valuable**: the
  ≥20% area-saving acceptance threshold that buys a *wall-parallel* rectangle rather than a *smallest*
  one. The geometry is small; the acceptance rule and the "never touch the source file" guarantee are
  the work.]* (2D convex hull of the footprint,
  minimum-area rectangle), accepted **only when it saves at least 20% area**. The reasoning is the
  valuable part: a true minimum-area rectangle sat **37° off a building's own walls to buy 14%**, which
  reads as broken. The threshold buys *wall-parallel* rather than *smallest*. Their measured gap was a
  54 × 78 m true extent against a 126 × 127 m axis-aligned box.
  **(b) pick-based move, rotate and scale** from two point pairs.
  **Check first whether the AABB-versus-OBB gap already affects our section box, zoom-to-model and any
  bounding-box UI** — if it does, that is a defect rather than a feature.

  **CHECKED 2026-08-06, and the answer is BOTH — but the live defect is not the one this entry
  hypothesised.** Two sites build a scene-wide `Box3` and include the **2000 × 2000** presentation
  ground plane `world.ts` adds (`aec-shadow-ground`):
  `apps/web/src/viewer/measureSection.ts` and `apps/web/src/viewer/envTools.ts`. Neither excludes it;
  `world.ts` does, with the comment *"the shadow-catching ground is 1 km across and would swallow the
  fit"*. **These are the fourth and fifth instances of the defect `apps/web/src/viewer/modelBounds.ts`
  was written to fix**, whose docstring already records that the fact was "encoded correctly twice and
  missed once".

  Measured against a 54 × 78 m building rotated 37° plus the real plane:

  | | |
  |---|---|
  | AABB of the model alone | **90.1 × 94.8 m** — the genuine AABB-vs-OBB gap, ~2× the true area |
  | AABB including the ground plane | **2000 × 2000 m** — what those two sites actually measure |
  | section-box clip half-extent | **700 × 700 m** about the origin → **the whole building is inside it, so the section box clips nothing** |
  | storey grid size | **2200 m** where it should be 104 m — **21× too large** |

  With presentation mode **off** both are correct, which is exactly why it hides and why no test caught
  it: it misbehaves in one render mode only.

  **So this entry splits.** The two ground-plane sites are a **defect** for Lane E to fix now, and the
  fix already exists — `planBoundsFromModels` in `modelBounds.ts` is an allowlist precisely so every
  future non-model mesh is excluded by construction rather than by name. Both sites should call it
  instead of hand-rolling a traverse. The OBB work then remains a real feature at its stated size:
  fitting an oriented box on top of these two sites would compute a beautiful oriented box over a 2 km
  ground plane.

  **The defect half is DONE, and it took two passes — there were six sites, not five.** Sites 4 and 5
  were fixed on 2026-08-06 and both call `modelBox3` today. **Site 6 was `fitToModels` — the
  zoom-to-model this entry names in its own instruction to "check the section box, zoom-to-model and
  any bounding-box UI".** The pass that acted on that instruction fixed the two it found and left the
  third, so `modelBounds.ts` shipped with its docstring enumerating five sites while a sixth caller
  sat in `app.ts` still walking the scene for `isMesh || isPoints`. With presentation mode on the fit
  framed a ~1.4 km sphere against a ~65 m building: **the model drew at about 5% of the view.**
  Fixed v0.3.1062, and the source gate in `apps/web/src/viewer/modelBounds.test.ts` now covers
  `app.ts` alongside the other two, mutation-checked by restoring the walk and watching it fail.

  *Note for whoever takes the OBB feature: the fit passes `referenceModels` explicitly, because
  `modelBox3`'s population is loaded fragments models and the walk it replaced included `isPoints` on
  purpose — survey scans and reference overlays. Dropping them would trade a wrong fit for an
  incomplete one, which is why that has its own twin test.* The OBB work itself is untouched.
### Gate and process items

### Reclassified, and worth acting on separately

Two sources are **not competitors**: a construction-operations consultancy, and a BIM services firm
delivering LOD 400/500 models and 5D quantity take-off on data-centre and hospital projects. **The
latter is a customer and channel profile rather than a threat** — a services firm delivering by hand
exactly what this platform automates, with a data-centre concentration matching the hotel and
data-centre gap already recorded in the proforma asset-class scope. One further source is live-events
design and is off-mission entirely. One hardware repository is a bench-top protocol tool with no
telemetry, device management or building-automation path, and is off-mission despite a superficially
plausible IoT reading — the connection was checked and deliberately not manufactured.

*Vendor names and commercial detail are deliberately absent from this file — they live in
`docs/internal/`, because `services/api/test_no_comparative_names.py` gates the public docs.*
## 🔧 R39 — DEPLOYMENT-TRUTH RING *(external engineering audit 2026-08-02, premise-checked item by item)*

**Three items added 2026-08-20 from the PR-reconciliation pass** — each is a control that reads
stronger than it is, which is this ring's whole theme:

- **R39-TSC-CACHE** *(XS, any lane)* — **a local typecheck once passed where CI's identical command
  failed, and the cause is not known.** On v0.3.1020 two type imports orphaned by SCALE-SEAM ⑭ passed
  `npm run typecheck` locally and failed CI with TS6196. That divergence is real and recorded.
  **The explanation first written here was wrong and is retracted**: it blamed
  `"incremental": true` and its cached `tsBuildInfoFile` for suppressing unused-symbol diagnostics.
  Re-tested with a deliberately unused import against a warm cache, plain `tsc --noEmit` exits 2 with
  TS6133 every time — editing a file invalidates its own cache entry, which is precisely the case in
  question. The original "mutation check" supporting the claim had run on a tree where the mutation
  failed to apply, so both arms passed and the agreement was read as confirmation.
  **Do NOT add `--incremental false` or a cache-clearing `pretypecheck` on the strength of this
  item** — that was the proposed fix, and it is cost against a benefit nobody has demonstrated.
  What is genuinely wanted: catch the next occurrence with the *state* preserved (keep the failing
  tree, run both locally and in CI on the same commit) so the mechanism can be identified rather than
  guessed. Until then this is an observation, not a defect with a known fix.

**Why this ring exists.** An external audit of the deployment surface found that several controls are
weaker than they read: a throttle that counts per process behind four workers, an upload cap that only
exists if requests happen to arrive through the bundled proxy. The shape is familiar — R35's theme of
"a lock the backend ignores" applied to the ops layer. **Already landed from the same audit** (do not
re-open): the converter build stage moved to the supported Node LTS with a pinned digest
(`services/api/Dockerfile`), a Content-Security-Policy with a no-inline-script gate
(`apps/web/nginx.conf` + `apps/web/src/deploy/nginx.test.ts`), the multi-worker sidecar-lock boot
refusal (`services/api/src/aec_api/main.py`), and full-history checkout for the secret-scan job.


- 🟡 **R39-DECOMP-VIEWER ③** *(L, Lane E — **seven slices shipped; `app.ts` is 5,160 → 3,311, a 36%
  cut. The `builders` map is entirely gone.** The paragraph below saying the extraction "is NOT begun"
  was true on 2026-08-06 and stayed on the page until 2026-08-17, through six shipped slices — a
  roadmap entry describing work as un-started while the work is being done is worse than a missing
  entry, because it sends the next reader to re-derive a plan that was already executed. Kept only
  because the *reason* it gives is still the live constraint.)* — `apps/web/src/viewer/app.ts`
  is the last of the three god-files still standing (client.ts was split by SCALE-SEAM, portal.ts is
  REL-4).

  **Shipped:** ① exports (51) · ② clash/QA (851) · ③ analyse (238) · ④ authoring (91) ·
  ⑤ project-browser panel (216) · ⑥ `loadProjectModel` (37) · ⑦ **drawings & sheets (142, v0.3.978)** ·
  ⑨ **fabrication detail (65)** · ⑩ **MEP / fire / life safety (169)** — both v0.3.981 ·
  ⑫ **envelope & free-form geometry (75, v0.3.982)** · ⑬ **model federation & version compare
  (88, v0.3.1043)**. `app.ts` 5,160 → **2,944**, a **43% cut**.
  Each ratcheted `services/api/test_file_sizes.py` down, never reset. `services/api/test_file_sizes.py`
  carries the per-slice history; that comment, not this list, is the record.

  **"never reset" was false for two days, and the way it was found is the transferable part.** Slices
  ⑭⑮⑯ walked the pin 2_865 → 2_757 → 2_630 → 2_571 on 2026-08-27, and a REL-4 portal commit to the
  same shared file later that afternoon carried the pre-⑭ line back in — value *and* comment trail, so
  it read as deliberate rather than as the lost hunk it was. Hazard 4 in the directions, exactly:
  staging by name takes every change in that file. Nothing could go red, because the only assertion
  was `measured > cap` and a pin that moves UP is a *wider* bound. The three slices' friction was spent
  silently: 295 lines of headroom on a file whose whole point is having none.
  **What found it was this row's own instruction** — the prioritised-view cell says to re-derive
  `wc -l apps/web/src/viewer/app.ts` against the pin before quoting either, and the two numbers
  disagreed by 295. Restored to 2_570 (the file's exact size; ⑯ set 2_571 against a file that already
  measured 2,570), and `MAX_SLACK` in `services/api/test_file_sizes.py` now fails the build on a pin
  more than 25 lines above its file. Mutation-checked at the boundary (25 passes, 26 fails) and
  against the real event (2_865 fails, naming the file and the 295). **A ratchet that can be silently
  unwound is a rearrangement one commit later**, which is the same sentence that file already carried
  about extractions without ratchets.

  **The first draft of this paragraph said that gate makes the prose rule *"only ever revised DOWN"*
  a check. It does not, and the overclaim is the more useful half of the record.** MAX_SLACK asserts
  *a pin must not sit far above its file* — a raise that grows the file to match passes with slack 0,
  and so would this very incident if the stale copy had carried `app.ts` back to 2,865 lines too.
  Down-only is a claim about **history** and cannot be decided from a working tree, which is the price
  of a check that needs no base ref. *A gate whose scope is narrower than its claim* is a defect
  `services/api/test_file_sizes.py` names in its own header, and writing one into the entry announcing
  the fix is how the shape survives — the residual, and a known merge-time false positive, are both
  stated next to the constant rather than here.

  **⑦ is the one that proved the accessor rule, which ①–⑥ only prepared for.** `exportsSection.ts`
  says outright that it "touches neither" mutable capture and that its deps type is *shaped so the
  next one can*. The drawings group is that next one: `activeStorey` and `activeStoreyZ` are `let`,
  reassigned by the level selector. Passing either by value compiles clean and freezes the level at
  panel-build time — which is before any level exists — so every plan, DXF and sheet would silently
  render the whole building instead of the level on screen. Threading them as accessors then made
  `tsc` reject `if (d.activeStorey()) q.set(…, d.activeStorey())`, because two calls cannot narrow
  where one `let` did: the compiler asking the right question, since two calls genuinely can differ.

  **⑦ also broke a gate, and that is the transferable part.** `sheetSpecs.test.ts` asserted against
  `app.ts` that `placeBtn` is built *and* appended — a gate written because that button nearly shipped
  constructed-and-unreachable. Moving the code moved the gate's subject, and it failed with its own
  message: *"the rail moved and this gate is now blind."* **An extraction is exactly the event that
  invalidates a gate's address.** Re-pointing it at the new file alone would have left it weaker than
  before, because the seam adds a link that can fail silently — build the button, forget to *return*
  it. It now follows all three hops (built → returned → appended) and each is mutation-checked.

  **⑨ is the slice that finally threads `selectedGuid`**, the capture this entry named first and the
  one with the worst failure mode. Every tool in the fabrication group is selection-gated, so a
  collapsed accessor would not break them loudly — it would make all five permanently inert behind a
  polite *"select an element first"*, which is exactly the shape `qaSection.ts` shipped once already.
  Eight reads, no local binding; `accessorNotCollapsed.test.ts` mutation-checked against the new file.

  **`tsc` earned its keep three times on this slice**, which is the argument for the whole recipe:
  it rejected a dep signature that quietly narrowed `authorAndReload` to `Promise<void>` (dropping the
  `{applied, refused}` verdict, so a future caller could read a REFUSED edit as a success); it
  rejected the accessor being called twice where narrowing was needed; and it rejected returning an
  **array**, because under `noUncheckedIndexedAccess` a destructured element is `T | undefined` —
  a named interface is the only shape that carries non-optional types across the seam.

  **⑩ threads `lastPoint`, the last of the two named mutable captures** — and it is the most volatile
  state on any of these seams. `selectedGuid` changes when you pick an element; `lastPoint` is
  rewritten on *every click in the 3D view*, and five of the six tools place geometry at it.

  **⑩ is also the slice where the recipe's own weak point showed.** The free-variable list was
  hand-written, and it found **12 of 17** captures — `askText`, `layerMgr`, `loadProjectModel`,
  `reloadModelPins` and `waitForPublish` were all missed. Worse, the one dep whose type was *guessed*
  (`layerMgr` as `{ rebuild(): void }`) compiled until a call site reached for `isolateGuids`.
  **Guessing a dep's type is the same error as guessing its name.** The fix is procedural: write the
  module first, let `tsc` enumerate the missing names, and thread what it reports — the compiler is a
  complete enumerator and a hand-written list never is. Doing that *before* splicing also keeps the
  errors attributable to the new file rather than mixed into `app.ts`.

  `tsc` also rejected narrowing `loadProjectModel` to `Promise<void>` — the real return is
  `Promise<boolean>`, and the boolean is *whether the re-tessellation succeeded*. Same defect class as
  the `authorAndReload` narrowing in ⑨: a dep type that discards a verdict lets a caller read failure
  as success.

  **⑫ took the envelope group and settled where this recipe stops.** Two findings, both from
  checking rather than assuming:

  - **The claim above — "neither needs a renderer" — was wrong, and it was mine.** It was written one
    release earlier without checking. **The annotation group is not renderer-free**: it adds and
    removes objects on the live `viewer.world.scene.three`, raycasts via `screenToGround`, and
    **assigns** to `annotGuide` / `guideWired`, which are `let` in `app.ts`. Reading a mutable capture
    through an accessor is cheap; *writing* one across a seam needs a setter pair, and the module
    would still need a WebGL context — the exact untestability these extractions exist to escape.
    **So the renderer-free seam ends at ⑫.** What remains needs a different technique: move the scene
    state into the module and let it own its objects, rather than reaching back through a seam. That
    is a bigger change than a lift and should be its own item, not a slice.
  - **Extraction boundaries follow meaning, not line numbers.** ⑫ is two *non-contiguous* ranges: the
    sandboxed IFC-code runner sits between the curtain wall and the slope/mesh pair and stays in
    `app.ts`, being a different concern with a different risk profile. Folding it in for one tidy cut
    would trade cohesion for convenience. Comments move with the code they describe — the first cut
    mismatched them and produced a module documenting an "Advanced" toggle it did not contain.

  **The unwired typecheck is what made both cheap.** Writing the module, leaving it imported by
  nothing, and running `tsc` listed `viewer`, `screenToGround`, `annotGuide`, `guideWired` and four
  more in a single pass — before a line of `app.ts` was touched, and with nothing to revert.

  **⑬ found one more renderer-free group inside what ⑫ had written off.** ⑫'s sentence "the
  renderer-free seam ends at ⑫" was true of the *annotation* group it was describing and too broad as
  written: the federation group measured **zero** `viewer.world` / `THREE` / `screenToGround` touches
  across 95 lines, reaching 3D only through `layerMgr` — a live object ⑨–⑫ already hand over whole.
  Measuring each candidate group separately, rather than trusting the summary sentence, is what found
  it. `layerMgr` is imported as `LayerManager` and not guessed, which is ⑩'s lesson applied.

  **Remaining:** ~550 lines in `buildToolsPanel`, of which the annotation group (~120) is the
  renderer-coupled part described above and needs its own item. The rest is the working-origin block
  (one renderer touch), the content/family library, and the rail assembly itself, which is wiring —
  the thing this file is *for*.

  **⚠️ The recipe as written does not apply, and this is the finding that matters more than the
  split.** It says *"the suite as the parity gate"*. **Nothing in the suite imports
  `apps/web/src/viewer/app.ts` — it has zero test coverage.** A full suite run after moving 871 lines
  of it would be green whether or not the move broke the viewer, because the suite never touches the
  file. SCALE-SEAM was safe for a different reason than "we ran the tests": `client.ts` had
  `apps/web/src/api/surface.test.ts` — *"the API client's public surface, pinned"* — asserting every
  method still existed after each cut. **There is no viewer equivalent and there cannot easily be
  one**, because `createViewerApp` needs a WebGL context and a Fragments worker, which is exactly why
  the file has no tests in the first place. *Do not read a green suite as parity here.*

  **What can serve as a gate instead, and it is not nothing:** make every extracted dependency an
  **explicit typed parameter**, so a capture you fail to thread is a **compile error**. `tsc` then
  gates the move. The one failure class it cannot see is a **stale closure** — and that is removed by
  construction if mutable state is passed as an **accessor** rather than a value. Which matters here:
  `projectId` is `const` (safe by value) but **`selectedGuid` and `lastPoint` are `let`**, so passing
  them by value would compile cleanly and silently freeze whatever they held at panel-build time.

  **The seams, measured 2026-08-06** (`app.ts` = 5,160 lines; pinned in `services/api/test_file_sizes.py`
  at that number *before* any cut, so the extraction has to beat the unimproved figure):

  | block | lines | size | closure captures |
  |---|---|---|---|
  | `buildToolsPanel()` | 1769–4840 | **3,071 (60% of the file)** | — |
  | ├ `builders` map | 3542–4798 | 1,257 | ~16 |
  | │ ├ `qa` | 3594–4464 | **871** | ~12 |
  | │ ├ `analyse` | 4465–4704 | 240 | ~14 |
  | │ ├ `authoring` | 4705–4798 | 94 | ~5 |
  | │ └ `exports` | 3543–3593 | 51 | ~5 |
  | `buildPanels()` | 1385–1536 | 152 | — |

  **The seam is cleaner than the capture counts suggest**, and that is the useful part: the builders
  compose two helpers — `section(key, title, opts)` and `toolBtn2(…)` — that are themselves closures
  declared *inside* `buildToolsPanel`. They can be handed over as functions, carrying their own
  state, instead of their state being re-plumbed. So a builder extracts as
  `buildQaSection({ section, toolBtn2, api, … })`.

  **The absence is self-reinforcing, and it decides the order.** This file has no tests *because* it
  needs a WebGL context and a Fragments worker — and it is risky to split *for the same reason*. The
  thing that makes coverage hard is the thing that makes change dangerous, and every year of that
  makes the next split harder. So the order is not "smallest first" for its own sake: **extract the
  parts that do NOT need a renderer first, precisely so they become testable.** A builder that only
  composes `section()` and `toolBtn2()` and calls the API is pure DOM assembly — once it is a module
  taking explicit parameters, it can be unit-tested for the first time, and the next extraction has
  something to lean on that this one did not.

  **Start with `exports`** (51 lines, 5 captures) — the cheapest place to prove the recipe, and no
  renderer in it. Then `qa`: 871 lines, one of the four independent builders, and R24-TOOLS-SPLIT
  already gave it internal structure.

**Parked from the same audit:** brotli — the build already emits `.br` siblings and the stock
nginx image cannot serve them; switching base images is a dependency decision for the user.
Web-vitals telemetry via a third-party package — same reason, new dependency.
## 🎚 UX-POLISH — interaction-craft ring (remainder beyond the NOW sprint)

**Audit 2026-07-25 (live, against the running stack).** Measured rather than opined: 170 visible
controls, **0 unlabelled**; **0 console errors**; **20/20** first-class Design destinations render real
content (the "Design tab is blank" report was a measurement error on my side, not a defect — `innerText`
returns empty for anything not laid out, and clicking rebuilds the nav, detaching the node being
measured). Two density defects were real and are **fixed in v0.3.677**: `Build` held 13 entries of
which 7 were project accounting, and `Model & standards` held 14 mixing project rules with model
findings. Split into Build/Money and Model & standards/Analyse & check — **max group 14 → 7**, nothing
removed. Remaining, in priority order:

- **UX-3 library depth** — thumbnails · drag-to-place · pick-host→auto-build · appendable IFC
  libraries · CC0 seed/H1. **UX-4** one-shell layout (a11y/mobile pass).
## 🏔 BIG-TICKET — multi-release initiatives (open ONE track; slice + reassess)

- **SPRINT C — FIELD-PWA** *(L, frontend)* — offline-first mobile PWA: service-worker sheet sync, auto
  slip-sheeting, hyperlinked callouts. *Ships build/typecheck-verified under the preview-stall caveat.*
- **PHOTO-PIN** *(L)* — photo/360 pinning to plan locations + timeline compare.
- **CMMS-OPS** *(L)* — preventive-maintenance plans + work orders on the COBie assets (ASSET-REG
  shipped the first slice).
- **A2 RAG index** *(M)* — an offline index over the ifcopenshell / IFC docs for the authoring
  assistant.
- **SITE-1 remaining** *(S–M)* — parcel overlays *(terrain DEM auto-fetch is network-dependent →
  flagged, offline-degrading)*.

### Corroboration — "machine-interpretable AEC" *(read 2026-07-30, no new items)*

An industry essay on making AEC formats legible to software. Reviewed for gaps; **it names almost
nothing we lack**, which is worth recording so it is not re-read as a source of work.

Its central line is one we arrived at independently three hours earlier: **visual plausibility is not
physical validity.** That is precisely R31-SCHEMA-DIAG's finding — a model that renders correctly,
passes IDS rule-compliance, and is structurally invalid IFC. Its other architectural claims map onto
things already built or already scoped: route deterministic questions to specialist tools rather than a
model (`query_dsl` is the deterministic selector; the AI command bar goes through validators and
recipes), externalise implicit structure as a graph (`docgraph.py`, `graph.py`, W9-4), preserve
provenance for verification (**R24-TRACE-UI ②**, `COST-DB` vintage, the `derived / declared / unlinked /
unavailable` tagging), constraint systems around generation (**R23-CONSTRAINTS**), and accumulate
ground truth across completed projects (`COST-DB`, vendor memory).

Its observation that there is *no canonical way to organise a building model* is the problem the room
spine, the discipline tree and `classification.py` exist to answer — and, per the user, the document
taxonomy should be derived from those same rooms rather than invented again.

**One external measurement worth keeping**, because it puts a number on an item we already hold:
current models score **40–55% on object-counting from drawing sets**, with symbols and linework the
weakest part. That is direct corroboration of **R23-SYMBOL-COUNT** (Lane B; **SHIPPED v0.3.1011**)
and a reason it was higher-value than its size suggested — it is the measurable floor under every
takeoff claim.

The framing worth adopting even though it is not a feature: **reduce verification cost, not just
production cost.** Several items already do this without saying so; it is the sharper way to argue for
them.
## 🔭 R31 — EXTERNAL SCAN (15 sources, 2026-07-30)

Fifteen sources reviewed: five open-source repos, five commercial products, two engineering-practice
articles, one capital-allocation essay, one curated finance list, one profile. **Most describe things we
already have** — that is the honest headline, and the rejected list below is the more useful half of this
scan, because it stops the exercise being re-run.

**One genuinely new build item, one strong corroboration, three gap-checks.**


- ~~**R31-K1-PACK**~~ *(was S/M)* — **the one genuine remainder of R31-SYNDICATION-TAIL.** `capital.py:90`
  already states the boundary in the statement PDF itself: *"…is informational and not a tax document;
  K-1s are issued separately."* That sentence is the spec. Everything a K-1 pack needs upstream — per
  investor contributions, distributions, unreturned capital, class rollup — already exists and is
  reached; what is missing is the allocation and the document. Well-bounded precisely because the
  boundary was written down rather than left implied.

**R31-CITE-HIGHLIGHT — scan note; the live entry is the Band 2 one.** *(re-headed 2026-08-05 — **this heading contradicted its own body**, and
  the live entry is the Band 2 one)* — it read *"S — premise HOLDS, and it is far cheaper than
  written"* while the ⚠️ CORRECTION further down this same entry establishes that the viewer half is
  **not** available and needs a decision about the vendored kernel repo. A reader taking the ⭐ and
  the "S" at face value — which is what a starred size is *for* — would never reach the paragraph
  that withdraws them.

  The two entries found **different, independent blockers, and both are real**: this one found the
  highlight function is module-private inside vendored code, and Band 2 found the `doc_id` resolves
  to no openable document. Neither alone is the whole story, which is why this is folded in rather
  than deleted. — **checked 2026-07-31.** Confirmed: we cite document and page and do **not**
  highlight the passage.
  `aiassist.ts:334` renders `"Source: p.12"` as **inert text** — not a link, and nothing calls the
  viewer. Citing a 40-page PDF and citing a paragraph are different products.

  ✅ **HALF SHIPPED 2026-07-31 — the data half is done.** `doc_text.answer()` now carries `doc_id` into
  every citation, and `rfi_qa.py` prefers it over the display name and passes the snippet as `span`.
  Pinned end-to-end: `test_doc_text` asserts every citation carries a `doc_id` **and that the id
  resolves against the catalog** — an id matching nothing is as dead as a name. Mutation-checked.

  The dropped field was the real blocker and is worth remembering as a shape: `search()` always
  produced `doc_id`, `answer()` rebuilt the citation list without it, and **both functions read
  correctly on their own.** The defect lived in the seam.

  ⚠️ **CORRECTION to this entry's own cost estimate — the viewer side is NOT as available as recorded.**
  It was written here (from the gap-check) that `find(page, query, limit)` and `flash(v, page, box)`
  were callable. Checked against the file: `vendor/massingpdf/plugins/search.ts` exports only
  **`findInWords`** and **`searchPlugin`**. `flash` exists — at line 279, drawing the rect and scrolling
  to centre exactly as described — but it is **module-private**, invoked only from a click handler on a
  search-result row (line 247). And **nothing outside the vendor tree imports the plugin at all.**

  So the remaining work is not "call the existing function". It is: expose a highlight entry point from
  the plugin, then have `portal/panels/aiassist.ts:334` — which today renders `"Source: p.12"` as inert
  `textContent` — open the document and drive it. **The catch worth pausing on:** `vendor/massingpdf/`
  is vendored from the separate `MassingCloud/massingifc` kernel repo, so an edit there is either lost
  on the next re-vendor or has to go upstream first. That is a real decision, not a line of code, and
  it is why the frontend half is *not* claimed as trivial.

  Still true and still the reason this is cheap overall: **no stored bbox is needed** (`extract_pdf_text`
  is pypdf and discards positions, so storing one would have forced a new extractor and possible AGPL
  exposure), because the passage text now travels in the citation and the client can re-find it.

### Corroboration, not a new item — R24-TRACE-UI ② is the right target

An external essay on construction capital allocation argues the industry's real gap is that the
"what should this cost and where should the money go" decision sits **outside** the software, fragmented
across estimates, value-engineering exercises and tribal knowledge. Its named requirements are
*structured data instead of PDFs*, *historical cost patterns across similar projects*, *current pricing*
— and **"decision context linked to estimates, not isolated numbers."**

We have the first three (`COST-DB` with vintage + source, `benchmarking`, `ESTIMATE-DIFF`). The fourth is
**exactly R24-TRACE-UI ②** as re-scoped on 2026-07-29: make the proforma emit its own derivation, each
figure carrying its inputs and a *model-derived / overridden / market-assumption* tag. Independent
external confirmation that the re-scope picked the right work — and a reminder that its value is the
**basis**, not the UI.

### EU BIM Task Group Handbook V2.1 — reviewed 2026-07-30, **no build items**

Reviewed at the user's request. It is a **policy** document: a strategic framework for public-sector
bodies introducing BIM at national or programme level, organised as four action areas — establishing
public leadership · communicating vision and fostering communities · developing a collaborative
framework · growing client and industry capability and capacity. Three of the four are governance and
procurement, with no software implication at all.

The fourth, *developing a collaborative framework*, is the one that could have mapped to product work —
in EU BIM terms it means standardised information requirements, open data formats and a common data
environment, i.e. **ISO 19650**. Premise-checked against the repo, case-sensitively and word-bounded:

| concept | where it already lives |
|---|---|
| CDE state machine | `modules/information_container/module.json` — real states `wip → shared → published → archived` |
| EIR, as an authored artefact | `modules/info_requirement/` — a register, not just a referenced term |
| BEP · MIDP · TIDP · LOIN · suitability | present across 13–33 code files each |
| open format as source of truth | IFC is the non-negotiable in `CLAUDE.md` |

So the handbook's technical content is implemented, and its strategic content is not ours to implement.
**Recorded rather than deleted** so the next agent handed this PDF does not re-derive it.

*Two process notes.* The supplied PDF has **no text layer** — 57 chars extracted from 57 pages by both
`pypdf` and poppler's `pdftotext`, no embedded page rasters, text drawn as vector outlines — and there
is no rasteriser on this machine, so it was read from the published edition and web sources instead.
And the first coverage measurement was **wrong in the reassuring direction**: a case-insensitive `EIR`
matches "their", `MIDP` matches "midpoint", so the initial grep reported 317 files and would have
supported "already covered" without evidence. The conclusion survived a correct measurement; the point
is that it was reached first by a broken one. See [[confident-wrong-beats-missing]].

### Rejected, with the reason — so this is not re-run

| source | why not |
|---|---|
| A PolyForm-Noncommercial multi-agent orchestrator | **Licence excluded.** MIT/BSD/Apache only; noncommercial forbids our use regardless of merit. |
| DuckDB-WASM spatial GIS platform (MIT) | In-browser spatial SQL is genuinely interesting, but it is a heavy new dependency and `parcels` / GIS already serve site analysis. Revisit only if offline spatial SQL becomes a requirement, not a curiosity. |
| Curated systematic-trading library list | Domain mismatch — market microstructure and HFT do not transfer to property cash flows. The one transferable idea (portfolio optimisation) is **R31-PIPELINE-ALLOCATE** above, without the dependency. |
| A Revit QA/QC add-in (MIT) | C#/.NET against the Revit API — unusable here. Its check list (missing/duplicate mark, wrong level, element count, health score) is **already ~covered** by `model_qa` + `model_warnings`. |
| Reference-closure element extraction | **Already covered.** `SUBSET-EXPORT` prunes to a QUERY-DSL slice via `remove_deep2` with the spatial skeleton preserved, and `editPreview` returns a single-element fragment. |
| "Keep the agent instruction file under 200 lines" | Checked: `CLAUDE.md` is **55 lines**. No action — and worth recording that the check was run, since the alternative is assuming. |
| An Apache-2.0 agent-evaluation harness (harbor) | **Not imported.** Licence is fine and it runs locally on Docker, but it is an *evaluation* harness with no training path — running it changes no behaviour here — and it needs an API key plus a container per task, against an offline/$0 constraint. Its unit of work (a task plus a verifiable check) is what `run_tests.py` and vitest already are, for free and already wired to CI. **The transferable idea, offered to the user and not yet adopted:** a regression corpus of the defects that passed a green suite here — the fake-link fallback, the 100%-wrong GP promote, the surface gate with 13 methods of slack, the lane gate that was red and untracked. Each is a case where a check existed and could not see the failure. Deliberately left uncoded until the user picks it up, so nobody claims an item nobody agreed to. |
| Commercial construction PM / AI-workspace / syndication products (five reviewed) | Capabilities reviewed and already covered: document Q&A with citations, takeoff on drawings, registries, schedule editors, 2D→BIM extraction (`plan_to_bim`), waterfalls. Named generically per the standing directive that competitor names stay out of repo docs; the one real gap they surfaced is **R31-SYNDICATION-TAIL**. |

### Practice notes (no build item)

Two engineering-practice sources describe what this session already does, which is worth recording as
confirmation rather than as work: **a second agent context finds bugs the first introduced** — that is
precisely how the glTF uint32 gap, the GP-promote error and the `surface.test.ts` slack were all caught
today, each by someone other than the author. And **"prove to me this works" beats accepting an
implementation** — the mutation-check habit. The failure modes the other article names (cascading
instability, security blindness, unmeasured debt) are what CodeQL-after-every-push, the ratchets and the
full-suite-on-merged-tree runs exist to prevent.
## 🛡 R35 — CONCURRENCY & SUPPLY-CHAIN HARDENING *(race sweep + external security audit, 2026-08-01)*

An external security audit and a directed race-condition sweep ran the same day; three defects were
fixed and gated immediately (v0.3.817), and the remainders below are coded items. The sweep's method
is the reusable part: **list every read-then-write seam, then ask what holds the world still between
the read and the write — and on WHICH backend.** A lock the backend ignores is worse than no lock,
because the code reads as protected. `with_for_update()` is a no-op on SQLite, which is a supported
deployment backend — that single fact produced duplicate human refs under four concurrent creates,
measured by the new `test_race_conditions.py` the first time it ran.

Shipped 2026-08-01:

* ✅ **job claim is now compare-and-swap** — two workers sharing one database could both mark the
  oldest queued job `running` and execute it concurrently ("handlers are idempotent" covers a
  crash-recovery re-run, not two copies interleaving live). `UPDATE … WHERE state = 'queued'` has
  exactly one winner across all workers; losers advance to the next job rather than sleeping.
* ✅ **ref allocation is a single atomic increment** — `UPDATE … SET n = n + 1 … RETURNING n`
  replaces read-modify-write under a row lock that only Postgres honoured. Counter seeding survives
  losing the first-create race via a savepoint (the `consume_stepup` pattern) instead of surfacing
  the PK refusal as a 500.
* ✅ **secret scanning is a suite gate** (`test_no_secrets.py`), not a paths-filtered workflow —
  a paths filter is how the lockfile gate sat red and unseen for three releases. Seven credential
  patterns at zero tolerance over every tracked file; the sanctioned dev constants
  (the guard's own subject matter) pinned to an allowlist whose every entry is asserted live.
* ✅ **the audit's Critical #1 was already closed** — `_production_guard()` refuses to boot on any
  non-SQLite DSN or `AEC_ENV=production` with a default secret / RBAC off / trusted X-User /
  default object-store creds, tested in `test_prod_hardening.py`. Recorded because the audit read
  only the `AEC_REQUIRE_SECRET` branch and called the fallback unguarded — **an audit that misses
  an existing control still tells you the control is hard to find.**

Shipped 2026-08-29 — **a hardening pass whose two findings were both in the SECURITY TOOLING, not in
the product.** That is worth stating plainly, because it is the second time on this repo that the
thing enforcing a rule was the thing that had quietly stopped enforcing it (`supply_chain` itself was
the first, with a classifier and an audit that nothing invoked).

* ✅ **`supply_chain --gate` exited 1 on a correct tree — permanently, and for over a fortnight.**
  It failed on *any* strong copyleft in the installed set, with no awareness of `SHIP_EXCLUDED`.
  `bcf-client` (GPLv3, an unconditional requirement of the LGPL `ifctester` we do need) has been
  declared there and purged from every artifact by the container's `--purge` since it was found — so
  the CLI and `services/api/test_license_gate.py` were **two enforcement paths for one policy giving
  opposite answers**, with the test right. The hardening runbook tells an operator to run the CLI
  before every release, where a permanent red is exactly the "gate somebody switches off" that this
  module's own audit note warns about for weak copyleft; the strong path had acquired the same
  defect. `--gate` now excludes `SHIP_EXCLUDED`, prints `GATE OK` / `GATE FAIL: <names>`, and tags
  an excluded package `STRONG*` with a footnote instead of a bare `STRONG` that reads as an
  unaddressed breach. Verified both ways: exit 0 on the real tree, exit 1 with the package named
  when the exclusion is removed.
  **The bug was found by an error, which is the transferable part** — the first read of the exit
  code was `$? ` after a pipe, so it reported the *pipe's* status. Re-reading it directly is what
  surfaced the mismatch. That trap is already written down in `docs/roadmap-directions.md` §2.
* ✅ **XML entity expansion: the posture was good and held by nothing** —
  `services/api/test_xml_parse_hardening.py`. Three first-party paths already parse untrusted
  schedule XML safely (`mspdi` and `p6xml` via `xmlsafe.parse`; `aec_data.schedule` via
  `defusedxml`) and no assertion required a fourth to. Now ratcheted, with the reader self-tested
  against a planted offender and both directions mutation-checked.
  The rule's *justification* is re-measured on every run rather than recalled: on CPython 3.12.3
  bare `ElementTree.fromstring` refuses external entities but expands internal ones —
  **100,000 characters from 249 bytes in 2 ms** — so if a future CPython hardens the default parser
  that check goes red and tells us the reason changed.
  **The one unguarded parse in the tree is vendored and was deliberately NOT patched.**
  `massingcapture/probe/e57.py` reads the E57 XML index bare, and is unreachable: nothing in
  `aec_api` or `aec_data` imports `massingcapture`, and the routed `aec_api/e57.py` is a different
  module that parses no XML. `VENDOR.md` pins the subset with *"Local deviations: NONE"* and
  `test_massingcapture_vendor.py` asserts it is **stdlib-only per file**, so neither `defusedxml`
  nor `xmlsafe` can be imported there — the fix belongs upstream. **Unreachability is therefore the
  control, so the unreachability is what is asserted**, and wiring the capture probes fails the gate
  and puts the XML question in front of that commit rather than a later audit.

Shipped 2026-08-21:

- ✅ **R35-DEAL-MEMORY** *(M — SHIPPED v0.3.1112)* — the platform's own closed deals as a comp database: when underwriting
  a new deal, surface this portfolio's realised outcomes (exit cap achieved vs assumed, actual
  lease-up months, cost/SF by vintage) beside the assumption being entered. External research
  (2026-08) puts this "institutional knowledge" layer as the least-commoditised part of the
  AI-underwriting stack — and it is the one layer that cannot be bought, because it is made of the
  operator's own history. Builds on `benchmarking.py`'s cross-project aggregation and the
  provenance spine; no new dependency.

  **PREMISE-CHECK 2026-08-27, and the entry was half-right in the way that reads as done.**
  `deal_memory.py` had shipped, was tested, and was routed — `GET /portfolio/deal-memory`. But
  `beside()`, the last function in it and the only one that answers the sentence above, **had no
  caller anywhere**: not a route, not the client, not a screen. `test_reachable` passes because the
  MODULE is imported, by the portfolio route. *A module can be reachable and its whole reason for
  existing still be unreachable* — the same finding R46 recorded about `read_p6xml_all`, and the
  second time this shape has been found by opening the file rather than by a gate.

  Shipped as `GET /projects/{pid}/deal-memory/beside`, on the proforma's cost budget, held by
  `services/api/test_deal_memory_beside.py`. **One of the engine's three metrics is offered and the
  other two are refused on the record**: `cost_per_sf` is a unit conversion from an entered hard cost
  and a GFA; `cost_variance_pct` beside a contingency would be the product asserting *"your
  contingency should cover our historical overrun"*, the same domain call `/schedule/eot` is waiting
  on; and a schedule VARIANCE beside an entered DURATION is a category error in matching units.

  **The "by vintage" half was nearly left out, and two gates disagreeing is what caught it.**
  `clientCallers.test.ts` refused a `portfolioDealMemory` with no screen; `test_route_reachability`
  then read its own frozen entry as called, because the new route put the substring `deal-memory`
  into the web source and that rule matches a leaf against the whole blob. Neither was wrong.
  Re-reading this entry settled it — it asks for cost/SF **by vintage**, `comps` returns `vintage`
  per project, and only the summary had been wired. **A gate collision is worth reading as evidence
  about the work, not as an obstacle to it.**

Also settled, no code change: **the Fragments converter stays Node, by constraint** — the Fragments
serializer exists only in the JS kernel libraries, so `services/converter/` is the one deliberate
non-Python server component (an isolated, subprocess-shaped CLI; everything else server-side is
Python). Revisit only when a Python Fragments writer exists upstream.
## 🩺 R37 — REPOWISE HEALTH BACKLOG *(external static-analysis pass, received 2026-08-02)*

A full task list from a repowise health scan: 2 import cycles, 11 oversized files, 139 dead-code
findings (~1,075 lines), 349 single-owner hotspot files, 636 small local refactors. It is real work
— and **its index is dated 2026-07-17 (commit f3b171f0 = v0.3.363), which is 455 releases behind main at v0.3.818.** The first draft of this sentence said "~150", an unverified guess that understated the staleness threefold — in the one section whose whole thesis is that unverified numbers get people hurt. Counted from the tag list, not estimated. Every
claim must be premise-checked against TODAY's tree before acting; several are already known-wrong:

* Its §4 ("9 high security findings, detail paywalled") is **already covered and mostly closed** —
  CodeQL runs on every push with 0 open alerts, `pip_audit`/`npm audit` ran 2026-08-01 (pypdf floor
  raised; diskcache advisory has no fix and is monitored), and `test_no_secrets.py` scans every
  tracked file in the suite. Do not re-open this as if unknown.
  **Corrected 2026-08-21: the `npm audit` half of that sentence was vouching for a scan that could
  not see anything.** It ran `--omit=dev` over a tree whose every advisory is dev-only, with
  `continue-on-error` and `|| true` besides — two HIGHs were sitting behind it the whole time. Fixed
  and gated by SEC-NPM-GATE above. The rest of the bullet stands; this is a note about how a true
  sentence ("it ran") can carry a false one ("so it is covered").
* Its dead-code list predates the reachability sweeps (R31/R32/Band 3) that deliberately WIRED
  several of the named symbols. Example class: `validate.py` and `docgraph.py` symbols were
  "unused" in mid-July and have callers now. The check per symbol is the usual one —
  `git grep` the name including string/registry references, then delete or wire, never assume.
* Its hotspot list (§3) is corroborated independently: `main.ts`, `portal.ts`, `client.ts` are the
  repo's own known god-files, and SCALE-SEAM already split `client.ts` by domain after this index
  was taken. Credit what shipped; keep the rest.

- ✅ **R37-TRIAGE** *(M — Lane C; **CLOSED — verified against the gate, not the prose, 2026-08-29**:
  `services/api/test_dead_code_population.py` reports **0 unreferenced beyond the 0 kept on purpose**
  and `DELIBERATELY_UNCALLED` empty. The "12 remaining candidates" this entry and the sprint row
  above it both describe are gone. *Closed in the same merge that archived R37-TESTED-UNWIRED from
  a concurrent sweep — two sessions reached the same class of finding independently, and this one
  is the item that sweep left because it had no gate reading to go on.*)*
  **STEP 3 RE-DERIVED v0.3.973, and the derivation is the finding.** The entry said the dead-code
  list "should be re-derived, not triaged". Done, and the useful output is not the list but *how far
  a wrong population misses by*:

  | population rule | candidates |
  |---|---|
  | public functions in `aec_api` never referenced by name | **877** of 1,993 |
  | …excluding decorated functions (FastAPI handlers are reached by decorator, never by name) | **35** |
  | …and counting string literals as references, over `services/api` **and** `services/data` **and** the test tree | **13** |

  **877 → 13 without changing a single threshold.** Every reduction was a correction to *what counts
  as a caller*, and the first number would have been shipped as "44% of this package is dead" by
  anyone who ran the obvious query. This is [[derive-the-population-and-the-reach]] with a
  67-to-1 error bar on it. **The 13 are candidates, not corpses** — string dispatch through a
  registry and `__all__` re-exports can still hide a caller, so each needs reading before deletion.

  The list, with the deletions struck through — **a backticked symbol reads as a live one**, which is
  the same convention this file already applies to files, and the reason `verify_stepup_token` was
  struck rather than removed: ~~`discipline_names`~~ · `excluded_import_names` · `input_fields` ·
  `map_procore_change_event` · `map_procore_rfi` · `map_procore_submittal` · `project_with_source` ·
  ~~`quadrant`~~ · `register_recipe` · ~~`scorecard_inputs`~~ · `search_filter` · `sync_property` ·
  ~~`verify_stepup_token`~~. Deleted: `verify_stepup_token` v0.3.973; the other three v0.3.980.

  **Nine are left unstruck, of which eight have a real caller** — and the ninth is worth naming
  rather than rounding away. `sync_property` has no caller: it is a deliberate refusal stub that
  raises `NotImplementedError` and names *itself* as the place to implement the credentialed ENERGY
  STAR exchange. It is kept because deleting it would remove the documented extension point from a
  module whose whole contract is "never fabricate a score", not because anything calls it. (The gate
  counts it as referenced because that error string names it — a limitation, stated rather than
  hidden.)

  **STEP 4 — all 12 read, v0.3.980. The list was wrong in both directions, and that is the result.**
  The table above records the rule being corrected twice, 877 → 35 → 13, without moving a threshold.
  The implication nobody drew is that **a rule corrected twice has not finished being wrong**. It
  had not: reading the 12 found **eight live symbols**, missed for three distinct reasons —

  | blind spot | the symbols | what deleting them would have done |
  |---|---|---|
  | **aliased imports** (`from .x import f as _f`, then `_f(...)`) | `search_filter` · `project_with_source` · `input_fields` | broken module search and three authoring routers |
  | **Python files that are not `.py`** | `excluded_import_names`, read by `desktop.spec` **and** `sidecar.spec` | broken both PyInstaller builds |
  | **methods reached through an instance** (`api.register_recipe(...)`) | `register_recipe` | broken the documented third-party **plugin API** |

  The `.spec` case is the sharpest: that symbol *is* imported, by name, unaliased — the scanner
  simply never opened the file, because its glob was `*.py`. **A population derived over the wrong
  file set is not a conservative estimate, it is a confident wrong answer**, and no test here would
  have gone red. (`map_procore_*` ×3 were plain misses — imported by `connectors.py`.)

  **And the list was short by two.** A corrected rule surfaced `get_meta` and `validate_dir`, which
  were never candidates. So the 13 was neither an upper nor a lower bound on anything.

  **Deleted (3), each for saying something false about itself rather than merely for being uncalled:**
  `evm.quadrant` — a second implementation of the CPI–SPI points `evm.ts` already derives, under a
  docstring claiming "Used for the quadrant scatter on the dashboard" · `cde.scorecard_inputs` — a
  wrapper "so the KPI engine has one import", which `bim_kpi.py` bypasses by calling the two
  functions it wraps · `classification.discipline_names` — an option list nothing offered.

  **Kept (10), with the evidence above, so no future sweep re-proposes them.**

  ⚠️ **Two more were deleted and had to be put back, which is the sharpest lesson here.**
  `module_schema.validate_dir` is called by `test_module_config.py`; `model_index.get_meta` is
  imported and called at `routers/standards.py`. Both were reported dead by the new gate **because
  the gate's comment-stripper was wrong**: it applied the TypeScript block-comment pattern
  `/\*.*?\*/` to `.py` files, and `test_module_config.py` contains `modules/*/module.json` — a
  literal `/*` and a literal `*/` — so the "comment" swallowed the file's imports. The full suite
  caught `validate_dir`; `get_meta` was caught by re-grepping every deleted name **without a `head`
  limit**, which is how it was missed the first time: `.venv` noise filled the first ten lines and
  pushed the real caller off the end.

  **Over-stripping is not the safe direction.** A false death in a dead-code gate is an instruction
  to delete working code. Stripping is now per-language, and the incident is written into the gate
  beside the patterns.

  **The rule now lives in `services/api/test_dead_code_population.py` as a ratchet at zero** — a new
  unreachable public function fails at the commit that adds it, instead of accumulating until
  somebody re-derives a population and gets it wrong a fourth time. Two things are worth knowing
  before trusting it:

  - **It had to be corrected FOUR times itself**, which is the lesson repeating one level down, and
    the last three each survived the fix for the one before. (1) `ast.walk` counted nested closures
    and discarded same-file callers → 69 flagged. (2) Reference matching counted **prose**, so it
    passed with zero and could not go red at all. (3) The **TypeScript** block-comment regex ran on
    `.py` files, and `modules/*/module.json` holds a literal `/*` and `*/` → it ate the imports and
    `validate_dir` was deleted. (4) `"""…"""` pairing shifts when an earlier `#`-strip removes a
    triple quote, swallowing code to end-of-file → `get_meta` was deleted. Python is parsed with
    `ast` now; regex stripping is `.ts`-only. **Two conclusions are easy to get backwards:
    over-stripping is not the safe direction, and changing how references are gathered changes what
    must be discounted** — the `def`-line subtraction was right for regex and wrong for `ast`, where
    it silently deleted real same-file calls.
  - **It still cannot see `quadrant`**, because a UI label string contains that word and string
    literals must count (registries dispatch on them). That one needed a human, and the limit is
    stated in the file rather than hidden by an exemption.

  **One of the 13 was worth the whole exercise.** `auth.verify_stepup_token` ran identical signature,
  expiry, action and password-fingerprint checks to `verify_stepup_claims` and returned **only the
  subject** — so a caller reaching for it could not spend the `jti`, and the step-up assertion it
  verified stayed **replayable**. A step-up exists to attest *"a human confirmed THIS act"*, and
  `rbac.consume_stepup` spends the jti against `stepup_spent` precisely so a captured token cannot
  seal a stack of documents. Nothing called the weak one, which is the reason to delete it rather
  than a reason to leave it: two verifiers where one silently drops replay protection is a footgun
  whether or not anyone has picked it up. `services/api/test_stepup_single_verifier.py` asserts the
  *property* — every step-up verifier returns something a caller can spend — rather than the absence
  of a name, because a grep for a deleted name passes forever and reads as coverage.

  **Steps 1–3 triaged in v0.3.865–867 on measurements rather than recollection:** cycles ALREADY-CLOSED and gated on both
  sides; the oversized-files list names the wrong files (`app.ts` sits at 97% of ceiling, the named
  candidates at 13–19%); the dead-code list should be re-derived, not triaged. Step 4 is explicitly
  Lane A and not routed here; step 5 is opportunistic. What remains needs a dependency decision.
  Original: re-run the backlog's
  claims against main: for each §2 symbol, grep for callers today and mark delete/wire/keep with
  the evidence; for §1's cycles, confirm the edges still exist; for §1b's split candidates, compare
  against the REL-3/REL-4 decompositions already landed. Output: this section rewritten with each
  item marked VERIFIED-OPEN or ALREADY-CLOSED, so the execution order below runs on facts.

Execution order after triage (the backlog's own, amended). **Paths are directory-qualified because
both basenames the backlog cites are ambiguous** — `modules.py` and `codecheck.py` each match two
tracked files, and the wrong-directory misroute is exactly how lanes collide:

1. ~~Break the two cycles~~ — **ALREADY-CLOSED, verified 2026-08-04, and both are now gated.**
   `services/api/test_import_cycles.py` reports **zero** top-level cycles across 516 first-party
   modules and 968 import edges, and `apps/web/src/no-import-cycles.test.ts` passes on the web side.
   The `db.py` ring is gone in the direction that matters: `models.py` does `from .db import Base`
   and `db.py` imports nothing back. `panelContext.ts` still exists — the *file* was never the
   problem, the *edge* was, and the edge is gone.

   Recorded rather than deleted because the backlog's index is 455 releases old: the useful output
   of triage is "this was true and is not any more", not a quietly shortened list. Nobody needs to
   re-derive it, and if a cycle returns, the two gates fail before anyone reads this.
2. **MEASURED 2026-08-04 — the backlog names the wrong files, and the real one is nearly out of
   room.** Against this repo's own ratchet (`services/api/test_file_sizes.py`, CEILING 5200):

       apps/web/src/viewer/app.ts   5064   97% of ceiling   <- 136 lines of headroom
       apps/web/src/api/client.ts   3967   76%
       .../portal/register/register.ts 2162  42%
       services/api/src/aec_api/modules.py  988  19%
       services/api/src/aec_api/main.py     697  13%

   The backlog's candidates are 13–19% of the ceiling; they are not the problem. `app.ts` is, and
   **the next feature that touches it reds the build** — v0.3.861 put 42 of those lines there for the
   verification photo button, so this is a live constraint, not a projection. Splitting `app.ts` is
   Lane E and a real piece of work; it is named here so nobody spends the effort on `modules.py`
   first and reports the file-size item as addressed.

   Retained below because "982 lines" is now 988 — the file grew while sitting on a to-split list,
   which is the other reason a stale backlog costs: it makes work look done that is quietly getting
   worse.

   Original: split `services/api/src/aec_api/modules.py` (982 lines — Lane C) and
   `services/api/src/aec_api/main.py` (Lane G convention applies: announce first, it is a shared
   file). The backlog's "codecheck.py" split almost certainly means
   `services/api/src/aec_api/routers/codecheck.py` (614 lines) — that is the **routers carve-out
   Lane C does not own**; whoever takes it claims it as a routers change, not under this item. The
   non-router `services/api/src/aec_api/codecheck.py` is 184 lines and needs no split.
3. **Delete only VERIFIED dead exports — and TRIAGING THIS LIST IS THE WRONG MOVE, verified
   2026-08-04.** Three cheap measurements, together decisive:

   * The two examples this section already suspected are confirmed stale: `validate.py` has **3**
     importers today and `docgraph.py` has **2**. Called "unused" in mid-July, wired since.
   * The cheap dead-code classes are **already gated** — `ruff --select F401,F841` (unused imports,
     unused locals) passes clean across `services/api/src` and `services/data/src` on every push.
     Whatever remains in the 139 findings is symbol-level: exports defined and never called, which
     ruff does not look for.
   * Finding those needs a tool this repo does not have (`vulture` is not installed), and **adding
     one is a new dependency — the user's call, not a triage step.**

   So the real choice is not "triage 139 findings vs skip them", it is **re-derive vs triage a
   455-release-old list**. Each stale entry costs a `git grep` including string and registry
   references — a symbol reached only through a registry looks dead to every naive check — and the
   two spot-checks suggest a high false-positive rate. Triage would spend that cost and still
   produce a list bounded by July's tree.

   **Recommended: leave this step closed as specified; open a fresh scan as its own item once the
   dependency question is answered.**
4. The web-side refactors (`apps/web/vite.config.ts`, `apps/web/src/main.ts`) are **Lane A work and
   belong to R36-RAIL-SCOPE's owner** — they are listed here for sequence only, not routed by this
   Lane C item; a C session must not pick them up off this list.
5. Hotspot tests, then small-effort batch work when already in a file.
## 🧭 R36 — ROOM COHESION RING *(three user directives, 2026-08-02: the rooms must each be a product)*

The user's asks, verbatim in spirit: the left rail must show only the current room's tools; drawings
and specs have **no way back to Design** and should integrate with the model viewer as one subapp;
the Author menu needs its "More" tools promoted and its groups split; and every room must be analysed
for what its role actually needs first. Audited before planning — the facts:

* **No tool is unassigned** — `spine.ts` refuses to file a destination without a room and surfaces
  the unrouted list in the rail (`destinations.test.ts` gates it). The defect is different: the rail
  renders **every room's group with the current one merely opened**, so every room shows all tools.
  Filtering exists as disclosure, not as scope.
* **The drawings/specs dead end is real** — `drawings.ts` renders into its own workspace with no
  back affordance and no route into the viewer; a user's only way out is knowing the room tabs are
  the navigation. Specs behaves the same.
* `destinations.test.ts:19` still says "the five that exist" over a seven-room assertion — label
  drift only, the assertion reads `ROOM_IDS`.

External reference points (2026-08 scan): browser CAD/BIM tools that feel coherent share three
choices — **one canvas, many modes** (2D sheets and 3D model are views of one subapp, switched
in-place, never separate pages); **tool scope follows context** (the palette shows the active mode's
verbs, with a command bar as the escape hatch to everything); and **role-shaped landing content**
(the first screen of a work area answers that role's first question, not a generic dashboard).


## 🧱 Decomposition & reliability carry-overs (interleave one per few releases)

- ◧ ⭐ **SCALE-SEAM ㉙ — `client.ts` is no longer a god-file, but the split is not finished.** *(②–㉘ have shipped, **㉘ construction accounting in v0.3.1120**)*
  **㉘ took the double-entry books and WIP out** (ten methods; `client.ts` 2,816 → 2,752) as
  `apps/web/src/api/accounting.ts`. **The strongest case yet for grouping by what the methods
  ANSWER**, because the group was in TWO non-contiguous clusters ~700 lines apart, with prequal,
  carbon and land screening in between — no prefix split would have found them together, and a
  route split would separate `journalBatchExportUrl` from the batch `createJournalBatch` creates.
  What they answer together is one question: *what do the books say?*
  **`costTraceability` did NOT come**, though it sits immediately above the second cluster — it
  answers which cost codes trace to model elements, a takeoff question that happens to be
  adjacent. *Adjacency in a file is not a relationship*, met for the third time (㉕, ㉗, ㉘).
  **`MARKS` was widened to ㉙ in this release rather than the next one**, which is the correction
  the ㉘ note asks for: widening on the way OUT of a slice, not on the way into the one after,
  is what stops the vocabulary from being one short of the open item again.
  **The per-file pin moved 2,837 → 2,752** — and it had been carrying slack it was never told
  about: v0.3.1119 took the file to 2,816 under duress from that very check and did not lower it.
  **㉗ took the PDF tools and A/E/C seals out** (9 methods, one contiguous run; `client.ts` 2,883 →
  2,837) as `apps/web/src/api/pdfTools.ts`. Grouped by what they DO, following ㉖: the run spans
  `/pdf/*`, `/stamps/library` and `/licenses/mine`, and a prefix split would separate `stampLibrary`
  from the `pdfStamp` that consumes it, and `myLicenses` from the seal dialog that is its only reason
  to exist.
  **`_pdfPost` did NOT move.** It is `protected` on `HttpCore`, which every mixin already extends, so
  it is where shared transport belongs — the seam is the feature, not the plumbing. Same call ㉔ made
  when `idsDownload` and `pinProjectIds` moved despite not being `json()` calls.
  *The doc-comment gate caught a real inconsistency on the way through: `myLicenses`'s comment spelled
  it "licences" while the code, the type and the route all say `licenses`, so the comment shared no
  word with its method. Fixed by matching the code rather than by widening the exemption set, which is
  frozen and may only shrink.*
  **㉘ required `MARKS` widened, and that landed in v0.3.1112** — measured as that file demands (29 item codes before, 29 after), and with a new assertion so the NEXT slice fails a test rather than relying on this sentence. *Which it had to, because this sentence still read "㉘ needs `MARKS` widened again" in the very release that widened it — the fifth stale status line in this ring, caught by review. A note asking a future reader to remember something is the thing a gate replaces, and leaving it up after building the gate is the same defect one level out.*

  **㉖ took the code-compliance group out** (8 methods; `client.ts` 2,961 → 2,883) as
  `apps/web/src/api/codecheck.ts`. **It is the first slice grouped by what the methods ANSWER rather
  than by a shared route prefix**, and that is a deliberate departure: the group spans
  `/projects/{pid}/codecheck`, `/codes/adoptions` and `/codes/ebc/pathways`, so a prefix split would
  have put `ebcClassify` and `ebcPathways` — the two halves of one screen — in two files. The prefix
  was only ever a cheap proxy for "one feature"; here it stops being one, and following it would have
  been rigour about the wrong thing.
  **㉗ needs `MARKS` widened again** in `apps/web/src/shell/roadmapLanes.test.ts` — ㉖ was added for
  this slice, and the vocabulary now stops there.
  *Two RFI methods (`rfiReadiness`, `rfiReadinessBcf`) sat INSIDE this run in the file and did not
  come with it. Adjacency in a file is not a relationship — the same lesson ㉕ recorded about
  `MaterialEntry`, met again and acted on the same way.*

  **㉕ took `/projects/{pid}/specialty` out** (5 methods + 5 types; `client.ts` 3,019 → 2,961) as
  `apps/web/src/api/specialty.ts`. Two neighbouring types stayed: `MaterialEntry` is imported by
  `apps/web/src/portal/panels/materials.ts`, so moving it would have been a breaking change dressed
  as tidying. **Adjacency in a file is not a relationship.** *`SpecialtySummary` nearly went the
  other way — the grep proving the types were unused outside had been truncated with `head -4`, and
  its one outside reference was on the line after the cut. Caught by the typecheck, not by me.*
  **㉖ needs `MARKS` widened** in `apps/web/src/shell/roadmapLanes.test.ts`: the marker vocabulary
  stops at ㉕, so the next slice cannot be written down before that is extended.

  **㉔ took `/ids` and `/projects/{pid}/ids` out** (6 methods, one contiguous run; `client.ts`
  3,066 → 3,026) as `apps/web/src/api/ids.ts`. The group was found by **measuring the longest
  same-prefix run left in the file**, not by picking a domain that sounded tidy — `/specialty` is
  the next at five, but its three types are interleaved with unrelated ones, so it is a more
  careful extraction than a late-session slice should be.

  ⚠️ **THIS EXTRACTION HAS BEEN LEAVING DOC COMMENTS BEHIND, and it has done it twice.** When a
  method moves, its comment stays with the file and attaches itself to whatever follows. Two
  distinct shapes, both measured:
  * **Eleven methods documented as a NEIGHBOUR's job** — fixed v0.3.1075, gated by
    `apps/web/src/api/docComments.test.ts`. `evm()` was described as `resourceLoading()`.
  * **~25 ORPHANED comments** — a doc comment immediately followed by another doc comment, its own
    declaration gone. Three sampled, all genuine and all traceable to this split:
    `httpCore.ts` still documents `setToken`, which moved to `api/auth.ts`; `model.ts` still
    documents TOPIC-BOARD, which moved to `api/topics.ts` in ⑳; `authoring.ts` still documents an
    IFCPATCH-LIB dry-run scan. **Not yet fixed or gated** — the count is a candidate count, not a
    verified one, and a gate that fails on 25 sites belongs with the cleanup rather than before
    it. *A wrong docstring is worse than none; an orphaned one is how a wrong one is made.*

  **㉓ took `/projects/{pid}/evm` out** (6 methods, one contiguous run — the tightest group left;
  `client.ts` 3,120 → 3,066) as `apps/web/src/api/evm.ts`, with `EvmEarnedSchedule`, whose only
  readers were those methods. *Measuring which group to take found that `evm()` was documented as
  `resourceLoading()`'s job — eleven methods carried a neighbour's comment, left behind by earlier
  slices of this same extraction. Fixed in v0.3.1075; `apps/web/src/api/docComments.test.ts` now
  stands where that got in.*

  **㉒ took `/projects/{pid}/precon` out** (6 methods, one contiguous run; `client.ts` 3,170 → 3,128)
  as `apps/web/src/api/precon.ts`.

  **㉑ took `/projects/{pid}/ai` out** (6 methods in five regions; `client.ts` 3,205 → 3,170)
  as `apps/web/src/api/ai.ts`. `aiReadiness` (`/ai-readiness`) stays. The increment marker
  in `roadmapLanes.test.ts` now runs ①–㉕.

  **⑳ took `/projects/{pid}/topics` out** (7 methods in three regions; `client.ts` 3,243 → 3,205)
  as `apps/web/src/api/topics.ts`. `pins()` stays (`/pins`).

  **⑲ took `/projects/{pid}/mep` out** (7 methods in four regions; `client.ts` 3,304 → 3,243)
  as `apps/web/src/api/mep.ts`. `connectMep` / `addMepFitting` stay (`editIfc`).

  **⑱ took `/projects/{pid}/documents` out** (9 methods, one contiguous run; `client.ts` 3,353 → 3,304)
  as `apps/web/src/api/documents.ts`. `api/docqa.ts` stays `/review` + `/doctext`.

  **⑰ took `/projects/{pid}/models` out** (9 methods in four regions; `client.ts` 3,412 → 3,353)
  as `apps/web/src/api/models.ts` (`withModels`). `api/model.ts` stays `/model`.

  **⑯ took `/projects/{pid}/elements` out** (11 methods in five regions; `client.ts` 3,482 → 3,412)
  as `apps/web/src/api/elements.ts`. `elements5dMap` (`/5d/heatmap`) and the job tray stay.

  **⑮ took `/projects/{pid}/drawings` out** (11 methods in six regions; `client.ts` 3,538 → 3,482)
  as `apps/web/src/api/drawingSheets.ts`. `markupStream` uses `liveStream` on HttpCore.

  **`client.ts` went 4,956 → 3,128 lines** (`wc -l`). Next is the next route-group by size; pick it by
  re-running the classification below, not by reading the section comments.

  **This entry read `③+` and named `/model`, `/modules` and `/estimate` as the next groups until
  2026-07-30, by which point all three had shipped.** Caught by `roadmapLanes.test.ts`, and not for the
  reason anyone would have predicted: the lane table assigned `SCALE-SEAM ⑥` while this bullet still
  said `③+`, so the two codes did not match and the item read as *unassigned*. A consistency check
  between two lists found staleness in one of them — which is the argument for asserting cross-list
  agreement even when neither list is the thing you are trying to protect.

  The original defect is still worth keeping: **`roadmap-completed.md` recorded SCALE-SEAM as complete
  while measuring ① — a 112-line reduction, 2% — with the file still at 4.8k.** That is the dangerous
  direction of drift. Stale estimates that *understate* what exists get tripped over eventually; one
  that overstates it means nobody looks again.

  **There is no big cut left, and this is the number that should set the estimate.** Classify all 669
  methods by the route each calls — the only honest basis, since the `// --- section ---` comments label
  the *start* of a run and the file then continues with other domains, so they no longer delimit
  anything. That gives **219 route-groups**; the largest is `/model` at 221 lines (**4.5%** of the file)
  and the top six together are 20%. So this is roughly **25 releases of one group each**, not a
  big-bang split. Anyone scoping it as an L-sized refactor is reading the section comments.

  **⑥ shipped** — `/procurement` out (9 methods / 86 lines; `client.ts` 4,026 → 3,940). The nine sat
  in **six** separate regions of the file, which is the concrete form of "the section comments no
  longer delimit anything": they label where a run *starts*, and the file then carries on into other
  domains. Groups are located by the route each method calls, and each body by brace matching.

  **⑦ shipped** — `/auth` out to `apps/web/src/api/auth.ts` (20 methods / 96 lines; `client.ts`
  3,967 → 3,871), across **four** regions. Three things are worth carrying forward.

  *The difficulty this entry predicted did not exist.* ⑥ said `/auth` "needs care, because it is the
  one group that owns token state rather than just calling routes", and sized it at 19 methods / 90
  lines. It does mutate token state — `changePassword` and `logoutAll` both adopt the fresh token the
  server returns — but that state has lived on `HttpCore` behind a **public** `setToken` since the T2
  transport extraction. A mixin cannot see `ApiClient`'s privates; its own base's public members are
  fine. The real blocker in ③ was `liveStream` being private *on `ApiClient`*, and nothing here is
  shaped like that. **The caution was recorded before the fix that removed it, and then outlived it** —
  the same drift as the `③+` staleness above, in the one direction that costs work rather than
  causing a defect: an item scoped defensively for a reason that has already been discharged.

  *Four methods that read as `/auth` deliberately stayed.* `auditLog`, `errorLog`, `clearErrorLog` and
  `reportClientError` sit inside the `// --- admin: user management ---` run but route to `/audit`,
  `/admin/errors` and `/client-errors`. Grouping by section comment would have moved three unrelated
  domains. The orphaned `// --- auth ---` banner was deleted rather than left labelling `integrations()`.

  *The surface ratchet had gone slack again — the second consecutive increment to find this.* Floor
  698, live count 699, raised to 699. What makes the claim usable is that the count was measured on
  the **unmodified** tree first: 699 before and 699 after, from the gate's own reader, so the move
  provably dropped nothing and the slack was inherited rather than caused. Mutation-checked both
  ways (drop one method → 698 red; leave the mixin uncomposed → 679 red), with each mutation
  confirmed to have applied before its result was read — the first attempt's regex silently matched
  nothing under CRLF and returned a green that meant nothing. **`⑥` reported this same drift; two in
  a row is the pattern the test predicted, not bad luck** — every merge that adds an endpoint converts
  the ratchet back into a floor, so re-reading it is part of taking a SCALE-SEAM increment, not a
  discretionary extra.

  **The remaining-groups list here was wrong, and re-measuring is the only way to keep it honest.**
  It named `/procurement`, `/auth` and `/elements` and omitted several larger ones. Measured on
  `main` by counting route literals per first path segment:

  `/auth` 20 · `/proforma` 15 · `/connections` 11 · `/drawing-set` 11 · `/drawings` 11 ·
  `/elements` 11 · `/models` 9 · `/documents` 9 · `/contracts` 8 · `/sync` 7 · `/pdf` 7 · `/mep` 7

  ⑦ is `/auth` (20) — the one group that owns **token state** rather than just calling routes, so it
  needs care; `/proforma` (15) is the larger easy one and is the better next cut if ⑦ stalls.

  **The method is safe and worth reusing verbatim.** `api/surface.test.ts` captures the runtime method
  surface, so "I moved code" is distinguishable from "I changed behaviour" — which **a typecheck cannot
  do**, since deleting a method and deleting its last caller both compile clean. Both gates are needed
  and they catch different things: dropping `scheduleCpm` fails the surface test by name *and* fails tsc
  at the two real call sites. Mutation-verified on ②, and it took three attempts to mutate correctly —
  the first broke the file syntactically (vitest reported "no tests", which is **not** a passing gate)
  and the second deleted a docstring line naming the method. **A mutation you have not confirmed landed
  tells you nothing.**

- ❌ **SRI for the offline WASM/fragment assets — considered 2026-07-29 and REJECTED.** An external
  audit recommended Subresource Integrity for the WASM and fragment assets. **It does not apply
  here**, and the reason is worth recording because the next outside reading will recommend it again:
  SRI exists so a document can pin the bytes it expects from a *different* origin. Checked — there
  are **no remote asset URLs** anywhere in `apps/web/src/` or `index.html`; everything is bundled and
  self-hosted, which CLAUDE.md requires (the viewer must run fully offline, local WASM, self-hosted
  tiles). Same-origin, content-hashed bundles get nothing from it: anyone who can alter the bundle
  can alter the `integrity=` attribute in the HTML that names it, in the same write. Adding it would
  be ceremony that reads as a control. **A hardening measure that does not narrow an attacker's
  options is worse than none — it spends review attention and returns a false sense of coverage.**


**External corroboration — Repowise re-index, 2026-07-29.** Worth recording because it was reviewed
once before and judged mostly not actionable; re-indexed, it independently names the same five files
this section and [[web-godfile-decomposition]] already target, ranked by *churn × prior bug fixes*:

| file | churn | prior bug fixes |
|---|---|---|
| `apps/web/src/portal/portal.ts` | 99.9th pct | 10 |
| `apps/web/src/viewer/app.ts` | 99.8th | 16 |
| `apps/web/src/api/client.ts` | 99.8th | 15 |
| `apps/web/src/main.ts` | 99.7th | 18 |
| `services/data/src/aec_data/edit.py` | 99.6th | 6 |

Also: 168 of 1,426 files are hotspots, and **17 of the 20 lowest-health files were bug-fixed in the
last 6 months at 5.01× the baseline rate.** That is the useful number — it says the decomposition
backlog is not hygiene, it is where the defects actually come from. The list is the same one
`multi-agent-lanes` names as the concurrent-edit collision points, arrived at from git history rather
than from our experience, which is what makes it worth more than a restatement.

**Two of its findings are NOT actionable and should not be picked up.** "Bus factor 1 on every
hotspot" is an artifact — every commit here carries one git identity regardless of which session
wrote it, so the metric cannot say anything about this repo. And "4,591 open findings" is unscoped;
treat it as a lint-level count, not a defect count, unless someone bounds it by severity first.
Scores for the record: defect risk 7.3/10, maintainability 8.5/10, static performance 9.9/10.


- ◧ **REL-4 leaves** *(M)* — `portal.ts` next leaf + `viewer/app.ts` leaves.

  **First `portal.ts` leaf out in v0.3.1082: `renderDeveloperHome` → `apps/web/src/portal/homes/developerHome.ts`**
  (1,473 → 1,400). Small on purpose. The `this.` references of every candidate were grepped *before*
  naming the slice, and the result changed the plan:

  | method | lines | what it touches on the class |
  |---|---|---|
  | `renderDeveloperHome` | 79 | `host`, `mods` — **a leaf** |
  | `renderDesignHome` | 94 | + `activeKey`, `buildNav`, and five sibling `render*` methods |
  | `renderPxBand` | 54 | + `activeKey`, `buildNav`, `renderBudget`, `renderScheduleViews` |
  | `renderPortfolio` | 116 | + `bar`, `root`, `panelCtx`, `renderHome` |

  The two persona homes sit next to each other, are named alike, take the same four arguments and are
  called on adjacent lines — **and only one of them is a leaf.** Moving `renderDesignHome` would mean
  inventing a callback bag for seven siblings: coupling added in the name of removing it. That makes
  three separate times this cycle that adjacency turned out not to be a relationship (SCALE-SEAM ㉕'s
  `MaterialEntry`, ㉖'s two RFI methods, and this) — and the first time it was **measured before the
  slice was chosen** rather than discovered while making it.

  **A size ratchet was added for `portal.ts` in the same release**, at 1,400. It had none, so it lived
  under the global ceiling it is nowhere near — meaning the extraction bought nothing any check could
  see, and the next dozen additions could have put the lines straight back while the work still read
  as done. **An extraction without a ratchet is a rearrangement.** Verified by mutation: setting the
  cap to 1,399 fails the build.

  `portal/homes/` also needed an owning lane — Lane A, matching `portal.ts` itself, the same way Lane
  B owns `portal/panels/`. The unowned-files gate caught that on the first run, which is what it is
  for.

  **The second slice was going to be `renderModuleCatalog`. Measuring it found that the whole cluster
  was UNREACHABLE, and that a user-visible feature had gone down with it — v0.3.1084.**

  `catalogEl` appears exactly three times in the file: its declaration, and two lines inside
  `refreshCatalog`, which opens `if (!this.catalogEl) return;`. Nothing else assigns it, so
  `renderModuleCatalog` never ran. `git log -S catalogEl` names commit 9a61f4cc (2026-06-24), which
  deleted the two mount lines **on purpose** — "the persistent nav rail (N1) owning module navigation"
  made the dashboard catalog redundant — and left ninety-one lines behind, plus a persona listener
  calling the resulting no-op.

  **The part that matters is not the dead lines.** `toggleFav` had exactly one call site in the whole
  app: the `☆` button inside that catalog. `readFavs` had three live readers — `buildNav`'s
  "★ Favorites" group and `shell/pinnedRail.ts`'s `pinnedItems`. So favourites could be *read* and
  never *written*, and `pinnedItems` could only ever return `mode: "recent"`: **the pinned rail's
  entire "pinned" mode was unreachable**, on a component whose docstring explains at length why it
  never mixes pins with recents — *"two identical-looking rows mean different things"* — protecting a
  distinction that could not arise.

  So the fix was not the tempting one. Deleting ninety-one dead lines would have dropped a size
  ratchet, kept every test green, and quietly finished killing a feature two surfaces are built
  around. `readFavs` having three readers is the evidence favourites are wanted; only the setter was
  lost. `moduleButton` now carries the pin — one place, so every rail row has it — and the catalog
  went in the same release, so the star does not exist twice.

  **`SECTIONS_BY_PERSONA` went with it, and had been orphaned for longer.** Its comment said "buildNav
  falls back to open-all when none match" — but buildNav stopped grouping modules by section in
  v0.3.767, when the room spine made a second taxonomy in one rail a defect. A constant's docstring is
  a claim about the rest of the tree and nothing checks it.

  **No reachability or uncalled-symbol gate would have caught any of this**, and none should be
  trusted to: every method in that catalog had a caller — *each other*. `apps/web/src/portal/favourites.test.ts`
  builds the real rail, clicks the real control and reads the preference back, and was mutation-tested
  against a star that only re-styles itself.

  **And a fourth, v0.3.1089 — this one in the DOCS rather than the code.** 83 `AEC_*`/`MASSING_*`
  env flags are read under `services/` and **32 appeared in no document at all**. Two of them decide
  who may sign in — `AEC_OAUTH_ALLOWED_DOMAINS` and `AEC_OAUTH_NO_AUTOPROVISION` — and neither has a
  restrictive default, so an OAuth deployment with both unset is open by configuration and the
  operator has no way to discover the controls that would close it. `AEC_GRID_KGCO2E_PER_KWH` is the
  same shape in a different register: its default is a US grid factor, so carbon figures are wrong
  elsewhere and reported confidently. Gated by `services/api/test_env_documented.py` in **both**
  directions — the reverse one rejected three of its own author's entries on the first run.

  **And a third, from a different sweep — v0.3.1087.** Looking for classes assigned in TS that no
  stylesheet defines found the **Project Pulse rail has never been styled**: `pulse.ts` shipped in
  v0.3.749 and no stylesheet has ever contained the string `pulse`. It is not dead code —
  `portal.ts:renderPulse` mounts it on the dashboard — so it rendered as bare HTML for ~330 releases,
  and `pulse.test.ts` stayed green throughout because it tests what `buildPulse` computes, which was
  always right. The cost is the tone: `good | watch | risk` is derived across five domains and
  rendered only as a class, so **a risk card was pixel-identical to a healthy one**. Fixed with the
  R26 status tokens, gated by `apps/web/src/portal/panels/pulseStyled.test.ts`, which requires the
  three tones to resolve to three *different* tokens rather than merely to exist.

  *The scan returns 62 unstyled classes and most are selector hooks on components that style inline.
  `pulse.ts` was the only file with unstyled classes AND zero inline styling — that one condition is
  what separated a finding from a list.*

  **The sweep that followed found a worse one — v0.3.1085.** Looking for other state that is read but
  cannot be written turned up `apps/web/src/ui/clearCache.ts`, whose `KEEP_KEYS` matched **no key this
  app writes**: the session is `aec-token` and the list said `aec_token`, while its other six strings
  (`shell-spine`, `aec_persona`, `aec_ws`, `prefs:`, `aec_pref_`, and `aec_user`, which no commit has
  ever written) appear nowhere else in the repository. So Settings → "Clear cached data" signed the
  user out, wiped every preference, and deleted `aec-field-queue` — unsynced field captures with
  photos — while reporting *"Kept your sign-in and preferences (0 settings)"* under a note promising
  the opposite.

  Its test was green because every fixture in it was invented: it asserted `isKeeper` against six keys
  that do not exist. **A test whose fixtures are fictional cannot fail for the reason it exists.**

  The fix inverts the default — keep unless positively identified as regenerable cache — because an
  allowlist destroys what nobody thought of and a denylist keeps it, and drift is inevitable either
  way. `apps/web/src/ui/clearCacheKeys.test.ts` enumerates every localStorage key in `src/` and checks
  both directions, the second being the one that would have caught the original list on the day it
  rotted. Writing that scan reproduced the same failure one level down twice, which is why an argument
  it cannot resolve now fails the build rather than being skipped.
- **REL-7** — evidence-gated dead-code removal *(needs RT-KNIP first — see Gated)*.
## 📦 R28 — ONE PROJECT, ONE FILE *(research 2026-07-26; the model/project split)*

**The premise check first, because it changes the whole question.** The ask was "should we invent a
`.mass` file — a zip with everything inside, like a markup tool's bundle?" **We already ship one.**
`aec_api/bundle.py` defines `.mmproj` (`FORMAT = "aec.mmproj"`): one zip carrying the published
Fragments tile, the source IFC, **every project-scoped database row** — which is all 130 CRUD modules
*and* the proforma, since those are `project_id` tables — plus attachment blobs. Import mints a fresh
project id and remaps foreign keys, so a bundle clones or moves machines cleanly. The app's Open menu
already lists it. So the container is not the gap; **nobody could tell it existed** is the gap.

**And a standard already defines this shape: ISO 21597 (ICDD).** *Information Container for linked
Document Delivery* is a zip with `/Payload documents/` (the heterogeneous files), `/Payload triples/`
(RDF linksets joining them, at document **or object** level), `/Ontology resources/`, and an
`index.rdf`. Part 2 standardises the link types. That is precisely "model + construction data +
proforma in one file, with the relationships preserved" — and adopting it is the same bet this
platform already made with BCF: **a bespoke container round-trips with nothing; a standard one
round-trips with everyone.** ([ISO 21597-1](https://www.iso.org/standard/74389.html) ·
[Part 2: link types](https://www.iso.org/standard/74390.html))

**The real defect is conceptual, and it produced two shipped bugs.** Opening a *model* does not open a
*project*, and opening a *project* does not guarantee a *model*. In v0.3.703 that split surfaced twice:
the portal rendered "No project open" **while a model sat visibly loaded**, and the Developer tab
latched itself permanently empty. Both were repaired at the symptom. The cause is that "project" and
"model" are two states the app keeps having to re-marry, and every feature built on top inherits the
seam.

* **THE `@massing/embed` FACADE WAS EVALUATED AND DECLINED, 2026-08-23** *(the user delegated the
  call: "review it and pull it in if it's great and beneficial")*. Measured from the published
  tarball, not from a summary. **The reason is architectural:** the facade's load path is IFC text
  into a **browser-side tessellator** — `open(source)` sniffs bytes and the required `Tessellator` is
  `(ifcText: string) => {meshes, guids}`, with its own seam entry reading *"load a model into the
  kernel from IFC text"*. Nothing in the package knows about pre-converted Fragments. That collides
  with two non-negotiables — pre-convert on the server, never parse full IFC in the browser; geometry
  streams as `.frag` — so adopting it means either breaking them or keeping our load path outside the
  facade, which leaves both copies live: the fork their own plan calls the only risk that can end the
  project. Its ledger reports 20/20 movable and `ready: true`, but that test asserts each `covered`
  entry is reachable through the facade's **type** — it proves each claim is backed, not that the
  claims cover the ground, and its 24 entries are a dissection of this viewer as it stood ~2026-08-06
  against 129 files / 16,408 lines today. All 12 packages were published on 2026-08-08 and none has
  been touched since. **What would change the answer:** a Fragments-shaped load path, plus a seam list
  derived from this tree. Full reasoning in `CLAUDE.md`; the decision remains the user's.
* **R28-VIEWER ④** — the future viewer opens a **container**, not a file. **This is now live and
  external**: the kernel rebuild is `MassingCloud/massingifc` (private), first commit 2026-07-26 —
  a framework-agnostic kernel + plugin host with **all fourteen capability families still contracts
  only**. That is the cheap moment to settle this, and the window closes as families get implemented.

  Its persistence is per-**document** (`{schema, version, savedAt, data}`); there is no **container**
  concept, so "open a project package" would land as a plugin concern and be retrofitted. A container
  is a *mechanism*, which by that repo's own first design rule puts it in the kernel, with `.mmproj`
  and ICDD as adapters. Three further contract-level notes: **project↔model unity** wants to be a
  kernel contract or the v0.3.703 bug class returns; **selection and markup anchors must key on
  GlobalId**, never fragment-local ids, or every capability above inherits transient identity; and the
  **5D/4D contracts should carry provenance** (`quantity_source`/`rate_source`, and the 4D link being
  the task's *output*) rather than bare values. Also: that repo has **no LICENSE**, which needs
  settling before this public repo can depend on it.

**Sequencing.** ① first — it is the bug class, needs no dependency and no standard. Then ② which is
mostly surfacing what exists. ③ is now unblocked and is the interop play, not a prerequisite. ④ falls
out of ① and ③ and should gate the viewer rebuild.

---

### ⚙ PERF triage *(external static analysis, 2026-07-26 — verified against the code)*

An external analyser produced eight performance findings. Most of its **facts** check out; two of its
headline **recommendations** are backwards, and one finding examined nothing. Recorded so the wrong
fix does not get made later from the same report.

* **PERF-WORKERS ① — the cache story is duplication, not size.** Verified: `ifc_loader` caches 8 models
  (`@lru_cache(maxsize=8)`), `drawings._BAKE_CACHE_MAX` is 4, and `UVICORN_WORKERS` defaults to **4**.
  The analyser's advice was to *raise* both caches. **That makes the problem it identifies worse**: the
  caches are per-worker, so raising them multiplies resident memory by the worker count — its own
  finding ③ contradicts its finding ①. The real options are a bounded **shared** cache (a loader
  process or Redis-backed handle), or worker affinity so one model lives in one worker. Sizing is the
  last lever, not the first.
### 🐍 DDC ecosystem scan *(2026-07-26 — a Python construction-data org, 30 repos)*

Scanned at the user's request. The headline is a **licence trap worth recording**, because the
repository's own README states the wrong licence for its most valuable asset.

**The CWICR cost database — 55,719 work items, 27k resources, 30 regions, 21–31 languages — is
`CC BY-NC 4.0`, NOT `CC BY 4.0`.** The skills repo's README advertises it as CC BY 4.0; the actual
`LICENSE-DATA.txt` in the data repo is **NonCommercial**. That is the same exclusion class as the
PolyForm-NC library already refused above, and taking the README at its word would have put a
non-commercial dataset inside a commercial product. The repo's *code* is Apache-2.0 and fine; only the
data is encumbered. **Check the LICENSE file, never the README's summary of it.**

**⛔ Not usable:** the CWICR **data** (CC BY-NC 4.0) · the `cad2data` RVT/DWG/DGN converters
(**proprietary** — an explicit commercial licence, despite the repo reading as open) · an
open-source construction ERP (**AGPL-3.0**) · and roughly ten GPL-3.0 notebooks covering embodied
carbon, ML price prediction, quantity takeoff and estimation.

**✅ Permissive and worth reading:** a 221-file **skills corpus for construction AI agents** (MIT), a
**4D–5D pipeline** (Apache-2.0), **Revit/IFC project quality checking** (MIT), a CAD/BIM-to-code
pipeline (MIT), and an IFC/Revit ETL collector (MIT).

**What is actually worth taking, and it is not code.** We already have `.claude/skills/` and the
master-builder skill, and we already have `model_qa`, `qto`, `fived` and the 4D/5D spine — so none of
those repos closes a capability gap. What the 221-skill corpus *is* good for is a **map of what
construction teams actually automate**, at a granularity nobody publishes otherwise. Read as a
coverage checklist against our 130 modules it is a gap-analysis input, not an import.


* ⛔ **R22-PHOTO-CV defect detection — REFUSED IN PLACE**, the way semantic search was. Not a
  scheduling problem: a defect classifier needs labelled construction photos and this project has
  none. **One carve-out, recorded so the refusal is not read wider than it is:** concrete *cracks*
  specifically do have public datasets (SDNET2018 and several Mendeley sets, mostly CC-BY), so that
  one class is reachable by fine-tuning if it is ever wanted. Broader defect detection is not.
  Fine-tuning needs a few hundred labelled images per class, not the thousands a from-scratch model
  would — the earlier "months of labelling" estimate was costed against training from scratch, which
  nobody should do, and overstated the barrier.

**⛔ Licence exclusions recorded from this scan (evaluated, refused, do not re-litigate).** Two
otherwise-relevant OSS projects are unusable under the standing MIT/BSD/Apache-only rule: a GPU map-
rendering library under **PolyForm Noncommercial 1.0.0** (non-commercial only — incompatible with a
commercial product regardless of technical fit) and a physics/simulation library under **AGPL-3.0**
(the same class of exclusion that already keeps PyMuPDF out of the PDF stack). Two are permissive and
remain open as options: a **MIT** OpenCascade-based geometry kernel (C#/.NET — a process boundary, so
a real cost) and a **MIT** TypeScript canvas UI toolkit. Nothing in this ring depends on any of them;
the deterministic path above needs **no new dependency at all**.

**Sequencing — HISTORICAL, all of it shipped.** *Kept for the reasoning, not as work.* R27-SOV-LOOP,
R27-CLAIM-TYPE, R27-RISK-CALIBRATE, R27-FIRM-MEMORY and R27-LAYOUT ①→③ are all in
[roadmap-completed.md](roadmap-completed.md). The original plan: SOV-LOOP first as the smallest change
with the largest reach; LAYOUT as one track because ② and ③ are meaningless without ①; CLAIM-TYPE and
RISK-CALIBRATE independent and interleavable; FIRM-MEMORY last, being a data-scoping change that wanted
the org tier settled.

This paragraph is why the lane table went on advertising four shipped items after their entries were
archived: **a planning note mentions a code, and a mention is indistinguishable from an entry** to any
check that searches text. Marking it historical is the fix; the lesson is that prose naming an item
keeps that item looking alive.

---

## ✏️ R29 — AUTHORING-FEEL RING *(research 2026-07-29: pascalorg/editor + 4 comparators)*

**Why this ring exists.** The prompt was "pascalorg/editor has interesting authoring abilities — import
what is beneficial." The audit's finding is that **almost none of what is beneficial is code we can
import**, and the reason is worth stating up front because it decides the whole ring: our authoring is
not behind on *features*, it is behind on *feel*. Every edit round-trips to a server recipe. Pascal's
edits do not.

### What each source actually is — checked, not assumed

| Source | Licence | Verdict |
|---|---|---|
| [pascalorg/editor](https://github.com/pascalorg/editor) — 19.3k★, pushed 2026-07-29 | **MIT** ✅ | **Ideas only.** Stack is React 19 + Next 16 + R3F + **WebGPU** + Zustand + Bun. Adopting its packages means adding React, Next and a second renderer beside our pinned `three` 0.184 / `@thatopen` 3.4.x pair. Not a dependency decision — a rewrite. |
| [louistrue/ifc5cad](https://github.com/louistrue/ifc5cad) (IFChili) | **AGPL-3.0** + LGPL-3.0 WASM ❌ | **Excluded by the licence rule.** 66+ CAD commands on OpenCascade WASM, IFC5/IFCX serialisation at "Phase 0". May be read for ideas; **no code may be copied**. |
| [ThatOpen/engine_clay](https://github.com/ThatOpen/engine_clay) | **MIT** ✅ | **Reference, not dependency.** The obvious candidate — IFC-native modelling, same family as our stack. But: **not published on npm** (`@thatopen/clay` → 404) and **last commit 2024-10-09**, stopping mid-feature on *"first working version of exportable wall corners"*. Roughly two years dormant. |
| [three-bvh-csg](https://github.com/gkjohnson/three-bvh-csg) vs [Manifold](https://github.com/elalish/manifold) | MIT / Apache-2.0 ✅ | If client-side booleans are ever needed, **Manifold**, not bvh-csg. bvh-csg is far faster than BSP but its own docs concede the result "may not be correctly completely two-manifold" and point at Manifold for CAD. A non-manifold solid is an unquantifiable solid. |

**Two corrections to the first pass, recorded because both would have led somewhere wrong.** Pascal's
README describes no file formats, and the first read concluded "no IFC". It has an **IFC importer**
(v0.9.0, `packages/ifc-converter`) — but import only: IFC → its own node schema, exports as
GLB/STL/OBJ, and the export path was contributed from outside the core team. And a search result
described `@thatopen/clay` as having "active npm distribution"; the registry returns 404 and the
commit log is two years cold. **Both claims were plausible, both were wrong, and both were only caught
by fetching the artifact instead of the description of it.**

### What we already have — checked before proposing anything

Not a gap list until the premise is verified ([[check-the-blocker-premise]]). Already shipped:
SketchUp-style **inference snapping** (`inference.ts` — axis / parallel / perpendicular, pure and
unit-tested), a **transform gizmo**, **grid overlay**, `draftPanel`/`draftProxy`, **eight** server-side
edit engines (`edit_core`, `edit_enclosure`, `edit_struct`, `edit_mep`, `edit_annotate`,
`edit_asbuilt`, …) plus `edit_history`, a family/type system, and IFC-as-source-of-truth with
GUID-stable recipes. Pascal has none of that last part: its data model is bespoke JSON.

**So the honest framing is not "Pascal is ahead".** On what a building *is*, we are far ahead. On what
editing one *feels like*, it is ahead, and the difference is one architectural choice: it keeps a
local scene graph with dirty-node tracking and regenerates only the changed geometry in the render
loop, so an edit is visible in the same frame. We commit through a server recipe and republish.

### The ring — sequenced to sit BEHIND current work, and slice-able

Each item is independently shippable and none blocks the NOW list. **The commit path does not change:
the server recipe stays the writer of record and IFC stays the source of truth.** What changes is that
the screen stops waiting for it.

* ✅ **shipped v0.3.819** — A29-LOCAL-PREVIEW — *the edit shows before the server agrees.* The rule
  that kept it honest is the one this codebase already lives by: **a pending edit must look
  pending.** As built: the amber draft marker stays over the incremental one-element preview until
  publish completes, and a failed recipe turns it red in place instead of erasing the evidence. See
  [roadmap-completed.md](roadmap-completed.md).

> **⚠️ These three carried "SHIPPED" in their own text and no ✅ marker until 2026-08-06, and
> `roadmapStale.test.ts` could not have caught it.** That gate scans `services/api/src` and
> `services/data/src` for a module declaring itself an item's implementation — **Python only**. All
> three of these are TypeScript in `apps/web/src/viewer/`, so they were *structurally outside the
> population*, and the gate would have stayed green forever. Verified before marking: each has a
> module, a test, and a live import in `apps/web/src/viewer/app.ts` — `placeValid.ts`,
> `spatialSelect.ts`, and `draftHistory.ts` (note the last does **not** match its item name, which is
> why a filename-based check would also have missed it). Widening that gate to the web tree is filed
> as ROADMAP-GATE-TS.

## ⛔ Gated — each entry names its unblocking event

**~~Verification-gated~~ — THE GATE WAS FALSE (corrected 2026-07-25).** This block was held for
months on the claim that a "dev-preview geometry stall" stopped `buildPanels` from ever running. Two
things were actually true: `.claude/launch.json` had **no API entry**, so the dev backend was never
started; and `buildPanels` fetched elements *before* rendering, so a project with no model threw a
swallowed 404 and left the panel blank. With the `api` launch target and a published 52 MB IFC, the
Project Browser builds completely (Floor 0: 151 elements, Floor 1: 3). **Nobody had tested the
blocker.** Each item below is now to be re-verified against the live stack and moved to ▶ NOW as it
passes — not assumed blocked: 🧭 **R17 viewer tail** — CITE-JUMP *(S; click-to-expand claims jump the
viewer to the cited GUID)* · 4D5D-VIEWER *(M/L; schedule + cost bound to GUIDs → a 4D scrubber with a
running earned-value readout)* · WALK-MODE WebXR pass *(M; the `renderer.xr` headset half of the
shipped desktop walk)* · BCF-VIEWPOINT restore depth *(S; section planes + visibility exceptions +
the `toDataURL` thumbnail)* · CLASH step-through UI *(S)* · FILL-MATRIX frontend *(S)* · NODE-CANVAS
*(L; the reusable connector/node substrate)* · COLLAB selection halos.

**Binary/toolchain-gated:** **SPRINT A — ENERGY phase 2** — ship the EnergyPlus (BSD) / Radiance
(LBNL) binaries through the durable job queue and parse results back onto the model *(phase 1 —
gbXML + IDF export — shipped v0.3.655)* · ~~**RT-NODE-LANE** — CI is on Node 22; the **local** Node is
still 20.3.1 *(user action)*, then unpin eslint off 9.39.5, then Vite 6→7 behind a build benchmark
*(defer Vite 8/rolldown)*.~~

> **~~RT-NODE-LANE~~ — EVERY STEP IT NAMES HAS ALREADY HAPPENED (checked 2026-08-25).** The line
> above is kept struck through rather than deleted, because *how* it went stale is the useful part.
> Measured against the tree, not recalled: CI pins **Node 24** in all five workflows that set a
> version (`ci.yml`, `desktop.yml`, `mobile.yml`, `pages.yml`, `security.yml`), both manifests declare
> `"engines": {"node": ">=24"}`, eslint is **10.8.1** (pinned in the root `overrides` AND
> `devDependencies`, so it is unpinned from 9.39.5 in the only sense that matters), and Vite is
> **8.2.1** — the version this entry told a reader to *defer*. `apps/web/vite.config.ts` has been
> using Rolldown's native `codeSplitting` grouping for long enough to have survived one deprecation
> rename.
>
> **It was gated on a user action that the user had already taken.** The entry named a real blocker
> — a local Node too old to run Vite 7 — and nothing re-read it once that stopped being true; the
> *"(user action)"* tag is what made it un-owned, because a gate waiting on somebody else is a gate
> nobody re-checks. CLAUDE.md fixed its own copy of this number on 2026-07-29 and recorded that it
> had then been wrong **three times in three lines**; this is the fourth site, and it sat two
> sections apart from the "Outstanding USER actions" bullet that repeated it.
>
> **The generalisation is about gates, not about Node.** An entry blocked on an external event
> records the world as it was on the day it was written and has no mechanism to notice the event
> happening. Every other kind of staleness in this file eventually trips something; a gated item
> trips nothing, because not being worked on is its expected state.

**New-dependency-gated (needs an explicit OK):** **RT-BVH** — three-mesh-bvh for the raw-three
raycast paths *(already present transitively, MIT — instrument before adding)* · **RT-KNIP** —
unused-export / dead-dep scan *(feeds REL-7)* · **ifclite-geom** *(MPL-2.0, Rust wheel — see R23)*.
**~~W10-9 dimensional constraints~~ — UNGATED 2026-07-25.** It was held on *planegcs, LGPL*; the
licence survey found we never needed a full geometric constraint solver. `kiwisolver` (Cassowary,
**BSD-3**) covers the linear/alignment/equal-spacing/clearance set and `scipy.optimize.least_squares`
(**BSD-3**) the nonlinear tail. Now ordinary work — see **R23-CONSTRAINTS**.

**Spec-gated:** **SPRINT E — FAB-DELIVER phase 2** — byte-exact BVBS BF2D / DSTV-NC, held behind the
authoritative spec + a real importer/validator. *A wrong file mis-bends real steel.*

**Flow-gated:** **JOB-QUEUE PAdES** *(S)* — PAdES sealing on the queue needs a queued signing flow
first. · **REL-6 tail** — cargo-audit / gitleaks in CI when available.

**P3 — externally gated:**
- *Upstream:* IFC5/IFCX **geometry** write (web-ifc/Fragments write path) · bSI Validation Service in
  CI (service account).
- *Paid / flagged (never core):* VIZ-U1/VIZ-3/VIZ-4 presentation/VR builds · W9-7 AI PDF
  auto-takeoff · CODE-6 licensed code prose · COST-DB cloud ingest *(the offline importers ship)* ·
  DWG (ODA) / USD (pxr) export.
- *Platform/pipeline:* native mobile Capacitor shell (needs macOS/Xcode; the PWA ships) · SOC 2
  **cloud-infra** feature set (KMS/retention/residency — the readiness matrix itself shipped as
  R19 COMPLY-SOC2) · BMS/IoT telemetry (Brick/Haystack source required) · reality-capture progress
  quantification (capture data required).
- *Large optional builds (prerequisites complete):* coupled-frame FEM solve · viewer tile-streaming
  upgrade · AR field overlay · per-county location-factor/PPI DB tables.
- *Counsel-gated:* regulated syndication depth. ⚖️ Not legal advice.
- *Environment note:* headless/hidden panes stall the Fragments raycast + web-ifc import workers
  (vendor-level; the app-side timeout fallback ships). Verify those two paths in a visible tab.
## 📋 Outstanding USER actions (not engineering work)

- **Copyright deposit upload** — case 1-15213313031, still pending on the government account.
- ~~**Local Node 20.3.1 → 22**~~ — **DONE, and stale here for weeks.** The supported baseline is
  Node 24 (CI pins it; both manifests require `>=24`). See the RT-NODE-LANE note in ⛔ Gated.
- ~~**`fix/cloud-domain-allowlist` — an unmerged SECURITY fix**~~ — **MERGED as PR #339, and it
  landed on `main` while this audit was still running.** Found 2026-08-25 by walking the remote
  branches: `AEC_OAUTH_ALLOWED_DOMAINS` was enforced in `routers/auth.py` only, so a restriction
  held on four sign-in doors and was bypassed by the massing.cloud one. It now hoists the check into
  `oauth.domain_allowed()` and calls it from both.

  **Two things about it are worth keeping.** First, it is the reason this branch had to merge `main`
  mid-session: `main` shipped its own **v0.3.1090** at the same time, which collided with the
  number this branch had already used, and every release here shifted up one. *The ship-release
  guidance says to fetch before bumping precisely to avoid that race; fetching once at the start of
  a long session is not the same thing.* Second, `oauth.domain_allowed` and this branch's
  `auth.get_or_create_sso_user` are **two independent fixes to the same two functions**, made in
  parallel by different sessions, and they composed cleanly — verified after the merge by checking
  both are called at both doors rather than by trusting git's silence.
- **Stale remote branches — 38 of 40 are fully merged into `main`** and can be deleted whenever you
  like; `lock/cve-floors-2026-08-09` looks unmerged but is **superseded**, not pending (`main`
  already carries `pypdf>=6.15.0`, `cryptography>=50.0.0` and the transitive-floors block, and the
  lock resolves to exactly those). Checked before reporting, because an unmerged branch named for
  three CVEs is precisely the kind of thing that reads as an open hole when it is not.
## Non-goals (documented rationale — not gaps)

`.mpp` parsing (XML/CSV import is the path) · custom Revit plugin (certified `revit-ifc` covers it) ·
live ENERGY-STAR/BAS integrations (flagged stubs only) · CAFM/1031 tooling · scraping code prose ·
GPL/AGPL vendor code (reimplement techniques) · **LLM/OCR reconstruction of unstructured docs**
(offering memoranda, scanned T-12s, rent-roll PDFs, leases — we ingest structured exports, and the
deterministic engines are what make the numbers defensible) · prompt-library / workflow-count framing
(a way of using an assistant, not product surface) · owning capture hardware / photogrammetry
pipelines / hosted digital-twin cloud · native VR-headset app + cloud co-presence sync · payment
execution + financing rails · consumer marketplaces · learned risk forecasting (Monte Carlo covers
it) · voice agents. Deliberate 501 bridges (money movement / KYC / paid APS) are a compliance
pattern, not gaps. Integrate-not-build: Cesium ion imagery · Speckle Automate · iTwin REST ·
Autodesk APS · Pollination.

**INTEGRATE (optional, feature-flagged, offline-degrading — never a runtime dependency):**
higher-coverage permit backend · contractor license/history feed · permit-density market-activity ·
new-home starts/pricing feed · named BCF-hub connectors · national e-ID/e-sign · ERP connectors ·
paid comp / market-data feeds and county-recorder pulls behind the existing `opendata.py`
indirection.

**License guardrails:** ifcopenshell/geom = LGPL (safe dep) · no AGPL (no PyMuPDF) · planegcs (LGPL,
extractable) over GPL solvers · CC0/CC-BY assets vetted per-asset · OSM = ODbL attribution as a
separate layer.

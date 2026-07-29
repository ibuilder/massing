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

**Status — reconciled 2026-07-29 at v0.3.778.** CodeQL **0** open (queried from the alerts API, not
inferred from a green run) · backend **423** suites · vitest **715** (incl. vendored kernel + PDF
engine) · `test_reachable` **301/305** modules callable · single-source version in
`apps/web/package.json` · all 18 CI runs green across v0.3.776–777.

*The previous status block claimed 416 / 557 as of v0.3.740 — thirty-eight releases stale. A status
line nobody re-derives is just an old measurement wearing the present tense.*

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

## ▶ NOW — parallel lanes *(rebuilt 2026-07-29 at v0.3.785)*

The previous NOW list — eight items, v0.3.773–777 — is closed and archived in
[roadmap-completed.md](roadmap-completed.md). Seven shipped; **R27-UW-PANEL was closed unbuilt**
because its premise did not survive the offline constraint, recorded rather than deleted so the idea
is not re-proposed next quarter.

**This section is organised by LANE rather than by priority, because the constraint changed.** Four
sessions work this repo concurrently. A single ranked list is the wrong shape for that: it serialises
work with no reason to be serial, and — as happened twice on 2026-07-29 — it leaves finished work
sitting uncommitted in a shared tree while somebody else edits around it.

### How to use this

1. **Claim a lane, not an item.** Lanes are disjoint by *file path*. Two sessions in one lane collide;
   two in different lanes do not.
2. **Land what you finish.** Do not leave completed work dirty in the tree — it is one `git add -A`
   from being committed by someone who has not read it.
3. **Version files and CHANGELOG belong to whoever holds the release**, not to the lane. Ship without
   them and let the batch pick them up, or take the release yourself — but say which.
4. **Check the premise before building.** Six of seven roadmap premises checked on 2026-07-28 were
   wrong. See the Practice note below; it has cost more than any other habit here.

### The lanes

| Lane | Owns these paths | Open work |
|---|---|---|
| **A · Shell & IA** | `apps/web/src/shell/`, `portal/`, `main.ts` | A29-SPATIAL-SELECT · nav/IA follow-ups |
| **B · UI & panels** | `apps/web/src/ui/`, `portal/panels/`, `field/`, `reportCenter.ts` | R24 tail — BASELINE · CHARTS-GRAMMAR · EMPTY-GUIDE ② · DENSITY ② |
| **C · Backend engines** | `services/api/src/aec_api/` (non-router) | R22 / R23 rings · R27-FIRM-MEMORY follow-ons |
| **D · Geometry & drawings** | `services/data/src/aec_data/` | R21 ring · R27-LAYOUT tail |
| **E · Authoring feel** | `apps/web/src/viewer/`, `inference.ts` | R29 ring — A29-LOCAL-PREVIEW ① · A29-PLACE-VALID ② |
| **F · Docs & demo** | `README.md`, `docs/`, `apps/web/src/demo/` | keep the shipped surface honest (below) |

**Shared files that need a heads-up before editing.** Every multi-session conflict so far has been one
of these: `services/api/run_tests.py` · `services/api/src/aec_api/main.py` · `docs/roadmap.md` ·
`CHANGELOG.md` · the three version files (`apps/web/package.json`, `src-tauri/tauri.conf.json`, and
`package-lock.json` — which is regenerated, never hand-edited).

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
* **Still genuinely open:** nobody has read the walkthrough end-to-end against the *seven*-room spine
  introduced at v0.3.796 (`deal · design · planning · schedule · cost · work · operate`). Room COUNT
  is gated; room ORDER and the Operate room's content are not.

`docsCurrent.test.ts` gates **10** assertions across `README.md` and `docs/walkthrough.md` — shell
flags in both directions, every room appearing in the README, the retired three-tab nav, the vitals
strip, what a sample *is*, deleted samples, and rooms the product does not have. That is more than
"a handful", and it is why two of the three items above closed themselves. **It should still gate
more:** every doc sentence naming a flag, a count or a room is a claim that can rot, and the ones
that rotted were all sentences no test read. Note for whoever extends it — the file lives in
`apps/web/src/shell/`, which is **Lane A**, not Lane F.

### Decisions, not effort — these want your call
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
- **QUALITY-ROOM** — inspections/ITP sit in Design because an inspection checks the built thing
  against the design. Answered 2026-07-28: the *task* already reaches Work via the queue
  (`INS-001`, `DEF-001`, `NCR-001` are in it now), so the *register* stays with its discipline.
  Revisit only if that stops feeling right in use.
- **Branch protection** — `main` is unprotected and public. Blocking force-push and deletion costs
  nothing and is not reversible after an accident.
- **R26-V-TIMING** — needs real users. **Plugin pricing** — needs customers. Both correctly parked.

### External analysis tools — reviewed 2026-07-29, mostly NOT actionable *(CodeFlow · Repowise)*

Two third-party analyses were reviewed in full. **Neither produced work worth doing**, and the reason
is worth recording so the next person does not re-run the exercise or, worse, act on the numbers.

**[CodeFlow](https://app.getcodeflow.com/github/ibuilder/massing) — remove it or scope it. This is a
user decision, and it is the one real outcome of this review.**

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
* **It fails on every PR.** A permanently-red check is worse than no check: it teaches everyone to scroll
  past red, which is how a real failure gets waved through. It nearly did here — five PRs were reported
  as failing when only #98 had a genuine CodeQL HIGH.

**[Repowise](https://www.repowise.dev/s/5ad6b7549ac4/overview) — reading a snapshot 426 releases old.**

It has indexed **`f3b171f` = v0.3.363**; main is **v0.3.789**. Every count it reports (881 files, 6,587
symbols, 2,771 findings, 45 dead exports) describes a codebase that no longer exists. Same failure as
the demo snapshot: **a capture rots and nothing fails when it does.** Re-index before quoting any figure.

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


## 🏗 R21 — LOD 400→500 DOCUMENTATION RING *(from a real LOD 400 shop-drawing set, 2026-07-25)*

Measured against an actual issued wall-section + detail package (13 sheets, 1:100 → 1:10) rather than
against a description of one. The mission is **acquisition → turnover at LOD 500**, and LOD 500 is
field-verified as-built — but a project only *reaches* verification through an issuable LOD 400 set.
These are the gaps between what the platform draws today and what that package contains.

**Tier 1 — the set cannot be issued without these**

- ◧ **R21-4D-CLASH** *(phase 1 shipped v0.3.682; install-before-support still open)* — **sequence clash**: two trades occupying one space in the same schedule
  window, or an install ordered before its support. The 4D timeline and CPM both exist; this reads
  them together.

  **Phase 2 needs a prerequisite that does not exist**: `schedule_activity` carries no element
  GlobalId, so nothing knows *what a task installs*. Install-before-support cannot be computed
  without a real **task→element binding** — that binding is the actual next piece of work, and
  approximating it (by trade, by name match) would produce confident findings nobody can trust.
- **R21-MULTISCALE** *(S)* — several viewports at **different scales** on one sheet (1:100 overall +
  1:50 parts), each with its own title/scale block. `sheet_layout.py` composes viewports; per-viewport
  scale is the missing parameter.
- **R21-SPACE-TAG-SECT** *(S)* — room names on sections (CLINIC 1, IP RM., DAY CASE RM.). `space_tags`
  exists for plans; sections need the same treatment against the cut plane.
- **R21-DIM-COMPONENT** *(M)* — component-level dimension strings beside the floor-to-floor chain
  (cladding offsets, insulation thickness, canopy projections), which is what a fabricator measures.

*Why this ring and not more content:* the family shelf now clears every typology (v0.3.670), so the
binding constraint on "can a user take this to LOD 500" moved from **what can be modelled** to
**what can be issued and then verified**. R21 is the issuable half; the LOD-500 verification half
shipped in v0.3.673.

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

- ⭐ **R22-PRODUCTION** *(L)* — **field production tracking against model quantities.** Crews claim
  installed quantity against an element GUID; percent-complete, pay-app line, 4D status and EAC all
  update from that one entry. Field-capture competitors do this *without* a model, reconciling to
  cost codes by hand. This is the specific feature that makes LOD 500 pay for itself, and it closes
  the loop between the QTO we already generate and the EAC we already compute.
- **R22-ENTITLEMENT** *(M/L)* — **permit & entitlement workflow**: jurisdiction submittal packages,
  review cycles, comment responses, and **conditions of approval carried into the model as
  constraints**. Today there is a hole between "acquisition" and "construction" in our own mission
  statement — we underwrite the deal and we build it, and nothing spans approval.
- ⭐ **R22-AGENT-PACKS** *(M)* — **named agent packs + org "Skills" + a governance console** over the
  MCP layer we already ship. We expose raw capability; the market ships "Submittal Review Agent",
  which a superintendent understands. Pure packaging of existing tools, plus per-run audit logging —
  the gating factor for enterprise adoption. Our version reads the IFC, so a submittal check can test
  the submitted product against the element's *specified properties* rather than against a PDF.

**Tier 2 — evidence, provenance and procurement**

- **R22-ITP-NCR** *(M)* — **quality module: ITPs, hold/witness points, NCR lifecycle**, attached to
  elements. This is precisely the evidence chain COBie turnover is meant to hand over and currently
  cannot assemble — and it is the natural feeder for LOD-500 verification.
- **R22-PROVENANCE** *(L)* — **cite to file, page and revision.** Every proforma assumption, estimate
  line and agent answer traceable to a source page. Three of thirteen platforms *lead* with this; it
  is what makes AI output admissible in an IC memo or a claim.
- **R22-NOTICE-CLOCK** *(S/M; **PR #95** — `notice_clock.py` + `routers/notices.py`; adds
  `notice_family` to `prime_contract` and `occurred_on`/`became_aware_on` to `change_event`)* —
  contractual notice clocks / time-bar tracking. Detect a triggering event in a daily log or RFI,
  start the contract's notice period, draft the notice. Highest dollar-per-line-of-code feature in
  construction administration; we already hold the contract calendar and the daily record.
- ⭐ **R22-CLASSIFY-AI** *(M; **PR #97** — `classify_assist.py` + `routers/classify.py`)* — assisted
  classification of *imported* IFC. Propose codes, human confirms.
  **The premise was wrong in a way that makes this more urgent, not less** (corrected 2026-07-29 while
  implementing it). The entry said an unclassified model "gets nothing" — a visible, harmless failure.
  It does not. `classification.classify()` returns a `(code, title)` for **any** `ifc_class`, silently
  falling back to the default bucket when unmapped. So an imported proxy-heavy model prices everything
  as *01 00 00 General Requirements* while the estimate reports a **complete takeoff**. That is not a
  gap, it is a confident wrong number — the same shape as the `get_area` defect ([[qto-measured-area]]):
  a fabricated value is worse than a missing one because nothing downstream can tell. #97's coverage
  figure therefore counts only what the model **declares**, never what the fallback supplied.
  *The IfcClass half is already built and routed* (`ifc_classify.py` via `conceptual.py`).
- **R22-PROCURE-DEPTH** *(M)* — sub **prequalification** (bonding/EMR/capacity), **contract-clause
  risk extraction**, and **vendor scorecards persisting across projects**. Bid leveling covers one
  step of five.
- ✅ **R22-MEMORY** *(**PR #104**, merged 2026-07-29 — `unit_rate_memory.py` is on `main`)* —
  **two-thirds already built.** Verified 2026-07-29
  by reading the file, not the entry: `benchmarking.cost_benchmarks()` already mines `direct_cost`
  records **across all the caller's projects** and returns a low/p25/median/p75/high distribution per
  **cost code**, with a `min_samples` floor, routed via `routers/benchmarking.py`. Cross-project
  pull-planning stats, RFI/submittal response rates and space utilisation are there too. So *"every
  bid result makes the next estimate better"* is true today at the cost-code level.
  **What is missing is exactly the half the entry called the differentiator.** `grep -i
  "qto\|quantity\|unit_rate\|guid" benchmarking.py` returns **zero**. It knows what a cost code cost,
  never what it cost **per measured unit** — and a cost-code distribution is what anyone with an
  accounting export can build. `$/m² of IfcWall, from our own actuals, cross-project` is the part
  that needs the QTO spine and the part that does not exist.
  **Remainder, correctly sized:** *unit-rate memory* — join `direct_cost` actuals to the estimate's
  measured quantities so the distribution is per unit rather than per code.
  **Shipped in PR #104** (`unit_rate_memory.py`): cost ÷ **installed quantity**, joining `direct_cost`
  to `production_quantity` — two modules owned by different engines that had never been read together.
  Rates are computed **per project then distributed**, never Σcost ÷ Σquantity, which is a weighted
  average wearing a distribution's clothes; the pooled figure is reported alongside and labelled. Units
  are grouped, never converted. A review caught the totals being summed from **display-rounded** values
  — 6000.00 against a true 6000.30, and a pooled rate contradicting the formula printed beside it;
  aggregates now come from raw values, mutation-checked.
  *Third entry in one day whose estimate was set by a description that had drifted from the code, and
  the third distinct flavour: R23-RECIPE-ARTIFACT said "already is X" and nothing existed;
  R22-CLASSIFY-AI described a harmless failure that was really a confident wrong number; this one
  describes an unbuilt feature that is mostly shipped. All three were visible only by opening the
  file.*

**Tier 3 — on-ramps and reach**

- **R22-CAD-IMPORT** *(M)* — **DWG/DXF/PDF base-plan import.** The existing building stock is legacy
  CAD; today feasibility and test-fit only run on models we authored. This is the on-ramp for every
  non-BIM firm.
- 🔜 **R22-CARBON-OPTION** *(M; **PR #106 — OPEN, not merged as of 2026-07-29 22:20Z**)* — built and
  awaiting merge; `option_carbon.py` is on the branch, **not** on `main`. The premise was right about
  the capability and wrong about its REACH. `option_score` already scored **generated** massing variants
  on carbon, `option_takeoff.embodied()` computed it bottom-up, `carbon.py` rolled up a whole project —
  and `design_options.compare()`, the card a project keeps its schemes on, had none. `energy_eui` was
  not standing in: that is **operational** energy, a different lifecycle stage. Every row now states its
  basis — `declared` / `benchmark` / `unavailable` — and unmeasurable options are listed but never
  ranked, because an option with no area is not an option with zero carbon. The intensity table is
  **imported** from `option_score`, never copied, and a test asserts this module defines none of its own.
- ✅ **R22-ACCT-SEAM** *(M; already shipped — verified on `main` 2026-07-29, no new code)* — the seam
  exists in full and the entry had simply not been re-read. Outbound: `accounting.py` (GL CSV,
  QuickBooks IIF bills, journal entries, trial balance, approval-gated frozen batches). Inbound:
  `imports.py` (generic CSV/Excel → any module, incl. `direct_cost`) + `fin_ingest.py` (budget↔actuals
  two-way reconcile on the cost-code spine, unmatched surfaced BOTH ways and never netted, plus import
  lineage). Credentials: `connectors.py` (quickbooks / sage-erp / procore / acc). All routed via
  `routers/accounting.py`, and `test_accounting.py` **value-checks** the double-entry invariant exactly
  — `abs(dr - cr) < 0.01 and abs(dr - 125000) < 0.01`, not a range. **Remaining and genuinely blocked:**
  a live API *pull* needs real credentials, so it belongs in the gated table, not the open list.

  *Reporting "already covered" was the deliverable here.* The session that checked went in expecting to
  add a missing double-entry balance gate, found the assertion already exact, and wrote nothing rather
  than landing a redundant gate so the day would show a commit. That is the right call and the harder
  one.
- **R22-OPTION-OBJECT** *(S/M)* — make **option the primary object**: geometry + unit mix + cost +
  carbon + IRR as one comparable record, so no massing is ever evaluated without its returns.
- **R22-ENTITLE-RISK** *(S/M; **PR #99** — `proforma/entitlement_risk.py` + `POST /proforma/entitlement-risk`;
  no new module, no migration)* — approval probability + entitlement duration in the Monte Carlo.
  The largest unmodelled uncertainty in any acquisition proforma.
  **Premise corrected 2026-07-29 during implementation — the entry reads "add two inputs" and the
  truth was "the model has no place to put either":**
  * `Timing` has **no pre-construction period at all** (`construction_months` / `leaseup_months` /
    `hold_years`). The 6–30 months between buying a site and being allowed to build on it were not
    merely unpriced, they were **unrepresentable**.
  * `monte_carlo` samples only **continuous** drivers onto dotted paths, so a **binary** approval
    event could not be expressed in the first place.

  **The design decision a reader will want to argue with, so it is recorded rather than buried: a
  denied entitlement is NOT modelled as a bad IRR.** The draw is not solved at all. Pushing *"the
  building was never built"* through a solver that assumes construction proceeds produces a number,
  and that number then sits inside the P5–P95 of a distribution describing **a project that does not
  exist** — the same class of defect as `get_area` and the classification fallback, where a
  fabricated value survives review that a missing one would not. The consequence is the whole point:
  on the sample deal the 15% hurdle clears **1.00 conditional on approval and 0.58 unconditional**.
  A proforma that only ever reports the conditional figure is not being optimistic, it is answering
  a different question than the one the investment committee asked.
- **R22-REPORT-BUILDER** *(M)* — no-code report/dashboard builder. 132 modules of structured data
  with no end-user query surface means every custom report is an engineering ticket.
- **R22-PIPELINE** *(M)* — **multi-site pipeline dashboard** above the project workspace. Acquisition
  is a funnel, not a project.
- **R22-ROUTINES** *(S)* — **scheduled agent runs** (monthly progress report, weekly schedule-risk
  scan) rather than on-demand only. Turns AI from a tool you remember to use into infrastructure.
- **R22-PM-CONTRACTS** *(M)* — **preventative-maintenance contracts from turnover data.** The COBie
  asset register, warranties and service intervals become billable recurring PM contracts. Extends
  past turnover without breaking the mission; nobody in the scanned set does it from model data.
- **R22-PUBLIC-VIEWER** *(S)* — zero-signup public model viewer + shareable option links. Cheapest
  possible top-of-funnel for an open-source product.

**Deliberately NOT taken:** crew/equipment dispatch, payroll, inventory, and a general ledger. Those
are mature, crowded, low-margin categories with a decade of incumbency. **Prefer seams to
reimplementation** — R22-ACCT-SEAM exists precisely so we never write a GL.

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

- ⭐ **R23-CONSTRAINTS** *(L)* — W10-9 via **scipy's `least_squares`, which is already a dependency**
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
- **R23-STOREY-LOD** *(L)* — server-side coarse proxies per storey (extruded footprint / AABB) for
  small parts, MEP and furniture, swapping to real fragments on demand. Server-side keeps it
  deterministic, offline and $0. *`docs/internal/archive/phase2-large-models.md` claims no custom LOD is needed and is
  itself marked superseded — that claim is the thing to retire.*
- **R23-PICKING** *(M)* — ⚠️ **premise corrected 2026-07-25; do NOT build this on the stated evidence.**
  The scan read the 1500 ms `Promise.race` at `viewer/app.ts:337` as "an admission that picking latency
  already hurts". The source says the opposite, in its own comment: the race guards against *a stalled
  Fragments worker (hidden tab / heavy load)* silently eating clicks, and states plainly that **normal
  raycasts answer in ms**. It is a resilience guard, not a latency workaround, and there is currently
  **no measurement showing picking is slow at all**.
  GPU ID-buffer picking (scissored 1×1 target, O(1) in polygon count) remains a real technique and
  three-mesh-bvh is present transitively (MIT) — but this is now gated on **measuring raycast latency
  on a genuinely large model first**. If the measurement does not justify it, the correct outcome is to
  close this item unbuilt. *Fourth false premise found this session; see [[check-the-blocker-premise]].*
- **R23-DIGEST** *(M; **PR #94** — `routers/digest.py` + `aec_data/model_digest.py`)* — a deterministic
  multi-scale model digest (project → storey → zone → system → element) as compact JSON. Immediate
  non-AI value as a **diffable change-detection snapshot** between IFC versions; becomes the retrieval
  index if AI features land.
- **R23-RECIPE-ARTIFACT** *(M; **PR #98** — `recipe_log.py` + `routers/recipes.py`)* — versioned,
  diffable, exportable, replayable edit history.
  **Premise corrected 2026-07-29 during implementation: it was NOT already a CAD operation timeline.**
  The entry claimed formalising an existing thing. In fact `edit_history.json` is a stack of **file
  paths**, and the audit log records an edit's **outputs** (`/edit`) or merely recipe **names**
  (`/edit/batch`). **The parameters were nowhere**, so replay, diff and export had nothing to rest on.
  #98 records the missing half rather than formalising a present one — which is why it needed four
  capture hooks in `routers/authoring.py` rather than a serialiser.
  *Worth generalising: "it already is X, just formalise it" is the single most expensive kind of
  roadmap sentence, because it sets the estimate before anyone opens the file* ([[check-the-blocker-premise]]).
- **R23-BATCH-OVERLAYS** *(S)* — app-authored overlays (pins, grid, snap markers, dimensions, clash
  markers) use **zero** instancing; `three@0.184.0` has `BatchedMesh`. Keep the default BIM pass off
  `MeshStandardMaterial` (presentation mode only); make FOV/FAR responsive by viewport class.
- 🔜 **R23-GLTF-COMPRESS** *(S/M; **PR #105 — OPEN, not merged as of 2026-07-29 22:20Z**)* — built and
  awaiting merge; `gltf_export.py` + `test_gltf_compress.py` are on the branch, **not** on `main`.
  Shipped in two halves, split by what each costs the consumer. **Per-mesh index width** is free and on
  by default: measured first, indices were **60%** of a 175 KB export and every mesh was far under the
  ceiling, so a fixed uint32 was paying double. uint16 is core glTF 2.0 — no extension, ~30% off every
  export, nothing to check on the reader. **Draco is opt-in** (`draco=True`): 42,592 B → 5,040 B
  (**88%**), but `KHR_draco_mesh_compression` is *required*, not optional, so a consumer without the
  decoder reads nothing. Verified against **headless Blender 3.5**, which decodes Draco; trimesh does
  NOT, and returns the right vertex and triangle counts with every position at (0,0,0) while raising
  nothing — see the note under R22-ACCT-SEAM on what an independent-reader check actually proves.
  `DracoPy==1.7.0` pinned in `requirements-dev.txt` on the branch — 2.0.0 ships **Windows wheels only**,
  and `requirements.in` would force a hash-lock recompile. Shipping it in the API image is a
  `requirements.in` line + a Lockfile-workflow run, not done here.
- **R23-SYMBOL-COUNT** *(M)* — deterministic template-match symbol counting in the **existing** pdf.js
  takeoff worker: mark one instance, normalised cross-correlation, non-maximum suppression.
  **Zero new dependencies**, offline, auditable — which matters for quantities that feed a bid.
- **R23-PREFAB-KIT** *(M; **PR #96** — `prefab_kit` module, 133 total, + an Alembic revision)* — a
  prefab kit is a `query_dsl.select()` scope + BOM + pull-plan task + delivery date. A join across
  spines we already have, not a new engine. Strong LOD-500 fit: kits are what actually get
  field-verified.
- ✅ **R23-JURISDICTION-PACKS** *(M; **PR #101**, merged — `jurisdiction_packs.py` +
  `routers/jurisdiction.py`)* — jurisdiction-scoped data-requirement rule packs. The shape was there
  and the scoping was not: `rule_library` rules are per-project and hand-authored, `ids_authoring`
  builds from a *use case* rather than a place, and `Project.jurisdiction` already resolved the IBC
  edition while nothing read it for **data** requirements. Requirements are `rule_library`-shaped and
  run through `rule_library.evaluate()` — the same evaluator, not a second one.
  **Ships no regulatory claims on purpose:** one built-in `example` pack attributed to nobody, and
  `authority` / `edition` / `source` required to store a real one, because a requirement nobody can
  trace is indistinguishable from one somebody made up — and this pack fails other people's models.
  Two defects its own tests caught, both the same shape: the example pack used
  `Pset_WallCommon.FireRating`, which *parses* as a bare-field test, matches nothing, and passes on
  every model forever (now refused at import — a rule that cannot fail is worse than a missing one);
  and the fixture invented a flat pset shape when the index nests under `psets`.
  **Its authz hole is the more useful legacy** — see SEC-GLOBAL-AUTHZ under Decomposition &
  reliability.

**Watch, not work:** WebGPU (`WebGPURenderer` exists in the pinned three, but Fragments targets WebGL
— 2–3 year horizon) · browser-side IFC parsing (a streaming WASM parser now exists; server-side
pre-conversion still buys caching, GUID-stable recipes and offline tiles, so the non-negotiable holds).

**DECLINED 2026-07-25 — do not revisit without a new reason.** `ifclite-geom` is **MPL-2.0**, which
is off the stated MIT/BSD/Apache list, and its **99.9% agreement is not bit-identical**. It could only
ever have accelerated `world_bounds` and the clash AABB pre-pass — a narrow win — while adding a
file-level-copyleft Rust binary wheel and a second geometry answer that must be reconciled against the
first. A determinism guarantee is worth more than a bounds speed-up. *Original note kept below for the
record:* `ifclite-geom` as an *accelerator only* for
`world_bounds` and the clash AABB pre-pass. It is **MPL-2.0 (file-level copyleft, not on our
MIT/BSD/Apache list)**, a new Rust binary wheel, and **99.9% agreement is not bit-identical** — so it
must never touch drawing generation, which has to stay deterministic. Would ship behind a flag with a
per-GlobalId AABB cross-check against the ifcopenshell path.

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
| 04 | long jobs, foreground UI | R24-JOB-TRAY | ❌ **and cheaper than logged** — see below |
| 05 | analyses are modals → no history | R24-RUNS-INBOX | ❌ no runs concept in the web app |
| 06 | the single-GUID advantage is invisible | R24-ELEMENT-CARD | 🟡 `viewer/lifecycleStrip.ts` + `inspectorTabs.ts` are built and good, rendered from **one** call site (`viewer/app.ts:321`) |
| 07 | onboarding teaches the chrome | FIRST-RUN | 🟡 improved v0.3.777; still not the lot → building → deal chain |
| 08 | persona picker only relabels | *(none)* | ⚠️ reversed on purpose — see Decisions |
| 09 | tools panel mixes verbs with analyses | *(none)* | ❌ dropped in transfer → `R24-TOOLS-SPLIT` |
| 10 | finance numbers have no provenance | R24-TRACE-UI | 🟡 v0.3.775 shipped trace for *cost coverage*; the proforma chain (IRR ← NOI ← rent roll ← area ← GUID) — the audit's actual demo — is not built |
| 11 | density | R24-DENSITY | 🟡 two steps not three (`portal/prefs.ts:71`), dashboards only, **not registers** — which is where the 8-hour user lives |
| 12 | mobile is a bottom sheet in a desktop IA | R24-FIELD-MODE | 🟡 `field/field.ts` is a real offline queue with GPS, still inside the desktop IA |
| 13 | search is scoped to modules | R24-CMDK-VERBS | ❌ **measurably** — see below |
| 14 | empty states | R24-EMPTY-GUIDE | 🟡 `ui/empty.ts` is 24 lines, "no project" only |
| 15 | charts have no grammar | *(none)* | ❌ dropped → `R24-CHARTS-GRAMMAR` |
| 16 | Report Center is a list of nouns | *(none)* | ❌ dropped → `R24-REPORTS-BY-MOMENT` |
| 17 | three vocabularies collide | R24-TERMS | ❌ open |
| 18 | site promises a lifecycle, app opens on a shell | *(none)* | 🟡 R26-VITALS (v0.3.773) is arguably a **better** answer than the audit's lifecycle strip — treat as closed |

**External corroboration** (13-platform UI scan, 2026-07-29). Procore's design system evaluates
office and field as **separate** UX, not one responsive layout — independent support for #12. Solibri
beats Navisworks on IFC by making rulesets and checks **durable first-class objects**, and ACC's
answer to breadth is **saved, re-runnable, shareable** searches — both are the same shape as
`R24-RUNS-INBOX`, and it is the most externally validated item in the ring. LayOut 2026's tray
redesign drew open backlash ("bulky, less legible and inefficient", broken shortcuts) — density is a
**regression risk**, not a taste call, which is why `R24-DENSITY` ships as a user switch and why
`R24-KEYS` is not optional. Bluebeam Revu 21 deliberately did **not** restyle and invested in
customizable profiles instead. And two conclusions worth keeping: **no incumbent ships a command
palette as a primary entry point** — a real opening, and a warning that ⌘K must be *taught*, not just
bound — and **none of them can trace a number to a GlobalId**. That is the moat and it is still
uncashed.

---

### Sprint 1 — instrument, then decide *(the audit's phase 0, never built)*

Everything after this sprint is a claim about adoption. Nothing in the stack can currently confirm or
refute one, so this goes first even though it is the least visible.

- ✅ **R24-BASELINE** — **SHIPPED**: `baseline.py` + `GET /admin/baseline` (admin-gated, cross-project).
  **Three of the six are measured, three refuse — and the split is the finding.** The entry listed six
  metrics as though they were one kind of thing:
  - **Derivable from `record_activity`** (every create/update/transition already carries an actor and
    a timestamp): *rooms touched per user per week* (module → section → room via `rooms.room_of`, so
    it cannot drift from the rail), *field captures per super per day*, *median RFI turnaround*
    (paired transitions into `open` then `answered`).
  - **`available: false` with a reason**: *time-to-first-meaningful-action* and *p95 **interaction**
    latency* are client-side — no server event marks either end; *"where is X" support threads* lives
    in a support inbox this product cannot see. A client measure faked from a server proxy reads like
    the target and answers a different question, which is precisely how a shell nobody can score gets
    shipped with a dashboard.

  Two things fell out of building it. **`http_request_duration_seconds` was `_sum`/`_count` only** —
  that is a *mean*, and a mean cannot answer the p95 R24-PERF-BUDGET asserts, so a latency
  **histogram** was added with 0.1 s as a deliberate bucket edge. And an unanswered RFI is excluded
  from the numerator and reported as `open_unanswered` rather than counted as zero days — the same
  defect shape as the draw priced at zero. Tests are **value-checked against hand arithmetic**, not
  range-checked, and mutation-checked both ways.

- ⭐ **R24-PERF-BUDGET** *(S)* — **now measurable**: `metrics.quantile(0.95)` reads the histogram
  above. The remaining work is the asserted budget itself (100 ms click echo, 1 s panel, p95 < 100 ms)
  as a `test_*`, per *Verify, don't recall*. Note what the server can and cannot say: request p95 is
  server-side and now real; **click-echo latency is client-side and still needs a beacon.**
- **R24-PERF-BUDGET** *(S, reinstated)* — the audit's P5: 100 ms click echo, 1 s panel, p95 < 100 ms.
  Write it as an asserted budget, not a hope — prose drifts, `test_*` does not (see *Verify, don't
  recall* in CLAUDE.md).
### Sprint 2 — cash the moat *(the differentiation no competitor can copy)*

- ⭐ **R24-ELEMENT-CARD ②** *(M — was L)* — the strip exists and works. The remaining work is
  **call sites**, not components: render it in RFI, estimate line, pay app and COBie row. Extract from
  `viewer/inspectorTabs.ts` into a viewer-independent module first, since those four surfaces must not
  pull in three/@thatopen.
- ⭐ **R24-TRACE-UI ②** *(**L, and BACKEND** — re-scoped 2026-07-29 after a premise check)* — make the
  **proforma emit its own derivation**: each headline figure carrying its inputs and a
  **model-derived / overridden / market-assumption** tag, terminating in a GlobalId where one exists.
  `proforma/solve.py` · `returns.py` · `operations.py`. The UI half is genuinely small once the data
  exists, and the v0.3.791 element card is already the right terminus.

  **This entry read as a ready-to-build M and was not.** It said *"`traceability.py` already walks
  model→cost→GL by GlobalId; this is the surface for it"* — true of **cost**, false of the proforma.
  Measured on `e653473b`: `traceability.py` is cost-only (its docstring scopes it to `element_costs`
  / `summary`; **0** mentions of proforma/IRR/NOI/rent), and `proforma/*.py` contains **zero**
  `GlobalId` / `guid` references, so no figure links to a model element at any layer. The lone
  `"basis"` string in `entitlement_risk.py` names which population was averaged — not a chain.

  Building the UI first would have meant **inventing provenance in the client**: a trace that looks
  like it walks to a GlobalId while actually asserting one. That is the fabrication shape this repo
  has spent a day naming, and it would have been shipped as the on-stage demo. Whoever picked up
  Sprint 2 would have started in the client and found nothing to render.
- **R24-RUNS-INBOX** *(M)* — clash, IDS, cost and energy become durable Runs (inputs, timestamp,
  author, artifact, **diff against the previous run**) with a per-project inbox. Most externally
  validated item in the ring — see the corroboration note above.

### Sprint 3 — the front door earns its keyboard

- ⭐ **R24-CMDK-VERBS** *(M; the grouping half shipped v0.3.780 as **R24-CMDK-GROUPS**)* — results now
  render in sections (**Do · Records · Elements · Reports · Modules · Go to**), a group is inferred
  from the `hint` a caller already sets, recency ranks your last twenty commands, and the row cap is
  **per section** — a flat cap removed every workspace from the list once 130 modules outranked them.
  Still missing, and the reason this stays open: **authoring verbs**, **element lookup by GlobalId**,
  **reports**, and `/assistant` as the fallback row. Those are providers in `main.ts`, not palette
  work — the `Elements` and `Reports` sections exist and are empty until something registers into them.
- **R24-DENSITY ②** *(M)* — three steps (Field 56 px / Default 36 px / Compact 28 px) applied to
  **registers**, not just the dashboards `prefs.ts` covers today. Tabular figures wherever a number appears.

### Sprint 4 — field, and the long tail

- **R24-FIELD-MODE** *(L)* — capture-first home, 56 px targets, 7:1 outdoor contrast, permanently
  visible sync queue, dictation on notes. A mode, not a breakpoint.
- 🟡 **R24-CHARTS-GRAMMAR** — **no-data rule SHIPPED v0.3.783**, the rest open. Only `histogram`
  handled empty input; the other twelve drew their axes, gridlines and legend with nothing in them —
  no `NaN`, nothing broken, and therefore indistinguishable from a chart whose data failed to load.
  All nine framed charts now share `noData()`, and `CHART_KINDS` + `charts.test.ts` fail the build if
  a new chart skips it.
  **Still open:** one tick style, one legend position, one currency format.
  **And one correction to the audit, made deliberately:** it says colour should be "restricted to the
  four semantic hues". That is right for *status* and wrong for *series identity* — a seven-series
  S-curve needs seven distinguishable colours, and collapsing them to four makes the chart unreadable
  in service of a rule about badges. The split to enforce is **semantic hues for status, a
  categorical ramp for series**, which is a different contract from `ui/colorContract.ts` (that one
  governs CSS selectors; SVG fills are outside it entirely).
- 🟡 **R24-REPORTS-BY-MOMENT** — **grouping SHIPPED v0.3.785; scheduling still open.** The catalog was
  **56 reports under 18 group headings, six holding a single report**. Seven packages now sit above
  them — owner monthly · lender draw · IC · precon/GMP · design issue · closeout · ownership quarter —
  each stating who asks and when, collapsed by default, with every report still under its noun
  heading below. `reportMoments.test.ts` reads `reports.py` and fails the build if a package names an
  id the server no longer defines; without that, a renamed report shortens a package silently on the
  Friday it is due.
  **Still open: "scheduled and shared, not just downloaded."** A package is currently something you
  open and click through. Making it a *scheduled deliverable* — assembled on a date, sent to a
  recipient, with a record that it went — is the larger half and wants `routers/jobs.py` (now wired
  to the UI by R24-JOB-TRAY) plus a delivery surface. That is a real feature, not a grouping change.
- **R24-TOOLS-SPLIT** *(S, reinstated)* — authoring verbs act instantly; analyses produce an artifact
  after a wait. Split them; the analyses half lands in `R24-RUNS-INBOX` and the job tray.
- **R24-TERMS** *(S)* · **R24-MONO-DATA** *(S)* · **R24-TOOLS-SPLIT** *(S)* · **R24-DENSITY ②** *(M)*
  — the remaining long tail.

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
  `apps/web/src-tauri/tauri.conf.json`, **and `package-lock.json` (~line 23)**.
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

## 📐 R27 — THE DRAWING IS DATA RING *(external research 2026-07-26: one paper + 16 sources)*

**Where the evidence came from.** A peer-reviewed layout-analysis paper on construction drawings
([arXiv:2607.18997](https://arxiv.org/abs/2607.18997), with its ADIRO region taxonomy and a benchmark
of detection vs. vision-language models), a systems-engineering handbook on durable technical
representation, and thirteen reachable industry/OSS sources. Three sources refused automated fetch
(403/503) and are **not** cited as evidence for anything below — an unread source is not a source.

**The thesis this ring is built on.** The platform already treats the *model* as data. It still
treats the *drawing* as an image with some text behind it. Every source that mattered converged on
the same seam: between a sheet's metadata (which we read) and its content (which we render) sits a
**layout layer** — where on the sheet the titleblock, revision table, legend, notes and each drawn
view actually are — and nothing in this repo computes it. That layer is what turns a PDF from a
picture into something a takeoff, a note and a revision can each be *attached to*.

**Two findings shape the approach, and both cut against the obvious build.**

*A general-purpose document-layout model is a **negative** prior here.* The paper's ablation is
unusually direct: pre-training on general document layout scored **0.589** against **0.727** for the
same architecture randomly initialised and **0.772** for generic-object pre-training. Construction
sheets are not documents with unusual furniture; they are a different distribution, and a model that
has learned "this is a paragraph" is actively wrong about them. This is evidence *against* reaching
for an off-the-shelf document-AI dependency — which is also the outcome the offline/$0 constraint
needs, so the constraint costs nothing here.

*The vector layer is already on the sheet.* Our sheets are generated by `drawings_render`/`sheetgen`
and most received sheets are vector PDFs. Region boundaries are literally drawn — titleblock borders,
viewport frames, table rules are **paths**, not inferred shapes. So the first implementation is
deterministic geometry over `pypdf`'s content stream, not detection. Detection is what you need when
you have thrown the vectors away; we mostly have not. Rasters fall back to "unknown", stated.

* **R27-LAYOUT ① — the layout is written but never read back.** *(Corrected after checking the code:
  the first draft of this item said "add `sheet_layout.py`". That module already exists —
  [sheet_layout.py](../services/data/src/aec_data/sheet_layout.py), and it is good — but it runs in
  the **write** direction: it composes viewport rectangles, fixed 1:N paper scales, per-viewport class
  freezes and titleblocks onto sheets we generate. Nothing reads that structure back out of a PDF.)*

  So this is the **same asymmetry R25-TASK-BIND closed for the 4D binding**: a platform that can write
  a structure but not read it has a one-way door, and the structure stops existing the moment the file
  leaves. Two halves, and the first is nearly free:

  ✅ **(a) Our own sheets** *(shipped v0.3.702)*. Detection was never required here, only persistence:
  `compose_viewports` already computes the exact page←world affine in order to place the geometry, so
  `sheet_regions()` now keeps it. Each region reports `basis: "authored"` — these *are* the numbers the
  sheet was drawn with, not a recovery from the rendered output — and the **measurable** rect is the
  inner one, not the cell, because the cell includes padding and the label band and scoping a takeoff
  to it would accept a trace that is not on the drawing. `to_world()` inverts the affine; an
  unmeasurable viewport reports **`to_page: null`, never identity**, since an identity would silently
  report page points as metres. The transform is asserted by **inverting an actual rendered vertex**
  rather than against a second implementation of the same arithmetic — the 4D binding round-tripped
  perfectly through its own writer+reader pair while encoding the wrong IFC relation.

  ✅ **(b) Received sheets** *(shipped v0.3.778)* — [sheet_recover.py](../services/api/src/aec_api/sheet_recover.py),
  `POST /projects/{pid}/drawings/received-regions`. Rectangles come from the page's own content stream
  and are classified with the ADIRO-style vocabulary; `basis` is `sidecar` | `vector` | `unknown`, and
  a page with no vectors returns a **stated unknown, never an empty list** — an empty list is a claim
  about the drawing, unknown is a claim about us. `to_page` is null for every region and never
  identity: the page↔world mapping is not recoverable from a sheet we did not draw. A printed scale
  comes back as `scale_denom_proposed` for calibration to accept, never applied — a takeoff
  auto-calibrated wrong *looks finished*, which is worse than one nobody calibrated.

  Two things the first cut got wrong, both caught by making the test disagree with the code:
  **rectangles must be transformed through the CTM stack** (reading `re` operands raw is the obvious
  version and is wrong on every sheet whose views are placed with `cm`), and **a region's kind must be
  decided by the text it *owns*, not all text inside it** — a revision table nests in the titleblock,
  so reading contained text made the titleblock a "revision table". The border check also passed
  vacuously at first because it restated the implementation's own 0.98 threshold; it now asserts
  against the rectangle the test actually drew, and the border it was supposed to catch was in fact
  still in the output.

  Evidence: arXiv:2607.18997 §layout-layer. Read-side gap confirmed in
  [sheet_extract.py](../services/api/src/aec_api/sheet_extract.py), which walks pages via `pypdf` and
  regexes the text layer with no notion of *where on the sheet* anything sits.

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

* **R28-UNIFY ①** — **one open, one save.** Opening any model creates or attaches a project (with its
  API data if it exists); opening a project ensures a model exists — **a blank authorable one if
  there is none**, so a user can start drawing immediately rather than meeting an empty viewer. This
  is the item that removes the class of bug, not the two instances of it.
* **R28-BUNDLE ② — make `.mmproj` legible.** It already carries the data; nothing says so. Name it in
  the UI, show what a bundle contains before import, and state on export what was included and what
  was **left out** (`_SKIP_TABLES` drops users, audit log, settings and connections — correct, and
  currently silent). The same unknown ≠ none rule the engines follow.
* **R28-ICDD ③ — a standards-conformant envelope.** Emit and read ISO 21597 containers, with our
  payloads as documents and the GlobalId-keyed relationships as RDF linksets. `.mass` can then simply
  **be** an ICDD container with our extension — the branding without the lock-in.
  ✅ **`rdflib` (BSD-3) is APPROVED** *(user, 2026-07-26)* — no longer gated. Licensing is recorded in
  [ATTRIBUTIONS.md](ATTRIBUTIONS.md), which also states that the container is implemented from the
  **published standard** and that no ISO specification text is redistributed. The dependency is pinned
  in `requirements.in` **in the change that first uses it**, with `requirements.lock` regenerated in the
  same commit — the lockfile gate fails any push that leaves the two out of step, and a dependency
  carried ahead of its code is supply-chain surface for no benefit.
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
* **PERF-RATE ② — the rate limit is per-worker and only warns.** Verified at `main.py:155-162`: with
  `AEC_RATE_LIMIT_RPM>0`, multiple workers and no `AEC_REDIS_URL`, each worker counts independently, so
  the effective limit is N× the configured one. It logs `CRITICAL` and **starts anyway**. A security
  control that announces it is not working and then runs is worse than one that is absent, because the
  operator believes it is on. Refuse to start, or drop to one worker.
* **PERF-THREADS ③ — cap the pool, but the stated mechanism is wrong.** The claim was "unbounded
  threads → resource exhaustion". Starlette/anyio's default pool is **40 threads, not unbounded**. The
  genuine risk is different and worth fixing: 40 concurrent *IFC* operations at hundreds of MB each is
  an OOM, so the cap wants to be small and explicit for model work specifically — not because threads
  are unbounded but because each one is expensive.

**Not adopted.** "No evidence of query batching" is an absence of evidence offered as a finding — the
report did not examine the ORM layer and does not name an endpoint. It is the inverse of this repo's
own rule: *a check that examined nothing must not report anything*, clean **or** dirty. Lazy imports
are also deliberate — they keep cold start cheap for the paths a deployment never touches — and the
bake cache's `id()` key is already sound: it holds a strong model reference and re-checks identity.

---

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

* **R27-SKILL-GAP** *(S — reading, not building)* — diff the MIT skills taxonomy against our module
  catalog and the master-builder skill; record only the gaps that fit the mission. Explicitly **not**
  a bulk import: 221 generated skill files would bloat the repo and duplicate engines we already have
  tested. The output is a short list of missing *capabilities*, not files.

**⛔ Licence exclusions recorded from this scan (evaluated, refused, do not re-litigate).** Two
otherwise-relevant OSS projects are unusable under the standing MIT/BSD/Apache-only rule: a GPU map-
rendering library under **PolyForm Noncommercial 1.0.0** (non-commercial only — incompatible with a
commercial product regardless of technical fit) and a physics/simulation library under **AGPL-3.0**
(the same class of exclusion that already keeps PyMuPDF out of the PDF stack). Two are permissive and
remain open as options: a **MIT** OpenCascade-based geometry kernel (C#/.NET — a process boundary, so
a real cost) and a **MIT** TypeScript canvas UI toolkit. Nothing in this ring depends on any of them;
the deterministic path above needs **no new dependency at all**.

**Sequencing.** R27-SOV-LOOP first — it is the smallest change with the largest reach and needs no
research. Then R27-LAYOUT ①→②→③ as one track, since ② and ③ are meaningless without ①.
R27-CLAIM-TYPE and R27-RISK-CALIBRATE are independent and can interleave. R27-FIRM-MEMORY last: it
is a data-scoping change and wants the org tier settled first.

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

* **A29-LOCAL-PREVIEW ①** — *the edit shows before the server agrees.* Adopt the dirty-node idea:
  mark the touched element, regenerate its mesh locally, render it as a **pending** overlay, then
  reconcile against the published fragments when the recipe returns. The rule that keeps this honest
  is the one this codebase already lives by: **a pending edit must look pending.** A local preview
  drawn identically to committed geometry is a lie the moment the recipe fails, and a silent divergence
  between what the screen shows and what the IFC holds is worse than a slow edit.

* **A29-PLACE-VALID ②** — *say no before the round-trip, not after.* Pascal's spatial grid answers
  `canPlaceOnFloor` / `canPlaceOnWall` / `getSlabElevationAt` before a placement commits. We validate
  server-side, so an invalid placement costs a full round-trip to be told no. Reuse the existing
  `inference.ts` maths; this is a pure function and belongs beside it, unit-tested the same way.

* **A29-SPATIAL-SELECT ②** — *click depth, not just objects.* Their selection walks Site → Building →
  Level → Zone → Item. That hierarchy is **IfcSite → IfcBuilding → IfcBuildingStorey → IfcSpace →
  element** — we hold the real one and navigate it as a flat list. This is the item where being
  IFC-native makes the feature *better* for us than for them, because their tree is a convention and
  ours is the model.

* **A29-UNDO-LOCAL ③** — *undo the stroke, not the commit.* We version on the server; they keep a
  50-step in-browser history. Both are right for different questions — "undo my last three drags"
  should not require three republishes. Scope: the in-progress draft only, discarded on commit, with
  the server history unchanged as the record.

* **A29-GUIDE-UNDERLAY ③** — *trace over a plan.* A 2D reference image pinned to a level and scaled,
  for redrawing an existing building from a scan or a PDF. Small, self-contained, and the one place
  their `Guide` node maps onto something we do not have.

**Explicitly NOT in this ring:** adopting React/R3F, adopting a bespoke node schema beside IFC,
vendoring `engine_clay` (dormant), and anything from IFChili (AGPL). If client-side booleans become
necessary later, that is a separate decision with **Manifold** as the candidate and a dependency
conversation attached.

## 🎚 UX-POLISH — interaction-craft ring (remainder beyond the NOW sprint)

**Audit 2026-07-25 (live, against the running stack).** Measured rather than opined: 170 visible
controls, **0 unlabelled**; **0 console errors**; **20/20** first-class Design destinations render real
content (the "Design tab is blank" report was a measurement error on my side, not a defect — `innerText`
returns empty for anything not laid out, and clicking rebuilds the nav, detaching the node being
measured). Two density defects were real and are **fixed in v0.3.677**: `Build` held 13 entries of
which 7 were project accounting, and `Model & standards` held 14 mixing project rules with model
findings. Split into Build/Money and Model & standards/Analyse & check — **max group 14 → 7**, nothing
removed. Remaining, in priority order:

- ⭐ **UX-READINESS-EVERYWHERE** *(M; superseded by **R24-READINESS-HOME**, kept for its evidence)* — **the app already contains its own "simple stupid" front door
  and hides it.** The Master Builder panel is a live 8-step readiness synthesis: each step reads
  ready / partial / gap against real project data, names exactly what is missing ("needs: Jurisdiction
  so code editions + loads resolve"), and offers **→ Close this gap** straight to the tool that fixes
  it — plus an honest disclaimer that labels reflect what is *present*, not what is *correct*. That is
  precisely the "tell me what to do next" surface a builder/developer/architect/engineer wants on
  opening a project, and it is reachable from exactly ONE destination inside ONE workspace (Design).
  Promote the readiness strip to every workspace dashboard, scoped per persona.
- **UX-DUP-DESTINATIONS** *(S)* — `Model Health`, `Model Analysis` and `BIM KPIs` are three
  destinations whose names do not tell a user which answers their question; all three now sit together
  under `Analyse & check`, which makes the overlap visible and worth resolving rather than hiding it.
- **UX-GANTT** *(M)* — weekly Gantt/calendar hybrid with inline % + crew coloring + a metric strip.
- **UX-VIEWED** *(S)* — ShareToken page view-timestamps → Sent/Viewed/Paid chips, self-hosted.
- **UX-AR** *(S)* — Sent→Approved→Paid manual status pipeline on invoices/bills (no payment rails).
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

## 🧱 Decomposition & reliability carry-overs (interleave one per few releases)

- **SEC-PLUGIN-SANDBOX** *(L)* — **plugin Python executes inside the API process.**
  `plugin_registry.py:136-141` does `spec_from_file_location` → `module_from_spec` →
  `spec.loader.exec_module(mod)`, then calls `mod.register(PluginApi(...))`. Whatever the entry
  module does at import time runs with the API's full privileges: its DB session, its filesystem, its
  network, its environment.

  **What is already right, so nobody re-does it:** discovery is **opt-in and off by default**
  (`AEC_PLUGINS_ENABLED=1`), the manifest is validated before the entry is touched, `api_version`
  major must match, and a plugin that raises is refused non-fatally with its recipes rolled back out
  of `edit.RECIPES`. That is a careful loader. It is not a boundary — every one of those checks
  happens *before* `exec_module`, and none of them constrains what the code then does.

  The work is a real boundary, not more validation: run registration in a **separate process** with
  a narrow IPC contract (register-only, returning recipe names), a wall-clock and memory cap, and no
  ambient DB or storage handle. Signing is the weaker alternative — it answers *who wrote this*, not
  *what it may do*, and this repo already learned from [[sandbox-object-api-surface]] that a denylist
  cannot see methods reached through an injected object. Gate the design on that lesson.

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
| `services/data/src/edit.py` | 99.6th | 6 |

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


- ✅ **SEC-GLOBAL-AUTHZ** — **SHIPPED**: the ratchet landed as PR #102, the HIGH was fixed in #101,
  and the allowlist was hardened in v0.3.793/794. `test_global_authz.py` freezes 39 known global
  mutating routes and fails the build on a new one; coverage checked against `app.openapi()` (0 of 51
  invisible to it); mutation-checked before merge, not after. The `AUTHORISING` set is now verified
  against the source — two names in it (`require_license`, `require_plan`) resolved to nothing, which
  is a pre-authorised hole waiting for someone to define a matching name. Original entry kept below
  because the *mechanism* is the durable lesson. — **there is no authz gate for platform-global
  routes, and a HIGH got through the hole on 2026-07-29.** `test_route_authz` enumerates `/projects/{pid}` routes and
  asserts each carries `require_role`; it passed on 695 routes while three brand-new routes with no
  `{pid}` in the path — `GET`/`POST`/`DELETE /jurisdiction/packs` (PR #101) — were reachable
  **unauthenticated**. Measured with RBAC on and no credentials: `200` / **`201`** / `200`, with
  `GET /admin/errors` correctly `403` in the same run.

  The mechanism generalises past that PR and is the reason this is a ring item rather than a bug
  note: **`Depends(current_user)` identifies, it does not authorise.** With RBAC on and no bearer
  token, cookie or trusted header it returns the literal string `"anonymous"`, so a route guarded
  only by it *has a name attached and no gate* — and the signature reads like a gate, which is how it
  survives review. Any non-`{pid}` route that mutates shared state has the same exposure and nothing
  currently checks for it.

  The work: a companion to `test_route_authz` that enumerates **mutating routes with no `{pid}`** and
  fails any whose dependency chain is only `current_user`. Then audit the existing ones — this was
  found on new code and nobody has looked at the routes already on `main`. Note the second-order
  trap when writing it: every jurisdiction suite popped `AEC_RBAC`, and with RBAC **off**
  `current_user` returns the `X-User` header, so the bug **cannot appear** — the new test must run
  RBAC-**on** and lead with a control assertion, or it passes for the wrong reason.
  *(Fixed on the branch: writes → `require_admin_user`, reads → a `require_identified` that refuses
  `anonymous`; `test_jurisdiction_authz.py` pins it. The general gate is what remains.)*
- **REL-4 leaves** *(M)* — `portal.ts` next leaf + `viewer/app.ts` leaves.
- **REL-7** — evidence-gated dead-code removal *(needs RT-KNIP first — see Gated)*.

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
gbXML + IDF export — shipped v0.3.655)* · **RT-NODE-LANE** — CI is on Node 22; the **local** Node is
still 20.3.1 *(user action)*, then unpin eslint off 9.39.5, then Vite 6→7 behind a build benchmark
*(defer Vite 8/rolldown)*.

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
- **Local Node 20.3.1 → 22** — unblocks RT-NODE-LANE's local half.

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

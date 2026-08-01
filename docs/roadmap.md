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

## 📌 START HERE

1. **[roadmap-directions.md](roadmap-directions.md)** — non-negotiables, how to verify, shared-clone
   hazards, lanes, testing, release discipline, what "done" means. **Read before touching anything.**
2. **[What is left, prioritised](#-what-is-left--prioritised)** — the ranked view, below.
3. **[The lanes](#-now--parallel-lanes)** — who owns which paths, so two agents do not collide.
4. **[roadmap-completed.md](roadmap-completed.md)** — what shipped, and why it was built that way.

*This file is the list of work. It is not the place for working conventions — those drifted into it
over several months and were moved out on 2026-07-31 so this could stay readable.*

---

## 🥇 What is left — prioritised

**49 open items.** Ranked by consequence-if-wrong, then by whether the thing is *reachable* rather than
merely *built*. Sizes are the roadmap's own. ⭐ marks the highest-value item in a band.

### Band 1 — correctness and safety (do first; each is a live wrong answer or an open door)

## ✅ **BAND 1 IS EMPTY as of 2026-07-31.**

Three items left it in one day and **none of them left the same way**: two were real defects and shipped,
and the third was closed *unbuilt by measurement*. That third outcome is the one worth protecting — an
item can be finished by producing a number that says it should not be built, and that is a result, not
a failure to deliver.

- ✅ **R33-CLAWBACK-AMOUNT** — shipped (`856970c8`). Verified by reading the implementation, not the PR
  title.
- ✅ **R34-SHEET-SCALE** — shipped (`365976d8`). The engine was already right; nothing set the field.
- ⛔️ **R23-PICKING — CLOSED UNBUILT, on a measurement.** See below.
- ↘️ **SEC-PLUGIN-SANDBOX** — left the band (still open, moved to platform); the threat model was
  checked rather than assumed and no unprivileged path reaches it.

✅ **R33-CLAWBACK-AMOUNT — SHIPPED** in PR #136 (`856970c8`). `waterfall.solve_clawback_for_pref(lp_cf,
lp_dates, pref_rate, cap)` now solves for the cash added at the final date that lifts the LP's **XIRR**
to the pref, capped at the promote actually paid, and `run_waterfall` reports the shortfall when the
promote cannot cover it. The rate-times-principal proxy with no time dimension is gone. Verified by
reading the implementation, not the PR title: `xirr` is imported and used, and the docstring carries the
5.8x construction that motivated the entry.

✅ **R34-SHEET-SCALE — SHIPPED 2026-07-31.** The engine had accepted a per-region `scale_units_per_px`
since R34-MEASURE-PROVENANCE; **nothing ever set it, and nothing tested it**, so the capability existed
and the defect was live — the gap was *reach*, not capability. The overlay kept one `scale` that
recalibration overwrote and passed it at Quantify time, so tracing a plan at 1/8"=1' and then
recalibrating for a detail at 1/2"=1' **retroactively re-measured the plan regions at the detail's
scale** — worse than the "one scale per set" this entry described. Scale is now stamped onto each region
at trace time. Details in [`roadmap-completed.md`](roadmap-completed.md).

↘️ **SEC-PLUGIN-SANDBOX left this band on 2026-07-31** (still open, now under Band 6 · platform). The
loader really does `exec_module` arbitrary Python with the API's privileges — but the threat model was
checked rather than assumed, and **no unprivileged path reaches it**: the plugin dir does not overlap
the upload root, no route writes into it, reload is platform-admin gated, and discovery is off by
default. That makes it operator-installed code, i.e. `pip install`, not an open door. It becomes Band 1
the day plugins are *distributed* rather than operator-placed. Full reasoning at the item.

✅ **SEC-SEAL / SEC-FIRM-RULES / SEC-ESIGN-HOOK / SEC-CACHE — SHIPPED v0.3.807.** Four exploitable
findings, none of which were on this list because none had been noticed: an **unauthenticated** caller
could obtain a PDF bearing a rendered PE seal with a name and licence number of their choosing; any
project-admin could replace (and thereby erase) the firm's standards library by naming their own
throwaway project; `/esign/webhook` accepted anonymous unbounded writes into the audit table; and
tenant JSON was served with no cache policy. Sealing now requires a verified licence **and** a human
step-up a stored token cannot satisfy. See CHANGELOG v0.3.807; migration `b06f7bc8ba2f` plus a
**go-live data-entry step** (a licence row per licensee) is documented in `docs/PRODUCTION_CHECKLIST.md`.

### Band 2 — built but unreachable (cheapest real value in the file)

Seven of eleven engines once shipped with no route. These are the current instances.

| item | size | the gap |
|---|---|---|
| ~~**R32-CURRENT-SET**~~ | S | ✅ **CLOSED 2026-07-31 by decision, no code change.** The gap-check found the register already picks the newest revision per sheet — the defect was never "superseded sheets are shown". The real question was *which* "current" a viewer sees, and the user's call is **latest authored**, which is what it already shows. The issued set remains separately authoritative (filed `Drawing Set`, issuance register, transmittal). |
| ~~**R24-TRACE-UI ②**~~ | L | ✅ **SHIPPED 2026-07-31** (`b3a630ea`). 19 headline figures report which assumptions the caller **declared** vs the engine **defaulted**, derived from `model_dump(exclude_unset=True)` — deriving from the validated dump would report everything as declared and answer the reviewer's question with fiction. `element_link` is `None` everywhere with a stated reason: the proforma holds no GlobalId and an invented terminus is worse than none. `POST /proforma/provenance`. |
| ~~**R27-LAYOUT ①**~~ | S | ✅ **STALE BAND ENTRY — closed 2026-07-31, both halves were already shipped.** (a) our own sheets: `sheet_layout.sheet_regions()` keeps the page←world affine with `basis: "authored"` (v0.3.702). (b) received sheets: `sheet_recover.py` + `POST /projects/{pid}/drawings/received-regions` (v0.3.778). Reached at `analysis.py:610`; covered by `test_sheet_layout` and `test_sheet_recover`. The detail entry recorded both as shipped and this table row was never updated — **the roadmap's own drift, not the code's.** |

✅ **R32-MODEL-IN-TREE + R32-FILE-GENERATED — SHIPPED 2026-07-31** (`44a901bd`, `4f6a5c84`). Two thirds
of the filing ask are done. `12_Model/IFC` holds the model, and **issuing a set now files it**: the
transmittal lands in `02_Drawings` on issue, beside the hand-uploaded drawings rather than in a
"generated" silo. The remaining third is `R32-CURRENT-SET` above, and it is now a *read-side* change.

Four decisions, recorded because they are the constraints the next filing caller inherits:

1. **File on publish, never on save.** `source.ifc` is rewritten by every edit recipe; filing on write
   would mint a revision per keystroke and make the chain meaningless.
2. **File by KIND, into the folder that kind already uses** — there is no `Generated Drawings` folder,
   and a test asserts none exists. A silo would rebuild the two-parallel-stores problem and split "the
   current set" across two places, which is exactly what `R32-CURRENT-SET` then has to reconcile.
3. **Titles carry the semantics.** The set's title is *constant*, so re-issues supersede into one
   current document (P01, P02, …) — that is what lets the tree answer "which set is current". A
   transmittal is titled *per issuance*, because one that superseded its predecessor would destroy the
   release history it exists to provide.
4. **Filing at issue is non-fatal and reported.** The issuance is already committed when filing runs, so
   raising would surface as "issuing failed" for a release that *did* happen. The response carries
   `filed` or a `filed_error` reason — an explicit unavailable, never a silent success.

✅ **DECIDED by the user, 2026-07-31: `12_Model/IFC` IS `required`.** Asked precisely because it moves
every existing project's document-control health score at once — and that is the intended effect. A
project whose model has never been filed is genuinely non-compliant, and the score should say so rather
than stay comfortable. Existing projects will show `12_Model/IFC` under `required_missing` until someone
files a model; **that is a true finding, not a regression.** Only the IFC leaf is required —
`12_Model/Federated` is not, because a project with one authored model and no federated coordination
model is complete, and requiring it would manufacture a permanent gap nobody can close.

The gate is on *reach*, not on the flag: the test asserts an unfiled model **appears** in
`documents/health` → `required_missing`, and that filing it **clears** the gap. A `required` flag that
no health report surfaced would be the same defect this band exists to catch.

### Band 3 — gap-checks (hours, not days; each may close for free)

## ✅ **BAND 3 IS COMPLETE — all five checked 2026-07-31. Five closed, zero builds.**

The band's own thesis held again, and harder than expected: **five of five premises failed.** What the
whole exercise cost was a few hours of reading; what it saved was five builds.

*Corrected after a re-check.* This first read "four closed, one reframed": `R31-SYNDICATION-TAIL` was
recorded as mostly-failing with one genuine remainder, the K-1 pack. That remainder was then **built and
shipped the same day** (`aabad457`), so the band's real output is five closures.

⚠️ **Recorded as *shipped today*, not as *never a gap*** — and the distinction is the point. On the
re-check the sibling session found `capital.k1_pack()` present and concluded it had always been there.
It had not; it existed because that session's own finding caused it to be built hours earlier. **All
sessions share one git identity, so a sibling's fresh work is indistinguishable from history** unless
you read the file's `git log`. Writing "we were always fine here" would have been false and would make
every other closure in this band less trustworthy.

**The closures were re-checked for REACH, not just capability** — a `module.json` on disk is not reach,
and an engine nothing calls is the defect this file keeps finding. Every closure below names a live
caller:

| closed item | why | reached from |
|---|---|---|
| **R22-ITP-NCR** | all four asks exist — `itp.point_type` is a required select (Hold/Witness/Review/Surveillance/Monitor) with method, acceptance criteria, frequency and both parties; `ncr` runs `open → dispositioned → closed` with disposition, corrective action, root cause, severity; element attachment is `element_guids` | `quality_chain` ← `routers/construction.py:260,283` · modules → section `Quality` → room `schedule` |
| **R22-PROCURE-DEPTH** | all three named remainders are built — `prequalification` module (EMR, bonding capacity, revenue, references, workflow), `clause_playbook.py` (accept/negotiate/refuse per contract type, severity, fallback, deviation register), `vendor_memory.py` cross-project scorecards | `routers/realestate.py:300,309,332` · `routers/benchmarking.py:83` · modules → `Preconstruction` → room `planning` |
| **R27-SKILL-GAP** | the corpus diff is nearly empty — `ids-checker`, `energy-simulation`, `schedule-compression`, `weather-impact-scheduler` and ~15 more all already have engines or modules | see the entry for the file-level list |
| **R31-SYNDICATION-TAIL** *(mostly)* | the entry's own instruction was *"do not build a cap table before confirming `capital.py` lacks one"* — **it does not lack one.** `capital.cap_table()` returns ownership %, contributed/distributed/unreturned and per-class rollup. Soft/hard commitments are built under a different name: `investor` states `prospect → committed → funded → exited` | `distwaterfall.py:67` · `report_builders/finance.py:293,510` · `reports.py:103` |

**Three real remainders survived, all small**, and each is now its own entry rather than hiding inside a
closed one: **R31-K1-PACK**, **R31-CITE-HIGHLIGHT** (reframed — see below, it is far cheaper than
written) and **R22-PHOTO-CV**.

⚠️ **Two traps recorded so the next reader does not re-fall into them:**

1. **`commitment` is a CONSTRUCTION module, not an investor one** — Purchase Order / Subcontract / Work
   Authorization, with `retainage_pct` and `cost_code`. Reading it as the syndication side is almost
   certainly what produced the R31-SYNDICATION-TAIL entry in the first place. A name collision, not a
   missing feature.
2. **A loose `grep -i "ids"` matches "bids" and "considers"** and nearly produced a false gap. Same
   substring-contamination shape as `EIR`/"their" and `MIDP`/"midpoint". Word-bound it.

### Band 4 — capability the product is judged on

✅ **R34-TAKEOFF-COUNT — SHIPPED (#139, `29c26f27`); it was still listed here.** The platform had **no count measure at all**: every assembly was `area` or `length`, so a door, fixture, receptacle or sprinkler head — the thing an estimator counts most often — could not be taken off a drawing. Now a third measure, and **a count is never scaled**: area goes as scale², length as scale¹, and six doors are six doors at any sheet scale. Making it a third *measure* rather than a third *unit* is what makes that structural instead of remembered. Verified present: 13 count refs in `takeoff2d.py`, `test_takeoff_count` registered.

⭐ **R22-ENTITLEMENT** (M/L) · **R31-PIPELINE-ALLOCATE** (L) · **R22-REPORT-BUILDER** (M) ·
**R22-PIPELINE** (M) · **R21-DIM-COMPONENT** (M) · **R21-4D-CLASH** (phase 2)

*Three items left this row on 2026-07-31, all already built:* **R22-PRODUCTION** (`c23c26dd`),
**R21-SPACE-TAG-SECT** (rode inside `50f195cf`, no commit of its own), and **R22-CAD-IMPORT** (the DXF
path shipped long ago; its "we only run on models we authored" premise was false). That is three in
one row, on top of five earlier the same day. **A band row is a cache of the detail entries and it is
never invalidated** — nothing recomputes it when an item ships, so it drifts in one direction only:
toward advertising work that is already done. Check the code before picking up a row, and note that
`R22-ENTITLEMENT` below survives a grep for "entitlement" **only** because `entitlements.py` is
subscription tiers — a pure name collision, and the reason this sweep verified semantics, not strings.

### Band 5 — interface and feel

⭐ **R24-PERF-BUDGET** (S) · ⭐ **R24-CMDK-VERBS** (M) · ⭐ **R24-ELEMENT-CARD ②** (M) ·
**R24-RUNS-INBOX** (M) · **R24-DENSITY ②** (M) · **R24-FIELD-MODE** (L) · **R24-CHARTS-GRAMMAR** ·
**R24-REPORTS-BY-MOMENT** · **R24-TOOLS-SPLIT** (S) · **R24-TERMS** (S) · **R24-MONO-DATA** (S) ·
**UX-READINESS-EVERYWHERE** (M) · **UX-DUP-DESTINATIONS** (S) · **UX-GANTT** (M) · **UX-VIEWED** (S) ·
**UX-AR** (S) · the five **A29** authoring-feel items · **R23-BATCH-OVERLAYS** (S)

### Band 6 — platform and format

**R28-UNIFY ①** · **R28-BUNDLE ②** · **R28-ICDD ③** · **R28-VIEWER ④** · **PERF-WORKERS ①** ·
**PERF-RATE ②** · **PERF-THREADS ③** · **R23-STOREY-LOD** (L) · **SCALE-SEAM ⑥** ·
**R34-MEASURE-PROVENANCE** (S) · **R22-AGENT-PACKS** (M) · **R22-ROUTINES** (S) ·
**R22-OPTION-OBJECT** (S/M) · **R22-PM-CONTRACTS** (M) · **R22-PUBLIC-VIEWER** (S) ·
**R23-SYMBOL-COUNT** (M) · **R22-PROVENANCE** (L)

### Parked — needs a decision, not an engineer

**R32-TAXONOMY-LIFECYCLE** (the user has since answered: derive the document taxonomy from the seven
rooms) · **R24-PERSONA-SHAPE** · **R24-IDENTITY** · **R26-V-TIMING** · **QUALITY-ROOM** ·
**PHOTO-PIN** and **CMMS-OPS** (BIG-TICKET: open **one**, slice it) · **REL-7** (gated on RT-KNIP).

---

## ▶ NOW — parallel lanes *(rebuilt 2026-07-29 at v0.3.785)*

**How to work here lives in [roadmap-directions.md](roadmap-directions.md), not in this file.** Claim a
lane rather than an item, premise-check before building, announce before a full suite, and land what
you finish. Those rules and the reasons behind them are in the directions; this section is only the
lane assignment.

**Organised by LANE rather than by priority**, because several sessions work concurrently and a single
ranked list serialises work with no reason to be serial. For a ranked view of the same items, see
**[What is left, prioritised](#-what-is-left--prioritised)** above.

### The lanes

**Nine lanes, and every open item is assigned to exactly one.** `shell/roadmapLanes.test.ts` asserts
that: it extracts the item codes from this file and fails if any is missing from the table below, or if
the table names a code that no longer exists. **Pick a lane, read its row, take any item in it** — no
two rows share a path, so two agents in different rows cannot collide.

| Lane | Owns these paths — disjoint | Open items in this lane |
|---|---|---|
| **A · Shell & IA** | `apps/web/src/shell/`, `apps/web/src/portal/portal.ts`, `main.ts` | R24-CMDK-VERBS · R24-RUNS-INBOX · R24-TOOLS-SPLIT · UX-READINESS-EVERYWHERE · UX-DUP-DESTINATIONS · UX-VIEWED · REL-4 |
| **B · UI & panels** | `apps/web/src/ui/`, `portal/panels/`, `field/`, `reportCenter.ts` | R24-CHARTS-GRAMMAR · R24-REPORTS-BY-MOMENT · R24-DENSITY ② · R24-EMPTY-GUIDE ② · R24-MONO-DATA · R24-TERMS · R24-FIELD-MODE · UX-GANTT · R22-REPORT-BUILDER · R23-SYMBOL-COUNT · R31-CITE-HIGHLIGHT · R32-CURRENT-SET |
| **C · Backend engines** | `services/api/src/aec_api/`, `!services/api/src/aec_api/routers/` | R22-PRODUCTION · R22-ENTITLEMENT · R22-AGENT-PACKS · R22-PROVENANCE · R22-OPTION-OBJECT · R22-PIPELINE · R22-ROUTINES · R24-PERF-BUDGET · R27-SOV-LOOP · R27-CLAIM-TYPE · R27-RISK-CALIBRATE · R27-FIRM-MEMORY · R31-PIPELINE-ALLOCATE · R22-PHOTO-CV · R34-MEASURE-PROVENANCE · SEC-PLUGIN-SANDBOX · PERF-WORKERS ① · PERF-RATE ② · PERF-THREADS ③ |
| **D · Geometry & drawings** | `services/data/src/aec_data/` | R21-4D-CLASH · R21-SPACE-TAG-SECT · R21-DIM-COMPONENT · R22-CAD-IMPORT · R23-STOREY-LOD · R23-BATCH-OVERLAYS · R28-UNIFY ① · R28-BUNDLE ② · R28-ICDD ③ |
| **E · Authoring feel & viewer** | `apps/web/src/viewer/`, `inference.ts` | A29-LOCAL-PREVIEW ① · A29-PLACE-VALID ② · A29-SPATIAL-SELECT ② · A29-UNDO-LOCAL ③ · A29-GUIDE-UNDERLAY ③ · R24-ELEMENT-CARD ② · R28-VIEWER ④ · R22-PUBLIC-VIEWER · UX-AR |
| **F · Docs & demo** | `README.md`, `docs/`, `apps/web/src/demo/` | keep the shipped surface honest (below) — no coded items |
| **G · API surface** | `services/api/src/aec_api/routers/`, `main.py` | no standalone items: **every lane routes its own work**, which is why this is a lane rather than a shared file |
| **H · Registers** | `services/api/modules/*/module.json` | R22-PM-CONTRACTS |
| **I · API client** | `apps/web/src/api/` | SCALE-SEAM ⑥ |

**Parked — not available to pick up.** These are decisions or multi-release commitments, listed so
nobody starts one thinking it is a sprint item: QUALITY-ROOM · R26-V-TIMING · R24-PERSONA-SHAPE ·
R24-IDENTITY · R32-TAXONOMY-LIFECYCLE (all five need the user's call) · PHOTO-PIN · CMMS-OPS (BIG-TICKET: open **one**, slice
it) · REL-7 (gated on RT-KNIP).

**Two lane boundaries were wrong until 2026-07-30 and are worth naming.** Lane A used to own
`apps/web/src/portal/` *wholesale* while B owned `portal/panels/` — a nested overlap, so the two lanes
least likely to notice each other shared a directory. And `routers/` sat inside C's path with no owner
of its own, which is how a route can be added twice. **A lane table whose paths overlap is not a lane
table**; the new `roadmapLanes.test.ts` asserts disjointness so this cannot come back.

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
- ✅ **R21-MULTISCALE — the capability was already there; the entry was stale.** Checked 2026-07-31: `compose_viewports` has taken a **per-viewport `scale`** since the viewport work — its docstring documents `"scale": 100  # 1:100 on paper; omit/None → fit-to-rect`, it reads `vp.get("scale")` per view, and emits a per-view `scale_denom`. Reached at `analysis.py:603`. The entry said "per-viewport scale is the missing parameter"; it was not missing.

  **What WAS missing was the proof, and that is now a gate.** `test_sheet_layout` paired one fixed scale with one fit-to-rect view — which does not test the claim, because "fit" is not a scale anyone specified and a build applying ONE denominator to every viewport would still pass. It now composes **1:50 and 1:100 on one sheet** and asserts each keeps its own denominator *and* that the finer scale is never smaller on paper — a label is cosmetic, an extent is the drawing. Mutation-checked: forcing the first viewport's scale onto all views yields `('1:50','1:50')` and goes red. *(Original entry below.)*
- ~~**R21-MULTISCALE**~~ *(S)* — several viewports at **different scales** on one sheet (1:100 overall +
  1:50 parts), each with its own title/scale block. `sheet_layout.py` composes viewports; per-viewport
  scale is the missing parameter.
- ✅ **R21-SPACE-TAG-SECT** — **SHIPPED inside `50f195cf`**, which is why nobody noticed: it rode along
  with the qto class-match fix rather than getting its own commit, so the band row went on advertising
  it. `space_tags_section()` is at `drawings.py:677` and is genuinely called at `drawings.py:1468` —
  checked for a *caller*, not merely a definition, because the log lines inside a function match a
  grep for its own name and read exactly like use.
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

- ✅ **R22-PRODUCTION** — **SHIPPED (`c23c26dd`, PR #142).** `GET /projects/{pid}/progress/reconciliation`
  compares field-installed quantity against the model takeoff per cost code. Both halves had existed
  for months without being joined, and the reason was structural rather than an oversight: the module
  carrying `cost_code` — the join key — is read only by pricing and carbon, while the module the
  production loop actually consumes has no `cost_code` field at all. The loop read the module that
  cannot join. Built as four refusals (units never silently equated, over-install reports >100% rather
  than clamping, an uncoded takeoff says so, unmatched field codes named not counted), and every
  headline percentage carries `covered_pct` — 97% complete across 3% of the model is true and useless.
- **R22-ENTITLEMENT** *(M/L)* — **permit & entitlement workflow**: jurisdiction submittal packages,
  review cycles, comment responses, and **conditions of approval carried into the model as
  constraints**. Today there is a hole between "acquisition" and "construction" in our own mission
  statement — we underwrite the deal and we build it, and nothing spans approval.

  ⚠️ **Two name collisions sit on this item; gap-check on SEMANTICS before touching it.**
  `entitlements.py` is **subscription tiers** (free/pro/enterprise), nothing to do with land use.
  `proforma/entitlement_risk.py` is genuinely adjacent — but it *scores risk*, it does not run a
  submittal workflow, so it neither closes this nor is irrelevant to it. A name-based sweep gets this
  item wrong in **both** directions: `entitlements.py` makes it look shipped, and stopping there means
  never noticing `entitlement_risk.py`, which the eventual build should probably feed. Third
  collision found on 2026-07-31, after `report_builders/` (five hardcoded builders, not the no-code
  builder R22-REPORT-BUILDER describes).
- ⭐ **R22-AGENT-PACKS** *(M)* — **named agent packs + org "Skills" + a governance console** over the
  MCP layer we already ship. We expose raw capability; the market ships "Submittal Review Agent",
  which a superintendent understands. Pure packaging of existing tools, plus per-run audit logging —
  the gating factor for enterprise adoption. Our version reads the IFC, so a submittal check can test
  the submitted product against the element's *specified properties* rather than against a PDF.

**Tier 2 — evidence, provenance and procurement**

- ✅ **R22-ITP-NCR** *(M)* — **CLOSED 2026-07-31, premise FAILED.** All four asks exist and are reached.
  `itp.point_type` is a **required select** — Hold Point · Witness Point · Review Point · Surveillance ·
  Monitor — alongside `method`, `acceptance_criteria`, `frequency`, `responsible_party`,
  `verifying_party`, `record_form`. `ncr` runs a real lifecycle `open → dispositioned → closed` with
  `disposition`, `corrective_action`, `root_cause`, `severity` and a link to `inspection`. Element
  attachment is `element_guids`, which `quality_chain.py` reads per element (built by R22-QUALITY-CHAIN,
  #110) and which `routers/construction.py:260,283` serves as the chain and turnover-readiness. Modules
  resolve section `Quality` → room `schedule`, and `test_module_rooms` fails the build on an unmapped
  section, so this cannot rot silently.
- **R22-PROVENANCE** *(L)* — **cite to file, page and revision.** Every proforma assumption, estimate
  line and agent answer traceable to a source page. Three of thirteen platforms *lead* with this; it
  is what makes AI output admissible in an IC memo or a claim.
- ✅ **R22-PROCURE-DEPTH** *(M)* — **CLOSED 2026-07-31, premise FAILED.** Claimed "bid leveling covers
  one step of five" and named three remainders; **all three were already built**, and all three are
  reached: `prequalification` module (EMR, bonding capacity, annual revenue, references, rating,
  expiry, workflow `invited → submitted → approved/rejected`) · `clause_playbook.py`, a per-contract-type
  registry of accept/negotiate/refuse positions with severity and fallback plus a deviation register,
  called from `routers/realestate.py:300,309,332` · `vendor_memory.py` cross-project scorecards, called
  from `routers/benchmarking.py:83`. Module reach resolves `Preconstruction` → room `planning`.

**Tier 3 — on-ramps and reach**

- ✅ **R22-CAD-IMPORT** — **the DXF path was already SHIPPED, and its stated premise was false.** The
  entry read "today feasibility and test-fit only run on models we authored". They do not:
  `POST /projects/{pid}/raise-plan` (`routers/authoring.py:1161`, `require_role("editor")`) raises an
  uploaded DXF into a real IFC4 model registered as a *2D Raise* discipline model — which flows into
  the viewer, QTO, the estimate and federated clash like any other. `preview=true` returns detected
  wall/room counts without writing. Two readers exist, both on **ezdxf (MIT)**: `dxf_takeoff.py`
  (measured quantities per layer) and `plan_to_bim.py` (walls extruded from line-work, `IfcSpace`s from
  closed polygons).

  **Measured, not read.** A metric DXF (`$INSUNITS=6`) with one 8×6 m closed room raised to 4 `IfcWall`
  + 1 `IfcSpace`, area 48.0 m² (exact), schema IFC4, GUIDs present on every wall. Units are detected
  from the header rather than assumed.

  **What is genuinely NOT built, stated plainly rather than left to look shipped:** *DWG* natively —
  it must be converted to DXF externally first, which is a deliberate licence choice (the available
  converters are AGPL or proprietary) and should stay a documented external step, not a dependency.
  And *PDF* → base plan: PDF **takeoff** exists (TAKEOFF-2D), but raising a PDF to geometry does not.
  If the PDF half is still wanted it should be re-cut as its own item with its own sizing, because it
  shares nothing with the DXF path — vector recovery from a PDF is a different problem, not a format
  variation.
- **R22-OPTION-OBJECT** *(S/M)* — make **option the primary object**: geometry + unit mix + cost +
  carbon + IRR as one comparable record, so no massing is ever evaluated without its returns.
- **R22-REPORT-BUILDER** *(M)* — **RESCOPED 2026-07-31; the original premise was false.** The entry
  read "132 modules of structured data with **no end-user query surface**". There is one, and it is
  good: per-field filtering with operators (`?f.discipline=Structural&f.amount.gte=1000`, capped at
  `MAX_FILTERS = 12`), field names validated against the module's declared fields in **one** place so
  the two cannot drift, calculated columns (`qty * unit_cost`), generic Excel/CSV import with preview,
  and **saved views** persisted server-side with saved-search alerts. A user can already filter,
  compute a column, save it and be alerted on it without an engineering ticket.

  The real remainder is the four things that separate a saved *list* from a *report*:
  1. **No aggregation over user-chosen fields.** The only `group_by` in the whole module path is
     internal and hardcoded to `workflow_state` (`modules_query.py:230,241`). No count/sum/avg by
     discipline, trade or month. **This is the substantive one.**
  2. **Single-module only.** `SavedView.module` is one string and nothing spans modules, so "RFIs
     against change orders by trade" is not expressible — and that is most of what a report *is*.
  3. **`SavedView.config` is an unvalidated JSON blob**, "filter/sort/column config" by docstring only.
     A saved view is whatever a client happened to write, so a schema change breaks views silently
     with no migration path. Same family as `module.json` having no capability key.
  4. **Per-user, never shared** — `user` is part of the identity key, so a view cannot be a firm or
     project report. A builder whose output only its author can see is a personal filter.
  5. **`reports.REPORTS` is a separate registry the saved-view layer knows nothing about.** Reports
     already exist, with their own categories, rendered in their own panel — so a "report builder"
     that only grows the module query surface would ship a *second* way to make a report, sitting
     beside the one users already have. Unifying them, or deciding deliberately that they stay
     separate, is part of this item.

     **This fifth line was missing from the four-item list above for a day**, and how it was missed is
     the point: the gap-check read the module and saved-view layer thoroughly and never opened the
     report registry. The list was **accurate about what it examined and incomplete about the item** —
     the same failure this entry exists to correct, committed while correcting it. `reports.REPORTS`
     is invisible to a module-layer sweep because it renders in a different panel, which is also how
     three of its categories came to name sections the product had retired (fixed separately).
     **A completeness check has to ask what it did not look at, not only what it found.**

  Still (M), but a *different* (M): add aggregation and cross-module scope to the surface that exists,
  give `SavedView.config` a schema, and let a view be shared. **Building the entry as written would
  have rebuilt working filtering.** Items 3 and 4 land in `models.py`/`routers/modules.py` — check the
  lane table before starting, that is not lane C's to take unilaterally.
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

- ✅ **R23-CONSTRAINTS — SHIPPED; the band row was stale.** Verified 2026-07-31 against the code, not the entry: `services/data/src/aec_data/dim_constraints.py` solves dimensional locks as a **linear least-squares system with priority tiers**, reached at `POST /projects/{pid}/constraints/solve` (`analysis.py:522,542`), with `test_dim_constraints` registered and passing. **No new dependency was added** — the module's own docstring records why: the roadmap had unblocked this by accepting `kiwisolver`, and that reasoning was right about the *shape* and wrong about the *need*, since `lstsq`'s **rank** is the degrees of freedom and its **residual** is whether a tier is satisfiable — the two numbers the UX actually needs. *(Original entry below.)*
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
- **R23-STOREY-LOD** *(L)* — server-side coarse proxies per storey (extruded footprint / AABB) for
  small parts, MEP and furniture, swapping to real fragments on demand. Server-side keeps it
  deterministic, offline and $0. *`docs/internal/archive/phase2-large-models.md` claims no custom LOD is needed and is
  itself marked superseded — that claim is the thing to retire.*
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
- **R23-BATCH-OVERLAYS** *(S)* — app-authored overlays (pins, grid, snap markers, dimensions, clash
  markers) use **zero** instancing; `three@0.184.0` has `BatchedMesh`. Keep the default BIM pass off
  `MeshStandardMaterial` (presentation mode only); make FOV/FAR responsive by viewport class.
- **R23-SYMBOL-COUNT** *(M)* — deterministic template-match symbol counting in the **existing** pdf.js
  takeoff worker: mark one instance, normalised cross-correlation, non-maximum suppression.
  **Zero new dependencies**, offline, auditable — which matters for quantities that feed a bid.

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


- ⭐ **R24-PERF-BUDGET** *(S)* — **now measurable**: `metrics.quantile(0.95)` reads the histogram
  above. The remaining work is the asserted budget itself (100 ms click echo, 1 s panel, p95 < 100 ms)
  as a `test_*`, per *Verify, don't recall*. Note what the server can and cannot say: request p95 is
  server-side and now real; **click-echo latency is client-side and still needs a beacon.**
### Sprint 2 — cash the moat *(the differentiation no competitor can copy)*

- ⭐ **R24-ELEMENT-CARD ②** *(M — was L)* — the strip exists and works. The remaining work is
  **call sites**, not components: render it in RFI, estimate line, pay app and COBie row. Extract from
  `viewer/inspectorTabs.ts` into a viewer-independent module first, since those four surfaces must not
  pull in three/@thatopen.
- ✅ **R24-TRACE-UI ② — SHIPPED 2026-07-31 (`b3a630ea`).** 19 headline figures report which assumptions
  the caller **declared** and which the engine **defaulted**, derived from `model_dump(exclude_unset=True)`
  — deriving from the validated dump would report everything as declared and answer the reviewer's
  question with fiction (mutation-checked: it drops the sparse deal from 8 defaulted inputs to 2).
  `element_link` is `None` on every figure with a stated reason, because the proforma holds no GlobalId
  and an invented terminus is worse than none. `FIGURE_INPUTS` is completeness-checked **both ways**
  against `solve()`'s own output. `POST /proforma/provenance`, plus inline on `/proforma/solve`.

  *Original entry below — the premise correction is the reason this was built backend-first:*
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

* ✅ **R27-LAYOUT ① — DONE; both halves shipped (v0.3.702 + v0.3.778).** *Was: the layout is written but
  never read back.* *(Corrected after checking the code:
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

* ✅ **R27-SKILL-GAP** *(S)* — **DONE 2026-07-31. Premise mostly FAILED; the diff is nearly empty.**

  **The corpus is [`datadrivenconstruction/DDC_Skills_for_AI_Agents_in_Construction`](https://github.com/datadrivenconstruction/DDC_Skills_for_AI_Agents_in_Construction)** — recorded here because the
  entry named it only as "a 221-file skills corpus (MIT)", and *a gap-check whose input nobody can find
  is not repeatable*. Identity confirmed by count (exactly **221 `SKILL.md` files**) and the licence
  read **from the LICENSE file, not the README**, per this ring's own rule: MIT.

  **32 of the 221 (15%) are dead on arrival.** They are CWICR-based (`cwicr-*`,
  `bim-cost-estimation-cwicr`, `semantic-search-cwicr`) and this ring already refused **CWICR data as
  CC BY-NC 4.0**. The MIT skill files are usable; the data they operate on is not. Effective corpus
  ~189 — and the single largest domain in it is one already ruled out on licence.

  **Checked precisely rather than by keyword, and the plausible gaps were all already built:**
  `ids-checker` → `ids_authoring.py:63` + `model_ci._ids_check:78` with real `.ids` files at
  `{pid}/ids/project.ids` · `energy-simulation` → `energy.py`, `energy_star_bridge.py` ·
  `schedule-compression` → `px.py:286-309`, crash **and** fast-track levers with `days_potential` ·
  `weather-impact-scheduler` → `notice_clock.py:128`, weather-delay notice citing §15.1.6.2 · plus
  procurement, contract-clause, prequal, payment-app, punchlist, lien-waiver, warranty, RFI, submittal,
  look-ahead, resource-levelling, QTO, clash, 4D and carbon — all with modules or engines.

  ❌ **Deliberate divergence — do NOT file this as a gap and do not "close" it.** The corpus has
  `vector-search`, `rag-construction` and `semantic-search-cwicr`; we have **zero** embedding/vector
  code and `doc_text.search()` is pure token overlap. That is a **stated design choice**, not an
  omission — the module docstring says *"Deterministic retrieval … fully offline; no LLM required and
  none silently invoked."* Adopting semantic search trades that away. Refused on purpose.

* ⭐ **R22-PHOTO-CV** *(M — needs a mission-fit call before building)* — **the one real gap the corpus
  surfaced.** Three skills (`progress-monitoring-cv`, `progress-photo-analyzer`, `defect-detection-ai`)
  have no counterpart here; grepping for photo analysis returns nothing but storage.

  **The substrate already exists, and it is the reach shape one layer up:** `routers/verification.py:109`
  uploads a photo **against a GUID**, so site photos are already element-attached — and *nothing reads
  them*. The data is landing and no consumer exists. That makes this cheaper than a green-field CV
  feature and it is why it is worth recording rather than dismissing.

  **Gate it on the non-negotiables before any build:** a CV model is a new dependency and probably a
  large one, the viewer must stay fully offline, and licences must be MIT/BSD/Apache. If those cannot
  all hold, the honest outcome is to refuse it in place — the way semantic search was refused above.

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
weakest part. That is direct corroboration of **R23-SYMBOL-COUNT** (Lane B) and a reason to treat it as
higher-value than its size suggests — it is the measurable floor under every takeoff claim.

The framing worth adopting even though it is not a feature: **reduce verification cost, not just
production cost.** Several items already do this without saying so; it is the sharper way to argue for
them.

## 📐 R34 — TAKEOFF ACCURACY: the platform cannot count *(2026-07-30)*

Prompted by the user ("accurate counts are important") and researched against **OpenTakeoff**
([Kentucky-ai/opentakeoff](https://github.com/Kentucky-ai/opentakeoff), **Apache-2.0**, browser-only,
no paid dependencies — licence and offline constraints both satisfied, so it is usable as guidance and
in principle as code). Three gaps, all verified in our source rather than assumed.

### ⭐ R34-TAKEOFF-COUNT *(M)* — there is no count measure at all

`takeoff2d.py` defines `_UNIT_LABEL = {"area": "m²", "length": "m"}` and every entry in
`TAKEOFF_ASSEMBLIES` is `area` or `length`. **The platform cannot take a count off a drawing.** Not
doors, not fixtures, not receptacles, not sprinkler heads — the operation an estimator performs most
often on a plan set is absent, so a count today is done outside the platform and typed back in.

That is also the item with an external measurement attached: models score **40–55% on object-counting
from drawing sets**, symbols and linework the weakest part, which makes counting the measurable floor
under every takeoff claim. Worth noting that OpenTakeoff — a dedicated takeoff tool — offers a Count
*tool* but **no automated symbol-detection algorithm**, so the manual-count-with-good-ergonomics path
is the proven one and automatic symbol recognition is genuinely unsolved rather than merely unbuilt.
Build the honest version first: a count measure, priced per unit, that a human or an agent places.
Pairs with **R23-SYMBOL-COUNT** (Lane B) which is the recognition half.

### ✅ R34-SHEET-SCALE *(S)* — SHIPPED 2026-07-31 · see [`roadmap-completed.md`](roadmap-completed.md)

### R34-MEASURE-PROVENANCE *(S)* — a measurement does not record how it was made

OpenTakeoff's best idea, and the one most aligned with where this platform already went: **every
measurement records its scale, whether it was one-click or hand-drawn, and whether a person or an agent
made it.** We record the number.

We already apply exactly this principle to money (`COST-DB` rate + vintage + source) and to options
(`derived / declared / unlinked / unavailable`). A traced quantity is at least as contestable as a
rate, and once an agent can place measurements the question "who measured this, how, at what scale"
stops being bookkeeping and becomes the basis of the estimate. Same argument as **R24-TRACE-UI ②**.

### Not adopted

Its flood-fill room tracer, adaptive thresholding for scans, and angle-locking already have our
equivalents (`takeoff2d` does shoelace area and polyline length server-side; the browser traces). Its
measurement engine is **deterministic geometry, not ML**, which is the same choice we made — worth
recording because "AI takeoff" invites the opposite assumption.

## ✅ R33-CLAWBACK-AMOUNT — SHIPPED in PR #136 (`856970c8`), 2026-07-31

*Kept below with its original text because the reasoning is the reusable part — it is the worked example
of why a money check must compare a **value**, not a range. Fixed by `solve_clawback_for_pref()`, which
solves for the cash at the final date that lifts the LP's XIRR to the pref.*

### 💰 the GP giveback was computed with no time dimension *(diagnosed 2026-07-30)*

**Lane C. Researched and specified here; deliberately NOT implemented in this session** — see the note
at the end, which is part of the item.

### The defect, measured on the repo's own fixture

`proforma/waterfall.py` computes the clawback as:

```python
owed = (pref_rate - lp_irr) * lp_contrib   # rough restitution proxy
```

Its own comment calls it a proxy. It is **a rate multiplied by a principal with no time factor**, so it
cannot express the money needed to move a multi-year return. On the clawback fixture already in
`test_waterfall.py` — `lp_irr = -3.72%` against an 8% pref, `lp_contrib = 900`, three years — it yields
`(0.08 - (-0.0372)) x 900 = 105.49`, and the GP returns that out of 151.13 of promote. An LP sitting
11.7 percentage points under its pref for three years on 900 of capital is owed materially more than
105.49; on a separate clean 5-year conventional case the same formula understated the exact shortfall
**5.8x** ($41,485 against $240,466).

Second, smaller defect, already documented in that test file's own comments: the guard
`if lp_irr is not None` means the clawback **silently does nothing** whenever XIRR has no root —
**26% of a 729-pattern sweep**.

### What the market actually does (researched, two independent sources)

- The pref is an **accruing balance on unreturned capital** (simple or compounding) — a capital-account
  mechanic. **We already do this correctly** (`pref_accrual="compounding"`, `lp_unreturned`).
- The clawback runs at the capital event when the GP has taken more promote than it was entitled to on
  a whole-deal basis, and it returns **the excess, capped at the promote actually received**.
  Our `min(owed, period_gp)` cap is therefore **already right**; only the `owed` figure is wrong.
- The hurdle is *usually* stated as an IRR and *can* be stated as an NPV/accrual test — the user's own
  framing, and the reason the implementation must not assume a root exists.

### The fix, and the reason it is small

**The correct solver is already in the same file, twenty lines above.**
`solve_cash_for_irr_hurdle(...)` bisects on a distribution until the LP's XIRR reaches a target. The
clawback needs exactly the inverse: *the cash added at the final date that lifts the LP to the pref*,
capped at the promote paid. The file contained the right technique and the clawback path used the proxy.

```
owed = bisect(extra in [0, promote_paid]) until xirr(lp_cf with extra at final date) >= pref
```

Two edge cases, both decided in the LP's favour, because a lookback exists to protect the LP:
`xirr` returning `None`, and a promote too small to close the gap — **return the full cap** in each.
Report `clawback_owed` and `clawback_restored` separately: they differ when the promote cannot cover
the shortfall, and reporting only the restored figure lets a partly-cured deal read as fully cured.
Both must be `None` (not `0.0`) when clawback is off, so "not requested" never reads as "nothing owed".

### Why this is specified rather than shipped

Two implementation attempts were made and both reverted. The first changed the *test* (IRR to NPV) as
well as the amount, which silently alters behaviour on non-conventional cash flows; the second was
abandoned mid-patch. More usefully: during the first attempt the "verification" was run against
**fabricated fixture constants** — `LP`/`GP`/`TIERS` invented rather than read from the test file, and
the tier key guessed as `irr` when it is `hurdle` — so every number it produced described a deal that
does not exist, and one of them was reported as a finding before being withdrawn.

That is the [[confident-wrong-beats-missing]] shape on money code, and the reason the item carries this
paragraph: **read the fixture, never reconstruct it**, and verify a waterfall change through
`run_waterfall`'s returned dict rather than by rebuilding `lp_cf` outside the function, which is where
both errors entered. Conservation, monotonicity, cap-respected and LP-reaches-hurdle are all assertable
from the public output alone.

## 🗄 R32 — THE FILING SPINE: model, drawings and specs as controlled documents (2026-07-30)

From a user-supplied fileshare-standard study. **Most of the machinery already exists and the premise
is a wiring problem, not a build** — the eighth premise this week that was mostly built. What follows
separates what is already shipped, what is genuinely missing, and what in the source study does **not**
apply to this product, so nobody re-derives any of it.

### Already built — do NOT rebuild

| capability | where |
|---|---|
| standard folder taxonomy as **data**, per-node owner role, discipline, default CDE state, `required` flag | `folder_template.py` (11 top-level folders, QS/contract-admin shaped) |
| file store with **revision + supersession** — same name in same folder supersedes, prior kept for audit | `docmanager.py` |
| **"current only" is already the DEFAULT** — `list_folder(..., include_superseded=False)` | `docmanager.py:115` |
| filename + sheet-ID conventions with a validator and a register audit | `naming.py` (ISO 19650 container names · US NCS sheet IDs) |
| CDE states `wip → shared → published → archived` | `modules/information_container/` |
| tree, upload, move, folder listing routes | `routers/documents.py` |

So "standardise the format" and "version it" are, at the file-store layer, **done**. The gaps are
elsewhere and they are specific.

### ✅ R32-FILE-GENERATED *(M)* — SHIPPED 2026-07-31 (`4f6a5c84`)

**Was measured:** `sheetgen.py`, `drawingset.py`, `issuance.py` and `specs.py` contained **zero**
references to `docmanager`. Generated drawings and specs were produced, returned and never entered the
controlled tree — no revision, never superseding anything, absent from the file manager. Every
governance property the document layer implements was unavailable to exactly the artefacts the platform
itself produces. *(The original entry named `specmanual.py`, which does not exist.)*

**Now:** issuing a set files it. `filing.file_transmittal()` runs on issue and lands the transmittal in
`02_Drawings`; `filing.file_drawing_set()` compiles and files the set as the next revision of one
document. The supersession logic finally has a caller — which was always the whole item.

**Still open here, and it is the honest remainder:** only the **drawing** path is wired.
`specs.py` produces a submittal log rather than a spec manual PDF, so there is no spec artefact to file
yet; when one exists it belongs in `01_Contract Documents/Specifications`, by rule 2. Recorded rather
than quietly counted as done.

The four decisions this shipped with are listed in Band 2 above, and the `12_Model`-not-`required`
question is still the user's to answer.

### ✅ R32-MODEL-IN-TREE *(S)* — SHIPPED 2026-07-31 (`44a901bd`)

Was: two parallel stores — the source model at `{pid}/source.ifc`, the document tree at
`{pid}/docs/<folder>/`, with **no folder for the model**. The artefact everything else derives from was
the only one with no revision, no supersession and no presence in the file manager.

Now: `12_Model` / `12_Model/IFC` / `12_Model/Federated` are in the standard taxonomy, and
`filing.file_model()` files the model through `docmanager` — so a model revision **is** a document
revision, superseding the prior one and leaving the as-issued version recoverable. Reachable at
`POST /projects/{pid}/documents/file-model` and `GET /projects/{pid}/documents/model-history`.

**Three decisions recorded here because they constrain R32-FILE-GENERATED:**

1. **File on publish, never on save.** `source.ifc` is rewritten by every edit recipe; filing on write
   would mint a revision per keystroke and make the chain meaningless.
2. **File by KIND, into the folder that kind already uses** — no `Generated Drawings` folder. A silo
   for generated output would rebuild the same two-stores problem and split "the current drawing set"
   across two places, which is exactly what R32-CURRENT-SET then has to reconcile. **A test asserts no
   such folder exists**, so this cannot be quietly reversed.
3. **`12_Model` is deliberately NOT `required`.** `required_paths()` feeds the document-control health
   score, so marking it required would drop every existing project's compliance number for something
   they have not had the chance to do. Whether an unfiled model *should* count against health is a real
   question — but it is a policy change, and it needs the user's call rather than a side effect.

*Bug found by its own test: history was ordered by `uploaded_at`, which is second-resolution, so two
revisions filed in the same second tied and the order became whatever the sort did. Now ordered by the
monotonic index sequence.*

### R32-CURRENT-SET *(S)* — the drawing display is not the file manager

`docmanager` defaults to current-only, but the drawings UI reads the drawing registers, not the
document tree, so "show only the current set" is not enforced where field users actually look.
Once generated sheets are filed, the display should read the **published, non-superseded** set — one
source, not two.

⚠️ **Gap-check done 2026-07-31, and the premise needs restating — the real gap is worse than "two
sources", and it is a PRODUCT decision rather than a wiring job.**

The register *does* already compute a current set, so "superseded sheets are shown" is **not** the
defect. `drawingset.register()` groups revisions per sheet number and takes `revs[-1]` after sorting by
`_rev_key` — the newest revision wins and older ones go to `superseded`. What it does **not** do is
consult issuance at all: there is **no reference to `drawing_issuance` in that computation**, and
`workflow_state` is carried onto the row but never filtered on.

So the register's "current" means **the latest revision anyone authored**. The document tree's "current"
now means **the latest revision actually issued** (`SET_TITLE` supersession, shipped with
R32-FILE-GENERATED). Both are legitimate answers to different questions:

| question | answered by |
|---|---|
| what is the newest revision of record? | the register — right for the design team |
| what was released, and is therefore buildable? | the filed set — right for the field |

✅ **DECIDED by the user, 2026-07-31: the display shows the LATEST AUTHORED revision.** The current
behaviour is therefore correct and this item **closes without a code change** —
`apps/web/src/reportCenter.ts:139` calls `api.drawingSet(pid)`, which is the register, which is
latest-authored. Nothing to rewire.

**The concern was raised and the decision stands, so it is recorded rather than re-argued:** a viewer of
that panel can be looking at a revision that was never issued. The mitigation is that the issued set is
*also* reachable and is now first-class — the filed `Drawing Set` document in `02_Drawings` supersedes
per issue, the issuance register records every release, and a transmittal PDF names exactly which sheets
and revisions went out. Anyone who needs "what was released" has an authoritative answer; the panel
simply is not that answer.

**Do not "fix" this later by redefining `current_set`.** If the two meanings ever need to appear
together, add a labelled `issued` view beside `latest` — never change what the existing number means.
Two things called "current" that silently swap meaning is worse than two clearly-named things.

### R32-TAXONOMY-LIFECYCLE *(M — needs the user's call on scope)* — 11 folders is construction-only

Our taxonomy is `01_Contract Documents … 11_Final Account`: contract administration for a job already
under way. The study's is a 20-folder **development** lifecycle — land acquisition and due diligence,
entitlements and permitting, finance and proformas, BIM/CAD/GIS, sales/leasing/marketing, ownership
handover, plus an explicit `14_External-Partner-Exchange`.

For a platform whose users are developers as well as builders, everything before contract award and
after turnover currently has no home. **This is a decision, not a build**: extending the tree changes
every existing project's structure, and the `required`-flag completeness score with it. Options are
(a) extend the single tree, (b) ship a second template selected per project type, (c) leave it. Do not
start without an answer.

### From the study, deliberately NOT adopted

| in the study | why not |
|---|---|
| MyWorkDrive as the access layer; **NTFS permissions as the source of truth** | A different architecture. Our store is object storage with application RBAC and per-project roles; there is no Windows ACL to preserve. Adopting it would mean giving up the permission model the whole platform already enforces. |
| PowerShell deliverables (`New-ProjectStructure.ps1`, `Set-ProjectPermissions.ps1`, AD group scripts) | Those provision a Windows file server. We provision a project via the API; `docmanager` already materialises the tree. Nothing to port. |
| elFinder hardening (upload RCE via `connector.minimal.php`, extension allowlists, disabling script execution in upload dirs) | **We do not run elFinder.** `docmanager.py` describes itself as "elFinder-style" and `portal/panels/documents.ts` is our own implementation — the name is a simile, not a dependency, so the CVE class does not apply. Recorded because the phrase in our own docstring will otherwise make someone think it does. |
| `90_Superseded` as a *folder* | We supersede **in place** with an index flag and hide by default, which is strictly better: the file keeps its identity and its folder, and history is a filter rather than a move. Moving superseded files to a sibling folder would break the "same name, same folder" supersession rule `docmanager` is built on. |

**Transferable and worth taking:** the naming pattern's explicit `Rev[XX]` fixed-width field and ISO
date ordering (compare against `naming.py`, which may already satisfy it); the metadata dictionary as a
checklist for what a filed document should carry; and the controlled-vs-working split as a *rule* —
a document is one or the other, never both.

## 🔭 R31 — EXTERNAL SCAN (15 sources, 2026-07-30)

Fifteen sources reviewed: five open-source repos, five commercial products, two engineering-practice
articles, one capital-allocation essay, one curated finance list, one profile. **Most describe things we
already have** — that is the honest headline, and the rejected list below is the more useful half of this
scan, because it stops the exercise being re-run.

**One genuinely new build item, one strong corroboration, three gap-checks.**

- ✅ **R31-SCHEMA-DIAG** — **SHIPPED.** `services/data/src/aec_data/schema_diag.py` +
  `test_schema_diag.py`, served at **`GET /projects/{pid}/models/schema-diag`** beside `/models/qa`
  and `/models/norm-valid`.
  **The route was in the OpenAPI schema and raised `NameError` on every call** — `source_ifc_path`
  is imported into that module as `_source_ifc`. Presence in the schema proves *defined*; only the
  request proves *callable*, and a schema-only assertion would have shipped it. `test_reachable.py`
  could not have caught it either: it walks the import graph of `aec_api` and this engine is in
  `aec_data`, reached by a lazy import inside the handler. The test now asserts over HTTP, and
  compares the status against the SIBLING routes rather than a literal, so a hard-coded 404 cannot
  keep passing if the whole family starts returning 500.
  **It found a crash on the way in, which is worth more than the diagnostic.** `ifcopenshell` 0.8.5
  **segfaults** — exit 139, reproduced 3/3 — on an IFC ending inside an unclosed `'` literal, the shape
  a truncated upload or an interrupted write produces. A segfault is not an exception: `try/except`
  cannot catch it, so the process handling the request dies. `ifc_loader.open_model` (the choke point,
  **133 callers**) now screens for exactly that one input and refuses it as an ordinary error.
  The screen is deliberately narrow: an unclosed parenthesis and a mid-instance truncation both fail
  the structural checks and ifcopenshell opens them *without complaint*, so refusing everything that
  fails to parse would break uploads that work today — a worse bug than the crash.
  It also found a **real IFC2X3 violation in a shipped sample**: 27 `IfcFurnitureType` instances in
  `basichouse.ifc` pass `$` for `AssemblyPlace`, which the schema declares mandatory. Written by a
  mainstream exporter; the file loads, renders, and passes IDS. That is the argument for the whole item
  in one example. Zero false positives across the other shipped samples.
  Original scope below, kept because the reasoning is what justified the build:

- ✅ **R31-SCHEMA-DIAG** *(shipped — original entry, kept for the reasoning)* — **validate the IFC against the SCHEMA, not just against a spec.**
  Everything we have scores *completeness* or *hygiene*: `openbim_quality` is IDS rule-compliance % and
  LOIN completeness over the `{guid: element}` properties index; `model_qa` is hygiene (duplicate
  GlobalIds, overlaps, orphans, unenclosed spaces, blank names, wrong storey). **Nothing checks
  structural validity**: an unknown entity type, a dangling `#12345` reference, an attribute of the wrong
  type, an attribute violating its declared cardinality.

  Why it matters now rather than before: **we WRITE IFC.** Since authoring became a first-class goal the
  platform emits files, and a model can score **100% IDS-compliant and still be rejected on import by
  another tool** — those are different failure classes, and only one of them is currently visible. This
  is also the class of defect a viewer hides: geometry renders, the file is broken.

  Reference implementation to study, not vendor: [`NepomukWolf/vscode-ifc`](https://github.com/NepomukWolf/vscode-ifc)
  (**MIT**) runs exactly these diagnostics through an IFC language server — invalid references, type
  mismatches, unknown entities, cardinality errors. `ifcopenshell` can express most of it server-side.
  Premise-check first: confirm none of `model_qa` / `quality` / `norm_valid` already covers a given check
  before adding it, because three of the four names above sound like they might and do not.

- **R31-PIPELINE-ALLOCATE** *(L)* — **allocate constrained capital ACROSS the pipeline, not within one
  project.** We score options *inside* a project (`GEN-SCORE`, `SHADOW-COST`, `schedule_options`) and we
  *report* across projects (`FIN-PORTFOLIO`, `benchmarking`). The missing step is the decision itself:
  given N candidate projects with cost, return, risk and timing, and a capital constraint, which subset
  and what sizing. `scipy` is already a dependency (`requirements.in:27`), so the optimiser needs **no new
  package** — this is deliberately not the "add a portfolio library" version of the idea.

- ✅ **R31-SYNDICATION-TAIL** *(M)* — **CHECKED 2026-07-31; two of three asks already built. Rescoped to
  `R31-K1-PACK` below.** The entry's own instruction — *"Do not build a cap table before confirming
  `capital.py` lacks one"* — was the right one and it **does not lack one**: `capital.cap_table()`
  returns ownership %, contributed / distributed / **unreturned**, per-class rollup and sorted rows, and
  is reached from `distwaterfall.py:67`, `report_builders/finance.py:293,510` and `reports.py:103`
  ("Investor Cap Table"). Soft/hard commitment tracking is built **under a different name**: `investor`
  states are `prospect → committed → funded → exited`, so soft circle and hard commitment are workflow
  states rather than an enum somebody was looking for.

  ⚠️ **The name collision that probably produced this entry:** the **`commitment` module is
  CONSTRUCTION commitments** — Purchase Order / Subcontract / Work Authorization, with `retainage_pct`
  and `cost_code`. It has nothing to do with investor commitments. Reading it as the syndication side
  badly misjudges the item.

- ✅ **R31-K1-PACK** *(S/M)* — **SHIPPED 2026-07-31** (`aabad457`), and it deliberately does **not**
  emit a K-1. A Schedule K-1 reports a partner's distributive share of *taxable income*, which needs a
  §704(b)-allocated income statement; this platform has capital movements and **no income statement at
  all**. So `capital.k1_pack()` returns the half we can evidence and **names what it cannot supply** —
  `is_tax_document: false` plus a `not_included` list (704(b) allocation, depreciation and §754/§743(b)
  basis, guaranteed payments, outside basis / at-risk, separately stated items, state apportionment).
  An accountant told what is absent can supply it; one handed a plausible-looking pack cannot know to.
  `GET /projects/{pid}/k1-pack`.

  **Two money-math decisions worth not undoing:** there is *no beginning/ending capital balance*,
  because that is a §704(b) rollforward needing the income allocation we lack — absent beats guessed
  from contributions, which would be wrong in a way that looks right. And `ownership_pct` is an
  **allocation ratio**, so `allocation_check` reports the exact rounding residual rather than hiding
  it; ratios silently summing to 99.9997% would misallocate income for every partner every year and
  survive inspection. Mutation-checked both ways.

  *(Original entry, kept because the boundary sentence was the spec:)*
- ~~**R31-K1-PACK**~~ *(was S/M)* — **the one genuine remainder of R31-SYNDICATION-TAIL.** `capital.py:90`
  already states the boundary in the statement PDF itself: *"…is informational and not a tax document;
  K-1s are issued separately."* That sentence is the spec. Everything a K-1 pack needs upstream — per
  investor contributions, distributions, unreturned capital, class rollup — already exists and is
  reached; what is missing is the allocation and the document. Well-bounded precisely because the
  boundary was written down rather than left implied.

- ⭐ **R31-CITE-HIGHLIGHT** *(S — premise HOLDS, and it is far cheaper than written)* — **checked
  2026-07-31.** Confirmed: we cite document and page and do **not** highlight the passage.
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

## 🧱 Decomposition & reliability carry-overs (interleave one per few releases)

- ⭐ **SCALE-SEAM ⑥ — `client.ts` is no longer a god-file, but the split is not finished.** ②–⑤ have
  shipped: `schedule.ts` (v0.3.800, 26 methods / 207 lines) · `model.ts` (v0.3.802, 29) · `modules.ts`
  (v0.3.803, 34) · `estimate.ts` (v0.3.804, 12). **`client.ts` went 4,956 → 4,025 lines.** ⑥ is
  `/procurement` (89 lines, 9 methods), then `/auth` (90, 19 — which needs care, because it is the one
  group that owns token state rather than just calling routes).

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

  **Threat model, checked 2026-07-31 — this is a PRODUCT gap, not a live vulnerability, so it does not
  belong in the exploitable band.** What was checked, not concluded: `_plugins_dir()` defaults to
  `<repo-root>/plugins` and is overridden only by `AEC_PLUGINS_DIR`; user uploads land under
  `STORAGE_DIR` (`./storage`) — **the two do not overlap**; no route anywhere under `routers/` writes
  into the plugin directory (`/plugins` is a GET, `/plugins/reload` is platform-admin gated); and
  discovery is off unless `AEC_PLUGINS_ENABLED=1`. So the only way a `.py` reaches `exec_module` today
  is an operator putting it on the disk — which is the same privilege as `pip install`, and an env var
  is a trusted input. **There is no path from an unprivileged caller to plugin execution.**

  That changes the moment plugins are *distributed* — a marketplace, a shared pack, anything a user
  installs rather than the operator. Build the boundary **when that ships, and as its prerequisite**,
  not before; an L-sized process boundary for a dormant operator-only path is cost with no risk retired.

  **Do not confuse this with the A1 `execute_ifc_code` sandbox — a different surface that IS bounded.**
  Probed 2026-07-31 by execution rather than by reading its docstring; all 12 escapes refused and the
  benign case ran: dunder ladder (`__subclasses__`), `import`, `__import__`, `open`, `eval`, `getattr`,
  `lambda`, `def`, `while True`, `model.write` → `SandboxError`; `for i in range(10**12)` hit the
  5s wall-clock deadline at 5.02 s; `10**10**9` hit the chained-`**` integer-blowup guard. No file was
  written. This retires the [[sandbox-object-api-surface]] note's "banning `while` does not bound
  execution" — a deadline now exists and was observed firing.

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

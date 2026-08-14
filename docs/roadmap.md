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

**FIN-SUITE-BLIND closed here on 2026-08-01** (G702 retainage, the 0%-read-as-unset money bug, and
the reserve/benchmarking/proforma sweep) — its full record is in
[`roadmap-completed.md`](roadmap-completed.md). Two seams took its place, both found by the R35 race
sweep rather than by a failing test, which is the reason they rank first: **nothing in the suite can
currently fail if either regresses.**

- ◧ **PARTLY SHIPPED v0.3.876 (2026-08-07)** — R39-UPLOAD-CAP-APP ① and R41-UPLOAD-WARK. **The
  front half is closed; the back half has its primitive and no adopters.** The cap existed and
  decided from `Content-Length`, so a chunked body — the ordinary HTTP/1.1 way to send a body of
  unknown length — short-circuited the condition and was **never measured at all**.
  `bodycap.MaxBodySizeMiddleware` now counts bytes on the ASGI `receive` channel, which bounds every
  route at once rather than a hand-listed set that would be stale the day it was written.
  `storage.put_stream` is the back half's missing primitive (local `.part`+rename, S3 multipart, both
  cleaning up on refusal). **Corrected 2026-08-10: "no call site has been converted" was already
  false when written.** Four were — `routers/authoring.py` (twice), `routers/bcf_api.py`,
  `routers/bim.py` — and `storage.py`'s own docstring says "the four converted routes", so the
  roadmap contradicted the code it was describing. The caller-side helpers exist too:
  `storage.upload_chunks`, `storage.stream_to_path`, `storage.file_chunks`. A fifth converted
  v0.3.927: the APS **RVT** path in `routers/convert.py`, which did
  `rvt.write_bytes(await file.read())` on the largest files anything uploads here.

  **The remaining ~34 sites are NOT all convertible, and counting them as if they were is what made
  this item look bigger than it is.** They split three ways, and only the first is work:
  *(a)* routes that **store** the upload — convertible, same one-line shape as the five done;
  *(b)* routes that hand the bytes to a **whole-buffer parser** — CityGML XML, E57 point-cloud
  decode, BFAST/VIM, `bcf_io.parse_records_bcfzip`, the Excel/CSV sheet readers. Streaming those
  means changing the parsers, which is a different item with a different risk profile, and pretending
  otherwise is how a "convert the call sites" ticket quietly becomes a rewrite;
  *(c)* routes whose payload is **structurally small** — an IDS file, a JSON config, a `.bcf` —
  where the copy is not worth a code change.

  So the honest remaining scope is (a), and the next step is to *classify the 34* rather than
  convert them — **a count is not a work list.**

  **CLASSIFIED 2026-08-13.** Every `await file.read()` in `services/api/src/aec_api/routers/` was
  read together with what it does with the bytes on the next two or three lines, because the call
  itself is identical in all three buckets — which is exactly why the count read as one work item.

  * **(a) stores the bytes — convertible, and this is the whole work list.**
    `documents.py` (`docmanager.upload`) and `modules.py` ×2 (`mod_engine.add_attachment`, single and
    bulk). These hand a `bytes` object to a function that persists it, so converting them means
    widening *that* function to take chunks — `storage.put_stream` already does. **Three, not
    thirty-four. All three converted in v0.3.941–942.**

    **Corrected 2026-08-13: this first said FIVE and named `authoring.py`'s content-shelf asset.**
    That route never stores the upload — it hands the buffer to `content.parse_mesh` and keeps only
    the resulting verts/faces, so it belongs in (b). The misclassification came from reading the two
    lines *after* `await file.read()` (a filename suffix and a category lookup, which read like the
    preamble to a store) instead of following `data` to its single use. **Classify an upload by where
    its bytes are USED, not by what surrounds the read.**

    `bim.py`'s BCF topic attachment is a fourth store site and is absent from this list on purpose:
    R41-UPLOAD-WARK converted it back in v0.3.876, so it has no `await file.read()` left to find. A
    population derived from "sites that still read the whole body" correctly excludes what is already
    fixed — but it also means the list is not "every store site", and reading it as one would
    undercount the surface.
  * **(b) hands the buffer to a parser** — `analysis.py` ×4 (point cloud, sheet recover, IDS),
    `bim.py` ×5 (bundle, BCF zip, clash XLSX/XML), `drafting.py` ×2 and `drawings.py` ×2 (PDF),
    `modules.py` ×2 (openpyxl, BCF), `authoring.py` (IFC open), `verification.py` (`photo_cv`),
    `convert.py` ×3, plus `standards.py` / `research.py` / `review.py`. Streaming these means
    changing the parsers, which is a different item with a different risk profile.
  * **(c) structurally small or already capped** — `properties.py` rejects over `AEC_PROPS_MAX_MB`
    before parsing; the remaining config/IDS uploads are small by construction.

  **Two of (a)'s neighbours were converted in v0.3.940** and were not on anyone's list, because they
  are the one shape that hides in bucket (b): `cost.py`'s DXF takeoff and `authoring.py`'s raise-plan
  both read the whole upload and then **wrote it straight back out to a temp file** to hand a *path*
  to a parser. Starlette had already spooled that upload to disk, so each was a
  disk-to-memory-to-disk copy of a file that existed the whole time — the identical conversion
  `convert.py`'s RVT path already carried. Both routes have real upload tests, and mutation-checking
  proved those tests reach the new code rather than merely passing beside it.


### Band 2 — built but unreachable (cheapest real value in the file)

Seven of eleven engines once shipped with no route. The R32 filing-spine entries that occupied this
band are all closed and recorded in [`roadmap-completed.md`](roadmap-completed.md). The current
instances:

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
| `health` | 634 | *(none)* | pure gain — schedule-quality scoring we do not have |
| `compare` | 555 | *(none)* | pure gain — baseline/revision diff |
| `levelling` | 587 | *(none)* | pure gain — resource levelling |
| `locations` | 477 | *(none)* | pure gain — location-based (LBMS) scheduling |
| `resources` | 254 | *(none)* | pure gain |
| `takt` | 444 | `aec_api/takt.py` **163** | **two implementations, same `plan()`** |
| `lastplanner` | 436 | `aec_api/pull_plan.py` **248** | overlapping |
| `risk` | 303 | `aec_api/schedule_risk.py` **195** | overlapping |
| `progress` | 214 | `aec_api/progress_rollup.py` **134** | overlapping |

**The split matters more than the total, and it is why this is two sprints rather than one.** Five
modules have no counterpart — wiring those is additive and cheap. Four *already have ours beside
them*, so "add an adapter" would create the second implementation this repo has been burned by
before. `takt` is the sharpest case: both define `plan()`. Theirs also has `crews_for`,
`minimum_takt` and `to_network` (crew sizing, minimum feasible takt, and conversion to a CPM
network); ours has `takt_svg`, which theirs does not. **Ours is a renderer that grew an engine; the
answer is to keep our renderer and delete our engine**, not to run both.

- **R45-SCHED-REACH ①** *(M)* — adapters for the five with no counterpart: `health`, `compare`,
  `levelling`, `locations`, `resources`. Each gets a thin `aec_api` adapter + route, following the
  `schedule_cpm.py` pattern (adapter converts our model to theirs, never the reverse — the vendored
  `core` is stdlib-only *by contract* and must not learn about SQLAlchemy). Ship one at a time; each
  is independently valuable and `health` is the highest — a schedule-quality score is the thing a GC
  is asked for and cannot currently produce.
- **R45-SCHED-DEDUPE ②** *(M, do AFTER ①)* — settle the four overlaps, one decision each, in the
  order `takt` → `progress` → `risk` → `lastplanner`. For each: diff the two behaviours, keep the
  deeper engine, keep our rendering/persistence, delete the loser, and write a test asserting there
  is exactly one implementation. **Do not start this until ① proves the adapter pattern**, and do not
  do it as a batch — four simultaneous deletions across the schedule surface is how a regression
  hides.
- **R45-VENDOR-REACH ③** *(S)* — the gate this needs and does not have.
  `test_massingplan_vendor.py` proves the copy is *faithful* (digest, stdlib-only, no fork). Nothing
  proves any of it is *reached*. A re-sync can therefore double the vendored tree and every check
  stays green — which is exactly what just happened. Add a transitive-reachability assertion with an
  explicit, shrinking allowlist of unreached modules, so the number can only go down.

- ◧ **R31-CITE-HIGHLIGHT** *(NOT S — snippet display shipped v0.3.868; the data-model blocker was
  CLEARED v0.3.877; **the citation became a control in v0.3.938** — all that remains is the viewer
  `PageWords` bridge for the in-page highlight box)* — **the citation could not be resolved to
  anything openable, so "make it a control" had nothing to click through to.**

  **SHIPPED v0.3.938 — and the delay was self-inflicted, which is the lesson.** The work was one
  afternoon once the premise was checked. What kept it open was that both citation renderers declared
  their own inline `{ page, snippet }` type and dropped the `doc_id` and `openable` the server had
  been sending since v0.3.877 — so the capability was invisible from both ends, and a code comment
  plus this very entry both asserted a blocker that no longer existed. `citationContract.test.ts`
  now asserts the shared `DocCitation` type against `doc_text.py` by set equality, so a client type
  narrower than the response fails a build instead of quietly re-scoping a feature as blocked.

  **CLEARED 2026-08-07.** The blocker was smaller and dumber than this entry knew: `ingest` ran
  `extract_pdf_text` and then **discarded the PDF**, so even when a real document existed nothing
  afterwards could open it. The index entry now carries `source` / `source_kind`, a posted PDF is
  stored beside its chunks, `GET /projects/{pid}/doctext/{doc_id}/source` serves it, and every
  citation reports `openable` as a value. A text-only ingest reports `openable: false` — there is no
  document behind it and there never was, so that is an answer rather than a gap. **What remains is
  only the viewer half**: `citeLocate.ts` is written against a structural interface and still needs
  something to supply `PageWords`.

  `doc_text.py` derives `doc_id` as a **slug of the document's name**, and the doctext index stores
  `{doc_id, name, chunks, sections, ingested_at}` — no file id, no path. `ingest(pid, name, text=None,
  pdf_bytes=None)` takes raw bytes plus a name, so **a doctext document need never have been a stored
  file at all**; for a text ingest there is no PDF anywhere. `rfi_qa.py:182` switched citations to
  `doc_id` in v0.3.810 describing it as "the RESOLVABLE identifier" — it is not resolvable either, so
  that change moved the dead end rather than closing it.

  Unblocking it needs a backend change first: record the source document (file id or storage key) on
  the doctext index entry at ingest, and accept that text-only ingests can never highlight. Then the
  viewer needs a `PageWords` bridge for `locatePassage` to read — `citeLocate.ts` is written against
  a structural interface precisely so it does not depend on the viewer, but something must still
  supply the words.

  **Shipped instead (v0.3.868): the citation now shows the snippet it is citing**, which the server
  has been sending all along and the UI discarded, rendering `p.12` alone. That is a page number the
  reader had to take on trust in a draft about to go to a design team. It needs no resolution path.

  Original: **the data half and the locator are both done; nothing calls them.** `doc_text.answer()` carries `doc_id` into every citation and `rfi_qa` passes the
  passage as `span` (v0.3.810); `drawings/citeLocate.ts` finds that passage on the page and returns
  its box, degrading through three match rungs and reporting ambiguity (v0.3.816). The remaining work
  is one seam: `portal/panels/aiassist.ts` still renders `"Source: p.12"` as inert `textContent`, and
  its local citation type declares only `{ page, snippet? }` — **it drops the `doc_id` and `span` the
  server already sends.** Widen the type, make the citation a control, call the locator, draw the box.
  *Recorded as unreachable in the module's own header so it cannot be mistaken for shipped
  capability — the mistake this band exists to catch.*

- ◧ **QTO-TRADE — the four procurement methods cannot be wired at all, and this is why.**
  *(**backend half DONE**; the remaining work is the other three methods' screens — Lane B, not C)*

  **BACKEND CLOSED, verified 2026-08-13.** `procurement.normalize_qto_line` accepts either dialect
  and is called by `buyout_packages`; the trade comes from `classification.py`, not from a second
  mapping table beside it — which is what the entry below asked for and the right call, since a
  second table is how two sources of truth start disagreeing about what a wall is.

  **`buyoutPackages` now has a screen (v0.3.939)**: *Buyout packages* on the budget panel feeds
  `qtoByFloor`'s `by_discipline` lines — the exact `{ifc_class, count, unit, quantity, rate, amount}`
  shape that used to produce zero packages — straight into the engine.

  Two empty states are rendered **separately and deliberately**, because collapsing them is the
  specific failure this entry warned about: *no priced quantities* (nothing to package yet) reads
  differently from *lines went in and nothing came out* (a grouping problem). One empty table for
  both is what would have said "this project has no scope" about a fully-priced model.

  Remaining: `procurementLevel`, `procurementLevelQuotes`, `buyoutSchedule` still have no caller.
  They need returned quotes to level, which is a different input than the model.

  **Two agents reached this independently, from different directions, on 2026-08-07** — one from the
  input shape, one from the bid-submission side — and both refused to guess. That convergence is
  what promotes it from a wiring backlog item to a backend finding.

  `services/api/src/aec_api/procurement.py` resolves a line's identity as
  item-or-description-or-material and **skips any line where all three are absent**. Both
  model-derived QTO sources return ifc_class / count / unit / quantity / rate / amount — none of
  those three, and no grouping key. Feeding the engine the exact shape the by-floor QTO produces
  returns zero packages and zero cost. A screen over today's inputs would render
  **"Buyout — 0 packages"**, which reads as *this model has nothing to buy out* rather than
  *this input is incompatible*.

  **The generalisation matters more than the fix:** the reach sweep proved 110 of 110 parseable
  client methods have live server routes, and reachability was allowed to follow from that. It does
  not. **Route existence and input adequacy are different questions**, and the sweep only ever
  measured the first. The blocking work is a trade classification for QTO lines — backend, not UI.

- ✅ **RATCHET-SET — the uncalled ceiling is a scalar with no floor, and it loosened silently today.**
  *(S; `apps/web/src/api/clientCallers.test.ts`)*

  **ALREADY DONE — verified 2026-08-13, and this entry was the stale thing.** The conversion landed
  on 2026-08-07: `clientCallers.test.ts` now holds the committed `UNCALLED` set and there is no
  surviving `toBeLessThanOrEqual` assertion anywhere in the file — the only occurrences are inside
  the history comments explaining why the scalar was removed, which is exactly the shape that makes a
  grep say "still there". It went further than this entry asked, too: rather than one set-equality it
  asserts two directional `toEqual([])` checks, so *newly appeared* and *newly wired* report as
  separate diffs instead of merging into one indistinguishable blob.

  Left here rather than moved to `roadmap-completed.md` with the closing argument intact, because the
  reasoning below is the record of *why* a scalar ceiling was the wrong instrument, and it is worth
  reading before anyone adds another one.

  The assertion is measured-less-than-or-equal-to-ceiling. **Nothing asserts the ceiling is tight**,
  so a *higher* literal always passes. On 2026-08-07 five PRs lowered that one line from four
  different bases; two live instances were caught only by hand: #254 carried 129 onto a main at 128,
  and #273 carried 123 onto a main at 117 — each would have raised the ceiling with every gate green
  and nobody able to see it.

  **Merge sequencing does not fix this.** It decides *which* number lands, not whether it is true:
  two PRs measured against one base are both correct until either merges, and then the second is
  wrong. The second must **re-measure**, not rebase.

  Replace the scalar with the committed **set of uncalled method names**, asserted equal. Tight by
  construction (set equality has no loose direction); merge-friendly (two PRs reaching different
  methods delete different lines instead of fighting over one); and strictly more informative — a
  method moving into the known-uncalled exclusion becomes a visible line move rather than an
  invisible population change.

  **It does not fix the deeper problem and should not be sold as doing so.** A name leaving the list
  still only proves a call site appeared, not that the feature works — a caller wired to an
  incompatible input lowers the number while every gate stays green. That needs a second check:
  a reach PR should show its endpoint returning real data with the arguments its own caller sends.

- ✅ **BOE-MAPPING-DEDUP — the estimate-to-BoE mapping has more than one implementation.** *(S)*

  **DONE — verified 2026-08-13, and this entry's prescription was wrong about where the seam is.**
  The second duplicate was resolved by extracting `apps/web/src/ui/confidenceReading.ts`, which both
  `apps/web/src/portal/panels/budget.ts` and `apps/web/src/portal/register/register.ts` now import;
  the units are applied once there and asserted by `apps/web/src/ui/confidenceReading.test.ts`
  (7 tests). Two panels calling one shared reader is not duplication.

  The instruction below — *"panels should call the seam rather than re-derive it"*, naming
  `services/api/src/aec_api/commercial_drift.py` — could not have been followed as written. That
  module holds `bid_award_figure` / `walk` / `for_project`: bid-to-award **drift**, with no
  confidence function in it at all. The server-side confidence scorer is
  `services/api/src/aec_api/est_confidence.py`, and it already computes the score; what the two
  panels were each re-deriving was the **unit handling on the response**, which is a client concern
  and correctly lives in a client module. **A roadmap item that names the wrong file sends the next
  reader to rewrite working code** — the same failure as R31 above, on the same day.

  The cost-code and total mappings are re-derived client-side where the seam already exists
  server-side in `services/api/src/aec_api/commercial_drift.py`. One duplicate was removed in
  v0.3.879 (the per-record BoE view in `apps/web/src/portal/register/register.ts`); a second remains
  for the confidence reading, now called from both the register and
  `apps/web/src/portal/panels/budget.ts`. Panels should call the seam rather than re-derive it.

  Booked deliberately rather than paid under time pressure: both copies were already merged when the
  duplication was diagnosed, and cutting one mid-flight would have moved the reach ceiling again on
  the files that batch was already fighting over.


- ◧ **R43-VIEWER-CONFORMANCE** *(S — Lane E; MassingViewer issue #512; **RUN 2026-08-13**, full
  result in [`docs/internal/viewer-conformance-2026-08-13.md`](internal/viewer-conformance-2026-08-13.md))*
  — **run their conformance suite against our live API.**

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

- ✅ **CLOSED by PULSE-FINDINGS — `suggestion_clears_horizon` reaches a screen.** *(verified
  2026-08-13)* `apps/web/src/portal/portal.ts` fans `reserveStudy` into the home pulse and maps the
  field to `reserveSuggestionFails` on the deal card. The finding below — *"no panel calls
  `reserveStudy` at all"* — was true when written and is not now.

  Read **strictly**, and that is the part worth keeping: `=== false`, never `!value`. A missing field
  means *the engine did not answer*, and letting that read as *the suggestion fails* invents a risk
  line from an absent value — which costs trust in every other line on the card.
  `apps/web/src/portal/panels/pulse.test.ts` gates the strictness against `portal.ts` source and
  carries a vacuity guard, because the mutation that swapped `=== false` for `!value` passed all 77
  portal tests with nothing guarding it.

- ✅ **CLOSED by PULSE-FINDINGS — `nothing_renovated` renders.** *(verified 2026-08-13)* Same fan-out:
  `portal.ts` calls `proformaRenovation` and shows the finding on the deal card, preferring the
  engine's own `nothing_renovated_why` and falling back to "no unit completed a start". The claim
  below that *"the only caller of `proformaRenovation` is a test"* is stale.

  **Chasing that one turned up something larger, and it is now gated.**
  `apps/web/src/api/surface.test.ts` introduced a list with *"the methods the rest of the app
  actually calls … each has real call sites in the shell, the viewer or the portal"*, and three names
  under it had no caller but that list. Adding a client method makes the *endpoint* reachable and
  leaves the *screen* as absent as before. `apps/web/src/api/clientCallers.test.ts` now separates the
  two questions and ratchets the second: **132 of 703 client methods have no caller outside
  `src/api` and tests.** Wiring these two fields to a screen is the remaining work, and it lowers
  that number.
## ▶ NOW — parallel lanes *(rebuilt 2026-07-29 at v0.3.785; bands re-seated 2026-08-01 at v0.3.818)*

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
| **A · Shell & IA** | `apps/web/src/shell/`, `apps/web/src/portal/portal.ts`, `main.ts` | R24-CMDK-VERBS · R24-RUNS-INBOX · UX-READINESS-EVERYWHERE · UX-DUP-DESTINATIONS · REL-4 · R40-RIBBON ② · R43-CRUD-FRAGMENTS |
| **B · UI & panels** | `apps/web/src/ui/`, `portal/panels/`, `portal/register/`, `field/`, `reportCenter.ts` | R24-ELEMENT-CARD ② *(moved from E 2026-08-06 — the cell said E, the item's own text says the remaining work is "purely call sites: RFI, estimate line, pay app, COBie row", which live in `apps/web/src/ui/` and `apps/web/src/portal/panels/`. **A lane's paths and a lane's items are two claims and only the first is tested**, so the cell drifted from the item under it)* · R24-CHARTS-GRAMMAR · R24-REPORTS-BY-MOMENT · R24-DENSITY ② · R24-MONO-DATA · R24-TERMS · R24-FIELD-MODE · UX-GANTT · R22-REPORT-BUILDER · R23-SYMBOL-COUNT · R31-CITE-HIGHLIGHT · R36-ROOM-BRIEFS · R38-SHEET-MARKUP ③ · R39-A11Y-JOURNEYS ② · BOE-MAPPING-DEDUP *(the second copy of the estimate-to-BoE mapping; call the seam)* |
| **C · Backend engines** | `services/api/src/aec_api/`, `!services/api/src/aec_api/routers/`, `!services/api/src/aec_api/main.py` | R22-ENTITLEMENT · R22-AGENT-PACKS · R22-PROVENANCE · R22-PIPELINE · R24-PERF-BUDGET · SEC-PLUGIN-LOADER · PERF-WORKERS ① · PERF-THREADS ③ · R35-DEAL-MEMORY · R37-TRIAGE · R40-EOT ② · R39-UPLOAD-CAP-APP ①◧ · R41-CLASH-TRIAGE · R41-COMMERCIAL-DRIFT · R41-UPLOAD-WARK · QTO-TRADE *(blocks the four procurement methods; a trade classification for QTO lines, not UI)* · R43-MASSINGBILL-CORE · R43-PLAN-DRIFT |
| **D · Geometry & drawings** | `services/data/src/aec_data/` | R38-ARRAY-LIVE ③ · R21-4D-CLASH · R28-BUNDLE ② — **the three that landed in PRs #176/#178/#179 on 2026-08-02** (R28-ICDD, R23-STOREY-LOD, R28-UNIFY) are shipped and pending archive. **Corrected 2026-08-06: this read "all SHIPPED and MERGED", which was false for 8 of the 11 codes beside it** — SEC-PLUGIN-SANDBOX is ◧ with its `setrlimit` half explicitly REFUSED, R38-SYNC-VIEW and R21-4D-CLASH are ◧, and five carry no marker at all. A row-level word like "all" has no defined scope, so it drifts the moment the row grows; the item markers are the authority and this sentence is not. **Three carried defects a post-merge review then found, all fixed v0.3.843**: the array editor repositioned nothing on a pitch change, the ICDD writer left a truncated container when it refused, and the guided cut dropped linework silently. *Merged is not verified — that is the argument for the review pass, not against it.* |
| **E · Authoring feel & viewer** | `apps/web/src/viewer/`, `inference.ts` | A29-GUIDE-UNDERLAY ③ *(in flight, PR #199)* · R28-VIEWER ④ · R36-VIEWER-SUBAPP *(the remaining half of the rail arc — the canvas must switch 2D/3D in place, including PRINT)* · R38-SYNC-VIEW ③ *(mostly built; only cursor sync left)* · R38-SOLVER-LOCKS ③ · R23-BATCH-OVERLAYS · R39-VIEWER-OBS ② · R39-DECOMP-VIEWER ③ *(ratchet pinned; seams measured — see entry)* · R38-SYNC-SELECT ③ *(SHIPPED v0.3.829, pending archive)* · R41-MODEL-ALIGN · R43-VIEWER-CONFORMANCE |
| **F · Docs & demo** | `README.md`, `docs/`, `apps/web/src/demo/` | keep the shipped surface honest (below) — no coded items. **`demoData.test.ts` now gates the shell's startup endpoints**; re-run `build_demo_data.py` and that test after adding one |
| **G · API surface** | `services/api/src/aec_api/routers/`, `main.py` | no standalone items: **every lane routes its own work**, which is why this is a lane rather than a shared file |
| **H · Registers** | `services/api/modules/*/module.json` | — |
| **I · API client** | `apps/web/src/api/` | SCALE-SEAM ⑧ |
| **J · Build & tooling** | `apps/web/scripts/`, `apps/web/vite.config.ts`, `apps/web/src/style.css`, `services/api/test_file_sizes.py`, `services/api/run_tests.py` | BUILD-WORKTREE-CHUNKS *(lane added 2026-08-06 — **three sessions in one day flagged a path belonging to no lane**: `services/api/test_file_sizes.py`, `apps/web/src/style.css`, and the build scripts. Each flagged it correctly and then had to edit it anyway. An unowned shared path is not neutral ground; it is a collision nobody is watching for)* · R41-BUNDLER-SPLIT |

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
`proforma/` · `drawings/` · `kernel/` · `pins/` · `studio/` · `tools/` · `tree/` · the loose `portal/`
files · `tooling/` + `dev/` (probably J) · `account/` · `connections/` · `deploy/`.

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
deliberately. The live case: **`R23-SYMBOL-COUNT` and `R38-SHEET-MARKUP ③` are Lane B and land in
`apps/web/src/drawings/`, while `R36-DRAWINGS-RETURN` is Lane A and lands there too** — so `drawings/`
is contested by two lanes right now, the same shape as the register with the extra twist that nobody
owns it. It needs its own premise-check and possibly the same answer. It is deliberately left open:
guessing an owner for a directory two lanes are already aimed at is how the register problem was made.

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

- **CC0-1.0 on the permitted licence list.** We already ship 59 CC0 files under
  `services/data/families/external/`, and `manifest.json` records the licence in four places — so the
  written rule is narrower than the shipped reality. CC0 is a public-domain dedication, strictly more
  permissive than MIT. The recommendation is to add it; **widening an allowlist is not ours to do.**
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

- ◧ **R43-MASSINGBILL-CORE** *(M — Lane C; kit reviewed 2026-08-10 at their pin `3af9124c`)* —
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

- ✅ **R43-PLAN-DRIFT** *(S — Lane C; local half v0.3.943, cadence DECIDED + shipped v0.3.944)* —
  **pin cadence for the vendored massingplan engine.** What does not exist is a way to notice when
  the pin stops being correct. The decision outstanding is cadence, not correctness.

  **The pin named here was stale, which is the item's own failure mode.** This read `155640a7`;
  `VENDOR.md` records the tree moved to `b703dca4` on 2026-08-11 and says so explicitly — *"was
  `155640a7`, 2026-08-10"*. A pin copied into prose drifted from the pin in the tree, and nothing
  noticed. Corrected 2026-08-13.

  **CADENCE DECIDED v0.3.944: weekly, non-blocking, one reused issue.**
  `.github/workflows/vendor-drift.yml` runs `services/api/vendor_drift.py` on a Monday schedule and
  opens/updates a single issue; it never fails a build, because upstream moving is not a defect in
  this tree and a red nobody can fix by editing our code teaches people to ignore red. Weekly rather
  than daily because the pin moves a few times a month and noise is how a notification stops being
  read. The issue is **closed again** when the pin catches up, so it does not become furniture.

  **UNKNOWN is a first-class verdict.** A failed upstream query reports "could not tell", never "no
  drift" — otherwise a job that has silently stopped working posts good news every Monday forever.
  `services/api/test_vendor_drift.py` proves all three verdicts are reachable and that the exit code
  stays 0 when drifted. `read_pin` is single-sourced in `vendor_drift.py` and imported by the local
  gate, so the two checks cannot disagree about which commit VENDOR.md names.

  **The half that was never blocked is a test.** *Has upstream moved?* needs a cadence, a network
  and a decision. *Has anyone edited the copy HERE?* needs none of those — only the recipe VENDOR.md
  already writes down. `services/api/test_massingplan_vendor.py` executes that recipe, comparing
  against the digest **parsed from VENDOR.md** rather than a second copy in the test, so a re-sync
  updates one file and the gate follows. It also holds the stdlib-only contract the whole adoption
  rests on. Mutation-checked three ways: a local edit, a digest not updated after a re-sync, and a
  third-party import into `core` — the last caught independently by two checks.

  VENDOR.md earned it. Its own words about the previous, unreproducible digest: *"a recorded
  verification value nobody can recompute is not a verification, it is a decoration."* A recipe
  stated in prose and never executed is one revision from being decoration again.
## 🏗 R21 — LOD 400→500 DOCUMENTATION RING *(from a real LOD 400 shop-drawing set, 2026-07-25)*

Measured against an actual issued wall-section + detail package (13 sheets, 1:100 → 1:10) rather than
against a description of one. The mission is **acquisition → turnover at LOD 500**, and LOD 500 is
field-verified as-built — but a project only *reaches* verification through an issuable LOD 400 set.
These are the gaps between what the platform draws today and what that package contains.

**Tier 1 — the set cannot be issued without these**

- ◧ **R21-4D-CLASH** *(phase 1 shipped v0.3.682; install-before-support still open)* — **sequence clash**: two trades occupying one space in the same schedule
  window, or an install ordered before its support. The 4D timeline and CPM both exist; this reads
  them together.

  **Blocker retired (2026-08-02):** the "no task→element binding" prerequisite was FIXED by
  R25-TASK-BIND (element_guids reaches analyze(); bound_activities counts it in
  `services/api/src/aec_api/sequence_clash.py`) — this prose outlived the code. Phase 2 SHIPPED
  same day: `services/data/src/aec_data/support_graph.py` reports what the IFC *states*, graded by
  what it licenses (connected/assembly/structural; direction only from an analysis model), and
  deliberately refuses to infer support from geometry — a column and beam that touch but are
  unrelated produce zero edges. No relations returns stated:false — absent data, not absent
  conflicts.
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

- ◧ **R22-ENTITLEMENT** *(M/L — ①② shipped: `approval_conditions.py`, `condition_checks.py`)* — **permit & entitlement workflow**: jurisdiction submittal packages,
  review cycles, comment responses, and **conditions of approval carried into the model as
  constraints**. Today there is a hole between "acquisition" and "construction" in our own mission
  statement — we underwrite the deal and we build it, and nothing spans approval.

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
- ◧ **R22-AGENT-PACKS** *(M — `agent_packs.py` shipped; audit half CLOSED 2026-08-06; console is Lane A/E)* — **named agent packs + org "Skills" + a governance console** over the
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

- ◧ **R22-PROVENANCE** *(L — assumptions + estimate legs done; ANSWERS leg is the remainder)* — **cite to file, page and revision.** Every proforma assumption, estimate
  line and agent answer traceable to a source page. Three of thirteen platforms *lead* with this; it
  is what makes AI output admissible in an IC memo or a claim.

  **Estimate leg closed 2026-08-06.** `provenance_report` already said exactly what was missing, in
  code rather than prose: the `estimate` register stored line items as code/description/qty/unit/
  unit_cost/amount and captured no `source`, `quote_ref` or `basis_date`, so `boe_ledger` could only
  run on lines posted in a request body. Those three columns now exist and `from_project` gathers the
  leg from stored records.
  *The bug that mattered was the seam, not the columns.* `boe_ledger` reads `cost_code` and `total`;
  the register writes `code` and `amount`. Passing the rows over unmapped does not raise — `_key()`
  falls through to `description`, so every line still gets a key, `cost_code` returns None on every
  row, and `total` silently drops to None for any line priced as a lump sum rather than qty x unit
  cost. That is a full, plausible, quietly-wrong ledger. The mapping is now stated in one place and
  `services/api/test_provenance_estimate_leg.py` asserts it against `boe_ledger`'s **real output**,
  not a fixture written to agree with it; mutation-checked by emptying the map (4 named FAILs).
  **The ANSWERS leg stays `not_captured` and the verdict still cannot read `admissible`** — agent
  answers are not persisted at all (`cited_answer` is an in-flight contract with no store behind it),
  and a leg reading `no_data` because nobody filled it in is a different problem from having nowhere
  to put it. A store of answered claims is the remaining schema change.

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
- ◧ **R23-BATCH-OVERLAYS** *(S)* — **the instancing clause is CLOSED UNBUILT, with the measurement,
  and the sweep found a different defect in the same place.** Following the precedent set by the item
  directly above: replace the prose claim with a number, and if the number does not justify the work,
  keep the number.

  The premise was "app-authored overlays use **zero** instancing", which is true and turns out not to
  matter, because **there is almost no population to instance.** Enumerated every scene-object
  construction in app code — 31 sites across 11 files, all forms, not a sample — and of the five
  families named above:

  | named family | what it actually is | instanceable? |
  |---|---|---|
  | pins | **DOM `<div>`s** projected per frame (`apps/web/src/pins/pins.ts`) | no — `BatchedMesh` cannot batch DOM |
  | grid | 1 `Line` + 1 `Sprite` per axis (`apps/web/src/viewer/draft/gridOverlay.ts`) | **the only real population** |
  | snap markers · dimensions · clash markers | no mesh overlay exists | nothing to batch |
  | (unnamed) GIS context | **already hand-merged** into 3 objects (`apps/web/src/viewer/gis.ts`) | already optimal |

  Everything else — peer cursors, reference models, the guide underlay, the gizmos — is O(1) or
  O(peers). And where the population *is* real, `BatchedMesh` is still the wrong tool: each grid
  bubble carries its **own 64×64 `CanvasTexture` and material**, and `BatchedMesh` requires a shared
  one. The correct fix there is a texture atlas or a cache, not instancing.

  **What the measurement did find, in `gridOverlay.ts`:** `set()` rebuilds on every work-plane move,
  and `clearMeshes` disposed geometry and material but not the texture — in three.js
  `Material.dispose()` does **not** release `material.map`. Measured `AXES=8 → 8 textures made → 8
  leaked after ONE rebuild`, i.e. a GPU leak proportional to axes × elevation changes during ordinary
  authoring. Fixed by caching bubbles by tag (which also removes the re-rasterisation churn) and
  moving ownership to `dispose()`. A third bug fell out: `getContext("2d")!` asserted a context that
  is null under happy-dom, which is **why the file had no tests at all** — the untestability and the
  defect had one cause.

  **The FOV/FAR clause is now BUILT** (`apps/web/src/viewer/cameraProfile.ts`), and measuring it found
  a second defect the clause did not describe. The library constructs the camera as
  `PerspectiveCamera(60, aspect, 1, 1e3)` and nothing had revisited it:

  - **A fixed VERTICAL fov gives a phone a third of the view a desktop gets** — horizontal fov is
    derived from vertical and aspect, so portrait collapses it: **30°** on a phone against **85°** on
    desktop. Now derived from a target horizontal angle and clamped, so a phone gets ~46°. The clamp
    floor is 60° — today's value — deliberately: this can only ever *widen*, never narrow. A profile
    that computed a "better" 51° for desktop would be a regression shipped as an improvement, and
    nobody reports seeing less as a bug.
  - **`near = 1 m` is wrong for the first-person walkthrough.** `apps/web/src/viewer/walkMode.ts` puts
    the eye at 1.65 m and exists for close inspection — but everything within a metre of the eye was
    clipped, so walking up to a wall or a column made it vanish before you reached it.

  **Why the near plane moves only in walk mode, with the number that decides it.** Depth precision at
  distance scales with `near`; for a 24-bit buffer the resolvable gap is about `z²/(near·2²⁴)`:
  `near=1` gives 2.4 mm at 200 m, `near=0.1` gives **6.0 mm at 100 m**. `apps/web/src/viewer/guideUnderlay.ts`
  lifts its plane 5 mm to avoid z-fighting, so a *global* change would make that underlay z-fight on
  any model of real size — trading a walk-mode defect for a rendering one.

  The `MeshStandardMaterial` clause needs no work — every remaining use is GIS context, not the BIM
  pass.
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
| 04 | long jobs, foreground UI | R24-JOB-TRAY | ✅ **shipped; this row was stale** — `apps/web/src/ui/jobTray.ts` is 373 lines, mounted at `apps/web/src/main.ts:2052`, 28 tests. The ❌ survived its own implementation |
| 05 | analyses are modals → no history | R24-RUNS-INBOX | ◧ **v0.3.947** — history + run-over-run diff in `apps/web/src/ui/runs.ts` / `apps/web/src/ui/runsInbox.ts`. The premise "no runs concept" was **half wrong**: `Job` already stores params, actor, timestamps and result. Routing clash/IDS/cost/energy *through* the queue is the open half |
| 06 | the single-GUID advantage is invisible | R24-ELEMENT-CARD | 🟡 `apps/web/src/ui/lifecycleStrip.ts` + `inspectorTabs.ts` built; now **two** call sites — the viewer inspector and `apps/web/src/ui/elementCard.ts`, mounted from `apps/web/src/portal/panels/traceability.ts:75`. Four surfaces still unwired |
| 07 | onboarding teaches the chrome | FIRST-RUN | 🟡 improved v0.3.777; still not the lot → building → deal chain |
| 08 | persona picker only relabels | *(none)* | ⚠️ reversed on purpose — see Decisions |
| 09 | tools panel mixes verbs with analyses | *(none)* | ✅ **v0.3.848** — `R24-TOOLS-SPLIT` cut the 1087-line `qa` section in two; Analyse is its own rail item |
| 10 | finance numbers have no provenance | R24-TRACE-UI | 🟡 v0.3.775 shipped trace for *cost coverage*; the proforma chain (IRR ← NOI ← rent roll ← area ← GUID) — the audit's actual demo — is not built |
| 11 | density | R24-DENSITY | 🟡 two steps not three (`portal/prefs.ts:71`), dashboards only, **not registers** — which is where the 8-hour user lives |
| 12 | mobile is a bottom sheet in a desktop IA | R24-FIELD-MODE | 🟡 `field/field.ts` is a real offline queue with GPS, still inside the desktop IA |
| 13 | search is scoped to modules | R24-CMDK-VERBS | ✅ **v0.3.946** — verbs, elements, reports and an assistant fallback; `apps/web/src/ui/paletteProviders.ts`. Fixed a second defect on the way: async hits were `concat`ed onto an already-grouped list, so a record landed under a **second** RECORDS heading below Modules |
| 14 | empty states | R24-EMPTY-GUIDE | ✅ **verified done 2026-08-14** — the "24 lines, 'no project' only" reading is stale by a wide margin. `apps/web/src/ui/empty.ts` is 156 lines and R36-EMPTY-STATE shipped the hard part: a register with no rows distinguishes **none / filtered / failed**, because those send a reader to three different places and rendering them identically was the defect. Plus acronym-safe nouns ("No rfis yet" was the bug), `textContent` throughout since the name and the error body are untrusted, and `data-empty` so a test can assert WHICH kind was decided. Curated hints in `apps/web/src/ui/emptyGuide.ts` (157 lines), wired at two `register.ts` call sites, covered by `apps/web/src/ui/empty.test.ts` and `apps/web/src/ui/emptyGuide.test.ts` |
| 15 | charts have no grammar | *(none)* | ❌ dropped → `R24-CHARTS-GRAMMAR` |
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


- ◧ **R24-PERF-BUDGET** *(S — `perf_budget.py` shipped)* — **premise re-checked 2026-08-06: the work
  this entry describes as remaining is done.** It reads "the remaining work is the asserted budget
  itself … as a `test_*`". That test exists — `services/api/test_perf_budget.py` — and it is the
  strong form: the server budget is asserted against **real traffic** driven through the app, with
  the p95 read from the live histogram rather than a synthetic number, and `quantile` returning None
  is treated as a **failure** on the `beyond_histogram` branch, because reading None as "no problem"
  would make the budget pass hardest exactly when latency is worst.
  **The true remainder is the client beacon, and it is Lane A/E, not Lane C.** `BUDGETS` lists all
  three and marks `click_echo` and `panel_load` `measurable: False` with a stated reason — nothing on
  the server can observe a click-to-paint interval. That is the honest shape, not a gap: a budget file
  listing three and quietly checking one is how a green suite implies more than it tested. Whoever
  takes this should build the beacon and flip those two, and should not expect to write a backend test.
### Sprint 2 — cash the moat *(the differentiation no competitor can copy)*

- ◧ ⭐ **R24-ELEMENT-CARD ②** *(S — was M, was L; ◧ added 2026-08-06 — `apps/web/src/ui/elementCard.ts` declares this item and one surface already mounts it, so "nothing exists" was never true; what is open is REACH, not capability)* — the strip exists and works, **and the extraction it
  was blocked on is DONE.** The card's frame + loader live in `apps/web/src/ui/elementCard.ts` and one
  non-viewer surface already mounts it (`apps/web/src/portal/panels/traceability.ts:75`).

  The extraction cost two import lines: `lifecycleStrip.ts` imported **one type** and nothing else — it
  was already viewer-independent and merely *filed* under `viewer/`. Another estimate that came from
  where a file sat rather than what it contained, which is why this dropped L → M → S.

  Remaining is purely call sites: **RFI, estimate line, pay app, COBie row.** No component work, no
  dependency risk — `elementCard.ts` takes a GlobalId and an API client.
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
- ◧ **R24-RUNS-INBOX** *(M; history half v0.3.947)* — clash, IDS, cost and energy become durable Runs
  (inputs, timestamp, author, artifact, **diff against the previous run**) with a per-project inbox.
  Most externally validated item in the ring — see the corroboration note above.

  **The recorded premise, "no runs concept in the web app", was half wrong — and the wrong half is
  the expensive one to assume.** `models.py:Job` already stores every field a run needs: `params`
  (inputs), `actor` (who), `created_at`/`finished_at` (when), `result` (the artifact), and
  `routers/jobs.py` has served them for a long time. There was never a missing table, so the item
  splits into a cheap half and a risky one:

  - ✅ **History and comparison** — `apps/web/src/ui/runs.ts` (pure) and
    `apps/web/src/ui/runsInbox.ts` (render). Runs group by kind, newest first, each diffed against
    the previous **comparable** run. Reachable from the job tray's footer and from ⌘K.
    The decision the module exists to get right: **a metric present in one run and absent in the
    other has a `null` delta, never zero.** Absence-as-zero turns a detector that stopped reporting
    `count` into a confident, precise, invented −412 — worse than no number, because it reads as a
    finding. Same reasoning refuses a **failed** run as a baseline: a run with no result is not a run
    whose every metric fell to zero. Both are mutation-checked.
  - ❌ **Routing the analyses through the queue** — clash, IDS, cost and energy still run in the
    request thread behind a modal, so they never become rows. Four call sites and their handlers;
    the larger and riskier half. Until it lands the inbox is genuinely **empty on most projects**,
    and its empty state says which half is missing rather than implying the feature is broken.

### Sprint 3 — the front door earns its keyboard

- ✅ **R24-CMDK-VERBS** *(M; grouping half v0.3.780 as **R24-CMDK-GROUPS**, providers v0.3.946)* —
  results render in sections (**Do · Records · Elements · Reports · Modules · Go to**), a group is
  inferred from the `hint` a caller already sets, recency ranks your last twenty commands, and the row
  cap is **per section** — a flat cap removed every workspace from the list once 130 modules outranked
  them. The four missing providers shipped in `apps/web/src/ui/paletteProviders.ts`, all pure and all
  injected, so none of them imports the viewer, the API client or the DOM:
  - **Authoring verbs** do not reimplement Move/Copy/Rotate — they find the toolbar button by its
    `title` and click it. `apps/web/src/viewer/toolbarLayout.ts` already keys the whole tool table on
    that exact string and already fails when an installed button is missing from it, so the palette
    inherits that gate: a retitled button cannot silently lose its palette row. A verb whose button is
    not installed is **omitted, not disabled** — before a model loads, every authoring row would
    otherwise look available and do nothing.
  - **Elements** is a GlobalId lookup plus an IFC-class list, and deliberately not a name search:
    there is no server-side element text search, and pulling every element down to filter in the
    browser would violate "never parse the model in the browser" to answer a question badly.
  - **Reports** are static rows from the server catalog, so they go through ranking and recency —
    the two reports you run each month rise on their own. Choosing one opens the Report Center
    *scrolled to and highlighting that row* (`focusReportRow`), rather than dropping the reader at
    the top of a 56-row modal to re-find what they just named.
  - **Ask** is the fallback, passed as `fallback` rather than mixed into the results, so it is
    appended *after* the per-section cap. A fallback the cap can delete is not a fallback — it would
    vanish exactly when a query matched twelve things badly, which is when it is most useful.

  **And a defect found while reading, not while testing:** `refresh()` did `items = items.concat(extra)`,
  so async hits were appended to an already-grouped list. A record — group *Records*, which sorts
  second — landed *below* Modules and Go to under a **second** `RECORDS` heading. The grouping was a
  property of the first paint only, and the section the async provider exists to fill was the one it
  could never reach; adding Elements and Reports would have made it three duplicate headings. Fixed by
  `mergeResults`, which re-sorts on group rank alone — `Array#sort` is stable, so each side keeps its
  own ranking inside its section, and re-scoring would have thrown away the server's relevance order.
- **R24-DENSITY ②** *(M)* — three steps (Field 56 px / Default 36 px / Compact 28 px) applied to
  **registers**, not just the dashboards `prefs.ts` covers today. Tabular figures wherever a number appears.
  *The register half is `portal/register/register.ts` as of v0.3.850 — inside Lane B, where this item
  is. It was inside Lane A's `portal.ts` until then, which is why `R24-MONO-DATA` skipped its hunk.*

### Sprint 4 — field, and the long tail

- **R24-FIELD-MODE** *(L)* — capture-first home, 56 px targets, 7:1 outdoor contrast, permanently
  visible sync queue, dictation on notes. A mode, not a breakpoint.
- 🟡 **R24-CHARTS-GRAMMAR** — **no-data rule SHIPPED v0.3.783**, the rest open. Only `histogram`
  handled empty input; the other twelve drew their axes, gridlines and legend with nothing in them —
  no `NaN`, nothing broken, and therefore indistinguishable from a chart whose data failed to load.
  All nine framed charts now share `noData()`, and `CHART_KINDS` + `charts.test.ts` fail the build if
  a new chart skips it.
  **Tick / legend / currency SHIPPED v0.3.948**, and none of the three was cosmetic once measured:
  - **Ticks.** Three charts hand-rolled the same gridline loop and the copies had already diverged —
    `lineChart` labelled `max − (k/4)(max − min)`, `groupedBar` and `waterfall` labelled
    `max − (k/4)·max`, a different axis whenever the minimum is not zero. And **`stackedBar` drew no
    gridlines at all**, so a cash-flow chart beside a budget chart was read against different
    furniture. One `yGrid`, and a source scan that fails on a local gridline loop.
  - **Legend.** Four hand-rolled copies of the same magic coordinates → one `legendRow`. The donut
    keeps the one legitimate position difference (under the ring, which has no plot to sit above) and
    still goes through the helper, so swatch, size and spacing cannot drift.
  - **Currency.** The real number was **22 declarations in six behaviours**, not the 18 a first grep
    found — the gate enumerated the population and my grep had not. **Ten wrote
    `` `$${Math.round(n).toLocaleString()}` ``, which renders a loss as `$-1,000`** with the currency
    mark on the wrong side of the minus; three had already fixed it locally, so the panels disagreed
    with themselves. `inspectorTabs.ts` used `Intl` currency *and* mapped a non-finite value to
    **`$0`** — an absent number rendering as a plausible zero, the failure the vitals strip exists to
    prevent. `proforma/format.ts` **exported** a competing one. All 22 now import `usd` from
    `apps/web/src/ui/charts.ts`; `chartsGrammar` bans re-declaring it.
    **And one of the 22 was not money at all**: the stormwater card's `usd` emitted no `$` because it
    formats cubic feet. Converting it would have put a currency mark on a detention volume — so `qty`
    exists, and the rule bans *declaring* a formatter rather than banning the name.
  - `unit: "money" | "percent" | "count"` now says what a chart's numbers **are** rather than making
    every caller remember a formatter; an explicit `fmt` still wins.

  **Still open:** the series-colour split below.
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
- **R24-TERMS** *(S)* · **R24-MONO-DATA** *(S)* · **R24-DENSITY ②** *(M)* — the remaining long tail.

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

- **R38-ARRAY-LIVE ③** *(M, prerequisite in Lane C/D)* — "arrays whose count/spacing stay editable
  after placement". Premise-checked: `groups.array_element(guid, nx, ny, dx, dy, dz)` produces
  **independent GUID-stable copies and stores nothing** — no group, no pset, no definition. There is
  therefore nothing to re-edit; changing a count today means deleting copies by hand. **Prerequisite:
  persist the array definition** (an IfcGroup or pset carrying nx/ny/dx/dy/dz plus its member GUIDs)
  and a `set_array_params` recipe that adds/removes members to match. Viewer half is then small.
- **R38-SOLVER-LOCKS ③** *(M — **DECIDED 2026-08-07: both, within-element first**)* — the R23
  dimensional locks as UI.

  **The user's call:** ship *within*-element locks (hold depth, drive width, keep area) against the
  existing solver now, and treat *across*-elements (align these walls, hold this offset) as a separate
  later item once multi-element parameter edits exist. That gets a usable feature out without
  committing to the larger build up front.

  **Premise-checked 2026-08-07, and the entry's framing was wrong in a way that makes this cheaper
  than it reads.** The question was posed as though the solver constrained the answer. It does not:

  - `services/data/src/aec_data/dim_constraints.py` exposes `solve(variables, constraints)` over a
    **flat dict of named scalars**. It has no concept of an element, so within-element and
    across-element are the same call with different variable names. Its own docstring's example —
    *"keep a wall 3000 from a grid"* — is an **across**-element relationship, so the general case is
    what shipped.
  - **The route already exists**: `POST /projects/{pid}/constraints/solve` in
    `services/api/src/aec_api/routers/analysis.py`. It has **no client caller**, so the whole feature
    is server-only today — the same shape the reachability gate exists to catch, and it is not in
    `KNOWN_UNCALLED`, so it slipped past on the last-static-segment rule.

  **So the solving is done; the work is UI plus a write-back.** The route says so itself: *"pure
  computation over caller-supplied values — it neither reads nor writes the model."* A UI must gather
  variables from the selection, call solve, and apply the result back through an edit recipe.

  **The instance-level write path DOES exist** — `services/data/src/aec_data/edit.py`'s `RECIPES`
  table has **14 entries keyed by `p["guid"]`**, a single element rather than a type. The relevant
  ones: `set_extrusion_depth(guid, depth)`, `set_wall_thickness(guid, thickness)`,
  `set_wall_slope(guid, start_height, end_height)`, `move_element(guid, dx, dy, dz)` and
  `set_element_pset(guid, pset, prop, value, dtype)`.

  *This entry claimed the opposite for one revision, and the way it went wrong is the reusable part.*
  The functions that ARE the wrong granularity are easy to find by name — `edit_type_params` (type),
  `set_pset_on_class` (class), `set_storey_elevation` (storey), `instance_props` (read + reset only) —
  and a grep for guessed setter names finds exactly those and stops. The guid-keyed writes live in a
  **dispatch table**, not under names anyone would guess. **If a claim is load-bearing, enumerate the
  whole table rather than the functions you can name.**

  **So the remaining work is a MAPPING, not a capability.** `solve()` returns named scalars, and
  something must decide that `thickness` on a wall writes through `set_wall_thickness(guid, …)` while
  `depth` on a column writes through `set_extrusion_depth(guid, …)`. That mapping is the substance of
  Apply; it is Lane E/C work and needs no new recipe.

  **Where a variable has no recipe, refuse that one BY NAME and apply the rest.** A partial apply that
  says which locks it could not write is honest; one that silently drops them is the
  `suggestion_clears_horizon` failure in a new place — a result that looks complete and is not.

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
  - ◧ **R38-SYNC-VIEW ③** *(M, Lane E — **checked 2026-08-06: MOSTLY BUILT**, one of the three
    named syncs is missing)* — `apps/web/src/viewer/planPane.ts` opens with "R38-SYNC-VIEW +
    R38-SYNC-SELECT" and `apps/web/src/viewer/app.ts` mounts it beside the model. **Storey sync**
    ships (`planParams(storey)`, and the pane refetches only when the *cut* changes, so a selection
    change costs no round-trip). **Pan and zoom** ship (`overflow:auto` body; a client-side
    `zoomPct` that deliberately does *not* refetch, because zoom is presentation and a refetching
    zoom would cost a bake per click). 14 tests. **The residue is live CURSOR sync, and it is BLOCKED** — checked
    2026-08-06 and it is not client work at all. `plan_drawing_svg` computes
    `T(x, y) = (ox + (x - mnx) * scale, oy + draw_h - (y - mny) * scale)` and then **discards every
    term of it**: the root carries only `width`, `height` and `viewBox="0 0 W H"`, and the only
    `data-` attributes anywhere are `data-guid` / `data-class` on polylines. **A client holding a
    world position cannot find its pixel.** Blocked on **R38-PLAN-TRANSFORM ③** below.

    *The tempting workaround is the one to refuse*: the transform could be back-solved from a
    polyline whose element geometry is known, which would work in a demo and drift silently the
    first time a cut differs from what the client thinks it is. That is the same shape as
    R24-TRACE-UI's rejected plan — **inventing in the client a fact the server threw away**.
    Original text: the second viewport with **cursor, pan/zoom and storey sync**. Buildable today;
    needs no identity.
  - ✅ **R38-PLAN-TRANSFORM — SHIPPED v0.3.928.** The plan SVG root now carries the six terms of its
    own transform: `data-plan-scale`, `-ox`, `-oy`, `-minx`, `-miny`, `-drawh`. `plan_drawing_svg`
    derived all six to place every polyline through a local `T(x, y)` and serialised none of them, so
    the drawing knew where everything was and the client could not ask. Full float precision, not
    formatted: a rounded scale puts a cursor visibly off at the far end of a large plan, which reads
    as a sync bug rather than as rounding.

    `services/api/test_plan_transform.py` asserts the **round trip, not the attributes** — it reads
    the terms off the root, rebuilds the inverse independently, takes a real pixel off a real
    polyline the server placed, and requires pixel → world → pixel agreement to 1e-3. Plus an extent
    check (catches a self-consistent but wrongly-scaled transform) and a two-storey comparison
    (catches a hardcoded one; `scale`, `minx`, `miny`, `drawh` all move). *Asserting the attribute
    exists would pass on a value that is wrong, stale, or from a different cut — the presence of an
    attribute says nothing about it being the transform the drawing actually used.*

    **This unblocks R38-SYNC-VIEW's cursor sync**, the last third of that item, and with it anything
    that needs to point at a place rather than at an element.
  - ✅ **R38-PLAN-IDENTITY — ALREADY DONE when this entry was written; confirmed 2026-08-10.**
    `cut_baked_guided` exists in `services/data/src/aec_data/drawings.py`, returns
    `(guid, ifc_class, polyline)`, and its own docstring opens with this item's id. The SVG has
    emitted `data-guid` per cut polyline since R38-SYNC-SELECT shipped v0.3.829. The entry stayed
    open anyway and kept being cited as a prerequisite blocking three other items. **Third stale
    premise found the same day** — after massingbill's "pure addition" claim and R41-UPLOAD-WARK's
    "no call site has been converted" — and all three overstated the work remaining, which is the
    direction that makes a roadmap quietly wrong rather than loudly wrong.
  - ✅ **R38-SYNC-SELECT ③** *(S, Lane E)* — **SHIPPED v0.3.829** — selection sync in both directions.
    The SVG emits `data-guid` per cut polyline (both rendering modes), the pane adds invisible fat
    hit-twins to ~1px linework, and one element lights as MANY loops. Shipping it also surfaced that
    the pane had been unreachable (toggle button never appended), its fetch had failed cross-origin
    since v0.3.826 (`credentials:"include"` without a credentials CORS grant), and the live route
    dropped the `storey` param entirely — three defects only a live drive could see.
- **R38-SHEET-MARKUP ③** *(M, Lane B)* — the vendored markup toolset (clouds, callouts, stamps,
  tool sets) opened on the room's OWN generated sheets, markups tied to GUIDs through the existing
  pin-to-drawing spine.
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
- ◧ **R40-EOT ②** *(M–L, Lane C — `eot.py` shipped; the SOURCED path shipped 2026-08-07)* — extension-of-time entitlement, with its method stated. Every input
  exists (`schedule_cpm.compute` gives ES/EF/LS/LF and free float, with total float derivable as
  LS−ES; `schedule_baselines` gives named baselines and per-activity variance; `notice_clock`
  already types weather/constructive-change/suspension delay events). What is missing is the step
  from baseline + as-built + events to a defensible entitlement: EOT days, excusable /
  non-excusable / compensable, per-event time impact. **The refusal IS the feature:** forensic delay
  **Premise-checked: every refusal the entry asks for is already in `eot.py`** — the four methods as a
  closed set, `method_required`, concurrency named rather than apportioned, absorbed float reported as
  absorbed. **What had no provenance were its inputs.** `POST /schedule/eot` took `baseline_finish`,
  `actual_finish` and the whole event list from the request body, while `schedule_baselines` (named
  captured baselines + per-activity variance) and `notice_clock` (typed weather / constructive-change
  / suspension events, each carrying its source record) sat wired to nothing. On the number the entry
  itself says ends up in arbitration, that is the wrong place to leave provenance: two people can
  produce different EOTs from one project by typing different dates, and every careful refusal sits
  downstream of an input nobody can audit.
  `services/api/src/aec_api/eot_sourced.py` + `POST /projects/{pid}/schedule/eot/sourced` joins them.
  **The design follows from what the two sources actually give**, which is not the same thing:
  `variance()` gives **quantum** (`finish_var` per activity vs a *named* baseline); `notice_clock`
  gives **cause** and carries **no `days` field at all** — detection establishes that an event
  occurred, never what it cost. So the gap is reported rather than filled, twice:
  *an event with no stated duration is `needs_duration`*, listed and excluded from the figure rather
  than handed the slip it sits near; and **slip with no matching cause is `unattributed`, never
  `non_excusable`** — defaulting unexplained slip to contractor risk hands one party an entitlement
  finding nobody demonstrated. Matching is by explicit `activity_id` only: proximity is not causation,
  and causation is the contested half of every claim. All three mutation-checked (5 / 2 / 6 named
  FAILs); no baseline returns `baseline_required` **with the available baselines** rather than falling
  back to a typed date.
  *Two of my own assumptions were wrong and caught by reading the engine rather than trusting the
  name:* `compute_variance` rows key on `ref` (there is no `id`), and its `summary` carries slip counts
  and `max_slip_days` but **no project finish dates** — so `baseline_finish`/`actual_finish` are passed
  through from the caller and NOT derived here, because inventing a completion date would fabricate
  the very input this exists to make auditable.

  analysis has a published method taxonomy (AACE 29R-03, SCL Protocol 2nd ed) and **the same facts
  give different answers under different methods** — as-planned-vs-as-built, windows and time-impact
  are not interchangeable, and concurrent-delay apportionment is openly contested. The engine states
  its method and **refuses to emit an EOT number without one**, reporting concurrency *as*
  concurrency rather than silently apportioning it. An unmethodded EOT figure is the
  confident-wrong shape at its most expensive: this number ends up in arbitration.
- ◧ **R22-PIPELINE** — no rewrite needed; a **spec reference now exists** from the same drop (portfolio
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

- **R41-MODEL-ALIGN** *(M — Lane E)* — **align a federated model that arrived with wrong, missing or
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
- **R41-CLASH-TRIAGE** *(M — Lane C)* — **a reduction stage between detection and workflow.** A
  competitor's headline is not detection quality but **22,843 raw clashes reduced to 103 groups**:
  group by geometric and semantic similarity, drop duplicates, filter grazing false positives, then
  rank survivors by construction consequence. We have detection including soft and sequence clash, and
  BCF round-trip. **Detection without reduction produces a number nobody reads**, and the same shape
  applies to every engine that emits many findings — code compliance, scope gap, QTO variance.

  **All four asks were already built**, which is the finding. `clash_intel.analyze` groups by greedy
  set-cover on the dominant element (a duct crossing 12 joists is ONE issue), scores by discipline
  pair x penetration volume x group size, and `aec_data.clash.detect` takes `min_volume=1e-3` plus a
  `tolerance` that shrinks the boxes so merely-touching elements never register — that is grouping,
  de-duplication, grazing-filter and consequence ranking. It also carries a stable `group_hash` across
  re-runs, which this entry never asked for.
  **What was NOT verified is the only number the entry is about.** `test_clash_intel.py` asserted
  `reduction == 2.0` on a **four-clash** fixture, and four rows cannot demonstrate an order of
  magnitude — greedy set-cover is precisely the algorithm whose ratio is a function of topology, fine
  on a toy and ~1:1 on a federation where every pair is distinct. `services/api/test_clash_reduction_scale.py`
  measures it on realistic shapes: **5,760 raw → 320 groups (18:1)**, sparse 2:1 versus dense 30:1, so
  the ratio provably tracks density rather than sitting at a constant. It also closes the two ways a
  grouper can cheat — reducing by *losing* clashes (membership is summed, not just groups counted) and
  merging problems a coordinator would have to split again (60 unrelated clashes must stay 60 issues).
  Mutation-checked by keying the group on both elements: 4 named FAILs, ratio collapses to 1.0:1.
  *The first mutation attempt was applied and changed nothing* — it hit `_group_hash`, which labels
  groups rather than forming them, and reported a clean pass. **An applied mutation that alters no
  behaviour reads exactly like a gate that cannot fail**; the measured numbers coming back identical
  is what caught it.
- ◧ **R41-COMMERCIAL-DRIFT** *(M → S/M — Lane C; the document walker SHIPPED 2026-08-07, the PO hop remains)* — **diff the money across documents, not across our own
  estimates.** R25-ESTIMATE-DIFF compares two of *our* numbers. The gap is the chain **bid → executed
  contract → purchase order → invoice**, each hop diffed against the one before it with findings ranked
  by dollar impact: scope added between bid and contract, invoice lines drifting from a locked buyout
  price. This is where subcontractors actually lose money, and it sits on top of cost and document
  control we already have.

  **Walker SHIPPED — `commercial_drift.py`, `GET /projects/{pid}/commercial-drift`.** Premise-checked
  first and the item was smaller than written: three of the four hops already existed **and were
  already referentially wired** (`subcontract.awarded_from → bid_submission`,
  `sub_invoice.subcontract → subcontract`), so bid → contract → invoiced needed no schema change.
  **Why the existing engines could not do it.** `margin.py` and `cost_spine.py` both measure per cost
  code, and **a roll-up adds before it compares** — two subcontracts can net to the right code total
  while one award drifted +15% and another −15%. There is a test for exactly that: both are reported
  here and the per-code view sees nothing.
  **Two agreed numbers are deliberately NOT called drift**, which is the whole design:
  *a change order is money somebody signed for* — `subcontract.change_orders` sums `cor.amount`, so it
  belongs to the contract→invoiced hop as part of the agreed sum and never to bid→contract; counting
  it as drift would flag every project that has a CO, which is every project. And *an unaccepted
  alternate was never bought* — `bid_submission` carries `amount`, `base_bid` and an `alternates`
  table with an `accepted` flag, so the comparable award figure is base bid + **accepted** alternates,
  with the row stating its basis. Comparing `amount` blindly buys the rejected ones; comparing
  `base_bid` alone makes the accepted ones look like scope from nowhere.
  A hop missing a figure on either side is `incomparable` and counted separately — not a zero-dollar
  difference. All three refusals mutation-checked (4 / 6 / 2 named FAILs).
  **Remaining: the PO hop.** `purchase_order` still does not exist and `procurement_package` carries
  `est_cost`/`award_amount` with **zero reference fields** — an island nothing can walk into or out
  of. That register plus one more hop closes the entry.

  **PREMISE-CHECKED 2026-08-06 (no build): three of the four hops exist AND are already linked, and
  the cost-code axis of this diff is done. The item is much smaller than written.**
  Registers present: `bid_submission` (`amount`, `unit_prices`), `bid_package`, `prime_contract`
  (`value`, `sov_value`), `subcontract` (`value`), `owner_invoice` (`amount`, `retainage_total`,
  `architect_certified_amount`), `sub_invoice` (`amount`). **The chain is already referentially
  wired**: `subcontract.awarded_from → bid_submission` and `sub_invoice.subcontract → subcontract`,
  so bid → contract → invoice can be walked today without a schema change.
  **And the diff partly exists, along a different axis than the entry assumes.** `margin.py`
  (MARGIN-CBS) already totals budget / committed / actual / billed per cost code, and `cost_spine.py`
  already asks the harder question — whether one cost code carries the *same scope* from estimate
  through budget, commitment and invoice, because a code appearing at one stage and not the next
  produces a row that looks fine. That is document drift measured **per cost code**.
  **What is actually missing is two things, not four:**
  1. **the PO hop has no register.** `purchase_order` does not exist; `procurement_package` carries
     `est_cost` and `award_amount` but has **zero reference fields** — it is an island, so nothing can
     walk into or out of it. This is the one genuine schema gap;
  2. **nothing diffs amounts document-to-document along the references that already exist** — bid
     `amount` vs the `subcontract.value` it was awarded into, contract value vs the sum of its
     `sub_invoice.amount`. The per-code roll-up cannot see this: two documents can net to the right
     code total while the individual award drifted.
  Sized on evidence rather than the entry's wording, this is **S/M** — one register plus one walker
  over existing references — not the M implied by "build a four-hop diff".

  **PREMISE-CHECKED 2026-08-06 (no build): three of the four hops exist AND are already linked, and
  the cost-code axis of this diff is done. The item is much smaller than written.**
  Registers present: `bid_submission` (`amount`, `unit_prices`), `bid_package`, `prime_contract`
  (`value`, `sov_value`), `subcontract` (`value`), `owner_invoice` (`amount`, `retainage_total`,
  `architect_certified_amount`), `sub_invoice` (`amount`). **The chain is already referentially
  wired**: `subcontract.awarded_from → bid_submission` and `sub_invoice.subcontract → subcontract`,
  so bid → contract → invoice can be walked today without a schema change.
  **And the diff partly exists, along a different axis than the entry assumes.** `margin.py`
  (MARGIN-CBS) already totals budget / committed / actual / billed per cost code, and `cost_spine.py`
  already asks the harder question — whether one cost code carries the *same scope* from estimate
  through budget, commitment and invoice, because a code appearing at one stage and not the next
  produces a row that looks fine. That is document drift measured **per cost code**.
  **What is actually missing is two things, not four:**
  1. **the PO hop has no register.** `purchase_order` does not exist; `procurement_package` carries
     `est_cost` and `award_amount` but has **zero reference fields** — it is an island, so nothing can
     walk into or out of it. This is the one genuine schema gap;
  2. **nothing diffs amounts document-to-document along the references that already exist** — bid
     `amount` vs the `subcontract.value` it was awarded into, contract value vs the sum of its
     `sub_invoice.amount`. The per-code roll-up cannot see this: two documents can net to the right
     code total while the individual award drifted.
  Sized on evidence rather than the entry's wording, this is **S/M** — one register plus one walker
  over existing references — not the M implied by "build a four-hop diff".

  **PREMISE-CHECKED 2026-08-06 (no build): three of the four hops exist AND are already linked, and
  the cost-code axis of this diff is done. The item is much smaller than written.**
  Registers present: `bid_submission` (`amount`, `unit_prices`), `bid_package`, `prime_contract`
  (`value`, `sov_value`), `subcontract` (`value`), `owner_invoice` (`amount`, `retainage_total`,
  `architect_certified_amount`), `sub_invoice` (`amount`). **The chain is already referentially
  wired**: `subcontract.awarded_from → bid_submission` and `sub_invoice.subcontract → subcontract`,
  so bid → contract → invoice can be walked today without a schema change.
  **And the diff partly exists, along a different axis than the entry assumes.** `margin.py`
  (MARGIN-CBS) already totals budget / committed / actual / billed per cost code, and `cost_spine.py`
  already asks the harder question — whether one cost code carries the *same scope* from estimate
  through budget, commitment and invoice, because a code appearing at one stage and not the next
  produces a row that looks fine. That is document drift measured **per cost code**.
  **What is actually missing is two things, not four:**
  1. **the PO hop has no register.** `purchase_order` does not exist; `procurement_package` carries
     `est_cost` and `award_amount` but has **zero reference fields** — it is an island, so nothing can
     walk into or out of it. This is the one genuine schema gap;
  2. **nothing diffs amounts document-to-document along the references that already exist** — bid
     `amount` vs the `subcontract.value` it was awarded into, contract value vs the sum of its
     `sub_invoice.amount`. The per-code roll-up cannot see this: two documents can net to the right
     code total while the individual award drifted.
  Sized on evidence rather than the entry's wording, this is **S/M** — one register plus one walker
  over existing references — not the M implied by "build a four-hop diff".

  **PREMISE-CHECKED 2026-08-06 (no build): three of the four hops exist AND are already linked, and
  the cost-code axis of this diff is done. The item is much smaller than written.**
  Registers present: `bid_submission` (`amount`, `unit_prices`), `bid_package`, `prime_contract`
  (`value`, `sov_value`), `subcontract` (`value`), `owner_invoice` (`amount`, `retainage_total`,
  `architect_certified_amount`), `sub_invoice` (`amount`). **The chain is already referentially
  wired**: `subcontract.awarded_from → bid_submission` and `sub_invoice.subcontract → subcontract`,
  so bid → contract → invoice can be walked today without a schema change.
  **And the diff partly exists, along a different axis than the entry assumes.** `margin.py`
  (MARGIN-CBS) already totals budget / committed / actual / billed per cost code, and `cost_spine.py`
  already asks the harder question — whether one cost code carries the *same scope* from estimate
  through budget, commitment and invoice, because a code appearing at one stage and not the next
  produces a row that looks fine. That is document drift measured **per cost code**.
  **What is actually missing is two things, not four:**
  1. **the PO hop has no register.** `purchase_order` does not exist; `procurement_package` carries
     `est_cost` and `award_amount` but has **zero reference fields** — it is an island, so nothing can
     walk into or out of it. This is the one genuine schema gap;
  2. **nothing diffs amounts document-to-document along the references that already exist** — bid
     `amount` vs the `subcontract.value` it was awarded into, contract value vs the sum of its
     `sub_invoice.amount`. The per-code roll-up cannot see this: two documents can net to the right
     code total while the individual award drifted.
  Sized on evidence rather than the entry's wording, this is **S/M** — one register plus one walker
  over existing references — not the M implied by "build a four-hop diff".

  **PREMISE-CHECKED 2026-08-06 (no build): three of the four hops exist AND are already linked, and
  the cost-code axis of this diff is done. The item is much smaller than written.**
  Registers present: `bid_submission` (`amount`, `unit_prices`), `bid_package`, `prime_contract`
  (`value`, `sov_value`), `subcontract` (`value`), `owner_invoice` (`amount`, `retainage_total`,
  `architect_certified_amount`), `sub_invoice` (`amount`). **The chain is already referentially
  wired**: `subcontract.awarded_from → bid_submission` and `sub_invoice.subcontract → subcontract`,
  so bid → contract → invoice can be walked today without a schema change.
  **And the diff partly exists, along a different axis than the entry assumes.** `margin.py`
  (MARGIN-CBS) already totals budget / committed / actual / billed per cost code, and `cost_spine.py`
  already asks the harder question — whether one cost code carries the *same scope* from estimate
  through budget, commitment and invoice, because a code appearing at one stage and not the next
  produces a row that looks fine. That is document drift measured **per cost code**.
  **What is actually missing is two things, not four:**
  1. **the PO hop has no register.** `purchase_order` does not exist; `procurement_package` carries
     `est_cost` and `award_amount` but has **zero reference fields** — it is an island, so nothing can
     walk into or out of it. This is the one genuine schema gap;
  2. **nothing diffs amounts document-to-document along the references that already exist** — bid
     `amount` vs the `subcontract.value` it was awarded into, contract value vs the sum of its
     `sub_invoice.amount`. The per-code roll-up cannot see this: two documents can net to the right
     code total while the individual award drifted.
  Sized on evidence rather than the entry's wording, this is **S/M** — one register plus one walker
  over existing references — not the M implied by "build a four-hop diff".
- ◧ **R41-UPLOAD-WARK** *(M — Lane C; **the byte-bound half SHIPPED v0.3.876** — `services/api/src/aec_api/bodycap.py` measures the request body instead of trusting `Content-Length`, and `storage.put_stream` gives callers a way to write without holding the object. **The resumable handshake below is untouched, and no upload route has been converted to the streaming write yet** — that is what is left)* — **content-addressed resumable upload in front of object
  storage.** Technique from an MIT-licensed file server (verified from its LICENSE); reimplement the
  handshake rather than adopt the server. Three parts: chunk size chosen so the **chunk *count* stays
  bounded**, keeping the handshake manifest roughly constant regardless of file size — a fixed part
  size gives a manifest that grows linearly with a large IFC; an upload identity derived from
  `hash(salt + filesize + chunk hashes)` so **resumption is not a special code path** (re-handshake,
  receive the still-needed list) and deduplication falls out for free; and per-chunk hashes catching
  corruption **before** IFC-to-Fragments conversion runs. **IFC revisions are large and mostly
  identical between uploads**, so an unchanged re-upload currently costs a full transfer.

  **PREMISE-CHECKED 2026-08-06; the hazard it surfaced is now FIXED and half the mechanism landed.**
  The premise holds — nothing is chunked, resumable or content-addressed — but two things changed the
  shape of it.
  *The hazard, and it was worse than the version I first wrote.* I flagged that a chunked upload would
  defeat `AEC_MAX_UPLOAD_MB` because the guard reads `content-length` on a single request and N small
  chunks each pass. The real mechanism was simpler and already live: **with no `content-length` header
  at all the condition short-circuited and the body was never measured** — so the cap was defeatable
  without chunking anything. Fixed in v0.3.876 by `bodycap.MaxBodySizeMiddleware`, which counts bytes
  on the ASGI `receive` channel. Recorded because the correction matters: I reasoned to the right
  conclusion from the wrong mechanism, and a guard that *fails open on a missing header* is a
  different class of bug from one that is out-scoped by chunking.
  *The other half stands and has moved.* `storage.put(key, data: bytes)` was whole-bytes on both
  backends; `put_stream` now exists (local `.part`+rename, S3 multipart) — but **no call site is
  converted**, verified in the tree. So the remaining work is the conversion plus the content-addressed
  handshake itself, and whatever lands must still cap the *assembled* size at the handshake rather
  than trusting a declared filesize. Their
  sparse-file capability check is this codebase's own house style expressed in a network protocol: on a
  mismatch it **refuses loudly**, naming file, chunk index and offset, rather than silently writing a
  corrupt file.

  **CHECKED 2026-08-06 — the premise HOLDS, and the tree is one step worse than the entry says.**
  Nothing in `services/` mentions resumable, chunked, multipart or part-number uploads. Every upload
  is a single FastAPI `UploadFile` multipart POST, and `services/api/src/aec_api/storage.py`'s
  interface is `put(key, data: bytes)` — **there is no streaming put at all**. Six call sites do
  `await file.read()`, so **the whole file is materialised in memory** before it reaches storage.

  So the entry's framing — "an unchanged re-upload currently costs a full transfer" — is a *bandwidth*
  argument, and it is right. But the same fact is also a **memory** argument for a 50 MB IFC, and that
  half is not in the entry. Note the asymmetry that makes this cheap to miss: `storage.py` already has
  `get_range(key, start, end)`, so ranged **reads** are supported and only **writes** are all-or-nothing
  — the capability looks half-present when the half that matters is absent.

  Nothing is content-addressed either: storage keys are caller-supplied paths sanitised by `safe_seg`
  / `validate_key`, and there is no hashing in the storage layer, so deduplication has nothing to key
  on. The entry's `hash(salt + filesize + chunk hashes)` identity would be the first content address
  in the system rather than a change to an existing one.

### Gate and process items

- ✅ **R41-BUNDLER-SPLIT** *(S — Lane J; DONE v0.3.941)* — **the suite never exercises the bundler that ships.** The app
  is *built* with **Vite 8 / rolldown** (pinned in `apps/web/package.json`, installed nested at
  `apps/web/node_modules/vite`) and *tested* under **Vite 6 / rollup**, from the copy hoisted to the
  repo root.

  **The stated cause was wrong, and it made this look like a dependency decision it is not.** This
  read "because `vitest@4.1.10` depends on vite ^6". It does not: vitest declares
  `^6.0.0 || ^7.0.0 || ^8.0.0` in **both** `dependencies` and `peerDependencies`, and 4.1.10 is the
  current release. Checked against the lockfile, **no consumer requires ^6 exclusively** —
  `@vitest/mocker` is `^6 || ^7 || ^8` and `vite-plugin-pwa` is `^3 … ^8`. The root copy is 6.4.3
  purely because that resolution satisfies every range and nothing has forced npm to move it.

  So the remedy is a **lockfile dedupe**, not a version bump and not a new dependency.

  **CLOSED v0.3.941 — and the dedupe alone was not enough, which is worth recording.** An
  `overrides` entry was the obvious fix and npm *registered* it (`npm ls` printed `vite@8.1.5
  overridden`) while leaving the hoisted copy at 6.4.3 and reporting the tree `invalid`. Neither
  `npm install` nor `npm install --package-lock-only` re-resolved it, and deleting
  `node_modules/vite` did not either — the lockfile still pinned 6.4.3 and `npm install` honours the
  lock. **A registered override with an unchanged lock is the shape to watch for**: npm tells you it
  applied and the tree says otherwise, so trusting the config over `npm ls` would have left the split
  in place while reporting it fixed.

  What worked was declaring `vite` as a root devDependency at the same exact pin `apps/web` uses.
  That is one added line, not a new package — the root then dedupes to a single `vite@8.1.5` and
  `apps/web/node_modules/vite` disappears entirely.

  **The suite now runs on the bundler that ships**: 1,576 tests pass under Vite 8 / rolldown, and
  faster (26.5 s vs 32.6 s). Typecheck, lint and the production build are unchanged, and the
  precache output is byte-identical at 902.20 KiB — so this bought the coverage without moving what
  ships. Consistent between the clone and a
  worktree, so test results are not *unstable* — but the test environment is not merely narrower than
  production, it is **a different implementation**, and it can agree with you about code the shipping
  bundler treats differently.

  Chunking, CommonJS interop and tree-shaking are exactly where rollup and rolldown diverge, and we
  assert about all three: `bundle-budget.mjs` asserts the vendor split, and the 19.7× shell found in
  BUILD-WORKTREE-CHUNKS was a rollup-vs-rolldown difference. Same family as
  `test-environment-more-permissive-than-browser`: happy-dom vouched for a drop the real browser
  refuses. **Ask not what the test environment cannot see, but where it is a different thing wearing
  the same name.**

  Not resolvable inside BUILD-WORKTREE-CHUNKS — that item is about *which* Vite resolves, this one is
  about the two of them being legitimately different tools. Options are to wait for a vitest that
  tracks vite 8, to run a smoke suite against the built rolldown output, or to accept it explicitly
  and write down why.

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

**Why this ring exists.** An external audit of the deployment surface found that several controls are
weaker than they read: a throttle that counts per process behind four workers, an upload cap that only
exists if requests happen to arrive through the bundled proxy. The shape is familiar — R35's theme of
"a lock the backend ignores" applied to the ops layer. **Already landed from the same audit** (do not
re-open): the converter build stage moved to the supported Node LTS with a pinned digest
(`services/api/Dockerfile`), a Content-Security-Policy with a no-inline-script gate
(`apps/web/nginx.conf` + `apps/web/src/deploy/nginx.test.ts`), the multi-worker sidecar-lock boot
refusal (`services/api/src/aec_api/main.py`), and full-history checkout for the secret-scan job.

- **BUILD-WORKTREE-CHUNKS** *(M — Lane J)* — **a `vite build` from a git worktree succeeds and emits
  the wrong bundle.** One commit, two checkouts: the `three-*.js` and `thatopen-*.js` chunks vanish and
  the eager shell goes from **334 KB to 6,581 KB — 19.7×** — at **exit 0**. `searchForWorkspaceRoot`
  returns the worktree root rather than the repo root, deps fall back to CommonJS interop, and the
  `advancedChunks` rules never match. **Resolution is NOT the cause** — `three` and
  `@thatopen/components` resolve to identical absolute paths in both checkouts.

  **Three things had to line up for it to stay silent**, which is the part worth keeping:
  `apps/web/scripts/bundle-budget.mjs` *computed and printed* the lazy-chunk count without asserting
  it; the only objection came from the PWA precache limit, an accident rather than a check anyone
  wrote; and `VitePWA` is excluded when `VITE_PAGES=1`, so on the public-facing path even the accident
  is absent. `apps/web/vite.config.ts` had already written the warning in its own comment — *"verify by
  grepping the OUTPUT, never by reading the config and believing it"* — and nobody was doing it.

  **Half closed in v0.3.874:** `apps/web/scripts/copy-wasm.mjs` resolves the package instead of guessing
  directory depth (the fix already existed one file away in `apps/web/vitest.config.ts`, and
  `copy-wasm.mjs` imported `createRequire` and left it unused), and `bundle-budget.mjs` now *asserts*
  the vendor chunks exist. What remains is workspace-root scoping in `apps/web/vite.config.ts`,
  deliberately not taken inside a tooling PR: shared config, blast radius across every lane, and the
  fix is scoping rather than resolution. **Interim policy, now in the gate's own failure message:**
  builds happen in the main clone or in CI; a worktree build is for typecheck and tests, never a
  shippable bundle.

  **Still open beside it:** `npm run budget` is absent from `.github/workflows/pages.yml` entirely, so
  the public build has neither guard. Being fixed as a follow-up.

- ◧ **R39-UPLOAD-CAP-APP ①** *(S, Lane C — **FRONT HALF SHIPPED v0.3.876; the conversion of the
  36+ `await file.read()` call sites onto `storage.put_stream` remains, and is the rest of
  R41-UPLOAD-WARK.** premise corrected 2026-08-06: an app-level cap DOES
  exist**, so the item is not "add one" but "make the existing one measure rather than trust")* —
  the entry said the cap lives only in nginx (`client_max_body_size`) and that a deployment exposing
  the API directly has **no cap at all**. That is wrong: `services/api/src/aec_api/main.py` defines
  `_MAX_UPLOAD_BYTES` from `AEC_MAX_UPLOAD_MB` (1 GB default) and the `security` middleware rejects
  oversized bodies with a 413.

  **The residue is exactly the sentence the entry already wrote as its prescription, and it is worth
  keeping for that reason:** *"count as chunks arrive and cut off at the limit, never
  buffer-then-measure"*. The present guard does neither — it is **header-derived**, and its own
  comment says so (*"cheap Content-Length check — avoids reading them into memory"*). A request that
  does not carry that header is not measured. So the work is to make the limit a property of the
  bytes received rather than of what the request declared about itself.

  *Deliberately not spelled out further here: the repo is public and this is a request-handling
  boundary. The precise reachability note went to the release holder for `docs/internal/`, per the
  non-negotiable that security detail stays out of published docs.*

  **How to size it, so the next reader neither panics nor dismisses it.** An unbounded body read is
  **DoS-shaped**, and the standing security-review policy explicitly excludes DoS and
  memory-exhaustion from vulnerability reporting. That does not make it a non-issue — it makes it
  **tracked engineering work rather than an incident**. No drop-everything fix; a real entry with a
  real fix.

  **It composes with `R41-UPLOAD-WARK`, and neither entry could see this alone.**
  `services/api/src/aec_api/storage.py` has **no streaming put**: the protocol is
  `put(key, data: bytes)`, and **36 call sites across 15 router modules** do `await file.read()`
  before handing the bytes over — counted 2026-08-06. So the same request is **both unmeasured and
  fully materialised**: this entry bounds it from the front, `R41-UPLOAD-WARK`'s chunked handshake
  bounds it from the back, and *"count as chunks arrive"* is the identical instruction from either
  end. **Two entries, one mechanism** — fix either in isolation and the other still holds the memory
  open.

- **R39-A11Y-JOURNEYS ②** *(M, Lane B)* — keyboard-only acceptance journeys for the seven rooms,
  encoded as tests rather than an audit doc: for each room, tab-reach the primary action, operate it,
  and land focus somewhere sane. The a11y sweeps so far checked *attributes*; nothing yet checks a
  *journey*, and a journey is what a keyboard user actually has.
- **R39-VIEWER-OBS ②** *(M, Lane E)* — the viewer has no timing record: "loads slowly" arrives as a
  feeling, not a number. Instrument the load journey (fetch → parse → first frame, keyed by model
  size) and POST the timings to the platform's own API — no third-party telemetry, nothing new to
  approve — so p50/p95 by model-size bucket is a queryable fact before any perf work is prioritised.
- 🟡 **R39-DECOMP-VIEWER ③** *(L, Lane E — **started 2026-08-06: the ratchet is pinned and the seams
  are measured; the extraction is NOT begun, and the reason is below**)* — `apps/web/src/viewer/app.ts`
  is the last of the three god-files still standing (client.ts was split by SCALE-SEAM, portal.ts is
  REL-4).

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

- ⭐ **UX-READINESS-EVERYWHERE** *(M; superseded by **R24-READINESS-HOME**, kept for its evidence)* — **the app already contains its own "simple stupid" front door
  and hides it.** The Master Builder panel is a live 8-step readiness synthesis: each step reads
  ready / partial / gap against real project data, names exactly what is missing ("needs: Jurisdiction
  so code editions + loads resolve"), and offers **→ Close this gap** straight to the tool that fixes
  it — plus an honest disclaimer that labels reflect what is *present*, not what is *correct*. That is
  precisely the "tell me what to do next" surface a builder/developer/architect/engineer wants on
  opening a project, and it is reachable from exactly ONE destination inside ONE workspace (Design).
  Promote the readiness strip to every workspace dashboard, scoped per persona.
  `Model Health` (8 references), `Model Analysis` (5) and `BIM KPIs` (5) are three
  destinations whose names do not tell a user which answers their question; all three now sit together
  under `Analyse & check`, which makes the overlap visible and worth resolving rather than hiding it.
- **UX-GANTT** *(M)* — weekly Gantt/calendar hybrid with inline % + crew coloring + a metric strip.
- **UX-DUP-DESTINATIONS** *(S — **checked 2026-08-06 and still genuinely OPEN**; recorded so the next
  reader does not re-check)* — all three destinations are still present and distinct in the tree:
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

- ◧ **R31-CITE-HIGHLIGHT** *(re-headed 2026-08-05 — **this heading contradicted its own body**, and
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

Open:

- ◧ **R35-DEAL-MEMORY** *(M — `deal_memory.py` shipped)* — the platform's own closed deals as a comp database: when underwriting
  a new deal, surface this portfolio's realised outcomes (exit cap achieved vs assumed, actual
  lease-up months, cost/SF by vintage) beside the assumption being entered. External research
  (2026-08) puts this "institutional knowledge" layer as the least-commoditised part of the
  AI-underwriting stack — and it is the one layer that cannot be bought, because it is made of the
  operator's own history. Builds on `benchmarking.py`'s cross-project aggregation and the
  provenance spine; no new dependency.

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
* Its dead-code list predates the reachability sweeps (R31/R32/Band 3) that deliberately WIRED
  several of the named symbols. Example class: `validate.py` and `docgraph.py` symbols were
  "unused" in mid-July and have callers now. The check per symbol is the usual one —
  `git grep` the name including string/registry references, then delete or wire, never assume.
* Its hotspot list (§3) is corroborated independently: `main.ts`, `portal.ts`, `client.ts` are the
  repo's own known god-files, and SCALE-SEAM already split `client.ts` by domain after this index
  was taken. Credit what shipped; keep the rest.

- ◧ **R37-TRIAGE** *(M — Lane C; do FIRST, before any deletion or split)* — **steps 1–3 triaged in
  v0.3.865–867 on measurements rather than recollection:** cycles ALREADY-CLOSED and gated on both
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

- ◧ **R36-VIEWER-SUBAPP** *(L — Lane E; SLICE 4 SHIPPED v0.3.918 — `apps/web/src/viewer/canvasMode.ts`)*
  — **the mode switch is in.** The canvas is now one surface at a time (Model ▸ Sheets) rather than 3D
  with a strip attached: the plan was `position:absolute; right:0; width:38%`, so 2D was a slice of the
  model rather than a peer of it. Visibility is DERIVED from the mode, so "both visible" and "neither
  visible" are unrepresentable rather than merely discouraged, and the old "◫ Plan beside model"
  toggle now routes through the switch so one thing owns the pane. A refusal carries a reason —
  Sheets before a project is open says so, because a tab that swallows the click reads as broken.

  Slices 1–3 were the print path this depended on, and the roadmap's own sequencing note was right
  that it had to come first: `axon` reaching the shipping dispatcher (it had been drawing a plan
  titled ISO VIEW), the `views=` grammar, and "place this view on a sheet". Without them the switch
  would have exposed 2D and 3D as non-peers immediately.

  **SPECS SHIPPED v0.3.920 — all three modes are real.** `apps/web/src/viewer/specPane.ts` renders the
  3-part MasterFormat manual as a canvas surface, and selecting an element reveals its section. It
  needed **no backend work**: `specmanual.py` has served `elements: [{guid, name, ifc_class}]` per
  section since it shipped, and the client's return type simply never declared the field — so the
  section↔element link looked like unbuilt work while sitting in every response. Exact mirror of the
  sheet-params defect: there the client SENT keys the route ignores, here it IGNORED keys the route
  sends. A contract believed rather than read, in both directions.

  The `elements` list is **capped at 50 per section** while `element_count` is the true total, so the
  pane distinguishes *"no spec section"* from *"not in the first 50, so I cannot tell"* — the second
  reported as the first would be a statement about the payload posing as one about the model.

  The v0.3.918 guard that forbade registering `specs` without a surface now guards the general rule,
  and a mutation showed it had been **too weak**: it matched the string `specPane` anywhere, which the
  mode's own `enter`/`leave` satisfy, so a mode wired to a pane that is never built would have passed.
  It now requires `new SpecPane(` AND the `appendChild` — "built but never appended" being this repo's
  most repeated defect.

  **Not verified live.** `createViewerApp` needs a WebGL context and a Fragments worker and the
  dev-preview geometry loader stalls, so the tab strip has not been seen in a browser. 11 unit tests
  cover the switch's behaviour and `tsc` covers the wiring; the DOM is unverified and said so.

  **Slice 5, measured v0.3.919 — the model↔sheet half ALREADY WORKED, by accident.** Picking in 3D and
  switching to Sheets does carry the GlobalId, because three unrelated mechanisms happen to line up:
  `onSelectionChanged` fires whether or not the pane is visible and stores `sel` before touching the
  DOM; `dock("full")` forces a refresh; `refresh` ends by re-applying `syncPlanHighlight`. Remove any
  one and the feature vanishes silently — the plan renders, nothing is lit, and it reads as "that
  element isn't on this level". `PlanPane` had **no instance-level tests at all**, so nothing would
  have noticed. `apps/web/src/viewer/planPaneSelection.test.ts` is now the thing that fails first.

  **Slice 6 scoped by measurement, 2026-08-09 — it is an INTEGRATION, not a build.** The markup and
  takeoff layer is already complete and wired: all five client methods (`drawingMarkup`,
  `addDrawingMarkup`, `saveDrawingMarkups`, `deleteDrawingMarkup`, `promoteDrawingMarkup`) have
  callers, the read side has four, and every one of them is in `apps/web/src/drawings/drawings.ts`.
  Nothing needs writing; it needs to be reachable from the Sheets canvas so a drawing is marked up
  where it is being looked at, rather than in a different room.

  **The one real design question, and the non-negotiables answer it.** Markups key on a sheet id — a
  persisted document record — and the viewer's Sheets mode renders `plan.svg?storey=…&scale=…`, a
  live cut with no record and no id. So a generated plan needs an identity to attach markups to.
  Keying on the storey NAME would look natural and is wrong: levels can be renamed here, and every
  markup on that level would orphan silently. Per the non-negotiable — *reference by IFC GlobalId,
  never transient ids* — the key is the **storey's GlobalId**. That is a rule the project already
  holds, not a new decision, and it is the reason this is specified rather than open.

  Cost that follows: `PlanPane` asks for a storey by name (`activeStorey()`), so slice 6 also has to
  carry the storey's GUID down to the cut request. The existing `${sheet.id}#pdf` convention shows
  the codebase already namespaces markup stores by suffix, so `plan:<storeyGuid>` fits the pattern
  that is there.

  Remaining: the **keynote → spec section** link (the spec surface now exists; keynotes do not yet
  carry their section code), and slice 6 as specified above.

- **R36-ROOM-BRIEFS** *(M — Lane B; one room per release)* — per-room, per-role landing priority:
  each room opens with the three answers its primary role needs (superintendent in Schedule: today's
  lookahead, blockers, yesterday's variance; developer in Deal: returns vs guardrails, open
  diligence, next decision gate). Write each brief as a short spec in the room's panel file header,
  then make the panel match it. The Work room already does this by construction; it is the template.
## 🧱 Decomposition & reliability carry-overs (interleave one per few releases)

- ◧ ⭐ **SCALE-SEAM ⑧ — `client.ts` is no longer a god-file, but the split is not finished.** *(◧ added 2026-08-06: the bullet's own text says ②–⑧ have shipped and `apps/web/src/api/proforma.ts` declares ⑧ — the SLICE is done and the SERIES is not, which is exactly what ◧ means)* ②–⑧ have
  shipped: `schedule.ts` (v0.3.800, 26 methods / 207 lines) · `model.ts` (v0.3.802, 29) · `modules.ts`
  (v0.3.803, 34) · `estimate.ts` (v0.3.804, 12) · `procurement.ts` (9) · `auth.ts` (20) · `proforma.ts` (⑧).
  **`client.ts` went 4,956 → 3,796 lines** (`wc -l`; ⑦ left it at 3,871). ⑨ is the next route-group by size; pick it by
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

- **SEC-PLUGIN-LOADER** *(L)* — **renamed from SEC-PLUGIN-SANDBOX on 2026-08-05: it was a different
  item wearing the same ID.** The other SEC-PLUGIN-SANDBOX (Band 1) is `sandbox.py`'s
  `execute_ifc_code` AST allowlist, shipped v0.3.864. This one is `plugin_registry.py` importing
  third-party Python into the API process. Different file, different lane, different status — and
  while they shared an ID, "SEC-PLUGIN-SANDBOX is partially shipped" was simultaneously true and
  false. An ID collision is worse than a stale line: a stale line is merely out of date, whereas this
  made a *correct* status report misleading. — **plugin Python executes inside the API process.**
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


- **REL-4 leaves** *(M)* — `portal.ts` next leaf + `viewer/app.ts` leaves.
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

* **R28-BUNDLE ② — make `.mmproj` legible.** It already carries the data; nothing says so. Name it in
  the UI, show what a bundle contains before import, and state on export what was included and what
  was **left out** (`_SKIP_TABLES` drops users, audit log, settings and connections — correct, and
  currently silent). The same unknown ≠ none rule the engines follow.
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

* 🟡 **A29-GUIDE-UNDERLAY ③** *(in flight, PR #199)* — *trace over a plan.* A 2D reference image
  pinned to a level and scaled, for redrawing an existing building from a scan or a PDF. Small,
  self-contained, and the one place their `Guide` node maps onto something we do not have.
  `apps/web/src/viewer/guideUnderlay.ts` holds the calibration, the refusals and the plane;
  `app.ts` gets six lines.

  **Scale is the whole feature, and the entry undersold it.** An underlay that is merely *placed* is
  decoration — the reason to build it is that walls traced over it come out at real dimensions. So
  every path reduces to metres-per-pixel and every derivation **refuses rather than guesses**: a
  silently-wrong scale is the one failure that poisons everything traced afterwards, and unlike a
  mis-placed image it looks completely fine on screen. The coincident two-point pick is the one that
  matters, because it is what a real user produces by double-clicking, and dividing by a zero pixel
  distance yields `Infinity`.

  **This item is what found the `modelPlanBounds` defect** (PR #198). Premise-checking "can I add a
  plane to the scene?" led to "what already reads the scene?", and the answer was that a
  2000 × 2000 shadow-catcher had been defeating the mis-click guard. *Before adding an object to a
  shared structure, check what already reads that structure* — a new object is the moment you finally
  have a reason to enumerate the readers.

  **A mutation pass caught a decorative test of my own.** "the guide is not a raycast target" passed
  whether or not the guard existed: calling `mesh.raycast()` by hand on a mesh whose world matrix was
  never updated intersects nothing either way, so it asserted an empty array that was empty for the
  wrong reason. It now runs a **control** first — an identical unguarded plane must be hit by the same
  ray — so empty means "the guard worked" rather than "the ray missed". Same shape as the picking
  benchmark that reported a confident p50 with `hits: 0`.

**Explicitly NOT in this ring:** adopting React/R3F, adopting a bespoke node schema beside IFC,
vendoring `engine_clay` (dormant), and anything from IFChili (AGPL). If client-side booleans become
necessary later, that is a separate decision with **Manifold** as the candidate and a dependency
conversation attached.

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

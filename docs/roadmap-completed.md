# Roadmap — completed / shipped archive

*Working conventions live in [roadmap-directions.md](roadmap-directions.md); open work lives in
[roadmap.md](roadmap.md). This file is what shipped, and why.*

Historical reference: everything **already shipped**. The single **open** backlog lives in
[roadmap.md](roadmap.md) ("What's left"). Nothing here is a to-do — it's the record of what was built,
wave by wave and track by track, so the working roadmap can stay lean. Sections are in rough
chronological / thematic order; ✅ markers and version tags are the source of truth for *when*.

---

## ✅ LOD 2025 — the achieved-LOD number stops measuring the wrong thing *(2026-08-08, v0.3.901–903)*

All three items booked from the BIMForum LOD Specification 2025 (supplied by the user) are in. The
theme is one defect in three places: **the platform reported LOD numbers it had no evidence for.**

- **LOD-ASPECTS** *(v0.3.901)* — `achieved_lod` mapped a COUNT of LOIN facets onto a band
  (`_FACETS_TO_LOD[5] = "LOD 400"`) and nothing on that path looked at a shape. Measured: a generic
  `IfcWall` box carrying a classification, a Pset and a Qto scored **LOD 350**; strip the property
  and quantity sets, changing not one vertex, and the same box scored **LOD 200**. Two bands on
  tagging alone, on a figure that goes into contracts and BIM execution plans.

  It could not be fixed in `lod.py` alone: the properties index carried **no geometry at all**, so
  the four geometric aspects were undecidable rather than unused. Shape *facts* now ride in the index
  (`rep_types`, `rep_ids`, `has_openings`, `has_material`, `placed`) — facts *about* geometry, small
  enough for a metadata index, so the geometry/metadata separation holds.

  **The first draft was wrong and its own test caught it.** Folding "what the evidence supports" and
  "what it rules out" into one value and taking the minimum made *every element in every model*
  LOD 200, because Location and Dimensionality accuracy are unreadable. `supported` and `cap` are now
  separate: an aspect nobody can read widens the CEILING and never lowers the band. That separation
  is the product value — `ceiling_distribution` says the gap is **unread model, not missing model**.

  Honest ceiling: a model read tops out at **LOD 350**, because nothing in the index distinguishes a
  coordination-ready solid from a fabrication-ready one. The old code claimed 400 on no evidence.

- **LOD-500-LOA** *(v0.3.902)* — the definition requires the level of accuracy to be *noted on the
  element*; we recorded that a verification happened and never how good it was. Three grades now:
  `declared` (a label AND a tolerance in mm), `derived` (a measurement exists, nobody stated the
  accuracy), `none`. A bare label is refused deliberately — USIBD's tolerance table is not ours to
  embed, so an unresolvable label would satisfy every "is an LOA recorded?" check while leaving the
  accuracy as unstated as before.

  **The grade red-flagged the platform's own flagship path on its first run.** `scan_deviation` — the
  one real producer of LOD 500 verifications — had the tolerance in hand and spent it on a free-text
  note (`"p95 deviation within {tolerance} m"`), unreadable by anything downstream. It now declares
  the accuracy as a label plus a number.

- **LOD-ELEMENT-TABLE** *(v0.3.903)* — the target matrix was **authorable and uncomparable**.
  `element_category` is free text, so no target could be joined to an element, and `assess()`
  returned targets and achieved distribution side by side without ever comparing them. Targets are
  now addressable by IFC class / Uniformat / discipline with most-specific-wins, Uniformat matches by
  prefix, and compliance is reported per stage with `short_by_rule` naming which rule decided. An
  element no rule addresses is reported as untargeted and never counted as compliant.

**⚖️ Licence, and it shaped every one of the three.** Part I is CC BY-NC-ND and Part II is CC BY-NC —
NonCommercial is a hard exclusion for a public repo and a commercial product, and NoDerivatives
additionally forbids adapting Part I. **No BIMForum content is in the codebase**: no element table, no
keynotes, no per-element definitions, no Uniclass→Omniclass crosswalk, and no band→aspect-value table.
What is used is what is not BIMForum's to license — the ISO 7817-1 aspect names and the AIA band
numbers — with every threshold derived from IFC's own representation vocabulary. The workbook's own
words are the design brief and its limit: its rows are *"examples … intended to be customized by the
user"*. **The platform ships the structure; the project authors the content.**

*What to carry forward: the recurring shape here is a number computed from whatever data happened to
be available and then labelled as the thing somebody wanted to know. All three fixes are the same
move — say what was actually measured, and report the part you could not measure as unmeasured.*

---

## ✅ R41-REACH-WRITES — all four write endpoints wired, each with the step it needed *(2026-08-08, v0.3.890–895)*

The four write-side endpoints the reach sweep deliberately left alone, "because each one needs a
confirmation or recovery step designed rather than bolted on". All four are in. **The rule held: not
one of them turned out to be a three-line wiring job, and two of them were sitting on server defects
that only surfaced because the research came before the button.**

- **`saveSharedParams`** *(v0.3.890)* — the write is a `PUT` that REPLACES the whole registry, so the
  obvious implementation (save the rows this form is holding) silently deletes every definition it
  does not know about, on a standard every model in the project is authored against. The payload is
  therefore always the full list the dialog just read, minus exactly one entry; if `pset`+`name` does
  not identify a single row it refuses rather than guessing, and the count shown afterwards comes
  from a re-read rather than from arithmetic. Extracted to
  [`sharedParamsPanel.ts`](../apps/web/src/viewer/tools/sharedParamsPanel.ts) — the size ratchet fired
  on the commit that added it, which is the friction working on its author.
- **`deleteProjectModel`** *(v0.3.891)* — removing a discipline model does not degrade federated
  clash, it **turns it off**: `analysis.py` needs ≥2 accessible models, so deleting the
  second-to-last one produces a 409 the next time somebody runs clash, not an error at the moment of
  deletion. The confirmation computes that from the same two inputs the server uses and says so
  plainly. [`projectModelsPanel.ts`](../apps/web/src/viewer/tools/projectModelsPanel.ts).
- **`deleteView`** *(server v0.3.892–893, UI v0.3.894)* — **the research found a security defect
  before the button existed.** `return {"deleted": bool(v)}` was truthy whenever the row EXISTED, so
  deleting another user's saved view answered `deleted: true` with the view intact. Worse, the
  mutation check showed the route never compared `project_id`: a view id from a different project was
  **actually deleted** through this project's path. No test covered the route at all.
  [`test_view_delete.py`](../services/api/test_view_delete.py) closes it with 13 paired assertions.
  v0.3.893 then fixed the half missed the first time — neither this route nor its sibling
  `mark_view_seen` checked `module == key`, so the module segment of the URL was decorative. The UI
  (register toolbar) reads the `deleted` flag rather than assuming, which is only safe *because* the
  flag became honest first.
- **`reviewModelVersion`** *(v0.3.895)* — the state transition, and the entry was right that it
  needed the seal work's thinking without needing its mechanism. `approved` is **terminal** (no
  reopen, no revoke), so the confirmation says the words "cannot be undone" and names the account it
  will be recorded against; and the server refuses `approve` from the `api-key` identity in
  multi-user mode, because `reviewed_by` is a permanent answer to "who approved this" and a machine
  credential is not a who. A full password step-up was considered and **rejected with a reason**: a
  seal is a per-document legal attestation, this is an internal QA record, and mandating
  re-authentication would be a contract change for every human caller in exchange for a smaller
  claim. Second finding, unrelated to the write: `ApiClient.modelVersions` declared 4 of the 8 keys
  the server had been sending since R18, so the review state was **invisible** before it was
  unwritable. [`modelReviewPanel.ts`](../apps/web/src/viewer/tools/modelReviewPanel.ts),
  [`test_version_approve_identity.py`](../services/api/test_version_approve_identity.py).

**What to carry forward.** The entry's general rule — *a reach sweep may wire anything that cannot
lose work and must stop at anything that can* — paid for itself twice over. Two of the four endpoints
were **broken in ways a three-line wiring would have shipped straight to users**, and both were found
by reading the endpoint before writing the caller. The cost of the discipline was four small releases
instead of one; the thing it bought was not the confirmations, it was the two defects.

## ✅ R38 Wave 1 — the first ten minutes, three of four shipped *(2026-08-02, v0.3.819–820)*

Two sessions, two lanes, one interface message — the server half and the draw-tool half of the same
item landed without either touching the other's files.

- **A29-LOCAL-PREVIEW** *(v0.3.819)* — a pending edit looks pending: the amber draft marker stays
  over the incremental one-element preview until publish completes (real-looking geometry with no
  marker was indistinguishable from a committed element), and a failed recipe turns the marker RED
  and leaves it where the failure happened — the next draft action is the acknowledgement that
  clears it. State machine unit-tested headless, mutation-checked in both directions.
- **R38-DIM-INPUT** *(v0.3.820)* — the typed-constraint box is VISIBLE as a dimmed hint the moment a
  run is in progress ("type a length — 6 · 12'6 · <30 · 6<30") rather than appearing only after the
  first keystroke of a grammar nobody knew existed. The grammar accepts imperial: 12'6 parses to
  feet-inches, echoes back "3.81 m" in the HUD before the click commits it, and composes with the
  angle form (12'6<30). Strict on nonsense: 13 inches, "'6", mid-token inch marks all refuse.
- **R38-STAIR** *(v0.3.820; server half on main same day)* — "add_stair" / "add_ramp" recipes
  (straight-run IfcStair+IfcStairFlight / IfcRamp+IfcRampFlight, beside the railing recipe in the
  enclosure engine), with the deliberate design call that the run is authored EXACTLY where it was
  drawn: riser/tread and slope compliance is *reported* by "stair_geometry"/"ramp_geometry"
  (module-constant limits, IBC-shaped: riser ≤ 0.19 m, tread ≥ 0.25 m, ramp ≤ 1:12), never enforced
  by silently lengthening a run to somewhere the user did not put it. Verified past unit tests: the
  authored IFC meshes on a write/read round trip and converts cleanly to fragments. The web half
  adds the two draw tools (width param; rise = active storey → next) and SR / RP shortcuts.
  Follow-on (folded into R38-PUSHPULL): show the compliance report live while dragging.

- **R38-PUSHPULL** *(v0.3.821)* — the hero gesture, closed the same day: a single vertical handle
  at the selected element's top face, a base-anchored amber ghost (the bottom face never moves —
  the preview agrees with what the recipe will do), committed through the pre-existing
  "set_extrusion_depth" recipe (IfcExtrudedAreaSolid.Depth edited in place, GUID-stable; the server
  refuses non-extrusions, so no client allowlist to drift). Premise-check found the server half
  already existed — the E3 registry comment literally reads "pull an existing extrusion's depth" —
  so the M-sized item was in fact the gesture alone. Safety rails pure and tested: sub-5 mm drags
  commit nothing, downward drags clamp above zero, base-anchor invariant pinned for every delta.

**Wave 1 complete** (v0.3.819–821). Carried forward as R38-STAIR-LIVE: the live riser/tread
readout while dragging a stair run.

## Reconciliation 2026-07-31 (v0.3.808-810) — eighteen items closed, and how many premises failed

Moved out of `roadmap.md` in one pass. **Eight of these closed because their PREMISE did not survive
checking, not because they were built** — the entry described a gap that was already filled, or filled
differently. That ratio is the finding: a band row is a cache of the detail entries and nothing ever
invalidates it, so it drifts one way only, toward advertising work that is already done.

- ✅ **R33-CLAWBACK-AMOUNT** — shipped (`856970c8`). Verified by reading the implementation, not the PR
  title.

- ✅ **R34-SHEET-SCALE** — shipped (`365976d8`). The engine was already right; nothing set the field.

- ✅ **R21-MULTISCALE — the capability was already there; the entry was stale.** Checked 2026-07-31: `compose_viewports` has taken a **per-viewport `scale`** since the viewport work — its docstring documents `"scale": 100  # 1:100 on paper; omit/None → fit-to-rect`, it reads `vp.get("scale")` per view, and emits a per-view `scale_denom`. Reached at `analysis.py:603`. The entry said "per-viewport scale is the missing parameter"; it was not missing.

  **What WAS missing was the proof, and that is now a gate.** `test_sheet_layout` paired one fixed scale with one fit-to-rect view — which does not test the claim, because "fit" is not a scale anyone specified and a build applying ONE denominator to every viewport would still pass. It now composes **1:50 and 1:100 on one sheet** and asserts each keeps its own denominator *and* that the finer scale is never smaller on paper — a label is cosmetic, an extent is the drawing. Mutation-checked: forcing the first viewport's scale onto all views yields `('1:50','1:50')` and goes red. *(Original entry below.)*

- ✅ **R21-SPACE-TAG-SECT** — **SHIPPED inside `50f195cf`**, which is why nobody noticed: it rode along
  with the qto class-match fix rather than getting its own commit, so the band row went on advertising
  it. `space_tags_section()` is at `drawings.py:677` and is genuinely called at `drawings.py:1468` —
  checked for a *caller*, not merely a definition, because the log lines inside a function match a
  grep for its own name and read exactly like use.

- ✅ **R21-DIM-COMPONENT** — **SHIPPED 2026-07-31 (`1880a508`, v0.3.810).** Every assembly the cut passes
  through carries its `IfcMaterialLayerSet` breakdown, each band drawn in **proportion** so a 12 mm board
  beside 150 mm of insulation reads as the sliver it is. The load-bearing part is the **disagreement**:
  `declared_m` (what the layer set states) and `measured_m` (what the geometry is) are two claims, and a
  set summing to 300 mm on a wall modelled at 250 mm prints `! modelled 250 (-50)` rather than being
  reconciled — there is no basis for preferring either, and printing the declared total silently is how a
  trade builds to a number nobody checked. An element with no layer set is **absent**, not fabricated
  from its overall thickness; a layer with no stated thickness makes the total **unknown**, not a
  confident under-count.

*Why this ring and not more content:* the family shelf now clears every typology (v0.3.670), so the
binding constraint on "can a user take this to LOD 500" moved from **what can be modelled** to
**what can be issued and then verified**. R21 is the issuable half; the LOD-500 verification half
shipped in v0.3.673.

- ✅ **R22-PRODUCTION** — **SHIPPED (`c23c26dd`, PR #142).** `GET /projects/{pid}/progress/reconciliation`
  compares field-installed quantity against the model takeoff per cost code. Both halves had existed
  for months without being joined, and the reason was structural rather than an oversight: the module
  carrying `cost_code` — the join key — is read only by pricing and carbon, while the module the
  production loop actually consumes has no `cost_code` field at all. The loop read the module that
  cannot join. Built as four refusals (units never silently equated, over-install reports >100% rather
  than clamping, an uncoded takeoff says so, unmatched field codes named not counted), and every
  headline percentage carries `covered_pct` — 97% complete across 3% of the model is true and useless.

- ✅ **R22-ITP-NCR** *(M)* — **CLOSED 2026-07-31, premise FAILED.** All four asks exist and are reached.
  `itp.point_type` is a **required select** — Hold Point · Witness Point · Review Point · Surveillance ·
  Monitor — alongside `method`, `acceptance_criteria`, `frequency`, `responsible_party`,
  `verifying_party`, `record_form`. `ncr` runs a real lifecycle `open → dispositioned → closed` with
  `disposition`, `corrective_action`, `root_cause`, `severity` and a link to `inspection`. Element
  attachment is `element_guids`, which `quality_chain.py` reads per element (built by R22-QUALITY-CHAIN,
  #110) and which `routers/construction.py:260,283` serves as the chain and turnover-readiness. Modules
  are reachable in room `schedule` via `rooms.room_of`, and `test_module_rooms` fails the build on an
  unmapped section, so this cannot rot silently.

- ✅ **R22-PROCURE-DEPTH** *(M)* — **CLOSED 2026-07-31, premise FAILED.** Claimed "bid leveling covers
  one step of five" and named three remainders; **all three were already built**, and all three are
  reached: `prequalification` module (EMR, bonding capacity, annual revenue, references, rating,
  expiry, workflow `invited → submitted → approved/rejected`) · `clause_playbook.py`, a per-contract-type
  registry of accept/negotiate/refuse positions with severity and fallback plus a deviation register,
  called from `routers/realestate.py:300,309,332` · `vendor_memory.py` cross-project scorecards, called
  from `routers/benchmarking.py:83`. Module reach resolves to room `planning` via `rooms.room_of`, and
  `test_module_rooms` fails the build on an unmapped section — so the reach claim is checked, not
  asserted.

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

- ✅ **R23-CONSTRAINTS — SHIPPED; the band row was stale.** Verified 2026-07-31 against the code, not the entry: `services/data/src/aec_data/dim_constraints.py` solves dimensional locks as a **linear least-squares system with priority tiers**, reached at `POST /projects/{pid}/constraints/solve` (`analysis.py:522,542`), with `test_dim_constraints` registered and passing. **No new dependency was added** — the module's own docstring records why: the roadmap had unblocked this by accepting `kiwisolver`, and that reasoning was right about the *shape* and wrong about the *need*, since `lstsq`'s **rank** is the degrees of freedom and its **residual** is whether a tier is satisfiable — the two numbers the UX actually needs. *(Original entry below.)*

- ✅ **R24-TRACE-UI ② — SHIPPED 2026-07-31 (`b3a630ea`).** 19 headline figures report which assumptions
  the caller **declared** and which the engine **defaulted**, derived from `model_dump(exclude_unset=True)`
  — deriving from the validated dump would report everything as declared and answer the reviewer's
  question with fiction (mutation-checked: it drops the sparse deal from 8 defaulted inputs to 2).
  `element_link` is `None` on every figure with a stated reason, because the proforma holds no GlobalId
  and an invented terminus is worse than none. `FIGURE_INPUTS` is completeness-checked **both ways**
  against `solve()`'s own output. `POST /proforma/provenance`, plus inline on `/proforma/solve`.

  *Original entry below — the premise correction is the reason this was built backend-first:*

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

- ✅ **R31-PIPELINE-ALLOCATE** — **SHIPPED 2026-07-31 (`6ba0c466`, PR #147, v0.3.810).** The one entry all
  day whose premise **held** on checking, out of eight. `POST /pipeline/allocate` returns the subset with
  the highest total value under a capital constraint — an exact integer optimum, no LP relaxation, on the
  `scipy` already present. **Ranking is not selection:** `fca.portfolio` orders worst-first and advises
  funding those first, which loses whenever one high-return project crowds out two smaller ones that
  together beat it.

  Built as refusals, because a fractional answer here converges and looks buildable: a project that
  cannot fit even with the whole budget is **named** with how far over; a candidate with **no stated
  value is refused**, not treated as zero; and if no optimum computes it returns **no selection** rather
  than substituting the ranking. It reports what greedy would have chosen beside the optimum — and a
  difference of zero means *these candidates have no crowding-out*, not that ranking is safe. That
  self-check caught an inverted fixture during development: the assertion said the **test** could not
  distinguish, not that the solver was wrong.

  A follow-on security fix landed with it (`6a2758d0`): the route shipped guarded by
  `Depends(current_user)`, which identifies without authorising — the third sighting of the v0.3.807 seal
  defect. Caught by the v0.3.808 prefix-coverage gate, one release after that gate shipped.

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

## ✅ R34-SHEET-SCALE — a takeoff region is measured at the scale it was traced under *(2026-07-31)*

**The engine was right and the defect was live anyway.** `takeoff2d.quantify()` has honoured a per-region
`scale_units_per_px` since R34-MEASURE-PROVENANCE, falling back to the call-wide scale when absent, and
recorded which it used in `scale_source`. **Nothing ever set it, and no test ever exercised it** — so the
capability shipped, was never reached, and the roadmap entry describing the gap was itself understated.

The real failure was worse than "one scale per plan set". The trace overlay keeps a single module-level
`scale` that recalibration overwrites, and passed *that* to `quantify()` when Quantify was pressed —
not when the region was drawn. Loading a second sheet clears neither the regions nor the scale. So:

> calibrate at 1/8"=1' → trace the plan → load the detail sheet → recalibrate at 1/2"=1' → Quantify
> ⇒ **the plan regions are re-measured at the detail's scale.** Areas go as scale², so a 4× ratio is a
> 16× area error, priced, with a plausible number as the output.

**Fix:** stamp the scale onto each region at *commit* time. All three commit paths (trace double-click,
trace Enter, flood-fill click) now funnel through one `addRegion()`; the client declares
`scale_units_per_px` on the wire type rather than relying on structural typing to carry an undeclared
property; and a multi-scale result reports the range instead of leaving it to be discovered.

**Grade of the verification** — engine gate `test_takeoff2d.py` mutation-checked: with
`scale_applied` forced to the call scale it fails with *"the region's own 0.10 m/px must win over the
call's 0.05, giving 100 m² not 25"*, green on restore. Web gate `takeoff2d.test.ts` mutation-checked
under the CI invocation: removing the stamp turns 2 of 5 red (stamp count verified 0 before trusting the
run — a mutation that did not land tells you nothing), green on restore. `npm run test --workspace
apps/web` 927/927; typecheck and lint clean. Not exercised live in a browser — the overlay needs an
uploaded drawing and a canvas.

**Two lessons worth more than the fix.**

1. **"Built" and "reachable" are independent, and a *tested* engine can still be an untested feature.**
   The value-check that would have caught this (`assert quantity == 100.0`) did not exist; a range-check
   (`> 0`) would have passed throughout. Ask of any provenance-style field: *who writes it?*
2. **Running `vitest` from the repo root sweeps `.claude/worktrees/`** and tests other sessions' working
   copies — it reported *152 failed / 756 tests* here, none of them real. A positional path filter does
   **not** help, because a worktree path contains `apps/web/src` too. The canonical command is
   `npm run test --workspace apps/web` (what CI runs); it reads `include: ["src/**/*.test.ts"]` relative
   to `apps/web` and cannot see a worktree. A seventh shared-clone hazard, and the first that fabricates
   *failures* rather than hiding them.

---

## 🗓 Reconciliation 2026-07-30 — thirteen items shipped but still listed as open

Ten of these were **merged pull requests** (#94 – #106) whose roadmap entries were never moved; three
were marked ✅ in place and left sitting in the open rings. Together they were **203 lines** of the
1,457-line working roadmap presenting finished work as available work — the exact failure the roadmap's
own housekeeping note warns about, and worse than a stale line elsewhere because an agent picking a
sprint item off this file would have started building something that already exists.

**Why they are archived with their full text rather than one-lined.** Six of the thirteen carry a
*corrected premise* — the entry described the code wrongly and someone found out only by opening the
file. Those corrections are the most reusable thing in the batch, and three of them are three distinct
flavours of the same failure, worth keeping side by side:

- **R23-RECIPE-ARTIFACT** — *"it already is X, just formalise it"* and nothing existed. The single most
  expensive kind of roadmap sentence, because it sets the estimate before anyone opens the file.
- **R22-CLASSIFY-AI** — the entry described a *harmless visible* failure; the truth was a **confident
  wrong number** (an unclassified model priced entirely as *General Requirements* while the estimate
  reported a complete takeoff).
- **R22-MEMORY** — described an unbuilt feature that was **two-thirds already shipped**.

**Also fixed in the same pass:** `R24-PERF-BUDGET` appeared **twice** as an open item, once as
⭐ *(S)* and once as *(S, reinstated)*, with different text.

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

- ✅ **R22-CARBON-OPTION** *(M; **PR #106**, merged 2026-07-29 22:37Z — `option_carbon.py` +
  `design_options.py`)* — verified on `main` by content, not by merge status: `option_carbon.py`
  present, `kgco2e_per_sf` ×3 in `design_options.py`, `POST /options/carbon` routed, and both
  `test_option_carbon` and `test_option_carbon_route` named in `run_tests.py` with both files on disk.
  The premise was right about the capability and wrong about its REACH. `option_score` already scored **generated** massing variants
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

- ✅ **R23-GLTF-COMPRESS** *(S/M; **PR #105**, merged 2026-07-29 — `services/data/src/aec_data/gltf_export.py`
  + `test_gltf_compress.py` / `test_gltf_export.py`)* — verified on `main` by content: `draco_available()`
  present, the 65536 ceiling present, `DracoPy==1.7.0` in `requirements-dev.txt`, and **nothing added to
  `requirements.in`** — the hash lock is deliberately untouched. Note the module is in **`aec_data`**, the
  engine layer, not `aec_api`; `aec_api` may import `aec_data` and never the reverse.
  Shipped in two halves, split by what each costs the consumer. **Per-mesh index width** is free and on
  by default: measured first, indices were **60%** of a 175 KB export and every mesh was far under the
  ceiling, so a fixed uint32 was paying double. uint16 is core glTF 2.0 — no extension, ~30% off every
  export, nothing to check on the reader. **Draco is opt-in** (`draco=True`): 42,592 B → 5,040 B
  (**88%**), but `KHR_draco_mesh_compression` is *required*, not optional, so a consumer without the
  decoder reads nothing. Verified against **headless Blender 3.5**, which decodes Draco; trimesh does
  NOT, and returns the right vertex and triangle counts with every position at (0,0,0) while raising
  nothing — see the note under R22-ACCT-SEAM on what an independent-reader check actually proves.
  `DracoPy==1.7.0` pinned in `requirements-dev.txt` — 2.0.0 ships **Windows wheels only**, and
  `requirements.in` would force a hash-lock recompile. Shipping it in the API image is a
  `requirements.in` line + a Lockfile-workflow run, **not done here**.

  **The review finding is worth more than the feature.** The **uint32 fallback branch was unreachable by
  every fixture in the suite** — all of them ran on ~960-vertex meshes, so nothing could cross a 65,536
  ceiling. It was reached by synthesising the mesh and substituting the producer at the seam, and then
  mutating the ceiling by one exposed the real corruption: index 65,536 reads back as **65,535** — same
  byte length, valid glTF, wrong triangle. **If no fixture can reach a branch, manufacture the input at
  the seam rather than concluding the branch is fine.**

  **Four instances of one shape in a single day, across three subsystems and three authors** — a check
  standing where the failure cannot arrive:
  1. this uint32 branch, unreachable by any fixture in the suite;
  2. the trimesh reader "confirming" a Draco file whose every vertex was `(0,0,0)` (see R22-ACCT-SEAM);
  3. the README room-count gate, satisfied by the word "operate" sitting in an unrelated sentence while
     the README told readers there were six rooms and there were seven;
  4. and the one worth the most, because the instrument itself was wrong: a check for "did #105 ship?"
     that looked for `gltf_export.py` under `services/api/` — the wrong source root — and so would have
     reported MISS for a file that existed. It gave the right answer only because `gh pr list` ran beside
     it and the two disagreed. **Two independent signals is what turns a mis-aimed check into a caught
     one**; a single confident negative is indistinguishable from a true one.

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

---

## 🗓 Session v0.3.703–710 (2026-07-26) — the stall, the container, the claims, and seven engines nobody could call

The second half of 2026-07-26. **R26 THE SPINE completed** and **R27** shipped six of its eight items.
But the durable output of this run was not features — it was discovering that most of our *evidence*
was wrong, and then that most of our *capability was unreachable*.

**Three cases where a green signal measured nothing.** The render audit had never once been pointed at
the shell it was built to verify, then turned out to score an empty-state placeholder as content — a
false pass, which ships rather than getting investigated. The weeks-old "preview stall", written into
a skill as an inherent browser limitation, was five SSE handlers running DB polls on the event loop:
>8s timeouts became ~20 ms. And a suite run that never started looked exactly like one that passed,
because `grep -c "^FAIL"` returns 0 either way.

**Then the bigger one.** Of eleven things built that day, **seven shipped with no route** — fully
tested, CI-green, CodeQL-clean, and unreachable. Every gate in the repo measures the module; none
measures whether a request can arrive. Sprint A wired four; three went to Sprint A-2.

**Roughly ten premises checked, most of them false**, including three of mine: `sheet_layout` already
existed, `.mmproj` already did everything `.mass` was asked to do, the `:8093` blocker had no process
behind it, the CWICR dataset is CC BY-**NC** contrary to its own README, an external perf report's two
headline fixes were backwards, and one release was called green from a truncated query.

### 🏛 R26 remainder, completed v0.3.708

R26-ICONS shipped: one monoline set (Lucide, ISC), **vendored** — an icon set *is* SVG files, so the
31 used are copied in. No package, no CDN, and none of the ~1,500 unused ones in the bundle. They
stroke `currentColor` and fill nothing, so the colour contract governs them automatically and an icon
is *structurally incapable* of introducing another meaning for blue. The "decision" this waited on
turned out to be a false choice between hand-authoring and taking a dependency.


---

## 🗓 Session v0.3.684–702 (2026-07-25/26) — the spine, the 5D/4D rings, and the drawing layer

Two rings closed end to end. **R26 THE SPINE** restructured the app around five rooms constant for
every role, with four verification gates built to protect the restructure rather than to describe it.
**R25 5D** made the model *be* the estimate: quantities measured from the model, rates carrying their
source and date, the 4D and 5D bindings written natively into IFC, and two estimates diffable by
GlobalId. Both rings are archived below exactly as they were specified and shipped; what remains open
from each is listed in [roadmap.md](roadmap.md).

The recurring lesson across the whole run, earned about ten times: **a check that examined nothing
must not report clean.** `unknown` ≠ `none` ≠ `no`. Its sharper sibling arrived late and cost a
release: **a self-consistency check is not a correctness check** — `estimate_diff` reported
`reconciles: true` over per-element numbers it had fabricated by dividing a line evenly across its
GlobalIds. Verify against something you did not write.

## 🏛 R26 — THE SPINE: five rooms, one project *(app audit + redesign, 2026-07-25)*

**The finding, in one line:** *"You built a platform. The UI is presenting it as a filing cabinet."*
Seven workspaces carry **four different left-rail taxonomies**, so nothing a user learns in one
transfers to the next, and modules land in more than one — Facility Condition appears twice in the
Developer rail alone; Model Health appears three times on the Design screen at once. The app has no
**spine**: nothing says what this project is, where it stands, or what to touch next.

**This ring changes the front door, not the building.** Every engine, module, selector spine and
format written to date survives untouched — `query_dsl`, the 130-module config engine, the drawing
generators, the 5D cost binding, LOD-500 verification, the workflow state machines. What changes is
that a module stops being *a destination you must find in a catalog* and becomes **reachable four
ways**: from the room it belongs to, from the element it is anchored to, from your work queue when it
is your turn, and from ⌘K by name. The catalog survives as the fourth path rather than the only one.

**Decisions taken 2026-07-25** *(asked and answered, so they are not re-litigated)*:
professional terms are primary and there is **no Lay mode** — the rooms are **Model · Cost · Schedule ·
Deal · Work**, because the users are builders, developers, architects and engineers who already own the
vocabulary. The new shell lands **behind a flag with both shells live**, and the default flips only
once it beats the old one.

### Sprint A — foundations *(no flag needed; these improve the current shell too)*

- ✅ **R26-ONE-HEALTH** *(shipped v0.3.686)* — **the app currently contradicts itself and it is verified.**
  `portal.ts:643` renders `/models/health → overall_score` ("24 · at risk") and `portal.ts:865` renders
  `/health → health_score` ("77/100") — two engines, one word, same session. Once a user catches the app
  disagreeing with itself, every other number becomes suspect. **One score, computed once, referenced
  everywhere**: establish which engine is canonical, have the other reference rather than recompute.
- ✅ **R26-MODULE-HOME** *(shipped v0.3.686)* — one canonical **room** per module across all 130, plus references. The
  16-section map in the audit is the starting allocation. Ships with the reachability gate below, so a
  restructure cannot silently lose a module.
- **R26-OFFER-NOT-ERROR** *(S)* — a failure becomes an **offer with a button**. `"(404) — needs a
  published model"` becomes *"No published model yet"* + **Publish now**. The viewer empty state
  (v0.3.677) is the pattern to copy; the audit found 12 drawings all returning a raw 404 string.

### Sprint B — the shell, behind a flag

- ✅ **R26-SHELL** *(shipped v0.3.686 + v0.3.689)* — the five-room spine, constant for every role; a
  **workspace weights and preselects** it but never replaces it. Behind `?shell=spine`, with the
  current shell untouched beside it, and a `/rooms` failure falling back to the classic rail rather
  than to an empty one — a shell experiment must not be able to strand a user.
  The rail is now rendered, and building it forced the destination catalog out of `buildNav()` into
  `shell/destinations.ts`. That is where the value was: as a literal inside a render function, nobody
  could check it, which is how a destination came to appear twice in one rail. It is now asserted in
  **both directions** — every destination has a room, and every room entry names a real destination —
  so an unplaced destination is a build failure rather than something a user finds missing.
  Rooms also needed a **tri-state** open/closed memory, unlike stages. A stage defaults to open, so
  recording only collapses suffices; a room defaults to *closed* unless it is the workspace's own,
  because five rooms holding 45 destinations all expanded is the wall of options the spine exists to
  end. Live: Construction opens on Schedule with 5 entries showing and 45 one click away.
- **R26-VITALS** *(M)* — six numbers along the bottom — LOD, area, $/sf, float, IRR, health — replacing
  the 10 viewport controls currently pinned to every workspace whether or not it has a viewport. This
  is the "one model" claim, continuously proven. Viewport controls move into **Model** where they apply.
- **R26-NEXT-ACTION** *(S)* — one line stating what to do next. Master Builder already computes exactly
  this (8-step readiness with *→ Close this gap*); this is promotion, not a new engine.

### Sprint C — the Inspector *(where the last two rings become visible)*

- ✅ **R26-INSPECTOR** *(shipped v0.3.687 + v0.3.690)* — select an element and the six-state strip sits
  directly under the identity header: **designed · checked · priced · scheduled · installed · verified**.
  This is the payoff surface for work already shipped — the 5D binding (v0.3.684) supplies the rate,
  the LOD-500 stamp supplies the accuracy — and it is what makes "one model, one key" tangible in the
  first thirty seconds instead of requiring three tabs and prior knowledge.
  Wiring the three remaining states was where the care went, because each had its own way of turning
  *we did not ask* into a confident answer. `model_qa` caps every offender list at 20, so answering
  "is this element clean" from that sample would report **clean for the 21st duplicate** — a check
  that examined a different element, answering about this one; the rules are now re-evaluated exactly
  per GUID (`model_qa.element_findings`), and that specific case is what the test asserts. An element
  no activity claims looks unscheduled, but where **nothing** in the project binds tasks to elements
  that is a missing capability dressed up as a finding about the building — so the project-wide
  binding is checked first, and only a project that uses it can return a real "no". And verification
  can come from the IFC stamp or a field record: the stamp wins, the record is the fallback, and
  `source` says which, because they are not the same evidence even when they agree.
  ◧ *Still open:* the Properties/Cost/Schedule/Field **tabs** — the strip is the spine of that panel,
  not the whole of it.

### Sprint D — work, tools, and the visual system

- ✅ **R26-WORK-QUEUE** *(shipped v0.3.694)* — the ball-in-court feed is now a queue: dated, bucketed
  by urgency, and carrying the actions this caller can actually run, at `GET /projects/{pid}/work-queue`
  and as **My Work** in every rail's first stage (Work room under the spine).
  Two properties make it worth having. **`undated` is not `later`** — an item nobody dated is a gap
  somebody should close, so it gets its own bucket *above* `later`; folding it in would sort an urgent
  dateless RFI below a routine item due next month and hide the gap that caused it. Absent, blank and
  **unparseable** dates all land there, because an unreadable date means the same thing as a missing
  one. And the actions offered are the ones the **engine will honour** for this party from this state —
  proved by running one against the API, not asserted — because a queue offering a button the server
  rejects spends the user's trust before their time. An action gated behind required fields is shown
  as a link into the record: it needs a form, not a click.
  Built **on** `my_work`, and asserted to return exactly that feed — a second definition of "in my
  court" is how two screens come to disagree, which is the defect one layer up.
- ✅ **R26-TOOLBAR** *(shipped v0.3.691)* — the model toolbar carried **27 unlabeled glyphs, all of
  them, always**. It is now **Levels · Section · Measure · Ask** — four labeled verbs on one row —
  with the other 23 under **More**, grouped and described. Verified live in the running viewer.
  Nothing removed: the layout pass only moves buttons between two containers, so it *cannot* drop a
  tool, and one the table does not describe appears under More tagged `data-unlaid` rather than
  vanishing. Live `unlaid` is 0.
  The design error worth remembering: treating "always visible" as a predicate that returns true let
  contextual verbs push **Ask** past the cap the moment you selected something. A verb you learn the
  position of and then cannot find is worse than one that was never on the bar — pinned verbs now
  hold fixed positions and contextual ones append.
- **R26-WALK-DUP** *(S, found by the above)* — there are **two** first-person walk tools, both 🚶,
  both installed: `envTools` drives the camera per frame and you drag to look; the later R17
  `walkMode` takes a pointer lock and exits on Esc. Labelling made the duplication legible
  (*Walk (drag)* / *Walk (locked)*); deciding which survives is a behaviour change and needs one.
- ✅ **R26-COLOUR-DISCIPLINE** *(shipped v0.3.692)* — blue now means **you can act on this**; green =
  solved, amber = attention, red = blocking, everything else including data is plain text. Five things
  stopped being blue: KPI numbers, the IFC-class badge, form section headings, the ball-in-court pill,
  and node-graph output values. None was ever a control.
  The KPI case is the instructive one, because the tempting fix is wrong both ways: colouring every
  number is what made dashboards unreadable, colouring none loses the cue that some are links. So
  `.kpi-v` is plain and `.kpi-click .kpi-v` stays blue — the colour now asserts something true.
  Verified live: 4 clickable KPIs blue, 2 plain ones in text colour.
  Enforced, not merely stated: `ui/colorContract.ts` lists every selector allowed to paint with the
  accent and its test asserts that list against `style.css` in **both directions**. Writing the list
  by hand first was instructive — most guesses were wrong, because they used the accent only on
  borders, which the gate deliberately exempts.
- **R26-ICONS** *(S — needs a decision)* — one monoline icon set at a single weight, state-tinted,
  replacing coloured emoji. **Blocked on a source**: hand-authoring ~100 inline SVGs is a sprint of
  its own, and any licensed set is a new dependency needing an explicit OK (MIT/BSD/Apache only).
  Worth noting the emoji are not currently a *legibility* failure now that the toolbar carries words —
  this is polish, not a defect, so it should not jump the queue on that basis.

### Sprint E — verification *(all four gates were requested; none is optional)*

- ✅ **R26-V-REACH** *(shipped v0.3.686 — deliberately BEFORE the restructure it protects)* — assert **every module has exactly one canonical home and is reachable**. The
  single biggest risk in an IA change is silently losing a module; this makes that impossible.
- ✅ **R26-V-CONSISTENT** *(shipped v0.3.693)* — six cross-surface identities asserted **between the
  endpoints that render them**, not against arithmetic restated in the test: comparing an endpoint to
  a local recomputation only proves the test can add up, and it was *agreement between screens* that
  was the defect. Open RFIs (dashboard vs board) · total records (KPI vs its own breakdown) · budget
  (cost summary vs the dashboard's snapshot) · my action items · health score (headline vs the
  domains it is a mean of) · module catalog vs room allocation. Confirmed to bite by perturbing the
  dashboard and watching it fail.
  Every check runs on a **seeded, non-zero** project, because zero equals zero on every surface and a
  gate run against an empty project passes while proving nothing. Two mistakes are recorded in the
  file: the health check originally read a `score` field the domains do not have, so it skipped
  silently and passed having tested nothing; and the seed for one module failed without being
  asserted, leaving three identities comparing two views of the same absence.
  Coverage is **declared** in `IDENTITIES` and is explicitly not a claim of global consistency — six
  pairs are pinned, and saying more would be the same defect one level up.
- ✅ **R26-V-LIVE** *(shipped v0.3.695)* — a **repeatable** render audit (`window.__liveAudit()`, dev
  only), not a click-through. Click-throughs do not survive: the next person redoes the whole thing,
  and afterwards nobody can tell whether a pane was blank or merely unmeasured. Live result: **all 7
  workspaces ok, 0 problems, 0 unknown.**
  What is tested is not "does the app render" but **does the auditor lie**. Four traps, all of which
  fail toward a false blank — the expensive direction, because it invents defects that then get
  "fixed": `innerText` is empty for anything not laid out · a click rebuilds the nav and detaches held
  nodes · the shell is not the content pane · **and a pane that is still booting is not an empty
  pane**. The fourth was found by running the auditor against the real app: it reported Model, Design
  and Developer blank, and all three were mid-boot and fully populated seconds later. An empty verdict
  is now never final on first look.
  Two bugs in the auditor were caught by its own tests: `offsetParent` reports every `position:fixed`
  element as hidden (so the floating toolbar and every modal would have read as invisible), and it is
  untestable without a layout engine — a guard against the audit's worst failure mode has to be the
  best-tested thing in the file, not the least.
- **R26-V-TIMING** *(M)* — instrument first-task completion per persona against the audit's baseline, so
  the redesign's claim is **measured rather than asserted**.

## 💵 R25 — 5D: the model IS the estimate *(research 2026-07-25; phase 1 shipped v0.3.684)*

**The research changed the architecture before any code was written.** The plan was a bespoke
task→element join table. But IFC already carries both bindings natively — `IfcRelAssignsToProcess`
(products → task, the 4D link) and `IfcRelAssignsToControl` → `IfcCostItem` (elements → priced line,
the 5D link), grouped by `IfcCostSchedule`. A join table would have put the 5D spine **outside** the
model: unable to travel with the file, unreadable by any other tool, and drifting on every re-export —
a direct breach of *IFC is the source of truth*. The industry guidance agrees on the other half:
elements map to a WBS/CBS, and **model-based measurement rules must state how each quantity is
derived**.

**✅ Shipped (v0.3.684)**
- `aec_data/cost_ifc.py` — cost written into the model as `IfcCostItem` + `IfcRelAssignsToControl`,
  read back through a real re-parse from disk. Every quantity carries its **basis** as the quantity's
  own description, because *"120 m²"* is not a measurement and *"120 m², net area, openings deducted"*
  is. An unmatched GlobalId is **reported** while the line is still written — dropping it would make
  the estimate quietly cheaper than the project.
- `aec_api/fived.py` — a cost rule is **a stored `query_dsl` selector plus a rate**, not a new engine,
  which is what lets `IfcWall & FireRating=2HR` on the podium be a different line from a level-12
  partition. Later rules win (layering is how estimates are built) and each element records **which**
  rule priced it. An element no rule matched is **unpriced and reported**, never silently zero — the
  same failure mode as a clash matrix calling an untested pair clean.
- `POST /projects/{pid}/cost/estimate`.

**Next rungs, in order**
- ✅ **R25-TASK-BIND** *(shipped v0.3.696)* — the 4D half, in `aec_data/fourd_ifc.py`:
  `write_work_schedule` / `read_work_schedule` over `IfcWorkSchedule` + `IfcTask`, mirroring
  `cost_ifc`. The asymmetry it closes is the point — `schedule.from_ifc` could always *read* tasks and
  their outputs, but nothing could *write* them, so a schedule authored elsewhere could be consumed
  while the platform's own lived only in its database. A read half with no write half is a one-way
  door. This also unblocks R21-4D-CLASH phase 2 and turns the Inspector's `scheduled` state from
  structurally unanswerable into answerable.
  **This entry named the wrong relation, and so did the first implementation.** `IfcRelAssignsToProcess`
  is the task's *input* (`task.OperatesOn` — "operates on that product"). The link for "this task
  builds this element" is `IfcRelAssignsToProduct`, the task's **output**. Both are real IFC and both
  round-trip cleanly through a reader written to match, so the error is invisible to any test that
  only checks its own writer — what caught it was asserting the binding against `schedule.from_ifc`,
  which like every tool asking "what does this task build" reads outputs.
  Three deliberate behaviours: an unmatched GlobalId is **reported** and its task still written (the
  work is real; dropping it makes a programme quietly shorter than the project) · **half** a date
  range writes no dates at all (a duration resting on one supplied end reads as authoritative and is
  not) · an *absent* task type defaults to CONSTRUCTION but an *empty* one is refused, the same
  distinction `cost_ifc` draws for `basis`.
- ✅ **R25-QTO-WIRE** *(shipped v0.3.697)* — `qto.measure()` returns every element's quantities by
  GlobalId, and the estimate route composes it, so a 5D estimate prices the **model's own** numbers.
  This is the actual content of "the model IS the estimate": every rule, rate and roll-up could be
  right while the quantities described a different building — an estimate internally consistent and
  externally wrong, which is the worst kind because nothing in it looks off.
  The substance is **provenance**. `declared` is the model's own `IfcElementQuantity`; `computed` is
  our measurement off the meshed solid; `override` is the caller replacing both; and an **absent**
  provenance reads `unknown`, never `declared` — a caller who sends quantities with no provenance has
  said nothing about where they came from. A line is only `declared` when *every* element in it was;
  one measured element in fifty makes it `mixed`, because rounding that away would have the reader
  believe the model asserted a number we partly made up. `computed_quantity_lines` /
  `computed_quantity_amount` say how much of the total rests on our arithmetic.
  Provenance annotates and never moves a number — the totals are asserted identical across all four
  labellings, so the label cannot quietly start doing arithmetic.
- ✅ **R25-COST-VINTAGE** *(shipped v0.3.699)* — a cost rule may now set `rate_from: "vintage"` and
  draw its rate from the project's pinned cost database, localized and escalated, so the number
  arrives with a **year** attached. Each line reports `rate_source` (`quoted` · `vintage` · `mixed`)
  and the payload carries the vintage metadata. This is the other half of v0.3.697's quantity
  provenance: an estimate is a rate times a quantity, and a line that can answer for one half and not
  the other is only half checkable. Two estimates differing 40% because one priced off a 2019 vintage
  is a question somebody can answer; the same gap with bare numbers on both sides is not.
  **A vintage rule whose class the database does not price gets its own state, `no_rate`.** The rule
  matched the element, so it is not *unpriced*; there is no number, so it is not *priced*. Folding it
  into either would make the estimate silently short or silently free, and `complete` is false while
  any remain. Layering still wins: a later rule that can price the element clears the flag, because
  reporting a gap a subsequent rule already closed sends an estimator to check something that is fine.
- ✅ **R25-ESTIMATE-DIFF** *(shipped v0.3.700)* — `estimate_diff.py` +
  `POST /projects/{pid}/estimate/diff`. "The estimate went up $340k" is not information; *which
  elements* moved it and *why* is — and because both estimates key on GlobalId, the diff can say.
  That is the whole reason this platform refuses to identify elements any other way.
  **Four causes, because they are four different questions.** `added`/`removed` are scope;
  `requantified` is a design event; `repriced` is a commercial decision. A number that moved because a
  rate was updated and one that moved because a wall got longer must never sit in the same row —
  collapsing them into "the total changed" is how an estimate review becomes an argument.
  **`both` is not a leftover bucket.** When quantity and rate move together, apportioning the delta
  across the other two yields two numbers that sum correctly and neither of which describes what
  happened, so it is one change with both pairs shown.
  **The parts add back to the whole,** and `reconciles` says so. A diff that looks authoritative while
  quietly losing money is worse than no diff, so the residual is computed and reported, not assumed.
- **R25-TRACE-UI** *(M)* — *(same surface as R24-TRACE-UI)* the chain made visible: figure → cost line
  → rule → selector → element.

---

## 🗓 Session v0.3.543–567 (2026-07-20) — quick-wins, flagship sprints, master-builder skill, fab + solver tails

The big continuous run: a quick-wins sprint, two flagship big-ticket tracks driven multiple phases deep
(Schedule Optioneering and the Client-Portal), the **master-builder skill installed in-repo and
co-evolved with the platform**, plus a hardening pass, a security bump, and two structural/fab tails —
every item a verified CI-green release, **CodeQL 0 open alerts throughout**. Per-release detail in
[CHANGELOG.md](../CHANGELOG.md); the highlights:

- **⚡ QUICK-WINS SPRINT (v0.3.552, batched):** NORM-VALID tails (STEP-syntax + bSDD classification-coverage
  lanes), **WARN-1** unified model-warnings feed (`model_warnings.py` + `/models/warnings`), DRAW-STATUS
  drawing lifecycle field, SCOPE-GAP spec-section refinement (`covered_without_specs`), GOLDEN-THREAD seed
  (`/golden-thread/seed` from the model-CI report, idempotent).
- **🧮 SPRINT B — SCHEDULE OPTIONEERING (flagship, v0.3.553–556):** deterministic crew/zoning optioneer
  over the Takt line-of-balance model (`schedule_options.py` + `/schedule/optioneer`) → widened with
  fast-track overlap + sequence permutation (grid capped at 800) → the 🧮 scenario-comparison panel
  (Pareto frontier + recommended-plan summary) → optimises the **real project** (takt train derived from
  the project's own `schedule_activity` records).
- **🏛 SPRINT MB — MASTER BUILDER (v0.3.557–558, 562) + the skill:** installed the **`master-builder`
  skill** (`.claude/skills/master-builder`, now v0.3.2) and shipped its 8-step protocol as software —
  `master_builder.py` + `/master-builder/brief` + the 🏛 panel (place → program/HBU → feasibility →
  regulatory → design → delivery → risk → handover, grounded in the project's jurisdiction) → place-grounding
  from the model's georeferencing (code family + hemisphere/climate band + hazard params to verify) →
  a shareable **Markdown brief** (`/master-builder/brief.md`). Skill co-evolved: build-doctrine §11
  (synthesis over sources of truth), global-codes §8 (mechanized grounding), construction-delivery
  (fabrication-output honesty boundary).
- **🔗 SPRINT D — CLIENT-PORTAL (v0.3.563–566):** a `ShareToken` model + `client_portal.py` + editor-gated
  token management + the PUBLIC `/shared/{token}/digest` (curated readiness only — no record data / GUIDs /
  financials / PII) → a self-contained fully-escaped public HTML readiness page → **selections & allowances**
  rollup (`selections.py` + `/selections/summary`: allowance-vs-actual, per-category deltas, over-allowance
  change-order candidates) → **push overages to change events** (`/selections/push-change-events`, idempotent).
- **🔩 SPRINT E — FAB-DELIVER phase-1 (v0.3.560):** rebar bar-bending schedule now carries per-mark leg
  lengths, bend angles, bend count, and shape family off the authored geometry (`rebar_rules.bending_detail`).
  The BVBS machine bending-file export is **held behind a validation gate** (a byte-wrong file mis-bends
  real steel — per the fabrication-output doctrine).
- **🧰 Tails & hygiene:** **SOLVER-OUT** Code_Aster `.mail` mesh export beside the OpenSees `.tcl`
  (v0.3.567); **RT-ORJSON remainder** for the hot storage-blob paths (v0.3.550, measured 1.7×/4.8×); a
  **hardening pass** over the wave (v0.3.559 — adversarial audit, no XSS/no high-sev, 3 low-sev fixes: DMS
  sign, optioneer input-normalisation + value clamps + 422s, a panel row-highlight identity bug); and a
  **security bump** clearing the brace-expansion advisories (v0.3.561).

## 🗓 Session v0.3.510–542 (2026-07-19) — execution-queue tail + R15/R14 rings closed

Continuation of the audit-synthesized wave: the ★ execution queue (#0–20) finished, then the entire
🧭 **R15 ring** was executed to completion and the shippable **R14** tiers cleared — every item a
verified CI-green release, **CodeQL 0 open alerts throughout**. **Recurring lesson:** "the well is dry"
was repeatedly wrong — verifying by source (route/module/engine) kept surfacing genuine bounded items
mislabeled as flagship-scale. Full per-release detail is in [CHANGELOG.md](../CHANGELOG.md) (v0.3.510–
542); the highlights:

- **Queue tail:** HARDEN-2 (v0.3.510, 2 sec + 7 bug fixes), RT-ORJSON (v0.3.511, 7–9× serialize),
  MARKUP-2 slices (v0.3.512–516), XLSX-ROUNDTRIP + DXF-EXPORT + QUERY-DSL clash wiring + FOURD-SIM-2 +
  RESOURCE-LEVEL-2 (v0.3.513), MODEL-CI-2/3 (v0.3.520), PERF-4 (v0.3.519), SURF-2b/4b (v0.3.517–518),
  CX-1 commissioning + REBAR-RULES/BBS + PROC-LOOP (v0.3.520–521), ENTITLE-1 export gates (v0.3.522),
  JOB-QUEUE pid-lock (v0.3.523), CLOUD-BRIDGE massing.cloud (v0.3.524).
- **R15 ring (all shipped/verified):** SMART-VIEWS + clash-freshness (v0.3.525/530), VERSION-COMPARE-3D
  (v0.3.526), IFCPATCH-LIB purges + **SUBSET-EXPORT** discipline slice (v0.3.527/533), BCF-API-SRV 2.1 +
  viewpoints (v0.3.528–529), EST-ASSEMBLIES (v0.3.531), **FEM-EXPORT** OpenSees (v0.3.532), **NORM-VALID**
  openBIM conformance (v0.3.535), **REVISION-DELTA** version→cost (v0.3.536), **BEP-GEN** ISO 19650 BIM
  Execution Plan (v0.3.537), **ROLES-BIM** info-management RACI template (v0.3.538), **PM-CLOSE** charter +
  lessons-learned (v0.3.539), **TRANSMIT-ITP** inspection & test plan (v0.3.540), **MEETINGS** action-item
  ↔ RFI/issue links (v0.3.541), **EST-BANDS** range estimate (v0.3.542).
- **Along the way:** COORD-FRESH stale-clash recheck (v0.3.529), a subset-export path-injection harden
  (v0.3.534, CodeQL), and a dev CORS fix (localhost + 127.0.0.1 both trusted, v0.3.542).

## 🗓 Session v0.3.493–509 (2026-07-19) — the ★ execution-queue wave (audit-synthesized)

The R15 landscape + codebase + security/perf audit pass (task #445) produced a re-prioritized
execution queue; this wave executed items #0–16 top-down, every one a verified CI-green release,
CodeQL 0 open alerts throughout. **Recurring audit correction:** the "orphaned capability" counts were
materially overstated — the workflow state machine, 4D element-linking, temp site-logistics geometry,
and most SURF-3/4 candidates already existed under other names — so each item narrowed to its genuine
delta after verifying by feature/route, not wrapper name.

- **#0 SEC-XSS (493)** — attachment stored-XSS closed: raster-allowlist inline, everything else
  `attachment` + nosniff + CSP sandbox.
- **#1–2 PERF-1/2 (494)** — event-loop-blocking pdf/import/upload ops → `run_in_threadpool`;
  `drawings.bake()` memoized + `world_bounds()` AABB fast path; 2 frontend listener leaks fixed.
- **#3 PERF-3 (495)** — `discipline_summary_file` mtime-keyed cache (was re-tessellating per GET);
  `clash_detect` durable job kind (narrow-phase clash off the request path).
- **#4 PERF-4 partial (496)** — TEST-FASTPATH (fresh-DB init skips `_ensure_columns/_indexes`;
  suite ~780s→~525s) + PAYLOAD-CAPS (`/topics` limit/offset, `/pins` hard cap). DASH-UNION et al
  remain open (see queue).
- **#5 PANEL-LAZY (497)** — ~30 secondary portal panels dynamic-imported (per-file chunks) out of
  the eager shell.
- **#6 SURF-1 (498)** — Schedule toolbar: P6/MSP import, predictive alerts, earned schedule surfaced.
- **#7 SURF-2 (499)** — Budget "📐 Estimate from the model" card: conceptual, resource-based (L/M/E),
  QTO-by-floor, DXF takeoff.
- **#8 SURF-3 (verified 499)** — already done; the audit's orphan flag was a false positive (viewer
  dispatches recipes by name via `authorAndReload`, bypassing typed wrappers).
- **#9 SURF-4 (500)** — viewer "🔍 Data QA" surfacing `/elements/qa` completeness with
  click-to-select-missing. **(501)** — fix(sec): the SURF-2 card wrote a DXF filename + server/model
  free-text into `innerHTML` unescaped (CodeQL js/xss-through-dom); `esc()` exported from `ui/charts`
  and applied.
- **#10 WORKFLOW-ENGINE (502) + WFE-2 (503)** — audit premise corrected (the state machine already
  shipped); genuine gaps closed: `party_owner` now tracks ball-in-court on every transition
  (`court_party`), and `escalation.py` turns the due-feed into action (L1/L2/L3 ladder,
  `escalation:L{n}` timeline entries the notifications feed surfaces, `GET/POST /escalations`,
  idempotent `escalation_scan` job kind). 503 = the portal-home escalation surface with one-click
  "escalate & notify".
- **#11 SCHED-P6 (504)** — the export half of the round-trip: `GET /schedule/export?fmt=xer|msp`
  serializes the LIVE schedule keyed by activity code (`to_xer`/`to_mspdi`); import auto-detects
  MSPDI too (`parse_mspdi`); re-import matches by code, no GUID drift. Export buttons on the panel.
- **#12 FOURD-SIM core (505)** — the viewer 4D playback (`viewer/fourD.ts`): scrub/auto-play through
  construction days, built-so-far shown, not-yet-built hidden, the day's completions amber; reusable
  `LayerManager.colorGuids/resetColors`. (Linking + temp geometry already existed — W9-5.)
- **#13 QUERY-DSL (506)** — the selector grammar over the property index (`query_dsl.py`:
  parse/matches/select; ops `= != >= <= > < ~` + existence) + `GET /model/select` + the viewer
  "🔎 Query-select" isolate tool. The reusable scoping spine.
- **#14 RULE-LIB (507)** — user-authored parametric rules on QUERY-DSL (scope + require + severity;
  `rule_library.py`, `GET/PUT /rules` atomic-validated, `GET /rules/run`, viewer "✔ Rule check").
- **#15 RESOURCE-LEVEL named baselines (508)** — `schedule_baselines.py`: a library of named
  snapshots (GMP/Recovery/…) + variance vs any chosen baseline (`/schedule/baselines` CRUD +
  `/baselines/{id|latest}/variance`) + the "📌 Baselines" drawer.
- **#16 MODEL-CI core (509)** — the pluggable check-pack runner (`model_ci.py` + `POST /ci/run` +
  `GET /ci/latest`) → pass/warn/fail badge artifact, seeded with RULE-LIB + data-completeness gates;
  viewer "▢ Model CI" tool.

## 🗓 Sessions v0.3.457–492 (2026-07-18/19) — the P1 run + P2 ring (pre-queue)

The 2026-07-18 re-prioritization's P1 list ran to completion, then the P2 ring advanced
opportunistically. Every item live-verified where the preview allowed.

**P1 (all shipped):** COLLAB-CURSORS (458 — peer view-cones/name tags; COLLAB-1 complete) ·
PREFLIGHT (459 — composed gate over health/classification/keynotes/QA/IDS/BCF, gates
`/drawing-set/issue`) · SITE-1 first slice (460 — OSM buildings/roads/land-use, cached, ODbL) ·
UX-2 snap (461 — vertex/midpoint/corner/center snapping + rubber guides) · EST-1 (462 — labour
estimate prices the QTO; `/schedule/from-estimate` upserts crew-day CPM activities) · REL-4 leaves
(463 collab/presence · 467 KEYS+dyn-input · 468 reportCenter · 481 measureSection) · JOB-QUEUE
artifact pattern (464 `compiled_set_pdf` + artifact streaming; 487 `model_export` .glb/.gltf) ·
3D-HERO (465) · SHEET-LINK (466 — cover-index GoTo links + callout-bubble anchors).

**P2 ring (shipped through 492):** RISK-BOARD (470) · CODE-1/3 jurisdiction+edition (471) · S4 undo
grouping (471) · B1 sign-in-first + AI read tools (472) · PROFORMA-LIVE + E7 live schedules (473) ·
NL-QA recipes + READY-AGENT (474) · BOARDS + cost calibration (475) · ENV-1 wind screen + VIZ-1
parity (476) · MEP sizing (pressure-loss/tray-fill/thermal) + VIZ-2 SSAO/bloom + B2 tour + CODE-4
amendments (477) · W10-4 auto_connect_mep + A1/A2/C1 provider prominence + REL-6 webhook privacy
(478) · B3/B4/C2 onboarding + SpecLink + F0b representations (479) · D8 COMcheck approvability→BCF
(480) · REL-5 bridge dataclasses + measureSection (481) · E6 design-option branches + E8 model
guardrails (483) · W9-6b program_fit (484) · W9-5 logistics motion + swept crane clash (485) ·
W9-4 doc_text cited retrieval (486) · REL-8 docstrings enforced (487) · E3 sketch-to-BIM
extrude/pull (488) · B5 connection assemblies (490) · UX-1 full ribbon merge (491) · R14 ring
planned + doc_text ReDoS round 2 (492). DISC-poché (469).

## 🗓 Session v0.3.413–425 (2026-07-17) — the four-lane audit → prioritized upgrade cycle

A full-platform evaluation (four parallel audit lanes: backend bugs, web frontend, docs/repo surface,
2026 industry research) produced the **🎯 Upgrade plan** in [roadmap.md](roadmap.md), then executed it
in priority order — every item its own verified CI-green release, CodeQL 0 throughout.

- **413 — docs/repo surface**: README de-staled + neutral wording; status pages live-badged; roadmap
  coherence; issue/PR templates; the plan itself.
- **P0 security (414–417)**: **SEC-TENANT** (portfolio/benchmark roll-ups membership-scoped — was a
  cross-tenant P&L/WIP leak; + search limit clamp + attachment predicate; `test_tenant_scoping.py`),
  **WEB-BOOT** (corrupted `aec-settings` no longer bricks the app), **SEC-GUARD** (production guard on
  any non-SQLite DB or `AEC_ENV=production`), **SEC-MCP** (membership authz in MCP dispatch).
- **P1 reliability (418–420)**: **WEB-LIVE** (SSE re-subscribe + disconnected surface) + **WEB-LEAKS**
  (drag-listener + preview-GPU leaks), **DOC-RACE** (per-project sidecar locks, 12-thread proof),
  **TZ-UTC** (one UTC clock across 7 aging engines — the fix tripped its own drift live in tests).
- **P2 docs/demo (421–422)**: **DEMO-REGEN** (Pages snapshot recaptured, 952 fixtures — was ~110
  releases stale), **README-TRIM** (983→560) + June-audit supersede banners.
- **P3 2026 capabilities (423–425)**: **SCHED-RISK** (Monte Carlo P10/50/80/90 over the CPM network,
  criticality index, delay drivers, PPC-calibrated tail), **CARBON-EC3** (per-element A1–A3 off the
  model, Buy Clean limit check, LEED-style inventory — LEED v5 mandate effective 2026-07-01),
  **PERMIT-CHECK** (submission-readiness report over the code engines + drawing register).

*P3 continued (426–431):* **UI-SURFACE** (426, first slice — Monte Carlo card in Schedule; Carbon-
compliance + Permit-readiness in Risk & Cost; 429 added the acceleration-levers card) · **QA-AGENT**
(427 — `drawing_qa` sheet-cited set review) · **LAYOUT-EXPORT** (№16 found already shipped in Wave 8) ·
**5D-BIND** (428 — `element_5d` GUID-keyed live cost+carbon rows, reprice-on-edit).

**OpenAEC / Open CAD Studio study (2026-07-17)** → the 🧭 CAD-UX lessons in roadmap.md; shipped from it:
**CADCMD** (430 — a deterministic CAD command line, `cadCommands.ts`, over the edit recipes: WALL/COLUMN/
BEAM/SLAB/LEVEL/SPACE + aliases + history + spacebar-repeat, 11 pure-parser tests) and **AUTHOR-MATRIX**
(431 — `authoring_matrix`, a live 76-recipe/14-category coverage table from `edit.RECIPES`, served at
`/reference/authoring-matrix`, committed to `docs/authoring-matrix.md`, guarded by a completeness test).
Detail in memory [[openaec-study-2026-07-17]].

*Remaining open (roadmap.md §🎯 / §🧭): UI-SURFACE №11 tail (unused-method triage), the №18 later-bucket,
and the CAD-UX lessons SNAP-KIT / CLIENT-LIMITS / VIEWER-FUNNEL / PLUGIN-REGISTRY / MCP-PACK /
SHEET-VIEWPORTS.*

## 🗓 Session v0.3.398–412 (2026-07-17) — code-gap closeouts + the REL-3 leaf marathon

Two arcs in one session: the **code-gap sweep** (verifiable analysis/QA wins pulled forward while
modularization looked stuck) and then — once the DEV-2 import-cycle guards made façade extractions safe —
the **REL-3 leaf marathon** that decomposed the worst files in the tree. 254/254 suites green at the end;
CodeQL 0 open alerts throughout. Detail in memory [[gap-sweep-2026-07-17]].

**Code-gap closeouts (398–401):**
- **MODEL-DIFF (398):** per-element fingerprints on every version snapshot (name · class · type · level ·
  Pset-hash · Qto-hash); `versions.diff` now reports **modified** elements + what changed (renamed /
  reclassified / retyped / re-leveled / properties / quantities); `/versions/diff` + viewer Version history
  with click-to-select-in-3D; `ModelVersion.fingerprints` JSON column auto-migrates.
- **FIN-TEST (399):** `test_leasemgmt.py` (escalation compounding, CAM recovery + over/under, renewal
  at-risk) + `test_changeorders.py` (CO pipeline by state, schedule-days excl. rejected, ball-in-court,
  ROM exposure) — hand-computed; math was already correct, now locked.
- **DRIFT (400):** `lateral.drift_check` (ASCE 7-22 §12.12.1 allowable Δa by Risk Category; §12.8.6 design
  drift Δ=Cd·δxe/Ie with per-story pass/fail) + `torsional_check` (§12.3.2.1 Type 1a/1b + Ax), wired into
  `lateral_from_model` + the `structure/lateral` endpoint.
- **IFC-QA (401):** `aec_data/roundtrip_qa.py` — `fingerprint` / `compare` (identical + lossless verdicts,
  per-dimension deltas, offender GUIDs) / `roundtrip` (write→reopen); `GET …/models/export-qa`.

**DEV-2 cycle guards (402–403):** `test_import_cycles.py` (stdlib ast + Tarjan over `aec_api`+`aec_data`
top-level imports) and `apps/web/src/no-import-cycles.test.ts` (runtime import graph, `import type`
excluded — tsc erases it). 0 cycles both sides; no new deps; a regression fails CI with the cycle path.

**REL-3 leaf marathon (404–412)**, each a leaf + façade re-export (zero caller change), each verified by
the guard + its suites: `connectors_mappings.py` (404, pure Procore field-mapping) · `drawings_render.py`
(405, sheet SVG/PDF renderers; `data/drawings.py` 941→788) · `edit_core.py` (406, the 9 authoring
primitives — the foundation that unblocked the recipe splits) · `connectors_vendors.py` (407, raw
Procore/ACC/QuickBooks/ERP HTTP clients; test seams stay on `connectors.py`; 495→325 total) ·
`edit_asbuilt.py` (408, phase/as-built/manufacturer/classification writers) · `edit_mep.py` (409, the
416-line MEP group) · `edit_struct.py` (410, walls/slabs/columns/beams/steel/rebar/footings) ·
`edit_annotate.py` (411, notes/dims/rev-clouds/tags) · `edit_enclosure.py` (412, coverings/railings/
roofs/hosted openings). **`edit.py` 2127→761 (−64%)**; remainder is the genuine engine core.

---

## 🗓 Session v0.3.393–397 (2026-07-17) — dev-velocity & modularization

The pivot from features to **making development faster + the codebase more maintainable** (the release cycle
was the bottleneck). Detail in memory [[weekend-push-2026-07-17]].

- **DEV-1 — parallel test gate (393):** `run_tests.py` runs the ~180 isolated `test_*.py` through a bounded
  `ThreadPoolExecutor` + a geometry worker cap (`AEC_GEOM_WORKERS=1` via new `aec_data/geomconf.py`, so each
  test is single-threaded and the outer parallelism owns the cores — no cpu×cpu oversubscription) +
  `PYTHONUTF8=1`/utf-8 capture. **~30 min → ~11 min (2.7×)**, 250/250 green, prod geom default unchanged.
- **REL-3 modularization — 4 clean slices**, each a leaf + façade re-export at the old path (zero caller
  change): codecheck egress → `codecheck_egress.py` (394, 502→184); module full-text search →
  `modules_search.py` DI leaf (395); computed schedules → `drawing_schedules.py` (396, `drawing.py` 941→821);
  **the registry+table foundation → `modules_registry.py`** (397, `modules.py` 969→882) — the enabling
  extraction that lets the CRUD/feed layers split without a cycle.
- Roadmap reorganized: dev-velocity/modularization made the top focus; large feature/infra bets tracked for
  later. The ruff-autofix hook fixed to use `$CLAUDE_PROJECT_DIR`.

## 🗓 Session v0.3.380–392 (2026-07-17) — analysis engines, deliverables, dev-tooling

The **complete W10-7 analytical model** + preliminary analyses, the top enterprise deliverable/cleanup gaps,
and the ruff-autofix dev hook. All direct-to-main, each CI-green + 0 CodeQL alerts. Detail in memory
[[weekend-push-2026-07-17]].

**Authoring UX** — **KEYS** Revit-style 2-letter draw shortcuts (380). **PREFLIGHT** one-click PASS/HOLD
issuance gate composing the model-health lenses + classification completeness + open blockers (381).

**Structural analysis (the analytical model is now complete + solver-ready):**
- **STRUCT-SOLVE** (382) — gravity load case → determinate member statics (reactions, shear/moment/deflection
  diagrams); `aec_api/struct_solve.py`, `GET /structure/solve`.
- **STRUCT-LATERAL** (389) — ASCE 7 §12.8 seismic ELF + simplified MWFRS wind → base shear + story
  forces/shears/overturning, governing flagged; `aec_api/lateral.py`.
- **STRUCT-LOADS-IFC** (390) — `apply_structural_loads` writes `IfcStructuralLinearAction` (D+L) onto every
  analytical member → loaded IFC.
- **Analytical shear walls** (391) — load-bearing walls → vertical mid-plane `IfcStructuralSurfaceMember`s.
- **Analytical supports** (392) — `apply_structural_supports` fixes base nodes (pinned/fixed
  `IfcBoundaryNodeCondition`) → a complete, solvable analytical IFC handed off to SAP2000/RISA/Robot.

**MEP** — **MEP-SIZE** (386) air/water velocity checks vs ASHRAE/erosion limits + NEC tray fill,
`aec_data/mep_sizing.py`, `GET /mep/sizing`.

**Construction docs / deliverables** — **VIEW-RANGE** (383) plan view-depth (foundations below the cut as
dashed lines); **COVER-SHEET** (384) rendered cover + key-plan thumbnail + discipline-grouped paginated
index; **EXPORT** (387) binary glTF `.glb` + first-class IFC re-export; **TAKEOFF-2D** (388) drawing-based
quantity takeoff → the 5D estimate.

**Code health** — **DISC-SSOT** (385) sheet-series is now a derived view of the one discipline map
(`classification.series_of_ifc_class`; `sheetgen`/cover private tables removed). Self-authored **ruff-autofix
PostToolUse hook** (`.claude/hooks/ruff_fix.py`, `$CLAUDE_PROJECT_DIR`).

## 🗓 Session v0.3.352–377 (2026-07-16/17) — frontier tracks, UX, hardening, deliverables

**Discipline / classification depth** — DISC-coverage report (`/elements/by-discipline` completeness view,
v0.3.352); DISC-cw context-aware curtain-wall/roof member classification via the index `host` field (353).

**Construction documents** — D5 PDF detail callouts + real sheet refs (354); W10-6 room-schedule
`IfcElementQuantity` depth (356); **compiled drawing-set PDF** — the whole set in one file (375);
**shareable project package** PDF — overview + drawings + cost + proforma (377).

**MEP / structural** — W10-4 MEP design flow-rate psets (355); **W10-7 structural analytical model** —
`IfcStructuralAnalysisModel` from the frame (curve members, 357) + surface members from slabs (358).

**RFI-0 / W9-4** — the **document/specification graph** + cited element provenance (359) and the
**NL-QA** cited-answer layer (360).

**COLLAB-1 real-time co-editing** — model-edit SSE stream + presence snapshot (361), optimistic edit-lock
(362), the viewer presence + reload-banner wiring (366).

**AUTH-VS visual node authoring** — the recipe-graph execution engine (363) + the draggable node canvas
(367).

**Web client + designer-workspace UX** — typed client bridge to the new engines (364); the Ask-the-model
box + structural-analytical panel (365); UX-3 Library search operators + Recent (368); UX-4
Project-Browser spine (369); UX-1 lifecycle ribbon tabs (370).

**Reliability / security / relationships** — security hardening pass (XXE-safe P6 parser, non-crypto hash
flags, pillow pin, clean audit — 371); openModule O(n·m)→Map + import-cycle false-positive verification
(373); **model estimate → developer proforma** hard-cost sync (376). Docs refreshed to v0.3.372.

---

## ★ Recent releases — v0.3.313–335 (discipline tree · UX-2 annotation · MEP-FP · CODE-EBC)

Moved out of the working roadmap so it holds only open items.

**🗂 DISC — unified discipline tree (v0.3.330–335).** One CSI-MasterFormat/UniFormat/NCS vocabulary + colour
palette across the viewer, model browser, estimate, and both packages.
- **DISC-1 (v0.3.330)** — canonical `DISCIPLINE_COLORS` + `discipline_color()` (fire=red…telecom=purple; FA
  swatch distinct from FP); full IFC-class→discipline coverage (`_IFC_DISCIPLINE`) for MEP/fire/electrical/
  telecom entities the MasterFormat map missed; `discipline_tree()` (colour + divisions + uniformat + sheet
  series + rolled-up IFC classes + `ifc_class_discipline`), served on `GET /reference/disciplines`.
- **DISC-2 (v0.3.331)** — a **Color by** toggle (IFC class ↔ Discipline) on the IFC-classes panel + a legend
  of disciplines present + a **Paint model** button; `tree.ts` consumes the served map (`setDisciplineLookup`)
  instead of its regex; rebar/mesh/tendon → Structural.
- **DISC-3a (v0.3.334)** — `estimate.by_discipline` (really per-IFC-class) now tags each priced line with its
  discipline + adds a true `by_discipline_rollup`; per-class detail kept as `by_class`.
- **DISC-3b (v0.3.335)** — new `aec_data/disciplines.py` holds the canonical `MF_DIVISIONS` + colour palette;
  `classification.py` imports them (drops copies) and `specmanual` drops its duplicate `_DIVISIONS` — one
  source across both packages (aec_api can import aec_data, not vice-versa).
- **DISC-4a (v0.3.332)** — `add_fa_device` (smoke/heat detector `IfcSensor`; pull-station/horn-strobe/bell/FACP
  `IfcAlarm`) on a **Fire Alarm** system; `add_comms_device` (MDF/IDF/switch/WAP `IfcCommunicationsAppliance`,
  data outlet `IfcOutlet`) on a **Telecommunications** system.
- **DISC-4b (v0.3.333)** — 🔔 Fire-alarm + 📶 Telecom tool buttons; demo tower rebuilt with a unitized
  `IfcCurtainWall` facade, 286 fire-rated walls (2-hr core / 1-hr demising), an `IfcRoof` assembly, 90
  detectors + 61 alarm devices, 37 telecom devices — all 8 disciplines colored distinctly.

**🏷 UX-2 — interactive annotation (v0.3.323–328).** `add_annotation` text notes (v0.3.323) · `add_dimension`
two-click dimensions (v0.3.324) · `add_revision_cloud` + **plan rendering of view-placed annotations**
(v0.3.327) · `add_tag` element-aware tags auto-read from the host, assigned via `IfcRelAssignsToProduct`
(v0.3.328). Closed the author→sheet loop the baked-SVG path couldn't.

**🧯 MEP-FP — fire protection as a first-class system (v0.3.311–319).** Discipline via `PredefinedType` +
`add_mep_*` discipline arg + `set_system_predefined` (v0.3.311) · `add_fire_equipment` sprinkler/hose-reel/FDC/
hydrant/pump (v0.3.315) · NFPA-13 `sprinkler_coverage` pre-check (v0.3.316) · `add_riser` vertical standpipes/
stacks/vents (v0.3.319).

**Other v0.3.313–329.** CODE-EBC IEBC Work-Area classifier (v0.3.310) · RFI-0→BCF decision-readiness promotion
(v0.3.313) · EST-1 material/equipment `full_estimate` (v0.3.314) · CONTENT-1 mesh import + auto-classify
(v0.3.321) · A4 LLM scene-digest (v0.3.322) · G3 O&M/warranty doc refs (v0.3.318) · the `open_model` stale-cache
fix keyed by (path, mtime, size) (v0.3.325) · QTO length derivation so linear MEP/railing prices non-zero
(v0.3.329) · Capacitor 6→7 clearing the tar CVEs (v0.3.312).

---

## ★ Current initiative — Code quality & hardening (2026-07)

From a four-domain, file-grounded audit (Python architecture · Python performance/correctness ·
TypeScript · Rust/build-CI). The core is mature; this closes the specific remaining gaps and finishes
half-rolled-out patterns. Delivered as ordinary versioned, CI-green releases, safety-net first.
Full proposal (ranked, with file evidence): https://claude.ai/code/artifact/aabdff8f-e331-4f91-8961-09d0394be4d5

### ✅ Shipped — Waves 1–6 (v0.3.177–191)
- **Wave 1 — Observability (v0.3.177).** O1 server error-log feed (global 500 handler + request-id →
  `error_log` + admin `/admin/errors`, retention-capped) · O2 client-side capture + admin **Errors** panel.
- **Wave 2 — Perf quick-wins (v0.3.178).** P1 `scan_deviation` threadpool · P2 model-keyed `_scan_cached`
  · P5a `(project_id, ts)` index · P5b property-index lock.
- **Wave 3 — Scale (v0.3.179).** P3 `wip.portfolio()` N+1 → `sum_field` SQL aggregate · P4 dashboard/
  schedule routers off `list_records(limit=1e6)` → `count_records`/`func.sum`.
- **Wave 4 — Type boundary (v0.3.181, 190).** T1 OpenAPI-generated TS types (`openapi-typescript` →
  `schema.d.ts` + `openapiTypes.ts` seam) · T4 typed `ui/dom.ts` (`el()/frag()/clear()/readForm<T>()`)
  + Vitest suite.
- **Wave 5 — Modularization (v0.3.181, 186–189).** A1 `model_index.py` extraction (fixed the 5-engine
  dep inversion) · A2 `reports.py` 1,436 → 176-line dispatch + `report_builders/` package · A3 shared
  `deps.open_source_ifc()` · T2 `ApiClient` transport → `httpCore.ts` (`HttpCore`) · T3 portal
  favorites/recents/persona-sections → `portal/prefs.ts`.
- **Wave 6 — Reproducibility + ops (v0.3.182–185, 191).** B1 single-source fragments/web-ifc pair +
  CI guard · B4 converter CLI output-guard + Dependabot `directory:/` · O3 fail-closed prod secrets
  (`${VAR:?}`) · O4 Rust `clippy`/`fmt` PR CI (`rust-ci.yml`) + Trivy (CRITICAL gate + non-blocking HIGH
  report) · P6 `Decimal` money helpers (`money.py`: `q2`/`to_cents`/`allocate`).
- **Wave 7 — Strictness + Docker hardening (v0.3.193–195).** T5 `noUncheckedIndexedAccess` ON + **251
  real guards** across 25 files (no blind `!`; 34 justified `// safe:`; caught real latent crashes —
  empty-selection index, malformed frag pairs, `selectedIndex -1`, unknown-role rank, malformed
  GeoJSON/GeoTIFF) · T6 type-aware ESLint scoped to `no-floating-promises` (45 unhandled-promise fixes)
  + `no-misused-promises` (`checksVoidReturn:false`) · B3 API image multi-stage (build toolchain stays
  in `pybuild`, **no compiler in the runtime**) + web `npm ci` on the workspace lockfile + root
  `.dockerignore`; dropped the vestigial `packages/shared-types` phantom workspace.

---

## ☆ Wave 8 — 2026 field-research upgrades (6 of 7 SHIPPED, v0.3.203–210)

> **Status:** ① clash-coordination intelligence (v0.3.203) · ② model→field layout (v0.3.204) · ④ load
> takedown (v0.3.205) · ⑤ model hygiene (v0.3.206) · ⑥ CEP generator (v0.3.207) · ③(a) Gaussian-splat
> reality capture (v0.3.208) · ③(b) verified-as-built progress (v0.3.210) — **all shipped.** Only ⑦
> (compliant syndication) is open, and it is **deferred by decision to a licensed-platform connector**
> (see the top "What's left" section). The per-track detail below is retained for reference.

**Field scan #2 — coverage validation (pics8, 2026-07).** A second 11-image industry-reference scan (LOD
100–500 ×3, IFC-vs-Shop-vs-As-Built drawings, PMBOK PM domains, the BIM 3D→7D master guide, the PM
strategy→benefits delivery workflow ×2, "one model, every discipline", the clash-resolution workflow, and
the 10-part CEP) was reviewed for new opportunities. **Result: no new tracks — every theme already ships**
(LOD matrix; submittals/drawing-set/as-built + verified-as-built; risk/stakeholder/quality/cost/schedule/
procurement/closeout; all 7 BIM dimensions incl. 5D cost + 6D carbon/ESG + 7D CMMS/twin; project-health +
portfolio; discipline spine + federation; Wave 8 ① clash coordination; Wave 8 ⑥ CEP). Shop drawings are
covered as a `submittal` type ("Shop Drawing"). The one micro-observation — **FF&E / furnishings** — was
folded in additively (v0.3.212): the furnishing IFC classes now classify to MasterFormat Division 12, so
FF&E takes off and procures correctly without a risky discipline-taxonomy change. Otherwise this scan is a
confirmation that platform breadth matches the reference material, not a backlog addition.

Sourced from a July-2026 field scan: 14 industry reference sheets (structural loads, LOD, BuiltWorlds
Robotics Top-50, PMO/EPMO, BIM Control Stack, Revit-mistakes, ISO-19650 delivery, a 4-part clash
workflow, planning-vs-controlling, a 10-part construction-execution plan) + three build briefs
(reality-capture→IFC twin; two real-estate-tokenization roadmaps) + VIM (vimaec.com) and a Revit-MCP
automation portfolio. Each track below was validated against **institutional references** and its
dependency licenses verified against our permissive mandate (no AGPL/GPL in the core). Ordered by
leverage. These **deepen existing seams** (clash+BCF, deviation heatmap, `structure.py`, report-gen,
cap-table) — none is a rebuild.

**① Clash Coordination Intelligence — the management layer on top of detection (highest leverage).**
The strongest signal (4 of the 14 sheets walk detect → filter/dedup → assign/resolve → validate/close).
We already *detect* federated clashes + import clash XLSX + speak BCF; the gap is the **coordination
workflow**. The proven industry pattern (model-coordination platforms + the buildingSMART BCF
standard): a **two-layer model** — ephemeral `Clash` rows (thousands, regenerated per run) vs persistent
`Issue` = one **BCF Topic** (tens). Build: (a) **grouping** — by-element set-cover + `DBSCAN` proximity +
grid/level bucketing → the industry's ~10:1–100:1 reduction; (b) **tolerance/matrix** — hard vs
soft/clearance + a discipline **clash matrix** (which pairs to test, per-cell severity) as the primary
false-positive control (research shows ~30–60 % of raw clashes are noise); (c) **severity score**
(matrix × penetration depth × group size × structural flag); (d) an **assign→in-progress→closed /
reopened** state machine mapped 1:1 to BCF `TopicStatus`; (e) a **stable `clash_hash`** (sorted GUID pair
+ snapped point) so re-runs auto-set *Resolved* / auto-*ReOpen* on reappearance without losing comments;
(f) **clash KPIs** (open/closed, aging, by-trade-pair, reappearance rate, burn-down). Pure Python over
our existing clash + `bcf_io.py`; GUID-keyed; zero license exposure.

**② Model → Field layout + verified as-built (smallest surface, immediate field utility).**
The BuiltWorlds Robotics-Top-50 sheet points at the 2026 field-robotics wave (floor-printing robots,
layout/drilling robots, robotic total stations). They all consume two open primitives from the model:
a **PENZD/PNEZD points CSV** (Point-№, Easting, Northing, Z, Description) and **DXF linework** (for floor
printers). Build a **`model → layout CSV`** exporter (grid intersections from `IfcGrid`, wall control
lines, MEP hanger/anchor points, sleeve/penetration centroids, column setout — Description encodes type +
IFC GlobalId; real-world E/N/Z via our set-origin handling) and a **`model → DXF`** layered drawing
(`ezdxf`, MIT). Close the loop: import measured total-station shots, match by Point-№/GUID, and write a
**BCF topic per out-of-tolerance point** — as-built verification becomes another BCF type on our existing
pin/RFI spine. Monetizes "IFC as the source of truth"; no new heavy deps.

**③ Reality walkthrough + schedule-linked verified-as-built (high visual differentiation).**
**Part (a) SHIPPED v0.3.208.** From the `photosynth-to-massing` brief. Two parts: (a) a **3D Gaussian-splat
"reality" layer** in the viewer — photoreal, phone-captured, co-registered with the IFC + LAS/LAZ we
already load; delivered via `@mkkellogg/gaussian-splats-3d` (MIT), lazy-loaded as its own chunk (out of
the app-shell bundle), offline (bundled inline sort worker, in-memory object URL — no CDN), routed through
the existing reference-overlay flow (`.splat` / `.ksplat`, plus splat-PLY content detection) with worker
teardown on removal; the permissive capture path is `gsplat`/Nerfstudio (Apache-2.0) — *avoid the original
Inria 3DGS (non-commercial)*. **Part (b) SHIPPED v0.3.210** — `field_verification` module (per-element,
GlobalId-anchored, workflow = verification state) + `verified_progress.py` roll element verification up to
each schedule activity as **verified-in-place % vs claimed %** with the **trust gap** (the OpenSpace /
Disperse / Buildots value proposition, pure software for us); `seed_from_layout` turns an as-installed
`layout.verify` result into verification records; viewer tool + Report Center report. Original brief:
Turn our **deviation heatmap into progress** — per-element capture/verification state + % complete tied
to schedule tasks. Add **E57 polish** on the
existing `e57.py`. Automated point-cloud→IFC (**Cloud2BIM is GPL-3.0**) stays an optional *out-of-process*
converter, never linked into the core.

**④ Preliminary gravity load takedown + ASCE 7 combinations (design-phase depth).**
The "Types of loads" sheet. Extend `structure.py` (today: system *recommendation* only) with a
**tributary-area gravity takedown** — dead (self-weight from `IfcMaterial` × geometry + SDL) + live (ASCE
7 Table 4.3-1 by `IfcSpace` occupancy, with the §4.7 live-load-reduction closed form) distributed by
tributary geometry and **accumulated storey-by-storey down each column line to the footings** — plus an
**ASCE 7 load-combination engine** (LRFD §2.3 + ASD §2.4; the coefficients are facts). Output per-column /
per-footing service + factored axial loads for preliminary sizing. **No FEA, no solver** — pure
`ifcopenshell` + arithmetic; optional **PyNite (MIT)** / **sectionproperties (MIT)** tier later for
continuous-member checks (**avoid anaStruct — LGPL-3.0**). Ships with the same PE/RA honesty caveat as our
stamp/seal path: *preliminary coordination estimate, not a substitute for a licensed engineer; lateral
(wind/seismic) out of scope*.

**⑤ Model-hygiene checker (quick win). — SHIPPED v0.3.206.** The "Common Revit mistakes" sheet + the
Revit-MCP portfolio's *Model Checker / Duplicates Resolver*. `model_qa.py` now covers **geometric
hygiene**: duplicate GUIDs, overlapping duplicate elements, orphaned elements, unenclosed rooms/spaces,
blank names, and (new) **elements on the wrong storey** — GUID-anchored, guarded, scored, feeding the
Model-QA report/BCF issues.

**⑥ Construction Execution Plan (CEP) generator. — SHIPPED v0.3.207.** The 10-part "How to prepare a CEP"
sheet. `_cep` report builder assembles a 10-section CEP (org/RACI · scope/WBS · master schedule &
milestones · procurement/subs · cost & change control · safety · quality · submittal/RFI procedures ·
permits · closeout/turnover) live from the construction modules + summary engines, PDF/Excel via the
existing report stack, auto-surfaced in the Report Center (group *Quality*). ISO 21502 / CMAA practice
areas paraphrased in original prose. A CEP is the
*superset* of a BEP (the BEP governs the model; the CEP governs the work). We already hold the data:
section-templated generator (scope · stakeholder/RACI · site logistics · work packaging/pull-plan ·
resources · cost/schedule/risk + EVM · quality/ITP · HSE/resilience · procurement/subs · commissioning/
COBie-G704) auto-populated from existing modules, BEP linked as an appendix (not duplicated). Reuse the
report/PDF stack; cite ISO 21502 / CMAA practice areas in original prose (no copyrighted text, no
competitor names).

**⑦ Compliant syndication / investor-management depth — cap-table-first, token-last (strategic, legal-gated).**
From the two tokenization briefs. The validated best practice across regulated securities platforms and
the non-token fund-administration gold standards: a securities platform is **~80 % a regulated
investor-management system, ~20 % blockchain** — Postgres is the legal source of truth, the token an
optional mirror. We already have proforma, JV waterfall, LP portal, capital calls, cap-table.

**DECISION (revised) — integrate, don't build.** We will **not** build the securities/compliance stack
ourselves (KYC/accreditation, transfer-agent recordkeeping, Reg-D compliance engine, escrow, the token) —
that is licensed, counsel-gated, multi-year work and outside our risk appetite. Instead Massing stays the
**origination front-end** (the deal, the IFC model, the proforma, the JV waterfall, a read-only cap-table
view) and **hands the regulated pieces to a licensed platform via API** — the same "connectors OK, we
never move money" posture as our Procore / QuickBooks bridges. Confirmed integration path: **a licensed
securities platform** — an SEC-registered **transfer agent + broker-dealer/ATS** — exposing a **partner
connect API**, a **RESTful KYC/KYB/AML identity service**, and **Transfer-Agent-as-a-Service**; for the
non-token fund-admin route, hand off to a fund administrator (data export / referral). So the buildable work shrinks to a
**thin connector** (`connectors.py` already has the pattern): push deal + investor + distribution data to
the partner, pull back verified-KYC / holder-of-record status, deep-link investors into the partner's
onboarding, and show the partner's cap-table state in the LP portal. The token (ERC-3643) is the
partner's concern, not ours; its T-REX reference being **GPL-3.0** is now moot for us. ⚖️ *Not legal
advice; the partner is the licensed entity.*

**Sequencing recommendation:** ① and ② are the near-term, highest-leverage, lowest-risk builds (both pure
software on existing seams). ③–⑥ are self-contained increments to schedule by customer pull. ⑦ is now a
**lightweight integration** (a licensed-securities-platform connector) rather than a build — pursue only
when a customer needs to actually raise/syndicate, and keep Massing out of the regulated path entirely.

---

<!-- ═══════════════════════════ SHIPPED ARCHIVE (historical reference) ═══════════════════════════ -->
## Authoring depth + the design engine — ✅ SHIPPED (v0.3.87–88+)

Sourced from a competitive/practice scan (18 industry reference sheets on BEP / LOD / BIM roles /
Revit MEP plant rooms / naming conventions / P6 scheduling / envelope assemblies / construction-tech
M&A) plus two products: **Higharc Studio** (AI-native generative home design — live model → 2D/BIM
auto-propagate, options/variants in one model, rules-based standards) and **ifc-lite** (LTplus-AG,
Rust+WASM browser IFC toolkit — columnar/DuckDB analytics, IFC5/IFCX, broad export). The scan confirmed
we already cover ~80% of professional BIM/PM practice; the real gaps are authoring depth, MEP/schedule
engineering depth, and Higharc-style live-design/options. Do **Phase A then Phase B**, sequentially.

**Phase A — openBIM authoring depth** (SHIPPED v0.3.87–88):
- **A1 — BEP document generator.** Compose a full ISO 19650 **BIM Execution Plan** PDF from the existing
  CDE / EIR / AIR / roles / LOIN / naming registers (objectives, roles-&-responsibilities matrix,
  LOD/LOIN table, information-exchange schedule, naming standards, model-coordination process, QA,
  deliverables). New `reports` builder — inputs already stored.
- **A2 — LOD matrix + element-level LOD.** A `lod_target` register (phase × discipline × element-category
  → LOD 100–500) + validate model elements against target; surface in the openBIM quality scorecard.
- **A3 — Naming-convention validator + document register.** Configurable metadata pattern
  (`DocType_Discipline_Description_Rev_Date`), validate drawing/upload names, master-folder structure in
  the CDE.

**Phase B — the design engine** (SHIPPED v0.3.89; Higharc-inspired):
- **B1 — Design options / variants.** A project carries N schemes; compare area / cost / energy / returns
  across them; promote one to "current." Extends test-fit scheme-compare to the whole project.
- **B2 — Live 2D propagation.** Make the 2D plan/section/elevation generator option-aware and re-run on
  model change (2D generation exists — make it *live-linked*).
- **B3 — Standards ruleset.** Allowed assemblies / materials / product selections the generator + in-viewer
  authoring honor.

**Later phases (backlog, not yet scheduled):**
- **C — engineering depth (SHIPPED v0.3.90):** MEP equipment schedules + pipe/duct sizing + load-calc→
  tonnage + hanger spacing + per-system summaries (extends D5 parametric MEP); resource-loaded scheduling
  + histograms + S-curve + over-allocation.
- **D — interoperability & analytics (SHIPPED v0.3.91; ifc-lite-inspired):** model analytics query layer
  (group-by + count/sum over the property index, saved views); data export (CSV + JSON-LD; Parquet/glTF
  future); envelope code-compliance checker (assembly R/U vs IECC 2021 climate-zone minimums); IFC5/IFCX
  read-path readiness (watch-item — lands when web-ifc/Fragments support arrives).
- **E — field AI (SHIPPED v0.3.92):** field labor-productivity analytics (units/man-hour by trade);
  computer-vision % complete as a feature-flagged external bridge (AEC_CV_BRIDGE — fabricates nothing
  when off).

**Initiative complete (v0.3.87–v0.3.92):** Phases A–D shipped as full features; Phase E shipped
(productivity real + CV as a documented bridge).

**Deferred slices closed (v0.3.95):** the five items previously scoped as needing a dependency / external
service / upstream support are now shipped as far as each honestly can be — **Parquet** export (`pyarrow`;
`/model/export.parquet`); **glTF 2.0** geometry export (`ifcopenshell.geom` triangulation, per-class
meshes, `/model/export.gltf`); the **CV bridge end-to-end** (id-or-name resolution + batch ingest +
[reference adapter](cv-bridge.md), still externally-modelled by design); **live 2D propagation** (model-version
bump + `/drawings/stream` SSE, Redis-shared across workers via `AEC_REDIS_URL`, fail-open to in-process);
and **IFC5/IFCX/ifcJSON data reads** (tolerant
JSON→element-index parser; geometry rendering still lands upstream). Genuinely upstream-only remainder: IFC5
geometry *rendering* (web-ifc/Fragments) and a bundled/trained CV model.

**Earned Value Management — research-backed EVM module (SHIPPED E1–E7, v0.3.109+):** the app had
two disconnected halves (schedule EV without Actual Cost; cost actuals by cost code with a heuristic
forecast). `evm.py` joins them **by cost code (control account)** into one ANSI/EIA-748-aligned set:
PV/EV/AC/BAC, CV/SV/CPI/SPI + bands, per-control-account table, and the EAC/ETC/VAC/TCPI **forecast
family** (best EAC is stage-dependent per the construction-forecasting research, so all are shown).
Sequence: **E1+E2** engine+forecast (v0.3.109) → **E3** Earned Schedule shipped (ES/SV(t)/SPI(t)/IEAC(t) →
forecast finish; fixes the SPI→1.0 tail defect) → **E4+E5** shipped: 3-line S-curve + 📊 Earned Value dashboard + upgraded report
dashboard/report → **E6** EV measurement methods (0/100, 50/50, units-complete, milestone, LOE) + split
installed vs billed/stored/retained EV → **E7** shipped: model-based EV (installed-elements % × BAC from field verification — the
differentiator over P6/Procore-style EVM) + stage-adaptive forecast + earned duration.

**Model authoring — true model-creation program (SHIPPED P0–P6, v0.3.102+):** upgrading the Model
workspace from shallow prompt-driven placement into a real drafting tool with a full BIM family library.
Architecture (research-confirmed): the **browser captures intent** (family + parameters + placement),
the **server authors real IFC** via `ifcopenshell.api` (source of truth), and re-streams fragments — no
browser CAD kernel (ThatOpen Fragments editing can't create elements/write IFC). No permissive pre-built
IFC family catalog exists, so families are **generated procedurally**, seeded from permissive sources
(buildingSMART Community-Sample-Test-Files CC-BY-4.0, re-keyed AISC/Eurocode profile tables, bSDD for
Uniclass/OmniClass + Psets). Sequence: **P0 Draft panel** (`viewer/draft/`, parametric palette + named
params, v0.3.102) → **P1** grid + levels drafting refs (`grid.py` IfcGrid/derived reader + snap +
editable-storey recipes + Grid & Levels panel, v0.3.103) → **P4** structural (steel.py AISC W-shapes as
native IfcIShapeProfileDef + rebar IfcReinforcingBar + IfcFooting, v0.3.104) → **P5** MEP (duct/pipe/
cable-carrier/cable runs w/ ports + IfcDistributionSystem + point equipment: panel/outlet/light/
diffuser/drain/fixture/alarm/sensor/comms, v0.3.105) → **P3** architectural (IfcCovering
ceiling/tile/wood/cladding + IfcRailing, v0.3.106) → **P6** draft perf — optimistic local proxy
(v0.3.107) **+ incremental one-element preview fragment** (`preview.py` + `/edit-preview`, v0.3.108) so
real geometry appears without the whole-model reconvert; plus **MEP fittings** (elbows/tees). **Complete
(P0–P6):** the Draft palette spans all three disciplines with grid/level snapping and instant real-
geometry feedback. Follow-ups if wanted: element property editor (structured Pset editing) +
classification (Uniclass/OmniClass via bSDD) tagging. Earlier placeholder: **P4-cont/**
structural (steel parametric profiles + rebar) → **P5** MEP (duct/pipe runs, electrical, fire/telecom) →
**P3** architectural (coverings/ceilings/tile/wood) → **P6** draft perf (optimistic + incremental
fragments); standards (PredefinedType + classification + Psets at the type level) woven throughout.

**Market intelligence + concept-render bridge (v0.3.101):** from an industry-research pass. A regional
market table (escalation % · labour US$/hr · location index) + a two-speed warm/cold sector signal
(`market_intelligence.py` + `market_assumption` module + `/market/*` + 💹 panel), escalating a base cost
to the **construction midpoint** by region — feeding the conceptual estimate's new market block + a
report. Seed defaults are public T&T GCMI 2026 headline figures (editable, [attributed](ATTRIBUTIONS.md)).
Plus a feature-flagged **AI concept-render bridge** (`render_bridge.py` + `concept_render` module +
🖼 panel, `AEC_RENDER_BRIDGE` off by default): grounds a prompt from the program/massing, ingests returned
images as reviewable records, fabricates nothing when off ([docs/render-bridge.md](render-bridge.md)).

**Code-audit follow-through (v0.3.98–v0.3.100):** a four-dimension audit (backend wiring, UI/UX, sample
data, performance) found the platform structurally clean (46/46 routers, 47/47 reports, 32/32 module
refs). Shipped in three batches + the two deferred items: perf quick-wins (`count_records`, off-loop index
upload, docmanager `tree()` hoist), Documents a11y/responsive + role/phase-gap views, surfaced the
columnar/VIM/STEP analytics, a populated Pages demo (seeded model → Model Analysis + Document Control,
~826 fixtures), a **per-model-version scan cache** (Redis-shared across workers, fail-open) for the hot
colour-by/facets scans, **gzipped colour-by** (+ compact `ids=false`), and a windowed portfolio scenario
query. Audit fully closed.

**Ara3D-inspired efficiency (G1–G3, v0.3.97):** columnar/string-interned property index + EAV Parquet
export for DuckDB analytics (`bim_columns.py`, from Ara3D BimOpenSchema); pure-Python BFAST/G3D/VIM reader
(`aec_data/bfast.py`) opening `.vim`/`.g3d` offline; a fast streaming STEP metadata/entity-histogram scan
(`aec_data/step_scan.py`) with no full parse. MIT-attributed ([ATTRIBUTIONS](ATTRIBUTIONS.md)); the rest
of the Ara3D SDK (geometry/SIMD/collections) was intentionally not ported — numpy/scipy/trimesh already
cover it. Reviewed OpenAEC-BIM-validator: no integration needed (we already do ifctester IDS validation +
BCF).

**Document Control (F1–F6, v0.3.96):** a role-based standard file manager — a fixed project folder
taxonomy (`01_Contract Documents … 11_Final Account`) with each folder owned by a role (PM = business,
Superintendent = field, Architect/Engineer = drawings), ISO 19650 CDE state, and required flags; a
document manager over object storage that auto-names uploads to the information standard and supersedes
(never overwrites) revisions; an elFinder-style two-pane Documents panel; a Document-Control health report
+ AIA phase-gap checks. Reuses the discipline spine, CDE states, naming validator and storage backend.

**Strategic read:** the construction-tech trend is platform consolidation + AI agents + connected
ecosystems + interoperability (ongoing industry M&A). Our open, IFC-native, self-hosted, one-model
posture with an MCP server for AI agents + connectors is well-aligned — lean into interoperability
(import/export breadth) and AI-over-the-model.

---

## Active plan (sequenced) — ✅ SHIPPED archive

User-directed sequence (historical, as of v0.2.8; superseded by later themes below — latest **v0.3.86**).
Carry this out in order; each item ships as its own release.

1. **Real-estate / capital depth**
   - [x] WPRealWise / MLS listing syndication bridge + marketing flyer (`re_bridge.py`) — **v0.2.8**
   - [x] Lease-management depth — renewals, rent escalations, CAM reconciliation (`leasemgmt.py`) — **v0.2.9**
   - [x] Equity waterfall / distribution scenario modeling (`distwaterfall.py`) — **v0.2.10**
   - [x] Investor-portal document sharing (signed statement links via `signing.py`) — **v0.2.11**
   - [x] Comps-import automation (bulk CSV / RESO → `comparable`, `comps.py`) — **v0.2.12** ✅ phase complete
2. [x] **Polish & harden existing** — empty-project robustness (regression-locked), malformed-input
   safety, waterfall no-investor guard, a11y labels on new inputs — **v0.2.13**.
3. [x] **Production / ops** — non-root API container + `/metrics` test — **v0.2.14**; backup/restore
   runbook, healthchecks + depends-on conditions, rate-limit env knobs, Caddy HTTPS overlay already shipped.

Construction-depth analytics (the prior theme) shipped fully in v0.2.0–v0.2.7 (6-log suite,
closeout dashboard, executive project-health rollup, e-sign bridge, E57 import, GIS basemaps,
field-capture PWA).

---

## Shipped (highlights)
- **Viewer** — Three.js + Fragments, offline WASM; tree/layers/isolate/section/measure; federation;
  clash (AABB + mesh boolean → BCF); IDS validation; 2D plans/sections/elevations + PDF sheets.
- **Authoring round-trip** — server-side `ifcopenshell` recipes (walls/slabs/columns/beams/roofs,
  openings, edit/move/copy, Pset) → background republish; GUID-stable. Family/type library.
- **Generative massing** — zoning envelope → massing + structural frame + per-unit spaces + envelope
  (facade + windows) + service core (elevator/stair/MEP risers), one click. (Test Fit extends this — §A.)
- **GC portal** — config-driven modules (RFIs, submittals, CO chain, daily, QA, safety, closeout…),
  role-gated workflow, relations/rollups, kanban, search, pay apps (G702/G703), CPM, bid leveling,
  dashboards, **field capture** (offline photo→record), module-log PDFs, closeout package ZIP.
- **Developer/finance** — proforma (S&U w/ interest reserve, XIRR/NPV/EM, JV waterfall, sensitivity,
  Monte Carlo), **line-item hard/soft cost budgets**, **specialty assets** (on-site energy +
  vertical-farm/PFAL revenue), **investment-memo PDF**, model→proforma seeding.
- **AI** — "Ask AI" over a live project snapshot; AI risk summary; AI-drafted RFIs.
- **Platform** — SSO (Google/Microsoft/Procore), no-admin model, onboarding + tour, connectors
  (Procore/ACC/QuickBooks/Sage/Viewpoint/SQL), PWA + signed auto-updating desktop app, rate limiting,
  security headers, takeoff caching. Full lifecycle verified acquisition→turnover (E2E 63/63).

---

## A. Model generation & **Test Fit**  — archive / parking-lot
We have generative *massing*; Test Fit is the optimization layer above it — making the program
actually **fit** the site/floor-plate and **optimizing yield**, with side-by-side scenarios. Our
edge stays IFC-native (every fit is real openBIM, flowing into drawings/QTO/estimate/proforma).
Grounded in [TestFit Site Solver](https://www.testfit.io/product/site-solver),
[Parking Solver](https://www.testfit.io/product/parking-solver),
[Generative Design](https://www.testfit.io/blog/unleash-boundless-building-optimization-with-testfit-generative-design).

- ✅ **DONE — generative massing** (zoning → massing/frame/units/envelope/core).
- ✅ **DONE — A1 unit-mix configurator + corridor layout.** `test_fit.layout()` tiles a unit mix on a
  double-loaded corridor (units both sides) → placed rects + yield; `generate_ifc(unit_layout=
  "corridor")` builds real corridor + unit IfcSpaces. "Double-loaded corridor" toggle on the form.
- ✅ **DONE — A3 parking (lite) + A4 yield compare.** `test_fit.parking()` (stalls/unit ratio →
  count/area/cost) and `compare()` rank schemes; `POST /test-fit/compare` + a "📐 Test Fit" Finance
  panel (units/efficiency/avg-SF/NSF/stalls, best ★). *Next: parking as real IFC geometry, egress.*
> **A-theme status (reconciled 2026-06):** A1/A3/A4/A5/A6 are **done** (see the ✅ entries); the
> egress *analysis* (occupant load · travel · exits · separation), **parking as real IFC geometry**,
> and the **polygon-offset footprint** all shipped in the Test-Fit-depth pass. The bracketed entries
> below are the *original* aspirational specs kept for reference — only two pieces remain genuinely
> open: **(A1b)** named unit-*type* presets (studio/1BR/2BR target-SF + mix) you can save/load, and
> **(A2-geometry)** auto-*placing* code-positioned egress **geometry** (corridors/stairs/elevators as
> IFC, not just the pass/fail check). Both are deeper generative-design work, not blockers.
- ✅ **DONE — A1b unit-type presets.** The Test Fit panel has a **custom unit-mix editor** (add/remove
  types with name · target SF · mix %, saved to localStorage); "Compare schemes" sends it with
  `with_defaults` so **your mix is ranked against the presets**. **The Test Fit A-theme is now fully
  complete (A1–A6 + egress check + egress geometry).**
- ✅ **DONE — A2 egress geometry.** `generate_ifc(core=True)` now places **two means of egress
  positioned for code** — the core stair plus a second **"Egress stair 2"** at the opposite corner
  (≥⅓-diagonal remoteness, IBC 1007.1.1) — alongside the elevator + MEP risers, on the double-loaded
  corridor. (The egress pass/fail *check* was already in `test_fit.egress`.) *Remaining ref:* A1b
  unit-type presets.
- ✅ **DONE — A3/A4 parking + yield compare** (parking lite + real IFC stalls; `compare()` ranks fits).
- ✅ **DONE — A5 generative design (targets).** `test_fit.optimize()` sweeps unit-mix × parking
  presets, scores yield-on-cost, filters by targets (units/efficiency/parking/YoC), ranks. `POST
  /test-fit/optimize` + "⚡ Optimize" button. *Next: tie YoC to the live proforma vs the proxy.*
- ✅ **DONE — A6 (lite) real lot polygons.** `compute_massing(lot_polygon=[[x,y],…])` — shoelace
  area drives the program (L-shaped parcels yield less than their bbox). *Next: true polygon-offset
  footprint + parking/drive-aisle placement on the parcel.*

## B. Developer / finance portal
Grounded in an institutional model (M. Emma thesis) + CRE practice (hard 70–80% / soft 20–30%,
contingency 5–10%; Uses = Acquisition + Hard + Soft + Financing; Sources = Debt + Equity).
- ✅ **DONE — B1 line-item hard/soft cost budgets** (`dev_budget.py`, Finance budget panel).
- ✅ **DONE — B4 specialty assets** (energy + vertical-farm revenue → capex/revenue/opex).
- ✅ **DONE — B5 investment memo PDF** ("presentation with financials").
- ✅ **DONE — B2 Sources & Uses (first-class view)** (`proforma/sources_uses.py`, `solve_sources_uses`).
  Grouped Uses (cost budget + acquisition + financing) vs Sources (senior debt sized by
  LTC/LTV/DSCR/debt-yield, mezz, LP/GP equity); per-period draw spread feeding interest reserve.
- ✅ **DONE — B3 property & tax assumptions.** `dev_property.py` + GET/PUT `/projects/{id}/property`
  + "🏢 Property & tax" Finance panel: parcel/areas/purchase + tax table (school/county/town/fire →
  total) → OPEX, purchase → acquisition line; per-SF ratios. ✅ **DONE — appraisal/market comps** (see B7).
- **B6 — Pitch-deck variant** of the memo (10–20 slides) + market/timeline sections, photos.
- ✅ **DONE — B7 disposition & marketing kit** (v0.1.86). A RESO-aligned `listing` config module that
  **auto-fills from the model + proforma** (`marketing.py`), a BIM-native **Listing Fact Sheet PDF** +
  a **signed public listing link/QR** (read-only — market a building off-plan), and a **RESO Data
  Dictionary** export seam. `GET /listings/autofill`, `POST /listings/{lid}/share`, `GET
  /listings/{lid}/public`, `GET /listings/{lid}/reso`. See [realestate-marketing.md](realestate-marketing.md).
- ✅ **DONE — B8 tri-approach appraisal** (v0.1.86). `appraisal.py` values the asset three ways —
  **cost + income + sales-comparison** (with comps) — and **reconciles** them into a final value;
  surfaced as a **Valuation** tab in Finance with a **Valuation report (PDF/Excel)**. `GET|POST
  /projects/{id}/appraisal`. See [realestate-marketing.md](realestate-marketing.md).

## U. Underwriting realism  — archive / parking-lot
The engine solves the math correctly, but it accepts un-risk-adjusted inputs — e.g. feeding
specialty *operating* revenue (a farm/energy business) straight in as if it were de-risked rent
produced an implausible ~71% IRR in the vertical-farm E2E. "Real underwriting" adds the discipline,
defaults, and guardrails that make the IRR credible. Grounded in CRE practice:
[NOI stress-testing](https://bsreconsulting.com/blog/noi-in-real-estate),
[capital reserves](https://www.adventuresincre.com/the-road-to-a-stabilized-noi-capital-reserves-case-study/),
[market vs contract rent](https://www.mmcginvest.com/post/market-rent-vs-contract-rent-normalizing-leases-in-real-estate-underwriting),
[reviewing assumptions](https://thefractionalanalyst.com/tfa-blog/3-steps-to-review-underwriting-assumptions),
[accurate pro formas](https://wiss.com/real-estate-pro-forma-projections/).

- ✅ **DONE (engine) — U1 revenue realism.** Lease-up curve + occupancy + credit loss already in the solve; market-vs-contract discipline is the remaining input-side note. Was: U1 — Revenue realism. Market-rent vs contract-rent (underwrite the **lower** for debt), a
  **lease-up / absorption curve** to stabilization, vacancy (5–7%), credit loss, and concessions —
  not a single flat "potential rent."
- ✅ **DONE — U2 capital reserves above NOI** (`operations.reserves_annual`, deducted before NOI in solve + a Reserves/yr driver). Was: U2 — Opex build + reserves. A real opex schedule (management ≈ 5% of EGI, utilities, insurance,
  R&M, payroll) + **capital reserves above NOI** ($/unit or $/sf), instead of a flat opex ratio.
- ✅ **DONE (partial) — U3** guardrails now cite `benchmarks` IRR/cap bands; Comparables module added. Next: validate exit cap vs comps. Was: U3 — Cap-rate & comp discipline. Stabilized vs value-add cap-rate bands (≈4–5.5% stabilized,
  5.5–7.5% value-add), an exit-cap **spread** over going-in, and a **Comparables** record (market
  rent/cap/$-per-sf) the deal is validated against (the thesis model has a Comparables tab).
- ✅ **DONE — U4 specialty risk discount.** `specialty.summarize()` now reports gross **and**
  risk-adjusted (underwritten) revenue/offset (default 35% haircut on produce, lighter on energy
  savings); `to_proforma_deltas` flows the **underwritten** figures into the deal so the blended IRR
  isn't overstated. *Next: full specialty P&L + ramp; report blended vs real-estate-only.*
- ✅ **DONE — U5 underwriting guardrails.** `underwrite.guardrails()` flags returns outside market
  bands (IRR >35% / EM >4× / negative or thin dev-spread / DSCR <1.2); `/proforma/solve` returns
  them and the Finance **sticky returns bar** shows a badge ("⚠ check assumptions"). *Next: wire
  Monte Carlo to specialty risk; validate vs Comparables.*
- ✅ **DONE — U6** Test Fit optimize accepts `pid` and seeds land (property) + hard $/sf (budget) from the live project. Was: U6 — Tie Test Fit optimize to the live proforma (vs the proxy) so generative yield-on-cost
  uses the real cost budget + underwritten NOI.

## R. Built-world techniques (research-grounded)  — archive / parking-lot
Lessons from the literature on how tall buildings are actually financed and built — to make the
generative + construction sides reflect real practice, not just geometry. Sources: Carol Willis,
[*Form Follows Finance*](https://archive.org/details/formfollowsfinan0000will) and
[*Building the Empire State*](https://wwnorton.com/books/Building-the-Empire-State/)
([Skyscraper Museum](https://skyscraper.org/empire-state-building-construction/)); Mario Salvadori,
[*Why Buildings Stand Up*](https://wwnorton.com/books/Why-Buildings-Stand-Up); and CM/real-estate
research at [VT Myers-Lawson](https://mlsoc.vt.edu/research.html) (lean construction),
[NYU Schack / PropTech](https://www.sps.nyu.edu/homepage/academics/executive-education/schack-institute-of-real-estate.html),
and ASU.

- ✅ **DONE — R1 form follows finance (daylight-limited leasable depth).** `test_fit.layout()` caps
  leasable depth at a daylight limit (~9 m / 25–30 ft from a window); space deeper earns no rent, so a
  too-deep plate loses rentable area to a dark core and its **daylight efficiency (rentable ÷ gross)**
  drops (verified: 40 m plate 43% vs 16 m plate 77%). Surfaced in the Test Fit compare table (Daylight
  column + ⚠ on deep plates). *Next: make it an optimize objective + sweep plate depth; core-efficiency
  for the elevator/stair core.*
- ✅ **DONE — R2 construction as a vertical assembly line.** `takt.plan()` + `POST /schedule/takt`:
  line-of-balance schedule where trades chase floor-to-floor at a steady takt (days/floor), with a
  **just-in-time delivery plan**, floors/week ascent rate, duration, and peak crew. *Next: takt UI/
  chart; tie to daily-report actuals.*
- ✅ **DONE — R3 structural-system advisor.** `structure.recommend(height, floors, span)` picks the
  system by scale — flat-plate (low) · flat-plate + shear walls (mid) · shear-core + frame (high) ·
  outrigger/tube (supertall) — with rough member sizing (slab ≈ span/30, beam ≈ span/16, columns grow
  with floors, capped 1200 mm), a load-path read, and span/slenderness flags. `POST /structure/
  recommend`; the **generated frame now uses these sizes** (vs the fixed 0.6 m/7.5 m frame) and the
  system shows in the massing result. *Next: per-floor column taper; lateral core geometry.*
- ✅ **DONE — R4 lean / PPC analytics.** A `weekly_plan` (Last Planner) module + `lean.ppc()` +
  `GET /projects/{id}/lean/ppc`: Plan Percent Complete + ranked reasons for non-completion + a
  rating (good ≥ 80%). *Next: surface on the dashboard; production-rate actual vs takt.*
- ✅ **DONE — R5 research-grade data & comps.** `benchmarks.py` + `GET /benchmarks` (citable cost/sf,
  cap-rate, soft-cost, productivity, PPC ranges, wired into the underwriting guardrails) + a
  `comparable` module for deal comps.

## C. Lifecycle / construction depth
- ✅ Field capture (offline), module-log PDFs, closeout package ZIP, auto-TRIR, subject alias.
- ✅ **DONE — C1 multi-period pay apps.** `cost.advance_period()` rolls completed-this → prev across
  SOV lines for successive draws; g702 `release_retainage` on the final app. *Next: auto lien waivers.*
- ✅ **DONE — C2 COBie field-enrichment** — Warranty / System / Asset / Document tabs fold closeout
  data into the COBie export.
- ✅ **DONE — C3 4D sequencing.** `fourd.timeline()` + `GET /projects/{id}/schedule/4d` maps elements
  onto the takt plan (trade × floor) → scrubable frames (cumulative % built/day), with a **viewer
  scrub** (the Schedule tools slider isolates built-to-date) + a takt **line-of-balance chart**.
- ✅ **DONE — C4 workflow-engine upgrades** (v0.1.87):
  - **Transition field-gating** — transitions declare `requires:[field]`; the engine refuses and the
    UI disables the workflow button until those fields are filled (e.g. RFI can't be Answered without an answer).
  - **Company / Contact directory + reference lookups** — first-class directory config modules with
    `reference` field lookups (e.g. `subcontract.vendor_company`).
  - **Due / overdue SLA feed** — `GET /projects/{id}/due-feed` scans all due-bearing modules into one
    ranked feed, surfaced by a **"Deadlines"** portal-home widget.
  - **In-app workflow map** — a state diagram of the module workflow on the record view (current state
    highlighted, gated transitions drawn as edges).

## M. Materials, rendering & computational design  — archive / parking-lot
Closing gaps vs Revit (families/materials), Rhino/Revit/Matterport (rendering), and Dynamo
(visual data/computational). Stays IFC-native + web-first (That Open / Fragments stores per-mesh
material info). Grounded in: [IfcMaterial layer sets](https://forums.buildingsmart.org/t/why-are-material-layer-sets-excluded-from-ifc4-reference-view-mvd/3638),
[three.js PBR](https://threejs.org/docs/pages/MeshStandardMaterial.html),
[Dynamo alternatives / Hypar](https://www.ebool.com/alternatives/dynamo-bim).

- ✅ **DONE (M1 start) — materials & surface styles.** `materials.apply_palette()` assigns an
  IfcMaterial + IfcSurfaceStyle colour per element class to generated/dome models (concrete, glazing,
  steel, vegetation…), so models carry real material data and render in colour. *Next: a material
  editor + per-project palette.*
- ✅ **DONE (M2) — render mode + PBR.** A viewer toolbar **render mode** (◓): a directional **sun
  with soft (PCF) shadows**, hemisphere sky/ground fill + a fill light, **ACES tone mapping** & sRGB
  output, and a shadow-catching ground plane. A **PBR pass** upgrades plain lit surfaces to
  `MeshStandardMaterial` (roughness/metalness, keeps the M1 IFC colours) lit by an **IBL studio
  environment** (RoomEnvironment via PMREM) for soft ambient + reflections — Fragments' own
  `ShaderMaterial` meshes are deliberately left untouched (they carry engine render hooks). Toggled
  on demand (flat stays the cheap default), reversible, re-applied as new models load. A **sun /
  shadow study** (☀) drives the render-mode sun by **date · time-of-day · latitude/longitude** (NOAA
  solar position), so shadows track the real sun arc live — including warm low-angle light and a
  below-horizon night state. A **first-person walkthrough** (🚶, Matterport-style) drops you to eye
  height (1.6 m) with **W/A/S/D** to walk (horizontal-locked, feet on the floor) and drag-to-look;
  toggling off restores the prior camera. **M2 is complete** — next rendering depth lives under a
  future theme (real-time GI / baked AO, exterior HDRI skies).
- **M3 — Family & material depth** (Revit-parity). ✅ **DONE (layer sets)** — `material_layers.py`
  attaches real **IfcMaterialLayerSet** assemblies (exterior wall = brick · cavity · insulation · CMU ·
  gypsum; interior partition; floor slab; flat roof) to every wall/slab/roof via an
  IfcMaterialLayerSetUsage, chosen from `Pset_WallCommon.IsExternal` and slab `PredefinedType`. Runs in
  the generation pipeline after the M1 palette; carries genuine compound-structure data for take-off,
  U-value and schedules. ✅ **Family library** also expanded — [families.py](../services/data/src/aec_data/families.py)
  now offers 37 placeable types across Furniture / Sanitary / Appliance / **Lighting / MEP / Structural /
  Transport** / Plant, each **parametric**: a `dims` override places a distinctly-named, correctly-sized
  **type variant** (Revit-style type families); new classes carry palette colours. ✅ **Import of
  external IFC type content** also shipped — `families.import_types_from_ifc` copies every
  IfcTypeProduct (with geometry) from an uploaded manufacturer/3rd-party IFC into the project via
  `project.append_asset` (deduped, then placeable); exposed at `POST /projects/{id}/families/import`
  and as *"⇪ Import IFC families…"* in the authoring panel. **M3 is complete.**
- ✅ **DONE (M4 start) — computational graph** (Dynamo/Hypar-style, zero-touch). `compute_graph.py`
  exposes the pure engines as **nodes** (params→input ports, dict return→output ports) + an executor:
  `GET /compute/nodes` (palette) and `POST /compute/graph` run a {nodes, edges} graph in dependency
  order (zoning → structure/takt/cost → yield). After the Dynamo zero-touch primer. ✅ **DONE — visual
  node editor** ([studio/nodeEditor.ts](../apps/web/src/studio/nodeEditor.ts)): a new **Studio**
  workspace with a palette, draggable nodes, click-to-connect ports (SVG bezier edges), live param
  fields, and **Run** (executes server-side, values flow through the wires). Graph persists to
  localStorage; persona-gated to developer/architect/engineer. **M4 complete.** *Next (optional): a
  module-relations graph view.*

## L. Library & interoperability evaluations  ★ research pass (2026-06)
Surveyed external libraries against the mission (IFC source-of-truth, server-side IFC→Fragments,
offline viewer, Blender/Bonsai as the *desktop* editor). Verdicts — adopt only what serves the
mission; see [adr/0001-dependencies-and-updates.md](adr/0001-dependencies-and-updates.md) for the
bundling/auto-update policy these feed into.

- **IFClite / `@ifc-lite/*`** (MPL-2.0, Rust+WASM, 25 npm pkgs — [ifc-lite](https://github.com/louistrue/ifc-lite)).
  Claims ~5× faster geometry than web-ifc and, crucially, **IFC5 / IFCX (JSON) support**. *Verdict:
  evaluate — but do **not** swap the browser engine* (our non-negotiable is "never parse full IFC in
  the browser at runtime"; ThatOpen pin coupling). Two useful, contained spikes: **(L1)** trial
  `@ifc-lite/geometry` (the "ifclite-geom" tessellator) as a faster **server-side** converter behind
  the existing convert API; **(L2)** track `@ifc-lite/parser` for **IFC5/IFCX readiness** so IFC
  stays the source of truth as the schema evolves. MPL-2.0 is compatible with our stack.
- **pyRevit** (free, open-source Revit add-in — [pyrevitlabs/pyRevit](https://github.com/pyrevitlabs/pyRevit)).
  *Verdict: adopt as guidance, not code.* ✅ **DONE (L3)** — Open menu now has *"Free: export IFC
  from Revit (no bridge)…"* documenting Revit's built-in IFC export + pyRevit batch export, so the
  free single-project promise is reachable without the paid Autodesk bridge. Not bundled (it runs
  inside desktop Revit; we never read .rvt offline).
- **Custom Revit export plugin?** ❌ **Not needed (decided 2026-06).** Autodesk's
  [revit-ifc](https://github.com/Autodesk/revit-ifc) is the official, free, open-source, *certified*
  IFC exporter for Revit 2019+ (ships natively; an OSS override exists) — a custom plugin would just
  duplicate it. Coordination/review tools are not authoring apps and their IFC export is
  weak/third-party, so the correct workflow is **export IFC from each authoring source** (Revit native)
  and federate here. Our free pyRevit path (L3) already covers batch export. *Optional future nicety:*
  a one-click pyRevit macro that exports IFC **and uploads to a Massing project** — convenience
  only, not a mission requirement.
- **IFC5 / IFCX** — confirmed **alpha** (component-based + JSON serialization,
  [IFC5-development](https://github.com/buildingSMART/IFC5-development)); not production. L2 stays
  *track, don't adopt*; revisit when buildingSMART moves past alpha.
- **FreeCAD** (LGPL — [FreeCAD](https://github.com/FreeCAD/FreeCAD)). Scriptable, **headless-capable**
  via the same `ifcopenshell` we already run, with NativeIFC bidirectional linking + 2D drawing
  generation. *Verdict: evaluate (L4)* as an optional **headless server engine** for parametric
  family generation and 2D-drawing export — additive to our pipeline, no new client weight. Lower
  priority than L1/L2.
- **Pascal Editor** ([pascalorg/editor](https://github.com/pascalorg/editor), R3F + WebGPU, IFC
  importer). A browser **3D building editor**. *Verdict: reference only — out of scope.* The mission
  is explicit that **Blender/Bonsai is the desktop editor, not the web viewer**; in-browser authoring
  would contradict it. Keep as a UX reference for the existing edit-gated place-tools; do not adopt.

**Schedule import (P6 / MS Project)?** ✅ **.xer (Primavera P6) parsed + wired into 4D** —
`schedule.parse_xer` reads the TASK table (planned→actual→early date fallback); `POST
/projects/{id}/schedule/import-xer` stores it and the **4D scrub then reports real calendar dates**
(`source:"p6"`, the project's P6 start→finish), surfaced by an "⬆ Import P6 (.xer)" button next to
the 4D tool. Element build-order stays takt-derived (no per-activity element mapping claimed).
**.mpp (MS Project) intentionally not parsed** — it's a proprietary OLE-compound binary with no
reliable open-source reader; the standard path is *MS Project → Save As XML/CSV → import* (CSV mapping
already supported). **What else to import:** IFC (✅ source of truth), RVT/DWG/NWC via the paid APS
bridge or free Revit-IFC export (✅), BCF issues (✅ round-trip), data via connectors (Postgres/Procore/
QuickBooks/Sage/Viewpoint ✅). Candidate future imports: **E57/point clouds** (reality capture →
overlay) and **glTF** — both nice-to-have, neither blocking the IFC-source-of-truth mission.

**Do we need to create/import libraries to "run on its own"? Do they auto-update?** No new library is
required — the desktop build already runs standalone (Tauri shell + bundled PyInstaller FastAPI
sidecar + self-hosted web-ifc WASM), and the *whole app* auto-updates via signed GitHub releases.
Third-party geometry/WASM deps are **pinned and shipped inside that signed update**, never
background-updated independently (that would break the offline guarantee and the ThatOpen
`components`↔`fragments` version coupling). Policy recorded in the ADR above.

## D. Platform / production
Tracked in [production-readiness.md](internal/archive/production-readiness.md): main.ts account/connections split,
dashboard JSON-extraction perf, Redis-backed rate limits (multi-worker), CI dependency scanning,
a11y pass. Plus: mobile (Capacitor) build hardening; RVT→IFC (APS) polish.

---

## Status & what's left — ✅ archive (v0.1.87 reconciliation)
The headline themes are **shipped** (v0.1.87): generative design + **Test Fit** (A1/A3/A4/A5/A6),
the **developer/finance portal** (B1 budgets · B2 Sources & Uses · B3 property/tax · B4 specialty ·
B5 investment memo), the full **lifecycle** (acquisition→turnover), **AI assistant**, **SSO**, and
the production-blocking hardening (see [production-readiness.md](internal/archive/production-readiness.md) — now
shippable). **30/30 API suites + 3 data suites + 24 web unit tests** (incl. a Studio node-editor DOM
smoke test, an `escapeHtml` / connections stored-XSS lock, and a direct 4D-timeline-engine test) +
a report-only dependency scan.

Remaining = incremental depth (not blockers). **Reconciled against the actual codebase (2026-06)** —
several items the old list called "next" were already implemented; verified by reading source, not
the prior list. Status now in rough priority:

1. **Test Fit depth** — ✅ **DONE** (this pass). A2 egress deepened (occupant load, egress width, min
   exits, exit separation) **and surfaced** in the Test Fit compare UI as a ✅/⚠️ life-safety line;
   parking as real IFC geometry (`PARKING` IfcSpaces on a *Site Parking* storey); true
   **polygon-offset footprint** (`offset_polygon` → `buildable_polygon`); optimize's yield-on-cost +
   **dev spread** use the canonical proforma `returns` (with stabilized occupancy).
2. **Developer deck** — ✅ **DONE.** [report.py](../services/api/src/aec_api/report.py)
   `investment_deck_pdf` now has 6 slides: added **Market & positioning** (the deal's yield/IRR/soft-cost
   against conceptual benchmark bands) and a **Development timeline** (phased gantt bar from the saved
   scenario's construction/lease-up months), plus a **site photo** on the cover pulled from project
   attachments when present.
3. **Construction**
   - C1 pay-apps + lien tracking + COBie record-folding — ✅ done (`f0b1367`); printable statutory
     waiver **document/PDF** added v0.1.36 (`GET /cost/lien-waiver[.pdf]`).
   - **C2 model-derived COBie field depth** — ✅ **DONE.** [cobie.py](../services/data/src/aec_data/cobie.py)
     Space sheets now carry **net/gross area + usable height** (from Qto); Type sheets carry
     **manufacturer / model / warranty / expected-life / replacement-cost / color / material**;
     Component sheets carry **serial / install-date / warranty-start / tag / asset-id**; and a new
     **Attribute** sheet flattens every remaining pset (Name/Value/SheetName/RowName) so no model data
     is dropped in handover.
   - C3 4D sequencing — ✅ already done: [fourd.py](../services/api/src/aec_api/fourd.py) `timeline()`
     + `GET /schedule/4d` + a scrubber in the web portal; schedule viz (`gantt_svg` / `lob_svg`) too.
4. **Platform** — ✅ **Redis-backed rate limits** done: set `AEC_REDIS_URL` and the per-IP limit is
   shared across workers via an atomic Redis `INCR`+`EXPIRE` (fail-open to the in-process bucket on any
   Redis error; redis is lazily imported only when the URL is set), with a `test_ratelimit` gate.
   ✅ **Dashboard JSON-extraction perf** done: status counts via an indexed `GROUP BY` (no JSON), and
   the `data` blob parsed only for active (non-terminal) records — identical output, much less work on
   completed-record-heavy projects. ✅ **a11y pass** (first cut): workspace + finance tabs now expose
   `role="tab"`/`role="tablist"` with `aria-selected` tracking the active tab, the persona picker has an
   `aria-label`, and the status bar is a polite `role="status"` live region (existing landmarks/labels
   were already in place). ✅ **main.ts modularization (round 1)** + **security pass**: the admin
   **connections UI** (~240 lines) is extracted to a **lazily-imported** `connectionsUI.ts` chunk
   (main.ts 1205→963 lines; the 13 kB chunk loads only when an admin opens it), and real stored-XSS
   vectors (connection name, Procore ID, browsed DB cells, audit detail) are now escaped via a shared
   `escapeHtml`. ✅ **Round 2** done: the account/auth/admin UI (sign-in + SSO, reset, account menu,
   password, user management, audit log, project members — ~330 lines) extracted to
   `account/accountUI.ts` behind a small deps object; **main.ts is now 657 lines** (from 1205). Sign-in
   was also rebuilt on the shared `modalShell` (it had hand-rolled its own overlay, so it now gets
   Esc-to-close / focus-trap / dialog-ARIA like every other modal).
5. **Mobile** — framework + plan written ([docs/mobile.md](mobile.md)): the web app is already an
   installable offline **PWA** with the field-capture loop, so the native app is a **Capacitor wrapper**
   of the existing build (camera/GPS/push as capability-detected plugin swaps), not a rewrite. Native
   store builds need a macOS/Xcode + Android-SDK pipeline (separate from the Tauri desktop release);
   recommendation is to ship the PWA "Add to Home Screen" now and fast-follow the native shell.

**Net:** the reconciled roadmap is effectively cleared — every theme (M1–M4, Test Fit, Developer deck,
Construction C1–C3, Platform Redis/perf/a11y) is done except the low-value main.ts refactor and the
out-of-scope mobile app.

---

## Lifecycle completion + production readiness (v0.3.53–v0.3.59, Jul 2026)

Seven sequenced releases closed the production blockers and the two lifecycle gaps (pre-construction
and post-turnover operations) surfaced by the full-code + market audit:

1. **v0.3.53 — backend production blockers**: Postgres-without-RBAC boot guard, SQL-side project
   membership filtering, bounded board/CSV/sync loads, storage-prefix delete cascade, advisory-locked
   autosync, rate-limiter LRU.
2. **v0.3.54 — ops & supply chain**: runnable preflight (`scripts/validate_prod_config.py`) +
   PRODUCTION_CHECKLIST, Dependabot, container build + Trivy gate → ghcr, Cargo.lock workflow,
   sidecar signing, seed guard, TrustedHost.
3. **v0.3.55 — UX/a11y/perf**: promptModal retires every `prompt()`, table-header `scope`,
   mobile pass, perf baseline.
4. **v0.3.56 — pre-acquisition**: `due_diligence` (ASTM E1527-style categories) + `entitlement`
   modules with a go/no-go readiness rollup + 📜 panel.
5. **v0.3.57 — operations (CMMS + energy)**: `work_order`/`pm_schedule`/`meter`/`meter_reading`,
   PM generation + KPIs (PM compliance, MTTR), metered EUI + trends, flagged ENERGY STAR bridge,
   🔧 Operations + ⚡ Energy panels.
6. **v0.3.58 — capital stewardship**: reserve study (component replacements + funding adequacy +
   suggested contribution), `capital_plan` (CIP), `cam_expense` + CAM reconciliation with
   variable-only gross-up + per-tenant statement PDFs, Finance ▸ Asset Mgmt tab.
7. **v0.3.59 — ESG + POE**: GHG Scope 1/2 from a local factor table, water, certification tracking,
   `poe` module (actual-vs-design EUI gap), 🌱 ESG & POE panel + Report Center entry.

**Documented follow-ups (out of scope by design):** live ENERGY STAR/BAS/BMS integrations (flagged
stubs only), full institutional reporting packs, space/move management (CAFM), 1031 tooling, JWT
revocation blacklist + Redis-backed presence (known limits in PRODUCTION_CHECKLIST).

---

## Standards, KPIs & AI-over-model (v0.3.61–v0.3.68, Jul 2026)

Eight sequenced releases (a competitive scan of eight AEC products + the ISO 19650 / buildingSMART /
BIM-KPI frameworks) made the platform demonstrably standards-aligned across the lifecycle and added
the AI-over-model layer competitors lead with — all offline-first, money behind flagged bridges,
docs neutral:

1. **v0.3.61 — ISO 19650 CDE**: `information_container` (WIP→Shared→Published→Archived + suitability/
   revision codes + approval gates) + `info_requirement` register (OIR/AIR/PIR/EIR/BEP/MIDP/TIDP);
   CDE-discipline metrics; 🗂 CDE / Standards panel.
2. **v0.3.62 — openBIM quality** (`openbim_quality.py`): LOIN per element, IDS rule-compliance %,
   IFC export health, bSDD alignment — scored over the model property index.
3. **v0.3.63 — BIM KPI scorecard** (`bim_kpi.py`): the 10-category information-management scorecard
   (n/a when inputs absent) + a handover data-drop acceptance gate + Report Center entry; 📊 panel.
4. **v0.3.64 — AI over the model**: an **MCP server** (`mcp_server.py` + `mcp_tools.py`, SDK optional)
   exposing the project to external agents, plus grounded **standards-compliance experts**
   (`standards_expert.py`) referencing the clause behind each finding. [docs/mcp.md](mcp.md).
5. **v0.3.65 — digital twin + DPP** (`twin.py`, `building_system`): asset↔system linkage + sensor
   mapping (ISO 23247) + Digital Product Passport scaffolding (GS1/EPD/manufacturer).
6. **v0.3.66 — procurement compliance gate** (`procurement_gate.py`): per-vendor can-bid / can-bill
   from the COI / prequal / subcontract / waiver records + the outbound nudge feed.
7. **v0.3.67 — drawing-sheet extraction** (`sheet_extract.py`): parse a PDF text layer / pasted index
   into `{number, title, discipline}` → optionally create Drawing records (AI page-image path flagged).
8. **v0.3.68 — concept space programming** (`adjacency.py`, `space_program`): the program as a
   node/adjacency graph → gross area + use mix that feed the massing generator; 🧩 Space Program panel.

The platform now spans **land acquisition → programming → design (ISO 19650) → construction → turnover
→ operations (twin/ESG)** with standards alignment and an AI surface at each stage.

---

## Design workspace + role-based placement (v0.3.70)

Added a **Design** top-level workspace (between Drawings and Construction) as the architect/engineer's
design-phase seat, and did a methodical pass so every tool shows in the view(s) whose role owns it.
See [roles-views.md](roles-views.md) for the full role→view map.

- **Engine**: a module can now belong to more than one workspace (`workspace` is a `|`-separated list);
  shared A/E↔GC registers (RFI, submittal, drawing, transmittal, meeting, permit, spec) show in both
  Design and Construction without duplicating records.
- **Design nav**: Brief & program (Space Program · Project Lifecycle) + Model & standards (IDS · CDE /
  Standards · BIM KPIs · Model Health) — the design/standards destinations moved here out of the GC
  portal. A **Model Health** launcher deep-links to the model-QA checks in the Model Tools rail
  (they need the loaded geometry). Personas: architect/engineer home into Design.

## Part C — UX / performance / productivity backlog (approve item-by-item)

Candidate upgrades identified during the Design-workspace pass, not yet scheduled:

1. **Nav density** — the Construction portal + the multi-card panels (Schedule now stacks 6 cards) are
   getting dense; add per-stage collapse memory and a denser dashboard summary.
2. **Role landing dashboards** — every persona should open to a tailored command-center (the Design
   home sets the pattern; extend to Finance and Developer).
3. **Viewer-tool discoverability** — the model-health checks (Data QA, code-readiness, clash, IDS) are
   buried in the Model Tools rail; the Design **Model Health** launcher is step 1 — consider a
   first-class "Model health" surface with live scores.
4. **Front-end perf** — `portal.ts` is ~4,000 lines and eager; split per-workspace render bundles
   (dynamic import) so Design/Developer code loads on first open. Keep the Brotli shell budget gate.
5. **Cross-workspace deep-links** — RFI → drawing → model element; saved views per role; ⌘K scoped by
   the active workspace.
6. **A11y** — keep verifying new tabs/dashboards (roles, focus order, contrast) as workspaces grow.

---

## Operations depth — facility condition + pull-planning (v0.3.72+)

Rounding out the operate phase and the Last Planner board:
- **v0.3.72 — Facility Condition Assessment + FCI (M1, shipped)**: `fca_element` module + `fca.py`
  engine (FCI = deferred + renewal ÷ CRV, UNIFORMAT II, condition bands, portfolio roll-up), reserve-
  study integration, 🏥 Facility Condition panel + report.
- **v0.3.73 — M2 (shipped) — deeper Last Planner analytics**: Tasks-Made-Ready %, make-ready lead time, perfect-
  handoff %, PPC trend by week, variance-reason Pareto, and cross-project pull-planning benchmarks.
- **v0.3.77 — real-time collaborative pull board (M3, shipped)**: an SSE stream
  (`/pull-plan/stream`) over a cheap board change-signature live-refreshes the board as any trade
  edits; presence chips show who else is on it; and an opt-in optimistic lock (`expected_modified_at`
  → 409) stops silent overwrites — reusing the existing presence/notification-stream primitives, no
  new deps. The lock is generic (every module benefits, via the record editor).

---

## Climate & water resilience (v0.3.75+)

Rainfall and flooding as quantifiable design parameters, across the lifecycle:
- **v0.3.75 — W1+W2 (shipped)**: flood risk (ASCE 24 Design Flood Elevation + flood-proof-MEP check)
  and stormwater (Rational Method Q=C·i·A + detention) — `flood_risk`/`drainage_area` modules +
  `resilience.py` + 🌊 Climate Resilience panel + report.
- **v0.3.76 — W3+W4 (shipped)**: weather-sequenced construction — a `weather_sensitivity` flag on
  schedule activities + a `climate_site_risk` register (hazard/season/severity/controls) + weather-delay
  days rolled up from the daily reports (`resilience.weather`); and a physical climate-risk rating
  (Low/Moderate/High/Severe over flood exposure + at-risk assets + open site hazards + weather delays,
  `resilience.climate_risk`) folded into the ESG scorecard (`physical_risk`).

## The Discipline Spine — layered model → sheets → specs → bid packages → budget (v0.3.79+)

Represent a project as federated **structural / MEP / architectural** models whose discipline-tagged
sheets thread through specifications, bid packages and the budget — grounded in the US National CAD
Standard discipline designators + CSI MasterFormat, with the Uniformat↔MasterFormat crosswalk. Two
shared vocabularies (discipline + MasterFormat division) do the joining. Five phases:

- **v0.3.79 — D1 (shipped): shared vocabularies.** `classification.py` gains the NCS discipline
  vocabulary (A/S/M/E/P/F/C/T/G/L/Q with each discipline's default MasterFormat divisions + Uniformat
  groups), the MasterFormat division master (25) and the Uniformat↔MasterFormat crosswalk;
  `discipline_of_ifc_class`, `discipline_code` (legacy-alias normalization). `GET /reference/disciplines`.
  Free-text `discipline`/`division` fields → validated selects. `test_disciplines`.
- **v0.3.80 — D2 (shipped): discipline-tagged model.** Record which discipline model each GUID came from in the
  properties index (source-file = authoritative discipline tag); `GET /elements?discipline=`; persist
  per-model transforms; discipline layer toggles + colour-by-discipline in the viewer.
- **v0.3.81 — D3 (shipped): discipline sheets.** `drawing_set` module; parse the NCS Sheet ID (discipline +
  sheet-type digit + sequence) into structured fields; `revision_register` module; `drawing↔spec_section`.
- **v0.3.82 — D4 (shipped): connect the procurement chain.** `bid_package.spec_sections` TEXT → reference array;
  `cost_code` link + shared discipline on bid_package/spec_section/cost_code; a `spine.py` traceability
  engine (discipline → models → sheets → specs → bid packages → cost codes → budget + coverage gaps).
- **v0.3.83–84 — D5 (shipped): discipline-aware generation.** Extend `generate/massing` to emit separate STR / ARCH /
  parametric-MEP models sharing one origin + storeys + a real `IfcGrid`, auto-registered with discipline
  tags, and seed the spec/bid/budget skeleton per discipline from the mapping table.

## Resourcing + Accounting depth (v0.3.117+)
A research-backed plan to deepen resource loading and construction accounting, keyed on cost code and
reusing the config engine's reference/rollup relational spine.
- **R (shipped v0.3.117) — Resource loading, real + relational.** A `resource_assignment` model ties a
  resource (labor / equipment / material + rate) to a **schedule activity** and a **cost code**. The engine
  produces a cost-loaded manpower histogram (by trade/type), cumulative unit + cost S-curves, over-allocation
  vs an availability cap, and a **leveling advisory** that smooths over-allocated work within its CPM float
  (critical-path work stays locked). Wired to a `👷 Resource loading` panel; `cost_code.resource_budget`
  rollup; falls back to activity `crew_size`.
- **A1 (shipped v0.3.118) — WIP schedule.** `wip.py` on top of `cost.py`: percentage-of-completion
  (cost-to-cost) → earned revenue vs billed → over-billing (contract liability) / under-billing (contract
  asset), retainage, gross profit, backlog, plus a portfolio WIP sorted by cash risk — the accounting twin
  to the earned-value module. `GET /projects/{id}/wip` + `/wip/portfolio`, a `📄 WIP Schedule` panel + report.
- **A2 (shipped v0.3.119–120) — Statements + GL.** `contractor.py` — POC income statement + contract-
  position balance-sheet section (asset/liability, retainage, AP, net contract working capital), per-job
  + company-wide. `accounting.py` — a standard construction chart of accounts + a balanced double-entry
  journal (job cost / billing / WIP POC adjustment → revenue nets to earned) + trial balance; 📒 General
  Ledger panel + the existing GL-CSV / QuickBooks-IIF export.
- **Moat (shipped v0.3.121) — Cost traceability by GlobalId.** `traceability.py` — cost lines (budget /
  commitment / direct cost / sub invoice) carry `element_guids`; the engine computes coverage (share of job
  cost tied to real model elements) overall and per cost code, and answers "what did this element cost?" by
  GlobalId. `GET /projects/{id}/cost/traceability` + `/elements/{guid}/costs`, a 🔗 Cost Traceability panel.
  The end-to-end model → resource → cost → GL link a cost-code-only ledger can't make.
- **I (planned) — Interop.** Balanced cost-coded journal-entry export to the accounting system of record
  through an approval gate; then derive WIP % complete and resource curves from **model quantities by
  GlobalId** (the coverage index above is the foundation).

---

## 🏗️ Wave 9–11 — authoring suite + Master Builder + AI-MCP (shipped)

The in-browser authoring push and everything downstream of it. Version tags + a one-line note per shipped
item; the still-open remainder of each track lives in [roadmap.md](roadmap.md).

### Model workspace → true in-browser authoring program (P1–P6, v0.3.231–241)
The 2026-07 direction change: the Model workspace became a genuine authoring+coordination program
(create from scratch → draw/edit by GUID-stable recipe → drag-to-move → clash/coordinate).
- **P1** blank model from scratch (`generate_blank_ifc` + `POST …/model/blank`) + first-class Author-mode surfacing (v0.3.231)
- **P2** removed redundant legacy place buttons + ~90 lines dead code — Draft panel is the single authoring surface (v0.3.232)
- **P3** room/space authoring UI (➕ Add rooms/spaces via `add_spaces`) (v0.3.234)
- **P4** author-ready **template picker** — blank + office bay / residential floor / warehouse (v0.3.233)
- **P6a** cut four duplicative rail sections → deep-links; removed ~700 lines (v0.3.235)
- **P6b** dedicated **💥 Clash & coordination** rail toggle (federated + single clash, list, metrics, promote-to-BCF) (v0.3.236)
- **P6c** rail re-clustered **Navigate / Author / Coordinate** (v0.3.237)
- **P6d** docked **📋 Properties** rail panel with a Type/Instance identity header (v0.3.238)
- **Model browser** — **group-by** (level / discipline / IFC class / type-family) + **search** across name·GUID·class·type·discipline, auto-expanding matches (v0.3.239)
- **Manage levels** — per-storey rename + set-elevation (`rename_storey`/`set_storey_elevation`; storey listing carries GUIDs) (v0.3.240)
- **Selection sets** — named saved searches you can isolate in one click, persisted per-project (v0.3.240)
- **P5 edit-in-place** — drag-to-move transform gizmo (ghost preview + ΔE/ΔN/ΔZ + grid-snap) via the GUID-stable `move_element` recipe (v0.3.241)

### Wave 9 — 2026-07 research scan (v0.3.245–251)
- **W9-1** property mapping / normalization — the **transform** verb between IDS-validate and COBie-export (`propmap.py`, `map_properties` recipe, `/propmap/detect`+`/plan`, 🔧 Normalize properties) (v0.3.245)
- **W9-2** computed **occupancy load + egress capacity** (IBC 1004.5/1010.1.1/1006.2; `codecheck.egress_analysis`, `/codecheck/egress`, 🏛 Occupancy & egress) (v0.3.246); **W9-2b** BCF round-trip (`POST /codecheck/egress/bcf`) (v0.3.251). *Fire-separation between occupancies still deferred (needs space-boundary geometry).*
- **W9-3** IFC5-style **property-override layers** — USD-like non-destructive overlays, strongest-wins, `bake` flattens to a GUID-stable IFC (`layers.py`, `/layers`+`/resolve`+`/bake`, `apply_layers`, 🧬 Property layers) (v0.3.247)
- **W9-4 v1** semantic **model graph** from IFC relationships — multi-hop cited neighbor queries (`graph.py`, `/graph/neighbors`, 🕸 Related elements) (v0.3.248). *Harder half (spec/drawing/code ingest + NL→graph) still open — see roadmap.md.*
- **W9-5 (M first step)** site logistics on the 4D timeline — temporary resources as first-class time-phased 3D glyphs (`logistics.py`, `/logistics`+`/state`, 🏗 Site logistics) (v0.3.250). *L part (motion along paths + swept crane-reach clash) still open.*
- **W9-6a** generative fit-out — **auto-furnish** grids real `IfcFurnishingElement` into every `IfcSpace` (`furnish_spaces` recipe, 🪑 Furnish spaces) (v0.3.249)

### ① Generative-design & analysis depth — DONE (v0.3.215–227)
- **Test Fit** — daylight-limited plate-depth **optimize** + `core_efficiency` (v0.3.215); polygon-offset buildable footprint + parcel-bound surface parking (v0.3.221)
- **Structural generative** — per-floor column taper by √(floors carried) + sized lateral RC core, extruded as real shear walls (v0.3.220)
- **Underwriting realism** — exit-cap-vs-comps guardrails (v0.3.216); specialty P&L + ramp + blended-vs-RE IRR (v0.3.222); Monte-Carlo the specialty risk discount → blended-IRR distribution (v0.3.223)
- **Lean / takt** — `takt.progress()` + actuals overlay (floor variance, achieved vs planned, PPC) (v0.3.224)
- **Rendering / computational** — material editor + per-project palette (v0.3.225); module-relations graph view (v0.3.226). *Heavier GPU work (real-time GI / baked AO / HDRI skies) is a documented web-viewer non-goal.*
- **Developer deliverable** — investment pitch deck expanded to 9 slides (exec summary, capital stack, business plan) (v0.3.227)

### ② UX / performance / productivity — DONE (v0.3.228–242)
- **Role landing dashboards** — tailored Design / Developer / Finance homes (v0.3.228)
- **Nav density** — per-stage collapse memory (v0.3.230) + command-center density toggle (⊞/⊟, persisted) (v0.3.242)
- **A11y** — audited this cycle's new panels (SVG accessible names, labeled controls, `scope` headers, `.sr-only`) (v0.3.229); ongoing as panels ship
- ⌘K, saved-views-per-role, cross-workspace deep-links (both directions), and the `portal.ts` per-domain split all shipped earlier

### ③ Interop / library evaluations (v0.3.243)
- **L1** `@ifc-lite/geometry` server-side converter spike — **EVALUATED → DEFER**: the current Fragments path converts a 1.6 MB IFC → `.frag` in ~1.1 s, no bottleneck at our model scale. *Re-trigger: a customer with ≳50 MB IFC where conversion latency bites.*
- **L4** FreeCAD headless engine — **EVALUATED → DEFER**: parametric families + 2D drawings are already covered by `ifcopenshell` recipes + `drawings.py` + `sheetgen.py`. *Re-trigger: a concrete parametric op `ifcopenshell` cannot express.*
- **glTF import overlay** — already ships (`referenceLoader.ts` parses `.gltf`/`.glb` into a view-only reference overlay)
- **pyRevit "Publish to Massing" macro** — already ships (`integrations/pyrevit/Massing.extension`: export IFC → upload → convert → open; no paid bridge)
- **RVT→IFC via the paid Autodesk bridge** — hardened (v0.3.243): a properly-gated Design-Automation stub + input validation + `test_aps.py` locking the gate order (501 → 400 → 402 → 400 → 502)

### Wave 10 — IFC authoring suite (shipped parts)
- **W10-1** real type/family system — `create_type`/`edit_type_params` (in-place shared-box propagation, GUID-stable)/`assign_material_set`, `type_detail` inspector, 🧱 Family types browser (v0.3.252)
- **W10-3** groups, assemblies, arrays — `create_group`/`ungroup`, `create_assembly`, `array_element`, 🧩 Groups & arrays viewer tool (v0.3.253)
- **W10-8** phasing — `set_phase` tags new/existing/demolish/temporary via `Massing_Phasing.Status`, `phase_summary`, 🕐 Phasing tool (v0.3.254). *Tying phase to the 4D slider remains a sub-item.*

### Wave 11 — The Master Builder (shipped parts, v0.3.255–279)
- **E9** selector DSL (`query_elements` + 🔎 Query + `GET /query`) + `geom.tree` spatial index (v0.3.255)
- **F0** the representation/context spine + LOD state — `ensure_contexts` (Model+Plan roots, Body/Axis/Box/FootPrint/Annotation subcontexts), `set_lod`/`lod_summary` (`Pset_MassingLOD.Stage` 100→500), 📶 Level of Development tool (v0.3.256). *F0b (derive Box/Axis/FootPrint from Body) still open.*
- **B2** parametric door/window generators — `geometry.add_door/window_representation` (real lining/frame/panels, wall-sized lining, box-proxy fallback) (v0.3.257)
- **D4** classification + document carriers — `classify` → `IfcRelAssociatesClassification` (UniFormat/MasterFormat/OmniClass/Uniclass), `attach_document` → `IfcRelAssociatesDocument`, `element_detailing` inspector, 🏷 Detailing tool (v0.3.258)
- **D3** IDS-shaped detail-rule engine — `apply_rules` (applicability facets → content bundle via the Track-D carriers), `validate_rules` (missing-keynote pre-flight), ✨ Auto-detail tool + seed library (v0.3.259); **D7** the window-flashing worked case ships in the seed library (exterior window → IBC §1404.4/ASTM E2112/AAMA 711 flashing + 08 51 00)
- **C1** plan-drawing generator — `drawing.py::plan_svg` derives footprints **directly from authored extruded-profile geometry** (no OCC), class-styled poché scaled to paper mm, storey-scoped, 🖨 Generate plan (v0.3.260)
- **C2** overall dimension strings + keynote bubbles & legend generated from each element's Track-D classification codes (v0.3.261)
- **C3** issuable ARCH-D **sheet + titleblock** (`drawing.py::sheet_svg`, 📄 Issue sheet) (v0.3.262); **C3b** the sheet rendered **to PDF** via reportlab — the submittable AHJ deliverable (`sheet_pdf`, ⤓ Sheet PDF) (v0.3.263)
- **C4** computed **door/window/room schedules** (`drawing.py::schedules`/`schedule_svg`, 📋 Schedules) (v0.3.264)
- **B6** domain-geometry catalog — steel connections (`connections.py::add_base_plate`/`add_shear_tab`, 🔩) (v0.3.265) · rebar cages (`rebar.py::add_rebar_cage`, 🪝) (v0.3.266) · MEP fittings + connected systems (`add_mep_fitting`, `mep.py::mep_summary`, 🔀) (v0.3.268; also fixed a `sheet_svg` empty-model crash + `test_wave11_edges.py`) · curtain-wall (`curtainwall.py::add_curtain_wall`, 🪟) (v0.3.270)
- **D1** code-analysis summary — `codecheck.code_analysis` (occupancy Ch.3, construction type + Table 601, allowable area 506.2/504/506.3, occupant load 1004.5 + egress Ch.10), 🏛 Code analysis QA tool, `/codecheck/analysis` (v0.3.274)
- **C5** sections & elevations reachable — 📐 Sections & elevations tool (cut X–X/Y–Y sections + projected N/S/E/W elevations from `drawings.py`, auto-centred cut); also fixed a world-placement bug so all 2D output places off-origin elements correctly (v0.3.276)
- **G1** LOD-500 verified-as-built — `verify_asbuilt` stamps `Massing_AsBuilt` (VERIFIED + provenance), `asbuilt_summary` → readiness % by method, `/lod500`, ✅ As-built verify tool (v0.3.279)

### AI-MCP / NL authoring (shipped, v0.3.271–278)
- **S1+S2** natural-language authoring over the edit-recipe engine — `nlauthor.py` (`RECIPE_SPECS` + `validate_call` guardrail + keyword `interpret`), `POST /ai/author` (interpret-only, confirm-before-apply), ✨ command bar. Deterministic no-API-key baseline (v0.3.271)
- **S3** multi-step LLM interpretation — `nl_ai.plan()` produces a structured JSON plan against `RECIPE_SPECS` ("a 5×4 m room" → 4 walls); every step re-validated by `validate_call`, GUIDs filled from selection (never fabricated), destructive recipes withheld, keyword fallback; ✓ Apply-all chains edits into one republish (v0.3.278)
- **S3 fix** — `_PLAN_SCHEMA` params were an open object (strict structured-output 400s); params now a JSON string parsed by `_coerce_params`; apply-all recovers from a mid-chain failure (republishes what applied, reports "stopped after N/M") (v0.3.280)

### Wave 11 — CD-set finish + code intelligence + LOD-500 turnover (v0.3.281–293)
- **C6 DXF export** — `dxf.py` dependency-free R12 writer; `plan_dxf`/`section_dxf`/`elevation_dxf` on named layers + `.dxf` endpoints + ⤓ DXF buttons (v0.3.281)
- **C6 schedules-on-a-PDF-sheet** — `drawing.schedule_pdf` lays the door/window/room schedules on an ARCH-D titleblock sheet; `GET /drawings/schedule.pdf`, 📋 Schedules sheet tool; titleblock factored to a shared `_titleblock_pdf` (v0.3.282). **The construction-document set is now complete** (plans/sections/elevations/schedules → SVG/PDF/DXF).
- **E4 progressive-disclosure toolbar** — everyday authoring + drawing tools visible; LOD-350/400 fabrication + detailing tools behind a persisted "🔧 Advanced fabrication tools" toggle (v0.3.283)
- **E8 authoring guardrails (first slice)** — `guards.py::precheck` enforced in `apply_recipe` (finite coords, no zero-length lines, positive dims, valid enums, required refs) + `POST /edit/precheck`; blocks broken edits, warns on unit-slip magnitudes; verified against 49 recipe-exercising tests (v0.3.284)
- **CODE-1 jurisdiction catalog** — `codes.py` code-family/edition catalog + `resolve(jurisdiction)` → adopted editions with a national-baseline fallback + mandatory verify-with-AHJ note; `GET /codes/{families,adoptions,seeded}`; copyright-safe facts only (v0.3.285)
- **CODE-3 edition-aware code analysis (first slice)** — `code_analysis` resolves the jurisdiction's adopted IBC edition and names it in the badge/citations/disclaimer; `?jurisdiction=` + a Jurisdiction field (v0.3.286)
- **Hardening** — whitelist Content-Disposition filename segments on the DXF/PDF drawing endpoints (defence-in-depth after a clean security review) (v0.3.287)
- **Dependency hygiene** — bump vitest 3 + happy-dom 20 to clear 4 critical Dependabot advisories (dev/test-only); full web suite re-verified (v0.3.288)
- **D6 3-part MasterFormat project manual** — `specmanual.py` groups elements into CSI divisions → sections, SectionFormat Part 1/2/3 (Part 3 Execution from attached install docs); `GET /spec/manual{,.txt}` + 📖 Project manual tool (v0.3.289)
- **D8 approvability pre-flight** — `codecheck.approvability` runs a plan-reviewer checklist (egress capacity, door clear width, two-exits, occupancy classification, substantiated fire-rated assemblies), each cited, with a readiness score; `GET /codecheck/approvability` + ✅ pre-flight tool that isolates flags (v0.3.290)
- **G3 manufacturer/serial (O&M/turnover)** — `set_manufacturer_info` stamps the standard `Pset_ManufacturerTypeInformation`/`Pset_ManufacturerOccurrence`; `asbuilt_summary` counts with_manufacturer/with_serial; stamp form in the as-built tool (v0.3.291)
- **Debug fixes** — a post-release audit caught two wrong-result bugs: `specmanual` layer-set materials never surfaced (now resolves `IfcMaterialLayerSetUsage` → layer materials); D8 occupancy check counted free-text `LongName` (now gates on `Pset_SpaceOccupancyRequirements.OccupancyType`); both regression-tested (v0.3.292)
- **Model Health — Code & permit-readiness lens** — the composite scorecard gains a fifth lens from the D8 pre-flight, so the single "is my project healthy?" number now spans integrity, ISO-19650, clash, verified-as-built, and permit-readiness (v0.3.293)

### Roadmap hygiene + docs (2026-07)
- Reorganized the roadmap so the active file holds only open work; moved every shipped item to this archive; removed all competitor name-drops from both files; refreshed README / in-app guide / Pages landing to the current end-to-end capability.



---

# Archived roadmap snapshot — 2026-07-18 (pre-reprioritization, at v0.3.456)

Everything below is the full roadmap as it stood after the v0.3.441–456 arc (audit remediation ·
GEN-SCORE · PLUGIN-REGISTRY · VIEWER-FUNNEL · perf · authoring split · JOB-QUEUE · SHEET-VIEWPORTS
server+editor · the Gate-A breakthrough — the "preparing geometry" fix — · SNAP-KIT completion ·
REL-4 slices 1–2). Every ✅/🟡-shipped entry here is the permanent completed record; the still-open
items were re-extracted into the rewritten, re-prioritized live [roadmap.md](roadmap.md).

# Roadmap

The single product roadmap. Supporting detail lives in:
[production-readiness.md](internal/archive/production-readiness.md) (security/perf/ops checklist),
[gc-portal.md](gc-portal.md), [gc-tools-audit.md](internal/archive/gc-tools-audit.md),
[ux-findings.md](internal/archive/ux-findings.md).

Three pillars on one IFC-keyed model: **BIM viewer** · **GC portal** (config-driven modules) ·
**developer/finance** (proforma). Shipped continuously — latest release **v0.3.450** (the audit-remediation + roadmap-completion arc
v0.3.441–450: audit fixes, GEN-SCORE, PLUGIN-REGISTRY, VIEWER-FUNNEL, perf, the authoring split,
JOB-QUEUE, SHEET-VIEWPORTS server slice — every buildable open item shipped; the remainder is
explicitly gated in the ⛔ section below). Recent waves
(v0.3.393–431): the **dev-velocity & modularization program** — test gate parallelized ~30→~11 min,
backend + web **import-cycle guards** in CI, and the worst hotspots decomposed behind façades (`edit.py`
2127→761 via a foundation + five recipe leaves; `connectors.py` and the sheet renderers split the same
way) — plus the **code-gap closeouts**: element-level **MODEL-DIFF**, ASCE 7 **DRIFT** screen, **FIN-TEST**
money-math locks, and the **IFC-QA** export round-trip fidelity check. Full record in
[roadmap-completed.md](roadmap-completed.md).

> **This file holds only what is still OPEN.** Everything shipped — every wave, track, and release — lives in
> [roadmap-completed.md](roadmap-completed.md), so *what's left* is never buried under *what's done*. The
> Model workspace is a genuine authoring + coordination program (from-scratch models, GUID-stable
> draw/edit recipes, drag-to-move, model browser, levels, selection sets, the construction-document set, code
> intelligence, the discipline tree). What remains is **the UX consolidation of that capability** plus
> incremental depth, spikes, upstream-blocked work, and documented non-goals — nothing is blocking.

---

## 🚀 Current focus (2026-07-17)

Two big cycles **completed** and are archived in [roadmap-completed.md](roadmap-completed.md): the
**dev-velocity & modularization program** (v0.3.393–412 — parallel test gate, import-cycle guards, the
REL-3 façade decompositions, the MODEL-DIFF/DRIFT/FIN-TEST/IFC-QA closeouts) and the **four-lane audit
upgrade plan** (v0.3.413–428 — P0 security → P1 reliability → P2 docs/demo → P3 2026 capabilities). The
**OpenAEC / Open CAD Studio study** (v0.3.430–431) added the CAD command line + authoring matrix.

**What's still open** is consolidated in the two sections below — the 🎯 upgrade-plan remainder and the
🧭 CAD-UX lessons — plus the standing engineering backlog:

- **REL-4 — decompose the *web* hotspots** *(now live-verifiable — Gate A open)* — `viewer/app.ts` split
  by responsibility, leaf-by-leaf with live proof; `main.ts`; `portal.ts`.
  ✅ Slice 1 SHIPPED v0.3.455: envTools.ts (render/sun/walk/levels, 4,361→4,215) — all four tools
  exercised in the running viewer post-extraction.
  ✅ Slice 2 SHIPPED v0.3.456: fileIO.ts (open/import/export + Tauri dialogs, 4,215→4,044).
  Next candidates: the collab/presence block · the KEYS + dyn-input layer · measure/section tools.
- **REL-3 remainder** — `modules.py` CRUD/feeds (needs a DI pass, would cycle otherwise) · `main.py` ·
  rest of `data/drawings.py` / `drawing.py`. *(Diminishing returns — attack opportunistically.)*
- ✅ DEV-3 (partial, v0.3.450): **incremental tsc** — local `npm run typecheck` 67s cold → **9.4s warm**
  (buildinfo in `node_modules/.cache`, never committed; CI runs cold, unchanged there).
  DEV-2 evaluated & closed: coverage-upload deferred with rationale (the gate runs 265 suites as parallel
  subprocesses; cross-process coverage instrumentation costs ~30-50% wall on a ~10-min gate for a number
  nobody acts on) · hotspot docstrings — the split modules carry full module/endpoint docs. ·
  ✅ REL-5/7 — CLOSED by evidence (v0.3.441 audit): `errorReporting.ts` already wires window.onerror +
  unhandledrejection to the O1 error log, panel promises carry near-universal `.catch` coverage, and the
  caller scan found no zero-caller client methods — the "~1,075 dead lines" claim didn't survive proof,
  so nothing is deleted.
  ✅ COBie/parse robustness SHIPPED v0.3.442 (all 8 swallow sites → counted, logged skips).

Deferred bridges (deliberate 501s — money movement / KYC / paid APS) are a defensible pattern, not gaps.

---

## 🎯 Upgrade plan (2026-07-17 audit) — mostly SHIPPED (archived in roadmap-completed)

The four-lane audit plan (P0 security · P1 reliability · P2 docs/demo · P3 2026 capabilities) executed
**v0.3.413–428** — full detail in [roadmap-completed.md](roadmap-completed.md). Shipped: SEC-TENANT ·
WEB-BOOT · SEC-GUARD · SEC-MCP (P0) · WEB-LIVE · WEB-LEAKS · DOC-RACE · TZ-UTC (P1) · DEMO-REGEN ·
README-TRIM · UI-SURFACE first slice (P2) · SCHED-RISK · CARBON-EC3 · PERMIT-CHECK · QA-AGENT ·
LAYOUT-EXPORT (found already shipped) · 5D-BIND (P3).

**Still open from the plan:**
- ✅ **UI-SURFACE №11 tail — CLOSED by the v0.3.441 audit**: the frontend audit's caller scan found no
  zero-caller exported client methods — the earlier flagged names were authoring recipes dispatched by
  string or variant-named surfaces, as suspected. Nothing to delete.
- **№18 later-bucket** *(P3, large)* — SOC 2 feature set (KMS/retention/residency) · IFCX server-side
  read/write + bSI Validation Service in CI · BMS/IoT telemetry (Brick/Haystack) · reality-capture
  progress quantification · viewer tile-streaming upgrade · multiplayer cursors · AR field overlay.
  - ✅ **GEN-SCORE (generative option scoring) SHIPPED v0.3.443** — `option_score.py`: a deterministic
    variant grid around a zoning envelope (`generate_options`, FAR-utilisation steps × building types)
    scored through the platform's own engines — conceptual $/SF (cost) · whole-building embodied-carbon
    benchmarks (carbon) · net sellable area (yield) · FAR/height zoning checks (compliance) — min-max
    normalized within the set, weighted composite, non-compliant options capped and never recommended.
    `POST /design/options/generate` + `/design/options/score`; ⚖ Score-options block on the conceptual
    estimator card (Analytics ▸ Risk & Cost). Deepen later with per-option 5D takeoffs + EPD carbon once
    options carry real models.

**Still open from the velocity program:** DEV-2 tail (CI coverage upload · hotspot docstrings) · REL-3
remainder (`modules.py` CRUD/feeds — needs a DI pass · `main.py` · rest of `data/drawings.py`/`drawing.py`;
✅ `routers/authoring.py` split SHIPPED v0.3.447 — 1350→1030 + docs/analysis/shared leaves, URLs unchanged)
· **REL-4** (decompose the web hotspots — `viewer/app.ts` worst, `main.ts`, `portal.ts`; tools-panel
verify) · REL-5/7 (error handling + verified dead-code) · DEV-3 (build/tsc speed) · COBie/parse robustness.

---

## ⛔ Blocked / gated — what remains and exactly what unblocks it (2026-07-18)

Every item still open after the v0.3.413–450 arcs carries a concrete gate. Nothing below is vague
backlog; each entry names the unblocking event.

**Gate A — live-viewer verification** *(the dev-preview geometry loader stalls at "preparing geometry",
so interactive viewer flows can't be honestly verified in this environment; unblocked by a session with
the viewer running against a live backend):*
- SNAP-KIT phase 2 (osnap glyphs + dynamic-input overlay on the cursor — the tested engine is ready)
- REL-4 (decompose `viewer/app.ts` 4,290 lines / `main.ts` / `portal.ts` — a blind refactor of the
  viewer entry is imprudent without runtime proof; pure-leaf extractions continue opportunistically)
- SHEET-VIEWPORTS interactive paper-space editor (drag viewports — the server endpoints are live)
- SITE-1 multi-scale composed BIM↔GIS UX (the overlay loaders ship) · viewer tile-streaming upgrade ·
  multiplayer cursors · AR field overlay

**Gate B — upstream dependencies:** IFC5/IFCX geometry **write** (web-ifc/Fragments write-path) ·
bSI Validation Service in CI (external service account).

**Gate C — paid/networked services:** COST-DB cloud ingest (massing.cloud subscription + signed
bundles; the custom + public importers ship) · APS RVT bridge beyond the shipped flag (paid Autodesk) ·
SOC 2 feature set (KMS/retention/residency — cloud infra) · BMS/IoT telemetry (needs a
Brick/Haystack-speaking building source).

**Gate D — large optional builds** *(complete prerequisites ship today; each is a deliberate,
multi-session build to start when wanted):* coupled-frame FEM solve (the analytical model is
solver-ready) · server-rendered 3D hero · VIZ-U1 Unity bridge · reality-capture progress quantification ·
the 🔮 frontier bets (PROFORMA-LIVE, COST-AGENT, BOARDS, ENV-1, READY-AGENT, RISK-BOARD).

## 🧭 CAD-UX lessons (2026-07-17, from the OpenAEC / Open CAD Studio study)

Open CAD Studio (Hakan Seven; native-DWG AutoCAD-workalike, Rust+iced+wgpu) and the OpenAEC Foundation
(~60 repos, Rust-core→WASM, Tauri, IFCX bet) are on adjacent paths. We're an all-in-one so we won't split
into micro-apps, but the **CAD authoring UX** and a few dev practices are worth adopting. Feasibility-ordered:

1. ✅ **CADCMD — a CAD command line over the viewer — SHIPPED v0.3.430; polar/relative coords v0.3.439** *(★★★★ · the user's top ask)* —
   a typed command bar in authoring mode driving the existing GUID-stable edit recipes: AutoCAD-style
   grammar (`WALL`, `COLUMN`, `SLAB`, `GRID`, `DIM`…) + single-letter aliases (L/C/M/Z) + spacebar-repeat
   + up-arrow history + prompt-driven flows ("Specify first point"). Every drafter already knows this;
   it's scriptable for free. Builds on the shipped AI command bar (reuse its input + recipe dispatch).
2. ✅ **SNAP-KIT — COMPLETE v0.3.453** *(★★★★)* — phase 1 (v0.3.434: pure engine + 45° polar tracking)
   + phase 2 (v0.3.453: **typed dynamic input** — `6` / `<30` / `6<30` mid-draw with a HUD, beats every
   automatic snap — plus snap-kind glyphs ◻/∠/◇/⌨ on each placed point). **Live-verified to the IFC**:
   a wall drafted with typed `8<60` landed at exactly 8.00 m @ 60.0° in the published model. The live
   loop also surfaced + fixed two interaction bugs (draft-beats-measure priority; raycast timeout).
3. ✅ **AUTHOR-MATRIX — SHIPPED v0.3.431 — a public authoring-coverage matrix** *(★★ · like OCS's COMMANDS.md)* — one markdown
   table (IFC classes × create/edit/delete/parametrize, implemented/partial/missing) in the repo + docs.
   Honest maturity signal for users, work-picker for contributors. Cheap; generate from `edit.RECIPES`.
4. ✅ **CLIENT-LIMITS — SHIPPED v0.3.433 — [`docs/client-vs-server.md`](client-vs-server.md)** *(★★)* — what runs in the browser vs the Python
   service and why. Bank OCS's two transferable landmines: **WebGL2 has no vertex-stage storage buffers**
   (custom hatch/linetype must use triangulation/textures or gate on WebGPU) and **wasm is single-threaded
   without SharedArrayBuffer** (already why the viewer needs coi-serviceworker). Doubles as arch docs.
5. ✅ **VIEWER-FUNNEL — SHIPPED v0.3.445** *(★ · positioning)* — the landing (massing.build) now names the
   demo a **free in-browser IFC viewer & model checker**: hero CTA + a dedicated section (open-your-IFC ·
   read-only model QA · "no signup, no install, no upload — your model never leaves your machine") with
   the upgrade path to the desktop app / full stack. Visually verified.
6. ✅ **PLUGIN-REGISTRY — SHIPPED v0.3.444 — manifest-gated recipe plugins** *(★★★)* — OCS's best design,
   adapted: a plugin is a directory with a `plugin.json` manifest (name/version/`api_version`) + a
   `register(api)` entry that adds **namespaced GUID-stable recipes** (`<plugin>.<recipe>`) into the same
   `edit.RECIPES` registry every authoring surface dispatches (POST /edit, CADCMD, AI bar, MCP
   `run_recipe`) — and they appear in the authoring matrix automatically. Three hard gates: **opt-in**
   (`AEC_PLUGINS_ENABLED=1` — plugins execute Python at load), **api-version MAJOR match** (refused with
   a reason otherwise), **collision refusal** (never overwrite). Idempotent reload; refusals are data +
   logs, never fatal. `plugin_registry.py` · `GET /plugins` + admin-gated `POST /plugins/reload` ·
   template + worked example at `plugins/`. *(Later: curated registry.json + process isolation.)*
7. ✅ **MCP-PACK — SHIPPED v0.3.435 — Massing MCP server + skill/docs pack** *(★★)* — the MCP catalog grew
   8→14: the authoring + analysis engines are now agent-drivable (`list_recipes`, `run_recipe`,
   `schedule_risk`, `carbon_report`, `permit_readiness`, `drawing_qa`), so an agent is a first-class
   *author*, not just a reader. The two write tools (`create_rfi`, `run_recipe`) carry the same editor-role
   gate as their HTTP routes. A drop-in Claude skill pack lives at `docs/mcp-skills/` (SKILL.md + draft-RFI /
   run-takeoff / drive-a-recipe playbooks). Builds on SEC-MCP (v0.3.417 authz).
8. ✅ **SHEET-VIEWPORTS — COMPLETE v0.3.454** *(★★★)* — server slice (v0.3.449: `sheet_layout.py` —
   fraction-rect viewports, fixed 1:N true paper scale with Liang-Barsky clipping, per-viewport class
   freeze, presets, shared titleblock SVG/PDF) + the **interactive editor** (v0.3.454: Drawings ▸
   ⊞ Paper space — preset picker, per-viewport controls, live server-composed preview with
   **drag-to-move viewport overlays**, PDF download). Live-verified: a pointer-drag moved a viewport by
   exactly its drag delta and the sheet recomposed; PDF downloaded through the real endpoint.

**Not adopting** (from the same study): the 25-micro-apps split (our all-in-one is stronger); a public
"everything production-ready by <date>" promise (ship dated releases, not dated promises); AI-velocity
without fidelity gates (our per-release suite + IFC-QA roundtrip is exactly the gate they lack); and
IFCX-as-foundation (IFC stays our source of truth; IFCX is a future *export*, tracked in №18).

**📦 Tracked for later — large / needs nimbleness (attack once the cycle is fast; some worktree-forkable):**
SITE-1 open-geodata BIM↔GIS view (🟡 the overlay half ships today — `viewer/gis.ts` loads GeoJSON
vector / GeoTIFF DEM / self-hosted XYZ basemap as georeferenced reference objects; the multi-scale
composed UX is viewer-gated, see ⛔) · ✅ **durable background-job queue SHIPPED v0.3.448** (`jobs.py`: DB-backed
queued→running→done|error rows, per-process worker with crash recovery — orphaned `running` re-queues,
idempotent-handler contract — a `register_kind` registry plugins can extend, `echo` + real `cobie_export`
kinds, enqueue/poll/list endpoints with cross-project 404s; heavy inline paths migrate onto it
opportunistically) · **server-rendered 3D hero** for the package · **COST-DB cloud ingest** (public-source + signed
bundles) · **coupled-frame FEM solve** (the analytical model is complete + solver-ready, so this is a big
optional build) · VIZ-U1 Unity bridge · IFC5 geometry write (upstream-blocked) · the frontier bets below
(PROFORMA-LIVE, COST-AGENT, BOARDS, ENV-1, READY-AGENT, RISK-BOARD). Detail in
[🔮 Frontier](#-frontier--2026-07-research-round-2--net-new-bets) + [🏗 Enterprise gaps](#-enterprise-gaps-audit-2026-07).

---

## 🎨 UI/UX Master Pass — the designer's modeling workspace

Research-backed (Bonsai/IfcOpenShell · Revit + Dynamo/pyRevit · SketchUp + 3D Warehouse · Tekla component
catalog · ArchiCAD GDL/Info-Box). **Why now:** the model rail has grown to **~97 tools across 7 loosely-named
collapsible sections**, organized by accretion, not by how a designer models. Two shipped capabilities are
under-surfaced: **interactive annotation** (the UX-2 recipes ship, but need the ribbon home) and the **content
library** (scattered across 🏗 CONTENT-1, the family catalog, the type browser rather than one palette).

**Transferable patterns adopted:** task-grouped ribbon left-to-right by lifecycle (Revit tabs); **type-first
"Add" flow** (Bonsai `+Add IfcWallType`, Revit Type Selector); **instance-vs-type split** in Properties; a
**Project-Browser tree** as the model spine; a **catalog content panel** with search + `tag:`/`type:` filters,
Recent, thumbnails, editable tags; a **pick content → pick host → auto-build** placement flow; a live
**inference/snap engine + typed dimensions** (builds on shipped E1 inference); an **Info-Box** contextual strip;
**UI as a thin wrapper over scriptable GUID-safe recipes**; an **appendable IFC-as-library** model.

- 🟡 **UX-1 (first slices) SHIPPED v0.3.341–342** — (a) tool sections labelled + ordered by the modeling
  lifecycle (Data · Build · Analyze & Coordinate · Document), "More tools" flowing Build → Analyze → Document;
  (b) the interactive annotation tools + content library surfaced as their own **✍ Annotate** and **📚
  Library** groups (out of the Advanced-fabrication fold). **Ribbon tabs SHIPPED v0.3.370** — a lifecycle
  tab-strip (All · Build · Analyze · Coordinate · Document · Data) filters the sections to one phase.
  **UX-1 remaining:** physically merging the Build sub-sections into one Build tab (vs. tab-filtering).
- **UX-1 — Ribbon consolidation** *(M · high)* — regroup the ~97 tools into a lifecycle task ribbon replacing
  the 7 accreted sections: **Build/Author** (grids·levels → walls·columns·slabs·roofs·families·MEP; sloped/
  mesh/sandbox under an "advanced" fold) · **Annotate** (UX-2) · **Library** (UX-3) · **Analyze** (code/EBC ·
  egress · decision-readiness · labour · model-health) · **Coordinate** (clash · IDS/BCF · MEP connectivity ·
  phasing) · **Document** (drawings · sheets · schedules · issuances) · **Data** (properties · classifications ·
  exports · connections). Keep the persona-primary/"More tools" collapse; re-key it to these groups. Reuses the
  `section()` helper in `viewer/app.ts`.
- **UX-2 (remaining) — inference-snapped annotation placement** *(M)* — the interactive `IfcAnnotation` tools
  (text notes ✅ · dimensions ✅ · element-aware tags ✅ · revision clouds ✅, all rendered onto the plan) ship;
  what's left is **SketchUp-style snap to endpoints/edges/midpoints as you place** (extends the shipped E1
  inference engine) + live guide-lines.
- 🟡 **UX-3 (first slice) SHIPPED v0.3.343** — the 📚 Library opens one **searchable unified palette** merging
  the CONTENT-1 content catalog + the W10-1 family types in a single filterable list (search across name /
  class / category / phase; click-to-place at E,N; inline mesh import). **Operators + Recent SHIPPED
  v0.3.368** — `type:`/`class:`/`category:`/`discipline:`/`tag:` scoped search + a per-project Recent
  bucket. **Remaining:** thumbnails, drag-to-place, pick-host→auto-build, appendable IFC libraries.
- **UX-3 — Unified Library palette** *(L · high)* — one browsable **content panel** unifying the W10-1
  type/family system + the CONTENT-1 catalog (logistics/furniture/landscaping) + external IFC/glTF import: a
  **thumbnail grid**, case-insensitive search with `tag:`/`type:`/`discipline:` filters, a **Recent** bucket,
  predefined groups, and **click/drag-to-place**. Hosted content uses **pick-item → pick-host → auto-build**
  (a door picks its wall; a steel connection picks its beams). **Appendable IFC libraries** — load types
  (+ profiles/materials) from any IFC file. New `library` client + a **Library** rail group. Folds in the
  CONTENT-1 remaining (curated CC0 seed + thumbnail palette) and H1 (CC0 furniture families + PBR materials).
- 🟡 **UX-4 (Info-Box) SHIPPED v0.3.346** — an always-visible **Info-Box** strip on the 3D canvas showing the
  selected element's name · class · level · discipline (with the tree colour dot), regardless of the active
  rail tab.
- 🟡 **UX-4 ("Script this") SHIPPED v0.3.348** — a ⌨ toolbar button that reveals the GUID-safe **recipe plan**
  behind a plain-English command (the verbs the AI bar + sandbox share) and applies it — the code interface
  made discoverable. **Project-Browser spine SHIPPED v0.3.369** — the model browser opens with a Views ·
  Sheets · Schedules nav strip above a labelled Model tree. **UX-4 remaining:** the type-library branch in
  the browser + assembling the full one-shell layout.
- **UX-4 — Designer workspace layout** *(M · high)* — assemble the four resources into one shell: a
  **Project-Browser spine** (spatial tree + views/sheets/schedules + the type library — extends the model
  browser), the docked **Properties** palette with the **instance-vs-type split** (extends P6d), the **Library**
  palette (UX-3), the **task ribbon** (UX-1), plus an **Info-Box** contextual strip and a visible **"Script
  this" affordance** that opens the command bar/sandbox on the same recipe verbs. A11y + mobile-viewport pass
  folded in.

*Sequence: UX-1 (reorg) → UX-3 (library) → UX-2 remaining (snap) → UX-4 (assemble). Each ships as its own
verified release.*

---

## 🧱 Wave 11 — Master Builder (remaining depth)

The architectural spine, guardrails, and drawing generator ship; these deepen geometry, drawings, and
code-intelligence.

**Construction documents**
- ✅ **Plan-render fix SHIPPED v0.3.345** — `drawings.plan_svg` room tags + door/window callouts filter to
  the cut level (no more cross-level label stacking), and plans carry a titleblock band (title box · graphic
  scale bar · north arrow · general notes; cut-plane AFF + grid). Room names XML-escaped.
- ✅ **Composed-sheet cap SHIPPED v0.3.347** — `default_sheet` no longer renders a plan per storey (30-storey
  tower timed out); caps to ~4 sampled levels + takes an optional `storey` for a single-level sheet.
  `sheet.{svg,pdf}?storey=…`.
- **C6 (remaining)** — reference-line datums (`IfcReferent`/`IfcVirtualElement`) + **"drawn detail follows
  LOD"** poché (representation selection + `IfcMaterialLayerSet` poché + annotation density → schematic
  single-line ↔ CD layered poché). Permissive libs only (no AGPL).
- **D2** — **routed egress / life-safety plans** (path-trace over the W9-4 semantic graph, not just tabulated).
- ✅ **D5 SHIPPED v0.3.354** — detail callouts render on the **PDF** sheet path (NCS divided-circle bubble +
  leader + DETAILS legend), and the bubble carries a **real sheet ref** (doc `Identification`, else the
  sheet number derived from the `Location` basename) instead of a placeholder.
- **D8 follow-ups** — wire COMcheck/energy-doc + A117.1 clearance checks into the approvability pre-flight and
  round its findings to BCF.
- **`Pset_Massing_SpecLink` breadcrumb** — the remaining Track-D carrier.

**Geometry depth → LOD 350/400**
- **F0b** — derive **Box / Axis / FootPrint** geometry on demand from `Body` (consumed by the C drawing gen).
- **B3 (remaining)** — wall **Axis** representation + arbitrary clip planes (gable peak mid-span).
- **B5 (next)** — fasteners/hangers as real assemblies + connection geometry (extends the shipped
  `connect_elements`/`element_connections`).

**Open-ended authoring (the moat)**
- **A2** — **RAG index** over ifcopenshell / IFC docs to ground code-gen (extends the shipped sandbox +
  scene-digest).

**Master-builder UX**
- **E2** — **type-a-dimension-while-drawing** (VCB). **E3** — **sketch-to-BIM push/pull** (2D profile →
  extrude). **E5** — **direct-manipulation parametric handles**. **E6** — **recipe-log design-option branches**
  (the recipe log *is* the undo stack; S4 undo/redo ships). **E7** — **live schedules / quantities as you
  model**. **E8 (remaining)** — model-aware guardrail checks (host is actually a wall, storey exists — needs
  the model at precheck time).

**Content library**
- **H1** — seed **CC0 furniture families + PBR materials** (CC0/CC-BY only — ambientCG, Poly Haven, Poly Pizza,
  Quaternius, Kenney, AMD MaterialX), attribution + license stored per asset. *Folds into UX-3.*

**License guardrails (firm):** `ifcopenshell` + geom serializers are **LGPL** — safe to depend on.
Reimplement drawing/annotation *techniques*, never vendor GPL code. SVG→PDF/DXF via permissive libs only
(**no AGPL** — no PyMuPDF). CC0 asset sources vetted per-asset. IDS is an open buildingSMART standard.

## 🤖 AI-MCP / NL authoring (remaining)

S1–S4 ship (deterministic baseline → multi-step LLM interpretation → confirm-before-apply → undo/redo).
- **S4 (next)** — multi-step **undo grouping** (one apply-all = one undo).
- **S5** — multi-turn **clarifying questions**.
- **Read tools** (quantities / schedules / clashes / violations) + an actual **MCP server surface**.

## 🏛️ Wave 10 — authoring-suite leftovers

- **W10-2** — **parametric family generators** (code-defined; typed params + optional formulas; profile library
  I/L/T/U/C/rect/circle + swept/boolean primitives so doors/windows/columns/casework are *generated*, not
  boxes). Freeform via an optional **build123d (Apache-2.0) / OCP (LGPL)** track. *Pure ifcopenshell for the core.*
- 🟡 **W10-4 sizing psets SHIPPED v0.3.349, flow SHIPPED v0.3.355** — `add_mep_run`/`add_riser` write
  `Pset_Massing_MEPSizing` (NominalSize_mm · Shape · Length_m · optional FlowRate/FlowUnit — default unit
  CFM/GPM/A by system) so schedules/QTO/sizing read size + design flow without geometry. *Remaining:
  coincident-port auto-connect.*
- **W10-5** — **annotation & tagging layer** — *largely delivered by UX-2 (notes/dims/tags/clouds on plans);*
  finish section/elevation annotation views.
- 🟡 **W10-6 schedule CSV SHIPPED v0.3.351, Qto depth v0.3.356** — door/window/room schedules export to CSV
  (`schedule.csv?kind=`); the room schedule now carries `IfcElementQuantity` depth (Perimeter + Volume from
  `Qto_SpaceBaseQuantities`). *Remaining: keynote-legend schedule view.*
- 🟡 **W10-7 frame SHIPPED v0.3.357** — **structural analytical model** (`IfcStructuralAnalysisModel`): the
  `derive_analytical` recipe idealises the physical frame (columns/beams) into `IfcStructuralCurveMember`s
  (IfcEdge topology) tied at shared `IfcStructuralPointConnection` nodes, linked back to the physical
  elements, with a permanent-G self-weight load case; idempotent; served at `GET .../analytical`.
  **Surface members SHIPPED v0.3.358** — slabs/roof decks → `IfcStructuralSurfaceMember` (planar
  `IfcFaceSurface`). **Wall surface members SHIPPED v0.3.391** — load-bearing (shear) walls → vertical
  mid-plane surface members (partitions skipped via `Pset_WallCommon.LoadBearing`). **Load activities
  SHIPPED v0.3.390** (`apply_structural_loads`). **Supports SHIPPED v0.3.392** (`apply_structural_supports`
  — pinned/fixed base `IfcBoundaryNodeCondition`). Members + loads + supports = a complete, solvable
  analytical model. *Remaining: coupled-frame (FEM) solve.*
- **W10-9** — **parametric constraints & dimensional locks (the hard one)** — no IFC representation; store in a
  sidecar, solve, bake to IFC. Start with 1D/alignment locks. **License:** FreeCAD's **planegcs (LGPL,
  extractable)**; avoid python-solvespace (GPL) and OpenSCAD (GPL).

## 🔬 Wave 9 — research-scan leftovers

- **W9-4 (harder half)** — ingest **specs / drawings / code documents** as graph nodes + **NL→graph query with
  cited sources** (GUID + spec page + code section) — the explainability substrate under W9-2 code-checks and
  the RFI-0 NL-QA layer.
- **W9-5 (L part)** — smooth **equipment motion along paths** as the 4D slider advances + swept crane-reach
  clash.
- 🟡 **W9-6b FF&E BOM SHIPPED v0.3.350** — `content.furniture_bom` counts placed furnishings by item + level
  (`GET /projects/{pid}/ffe-bom`) — the auto-BOM half. *Remaining: the procedural headcount-program →
  `IfcSpace` zones + auto-furnish generator.*
- **W9-7 — AI 2D-PDF auto-takeoff** *(optional / paid, flagged bridge)* — manual calibrated PDF takeoff ships;
  AI auto-extraction is a flagged bridge like the paid RVT path, never core.
- **W9-8 — NL imperative authoring** — folds into the AI-MCP track.

---

## 🔮 Frontier — 2026-07 research round 2 + net-new bets

Ranked most-actionable first. Competitor names kept out — capabilities described directly (standing directive);
interop targets / content platforms / open standards named where they're integrations.

### 📊 Estimating → 5D depth
- ✅ **EST-1 crew-days→duration SHIPPED v0.3.339** — the labour estimate now rolls per-line crew-days up by
  trade group into a **working/calendar-day schedule duration** (`crews` = parallel crews per trade shortens
  it; trades sequential = conservative critical path). Flows through `labor_estimate`/`full_estimate`/
  `from_model`; `?crews=N` on `/estimate/labor`.
- **EST-1 (remaining)** *(M)* — full **QTO integration** (drive the activity quantities from the real
  `aec_data.qto` takeoff, not just element dimensions) + wire the duration into the CPM/Gantt schedule.
- ✅ **COST-DB backbone SHIPPED v0.3.337** — `cost_datasets` + `cost_items` schema, project `cost_dataset_id`
  pin, an offline `PublicDataImporter` (`cost_db.py`) building a `public_local` vintage from the shipped
  benchmark rates, a vintage resolver (latest/exact/nearest-fallback/strict) + `is_latest` management, and the
  `/cost/datasets` + `/projects/{pid}/cost-vintage` endpoints.
- ✅ **COST-DB estimate integration SHIPPED v0.3.338** — the model estimate (`/estimate/from-model` +
  `/qto/by-floor`) prices the takeoff **through the project's pinned vintage** (its rate map as overrides) and
  returns the `cost_vintage` it priced with — reproducible estimates.
- ✅ **COST-DB localization + escalation SHIPPED v0.3.436** — `cost_db.rates_for_project` takes the pinned
  vintage's national-average rates and makes them project-real **offline**: × the project region's cost index
  and escalated from the vintage year to the construction midpoint (reusing the shipped market table +
  `market_intelligence.escalation_factor`). The takeoff (`/qto/by-floor`, `/estimate/from-model`) and the
  `/cost-vintage` endpoint carry the `cost_adjustment` (location index · escalation · combined factor); region
  & timeline come from the project's `market_assumption`. **Remaining build-order steps:** the `massing.cloud`
  CloudDatasetImporter (signed bundle), real public-source ingest (BLS/FRED/DoD/Census), per-county
  location-factor / PPI-index DB tables, delta sync, Ed25519 signatures.
- ✅ **COST-DB custom cost-book import SHIPPED v0.3.440** — a firm installs its **own** rates as a
  `custom`-origin vintage (`cost_db.import_custom_vintage` + `parse_cost_rows`): `POST
  /cost/datasets/import-custom` takes a flat `{ifc_class: rate}` map or `rows: [...]`, MasterFormat-codes
  any gaps off the classification spine, replaces the same (year, quarter) in place on re-upload, and sets
  it latest — so a project prices through the firm's negotiated/historical costs (localized + escalated
  like any vintage). Offline. This is the "+ import" the task title always implied.
- **COST-DB — vintage-versioned cost database + import** *(L · high)* — a local, **vintage-versioned (by year)**
  cost database populated from **either free public sources (BLS/FRED/DoD-UFC/Census — offline-first) or the
  `massing.cloud` subscription API**, behind one `DatasetImporter` interface. Projects **pin** to a specific
  vintage so every estimate is reproducible; import `latest` or a specific historical year with a configurable
  fallback (`strict`/`nearest`); cloud bundles are **checksum-/signature-verified** before a transactional
  upsert; older vintages **escalate forward** via stored PPI series. Feeds 5D cost / estimating / GC-portal
  budget / FCA / Last Planner through the pinned vintage. Open-source ships the **public importer + adapters
  only** — proprietary data (1build/RSMeans) arrives solely via the subscriber's authenticated cloud pull,
  never committed to the repo. Full spec + schema + build order: **[cost-db-import-plan.md](internal/research/cost-db-import-plan.md)**
  (server side: `massing_cloud_plugin_plan.md`; location engine: `massing_location_cost_import_plan.md`).
  *Build order: schema → PublicDataImporter (offline spine) → vintage resolver + project pinning →
  CloudDatasetImporter (manifest/bundle/verify/upsert) → subscription detection + public fallback → delta sync →
  Ed25519 signatures → escalation-forward.*

### 🚫 RFI-prevention (the openBIM information-delivery moat)
- ✅ **RFI-0 missing-dimension detection SHIPPED v0.3.336** — a 5th gap source in `decision_readiness`:
  doors/windows with no `OverallWidth`/`OverallHeight` + rooms with no floor area → ranked `dimensions`
  gaps that ride the existing BCF promotion.
- 🟡 **W9-4 doc-graph SHIPPED v0.3.359** — the cited-source substrate: `docgraph.build` folds spec-section
  (classification code) + document (sheet-ref'd) nodes onto the model graph (`specified_by`/`documented_by`);
  `element_sources(guid)` returns one element's cited provenance (spec sections · documents · location).
  Served at `GET .../doc-graph` and `GET .../elements/{guid}/sources`.
- ✅ **RFI-0 NL-QA SHIPPED v0.3.360** — `POST /projects/{pid}/rfi/qa` routes a plain-language question to the
  doc-graph / decision-readiness and answers with cited sources ("what governs \<element\>?" → spec + detail
  + level; "what's blocking approval?" → ranked gaps + fixes; "what is spec section 05 12 00?" → governed
  elements). Deterministic (no API key needed); every claim carries its source.
  *Remaining depth: external spec/code-document text ingestion (page-level citations) + LLM rephrasing.*

### 🎮 Visualization — Unity as the optional bridge
- **VIZ-U1 — Unity/Pixyz IFC → WebGL presentation build** *(L · optional/paid/flagged)* — Pixyz imports **IFC
  natively** (GlobalId + metadata), Unity exports a **browser WebGL build** (no cloud-GPU stream) — a
  high-fidelity presentation mode as a browser build. Proprietary seat-licensed → optional, flagged, one-way
  (viz only), never the default viewer. The on-mission path stays glTF export (ships) + three.js PBR (VIZ-2).

### 🌍 BIM-GIS digital twin
- **SITE-1 — multi-scale BIM ↔ GIS view** *(M · ★★★★)* — a browser view composing the building IFC with its
  regional GIS context (parcel, zoning envelope, terrain, neighbours) from open geodata (GeoJSON / parcel APIs).
  Validated by an open-source (AGPL) BIM+GIS peer — reimplement techniques, never vendor AGPL code. Feeds
  authoring + the code/zoning engine + auto site-context ingestion (setbacks/height/FAR → buildable envelope).

### 🌦 Early-design environmental performance
- **ENV-1 — wind-comfort / microclimate at massing** *(M · med)* — beside the shipped solar-access analysis, a
  simplified pedestrian wind-comfort pass (prevailing-wind exposure, wind-shadow) for early "is this a wind
  tunnel?" feedback. Offline + approximate (not CFD); a CFD-grade version stays a flagged bridge.

### 🧩 Authoring surface parity
- ✅ **AUTH-VS — visual node-based authoring** *(L · parity)*. **Engine SHIPPED v0.3.363** +
  **canvas SHIPPED v0.3.367** — `nodegraph.execute_graph` runs a recipe graph (Kahn order + `{"$from": id,
  key?}` refs; `POST /edit/graph`), and the viewer ships a draggable node-graph editor (`nodeCanvas.ts`):
  palette → drop nodes, wire output●→input○ (auto-injects the `$from` ref), Run graph → one GUID-stable
  publish. Verified live: launcher, palette (7 recipes), add/drag/wire/ref-injection.

### 🚀 Model-authoring & collaboration frontier
- 🟡 **COLLAB-1** *(L · ★★★★★)* — **real-time multiplayer co-editing**. **Awareness slice SHIPPED v0.3.361**:
  a model-edit SSE stream (`GET .../model/stream`) + collab snapshot (`GET .../collab`) that live-reloads a
  second viewer after another user publishes and shows the presence roster; in-model comments already ride
  the GUID-anchored Topic/Comment model. **Edit-lock SHIPPED v0.3.362** — `/edit` takes an optional
  `base_source`; a stale write (another user published since) is rejected 409 instead of silently
  overwriting. *Remaining: per-user cursor/selection overlays and the client-side viewer wiring.*
- **PROFORMA-LIVE** *(M · ★★★★)* — tighten the **model↔proforma live loop**: yields/unit-mix/parking/efficiency
  + cost recompute **inline as you model**, not only in the portal.
- **COST-AGENT** *(M · ★★★★)* — an estimating agent that re-estimates on each geometry change + learns from
  historical cost data (companion to AI-MCP + estimating→5D).
- **BOARDS** *(M · ★★★½)* — a "Boards" presentation surface: styled design-option views, shadow studies,
  auto-generated stakeholder decks as first-class artifacts alongside sheets.
- **NL-QA** *(S · ★★★½)* — built-in NL QA recipes once AI-MCP matures ("audit issues + suggest fixes," "check
  room accessibility," "normalize inconsistent Psets"). Maps onto code-check + model-hygiene + RFI-0.
- *Validated / overlap (verify, don't rebuild):* bulk IFC Pset editor (⊂ override layers), manufacturer
  product-configurator → IFC type (⊂ families/types), in-context comments (⊂ BCF).

### 🗂 DISC — unified discipline tree (remaining, optional)
DISC-1…4b shipped (colour palette, full IFC coverage, `discipline_tree()` served, color-by-discipline viewer,
estimate discipline rollup, one canonical `aec_data/disciplines.py` source, fire-alarm + telecom recipes + tool
buttons, tower rebuilt with all 8 disciplines). Optional remnants:
- ✅ **DISC-coverage SHIPPED v0.3.352** — `/elements/by-discipline` returns a **coverage** view over the
  tree (every standard discipline present/absent + count, `disciplines_covered`/`_total`, `missing` list) —
  a completeness lens over the property index, no geometry parse.
- **DISC-poché** — an opt-in **colour-by-discipline mode** for the 2D plan/PDF poché (today the poché is
  deliberate per-class architectural convention).
- ✅ **DISC-cw SHIPPED v0.3.353** — context-aware curtain-wall member classification: an `IfcMember`/`IfcPlate`
  aggregated under an `IfcCurtainWall` (or `IfcRoof`) now reads Architectural, not Structural. The property
  index records each element's aggregating `host` class; `discipline_of_ifc_class(cls, host)` consults it.

---

## 🔐 Sign-in & first-run onboarding

**Goal:** make social sign-in the prominent default and sequence it into the tutorial — *without* a hard gate
(the app runs free/offline; a signup wall before the "aha" moment craters top-of-funnel). Google + Microsoft
OAuth, MFA, SSO/SAML/SCIM, and a first-run welcome modal + ≤5-step tour already ship. This is **prominence +
flow**, not new auth. Files: `apps/web/src/ui/onboarding.ts`, `apps/web/src/account/accountUI.ts`.

**First slice (one sprint):**
- **B1 — optional sign-in as the welcome modal's first panel** *(M)* — a headline + prominent **Continue with
  Microsoft/Google** (only configured providers, via `authProviders()`), a quiet "More options," and a visible
  **"Explore without an account →"** dropping to the quick-start cards. Prominent, never a wall.
- **B2 — sign-in → tour** *(S)* — after sign-in *or* "Explore without an account," auto-launch the tour and
  `markOnboarded()` once.
- **A1 — Google + Microsoft as co-equal visible defaults** *(S)*. **A2 — collapse everything else behind "More
  sign-in options"** *(S)*. **C1 — reorder the sign-in modal to lead with one big provider button** *(S)*.

**Fast-follow:** **B3 — role self-selection after sign-in** *(M)* · **B4 — keep the tour ≤5 steps** *(S)* ·
**C2 — value-moment "Sign in to save your work" prompt** *(S)*.

**Deferred (explicit triggers):** **A3 — Sign in with Apple** (only alongside a native iOS wrapper) ·
**A4 — skip Facebook/GitHub** (wrong audience; LinkedIn only on demand) · **B5 — persistent quick-start
checklist** *(L)*.

*Privacy/mission guardrails: keep the guest/offline path fully functional; no telemetry before consent; SSO
buttons stay config-gated.*

---

## 🏛️ Future inbox — building-code library (jurisdiction-aware)

The copyright-safe strategy: **own the rules, facts, and checks; deep-link out for prose; license prose later.**
**GREEN:** section numbers/titles/edition years, jurisdiction→adopted-edition adoption facts, numeric
thresholds/formulas (facts of law — what `codecheck.py` encodes), our own paraphrased rule content. **RED:**
scraping/redistributing ICC/ASTM verbatim prose. *(CODE-1 catalog, CODE-2 occupant-load, CODE-3 first slice,
CODE-EBC ship — see the archive.)*
- **CODE-1 follow-ups** — extend the per-state adoption seed (ICC adoptions DB + DOE energy-code status) + per-
  project jurisdiction storage.
- ✅ **CODE-3 SHIPPED v0.3.344** — `apply_rules(ibc_edition=…)` rewords the Track-D detail-rule citations to
  the project's resolved adopted IBC edition (an exterior window cites the actually-adopted §1404.4 edition);
  threaded through the `apply_detailing_rules` recipe. *Remaining: auto-resolve the edition from the project
  jurisdiction at the /edit call site.*
- **CODE-4** *(S)* — local-amendment overlay + manual-entry UI (store *our summary* + a link).
- ✅ **CODE-5 SHIPPED v0.3.340** — `codecheck.code_ids` emits the machine-checkable subset of the applicable
  code requirements as buildingSMART **IDS 1.0** (rated-element `FireRating` + space area + envelope U-value,
  driven by the fired code rules); `GET /codes/ids` (+ `.ids` download). Validates an IFC in any IDS checker.
- **CODE-6** *(L, flagged/paid)* — licensed prose integration behind a flag + cost warning; only after CODE-1–3
  prove demand.

## 🎮 Future inbox — viz export (one-way, never core)
- **VIZ-1** *(S · on-mission)* — glTF/`.glb` (+ optional `.udatasmith`) export. **Largely ships — confirm parity.**
- **VIZ-2** *(S/M · on-mission)* — **three.js PBR "presentation mode"** (IBL/HDRI, SSAO/bloom, baked lightmaps),
  offline + license-free.
- **VIZ-3** *(L · paid/flagged)* — pixel-streamed cinematic mode. **VIZ-4** *(L · paid/flagged)* — VR
  design-review bridge. Optional interop tiers, never the default viewer.

---

## 🔒 Security backlog

- ✅ **SEC-DEP-1 / SEC-DEP-2 resolved** (Capacitor 6→7 cleared the tar CVEs, v0.3.312; the glib/Tauri gtk3
  unsoundness dismissed `not_used` — Linux-desktop-only, no gtk3-compatible fix, we never call
  `VariantStrIter`). **Security tab: 0 CodeQL + 0 Dependabot alerts.** Detail in the archive. Continue CodeQL
  monitoring on each push.

---

## 🚧 Blocked, deferred & non-goals

**④ Blocked upstream — revisit when the dependency lands**
- **IFC5 / IFCX *geometry* write** — the **data** write-path shipped (v0.3.213); only geometry authoring waits
  on web-ifc / Fragments IFC5 support (still alpha). Track buildingSMART.
- **Native mobile shell** — a **Capacitor wrapper** of the offline PWA (needs a macOS/Xcode + Android-SDK
  pipeline separate from the Tauri desktop release). PWA "Add to Home Screen" ships; the native shell is the
  fast-follow. See [mobile.md](mobile.md).

**⑤ Deferred by decision — integrate, don't build (pursue on customer pull)**
- **Regulated syndication depth** — the licensed stack (KYC/accreditation, transfer-agent recordkeeping, Reg-D
  engine, escrow, the token) stays counsel-gated. Our origination-side **connector shipped v0.3.213**
  (`securities_bridge`, never moves money); build deeper only when a customer actually raises/syndicates.
  ⚖️ *Not legal advice; the partner is the licensed entity.*

**⑥ Intentional non-goals — documented rationale (not gaps)**
- **In-browser IFC authoring** — **REVERSED (2026-07): now a first-class, shipped capability.** Blender/Bonsai
  remains an *optional* advanced/interop editor. **`.mpp` (MS Project) parsing** — proprietary OLE binary; path
  is *Save As XML/CSV → import*. **Custom Revit plugin** — the certified `revit-ifc` exporter covers it.
- **A4/A5 portal-core split** — the catalog↔nav orchestration is deliberately coupled; further extraction trades
  readability for indirection.
- **Out-of-scope-by-design operations integrations** — live ENERGY STAR / BAS / BMS (flagged stubs only), full
  institutional reporting packs, space/move management (CAFM), 1031 tooling, JWT-revocation blacklist + Redis-
  backed presence (known limits, tracked in PRODUCTION_CHECKLIST).

---

## 🔎 Research-2 additions (2026-07)

From the 2026-07 research round (pics12 images + 9 web sources: DDS-CAD, OpenTakeoff, Geopogo, Fieldwire,
BuildPass, pyRevit patterns, the BIM+GIS infographic). Only genuinely on-mission, feasible items kept;
license notes inline. Skips: AutoCAD-LISP repos (DWG-bound, low value), weld-symbols (unlicensed niche),
Geopogo-as-product (closed Unreal — its *context-ingest* idea folds into SITE-1), full mobile field app.

**Authoring & drawings (highest value):**
- **KEYS — Revit-style keyboard shortcuts** *(S/M · ★★★★★)* — 2-letter authoring shortcuts (WA/CL/DR/CS/…)
  over the recipe+tool actions so Revit-trained users are instantly fast. *(IMG_0259 shortcut cheat-sheet.)*
- ✅ **VIEW-RANGE — plan view-depth — SHIPPED v0.3.383** — `plan.svg?view_depth=<m>` shows foundations/
  footings below the cut as dashed hidden lines (`below_footprint_baked`); the Top/Cut/Bottom/View-Depth
  model vs. one cut_z. *Remaining: per-plane visibility control + the footprint sheet/PDF path.* *(IMG_0247.)*
- **PREFLIGHT — model-health / QA issuance gate** *(S/M · ★★★★)* — one-click audit (orphaned GUIDs · missing
  classifications · unplaced elements · open BCF · param completeness) as an issue-the-set gate. *(pyRevit.)*
- **SHEET-LINK — hyperlinked callouts across the sheet set** *(S · ★★★)* — clickable detail/section bubbles
  cross-link sheets in the PDF/SVG viewer. In-house on sheetgen + markup. *(Fieldwire plan-hyperlinking.)*

**Estimating & engineering:**
- **TAKEOFF-2D — PDF/scan quantity takeoff** *(M · ★★★★)* — browser flood-fill "one-click area" tracer on
  uploaded drawings → feeds the existing 5D estimate; covers the drawings-only case model-takeoff misses.
  *License: OpenTakeoff is Apache-2.0 — vendor or reimplement freely (same Vite/pdf.js/pdf-lib stack).*
- ✅ **MEP-SIZE — MEP engineering checks — SHIPPED v0.3.386** — `GET /mep/sizing` computes flow velocity in
  each authored duct/pipe from size + design flow (`Pset_Massing_MEPSizing`) and checks it pass/fail vs
  accepted limits (ASHRAE ~2500 fpm air, ~8 ft/s water, NEC 392 tray fill); viewer surfaces it with isolate-
  in-3D. *(DDS-CAD technique.)* *Remaining: pressure-loss balancing, thermal load, per-conductor tray fill.*
- **STRUCT-LOADS — load cases + static analysis** *(L · ★★★★)* — extend W10-7 with dead/live/wind/seismic
  `IfcStructuralLoadCase`s + per-member load activities, and lightweight beam/column static
  (shear/moment/deflection) diagrams. *(IMG_0250 structural-analysis primer.)*

**Site / GIS (folds Geopogo + the BIM+GIS infographic into SITE-1):**
- **SITE-1 first slice — open-geodata site context** *(M · ★★★★)* — use the existing georeference to drop the
  model onto a real basemap with **OSM footprints + parcels + terrain DEM + neighbouring-building extrusions**
  as a separate context layer; GeoJSON→extruded blocks. *License: OSM=ODbL (attribution, keep it a separate
  layer), CityJSON/OGC open, Cesium/Google 3D-tiles optional online-only enhancement (viewer stays offline
  per the non-negotiable). No GPL/AGPL/paid-SDK lock-in.* Later: CityGML/CityJSON LoD1–2 read; a full IFC↔
  CityGML *semantic* harmonization is L and deferred.

**Lower-priority / conceptual:**
- **READY-AGENT** *(M · ★★★)* — extend RFI-0 into a proactive agent that surfaces missing approvals /
  unresolved clashes / handover-blockers with cited evidence. *(BuildPass agent pattern.)*
- **RISK-BOARD** *(S/M · ★★★)* — a project-risk register unifying the "hidden" risks (data-quality gaps,
  coordination debt, schedule compression, cost escalation) already computed by hygiene/clash/estimate/schedule
  into one dashboard. *(IMG_0251 construction-iceberg framing.)*
- Market note *(IMG_0258 "Top 20 BIM firms")*: the target audience is infrastructure-heavy (AECOM/Jacobs/WSP/
  Arup…) → reinforces **IFC4.3 infrastructure** depth + **SITE-1** as strategically important, not net-new.

## 🔧 Reliability & hardening (REL)

From a static-analysis pass (blast-radius / churn / coupling). Findings are **leads to verify, not commands** —
ground each in the real code before editing. Ship phases in order; each an independent PR; keep the suite green.
Refactor rule: **no public-API/behavior change** except the (shipped) security phase. Prefer structural fixes
(extract leaf module / invert dependency / DI) over deferred function-local imports.

- ✅ **REL-1 — web portal "cycle" = FALSE POSITIVE (verified 2026-07)** — both legs are `import type`
  (`panelContext.ts:2` imports `PortalHost`, `portal.ts:7` imports `PanelContext`) — stripped at build, so
  there is **no runtime cycle**. The recommended fix (type-only import) is already in place. No change needed.
- ✅ **REL-2 — API `db.py` "cycle" = FALSE POSITIVE (verified 2026-07)** — `db.py` imports neither `modules`
  nor `models`, so it has **no back-edge**; `models.py→db.py` is a clean one-way dep (needs `Base`); and
  `distribution.py→modules.py` is a **deferred function-local import** (the suspected false edge, confirmed —
  it's a lazy import, not a load-time cycle). No module-load cycle exists. No change needed.
- **REL-3 — modularize oversized API/data modules** *(L–XL, one PR each, façade at old path)* — `main.py`→~4,
  `modules.py`→~6 (relieves REL-2), `codecheck.py`→~3, `connectors.py`→~6, `auth.py`→~5, `data/drawing.py`→~4,
  `data/massing.py`→~3, `data/drawings.py`→~5, `bcf_io.py`→~3, `routers/generate.py`→~5. **`ruff`+`pytest`
  green after each.**
- 🟡 **REL-4 — decompose web hotspots** *(L–XL, one PR each)* — `viewer/app.ts` (worst file) split by
  responsibility (render setup / event wiring / data load / UI glue); `main.ts` extract large methods + flatten
  nesting; `portal.ts` split; `api/client.ts` — if generated, fix the generator/config not the output. **Must
  be tested + debugged after each** (perf-sensitive; the geometry preview stall means verify via typecheck/
  lint/vitest + tools-panel technique). **`openModule` O(n·m) fix SHIPPED v0.3.373** — the per-column
  `m.fields.find` linear scan is now an O(1) `Map` lookup.
- **REL-5 — error handling & I/O-in-loop** *(behavior-affecting)* — handle unhandled promise rejections in
  `main.ts`; `errorReporting.ts::installErrorReporting` must not throw during install; batch FS calls out of
  loops in `vite.config.ts::writeBundle` + `scripts/bundle-budget.mjs`; `bridge.py::execute` → dataclass; dedupe
  DRY in `recipes.py`/`vite.config.ts`.
- ✅ **REL-6 — security hardening — SHIPPED v0.3.371** — XXE-safe P6 parser (defusedxml), non-crypto SHA-1
  flags cleared, pillow≥12.3 pin; audit run (npm 0 vulns · bandit HIGH→0 · secret-scan clean). *Remaining:
  optional private-IP/metadata blocking on admin webhook URLs; `cargo audit` (tauri) + `gitleaks` full-history
  scan in CI when those tools are available.*
- **REL-7 — verified dead-code cleanup** *(LAST, small batches)* — ~139 findings / ~1,075 lines. Prove
  unreferenced across the repo **and** out-of-band entry points (pyproject/package.json scripts, CI,
  Dockerfiles, pyRevit `.pushbutton` manifests, dynamic imports) before deleting. Start with unused
  exports/internals; be skeptical of `e2e_*.py`, `loadtest.py`, `routers/{scim,saml}.py`, converter/pyrevit.
- **REL-8 — lock in gains** *(ci)* — CI cycle check (`import-linter` / `eslint-plugin-import` no-cycle); upload
  coverage from CI; module-header docs on refactored hotspots (bus factor 1).

## 🏗 Enterprise gaps (audit 2026-07)

From a codebase audit for enterprise-grade CAD + analysis readiness. **What's already strong** (don't
rebuild): model versioning/diff, audit trail, RBAC + SAML/SCIM, portfolio rollups, and a strong 5D
cost↔GUID linkage (`cost.element_5d`, `estimate.estimate_from_model`). The enterprise gap is concentrated
in **deliverables, engine relationships, and analysis depth** — the top items, with the ones already
closed this session marked:

- ✅ **Compiled drawing-set PDF** — SHIPPED v0.3.375 (`/drawing-set/compiled.pdf`).
- ✅ **Model-estimate → proforma link** — SHIPPED v0.3.376 (`/dev-budget/sync-from-model`).
- ✅ **Client project package** — SHIPPED v0.3.377 (`/project-package.pdf`).
- ✅ **Rendered cover sheet / index** — SHIPPED v0.3.384 (`drawingset._cover_pdf`): title block + key-plan
  footprint thumbnail + discipline-grouped, paginated drawing index.
- ✅ **Structural analysis: apply loads + solve** — SHIPPED v0.3.382 (`/structure/solve`): gravity load
  case applied to the analytical members + a determinate member-by-member statics solve (reactions, shear/
  moment/deflection diagrams, column axial). *Remaining: lateral solve · load activities written to the IFC ·
  coupled-frame FEM.*
- ✅ **Single discipline/class source of truth** — SHIPPED v0.3.385: sheet-series derives from the one
  discipline map (`classification.series_of_ifc_class`); trade stays a separate build-sequence axis.
- 🟡 **Broader CAD/geometry export** — **binary glTF (.glb) + first-class IFC re-export SHIPPED v0.3.387**
  (`/model/export.glb`, `/model/export.ifc`) beside DXF R12 + `.gltf`; viewer has Export IFC/.glb/.gltf.
  *Remaining (deferred — proprietary/heavy deps): DWG (ODA/Teigha), USD (pxr).*
- **Durable background-job queue** *(★3 · M)* — geometry export, PAdES sealing, and large set generation run
  **inline** (`run_in_threadpool`); no durable queue/worker. Fine for demos, fragile under real load. Touch
  `main.py` + a worker/queue; migrate `generate.py`/`drawings.py`/`exports.py` heavy paths.
- **Server-rendered 3D hero** *(★3 · M)* — geometry streams client-side, so the project package has no 3D
  render (only a composed plan/section/elevation overview). Add a client screenshot-capture → upload path,
  or a headless render, to drop a hero image into the package.


---

## 🔬 R16 ring — COMPLETE (archived 2026-07-23, shipped v0.3.573–598)

All Tier-1/Tier-2 engines + Tier-3 SEC-SUPPLY shipped. Full original spec below for provenance.

## 🔬 R16 — external-scan upgrades (2026-07-21)

Synthesized from a broad research pass on the construction-software field. **Recurring strategic
edge:** a large share of the field spends its core AI budget *reconstructing structured data from
unstructured inputs* (prose→plan, PDF→takeoff, email→line-items, bid-doc→equipment). Because **IFC is our
source of truth**, we skip that whole problem and invest the same effort in deterministic
scoring/optimization/validation on data we already hold — via the `rule_library.py` + `query_dsl.py`
selector/rule spine and the `schedule_options.py` optioneer pattern, which recur as the implementation
vehicle across almost every item. BUILD = deterministic/offline/we-own-it · INTEGRATE = optional
feature-flagged connector (never a runtime dep) · SKIP = conflicts with a constraint/non-goal.

**Tier 1 — flagship, high-value, reuse proven engines:**
- ◧ **MASSING-OPT — layout optioneer** *(L; phase-1 v0.3.576).* The literal "Massing" play. ✅
  `layout_options.py` `optioneer()` deterministically sweeps envelope levers (floor-to-floor · core
  efficiency · coverage strategy · unit size) over `massing.compute_massing`, scores each by a transparent
  yield-on-cost proforma, and ranks by objective + a Pareto cost-vs-profit frontier → `POST
  /massing/optioneer` (stateless) + client + ✅ the **🧮 Massing Optioneer portal panel** *(v0.3.582)*
  (envelope form → ranked options + frontier). **Remaining:** emit each option as a **GUID-stable
  edit-recipe chain** (blank IFC → levels/grid → walls/slabs).
- **MARGIN-CBS — per-cost-code live margin rollup** *(M).* One reconciliation view keyed on the
  CBS/cost-code (`CBS-1` shipped) that computes **committed vs. billed vs. earned margin** per cost code
  from one quantity record, tying QTO → pay-apps → actuals. `GET /projects/{pid}/margin/by-costcode` (reuse
  the where-aggregate SQL-helper shape) surfaced as a portal money card like the selections card. Closest
  fit to the GC portal; highest-value GC item in the scan.
- ✅ **ASSET-REG** *(v0.3.574)* + **PM-OPS — asset register + preventive maintenance** — the concrete first
  slice of the deferred CMMS-OPS. `GET /model/assets` deterministically derives the maintainable-asset
  register from the IFC by class (`classification.py` + `query_dsl.py`), GUID-keyed; a `pm_task` config
  module (asset-GUID link, PPM interval, last/next-due, warranty, spares, O&M docs via `docmanager.py`); +
  round-trip COBie export from the register. Extends the design-to-turnover lifecycle into operations, no
  new infra. (IFC = source of truth: FM data derives from the model, never a parallel sheet.)
- ◧ **MEP-EQUIP + SPEC-CONFLICT — equipment procurement + spec-vs-model conflict** *(M; phase-1 v0.3.580).*
  ✅ `equipment.py` + `GET /model/equipment` derives the equipment schedule straight from the IFC
  (`IfcEnergyConversionDevice`/`IfcFlowMovingDevice`/`IfcFlowTerminal`… subtype-resolved) — **no
  doc-scanning, because we own the model** — grouping procurable units by (class, type) into **RFQ
  line-items with a quantity + representative spec** (from the Psets) + GUIDs; ducts/pipes/controls
  excluded. Client `modelEquipment`. ✅ **SPEC-CONFLICT** *(phase-2 v0.3.581)* — `equipment.spec_conflicts`
  + `POST /model/equipment/spec-check` cross-checks each scheduled line's Pset values against a
  specified-requirement set (`{ifc_class: {spec_key: expected}}`) → conflicts + missing (the "air-cooled
  schedule vs water-cooled spec" catch), deterministic. ✅ the **🔩 Equipment schedule portal panel**
  *(v0.3.582)*. **Remaining:** tie into submittals + budget/GMP + QTO as an RFQ package + a curated starter
  requirement set + an in-panel spec-conflict view.
- **RECIPE-MACROS + headless `massing` CLI** *(M/L; three independent sources converge here).* Save a
  chained sequence of edit-recipes as a **named, parameterized,
  shareable command** with a typed-variable schema (`POST /macros`, `POST /macros/{key}/run`), executed as an
  **ordered, resumable background job** (reuse job-artifacts) through the **model-diff plan/preview/apply
  gate**. Surface the SAME registry across three faces — the viewer **CADCMD** line, the **MCP** tools, and a
  new headless **`massing` CLI** binary (structured-CLI contract: `--json` structured output, meaningful exit
  codes, fully non-interactive; `massing convert|validate|diff|select|edit run|export`). Headline: **`massing
  check`** runs model-CI (IDS/rule-library) and **exits non-zero on failure** so a CDE/repo pipeline fails
  the build when a model breaks compliance — the single most valuable ISO-19650 CI pattern in the scan. Dual
  auth (interactive session vs env-var CI token); an `eval`-against-the-running-model path (no cold re-convert).

**Tier 2 — solid, reuse engines:**
- ✅ **MEP-FITTINGS — implied fitting inference** *(S/M; v0.3.592).* At each `MEP-GRAPH` node/joint a
  direction/size change *implies* a fitting; `mep_fittings.py` + `GET /mep/fittings` infers **tee/cross** at
  branch nodes (degree ≥3), **reducer** at a segment-to-segment nominal-size step, and **elbow** at a
  direction change (sweep-axis angle from the placement) — deterministic geometry, no CV (IFC gives us what
  others infer from PDFs). Branch legs aren't double-counted; counts roll into **QTO** as EA `qto_lines`.
  Client (`mepFittings`) + `test_mep_fittings` over three authored+connected mini-systems + ✅ the **🔩 MEP
  Fittings portal panel** *(v0.3.596)* (fitting-type chips + QTO-lines table + inferred-at detail).
- ◧ **PROCURE-LEVEL — RFQ / quote-leveling** *(M; v0.3.594).* ✅ `procurement.buyout_packages` +
  `POST /procurement/buyout-packages` groups QTO line items into buyout packages, each carrying a ready **RFQ
  scope** (item/qty/unit); `procurement.score_quotes` + `POST /procurement/level` scores returned quotes for a
  package against that scope on a normalized basis — **price** (extended over scope qty, uncovered scope
  extrapolated), **coverage completeness**, and **lead time** → a composite [0,1] ranking with each supplier's
  scope gaps (incomplete bids penalized, not dropped). Client (`buyoutPackages`/`procurementLevel`) +
  `test_procure_level`. **Remaining:** persist packages (a `procurement_package` module) + the send-RFQ bridge.
  (Supplier price/catalog feeds = INTEGRATE; placing the PO stays human.)
- ◧ **TESTFIT-ADJ — adjacency + dimensional rule packs** *(S/M; v0.3.597).* ✅ `adjacency.py` +
  `POST /model/adjacency`: an **adjacency graph** over the model's IfcSpaces (bboxes within a wall-thickness
  gap on the same storey — deterministic, no OCC, footprints from the extruded profiles, corner-only touches
  excluded) scored against a program's `required_adjacent` / `forbidden` type-pairs, plus a
  **dimensional-compliance** rule pack (`min_room_dim` = the short side of the footprint · `min_area` ·
  `min_ceiling_height`, global or `by_type`). Client (`modelAdjacency`) + `test_adjacency` over a relabelled
  2×2 grid. **Remaining:** needs-daylight/exterior-wall + needs-wet-wall terms, and folding the dimensional
  pack into `rule_library.py`/`/rules/run` for the property-based checks (egress-width · setback).
- ◧ **DESIGN-METRICS + DAYLIGHT — live design-metrics engine** *(M; v0.3.591).* ✅ `design_metrics.py`
  + `GET /model/design-metrics`: program efficiency (floors · GFA · net floor area · net-to-gross · unit
  count · avg-unit · area-by-space-type) + a **deterministic average-daylight-factor ESTIMATE** from the
  model's own `IfcWindow` glazed area vs net floor area (CIBSE formula with documented constants → banded
  ≥2% good / 1–2% fair / <1% limited, clearly labelled an estimate, not ray-traced). Pure over an opened
  model so it recomputes on every edit; client + `test_design_metrics` + ✅ the **📐 Design Metrics portal
  panel** *(v0.3.596)* (KPI header + a banded daylight card + area-by-type table, in the design workspace).
  **Remaining:** wiring per-`IfcSpace` code-check rule sets alongside the model-wide numbers.
- ◧ **PROD-ACTUALS — productivity actuals loop** *(M; v0.3.593).* ✅ `prod_actuals.py` +
  `POST /projects/{pid}/progress/actuals`: a `{task_id, qto_line, material_class, qty, cycle_time,
  idle_time, unit}` actuals schema rolled up per activity into the **installed rate** (qty ÷ productive/
  cycle hours) + **crew utilization** (productive ÷ productive+idle), compared to the **planned** rate →
  ahead / on-track / behind (±5%) + a remaining-hours projection at the current rate; worst-variance first.
  Pure over the supplied rows; client (`progressActuals`) + `test_prod_actuals`. **Remaining:** persist the
  actuals (a `progress_actual` module) + a CSV/webhook telematics connector + surface on the LOB/4D views.
- ◧ **SPACE-UTIL — utilization + supply/demand planner** *(S/M; v0.3.585).* ✅ `space_util.py` +
  `GET /model/space-utilization` (per-`IfcSpace` occupancy capacity at an area-per-person standard, by
  type) + `POST /model/space-demand` (headcount program → required-area-by-type → gap-vs-modelled-inventory,
  worst-deficit first); pure arithmetic, no sensors/ML; client + `test_space_util`. **Remaining:** a portal
  panel + extend the cross-project benchmarking (our own-projects analog to a large external dataset).

**Tier 3 — tooling / DX / security (cross-cutting):**
- **CSS-REFACTOR — panel CSS modernize** *(S).* Across the ~130-module panels: a shared
  `.stack > * + *` owl utility (kill per-child margin hacks), flex `space-between` over nth-child, `:is()` to
  collapse selector lists, standardized `:focus-visible` outlines (a11y), `16px` inputs (stop iOS zoom on the
  PWA), `:empty` to hide blank containers, logical properties for future RTL. Pure-CSS, offline-safe.
- ◧ **SEC-SUPPLY — supply-chain hardening** *(S; v0.3.598).* ✅ `supply_chain.py` (dependency-free,
  stdlib `importlib.metadata`): a **license audit** classifying every installed distribution permitted /
  copyleft / unknown (word-boundary matched; STRONG GPL/AGPL split from weak LGPL/MPL) — mechanically
  enforces the no-AGPL constraint (`python -m aec_api.supply_chain --gate` fails only on strong copyleft); a
  minimal **CycloneDX 1.5 SBOM**; and a lightweight **uploaded-PDF sanity check** (header/EOF/size +
  JavaScript/Launch/EmbeddedFile/OpenAction active-content flags, no AGPL parser). Folded into the
  `security-monitoring` skill; `test_supply_chain`. **Remaining:** the MCP tool-poisoning self-audit + wiring
  the audit as a non-gating CI step. *(Cherry-picked from a mostly-off-topic pack; does NOT replace CodeQL or
  the esc() XSS discipline.)*
- **DX-HOOKS — Claude Code guardrails** *(S — needs the config path + an explicit OK,
  since hooks change harness behavior).* A `PreToolUse` secret-scan + destructive-command (`git reset --hard`
  / force-push / `rm -rf`) guard; a `Stop` hook that runs the `security-monitoring`/`backend-tests` skills so
  the "check after every push" directive is enforced by the harness not memory; the **Anthropic Security-Review
  GitHub Action** as an orthogonal second PR gate beside CodeQL; a SkillSpector-style scan of our own
  `.claude/skills`.

**INTEGRATE (optional, feature-flagged, never a runtime dependency):**
- **MARKET-DATA connector.** A flagged/paid "propdata.py" connector feeding the pro-forma /
  underwriting / valuation modules — parcel + rent-comps (ZORI/HUD FMR) + FHFA HPA + FEMA flood (ties into the
  shipped `resilience.py` DFE) + Opportunity-Zone flags + FRED macro. Same posture as the APS/RVT bridge:
  gate it, normalize to our inputs, never assume online. Also adopt two architecture-agnostic techniques from
  it as BUILD: the **self-enriching cache** (local store → on-miss fetch from an authoritative source → cache
  with source + fetched-at provenance) for our own reference/GIS lookups; and **weighted multi-source
  estimates that expose each component value + its weight** (not just the blend) — fits the golden-thread ethos.

**SKIP (reaffirmed non-goals — the scan's core-AI approaches we deliberately don't take):**
LLM natural-language plan generation, CV takeoff from 2D PDFs, LLM bid-doc
equipment extraction, on-sensor CV pick-classification, embedded-in-Revit agents — all reconstruct data we
already hold as structured IFC. Owning sensors / a sourcing marketplace / placing POs or moving money.
Skip-trace / owner-contact / foreclosure-lead (PII, off-mission).

> **Re-prioritization:** the ▶ NOW list above gains three R16 Tier-1 items at the top —
> **MARGIN-CBS** (small, high-value, closest GC fit), **ASSET-REG** (concrete CMMS-OPS first slice), and
> **RECIPE-MACROS/CLI** (converged-on by 3 sources). **MASSING-OPT** and **MEP-EQUIP** are the next authoring/
> MEP wins after those. Tier 3's **SEC-SUPPLY** + **CSS-REFACTOR** interleave as small hardening/quality
> releases.

---

## 🧭 R17 + 🏛 R18 + the reconciled NOW wave — SHIPPED v0.3.600–646 (archived 2026-07-24)

The full R17 backend wave, the R18 authoring-parity ring's completed items, and the reconciled NOW
list (10/10) — moved here from the live roadmap at the 07-24 cleanup. Per-release detail in CHANGELOG.

**R17 Sprint A — provenance & AI trust:** ★ CITED-ANSWER (v0.3.600 — the `CitedAnswer` contract:
claims → typed `CitationRef`s (ifc/doc/record/rule), deterministic coverage %, uncited-claim guard,
conflict surfacing, provenance-as-confidence; `cited_query` + `POST /answer/cited-query`) + RFI-QA
emission (v0.3.628 — every `/rfi/qa` answer carries `cited`; sourceless fallbacks honestly UNCITED) ·
PERSONA-ANSWER (v0.3.612 — Exec/PM/Field lenses, deterministic insight + follow-up chips, no LLM).
Producer disposition (2026-07-24): `POST /ask` + the Ask panel are LLM-phrased by design and stay
outside the contract rather than faking coverage.

**R17 Sprint B — model-navigable coordination:** BCF-VIEWPOINT capture upgrade (v0.3.618 — issue
creation always captures camera + orbit target + active section planes) · WALK-MODE desktop
(v0.3.618 — pointer-lock WASD walk, headless `WalkController` vitest-covered) · TOPIC-BOARD backend +
🗂 Issue Board panel (v0.3.617/622 — kanban columns in stable workflow order + QUERY-DSL smart
filters over topic fields) · TOPIC-LIFE (v0.3.626 — status state machine on PATCH w/ vendor-status
round-trip passthrough, threaded comments, per-topic timeline + inline drawer) · CLASH-WALKTHROUGH
(v0.3.619 — every clash topic carries a framed viewpoint at a 4 m standoff).

**R17 Sprint C — estimating intelligence (complete):** EST-CONFIDENCE (v0.3.601 — per-line
source×phase confidence, % of budget assumption-based) · BOE-LEDGER (v0.3.613 — assumption ledger +
phase drift + qty/price variance decomposition) · BUYOUT-SCHED (v0.3.602 — last-responsible-order =
install start − lead time) · CONCEPT-BUDGET (v0.3.614 — own-history $/area rates, escalated, p25–p75).

**R17 Sprints D–F:** SCOPE-REG (v0.3.603 — the scope register + gap analysis) · TRANSMITTALS verified
already covered · PERMIT-TIMELINE (v0.3.604) · ABSORPTION-SELLOUT + LOT-SUPPLY-INDEX (v0.3.605) ·
PROGRESS-ROLLUP (v0.3.606) + SCAN-4D capture-diff (v0.3.616) · FILL-MATRIX (v0.3.607) · WALL-ASSEMBLY
thermal (v0.3.610) · PARCEL-IMPORT (v0.3.609) · PORTAL-TXN phases 1–3 (v0.3.611/625/627 — public
tokenized decisions, opt-in payment-schedule display, scoped client comment thread over a BCF feedback
topic) · DORMER roof-window slice (v0.3.620 — `add_roof_window`, SKYLIGHT fill, GUID-stable) ·
RUNTIME: Node 22 CI + oxlint (v0.3.608) · MASSING-OPT `emit_recipes` (v0.3.630) · PROD-ACTUALS module
(v0.3.631) · PROCURE-LEVEL packages + send-RFQ (v0.3.631) · TESTFIT-ADJ daylight/wet-wall terms
(v0.3.632) · WKT ReDoS fix (v0.3.621).

**Drift-guard incident (v0.3.628–629/632):** the db-migrations workflow had never run (psql
PGDATABASE defaulting) which hid that the Postgres FTS GIN indexes were never created in prod
(`concat_ws` is STABLE → CREATE INDEX rejected; search was seq-scanning). Fixed: `PGDATABASE` in the
job env; `_pg_document` rebuilt on all-coalesced `||`; fresh-DB migration-chain ordering (baseline
`has_table` skip + per-migration GIN blocks + a static guard in `test_alembic_migrations`).

**🏛 R18 completed items:** SCHED-CALC (v0.3.635 — `calc_fields.py` AST-whitelist formula evaluator +
`/drawings/schedules/calc` + `/modules/{key}/calc`) · OPS-DR (v0.3.636 — `BACKUP_KEEP` retention +
docs/ops-dr.md runbook) · AUTH-CONSTRAINTS ① (v0.3.637 — `aec_data/constraints.py` broken-host/
illegal-placement checker + `GET /model/constraints`; host/level refs persist natively in IFC) ·
MODEL-PUBLISH (v0.3.638 — `review_status` draft→in_review→approved on ModelVersion +
`/versions/{v}/review`; the concurrency half was already live via COLLAB-1 `base_source`) · RULE-PACK
FOLD (v0.3.639 — the space pack via `/rules/space-pack` folded into `/rules/run` as `space:*` rows) ·
SEC-SUPPLY CI (v0.3.640 — `mcp_tool_audit()` + `mcp-audit` CLI + report-only workflow step) ·
SPACE-UTIL benchmarking (v0.3.641 — `/benchmarks/space-utilization`, 12-model cap, portfolio median) ·
MEP-EQUIP ties (v0.3.642 — `/model/equipment/to-submittals` idempotent + `/budget-lines` +
`/starter-requirements`; `"*"` presence semantics) · RECIPE-MACROS CLI (v0.3.643 — the headless
`massing` CLI: `new`/`run`/`check --gate --json`) · ADR-LITE (v0.3.644 — docs/adr/ + ADR-0001) ·
SDK-VERSIONING verified already shipped (the plugin registry's `api_version` MAJOR gate) ·
VIEW-TEMPLATES (v0.3.645 — layered view presets w/ deterministic resolve, byte-identical re-resolve) ·
FAMILY-DEPTH ① type catalogs (v0.3.646 — `TYPE_CATALOGS` + `catalog_types`/`catalog_dims` +
`type_name` on the add_family recipe/place route + `GET /families/{key}/types`).

**The reconciled NOW list (2026-07-24) shipped 10/10:** SCHED-CALC · OPS-DR · AUTH-CONSTRAINTS ① ·
MODEL-PUBLISH · CITED-ANSWER producers resolved · RULE-PACK FOLD · MEP-EQUIP ties · SEC-SUPPLY CI ·
RECIPE-MACROS CLI · SPACE-UTIL benchmarking.

---

## 🏢 R19 + 🏛 R18 tail + 🏙 R20 + the carry-overs — SHIPPED v0.3.647–661 (archived 2026-07-24)

Fifteen releases in one continuous run, every one full-suite green with **CodeQL 0 open alerts**.
Three complete rings, the last NOW-list carry-overs, and the backend suite grown 344 → **363**.
Per-release detail in [CHANGELOG.md](../CHANGELOG.md).

**🏢 R19 — enterprise & finance-platform readiness (COMPLETE).** From the 07-24 external planning
pack. Its competitor-matrix deliverables were deliberately **not adopted** (standing directive); the
authoring gap analysis was already R18 and most finance engines already shipped, so what was actually
built is the program-formalization + governance layer:

- **Enterprise track (v0.3.649 + v0.3.653):** SEC-THREAT — [threat-model.md](security/threat-model.md),
  STRIDE over the real surfaces + a control→evidence verification matrix + a gap backlog, with gaps
  G-2 (SBOM CI artifact) and G-5 (password deny-list, `weak_password_reason` + `test_password_policy`)
  closed in-sprint · COMPLY-SOC2 — [soc2-readiness.md](compliance/soc2-readiness.md), the TSC matrix
  CC1–CC8 + A1 + C1 with evidence sources · OPS-OBS — [runbooks.md](ops/runbooks.md), eight incident
  runbooks + SLOs + the correlation-ID triage spine · ENG-STD —
  [backend-standards.md](engineering/backend-standards.md) + [web-standards.md](engineering/web-standards.md)
  · **INTEROP-RT** (v0.3.653) — `aec_data/roundtrip.py`: serialize → reparse → compare
  (GUID/class/name/containment/type/psets, unmatched both ways, one `fidelity_ok` verdict) +
  `GET /model/roundtrip` + `massing roundtrip --gate` + `test_roundtrip`.
- **Finance track (v0.3.650):** FIN-GOV — `fin_gov.py` scenario review workflow (draft→in_review→
  approved→published, immutable once approved, changed-assumption paths audit-logged; Alembic
  `c6dcec8fe81d`) + locked reporting periods enforced in the modules **engine** (409 on create/update/
  move/delete into a closed month, so imports are covered too) · FIN-CALC — `proforma/residual.py`
  residual-land inverse solver (`POST /proforma/residual-land`, honest "not achievable even at $0
  land") + golden reference fixtures +
  [calculation-precision.md](engineering/calculation-precision.md) · FIN-PORTFOLIO —
  `GET /proforma/portfolio/compare` + the `investor_pack` Report-Center preset · FIN-INGEST —
  `fin_ingest.py` `/finance/reconcile` (budget↔actuals both ways + uncoded rows) + `/finance/imports`
  lineage.

**🏛 R18 tail — authoring parity (RING COMPLETE).** AUTH-CONSTRAINTS ② level-move re-derivation
(v0.3.651 — `set_storey_elevation` shifts every root placement by Δz and detects non-riding hosted
openings via a before/after Z snapshot) and ③ wall joins (v0.3.653 — `wall_joins.py` L/T detection +
an idempotent butt-join `resolve`) · FAMILY-DEPTH ② instance-over-type overrides (v0.3.651 —
`instance_props.py` `effective_properties()` with `source`/`overridden`/`type_value`, and
`reset_property_to_type()` that refuses when there is no type backing), ③ composite families
(v0.3.653 — `COMPOSITES` under `IfcElementAssembly`) and ④ shared parameters (v0.3.653 —
`shared_params.py` registry → schedule columns reachable by SCHED-CALC). *Cross-project family-library
versioning was deliberately deferred until a customer needs multi-firm libraries — the existing
`import_types_from_ifc` + MODEL-PUBLISH review states cover the single-firm case.*

**🏙 R20 — CRE deal-desk depth (RING COMPLETE, v0.3.657–660).** From two external field guides on
running an AI assistant across CRE / ground-up-development workflows. **Read honestly, most of their
content is prompting technique for reading messy documents — our documented non-goal.** What was worth
taking is the deterministic discipline underneath, and each item was checked against what already
ships before being built. The through-line: *every material number carries its source, and a stale or
missing input stops the workflow instead of being filled in with something plausible.*

- **Tier 1 (v0.3.657–658):** CRE-NER — `net_effective.py`, straight-line **and** discounted net
  effective rent per lease and portfolio-wide, using the same active-lease filter as the rent roll so
  the two surfaces can never describe different portfolios; un-computable leases are named, not
  dropped · CRE-COMP-TIER — `comp_tier.py`, a ranked source tier (recorded sale → … → unknown) that
  decides which comp wins, with every derived band reporting the **worst tier it depended on** ·
  CRE-T12 — `t12.py` with its own OPERATING chart of accounts, and **the tie-out as a hard gate**
  (`stopped: true`, `adjusted_noi: null` when totals disagree) plus add-back checks surfaced as
  questions, never applied silently · CRE-RRSCRUB — `rent_scrub.py`, seven checks that report
  `applicable: false` **with what they needed** rather than a silent pass.
- **Tier 2 (v0.3.659):** CRE-COVENANT — `covenants.py`, day-count basis and clock start as
  first-class fields, due dates that show their work, untested ≠ passing, cure windows tracked
  separately · CRE-AUTHORITY — `deal_authority.py`, per-fact-type authority that **gates** on
  missing/stale/superseded and refuses undated facts · CRE-SUPPLY — `supply_pipeline.py`,
  evidence-weighted units (loan recorded 1.0 → announced 0.05) with rumored supply kept visibly
  separate · CRE-DECISION-GATE — `decision_gate.py`, seven pre-committee gates where **unknown
  blocks**, returning actions rather than just failures.
- **Tier 3 (v0.3.660):** CRE-ICMEMO — the `ic_memo` Report-Center preset that **refuses to render**
  on a missing basis/NOI/debt/equity/exit-cap, naming what is absent and what to do · CRE-HOLDSELL —
  `hold_sell.py`, incremental hold-year cash flows against the proceeds declined today, explicit cap
  drift, honest "no year clears the hurdle" · CRE-CLAUSE — `clause_playbook.py`, clause positions as
  data with a **required red line per clause**, and unreviewed clauses reported as open risk rather
  than assumed acceptable.

**⚡ ENERGY phase 1 (v0.3.655).** `aec_data/energy_export.py` — the IFC becomes a thermal model (zones
· zero-thickness mid-plane surfaces, each tagged `exact`/`bbox` by checking the mesh against its
bounding box · constructions whose conductivities are back-derived from the platform's own R so the
export cannot contradict it) with **gbXML** and **EnergyPlus IDF** writers over one intermediate, both
byte-deterministic. `GET /energy/model` + `/energy/export.gbxml` + `/energy/export.idf`.

**🔁 Carry-overs (COMPLETE).** VERSION-COMPARE per-property values (v0.3.654 — bounded `_prop_values()`
at fingerprint position [7], with `_materially_differs` still comparing 0..6 so value drift never
forges a structural change) · IFCPATCH-LIB rebase-origin / unit-convert / split-by-storey (v0.3.654;
**merge deliberately skipped** — federation already covers multi-model work) · BCF-API-SRV 3.0 shape +
attachments-over-API (v0.3.654) · **SPRINT B phase-4b** (v0.3.661 — crew shifts follow the CPM:
`critical_path` as a list or `"auto"` off the project's own network; off-path trades are excluded from
the crew grid **and named**, and a path matching nothing falls back to the slowest-trade heuristic and
says so, because a second crew on a trade with float buys no days and still costs the premium) ·
**NORM-VALID implementer-agreement depth** (v0.3.661 — MVD `ViewDefinition[…]` parse, unit-assignment
completeness **and** unambiguity, and relationship cardinality: dangling relationships, single spatial
container / whole / voided element, no double-placed part, unbroken spatial-aggregation chain).

**Defects found and fixed en route (v0.3.661).** The NORM-VALID header lane read
`model.wrapped_data.header` — a *method* on the C++ wrapper — inside a bare `except`, so **every header
check had been silently reporting "empty" for every file ever validated**. Fixed to `model.header`.
That exposed two more: our own generators assigned no `PLANEANGLEUNIT` and shipped an empty
`FILE_NAME`/`FILE_DESCRIPTION` (now `massing.stamp_conformance()`, applied to all three generators);
and `schedule_cpm.compute()` emitted record ids in `critical_path` but refused to *accept* an id as a
predecessor token — its own output was not valid input.

**Security.** Two HIGH dependabot advisories closed by root npm `overrides`: js-yaml ≥4.3.0
(v0.3.648) and postcss ≥8.5.18 (v0.3.656).

## ▶ NOW list closed out — v0.3.662–v0.3.675 *(archived 2026-07-25)*

The 07-24 NOW list, finished. Per-release detail in [CHANGELOG.md](../CHANGELOG.md).

0. ✅ **FAMILY-CONTENT** *(shipped v0.3.662)* — the platform can now hold a real family library.
   Four verified geometry defects fixed (sizeless real sections · resize appending a second solid ·
   hollow sections silently reshaped as boxes while keeping their catalog name · metric-hardcoded
   variant names) plus the external **pack shelf**: `family_packs.py` +
   `POST /families/import-pack` (name-only resolution, sha256 in the audit trail) and manifest
   metadata on `GET /families/library`. See [families.md](families.md).
   ✅ **Shelf stocked** *(v0.3.668)* — the 40 packs (270 families · 2,334 types · 6.1 MB) are built
   from the catalog and **committed**, so a fresh clone has a stocked shelf with no build step.
   **Remaining:** a browsable shelf UI in the Library palette *(UX-3 depth, below)* · the content
   repo publishing a **tagged release** so `scripts/fetch_families.py` can fetch rather than needing
   a local build *(user/upstream action)* · the upstream manifest declaring a **licence** — it
   currently declares none, so the shelf honestly reports `unlicensed`.
1. ✅ **🎚 UX-POLISH sprint — COMPLETE** *(v0.3.663–664)*. The backend surface had outrun the front
   end; this closed the gap.
   ✅ **UX-KPI** — the narrative band on the developer + design homes · ✅ **UX-CHIPS** — `toneFor`
   taught the *real* vocabulary (112 module workflow states; 30 were recognised, so 73% of every
   register rendered grey), then rolled to the module record grid (incl. DRAW-STATUS), the
   action-items and brief feeds, and the selections money card · ✅ **UX-ACT** — the
   `select_elements` action kind for diagnostics that name geometry (rule violations), the
   optioneer's caveats paired with resolving buttons, and the `navigate` kind wired ·
   ✅ **UX-DEMO** — `demo_seed.py` generates schema-valid records from each module's own field
   defs, so the 108 previously-empty registers fill (`seed_demo.py --all-modules`); references are
   refused rather than faked.
   **Remaining:** the demo/docs/Pages refresh — regenerate `demoData.json` off the fuller seed.
2. ✅ **💲 COST-SPINE — COMPLETE** *(v0.3.665)*. `cost_spine.py` + `GET /cost-spine` traces cost-code
   identity across budget → commitment → actual → invoice, reporting **presence** rather than only
   amounts: the stages each code reaches, where the chain first breaks, spend on codes nobody
   budgeted, invoices over their commitment, records with *no* code at all (which no per-code report
   can show), and off-register codes. `traceability_pct` is surfaced **on the margin card**, because
   that is the number that inherits the coverage.
3. ✅ **🧱 REL-3 — `modules.py` split — COMPLETE** *(v0.3.666)*. **It never needed dependency
   injection.** The read + workflow-evaluation functions call nothing else in the module, so the
   graph was already acyclic and the fix was a layering cut: `modules_query.py` takes the
   self-contained base, `modules.py` keeps the write path and re-exports everything, so none of its
   **114 importers** change. 975 → 859 lines.
   **Remaining REL-3 slices**, to interleave one per few releases:
   `main.py` · `codecheck.py` · `connectors.py` residue · `auth.py` ·
   `data/drawing.py`/`drawings.py`/`massing.py` · `bcf_io.py` · `routers/generate.py`.
5. ✅ **⚙️ WFE-3 — COMPLETE** *(v0.3.668)* — per-project workflow overrides (`workflow_config.py` +
   `GET/PUT/DELETE /workflow/{key}`). A save that would **strand live records** — an occupied state
   with no way out — is refused with the state and count named, because a stranded record looks
   exactly like one nobody has got to yet. Rewires declared states only; never invents new ones.
6. ✅ **📈 GEN-SCORE depth — COMPLETE** *(v0.3.669)* — `option_takeoff.py`: elemental quantities off
   the massing geometry → per-element cost + embodied carbon through the platform's own EPD factors.
   A benchmark can't see geometry (a plate and a tower with equal GFA score identically); a takeoff
   can. Uncovered elements are named rather than counted as carbon-free, and a set that **mixes**
   quantity-derived with benchmark carbon is flagged as not like-for-like.

*Reassess after sprint 3. Items 4–6 are genuinely optional ordering; 1–3 are not.*

---

# Archived from the active roadmap — 2026-07-28 (v0.3.772)

Moved wholesale during a roadmap rebuild. **Three items in the SPRINT A-2 block below were listed as
"built but unrouted" and were verified shipped at archive time** — `dim_constraints`
(`routers/analysis.py:542`), `sheet_regions` (`routers/analysis.py:572`, live 200) and `iconFor`
(consumed in `viewer/toolbarView.ts:15`). They are kept verbatim as a record of the claim, not as
outstanding work.

Two items were **hoisted back into the active roadmap** rather than archived with their rings,
because they were open work sitting under a COMPLETE heading: **R25/R24-TRACE-UI** and
**R26-V-TIMING**. That pattern is what hid R26-VITALS.


## 🔎 RING RECONCILIATION — 2026-07-28, v0.3.765

**The backlog was mostly already built.** 61 ring items were checked against the codebase, not
against their own descriptions. The test was reachability, because a word in a doc is not a feature
and this repo has paid for that confusion before (seven engines, no route).

**16 of 18 verified candidates are SHIPPED AND ROUTED** — entitlement, golden thread, provenance,
sub-prequalification, cross-project memory, DXF/CAD import, the accounting seam, design options as
objects, the portfolio pipeline, preventive-maintenance contracts, jurisdiction packs, the model
digest, the Gantt, CMMS operations, and site/parcel work. They were carried as backlog for weeks
while sitting in `routers/`.

**This is the same shape as S4.** The five room tabs already existed and were rendered as a sub-rail;
`bundle.py` already round-tripped; favourites already persisted. **A research ring records what was
missing on the day it was written, and nothing re-reads it afterwards.** The ring is a snapshot that
ages into fiction.

### What is actually left

**No orphan. That finding was mine and it was wrong — corrected within the hour.**
- **R22-ITP-NCR is SHIPPED AND REACHABLE.** `itp` is registered as "Inspection & Test Plan" (one of
  132 config modules) and `GET /projects/{pid}/modules/itp` returns **200**.
- The probe searched `routers/` for the literal string `itp` and found none, so it reported an
  orphan. **There are two different things called a "module" here, with different reachability
  rules**, and the probe applied the wrong one:
  - **engine modules** (`src/aec_api/*.py`) need a route, and `test_reachable.py` walks the import
    graph to prove it;
  - **config modules** (`services/api/modules/*/module.json`) are served by the *generic* module CRUD
    the moment they are registered — a dedicated route would be the anomaly, not the requirement.
- So the gate proposed alongside this finding is **not needed**, and building it would have hardened
  a rule that is false for half the things it names. Registration already is the reachability
  guarantee for config modules, and the engine loads all 132 from disk.

**Two genuinely unbuilt, both already on the NOW list:**
- **R28-ICDD** (SPRINT C) — no source trace. Needs `rdflib`.
- **R22-REPORT-BUILDER** — no source trace; `reports.py` has the registry but no builder UI.

**Seven greenfield, no trace anywhere:** R21-MULTISCALE, R21-DIM-COMPONENT, R22-NOTICE-CLOCK,
R23-STOREY-LOD, R23-SYMBOL-COUNT, R24-RUNS-INBOX, PHOTO-PIN.

**Nine partial** (1–2 files — a seam exists, the feature may not): R22-ITP-NCR, R22-REPORT-BUILDER,
R23-GLTF-COMPRESS, R23-PREFAB-KIT, R24-DENSITY, R24-FIELD-MODE, R24-TERMS, R28-ICDD, PERF-RATE.

**So the honest backlog is ~16 items, not 61.** The rings below are kept for their *reasoning*, which
is still good; their status claims are not to be trusted without a reachability check first.

**The durable fix is a gate, not another audit.** `test_reachable.py` checks routers; it did not
catch a module with no route. Extending it to assert every `services/api/modules/*` is reachable
would have found R22-ITP-NCR the day it landed — and would stop the next one.

## ✅ RELEASE THE NEW LAYOUT — **COMPLETE v0.3.751–764**, one item left

Shipped, each live-verified against a running stack rather than by test alone:

- **S1 PROVE** — the layout renders. `/rooms` 200 in 18 ms, all three portal workspaces populated.
  The "empty rooms" scare was a **dead backend**; I built a case for a product defect twice from a
  corpse whose own log read `200 OK`. See [[prove-the-backend-is-alive]].
- **S2 HARDEN** — Node 24 (not the branch's 22 — v22 had 276 days left, v24 has 642), Postgres 17,
  Capacitor 8, the security-audit branch (SSRF-via-redirect, sandbox, SVG), the Android build gate,
  and a version-consistency gate that had been silently wrong for ~100 releases.
- **S3 SHOWCASE** — `maple_grove_house.mass`: 23 elements, served, opens as a project. Plus the
  library-directory bug that meant `GET /samples` **never worked**, and empty-first-run onboarding.
- **S4 SHELL** — the five rooms as primary navigation, NEXT BEST ACTION in the header, the pinned
  rail, and the three chrome defects from the 07-28 screenshot.

**The one thing left: delete `?shell=classic`.** Held deliberately, and this is the reasoning rather
than hesitation. The classic rail is already **unreachable in normal use** — the seven workspace
buttons are gone when the spine is on — so it costs nothing sitting there, while deleting it is the
only irreversible step in the whole ring. `pulse.ts` renders on the portal home but has never been
watched populating against real engine data; only its logic is tested. And nobody outside this
session has used the new shell for a day's work.

**The gate: one real user runs a day through it.** Then this is a one-line release. Tidiness is not
worth spending the way back on.

1. **📦 MASS-FIRST — the container is the project, everywhere.** *Build. Backend landed v0.3.744;
   these are the remaining halves.* User direction, 2026-07-28:

   - **② Package real samples — blocked on CONTENT, not on tooling.** `build_samples.py` works and
     self-verifies; measured 2026-07-28 against all 24 projects in the dev DB. The problem is what
     is in them: the three plausible candidates (Verification House, two Maple Street Houses)
     package to **~10 KB with 0 elements** — tables are `jobs`, `model_versions`, `record_activity`,
     `ref_counters`, `project_members`, and at best one `topic`. No estimate, no schedule, no
     drawings. Committing those would reproduce the exact defect this feature exists to fix: a
     "sample" that demonstrates nothing.
     So the real work is **authoring a showcase project**, not packaging one — the live house test
     extended with a full estimate, a schedule, several RFIs through to closed, and generated
     sheets. Then `build_samples.py --project <pid>` and commit. Until that exists, `GET /samples`
     correctly returns `[]`, and the three hard-coded `.frag` menu entries must stay.
     (Also noted while probing: the dev SQLite DB has **no `element` table at all**, so where
     element rows live — and whether `bundle.py` captures them — needs settling before a packaged
     sample can claim an element count. Do that first; a sample whose manifest says `0 elements`
     for a real building is a wrong number, not a small one.)
   - **② One "Load sample", from the library.** Replace the three hard-coded `.frag` menu entries in
     `main.ts` (`/school_str.frag`, `/school_arq.frag`, `/basichouse.frag`) with a single entry that
     lists `GET /samples` and opens the chosen container. Those three are the last place the product
     shows geometry-without-data.
   - **② A sample opens on first load.** An empty app should already be showing a populated project,
     not an empty canvas asking to be filled.
   - **② Every model gets a `.mass`.** Loading an IFC with no container creates a blank one, so a
     project is never "geometry with data bolted on later" — it is a container from the first second.
   - **③ Re-cut Create / Open / Save.** Evaluate the current dropdowns against the container model
     and **reinvent if they do not make sense** — the user's words. "New project" must be obvious;
     today it is not. Do this *after* the four above, so the menu is designed against how the
     product actually behaves rather than how it behaved.

   The through-line: geometry stopped being the unit of work here a long time ago, and the file
   menu never noticed.

2. **🔀 BRANCH-DRAIN — two long-lived branches, each its own release.** *User: do both.*
   - `chore/deps-upgrades-2026` (PR #69) — Capacitor 7→8, Postgres 16→17. 190 commits behind and it
     crosses two majors, so: rebase, full backend suite, full web gate, desktop build, **then** ship
     alone. Never bundled with feature work — a two-major bump that breaks something must be
     bisectable to itself.
   - `security/audit-2026-07` — 56 commits behind; R1–R4 were waiting on a decision that has now
     been given. Land it as its own release with the findings written up in the commit.

3. **📊 SAMPLE-DATA-REAL — populate the samples with real historical figures.** *User: use public
   historical data; it is the best available until there are users.* This unblocks nothing on its
   own, but it is what makes R26-V-TIMING and plugin pricing measurable later: a sample carrying
   plausible real cost/schedule history is a dataset those two can be evaluated against. Public
   sources only, and **no real party names, addresses or contract values** — the repo is public.

1. **🧱 SCALE-SEAM — `client.ts` is the breakpoint, and it is measurable.**
   > **CORRECTION 2026-07-29 — this entry is filed as complete and the work is not done.** It records
   > ①, the `authoring.ts` extraction, which took `client.ts` from 4,956 to 4,844 — **112 lines, 2%** —
   > and the item was then closed with the god-file intact. ② shipped v0.3.800 (`schedule.ts`, 207 more
   > lines). Reopened as **SCALE-SEAM ③+** in `roadmap.md`, with the measurement that should have set
   > the scope: 669 methods across **219 route-groups**, largest 4.5% of the file, so ~25 releases of
   > one group each rather than one refactor. Left in place rather than deleted because *how* it came to
   > be marked done is the lesson — a first slice landing is not the item landing, and a completed pile
   > is where a claim goes to stop being checked.

   *Build; now the top, ahead of feature work.* Measured 2026-07-28:

   | file | lines | commits / 14d |
   |---|---|---|
   | `api/client.ts` | **4,956** | **152** |
   | `viewer/app.ts` | 4,565 | 114 |
   | `portal/portal.ts` | 2,699 | 24 |
   | `main.ts` | 1,440 | 17 |

   `client.ts` carries **631 methods on one class** and is touched ~11×/day. Every feature adds to it,
   nothing ever removes from it, and it must be opened to add any endpoint. That is the definition of
   a file that stops being editable — not because it is long, but because **length × churn** means
   every change competes with every other change for the same window of attention.

   **The fix is a seam, not a rewrite.** Split by domain the way the routers already are — the server
   side solved this exact problem with `routers/*.py`, and the client never followed. `client.ts`
   becomes a thin composition of `api/model.ts`, `api/cost.ts`, `api/coordination.ts`, … each owning
   its endpoints. Nothing changes for callers; `ApiClient` keeps its shape.
   **Do it incrementally and prove it**: extract one domain, assert the public surface is unchanged
   (method-name set equality, asserted in a test), ship, repeat. A big-bang split of a file with
   152 commits a fortnight will collide with everything in flight.

   `viewer/app.ts` is the same disease and comes second. `schema.d.ts` (32k lines) is **generated** —
   not a comprehension problem, leave it.

1. **📄 PDF-ADOPT ② — move the takeoff flow onto the vendored engine.** *Build; ① shipped v0.3.740.*
   `@massingcloud/pdf-viewer` is vendored at `65e9011` — aliased through the one map, zero local
   patches, 5 reachability tests, **no new dependency**, **not in the eager bundle** (entry stayed
   346 KB). `drawings/pdfTakeoff.ts` still owns the flow. Replace in slices — open/render, then
   markup, then calibrated takeoff — so a regression stays bisectable. Publishing upstream to npm
   would let us drop the vendoring; that is a decision, not a blocker.
2. **📦 SPRINT C — R28-ICDD ③ + R28-BUNDLE ② (the UI half).** *Build.* `rdflib` approved; add it to
   `requirements.in` and regenerate the lock via the `lockfile.yml` workflow — never on a dev box.
3. **🧩 KERNEL-ADOPT ③ — one more capability onto the kernel.** *Build.* ① the identity boundary
   (v0.3.713) and ② markup through the plugin host (v0.3.717) each closed a real defect; pick ③ from
   a real pain, not from the kernel's feature list. **Undo is not a candidate** — checked: model-level
   undo via the versioned source IFC is stronger for authoring.
4. **🖼 Demo + docs refresh.** *Build, low stakes.* The snapshot was regenerated at v0.3.733 after
   the QTO fix; README/guide still quote pre-v0.3.723 numbers in places.
5. **🔍 TRIAGE — R27 tail + 🧱 decomposition carry-overs.** *Analyse first, then decide — LAST
   deliberately.* This was one bucket holding two unrelated things because neither felt big enough
   alone, which is exactly how items go stale unread. It stays last **and the first step is not
   building** — it is going through what is actually in there and deciding, item by item, what earns
   a place and what gets deleted. A carry-over that has survived this long without hurting anyone is
   evidence about its own priority. **Default answer is drop, not do**; anything kept has to justify
   itself against whatever else is on the list by then.

### 🤔 Decisions, not effort — these want your call, not my time
- **`chore/deps-upgrades-2026` (PR #69)** — Capacitor 7→8, Postgres 16→17. Its own release, its own
  suite run; 190 commits behind and crosses two majors.
- **`security/audit-2026-07`** — findings R1–R4 need a decision before it can land. 56 commits behind.
- **`.mass` ownership** — we already have a working container (`bundle.py`; verified live 07-28: an
  11-entry zip that re-opens with an RFI still `closed` and the estimate rebuilt to the identical
  total). The *kernel* has the contract and no file writer — upstream
  [issue #6](https://github.com/MassingCloud/massingifc/issues/6). Push ours up, or keep it
  product-side? Nothing to build either way.
- **Branch protection** — `main` is unprotected and public. Recommend blocking force-push and deletion
  only; direct version-numbered pushes keep working, published history cannot be rewritten.
- **R26-V-TIMING** — needs real users. **Plugin pricing** — needs customers.

## 🏛 R26 — THE SPINE *(ring COMPLETE, archived 2026-07-26 at v0.3.710)*

Every item shipped, R26-ICONS last (v0.3.708). The render audit **ran under the spine and passed** —
7/7 workspaces, five rooms, 153 destinations — and it is trustworthy because the false-pass hole was
closed first.

**The spine IS the default** — and was made so back at v0.3.715, with the reachability work finished
at v0.3.739 (persona-home landing + `← Project home` signpost). Verified live 07-28: the room rail
renders in Construction, Developer and Design, all five rooms with their job strings. One item remains
and cannot gate it:

- **R26-V-TIMING** *(M — needs real users)* — instrument first-task completion per persona against the
  audit's baseline. Deliberately open: an *after* measurement cannot gate what it measures.

---

## 💵 R25 — 5D *(ring COMPLETE; archived 2026-07-26 at v0.3.702)*

The model **is** the estimate, end to end: cost and 4D bindings written natively into IFC
(`IfcRelAssignsToControl`→`IfcCostItem`, `IfcRelAssignsToProduct` for tasks), quantities measured from
the model rather than supplied by the caller, rates carrying their source and vintage year, and two
estimates diffable by GlobalId with every dollar attributed to a cause. Archived in full — see
[roadmap-completed.md](roadmap-completed.md#-session-v03684702-2026-0725/26--the-spine-the-5d4d-rings-and-the-drawing-layer).

The chain's last missing link closed in v0.3.702 as **R27-SOV-LOOP**: nothing had built a schedule of
values *from* an estimate, so the numbers were re-keyed by hand at exactly the seam where somebody
asks to be paid.

Only one item remains, and it is tracked in R24 rather than duplicated here:

- **R25/R24-TRACE-UI** *(M)* — the chain made visible in the UI: figure → cost line → the elements
  behind it. The data is complete; this is the surface that shows it.

---

## ✅ SPRINT A-2 — the last three engines nobody can call — **SHIPPED v0.3.711**

Sprint A wired four engines that had shipped tested and unreachable. Auditing for the rest found
**three more**, one of them created during Sprint A itself. All three are now reachable, and
`test_engine_routes` asserts it over real HTTP rather than by importing the module:

* **A2-CONSTRAINTS** — `dim_constraints` (v0.3.701) has **no route and no MCP tool**. The solver is
  fully tested and nothing in the platform can reach it; that entire release is currently inert.
  **Done:** `POST /projects/{pid}/constraints/solve`. A malformed constraint is refused with 422
  rather than dropped — a lock nobody applied is worse than an error, because the model then looks
  constrained and is not. (An MCP tool is still open; the route was the blocker.)
* **A2-SHEET-REGIONS** — `sheet_layout.sheet_regions()` (v0.3.702) is **not exposed**, yet
  `POST /takeoff/2d` now *accepts* a `layout` object. The consumer was wired and the producer was
  not, so a caller has no way to obtain what the route asks for — the same one-way asymmetry
  R25-TASK-BIND existed to close, reintroduced while closing something else.
  **Done:** `GET /projects/{pid}/drawings/sheet-regions`. One finding along the way — `presets()`
  falls back to `key` for any unknown name, which is right for a library and wrong for a route, where
  a typo would return a *different* layout labelled as the one asked for. The route keeps its own
  whitelist, refuses before opening the model, and `test_sheet_layout` asserts the two lists cannot
  drift.
* **A2-ICON-RENDER** — `TOOL_ICON` + `iconFor()` (v0.3.708) are complete and tested, but
  `toolbarView.ts` **never calls them**. The mapping is done; the rendering was never wired, so
  nothing on screen changed. "All 27 verbs mapped" was true and misleading.
  **Done:** `labelFor()` renders the vendored SVG, falling back to the original emoji glyph and
  tagging the button `data-glyph-fallback` when a tool has no icon — half a bar of line icons beside
  half a bar of emoji is ugly but readable, whereas a blank square is a tool the user cannot find.
  Two traps here. The pre-existing test asserted the *emoji* survived, encoding the old behaviour
  rather than its intent; it now asserts a mark of either kind. And the new tests passed while
  silently using a `ToolContext` property that does not exist — **vitest does not typecheck**, so
  `npm run typecheck` was the only gate that caught it.

**The standing check this produces, to run every sprint:** *what did we build that nothing calls?*
Of eleven things built on 2026-07-26, **seven were unreachable** — tests passing is not the same as a
request being able to arrive. `grep` the new module name across `routers/` before calling an item
done.

---

## ▶ NOW list of 2026-07-28 — all eight closed (v0.3.773–777)

Archived 2026-07-29. Seven shipped, one (**R27-UW-PANEL**) was closed *unbuilt* because its
premise did not survive the offline constraint — recorded rather than deleted, since a closed
item with its reasoning is what stops the same idea being re-proposed next quarter.

## ▶ NOW — one prioritized list *(rebuilt 2026-07-28 at v0.3.772)*

There were **three** competing NOW sections before this rebuild, and four more sections headed
COMPLETE that still contained open work. That is how R26-VITALS — the prototype's most visible
pillar — sat unbuilt inside `roadmap-completed.md` for weeks: **an unshipped item filed under a
completed heading is invisible**, because nobody goes looking there. One list, in order.

### ~~1 · R26-VITALS~~ — **DONE v0.3.773.** Was:
Six numbers along the bottom — **LOD · area · $/sf · float · IRR · health** — replacing the ten
viewport controls pinned to every room whether or not it has a viewport (audit finding 13: *"ten
permanent controls, irrelevant on four of seven tabs, occupying the most valuable strip of the
window"*). The audit calls this *"the only continuous proof of the one-model claim"*.

Three of the prototype's four pillars shipped (spine, Inspector, work-queue-as-home). This is the
fourth. **Build it as one `/projects/{pid}/vitals` assembly endpoint** over engines that already
exist — five separate client fetches is precisely how audit finding 03, *"the app contradicts itself
on screen"*, happens. Viewport controls then move into Design, where they apply.

### ~~2 · VITE-8~~ — **DONE v0.3.774** (and it caught a silent vendor-split regression). Was:
Vite 6→8 (Rolldown) + Vitest 3→4. The only genuinely outstanding item from that PR; its other
runtime bumps are already on main (Capacitor 8.4.2, postgres:17) or superseded (it wanted Node 22,
main runs 24). A major build migration, so it gets its own release and the full gate.

### ~~3 · CI-HYGIENE~~ — **DONE v0.3.774**; two of the four items were already done. Was:
Pin the MinIO and nginx image tags, extend Dependabot to container images + a Vite group, and make
the Cargo.lock guard non-fragile with `cargo metadata --locked`.

### ~~4 · R27-UW-PANEL~~ — **CLOSED, not built.** The premise does not survive the constraint

Written as "give `__uw__` a real portal panel so Deal lands on Underwriting". Checked before
building, and the trade is bad:

- **Underwriting is already reachable and labelled** from the Deal room — `📊 Underwriting` sits in
  the rail, one click away, in the same group as Deal's other destinations.
- **Underwriting is a full-page surface**, not a 280px panel. It is the finance workspace's Proforma
  tab. Forcing it into an `.rpanel` for the sake of a uniform landing mechanism is the same wrong
  shape that made Drawings a launcher rather than a side panel in v0.3.772.
- **`finance` is not a portal workspace** (`PORTAL_WORKSPACES = construction, developer, design`).
  Landing Deal there would surrender the rail that carries Deal's **16 registers** — the room's
  actual substance — to gain one panel.

So Deal lands on **Portfolio**: a real panel, in the portal, with the rail intact, and Underwriting a
labelled click away. That is the better arrangement, not a workaround for it. Was:
Give `__uw__` a real portal panel so Deal lands on Underwriting instead of Portfolio. v0.3.770 tried
to shortcut this by marking the workspace hand-off active; the marker never cleared, so a repeat
click reported arrival for a navigation that never ran. Reverted in v0.3.771, and `spine.test.ts`
now asserts no room's home carries `goto`.

### ~~5 · R25/R24-TRACE-UI~~ — **DONE v0.3.775**: the coverage figure opens onto its elements. Was:
The 5D chain made visible: figure → cost line → the elements behind it. The engines all exist; this
is the last mile that makes the differentiator discoverable by clicking rather than by reading docs.

### ~~6 · SAMPLE-LIBRARY ②~~ — **DONE v0.3.776**: a second building type, and a real one
`riverside_school_structural.mass` — 1551 elements (619 reinforcing bars, 375 beams, 299 slabs, 203
columns, 15 assemblies, 5 storeys), packaged through the same publish path a user drives. The library
now shows what the two containers are *for*: the house proves the browser authoring path end to end
at 23 elements; the school is a frame an engineer recognises. It is **structure only**, so Area and
$/ft² render as `—` with their reasons — the vitals strip working, not a gap papered over. Was:
`build_samples.py` works and the library ships (v0.3.769). What is missing is **content**: more than
one `.mass`, covering more than one building type. Blocked on authoring time, not on tooling.

### ~~7 · ONE-LOAD-SAMPLE ② + FIRST-RUN ②~~ — **DONE v0.3.777**: the last hard-coded geometry is gone
The first-run half was already built (the picker opens on zero projects, `library.test.ts` gates it).
The remainder was worse than a leftover menu entry: `viewer/app.ts` chose geometry with a **regex on
the project's name**, so a project called "Riverside School" with no published model rendered an
unrelated demo's frame, and any session with no project always did. The gate that was meant to
prevent exactly this asserted the filenames were gone from `main.ts` — and passed, while they lived
one file over as the default. **A check scoped to one file measures that file, not the behaviour.**
Removed, `library.test.ts` now reads the viewer too (mutation-checked), and the three orphaned
`.frag` assets left every build and desktop installer — 7.4 MB.

### ~~8 · MASS-FOR-EVERY-MODEL ② + CREATE/OPEN/SAVE ③~~ — **DONE v0.3.777**
Opening an IFC with the server reachable but no project fell through to "view only" — a mesh with no
quantities, no cost, no schedule, nothing to pin an RFI to, nothing saved. It now offers a container
and lands you in it. **Offers**, because creating a project writes to the user's database, and doing
that unasked is the side effect the sample picker already refuses to commit. The Open/Save menus are
re-cut by what the thing *is*: Project · Model geometry · Site context · Import. "Sample models"
stopped being a category when a sample became a real `.mass`.

## Reconciled 2026-07-29 at v0.3.796 — items completed after v0.3.777

### from 🏗 R21 — LOD 400→500 DOCUMENTATION RING *(from a real LOD 400 shop-drawing set, 2026-07-25)*

- ✅ **R21-HATCH** *(shipped v0.3.676)* — **material hatch patterns on cut geometry.** The reference details separate
  concrete (stipple), reinforced concrete (crosshatch), steel (diagonal), insulation, masonry and
  earth by *pattern*. `drawings.py` poché (v0.3.673) fills by class group with flat grey tones, which
  cannot make those distinctions at 1:10. Needs an SVG `<pattern>` library keyed to IFC material, and
  a scale-aware pattern density so a 1:100 section and a 1:10 detail do not use the same spacing.
- ✅ **R21-KEYNOTE-SECT** *(shipped v0.3.677)* — **keynote leaders with dot terminators on sections/details.** The
  package annotates every layer of the assembly ("60mm MINERAL-GLASS WOOL BOARD INSULATION",
  "RC SLAB AS PER STRUCTURAL DRAWINGS") in a left-hand text column with leaders to a dot on the
  component. `drawing.py` has `_leader_callout` for PLANS only; sections have no annotation layer.
- ✅ **R21-DETAIL-REF** *(shipped v0.3.677)* — **detail callout bubbles + the section↔detail cross-reference graph.**
  Numbered bubbles on the wall section point at enlarged details on other sheets; each detail carries
  its own bubble, title and scale ("12 / BRIDGE TOP DETAIL / 1:10"). Today nothing links a section to
  its details, so a set cannot be navigated or checked for orphaned/dangling references.
- ✅ **R21-VG-OVERRIDES** *(shipped v0.3.677)* — **object styles + rule-based view filters.** Per-category **cut vs
  projection** line weight, colour and pattern, plus filters that override graphics by rule
  ("fire rating ≠ None", "width > 900"). This is what makes output look like a drawing instead of a
  dump. **Compose on `query_dsl.py`** — it is already THE element selector; a view filter is a stored
  selector plus an override, not a new engine.

**Tier 2 — coordination depth the set implies**
- ✅ **R21-SOFT-CLASH** *(shipped v0.3.681)* — **clearance (soft) clash + a clash matrix.** Hard clash exists; the
  reference material distinguishes hard / soft-clearance / workflow-4D. Soft clash is a *rules* problem
  (NEC working space, valve access, coil pull, door swing) and the discipline-pair matrix declares
  which combinations are tested at all. Without it, "clash-free" overstates what was checked.
- ✅ **R21-TAGS** *(shipped v0.3.683)* — **element tags on drawings** (a door tagged `D2` carrying `900 x 2100`),
  auto-placed with leader avoidance, driven by the same type data the schedules already read.
- ✅ **R21-BREAKLINE** *(shipped v0.3.683)* — break lines + partial views, so a detail can stop mid-element honestly
  instead of running to the sheet edge.

**Tier 3 — set-level assembly**

### from 🎯 R22 — COMPETITIVE GAP RING *(13 platforms scanned 2026-07-25; acquisition→turnover mission)*

- ✅ **R22-GOLDEN-THREAD** — **already built** (`golden_thread.py`); verified 2026-07-29, not
  re-listed as open. Was: design freeze + immutable approval log — named baseline model states, who
  approved what and when, and a diff of everything after. Legally mandated in the UK (Building Safety
  Act 2022). *Another entry that was open in prose and closed in code — check before building.*

### from ⚡ R23 — ENGINEERING UPGRADE RING *(technical scan 2026-07-25; file:line evidence)*

- ✅ **R23-PERF-TEST** *(shipped v0.3.678)* — runtime perf budget in vitest: assert `renderer.info.render.calls` under a
  threshold, and that `renderer.info.memory.geometries/textures` returns to baseline after dispose.
  The leak assertion is the one that pays — there is already a confirmed leak (below).
- ✅ **R23-RENDERER-FLAGS** *(shipped v0.3.678)* — `viewer/world.ts:32` constructs `SimpleRenderer` with **no
  parameters**, so it silently inherits `antialias: true` always and sets no `powerPreference`.
  `antialias` is a context attribute — construction-only, so this cannot be fixed after the fact.
  **Correction on implementation:** this entry's implied fix — drop `antialias` because the composer
  already resolves 4× MSAA — was **wrong**, and the source disproved it before it shipped.
  `setPresentationFx` is opt-in, so the ordinary BIM view renders straight to the canvas; disabling it
  would have put jagged edges on every model to save work in a mode most users never enter. Shipped
  as `powerPreference: "high-performance"` + `stencil: false`, with `antialias` kept on — all four
  attributes verified on the live WebGL context.
- ✅ **R23-UPDATE-COALESCE** *(shipped v0.3.678)* — `viewer/loader.ts:25-26` fires `fragments.core.update()` on **every**
  camera-controls update event, unthrottled: the textbook expensive-pass-per-event mistake. Coalesce
  to one per rAF, keeping the rest → `update(true)` full-quality pass.
- ✅ **R23-RAF-LEAK** *(shipped v0.3.678)* — `pins/pins.ts:29-30` starts a **second permanent rAF with no cancellation
  path**, alongside the engine's own uncapped loop. It survives viewer teardown.
- ✅ **R23-PIXEL-GOVERNOR** *(shipped v0.3.678)* — pixel ratio is pinned at `min(dpr, 2)` with no adaptive downscale
  under load. A frame-time-EMA governor is the cheapest large win on a 4K display with a tall tower.

**Tier 2 — real work, high payoff**
- ✅ **R23-SHADOW-COST** *(shipped v0.3.679)* — `viewer/world.ts:182-192` puts a 2048² shadow map over a **±140 m ortho
  frustum** — catastrophic texel density on a 30-storey tower — on top of hemisphere + fill lights and
  SSAO+Bloom through a 4× MSAA composer. Set `shadowMap.autoUpdate = false` with manual invalidation,
  fit the frustum to visible bounds, and run post only on camera rest.
- ✅ **R23-REVIT-EXPORT-CFG** *(shipped v0.3.680)* — script `IFCExportConfiguration` from the pyRevit bridge instead of
  trusting the export dialog, and **enforce the `IfcGUID` shared parameter** so GlobalIds survive
  re-export. That is our first non-negotiable (reference by GUID, never transient ids) and it is
  currently left to a checkbox someone else ticks. Add a pre-publish model audit (warnings, unplaced
  rooms, in-place families, imported CAD) — exactly the conditions that produce garbage IFC.

**Tier 3 — worthwhile, lower urgency**

### from Sprint 1 — instrument, then decide *(the audit's phase 0, never built)*

- ✅ **R24-JOB-TRAY** — **SHIPPED v0.3.780.** Was *(S — was M)* — **re-scoped: this is wiring, not engineering.**
  `services/api/src/aec_api/routers/jobs.py` already enqueues, polls and lists jobs with per-kind RBAC.
  `grep -rn "/jobs" apps/web/src` returns **nothing** — no client has ever called it. Add the typed
  surface to `api/client.ts`, a self-contained `ui/jobTray.ts`, then one mount point. Another instance
  of the pattern in *what-did-we-build-that-nothing-calls*; the engine shipped and the path to it did not.

### from Sprint 3 — the front door earns its keyboard

- ✅ **R24-KEYS** — **SHIPPED v0.3.782.** One contract in `ui/keys.ts` (Anywhere · In the 3D view ·
  Draw tools), replacing the six-second toast in `main.ts` *and* the viewer's separate draw-code
  modal — `?` used to give a different answer depending on whether the 3D bundle had loaded, and
  neither surface mentioned ⌘K. `keys.test.ts` asserts the contract against the handler and against
  `keysDyn`'s code table in both directions.
  **What was deliberately NOT published:** the audit's `G then M`, `J`/`K`, `A` = answer, and
  `W S C B`. None of them exist — the draw codes are two-letter (WA · SL · CL · BM), Revit-style.
  Building them is real work and belongs to whichever ring owns registers and authoring, not to a
  help screen. A contract that lists keys nothing dispatches is how a contract stops being one.

### from Sprint 4 — field, and the long tail

- ✅ **R24-EMPTY-GUIDE ②** — **SHIPPED v0.3.787.** `ui/emptyGuide.ts` gives 24 registers a line
  saying *where their rows come from* ("An RFI is a question asked against a drawing… raise one from
  a drawing, or from an element in the model") instead of restating the "+ New" button. Curated,
  never generated: the other 109 modules keep the generic copy, because an invented upstream is a
  confident wrong answer somewhere the user cannot check it. `emptyGuide.test.ts` validates every key
  against `services/api/modules/*/module.json` — it caught two non-existent keys (`change_order`,
  `pay_app` → `change_event`, `owner_invoice`) on its first run.

### from 📐 R27 — THE DRAWING IS DATA RING *(external research 2026-07-26: one paper + 16 sources)*

* ✅ **R27-LAYOUT ②** *(shipped v0.3.706)* — **a takeoff scoped to the view it belongs to.**
  [takeoff2d.py](../services/api/src/aec_api/takeoff2d.py) takes `regions` **from the caller** and a
  `scale_units_per_px` **from the caller** — every quantity on a sheet is hand-traced and hand-
  calibrated, and nothing checks that a traced polygon sits inside the view it is being priced
  against. With ① landed: seed candidate regions from the detected viewports, and read the scale from
  the titleblock's scale text or a detected scale bar so `calibration_scale` has something to *check*
  rather than only something to accept. **The scale is proposed, never silently applied** — a takeoff
  calibrated by a machine that was wrong is worse than one nobody calibrated, because it looks done.
* ✅ **R27-LAYOUT ③** *(shipped v0.3.707)* — **a note attaches to what it governs.** Once regions exist, a general note, a
  keynote and a revision cloud each belong to a *view*, not to a page number. This is what makes
  `keynotes`/`DETAIL-REF` (R21) round-trip against received sheets rather than only our own.
* ✅ **R27-CLAIM-TYPE** *(shipped v0.3.709)* — **what kind of statement is this?** The representation handbook's one durable
  idea: a record should say whether it is an **intent** (specified), an **embodiment** (built),
  an **evidence** (measured/observed) or an **inference** (derived). `element_facts.gather()` already
  states a `source` per fact and `verified()` already prefers an IFC stamp over a field record — this
  generalises that from one engine's convention into a field the whole fact spine carries. The payoff
  is concrete: "this wall is fire-rated" sourced from a *specification* and from a *field
  observation* are different claims, and today they render identically.
* ✅ **R27-SOV-LOOP** *(shipped v0.3.702)* — **close takeoff → estimate → SOV → pay app.** Confirmed gap, not a suspicion: the
  `estimate` and `sov` modules both exist, `cost.py` reads a G703, and **nothing anywhere builds an
  SOV from an estimate**. The chain the whole cost pillar implies is broken at exactly one seam, and
  it is currently bridged by re-keying. Build `sov_from_estimate()`: estimate lines → SOV line items,
  carrying `quantity_source`/`rate_source` (shipped v0.3.699) forward so a pay-app line can be traced
  back to the model element it was measured from.

  **Shipped as `sov_build.from_estimate()` + `POST /projects/{pid}/cost/sov`.** The transformation is a
  **regrouping** — an estimate is keyed by (code, basis, rate) because those price differently; a
  contract bills the code — and the whole risk of a regrouping is money going missing inside it. Four
  refusals: unpriced scope is **excluded and named**, never dropped (an SOV built only from the lines
  that happened to price is smaller than the job and looks complete, because every line in it is
  right); the **rounding residual is placed on the largest item and reported**, because rounding each
  item then summing ≠ rounding the total once and that penny is what gets a G703 rejected; a
  zero-markup result carries **`at_cost: true`**, since scheduled values are *contract* values while an
  estimate is *cost*, and billing lump-sum off unmarked-up cost under-bills by the entire fee every
  month; and each item keeps its **GlobalIds and quantity/rate sources**, collapsing to `mixed` rather
  than rounding one measured element among fifty up to `declared`.

  `/cost/estimate` and `/cost/sov` were also collapsed onto one shared `_run_estimate` helper — two
  code paths computing "the estimate" is how a billed number stops matching the priced one.
  `reconciles` is named honestly as a **conservation** check (it proves the regrouping lost no money,
  not that the estimate was right) and is verified against **two independently-built accumulations** in
  the source.
* ✅ **R27-RISK-CALIBRATE** *(shipped v0.3.710)* — **the distribution comes from your own history, not a guess.**
  "schedule_risk.py" (deleted v0.3.972 — de-linked, not rewritten: this file is a historical record
  and the module really did exist when this was written) already ran Monte Carlo over the CPM
  network and reports P10/P50/P80/P90 — the *shape* is done. What it lacks is a defensible
  distribution: durations come from caller-supplied three-point estimates, i.e. somebody's opinion
  entered three times. The industry answer is calibration against a large historical corpus, which we
  will never have offline. **The project's own corpus we do have**: schedule baselines plus progress
  actuals are planned-vs-actual per activity. Derive per-activity-type spread from that, report
  `calibrated_from: n activities` — and when n is too small to mean anything, **say so and fall back
  to the three-point, rather than dressing an opinion as a statistic.**
* ✅ **R27-FIRM-MEMORY** *(shipped v0.3.778)* — **standards that outlive a project.**
  [firm_standards.py](../services/api/src/aec_api/firm_standards.py) + `GET/PUT /firm/rules` and
  `GET /projects/{pid}/rules/effective`. Firm rules reuse `rule_library`'s own blob path and validator
  under a reserved scope, so there is one persistence path and one definition of a valid rule; a
  project layers over them **by rule id, not by name** — matching on name would make a rename look
  like a new rule and silently reinstate the firm's version alongside the project's. Every effective
  rule states its `source`, and one that displaces a firm rule carries the version it replaced.
  Overriding is legitimate; being *invisible* is not, because the failure here is not a wrong answer,
  it is a firm discovering its standards were quietly optional. `PUT /firm/rules` is admin-only: a
  project editor may override a standard on their own job, but changing what the firm stands for is
  not a per-project act.

  **The scope question, answered rather than assumed.** The item said "org-scoped", and this codebase
  has **no `Organization` entity** — what `test_tenant_scoping` calls a tenant is RBAC over project
  membership. Rather than invent a multi-tenant model nobody asked for, *firm* means **the
  deployment**: a self-hosted install is one firm's install. Stated in the module rather than hidden;
  if organisations arrive, `FIRM_SCOPE` becomes an org id and the inheritance logic is unchanged.

## Release log v0.3.778 → v0.3.796 *(reconciled 2026-07-29)*

`roadmap-completed.md` had stopped at **v0.3.777** while `main` was at **v0.3.796** — nineteen
releases with no record here. That gap is the same doc-rot this ring keeps finding: nothing reads
prose, so nothing failed. Recorded from `CHANGELOG.md`, newest first.

- **v0.3.796 — R30-TOOLS: a register can finally say what it can DO**
- **v0.3.795 — R24-MONO-DATA, and three tests of mine that were making other tests fail**
- **v0.3.794 — the guard that would have failed a build over a dependency that exists**
- **v0.3.793 — an allowlist entry with no referent is a hole waiting for a matching name**
- **v0.3.792 — ReDoS on IFC-authored text, and the two halves of the fix**
- **v0.3.791 — R24-ELEMENT-CARD ②: the strip goes where the element is named (and a broken import from v0.3.790)**
- **v0.3.790 — an unsolvable draw was being priced at zero**
- **v0.3.789 — the public site was sending visitors after a sample that no longer exists**
- **v0.3.788 — the demo script did not know about two shipped features, and the log was out of order**
- **v0.3.787 — R24-EMPTY-GUIDE ②: an empty register says where its rows come from**
- **v0.3.786 — the public demo was serving a taxonomy the app cannot render**
- **v0.3.785 — R24-REPORTS-BY-MOMENT: the Report Center stops being a list of nouns**
- **v0.3.784 — `safeHref`: the sink that no gate in this repo was watching**
- **v0.3.783 — R24-CHARTS-GRAMMAR: an empty chart now says so**
- **v0.3.782 — R24-KEYS: one keyboard help, and it is true**
- **v0.3.781 — SEC: an imported schedule's text is not ours to trust**
- **v0.3.780 — the queue was always there; nothing had ever asked it**
- **v0.3.779 — one front door, and the rooms keep their names**
- **v0.3.778 — the R27 ring closes: a received sheet has regions, and a firm has standards**

### R30-TOOLS — shipped v0.3.796 with no roadmap entry at all

Worth naming because it was never a roadmap item: a module's `tools:` key, letting a register
declare the destinations that operate on it. 56 modules, plus the `GET /modules` allowlist
forwarding the new key (it drops anything it does not name — the failure would have been silent
with all 56 files correct), plus `moduleTools.test.ts` asserting every `dest` resolves against
`ALL_DESTS`. The engines existed the whole time; the seam from register to tool did not.


---

## Moved from the live roadmap on 2026-08-01 (at v0.3.817)

These four sections carried **zero open items** — every entry in them was shipped or closed by
decision. They are kept whole rather than summarised, because each one records *why* something was
closed, and several were closed by finding the capability already existed. That reasoning is the
part worth keeping; a one-line "done" would throw it away.

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
| **R22-ITP-NCR** | all four asks exist — `itp.point_type` is a required select (Hold/Witness/Review/Surveillance/Monitor) with method, acceptance criteria, frequency and both parties; `ncr` runs `open → dispositioned → closed` with disposition, corrective action, root cause, severity; element attachment is `element_guids` | `quality_chain` ← `routers/construction.py:260,283` · modules reachable in room `schedule` (`rooms.room_of`) |
| **R22-PROCURE-DEPTH** | all three named remainders are built — `prequalification` module (EMR, bonding capacity, revenue, references, workflow), `clause_playbook.py` (accept/negotiate/refuse per contract type, severity, fallback, deviation register), `vendor_memory.py` cross-project scorecards | `routers/realestate.py:300,309,332` · `routers/benchmarking.py:83` · modules reachable in room `planning` (`rooms.room_of`) |
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

✅ **PF-RENOVATION — SHIPPED v0.3.813 (#159).** Scope item 4 of the CRE asset-class survey
(`docs/internal/research/proforma-asset-class-scope.md`). A value-add unit now has the three phases it
actually has — in-place rent until work starts, **nothing** during renovation, renovated rent only from
the month it comes back online. Applying the premium from day one is the standard overstatement and is
invisible in the output. Pace and per-unit downtime are **required, never defaulted**: without them the
model either renovates everything instantly or costs only its capex, and either is indistinguishable
from a correct answer. Items 1–3 (income basis, rent-roll wiring, rollover pricing) shipped in
v0.3.811–812; **items 5 (hotel ADR/RevPAR + data-centre capacity) and 6 (mezzanine/refinance) remain**.

⭐ **R22-ENTITLEMENT** (M/L) · **R22-REPORT-BUILDER** (M, rescoped) · **R22-PIPELINE** (M) ·
**R21-4D-CLASH** (phase 2)

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


### FIN-SUITE-BLIND — CLOSED 2026-08-01 (v0.3.812-814), moved out of Band 1

- ✅ ~~**FIN-SUITE-BLIND**~~ *(CLOSED 2026-08-01, v0.3.814)* — **the G702 slice is done; the sweep across the
  other finance suites is not.** The named evidence was checked and acted on: `retainage_prev` (G702
  line 7) was asserted in **zero tests, in any file**, which is why a 10%-retainage contract could
  report a negative payment due while the suite stayed green. `test_g702_lines.py` now value-checks
  lines 5–8 on a fixture that **distinguishes** — mixed per-line rates (10% / 5% / 0%), because with a
  single default rate the broken and correct implementations agree by coincidence.

  Writing that fixture found a second, live money defect: `ret_pct = _n(...) or DEFAULT_RETAINAGE`
  treated an **explicit 0%** as unset, so a line the owner had agreed to hold nothing on had the 5%
  default withheld anyway — $1,000 wrongly held on a $20,000 line. Fixed and mutation-proved.

  ✅ **THE SWEEP IS DONE — 2026-08-01 (v0.3.814).** `reserve.py`, `benchmarking.py` and `proforma/`
  were each asked what their suites cannot see.

  * **`reserve.py` — two live defects.** The suggested annual contribution came from a binary search
    that returned its upper bound after forty halvings **without ever testing that bound was
    feasible**; against an opening deficit it is not, so a 500k shortfall produced a confident
    80,001/yr that came back underfunded from year one when re-run at exactly that figure. There was
    nothing to search for — solvency through year *k* means `c >= (cum_out(k) - opening) / k`, so the
    answer is the largest of those, solved in one pass. It now re-runs its own schedule at its own
    answer and reports `suggestion_clears_horizon`. Second: an asset with a cost and a life but **no
    install date** was projected as installed *today* — the most optimistic reading available — so a
    20-year component contributed nothing to a 25-year study while `components_missing_data` read 0.
    Now named and counted, not dropped.
    The test could not see either: `assert suggested > 10000` passed for ~10⁵ wrong answers, and no
    fixture had a negative opening balance. It now pins the exact value (66667, binding year named)
    and asserts **one dollar less does NOT clear** — otherwise any over-estimate satisfies it.
  * **`benchmarking.py` — the tests were already sound** (p25/median/p75 interpolation, overdue
    counts, a 14-day turnaround all value-checked). The defect found was a directive violation in the
    module docstring, not a maths hole.
  * **`proforma/` — covered.** `loan.py` exercises all three funding modes with value assertions and
    names what it deliberately does *not* assert; `exit_cap` is schema-validated `gt=0` so the
    defensive `or 0.0` in `operations.reversion` is unreachable from the route. Live invariants were
    re-verified over HTTP across all three funding modes: sources == uses, LP+GP == equity, no
    unscheduled cost lines, and a `min_dscr` covenant provably binding (19.00M → 18.74M).


### Band 2 R32 filing-spine record — moved out of the live roadmap 2026-08-01

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

---

## ✅ 2026-08-06 — the four-lane day *(v0.3.861 → v0.3.874, 24 items)*

Four sessions shipping to `main` at once. What landed is below; **what the day actually taught is in
`docs/roadmap-directions.md`**, because most of it was about instruments rather than features.

Three workflow defects were found by measuring rather than reading, and all three were GitHub starter
templates whose assumptions this repo's merge rate had outgrown: `pages.yml` deploying on every
`docs/**` touch (main red for two and a half hours), `ci.yml` with no concurrency at all (a full
suite per superseded rebase), and `codeql.yml` running four language analyses per PR push with
nothing superseding the stale ones — 15 of 28 queued jobs.

The recurring failure was not a bug in the code. **Four times in one day an instrument measured a
tree other than the commit it named**: a bundle budget set from a stale working copy and landing
below the artefact it gated; a scoping test that reported "all four languages" because `jq` was
absent and the fail-safe fired correctly; a citation gate failing on three paths that were on `main`
while the suite ran 112 commits behind; and a lockfile copied from that same stale clone, caught by
`versionConsistency.test.ts`. Each time the code was fine.

- ✅ **R35-PIDLOCK-XPROC** *(M — Lane C, SHIPPED `2b332674`; **body corrected 2026-08-05**)* — the
  paragraph below described the problem in the present tense long after the fix landed, so a ✅ item
  read as open work. It said `pid_lock` serialises "within one process only"; since `2b332674` it
  takes a **Postgres session advisory lock** as well. **The one true residue, now enforced rather
  than narrated:** on any non-Postgres backend there is no advisory lock, so serialisation really is
  in-process only — and v0.3.869's worker split made that reachable in a new way, since a dedicated
  worker is a second writer by definition. v0.3.872 closes it: `services/api/src/aec_api/worker.py` refuses to start there,
  and the boot guard counts **writer processes** rather than uvicorn workers. Historical description
  follows. — `pid_lock.mutating(pid)` serialises the sidecar
  read-modify-write (docmanager index, edit history) **within one process only**, and the module said
  so plainly. Under `uvicorn --workers > 1` two workers can interleave load→save on the same project
  and the first writer's entry is silently lost — no error, no duplicate, just an index that forgot
  something. The v0.3.817 sweep fixed the two seams that had a *database* to arbitrate them (ref
  counter, job claim); this one writes to object storage, so it needs either a DB advisory lock or a
  storage CAS. **Keep the `mutating(pid)` interface** so no caller changes.
  *Until it lands, single-writer-per-project is the supported deployment shape — that is a real
  constraint on the product, not a note.*

- ✅ **R22-OPTION-OBJECT** *(S/M — done)* — option as the primary object: geometry + unit mix + cost +
  carbon + IRR as one comparable record, so no massing is ever evaluated without its returns.
  `option_object.py`, served at `GET /projects/{pid}/design/options/record`. **Band 3 outcome: all
  four engines already existed and were good — nothing joined them**, so a reader compared schemes
  across three screens by eye, which is the failure the entry's own sentence describes. The join
  re-derives nothing; each number comes from the engine that owns it, and each engine's `basis`
  (declared / benchmark / derived / unlinked) is carried through rather than flattened. It refuses
  twice: a missing axis is `absent`, never a zero (`option_score` once coerced a missing `cost_per_sf`
  to 0.0 and scored it **100** on a lower-is-better axis), and it does **not** rank — `option_score`
  owns that. `comparable_count` is the number to read.
  *The defect worth remembering was in the seam, not the logic:* the first join read `total_cost`,
  `equity_irr` and `carbon_intensity_kgco2e_m2`, **none of which any engine emits**. It returned all
  five axes absent for a fully-populated project while its unit test passed, because the fixture was
  invented alongside the code — both sides of the join were wrong in the same way and agreed
  perfectly. A test that supplies both sides of a join cannot see the only defect that matters;
  `test_option_object_route.py` supplies neither and asserts every axis equals what its owning route
  serves.

- ✅ **R22-PM-CONTRACTS** *(M — Lane H, SHIPPED 2026-08-06)* — **preventative-maintenance contracts
  from turnover data.** The COBie asset register, warranties and service intervals become billable
  recurring PM contracts. Extends past turnover without breaking the mission.

  **Premise-checked first, and the entry was half wrong — in the direction that wastes work rather
  than causing a defect.** Read as written, this item sounds like PM capability is missing. It is
  not: `pm_schedule`, `warranty`, `asset_register`, `work_order`, `equipment_log` and `cmms.py` were
  all already here, and `pm_schedule` even carries `frequency_days`/`next_due` and a
  "Generate PM work orders" tool. What did **not** exist is the item's actual noun — a *billable
  recurring service agreement*. The four contract-shaped registers are all **construction** contracts
  (`prime_contract`, `subcontract`, `owner_invoice`, `sub_invoice`); not one models a term, a billing
  frequency, an escalation, a renewal notice or a response SLA. So the gap was real and much narrower
  than an M implies: one register, not a subsystem. *Recorded rather than deleted, because "checked,
  and here is what was actually missing" is what stops the next agent re-running the check.*

  **Shipped:** `services/api/modules/pm_contract/module.json` — 18 fields in four contiguous
  fieldsets (Agreement / Coverage / Term / Commercial), referencing `company`, `asset_register`,
  `pm_schedule` and `warranty`, with a six-state workflow carrying the renewal path
  (`draft → active → expiring → renewed → active`, plus lapse and terminate). `PMC` prefix verified
  free against all 135 pre-existing registers. Alembic revision `a7e3b9c04d15` chained to head,
  **including the Postgres FTS GIN tail** — the part that reads as boilerplate and is the reason a
  post-baseline module silently loses full-text search on Postgres while passing every SQLite test.

  **A gate caught me writing a commercial term nobody agreed to.** The first draft defaulted
  `billing_frequency` to "Quarterly" and `coverage` to "Labour only" — helpful-looking, and exactly
  what `test_field_attrs.py` forbids: it caps defaults across every register at eight and requires
  each to be a fact about the **record** (a daily report is filed today), never a **policy**. On a
  contract register that rule is at its sharpest: a defaulted billing frequency is a *term*, and it
  would have been recorded as though someone had chosen it, invisibly, because a default looks
  deliberate. Both removed. Worth noting that this is a **ceiling, not a floor** — the only such
  assertion in the module gates, because here the risk runs toward adding rather than omitting.

  **The `starts_after_warranty` flag is the join the item was actually asking for.** A PM contract
  that begins while the equipment warranty still runs is money paid twice for the same obligation;
  the field, plus the `warranty` reference, is what lets turnover data drive the contract start date
  rather than a guess.

  **Reachability measured over HTTP, not inferred:** `GET /modules` returns **136 (was 135)** with
  `pm_contract` present and a key-shape identical to `pm_schedule`, including the derived `room`.
  Worth recording how the first probe lied: it reported `/modules` → 200 with **0 modules**, which
  reads as an empty registry and was the instrument — `TestClient(app)` outside a `with` block never
  runs startup, so the registry never loaded. The route had been answering 200 the whole time.
  (`/modules/{key}` 404s for `pm_schedule` too; that route shape does not exist.)

- ✅ **R23-STOREY-LOD** *(L — SHIPPED, PR #176/#178/#179)* — server-side coarse proxies per storey (extruded footprint / AABB) for
  small parts, MEP and furniture, swapping to real fragments on demand. Server-side keeps it
  deterministic, offline and $0. **Blocker retired by measurement 2026-08-02:** the recorded
  "no Fragments writer" blocker blocks *direct encoding* of a `.frag` in Python, not *production* of
  one — a proxy authored as IFC runs through the converter this repo already ships (measured end to
  end: 3 storeys → proxy IFC in 5.6 s → 3,817-byte frag in 6.4 s, zero new dependencies). The same
  sentence genuinely does still block **viewer-side** LOD; the two differ by one process boundary we
  own. *`docs/internal/archive/phase2-large-models.md` claims no custom LOD is needed and is
  itself marked superseded — that claim is the thing to retire (still unverified).*

- ✅ **R24-TOOLS-SPLIT** *(SHIPPED v0.3.848)* — authoring verbs act instantly; analyses produce an
  artifact after a wait. The `qa` section is cut in two and Analyse is a rail item of its own; see the
  record below. The item's second half — giving those analyses a *history* rather than a modal — is
  `R24-RUNS-INBOX` and stays open.

* ✅ **R28-UNIFY ①** *(marker added 2026-08-06 — the lane table already said SHIPPED and MERGED, and `apps/web/src/shell/openUnify.ts` declares it in its opening line; only the marker was missing)* — **one open, one save.** Opening any model creates or attaches a project (with its
  API data if it exists); opening a project ensures a model exists — **a blank authorable one if
  there is none**, so a user can start drawing immediately rather than meeting an empty viewer. This
  is the item that removes the class of bug, not the two instances of it.

* ✅ **R28-ICDD ③ — a standards-conformant envelope.** Emit and read ISO 21597 containers, with our
  payloads as documents and the GlobalId-keyed relationships as RDF linksets. `.mass` can then simply
  **be** an ICDD container with our extension — the branding without the lock-in.
  ✅ **`rdflib` (BSD-3) is APPROVED** *(user, 2026-07-26)* — no longer gated. Licensing is recorded in
  [ATTRIBUTIONS.md](ATTRIBUTIONS.md), which also states that the container is implemented from the
  **published standard** and that no ISO specification text is redistributed. The dependency is pinned
  in `requirements.in` **in the change that first uses it**, with `requirements.lock` regenerated in the
  same commit — the lockfile gate fails any push that leaves the two out of step, and a dependency
  carried ahead of its code is supply-chain surface for no benefit.

* ✅ **PERF-RATE ② — DONE, verified 2026-08-06; the entry described behaviour that changed in
  v0.3.721.** It now **refuses to start**: `_rate_limit_is_per_worker()` appends to `problems`, and
  `_production_guard` raises *"refusing to start a production deployment with an unsafe
  configuration"*. The prescription below — *"Refuse to start, or drop to one worker"* — was carried
  out; only the entry lagged. `main.py`'s own comment records the change: *"Until v0.3.721 this logged
  CRITICAL and then started anyway: the loudest possible message, followed by the exact behaviour it
  warned about."* Original text: **the rate limit is per-worker and only warns.** Verified at `main.py:155-162`: with
  `AEC_RATE_LIMIT_RPM>0`, multiple workers and no `AEC_REDIS_URL`, each worker counts independently, so
  the effective limit is N× the configured one. It logs `CRITICAL` and **starts anyway**. A security
  control that announces it is not working and then runs is worse than one that is absent, because the
  operator believes it is on. Refuse to start, or drop to one worker.

* ✅ **R22-PHOTO-CV Tier 1 — SHIPPED v0.3.851.** `services/api/src/aec_api/photo_cv.py`, wired into
  `services/api/src/aec_api/routers/verification.py`. The gap was never a model, it was a **consumer**:
  that route had been attaching photos to GlobalIds for months and nothing ever read one.

  Tier 1 is classical image processing with **no new dependency** — numpy and pillow were already in
  both lockfiles. A quality gate (Laplacian-variance focus + exposure clipping) **flags** a photo that
  carries no evidence, a perceptual hash catches the same shot uploaded against thirty elements to
  clear a checklist, and a normalised comparison screens the incoming photo against the outgoing one
  at upload — the only moment both exist, since `photo_key` is a single column.

  **The gate FLAGS, it does not REFUSE — corrected in v0.3.852, and the distinction was bought the
  hard way.** As first shipped it returned a 400 for anything it could not decode. That reddened main,
  and the red build was the lesser problem: **iPhones shoot HEIC by default and Pillow cannot decode
  HEIC without `pillow-heif`**, which is not a dependency here, so the gate would have rejected the
  most likely genuine field photo on the platform most field engineers carry. Silent data loss wearing
  the costume of a safety check — and one CI could never catch, because no fixture is a real phone
  photo. It also contradicted its own docstring one paragraph up, which argues a blurred frame must be
  kept because the engineer may have no better shot. An undecodable upload is now stored with
  `quality.analysed = False`: **between discarding real evidence and keeping something unreadable,
  keeping is the recoverable error.**

  **A second defect rode in on that fix (v0.3.853).** The decoder's exception was interpolated into
  the response, leaking `<_io.BytesIO object at 0x7f…>`; CodeQL flagged `py/stack-trace-exposure` on
  the exact line, taking open alerts 0 → 1 on the fixing commit. Detail now goes to the log and the
  caller gets a fixed sentence. Both behaviours are mutation-checked in
  `services/api/test_verification.py` — restoring either defect reds the suite.

  **The API states its own confidence, because the mathematics is asymmetric.** `near_identical=True`
  is a strong claim; a high `change_score` is a screening signal only, and a camera move scores higher
  than most real change. That asymmetry is asserted in `services/api/test_photo_cv.py`, whose
  load-bearing case is that an *exposure* shift must NOT read as change — a test that failed on first
  run and corrected the design: dHash is not exposure-invariant where highlights clip, so it cannot
  veto the two measures that are invariant by construction.

* ✅ **R22-PHOTO-CV Tier 2 — pretrained detection** *(M — decided 2026-08-03: site logistics first)*.
  Torch + torchvision (**both BSD-3**) for training/export only; the API service gets **onnxruntime**
  (MIT, ~50 MB) so the training framework never enters the deployed image. Per the dependency rule
  above, neither is pinned until the code that uses it lands. First target is COCO-pretrained
  detection — people, vehicles, plant — which needs **zero labelling** and proves the pipeline end to
  end on real photos before anyone labels anything. `photo_cv.photo_quality` becomes the pre-filter:
  feeding a blurred frame to a detector produces confident nonsense.

  **The licence objection recorded here until 2026-08-03 was wrong and is retracted.** It read "a CV
  model is a new dependency and probably a large one… licences must be MIT/BSD/Apache", implying the
  frameworks were the problem. They are not: torch, torchvision, scikit-image and scikit-learn are
  BSD-3 and OpenCV is Apache-2.0. **The actual trap is Ultralytics YOLO, which is AGPL** — and it is
  what nearly every tutorial reaches for, so name it rather than the category.

* ✅ **R22-PHOTO-CV Tier 2 — VALIDATED on a real photograph, 2026-08-04.** The claim the unit suite
  is structurally unable to make is now settled by observation. Against a CC BY 3.0 construction
  photo from Wikimedia Commons ("A day's work done, Hitchin railway flyover workers go home"),
  `scripts/try_detect.py` returned **5 people and 1 car in 1.18 s**, scores 0.58–0.99.

  **The box geometry is what makes it convincing, not the count.** People came back 40–62 px wide by
  135–160 px tall — roughly 1:2.6, the human aspect ratio — clustered together, while the car was
  104×44, wide and short, elsewhere in the frame. A miswired preprocessing step produces plausible
  *counts* but not correct *proportions*; this is the check that would have caught the CHW/NCHW bug
  fixed in v0.3.857 had a photo been available then.

  The test photo is **not committed** — it is third-party CC BY content and the repo has no need of
  it. `scripts/try_detect.py` points at any local image, which is the reusable half.

- ✅ **R38-NODE-SLIDERS ③** *(S, Lane E — **checked 2026-08-06 and found ALREADY BUILT**, not
  started)* — `apps/web/src/viewer/nodeSliders.ts` declares itself this item's implementation in its
  opening line, exports `sliderSpecs` / `applySlider`, and carries 9 tests.
  `apps/web/src/viewer/nodeCanvas.ts` wires it: a **🎚 Sliders** button opens a side rail holding
  every numeric parameter across the graph as a named slider (`n2 · recipe`), scrubbed with the
  mouse, with run-on-release. Reachable from `apps/web/src/viewer/app.ts` via `openNodeCanvas`.
  The textarea stays the single source of truth — a slider reads the JSON and writes the JSON, so
  hand-edits and scrubs interleave without two copies drifting. Original text: node-canvas inputs
  exposed as named room-level sliders. Unblocked and small; the node graph already stores its
  inputs. Lowest risk of the three.

- ✅ **R41-GATE-SUBSTANCE** *(S — Lane J, SHIPPED 2026-08-06)* —
  **`services/api/test_claude_md_gates.py` proves a cited path resolves; it does not prove the file
  still says anything.** A path can resolve to a twelve-byte stub. Shipped as
  `services/api/test_doc_substance.py` over eight artefacts.

  **A floor is not a ratchet, and writing it like one would have been wrong.** `test_file_sizes.py`
  sets per-file *ceilings* at the exact current value, because the direction of travel is down and
  slack makes them decorative. **A floor is the mirror image, and the same reasoning gives the
  opposite answer:** these artefacts legitimately *lose* content — the roadmap sheds items into
  `docs/roadmap-completed.md`, the README gets tightened, a demo corpus is regenerated smaller. A
  floor at today's value fails on every honest deletion, and a gate that goes red when you do the
  right thing is one people switch off. So the floors sit clearly below current and far above a stub:
  they catch **truncation, not shrinkage.**

  **Bytes alone are a poor proxy and the mutation test proved it.** A file of repeated whitespace
  passes a byte floor — so markdown is measured by **headings** as well, and the two data catalogues
  by **entry count**. `apps/web/src/demo/demoData.json` is minified to a single line, so a
  line-count floor reads **zero** for a healthy 1.4 MB file; that is why this is its own gate rather
  than another map inside the line-count one. *The unit that detects a stub differs per artefact.*

  Covered: `docs/roadmap.md` (226 KB / 61 headings) · `docs/roadmap-directions.md` ·
  `docs/roadmap-completed.md` — deliberately **not** citation-gated, so nothing else would notice it
  emptying · `README.md` · `CLAUDE.md` · `LICENSE-NOTES.md` ·
  `services/data/families/external/manifest.json` (the family shelf: 57 `packs`) ·
  `apps/web/src/demo/demoData.json` (1,249 endpoint keys).

  Mutation-checked in all three modes: truncate the roadmap to ten bytes → red; 240 KB of newlines
  with **zero headings** → red; the shelf reduced to 3 packs but padded to 214 KB → red. The last two
  are the ones a byte floor alone would have passed.

  **The rate tables named in the original entry were deliberately left out.** `equipment_rate`,
  `labor_rate` and `material_rate` are `module.json` *schemas*, not data files, and
  `module_schema.py` already rejects a malformed one — a size floor there would guard something that
  is guarded, while implying the rate *data* is covered when it lives in the database.

- ✅ **R41-LICENCE-GATE** *(S — Lane J, SHIPPED 2026-08-06)* — **enforce the licence allowlist in CI
  instead of by reading.** This scan found three repositories whose actual LICENSE differs from their
  README or badge, two of them forbidding exactly our use.

  **Premise-checked, and the gate half-existed.** `services/api/test_license_gate.py` already fails
  the build on a GPL/AGPL dependency — so the item as written ("enforce it in CI instead of by
  reading") was already true. What was *not* true was its scope, in two ways that matter and that the
  entry did not distinguish:

  1. **It walks Python distributions only.** The npm tree — **638 packages**, including `three`,
     `web-ifc` and the whole That Open stack — was never in its population.
  2. **It reads DECLARED metadata** (Trove classifiers, the `License` field, the SPDX expression).
     *That is the badge.* **A declaration cannot catch a lying declaration**, which is the exact
     defect the item was filed about.

  So `apps/web/scripts/check-licences.mjs` reads each package's **LICENSE file** and cross-checks it
  against the declaration — two independent statements about one fact, disagreement is the signal,
  the same shape as the roadmap self-consistency gate on a different artefact. It runs in the **web**
  CI job, because that is the job that runs `npm ci`; in the API gate `node_modules` does not exist
  and the scan would have passed by finding nothing.

  **It found the defect in our own docs.** `LICENSE-NOTES.md` listed *"That Open Engine
  (`@thatopen/*`, web-ifc) | MIT-style | Permissive"*. The `@thatopen/*` packages are MIT; **`web-ifc`
  is MPL-2.0** — weak, file-level copyleft with a real obligation attached to modifying it. Corrected,
  and the table now says it is checked rather than merely written.

  **The false positive it almost shipped with is the reusable part.** The first classifier tested
  licence names in *precedence* order, GPL before MPL, and reported three contradictions — one being
  `web-ifc` "declared MPL-2.0 but actually GPL", a core dependency named in the non-negotiables.
  Wrong: **MPL-2.0 defines "Secondary License" by naming the GNU GPL, LGPL and AGPL**, so every
  MPL-2.0 file contains the string. The fix is not a longer exclusion list but a different rule —
  **the earliest title wins**, because a licence names itself at the top and every later mention is
  prose about a different licence. *An alarming result should raise the bar on the instrument, not
  lower it*: three hits including a core dependency was the moment to doubt the classifier.

  Current state: 638 packages, **0 forbidden**, 3 weak-copyleft reported (`web-ifc` + two
  `lightningcss` builds, all MPL), 8 unclassified held as a down-only ratchet. Mutation-checked with a
  planted package declaring MIT over an AGPL file → `CONTRADICTION`, and declaring AGPL outright →
  `FORBIDDEN`.

  **Still open from this entry, deliberately not done here:** the filesystem CVE scan and the
  Dockerfile linter. Both are separate tools with their own populations; folding them into a licence
  gate would repeat the scope confusion this item just corrected.

- ✅ **R39-WORKER-SAFE** *(shipped v0.3.872 — the guard whose population I widened without widening
  the guard)* — `_production_guard` refused to boot a deployment that could not serialise sidecar
  writes across workers, testing `_worker_count() > 1`. That was **one route** to having two writer
  processes. R39-WORKER-SPLIT added a second, independent one: `AEC_JOB_WORKER=off` moves the job
  worker into its own process, so `UVICORN_WORKERS=1` plus a dedicated worker container is two
  writers and sailed straight through. On anything but Postgres, `pid_lock` degrades to a
  `threading.RLock` that two processes cannot share, and a mutating job interleaving with an API edit
  drops a sidecar entry **with nothing raised**.

  The guard was correct when written and became wrong when the product grew a new way to do the thing
  it forbids. That is the failure mode of any check that enumerates *causes* rather than measuring the
  *condition* — it cannot know about a cause invented later, and it keeps reporting green.

  Closed on both sides: the boot guard now counts writer processes and names which second writer it
  found, and `services/api/src/aec_api/worker.py` refuses to start where the lock cannot span
  processes —
  `AEC_WORKER_ALLOW_UNSAFE_LOCK=1` accepts the risk explicitly and still warns. **A guard that runs
  where the risk is beats one that runs where the config is**: the API's guard is production-scoped
  and the worker can be pointed at a database the API never saw. The dialect is read from
  `DATABASE_URL`, not from a live session, for the reason `main.py` already documented one file over
  — a connection blip must not permanently refuse a good deployment.

- ✅ **R39-STALL-VISIBLE** *(shipped v0.3.870 — the hole R39-WORKER-SPLIT opened, closed)* — once the
  worker can live in another container, **nothing the API can see changes when it dies.** The API is
  healthy (it does not run jobs), the worker container may be up and wedged, and every enqueue keeps
  succeeding. The only difference between a stalled queue and a healthy idle one is that a stalled
  queue has an *old job at its head*.

  So `/metrics` now exposes `aec_jobs_oldest_queued_seconds` — the age of the head — plus
  `aec_jobs_by_state`, `aec_jobs_worker_inline` and `aec_jobs_stats_ok`. Three choices carry the
  whole design, each one a way the metric could have read as reassuring while being useless:

  · **the age series is OMITTED on an empty queue, never 0.** Zero says "the head is brand new" when
    the truth is "there is no head", and it would make a `> 600` rule both permanently quiet on a
    stall and permanently healthy-looking. Absence is the Prometheus idiom for an unmeasured value.
  · **`aec_jobs_stats_ok` is always emitted** — it is the gauge that says whether the others mean
    anything. Without it a database the scrape cannot reach and a perfectly empty queue produce
    identical output, and an operator will read the reassuring one.
  · **age is the alarm, depth is not.** A deep queue draining fast is healthy; one job wedged for six
    hours never crosses a depth threshold. Depth is exported to *scale* on, not to page on.

  `services/api/test_job_stall.py` asserts all three, plus that the block actually comes out of the
  `/metrics` route rather than only out of the function — a perfect metric no endpoint serves is the
  same defect as a tested module behind no route. Four mutations tried, four caught.

- ✅ **R39-WORKER-SPLIT** *(shipped v0.3.869 — the platform's real scaling ceiling)* — the durable
  job queue ran as a **daemon thread inside the API process**, so the heavy kinds (full-model COBie,
  bundle generation, generative runs — all CPU- and memory-bound IFC parses) competed with every HTTP
  request the same container was serving. The symptom was never an error: one person converting a
  large model made the whole application slower for everyone, which reads as "the product is slow"
  rather than "a job is running".

  **Two things had already landed that made the split safe, and a stale comment hid both.**
  `jobs._claim_next` is a compare-and-swap (`UPDATE … WHERE id = :id AND state = 'queued'`) that is
  already correct across processes and hosts, and `pid_lock` became cross-process in
  R35-PIDLOCK-XPROC. But the `jobs.py` docstring still read *"the in-process claim is safe for the
  supported single-writer deployment; multi-worker deployments would add a DB row-lock claim
  (SELECT … FOR UPDATE SKIP LOCKED)"* — **both halves false**, and `FOR UPDATE` is a silent no-op on
  SQLite besides. A comment that talks the reader out of a capability the code already has is worse
  than no comment: it would have stopped exactly this change, and it was written by the same effort
  that built the CAS.

  Shipped: `AEC_JOB_WORKER` (`inline` default, `off` to serve requests only), the
  `python -m aec_api.worker` entrypoint in `services/api/src/aec_api/worker.py`, and a `worker`
  service in both compose files sharing the API's image and environment by YAML anchor. Scale it with
  `--scale worker=N`.

  **The failure mode this creates, and how it is held closed.** Setting `off` without running a
  worker means every enqueue succeeds, every row is written, every caller is told the work is under
  way, and nothing ever runs — no exception, no failed healthcheck, because the API is genuinely
  fine. `services/api/test_worker_split.py` therefore checks the flag *through a started app* in both
  directions (asserting only the `off` case would pass on a build where the worker never starts at
  all), drives a real job through `run_forever()`, and fails the build if any compose file sets `off`
  without a service that runs the worker. All four mutations were tried and all four fail the gate.

  The original text: the per-endpoint throttles in
  `services/api/src/aec_api/throttle.py` keep in-process counters, so behind N workers every limit is
  silently N× its configured value — the exact defect the rate-limit boot guard refuses for
  `AEC_RATE_LIMIT_RPM`, one file over. Back the counters with Redis when `AEC_REDIS_URL` is set (the
  seam the rate limiter already uses), and fold "endpoint throttles are per-worker" into the same
  production-guard warning so the operator is told instead of protected-in-name-only.

* ✅ **A29-PLACE-VALID ②** — **SHIPPED v0.3.831** — *say no before the round-trip, not after.* Pascal's spatial grid answers
  `canPlaceOnFloor` / `canPlaceOnWall` / `getSlabElevationAt` before a placement commits. We validate
  server-side, so an invalid placement costs a full round-trip to be told no. Reuse the existing
  `inference.ts` maths; this is a pure function and belongs beside it, unit-tested the same way.

* ✅ **A29-SPATIAL-SELECT ②** — **SHIPPED v0.3.832** — *click depth, not just objects.* Their selection walks Site → Building →
  Level → Zone → Item. That hierarchy is **IfcSite → IfcBuilding → IfcBuildingStorey → IfcSpace →
  element** — we hold the real one and navigate it as a flat list. This is the item where being
  IFC-native makes the feature *better* for us than for them, because their tree is a convention and
  ours is the model.

* ✅ **A29-UNDO-LOCAL ③** — **SHIPPED v0.3.833** — *undo the stroke, not the commit.* We version on the server; they keep a
  50-step in-browser history. Both are right for different questions — "undo my last three drags"
  should not require three republishes. Scope: the in-progress draft only, discarded on commit, with
  the server history unchanged as the record.

- ✅ **UX-AR** *(S — **checked 2026-08-06: ALREADY BUILT, and built better than this asked**)* —
  Sent→Approved→Paid manual status pipeline on invoices/bills (no payment rails).
  `services/api/modules/owner_invoice/module.json` and
  `services/api/modules/sub_invoice/module.json` both carry a real **workflow state machine**, not
  the manual status field this asked for: owner invoices run `draft → submitted → approved →
  rejected → paid` with transitions gated by **party**, sub invoices run `submitted → approved →
  paid → rejected`. The "(no payment rails)" constraint also still holds — there is no payment
  integration anywhere in `services/api/src`.

  **Two things about this entry are worth more than the tick.**

  *The ID is misleading and the lane follows the ID.* `UX-AR` sits in **Lane E · Authoring feel &
  viewer**, between `R28-VIEWER ④`, `R22-PUBLIC-VIEWER` and `R36-VIEWER-SUBAPP`. Read there, "AR"
  is **augmented reality**. It is **accounts receivable** — Billing. Its implementation is
  `services/api/modules/*/module.json`, which is **Lane H · Registers**. *Not moved here: the lane
  table is mid-restructure and belongs to the release holder — flagged for that pass.*

  *This is the ID-collision class `apps/web/src/shell/roadmapStale.test.ts` says it deliberately
  cannot catch* — "two different items sharing a name … detecting the next one needs a human reading
  two entries, not a regex". Here it is not two items sharing a name but **one name reading as two
  different things depending on which lane you meet it in**, which is worse: nothing is ambiguous
  until you notice, and a viewer session would have skipped it forever as somebody else's AR work.

- ✅ **R35-PIDLOCK-XPROC** *(M — SHIPPED `2b332674`)* — `pid_lock` serialises sidecar read-modify-write **in-process only**
  and says so honestly; `uvicorn --workers > 1` needs a shared lock (DB advisory lock or storage
  CAS). Until then single-writer-per-project is the supported shape. The item is the DB advisory
  lock, behind the same `mutating(pid)` interface so callers do not change.

- ✅ **AUTH-SNAP-OVERRIDE** *(S — Lane E; **SHIPPED — PR #192, merged `b9e4303f`**. Premise corrected
  2026-08-06 — the original text below described a mode that does not exist)* — a one-shot snap override for a single
  pick. Codes `EN` `MI` `CE` `PE` `NE` `NO` typed into the same two-letter buffer that arms the draw
  tools, spent by the next click, Escape cancels it and leaves the tool armed.
  `apps/web/src/viewer/snapOverride.ts` holds the table, the one-shot state machine and a
  single-kind candidate producer; `apps/web/src/viewer/snapEngine.ts` gains `perpendicularSnaps`,
  `nearestSnaps` and a kind filter on `resolveSnap`.

  **⚠️ The premise was wrong in two ways, and the second one is the interesting one.**

  *First:* there is **no modal snap preference to change.** The only snap setting in the app is
  `getSettings().snap`, a grid **increment** — a number. Object-snap is entirely automatic with a
  fixed precedence (typed constraint → Shift ortho → geometry snap → axis inference → polar → grid)
  and no part of it can be aimed. The gap was never "the mode is inconvenient to flip"; a drafter
  **could not ask for a snap kind at all, ever**. An entry describing a mode nobody built would have
  sent the next reader looking for it.

  *Second — this belongs in the built-but-unreachable tally, not in the authoring-feel ring.*
  `resolveSnap` and `segmentSnaps` in `apps/web/src/viewer/snapEngine.ts` — the priority-ordered
  resolver, the half that knows what a snap *kind* is — had **zero callers**. Only `polarConstrain`
  and `applyDynamicInput` were wired. `perpendicular` sat in the `SnapKind` union the whole time with
  nothing anywhere able to produce a candidate of that kind. Built, tested, correct, unreachable.

  **And no gate could have seen it.** `apps/web/src/shell/roadmapStale.test.ts` catches exactly this
  shape — an open item whose module already declares itself the implementation — but its population is
  `services/api/src` and `services/data/src`, **Python only**. A capability built in the web tree is
  structurally outside what it scans, so it stays "open" on this list with nothing to notice. Same
  hole `test_reachable.py` leaves on the other side: it asks whether a *module* is reachable from a
  route, never whether a *capability* is reachable from the product. Filed here as evidence that the
  population of any such gate has to cover `apps/web/src/` too, alongside the API-side instances found
  the same day (`/proforma/renovation`, `/proforma/rollover`, `/proforma/income-basis` with no
  frontend caller; `suggestion_clears_horizon` and `nothing_renovated` emitted and unrendered).

  Original text, kept because the chord suggestion still stands: a one-shot snap override for a single
  pick (theirs is Shift+right-click; Shift is already ortho lock here, so pick a free chord). The
  genuine gap: today a snap preference is modal, and needing *this one pick* to take a perpendicular
  means changing a mode and changing it back.

- ✅ **RAIL-DRAG** *(M — Lane E; **SHIPPED PR #197**)* — the palette rows in
  `apps/web/src/viewer/draft/draftPanel.ts` are drag sources; `apps/web/src/viewer/railDrag.ts` owns
  the payload rules and the one-drop-is-one-point verdict; `apps/web/src/viewer/app.ts` makes the
  canvas a drop target that hands the `DragEvent` straight to `captureDraftPoint`. One pipeline, two
  gestures, as the entry required.

  **Two findings worth keeping, because neither is about dragging.**

  *A drop is one point, and the catalog is not.* `draftCatalog` elements are `points: 1 | 2 | "poly"`,
  so a drop can only *finish* a `points: 1` element; a wall or a slab gets its **first** point and
  stays armed. The entry did not say this and it is the whole shape of the interaction. It is
  asserted as a partition over the real catalog rather than over examples, so a fourth arity added
  later fails a build instead of silently telling the user to double-click something that cannot be
  closed.

  *The browser hides the payload exactly where you need it.* During `dragover` the DataTransfer is in
  **protected mode** — `getData()` returns `""` and only `types` is exposed. Deciding "is this ours?"
  by reading the value means never calling `preventDefault()`, and the browser then refuses the drop
  **silently, with no error**. The feature does nothing and nothing reports why. Worse, **happy-dom's
  DataTransfer does not model protected mode**, so a test written against it passes while every real
  drop is refused — the suite would have actively vouched for the broken build. The stub in
  `apps/web/src/viewer/railDrag.test.ts` models it deliberately.

  Original text: drag from the Library palette into the canvas. Justification is
  **discovery, not parity**: dragging a door onto a wall is a better first-run mental model than
  arm-then-click. It must resolve through the existing `captureDraftPoint` + `placeValid` path so
  there is one authoring pipeline with two gestures, never two pipelines. Safe to build *because* the
  snap suite already exists underneath — drag without snapping places a wall at 4.03 m and calls it
  4.00 m, which for a GlobalId-bearing element that feeds schedules is worse than not placing it.

- ✅ **R36-RAIL-SCOPE** *(SHIPPED v0.3.828–835)* — the rail shows only the current room's group, and
  `rooms.py` gained the allocation the audit was missing: Work went from **0 registers to 28**, and
  Closeout moved to Operate. The room table is the single source; `roomNames.test.ts` gates the
  duplicate in `spine.ts`.

- ✅ **R36-AUTHOR-MENU** *(SHIPPED v0.3.836–843; the item under-scoped what was needed)* — the plan
  said "split Author into four groups and promote the proven More tools". Measured live first, the
  panel held **182 buttons and 11 inputs under 7 headings**, doing about ten unrelated jobs — 154 of
  them there before the toolbox arrived. "Tools" was not a category; it was where a control went when
  nobody decided, the same failure `rooms.py` records about the retired "Engineering" section.
  So the split went further than promotion: **28 viewer tools left the floating bar entirely** (the
  bar hid 23 of 28 behind **More**, and covered the model it acts on), the rail became 14 job-scoped
  items across 4 clusters, and `panel-tools` fell from 182 controls to 9. Context now **dims rather
  than hides** — a tool that relocates itself is a defect this repo shipped twice.
  Follow-on work the split itself created, all closed in v0.3.843: persona allowlists still named the
  deleted key, panels stacked duplicates on every persona switch, a saved ribbon tab could empty a
  panel permanently, and Clash was orphaned. `railKeys.test.ts` now holds all of it — **no rail key
  may be named that no item defines, and no panel may be unreachable.**

- ✅ **R36-AUTHOR-MENU** — **SHIPPED v0.3.836–843; see the resolved entry in this ring above.** This
  was the original plan text ("split Author into four groups, promote the proven More tools") and it
  outlived the work: the shipped split went considerably further, because measuring the panel first
  found 182 buttons rather than the handful the plan assumed. Kept as a pointer rather than deleted so
  the under-scoping is visible, and marked ✅ so it can never again read as open work — it sat
  unmarked, four days after shipping, one screen below its own resolution.

- ✅ **R36-EMPTY-STATE** *(S — Lane B — **SHIPPED v0.3.849**)* — **a register with no rows is indistinguishable from a broken
  one, and was reported as exactly that.** The trigger: "something is wrong with specs". Specs was
  fine — the module rendered in full, toolbar, filters, saved views, templates, import — but the
  project held **zero** `spec_section` records, and so did every other design register. A full surface
  around an empty table reads as a failure of the surface.
  Every register needs an empty state that says which of three things is true: *nothing has been
  created yet* (with the create action), *a filter is hiding everything* (with a clear-filters
  action), or *the fetch failed*. Today all three render identically. The distinction is the whole
  value — the first is an invitation, the second is a mistake the user made, the third is an outage.
  **Extend `ui/empty.ts` rather than starting one**: it already owns this job for the adjacent case
  ("no project open", demo-aware, 17 adopters) and already ships the `.empty-state` class. A second
  empty-state vocabulary beside it is how the icon set ended up with two languages.
  *Premise-check before building*: confirm the register renderer can distinguish an empty result from
  a filtered-to-nothing one — if it cannot, that plumbing is the real item and the copy is trivial.

  **Checked, and the premise held — the plumbing was the item, in two ways.** The branch tested
  `filter.q || filter.state`, which is half the filter vocabulary: `filter.fields` (the ⧧ Filter
  panel, and the control most likely to narrow a register to nothing) was invisible to it, so a
  filtered-out register claimed nothing had ever been created *and* offered curated advice about
  where those records come from. And the third case did not exist at all — the records fetch was the
  only unguarded `await` in `openModule`, so a failure left the "Loading …" skeleton up permanently
  and the rejection escaped through the `void openModule(...)` call sites. Both fixed in v0.3.849;
  the vocabulary went into `apps/web/src/ui/empty.ts` as directed, and the states are marked in the
  DOM with `data-empty` so a check can assert *which* was decided rather than that something
  rendered. Gates: `apps/web/src/ui/empty.test.ts` (the partition) and
  `apps/web/src/portal/registerEmpty.test.ts` (the renderer reaching all three, driven rather than
  grepped — a source regex passes on a branch that is present and never taken).

---

## ✅ R41-SCHEMA-STALE — a record that predates a schema change no longer reads back quietly wrong *(2026-08-07, v0.3.875)*

Shipped in two commits: the engine + Alembic revision + backend test, then the reader's banner.

**Three things the filed entry got wrong, kept because each was reasonable and each was still wrong.**

1. **"Force the payload to null on any version difference"** would have made the bug worse. Adding a
   field is the common change and is compatible — old rows simply lack it — so nulling on any
   difference blanks every historical record for a routine addition, rendering them as *empty and
   indistinguishable from never filled in*, which is the exact failure the item existed to remove.
   Severity now derives from the payload: `stale` fires on an orphaned key, a mistyped value, or a
   declared epoch bump; a bare signature change is reported as `changed` and is not stale.
2. **"135+ registers share one table shape, so it is one column"** was right about the factory and
   wrong about the database. One `_table()` declares the column, but `create_all` only creates
   MISSING tables and never alters an existing one — so without an Alembic revision the column would
   have appeared on a fresh SQLite test database and been absent from every deployed Postgres. The
   revision discovers its tables from the live database rather than the Python registry, because a
   table left behind by a renamed module is exactly the one whose rows are most likely to be stale.
3. **Existing rows are not backfilled.** Stamping them with today's signature would assert they were
   validated against a schema that may not have existed when they were written. NULL is the honest
   answer, and the payload checks need no stamp, so historical rows still get the detection.

**Verified.** Backend: four mutations, each confirmed applied and compiled, all four killed —
dropping the create stamp, forcing `stale` False, conflating `changed` with `stale`, and removing the
bool/int guard that stops `isinstance(True, int)` letting a checkbox pass as a currency amount. A
corpus sweep creates a record through the real engine in **135 of 136 registers** and asserts none
reports stale, with the reach asserted beside the verdict so a shrunken sweep cannot pass as a clean
one. Reader: 10 vitest checks, four mutations, all killed.

**One known blind spot, asserted so it stays known.** `subject` is the universal title alias and is
left in `data`, so renaming a module whose title_field *is* `subject` leaves an orphan nothing can
distinguish from alias residue. Undecidable from the record alone.

**The composite-key grep that came with the item found nothing, and the instrument was the finding**
— preserved in the original entry below.

### The entry as filed, with its 2026-08-06 audit

- **R41-SCHEMA-STALE** *(S — Lane C; **checked 2026-08-06: genuinely unbuilt** — no `schema_version` or equivalent stamp exists on any persisted record)* — **a stored record that predates a semantics change must read
  back visibly broken, never plausibly wrong.** Stamp a schema version on every persisted record; on
  read, a record at any other version returns with its payload **forced to null and a stale flag set**,
  so the caller degrades in a way a user can see and fix. We have 135+ registers plus BCF pins, saved
  views, origin data and module records. **Audit them against one question: when a stored record
  predates a change, does it read back as broken or as quietly wrong?** Related grep while in there —
  any composite cache or dedup key built by bare string concatenation collides, since `"abc" + "d"`
  equals `"abcd" + ""`; use an explicit delimiter.

  **AUDITED 2026-08-06. The answer is QUIETLY WRONG — the data-integrity category, not the UX one.**

  **There is no schema version to check.** The `mod_*` tables carry fourteen columns — `id`,
  `project_id`, `ref`, `title`, `workflow_state`, `party_owner`, `assignee`, `created_by`,
  `created_at`, `modified_at`, `anchor`, `element_guids`, `links`, `data` — and **not one of them
  records which version of the `module.json` wrote the row**. The only "stale" handling in
  `services/api/src/aec_api/modules.py` is a `stale_write` 409, which is optimistic concurrency on
  *simultaneous edits* and says nothing about a record predating a schema change.

  **Reads are keyed by the CURRENT schema's field names** — `data.get(f["name"])` — so drift degrades
  silently and in three distinct ways, none of which raises:

  * a **renamed** field leaves the old key orphaned in `data` and the new key absent, so the value
    renders **empty and indistinguishable from "never filled in"** — the worst case, because the data
    is still there and the UI says it never existed;
  * a **removed** field's value stays in `data`, unread and invisible;
  * a **retyped** field is rendered under the new type.

  So the entry's prescription stands unchanged and its urgency is confirmed: this is silent data loss
  in appearance, not a crash. **135+ registers share this one table shape**, so the fix is one column
  and one read-path branch rather than 135 changes.

  **The composite-key grep found nothing, and the instrument is the finding.** A scan of all 1,388
  tracked `.ts`/`.py` files for two interpolations with no delimiter between them
  (`` `${a}${b}` `` / `f"{a}{b}"`) returns **18 hits, none of them an identity**: every one is display
  text where the second interpolation is a conditional suffix, or a URL where it is a query string.
  **Zero genuine collisions.**

  That negative is only worth stating because the first version of the scan was **worthless and
  confident**. Its filter was `\b(key|cache|…)\b` — word-bounded — which **cannot match `cacheKey` or
  `cache_key`**, the two most likely real names. A self-test planting a real collision in each
  language caught it: the scan returned the same count with the probes present. *Word-bounding is the
  right default for a symbol search and the wrong one for a name-fragment search* — and a filter that
  excludes its own subject produces a clean bill of health.


---

## R22-PUBLIC-VIEWER — a share token may serve model geometry ✅ *(v0.3.878, PR #270)*

The entry sat in Band 2 for weeks described as a build. It was not: the share token was already
project-scoped, revocable and audited, and four routes already honoured one. **What was missing was
a decision** — may a share token expose model geometry at all? — and the roadmap had it filed as
missing code.

Answered 2026-08-07: **yes, as a per-token opt-in, never a default.** The flag defaults false, so no
link already in someone's inbox was widened retroactively. The token serves the converted fragment
and never the source IFC; unknown, revoked, not-opted-in and no-model-published all return an
identical 404 so none of them is an enumeration oracle. The owner's token list shows which links
carry geometry, because an opt-in nobody can audit after minting cannot be reviewed or regretted.

## REACH RING — ceiling 131 to 117 in one day ✅ *(v0.3.861–v0.3.880)*

The uncalled ceiling fell from 131 to 117 across #269, #271, #272, #273 and #254, with #266 still to
land. Every step was measured by re-running the gate rather than derived from what the wiring
touched — a discipline that earned itself twice over when two PRs each reached the same method and
the arithmetic would have produced a number the gate rejects.

The sharpest find was not a count. **FIN-GOV**: the finance period lock was *enforced* — every
mutation dated into a closed month refused with a 409 — while the control to see or reopen it had no
path in the UI. An unreachable feature is one nobody can use; an unreachable control over an enforced
rule actively blocks people, and that distinction is now how reach work is prioritised.

## Archived 2026-08-10 — 22 entries closed at v0.3.875–924

Moved out of `docs/roadmap.md` in one pass. Every entry below was already marked complete IN the
roadmap and was simply never archived, so the active list read ~19% longer than the work actually
outstanding — 662 lines of it. Each left a one-line stub behind, because the lane table still names
these ids and a stub keeps that reference resolvable.

- ✅ **SEC-PLUGIN-SANDBOX — COMPLETE as of v0.3.884.** Every part of this entry has shipped,
  including the half it recorded as refused. Full record in
  [`roadmap-completed.md`](roadmap-completed.md).

  The binding half landed v0.3.864 (an attribute **allowlist** rather than a denylist — IFC entity
  attributes are CamelCase by schema and the dangerous stdlib surface is lowercase, so the names
  nobody thinks of are closed by default). The bytes contract landed v0.3.877. The two things this
  entry listed as *"Remaining: adopt it in `edit.py`, then the isolation itself"* are both in:
  `services/data/src/aec_data/edit.py` rebinds the model through `REPLACING_RECIPES`, and
  `services/data/src/aec_data/sandbox_child.py` runs the snippet in a child process with a fixed
  argv, an environment allowlist, and a fail-closed spawn.

  **The `setrlimit` refusal was resolved rather than overridden, and that is the part worth keeping.**
  This entry argued at length that `RLIMIT_CPU` and `RLIMIT_AS` *cannot be added correctly
  in-process*: they bound cumulative process CPU and process-wide memory, so they would kill a
  healthy API worker after enough ordinary traffic and take every concurrent request down with it.
  That reasoning was correct, and the answer was never to add them anyway — it was to build the child
  the limits could live in. They are set in `sandbox_child.py` now, where their scope is exactly one
  snippet. **A refusal that names its precondition is how the precondition eventually gets built**;
  a refusal that just says "no" leaves nothing to satisfy.

  v0.3.884 closed the last hazard, found by security review rather than by a gate: the snippet was
  written as "code.py" into a workdir the child puts on `sys.path[0]`, **shadowing the stdlib `code`
  module** for everything the child imports. Not exploitable — nothing in the child's import chain
  (`ifcopenshell`, `.api`, `.guid`) reaches it — but one unrelated transitive import away from
  letting a submitted snippet execute as an *import*, outside the AST allowlist entirely, where the
  allowlist would never see it. Renamed to "snippet.py".

  Residual risk, unchanged and still stated in `services/data/src/aec_data/sandbox.py`: a native call
  reached through an allowed binding is bounded by that library, not by the trace hook.

- ✅ **SHIPPED v0.3.875 (2026-08-07) — R41-SCHEMA-STALE**, both halves. Full record archived in
  [`docs/roadmap-completed.md`](roadmap-completed.md); the two points worth carrying forward are that **the prescription in the entry was wrong and the scope
  claim was right for the wrong reason**. "Force the payload to null on any version difference"
  would have blanked every historical record the first time anyone *added* a field — i.e. rendered
  them as empty and indistinguishable from never-filled-in, which is the exact failure the item
  exists to remove. Severity now derives from the payload (orphaned / mistyped keys), not from the
  version alone. And "135+ registers share one table shape" was true of the *factory*, not of the
  deployed database: one `_table()` declares the column, but `create_all` never alters an existing
  table, so it still needed an Alembic revision or it would have passed on SQLite and failed on
  every deployed Postgres.

- ✅ **SHIPPED v0.3.876 (2026-08-07)** — R39-THROTTLE-SHARED ①. `throttle.py`'s per-endpoint caps
  now count through `ratecount`, shared across workers when `AEC_REDIS_URL` is set. The counter is
  `main.py`'s existing implementation extracted rather than a second one written beside it, which
  also fixed a real defect by construction: the old bound was a wholesale `clear()` at 10k keys, so
  a scanner cycling through callers could wipe the limiter's state for every caller it was
  legitimately throttling. **The lesson is the guard, not the counter** — a boot guard naming
  `AEC_RATE_LIMIT_RPM` read as covering rate limiting in general, and was silent about the
  always-on limiter capping `POST /auth/stepup` at 10/min. A generic-sounding gate hid a missing one.

- ✅ **LOD 2025 — COMPLETE as of v0.3.903.** All three items (LOD-ASPECTS, LOD-500-LOA,
  LOD-ELEMENT-TABLE) shipped. Full record in [`roadmap-completed.md`](roadmap-completed.md).

  **Two things worth keeping here.** First, the defect was one shape in three places: a number
  computed from whatever data happened to be available, then labelled as the thing somebody wanted
  to know. A well-tagged bounding box scored LOD 350; a verification recorded that it happened and
  never how accurate it was; a target matrix could be authored and never compared. Second, the fix
  in all three cases was the same move — **say what was actually measured, and report the part you
  could not measure as unmeasured.**

  **The licence constraint stands for anything that touches this again.** BIMForum Part I is
  CC BY-NC-ND and Part II is CC BY-NC; NonCommercial is a hard exclusion for this repo. No element
  table, keynotes, per-element definitions, Uniclass→Omniclass crosswalk or band→aspect-value table
  may enter the codebase. The ISO 7817-1 aspect names and the AIA band numbers are not BIMForum's to
  license and are what the implementation uses.

  **Still open, and named honestly:** a model read tops out at **LOD 350** — nothing in the served
  index distinguishes a coordination-ready solid from a fabrication-ready one, and nothing in it can
  see whether a placement is *accurate* rather than merely present. Both are reported as unread
  (`ceiling_distribution`) rather than assumed. Closing either needs geometry the index does not
  carry today, which is a deliberate scope call rather than an oversight.

- ✅ **R22-PUBLIC-VIEWER — SHIPPED v0.3.878 (#270).** The decision this entry was waiting on was
  taken 2026-08-07: **a share token may serve model geometry, as a per-token opt-in, never a
  default** — following the `show_payments` precedent exactly. `ShareToken.show_model` defaults
  false, so no link already sent was widened retroactively.

  The scope line that mattered: the token serves the converted **fragment**, never the source IFC.
  "Share the model" reads as either, and the wide reading discloses every property set,
  classification and GlobalId in the project — a much larger disclosure than was approved. There is
  a test that fails if the source IFC ever becomes reachable through a token.

  All four refusals — unknown token, revoked token, token without the opt-in, project with no
  published fragment — return an identical 404 body. Distinguishing them would tell an attacker
  whether a token exists, whether it was revoked, and whether a project has a model.

- ✅ **CLOSED FOR FREE — do the seven rooms all have a non-empty demo?** They do. Every module in
  every room has at least one seeded record: cost 18/18 (65 records), deal 9/9 (17), design 32/32
  (70), operate 15/15 (51), planning 26/26 (50), schedule 7/7 (24), and **work 28/28 (48)** — the one
  the check singled out. No build needed.

  *The measurement was wrong twice before it was right, which is the part worth keeping.* The first
  pass matched `/modules/{key}/records` and reported **zero records in all seven rooms** — a
  spectacular finding that was purely a wrong key shape; the list endpoint is `/modules/{key}`. A
  gap-check that reports total absence should be suspected of measuring the wrong thing before it is
  believed.

- ✅ **R22-ROUTINES** *(S — `routines.py` + migration shipped; the SWEEP shipped 2026-08-07)* — **scheduled agent runs** (monthly progress report, weekly schedule-risk
  scan) rather than on-demand only. Turns AI from a tool you remember to use into infrastructure.

  **The deciding half existed and nothing acted on it.** `routines.due()` already refuses well — an
  unknown cadence is refused rather than treated as due, `draft`/`retired` are never fired, missed
  windows fire ONCE for the current window (`catch_up_suppressed`) — and `jobs.enqueue` already
  rejects an unregistered kind, and `worker.py` already runs the queue. But both `/routines/due`
  endpoints are read-only, so "what should run now" was computed, returned and dropped: exactly the
  entry's own complaint.
  `services/api/src/aec_api/routines_run.py` + `POST /projects/{pid}/routines/run-due` closes it.
  **The defect that made this more than plumbing was latent**: `routines.from_project(db, pid, now,
  in_flight)` takes `in_flight` as a parameter and **no caller supplied one**, so the single refusal in
  the chain that needs outside knowledge — "the previous run has not finished" — could never fire. With
  the default empty set, a monthly report taking an hour is re-enqueued on every sweep for that hour.
  The sweep derives it from the jobs table instead.
  Three refusals, all mutation-checked: in-flight derived rather than assumed (3 named FAILs); a
  routine naming an unregistered kind is `refused` and **does not abort the sweep** for the ones beside
  it (2); and **the window is consumed at enqueue, not at success**, with the `job_id` recorded —
  consuming it on success would re-fire a failing routine every sweep until it passed, a retry storm
  dressed as a schedule.
  *Two shape assumptions were caught by reading rather than trusting a name*: `update_record` takes
  `actor` and `party` as **required positionals** (omitting them is a TypeError only the write path
  surfaces), and `me.TABLES[key]` is a Core `Table`, so columns are `t.c.*`. The register also had to
  be loaded explicitly outside the app lifespan — the same trap as a `TestClient` built outside a
  `with` block, where every module reads as absent and the failure looks like a missing feature.

- ✅ **R22-PUBLIC-VIEWER — SHIPPED v0.3.878 (#270)**, per-token opt-in; see the Band 2 record. *(was sized **M**, not S; see the Band 2 entry, which is the live one — its premise was corrected 2026-08-06: the scoped, revocable token and the routes honouring it ALREADY EXIST.)* This
  line is the original scan's one-sentence estimate. It called the item S because it counted the
  viewer, which exists; the Band 2 entry counted the **scoped revocable token and a route that
  honours it**, which do not. Two sizes for one ID is a prioritisation bug, not a rounding
  difference — S and M land in different sprints.

**Deliberately NOT taken:** crew/equipment dispatch, payroll, inventory, and a general ledger. Those
are mature, crowded, low-margin categories with a decade of incumbency. **Prefer seams to
reimplementation** — R22-ACCT-SEAM exists precisely so we never write a GL.

- ✅ **DONE for the parameters that exist** — R38-LIVE-PARAMS. Slices 1–3 shipped v0.3.823–825:
  the depth field, the slider with a live base-anchored ghost, and W/L dimension chips over
  `set_profile_dims`. Slice 3 was deferred in the morning (chips over one variable are theater),
  the prerequisite was named, Core shipped the recipes, and the chips landed the same afternoon —
  the pattern worth repeating for everything below. Three items were carved out of it by
  premise-check on 2026-08-02, each blocked on a **named server-side prerequisite**:

- ✅ **R41-FDD-INGEST** *(M — Lane C/H; `fault_finding` register shipped 2026-08-07)* — **consume fault findings; do not build a historian.** The operate
  phase has a real hole: FCA/FCI, work orders, PM schedules, asset registers and warranties all exist,
  but **nothing consumes time-series building-automation telemetry**, so condition is surveyed by a
  person rather than measured continuously. The tempting answer — build fault detection ourselves —
  needs a historian, point-role mapping and an ingest path, which is a *different product*: the
  reference implementation is six years old and 250 MB of repository. **The cheap path is a
  `fault_finding` register keyed to IFC GlobalId, populated from an external system's MCP or REST
  surface**, feeding the FCI and work-order modules we already have. Public ASHRAE Guideline 36 fault
  identifiers are a stable vocabulary to key against.

  **Premise held — genuinely unbuilt**, unlike most of this ring: `asset_register`, `fca_element`,
  `work_order` and `warranty` all existed and nothing consumed telemetry findings.
  `fault_finding` (FDD, 16 fields, four contiguous fieldsets: Fault / Provenance / Asset /
  Consequence) takes the cheap path the entry prescribes and **does not** build a historian.
  The design point is that we CONSUME rather than detect, so provenance is a fieldset rather than a
  footnote: `source_system` + `external_id` + `first_seen`/`last_seen`/`occurrences`. A finding with
  no source is not ours to assert, and a telemetry fault is an interval that recurs, not an instant —
  which is why `cleared → reported` ("recurred") is a real transition: **a fault that stops reporting
  is not necessarily fixed, and one that returns is not new.** `dismissed` is separate from `cleared`
  for the same reason.
  G36 identifiers FC1–FC15 are the `g36_id` vocabulary, plus an explicit "Other (not a G36 fault)" so
  an unmapped fault is recorded as unmapped instead of forced into the nearest code.
  **No defaults at all** — `test_field_attrs.py` caps them and requires each to be a fact about the
  record rather than a policy, and on a register fed by someone else's system every default would be
  an assertion about *their* data.
  Verified over HTTP with startup actually running: `GET /modules` → **137** (was 136), key-shape
  identical to `pm_contract`, room derived as `operate`, `POST` → 201 `FDD-001`.
  *The registry validator earned its keep*: the first draft wrote reference fields as `ref:` when the
  schema wants `module:`, and it named all four rather than failing silently.

  **CHECKED 2026-08-06 — the premise HOLDS, which is worth recording because most have not.** The
  modules the entry says exist do: `fca_element` + `services/api/src/aec_api/fca.py`, `work_order`,
  `pm_schedule`, `asset_register`, `warranty`. There is **no `fault_finding` register**, and **no
  ASHRAE Guideline 36 vocabulary anywhere** — every ASHRAE reference in the tree is design-side
  (Level 1 audit, heat-balance load, low-velocity duct, rule-of-thumb), none is FDD.

  **The one thing that looked like a counter-example is not one.** `meter` and `meter_reading`
  registers exist, so "nothing consumes time-series" reads wrong at first glance. `meter_reading`'s
  fields are `subject`, `meter`, `reading_date`, `consumption`, `cost` — **a utility bill, not
  building-automation telemetry**. Periodic manual consumption is a different shape from continuous
  point data, and nothing bridges them. The gap and the proposed cheap path both stand as written.

- ✅ **R41-IDS-VALIDATE** *(M — Lane D; DISSOLVED on premise-check 2026-08-06 — already built end to end)* — **buildingSMART IDS: author an Information Delivery
  Specification, run it against a model, read the report.** Conspicuously absent for a product whose
  thesis is IFC-native, and a likely second gap in the "openBIM gaps complete except the IFC5/IFCX
  write-path" claim. **Verify that claim against the tree before sizing this.**

  **Verified, and the entry is the thing that was wrong — the openBIM claim was right.** All three
  verbs exist and the loop is closed, including into the UI:
  *author* — `services/api/src/aec_api/ids_authoring.py` ships a starter template library keyed by
  element group (Pset_*Common properties per IFC class), builds a standards-valid buildingSMART **IDS
  1.0** file through `ifctester`, and generates an EIR contract document;
  *run* — `services/data/src/aec_data/validate.py` validates an IFC against an IDS with `ifctester`,
  taking an uploaded `.ids` or falling back to a default QA spec set;
  *read the report* — `POST /projects/{pid}/validate`, with `PUT`/`GET`/`DELETE /projects/{pid}/ids`
  storing the project's spec, and **all of it already called from `apps/web/src/api/client.ts`** —
  which makes it the rare feature that is not merely built but reachable.
  So "conspicuously absent" described a feature that was complete, wired and shipping. **The entry's
  own instruction is what caught it**, and that is the argument for writing entries that say what to
  verify: a sentence naming the check costs one grep and saved an M-sized build here.

  ✅ **VERIFIED 2026-08-06 — the premise is wrong and the claim HOLDS. This is already built,
  end-to-end and reachable.** All three parts the entry asks for exist:

  * **author** — `services/api/src/aec_api/ids_authoring.py` builds a standards-valid IDS 1.0 via
    `ifctester` from a starter template library, plus an EIR document. Routes `/ids/templates`,
    `/ids/build`, `/ids/eir` in `services/api/src/aec_api/routers/ids.py`; client methods
    `idsTemplates` / `idsBuildBlob` / `idsDownload`; UI in `apps/web/src/portal/panels/standards.ts`.
  * **pin to a project** — `/projects/{pid}/ids` with pin / unpin / status, so validation runs with no
    re-upload.
  * **run it and read the report** — `POST /projects/{pid}/validate`
    (`services/api/src/aec_api/routers/analysis.py`) over `services/data/src/aec_data/validate.py`,
    with precedence *uploaded > pinned > built-in defaults*. `format=json` returns the per-spec
    pass/fail summary and **`format=bcf` returns a .bcfzip punch list of the non-conformances**, one
    topic per failing specification — so an IDS audit round-trips into other coordination tools.

  That last part is **more** than the entry asks for. `ids_authoring.py`'s own docstring says it
  plainly: *"We already validate models against an IDS; this is the upstream half."* Closing as
  already built. **The "openBIM gaps complete except the IFC5/IFCX write-path" claim survives this
  test** — IDS was the suspected second gap and it is not one.

- ✅ **R41-DELETE-RATCHET** *(S — Lane J; FILE half + SYMBOL half both SHIPPED 2026-08-06)* —
  **assert in CI that removed things stay removed.** Shipped as
  `apps/web/src/tooling/deleteRatchet.test.ts` over eight deleted documents, and
  `services/api/test_delete_ratchet.py` over the API method surface.

  **The entry says "a negative assertion is three lines". It is — and the population is the whole
  problem.** Three plausible candidates were tested and all three failed, in three different ways:

  * `?shell=classic` was deleted, but `"classic"` still lives in `apps/web/src/dev/liveAudit.test.ts`
    as a run label — the string has a legitimate other life.
  * the More menu is gone, but `"more"` appears in `apps/web/src/viewer/app.ts` and
    `apps/web/src/viewer/railToolbox.ts` **in prose describing the removal** — the gate would fire on
    the documentation of its own rule.
  * the register renderer's internals — `renderRegister` and `registerBoard` were *guessed*, and
    `git log -S` says **neither ever existed at any commit**. That assertion would have passed
    forever, guarded nothing, and read as coverage. **It is the exact defect this ring is about, and
    the only thing that caught it was checking history for a name somebody had invented.**

  **So the first pass ratchets FILE PATHS, not symbols.** Every failure above is a string-matching
  problem; a path has none of them — prior existence is provable from history, current absence is one
  `git ls-files`, and it needs no comment-stripping, no word boundaries, and no matcher that can agree
  with everything.

  **The symbol half then became tractable — by not searching for a name.** Every failure above is a
  *string-matching* problem, so `services/api/test_delete_ratchet.py` does no string matching: it
  parses **definition sites** (`^  name(` at class indent, across `apps/web/src/api/*.ts`) and asserts
  a derived property over whatever it finds — **no API method is defined in two files**. That inverts
  all three traps at once. There is no list to guess wrong (`renderRegister` could not have been
  invented here, because nothing is named in advance); prose cannot match a definition site, so the
  gate cannot fire on the documentation of its own rule; and a word with a legitimate other life is
  irrelevant, because a second *definition* is the defect whatever else the word means elsewhere.
  **The failure it catches is invisible to the size ratchet.** Re-adding one method to `client.ts`
  while the mixin still defines it costs a few lines, clears the 3,780 pin comfortably, and produces a
  **shadow** — two definitions, the winner decided by composition order in
  `withAuth(withProforma(withDesignOptions(...)))`. Every call site resolves, nothing fails to compile,
  and the extraction is silently undone. 638 methods across 10 files, zero duplicates, **no exemption
  list**. Mutation-checked by re-adding `designOptionsRecord` to `client.ts`: 3 named FAILs naming the
  symbol and both owning files.
  *Scope worth stating so neither half is over-read:* no `.py`/`.ts`/`.tsx` file has ever been deleted
  on `main` (`git log --diff-filter=D`, 400 commits, **zero**) — which is exactly why the path ratchet
  lives over `docs/` and the source-side one is about definitions rather than deletions. In source,
  things here get *extracted*, not removed.

  **The eight are load-bearing because `docs/` IS the Pages web root.** Re-adding any one republishes
  a superseded planning document as a live public page. Two of them are competitive analyses, which a
  standing user directive keeps out of the public docs — and `services/api/test_no_comparative_names.py`
  enforces that **by content** while saying nothing about those *files*. **Neither check implies the
  other**, which is a better argument for both than either makes alone.

  **Enrollment stops the ninth entry being invented:** an entry must be absent now **and** present in
  some earlier commit, so something that merely "does not exist yet" cannot be enrolled and the gate
  cannot grow into a ban on future work. Enroll at deletion time; never archaeologise history, because
  inference cannot separate *removed on principle* from *removed incidentally*.

  **A stated blind spot, and it was proven rather than assumed.** `actions/checkout@v7` clones at
  `fetch-depth: 1` and `.github/workflows/ci.yml` does not override it. A `git clone --depth 1` of this
  repo reports `is_shallow=true`, **1 commit**, and the enrollment lookup finds **0** — so that half
  would have failed all eight entries in CI for a reason unrelated to the code. The two halves are
  therefore split by what they *need*: absence runs everywhere and is the ratchet; enrollment runs only
  where history exists and **says so when it cannot**, rather than passing quietly. Deepening the CI
  clone was rejected — a 2,000-commit fetch on every run to re-verify a property fixed at authoring
  time.

  Mutation-checked four ways: re-add a path → red; re-add it *relocated* → red on the basename check;
  enroll a never-existent path → red; empty the list → red on the vacuity guard.

  **Lineage:** `apps/web/src/portal/register/registerOwnership.test.ts` got there first and solved the
  hard half — the population is the moved code *named*, the matcher is asserted to find real names,
  comments are stripped, and the legitimate crossings are enumerated as doors. The symbol ratchet is
  the harder second version and should extract that helper rather than re-derive it.

- ✅ **R41-TEST-RESIDUE** *(S — Lane J; found 2026-08-06 by tracing a flaky suite to its cause,
  **and my own filed premise was wrong** — corrected below)* —
  **the backend suite leaves its databases behind, and the sweep that should have caught it was
  removing a filename nothing creates.**

  *Filed as "nothing sweeps them". That is false and the truth is more interesting.* `run_tests.py`
  sets `DATABASE_URL=sqlite:///./_{t}.db` per test and unlinks exactly that. But **351 of 538 test
  files overwrite `DATABASE_URL` at import** with a name of their own (`test_absorption.db`,
  `auth_test.db`). So the runner unlinked a file nothing ever creates while the real one persisted —
  **a cleanup that ran, succeeded, and removed nothing**, which is indistinguishable from one that
  works. The 187 tests that *do* use the runner's name were cleaned correctly the whole time, which
  is exactly why nobody noticed.

  **Fixed with two refinements from a second session, both better than the first design.** The sweep
  runs **per test as each finishes** rather than after the pool — with the disk at ~96% an end-sweep
  still peaked at ~1.4 GB held open at once. And **a failing test keeps its database**, because that
  file is the evidence for the failure and sweeping it destroys what someone needs at 3am.

  Per-test cleanup is **name-scoped from the test's own source**, not a snapshot diff: tests run
  concurrently, so "everything that appeared while I ran" also contains databases other tests are
  still using. The end-of-run backstop *does* use snapshot-diff, where no name is available — a
  `glob("test_*.db")` there would have its safety depend on which filenames happen to exist, and
  `preview.db` (the dev API's live database) shares that directory. A full `run_tests.py`
  writes a SQLite file per test module into `services/api/`, and no run removes what the last one
  wrote. Measured across the shared clone that day:

  | worktree | leftover `*.db` | size |
  |---|---|---|
  | "lane-f-proforma" | **324** | 1,423 MB |
  | "integrate" | **322** | 1,413 MB |
  | main clone | **332** | 1,441 MB |

  **~1.4 GB per worktree per full backend run**, and every one of those files was hours stale. With
  free space at ~3%, that is the whole problem: two sessions independently hit
  `sqlite3.OperationalError: disk I/O error` and vitest timeouts (`library.test.ts` 5,026 ms,
  `pdfVendor.test.ts` 20,016 ms) that **passed on a clean re-run**. The residue does not announce
  itself — it manufactures failures that look exactly like flaky tests, in files that have nothing
  to do with it, which is why it survived long enough to reach 2.8 GB.

  **The fix is two things and the second is the one that lasts.** The suite removes its own
  databases; *and* a **leftover count is asserted**, because a sweep that silently stops working
  looks identical to a clean tree — the same reason every gate here is mutation-checked rather than
  trusted.

  **Assert the COUNT, not free space.** Disk was measured swinging **~10 GB while a suite runs**, so
  a free-space threshold would flap with concurrency and teach people to ignore it. A leftover count
  is deterministic and attributable.

  *Filed by the session that found it rather than fixed on the spot: the files belonged to other
  sessions' worktrees, and the `git worktree remove --force` incident is precisely why a measurement
  gets reported and someone who owns the tree does the deleting.*

- ✅ **R41-REACH-WRITES — COMPLETE as of v0.3.895.** All four write endpoints are wired, each with
  the confirmation or refusal its own failure mode called for. Full record in
  [`roadmap-completed.md`](roadmap-completed.md).

  **The one thing worth repeating here, because it is the argument for the item having existed:** two
  of the four were sitting on server defects that a same-shape-as-a-read wiring would have shipped
  straight to users. `deleteView` answered `{"deleted": true}` for a row it had not touched *and*
  deleted views across project boundaries; `modelVersions` had been discarding half the review record
  the API already sent. Both were found by reading the endpoint before writing the caller, which is
  the only reason the four-releases-instead-of-one cost bought anything.

  The general rule stands and generalises past this entry: **a reach sweep may wire anything that
  cannot lose work, and must stop at anything that can.**

- ✅ **R39-THROTTLE-SHARED ①** *(M, Lane C — **SHIPPED v0.3.876**; checked 2026-08-06: accurate and genuinely open**;
  recorded so the next reader does not re-verify)* — `throttle.py` keeps `_HITS` as a plain
  in-process `dict`, so the per-worker multiplication the entry describes is real and unchanged.

- ✅ **R42-COMMIT-DELTA — COMPLETE, v0.3.911.** *Promote the preview fragment instead of discarding
it.* `apps/web/src/viewer/deltaCommit.ts` + `apps/web/src/viewer/deltaCommit.test.ts`.

  On a successful recipe the element has already been authored and converted, so the commit now keeps
  that fragment as an authoritative delta, clears the amber marker, reindexes **without** reconverting
  and does **not** reload. The full rebuild is an explicit `⟳ Rebuild (N)` in the rail. No loader work
  was needed: it has held base + N models keyed by id since it shipped. The path with **no** preview
  fragment still does the full publish — there is no geometry to keep there, and going delta would
  show the user a model missing the thing they just drew.

  *Both hazards were real and both are handled — the second one was the interesting half:*
  1. deltas are dropped **only after** the new base has loaded, and only when the rebuild actually
     succeeded. A failed consolidate keeps them, which is the one state where they are the only
     correct geometry on screen. Asserted both ways.
  2. the served **property index is rebuilt whole** (`properties_index.build_index`), so a delta's
     element is in the scene before it is in the index. It is neither appended per-element nor
     hand-waved: the reindex is **bracketed and counted**, and while it is in flight the rail says
     *"Model data is still updating — searches and quantities may not see the newest edits yet"*
     instead of *"The data is current"*. `publish` resolves on ACCEPT, not on completion, so the
     bracket closes on the poll to a terminal state — closing it early was one of the mutations
     checked. `settled()` is there for a caller that needs the index current before reading it.

  *A third case the entry did not anticipate, found by writing the tests:* a **successful full
  publish also rebuilds the pending deltas**, because they are in the IFC and the convert reads the
  IFC. Without clearing the store there, the rail would strand on "N edits not yet rebuilt" forever
  while `loadProjectModel`'s `disposeAll` had already reclaimed the very geometry those records named.

  *VERIFIED END-TO-END, v0.3.912.* The unit tests exercise the decision; the wire was measured
  separately against a running API and a real project, recording every request. Both paths, back to
  back, same recipe: the delta path sent `"publish":false` then `POST /publish` with the bare body
  `false`, made **0** model reloads and was user-visible in **45 ms**; the full-publish path took
  **1,025 ms** and one reload. `/elements` went 4 → 5 → 7, so the elements really landed.
  `store.reindexing` was true immediately after commit and false after `settled()`.

  *A DEFECT THIS ENTRY DID NOT ANTICIPATE, found by that verification and fixed in v0.3.912.* The
  preview and the commit were **two different elements**. `edit_preview` authors into a throwaway
  one-storey model, so both runs minted their own GlobalId — measured live: preview
  `33a6Uiew11Mv_Pc4qvizwA`, committed `0POIcNSNv2lh4Acrld7xm4`, and the preview id was in no index.
  Harmless while the fragment was discarded on commit; **keeping it made the mismatch permanent**, so
  the wall the user had just drawn was missing from selection, properties, LOD, QTO and pins until
  Rebuild. Hazard 2 above predicted an index *timing* problem and there is one — but no amount of
  reindexing fixes an identity that was wrong from the start. `apply_recipe(..., want_guid=)` now lets
  the commit adopt the preview's id. `services/api/test_adopt_guid.py`.

  *THE PRINT SLICE IS SMALLER THAN THIS ENTRY ASSUMES — shipped v0.3.915 (ADR-001 items 1–5).* The
  entry says *"3D only captures a hero image, so the two are not yet peers — slice the print path
  first."* That premise went stale: **CANVAS-PEER already shipped the axonometric as a real drawing**
  (true isometric basis, per-element silhouettes keeping their GlobalIds, depth-sorted). What was
  missing was reach, and it was worse than missing — the `axon` branch sat in `sheet_layout`'s
  *wrapper*, so the shipping path fell through to plan and a sheet asked for an axonometric returned
  **a plan cut at 1.20 m wearing the caller's title**. The branch now lives in the shared
  `_view_for_spec`, an unknown kind raises instead of substituting, and
  `services/api/test_view_kind_dispatch.py` asserts BOTH dispatchers agree kind-by-kind. Full
  reasoning: [`docs/internal/adr-001-sheet-composition.md`](internal/adr-001-sheet-composition.md);
  the slice plan is in [`docs/internal/r36-viewer-subapp-design.md`](internal/r36-viewer-subapp-design.md).

  *SLICE 3 SHIPPED v0.3.916 — and it found a third silent-drop.* The rail's three sheet buttons built
  their own query strings and sent `number`, `title` and `scale`; `sheet.*` accepts `sheet`, `page`,
  `purpose`, `rev`, `storey`, `views`. FastAPI drops unknown query parameters, so all three vanished
  — measured live: `?number=A-999` returned a sheet numbered **A-101**. Invisible because the rail's
  `number=A-101` equalled the route's default, so the per-level title it computed never reached the
  paper. There is no `title` field in the titleblock at all, so the description now goes in `purpose`,
  which is real. `apps/web/src/viewer/sheetSpecs.ts` can emit nothing outside `SHEET_PARAMS`, and its
  test asserts that set against **the route's own signature** rather than a remembered list. The new
  `🖼 Place this view on a sheet` control sends the active level's plan in 2D and a true isometric in
  3D — not a camera match, because a perspective camera and a parallel projection are not the same
  view. `apps/web/src/viewer/sheetSpecs.test.ts`.

  *Cost paid in the right place.* `app.ts` is on a per-file ratchet with zero headroom, so the feature
  could not simply be added to it. The commit DECISION moved into the module — where it is now
  testable without a loader, a fragment server or a running convert — and `waitForPublish` (nine
  lines, **24 call sites**, no test in its life) came out into `apps/web/src/viewer/publishWait.ts`
  with `apps/web/src/viewer/publishWait.test.ts`. `app.ts` ends where it started, at its pin.

- ✅ **R42-SESSION-MODEL — COMPLETE as scoped, v0.3.907.** *"Stop re-reading the IFC per edit"* is done; the remaining WRITE concern is tracked separately as **R42-SESSION-WRITE**.

  *What shipped, and why it was smaller than this entry assumed.* `open_model` was **already** cached
  by `(path, mtime, size)`. It was never missing — it was unreachable from the authoring loop,
  because every edit writes a new timestamped file so the next edit's key differs and misses by
  construction. Its own docstring said so, phrased as a reassurance about staleness. `apply_recipe`
  now hands its post-write model to the cache, so an edit's OUTPUT opens without a parse.
  `services/api/test_model_cache_seed.py` proves it by counting `ifcopenshell.open` calls.

  **What remains is the WRITE, and it needs a product decision rather than more code.** Each edit
  still serialises a whole new IFC. Deferring that means the file on disk is no longer the current
  model — which changes what *"the current source"* means to every other reader (publish, export,
  clash, the MCP tools, a second user's optimistic-lock check) and what *"saved"* means to a user.
  That is a decision about the product's contract with its own data, not a caching change, and it
  should not be made inside a commit that looks like an optimisation.

- ✅ **UX-VIEWED — COMPLETE, v0.3.922.** ShareToken view-timestamps now render as chips.
  `apps/web/src/ui/chips.ts::shareState` + the call in `masterBuilder.ts`.
  **Shipped as scoped — one call, plus the honest edge the entry did not anticipate.** The 2026-08-06
  check was right in every particular: `statusChip` already took a `ts` option *for this*,
  `last_viewed_at` was already typed at `client.ts`, and `masterBuilder.ts` never imported the chip
  module at all. Nothing needed building.

  **Paid is deliberately NOT produced, and that is a finding rather than a shortfall.** The vocabulary
  names three states; the share-token row carries no payment state. `show_payments` is a *capability*
  flag — whether the shared page displays payments — not a record that one happened. Deriving "Paid"
  from it would put a chip on screen asserting something nobody measured, so `shareState` returns two
  states and a test asserts it never returns the third. When a real paid signal reaches this row,
  whoever adds it must delete that test on purpose rather than discover the gap in review.


  Every layer this needs already exists. `services/api/src/aec_api/models.py` stores `view_count` and
  `last_viewed_at` on `ShareToken`; `services/api/src/aec_api/client_portal.py` **increments both on
  every view** and serves them from `_public_row`; `apps/web/src/api/client.ts` types them; and
  `apps/web/src/ui/chips.ts` is the chip vocabulary itself — its opening line names *"Sent → Viewed →
  Paid"* as the exact phrasing it exists to standardise, with 7 tests.

  **What is missing is one call.** `apps/web/src/portal/panels/masterBuilder.ts` renders the share
  row as a link plus a revoke button and inlines the count as plain text — `(3 views)`. It never
  calls `statusChip`, and it **never uses `last_viewed_at` at all**, so the timestamp is gathered on
  every view, stored, serialised, sent over the wire, typed in the client, and then dropped on the
  floor.

  So this is not "build a view-tracking pipeline" (S); it is *use the chip vocabulary that exists on
  the data that is already on the wire*. The remaining work is in one file. **Nothing needed
  building; something needed calling** — the same reach-not-capability shape as the `snapEngine`
  resolver with zero callers.

- ✅ **R36-DRAWINGS-RETURN — COMPLETE, v0.3.913.** `apps/web/src/shell/wsReturn.ts` +
  `apps/web/src/shell/wsReturn.test.ts`.

  **Three of this entry's four claims were already false when it was read.** Measured in the running
  app before writing anything — Drawings: room tabs 622×37 visible, Design tab present, "← Back to
  Model" present at 111×23. Specs: room tabs 510×37 visible, Design tab present, **no return
  control.** So the defect was an ASYMMETRY, not an absence, and only Specs had it.

  *Why Specs was missed, which is the part worth keeping.* The trigger was `DEAD_END_WS`, a set of
  **workspaces** — and Specs is not a workspace. `openSpecs()` calls `setWorkspace("design")` and
  opens a module inside it. Design is a perfectly ordinary workspace with tabs, so no list of
  dead-end *names* could ever have caught it, yet a user who pressed Specs on the model rail was
  still stranded: of the seven visible controls there mentioning model/3D, one was the Design tab
  they were already on, two were analysis modules, and four were project-home cards — start-over
  actions, not a way back. The rule is now about the **journey** (*a control that carries you out of
  your workspace owes you a return*) rather than the destination.

  *The suite could not have found this.* `wsReturn.test.ts` existed with **no `wsReturn.ts` beside
  it** — it reproduced `main.ts`'s logic including its own `DEAD_END_WS = new Set(["drawings"])`, so
  it asserted a COPY. Its own header said *"and Specs behaves the same"* while its copy excluded
  Specs. The decisions now live in the module and the test imports them.

  *Two defects the live check caught that the unit tests structurally could not:* a "jump" that did
  not change workspace offered a return using a stale origin; and the bar was rendered but **never
  removed**, so one press of Specs left "← Back to Model" in the Design workspace permanently. Every
  unit test mounts a fresh DOM, so nothing could persist across visits to be seen.

  ⚠ **v0.3.913 marked this COMPLETE while it was wired at 2 of ~10 crossings — corrected in
  v0.3.914.** A code review found that the rule was passed only at the two rail launches, so the
  other eight cross-workspace controls (the portal's "Open underwriting" → finance, a margin panel →
  model, six more) still stranded the user exactly as Specs did. The fix is not a longer list of call
  sites: **the `aec:goto-workspace` / `aec:workspace` EVENTS are the journey** — nothing dispatches
  them except a control in another workspace — so the rule now lives at the two listeners, where the
  next person adding a deep-link cannot forget it. The behavioural tests could not see this (they
  assert the rule, not its wiring), so `wsReturn.test.ts` gained a source gate that fails when a
  listener drops `"jump"` — mutation-checked.


## Archived 2026-08-13 — three R43 items closed in the tree but still listed as open

Moved out of [`roadmap.md`](roadmap.md) during a documentation audit. Each was already marked ✅ there
with its full record; the roadmap's own header says it carries **open items only**, so keeping them
inline made the open list longer than the open work. Two of the three are corrections rather than
builds — worth preserving for that reason, not despite it.

- ✅ **R43-CSRF-GET — AUDITED 2026-08-10, and the answer is "none, and now nothing can add one."**
  Our session cookie is `samesite="lax"` (`routers/auth.py`, `routers/saml.py`) and there is no CSRF
  middleware, so Lax is the entire defence — and Lax withholds the cookie on a cross-site POST but
  **sends it on a top-level GET**. The route table was therefore the whole protection, and nothing
  was watching the route table. An AST scan over all 456 service files found **six** GET handlers
  that touch the DB session and **zero that change state**: three verification routes and the SCIM
  user list are `select(...)` reads; the CAM statement PDF commits only its own `audit.record`, and
  dropping that would lose the audit trail, which is the worse trade; the OAuth callback does create
  a user but MUST be a GET because the provider chooses the method, and its authority is the
  provider's one-time code, not our cookie. **The finding was never "there is a bug" — it was
  "nothing would stop one",** so the deliverable is `services/api/test_mutating_get.py`, a ratchet on
  the exact (module, path, ops) set with a written reason per entry and a twin that refuses a reason
  short enough to be a rubber stamp. Mutation-checked three ways: a mutating GET added to a router,
  a broken scan (which must fail, not report clean), and a gutted reason.


- ✅ **R43-ORG-OWNERSHIP — the premise was wrong and the audit found a REAL hole anyway. Fixed
  v0.3.926.** This entry said "registration granting org ownership", which I imported from a generic
  threat list: **there is no Org or Tenant model in this codebase at all.** The tenancy primitive is
  `ProjectMember` plus a global `role` hint. Reading the six `User(...)` construction sites instead
  of the threat list is what turned up the actual defect — and **five of the six were already
  correct**, which is precisely why the sixth had gone unnoticed.

  `POST /auth/register` takes no token when the user table is empty, because there is no admin yet
  to authorise one. That part is fine. What was not fine is that it also set `role="admin"` — and
  `role` is not a hint, because `routers/auth.py`'s `_is_platform_admin` ends with
  `return u.role == "admin"`. **On a fresh public deployment the first stranger to reach
  /auth/register became platform admin, unauthenticated, even with `AEC_ADMIN_EMAILS` already naming
  someone else.** Restoring the defect under test returns `GET /auth/users` → **200**, so this was
  live and reachable rather than theoretical.

  Fix: when `AEC_ADMIN_EMAILS` is set the operator has already declared who the admins are, so
  bootstrap grants `"user"`; unset (desktop, local, single-operator) still grants `"admin"` and
  nothing changes. `services/api/test_bootstrap_admin.py` asserts **both halves** plus the gate —
  testing only the refusal would pass on a change that silently broke every local install, and the
  over-correction mutation proves the twin catches exactly that.


- ✅ **R43-PLAN-EMPTY-AT-CUT — SHIPPED v0.3.929.** A plan could compose fully — titleblock, scale
  bar, grid — while the cut plane found **no geometry**, and nothing in the output said so. Measured
  on `samples/school_str.ifc`: the top storey at 11.400 yields **zero** cut loops at the default
  `elevation + 1.2 m`, because the parapet is shorter than the cut height.

  **Why it was invisible:** an early "no geometry" return existed, but it fires only when polys AND
  below AND grid are *all* empty — and `grid_from_meshes` derives from the whole model rather than
  from the cut, so any storey with a grid skipped the guard entirely. A guard whose condition is
  broader than the thing it guards is a guard that never runs.

  Two halves. Machine-readable: `data-plan-cut-loops` on the SVG root, **a count rather than a
  boolean**, so it answers "was anything drawn" and "how much" with one value that cannot drift out
  of step with a separate flag. Human-readable: a red **NO GEOMETRY AT THIS CUT** note with the cut
  elevation, because a count does nothing for someone holding a printed sheet.

  **Deliberately not a silent re-cut at a lower plane.** The titleblock prints the cut elevation, so
  quietly cutting elsewhere would make that printed number a lie — a confident wrong answer instead
  of an obvious missing one. Asserted: an empty cut still reports the elevation it was *asked* for.

  Covered in `services/api/test_plan_transform.py` (same fixture, so the bake cost is paid once).
  Three mutations, all caught by name: removing the note, stamping it on **every** sheet — the twin,
  without which the empty-case check would pass on a plan that cried wolf on all of them — and
  hardcoding the loop count, which made the fixture stop containing an empty case and tripped the
  **vacuity guard** (`0 empty cut(s), 5 drawn`) rather than passing on nothing.


## Archived 2026-08-13 — five rings with no open work left in them

Moved wholesale out of [`roadmap.md`](roadmap.md), which says it carries **open items only**. Each of
these had zero open item bullets: R27, AUTHORING-GESTURE and R24-TOOLS-SPLIT are research narratives whose
conclusions already shipped, R42's two remaining entries are both ⛔ closed decisions,
and the Reach sweep describes wiring that was done. Together they were **239 lines of the open roadmap** describing no available work.** The research is worth keeping; it was in the wrong file.

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

## Reach sweep — Lane C/G/I *(2026-08-07)*

**Measured, then acted on.** `UNCALLED_CEILING` **131 → 123**, the drop measured by re-running the
scan rather than derived from what was wired.

- `portfolioCompare` wired into the portfolio panel as a **returns spread**. The executive roll-up
  gives a *blended* equity IRR — one number for the whole book, which cannot show that a single deal
  is carrying it. This gives per-project IRR / multiple / yield-on-cost from each project's latest
  solved scenario plus best-and-worst. An absent return renders em-dash, never 0%: a project with no
  solved scenario has not returned zero, and a fabricated zero would take the "worst" slot from a deal
  that genuinely holds it. **This is the R22-PIPELINE finding landing** — capability present, reach
  absent — folded into the sweep rather than re-listed as new work.
- `estimateBoe` wired as **Basis of estimate** on the budget panel. This closes a loop opened by
  R22-PROVENANCE: that work gave `estimate` line items `source` / `quote_ref` / `basis_date`, and
  `boe_ledger` checks them, but nothing showed the result — an estimate you cannot defend
  line-by-line is what a claim attacks first. The screen maps `code → cost_code` and `amount →
  total`, **the same seam `commercial_drift.ESTIMATE_TO_BOE` documents server-side**: handing the
  rows over unmapped does not raise, it silently produces a full, plausible, wrongly-keyed ledger.
- `clearBaseline` → `KNOWN_UNCALLED`, **with an expiry condition**. It deletes a captured schedule
  baseline, and R40-EOT ② has just made the *named* baseline the auditable input to an extension-of-
  time figure that ends up in arbitration. A one-click destroy beside that is a footgun, and "it has
  no caller" is not a reason to give it one. Retires when baseline deletion is behind a
  confirm-and-audit step.

**The procurement cluster is NOT a missing screen, and this is the correction worth carrying.** The
sweep's premise is that every uncalled method has a live server route, so the remedy is uniformly
"build the screen" — verified true for 110 of them. **A live route is not an available input.**
`buyoutPackages`, `buyoutSchedule`, `procurementLevel` and `procurementLevelQuotes` are POST endpoints
whose QTO lines must carry `{item, qty, unit, trade}`; the engine **skips any line without an `item`**
and falls back to a single `"General"` package without a grouping key. Both model-derived sources
(`qtoByFloor`, `estimateFromModel`) return `{ifc_class, count, unit, quantity, rate, amount}` — **no
`item`, no trade/csi/material_class/discipline**. Nothing in the client surface returns a
procurement-shaped line. A screen built on today's sources would render one package called "General"
and read as "this project has no scope". **These four need a trade classification on QTO lines
first**; that is the blocking item, not a panel.

## 🏗 R42 — INCREMENTAL COMMIT RING *(measured 2026-08-08)*

**The premise this ring corrects.** The obvious reading of the authoring pipeline — and the one I
reached first, from the route code alone — is *"every edit rewrites the whole IFC and reconverts the
whole model, so incremental geometry needs building."* **That is wrong, and the wrong half is the
expensive half to have believed.** Incremental geometry already exists and already ships:

* `POST /projects/{pid}/edit-preview` authors the element into a **one-element IFC** and converts
  just that (`services/api/src/aec_api/routers/authoring.py`, `services/data/src/aec_data/preview.py`)
* the viewer already holds **N fragment models keyed by id** — `loader.loadFragments(buffer, modelId)`
  and `disposeModel(id)` in `apps/web/src/viewer/loader.ts`, used today by the preview path, by
  drag-and-drop `.frag` open, and by reference models
* A29-LOCAL-PREVIEW already shows that geometry within ~2s, under an amber "not yet on the record"
  marker

So the pieces are built, wired, and in production. **What is missing is that the authoritative path
does not use them.** `authorAndReload` commits with `editIfc(..., publish=true)`, waits for a full
reconvert, then calls `loadProjectModel()` — which `disposeAll()`s and reloads everything, throwing
away the correct geometry it was already displaying and re-deriving it as part of the whole model.

**Measured on a 1,000-element model** (`Riverside School — structural`, dev API, same machine, same
converter, back to back):

| path | time | output |
|---|---|---|
| `edit-preview` — one element → `.frag` | **1.70 s** | 1,436 bytes |
| full republish — whole model | **37.39 s** | everything |

**22×, and the 1.7 s result is discarded.** 1,000 elements is a small building; the ratio widens with
the model, so the workflow degrades exactly as a project becomes worth working on. This is a
*number*, not an impression, and it should be re-measured rather than quoted after any converter
change — [[an-audit-must-state-its-configuration]].

### The ring

**SPIKED 2026-08-08, and the spike changed two things — read this before starting.**

*The stated hazard is smaller than written, and the sequencing below was wrong.* `_publish` already
takes `reconvert: bool` and does the two halves separately: (1) node converter → `.frag`, (2) rebuild
the properties index. So a commit CAN reindex without reconverting, and every GUID-keyed reader is
correct immediately — the index-staleness hazard does not have to exist. **But the halves are closer
in cost than hoped.** Measured on a 52 MB source: reindex **6.6 s**, convert **10.2 s** — the convert
is only 1.5× the reindex, because the reindex is itself a full IFC parse.

**So deferring the convert alone buys about 60%, not 95%, and R42-SESSION-MODEL is the bigger lever,
not the follow-up.** Both halves re-parse the whole file from disk; holding the model in memory is
what makes an incremental commit actually incremental, and it is what would let the index be appended
for one element rather than rebuilt. Re-sequence accordingly: **SESSION-MODEL first, then
COMMIT-DELTA on top of it.**

*Also found and FIXED in v0.3.906 (it was a prerequisite for any of this): `POST /publish` accepted
`reconvert` and nothing read it — `run_publish` called `_publish(p)` and took the default, so every
`reconvert=false` reconverted anyway. The switch this whole ring turns on was already present and
disconnected. `services/api/test_publish_reconvert.py`.*

- ⛔️ **R42-SESSION-WRITE — CLOSED, decided against 2026-08-09.** Deferring the per-edit IFC write
  was the remaining half of the speed win. **We are keeping the write.**

  *Why, stated so nobody re-opens it without new information.* Today every edit is durable the
  instant the request returns: `Project.source_ifc` points at a complete file, and publish, export,
  clash, the MCP tools and another user's optimistic-lock check all read that file as the truth.
  Deferring it moves the truth into server memory between edits and forces three answers nobody
  wants to give — does a mid-session export see the edits, are they lost on restart, does a second
  user see them before a flush.

  **And undo depends on it.** `edit_history` works by restoring a prior file path; it exists
  *because* every edit is a file. Deferring the write is not a caching change, it is a redesign of
  durability that takes undo with it.

  The cheap half is already banked — `R42-SESSION-MODEL` removed the re-PARSE (v0.3.907). What is
  left of the cost is the convert, and that is `R42-COMMIT-DELTA`'s territory, which does not touch
  durability at all. **Re-open only if the product decides to become session-based with an explicit
  Save**, which is a different product, not a faster one.

- ⛔️ **R42-UNDO — WITHDRAWN. The claim was false and I asserted it as verified.** This entry said
  *"there is no undo. Checked, not assumed: no inverse, no command stack."* **Undo and redo exist,
  are wired end to end, and have been for some time.**

  `services/api/src/aec_api/edit_history.py` is a bounded per-project undo/redo stack
  (`push` / `undo` / `redo` / `state`) kept as a storage sidecar. `POST /projects/{pid}/edit/undo`
  and `/edit/redo` restore the prior model version; **six** call sites push a pre-edit version
  (single edit, batch, macro, MCP run_recipe, …), and a batch deliberately pushes ONE entry so a
  multi-step command undoes as one step. The client has `editUndo` / `editRedo` / `editHistoryState`
  and a `↶ Undo` button in the rail that refreshes its own enabled state. There is even considered
  keybinding design: Ctrl+Z is reserved for popping the last point of an **in-progress draft**, with
  a comment saying element undo keeps the rail control precisely so the two do not collide.

  **How I got it wrong, because the mechanism matters more than the mistake.** I grepped
  `services/data/src/aec_data/edit*.py` for `def undo|undo_recipe|inverse`, found nothing, and wrote
  it down as checked. The capability lives in `services/api/`. That is the recorded lesson
  [[enumerate-the-table-not-the-names-you-know]] — **a grep proves a string absent, never a
  capability** — and writing "checked, not assumed" on top of an unchecked claim is worse than
  leaving it unqualified, because it tells the next reader not to re-check.

  **What is actually left, stated at the size it really is:** an undo costs a **full republish**
  (`_restore_version(..., publish=True)`), which the R42 measurements put at ~37 s on a 1,000-element
  model — so undo inherits exactly the cost R42-COMMIT-DELTA exists to remove, and needs no separate
  item. The only genuinely missing piece is a keyboard shortcut for *element* undo, since Ctrl+Z is
  taken by the draft-point undo; that is a small UX call, not a ring item.

### Deliberately NOT in this ring

* **Editing verbs** (align, mirror, trim/extend, offset, multi-select edit, working planes). The 96
  recipes are overwhelmingly `add_*`. Real, wanted, and cheaper once an edit is fast and reversible.
* **Constraints that survive an edit** — moving a wall does not re-solve its joins, its hosted
  openings or its dependents. Worth noting that this is *why* LOD-ASPECTS found Parametric Behavior
  unreadable from the model: it is unreadable partly because it is not yet there.
* **Sheets as data** — already 📐 R27, and the other half of "authoring tool" vs "modeller".

**Sequence (REVISED twice — see the spike note, and R42-UNDO withdrawn): R42-SESSION-MODEL (done), then R42-COMMIT-DELTA (done, v0.3.911). The ring is closed except R42-SESSION-WRITE, which was decided against.** The first is the one that
changes what the product *is*; the second removes the remaining per-edit constant; the third is table
stakes that gets cheaper once the first two define what an edit is. Everything under "NOT in this
ring" is additive at any later point and all of it is cheaper afterwards.

---

## 🧲 AUTHORING-GESTURE — the Open CAD Studio re-scan *(2026-08-03, premise-checked against the tree)*

Asked whether their drag-and-drop authoring is worth copying. **Three premises failed the check, two
of them mine**, so the answer is recorded with the corrections rather than the conclusion alone.

**1. Open CAD Studio does not author by drag-and-drop.** At v0.9.2 (2026-08-03, six releases past the
July study) every drag feature they ship is file-handling or chrome: *drag drawing files onto the
window* (v0.8.7) and *drag to reorder document tabs* (v0.8.9). Block and symbol placement is the
`INSERT` **command** — their own notes say there is no palette-insertion workflow. Their authoring
model is CAD-classic: type a command, pick points against snaps. **Building drag-to-author for parity
would be copying something that is not there.**

**2. Our precision suite is already at rough parity — I twice recommended building what exists.**
Verified in `apps/web/src/viewer/snapEngine.ts` and its call sites: `resolveSnap` + `segmentSnaps`
(endpoint / edge / midpoint / centre, then grid), `polarConstrain` (45° increments, 4° tolerance),
`applyDynamicInput` with a typed distance/angle constraint that **beats every automatic snap** because
the drafter said exactly what they want, shift-held ortho lock from the previous point, and a snap
glyph on hit. Plus `CADCMD` for the command grammar. SNAP-KIT shipped; the roadmap said so in
`docs/roadmap-completed.md` and two successive recommendations here ignored it.

*The instrument that failed both times was a memory file read instead of the code.* Same family as the
five already recorded — a claim that was true when written and had since been overtaken.

**3. Nothing in that GitHub account is usable as code — a licence wall, not a technical one.**
OpenCADStudio is **GPL-3.0**. Of twelve Python repos, `Road` / `freecad.trails` / `freecad.turns` /
`PyTrails` / `Delaunator-Python` are **LGPL-2.1**, and `NodeCAD` / `Modern-UI` are **GPL-3.0**. All
excluded by the MIT/BSD/Apache-only rule. `iced_aw` is MIT but Rust GUI widgets; the PythonOCC fork is
MIT over an LGPL base. **Nothing may be vendored, ported or read-and-reimplemented.** Behaviours
described in public release notes are interface descriptions rather than code, which is the same
footing the July study stood on when CADCMD was written.

### What is actually left, and it is small

## 🔪 R24-TOOLS-SPLIT — cut *(measured 2026-08-03, shipped v0.3.848)*

RAIL-SPLIT routed tool-groups to rail panels by their `data-tool` key, which worked for every group
except one: `qa` went whole to **Review**, and `GROUP_PANEL` recorded why Analyse could not become its
own rail item — *"the analysis it belongs beside (code, egress, cost, 4D) is still inside the `qa`
tool-group"*. A one-button rail item is the thin version of the empty-room failure, so Analyse waited
for this split rather than shipping hollow. **That condition is now met**, and the fold is gone.

**The measurement was the whole job.** The `qa` section was `apps/web/src/viewer/app.ts` **lines
3453–4539 — 1087 lines and 42 labelled controls with no internal structure at all**: zero
sub-headings, zero group markers, one divider. That is why this was *not* a re-parenting pass like
RAIL-SPLIT: **there was nothing to re-parent**, so the sub-group had to be created before anything
could be routed.

The seam fell exactly where the deferral note predicted — *"is the model right"* against *"what does
it tell you"*. **Three contiguous ranges, 234 lines, moved verbatim** into a second `section()` call
in the same builder:

| moved | controls | why |
|---|---|---|
| 3872–3936 | site logistics, 4D construction sequence | 4D — a reading over time |
| 4023–4158 | occupancy & egress, IBC code analysis, IEBC scope, cost estimate | code, egress, cost |
| 4194–4226 | the natural-language Ask | the one tool the `analyse` toolbox group already had |

**Cut as two `section()` calls, not as a file move — and that is what made it safe.** The block is one
closure over shared state (`api`, `pid`, `container`, the layer manager); extracting functions first is
how a re-parenting pass turns into a rewrite. Because each builder declares its own local `b` and
`out`, every moved range is the original text at the original indent, **not one identifier renamed**.
The status line was the trap worth naming: `out` is written by nearly every handler, so a single
shared one would have printed an Analyse result into the Review panel. Two locals, same name, one each.

**Verified by counting, in both directions.** `apps/web/src/viewer/toolsSplit.test.ts` freezes the
42-control inventory and asserts each is on the side the split intended, that none is in both, and
that neither half was hollowed out — a suite that only proves *Analyse has contents* passes just as
happily if `qa` had been emptied wholesale. Live at v0.3.848: Review 25 tools, Analyse 6 + Ask, the
moved handlers run (code analysis returned `IBC 2021 · CA adoption` after a jurisdiction re-check) and
each panel's status line stayed in its own panel.

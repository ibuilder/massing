# Roadmap

The single product roadmap — **open items only**, reconciled + re-prioritized **2026-07-24 at
v0.3.661**. The 🏢 R19, 🏛 R18 and 🏙 R20 rings and the whole 07-24 NOW list are **complete and
archived**. Everything ever shipped lives in [roadmap-completed.md](roadmap-completed.md); per-release
detail is in [CHANGELOG.md](../CHANGELOG.md). Supporting detail:
[production-readiness.md](production-readiness.md) · [gc-portal.md](gc-portal.md) ·
[ops-dr.md](ops-dr.md) · [mobile.md](mobile.md).

Three pillars on one IFC-keyed model: **BIM authoring/viewer** · **GC portal** ·
**developer/finance**. The finance and CRE pillars just took deep investment (R19 + R20) and the
authoring pillar closed its parity ring (R18). **What is thin now is the surface** — the interaction
craft, the demo, and the cross-cutting cost identity that make the shipped depth legible — plus the
structural carry-overs that keep the codebase workable.

**Status:** CodeQL 0 open alerts · backend suite green (**388** suites) · vitest 158 · single-source
version in `apps/web/package.json` · CI on Node 22. Reconciled **2026-07-25 at v0.3.687**.

**Read the gating honestly.** A large block of what remains is genuinely blocked — see
[⛔ Gated](#-gated--each-entry-names-its-unblocking-event). The ▶ NOW list below contains **only
non-gated work**.

---

## ▶ NOW — priority order (sprints of large chunks; one full-suite release per sprint)

0b. ◧ **🧱 FAMILY-COMPLETE — enough content to actually build a building** *(all six batches shipped
   v0.3.668–670; the completeness gate is green, depth-within-system continues)*.

   **Shipped.** The shelf went **41 packs / 281 families / 2,370 types → 57 / 426 / 2,796** across six
   catalog batches — plumbing, electrical, fire protection + alarm, mechanical, architectural +
   interiors, conveying + site — plus a `structural-foundations` pack the coverage gate forced.

   **The gate.** `family_packs.coverage()` (`GET /families/coverage`, `test_family_coverage`) checks
   the installed shelf against the IFC *type classes* each building system needs, per typology.
   Class-level, not family-count: it proves the shelf can place a pump, not that some catalog named
   something `fire_pump`. A system counts as satisfied only when **every** required class is present —
   terminals with no duct is not half an HVAC package — and a short system names its missing classes.

   **What it caught.** Zero `IfcFootingType` across 413 families: the catalog held W-shapes, HSS,
   precast, timber, rebar and PT, and no foundations, so all six typologies were unbuildable while
   the shelf looked enormous. Breadth had hidden it; only a mechanical check found it. All six —
   residential, commercial, hotel, hospital, industrial, airport — now clear every system.

   **What remains** *(the reason this is ◧ and not ✅)*:
   - **Depth-within-system.** The content plan's §8e target is **~800 families / ~7,500 types**;
     we are at 426 / 2,796. The gate proves each system is *representable*, not that it has the size
     series a real project schedules from. Size-series generators are the lever (3 AISC catalog
     families already expand to 1,299 real types) — apply the same to duct, pipe, luminaires,
     panelboards and door/window families.
   - **Raise the gate as the content grows.** Today it asks "is every system's class present". The
     next rung is "does every system have enough *types* to model it", which is the shape
     `tests/test_completeness.py` upstream already hints at.
   - ✅ **Duplicate families from batch 1** *(merged v0.3.688)*. Checking first changed what the merge
     meant: of the six keys the review flagged, **only one is a genuine duplicate**.
     `pipe_copper_l` → `pipe_copper_type_l` (one product, two names, one pack — the ASTM B88
     designation carries the wall thickness and wins). The other five are a **generic tier and a
     specific tier**: `wc_flush_valve` is one *kind* of toilet and the fixtures pack has no tank-type
     WC, `shower_receptor` is a *part* of a shower, `sink_kitchen` is not what "sink" means. Merging
     those would assert fixture types nobody specified — so the two-tier relation is now **recorded**
     (`FAMILY_TIERS`) instead of left implicit, and the next reviewer will not re-flag it. Done by
     **alias, not deletion**, because deleting a key breaks every model that already placed one; the
     generated packs are untouched since they are build output from the upstream generator.
   - ✅ **Pack licence** *(fixed v0.3.688)*. The premise was wrong and worth recording: the shelf
     reported `unlicensed` for all 57 packs, and the entry above blamed a manifest that "carries no
     `licence` field" — but `manifest.json` declares `CC0-1.0` for the library **and** on every pack
     row, alongside `code: MIT`. Nothing was unlicensed; our **reader** looked only for a singular
     per-pack `licence` key, so it missed both the library-level declaration and the plural
     `"licenses": [...]` list the rows actually use. A shape mismatch had been sitting in the backlog
     as a compliance problem. `unlicensed` is now 0, `licence_source` distinguishes a pack's own claim
     from an inherited one, and the terms follow the content into the import audit trail. The packs
     are licensed the same way as the rest of the platform: **code MIT, content CC0-1.0**.
   - **Content repo release.** The packs are still consumed from a working tree; a tagged upstream
     release would let the shelf pin a version. *(user action)*

4. ◧ **🎨 P2 authoring & document depth** *(L; slice it, reassess after two)*.
   ✅ **W10-2** *(v0.3.667)* — `family_shapes.py`: 14 parameterised profiles built as native IFC,
   swept or revolved, with boolean cut-outs. The write table is asserted **symmetric with the read
   table** so authored and imported content can't diverge, and every attribute name is validated
   against the real IFC4 schema. *(Meshes deliberately excluded — they can't be resized, scheduled
   or measured; that content belongs in an imported pack.)*
   **Remaining:** **B3** wall Axis + clip planes · **E5** parametric handles — both viewer-coupled
   and gated on the preview stall. *Every server-side item in this ring is now shipped.*
   ✅ **D2** *(v0.3.674)* — routed egress. The old check measured **straight-line** distance and said
   so; IBC 1017 limits distance *along the path of travel*, so the old number was always short and
   the error ran in the **unsafe** direction — it passed plans that do not comply. `egress_route.py`
   rasterises the plate and runs a multi-source Dijkstra from every exit; each space reports the
   routed distance, the straight-line one, and their **detour ratio**. No-route is its own outcome,
   an unmarked exit refuses rather than guessing, and the grid resolution is stated, not implied.
   ✅ **W10-5 + C6** *(v0.3.673)* — sections were bare linework: correct and unissuable. They now
   carry **poché** grouped by what the material *is* (structure heavier than enclosure heavier than
   openings — the one distinction linework cannot make), **LOD-following** so the tone steps back as
   the linework sharpens while the linework itself stays identical, **C6 reference-line datums**, grid
   bubbles, and the **floor-to-floor dimension chain**. A misspelled LOD is refused, not defaulted.

0c. ◧ **🎯 LOD-500 — field verification as a workflow, not a thousand clicks** *(v0.3.673; the
   ladder's top rung is now reachable)*.

   LOD 500 is the level most often misread. Per BIMForum it is **not** "more detail than LOD 400" —
   it is a *field-verified as-built* condition that applies to what exists rather than what was
   designed, and it is earned by someone going and looking. The 2024 specification adds that an LOD
   500 element's **accuracy must be stated by means other than the LOD number**.

   **Shipped.** The verification stamp had been written into the IFC since G1 and the LOD assessment
   never read it, so a fully verified model still reported "LOD 400, capped".
   - `lod.achieved_lod` reaches 500 from the stamp; a *thin verified* element gets there and an
     information-complete unverified one does not. Measured-outside-tolerance is **not** promoted.
   - `GET /lod/handover-readiness` — the gap as a **work list** (reason + next action per element,
     by discipline), because "62% ready" cannot be scheduled.
   - `scan_deviation.per_element_deviation` + `POST /scan/verify-lod500` — attribute a point cloud to
     individual elements and stamp the ones that verify, **with their measured deviation** so the
     assertion states an accuracy. Uncovered elements get no verdict: absence of points is not
     evidence. `apply=false` is a dry run.

   **Next rungs:**
   - **Verification evidence** — attach the scan/photo/report that backs each stamp, so an assertion
     is auditable rather than merely present.
   - **Verification-aware handover** — gate the turnover package on readiness, and carry the
     verification into COBie.
   - **Registered scan alignment** — today the cloud is assumed to be in model coordinates; a real
     survey needs a registration step before deviation means anything.


## 🏗 R21 — LOD 400→500 DOCUMENTATION RING *(from a real LOD 400 shop-drawing set, 2026-07-25)*

Measured against an actual issued wall-section + detail package (13 sheets, 1:100 → 1:10) rather than
against a description of one. The mission is **acquisition → turnover at LOD 500**, and LOD 500 is
field-verified as-built — but a project only *reaches* verification through an issuable LOD 400 set.
These are the gaps between what the platform draws today and what that package contains.

**Tier 1 — the set cannot be issued without these**

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
- ◧ **R21-4D-CLASH** *(phase 1 shipped v0.3.682; install-before-support still open)* — **sequence clash**: two trades occupying one space in the same schedule
  window, or an install ordered before its support. The 4D timeline and CPM both exist; this reads
  them together.

  **Phase 2 needs a prerequisite that does not exist**: `schedule_activity` carries no element
  GlobalId, so nothing knows *what a task installs*. Install-before-support cannot be computed
  without a real **task→element binding** — that binding is the actual next piece of work, and
  approximating it (by trade, by name match) would produce confident findings nobody can trust.
- ✅ **R21-TAGS** *(shipped v0.3.683)* — **element tags on drawings** (a door tagged `D2` carrying `900 x 2100`),
  auto-placed with leader avoidance, driven by the same type data the schedules already read.
- ✅ **R21-BREAKLINE** *(shipped v0.3.683)* — break lines + partial views, so a detail can stop mid-element honestly
  instead of running to the sheet edge.

**Tier 3 — set-level assembly**

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
- **R22-GOLDEN-THREAD** *(M)* — **design freeze + immutable approval log.** Named baseline model
  states, who approved what and when, and a diff of everything after. Legally mandated in the UK
  (Building Safety Act 2022). Our GUID-stable single-IFC architecture makes this *cheaper to build
  here than anywhere else* — a federated-file competitor cannot emit it automatically.
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
- **R22-NOTICE-CLOCK** *(S/M)* — **contractual notice clocks / time-bar tracking.** Detect a
  triggering event in a daily log or RFI, start the contract's notice period, draft the notice.
  Highest dollar-per-line-of-code feature in construction administration; we already hold the
  contract calendar and the daily record.
- ⭐ **R22-CLASSIFY-AI** *(M)* — **assisted classification of *imported* IFC.** We have a canonical
  discipline tree and a rule that a Uniclass code is never guessed — correct, and it means a client's
  unclassified model (which is nearly every real model) gets nothing. Propose codes, human confirms.
  Without this, QTO/cost/FCI/COBie only work on models we authored.
- **R22-PROCURE-DEPTH** *(M)* — sub **prequalification** (bonding/EMR/capacity), **contract-clause
  risk extraction**, and **vendor scorecards persisting across projects**. Bid leveling covers one
  step of five.
- **R22-MEMORY** *(M/L)* — **cross-project cost + decision memory** keyed to our own quantity codes.
  The only item here that *compounds*: every bid result makes the next estimate better, and our
  structured QTO makes it cleaner than any document-scraping competitor's.

**Tier 3 — on-ramps and reach**

- **R22-CAD-IMPORT** *(M)* — **DWG/DXF/PDF base-plan import.** The existing building stock is legacy
  CAD; today feasibility and test-fit only run on models we authored. This is the on-ramp for every
  non-BIM firm.
- ⭐ **R22-CARBON-OPTION** *(M)* — **embodied carbon per design option**, on the option card beside
  cost and area, computed from model quantities we already have. Increasingly a hard requirement in
  institutional underwriting.
- **R22-ACCT-SEAM** *(M)* — **AP/GL/cost-code export + ERP connectors.** Do *not* build a ledger;
  build the seam so actuals stop being hand-fed into EAC.
- **R22-OPTION-OBJECT** *(S/M)* — make **option the primary object**: geometry + unit mix + cost +
  carbon + IRR as one comparable record, so no massing is ever evaluated without its returns.
- **R22-ENTITLE-RISK** *(S/M)* — **approval probability + entitlement duration into the existing
  Monte Carlo.** The largest unmodelled uncertainty in any acquisition proforma.
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

- ⭐ **R23-CONSTRAINTS** *(L)* — W10-9 via kiwisolver + least_squares, per the unblock above.
  **Dependency taken 2026-07-25.** `kiwisolver` is **Modified BSD-3** — squarely on the approved
  licence list — a ~60–100 KB prebuilt wheel, and already a transitive dependency of matplotlib, so
  it adds a *declaration* rather than new surface area. Trivially reversible. Proceeding on the
  standing delegation; flagged here so it can be objected to in one line.
- ✅ **R23-SHADOW-COST** *(shipped v0.3.679)* — `viewer/world.ts:182-192` puts a 2048² shadow map over a **±140 m ortho
  frustum** — catastrophic texel density on a 30-storey tower — on top of hemisphere + fill lights and
  SSAO+Bloom through a 4× MSAA composer. Set `shadowMap.autoUpdate = false` with manual invalidation,
  fit the frustum to visible bounds, and run post only on camera rest.
- **R23-STOREY-LOD** *(L)* — server-side coarse proxies per storey (extruded footprint / AABB) for
  small parts, MEP and furniture, swapping to real fragments on demand. Server-side keeps it
  deterministic, offline and $0. *`docs/phase2-large-models.md` claims no custom LOD is needed and is
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
- ✅ **R23-REVIT-EXPORT-CFG** *(shipped v0.3.680)* — script `IFCExportConfiguration` from the pyRevit bridge instead of
  trusting the export dialog, and **enforce the `IfcGUID` shared parameter** so GlobalIds survive
  re-export. That is our first non-negotiable (reference by GUID, never transient ids) and it is
  currently left to a checkbox someone else ticks. Add a pre-publish model audit (warnings, unplaced
  rooms, in-place families, imported CAD) — exactly the conditions that produce garbage IFC.

**Tier 3 — worthwhile, lower urgency**

- **R23-DIGEST** *(M)* — a deterministic multi-scale model digest (project → storey → zone → system →
  element) as compact JSON. Immediate non-AI value as a **diffable change-detection snapshot** between
  IFC versions; becomes the retrieval index if AI features land.
- **R23-RECIPE-ARTIFACT** *(M)* — make the edit-recipe log first-class: versioned, diffable,
  exportable, replayable against a fresh IFC. It already *is* a CAD operation timeline; formalising it
  serves provenance, the as-built audit trail, and AI consumption in one move.
- **R23-BATCH-OVERLAYS** *(S)* — app-authored overlays (pins, grid, snap markers, dimensions, clash
  markers) use **zero** instancing; `three@0.184.0` has `BatchedMesh`. Keep the default BIM pass off
  `MeshStandardMaterial` (presentation mode only); make FOV/FAR responsive by viewport class.
- **R23-GLTF-COMPRESS** *(S/M)* — Draco or meshopt on the server-side glTF export path (permissive,
  server-side only, no browser dependency added). 90–95% size reduction.
- **R23-SYMBOL-COUNT** *(M)* — deterministic template-match symbol counting in the **existing** pdf.js
  takeoff worker: mark one instance, normalised cross-correlation, non-maximum suppression.
  **Zero new dependencies**, offline, auditable — which matters for quantities that feed a bid.
- **R23-PREFAB-KIT** *(M)* — a prefab kit is a `query_dsl.select()` scope + BOM + pull-plan task +
  delivery date. A join across spines we already have, not a new engine. Strong LOD-500 fit: kits are
  what actually get field-verified.
- **R23-JURISDICTION-PACKS** *(M)* — jurisdiction-scoped data-requirement rule packs (a regulator
  defines a pset spec a submitted model must satisfy). `query_dsl` + `rule_library` + IDS already carry
  this shape; turnover data requirements are the same problem.

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


## 🎛 R24 — INTERFACE RING *(external design audit 2026-07-25; see [design-audit.md](design-audit.md))*

**The thesis, and it is not "add features".** Adoption is the binding constraint, not capability.
**47%** of contractors name *getting people to use new technology* their biggest challenge (AGC 2024);
**12%** of features carry 80% of daily use (Pendo, 615 subscriptions). With ~130 modules shipped, about
**ten** matter to any one person on a given day — and which ten depends entirely on who they are. A
catalog with favourites and a filter treats that as a **browsing** problem. It is a **routing** problem.

The payoff is specific to us: every record, geometry and cost line shares one IFC GlobalId, so the
platform can answer *"where did this number come from"* in one hop. **The interface does not cash that
in.** R24 is about making the engine's one real advantage visible.

*Two findings were already partly closed by the independent live audit in v0.3.677 (nav density
14 → 7, and 0 unlabelled controls) — recorded in design-audit.md so they are not re-litigated.*

**Tier 1 — the front door**

- ⭐ **R24-SPINE** *(L)* — replace the catalog *as the entry point* with a persona-scoped rail of ~7
  destinations carrying live **ball-in-your-court** counts (not totals — a badge you cannot act on is
  noise). Nothing is deleted: the catalog stays behind "All modules" and ⌘K. Builds directly on the
  Build/Money · Standards/Analyse split already shipped.
- ⭐ **R24-CMDK-VERBS** *(M)* — the ⌘K palette exists and covers workspaces/modules/records. Extend it
  to **authoring verbs**, **element lookup by GlobalId**, and **reports**, grouped by
  *verb / record / element / report* rather than a flat list. The existing `/assistant` ask box becomes
  the fallback row, not a separate feature to find.
- ⭐ **R24-READINESS-HOME** *(M)* — *(supersedes UX-READINESS-EVERYWHERE)* home becomes a queue with a
  horizon: work queue left, health right, one banded verdict on top, rows actionable inline. The
  dashboard already computes ball-in-your-court and the SLA feed; Master Builder already computes the
  verdict. This is promotion and shaping, not new engines.
- ✅ **R24-ROLE-EXPLAIN** *(shipped v0.3.685)* — **never hide, explain.** Two role dimensions (capability × party) gate
  controls invisibly today. A disabled control that states *needs Engineer* converts a support ticket
  into onboarding. Cheap, and it makes the permission model legible.

**Tier 2 — the object and its numbers**

- ⭐ **R24-ELEMENT-CARD** *(L)* — one card wherever an element is named (viewer, RFI, estimate line,
  pay app, COBie row), with a six-state lifecycle strip: **designed · checked · priced · scheduled ·
  installed · verified**. The data for all six already exists on one key. *Note: `priced` is now real
  in the model itself — see the 5D cost binding — and `verified` is the LOD-500 stamp.*
- ⭐ **R24-TRACE-UI** *(M)* — every figure expands into the chain that produced it, tagged
  **model-derived / overridden / market assumption**, ending in a clickable element. `traceability.py`
  already walks model→cost→GL by GlobalId; this is the surface for it.
- **R24-RUNS-INBOX** *(M)* — clash, IDS, cost and energy results are modals, so they have **no
  history**. A modal cannot be diffed against last week, and for an engineer the delta between two
  runs *is* the work product. Make each a durable **Run** (inputs, timestamp, author, artifact, diff)
  with a per-project inbox.
- **R24-JOB-TRAY** *(M)* — convert / reindex / republish are background work with foreground UI.
  A global named-job tray, leaveable and resumable; the SSE feed already carries the events.

**Tier 3 — density, field, and the long tail**

- **R24-DENSITY** *(M)* — a three-step density scale (Field 56 px / Default 36 px / Compact 28 px),
  one switch, per user, persisted. A superintendent and a scheduler should not get the same row height.
- **R24-FIELD-MODE** *(L)* — a field *mode*, not a responsive breakpoint: capture-first home, 56 px
  targets, 7:1 outdoor contrast, permanently visible sync queue, voice-to-text on notes.
- **R24-MONO-DATA** *(S)* — a mono face for everything machine-produced (GlobalIds, quantities,
  currency, dates, statuses) and a sans for language. The fastest available signal for
  *"this is data, not prose"*, and nearly free.
- **R24-EMPTY-GUIDE** *(S)* — empty states were hardened for robustness, not guidance. The viewer's
  empty state (shipped v0.3.677) is the pattern to copy across.
- **R24-TERMS** *(S)* — three vocabularies (BIM · GC · real-estate) collide in one shell; pick one per
  persona rather than showing all three to everyone.


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

* **R27-LAYOUT ① — a sheet has regions, and we can say where.** `sheet_extract.py` reads the text
  layer only (`extract_from_text` regexes a drawing index; `extract_pdf` walks pages via `pypdf`) —
  there is no notion of *where on the sheet* anything sits. Add `sheet_layout.py`: recover rectangles
  from the page content stream, classify by the ADIRO-style vocabulary (titleblock · revision table ·
  legend · general notes · view/viewport · key plan · scale bar), and return regions in page
  coordinates with a per-region `basis` of `vector` | `text` | `unknown`. **A sheet whose vectors are
  gone returns `unknown`, never an empty region list** — the same unknown ≠ none rule that ten
  engines now enforce. Evidence: arXiv:2607.18997 §layout-layer; gap confirmed in
  [sheet_extract.py](../services/api/src/aec_api/sheet_extract.py).

* **R27-LAYOUT ② — a takeoff scoped to the view it belongs to.**
  [takeoff2d.py](../services/api/src/aec_api/takeoff2d.py) takes `regions` **from the caller** and a
  `scale_units_per_px` **from the caller** — every quantity on a sheet is hand-traced and hand-
  calibrated, and nothing checks that a traced polygon sits inside the view it is being priced
  against. With ① landed: seed candidate regions from the detected viewports, and read the scale from
  the titleblock's scale text or a detected scale bar so `calibration_scale` has something to *check*
  rather than only something to accept. **The scale is proposed, never silently applied** — a takeoff
  calibrated by a machine that was wrong is worse than one nobody calibrated, because it looks done.

* **R27-LAYOUT ③ — a note attaches to what it governs.** Once regions exist, a general note, a
  keynote and a revision cloud each belong to a *view*, not to a page number. This is what makes
  `keynotes`/`DETAIL-REF` (R21) round-trip against received sheets rather than only our own.

* **R27-CLAIM-TYPE — what kind of statement is this?** The representation handbook's one durable
  idea: a record should say whether it is an **intent** (specified), an **embodiment** (built),
  an **evidence** (measured/observed) or an **inference** (derived). `element_facts.gather()` already
  states a `source` per fact and `verified()` already prefers an IFC stamp over a field record — this
  generalises that from one engine's convention into a field the whole fact spine carries. The payoff
  is concrete: "this wall is fire-rated" sourced from a *specification* and from a *field
  observation* are different claims, and today they render identically.

* **R27-SOV-LOOP — close takeoff → estimate → SOV → pay app.** Confirmed gap, not a suspicion: the
  `estimate` and `sov` modules both exist, `cost.py` reads a G703, and **nothing anywhere builds an
  SOV from an estimate**. The chain the whole cost pillar implies is broken at exactly one seam, and
  it is currently bridged by re-keying. Build `sov_from_estimate()`: estimate lines → SOV line items,
  carrying `quantity_source`/`rate_source` (shipped v0.3.699) forward so a pay-app line can be traced
  back to the model element it was measured from. Highest value-per-line-of-code in this ring —
  every piece already exists.

* **R27-RISK-CALIBRATE — the distribution comes from your own history, not a guess.**
  [schedule_risk.py](../services/api/src/aec_api/schedule_risk.py) already runs Monte Carlo over the CPM
  network and reports P10/P50/P80/P90 — the *shape* is done. What it lacks is a defensible
  distribution: durations come from caller-supplied three-point estimates, i.e. somebody's opinion
  entered three times. The industry answer is calibration against a large historical corpus, which we
  will never have offline. **The project's own corpus we do have**: schedule baselines plus progress
  actuals are planned-vs-actual per activity. Derive per-activity-type spread from that, report
  `calibrated_from: n activities` — and when n is too small to mean anything, **say so and fall back
  to the three-point, rather than dressing an opinion as a statistic.**

* **R27-FIRM-MEMORY — standards that outlive a project.** `rule_library` is per-project (`load(pid)`
  / `save(pid)`); `design_standards` and `standards_expert` are likewise project-scoped. A firm's
  actual standards are the thing that *does not* change per project, and today they are re-authored
  or copied. Add an org-scoped tier that a project inherits and may override, with the override
  visible as an override. Deliberately **not** an AI feature: the sources selling "institutional
  memory" all reduce to clean extraction plus safe write-back, both of which we have.

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

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

**Status:** CodeQL 0 open alerts · backend suite green (**375** suites) · vitest 134 · single-source
version in `apps/web/package.json` · CI on Node 22. Reconciled **2026-07-25 at v0.3.675**.

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
   - **Duplicate families from batch 1.** The upstream review flagged overlaps introduced by the
     plumbing batch (`pipe_copper_type_l`/`pipe_copper_l`, `wc_flush_valve`/`toilet`,
     `sink_kitchen`+`sink_service`/`sink`, and three more). Key uniqueness did not catch them because
     the keys differ. Needs a merge decision, not a unilateral edit.
   - **Content repo release + licence.** The packs are consumed from a working tree; the shelf still
     reports `unlicensed` for every pack because the generator's manifest carries no `licence` field.
     Needs a tagged release upstream and a licence declaration. *(user action)*

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

- **R21-HATCH** *(M)* — **material hatch patterns on cut geometry.** The reference details separate
  concrete (stipple), reinforced concrete (crosshatch), steel (diagonal), insulation, masonry and
  earth by *pattern*. `drawings.py` poché (v0.3.673) fills by class group with flat grey tones, which
  cannot make those distinctions at 1:10. Needs an SVG `<pattern>` library keyed to IFC material, and
  a scale-aware pattern density so a 1:100 section and a 1:10 detail do not use the same spacing.
- **R21-KEYNOTE-SECT** *(M)* — **keynote leaders with dot terminators on sections/details.** The
  package annotates every layer of the assembly ("60mm MINERAL-GLASS WOOL BOARD INSULATION",
  "RC SLAB AS PER STRUCTURAL DRAWINGS") in a left-hand text column with leaders to a dot on the
  component. `drawing.py` has `_leader_callout` for PLANS only; sections have no annotation layer.
- **R21-DETAIL-REF** *(M)* — **detail callout bubbles + the section↔detail cross-reference graph.**
  Numbered bubbles on the wall section point at enlarged details on other sheets; each detail carries
  its own bubble, title and scale ("12 / BRIDGE TOP DETAIL / 1:10"). Today nothing links a section to
  its details, so a set cannot be navigated or checked for orphaned/dangling references.
- **R21-VG-OVERRIDES** *(L)* — **object styles + rule-based view filters.** Per-category **cut vs
  projection** line weight, colour and pattern, plus filters that override graphics by rule
  ("fire rating ≠ None", "width > 900"). This is what makes output look like a drawing instead of a
  dump. **Compose on `query_dsl.py`** — it is already THE element selector; a view filter is a stored
  selector plus an override, not a new engine.

**Tier 2 — coordination depth the set implies**

- **R21-SOFT-CLASH** *(M)* — **clearance (soft) clash + a clash matrix.** Hard clash exists; the
  reference material distinguishes hard / soft-clearance / workflow-4D. Soft clash is a *rules* problem
  (NEC working space, valve access, coil pull, door swing) and the discipline-pair matrix declares
  which combinations are tested at all. Without it, "clash-free" overstates what was checked.
- **R21-4D-CLASH** *(M)* — **sequence clash**: two trades occupying one space in the same schedule
  window, or an install ordered before its support. The 4D timeline and CPM both exist; this reads
  them together.
- **R21-TAGS** *(M)* — **element tags on drawings** (a door tagged `D2` carrying `900 x 2100`),
  auto-placed with leader avoidance, driven by the same type data the schedules already read.
- **R21-BREAKLINE** *(S)* — break lines + partial views, so a detail can stop mid-element honestly
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

## 🎚 UX-POLISH — interaction-craft ring (remainder beyond the NOW sprint)

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

**New-dependency-gated (needs an explicit OK):** **RT-BVH** — three-mesh-bvh for the raw-three raycast
paths · **RT-KNIP** — unused-export / dead-dep scan *(feeds REL-7)* · **W10-9** dimensional
constraints *(planegcs, LGPL — sidecar-solved, baked to IFC)*.

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

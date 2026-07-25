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

**Status:** CodeQL 0 open alerts · backend suite green (**363** suites) · vitest 132 · single-source
version in `apps/web/package.json` · CI on Node 22.

**Read the gating honestly.** A large block of what remains is genuinely blocked — see
[⛔ Gated](#-gated--each-entry-names-its-unblocking-event). The ▶ NOW list below contains **only
non-gated work**.

---

## ▶ NOW — priority order (sprints of large chunks; one full-suite release per sprint)

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

**Verification-gated (the dev-preview geometry stall — `buildPanels` never runs, so none of this can
be honestly verified live):** 🧭 **R17 viewer tail** — CITE-JUMP *(S; click-to-expand claims jump the
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

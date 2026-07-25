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
   **Remaining:** a browsable shelf UI in the Library palette *(UX-3 depth, below)*, and the
   content repo publishing a tagged release so `scripts/fetch_families.py` has something to fetch.
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
   **Remaining:** **W10-5** section/elevation annotation views · **C6** reference-line datums +
   LOD-following poché · **D2** routed egress / life-safety plans · **B3** wall Axis + clip planes ·
   **E5** parametric handles.
5. **⚙️ WFE-3** *(S; deferred-by-choice, now cheap)* — per-project configurable workflow transitions.
6. **📈 GEN-SCORE depth** *(M)* — per-option 5D takeoffs + EPD carbon on the generative option scorer.

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

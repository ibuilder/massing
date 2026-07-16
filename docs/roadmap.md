# Roadmap

The single product roadmap. Supporting detail lives in:
[production-readiness.md](production-readiness.md) (security/perf/ops checklist),
[gc-portal.md](gc-portal.md), [gc-tools-audit.md](gc-tools-audit.md),
[ux-findings.md](ux-findings.md).

Three pillars on one IFC-keyed model: **BIM viewer** · **GC portal** (config-driven modules) ·
**developer/finance** (proforma). Shipped continuously — latest release **v0.3.335**. Recent waves: the
**unified discipline tree** (DISC-1…4b — one CSI-MasterFormat/UniFormat vocabulary + colour palette across
the viewer, model browser, estimate, and both engines; fire-alarm + telecom as first-class systems; the demo
tower rebuilt with curtain-wall facade / fire-rated walls / roof / all 8 disciplines), the **UX-2 interactive
annotation** track (notes · dimensions · tags · revision clouds, rendered onto plans), **MEP-FP**
fire-protection systems, and **CODE-EBC** existing-building classification.

> **This file holds only what is still OPEN.** Everything shipped — every wave, track, and release — lives in
> [roadmap-completed.md](roadmap-completed.md), so *what's left* is never buried under *what's done*. The
> Model workspace is a genuine authoring + coordination program (from-scratch models, GUID-stable
> draw/edit recipes, drag-to-move, model browser, levels, selection sets, the construction-document set, code
> intelligence, the discipline tree). What remains is **the UX consolidation of that capability** plus
> incremental depth, spikes, upstream-blocked work, and documented non-goals — nothing is blocking.

---

## ⚡ Order of attack — highest value first

The authoring/coordination/discipline "big rocks" have shipped. The front now is the **UI/UX Master Pass** —
consolidating ~97 accreted tools into a designer's workspace and surfacing the two under-exposed capabilities
(interactive annotation, unified library) — then the remaining depth tracks.

1. **UX-1 — Ribbon consolidation** *(★★★★★)* — regroup the ~97 tools into a lifecycle task ribbon
   (Build · Annotate · Library · Analyze · Coordinate · Document · Data). Low-risk, immediate legibility win.
2. **UX-3 — Unified Library palette** *(★★★★★)* — one browsable content panel (types + CONTENT-1 catalog +
   import) with thumbnails, `tag:`/`type:`/`discipline:` search, Recent, and pick-item→pick-host→auto-build.
3. **UX-4 — Designer workspace layout** *(★★★★)* — assemble the Project-Browser spine + docked Properties
   (instance/type split) + Library + ribbon + Info-Box into one coherent shell.
4. **RFI-0 depth** *(★★★★★)* — missing-dimension detection + the NL-QA natural-language layer over the
   decision-readiness audit (the shipped audit composes approvability + detail-rules + hygiene + clash).
5. **EST-1 depth** *(★★★★)* — full QTO integration + tie crew-days to schedule durations (5D loop).
6. **Frontier (own planning pass each):** COLLAB-1 multiplayer · SITE-1 BIM-GIS · VIZ-U1 (Unity/WebGL) ·
   PROFORMA-LIVE · ENV-1 · AUTH-VS visual node authoring.

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
- **UX-3 — Unified Library palette** *(L · high)* — one browsable **content panel** unifying the W10-1
  type/family system + the CONTENT-1 catalog (logistics/furniture/landscaping) + external IFC/glTF import: a
  **thumbnail grid**, case-insensitive search with `tag:`/`type:`/`discipline:` filters, a **Recent** bucket,
  predefined groups, and **click/drag-to-place**. Hosted content uses **pick-item → pick-host → auto-build**
  (a door picks its wall; a steel connection picks its beams). **Appendable IFC libraries** — load types
  (+ profiles/materials) from any IFC file. New `library` client + a **Library** rail group. Folds in the
  CONTENT-1 remaining (curated CC0 seed + thumbnail palette) and H1 (CC0 furniture families + PBR materials).
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
- **C6 (remaining)** — reference-line datums (`IfcReferent`/`IfcVirtualElement`) + **"drawn detail follows
  LOD"** poché (representation selection + `IfcMaterialLayerSet` poché + annotation density → schematic
  single-line ↔ CD layered poché). Permissive libs only (no AGPL).
- **D2** — **routed egress / life-safety plans** (path-trace over the W9-4 semantic graph, not just tabulated).
- **D5 (next)** — detail callouts on the **PDF** sheet path + real sheet-number refs.
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
- **W10-4 (next)** — flow/sizing psets + coincident-port auto-connect (extends `connect_mep`).
- **W10-5** — **annotation & tagging layer** — *largely delivered by UX-2 (notes/dims/tags/clouds on plans);*
  finish section/elevation annotation views.
- **W10-6** — **schedules & QTO** (`IfcElementQuantity` — partly via C4; finish computed schedule / keynote-
  legend views into the export pipeline).
- **W10-7** — **structural analytical model** (`IfcStructuralAnalysisModel`, curve/surface members, point
  connections, load cases) — net-new domain alongside the physical model.
- **W10-9** — **parametric constraints & dimensional locks (the hard one)** — no IFC representation; store in a
  sidecar, solve, bake to IFC. Start with 1D/alignment locks. **License:** FreeCAD's **planegcs (LGPL,
  extractable)**; avoid python-solvespace (GPL) and OpenSCAD (GPL).

## 🔬 Wave 9 — research-scan leftovers

- **W9-4 (harder half)** — ingest **specs / drawings / code documents** as graph nodes + **NL→graph query with
  cited sources** (GUID + spec page + code section) — the explainability substrate under W9-2 code-checks and
  the RFI-0 NL-QA layer.
- **W9-5 (L part)** — smooth **equipment motion along paths** as the 4D slider advances + swept crane-reach
  clash.
- **W9-6b** — a procedural **office space-planning generator** (headcount program → `IfcSpace` zones + furniture
  + auto BOM).
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
  returns the `cost_vintage` it priced with — reproducible estimates. **Remaining build-order steps:** the
  `massing.cloud` CloudDatasetImporter (signed bundle), real public-source ingest (BLS/FRED/DoD/Census),
  location factors, delta sync, Ed25519 signatures, escalation-forward.
- **COST-DB — vintage-versioned cost database + import** *(L · high)* — a local, **vintage-versioned (by year)**
  cost database populated from **either free public sources (BLS/FRED/DoD-UFC/Census — offline-first) or the
  `massing.cloud` subscription API**, behind one `DatasetImporter` interface. Projects **pin** to a specific
  vintage so every estimate is reproducible; import `latest` or a specific historical year with a configurable
  fallback (`strict`/`nearest`); cloud bundles are **checksum-/signature-verified** before a transactional
  upsert; older vintages **escalate forward** via stored PPI series. Feeds 5D cost / estimating / GC-portal
  budget / FCA / Last Planner through the pinned vintage. Open-source ships the **public importer + adapters
  only** — proprietary data (1build/RSMeans) arrives solely via the subscriber's authenticated cloud pull,
  never committed to the repo. Full spec + schema + build order: **[cost-db-import-plan.md](cost-db-import-plan.md)**
  (server side: `massing_cloud_plugin_plan.md`; location engine: `massing_location_cost_import_plan.md`).
  *Build order: schema → PublicDataImporter (offline spine) → vintage resolver + project pinning →
  CloudDatasetImporter (manifest/bundle/verify/upsert) → subscription detection + public fallback → delta sync →
  Ed25519 signatures → escalation-forward.*

### 🚫 RFI-prevention (the openBIM information-delivery moat)
- ✅ **RFI-0 missing-dimension detection SHIPPED v0.3.336** — a 5th gap source in `decision_readiness`:
  doors/windows with no `OverallWidth`/`OverallHeight` + rooms with no floor area → ranked `dimensions`
  gaps that ride the existing BCF promotion.
- **RFI-0 (remaining)** *(M · ★★★★★)* — the **NL-QA natural-language QA layer** over the audit (needs the
  W9-4 spec/drawing graph nodes for cited-source answers).

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
- **AUTH-VS — visual node-based authoring** *(L · parity)* — a visual node-graph canvas over the edit-recipe
  engine (chain recipes as nodes; the recipe log already *is* a graph). The visual, no-code sibling of the
  shipped AI command bar + sandboxed `execute_ifc_code`.

### 🚀 Model-authoring & collaboration frontier
- **COLLAB-1** *(L · ★★★★★)* — **real-time multiplayer co-editing** (presence, cursors, live-streamed edits) +
  lightweight **in-model comments** — the biggest gap for a browser-based modeling tool.
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
- **DISC-poché** — an opt-in **colour-by-discipline mode** for the 2D plan/PDF poché (today the poché is
  deliberate per-class architectural convention).
- **DISC-cw** — **context-aware curtain-wall member classification** (an `IfcMember`/`IfcPlate` aggregated under
  an `IfcCurtainWall` → Architectural, not Structural).

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
- **CODE-3 (deepen)** — thread the resolved edition into the Track-D detail-rule citations.
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

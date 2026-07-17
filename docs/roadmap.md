# Roadmap

The single product roadmap. Supporting detail lives in:
[production-readiness.md](production-readiness.md) (security/perf/ops checklist),
[gc-portal.md](gc-portal.md), [gc-tools-audit.md](gc-tools-audit.md),
[ux-findings.md](ux-findings.md).

Three pillars on one IFC-keyed model: **BIM viewer** · **GC portal** (config-driven modules) ·
**developer/finance** (proforma). Shipped continuously — latest release **v0.3.377**. Recent waves
(v0.3.352–377): the **five frontier tracks** (W10-7 structural analytical · W9-4/RFI-0 doc-graph + NL-QA ·
COLLAB-1 real-time co-editing · AUTH-VS node authoring · UX-1/3/4 designer workspace); a **security
hardening pass**; and the top **enterprise deliverable/relationship gaps** — the **compiled drawing-set
PDF**, the **shareable project package** (overview + drawings + cost + proforma in one file), and the
**model estimate → developer proforma** hard-cost sync. Full record in [roadmap-completed.md](roadmap-completed.md).

> **This file holds only what is still OPEN.** Everything shipped — every wave, track, and release — lives in
> [roadmap-completed.md](roadmap-completed.md), so *what's left* is never buried under *what's done*. The
> Model workspace is a genuine authoring + coordination program (from-scratch models, GUID-stable
> draw/edit recipes, drag-to-move, model browser, levels, selection sets, the construction-document set, code
> intelligence, the discipline tree). What remains is **the UX consolidation of that capability** plus
> incremental depth, spikes, upstream-blocked work, and documented non-goals — nothing is blocking.

---

## 🗓 Weekend worklist — prioritized (2026-07-18/19)

Everything shipped is in **[roadmap-completed.md](roadmap-completed.md)**. This is what's LEFT, in order.
The frontier tracks, UX, security, and the top enterprise **deliverable/relationship gaps** all landed
(v0.3.352–377): the **compiled drawing-set PDF** (375), the **shareable project package** — overview +
drawings + cost + proforma (377), and the **model estimate → proforma** hard-cost sync (376) are done.

**Do next, highest value first:**

1. ✅ **KEYS — Revit-style authoring shortcuts — SHIPPED v0.3.380** — 2-letter codes arm a draw tool
   (WA/CL/BM/SL/RF/RA/SC/SB/RB/FT/DU/PI/CT/WR), Esc disarms, `?` shows help, HUD echoes the buffer,
   suppressed in inputs. *Remaining: type-a-dimension-while-drawing (VCB) + more non-draw actions.*
2. ✅ **PREFLIGHT — issuance gate — SHIPPED v0.3.381** — `GET /projects/{pid}/preflight`: one PASS/HOLD
   verdict + checklist composing the model-health lenses (hygiene · clash · code-readiness · verified) +
   **classification completeness** + open high-priority issues (hard blocker). *(pyRevit research.)*
3. ✅ **STRUCT-SOLVE — apply gravity loads + solve statics — SHIPPED v0.3.382** —
   `GET /projects/{pid}/structure/solve` applies an ASCE 7 gravity load case (dead + live by occupancy) to
   the W10-7 analytical curve members and runs a **determinate member-by-member statics solve** —
   reactions (`wL/2`), max shear/moment (`wL²/8`), indicative deflection vs L/360, and shear/moment/
   deflection diagrams; vertical members carry a tributary column axial; factored forces via the governing
   LRFD combo. Viewer surfaces it in the analytical panel with inline diagrams. **Lateral SHIPPED v0.3.389**
   — `GET /structure/lateral`: ASCE 7 seismic ELF (§12.8) + simplified wind MWFRS → base shear + story
   forces/shears/overturning, governing case flagged. **Member load activities SHIPPED v0.3.390** — the
   `apply_structural_loads` recipe writes an `IfcStructuralLinearAction` (D+L, global −Z) onto every
   analytical member, grouped under the load group → a loaded, solver-ready analytical IFC (idempotent,
   purged on re-derive). *Remaining: continuous-beam / coupled-frame (FEM) solve · section properties read
   from the physical member · drift/P-delta.*
4. ✅ **VIEW-RANGE — plan view-depth — SHIPPED v0.3.383** — `plan.svg?view_depth=<m>` draws the footprint
   of elements below the cut but within the view depth (foundations/footings) as dashed hidden lines with a
   legend — the Revit Top/Cut/Bottom/View-Depth model, not a single `cut_z`. `below_footprint_baked` sections
   each below-cut element through its mid-height; class-filterable; backward-compatible. *(IMG_0247.)*
   *Remaining: per-plane element-visibility control + wiring view_depth into the footprint sheet/PDF path.*
5. ✅ **COVER-SHEET — rendered cover + drawing index — SHIPPED v0.3.384** — the compiled set's cover is now
   a title block (project · subtitle · issue date · sheet count) + a **key-plan footprint thumbnail rendered
   from the model** + a **discipline-grouped, paginated drawing index** (no more silent truncation past the
   first page). `drawingset._cover_pdf`. *(audit gap #4.)*
6. ✅ **TAKEOFF-2D — PDF/scan quantity takeoff — SHIPPED v0.3.388** — a 📐 2D Takeoff overlay (upload a
   drawing image · calibrate scale · trace polygons or one-click flood-fill · quantify) + `POST /takeoff/2d`
   measuring shoelace area / polyline length × the calibration → priced per-assembly quantities into the 5D
   estimate. Measurement/pricing core unit-tested; canvas tracer build-verified. *(OpenTakeoff technique.)*
   *Remaining: PDF.js page rasterization in-app + a finer flood-fill contour trace.*
7. ✅ **DISC-SSOT — single discipline/class source — SHIPPED v0.3.385** — sheet-series is now a **derived
   view** of the canonical discipline map (`classification.series_of_ifc_class`), and `sheetgen.detect_series`
   + the drawing-set cover both derive from it (their private tables removed) — discipline↔sheet-series can
   no longer drift (reproduces the old map exactly). Takt *trade* (`fourd.TRADE_FOR_CLASS`) is documented as
   a deliberately separate build-sequence axis, not folded in. *(audit gap #7.)*
8. **REL-3/4 — modularize the worst hotspots** *(tech-debt · L, one PR each, TESTED)* — `viewer/app.ts`,
   `main.ts`, `modules.py`, `main.py`; façade re-exports; suite green after each. *(`openModule` O(n·m) fixed
   v0.3.373; import cycles verified false positives.)*
9. **Then:** SITE-1 open-geodata slice · MEP-SIZE · EXPORT (DWG/glb/USD + first-class IFC re-export) ·
   durable background-job queue · COST-DB · SHEET-LINK · MEP-SIZE · the rest of the frontier depth.

Full detail: **[🔎 Research-2 additions](#-research-2-additions-2026-07)** (KEYS/VIEW-RANGE/TAKEOFF-2D/…),
**[🏗 Enterprise gaps](#-enterprise-gaps-audit-2026-07)** (from the codebase audit), and
**[🔧 Reliability & hardening](#-reliability--hardening-rel)**.

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

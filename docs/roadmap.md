# Roadmap

The single product roadmap. Supporting detail lives in:
[production-readiness.md](production-readiness.md) (security/perf/ops checklist),
[gc-portal.md](gc-portal.md), [gc-tools-audit.md](gc-tools-audit.md),
[ux-findings.md](ux-findings.md).

Three pillars on one IFC-keyed model: **BIM viewer** · **GC portal** (config-driven modules) ·
**developer/finance** (proforma). Shipped continuously — latest release **v0.3.312** (recent: docs/marketing
refresh + status page · CODE-EBC existing-building classifier · MEP-FP fire-protection systems · Capacitor 7
security). A research-backed **UI/UX Master Pass** plan (designer workspace: ribbon · annotation · library)
is queued below.

> **This file holds only what is still OPEN.** Everything shipped — every wave, track, and release —
> lives in [roadmap-completed.md](roadmap-completed.md), so *what's left* is never buried under *what's
> done*. The in-browser authoring initiative (P1–P6 + model browser / manage-levels / selection sets /
> edit-in-place), the product-feature roadmap, the code-quality/hardening waves (1–7), Wave 8 (all seven
> field-research tracks + the syndication connector), and the shipped parts of Waves 9–11 + AI-MCP are all
> in the archive. The Model workspace is now a genuine authoring+coordination program, not a viewer with
> buttons. What remains is incremental depth, spikes, upstream-blocked work, and documented non-goals —
> nothing is blocking.

---

## ⚡ Order of attack — the next ~8, highest value first

The Master Builder wave's headline deliverables have shipped — the **construction-document set** (plans /
sections / elevations / schedules → SVG·PDF·DXF + the 3-part project manual), **code intelligence**
(code-analysis, egress pre-check, jurisdiction-aware editions, approvability pre-flight, detail-rule
engine), **authoring guardrails + progressive disclosure**, and the **LOD-500 turnover layer**. What's left
deepens each track:

**The "next ~8" order of attack is cleared** (CODE-2 · D5 · W10-4 · S4 · E1 · A1 · G2 · B3 · B4). The current
front, drawn from the 2026-07 research round 2 + remaining depth:
1. **RFI-0 — decision-readiness audit** *(★★★★★)* — compose approvability + detail-rule validate + model-hygiene + clash into one "what's missing?" report → BCF.
2. **EST-1 — productivity-rate cost/duration library** — man-hours/unit → labour cost + duration from quantities (5D).
3. ✅ **CONTENT-1 (import) SHIPPED v0.3.321** — `parse_mesh` (glTF/OBJ/STL/PLY → recentred metre verts/faces, Y-up→Z-up) + `detect_category` (filename → catalog key) + `POST /content/import` (auto-classified place via `place_content`) + a ⬆ Import-mesh picker. *(catalog + placement ✅ v0.3.306.) Remaining: a curated CC0 seed + thumbnail palette → folds into UX-3.*
4. **A2** — RAG-grounded code-gen. **F0b** — derive Box/Axis/FootPrint. *(A4 scene-digest ✅ v0.3.322; B5 connections ✅ v0.3.320.)*
5. **Frontier (own planning pass):** COLLAB-1 multiplayer · SITE-1/BIM-GIS · VIZ-U1 (Unity/WebGL) · CODE-EBC · PROFORMA-LIVE · ENV-1.

*(CODE-2 ✅ v0.3.295; D5 ✅ 296; W10-4 ✅ 297; S4 ✅ 298; E1 ✅ 299; A1 ✅ 300 (RCE-hardened 301); G2 ✅ 302; B3 ✅ 304; B4 ✅ 305; CONTENT-1 ✅ 306.)*

---

## ⏳ What's left — the whole open roadmap, prioritized

Ordered most-actionable first; pull an item up on real customer need. Grouped by track for context, but the
order-of-attack above is the priority spine.

### 🧱 Wave 11 — The Master Builder (remaining)

The single architectural spine (multi-representation, view-keyed elements) + the guardrails and the drawing
generator already ship; these deepen geometry, drawings, code-intelligence, and the authoring UX.

**Construction-document generation (the CD set ships; these deepen it)**
- **C6 (remaining slices)** — reference-line datums (`IfcReferent`/`IfcVirtualElement`) and **"drawn detail
  follows LOD"** poché (representation selection + `IfcMaterialLayerSet` poché + annotation density →
  schematic single-line ↔ CD layered poché). Permissive libs only (no AGPL). *(DXF export + plans/sections/
  elevations/schedules → SVG·PDF·DXF + the project manual already ship — see the archive.)*

**Geometry depth → LOD 350/400**
- ✅ **B3 (sloped tops) SHIPPED v0.3.304** — `set_wall_slope` rebuilds the wall Body as a trapezoidal
  extrusion (no boolean), top rising start_height→end_height; ⟋ Slope wall top tool. Verified by
  tessellation + a real web-ifc→Fragments converter round-trip. *Remaining B3 sub-items: wall Axis
  representation + arbitrary clip planes (gable peak mid-span).*
- ✅ **B4 SHIPPED v0.3.305** — **procedural-mesh escape hatch** (`add_mesh_representation` →
  `IfcTriangulatedFaceSet` from verts/faces; △ Add mesh tool + AI/code-callable). Verified by tessellation +
  converter round-trip.
- ✅ **B5 (first slice) SHIPPED v0.3.320** — `connect_elements` records an `IfcRelConnectsElements` between
  two elements (idempotent, rejects self/missing) + `element_connections` read-back (pairs + per-element
  degree); `GET /element-connections`. *Next: fasteners/hangers as real assemblies + connection geometry.*
- **F0b** — derive **Box / Axis / FootPrint** geometry on demand from `Body` (consumed by the C drawing generator).

**Code + spec + detail intelligence (IBC / MasterFormat)** — *D1 code-analysis, D3/D7 detail rules, D4
carriers, D6 project manual, D8 approvability pre-flight all ship (see the archive); these remain:*
- **D2** — **routed egress / life-safety plans** (path-trace over the W9-4 semantic graph, not just tabulated).
- ✅ **D5 SHIPPED v0.3.296** — **detail callouts** on the plan: an NCS-style divided-circle callout + a
  DETAILS legend for every element carrying an attached detail (`IfcRelAssociatesDocument`), distinct from
  the C2 keynote bubbles; `plan_svg` `details` toggle + count, flows into the SVG sheet. *(Keynotes-from-
  classification already ship via C2.) Next: detail callouts on the PDF sheet path + real sheet-number refs.*
- **D8 follow-ups** — wire COMcheck/energy-doc + A117.1 clearance checks into the pre-flight and round its findings to BCF.
- **`Pset_Massing_SpecLink` breadcrumb** — the remaining Track-D carrier.

**Open-ended authoring (the moat)**
- ✅ **A1 SHIPPED v0.3.300** — **sandboxed `execute_ifc_code`** (`sandbox.py`: AST allowlist, no
  imports/IO/reflection/dunder, curated namespace; off unless `AEC_ALLOW_IFC_CODE=1`; runs through the
  versioned/undo-able `/edit` path; ⚡ Run IFC code tool). *Next: A2 RAG index over ifcopenshell docs to
  ground code-gen, A3 AI emits recipes, A4 scene-digest.*
- **A2** — **RAG index** over ifcopenshell / IFC docs to ground code-gen.
- ✅ **A4 SHIPPED v0.3.322** — LLM **scene-digest** (`scene.digest`): composes element counts / storeys /
  spaces / MEP disciplines / phasing / LOD / hygiene into a compact dict + prose; `GET /scene-digest` + a 🔎
  Model digest tool; injected into the `/ai/author` planner prompt so authoring is grounded in the model.

**Master-builder UX (low barrier)** — *E4 progressive-disclosure toolbar + E8 authoring-guardrails (first
slice) + E9 selector DSL ship (see the archive); these remain:*
- ✅ **E8 (deepen) SHIPPED v0.3.317** — guardrails extended to nested type `dims`, footprint `points` arrays,
  sloped-wall heights, procedural-mesh verts/faces, and new reference requirements (connect_mep guid_a+guid_b,
  set_system_predefined system). *Remaining: model-aware checks (host is actually a wall, storey exists) — need
  the model at precheck time, a bigger change than the params-level rules.*
- ✅ **E1 SHIPPED v0.3.299** — **drawing inference** (`inference.ts`): automatic on-axis / parallel /
  perpendicular snapping from the previous point + edge, within ~6°, without holding Shift; hard
  geometry-vertex snap still wins; unit-tested. *Next: live inference guide-lines + a midpoint hover target.*
- **E2** — **type-a-dimension-while-drawing** (VCB).
- **E3** — **sketch-to-BIM push/pull** (2D profile → extrude).
- **E5** — **direct-manipulation parametric handles**.
- **E6** — **recipe-log undo/redo + design-option branches** (the recipe log *is* the undo stack).
- **E7** — **live schedules / quantities as you model**.

**LOD-500 verified-as-built data + content library** — *G1 as-built verify + G3 manufacturer/serial ship
(see the archive); these remain:*
- ✅ **G2 SHIPPED v0.3.302** — field-verified as-built **dimensions + variance** (`record_asbuilt_dimension`
  → `Massing_AsBuiltDim` measured/design/variance/within-tolerance; `asbuilt_summary` counts
  with_dimensions + out-of-tolerance; measure form in the as-built tool).
- ✅ **G3 follow-up SHIPPED v0.3.318** — warranty / O&M **document** refs via `IfcRelAssociatesDocument`:
  `attach_om_document` recipe (purpose-tagged) + `asbuilt_summary.with_om_docs` + a 📄 Attach O&M/warranty doc
  control in the ✅ As-built tool.
- **H1** — seed **CC0 furniture families + PBR materials** (CC0/CC-BY only — ambientCG, Poly Haven, Poly Pizza, Quaternius, Kenney, AMD MaterialX), attribution + license stored per asset.

**License guardrails (firm):** `ifcopenshell` + its geom serializers are **LGPL** — safe to depend on.
Reimplement drawing/annotation *techniques*, never vendor GPL code. SVG→PDF/DXF via permissive libs only
(**no AGPL** — no PyMuPDF). CC0 asset sources vetted per-asset. IDS is an open buildingSMART standard.

### 🤖 AI-MCP / NL authoring (remaining)

S1–S3 ship (deterministic baseline → multi-step LLM interpretation, confirm-before-apply). Remaining:
- ✅ **S4 SHIPPED v0.3.298** — model **undo / redo** (`edit_history` sidecar stack + `POST /edit/{undo,redo}`
  + `GET /edit/history` + ↶/↷ toolbar buttons; GUID-stable version restore). The `/edit-preview` ghosting
  half already ships. *Next: multi-step undo grouping (one apply-all = one undo).*
- **S5** — multi-turn **clarifying questions**.
- Then **read tools** (quantities / schedules / clashes / violations) + an actual **MCP server surface**.

### 🏛️ Wave 10 — authoring-suite leftovers (not superseded)

- **W10-2** — **parametric family generators** (code-defined; typed params + optional formulas; profile
  library I/L/T/U/C/rect/circle + swept/boolean primitives so doors/windows/columns/casework are *generated*,
  not boxes). Freeform families via an optional **build123d (Apache-2.0) / OCP (LGPL)** track through
  `ifcopenshell.geom`. *Pure ifcopenshell for the core.*
- ✅ **W10-4 (first slice) SHIPPED v0.3.297** — **MEP port-to-port connectivity** (`connect_mep` recipe →
  `IfcRelConnectsPorts`) + `mep.connectivity` validation (ports connected/open, links, dangling elements;
  `GET /mep/connectivity`) + a two-step Connect flow in the 🔀 MEP tool. *Remaining: flow/sizing psets +
  coincident-port auto-connect.*
- **W10-5** — **annotation & tagging layer** (`IfcAnnotation` tags/dimensions/text/keynotes on the plan/section/elevation views).
- **W10-6** — **schedules & QTO** (`IfcElementQuantity` — *partly shipped via C4*; finish computed schedule/keynote-legend views into the export pipeline).
- **W10-7** — **structural analytical model** (`IfcStructuralAnalysisModel`, curve/surface members, point connections, load cases) — net-new domain alongside the physical model.
- **W10-9** — **parametric constraints & dimensional locks (the hard one)** — geometric constraint solving has no IFC representation; store constraints in a sidecar, solve, bake to IFC. Start with 1D/alignment locks. **License:** use FreeCAD's **planegcs (LGPL, extractable)**; *avoid python-solvespace (GPL) and OpenSCAD (GPL).*

### 🔬 Wave 9 — research-scan leftovers

- **W9-4 (harder half)** — ingest **specs / drawings / code documents** as graph nodes + an **NL→graph query with cited sources** (GUID + spec page + code section) — the explainability substrate under the W9-2 code-checks.
- **W9-5 (L part)** — smooth **equipment motion along paths** as the 4D slider advances + **swept crane-reach clash** (moving-equipment conflicts over time).
- **W9-6b** — a procedural **office space-planning generator** (headcount program → `IfcSpace` zones + furniture + auto BOM).
- **W9-7 — AI 2D-PDF auto-takeoff** *(optional / paid, flagged bridge)* — we already ship **manual** calibrated PDF takeoff; AI auto-extraction of quantities is proprietary/paid → a flagged bridge like the paid Autodesk RVT path, never core.
- **W9-8 — NL imperative authoring** *(largely covered by AI-MCP)* — "add a 2-hr fire wall between the corridor and the stair" → proposed recipe → confirm → apply. Folds into the AI-MCP track above.

---

## 🔐 Sign-in & first-run onboarding (open slices)

**Goal:** make social sign-in the prominent default and sequence it into the tutorial — *without* a hard
gate (the app runs free/offline without an account; a signup wall before the "aha" moment craters
top-of-funnel for open/self-hostable tools). We already have Google + Microsoft OAuth (config-gated, shown
above the password form), MFA, SSO/SAML/SCIM, and a first-run welcome modal + ≤5-step tour. This is
**prominence + flow**, not new auth. Grounded in social-login conversion data, reverse-trial/value-first
studies, and onboarding-benchmark research. Files: `apps/web/src/ui/onboarding.ts`, `apps/web/src/account/accountUI.ts`.

**First slice (one sprint — the core ask):**
- **B1 — optional sign-in as the welcome modal's first panel** *(M)* — a headline + one prominent
  **Continue with Microsoft** + **Continue with Google** (only the providers the server has configured, via
  `authProviders()`), a quiet "More options," and a clearly-visible **"Explore without an account →"** that
  drops to the existing quick-start cards. Prominent, never a wall.
- **B2 — sign-in → tour** *(S)* — after a successful sign-in *or* "Explore without an account", auto-launch
  the existing tour and `markOnboarded()` once.
- **A1 — keep Google + Microsoft as co-equal visible defaults** *(S)* — Microsoft is the B2B/M365-Azure AD
  pick our audience (GCs, developers, A/E) actually lives in; zero new backend.
- **A2 — collapse everything else behind "More sign-in options"** *(S)* — password, org SSO/SAML, Procore —
  kills six-logo decision paralysis at the highest-intent moment.
- **C1 — reorder the sign-in modal to lead with one big provider button + "More options"** *(S)* — match the
  first-run panel for consistency.

**Fast-follow:**
- **B3 — role self-selection right after sign-in** *(M)* — reuse the existing role picker as an inline step,
  then gear the tools rail / tour to that role (role personalization is ~+40% retention).
- **B4 — keep the tour ≤5 steps** *(S)* — repoint the old final "sign in" step now that sign-in moves to the
  front (completion drops >50% past 5 steps).
- **C2 — value-moment prompt** *(S)* — higher-contrast "Sign in" toolbar button + a "Sign in to save your
  work" affordance once a guest has created/modified something (ask after a win, not a wall).

**Deferred with explicit triggers:**
- **A3 — Sign in with Apple** *(M)* — web-only today means Apple's "must also offer Sign in with Apple" rule
  does **not** apply (it binds only a native App Store app that offers another social login). Build only
  alongside a native iOS wrapper; adds the $99/yr Apple Developer Program + a private-relay email path.
- **A4 — skip Facebook** (net-negative, consumer-coded, high in-app-browser failure) **and GitHub** (wrong
  audience); LinkedIn only if analytics show demand.
- **B5 — persistent quick-start checklist** *(L)* — checklist-launched tours convert best (~67%); a home for
  secondary discovery, deferred past the first slice.

*Privacy/mission guardrails: keep the guest/offline path fully functional; no telemetry/personal data before
consent; SSO buttons stay config-gated so self-hosters don't advertise providers they haven't set up.*

---

## 🔮 Future — 2026-07 research round 2 (productivity-5D · existing-building code · RFI-prevention · Unity viz · content library · BIM-GIS)

Vetted from a 9-image field scan + 4 platform sources (an AI owner's-rep "eliminate-the-RFI" platform, a
game engine's AEC/IFC path, an open-source BIM+GIS digital-twin, and a 3D content warehouse). License/legal
flags are firm; **competitor product names kept out — capabilities described directly** (per the standing
directive). Interop targets / content platforms / open standards are named where they're integrations, not
rivalries. Ranked most-actionable first. Most confirm existing depth (MEP, the design→turnover spine,
ISO 19650, pull-planning, portfolio PMO); the genuinely net-new items:

### 📊 Estimating → 5D depth
- ✅ **EST-1 (first slice) SHIPPED v0.3.308** — `productivity.py` man-hours/unit rate library + loading
  factors; `labor_estimate` (quantity → man-hours → crew-days → cost) + `from_model` rough takeoff; `GET
  /estimate/labor{,/rates}` + a 💰 Labour estimate tool.
- ✅ **EST-1 material/equipment SHIPPED v0.3.314** — `MATERIALS` + `EQUIPMENT` $/unit benchmark layer +
  `full_estimate` (per-line material/equipment/line-total + grand total); `GET /estimate/labor?full=true` +
  the 💰 Cost estimate tool shows labour/material/equipment/total. Excludes overhead/profit. *Next: full QTO
  integration + tie crew-days to the schedule (durations).*
- **EST-1 (original spec)** *(M · high · buildable now)* — a **man-hours-per-unit**
  productivity-rate table (earthworks / concrete / masonry / structural steel / MEP / finishes) keyed by work
  activity + typical crew. From the model's computed quantities → labour hours → crew → **duration + labour
  cost**, with regional/condition loading factors (weather, congestion, night shift). Ties quantities →
  schedule + 5D cost; extends the estimating / EVM / resource-loading stack. Industry-benchmark facts,
  user-adjustable per project.

### 🚫 RFI-prevention (the openBIM information-delivery moat)
- ✅ **RFI-0 (first slice) SHIPPED v0.3.307** — **decision-readiness audit** (`rfi_prevention.decision_readiness`
  composes approvability + detail-rule validate + model-hygiene + clash → one ranked gap list, each with a
  fix; `GET /rfi/readiness` + a 🚫 Decision-readiness tool).
- ✅ **RFI-0 → BCF SHIPPED v0.3.313** — `POST /rfi/readiness/bcf` promotes every readiness gap to a
  GUID-anchored, category-labelled, severity-prioritised `type="readiness"` BCF topic (idempotent; mirrors the
  egress→BCF pattern); 📌 Promote-to-BCF button on the 🚫 tool. *Next: missing-dimension detection + the NL-QA
  natural-language layer over the audit.*
- **RFI-0 (original spec)** *(M · ★★★★★)* — the proactive inverse of the RFI: scan the model +
  drawings + specs for the **information gaps a builder would otherwise have to ask about** — missing
  dimensions, unresolved details, undefined finishes/specs, un-substantiated ratings, missing keynotes,
  open clashes — and surface them as a ranked *resolve-before-IFC* list that round-trips to BCF. Composes the
  shipped approvability pre-flight + detail-rule `validate_rules` + model-hygiene (`model_qa`) + clash-intel
  into one "what's missing?" report. The natural-language QA layer (**NL-QA**) plugs in here. Directly on the
  "information delivery" mission.

### 🪑 Content library — curated, auto-classified IFC parts (builds on B4)
- ✅ **CONTENT-1 (first slice) SHIPPED v0.3.306** — `content.py` catalog (~20 categories: site logistics /
  furniture / landscaping) + `place_content` recipe (authors an item at [E,N] from a supplied mesh or a sized
  placeholder → correct IFC class + phase (logistics = temporary, 4D-phased) + Uniclass/OmniClass); `GET
  /content/catalog` + a 🏗 Site content library palette. *Next: glTF/OBJ/SketchUp asset import → auto-detect
  category, click-to-place, and a license-vetted CC0 seed of detailed meshes.*
- ✅ **CONTENT-1 (import) SHIPPED v0.3.321** — import a **well-detailed mesh** (glTF/GLB/OBJ/STL/PLY — incl. a
  SketchUp model via glTF) and **auto-classify + place it as the *right* IFC**: `content.parse_mesh` (recentred
  metre verts/faces, Y-up→Z-up, face cap), `content.detect_category` (filename → catalog key), `POST
  /content/import` authors via `place_content` (furniture → `IfcFurniture`; site-logistics → proxy on the
  Temporary phase; landscaping → `IfcGeographicElement`) + a ⬆ Import-mesh picker. Per-asset **license vetting**
  is the operator's responsibility (CC0/CC-BY preferred; SketchUp models carry the SketchUp General Model
  License — vet each). *Remaining: a curated CC0 seed library + a browsable thumbnail palette → UX-3.*

### 🎮 Visualization — Unity as the optional bridge (supersedes the Unreal framing)
- **VIZ-U1 — Unity/Pixyz IFC → WebGL presentation build** *(L · optional/paid-license/flagged)* — Unity's
  Pixyz / Asset-Transformer imports **IFC natively** (preserving GlobalId + metadata), and Unity exports a
  **WebGL build that runs in a browser** — no cloud-GPU pixel-stream. So a high-fidelity presentation mode can
  ship as a *browser build*, materially closer to our web-first/offline core than the earlier engine's
  pixel-streaming path. Still a proprietary seat-licensed engine → optional, feature-flagged, **one-way (viz
  only), never the default viewer**. **This supersedes the earlier VIZ-3/VIZ-4 (Unreal) framing for the paid
  bridge tier.** The primary on-mission viz path stays VIZ-1 (glTF export, already ships) + VIZ-2 (three.js
  PBR presentation mode, offline + license-free).

### 🏛 Existing-building code intelligence
- ✅ **CODE-EBC SHIPPED v0.3.310** — IEBC **Work Area Method** scope classifier (`ebc.py`): `classify(...)`
  decision tree → **Repair · Alteration Level 1/2/3 · Change of Occupancy · Addition** with the driving
  citations (§502–§507 + requirements chapter), the nested applicable levels, and the jurisdiction's adopted
  IEBC edition; the >50%-work-area rule (§505) splits Level 2 from Level 3. `from_model(...)` infers a
  first-guess scope from phasing (existing vs new/demolish), overridable. `GET /codes/ebc/pathways` +
  `GET /projects/{pid}/codecheck/ebc?infer=` + a 🏚 Existing-building code tool. Facts of law (copyright-safe
  like CODE-1/2/3); AHJ makes the determination. `test_ebc.py` (16 scenarios). *Next: tie the classification
  to which approvability checks apply, and a change-of-occupancy occupant-load delta.*

### 🌍 BIM-GIS digital twin (reinforces the SITE-1 frontier item)
- **SITE-1 (reinforced) — multi-scale BIM ↔ GIS view** *(M · ★★★★)* — a browser view composing the **building
  IFC** with its **regional GIS context** (parcel, zoning envelope, terrain, neighbours) from open geodata
  (GeoJSON / parcel APIs) — the "digital-twin readiness" layer. Validated by an **open-source (AGPL) BIM+GIS
  digital-twin peer** using IFC/GeoJSON/BCF/IDS — *reimplement the techniques, never vendor the AGPL code.*
  Feeds authoring + the code/zoning engine.

### 🌦 Early-design environmental performance
- **ENV-1 — wind-comfort / microclimate at massing** *(M · med)* — beside the shipped solar-access analysis,
  a simplified **pedestrian wind-comfort** pass over the massing (prevailing-wind exposure, wind-shadow) for
  early-design "is this a wind tunnel?" feedback. Offline + approximate (not CFD); a CFD-grade version stays a
  flagged bridge.

### 🧩 Authoring surface (parity) + MEP completeness
- **AUTH-VS — visual node-based authoring** *(L · parity)* — a visual **node-graph scripting** canvas over the
  edit-recipe engine (chain recipes as nodes; the recipe log already *is* a graph) for repetitive parametric
  authoring without code. Complements the shipped AI command bar + sandboxed `execute_ifc_code` — the visual,
  no-code sibling. (The studio node-editor is the seed.)
- ✅ **MEP-FP (first slice) SHIPPED v0.3.311** — fire protection is now a **first-class distribution system**
  beside HVAC/plumbing/electrical: IfcDistributionSystems carry a **discipline** via `PredefinedType`
  (FIREPROTECTION/…); `add_mep_*` take a `discipline`, `set_system_predefined` retypes a system, `add_sprinkler`
  authors an `IfcFireSuppressionTerminal` head, and `mep_summary` reports discipline + a by-discipline rollup +
  `has_fire_protection`. Fire terminals are connectable (W10-4 covers sprinkler runs).
- ✅ **MEP-FP equipment SHIPPED v0.3.315** — `add_fire_equipment` authors sprinkler / hose-reel / FDC /
  hydrant (`IfcFireSuppressionTerminal` subtypes) + fire pump (`IfcPump`) onto the fire system; 🧯
  Fire-protection equipment tool places at the last-clicked point.
- ✅ **MEP-FP sprinkler coverage SHIPPED v0.3.316** — `mep.sprinkler_coverage` (NFPA-13 max area-per-head by
  hazard) head-count vs protected-area (IfcSpace NetFloorArea) pre-check; `GET /mep/sprinkler-coverage` + a 🧯
  coverage button.
- ✅ **Vertical risers SHIPPED v0.3.319** — `add_riser` sweeps an IfcPipeSegment vertically (+Z, bottom→top)
  with end ports on a system — fire standpipes / plumbing stacks / vents; ⭱ Vertical riser tool. The vertical
  complement to `add_mep_run`. *Next: sprinkler spacing/obstruction rules + tie to the fire-alarm sheet layer.*

**Not-new (confirmed existing depth):** the MEP 4-discipline model (HVAC/electrical/plumbing/fire — MEP-FP
above is the one gap), the design→turnover lifecycle spine, ISO 19650 BIM-management, Lean pull-planning, and
multi-project portfolio PMO all already ship.

### 🔒 Security backlog (Dependabot triage, 2026-07-15)

Surfaced on push at v0.3.309; **not runtime/CI-exposed**, so triaged rather than hot-patched:

- **SEC-DEP-1 — Capacitor 6 → 7 upgrade** ✅ *(shipped v0.3.312)* — 7 `tar` advisories (6 high / 1 medium,
  GHSA-9ppj-…/qffp-…/83g3-… etc., all extraction-time symlink/hardlink path-traversal) entered **only** via
  `@capacitor/cli@6`'s transitive `tar@6.2.1`. The fix is `tar ≥ 7.5.16`, but `tar@7` is ESM-only and
  Capacitor 6's CLI is CJS (`require('tar')` → `ERR_REQUIRE_ESM`), so a bare npm `override` breaks the mobile
  build. Real exploit path was nil — the CLI extracts only its own trusted platform templates during a
  developer-run `cap sync`, never untrusted input, never in CI or at runtime. Resolved by bumping the four
  `@capacitor/*` deps 6→7 (`@capacitor/cli@7.6.8` → `tar@7.5.20`); `capacitor.config.ts` needed no v7 changes and
  no native projects are checked in, so no Gradle migration was required.
- ✅ **SEC-DEP-2 — `glib` 0.20 (Tauri)** *(RESOLVED — dismissed `not_used`, 2026-07-16)* — the medium
  unsoundness (RUSTSEC-2024-0429 / GHSA-wrw7-89jp-8q8g) in `glib::VariantStrIter`'s `Iterator` impls (NULL-deref
  UB, not an exploit) is a **Linux-desktop-only** transitive dep of Tauri 2's **gtk3** webview stack
  (webkit2gtk 0.19 → gtk/gdk/gio/glib **0.18**); Windows uses WebView2 and macOS uses WKWebView, neither pulls
  glib. The **only** patched version is glib **≥ 0.20**, which is the **gtk4** generation and is incompatible
  with Tauri 2's gtk3 stack (`gtk 0.18` requires `glib ^0.18`; a `[patch]` override breaks the desktop build).
  Our code never calls `VariantStrIter`. **No gtk3-compatible fix exists**, so the Dependabot alert (#5) was
  dismissed as `not_used` with this rationale; the real fix arrives when Tauri moves to a gtk4/glib-0.20
  baseline (Tauri 3 / a future gtk4 `wry`). **Security tab is now clean: 0 CodeQL + 0 Dependabot alerts.**

---

## 🎨 UI/UX Master Pass — the designer's modeling workspace (end-of-roadmap consolidation)

Research-backed (Bonsai/IfcOpenShell · Revit + Dynamo/pyRevit · SketchUp + 3D Warehouse · Tekla component
catalog · ArchiCAD GDL/Info-Box). **Why now:** the model rail has grown to **~97 tools across 7 loosely-named
collapsible sections** (`models / origin / draft / gridlevels / exports / qa / authoring`) — real capability,
but organized by accretion, not by how a designer actually models. Two capabilities the wave shipped are also
under-surfaced: **annotation exists only baked into generated plan SVGs** (C2/D5) — there is *no interactive
in-view annotation* — and the **content library is scattered across separate buttons** (🏗 CONTENT-1, the
family catalog, the W10-1 type browser) rather than one browsable palette. This track consolidates the whole
authoring surface into an industry-standard workspace and fills those two gaps.

**Transferable patterns adopted** (from the research): task-grouped ribbon left-to-right by lifecycle (Revit
tabs); **type-first "Add" flow** (Bonsai `+Add IfcWallType`, Revit Type Selector) — GUID-stable occurrences
inherit from a reusable type; **instance-vs-type split** in Properties (Revit palette); a **Project-Browser
tree** as the model spine (Revit browser / Bonsai IFC tree); a **catalog content panel** with search +
`tag:`/`type:` filters, a Recent bucket, thumbnails and editable tags (Tekla catalog + SketchUp 3D Warehouse);
a **pick content → pick host → auto-build** placement flow (Tekla connections, doors-in-walls); a live
**inference/snap engine + typed dimensions** (SketchUp — builds on the shipped E1 inference); an **Info-Box**
contextual settings strip (ArchiCAD); **UI as a thin wrapper over scriptable GUID-safe recipes** (our RECIPES
≈ `ifcopenshell.api` / Revit API — the same verbs already power the command bar + sandbox); and an
**appendable IFC-as-library** model (Bonsai: any IFC file is a type library; no proprietary content DB).

- **UX-1 — Ribbon consolidation** *(M · high)* — regroup the ~97 tools into a task ribbon that follows the
  modeler's lifecycle, replacing the 7 accreted sections: **Build/Author** (grids·levels → walls·columns·
  slabs·roofs·families·MEP, sloped/mesh/sandbox under an "advanced" fold) · **Annotate** (UX-2) · **Library**
  (UX-3) · **Analyze** (code/EBC · egress · decision-readiness · labour · model-health) · **Coordinate**
  (clash · IDS/BCF · MEP connectivity · phasing) · **Document** (drawings · sheets · schedules · issuances) ·
  **Data** (properties · classifications · exports · connections). Keep the persona-primary/"More tools"
  collapse (already built) but re-key it to these groups. Reuses the `section()` helper in `viewer/app.ts`.
- **UX-2 — Interactive annotation tool** *(L · high · net-new)* — place **`IfcAnnotation`** in the 3D/plan
  view: dimensions, text/leader notes, element-aware tags, symbols, revision clouds — real IFC that feeds the
  drawing generator, closing the loop the baked-SVG path can't.
  - ✅ **UX-2 text notes SHIPPED v0.3.323** — `add_annotation` authors an `IfcAnnotation` + `IfcTextLiteral`
    (Annotation2D rep) as a note/tag/callout at an [E,N,z] point; 🏷 Add-note tool + `addAnnotation` client.
  - ✅ **UX-2 dimensions SHIPPED v0.3.324** — `add_dimension` authors a dimension `IfcAnnotation` (dimension
    line + measured-distance text) between two points; 📐 Dimension tool (two-click) + `addDimension` client.
  - ✅ **UX-2 revision clouds + plan rendering SHIPPED v0.3.327** — `add_revision_cloud` authors a scalloped
    `IfcAnnotation` (+ optional rev tag) around a region (2 corners or ≥3 points); ☁ Revision-cloud tool +
    `addRevisionCloud` client. **`drawing.plan_svg` now renders view-placed annotations** (notes / tags /
    dimensions / revision clouds), closing the author→sheet loop the baked-SVG path couldn't.
  - ✅ **UX-2 element-aware tags SHIPPED v0.3.328** — `add_tag` authors a tag `IfcAnnotation` whose label is
    auto-read from the host element (Name / Pset mark / type / class), placed at its centroid and assigned to
    it (`IfcRelAssignsToProduct`); 🏷 Tag-selected-element tool + `addTag` client. Renders on the plan.
    *Remaining: inference-snapped placement (SketchUp-style snap to endpoints/edges as you draw).*
- **UX-3 — Unified Library palette** *(L · high)* — one browsable **content panel** unifying the W10-1
  type/family system + the CONTENT-1 catalog (logistics/furniture/landscaping) + external IFC/glTF import
  (CONTENT-1-remaining): a **thumbnail grid**, case-insensitive search with `tag:`/`type:`/`discipline:`
  filters, a **Recent** bucket, predefined groups, and **click/drag-to-place**. Hosted content uses a
  **pick-item → pick-host → auto-build** flow (a door picks its wall; a steel connection picks its beams).
  **Appendable IFC libraries** — load types (+ profiles/materials) from any IFC file, per Bonsai. New
  `library` client + a **Library** rail group; extends `familyCatalog` / `contentCatalog` / the type browser.
- **UX-4 — Designer workspace layout** *(M · high)* — assemble the four resources a designer needs into one
  coherent shell: a **Project-Browser spine** (spatial tree + views/sheets/schedules + the type library —
  extends the existing model browser), the docked **Properties** palette with the **instance-vs-type split**
  (extends P6d), the **Library** palette (UX-3), the **task ribbon** (UX-1), plus an **Info-Box** contextual
  strip (active tool/element → its top IFC props inline) and a visible **"Script this" affordance** that opens
  the command bar / sandbox on the same recipe verbs (making the code interface a first-class, discoverable
  resource, not a hidden power-user path). A11y + mobile-viewport pass folded in.

*Sequence: UX-1 (reorg, low-risk, immediate legibility win) → UX-3 (library, reuses catalogs) → UX-2
(annotation, the biggest net-new build) → UX-4 (assemble the shell). Each ships as its own verified release.*

---

## 🔮 Future — 2026-07 research inbox (building codes · Unity/Unreal viz)

Parked as **future** items — not scheduled; picked up after the current Wave 11 tracks. Each notes size +
value; license/legal flags are firm.

### 🏛️ Building-code library (jurisdiction-aware code compliance)
The copyright-safe strategy: **own the rules, facts, and checks; deep-link out for prose; license prose later.**
**GREEN (do freely):** store section numbers/titles/edition years, jurisdiction→adopted-edition **adoption
facts**, numeric thresholds/formulas (facts of law — exactly what `codecheck.py` already encodes), and **our
own paraphrased** rule content. **RED (never):** scraping/redistributing ICC/ASTM verbatim **prose** — the
relevant fair-use rulings are preliminary/unresolved and a commercial SaaS reproducing code text is the exact
market-harm scenario in active litigation.
*(✅ **CODE-1 catalog** (`codes.py`) and **CODE-3 first slice** (edition-aware code-analysis) ship — see the
archive. These extend them:)*
- **CODE-1 follow-ups** — extend the per-state adoption seed from authoritative sources (ICC adoptions DB + DOE energy-code status) and add per-project jurisdiction storage.
- ✅ **CODE-2 (first slice) SHIPPED v0.3.295** — edition-scoped **occupant-load factors** threaded through
  `egress_analysis`/`egress_from_model` (the Business 100→150 gross change at IBC 2018); `code_analysis`
  resolves the jurisdiction's edition and computes the load with it. *Next: externalize the fuller `_RULES`
  threshold table into edition-scoped rows + `resolve_code_context(location, date)` as more deltas are encoded.*
- **CODE-3 (deepen)** — thread the resolved edition into the Track-D detail-rule citations so an exterior window cites the *actually-adopted* section.
- **CODE-4** *(S · med)* — local-amendment overlay model + manual-entry UI (store *our summary* + a link, not a third-party compilation).
- **CODE-5** *(M · med)* — emit `CodeRule`s as **buildingSMART IDS** XML so the same jurisdiction-resolved
  rules validate IFC via any IDS checker (extends our IDS→BCF pipeline).
- **CODE-6** *(L · med, flagged/paid)* — licensed **prose** integration behind a feature flag + cost warning,
  mirroring the paid Autodesk RVT-bridge pattern. Only after CODE-1–3 prove demand — a contract/cost commitment, not code risk.

### 🎮 Unity (Not Unreal?) Engine — one-way viz export only (never core)
Honest verdict: Unreal **breaks offline, doesn't author, and carries royalty/seat licensing** — categorically
incompatible with our permissive/offline core. Datasmith **does** preserve GlobalId + metadata as runtime
tags, but strictly **one-way (viz only)**.
- **VIZ-1** *(S · high · ON-MISSION)* — **glTF/`.glb` (and optional `.udatasmith`) export** from our
  ifcopenshell pipeline, feeding Unreal/Twinmotion **and** better web viewers with zero engine-license
  exposure. **NOTE: largely shipped — a glTF export path already exists; confirm parity / fill gaps.**
- **VIZ-2** *(S/M · on-mission)* — **three.js PBR "presentation mode"** (IBL/HDRI, SSAO/bloom, baked
  lightmaps) — ~90% of "impress the client" value while staying offline + license-free.
- **VIZ-3** *(L · optional/paid/flagged)* — pixel-streamed cinematic mode (cloud-GPU → WebRTC to a browser
  tab, on-demand). License-gated + per-session GPU cost; marketing/high-end only, never the default viewer.
- **VIZ-4** *(L · optional/paid/flagged)* — VR design-review bridge (Datasmith IFC → Unreal, GlobalId tags →
  click-through to our API). An optional interop tier, not core.

### 🚀 Model-authoring & collaboration frontier
The high-value net-new bets validated by the field: an **AI/NL layer over the model** (validating our AI-MCP
track) plus real-time collaboration and live site/proforma loops. Keep our IFC-native + openBIM round-trip
and CD/detailing depth as the moat.
- **AI-MCP / NL authoring** *(M · ★★★★★)* — natural-language authoring over our edit-recipe engine, IFC-native.
  **S1–S3 ship** (see the AI-MCP track above); next is S4/S5 + read tools + an MCP server surface.
- **COLLAB-1** *(L · ★★★★★)* — **real-time multiplayer co-editing** (presence, cursors, live-streamed edits) +
  lightweight **in-model comments** — the biggest gap for a browser-based modeling tool.
- **SITE-1** *(M · ★★★★)* — **auto site context + parcel/zoning-envelope ingestion** for a North-American
  address (parcel geometry, setbacks/height/FAR → buildable envelope); feeds authoring + the code engine.
- **PROFORMA-LIVE** *(M · ★★★★)* — tighten the **model↔proforma live loop**: yields/unit-mix/parking/efficiency
  + cost recompute **inline as you model**, not only in the portal.
- **COST-AGENT** *(M · ★★★★)* — an estimating agent that re-estimates on each geometry change + learns from
  historical cost data (companion to AI-MCP + the estimating→5D track).
- **BOARDS** *(M · ★★★½)* — a "Boards" presentation surface: styled design-option views, shadow studies,
  auto-generated stakeholder decks as first-class artifacts alongside sheets.
- **NL-QA** *(S · ★★★½)* — built-in natural-language QA recipes once AI-MCP matures ("audit issues + suggest
  fixes," "check room accessibility," "normalize inconsistent Psets"). Maps onto code-check + model-hygiene.
- *Validated / overlap (verify, don't rebuild):* bulk IFC Pset editor (⊂ our override layers), manufacturer
  product-configurator → IFC type (⊂ families/types), in-context comments (⊂ BCF — the gap is a lightweight
  authoring-surface comment).

---

## 🚧 Blocked, deferred & non-goals

**④ Blocked upstream — revisit when the dependency lands**
- **IFC5 / IFCX *geometry* write** — the **data** write-path shipped (v0.3.213, ifcJSON/IFCX element+property
  export); only geometry authoring waits on web-ifc / Fragments IFC5 support (still alpha). Track buildingSMART.
- **Native mobile shell** — a **Capacitor wrapper** of the existing offline PWA (needs a macOS/Xcode +
  Android-SDK pipeline separate from the Tauri desktop release). PWA "Add to Home Screen" ships today; the
  native shell is the fast-follow. See [mobile.md](mobile.md).

**⑤ Deferred by decision — integrate, don't build (pursue on customer pull)**
- **Regulated syndication depth** — the licensed stack (KYC/accreditation, transfer-agent recordkeeping,
  Reg-D engine, escrow, the token) stays counsel-gated, licensed-platform work. Our origination-side
  **connector shipped v0.3.213** (`securities_bridge`, ledger sync, never moves money); build deeper only when
  a customer actually raises/syndicates. ⚖️ *Not legal advice; the partner is the licensed entity.* (Full
  decision in the archive — [roadmap-completed.md](roadmap-completed.md).)

**⑥ Intentional non-goals — documented rationale (not gaps)**
- **In-browser IFC authoring** — **REVERSED (2026-07): now a first-class, shipped capability** (from-scratch
  models, GUID-stable draw/edit recipes, drag-to-move, model browser, manage levels, selection sets). Blender/Bonsai
  remains an *optional* advanced/interop editor. **`.mpp` (MS Project) parsing** — proprietary OLE binary, no
  reliable OSS reader; path is *Save As XML/CSV → import*. **Custom Revit plugin** — the certified `revit-ifc`
  exporter already covers it.
- **A4/A5 portal-core split** — the catalog↔nav orchestration is deliberately coupled; further extraction
  trades readability for indirection. The cleanly-separable pieces are already out (Wave 5).
- **Out-of-scope-by-design operations integrations** — live ENERGY STAR / BAS / BMS integrations (flagged
  stubs only), full institutional reporting packs, space/move management (CAFM), 1031 tooling, and a
  JWT-revocation blacklist + Redis-backed presence (known limits, tracked in PRODUCTION_CHECKLIST).

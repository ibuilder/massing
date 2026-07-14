# Roadmap

The single product roadmap. Supporting detail lives in:
[production-readiness.md](production-readiness.md) (security/perf/ops checklist),
[gc-portal.md](gc-portal.md), [gc-tools-audit.md](gc-tools-audit.md),
[ux-findings.md](ux-findings.md).

Three pillars on one IFC-keyed model: **BIM viewer** · **GC portal** (config-driven modules) ·
**developer/finance** (proforma). Shipped continuously — latest release **v0.3.251**.

> **🎯 Active initiative — turn the Model workspace into a true in-browser modeling program** (2026-07,
> direction change). The audit found the Model section was ~80 % viewer/analysis with authoring buried and
> no from-scratch start; the backend authoring engine (~30 GUID-stable recipes) was already real. Reversing
> the old "web = viewer, Blender = editor" non-goal (see [CLAUDE.md](../CLAUDE.md)). Research-informed by
> Revit, BlenderBIM/Bonsai and Bluebeam panel layouts.
>
> **Status: the tracked backlog is cleared** — P1–P6 plus the model browser, manage-levels, selection
> sets, and edit-in-place have all shipped. The Model workspace is now a genuine authoring+coordination
> program (create from scratch → draw/edit by GUID-stable recipe → drag-to-move → clash/coordinate), not a
> viewer with buttons. Remaining is a future enhancement, not a tracked gap: **parametric stretch/resize**
> (drag an element's extents, not just its position).
>
> **Shipped (P1–P5 authoring, P6a–d rail + browser/levels/sets):**
> - **P1** blank model from scratch (`generate_blank_ifc` + `POST …/model/blank`) + first-class Author-mode surfacing (v0.3.231)
> - **P2** removed the redundant legacy place buttons + ~90 lines dead code — Draft panel is the single authoring surface (v0.3.232)
> - **P3** room/space authoring UI (➕ Add rooms/spaces via `add_spaces`; level-add already existed) (v0.3.234)
> - **P4** author-ready **template picker** — blank + office bay / residential floor / warehouse, all editable (v0.3.233)
> - **P6a** cut the four duplicative rail sections (cost/schedule/drawings/energy → deep-links); removed ~700 lines (v0.3.235)
> - **P6b** dedicated **💥 Clash & coordination** rail toggle (federated + single clash, clash list, metrics, promote-to-BCF) (v0.3.236)
> - **P6c** rail re-clustered **Navigate / Author / Coordinate** (v0.3.237)
> - **P6d** docked **📋 Properties** rail panel with a Revit-style Type/Instance identity header — Properties no longer float; they dock in the Author cluster (v0.3.238)
> - **Model browser** — the tree now has a **group-by** switch (level / discipline / IFC class / type-family) + **search** across name·GUID·class·type·discipline, auto-expanding matches (Revit Project Browser parity) (v0.3.239)
> - **Manage levels** — per-storey rename + set-elevation editor (GUID-stable `rename_storey`/`set_storey_elevation` recipes; storey listing now carries GUIDs) (v0.3.240)
> - **Selection sets** — named saved searches you can isolate in one click; persisted per-project (Navisworks/Bluebeam search-set pattern) (v0.3.240)
> - **P5 — edit-in-place** — drag-to-move transform gizmo on the selected element (ghost preview + ΔE/ΔN/ΔZ readout + grid-snap), committed via the GUID-stable `move_element` recipe (v0.3.241)

> **The product feature roadmap, the code-quality/hardening initiative, AND the Wave 8 field-research
> upgrades are all effectively cleared.** Every headline feature theme shipped (generative design + Test
> Fit, developer/finance portal, full acquisition→turnover lifecycle, openBIM standards, AI-over-model,
> discipline spine, operations/resilience, scan-to-BIM + 2D→BIM); the four-domain hardening audit shipped
> as Waves 1–7 (observability, perf/scale, type boundary, modularization, reproducibility/ops, strictness
> + Docker); and **Wave 8** (2026 field scan) shipped **all seven tracks** — clash-coordination
> intelligence, model→field layout, load takedown, model hygiene, the CEP generator, Gaussian-splat
> reality capture, schedule-linked verified-as-built progress (v0.3.203–210), and ⑦'s origination-side
> **syndication connector** (v0.3.213). Since then: the **IFC5/IFCX data write-path** (v0.3.213) and an
> **in-browser E57 reader** (v0.3.214) closed the last two upstream-tagged items at the data layer. **The
> complete, re-ranked list of everything still open — swept up from every archive/parking-lot section — is
> the single "What's left" section below.** Everything under "Shipped archive" is historical reference only.

---

> **Shipped work lives in [roadmap-completed.md](roadmap-completed.md)** — the full done-archive (every wave, track, and release, A–D + L parking-lots, lifecycle/standards/discipline-spine/
> resourcing). This file now holds only the banner above and the open backlog below, so *what's left* is never buried under *what's done*.

## ⏳ What's left — the whole open roadmap, prioritized

> **✅ The v0.3.x actionable backlog is CLEARED (2026-07).** Buckets ① (generative/analysis depth) and ②
> (UX/perf) are fully shipped; ③ (interop) is done or evaluated-and-deferred with criteria (glTF import +
> pyRevit publish already ship; RVT bridge hardened v0.3.243; the L1 converter and L4 FreeCAD spikes were
> evaluated → deferred, see below). Of the original open buckets, only ④ upstream-blocked, ⑤
> deferred-by-decision, and ⑥ documented non-goals remain. **New actionable work now lives in the Wave 9
> research scan directly below** — vetted net-new upgrades from a 2026-07 field/product scan.

## 🔬 Wave 9 — 2026-07 research scan (openBIM depth · generative · AI)

Sourced from a 14-image AEC field scan + 14 product/repo teardowns (IFC5, ifcmapping, Kamai, Bentley
SYNCHRO, SPARC-FP, AECFoundry, five GitHub repos), each vetted against the mission **and the existing
code**. Most scanned content was already covered — LOD (we have `/lod/assessment`+matrix), drawing types
IFC/Shop/As-Built (drawings + submittals + turnover), Revit Category→Family→Type→Instance (our
type/instance model), PM/CM stacks + cost-management (GC portal + proforma/EVM), ITP/NCR (the `inspection`
+ `ncr` modules), a description→code-sections assistant (`codecheck.py`), and manual calibrated PDF takeoff.
The genuinely **net-new, permissive-license, buildable** items, ranked:

- ~~**W9-1 — Property mapping / normalization engine**~~ — ✅ **SHIPPED (v0.3.245)**: the **transform** verb
  between IDS-validate and COBie-export. `propmap.py` (`detect` present psets/props → `plan` dry-run → `apply`)
  + a GUID-stable `map_properties` recipe (move/copy semantics, type coercion) + `/propmap/detect` + `/propmap/plan`
  + a **🔧 Normalize properties** tool + `test_propmap.py`. Verified live remapping 12 walls' non-standard
  `ThicknessMm` onto `Qto_WallBaseQuantities.Width`. (ifcmapping.com)
- ~~**W9-2 — Code-compliance depth: occupancy load + egress capacity**~~ — ✅ **SHIPPED (v0.3.246)**:
  computed **occupant load** (IBC 1004.5 factors by occupancy) per space + building total, **egress width**
  required (load × 0.15 in) vs provided egress-door width (adequate/short), **32 in min door** (IBC 1010.1.1,
  click-to-isolate), and **two-exits-when-load>49** (IBC 1006.2), all cited. `codecheck.egress_analysis` +
  `egress_from_model` + `/codecheck/egress` + a **🏛 Occupancy & egress** tool + tests. Pre-check/assist,
  not certified. Verified live (40-space model → 344 occupants, 51.6 in required). **BCF round-trip
  SHIPPED (W9-2b, v0.3.251)**: `POST /codecheck/egress/bcf` promotes findings (below-min doors, egress
  shortfall, two-exit spaces) to anchored `codecheck` BCF topics, idempotent, visible in the Issues panel.
  *Fire-separation between occupancies still deferred (needs space-boundary geometry).* (SPARC-FP; UpCodes/Solibri)
- ~~**W9-3 — IFC5 composition / property-override layers**~~ — ✅ **SHIPPED (v0.3.247)**: USD-like
  non-destructive overlay layers (base → strongest) composing over the model — strongest enabled layer wins,
  conflicts flagged with provenance + both values, **bake** flattens to a GUID-stable IFC version. `layers.py`
  + `Project.prop_layers` + `/layers` (GET/PUT) + `/layers/resolve` + `/layers/bake` + `apply_layers` recipe
  + a **🧬 Property layers** tool + `test_layers.py`. Verified live (two-layer FireRating conflict → "2HR"
  baked). (biblus IFC5)
- **W9-4 — Semantic knowledge-graph over model + specs + code** *(L · staged)* — ✅ **v1 SHIPPED (v0.3.248)**:
  a typed graph from the model's IFC relationships (contained_in / aggregates / bounds / has_opening / fills /
  serves) with **multi-hop, cited neighbor queries** (`graph.py` + `/graph` + `/graph/neighbors` + a
  **🕸 Related elements** tool + `test_graph.py`; 117 nodes/116 edges live, a wall reaches 38 within 2 hops).
  *Still open (the harder half): ingesting **specs / drawings / code documents** as graph nodes + an NL→graph
  query with cited sources — the piece that makes W9-2's code-checks explainable.* (AECFoundry; ASK-BIM)
  *(Follow-up spec: ingest spec/code clauses as graph nodes + derived links (space → required rating) + an
  NL→graph query returning cited answers with GUID + spec page + code section — the explainability substrate
  under W9-2. AECFoundry; ASK-BIM / Graph-RAG-over-IFC.)*
- **W9-5 — Site logistics & equipment-motion on the 4D slider** *(L; M first step)* — ✅ **M FIRST STEP
  SHIPPED (v0.3.250)**: temporary resources (crane w/ reach ring, hoist, laydown, gate, fence, haul route,
  trailer, parking) as first-class objects in project coords with a **schedule window**, rendered as 3D
  glyphs that **time-phase** by date. `logistics.py` (`state_at`/`summary`) + `Project.site_logistics` +
  `/logistics` (GET/PUT) + `/logistics/state` + a `LogisticsOverlay` + a **🏗 Site logistics** tool +
  `test_logistics.py`. Verified live (3 resources time-phased). **Still open (the L part):** smooth **motion
  along paths** as the slider advances + swept crane-reach clash (moving-equipment conflicts over time).
  (Bentley SYNCHRO — clean-room parity)
- **W9-6 — Generative fit-out: furnish + office space-planning** *(S + M)* — **(a) ✅ SHIPPED (v0.3.249)**:
  **auto-furnish** — grids real `IfcFurnishingElement` (desk/table/bed/sofa templates) into every
  `IfcSpace`'s footprint with aisle clearances + storey containment, feeding QTO/BOM. `furnish_spaces`
  recipe + a **🪑 Furnish spaces** tool + `test_fitout.py`; verified live (blank → 8 rooms → 432 desks).
  **(b) still open**: a procedural **office space-planning** generator — headcount program (desks / offices /
  meeting rooms + circulation %) + floorplate → `IfcSpace` zones + furniture + auto BOM (M). (AutoCAD-automation
  repos — algorithmic idea only)

**Optional / lower priority:**
- **W9-7 — AI 2D-PDF auto-takeoff** *(M · optional connector)* — we already ship **manual** calibrated PDF
  takeoff (measure / area / count); AI auto-extraction of quantities from a PDF set (Kamai-style) is deeper
  but proprietary/paid → a flagged bridge (like the APS RVT path), never core. (kamai.io)
- **W9-8 — NL imperative authoring** *(S · parity)* — "add a 2-hr fire wall between the corridor and the
  stair" → a proposed edit recipe → confirm → apply, layered on the existing recipe engine + "ask the model"
  AI. (Synaps)

**Evaluated → skip (no merit / off-mission):** FastPlan (generic LLM plan PDF), Datum/Prodatum (small-firm
site SaaS, below us), Airi Lab (diffusion rendering — off-mission + offline/licensing conflict), MECIDTOOLS
+ scadlab (AutoCAD/OpenSCAD scripting we already exceed), Synaps-as-product (2D CAD, behind us on openBIM).

**Everything not shipped, consolidated in one place — this is the single, authoritative backlog.** Every
historically-deferred item from every archive/parking-lot section in
[roadmap-completed.md](roadmap-completed.md) (A Test Fit · U underwriting · R built-world · M
materials/rendering · L interop · D platform, plus each "*Next:*" sub-note) has been swept up and re-ranked
here, so you never have to read the archive to know what's open. The product features, the
code-quality/hardening initiative (Waves 1–7), and Wave 8 (all seven tracks — ⑦'s connector shipped
v0.3.213) are done. Everything remaining is **incremental depth, spikes, upstream-blocked work, or
documented non-goals — nothing is blocking.** Ordered most-actionable first; pull an item up on real
customer need. Each line ends with its archive source in parentheses for the full original spec.

**① Generative-design & analysis depth — buildable now, pull up on customer need** *(the deepest, highest-value bucket)*
- **Test Fit yield optimization** *(§A)* — ✅ **DONE (v0.3.215)**: daylight-limited plate depth is now an
  **optimize dimension** (`optimize(depths=…)` / `targets.sweep_depth`) returning a `depth_curve` +
  `best_depth_m`, and a new **`core_efficiency`** metric scores the daylight-dark core; a "sweep plate
  depth" toggle charts it in the Test Fit panel. **Polygon-offset footprint + parcel parking now DONE
  (v0.3.221)**: inward setback offset (`offset_polygon`) gives the buildable footprint, and
  `pack_parking()` places surface stalls + drive aisles in the **real parcel remainder** (inside the
  polygon, clear of the building box) so parking supply is parcel-bound. Full §A Test Fit bucket cleared.
- **Structural generative depth** *(§R3/§A)* — ✅ **DONE (v0.3.220)**: the generated frame now follows the
  load path floor-by-floor. `structure.column_schedule()` tapers columns with **√(floors carried)** (base
  widest → top narrowest, floored 400 mm, 50 mm zones) and `structure.lateral_core()` sizes a central
  RC core (~20 % of plate, walls thickening 250→900 mm with height) for core-lateral systems;
  `generate_ifc` extrudes each storey's columns at its own section + the core walls as real shear walls,
  and the proforma summary shows the taper + core.
- **Underwriting realism, deeper** *(§U)* — ✅ **FULLY DONE**. Exit-cap-vs-comps guardrails (v0.3.216);
  **specialty P&L + ramp** + specialty-only IRR + **blended vs real-estate-only IRR** (v0.3.222,
  `specialty.proforma()`/`blended_irr()`); **Monte-Carlo the specialty risk discount** → distribution of
  blended IRR (v0.3.223, `specialty.monte_carlo()` + "Risk sim" panel button). The whole §U depth bucket
  is cleared.
- **Lean / takt production analytics** *(§R2/§R4)* — ✅ **DONE (v0.3.224)**: `takt.progress()` +
  `takt_svg` **actuals overlay** measure actual-vs-takt (floor variance, achieved vs planned floors/week,
  ahead/behind); project `…/schedule/takt/progress` derives per-trade completion from `schedule_activity`
  and **bundles PPC**; a "Takt — actual vs plan" Schedule-panel card shows the overlaid LOB + variance +
  PPC. Planned LOB + JIT already shipped.
- **Rendering & computational depth** *(§M)* — ✅ **DONE**. Material editor + per-project palette
  (v0.3.225, `materials.merge_palette()` + `…/materials/palette` GET/PUT + `…/materials/apply` + 🎨 panel);
  **module-relations graph** (v0.3.226, `module_graph.build()` + `GET /modules/graph` + 🕸 SVG panel — nodes
  = modules, edges = reference/rollup links, sized by in-degree). *Only heavier GPU work remains as a
  documented non-goal:* real-time GI / baked AO / exterior HDRI skies (out of scope for a web viewer).
- **Developer deliverable** *(§B6)* — ✅ **DONE (v0.3.227)**: the investment **pitch deck**
  (`/investment-deck.pdf`) was already a landscape slide deck with market + timeline + photos; expanded to
  **9 slides** (added Executive summary, Capital stack, Business plan & value creation) toward the 10–20
  slide investor-deck target. Memo + deck both ship from live project data.

**② UX / performance / productivity (Part C — approve item-by-item)**
- **Role landing dashboards** — ✅ **DONE (v0.3.228)**: all three non-GC personas now have a role-tailored
  home — Design (model-health / phase-progress), Developer (RE register + deal returns), and now **Finance**
  (returns + capital stack + investor docs, a new Home tab in the finance workspace). The GC keeps its
  on-schedule/on-budget PX dashboard.
- **Nav density** — ✅ **DONE**: per-stage collapse memory (v0.3.230) + a **command-center density toggle**
  (v0.3.242, ⊞ Comfortable / ⊟ Compact, persisted) that tightens the multi-card home dashboards. Bucket cleared.
- **A11y** — keep verifying new tabs/dashboards (roles, focus order, contrast) as workspaces grow.
  *(v0.3.229 audited this cycle's new panels — SVG accessible names, labeled form controls, `scope` headers,
  a reusable `.sr-only`; ongoing as more panels ship.)*
- *(⌘K, saved-views-per-role, cross-workspace deep-links both directions, and the `portal.ts` per-domain
  split all shipped — see §Part C archive.)*

**③ Interop / library evaluations — spikes evaluated, deferred with re-trigger criteria** *(§L)*
- ~~**L1 — `@ifc-lite/geometry` server-side converter spike**~~ — **EVALUATED → DEFER (2026-07).** Benchmarked
  the *current* path first: `services/converter/src/ifcToFrag.mjs` (That Open Fragments, Node) converts a
  **1.6 MB IFC → .frag in ~1.1 s** — no bottleneck at the model scale we see (largest fixture 1.6 MB). A
  claimed ~5× converter only pays off on very large models, and adopting it means vetting + carrying a new
  MPL-2.0 dependency (supply-chain cost) for no measured benefit. **Re-trigger:** a customer with genuinely
  large models (≳50 MB IFC) where conversion latency becomes painful. *Do not swap the browser engine.*
- ~~**L4 — FreeCAD headless server engine**~~ — **EVALUATED → DEFER (2026-07).** Parametric family generation
  and 2D-drawing export are *already covered* by `ifcopenshell` (the ~30 GUID-stable authoring recipes) +
  `drawings.py` (plans/sections/elevations) + `sheetgen.py` (per-discipline sheet sets), so a FreeCAD engine
  would be largely redundant while adding a heavy LGPL binary to the server image. **Re-trigger:** a concrete
  parametric operation `ifcopenshell` genuinely cannot express.
- ~~**glTF import overlay**~~ — ✅ **already ships**: `referenceLoader.ts` parses `.gltf`/`.glb` (GLTFLoader)
  into a view-only reference overlay via **Open ▾ → Open mesh / point cloud**, alongside OBJ/STL/PLY/PCD/LAS.
- ~~**pyRevit "export IFC → upload to Massing" macro**~~ — ✅ **already ships**: the
  `integrations/pyrevit/Massing.extension` **"Publish to Massing"** button exports the active Revit doc to IFC
  (built-in exporter), uploads it, runs the server-side Fragments conversion, waits, and offers to open it —
  the one-click export→upload flow, no APS bridge. (Plus Open-in-Massing, BCF issue sync, Settings.)
- ~~**RVT→IFC (APS) bridge polish**~~ — ✅ **hardened (v0.3.243)**: the paid Autodesk **Design Automation**
  path stays a properly-gated stub (it can't be implemented generically — the WorkItem arguments depend on
  the operator's provisioned Activity's parameter names, so it raises a clear "provision your Activity"
  error rather than fake IFC). Added **input validation** (reject non-`.rvt` / empty *before* the cost gate)
  and **`test_aps.py`** locking the gate order — 501 (off) → 400 (wrong type) → 402 (unconfirmed cost) →
  400 (empty) → 502 (stub activity). The free path (export IFC from Revit, or the pyRevit "Publish" button)
  remains the recommendation.

**④ Blocked upstream — revisit when the dependency lands**
- **IFC5 / IFCX *geometry* write** — the **data** write-path shipped (v0.3.213, ifcJSON/IFCX element+
  property export); only geometry authoring waits on web-ifc / Fragments IFC5 support (still alpha —
  §L "IFC5/IFCX"). Track buildingSMART; `@ifc-lite/parser` (L2) is the adopt-candidate once it stabilises.
- **Native mobile shell** — a **Capacitor wrapper** of the existing offline PWA (needs a macOS/Xcode +
  Android-SDK pipeline separate from the Tauri desktop release). PWA "Add to Home Screen" ships today;
  the native shell is the fast-follow. See [mobile.md](mobile.md), §D.

**⑤ Deferred by decision — integrate, don't build (pursue on customer pull)**
- **Wave 8 ⑦ regulated syndication depth** — the licensed stack (KYC/accreditation, transfer-agent
  recordkeeping, Reg-D engine, escrow, the token) stays counsel-gated, licensed-platform work. Our
  origination-side **connector shipped v0.3.213** (`securities_bridge`, ledger sync, never moves money);
  build deeper only when a customer actually raises/syndicates. ⚖️ *Not legal advice; the partner is the
  licensed entity.* (Full decision in the Wave 8 §⑦ archive — [roadmap-completed.md](roadmap-completed.md).)

**⑥ Intentional non-goals — documented rationale (not gaps)**
- ~~**In-browser IFC authoring**~~ — **REVERSED (2026-07): now a first-class, shipped capability.** The web
  app is a genuine authoring tool — from-scratch models, GUID-stable draw/edit recipes, drag-to-move
  edit-in-place, model browser, manage levels, selection sets (see the initiative banner above). Blender/Bonsai
  remains an *optional* advanced/interop editor, no longer the required one. **`.mpp` (MS Project) parsing** —
  proprietary OLE binary, no reliable OSS reader; path is *Save As XML/CSV → import* (§L). **Custom
  Revit/Navisworks plugin** — Autodesk's certified `revit-ifc` already covers it (§L).
- **A4/A5 portal-core split** — the catalog↔nav orchestration is deliberately coupled (favorites ↔ nav ↔
  persona events ↔ in-place DOM refresh); further extraction trades readability for indirection. The
  cleanly-separable pieces are already out (Wave 5).
- **Out-of-scope-by-design operations integrations** — live ENERGY STAR / BAS / BMS integrations (flagged
  stubs only), full institutional reporting packs, space/move management (CAFM), 1031 tooling, and a
  JWT-revocation blacklist + Redis-backed presence (known limits, tracked in PRODUCTION_CHECKLIST).

**Recently cleared (were on this list):** Finance-persona command-center home (v0.3.228) · investor
pitch-deck expansion — exec summary + capital stack + business plan (v0.3.227) · module-relations graph view (v0.3.226) · per-project material editor + palette
apply/republish (v0.3.225) ·
actual-vs-takt production tracking + LOB actuals overlay + PPC bundle (v0.3.224) · Monte-Carlo the specialty risk discount → blended-IRR distribution (v0.3.223) ·
specialty multi-year P&L + ramp + blended-vs-RE IRR (v0.3.222) ·
parcel-aware surface parking placement (v0.3.221) · structural generative depth — per-floor column taper +
lateral-core geometry (v0.3.220) · Test Fit plate-depth optimize + `core_efficiency` (v0.3.215) ·
underwriting exit-cap-vs-comps guardrails (v0.3.216) · capital-markets syndication connector + IFC5/IFCX data write path
(v0.3.213) · in-browser E57 reality-capture reader (v0.3.214) · cross-workspace deep-links both directions
(v0.3.211–212) · FF&E classification (v0.3.212) · B2 hashed `pip-compile` lockfiles (v0.3.198) · accounting
interop — approval-gated journal export (v0.3.199) + model-quantity WIP % by GlobalId (v0.3.200) · the whole
Wave 8 build ①–⑥ + ③b (v0.3.203–210).

---

## 🔐 Sign-in & first-run onboarding (2026-07 research)

**Goal:** make social sign-in the prominent default and sequence it into the tutorial — *without* a hard
gate (the app runs free/offline without an account; a signup wall before the "aha" moment craters
top-of-funnel for open/self-hostable tools). We already have Google + Microsoft OAuth (config-gated, shown
above the password form), MFA, SSO/SAML/SCIM, and a first-run welcome modal + ≤5-step tour. This is
**prominence + flow**, not new auth. Research-cited (Corbado social-login data, reverse-trial/value-first
studies, Chameleon onboarding benchmarks, WorkOS on the Apple rule). Files:
`apps/web/src/ui/onboarding.ts`, `apps/web/src/account/accountUI.ts`.

**First slice (one sprint — the core ask):**
- **B1 — optional sign-in as the welcome modal's first panel** *(M)* — a headline + one prominent
  **Continue with Microsoft** + **Continue with Google** (only the providers the server has configured, via
  `authProviders()`), a quiet "More options," and a clearly-visible **"Explore without an account →"** that
  drops to the existing quick-start cards. Prominent, never a wall.
- **B2 — sign-in → tour** *(S)* — after a successful sign-in *or* "Explore without an account", auto-launch
  the existing tour and `markOnboarded()` once. Implements "prompt socials on startup → tutorial pops up."
- **A1 — keep Google + Microsoft as co-equal visible defaults** *(S)* — Microsoft is the B2B/M365-Azure AD
  pick our audience (GCs, developers, A/E) actually lives in; zero new backend.
- **A2 — collapse everything else behind "More sign-in options"** *(S)* — password, org SSO/SAML, Procore —
  kills the "NASCAR" six-logo decision paralysis at the highest-intent moment.
- **C1 — reorder the sign-in modal to lead with one big provider button + "More options"** *(S)* — match the
  first-run panel for consistency.

**Fast-follow:**
- **B3 — role self-selection right after sign-in** *(M)* — reuse the existing role picker as an inline step,
  then gear the tools rail / tour to that role (role personalization is ~+40% retention; we already have the
  role model, just surface it earlier).
- **B4 — keep the tour ≤5 steps** *(S)* — repoint the old final "sign in" step now that sign-in moves to the
  front (completion drops >50% past 5 steps).
- **C2 — value-moment prompt** *(S)* — higher-contrast "Sign in" toolbar button + a "Sign in to save your
  work" affordance once a guest has created/modified something (ask after a win, not a wall).

**Deferred with explicit triggers:**
- **A3 — Sign in with Apple** *(M)* — web-only today means Apple's "must also offer Sign in with Apple" rule
  does **not** apply (it binds only a native App Store app that offers another social login); ~5% consumer
  coverage + privacy relay. Build only alongside a native iOS wrapper; adds the $99/yr Apple Developer
  Program + a private-relay email path.
- **A4 — skip Facebook (net-negative, consumer-coded, high in-app-browser failure) and GitHub (wrong
  audience); LinkedIn only if analytics show demand.**
- **B5 — persistent quick-start checklist** *(L)* — checklist-launched tours convert best (~67%); a home for
  secondary discovery, deferred past the first slice.

*Privacy/mission guardrails: keep the guest/offline path fully functional; no telemetry/personal data before
consent; SSO buttons stay config-gated so self-hosters don't advertise providers they haven't set up.*

## 🏛️ Wave 10 — Full IFC authoring suite (Revit / Bonsai parity) — 2026-07 research

**Goal:** grow the ~30-recipe engine into a genuine model-authoring suite (families, types, parametric
generators, MEP systems, annotation, schedules, groups/phasing) — Revit + BlenderBIM/Bonsai capability in
the browser, IFC-native.

**The framing insight that drives the plan:** IFC has **no native parametric/constraint model** — it stores
baked geometry + parameters-as-properties. So a "parametric family" must be **our generator** that (a) emits
a baked `IfcRepresentationMap` and (b) stores its driving params as an `IfcPropertySet` on the
`IfcTypeObject`; editing a param re-runs the generator and swaps the map. **This is exactly how Bonsai works
— and Bonsai is built on the same ifcopenshell core we already use, so its techniques port straight to our
Python recipes (no Blender dep).** We already have the load-bearing spine: `families.py` builds
`IfcTypeProduct` + `RepresentationMap` and `edit.py::place_type` shares mapped geometry via `type.assign_type`
— it's just box-only + parameter-less today. Wave 10 **deepens this spine**, it doesn't rebuild it. Nearly
all of it is **pure ifcopenshell** (no new deps, no license risk).

Ordering principle: foundations that multiply everything first → breadth → the genuinely-hard constraint
solver last.

- **W10-1 — Real type/family system (foundation)** ✅ SHIPPED v0.3.252 *(M · pure ifcopenshell)* — promoted the
  box-only type path into a first-class family system: `create_type` (custom class + sized box + PredefinedType
  + type Psets, idempotent), `edit_type_params` (dims edit mutates the shared box solid **in place** → flows to
  every placed occurrence at once, GUID-stable), `assign_material_set` (`IfcMaterialLayerSet`, replace-on-reassign),
  `type_detail` inspector (dims / Psets / materials / occurrences) + enriched `/types` (occurrence counts) +
  `GET /types/{guid}` + a **🧱 Family types** browser/inspector in the viewer. Shared box-representation builder
  refactored out of `ensure_type`. `test_types.py` proves in-place propagation via the shared `RepresentationMap`.
  *Next: multiple representations + `IfcMaterialProfileSet` for beams/columns (folds into W10-2).*
- **W10-2 — Parametric family generators (code-defined)** *(L · pure ifcopenshell; optional build123d/OCP)* —
  each catalog entry becomes a **generator** with typed params + optional formulas; a param change re-runs it
  and swaps the map; params persist as a type Pset. Ship a **profile library** (I/L/T/U/C/rect/circle) +
  swept/boolean primitives so doors/windows/columns/casework are *generated*, not boxes. Freeform families via
  an optional **build123d (Apache-2.0) / OCP (LGPL)** track bridged through `ifcopenshell.geom` BRep/tessellation.
  IFC: profile defs, `IfcExtrudedAreaSolid`, `IfcBooleanClippingResult`. *Depends on W10-1.*
- **W10-3 — Groups, assemblies, arrays & nested families** ✅ SHIPPED v0.3.253 *(S · pure ifcopenshell)* —
  `create_group`/`ungroup` (`IfcGroup` named set, re-name adds, members keep containment), `create_assembly`
  (`IfcElementAssembly` aggregating parts, spatially contained), `array_element` (rectangular nx×ny parametric
  array; copies detached from the source's inherited group/aggregate so they're independent). `groups.py` +
  recipes + `GET /groups` & `/groups/{guid}` inspectors + a **🧩 Groups & arrays** viewer tool (build from
  saved selection sets, isolate members on click). `test_groups.py` green. *Nested/shared sub-components fold
  into W10-2 (a generator can emit an assembly).*
- **W10-4 — MEP systems, connectivity & sizing depth** *(M · pure ifcopenshell)* — upgrade current
  segments/ports into fully-connected logical systems with port-to-port connectivity + flow/sizing psets +
  a system browser + connectivity validation. IFC: `IfcDistributionSystem` via `IfcRelAssignsToGroup`,
  `IfcRelConnectsPorts`, `IfcRelNests`, flow/sizing Psets. *Extends existing MEP recipes.*
- **W10-5 — Annotation & tagging layer** *(M · pure ifcopenshell · UI-heavy)* — 2D annotation on the existing
  plan/section/elevation views: tags (auto-pull type/mark), dimensions, text, detail items, keynotes (reuse
  classification). IFC: `IfcAnnotation` (+`IfcTextLiteralWithExtent`, `IfcAnnotationFillArea`) in an
  `Annotation`/`Plan` context; keynotes via `IfcRelAssociatesClassification`. *Depends on the drawing engine.*
- **W10-6 — Schedules & quantity takeoff** *(M · pure ifcopenshell)* — attach quantity sets to elements;
  compute schedule / keynote-legend views (schedules are computed, not stored) into the existing export
  pipeline. IFC: `IfcElementQuantity` (`IfcQuantityLength/Area/Volume/Count`). *Depends on W10-1.*
- **W10-7 — Structural analytical model** *(L · pure ifcopenshell · net-new domain)* — an analytical model
  alongside the physical: analytical members/nodes, supports, load cases. IFC: `IfcStructuralAnalysisModel`,
  `IfcStructuralCurveMember`/`SurfaceMember`, `IfcStructuralPointConnection`, `IfcStructuralLoadCase`,
  `IfcRelConnectsStructuralActivity`. *Depends on the physical structural elements (exist).*
- **W10-8 — Phasing & design options** ✅ Phasing SHIPPED v0.3.254 *(S/M · pure ifcopenshell)* — `set_phase`
  tags elements **new/existing/demolish/temporary** via `Massing_Phasing.Status` (the standard status coding,
  so it colours/filters/round-trips), `phase_summary` counts by status. **🕐 Phasing** viewer tool (tag the
  selection or a saved selection set, phase overview, isolate-a-phase-in-3D) + `set_phase` recipe + `GET
  /phasing`. `test_phasing.py` green. *Design options already covered by the W9-3 IFC5 property-override
  layers; tying phase to the 4D timeline slider is the remaining sub-item.*
- **W10-9 — Parametric constraints & dimensional locks (the hard one)** *(L · higher-risk · needs an LGPL
  solver)* — geometric constraint solving (locks, equality, alignment) has **no IFC representation**; store
  constraints in a sidecar model, solve, bake to IFC. Start with 1D/alignment locks; a full 2D sketch solver
  is a research effort, not a sprint. **License:** use FreeCAD's **planegcs (LGPL, extractable)**; *avoid
  python-solvespace (GPL) and OpenSCAD (GPL)*. *Depends on W10-2 — arguably diminishing returns for full parity.*

**License map:** W10-1/3/4/6/8 are pure ifcopenshell (no deps, no risk); W10-2 freeform sub-track uses
build123d/CadQuery (Apache-2.0) on OCP/OCCT (LGPL); W10-9 needs planegcs (LGPL). **Avoid:** OpenSCAD (GPL),
python-solvespace (GPL), FreeCAD-as-app (GPL bits). **Skip entirely:** worksharing/worksets — no IFC concept
and irrelevant to a server-recipe authoring model. **Honest hard-vs-easy:** the quick wins deepen APIs we
already call; the genuine effort is the *family-editor UX* (live parametric feedback in the web viewer) and
the W10-9 constraint solver.

## 🏗️ Wave 11 — The Master Builder: LOD-400/500 authoring + code-compliant construction sets (2026-07 research)

**Goal:** one browser tool that replaces Revit + Navisworks + Autodesk APS + Bonsai — model **one
GUID-stable parametric model** whose detail dials from **schematic (LOD 100/200) → design development
(300) → construction (LOD 400) → as-built (500)**, and from that single model generate a **full,
municipality-approvable construction document set** (plans/sections/elevations/details/schedules + project
manual) carrying **IBC details, code references, and installation instructions** — with a barrier-to-entry
low enough that any builder becomes a master builder. Approved by user 2026-07 (all tracks); this Wave
**unifies and supersedes** the Wave 10 items where they converge (W10-2 generators ⊂ B, W10-5 annotation ⊂ C,
W10-6 schedules ⊂ C).

**The reframe that reshapes everything (BIMForum LOD spec):** you don't "model to LOD 500." LOD 500 is a
*field-verified as-built* **data/reliability** attribute — BIMForum defines **no** geometric requirement for
it. So the real target is **LOD 400 geometry + LOD 500 verified-as-built data + provenance**, which plays
straight to our architecture (geometry streams as `.frag`, data comes from the API). We can credibly support
"LOD 500" as a verification/COBie/provenance layer well before every fabrication bolt is modeled.

**The one architectural spine that unifies all tracks** — *multi-representation, view-keyed elements.* A
single `IfcProduct` (stable GlobalId across the whole ladder) carries **several `IfcShapeRepresentation`s**
under **`IfcGeometricRepresentationSubContext`** tagged by `RepresentationIdentifier` (`Body`/`Box`/`Axis`/
`FootPrint`/`Annotation`) + **`TargetView`** (MODEL/PLAN/SECTION/ELEVATION_VIEW) + **`TargetScale`**. This one
mechanism does three jobs at once: (1) **LOD dialing** — refine `Body` + swap placeholder types for real
types + add Psets, in place, GUID-stable; (2) **drawing generation** — the generator selects each element's
representation by `(identifier, target_view, target_scale)`, falling back to a live `ifcopenshell.geom` HLR
cut of `Body`; (3) **coarse↔fine display** — `Box`/`Axis` for schematic, layered `Body` poché for CDs. Build
this spine first; every track hangs off it.

**Unified foundation & tracks** (sequenced; the spine + guardrails lead):

- **F0 — The representation/context spine + LOD state** ✅ SHIPPED v0.3.256 *(M · pure ifcopenshell)* —
  `ensure_contexts` finds-or-creates the Model+Plan roots + Body/Axis/Box/FootPrint/Annotation subcontexts
  (by `TargetView`), idempotent; `set_lod`/`lod_summary` carry an element **LOD stage** (`Pset_MassingLOD.Stage`
  100→500, advances in place, GUID-stable) + a 📶 Level of Development viewer tool + `GET /lod`.
  `representations.py`, `test_representations.py` green. *Still to do in F0b: derive `Box`/`Axis`/`FootPrint`
  geometry on demand from `Body` (consumed by the C drawing generator).*
- **A · Open-ended authoring (the moat)** *(L)* — A1 **sandboxed `execute_ifc_code` recipe** (AST-whitelisted,
  ifcopenshell-only, no fs/Blender — turns our fixed recipe registry into unbounded authoring); A2 **RAG index**
  over ifcopenshell/IFC docs to ground code-gen; A3 **AI emits *recipes*** (parametric, GUID-stable, editable —
  the property Zoo/Text-to-CAD lack); A4 LLM **scene-digest** tool over the semantic graph. *ifc-bonsai-mcp
  (MIT) is the design reference; ifcopenshell is LGPL.*
- **B · Geometry depth → LOD 350/400** *(L, multi-sub-wave)* — B1 void+fill (already uses
  `feature.add_feature`/`add_filling` ✓); **B2 ✅ SHIPPED v0.3.257** — parametric door/window generators
  (`geometry.add_door/window_representation`: real lining/frame/panels, `operation` type, wall-sized lining,
  box-proxy fallback; `test_openings.py`); B3 wall **Axis rep + clippings/
  booleans** (sloped tops, gable walls); B4 **procedural-mesh escape hatch** (`add_mesh_representation` →
  IfcTriangulatedFaceSet for anything parametric recipes can't); B5 **connections/fasteners/hangers** +
  `IfcRelConnects*` (LOD 350 coordination); B6 **domain catalogs** in value order — steel connections → rebar
  (swept-disk along a directrix) → MEP connected systems + fittings → curtain-wall systems.
- **C · Construction-document generation (the deliverable)** *(L)* — **C1 ✅ SHIPPED v0.3.260** — plan-drawing
  generator (`drawing.py::plan_svg`): derives footprints **directly from authored extruded-profile geometry**
  (no OCC — our geometry path is web-ifc, ifcopenshell's OCC engine produces no mesh here), class-styled poché
  SVG scaled to paper mm, storey-scoped; 🖨 Generate plan tool + `GET /drawings/plan.svg`; `test_drawing.py`.
  *Next C-slices: sections/elevations, dimensions, keynotes from Track-D codes, per-GUID cache.* Original plan
  eyed `ifcopenshell.geom.serializers.svg` (OCC HLR) but that engine is inert in our build; C2 **parametric IFC dimensions** (geometry-anchored, the merged IfcOpenShell PR #8083 pattern:
  `IfcAnnotation` + `IfcRelAssignsToProduct` + face/layer/edge/vertex anchor JSON; regenerate on move) + smart
  tags via `drawing.assign_product`; C3 **sheets & titleblocks** (`IfcDocumentInformation` Scope="SHEET",
  token-substituted SVG titleblock, viewport placement) → **SVG→PDF/DXF** (permissive libs only, no AGPL);
  C4 **computed schedules** (door/window/room/finish/quantity from the model → table blocks on sheets);
  C5 **drawn detail follows LOD** (representation selection + stylesheet + `IfcMaterialLayerSet` poché +
  annotation density → schematic single-line ↔ CD layered poché); C6 reference-line datums (`IfcReferent`/
  `IfcVirtualElement`). *Views/annotations/sheets stored IN the IFC so they round-trip; render cache in MinIO
  keyed by GUID+geom-hash.*
- **D · Code + spec + detail intelligence (IBC / MasterFormat)** *(L)* — D1 **code-analysis sheet generator**
  (occupancy Ch.3, construction type/ratings Ch.6/Table 601, allowable area Table 506.2, occupant load Table
  1004.5, egress Ch.10 — mostly model data we already compute in W9-2); D2 **routed egress/life-safety plans**
  (path-trace over the W9-4 semantic graph, not just tabulated); **D3 ✅ SHIPPED v0.3.259 — IDS-shaped rule engine**
  (`apply_rules`: applicability facets — entity + PredefinedType, property, host-external/host-fire-rated
  relationship context → content bundle written via the Track-D carriers; `validate_rules` reuses the same
  rules as IDS QA missing-keynote pre-flight; ✨ Auto-detail tool + `apply_detailing_rules` recipe +
  `GET /detailing/rules/validate`; seed rule library; `test_rules.py`). **D7 ✅ the window-flashing worked
  case** ships in the seed library (exterior window → IBC §1404.4/ASTM E2112/AAMA 711 flashing detail + 08 51 00); **D4 ✅ SHIPPED v0.3.258 — classification + document carriers**
  (`classify` emits `IfcRelAssociatesClassification` for UniFormat/MasterFormat/OmniClass/Uniclass;
  `attach_document` emits `IfcRelAssociatesDocument`→Reference→Information for details/instructions, deduped;
  `element_detailing` inspector + 🏷 Detailing tool + `GET /detailing/{guid}`; `test_detailing.py`).
  *Still to add: the `Pset_Massing_SpecLink` breadcrumb.* D5 **keynotes & detail callouts** on drawings generated *from* the
  element's classification (NCS UDS Module 7); D6 **3-part MasterFormat project manual** (group elements by
  MasterFormat → SectionFormat Part 1/2/3, Part 3 Execution = the attached install instructions); D7 the
  **worked case**: place a window in an exterior wall → auto-attach IBC §1404.4 + ASTM E2112 + AAMA 711
  flashing detail (sill-pan/jamb/head shingle-lap sequence) + keynote + spec 08 51 00. D8 **approvability
  pre-flight** (reviewer-checklist: UL/GA numbers on rated walls, egress traced, COMcheck attached, A117.1
  clearances) — extends the IDS→BCF pipeline.
- **E · Master-builder UX (low barrier)** *(L)* — E1 **SketchUp-style inference snapping** (endpoint/mid/
  face/parallel/perp) + Shift-lock; E2 **type-a-dimension-while-drawing** (VCB); E3 **sketch-to-BIM push/pull**
  (2D profile → extrude); E4 **progressive-disclosure LOD-gated toolbar** (novices see place-wall/door/window;
  fabrication tools behind an advanced mode); E5 **direct-manipulation parametric handles**; E6 **recipe-log
  undo/redo + design-option branches** (the recipe log IS the undo stack); E7 **live schedules/quantities as
  you model**; E8 **guardrails encoding Bonsai's ~50 "don't make broken IFC" rules** server-side (novice can't
  produce invalid IFC — the reliability edge); E9 the **selector DSL** ✅ SHIPPED v0.3.255 (`query_elements` +
  🔎 Query tool + `GET /query`) + `geom.tree` spatial index.
- **G · LOD-500 verified-as-built data** *(M)* — G1 verification/as-built Pset + COBie + provenance stamps;
  G2 field-verified dimensions/variances; G3 external-doc refs (warranties/O&M/serials) via
  `IfcRelAssociatesDocument`. *This is the cheap, high-claim "LOD 500" layer.*
- **H · Content library** *(M)* — H1 seed furniture families + PBR materials from **vetted CC0** sources
  (Poly Pizza/Quaternius/Kenney meshes; ambientCG/Poly Haven/AMD MaterialX PBR — CC0/CC-BY only; exclude
  BIMobject/TurboSquid/etc.), attribution + license stored per asset.

**Recommended sequencing:** **F0 spine → E8 guardrails + B1–B3 geometry wins → C1–C3 drawing generator →
D1/D3/D4/D7 code+detail intelligence → A open-ended authoring → E inference UX → G/H woven throughout.** Each
is its own verified release; several Wave 10 items (W10-2/4/5/6) fold in here.

**License guardrails (firm):** `ifcopenshell` + `ifcopenshell.geom` serializers are **LGPL** — safe to depend
on and the exact layer every technique above sits on. **Bonsai/BlenderBIM (GPL)** drawing/annotation modules —
**reimplement the techniques, never vendor the code.** ifc-bonsai-mcp glue is **MIT** (safe to mirror);
MCP4IFC paper is CC-BY-SA (docs only). SVG→PDF/DXF via permissive libs only (**no AGPL** — no PyMuPDF).
CC0 asset sources vetted per-asset. IDS is an open buildingSMART standard (we already ship IDS→BCF).

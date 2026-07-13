# Roadmap

The single product roadmap. Supporting detail lives in:
[production-readiness.md](production-readiness.md) (security/perf/ops checklist),
[gc-portal.md](gc-portal.md), [gc-tools-audit.md](gc-tools-audit.md),
[ux-findings.md](ux-findings.md).

Three pillars on one IFC-keyed model: **BIM viewer** · **GC portal** (config-driven modules) ·
**developer/finance** (proforma). Shipped continuously — latest release **v0.3.244**.

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

> **✅ The actionable backlog is CLEARED (2026-07).** Buckets ① (generative/analysis depth) and ②
> (UX/perf) are fully shipped; ③ (interop) is done or evaluated-and-deferred with criteria (glTF import +
> pyRevit publish already ship; RVT bridge hardened v0.3.243; the L1 converter and L4 FreeCAD spikes were
> evaluated → deferred, see below). **What remains is only ④ upstream-blocked, ⑤ deferred-by-decision, and
> ⑥ documented non-goals — none of it buildable-now-by-choice.** The next substantive work is new research,
> not this backlog.

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

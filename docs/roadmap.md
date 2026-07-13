# Roadmap

The single product roadmap. Supporting detail lives in:
[production-readiness.md](production-readiness.md) (security/perf/ops checklist),
[gc-portal.md](gc-portal.md), [gc-tools-audit.md](gc-tools-audit.md),
[ux-findings.md](ux-findings.md).

Three pillars on one IFC-keyed model: **BIM viewer** · **GC portal** (config-driven modules) ·
**developer/finance** (proforma). Shipped continuously — latest release **v0.3.239**.

> **🎯 Active initiative — turn the Model workspace into a true in-browser modeling program** (2026-07,
> direction change). The audit found the Model section was ~80 % viewer/analysis with authoring buried and
> no from-scratch start; the backend authoring engine (~30 GUID-stable recipes) was already real. Reversing
> the old "web = viewer, Blender = editor" non-goal (see [CLAUDE.md](../CLAUDE.md)). Research-informed by
> Revit, BlenderBIM/Bonsai and Bluebeam panel layouts.
>
> **Shipped (P1–P4 authoring, P6a–d rail):**
> - **P1** blank model from scratch (`generate_blank_ifc` + `POST …/model/blank`) + first-class Author-mode surfacing (v0.3.231)
> - **P2** removed the redundant legacy place buttons + ~90 lines dead code — Draft panel is the single authoring surface (v0.3.232)
> - **P3** room/space authoring UI (➕ Add rooms/spaces via `add_spaces`; level-add already existed) (v0.3.234)
> - **P4** author-ready **template picker** — blank + office bay / residential floor / warehouse, all editable (v0.3.233)
> - **P6a** cut the four duplicative rail sections (cost/schedule/drawings/energy → deep-links); removed ~700 lines (v0.3.235)
> - **P6b** dedicated **💥 Clash & coordination** rail toggle (federated + single clash, clash list, metrics, promote-to-BCF) (v0.3.236)
> - **P6c** rail re-clustered **Navigate / Author / Coordinate** (v0.3.237)
> - **P6d** docked **📋 Properties** rail panel with a Revit-style Type/Instance identity header — Properties no longer float; they dock in the Author cluster (v0.3.238)
> - **Model browser** — the tree now has a **group-by** switch (level / discipline / IFC class / type-family) + **search** across name·GUID·class·type·discipline, auto-expanding matches (Revit Project Browser parity) (v0.3.239)
>
> **Open — tracked here:**
> - **P5 — edit-in-place** (drag/stretch/move geometry directly, vs click-place + full republish). The biggest
>   "feels like a real modeler" upgrade and the most interaction-heavy — needs a focused design pass. *(task #360)*
> - **Level rename / set-elevation** UI — recipes exist (`rename_storey`, `set_storey_elevation`); needs
>   per-storey GUID plumbing in the levels API.
> - **Selection sets** — named saved selections in the Visibility panel (Navisworks/Bluebeam pattern).

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
- **Nav density** — ✅ **per-stage collapse memory DONE (v0.3.230)**: nav stage groups are collapsible
  `<details>` that persist folded per `workspace:stage`; the active destination's stage stays open.
  *Remainder:* a denser summary mode for the multi-card command-center panels.
- **A11y** — keep verifying new tabs/dashboards (roles, focus order, contrast) as workspaces grow.
  *(v0.3.229 audited this cycle's new panels — SVG accessible names, labeled form controls, `scope` headers,
  a reusable `.sr-only`; ongoing as more panels ship.)*
- *(⌘K, saved-views-per-role, cross-workspace deep-links both directions, and the `portal.ts` per-domain
  split all shipped — see §Part C archive.)*

**③ Interop / library evaluations — contained spikes, adopt only if it serves the mission** *(§L)*
- **L1 — `@ifc-lite/geometry` server-side converter spike** (MPL-2.0, claims ~5× web-ifc): trial as a
  faster **server** IFC→tessellation path behind the existing convert API. *Do not swap the browser engine.*
- **L4 — FreeCAD as an optional headless server engine** (LGPL, same `ifcopenshell` we run): parametric
  family generation + 2D-drawing export, additive to the pipeline, no client weight. Lower priority than L1.
- **glTF import overlay** + a one-click **pyRevit "export IFC → upload to Massing" macro** — both
  convenience niceties (glTF *export* + the pyRevit *export* path already ship), neither mission-critical.
- **RVT→IFC (APS) bridge polish** — the paid Autodesk Model-Derivative path already works behind a flag;
  incremental hardening only.

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
- **In-browser IFC authoring** — Blender/Bonsai is the desktop editor by design (§L Pascal Editor); the
  web app stays a viewer + edit-gated place-tools. **`.mpp` (MS Project) parsing** — proprietary OLE binary,
  no reliable OSS reader; path is *Save As XML/CSV → import* (§L). **Custom Revit/Navisworks plugin** —
  Autodesk's certified `revit-ifc` already covers it (§L).
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

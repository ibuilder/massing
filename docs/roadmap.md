# Roadmap

The single product roadmap — **open items only**. Everything shipped lives in
[roadmap-completed.md](roadmap-completed.md); per-release detail is in [CHANGELOG.md](../CHANGELOG.md).
Supporting detail: [production-readiness.md](production-readiness.md) · [gc-portal.md](gc-portal.md) ·
[ops-dr.md](ops-dr.md) · [mobile.md](mobile.md).

Three pillars on one IFC-keyed model: **BIM authoring/viewer** · **GC portal** ·
**developer/finance**. All three have depth — finance and CRE from R19 + R20, authoring from R18, the
5D/4D spine from R25, the interaction surface from R26. **What is thin now is the drawing**: the sheet
is still handled as an image with text behind it rather than as data (📐 R27).

**Status — reconciled 2026-07-28 at v0.3.740.** CodeQL **0** open · backend **416** suites green ·
vitest **557** (incl. vendored kernel + PDF engine) · single-source version in `apps/web/package.json`
· CI on Node 22 · 3 remote branches, 1 open PR.

**The five-room shell is the DEFAULT and is reachable.** It renders in the Construction, Developer and
Design workspaces; opening a project lands on the persona's home and every other workspace carries a
`← Project home` signpost (v0.3.739). `?shell=classic` opts out and sticks.

**Read the gating honestly.** A large block of what remains is genuinely blocked — see
[⛔ Gated](#-gated--each-entry-names-its-unblocking-event). The ▶ NOW list below is **only non-gated
work**.

> **Housekeeping note, 2026-07-28.** This file had accumulated **three duplicate NOW sections** with
> contradictory content — items shipped hours earlier still listed as pending, numbering running
> 1, 2, 1, 5, 6, and a header claiming the new shell was opt-in after it had been made default. Cause:
> scripted edits that *inserted* a NOW section instead of replacing one, repeated over several
> releases. Rebuilt by hand here. **If you are editing this file with a script, replace between the
> section markers — never splice at a matched string.**

---

## ▶ NOW — one prioritized list *(rebuilt 2026-07-28 at v0.3.772)*

There were **three** competing NOW sections before this rebuild, and four more sections headed
COMPLETE that still contained open work. That is how R26-VITALS — the prototype's most visible
pillar — sat unbuilt inside `roadmap-completed.md` for weeks: **an unshipped item filed under a
completed heading is invisible**, because nobody goes looking there. One list, in order.

### ~~1 · R26-VITALS~~ — **DONE v0.3.773.** Was:
Six numbers along the bottom — **LOD · area · $/sf · float · IRR · health** — replacing the ten
viewport controls pinned to every room whether or not it has a viewport (audit finding 13: *"ten
permanent controls, irrelevant on four of seven tabs, occupying the most valuable strip of the
window"*). The audit calls this *"the only continuous proof of the one-model claim"*.

Three of the prototype's four pillars shipped (spine, Inspector, work-queue-as-home). This is the
fourth. **Build it as one `/projects/{pid}/vitals` assembly endpoint** over engines that already
exist — five separate client fetches is precisely how audit finding 03, *"the app contradicts itself
on screen"*, happens. Viewport controls then move into Design, where they apply.

### ~~2 · VITE-8~~ — **DONE v0.3.774** (and it caught a silent vendor-split regression). Was:
Vite 6→8 (Rolldown) + Vitest 3→4. The only genuinely outstanding item from that PR; its other
runtime bumps are already on main (Capacitor 8.4.2, postgres:17) or superseded (it wanted Node 22,
main runs 24). A major build migration, so it gets its own release and the full gate.

### ~~3 · CI-HYGIENE~~ — **DONE v0.3.774**; two of the four items were already done. Was:
Pin the MinIO and nginx image tags, extend Dependabot to container images + a Vite group, and make
the Cargo.lock guard non-fragile with `cargo metadata --locked`.

### ~~4 · R27-UW-PANEL~~ — **CLOSED, not built.** The premise does not survive the constraint

Written as "give `__uw__` a real portal panel so Deal lands on Underwriting". Checked before
building, and the trade is bad:

- **Underwriting is already reachable and labelled** from the Deal room — `📊 Underwriting` sits in
  the rail, one click away, in the same group as Deal's other destinations.
- **Underwriting is a full-page surface**, not a 280px panel. It is the finance workspace's Proforma
  tab. Forcing it into an `.rpanel` for the sake of a uniform landing mechanism is the same wrong
  shape that made Drawings a launcher rather than a side panel in v0.3.772.
- **`finance` is not a portal workspace** (`PORTAL_WORKSPACES = construction, developer, design`).
  Landing Deal there would surrender the rail that carries Deal's **16 registers** — the room's
  actual substance — to gain one panel.

So Deal lands on **Portfolio**: a real panel, in the portal, with the rail intact, and Underwriting a
labelled click away. That is the better arrangement, not a workaround for it. Was:
Give `__uw__` a real portal panel so Deal lands on Underwriting instead of Portfolio. v0.3.770 tried
to shortcut this by marking the workspace hand-off active; the marker never cleared, so a repeat
click reported arrival for a navigation that never ran. Reverted in v0.3.771, and `spine.test.ts`
now asserts no room's home carries `goto`.

### ~~5 · R25/R24-TRACE-UI~~ — **DONE v0.3.775**: the coverage figure opens onto its elements. Was:
The 5D chain made visible: figure → cost line → the elements behind it. The engines all exist; this
is the last mile that makes the differentiator discoverable by clicking rather than by reading docs.

### ~~6 · SAMPLE-LIBRARY ②~~ — **DONE v0.3.776**: a second building type, and a real one
`riverside_school_structural.mass` — 1551 elements (619 reinforcing bars, 375 beams, 299 slabs, 203
columns, 15 assemblies, 5 storeys), packaged through the same publish path a user drives. The library
now shows what the two containers are *for*: the house proves the browser authoring path end to end
at 23 elements; the school is a frame an engineer recognises. It is **structure only**, so Area and
$/ft² render as `—` with their reasons — the vitals strip working, not a gap papered over. Was:
`build_samples.py` works and the library ships (v0.3.769). What is missing is **content**: more than
one `.mass`, covering more than one building type. Blocked on authoring time, not on tooling.

### 7 · ONE-LOAD-SAMPLE ② + FIRST-RUN ②
Replace the remaining hard-coded `.frag` menu entries with the library, and have an empty install
open a populated project rather than an empty screen.

### 8 · MASS-FOR-EVERY-MODEL ② + CREATE/OPEN/SAVE ③
Loading an IFC with no container creates a blank one; then re-cut the Create / Open / Save dropdowns
against the container model now that `.mass` is real.

### Decisions, not effort — these want your call
- **ROOM-NAMING** — the prototype named rooms in plain language (Building · Budget · Timeline ·
  Money · My to-do); we ship professional terms (Design · Planning · Cost · Schedule · Deal · Work)
  and `rooms.py` records that as a deliberate reversal. Settle it with a real user, not from the
  armchair.
- **QUALITY-ROOM** — inspections/ITP sit in Design because an inspection checks the built thing
  against the design. Answered 2026-07-28: the *task* already reaches Work via the queue
  (`INS-001`, `DEF-001`, `NCR-001` are in it now), so the *register* stays with its discipline.
  Revisit only if that stops feeling right in use.
- **Branch protection** — `main` is unprotected and public. Blocking force-push and deletion costs
  nothing and is not reversible after an accident.
- **R26-V-TIMING** — needs real users. **Plugin pricing** — needs customers. Both correctly parked.

### Practice note — verify before carrying
Three sections in this file were wrong about their own state on 2026-07-28: **A2-CONSTRAINTS**,
**A2-SHEET-REGIONS** and **A2-ICON-RENDER** were all listed as built-but-unrouted, and all three are
routed and consumed (`analysis.py:542`, `analysis.py:572` + a live 200, `toolbarView.ts:15`). The
roadmap is a claim like any other. Check the premise before spending a release on it — see
[[check-the-blocker-premise]].


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

* **R27-LAYOUT ① — the layout is written but never read back.** *(Corrected after checking the code:
  the first draft of this item said "add `sheet_layout.py`". That module already exists —
  [sheet_layout.py](../services/data/src/aec_data/sheet_layout.py), and it is good — but it runs in
  the **write** direction: it composes viewport rectangles, fixed 1:N paper scales, per-viewport class
  freezes and titleblocks onto sheets we generate. Nothing reads that structure back out of a PDF.)*

  So this is the **same asymmetry R25-TASK-BIND closed for the 4D binding**: a platform that can write
  a structure but not read it has a one-way door, and the structure stops existing the moment the file
  leaves. Two halves, and the first is nearly free:

  ✅ **(a) Our own sheets** *(shipped v0.3.702)*. Detection was never required here, only persistence:
  `compose_viewports` already computes the exact page←world affine in order to place the geometry, so
  `sheet_regions()` now keeps it. Each region reports `basis: "authored"` — these *are* the numbers the
  sheet was drawn with, not a recovery from the rendered output — and the **measurable** rect is the
  inner one, not the cell, because the cell includes padding and the label band and scoping a takeoff
  to it would accept a trace that is not on the drawing. `to_world()` inverts the affine; an
  unmeasurable viewport reports **`to_page: null`, never identity**, since an identity would silently
  report page points as metres. The transform is asserted by **inverting an actual rendered vertex**
  rather than against a second implementation of the same arithmetic — the 4D binding round-tripped
  perfectly through its own writer+reader pair while encoding the wrong IFC relation.

  **(b) Received sheets.** Recover rectangles from the page content stream via `pypdf` and classify
  them with the ADIRO-style vocabulary (titleblock · revision table · legend · general notes ·
  view/viewport · key plan · scale bar), returning page coordinates with a per-region `basis` of
  `sidecar` | `vector` | `unknown`. **A sheet whose vectors are gone returns `unknown`, never an empty
  region list** — the unknown ≠ none rule that ten engines now enforce.

  Evidence: arXiv:2607.18997 §layout-layer. Read-side gap confirmed in
  [sheet_extract.py](../services/api/src/aec_api/sheet_extract.py), which walks pages via `pypdf` and
  regexes the text layer with no notion of *where on the sheet* anything sits.

* ✅ **R27-LAYOUT ②** *(shipped v0.3.706)* — **a takeoff scoped to the view it belongs to.**
  [takeoff2d.py](../services/api/src/aec_api/takeoff2d.py) takes `regions` **from the caller** and a
  `scale_units_per_px` **from the caller** — every quantity on a sheet is hand-traced and hand-
  calibrated, and nothing checks that a traced polygon sits inside the view it is being priced
  against. With ① landed: seed candidate regions from the detected viewports, and read the scale from
  the titleblock's scale text or a detected scale bar so `calibration_scale` has something to *check*
  rather than only something to accept. **The scale is proposed, never silently applied** — a takeoff
  calibrated by a machine that was wrong is worse than one nobody calibrated, because it looks done.

* ✅ **R27-LAYOUT ③** *(shipped v0.3.707)* — **a note attaches to what it governs.** Once regions exist, a general note, a
  keynote and a revision cloud each belong to a *view*, not to a page number. This is what makes
  `keynotes`/`DETAIL-REF` (R21) round-trip against received sheets rather than only our own.

* ✅ **R27-CLAIM-TYPE** *(shipped v0.3.709)* — **what kind of statement is this?** The representation handbook's one durable
  idea: a record should say whether it is an **intent** (specified), an **embodiment** (built),
  an **evidence** (measured/observed) or an **inference** (derived). `element_facts.gather()` already
  states a `source` per fact and `verified()` already prefers an IFC stamp over a field record — this
  generalises that from one engine's convention into a field the whole fact spine carries. The payoff
  is concrete: "this wall is fire-rated" sourced from a *specification* and from a *field
  observation* are different claims, and today they render identically.

* ✅ **R27-SOV-LOOP** *(shipped v0.3.702)* — **close takeoff → estimate → SOV → pay app.** Confirmed gap, not a suspicion: the
  `estimate` and `sov` modules both exist, `cost.py` reads a G703, and **nothing anywhere builds an
  SOV from an estimate**. The chain the whole cost pillar implies is broken at exactly one seam, and
  it is currently bridged by re-keying. Build `sov_from_estimate()`: estimate lines → SOV line items,
  carrying `quantity_source`/`rate_source` (shipped v0.3.699) forward so a pay-app line can be traced
  back to the model element it was measured from.

  **Shipped as `sov_build.from_estimate()` + `POST /projects/{pid}/cost/sov`.** The transformation is a
  **regrouping** — an estimate is keyed by (code, basis, rate) because those price differently; a
  contract bills the code — and the whole risk of a regrouping is money going missing inside it. Four
  refusals: unpriced scope is **excluded and named**, never dropped (an SOV built only from the lines
  that happened to price is smaller than the job and looks complete, because every line in it is
  right); the **rounding residual is placed on the largest item and reported**, because rounding each
  item then summing ≠ rounding the total once and that penny is what gets a G703 rejected; a
  zero-markup result carries **`at_cost: true`**, since scheduled values are *contract* values while an
  estimate is *cost*, and billing lump-sum off unmarked-up cost under-bills by the entire fee every
  month; and each item keeps its **GlobalIds and quantity/rate sources**, collapsing to `mixed` rather
  than rounding one measured element among fifty up to `declared`.

  `/cost/estimate` and `/cost/sov` were also collapsed onto one shared `_run_estimate` helper — two
  code paths computing "the estimate" is how a billed number stops matching the priced one.
  `reconciles` is named honestly as a **conservation** check (it proves the regrouping lost no money,
  not that the estimate was right) and is verified against **two independently-built accumulations** in
  the source.

* ✅ **R27-RISK-CALIBRATE** *(shipped v0.3.710)* — **the distribution comes from your own history, not a guess.**
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

## 📦 R28 — ONE PROJECT, ONE FILE *(research 2026-07-26; the model/project split)*

**The premise check first, because it changes the whole question.** The ask was "should we invent a
`.mass` file — a zip with everything inside, like a markup tool's bundle?" **We already ship one.**
`aec_api/bundle.py` defines `.mmproj` (`FORMAT = "aec.mmproj"`): one zip carrying the published
Fragments tile, the source IFC, **every project-scoped database row** — which is all 130 CRUD modules
*and* the proforma, since those are `project_id` tables — plus attachment blobs. Import mints a fresh
project id and remaps foreign keys, so a bundle clones or moves machines cleanly. The app's Open menu
already lists it. So the container is not the gap; **nobody could tell it existed** is the gap.

**And a standard already defines this shape: ISO 21597 (ICDD).** *Information Container for linked
Document Delivery* is a zip with `/Payload documents/` (the heterogeneous files), `/Payload triples/`
(RDF linksets joining them, at document **or object** level), `/Ontology resources/`, and an
`index.rdf`. Part 2 standardises the link types. That is precisely "model + construction data +
proforma in one file, with the relationships preserved" — and adopting it is the same bet this
platform already made with BCF: **a bespoke container round-trips with nothing; a standard one
round-trips with everyone.** ([ISO 21597-1](https://www.iso.org/standard/74389.html) ·
[Part 2: link types](https://www.iso.org/standard/74390.html))

**The real defect is conceptual, and it produced two shipped bugs.** Opening a *model* does not open a
*project*, and opening a *project* does not guarantee a *model*. In v0.3.703 that split surfaced twice:
the portal rendered "No project open" **while a model sat visibly loaded**, and the Developer tab
latched itself permanently empty. Both were repaired at the symptom. The cause is that "project" and
"model" are two states the app keeps having to re-marry, and every feature built on top inherits the
seam.

* **R28-UNIFY ①** — **one open, one save.** Opening any model creates or attaches a project (with its
  API data if it exists); opening a project ensures a model exists — **a blank authorable one if
  there is none**, so a user can start drawing immediately rather than meeting an empty viewer. This
  is the item that removes the class of bug, not the two instances of it.
* **R28-BUNDLE ② — make `.mmproj` legible.** It already carries the data; nothing says so. Name it in
  the UI, show what a bundle contains before import, and state on export what was included and what
  was **left out** (`_SKIP_TABLES` drops users, audit log, settings and connections — correct, and
  currently silent). The same unknown ≠ none rule the engines follow.
* **R28-ICDD ③ — a standards-conformant envelope.** Emit and read ISO 21597 containers, with our
  payloads as documents and the GlobalId-keyed relationships as RDF linksets. `.mass` can then simply
  **be** an ICDD container with our extension — the branding without the lock-in.
  ✅ **`rdflib` (BSD-3) is APPROVED** *(user, 2026-07-26)* — no longer gated. Licensing is recorded in
  [ATTRIBUTIONS.md](ATTRIBUTIONS.md), which also states that the container is implemented from the
  **published standard** and that no ISO specification text is redistributed. The dependency is pinned
  in `requirements.in` **in the change that first uses it**, with `requirements.lock` regenerated in the
  same commit — the lockfile gate fails any push that leaves the two out of step, and a dependency
  carried ahead of its code is supply-chain surface for no benefit.
* **R28-VIEWER ④** — the future viewer opens a **container**, not a file. **This is now live and
  external**: the kernel rebuild is `MassingCloud/massingifc` (private), first commit 2026-07-26 —
  a framework-agnostic kernel + plugin host with **all fourteen capability families still contracts
  only**. That is the cheap moment to settle this, and the window closes as families get implemented.

  Its persistence is per-**document** (`{schema, version, savedAt, data}`); there is no **container**
  concept, so "open a project package" would land as a plugin concern and be retrofitted. A container
  is a *mechanism*, which by that repo's own first design rule puts it in the kernel, with `.mmproj`
  and ICDD as adapters. Three further contract-level notes: **project↔model unity** wants to be a
  kernel contract or the v0.3.703 bug class returns; **selection and markup anchors must key on
  GlobalId**, never fragment-local ids, or every capability above inherits transient identity; and the
  **5D/4D contracts should carry provenance** (`quantity_source`/`rate_source`, and the 4D link being
  the task's *output*) rather than bare values. Also: that repo has **no LICENSE**, which needs
  settling before this public repo can depend on it.

**Sequencing.** ① first — it is the bug class, needs no dependency and no standard. Then ② which is
mostly surfacing what exists. ③ is now unblocked and is the interop play, not a prerequisite. ④ falls
out of ① and ③ and should gate the viewer rebuild.

---

### ⚙ PERF triage *(external static analysis, 2026-07-26 — verified against the code)*

An external analyser produced eight performance findings. Most of its **facts** check out; two of its
headline **recommendations** are backwards, and one finding examined nothing. Recorded so the wrong
fix does not get made later from the same report.

* **PERF-WORKERS ① — the cache story is duplication, not size.** Verified: `ifc_loader` caches 8 models
  (`@lru_cache(maxsize=8)`), `drawings._BAKE_CACHE_MAX` is 4, and `UVICORN_WORKERS` defaults to **4**.
  The analyser's advice was to *raise* both caches. **That makes the problem it identifies worse**: the
  caches are per-worker, so raising them multiplies resident memory by the worker count — its own
  finding ③ contradicts its finding ①. The real options are a bounded **shared** cache (a loader
  process or Redis-backed handle), or worker affinity so one model lives in one worker. Sizing is the
  last lever, not the first.
* **PERF-RATE ② — the rate limit is per-worker and only warns.** Verified at `main.py:155-162`: with
  `AEC_RATE_LIMIT_RPM>0`, multiple workers and no `AEC_REDIS_URL`, each worker counts independently, so
  the effective limit is N× the configured one. It logs `CRITICAL` and **starts anyway**. A security
  control that announces it is not working and then runs is worse than one that is absent, because the
  operator believes it is on. Refuse to start, or drop to one worker.
* **PERF-THREADS ③ — cap the pool, but the stated mechanism is wrong.** The claim was "unbounded
  threads → resource exhaustion". Starlette/anyio's default pool is **40 threads, not unbounded**. The
  genuine risk is different and worth fixing: 40 concurrent *IFC* operations at hundreds of MB each is
  an OOM, so the cap wants to be small and explicit for model work specifically — not because threads
  are unbounded but because each one is expensive.

**Not adopted.** "No evidence of query batching" is an absence of evidence offered as a finding — the
report did not examine the ORM layer and does not name an endpoint. It is the inverse of this repo's
own rule: *a check that examined nothing must not report anything*, clean **or** dirty. Lazy imports
are also deliberate — they keep cold start cheap for the paths a deployment never touches — and the
bake cache's `id()` key is already sound: it holds a strong model reference and re-checks identity.

---

### 🐍 DDC ecosystem scan *(2026-07-26 — a Python construction-data org, 30 repos)*

Scanned at the user's request. The headline is a **licence trap worth recording**, because the
repository's own README states the wrong licence for its most valuable asset.

**The CWICR cost database — 55,719 work items, 27k resources, 30 regions, 21–31 languages — is
`CC BY-NC 4.0`, NOT `CC BY 4.0`.** The skills repo's README advertises it as CC BY 4.0; the actual
`LICENSE-DATA.txt` in the data repo is **NonCommercial**. That is the same exclusion class as the
PolyForm-NC library already refused above, and taking the README at its word would have put a
non-commercial dataset inside a commercial product. The repo's *code* is Apache-2.0 and fine; only the
data is encumbered. **Check the LICENSE file, never the README's summary of it.**

**⛔ Not usable:** the CWICR **data** (CC BY-NC 4.0) · the `cad2data` RVT/DWG/DGN converters
(**proprietary** — an explicit commercial licence, despite the repo reading as open) · an
open-source construction ERP (**AGPL-3.0**) · and roughly ten GPL-3.0 notebooks covering embodied
carbon, ML price prediction, quantity takeoff and estimation.

**✅ Permissive and worth reading:** a 221-file **skills corpus for construction AI agents** (MIT), a
**4D–5D pipeline** (Apache-2.0), **Revit/IFC project quality checking** (MIT), a CAD/BIM-to-code
pipeline (MIT), and an IFC/Revit ETL collector (MIT).

**What is actually worth taking, and it is not code.** We already have `.claude/skills/` and the
master-builder skill, and we already have `model_qa`, `qto`, `fived` and the 4D/5D spine — so none of
those repos closes a capability gap. What the 221-skill corpus *is* good for is a **map of what
construction teams actually automate**, at a granularity nobody publishes otherwise. Read as a
coverage checklist against our 130 modules it is a gap-analysis input, not an import.

* **R27-SKILL-GAP** *(S — reading, not building)* — diff the MIT skills taxonomy against our module
  catalog and the master-builder skill; record only the gaps that fit the mission. Explicitly **not**
  a bulk import: 221 generated skill files would bloat the repo and duplicate engines we already have
  tested. The output is a short list of missing *capabilities*, not files.

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

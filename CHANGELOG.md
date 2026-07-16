# Changelog

All notable changes to Massing. Releases are signed, auto-updating desktop builds
(Windows / macOS / Linux); the updater always serves the latest. Format loosely follows
[Keep a Changelog](https://keepachangelog.com/).

## v0.3.324 — Interactive dimensions (UX-2, next slice)

Extends the in-view annotation tool with **dimensions**. New `add_dimension` recipe authors an
`IfcAnnotation` between two [E,N] points — a dimension line (`IfcPolyline`) plus the **measured distance**
as an `IfcTextLiteral` at the midpoint (auto-labelled `5.00 m`, or a custom label), in the Annotation
context; round-trips as real IFC and feeds the drawing generator. New **📐 Dimension** tool with a two-click
flow (first point → second point → measured dimension). The E8 guardrails already validate the two points
(finite + distinct → zero-length rejected). `addDimension` client + `test_annotation.py` extended (a 3-4-5
span → `5.00 m`, custom label, zero-length rejection). *Next: inference-snapped dimension placement + tags
that read a live IFC property.*

## v0.3.323 — Interactive annotation: place notes/tags as IfcAnnotation (UX-2, first slice)

The first slice of the UI/UX Master Pass's annotation gap: annotation existed **only** baked into generated
plan SVGs — now you can place it *in the model*. New `add_annotation` recipe authors an **`IfcAnnotation`**
with an `IfcTextLiteral` (an `Annotation2D` representation in the Annotation context) at an [E,N,z] point —
a note / tag / callout that round-trips as real IFC (and can feed the drawing generator, unlike the baked
SVG path). New **🏷 Add note / annotation** tool places one at the last-clicked point (text + kind prompt);
`addAnnotation` client. Empty text rejected. `test_annotation.py` (authors + round-trips through a written
IFC). *Next (UX-2): dimensions snapped by the E1 inference engine, element-aware tags, revision clouds; and
the UX-1 ribbon consolidation + UX-3 Library palette (best built with a live 3D session to verify the look).*

## v0.3.322 — Scene digest: an LLM-grounding model summary (A4)

A compact, one-glance summary of *what's in the model* — and the grounding the AI command bar was missing.
New `scene.digest(model)` composes the shipped summaries (element counts by class, storeys, spaces, MEP
systems + disciplines, phasing, LOD, model hygiene) into a small dict plus a one-paragraph `prose` overview,
degrading gracefully on a bare model. New `GET /projects/{pid}/scene-digest` + a **🔎 Model digest** tool
(counts, MEP disciplines, phasing, hygiene at a glance). Crucially, `POST /ai/author` now injects the digest
prose into the planner's system prompt, so Claude authoring is **grounded in the current model** ("N walls,
2 storeys, a fire-protection system…") instead of planning blind. `sceneDigest` client + `test_scene.py`.

## v0.3.321 — Mesh→IFC asset import: bring in detailed parts, auto-classified (CONTENT-1 remaining)

The other half of the content library: **import a well-detailed mesh and place it as the *right* IFC**, not
a random shape. New `content.parse_mesh` loads a glTF / GLB / OBJ / STL / PLY (trimesh) into recentred,
metre-scaled verts + faces (glTF Y-up → IFC Z-up; a face-count cap; `scale`), and `content.detect_category`
guesses the catalog category from the filename (`office-chair.glb` → `chair`; `Porta-John.stl` →
`sanitary_unit`; longest synonym wins). New `POST /projects/{pid}/content/import` (multipart) parses the file,
auto-detects (or takes `category=`), and authors it via the `place_content` recipe — correct IFC class +
phase + Uniclass/OmniClass classification — versioned, undo-able, republished. The 🏗 Site content library
tool gains an **⬆ Import mesh** picker (drops the asset at the last-clicked point). License-vet the source
before import. `importContent` client + `test_content_import.py`. Builds on the B4 mesh hatch + the CONTENT-1
catalog. *Next: a curated CC0 seed library + a browsable thumbnail palette (folds into the UX-3 Library pass).*

## v0.3.320 — Element-to-element connections (B5)

The LOD-350 coordination primitive: which elements are physically connected. New `connect_elements` recipe
records an `IfcRelConnectsElements` between two building elements (a beam framing into a column, a brace to a
gusset, a hanger to a slab) — distinct from the MEP port link (`connect_mep`). Idempotent per ordered pair,
rejects self/missing. New `element_connections` read-back reports the connected pairs (with class +
description) and each element's connection **degree**, served at `GET /projects/{pid}/element-connections`;
`connectElements` / `elementConnections` clients. Guarded (needs both GUIDs). Reachable via the AI command
bar; authored edges export for structural-analysis / coordination tools. `test_element_connections.py`.

## v0.3.319 — Vertical MEP risers (standpipes / stacks / vents)

MEP runs could only be drawn horizontally (`add_mep_run` sweeps in plan); a multi-story **riser** was
impossible. New `add_riser` recipe sweeps an `IfcPipeSegment` **vertically** (world +Z) from `bottom_z` to
`top_z` at an [E,N] point, with a port at each end, enrolled on a distribution system — the vertical
complement to `add_mep_run`, for **fire standpipes**, plumbing **stacks**, and **vents**. New **⭱ Vertical
riser** tool places one at the last-clicked point over a bottom→top elevation range. Verified
deterministically (ExtrudedDirection = +Z, Depth, base elevation) and by standalone tessellation (a real
cylinder spanning the height). `test_mep_systems.py` extended; zero/negative height is rejected.

## v0.3.318 — O&M / warranty document refs on the as-built model (G3 follow-up)

Completes the LOD-500 turnover trio (verify · dimensions · manufacturer) with **operation & maintenance /
warranty documents** bound to the physical asset. New `attach_om_document` recipe (a purpose-tagged
`attach_document` — `OPERATION_MAINTENANCE` or `WARRANTY`) associates a manual/warranty reference (name +
link) with the selection via `IfcRelAssociatesDocument`; `asbuilt_summary` now reports `with_om_docs`
(elements carrying an O&M/warranty document, detected by the document's `Purpose`) + the distinct document
names. The ✅ As-built (LOD 500) tool gains an **📄 Attach O&M / warranty doc** control and shows the O&M-doc
count in the readiness line. Guarded (needs a selection) + an `attachOmDocument` client. `test_lod500.py`
extended (2 O&M + 1 warranty doc → `with_om_docs` = 3).

## v0.3.317 — Deeper authoring guardrails (E8)

The pre-apply guardrails now catch more classes of broken edit before they touch the model. `guards.precheck`
gains: nested type **`dims`** validation (each value finite; dimension keys must be positive — mirrors the
top-level rules, non-dimension keys only finite-checked), **`points`** footprint arrays (every vertex a
finite [E,N] pair; ≥2 vertices), **sloped-wall heights** (`start_height`/`end_height` finite ≥ 0),
**procedural-mesh** `verts`/`faces` (non-empty), and new **reference requirements** — `connect_mep` needs
both `guid_a` + `guid_b`, `set_system_predefined` needs a `system`. Still fast, deterministic, params-level
(no I/O); errors block, suspicious-but-legal values warn. `test_guards.py` extended. This closes the E8
"deepen" follow-up (the first slice shipped earlier).

## v0.3.316 — Sprinkler coverage pre-check (NFPA-13-informed)

New `mep.sprinkler_coverage(model, hazard)` counts the SPRINKLER heads and compares against the number
NFPA 13 would require for the model's protected floor area (summed IfcSpace `Qto_SpaceBaseQuantities.
NetFloorArea`) at the hazard class — max protection-area-per-sprinkler is **200 / 130 / 100 ft²**
(light / ordinary / extra), a fact of the standard (copyright-safe; the text stays in NFPA 13). Returns head
count vs required, adequacy + shortfall, and area unknown → `adequate: null` when no spaces are measured. New
`GET /projects/{pid}/mep/sprinkler-coverage?hazard=` + a **🧯 Sprinkler coverage** button in the MEP tool
(shown when a fire-protection system exists). A planning assist — not a hydraulic calc, spacing check, or
obstruction review. `test_mep_systems.py` extended (2 heads / 400 m² → 22 required at light hazard; ordinary
requires more; empty model → n/a).

## v0.3.315 — Fire-protection equipment: hose reel / FDC / hydrant / fire pump (MEP-FP next slice)

Fleshes out the fire-protection system with real devices, not just piping. New `add_fire_equipment`
recipe authors a **sprinkler head**, **hose reel**, **fire-department (siamese) connection**, **hydrant**
(all `IfcFireSuppressionTerminal` subtypes with the right `PredefinedType` — HOSEREEL / BREECHINGINLET /
FIREHYDRANT / SPRINKLER) or a **fire pump** (`IfcPump`), each placed on the `Fire Protection` distribution
system (discipline = fire, so it rolls up in the MEP browser). New **🧯 Fire-protection equipment** tool
places the chosen device at the last-clicked point (mirrors the door/window place flow). `test_mep_systems.py`
extended (hose reel + FDC + fire pump land as the right IFC classes on the fire system). *Next: sprinkler
coverage/spacing check + standpipe risers.*

## v0.3.314 — Full cost estimate: labour + material + equipment (EST-1 next slice)

The model-driven estimate goes from labour-only to a fuller **5D cost**. `productivity.py` gains a
**material $/unit** (`MATERIALS`) and **equipment/plant $/unit** (`EQUIPMENT`) benchmark layer beside the
man-hours rates, and a new `full_estimate` augments each line with `material_cost` / `equipment_cost` /
`line_total` plus `total_material_cost` / `total_equipment_cost` / `total_cost`. `from_model(..., full=True)`
and `GET /projects/{pid}/estimate/labor?full=true` return it; the catalog now carries the unit material +
equipment costs too. The 💰 tool (renamed **Cost estimate — labour · material · equipment**) shows the
labour / material / equipment / total breakdown and a per-line total. Still excludes overhead / profit /
markup; all rates are editable benchmarks. `test_productivity.py` extended (concrete: $130/m³ material +
$15/m³ equipment; masonry $30/m² material, no equipment; totals reconcile).

## v0.3.313 — Decision-readiness gaps → BCF (RFI-0 next slice)

The decision-readiness audit (v0.3.307) now **rounds its gaps to trackable BCF issues**. New
`POST /projects/{pid}/rfi/readiness/bcf` runs `rfi_prevention.decision_readiness` and promotes every gap —
failed code checks, missing details/keynotes, model-data holes, open clashes — to a `type="readiness"` BCF
`Topic`: GUID-anchored (a 3D pin from the gap's first element), category-labelled, priority from the gap's
severity (high → high). Idempotent — re-running clears the prior readiness topics so they never pile up
(mirrors the W9-2b egress→BCF pattern). The 🚫 Decision-readiness tool gains a **📌 Promote N gaps to BCF
issues** button, so the "what's missing before we issue?" list becomes a resolvable, round-tripping issue set
in the Issues panel. New `rfiReadinessBcf` client. `test_readiness_bcf.py` (integration: 9 gaps → 9 topics,
409 without a source IFC, idempotent re-run).

## v0.3.312 — Security: Capacitor 6 → 7, clears the transitive `tar` advisories (SEC-DEP-1)

Dependency-hygiene release. The mobile shell's `@capacitor/*` packages (`android`, `cli`, `core`, `ios`)
move from `^6.2.1` to `^7`, pulling `@capacitor/cli@7.6.8` and its transitive `tar@7.5.20` (was `tar@6.2.1`).
That clears **7 Dependabot alerts** (6 high / 1 medium) — all node-tar extraction-time symlink/hardlink
path-traversal advisories (GHSA-9ppj-qmqm-q256, GHSA-qffp-2rhf-9h96, GHSA-83g3-92jg-28cx, GHSA-34x7-hfp2-rc4v,
GHSA-r6q2-hw4h-h46w, GHSA-8qq5-rm4j-mr97, GHSA-vmf3-w455-68vh) that entered **only** through `@capacitor/cli@6`.
The fix needs `tar ≥ 7.5.16`, but `tar@7` is ESM-only and Capacitor 6's CLI is CJS, so a bare npm override would
break `cap` (`ERR_REQUIRE_ESM`) — hence the full Capacitor 7 bump. Real exploit risk was nil (the CLI extracts
only its own trusted platform templates during a developer-run `cap sync`, never untrusted input, never in CI or
at runtime); this is security-tab hygiene, not an urgent patch. `capacitor.config.ts` needed no v7 changes; no
native `android/`/`ios/` projects are checked in, so there was no Gradle migration. Verified: `npm ls tar` resolves
`tar@7.5.20`, `npm run build` (Node 20) passes, and `cap sync` succeeds.

## v0.3.311 — Fire protection as a first-class distribution system (MEP-FP)

MEP systems now carry a **discipline**, so fire protection stands beside HVAC / plumbing / electrical
instead of being folded into a generic "MEP" group. `IfcDistributionSystem`s are stamped with a
`PredefinedType` (`FIREPROTECTION` / `VENTILATION` / `DOMESTICCOLDWATER` / `ELECTRICAL`…): `add_mep_run` /
`add_mep_fitting` / `add_mep_terminal` take a `discipline` (the segment/fitting/terminal recipes default to
their natural discipline), a new `set_system_predefined` recipe (re)types an existing system, and a new
**`add_sprinkler`** recipe authors an `IfcFireSuppressionTerminal` sprinkler head on the `Fire Protection`
system. The system browser (`mep.mep_summary`) now reports each system's **discipline** + PredefinedType, a
**by-discipline rollup**, and a `has_fire_protection` flag; fire-suppression terminals are counted and are
port-connectable, so the W10-4 connectivity check covers sprinkler runs too. The 🔀 MEP systems tool shows a
discipline rollup (with a "no fire-protection system yet" nudge) and a per-system discipline label. The
discipline is inferred from member classes when a system carries no explicit type, so existing models
classify correctly. `test_mep_systems.py` extended (fire-protection system + sprinkler heads +
`set_system_predefined` retag). *Next: sprinkler coverage/spacing + standpipe/fire-pump equipment.*

## v0.3.310 — Existing-building code: IEBC scope-of-work classifier (CODE-EBC)

Unlocks renovation / adaptive-reuse projects, which are governed by the **International Existing Building
Code**, not the new-construction path. New `ebc.py` (data side, facts-of-law like the CODE-1/2/3 engine —
owns the classification decision tree + published section/chapter numbers, never the copyrighted prose)
classifies a scope of work under the **Work Area Compliance Method**: **Repair · Alteration Level 1 / 2 / 3
· Change of Occupancy · Addition**. `classify(...)` is a pure, deterministic decision tree — a Level-2
trigger (space reconfiguration, adding/removing a door or window, reconfiguring/extending a system, added
equipment) becomes **Level 3** when the work area exceeds 50% of the building (IEBC §505), an addition or
change of occupancy governs as primary while co-occurring alterations still apply, and each result carries
the driving citations (§502–§507 + the requirements chapter), the applicable nested levels, and the
jurisdiction's adopted IEBC edition. `from_model(...)` first-guesses the scope from the model's **phasing**
(existing vs new/demolish → an alteration with a rough work-area estimate) which explicit flags override.
New `GET /codes/ebc/pathways` (reference catalog) + `GET /projects/{pid}/codecheck/ebc` (with `infer=true`
for the phasing-derived guess), an `ebcClassify`/`ebcPathways` client, and a **🏚 Existing-building code
(IEBC scope)** tool in the code-intelligence cluster. Preliminary classification — the AHJ makes the
determination. `test_ebc.py` (16 hand-worked IEBC scenarios + the phasing inference).

## v0.3.309 — Docs + marketing refresh: catch the user-facing surface up to the authoring wave

Non-code release. The README, in-app guide, and GitHub Pages landing had drifted ~14 releases behind
(last refreshed at v0.3.294) and named none of the authoring wave. All three now cover **model undo/redo**,
**SketchUp-style drawing inference**, **sloped-top walls**, **procedural mesh**, the **sandboxed
`execute_ifc_code`** escape hatch, the **site content library** (logistics/furniture/landscaping,
auto-classified), **MEP port-to-port connectivity**, **edition-aware code checks**, **detail callouts**,
the **decision-readiness (RFI-prevention)** audit, the **productivity-rate labour estimate**, and
**field-verified as-built dimensions** — with the new API surface (`/rfi/readiness`, `/mep/connectivity`,
`/estimate/labor*`, `/content/catalog`, `/edit/{undo,redo,history}`, `/authoring/capabilities`). Added a
shareable **current-status page** (`docs/status.html`) that snapshots what the platform does end to end,
and refreshed `docs/marketing-copy.md` with the authoring-stack feature lines. Regenerated the viewer demo
snapshot (`demoData.json`). Competitor-name-free throughout, per the standing directive.

## v0.3.308 — Productivity-rate labour cost + duration estimate (EST-1)

The estimating link from *quantities* to *schedule + 5D cost*. New `productivity.py` holds a
**man-hours-per-unit** rate library (earthworks / concrete / masonry / steel / MEP / finishes) with typical
crew sizes + condition **loading factors** (highrise / remote / summer / congested / night-shift).
`labor_estimate` turns a quantity of work into **man-hours → crew-days → labour cost**; `from_model` derives
a rough takeoff straight from the model (walls → masonry face area, slabs/columns → concrete volume) and runs
it. New `GET /estimate/labor/rates` (catalog) + `GET /projects/{pid}/estimate/labor?loading=&rate=` and a
**💰 Labour estimate** tool showing man-hours / crew-days / cost per activity. Editable benchmarks, labour
only (add materials/equipment/overhead for a full cost). `test_productivity.py`.

## v0.3.307 — Decision-readiness audit: RFI-prevention (RFI-0)

The proactive inverse of the RFI — every RFI is a decision made without the needed information, so this
surfaces the **information gaps a builder would otherwise have to ask about** *before* the set goes out. New
`rfi_prevention.decision_readiness` composes the checks that already ship — the approvability pre-flight
(failed code checks), the Track-D detail-rule validator (elements missing their detail/keynote),
model-hygiene (`model_qa`: orphaned / unenclosed / unnamed / duplicate), and clash coordination (open
clashes) — into one **ranked resolve-before-issue list**, each gap with a category, severity, and a concrete
fix. New `GET /projects/{pid}/rfi/readiness` and a **🚫 Decision-readiness (RFI-prevention)** tool that lists
the gaps and isolates the flagged elements in 3D. A pre-check assist — not a promise of zero RFIs.
`test_rfi_readiness.py`.

## v0.3.306 — Site content library: logistics / furniture / landscaping, auto-classified (CONTENT-1)

Place real-world parts into the **right** IFC place, not as random shapes. New `content.py` catalog maps ~20
categories — **site logistics** (tower/mobile crane, hoist, fencing, sanitary unit, site office, laydown,
gate, dumpster), **furniture** (desk/chair/sofa/table/bed/cabinet), and **landscaping** (tree/shrub/planter/
bollard) — each to its correct IFC class + project phase + classification. New `place_content` recipe authors
an item at an [E,N] point from a supplied detailed mesh **or** a category-sized placeholder box, then sets
the phase (logistics = **temporary**, so it time-phases on the 4D logistics slider) and the classification
(Uniclass/OmniClass). Logistics land as proxies, furniture as `IfcFurniture`, landscaping as
`IfcGeographicElement` (proxy fallback on older schemas). New `GET /content/catalog` + a **🏗 Site content
library** palette tool. Builds on the B4 mesh hatch; content is imported/authored per-asset with license
vetting (the catalog records the intended license tier; geometry is supplied, never bundled unvetted).
`test_content.py`.

## v0.3.305 — Procedural-mesh escape hatch (B4)

Author an element from a **raw triangle mesh** for geometry the parametric recipes can't express. New
`add_mesh_representation` recipe builds an `IfcTriangulatedFaceSet` (Tessellation body) from `verts`
(`[[x,y,z]…]` metres) + `faces` (`[[i,j,k]…]` 0-based), with index/degeneracy validation. GUID-stable,
versioned/undo-able. New **△ Add mesh** tool (JSON input) in the Advanced cluster; also directly callable
by the AI command bar / `execute_ifc_code`. Verified objectively — `test_mesh.py` tessellates a pyramid and
confirms the extents (2×2 base, apex 2 m, ≥6 triangles), and the output round-trips through the real
web-ifc → Fragments converter into a valid fragment.

## v0.3.304 — Sloped-top walls: parapet slope / shed / gable (B3)

Walls can now have a **sloped top**. New `set_wall_slope` recipe rebuilds the selected wall's Body as a
**trapezoidal side profile extruded across the thickness** — a plain `IfcExtrudedAreaSolid` (no boolean, so
every geometry engine renders it), with the top rising from `start_height` (at the wall's start point) to
`end_height`. GUID-stable, versioned/undo-able. New **⟋ Slope wall top** tool (Advanced cluster). Verified
objectively, not by eye: `test_wall_slope.py` tessellates the result (`ifcopenshell.geom`) and confirms the
start end sits at ~2 m and the far end at ~4 m (a real rising slope, base at Z = 0), and the output was
round-tripped through the actual web-ifc → Fragments converter into a valid fragment (it renders). This was
the last item on the Master-Builder order of attack.

## v0.3.303 — Fix: `test_edit_undo` CI failure (read-only `/app`)

The S4 undo test (v0.3.298) failed the CI API gate with `PermissionError: /app` — it drives `/model/blank`,
which writes the source IFC under `IFC_DIR` (defaults to `/app/ifc`, read-only in the container). The test
now points `IFC_DIR` at a writable scratch dir (and cleans it up), per the container-readonly-`/app` gotcha.
Test-only change; no product code affected.

## v0.3.302 — Field-verified as-built dimensions + variance (G2)

Completes the LOD-500 data layer. New `record_asbuilt_dimension` recipe stamps a **field-measured**
dimension on the selection, the **design** value (if given), the **variance** (measured − design), and
whether it's **within tolerance** — into `Massing_AsBuilt​Dim` (`{Dimension}_Measured/_Design/_Variance` +
`WithinTolerance`). `asbuilt_summary` now also reports `with_dimensions` and
`dimensions_out_of_tolerance`, surfaced in the ✅ As-built (LOD 500) tool alongside a measure form. With
G1 (verify) and G3 (manufacturer/serial), the model can carry the full field-verified as-built record for
turnover. `test_lod500.py` extended.

## v0.3.301 — SECURITY: close an RCE escape in the A1 sandbox

An adversarial review of v0.3.300 proved the AST sandbox was escapable to full RCE **when the flag is on**:
exposing the real `ifcopenshell` module let a snippet reach its transitive imports as plain (non-dunder)
attributes — `ifcopenshell.os.system(...)`, `ifcopenshell.api.importlib.import_module('subprocess')`,
`ifcopenshell.api.inspect.builtins.eval(...)`, etc. Fixed by **never exposing a module**: the snippet now
gets a minimal **facade** carrying only the intended authoring callables (`ifcopenshell.api.run`,
`ifcopenshell.guid.new`) — bound functions with no attribute path back to a module. Added an
attribute-name **denylist** (defense-in-depth) that also blocks the `str.format`/`format_map` dunder-read
bypass and `model.wrapped_data`. `test_sandbox.py` now asserts all 12 proven escape payloads are blocked
while the legitimate `ifcopenshell.api.run` authoring path still works. (The feature remains off by default.)

## v0.3.300 — Sandboxed `execute_ifc_code` escape hatch (A1)

The unbounded authoring escape hatch — run a small ifcopenshell snippet against the model for what the fixed
recipe registry can't express. Defense-in-depth, treating this as arbitrary-code territory:
**off by default** (raises unless the operator sets `AEC_ALLOW_IFC_CODE=1`, thereby accepting the risk); an
**AST allowlist** that rejects `import`, `def`/`class`/`lambda`, `while`/`with`/`try`, `del`, decorators,
dunder access (`__class__`/`__globals__`), and reflection/IO builtins (`open`/`eval`/`exec`/`getattr`/
`__import__`/`type`…) before anything runs; and a **curated namespace** exposing only `model`, `ifcopenshell`,
and a small safe builtin set. New `sandbox.py`, an `execute_ifc_code` recipe (runs through the versioned,
undo-able, audited `/edit` path), a `GET /authoring/capabilities` probe, and an **⚡ Run IFC code** tool in
the Advanced cluster. `/edit` now returns clean 403 (disabled) / 400 (rejected) instead of 500.
`test_sandbox.py` covers ~18 rejection cases + the flag gate + a real authoring snippet.

## v0.3.299 — SketchUp-style drawing inference (E1)

Free-hand drawing now lands clean lines automatically. A new `inference.ts` module infers, as you place a
point, an on-axis (±X / ±Z), **parallel**, or **perpendicular** direction from the previous point (and the
previous edge) and snaps the point onto that inference line when the cursor is within ~6° — no need to hold
Shift. A hard geometry-vertex snap always wins, and Shift stays the manual hard ortho-lock. Pure,
unit-tested math (`inference.test.ts`, 7 cases). Builds on the existing endpoint/edge and grid snapping.

## v0.3.298 — Model undo / redo (S4)

Authoring now has a real undo stack. Every `/edit` already wrote a new versioned source IFC and left the
prior versions on disk, so undo is just restoring a prior version + republishing — GUID-stable, so
pins/RFIs/clashes survive. New `edit_history` sidecar stack (no schema change), `POST /edit/undo`,
`POST /edit/redo`, and `GET /edit/history`; the restored path is verified to exist and stay inside the
project's IFC directory. **↶ Undo / ↷ Redo** buttons in the Model tools rail reflect the server-side history
depth and republish on click. A fresh edit invalidates the redo stack. `test_edit_undo.py`. (The
`/edit-preview` ghosting half of S4 already ships.)

## v0.3.297 — MEP port-to-port connectivity + validation (W10-4)

Turns a pile of MEP segments/fittings into a connected logical network. New `connect_mep` recipe wires two
elements **port-to-port** (`IfcRelConnectsPorts`, using the first free port on each; raises when none is
free). New `mep.connectivity` validation report — ports connected vs open, port-to-port link count, and the
**dangling** (floating) elements whose ports are all unconnected — served at `GET /projects/{pid}/mep/
connectivity`. The 🔀 MEP systems tool now shows the connectivity summary, a two-step **Connect** flow (pick
one element → connect to a second), and isolates floating elements in 3D. `test_mep_systems.py` extended.
*Next: flow/sizing psets + coincident-port auto-connect.*

## v0.3.296 — Detail callouts on the plan (D5)

Closes the attach-a-detail → callout-on-the-drawing loop. The plan generator now draws an **NCS-style detail
callout** (a divided circle with a leader) on every element that carries an attached detail drawing
(`IfcRelAssociatesDocument`), plus a **DETAILS legend** keyed to each detail — distinct from the keynote
bubbles (which reference spec/classification codes). `drawing.plan_svg` gains a `details` toggle and returns
a `details` count; the callouts flow through to the issuable SVG sheet automatically. So: attach a detail in
the 🏷 Detailing tool → generate the plan → the referencing callout appears. `test_drawing.py` extended.

## v0.3.295 — Edition-scoped occupant-load factors (CODE-2)

The egress computation is now edition-aware, not just the citations. `egress_analysis`/`egress_from_model`
take an IBC `edition` and apply edition-scoped occupant-load factors — the one well-established Table 1004.5
change: **Business areas are 100 gross ft²/occ in IBC 2012/2015 vs 150 gross in IBC 2018+**. `code_analysis`
resolves the jurisdiction's adopted edition first and threads it in, so a project in a 2015-edition
jurisdiction computes a *higher* occupant load (and required egress width) than the 2021 baseline, exposed
through the existing Jurisdiction field. The egress result carries `code_edition`; the default (no
jurisdiction) keeps the current-edition factor. Facts of law only. `test_code_analysis.py` extended.

## v0.3.294 — Docs, landing page & demo refreshed to the current product

Housekeeping so the outward-facing surfaces match what shipped. The **README**, the **in-app guide**
(`docs/guide.html`), and the **Pages landing** (`docs/index.html`) are reframed around the current
end-to-end capability — model from scratch → generate a permit-ready construction-document set → pre-check
code → hand over field-verified as-built data — with new sections/tutorials for the CD set, code &
permit-readiness, and LOD-500 turnover. Pre-existing competitor comparisons were removed (capabilities are
described directly); interop/connector/standard names kept. The **Pages demo snapshot** (`demoData.json`)
was regenerated against the current API (932 fixtures). The **roadmap** was re-archived: this session's
shipments moved to `roadmap-completed.md`, active roadmap re-prioritized (CODE-2 → D5 → W10-4 → …).

## v0.3.293 — Model Health scorecard gains a Code & permit-readiness lens

The composite **Model Health** scorecard now includes a fifth lens — **Code & permit readiness** — sourced
from the D8 approvability pre-flight (egress, door widths, occupancy classification, substantiated rated
assemblies). It scores by the pre-flight pass rate and headlines the checks still to fix, so the single
"is my project healthy?" number now reflects permit-readiness alongside integrity, ISO-19650 information,
clash coordination, and verified-as-built. Weights rebalanced to include it; the lens shows n/a (excluded
from the mean) when no gating checks apply. `test_model_health.py` updated.

## v0.3.292 — Fix two debug-audit findings in the D6 manual + D8 pre-flight

A post-release debug audit caught two wrong-result bugs (no crashes), now fixed with regression tests:
- **Project manual (D6) missed layer-set materials.** `specmanual._element_materials` (was `_element_material`)
  now resolves an `IfcMaterialLayerSetUsage` → `IfcMaterialLayerSet` → its layer materials (and profile /
  constituent sets + material lists), so a real wall's materials actually reach Part 2 Products instead of
  silently yielding nothing. Returns all distinct names, not one.
- **Approvability (D8) occupancy check always passed.** It counted a space's free-text `LongName` (which our
  own `add_spaces` always sets to "Room NN") as evidence of occupancy classification, so it could never fail.
  It now gates strictly on `Pset_SpaceOccupancyRequirements.OccupancyType`.

## v0.3.291 — Manufacturer / serial for the O&M / turnover layer (G3)

Completes the LOD-500 data layer. New `set_manufacturer_info` recipe stamps the standard IFC
`Pset_ManufacturerTypeInformation` (Manufacturer / ModelLabel / ProductionYear) and
`Pset_ManufacturerOccurrence` (SerialNumber / BarCode) on the selection — the data that round-trips to
COBie and asset/CMMS systems for O&M and turnover. Only non-empty fields are written; GUID-stable; a bad
GUID never aborts the batch. `asbuilt_summary` now also reports `with_manufacturer` / `with_serial` counts,
and the ✅ As-built (LOD 500) tool gains a manufacturer/serial stamp form. `test_lod500.py` extended.

## v0.3.290 — Approvability pre-flight: is the model permit-ready? (D8)

A plan-reviewer pre-flight checklist over the model, mirroring what a reviewer checks first. New
`codecheck.approvability` runs five cited checks — egress capacity (IBC 1005.3), egress door clear width
≥32 in (IBC 1010.1.1 / A117.1), two-exits-where-load>49 (IBC 1006.2), occupancy classification on spaces
(IBC Ch.3), and fire-rated assemblies substantiated by a UL/GA classification or attached detail (IBC Table
721) — returning pass/fail/na/info per check plus a readiness score. New
`GET /projects/{pid}/codecheck/approvability` and a **✅ Approvability pre-flight** viewer tool that lists
the checks and isolates flagged elements in 3D. A pre-check assist — not a certified review or a guarantee
of approval. `test_approvability.py`.

## v0.3.289 — 3-part MasterFormat project manual — the spec book (D6)

Closes the loop from "classify an element + attach its detail" to "a spec section writes itself." New
`specmanual.py` groups the model's elements by their MasterFormat work-result classification into CSI
**divisions → sections**, each framed in SectionFormat 3-part shape: **Part 1 General**, **Part 2 Products**
(the element types + materials actually in that section), **Part 3 Execution** (the installation
instructions attached via `IfcRelAssociatesDocument`, or a manufacturer-instructions fallback). New
`GET /projects/{pid}/spec/manual` (structured) + `/spec/manual.txt` (downloadable outline) and a **📖 Project
manual** viewer tool. A pre-check starting point — the real manual is authored by the spec writer.
`test_specmanual.py`.

## v0.3.288 — Clear the critical dev-dependency advisories (vitest 3, happy-dom 20)

Bumped the two dev/test dependencies carrying critical Dependabot advisories — `vitest` ^2.1.9 → ^3.2.6
(resolved 3.2.7) and `happy-dom` ^15.11.7 → ^20.8.9 (resolved 20.10.6) — clearing 4 critical + several high
alerts. Both are test-only (the runner and its DOM), never shipped to production, so real-world exposure
was low; this is hygiene. Verified the full web test suite (13 files / 79 tests) still passes on the new
majors, plus typecheck + build + bundle budget. (Remaining Dependabot items are transitive build tooling —
`tar`/`esbuild`/`glib` — for a follow-up.)

## v0.3.287 — Harden download filenames (defense-in-depth)

A security pass over this session's new endpoints came back clean; this applies its one hardening note.
The DXF/PDF drawing endpoints interpolate user-supplied `axis`/`direction`/`number`/`sheet` into the
`Content-Disposition` filename. Those are now whitelisted to `[A-Za-z0-9._-]` (`_safe_name`/`_safe_filename`)
so a crafted value can't break out of the filename quoting. Self-reflected only (no cross-user/stored
vector) and the response bodies are inert data files — this is precautionary, not a fix for an exploit.

## v0.3.286 — Edition-aware code analysis: cite the jurisdiction's adopted IBC (CODE-3)

The code-analysis summary now uses CODE-1: pass a `jurisdiction` (US state) and it resolves the adopted
**IBC edition** and names it throughout — the headline badge shows "IBC 2021", the citations read "IBC 2021
Table 506.2 …", and the disclaimer records the code context ("IBC 2021 (CA adoption, as-of 2024)"). With no
jurisdiction it uses the national baseline and prompts for one. The 🏛 Code-analysis tool gains a
**Jurisdiction** field that re-checks edition-aware in place. `GET /codecheck/analysis?jurisdiction=…`. Still
a pre-check assist — verify the edition in force with the AHJ.

## v0.3.285 — Jurisdiction code context: adopted-edition catalog (CODE-1)

The substrate for edition-aware code checking. New `codes.py` encodes only facts of law + published-edition
metadata: the model-code **families** (IBC/IRC/IECC/IFC/IPC/IMC/IEBC/IgCC/A117.1) and their editions (the
I-Codes publish on a fixed 3-year cycle), plus `resolve(jurisdiction)` → the adopted editions for a US
state, falling back to a documented national baseline when not seeded. Every result carries a mandatory
**"verify with the AHJ"** note and an as-of year — the shipped seed is a dated starting point to extend from
authoritative sources, never an authority (adoptions change each cycle and by local amendment). New
`GET /codes/families`, `/codes/adoptions?jurisdiction=…`, `/codes/seeded`, and an **Adopted codes** lookup
in the 🏛 Code-analysis tool. Copyright-safe by design: facts and section numbers only, no code prose. This
unlocks the later edition-aware citation work (thread `code_ctx` through the checks).

## v0.3.284 — Authoring guardrails: reject broken edits before they touch the model (E8)

The reliability edge — a novice can't produce invalid IFC. New `guards.py::precheck` runs params-level,
name-based rules over any recipe: coordinates must be finite [E,N] pairs, a line's endpoints must differ
(no zero-length walls), physical dimensions must be positive and finite, integer counts ≥ 1, LOD-stage in
range, and required host/target references present. **`apply_recipe` now enforces the gate** — a broken
edit raises a clear message and never writes a file (verified against 49 recipe-exercising tests; it
rejects nothing legitimate). Errors block; suspicious-but-legal inputs (an implausibly large dimension →
likely unit slip, a non-standard phase) surface as **warnings**. New `POST /projects/{pid}/edit/precheck`
lets the UI warn *before* committing, and the AI command bar now prechecks each step (blocks on errors,
confirms through warnings). `test_guards.py` covers the rules and the enforcement path.

## v0.3.283 — Progressive-disclosure toolbar: fabrication tools behind an "Advanced" toggle (E4)

Lowering the barrier to entry: the Model tools rail now shows only the everyday authoring + drawing tools
by default (rooms, furnish, types, groups, phasing, query, LOD, as-built, plans/sheets/schedules/sections).
The LOD-350/400 **fabrication + detailing** tools — steel base plates & shear tabs, rebar cages, MEP
fittings, curtain wall, and the detailing/auto-detail tools — tuck behind a **🔧 Advanced fabrication
tools** toggle. A first-time modeler sees a simple toolset; the choice persists in localStorage, so power
users keep their fabrication tools open.

## v0.3.282 — Schedules on an issuable PDF sheet (finishes the CD set)

The computed door/window/room schedules now lay out on an issuable **ARCH-D sheet** (border + titleblock)
and render to PDF — the tabular half of the construction-document set as a submittable sheet, next to the
plan/section/elevation sheets. New `drawing.schedule_pdf` (columns per schedule, row truncation guard),
`GET /drawings/schedule.pdf?kinds=…`, and a **⤓ Schedules sheet (A-601 PDF)** viewer tool. The titleblock
draw was factored into a shared `_titleblock_pdf` helper reused by the plan and schedule sheets. With DXF
(v0.3.281) this completes the near-term CD-set slices.

## v0.3.281 — DXF export for plans, sections & elevations (CAD interchange)

The drawing set now exports to **DXF** so the linework opens in any CAD tool. A hand-written, dependency-free
R12 DXF writer (`dxf.py` — POLYLINE entities, no library, no license exposure) serialises the same
world-placed polylines the SVG views use: `plan_dxf` / `section_dxf` (auto-centred cut) / `elevation_dxf`
on named layers (PLAN / SECTION / ELEVATION). New `GET /drawings/plan.dxf`, `/section.dxf`, `/elevation.dxf`
endpoints and **⤓ DXF** buttons alongside each view in the Sections & elevations tool. `test_dxf.py` covers
the R12 envelope, closed-loop detection, degenerate-skip, and world placement.

## v0.3.280 — Fix: S3 structured-output schema (LLM authoring path) + apply-all recovery

Two follow-ups to the S3 command bar. (1) The plan schema declared each step's `params` as an open
`{type: object}`, which Anthropic's strict structured outputs reject (every object must set
`additionalProperties: false`) — so a keyed request would 400 and silently fall back to the keyword
baseline, meaning Claude multi-step planning never actually ran. `params` is now a JSON **string** the
model fills and `_coerce_params` parses (tolerant of both string and dict, so the keyword path and tests
are unaffected); every object in the schema is closed. (2) **Apply-all** now recovers from a mid-chain
failure: because earlier edits already advance the source IFC but defer their republish to the last step,
a failure part-way used to strand them unpublished — it now republishes what applied and reports
"stopped after N/M steps" instead of leaving the model in a committed-but-unconverted state.

## v0.3.279 — LOD-500 as-built verification (G1)

BIMForum defines LOD 500 as a *field-verified as-built* reliability attribute — with **no** geometric
requirement — so we support it as a data layer over the geometry. New `verify_asbuilt` recipe stamps
elements with `Massing_AsBuilt` (Status=VERIFIED + VerifiedBy / VerifiedDate / Method / Note provenance),
and `asbuilt_summary` reports **LOD-500 readiness** (share of elements field-verified, broken down by
method: field-measure / laser-scan / total-station / photo / submittal / inspection). New
`GET /projects/{pid}/lod500` endpoint and a **✅ As-built verify (LOD 500)** viewer tool — stamp the
selection, watch readiness climb. GUID-stable, round-trips as a Pset. `test_lod500.py` covers the stamp,
method fallback, bad-GUID skipping, and readiness math.

## v0.3.278 — AI command bar S3: Claude multi-step authoring + one-click Apply all

The natural-language command bar ("type what to build") now plans with Claude when an Anthropic API key
is set — a single instruction like *"a 5×4 m room at 0,0"* becomes an ordered **multi-step plan** (four
walls), and *"add three columns along the north wall"* resolves without exact coordinates. New
`nl_ai.plan()` builds the plan against the shared `RECIPE_SPECS` schema and **re-validates every step**
through the same `validate_call` guardrail as the keyword path before it reaches you — the model never
writes anything, never invents GUIDs (host/target elements come from the current selection), and
destructive recipes are withheld from it entirely. No key → the deterministic keyword baseline, unchanged.
Multi-step plans get a **✓ Apply all N steps** button that chains the edits and republishes the model
once instead of per step. The paid path is rate-limited; any LLM hiccup falls back to keyword parsing,
never an error. New `test_nl_ai.py` covers the plan assembly, context-fill, and fallback.

## v0.3.277 — Fix: align room tags & callouts with the world-placed drawing linework

Follow-up to v0.3.276. The bake fix moved section/plan linework into world coordinates, but the two
annotation builders — `space_tags` (room tags) and `element_callouts` (door/window callouts) — still
read element geometry in *local* coordinates, so their label centroids collapsed onto each element's
own origin and no longer sat on the linework (every off-origin room tag stacked at 0,0). Factored the
world-coords setup into a shared `_world_settings()` helper and applied it to both builders, so tags and
callouts land on the elements they label. Regression coverage added to `test_sections.py` (off-origin
model: tags/callouts must fall within the linework bounds, not at the origin).

## v0.3.276 — Sections & elevations in the UI + world-placement fix for all drawings

The section and elevation SVG generators existed server-side but were unreachable — added a **📐 Sections
& elevations** tool to the viewer's drawing rail: cut sections (X–X / Y–Y) and projected N/S/E/W
elevations, true linework from the model geometry. The section cut now **auto-centres** on the model
(`section_svg(offset=None)`) so it lands through the building instead of the world origin — no coordinate
to guess.

**Fix (affects every drawing):** the geometry bake fed the plan/section/elevation/sheet generators
element meshes in *local* coordinates — each element's ObjectPlacement wasn't applied, so anything not
authored at the origin collapsed onto (0,0) and overlapping elements stacked. `bake()` now sets
`use-world-coords`, so all 2D output places elements where they actually are. Plans, sections, elevations,
and composed sheets of any real (off-origin) model are now correct. New `test_sections.py` guards the
auto-centre + world placement.

## v0.3.275 — Fix: code-analysis occupancy group now resolves for every occupancy label

The v0.3.274 code-analysis summary looked up the occupancy group in an exact-match dict keyed on
`"Business"`/`"Assembly"`/…, but the space-mix labels carry qualifiers and synonyms
(`"Assembly (unconcentrated)"`, `"Educational (classroom)"`, `"Industrial"`, `"Parking"`, the
`"Business (assumed)"` default) — so 6 of 13 labels silently fell through to group **"—"**. Replaced the
exact dict with an ordered **substring** matcher (`_occ_group`) so those resolve to A/E/F/S/B correctly;
accessory/utility spaces (no standalone group) still return blank by design. Regression coverage added.

## v0.3.274 — Code analysis: permit-set G-series code summary

The IBC **code-analysis summary** a permit set carries on its G-series code sheet — now computed straight
from the model. `codecheck.code_analysis()` assembles occupancy classification (inferred from the space
mix or set explicitly), construction type, gross area + story count, the **computed occupant load + egress**
(reused from the occupancy/egress pre-check), and the governing sections for allowable area/height
(Table 506.2, §504, §506.3) and element fire ratings (Table 601/602). New `GET /projects/{pid}/codecheck/
analysis` endpoint (occupancy_group / construction_type / sprinklered inputs) and a **🏛 Code analysis**
tool in the viewer's QA rail that lays it out as a code-sheet block. Pre-check assist that cites sections —
verify allowable area with the AHJ; not a certified review.

## v0.3.273 — Security: ReDoS-harden the NL command-bar regexes

CodeQL flagged 5 `py/polynomial-redos` alerts in the natural-language authoring parser (unbounded `\d+` /
`\s*` runs in `nlauthor.py`). Bounded every quantifier (`\d{1,9}(?:\.\d{1,6})?`, `\s{0,6}`) so the parse
is linear on any input — no catastrophic backtracking. Parsing behaviour unchanged (`test_nlauthor.py` green).

## v0.3.272 — Fix: IFC2x3 MEP browser crash + degenerate-input guard

From the post-release debug worktree:

- **IFC2x3 MEP browser crash.** `mep_summary` called `model.by_type("IfcDistributionSystem")`, which *raises*
  on an IFC2x3 model (that class is IFC4+) — and legacy MEP models are commonly IFC2x3. It now degrades to an
  empty result via a schema-safe `_by_type` helper (matches the `energy.py` pattern).
- **Coincident start/end points** in `add_wall`/`add_beam`/`add_rebar`/`add_mep_run`/`add_railing`/
  `add_curtain_wall` produced an opaque "only finite values are allowed" placement crash (zero-length axis).
  They now raise a clear `ValueError("start and end points must differ")`.

Guarded by additions to `test_mep_systems.py` (IFC2x3) and `test_curtainwall.py` (zero length).

## v0.3.271 — Natural-language authoring command bar (the low-barrier way in)

**Type what you want to build.** A new **✨ command bar** at the top of the Author panel turns plain English
into modelling — "add a 3 m wall from 0,0 to 5,0", "put a window in the selected wall", "steel column W14x30
at 6,6", "set LOD 350 on the selection", "add 6 rooms". The instruction is mapped to a **validated plan** of
`{recipe, params}` and shown for **confirmation** — nothing is written until you click Apply, and each step
runs through the normal GUID-stable `/edit` path (audited, undoable). Destructive ops (delete) require a
second confirm.

This is the deterministic **no-API-key baseline** (regex + keyword matching, unit-normalized dimensions
mm/cm/ft/in → metres, coordinate + section/LOD/phase parsing, selection + active-storey context) — so it
works for everyone with zero setup. It's also the foundation (shared `RECIPE_SPECS` table + `validate_call`
guardrail) for the LLM tool-use path next, and the first slice of the AI-authoring moat validated by the
Nonica/Arcol competitor research. Engine `nlauthor.py` (`interpret` / `validate_call` / `RECIPE_SPECS`);
`POST /projects/{id}/ai/author` (interpret-only). `test_nlauthor.py` green.

## v0.3.270 — Wave 11 · B6: curtain-wall systems

Completes the B6 domain-geometry catalog. **🪟 Curtain wall** authors an `IfcCurtainWall` along a line that
**aggregates** a real framing grid: vertical **mullions** + horizontal **transoms** (`IfcMember`, MULLION)
bounding **glazing panels** (`IfcPlate`, CURTAIN_PANEL) on a bays×rows layout — one LOD-350/400 assembly,
contained in the storey, GUID-stable. Oriented to the wall axis; profile dims are unit-scale-correct
(verified identical real sizes on metre **and** millimetre models). Engine `curtainwall.py::add_curtain_wall`;
`add_curtain_wall` recipe + viewer tool. `test_curtainwall.py` green.

## v0.3.269 — Fix: authoring correctness on non-metre models + egress door width

Bug fixes from a parallel correctness-audit worktree (verified against real ifcopenshell):

- **HIGH — profile geometry on millimetre/imported models.** `geometry.add_profile_representation` SI-converts
  only the extrusion *depth*, not the profile — so profile dims must be authored in **file units**
  (metres ÷ unit_scale). `_rect_profile`, `connections._circle`, `steel.i_profile`, `rebar._swept_bar`, and the
  inline builders in `add_spaces`/`add_slab`/`add_mep_run`/`add_rebar`/`add_roof`/`add_covering` wrote raw
  metres — making every wall/column/beam/slab/MEP/rebar **1000× too thin** on a mm model (ifcopenshell's
  default and most imported IFCs). Our own blank models are metre-based (scale=1) so tests never caught it.
  Also fixed `add_rebar_cage` hard-failing ("cover too large") and `add_spaces` double-scaling its placement,
  both consequences on mm models.
- **MED — egress door width always 0.** `codecheck._door_width_m` read `Pset_DoorCommon.Width`, but authored
  doors store width in the `OverallWidth` **attribute** — so `provided_width_in` was 0 and egress adequacy
  meaningless. Now reads `OverallWidth` (unit-scaled).
- **MED — copies re-parented to the wrong storey.** `copy_element` (used by arrays) put every copy in the
  *lowest* storey; now inherits the source element's container.

New `test_unit_scale.py` authors into a forced-millimetre model and asserts column/wall/steel/duct/slab/rebar
carry correct **real** sizes + rebar no longer crashes + egress width > 0. All metre-model tests unchanged
(scale=1 makes every ÷scale a no-op).

## v0.3.268 — Wave 11 · B6 MEP fittings + edge-hardening

**MEP fittings & system browser.** `add_mep_fitting` authors an elbow (`BEND`), tee/cross (`JUNCTION`), or
size change (`TRANSITION`) as an `IfcDuctFitting`/`IfcPipeFitting`/`IfcCableCarrierFitting` at a point — with
the right number of connection **ports** and assignment to a named `IfcDistributionSystem` — the LOD 350/400
detailing that turns loose runs into a real system. A new **🔀 MEP systems** tool browses each
`IfcDistributionSystem` (segment/fitting/terminal counts + a connectivity signal: elements with unconnected
ports, plus anything unassigned), and **🔀 MEP fitting** places a fitting at the last-clicked point. Engine
`edit.py::add_mep_fitting` + `mep.py::mep_summary`; recipe + `GET /mep`. `test_mep_systems.py` green.

**Edge-hardening (parallel bug-audit worktree).** Fixed a real crash — `drawing.sheet_svg` raised
`KeyError('paper')` on an empty model / bogus storey (the empty-geometry branch of `plan_svg` omitted the
`paper`/`inner` keys `sheet_svg` reads); it now composes a border+titleblock sheet instead. Added
`test_wave11_edges.py` — ~30 edge/error-path assertions across all 8 Wave 11 modules (families, groups, rebar,
connections, drawing, detailing, rules, representations): bad-dims/blank-name raises, array-detach invariant,
keynote priority, rule idempotency + untested facets, LOD int-coercion, and the `sheet_svg` regression guard.

## v0.3.267 — Security: CodeQL remediation pass

Hardening from the GitHub CodeQL scan. Genuine fixes:

- **Open redirect (SAML ACS)** — `RelayState` now must be a *same-site absolute path*; protocol-relative
  (`//evil.com`) and backslash (`/\evil.com`) forms — which browsers resolve cross-origin — are rejected.
- **Authenticated arbitrary-file read (federated clash)** — the `disciplines` map may now only *select* from
  the project's own registered model paths (source IFC + appended discipline models); a client can no longer
  point it at an arbitrary server path.
- **Path-traversal defense-in-depth** — a `storage.safe_seg()` whitelist guards every `pid`/`mid` segment used
  to build a filesystem path (upload/publish/models/import), and `LocalBackend` now rejects `..`/absolute/NUL
  keys up front + requires the resolved path to stay under the storage root (`is_relative_to`).
- **ReDoS (SCIM filter)** — the `userName eq "…"` parser drops the ambiguous `\s*…\s*` and uses a bounded
  `[^"]*`, eliminating catastrophic backtracking.
- **DOM-XSS / sanitization** — escape the user-influenced label in the place-family status line; make the nav
  label escape global (`/&/g` + `<`).
- **Stack-trace exposure** — the readiness probe logs the DB error server-side and returns a generic
  "database unavailable" instead of the exception text.
- **Least-privilege CI** — `permissions: contents: read` added to the CI, lockfile, and Rust workflows.

Remaining CodeQL alerts are triaged false-positives (HMAC-SHA256 *token signing* — passwords use
`pbkdf2_sha256`; the signed-token cookie; the intentional admin-only **read-only** SQL console; the trusted-
HTML `resultNote` helper whose callers `escapeHtml` untrusted data; `DOMParser` XML that is never injected;
a `blob:` object URL) and are dismissed with justification.

## v0.3.266 — Wave 11 · B6: rebar cages + research-inbox roadmap

**Reinforcement detailing (LOD 400).** A new **🪝 Rebar cage** tool builds a real reinforcement cage in the
selected concrete column: **4 longitudinal corner bars + stirrups** at a spacing, offset by concrete cover,
as **swept-disk `IfcReinforcingBar`s** (a disk of the bar radius swept along its centreline — the correct way
to model reinforcement; straight for the bars, closed-rectangle for the ties), grouped with the column into an
`IfcElementAssembly`. Engine `rebar.py::add_rebar_cage`; `add_rebar_cage` recipe. `test_rebar.py` green.

**Roadmap — future research inbox.** Folded a 6-source research round (building codes, Unreal, and the
arcol/atomatiq/nonica competitor scan) into a new **🔮 Future** section as parked items: a copyright-safe
**jurisdiction-aware building-code library** (own the rules/facts + deep-link; license prose later), **Unreal
as an optional paid viz bridge only** (glTF export + three.js PBR are the on-mission wins), and competitor-
informed items led by an **MCP server over our edit-recipe engine** (validates Track A), real-time
multiplayer, and auto site/zoning ingestion.

## v0.3.265 — Wave 11 · B6: structural steel connections (LOD 350/400)

Bare steel members become **fabrication assemblies.** Two connection recipes turn LOD-300 members into
LOD-350/400 shop assemblies, on the selected element:

- **🔩 Base plate (steel column)** — an `IfcPlate` base plate + up to 4 anchor bolts (`IfcMechanicalFastener`,
  ANCHORBOLT) authored under the column, then grouped **with the column** into an `IfcElementAssembly`.
- **🔩 Shear tab (steel beam)** — a shear-tab plate + bolts at the beam end, assembled with the beam (a simple
  beam-to-column shear connection).

Each is real IFC geometry, GUID-stable, sized/placed from the member's own placement. This is the first
domain-catalog slice of Track B6 (steel connections → rebar cages → MEP fittings → curtain-wall). Engine
`connections.py` (`add_base_plate` / `add_shear_tab`); `add_base_plate` / `add_shear_tab` recipes.
`test_steel_connections.py` green.

## v0.3.264 — Wave 11 · C4: computed schedules (door / window / room)

The tabular half of a CD set — **schedules computed straight from the model.** A new **📋 Schedules** tool
lists the **door**, **window**, and **room** schedules (marks, widths/heights, types, levels, areas), pulling
values directly from the elements (door/window `OverallWidth`/`OverallHeight`, space `NetFloorArea`, the
containing level). Each is also a standalone SVG table for a schedule sheet. Engine `drawing.py::schedules` /
`schedule_svg`; `GET /projects/{id}/drawings/schedules` (JSON) + `/drawings/schedule.svg?kind=doors|windows|rooms`.
`test_drawing.py` extended (door 0.90 m / window 1.50 m captured, table SVG with header + grid, bad-kind 400).

## v0.3.263 — Wave 11 · C3b: sheet PDF export (the submittable deliverable)

**The payoff of the whole chain: a PDF you can submit to the AHJ.** A new **⤓ Sheet PDF (A-101)** tool renders
the issuable sheet — ARCH-D border + titleblock + plan **poché** + overall dimensions + keynote legend —
**directly to PDF** via `reportlab` (BSD, already a dependency; no SVG→PDF converter, no AGPL). Everything on
the sheet comes from the model: geometry from the authored profiles, keynotes from the Track-D spec codes.

Model → author → auto-detail (IBC flashing rules) → **PDF construction sheet**, all in the browser, offline,
GUID-stable, no Revit/Autodesk. Engine `drawing.py::sheet_pdf`; `GET /projects/{id}/drawings/sheet.pdf`.
`test_drawing.py` verifies valid PDF bytes (`%PDF`/`%%EOF`, non-trivial size, empty-storey safety). Next:
computed schedules on the sheet, sections/elevations, per-GUID cache.

## v0.3.262 — Wave 11 · C3: issuable sheets + titleblock

The plan becomes a **sheet you can issue.** A new **📄 Issue sheet (A-101)** tool composes an **ARCH-D
(36×24″) sheet**: a border, a **titleblock** (MASSING mark, project name, sheet title, sheet number, scale,
north arrow), and the plan placed in a **scaled viewport** (aspect-preserving) inside the drawing area. The
sheet title/number track the active level. This is the construction-document deliverable format — the same
sheet the door/window/room schedules and detail callouts will land on next.

Engine `drawing.py::sheet_svg` (plan refactored to expose its inner content + paper size for composition);
`GET /projects/{id}/drawings/sheet.svg?storey=&scale=&number=&title=`. `test_drawing.py` extended. Pure SVG,
no new deps; **PDF/DXF export is the next C-slice** (permissive svglib+reportlab — reportlab is already
present, BSD-licensed).

## v0.3.261 — Wave 11 · C2: dimensions & keynotes on the plan

The plan drawing now **reads the model's intelligence.** `plan_svg` gains two layers:

- **Dimensions** — overall width &amp; height dimension strings (witness ticks + metric text), so the plan
  carries real measurements, not just linework.
- **Keynotes** — every drawn element carrying a **Track-D classification code** (MasterFormat/UniFormat) gets
  a numbered keynote bubble, and a **keynote legend** maps each number to its code + title. The keynotes are
  generated *directly from the codes the Auto-detail rule engine attaches* — so the loop closes: place a wall
  → it gets a spec code → the plan shows the keynote and legends it. Both layers toggle off.

The 🖨 Generate plan tool automatically produces the richer sheet (dimensions + keynote legend). Pure
computation from the authored geometry + classifications — no geometry kernel. `test_drawing.py` extended
(dimension strings, keynote bubbles + legend from 04 20 00 / 05 12 00). Next C-slices: sections/elevations,
sheets + titleblocks, PDF/DXF.

## v0.3.260 — Wave 11 · C1: plan-drawing generator (SVG)

The first slice of the **construction-document set** — generate a schematic **plan drawing** (SVG) straight
from the model. A new **🖨 Generate plan (SVG)** tool (Grid &amp; Levels) opens a 1:100 plan of the active level:
walls/columns/slabs/roofs/spaces drawn as **class-styled poché** (a CSS class per IFC class controls
linework/fill), correctly scaled to paper millimetres with a viewBox and a title.

Because our geometry path is web-ifc→Fragments (ifcopenshell's OpenCASCADE engine produces no mesh here), the
generator takes the research-recommended optimization: it derives each footprint **directly from the authored
extruded-profile geometry** (profile polygon × placement × solid position) — deterministic, no geometry kernel.
Engine `drawing.py` (`plan_svg`); `GET /projects/{id}/drawings/plan.svg?storey=&scale=`. `test_drawing.py`
green. Next C-slices layer on dimensions, keynotes (from the Track-D codes), sheets/titleblocks and PDF/DXF.

## v0.3.259 — Wave 11 · D3+D7: the detail-rule engine + IBC window-flashing case

The brain that turns model state into construction-document content — and the headline worked case. A new
**✨ Auto-detail (rules)** tool (Grid &amp; Levels) runs an **IDS-shaped condition→content rule library** over
the model:

- **Rules** = an `applies` block (IFC entity, predefined type, a property on the element, or a
  relationship-context facet like "fills an opening in an **exterior** wall") + an `attach` block (the
  content bundle — classification codes + detail/instruction documents), written through the Track-D
  carriers, GUID-stable.
- **The worked case (D7):** a window in an exterior wall auto-gets the **IBC 2021 §1404.4 / ASTM E2112 /
  AAMA 711 flashing detail** (sill-pan → jamb → head shingle-lap sequence, as an installation instruction)
  + **MasterFormat 08 51 00** + **UniFormat B2020**. An interior-wall window gets nothing. Exterior doors get
  their sill-pan/jamb flashing (08 11 00); fire-rated walls get an assembly keynote (09 21 16, tag UL/GA no.).
- **The same rules validate as IDS QA** — a missing-keynote pre-flight lists elements that match a rule but
  lack their required code (author-time attach, QA-time check). Shown before/after in the tool.

Engine `rules.py` (`apply_rules` / `validate_rules` + seed rule library); `apply_detailing_rules` recipe +
`GET /detailing/rules/validate`. `test_rules.py` green. Pure ifcopenshell; code citations are facts.

## v0.3.258 — Wave 11 · Track D carrier layer: codes & detail documents

The join layer between the model and the construction documents — attach **keynote/spec codes** and
**detail/instruction documents** to elements, IFC-natively. A new **🏷 Detailing** tool (Grid &amp; Levels)
on the selected element:

- **Classification codes** — `IfcRelAssociatesClassification` for **UniFormat** (element → keynote),
  **MasterFormat** (work result → spec section), **OmniClass** (product), Uniclass. One element carries
  all three; each code is the join key a keynote, a schedule row and a spec section share.
- **Documents** — `IfcRelAssociatesDocument` → `IfcDocumentReference` → `IfcDocumentInformation` attaches a
  **detail drawing + installation instruction** (name, detail no. like `A-541/3`, URI). Deduped by
  identification so re-attaching a shared detail reuses one record.
- A **detailing inspector** reads an element's codes + documents back.

This is exactly what the (next) detail-rule engine writes when "exterior window → IBC §1404.4 flashing
detail + ASTM E2112 instruction + spec 08 51 00" fires, and what keynote/schedule/spec/drawing generation
will read. Engine `detailing.py` (`classify` / `attach_document` / `element_detailing`); recipes +
`GET /detailing/{guid}`. `test_detailing.py` green.

## v0.3.257 — Wave 11 · B2: parametric door & window generators

Doors and windows now get **real lining, frame and panel geometry** from IfcOpenShell's built-in parametric
generators (`geometry.add_door_representation` / `add_window_representation`) instead of a single flat box
proxy — a LOD 300→350 jump for near-zero geometry code. Every existing **◧ Add door** / **◨ Add window** tool
benefits automatically (parametric is the default); the recipes also accept an `operation` type
(`SINGLE_SWING_LEFT`, `DOUBLE_DOOR_SINGLE_SWING`, window `SINGLE_PANEL`, …). Lining depth is sized from the
host wall's thickness. The host is properly voided (`IfcRelVoidsElement`) and the door/window fills the
opening (`IfcRelFillsElement`); a generator failure falls back to the box proxy so authoring never breaks.
This is the real door/window geometry that the Wave 11 detail-rule engine will hang the IBC/ASTM flashing
detail + keynote + spec off. Engine in `edit.py`; `test_openings.py` green.

## v0.3.256 — Wave 11 · F0: the representation/LOD spine (foundation)

The architectural foundation the rest of Wave 11 hangs off — **one GUID-stable element that can carry
several view-keyed representations, plus an explicit LOD stage**. A new **📶 Level of Development** tool
(Grid &amp; Levels):

- **⚙ Establish drawing contexts** — `ensure_contexts` finds-or-creates the full view-keyed context tree:
  Model + **Plan** roots and the `Body`/`Axis`/`Box`/`Annotation`/`FootPrint` subcontexts (each tagged by
  `TargetView`) that construction-drawing generation and coarse↔fine display need. Idempotent.
- **LOD stage** — tag the selected element or a saved selection set **100 → 500** (`Pset_MassingLOD.Stage`).
  LOD is element *maturity*, not a geometry mode: the same GUID-stable element carries it as its geometry
  and data are refined. Advancing updates in place (no duplicate pset); a distribution overview shows the
  model's maturity at a glance.

Engine `representations.py` (`ensure_contexts` / `set_lod` / `lod_summary`); `ensure_contexts` + `set_lod`
recipes + `GET /lod`. `test_representations.py` green. This is track **F0** — everything downstream (parametric
door/window generators, the SVG drawing generator, detail-follows-LOD) keys off this spine.

## v0.3.255 — Wave 11 · power selection (IfcOpenShell selector DSL)

The first foundation piece of Wave 11 (LOD-400/500 authoring): a **🔎 Query (selector)** tool that runs the
IfcOpenShell **selector query language** over the model — `IfcWall` · `IfcWall, IfcDoor` ·
`IfcWall, Pset_WallCommon.FireRating=2HR` · `IfcElement, material=concrete`. Matches can be **isolated in 3D**
or **saved as a reusable selection set**. This is the power-selection primitive that bulk edits, schedule
scoping, and (next) rule-driven detail/spec attachment all build on. Engine `query_elements` in `edit.py`;
`GET /projects/{id}/query`. `test_selector.py` green (class, multi-class union, pset-value filter, limit
truncation, invalid-query 400).

## v0.3.254 — Wave 10 · W10-8: element phasing

The renovation / demolition-sequencing dimension needed for as-built and phased models. A new **🕐 Phasing**
tool (Grid &amp; Levels) tags elements **new · existing · demolish · temporary** — writing the widely-used
`Massing_Phasing.Status` code (NEW/EXISTING/DEMOLISH/TEMPORARY) so it colours, filters, and round-trips:

- Tag the selected element, or bulk-tag any saved selection set, from a one-click phase palette.
- A phase-distribution overview (counts + bars per status, plus unphased).
- **Isolate a phase in 3D** — pick a status to isolate just those elements.

Re-tagging updates the status in place (no duplicate pset); stale GUIDs are skipped; all GUID-stable. Engine
`set_phase` / `phase_summary` in `edit.py`; `set_phase` recipe + `GET /phasing`. `test_phasing.py` green.
(Design options reuse the W9-3 IFC5 property-override layers already shipped.)

## v0.3.253 — Wave 10 · W10-3: groups, assemblies & arrays

Three IFC-native ways to compose placed elements, all GUID-stable, via a new **🧩 Groups &amp; arrays** tool
(Grid &amp; Levels):

- **Group** (`IfcGroup`) — a named, non-geometric *set* of elements (a saved selection / system you can name,
  isolate, schedule). Members keep their own spatial containers; re-using a name adds to the group. Build one
  from any saved selection set; right-click an existing group to dissolve it (`ungroup`, members untouched).
- **Assembly** (`IfcElementAssembly`) — a real *part-of* whole: a named element that aggregates its parts
  (a braced frame, a curtain-wall unit, a pre-cast panel). The assembly is spatially contained; its parts hang
  under it via `IfcRelAggregates`.
- **Array** — rectangular parametric duplication: copy the selected element on an nx × ny grid at a fixed
  pitch (a bay of columns, a run of fixtures) in one action. Arrayed copies are independent occurrences —
  they don't silently swell the source's group or double-aggregate its assembly.

Existing groups/assemblies are listed with member counts; clicking one **isolates its members** in 3D. Engine
in `groups.py`; `create_group` / `create_assembly` / `array_element` / `ungroup` recipes + `GET /groups` and
`/groups/{guid}` inspectors. `test_groups.py` covers the relationships, inspectors, and recipe path.

## v0.3.252 — Wave 10 · W10-1: first-class type/family system

The box-only type path is now a real **family type system** — the Revit "type properties" surface, IFC-native.
A new **🧱 Family types** tool (Grid &amp; Levels) browses every `IfcTypeProduct` with its placed-occurrence
count, and lets you:

- **Create a custom type** — any type class, an optional sized box, a PredefinedType, and type-level
  property sets (`create_type`). Idempotent by (class, name).
- **Edit a type's size** — and the change flows to **every placed occurrence at once**. Occurrences share
  the type's `RepresentationMap` (via `IfcMappedItem`), so `edit_type_params` mutates the one box solid in
  place — GUID-stable, no re-placement, no lost pins/RFIs.
- **Assign a material layer set** — an ordered `IfcMaterialLayerSet` (name + thickness per layer) that
  occurrences inherit through the type (`assign_material_set`); re-assigning replaces cleanly.
- **Inspect** a type — class, PredefinedType, box dims, type Psets, material layers, and its occurrences.

All three edits run through the versioned, GUID-stable `/edit` recipe path and reconvert. This deepens the
existing `families.ensure_type`/`place_type` spine (shared box-representation builder) into the foundation the
rest of Wave 10 (parametric generators, groups, MEP systems, schedules) stands on.

## v0.3.251 — Wave 9 · W9-2b: round-trip code findings to BCF

The computed occupancy/egress findings can now become **trackable BCF issues** — a "📌 Promote to BCF
issues" button in the Occupancy &amp; egress result turns each below-min door, egress shortfall, and
two-exits-required space into a `codecheck` **BCF topic** (anchored at the element / building, so it shows
in the Issues panel and round-trips via `.bcfzip` with other openBIM tools). Idempotent — re-running a
review replaces the prior code findings rather than piling up. `POST /codecheck/egress/bcf`. Verified
live: an egress-shortfall finding becomes an anchored topic in the Issues list. (Completes W9-2's
"round-trip to BCF"; fire-separation between occupancies still needs space-boundary geometry and stays a
follow-up.)

## v0.3.250 — Wave 9 · W9-5: site logistics on the 4D timeline (first step)

SYNCHRO-style **site logistics** without leaving openBIM. New **🏗 Site logistics** tool places temporary
construction resources — cranes (with a reach ring), hoists, laydown yards, gates, fencing, haul routes,
trailers, parking — in project coordinates, each with a **schedule window**. They render as lightweight
3D glyphs and **time-phase on the timeline**: pick a date and only the resources active then are shown,
so the site plan becomes a constructability + safety rehearsal. `logistics.py` (`state_at` + `summary`) +
`Project.site_logistics` + `/logistics` (GET/PUT) + `/logistics/state` + a `LogisticsOverlay` +
`test_logistics.py`. Verified live: 3 resources → all active mid-schedule, only the open-ended gate after
the crane/laydown windows close; overlay renders glyphs + time-phases visibility. (The static, time-phased
first step; smooth **motion along paths** + swept crane-reach clash is the deferred follow-up.)

## v0.3.249 — Wave 9 · W9-6: generative fit-out (auto-furnish)

Generative design extends from massing into **fit-out**. New **🪑 Furnish spaces** tool (Tools ▸ Grid &
Levels) grids real furniture (`IfcFurnishingElement`) into every `IfcSpace`'s footprint with aisle
clearances — pick a template (desk / table / bed / sofa) and a per-room cap (0 = fill the footprint). It
reads each room's actual geometry, places items on a clearance-aware grid, and contains them in the right
storey, so the furniture is real openBIM that flows into QTO / BOM / COBie. `furnish_spaces` recipe +
`test_fitout.py`. Verified live: a blank 2-storey model → 8 rooms → 432 desks placed end-to-end. (The
headcount-program office space-planning generator is a documented follow-up.)

## v0.3.248 — Wave 9 · W9-4: semantic model graph (v1)

The property index answers attribute lookups ("this door's width"); it can't answer **relational**
questions. New **🕸 Related elements** tool builds a typed graph straight from the model's own IFC
relationships (`contained_in` · `aggregates` · `bounds` · `has_opening` · `fills` · `serves`) and, for
the selected element, returns its **multi-hop neighbourhood with cited relationship paths** — e.g. a wall
→ its level → everything else on that level. Click any related element to select it in 3D. `graph.py`
(`build` + `neighbors`) + `/graph` (stats) + `/graph/neighbors` + `test_graph.py`. Verified live: 117
nodes / 116 edges on a federated model; a wall reaches 38 related elements within two hops. (First,
model-half slice — spec/code-document ingestion and NL→graph query are a deliberate follow-up.)

## v0.3.247 — Wave 9 · W9-3: IFC5-style property-override layers

Brings IFC5's compositional model to the data layer **today**, without waiting on the upstream geometry
alpha. New **🧬 Property layers** tool: build an ordered stack of named, non-destructive **overlay
layers** (base → discipline → coordination → override), each carrying `{guid, pset, prop, value}`
overrides added from the selected element. They **compose over the model without mutating the IFC** — the
strongest enabled layer wins, disagreements surface as **conflicts** (the data-world twin of clash
detection, with provenance and both values), and **Resolve** shows the effective value + what it
overrides. **Bake** flattens the composition into a new GUID-stable IFC version (so pins/RFIs/clashes
survive) and republishes. `layers.py` engine + `Project.prop_layers` column + `/layers` (GET/PUT),
`/layers/resolve`, `/layers/bake` + an `apply_layers` recipe + `test_layers.py`. Verified live: a two-layer
FireRating conflict resolves to the coordination layer's "2HR" and bakes onto the wall.

## v0.3.246 — Wave 9 · W9-2: occupancy load + egress capacity (computed)

Code-checking goes from *presence* to *computation*. New **🏛 Occupancy & egress** tool (Coordination &
QA) computes, straight from the model's IfcSpaces + IfcDoors: **occupant load** per space (IBC 1004.5
area-per-occupant factors by occupancy — Business 1:150, Assembly 1:15, Residential 1:200, …) and the
building total; **required egress width** (occupant load × 0.15 in, IBC 1005.3) vs the **provided**
egress-door width, with an adequate / short verdict; a **32 in minimum clear door** check (IBC 1010.1.1)
with click-to-isolate; and a **two-exits-when-load->49** flag (IBC 1006.2), all with cited sections. It's
a **pre-check / design assist**, not a certified review (thresholds are encoded, not ICC prose; travel
distance is out of scope). `codecheck.egress_analysis` + `codecheck.egress_from_model` +
`/codecheck/egress` + `test_codecheck.py` extended. Verified live on a 40-space model (344 occupants,
required 51.6 in egress).

## v0.3.245 — Wave 9 · W9-1: property mapping / normalization

The missing **transform** verb between IDS-validate and COBie-export. Federated models name the same
concept differently (`Pset_WallCommon.FireRating` vs a vendor's `Fire_Rating`); IDS flags the mismatch
but nothing fixed it. New **🔧 Normalize properties** tool (Coordination & QA): **detect** every
pset/property actually on the model (with counts + samples), build remap **rules** (source Pset.Prop →
target Pset.Prop, with type coercion and move/copy semantics), **preview** the match counts (dry-run),
then **apply** — a GUID-stable `map_properties` edit recipe rewrites the IFC and republishes, so pins /
RFIs / clashes survive. `propmap.py` engine + `/propmap/detect` + `/propmap/plan` endpoints +
`test_propmap.py`. Verified live: `Pset_WallCommon.ThicknessMm` → `Qto_WallBaseQuantities.Width` across
12 walls (source removed, target written, GUIDs preserved). First item of the Wave 9 research scan.

## v0.3.244 — Mobile UX polish (phone-viewport touch targets + nav)

Tuned the header for phones (≤560px): the workspace switcher becomes its own **horizontally-scrollable
row** (five tabs no longer wrap onto two cramped lines), header controls get **tappable ~36–40px touch
targets** (were 22–28px), and the ~200px project-name switcher is **clipped with an ellipsis** so the
project actions pack onto one line. Net: fewer, bigger, easier-to-hit controls and a cleaner nav — the
topbar drops from six cramped rows to five tappable ones, with no horizontal overflow. The verifiable
web/PWA slice of the mobile track (native iOS/Android builds still need a macOS+Xcode / Android-SDK CI
pipeline — see docs/mobile.md).

## v0.3.243 — RVT→IFC (APS) bridge hardening

The paid Autodesk Revit→IFC bridge is hardened: the `/import/rvt` endpoint now **validates input before
the cost gate** — a non-`.rvt` file or an empty upload is rejected with a 400 rather than proceeding
toward a billed conversion — and a new **`test_aps.py`** locks the full gate order (501 bridge-off →
400 wrong-type → 402 unconfirmed-cost → 400 empty → 502 stub-activity). The conversion itself remains a
correctly-gated stub: it can't be implemented generically (the Design Automation WorkItem arguments
depend on the operator's provisioned Activity), so it raises a clear "provision your Activity" error
instead of faking output. The free path (export IFC from Revit, or the pyRevit **Publish to Massing**
button) stays the recommended route.

## v0.3.242 — Command-center density toggle (compact / comfortable)

The role home dashboards (GC executive band, Developer/Finance/Design command centers) get a
**⊞ Comfortable / ⊟ Compact** toggle. Compact tightens card padding, grid gaps and KPI type so more of
the dashboard fits on one screen — no information is removed, just the whitespace. The choice persists
globally (a personal viewing preference, like the per-stage nav collapse memory). Clears the last
open item in the roadmap's UX/nav-density bucket.

## v0.3.241 — Modeling program, phase 5: edit-in-place (drag-to-move gizmo)

Elements can now be **moved by dragging**, not just by typing an offset. Turn on **Edit in place** (◈
in the model toolbar), select an element, and a Blender/Revit-style **transform gizmo** appears on it
with X / Y / Z handles; a translucent amber **ghost box** follows the drag for instant feedback, and a
live ΔE / ΔN / ΔZ readout shows the move. On release the world-space delta is mapped to the GUID-stable
`move_element` recipe and the model republishes — so the moved element keeps its identity and every link
(RFIs, issues, verifications) to it survives. Grid-snap applies to the drag; the gizmo re-attaches to the
element after the move so you can nudge it again. Camera orbit is suspended while a handle is dragged.

Verified live against the loaded federated model: the gizmo constructs, attaches its ghost, cleans up on
hide/dispose, and the world→recipe axis remap is correct (Δx→E, −Δz→N, Δy→Z). This completes the
in-browser modeling initiative's tracked backlog (P1–P6 + model browser, manage levels, selection sets,
and edit-in-place). Stretch/resize of parametric geometry remains a future enhancement.

## v0.3.240 — Modeling program: manage levels + named selection sets

Two model-management tools land in the rail. **Manage levels** (Tools ▸ Grid & Levels) lists every
storey with editable **name** and **elevation** fields — Save re-authors the IFC through the GUID-stable
`rename_storey` / `set_storey_elevation` recipes and republishes, so levels are finally editable, not
just addable. The storey listing now carries each level's **GUID** so edits target the right storey.

**Named selection sets** (Layers panel, the Navisworks / Bluebeam "search set" pattern) let you save a
search — by name, IFC class, type, discipline, or level — as a named set and **isolate** it in one click;
"Show all" clears the isolation. Sets persist per-project in the browser (a personal view aid, they never
touch the model). Verified live on a 108-element federated model: a "structural" set resolves to 75
elements, all 75 map to loaded fragment geometry and isolate, and show-all restores visibility.

## v0.3.239 — Modeling program: model-browser groupings + search

The model tree is now a proper **model browser**. A toolbar adds a **group-by** switch — **By level**
(the spatial default), **By discipline** (A/S/M/P/E/FP, using the index's own discipline classification
with an IFC-class fallback), **By IFC class**, and **By type / family** (instances under their type, the
Revit Project Browser view) — and a **search box** that filters every leaf by name, GUID, class, type,
or discipline across all groups, auto-expanding the branches that match so hits are visible without
hunting. Each group header shows its element count; clicking a leaf still selects by GUID.

Verified live against a 108-element federated model: all four groupings render with correct counts
(Structural 75 · Mechanical 24 · Plumbing 6 · General 3), searching "duct" narrows to the 6 matching
segments and auto-expands, clearing restores the full tree, and leaf clicks fire the GUID selection.

## v0.3.238 — Modeling program, phase 6d: docked Properties panel (Revit-style)

Properties used to appear in a **floating** aside on selection; it's now a **docked rail panel** — its own
📋 **Props** toggle in the Author cluster — the way Revit's Properties palette works. The panel leads with a
**Revit-style identity header**: the element name, its **Type** (the family/type it's an instance of), and
its class + level, above the instance parameters and property sets (attributes / quantities / editable
Psets / classification, all unchanged). When nothing is selected it shows a clear "select an element" prompt.
Esc / the ✕ clears the selection.

Verified live: the Props toggle appears in the Navigate / Author / Coordinate rail, the panel docks and
shows its empty-state, no console errors. Completes the rail's Author cluster (Tools/Draft + Properties).
Part of the left-rail redesign; the model-browser groupings, level rename, selection sets, and edit-in-place
are still open (see the roadmap).

## v0.3.237 — Modeling program, phase 6c: cluster the rail Navigate / Author / Coordinate

The left rail's toggles are now grouped into the three workflow clusters every reference tool uses (Revit,
BlenderBIM/Bonsai, Bluebeam): **Navigate** (Tree · Layers) · **Author** (Tools) · **Coordinate** (Clash ·
Issues), with a subtle divider/label between them (a thin rule in icon mode, the cluster name when the rail
is expanded). Each toggle's aria-label is prefixed with its cluster for screen readers. This completes the
core of the rail redesign — the model workspace now reads as a modeling+coordination cockpit rather than a
flat list of panels. Verified live: the three cluster labels render and grouping is correct.

## v0.3.236 — Modeling program, phase 6b: a dedicated Clash & coordination toggle

The clash/coordination engine was genuinely strong but **buried** inside a "Coordination & QA" accordion in
the Tools panel. It's now a **first-class rail toggle** (💥 Clash), modeled on Autodesk Model Coordination —
the left rail is now Tree · Layers · Tools · **Clash** · Issues.

The panel surfaces tools that already ship: **Run clash — all disciplines** (federated cross-discipline
across the layered models, with coordination KPIs — new / active / resolved / % reduction), a
**single-model check** (structure ✕ MEP/walls) for a model without appended disciplines, a **clash list**
where clicking a clash selects + zooms to it in 3D, **Coordination metrics** (open/closed, resolution rate,
by-discipline-pair, by-severity, reappearance), and **Open in Issues (BCF)** — every clash promotes to a
tracked issue. Backed by `/clash`, `/clash/federated`, `/clash/metrics`.

Verified live end-to-end: the Clash toggle appears, the panel builds, and a single-model check on a
framed+cored model found **1,422 clashes and created 200 BCF issues**. Phase 6b of the left-rail redesign;
next: a docked Properties panel (Revit-style type/instance) and Navigate/Author/Coordinate icon clustering.

## v0.3.235 — Modeling program, phase 6a: cut the duplicative rail sections

Starting the left-rail redesign (a modeling+coordination cockpit, grounded in how Revit, BlenderBIM/Bonsai,
and Bluebeam lay out their panels). The Model workspace's "Tools" panel had become an 11-section dumping
ground, four sections of which **re-plotted whole other workspaces**: Cost/Pay Apps, Schedule, Drawings (2D),
and Energy & MEP. A modeler coordinating geometry shouldn't scroll past pay-app tables to reach a tool.

Removed those four from the model rail — and deleted ~700 lines of their now-duplicate builder code — leaving
a compact **deep-link row** (💰 Cost → Construction · 📅 Schedule → Construction · 📐 Drawings → Drawings ·
⚡ Energy → Design) so they're one click away without cluttering the modeling surface. Nothing is lost from
the product; each still owns its real workspace. The rail now keeps only model-native tools: the Draft
authoring palette, Grid & Levels, Working origin, Models (federation), round-trip authoring, Coordination &
QA, and Exports.

Next in the redesign: a dedicated **Clash** toggle (surfacing the existing clash/coordination engine), a
docked **Properties** panel (Revit-style type/instance split), and re-clustering the rail icons
Navigate / Author / Coordinate.

## v0.3.234 — Modeling program, phase 3: author rooms/spaces

The backend `add_spaces` recipe (grid IfcSpace rooms over each floor's footprint) had no UI — you could
author walls and columns but not the **rooms** that drive the space schedule, COBie, gbXML, and area
take-offs. Added an **"➕ Add rooms / spaces"** button to the Grid & Levels section (next to the existing
"➕ Add level"): pick rooms-per-floor + ceiling height and it authors a real space schedule into the model.
Verified live: `add_spaces` authored 8 IfcSpace rooms (4 per floor × 2 floors) on a generated shell. With
level-add already present, the datum/space authoring gap the modeling audit flagged is now covered in the
UI. (Level rename / set-elevation deferred — they need per-storey GUID plumbing.) Phase 3 of the modeling
upgrade; next: edit-in-place (drag/stretch).

## v0.3.233 — Modeling program, phase 4: author-ready starting templates

The old sample models were three static `.frag` files you could only *look at* — they load without a
project, so authoring is impossible on them. The "New model from scratch" flow now opens a **template
picker** with four **author-ready** starting points, each opening as a real, editable IFC project in the
Model workspace with the Draft tools ready:

- **▦ Blank canvas** — 3 levels + a ground datum; draw everything from scratch.
- **🏢 Office bay** — a small framed structural bay (columns + beams + envelope) over 3 levels.
- **🏠 Residential floor** — one floor, double-loaded corridor with unit demising walls.
- **🏭 Warehouse shell** — a large single-storey enclosed clear-span shed to fit out.

Blank uses `…/model/blank` (P1); the rest are presets through the existing massing generator, so they
produce real geometry you then edit — not a locked demo. The picker is an accessible dialog (focus-trapped,
Esc). Verified live: the picker shows all four; the office-bay template generates a published, framed
3-storey editable model in ~1 s. (The static School/BasicHouse samples stay in the Open menu as view-only
reference.) Phase 4 of the modeling upgrade; next: grid/level/space authoring UI and edit-in-place.

## v0.3.232 — Modeling program, phase 2: remove the redundant authoring buttons

Killing the "excess buttons" from the audit. The viewer toolbar had **two ways to place the same element** —
the parameter-driven, snapping, per-level **Draft panel** (the real one) *and* an older click-to-place set
of toolbar buttons (Add wall / Add column / Add beam / Place family) that popped `prompt()` dialogs for
dimensions. The toolbar four were a redundant, clunkier duplicate of what the Draft panel does better, so
they're removed along with their whole legacy code path — `setPlaceMode`, `capturePlacePoint`,
`openFamilyPicker`, and the generic `pickFromList` picker (~90 lines). The Draft panel is now the single
authoring surface (as of P1 it opens front-and-centre on a new model).

The genuinely useful **selection-based** edit buttons stay (delete · add door/window to a selected wall ·
move · rotate · edit property · copy) since the Draft panel doesn't cover those. Net: fewer buttons, one
clear way to draw, no behaviour lost. Verified live: the four place buttons are gone, the selection-edit
buttons remain, and authoring via the Draft panel is unchanged. Phase 2 of the modeling upgrade; next: an
explicit Author/Review tool grouping, then grid/level/space authoring UI.

## v0.3.231 — Modeling program, phase 1: start a model from scratch

**A direction change: the web app becomes a real modeling tool, not just a viewer.** The audit was blunt —
the Model workspace was ~80% viewer/analysis, authoring was buried in an edit-gated Tools-rail sub-panel,
and there was **no way to start a model from nothing** (authoring required an existing IFC). The engine was
never the problem — the backend already has a ~30-recipe GUID-stable IFC authoring API (walls, columns,
steel, rebar, MEP, coverings, families, storeys, spaces, transforms). This ships the missing foundation.

- **Blank model from scratch.** New `generate_blank_ifc` + `POST /projects/{pid}/model/blank` author a
  minimal valid IFC — project/site/building, N **levels** (the datum you draw against), and a thin
  **ground-reference slab** for scale — with no building geometry. `POST` sets it as the source IFC and
  publishes it, so authoring works immediately.
- **"✏️ New model from scratch" flow.** One action creates a project, authors the blank model, lands you in
  the Model workspace, and **auto-opens the Draft/authoring panel** (`viewer.openAuthoring()`) so the
  drawing tools are front-and-centre instead of hidden. In the Open menu.
- Verified end-to-end against a live backend: new model → blank IFC published in ~1 s → Draft panel opens
  with the full element palette → an `add_wall` recipe authors a real wall with a stable GlobalId.

`CLAUDE.md` updated to make in-browser authoring a first-class goal (Blender/Bonsai becomes optional/interop,
not the required editor). This is phase 1 of a multi-release modeling upgrade — next: declutter the toolbar
into Author vs Review modes and remove the redundant legacy buttons; grid/level/space authoring UI;
author-ready templates; and edit-in-place (drag/stretch). Test: `test_generate` (blank model → 4 levels at
the requested height, ground datum only, valid spatial structure to author into).

## v0.3.230 — Collapsible nav stages with per-workspace memory

The left-nav destination rail groups first-class destinations by lifecycle stage (Plan & derisk · Build ·
Turn over · …). Those stage headers are now **collapsible** — fold a stage you don't use and it **stays
folded** next time you're in that workspace (persisted per `workspace:stage` in localStorage), so the rail
stays scannable as destinations keep growing. Each stage is a `<details>` with a disclosure caret; the
stage that owns the active destination always stays open regardless of the saved state, so you never lose
your place. Verified live: folding a stage persists and restores on return to that workspace, and other
stages are unaffected.

*(The "denser multi-card dashboard summary" half of this nav-density item remains a smaller follow-up.)*

## v0.3.229 — Accessibility pass on the new panels

An a11y audit of the panels added this cycle — the Finance command-center home, the module-relations
graph, the material editor, and the takt actual-vs-plan card — closing the gaps that screen-reader and
keyboard users would hit:

- **Named the graphics.** The module-relations SVG and the takt line-of-balance chart now carry
  `role="img"` + an `aria-label` (and the graph a `<title>`) describing the content — e.g. "Module-relations
  graph: 124 modules, 111 links" — instead of being an unlabeled blob. The Finance capital-stack bar gets an
  `aria-label` with the debt/equity split.
- **Labeled every form control.** The material editor's per-class colour, transparency, and name inputs and
  the graph's workspace filter now have `aria-label`s (previously anonymous); the material and takt data
  tables use `scope="col"` headers.
- Added a reusable `.sr-only` utility for visually-hidden accessible text.

All controls were already native buttons/inputs/selects (keyboard-reachable) — the gap was accessible
*names*, which are now present. Verified live: the graph SVG and all material inputs expose their labels.

## v0.3.228 — Finance home: a command-center landing for the finance persona

The Finance workspace opened straight into the proforma editor; now it lands on a **command center** —
the same pattern the Design and Developer personas already have. A new default **Home** tab (alongside
Proforma and Portfolio) summarizes the deal's financial picture: the returns from the latest saved
scenario (equity IRR — tinted good/warn by threshold — equity multiple, project IRR, yield on cost, NPV),
a **capital-stack bar** (senior debt vs equity with the split and a sources-≠-uses warning when it doesn't
balance, from Sources & Uses), and quick-launches to the Proforma editor, the Portfolio roll-up, and the
investor **memo** and **pitch-deck** PDFs. Everything degrades to a clear empty state before a scenario is
solved.

With this, all three non-GC personas have a role-tailored landing (Design = model-health/phase-progress,
Developer = real-estate register + deal returns, Finance = returns + capital + investor docs); the GC keeps
its on-schedule/on-budget PX dashboard.

New `listScenarios(pid)` client method + `openFinanceHomeTab()` in `main.ts`; a Home fintab in the finance
workspace. The home renders its **shell synchronously** (header, KPI placeholders, and the quick-launch
buttons) before the returns/capital data loads — so the panel is never blank even if the data request is
slow, offline, or fails; the returns and capital stack fill in afterward. Verified live: the shell appears
immediately, the capital stack renders from project Sources & Uses, the empty-state shows before a
scenario, and the quick-launches switch tabs / open the PDFs.

## v0.3.227 — Investor pitch deck, expanded: exec summary + capital stack + business plan

The generated investment **pitch deck** (`/investment-deck.pdf`) grew from 6 to **9 slides** toward a real
investor deck, all from the same live project data. Three new slides: an **Executive summary** (the thesis
in prose — total capitalization, the equity ask, the underwritten IRR/multiple over the deal horizon — plus
three headline metrics and highlights); a **Capital stack** (a stacked bar of senior debt vs equity with
loan-to-cost and the equity check, a clearer read than the Sources & Uses table); and a **Business plan &
value creation** slide that frames the **development-margin thesis** — build yield-on-cost vs the exit cap,
with the spread in bps as the value the development creates — followed by the entitle → build → stabilize →
exit strategy. Everything degrades gracefully when no proforma scenario is saved.

The deck now runs: title · exec summary · deal-in-numbers · market & positioning · Sources & Uses · capital
stack · development timeline · business plan · returns & the ask. Landscape, big-number slides, with site
photos from project attachments on the cover.

`report.investment_deck_pdf` in `report.py`. Test: `test_dev_budget` — the deck renders and now has 9
slides (was 6). Completes the §B6 developer-deliverable item (the memo + deck already shipped; this deepens
the deck to the roadmap's 10–20-slide investor-deck target).

## v0.3.226 — Module-relations graph: see how the ~180 config modules wire together

The config-driven modules form a data model; now you can see its shape. New `module_graph.build(registry)`
reads the module registry back as a graph — one node per module, one edge per cross-module link — where
edges come from **reference** fields (a record points at another module's record) and **rollup** fields (a
module aggregates a numeric field from records that point at it). Each node carries its in/out degree, and
the result surfaces the **most-referenced hubs** (the cost code tops it, referenced by ~23 modules) and the
**orphans** with no links. A `workspace` filter keeps a workspace's modules + the targets they reference so
the full ~180-node graph stays legible. Pure over the registry — no database.

Endpoint `GET /modules/graph?workspace=` returns the graph. A **🕸 Module Relations** destination in the
Design workspace renders it as an SVG: nodes on a ring laid out by workspace/section, sized by in-degree so
hubs stand out, reference edges solid and rollup edges dashed, hubs labelled, with a workspace filter and a
most-referenced summary. Hover any node for its links.

Engine `module_graph.py`; `routers/modules.py` endpoint; `portal/panels/moduleGraph.ts`. Tests:
`test_modules` — every module is a node, cost-impact reference edges target cost_code, cost_code tops the
in-degree ranking and its node degree matches its edges, workspace scope is a subset, only reference/rollup
edge kinds. **Completes the §M rendering/computational-depth bucket** (material editor v0.3.225 + this).

## v0.3.225 — Material editor: a per-project palette you can edit and re-apply

The M1 material/colour assignment (each IFC element class → an IfcMaterial + IfcSurfaceStyle colour, so
the model renders in real materials instead of flat grey) is now **editable per project**. New palette
helpers — `materials.palette_to_json()` / `palette_from_json()` / `merge_palette()` — expose the built-in
per-category table as JSON and let a project override any class's material name, category, colour, or
transparency; only the changed classes are stored, the rest fall back to the default.

Endpoints (design router): `GET …/materials/palette` returns the default table, the saved overrides, and
the **effective** merged palette; `PUT …/materials/palette` persists overrides to project storage; and
`POST …/materials/apply` loads the source IFC, re-runs the material/surface-style assignment with the
merged palette (in a tempfile — `/app` is read-only in prod), writes it back, and kicks the
convert→fragments reindex so the viewer shows the new colours. A **🎨 Materials** destination in the Design
workspace's Model & standards group renders the editable palette table (colour picker + transparency +
material name per class) with Save, Apply + republish, and Reset controls.

Engine `services/data/aec_data/materials.py`; `routers/design.py` endpoints; `portal/panels/materials.ts`.
Tests: `test_design_phase` — GET returns default + effective, PUT persists an override, GET reflects it
(unchanged classes keep the default), apply 400s with no source model.

## v0.3.224 — Actual-vs-takt production tracking: the LOB chart learns the real ascent

The line-of-balance takt plan (trades chasing floor-to-floor at a steady rate) now measures **actual
against plan**. New `takt.progress(plan, actuals)` compares each trade's actual floors-complete with the
floors it *should* have finished by that day, giving a **floor variance** (+ahead / −behind), the
**achieved production rate** (floors/week) vs the planned rate, and an on-takt / ahead / behind read for
each trade and the job overall. The lead trade's achieved rate vs the planned pace is the headline: is the
train ascending at takt? `takt_svg` gained an **actuals overlay** — each trade's real ascent drawn as a
dashed line against the solid plan, so plan-vs-actual reads at a glance.

Project endpoint `GET …/schedule/takt/progress` derives per-trade floors-complete from the GC
`schedule_activity` records (100% complete or an actual finish date), sizes the takt plan from the model's
storey count, and **bundles PPC** (Last-Planner reliability) so one payload drives a dashboard card showing
plan health + reliability together; `GET …/schedule/takt.svg` renders the overlaid chart; and a stateless
`POST /schedule/takt/progress` computes it from posted actuals. A **"Takt — actual vs plan"** card in the
Schedule panel shows the overlaid chart + a per-trade variance table (done/plan, variance, actual vs planned
floors/week) + overall status + PPC.

Engine `takt.progress()` + `takt_svg(actuals=…)`; `routers/research.py` endpoints; Schedule-panel card.
Tests: `test_research` — variance sign (ahead/behind/on-takt), achieved-rate math, overlay drawn, unknown
trades ignored, plus the project endpoint (floors-done from activities, clamped to storeys, PPC bundled) +
stateless endpoint. Closes the §R2/R4 production-analytics thread (planned LOB + JIT already shipped).

## v0.3.223 — Monte-Carlo the specialty risk discount → distribution of blended deal IRR

Closes the §U4 thread. The specialty **risk discount** (the U4 haircut that keeps a farm/energy operating
business from being underwritten like de-risked real estate) is now a **Monte-Carlo driver**, not a single
point. New `specialty.monte_carlo()` samples specialty params (`risk_discount`, produce prices, any dotted
path) across a distribution (normal / uniform / triangular, optionally clamped), blends each draw into the
deal's equity, and returns the **distribution of blended deal IRR and specialty-only IRR** — percentiles
(P5…P95), mean/std, P[metric ≥ target], and a histogram. It reuses the proforma Monte-Carlo sampler +
summary, so the readouts match the rest of the risk tooling, and it's reproducible under a fixed seed.

Answers the real question: *once the haircut and price volatility are uncertain, how much does the
farm/energy actually help — and how often does it hurt?* A harsher haircut band measurably lowers the
blended-IRR distribution. Endpoint `POST …/specialty/monte-carlo` (assumptions + variables + iterations +
targets); a **"Risk sim"** button in the Specialty panel runs 500 draws and shows the blended-IRR P5/P50/P95
+ P[≥15%] and the specialty-only spread.

Engine `specialty.monte_carlo()` (reuses `proforma.monte_carlo._sample`/`_summary` +
`proforma.sensitivity._set_path`). Tests: `test_specialty` — ordered percentiles + histogram, seed
reproducibility, target-probability readout, harsher-haircut → lower blended IRR, plus the endpoint
end-to-end. **The full §U underwriting-depth bucket (exit-cap comps · specialty P&L + ramp · blended IRR ·
Monte-Carlo risk) is now cleared.**

## v0.3.222 — Specialty assets modelled over time: multi-year P&L + production ramp + blended IRR

The on-site energy/vertical-farm business is now underwritten as an **operating business over time**, not
a single stabilised year. New `specialty.proforma()` runs a multi-year P&L where revenue and generation
**ramp** linearly from a start fraction to full output over `ramp_years`, while opex (grow-lights, labour)
runs at full load from year 1 — so the early years earn less, or lose money, before the business
stabilises (the honest picture of a startup ag/energy operation). It reports per-year rows (ramp %, revenue
+ offset, opex, net, cumulative), a **specialty-only IRR** (capex at t0, ramped nets, plus a terminal value
= stabilised net ÷ exit cap), and the payback year. All cash flows use the **risk-adjusted** (underwritten)
figures, so nothing is overstated.

New `specialty.blended_irr()` folds that business into the deal's **equity** cash flows and reports
**real-estate-only IRR vs blended IRR and the lift** — the answer to "does the farm/energy actually move
the deal return, net of its risk discount?" Endpoints `GET …/specialty/proforma` (query: years, ramp_years,
ramp_start, terminal_cap) and `POST …/specialty/blended` (solves the RE proforma from the posted
assumptions, then blends the saved specialty params). A **"P&L + ramp"** view in the Specialty panel charts
the year-by-year table, the specialty IRR/payback/terminal, and the blended-deal IRR lift.

Engine reuses the robust `proforma.returns.xirr`. Tests: `test_specialty` — ramp fractions + net rising to
the stabilised plateau, terminal = net ÷ cap, payback, slower ramp → lower IRR, blended lift + guards,
plus both endpoints end-to-end. *(Remaining §U4 thread: wiring Monte-Carlo sensitivity to the specialty
risk discount — next.)*

## v0.3.221 — Surface parking placed on the real parcel remainder (polygon-aware)

Generated surface parking now fills the **actual land the building doesn't use** instead of a fixed
strip stamped behind the plate. New pure `pack_parking(poly, bldg_w, bldg_d, n, …)` lays stalls in
double-loaded modules (two 5 m stall rows sharing a 7 m two-way drive aisle), sweeping the parcel's
bounding box and keeping a stall only when its whole rectangle is **inside the parcel polygon** (ray-cast
point-in-polygon) **and clear of the origin-centred building footprint** (plus a 2 m drive-apron buffer).
`generate_ifc` recentres the parcel on its bbox centre to share the building's frame, then places the
packed stalls as real `IfcSpace(PARKING)` on the Site Parking storey. On an irregular or tight parcel the
supply is now **parcel-bound** — you get the stalls the site can actually hold, not the number requested,
which is the honest feasibility answer. Rectangular-lot inputs with no polygon keep the legacy strip
(unchanged). Completes the A6 remainder (the shoelace footprint + inward setback offset shipped earlier).

Engine `massing.pack_parking()` + `massing._point_in_poly()`; wired through `routers/generate.py`
(passes `metrics["buildable_polygon"]`). Tests: `test_massing` — packer keeps stalls inside a 60×60
parcel and off the building box, supply is parcel-bound (asking for 100 000 returns what fits), triangular
parcel clips corners, degenerate inputs safe; plus an end-to-end `generate_ifc(parcel_polygon=…)` placing
stalls clear of the footprint.

## v0.3.220 — Generated frame follows the load path: per-floor column taper + lateral core

The structural advisor now shapes the *generated geometry* floor-by-floor instead of stamping one fixed
column everywhere. A column at level _i_ carries the floors above it, so its axial load — and thus its
cross-sectional area — grows toward the base; side length scales with **√(floors carried)**, floored at
400 mm and rounded to 50 mm zones (real frames taper in bands, not continuously). The advisor returns a
per-floor `column_schedule` (base = widest, top = narrowest) plus `base_column_mm`/`top_column_mm`, and
`generate_ifc` extrudes each storey's columns at that storey's section, so a tall building visibly narrows
its frame as it rises.

Alongside it, a **central lateral core**: when the recommended lateral system is a core (mid-rise and up),
the advisor sizes a reinforced-concrete core (~20 % of the floorplate, min 6 m) with wall thickness that
grows with height for drift control (250–900 mm), and the generator extrudes the service-core walls as
real shear walls at that thickness — not the thin default. Low-rise buildings (distributed shear walls /
braced bays) correctly get **no** central core. Sized on the real footprint at generate time. The proforma
massing summary now shows the taper (`cols taper 900→500 mm`) and the core (`6×6 m core, 400 mm walls`).

Engine `structure.column_schedule()` + `structure.lateral_core()`; wired through `routers/generate.py`
into `massing.generate_ifc(members=…)`. Tests: `test_structure` (taper monotonic base→top, √-load, 400 mm
floor, core thickens with height, 1-storey edge case), `test_generate` (endpoint returns the schedule +
core), `test_massing` (generated column X-extents taper 0.90→0.50 m; core walls extrude at 400 mm). Also
fixed a stale `test_massing` MEP assertion (the core adds a riser **and** a distribution main per floor).

## v0.3.219 — Desktop build: Windows installer (uvloop) — all three platforms now build

Final piece of the installer repair. With v0.3.218 the macOS + Linux installers built, but Windows
failed: `RuntimeError: uvloop does not support Windows`. `requirements.lock` is resolved on Linux (the
prod image + CI), so it pins the **Unix-only `uvloop`** (a `uvicorn[standard]` transitive) with no
platform marker — and it can't build on Windows. The desktop sidecar now installs the API deps from the
**unpinned `requirements.in`**, letting pip resolve per-platform: `uvicorn[standard]` drops uvloop on
Windows and keeps it on macOS/Linux. Prod reproducibility is unchanged — the hashed lock still governs
the API Docker image and the CI test gate; the desktop sidecar is a bundled per-platform binary. All
three installers (Windows `.msi`/`.exe`, macOS `.dmg`/`.app`, Linux `.AppImage`/`.deb`) now attach to
tagged releases.

## v0.3.218 — Desktop build: Python 3.12 to match the lock (completes the installer fix)

Second half of the desktop-installer repair. After v0.3.217 fixed the requirements *path*, the sidecar
step still failed: the workflow set up **Python 3.11**, but `services/api/requirements.lock` is
pip-compiled under **3.12** and pins `numpy==2.5.x`, which requires Python ≥3.12 — so 3.11 couldn't
resolve it (CI already uses 3.12, which is why CI stayed green). Bumped the desktop workflow's
`setup-python` to 3.12 to match CI and the lock. With v0.3.217's requirements-path fix, tagged releases
now build the Windows/macOS/Linux installers and attach them to the release.

## v0.3.217 — Fix the desktop-installer build (releases were empty drafts)

**Ops fix — restores the signed desktop installers on tagged releases.** The Desktop-release workflow's
"Build the backend sidecar" step still installed `services/api/requirements.txt`, which was renamed to
`requirements.lock` during the hashed pip-compile work (v0.3.198). Every tag since then failed that step
on all three platforms, so no Windows/macOS/Linux installers were built and each GitHub Release stayed an
**empty draft**. Fixed to install the hashed lock (`pip install --require-hashes -r requirements.lock`,
matching CI) and the un-hashed data reqs **separately** (pip forbids mixing hashed + un-hashed files in
one invocation). Also fixed the report-only `security.yml` pip-audit, which pointed at the same missing
file and so wasn't auditing the API dependencies at all. Tagged releases now produce installers again.

## v0.3.216 — Underwriting realism: validate the exit cap against sale comps

Deepens the underwriting guardrails (roadmap ① / §U). A going-out cap tighter than the market supports
silently inflates the reversion (value = NOI ÷ cap) and the whole IRR — the most common way a proforma
"pencils" on paper but not in reality. `underwrite.guardrails(result, comps=…)` now derives the
**cap-rate band from the deal's own `comparable` sale records** and flags the exit cap against it:
**high** when >50 bps below the tightest comp, **med** when below the band, **info** when inside it (and
silent when at/above the comp median — the conservative case). The solve result now surfaces `exit_cap`
in `returns`, and a new project-scoped **`POST /projects/{pid}/proforma/solve`** runs the comp-aware
guardrails; the Finance panel calls it automatically when a project is open, so the exit-cap flag appears
in the underwriting guardrails alongside the IRR/EM/spread/DSCR checks. Pure/backward-compatible: the
stateless `/proforma/solve` and no-comps projects are unchanged. `test_specialty` covers the band math
(high/med/info/silent), the rent-comp exclusion, and the end-to-end project-scoped endpoint.

## v0.3.215 — Test Fit yield optimization: plate-depth sweep + core-efficiency

Deepens the generative Test Fit optimizer (roadmap ① — deepest, highest-value bucket). **Plate depth is
now an optimize dimension.** `test_fit.optimize(…, depths=[…])` (or `targets.sweep_depth=True` for an
auto ×0.6–1.4 range) sweeps unit-mix × parking **× plate depth** and returns a **`depth_curve`** — the
best yield-on-cost, daylight efficiency, and core efficiency at each depth, plus the `best_depth_m` where
daylight-limited yield peaks **before a dark interior core starts eating rentable area** (Willis, *Form
Follows Finance*). New **`core_efficiency`** metric on every layout (share of the gross plate not lost to
the daylight-dark core — 1.0 on a shallow plate, falling as depth pushes area past the ~9 m daylight
reach), distinct from `efficiency` which also nets out the corridor. The Finance **📐 Test Fit** panel
gains a **"sweep plate depth"** toggle that renders the depth curve with the peak depth starred. Backward-
compatible: with no sweep the optimizer is unchanged (15 schemes, single depth). `POST /test-fit/optimize`
accepts `depths`; `test_testfit` covers the sweep, the curve, `core_efficiency`, and the shallow-beats-deep
daylight ordering.

## v0.3.214 — In-browser E57 reality-capture reader + roadmap consolidation

**In-browser E57 (ASTM E2807) reader.** E57 previously required an optional server-side `pye57`
conversion; now `.e57` laser scans decode **fully in the browser, offline** — honoring the
"viewer runs fully offline" non-negotiable. New `viewer/e57.ts` parses the 48-byte header, strips the
CRC-paged logical stream, reads the XML `Data3D` prototypes, and decodes the CompressedVector binary
for the common encodings (**Float single/double + ScaledInteger XYZ with optional RGB**, across one or
more data packets), centring on the bbox midpoint and stride-decimating to the render budget like the
LAS/LAZ path. Anything it can't decode raises a typed `E57Unsupported`, and `main.ts` **falls back to
the proven server converter** — so worst case is today's behavior, best case is no round-trip. Wired
through `referenceLoader` (new `e57` branch) and the Open menu. `e57.test.ts` builds synthetic E57
files (single-page, multi-page CRC-stride, ScaledInteger+RGB, Float) and round-trips them through the
reader. Closes the last data-layer item that was tagged "upstream-blocked."

**Roadmap consolidation.** `docs/roadmap.md` is now lean — the banner + a single, re-ranked
**"What's left"** master backlog (① generative-design depth · ② UX/perf · ③ interop spikes · ④
upstream-blocked · ⑤ deferred-by-decision · ⑥ non-goals), sweeping up every open item from every
archive/parking-lot section (A/U/R/M/L/D + each "*Next:*" sub-note). All shipped history moved to a new
**`docs/roadmap-completed.md`** so *what's left* is never buried under *what's done*.

## v0.3.213 — Two deferred items closed: capital-markets syndication connector + IFC5/IFCX write path

**(1) IFC5 / IFCX write path.** The IFC5 read path shipped earlier (tolerant JSON→element-index parser);
the write path was deferred as "waits on web-ifc / Fragments." That dependency only blocks *geometry*
authoring — the **data** layer (elements + property sets) is plain JSON and tractable now. New
`aec_data/ifc5_writer.py` inverts the reader: it serializes the model index to **ifcJSON**
(buildingSMART `{"type":"ifcJSON","data":[…]}`, full-fidelity — guid/class/name/type/storey + property
groups round-trip exactly) or **IFCX** (the OpenUSD-style node list; USD attributes are flat so property
groups collapse to one attribute set, values preserved). `GET …/model/export.ifcx?flavor=ifcjson|ifcx`
streams it; `openbim` now advertises **IFC5 in `ifc.write`** (not just read). `test_ifcx_write` round-trips
both flavors back through the reader and asserts the registry change. Geometry authoring still lands
upstream — this is the data write path, the inverse of what already reads.

**(2) Capital-markets syndication connector (ledger sync — never moves money).**
Closes the last deferred capital-markets item as a **flagged data connector** (the parcels/APS pattern):
export the investor cap table to a securitization / investor-management platform, without rebuilding the
regulated issuance stack. New `securities_bridge` serializes `capital.cap_table` into a neutral
**syndication package** (`schema: massing.syndication.v1` — fund summary + per-investor positions +
disclosures), served at `GET …/securities/package` and **always available offline** regardless of the
connector. When configured (`SECURITIES_PLATFORM_URL` + `SECURITIES_API_KEY`, admin-editable in
Settings), `POST …/securities/syndicate` pushes the package to the platform over stdlib `urllib` (a
generic authenticated REST target is implemented; named platforms raise an actionable error until wired).
**Scope guard — this connector never moves money:** it syncs the *ledger* (positions, ownership %,
recorded contributed/distributed totals) so the external platform's records match ours; capital calls,
distributions and transfers are executed by the licensed platform, not here. Every response carries
`moves_money: false` and the package a disclaimer. The Investors tab (proforma) gains a **Capital-markets
syndication** card: download the package JSON, see connector status, and sync when enabled. Status gate
uses `current_user`; the push requires **admin**. `test_securities_bridge` covers the disabled export,
the actionable 422, a stubbed generic push (positions only), and the unimplemented-target error.

## v0.3.212 — Cross-workspace deep-link (element → linked records) + FF&E classification
Two roadmap items. **(1) Reverse deep-link — element → linked records.** The portal already had the
forward direction (a record's "👁 Show in model" selects its tagged elements); the reverse was missing.
New `traceability.element_records(db, pid, guid)` scans every **pinnable** module and returns the records
tied to an element by GlobalId (its `element_guids` tag or `data.guid`) — RFIs, coordination issues,
change orders, field verifications, schedule activities, etc. — grouped by module. `GET
…/elements/{guid}/records`; the viewer's on-selection inspector now shows a **🔗 Linked records (N)**
section beside the 5D cost breakdown, so selecting an element in 3D surfaces every record that touches it.
Completes the record↔element round-trip. **(2) FF&E classification** (from the pics8 field scan): the
furnishing IFC classes (`IfcFurniture`, `IfcFurnishingElement`, `IfcSystemFurnitureElement`) now classify
to **MasterFormat Division 12 (Furniture / Furnishings — FF&E)**, so furniture takes off and procures
correctly — additive, no discipline-taxonomy change. `test_element_records` covers the cross-module
reverse lookup (a field-verification + an RFI on one element found across both modules) + the FF&E mapping.

## v0.3.211 — Model Health: one composite score over every model-quality check
The model-quality checks were spread across the Model Tools rail — Data QA, ISO 19650 KPIs, clash
coordination, verified-as-built — so a coordinator had to open four tools to know where the model stands.
New `model_health.py` **composes** them (it re-implements nothing) into a single **0–100 composite
score** with four graded lenses, each linking to the tool that acts on it: **integrity & hygiene**
(`model_qa` — duplicate GUIDs, overlaps, orphans, unenclosed, blanks, wrong-storey), **information &
delivery** (`bim_kpi` ISO 19650 KPI health %), **coordination** (`clash_intel` resolution rate), and
**verified as-built** (`verified_progress` verified-in-place % + trust gap). The composite is a weighted
mean over the lenses that have inputs; a lens with no inputs shows **n/a** and is excluded rather than
guessed, so the score is honest. New `GET …/models/health` (opens the source IFC for the hygiene lens
when present; the other lenses score from records + the published index, so it works without a parsed
model); a viewer tool **🩺 Model Health (all checks, one score)** heading the model-quality group with the
composite band + per-lens breakdown; and a Report Center **Model Health Scorecard** (PDF/Excel, health-by-
lens chart). `test_model_health` covers the composite math, the clean-model = hygiene-100 case, the
n/a-lens exclusion, and the HTTP endpoint. (Part C "first-class Model Health surface" — see `docs/roadmap.md`.)

## v0.3.210 — Wave 8 ③(b): schedule-linked verified-as-built progress (the trust gap)
Closes the last buildable Wave 8 item. Instead of trusting a self-reported "% complete", Massing now
rolls **element-level field verification** up to each schedule activity and surfaces the **trust gap** —
where the claimed percentage runs ahead of what has actually been verified in place (the OpenSpace /
Disperse / Buildots value proposition, done as pure software over the model we already hold). New:
- **`field_verification` module** — one GlobalId-anchored record per element, workflow = the verification
  state (`captured → verified / deviated → resolved`), with deviation (mm), method, photo and a link to
  its schedule activity.
- **`verified_progress.py` engine** — maps every element to the activity that builds it (the same hard-tie
  or class→trade→floor resolution as the 5D map), then computes per-activity **verified-in-place %** vs
  **claimed %** and the trust gap, worst-over-claim first, plus overall coverage. `seed_from_layout` turns
  an as-installed `layout.verify` result straight into verification records (in-tolerance → verified,
  out-of-tolerance → deviated); `layout.verify` now also returns the full per-point deviation list.
- **Endpoints** `GET …/verified-progress` + `POST …/verified-progress/from-layout`; a viewer tool
  **✅ Verified-as-built progress** (verified % vs claimed, trust gap, per-activity breakdown); a Report
  Center report **Verified-as-built Progress** (PDF + Excel, verified-vs-claimed chart). `test_verified_progress`
  covers the rollup math (claimed 80 % but 2/4 verified → 50 % verified, +30 trust gap), the class→trade
  fallback, the layout seeding, and the HTTP endpoint.

## v0.3.209 — Docs: Wave 8 in the in-app tutorial + the guide
Now that the Wave 8 field upgrades have shipped, the onboarding and guide teach them. `docs/guide.html`
gains **Tutorial 🛰️ · Coordinate, lay out & walk the as-built** (six steps: coordinate clashes into
grouped BCF issues, model-driven field setout CSV/DXF, the preliminary load takedown, the wrong-storey
model-QA check, the Construction Execution Plan, and the Gaussian-splat reality overlay) plus a nav link.
The in-app first-run **tour** copy is refreshed: the Open-model step now mentions point-cloud / GIS /
reality-capture overlays, and the Tools step names the field toolkit (coordinate clashes, field layout,
load takedown). Docs/tutorial only — no behavior change.

## v0.3.208 — Wave 8 ③(a): Reality-capture walkthrough (3D Gaussian splats) in the viewer
Walk the as-built reality against the design. The viewer now loads **3D Gaussian-splat** captures
(`.splat` / `.ksplat`, plus splat-PLY auto-detected by header) as a **view-only overlay** beside the BIM
model — the on-site phone/drone photogrammetry → splat that the 2026 reality-capture wave produces, co-
registered with the IFC and the LAS/LAZ point clouds we already read. Built on `@mkkellogg/gaussian-
splats-3d` (MIT): its `DropInViewer` drops into the existing three.js scene as a `THREE.Group` and self-
sorts each frame via `onBeforeRender`, so no render-loop changes were needed; it flows through the same
"open reference model" path (extensions + `accept` filter + federation registry), and its sort worker +
GPU buffers are torn down when the overlay is removed. **Offline-first** (our non-negotiable): the library
and its **inline-blob sort worker** are bundled — no CDN — and the scene parses from an in-memory object
URL, never the network. The library is **lazy-loaded as its own chunk** (252 KB / 66 KB gzip), fetched
only when a user actually opens a capture, so the eager app shell stays within budget (179.7 KB < 220 KB).
`SharedArrayBuffer` is off (no COOP/COEP header requirement); CPU sort for widest device support. Note: the
blob-URL worker needs `worker-src blob:` if the opt-in strict CSP is enabled. `splat.test.ts` covers the
splat-PLY detector. Part (b) — schedule-linked verified-as-built progress — remains on the roadmap.

## v0.3.207 — Wave 8 ⑥: Construction Execution Plan (CEP) generator
The GC counterpart to the BEP: a produced governance document that states **how the project is built**,
assembled live from the construction modules and summary engines rather than a stale Word template. New
`_cep` report builder emits a **ten-section CEP** — (1) project organization & authorities (standard
appointment roles + the awarded subcontractors as appointed trade parties), (2) scope & work breakdown
by bid package, (3) master schedule & key milestones, (4) procurement & subcontracting (prequalified +
executed subs, insurance/bond), (5) cost management & change control (CO totals from the change-order
engine), (6) safety plan (OSHA metrics), (7) quality plan (inspections / NCRs / first-pass yield), (8)
submittal & RFI procedures, (9) permits & regulatory, (10) closeout & turnover (punchlist / commissioning
/ warranties / O&M). Every data pull is guarded — a missing engine or empty module degrades to a
placeholder row, never a 500. Registered in the report catalog (group *Quality*), so it **auto-surfaces
in the Report Center** with PDF / Excel / markup buttons — no frontend change. Covered by the existing
`test_reports` catalog loop (52 reports each render a valid PDF + Excel; dispatch-parity enforced). ISO
21502 / CMAA practice areas paraphrased in original prose (no copyrighted text, no competitor names).
(Wave 8 ⑥ of 7 — see `docs/roadmap.md`.)

## v0.3.206 — Wave 8 ⑤: wrong-storey model hygiene + green CI (in-memory model tests)
Completes the Wave 8 model-hygiene track and fixes the API test gate. `model_qa.py` gains a sixth
integrity check — **wrong storey**: an element assigned to level A but physically placed at level B's
elevation (the classic "wrong level" authoring mistake), flagged only when the placement sits clearly
closer to another storey (1 m margin) and guarded so a malformed storey set degrades to "couldn't check"
instead of 500ing. `test_model_qa` now exercises a positive case (a wall assigned to L1 but placed at
L2's elevation is caught and anchored to its GlobalId). **CI fix:** `test_layout` and `test_loads`
opened `samples/*.ifc` on disk, but `samples/` is gitignored — a fresh CI checkout has no model, so the
API test gate went red on v0.3.204/205. Both now **build their IFC in-memory** (`ifcopenshell.file` — a
64-column grid for the layout points, a 3-storey/12-column stub for the load takedown), matching the
pattern the other model tests already use. No behavior change to the layout/loads engines.

## v0.3.205 — Wave 8 ④: Preliminary gravity load takedown + ASCE 7 load combinations
A defensible, **non-FEA** structural sanity-check from the model — the tributary-area "load takedown"
every engineer runs before sizing columns. New `loads.py`: dead (slab self-weight from thickness × concrete
density + superimposed) + live (ASCE 7-22 Table 4.3-1 by occupancy, with the **§4.7 live-load reduction**
closed form) → tributary area per column → **accumulate storey-by-storey down to the footing** → **ASCE 7
load combinations** (LRFD §2.3 + ASD §2.4) → governing factored axial. Output: per-storey rows + the typical
interior column / footing service & factored loads. New `GET …/loads/defaults` (reads storey + column counts
off the IFC) + `POST …/loads/takedown` (explicit storeys or auto-built uniform); client `loadsDefaults`/
`loadsTakedown`; a viewer tool prompts for floor area/occupancy and shows the column + footing loads with the
governing combinations. `test_loads` checks the ASCE 7 combos (1.2D+1.6L governs; 1.4D dead-only), the §4.7
reduction (50→24.36 psf), and the takedown arithmetic (3×120 psf×1000 sf = 360 kip dead/column, factored
~509 kip). **Preliminary only — no lateral (wind/seismic), and not a substitute for a licensed structural
engineer** (the caveat ships in the API, the UI, and the output). Pure `ifcopenshell` + arithmetic; optional
PyNite/sectionproperties (MIT) tier noted for later. (Wave 8 ④ of 7 — see `docs/roadmap.md`.)

## v0.3.204 — Wave 8 ②: Model → field layout (PENZD/PNEZD CSV + DXF) + as-built verification
The smallest-surface, highest-field-utility Wave 8 item — export the setout that the 2026 field-robotics
wave consumes, straight from the IFC. New `layout.py`:
- **Setout points** — grid intersections (`IfcGridAxis`) + column / footing / opening / wall object
  placements, in **real-world E/N/Z** (the `IfcMapConversion` is applied, so points land on the
  surveyor's grid), each carrying its **IFC GlobalId in the Description** for the round-trip.
- **PENZD / PNEZD CSV** (configurable column order + delimiter) — the near-universal total-station /
  marking-robot interchange (Trimble/Leica/Hilti).
- **Layered DXF** (`ezdxf`, MIT) — points + labels, a layer per element type — for floor printers
  (Dusty-style).
- **As-built verification** — upload the as-installed total-station shots, match by point number, and
  get per-point 3-D deviation with out-of-tolerance flagged and anchored to the element GlobalId.
New endpoints `GET …/layout/{points,points.csv,layout.dxf}` + `POST …/layout/verify`; client
`layoutPoints`/`layoutCsvUrl`/`layoutDxfUrl`/`layoutVerify`; a viewer tool exports CSV/DXF and explains
the stake → shoot → verify loop. `test_layout` runs against a real IFC (208 setout points on
`maple_tower`; PENZD+PNEZD+tab CSV; layered DXF; the 100 mm-off point flagged at 20 mm tolerance; the
IFC2X3 no-map-conversion path degrades gracefully). Pure `ifcopenshell` + `ezdxf`; permissive. (Wave 8 ②
of 7 — see `docs/roadmap.md`.)

## v0.3.203 — Wave 8 ①: Clash Coordination Intelligence (grouping · severity · reconcile · KPIs)
The management layer on top of geometric clash *detection* — the strongest signal from the 2026 field
scan (4 of 14 sheets), built the way Navisworks / Autodesk Model Coordination / Solibri / Revizto do it.
New `clash_intel.py` turns a raw clash result set into **tracked coordination issues**:
- **Grouping** — greedy by-element set-cover: a duct crossing 12 joists becomes **one** issue
  ("relocate this duct"), not 12 clashes (the industry's order-of-magnitude reduction).
- **Severity** — a discipline matrix (structural pairs weigh most) × penetration volume × group size →
  a 0-100 score + Low/Medium/High/Critical band.
- **Stable identity + reconcile** — a `group_hash` (dominant GlobalId + the other discipline) survives
  re-runs, so a federation cycle auto-marks issues **resolved** (gone) and auto-**reopens** them
  (reappeared) *without losing comment history* — the classic Navisworks pain point, handled.
- **KPIs** — status mix, worst discipline pairs, severity, open-issue aging, per-run burn-down +
  reappearance rate.
Issues are created as `coordination_issue` records (already **BCF-native + pinnable + GlobalId-anchored**),
so everything round-trips with any BIM tool. New endpoints `POST …/clash/{coordinate,analyze}`,
`GET …/clash/metrics`, and `coordinate=true` on `POST …/clash/federated`; a `clash_run` module persists
run snapshots; the viewer's federated-clash tool now runs the coordination pass (reduction + new/active/
resolved/reappeared + severity + a KPIs view). `test_clash_intel` covers grouping, severity, and the
resolve→reappear→reopen loop across three runs. Pure Python; no new dependency. (Wave 8 ① of 7 — see
`docs/roadmap.md`.)

## v0.3.202 — Fix: metadata-only project no longer hangs the viewer on "Loading model"
A project with an uploaded **property index but no published `.frag`** (geometry never converted) spun the
viewer's **"Loading model"** overlay forever, and because the auto-load never returned, the Construction /
Finance **portal never mounted** ("No project open"). The backend correctly **404s** `model.frag` for such
a project — that path was already handled — but the degenerate variants weren't: an **empty 200 body**, or a
**non-`.frag` payload** (e.g. a proxy / SPA host that rewrites a 404 into a 200 HTML page) reached the
Fragments worker, which can **hang** (not reject) on input it can't parse, so `withLoading`'s `finally` never
fired. `loadProjectModel()` now fails open to the same graceful no-model state a brand-new project takes:
skip an empty body, and wrap `loadFragments` so unparseable bytes fall through instead of stalling. New
`apps/web/src/ui/autoload.test.ts` covers 404 / empty-200 / non-`.frag` / valid-`.frag`. Verified: backend
`model.frag` 404 + `model_kind: None` confirmed against the API; typecheck + lint clean; full web suite green.

## v0.3.201 — UI cohesion: wire the approval-gated journal batch into the General Ledger panel
A UI/UX cohesion pass over the recent finance work found the v0.3.199 **journal export batch** had shipped
backend-only — its client methods (`createJournalBatch`/`journalBatchExportUrl`) had no surface, so the
approval gate was unreachable from the app. The **General Ledger** panel now carries a **Journal export
batches** section: **Freeze current books into a batch** (period + memo via an accessible modal → draft),
a list of batches with **state badges** (draft / submitted / approved / exported) and frozen Dr/Cr totals,
inline **workflow actions** driven by each record's `available_actions` (submit → approve → reject), and
**GL-CSV / IIF download** links that appear only once a batch is approved. Same GlobalId-keyed data, one
click from the ledger the figures come from. (The v0.3.200 model-WIP cross-check was already wired into the
WIP panel; the only remaining finance client method with no panel — `wipModelProgress` — stays a public
API for embeds, its data already surfaced via the WIP `model` block.) Verified: typecheck + lint clean,
production build green; endpoints exercised live.

## v0.3.200 — Model-quantity-derived WIP %: an independent progress signal that cross-checks cost POC
Roadmap item ②, part 2 (closes item ②). Cost-to-cost percentage-of-completion can mislead — a cost
overrun makes a *behind* job look *ahead*, and front-loaded billing hides under-production. So WIP now
derives a second, **physical** progress signal straight from the model: **installed model elements ÷
total, keyed by IFC GlobalId** (the "units-installed" output method — ASC 606 output measure / EVM
units-completed), optionally weighted by an IFC base quantity (e.g. `NetVolume`). "Installed" = an
element whose field-`verification` status is `installed`/`verified`, so this ties revenue recognition
back to what's actually built in the field, not just what's been spent — and survives re-conversion
because it's GlobalId-keyed. `wip.py` gains `model_progress()`; `schedule()` gains a `method`
(`cost-to-cost` default | `units-installed`) and always carries a `model` block cross-checking physical
vs cost % with a divergence flag (`cost-ahead` = the classic front-loaded-billing signal). New `GET
…/wip/model-progress` + `method=` on `GET …/wip`; client `wip(pid, method)` + `wipModelProgress`; the
WIP panel shows a model cross-check card. Portfolio roll-up skips the per-project model scan (stays
fast). `test_wip` extended (count 50% / NetVolume-weighted 30%; aligned → physical-ahead; units-installed
drives earned 500k → 750k; unavailable with no model).

## v0.3.199 — Accounting interop depth: approval-gated journal export batch
Roadmap item ②, part 1. A **journal batch** freezes the current books — flattened GL + balanced
double-entry journal + trial balance — into an auditable snapshot (`journal_batch` config module) that
moves `draft → submitted → approved → exported`; the config engine gates each transition by party, and
`audit.py` records it. Export (GL-CSV or QuickBooks-IIF) emits from the **frozen snapshot**, and is
**409 until the batch is approved** — so the accountant imports exactly the figures that were reviewed
and signed off, and nothing posts to the books without passing the gate. `accounting.py` gains
`snapshot`/`create_batch`/`export_batch`; new `POST /accounting/journal-batch` + `GET
…/{id}/export?fmt=gl|iif` endpoints + client methods. `test_accounting` extended (freeze → export-409 →
submit+approve → frozen CSV/IIF still balances at 125000; 422 on missing period, 404 on unknown batch).
(Part 2 — model-quantity-derived WIP % — is the remaining half of item ②.)

## v0.3.198 — Supply chain (B2): hash-pinned Python lockfile, generated in the prod interpreter
Closes the last deferred hardening item. Top-level runtime deps now live in `services/api/requirements.in`;
a new `lockfile.yml` CI job runs `pip-compile --generate-hashes --allow-unsafe` **inside `python:3.12-slim`**
(the exact prod base image) and uploads the compiled `requirements.lock` (2,061 lines, every wheel pinned
+ sha256-hashed) — so the resolution always matches production, never a dev box. The API Dockerfile's
build stage and the CI test gate now `pip install --require-hashes -r requirements.lock`, which **rejects
any substituted or tampered wheel** (defends against dependency-confusion / registry compromise). One lock
covers the data-service deps too (a strict subset) and `psycopg[binary]`, so it replaced the two prior
unpinned installs. `lockfile.yml` also gates pushes: it fails if `requirements.in` changed without
regenerating the lock. Verified end-to-end by CI (test gate runs the full backend suite against the pinned
tree; the api image builds from it).

## v0.3.197 — Docs: consolidate + reprioritize the open roadmap into one section
Roadmap cleanup — pulled *every* not-yet-done item (previously split across a "Deferred" block and a
"Feature backlog") into a single prioritized **"What's left"** section: ① actionable next = B2 hashed
pip lockfiles (env-blocked here → a CI `pip-compile --generate-hashes` job in python:3.12-slim);
② optional feature depth = accounting-interop journal export + the exploratory parking lot; ③ upstream-
blocked = IFC5/IFCX write-path, native mobile (Capacitor) shell; ④ intentional non-goal = the A4/A5
portal-core split (deliberately coupled). Refreshed the header to v0.3.196, updated the intro (both the
feature roadmap and the Waves 1–7 hardening initiative are cleared), and corrected stale "in progress"
markers in the archive (Sources & Uses shipped as `proforma/sources_uses.py`; EVM E1–E7 and model
authoring P0–P6 shipped).

## v0.3.196 — Docs: Wave 7 (T5/T6/B3) shipped; only B2 remains deferred
Roadmap updated — the code-quality initiative's Wave 7 (TS strictness + Docker hardening) is now shipped
and CI-green (v0.3.193–195), leaving **only B2** (hashed pip-compile lockfiles) deferred, with the precise
reason: a correct hashed lock must be generated in the prod interpreter (Linux/py3.12) via
`pip-compile --generate-hashes` in a CI/Docker job — this dev sandbox has no Docker, and a Windows/py3.10
lock would pin the wrong wheels. (A4/A5 portal-core splits remain intentionally-not-done: coupled
orchestration where extraction adds indirection over value.)

## v0.3.195 — Docker/build hardening (B3): multi-stage API image + reproducible web npm ci
**API image** — split the Python install into a `pybuild` stage: the build toolchain (`build-essential`,
`python3-dev`) compiles any source-only wheel there, then only the installed packages are copied into the
runtime stage (`pip install --prefix=/install` → `COPY --from=pybuild /install /usr/local`). The runtime
image now carries **no compiler/headers** — smaller, and a reduced attack surface (already ran non-root +
healthcheck). **Web image** — `npm install` → `npm ci` against the workspace-root lockfile (exact, locked
tree; fails on drift) for reproducible builds; removed the vestigial `packages/shared-types` phantom
workspace (no package.json, no imports) so the root install is clean, and regenerated the lockfile.
Added a root **`.dockerignore`** (keeps host `node_modules`/`dist`/`.venv`/`.git`/`.env`/`*.db` out of
every build context). Verified locally: lockfile regenerates clean, web build + ESLint + Vitest (66) all
green; the Dockerfile builds themselves are validated by CI's container matrix. (The nginx web runtime
ships no node deps, so dev-toolchain `npm audit` advisories don't reach production.)

## v0.3.194 — Lint (T6): typed no-floating-promises + 45 unhandled-promise fixes
Enabled type-aware ESLint (`parserOptions.projectService`) scoped to the two promise-safety rules only —
deliberately NOT the full `recommendedTypeChecked` set (which would flood on the intentional `any` at the
IFC/three/@thatopen boundaries). `no-floating-promises` (error) flagged **45** fire-and-forget async calls
that swallow rejections; all fixed with `void` (each verified to be a self-handling navigation/render
method, not a raw `fetch`/`import`, with `errorReporting.ts`'s global `unhandledrejection` handler as
backstop). `no-misused-promises` is scoped to `checksVoidReturn:false` so it catches genuinely-dangerous
promise-in-conditional/spread misuse (0 found) without churning ~90 idiomatic async event handlers. tsc
(251-guard T5 intact) + ESLint + Vitest (66) + build all green.

## v0.3.193 — Type safety (T5): enable noUncheckedIndexedAccess + 251 real guards
Turned on `noUncheckedIndexedAccess` in the web tsconfig — every array/record index access is now typed
`T | undefined`, forcing an explicit check. Fixed all **251** resulting violations across 25 files with
*real* guards (destructure-with-check, `?? <default>`, early-return/`continue`, optional chaining) — not
blind `!`. Non-null assertions were used only where an index is provably in-bounds (right after a
`.length` check or a literal-tuple index), each annotated `// safe: <reason>` (34 total); **zero**
`as any` / `@ts-ignore` / `eslint-disable` escapes. The sweep caught real latent crashes now hardened:
empty-selection `Object.entries(sel)[0]` in `createRfiFromSelection`, malformed-frag-pair `.replace()`,
a `selectedIndex === -1` throw, `CAP_RANK[role]` defaulting unknown roles to rank 0 (correctly denies
review/edit/admin), and malformed-GeoJSON/GeoTIFF coordinate handling (skip vs crash). Money math kept
`?? 0` on numerators/display only, never divisors (no new NaN paths). tsc + ESLint + Vitest (66) + build
all green.

## v0.3.192 — Docs: close out the Code quality & hardening initiative
Roadmap updated to reflect that Waves 1–6 of the four-domain audit all shipped CI-green (v0.3.177–191):
observability, perf/scale, the type boundary (OpenAPI types + `ui/dom.ts`), modularization
(`model_index.py`, `report_builders/`, `httpCore.ts`, `portal/prefs.ts`), and reproducibility/ops
(fragments single-source, fail-closed secrets, Rust PR CI, Trivy split, `money.py`). Four items are
recorded as **deferred with measured blockers** rather than forced: T5 `noUncheckedIndexedAccess`
(251 real violations → per-module, not one sweep), T6 typed-lint (same class), B2 pip lockfiles (must
resolve in prod Linux/py3.12, not this dev box), B3 Docker `npm ci` (CI-only verify, low value).

## v0.3.191 — Add Decimal money helpers money.py (P6)
Float money math drifts at the cent: `round(2.675, 2)` is `2.67`, and a naive `round()` three-way split
of $100 sums to 99.99. Added `aec_api/money.py` — `q2()` (round-half-up to cents), `to_cents()`, and a
penny-accurate `allocate()` (largest-remainder split that always sums to the total). Returns plain
floats/ints so engines can adopt them incrementally without signature changes. New `test_money` suite
registered in the gate. (Additive — existing `round(x, 2)` sites are unchanged; adoption is opt-in.)

## v0.3.190 — Add typed DOM helpers ui/dom.ts (T4)
`document.createElement(...)` + a run of property assignments is the single most-repeated pattern in
the UI (255× in portal.ts alone). Added a thin, dependency-free `ui/dom.ts`: `el(tag, props, children)`
(typed props — `class`/`text`/`style`/`dataset` plus any element property like `onclick`/`type`),
`frag()`, `clear()`, and a typed `readForm<T>()`. Ships with a 7-case Vitest suite and is adopted in the
portal catalog as a first use; available for incremental adoption elsewhere. Vitest now 66 tests; tsc +
ESLint + build green.

## v0.3.189 — Refactor (T3): extract portal preferences into prefs.ts
The portal's favorites/recents and the per-persona "which nav sections open first" map were private
`PortalUI` methods, read by both the nav rail and the module catalog. Pulled them into a small
`portal/prefs.ts` (localStorage-backed, pure functions) so the two consumers share one source of truth
instead of reaching into the class. Verified: `tsc`, ESLint, Vitest (59), Vite build all green.
(portal.ts and viewer/app.ts already received their principled decomposition in earlier releases —
portal→panels/ + PanelContext, viewer→ViewerContext/install modules; the remaining catalog↔nav
orchestration is intentionally coupled, so this pulls out the cleanly-separable preferences only.)

## v0.3.188 — Refactor (T2): extract the API-client transport core into httpCore.ts
The web `ApiClient` mixed its transport plumbing (base URL, bearer token, `json`/`_pdfPost`/`url`/
`health`) in with ~200 typed domain methods in one 2,760-line file. Pulled the transport into a small
`HttpCore` base class (`api/httpCore.ts`); `ApiClient extends HttpCore` and keeps only the endpoint
surface. Every `api.method()` call site is unchanged (facade preserved). Verified: `tsc --noEmit`,
ESLint, and Vitest (59 tests) all green; production Vite build succeeds. (A full sub-client split was
weighed and rejected — it would churn 200+ call sites for no behavioural gain; transport/domain
separation is the value that carries low risk.)

## v0.3.187 — Refactor (A3): shared open_source_ifc() helper for the analysis endpoints
Three analysis endpoints (`models/georeferencing`, `models/qa`, `scan/deviation`) each hand-rolled the
same "resolve the project's source IFC → 409 if missing → ifcopenshell.open → 400 if unreadable" dance.
Added `deps.open_source_ifc(db, pid)` — one resolve-then-open path with consistent 4xx handling — and
converged the three sites onto it (georeferencing + models/qa now one-liners; scan/deviation reuses the
409 resolver, keeping its threadpool open). Behaviour identical; verified via test_georef, test_model_qa,
test_scan_deviation, test_ai_readiness.

## v0.3.186 — Refactor (A2): decompose reports.py into a report_builders/ package
The Report Center's builder module was a 1,436-line god-file holding ~50 per-report builder functions
alongside the catalog + dispatch. Split the builders into a `report_builders/` package — one module per
domain (`finance`, `construction`, `precon`, `bim`, `operations`) over a shared `_common` helper — so
`reports.py` is now a 176-line dispatch layer (the REPORTS catalog, the key→builder registry, and
`build()`). Public API is byte-identical: `reports.build`, `reports.catalog`, `reports.Report`,
`reports.to_pdf/to_sheets` all unchanged. Verified: all 8 report-exercising suites green (test_reports
builds every one of the 51 reports to PDF + Excel); ruff clean whole-tree.

## v0.3.185 — CI: split Trivy into a CRITICAL gate + non-blocking HIGH report
Following v0.3.184: scoping the API scan past npm's bundled tooling wasn't enough — the **web** image
(final stage `nginx:alpine`) carries its own rolling set of fixable HIGH CVEs in its apk packages, which
a shared skip-dir can't cover. Both base images churn fixable HIGHs outside our control, so a blocking
HIGH gate keeps the pipeline red on upstream timing, not on our code. Resolution: **CRITICAL findings
still block the publish**, and a **second, non-blocking Trivy step prints fixable HIGH CVEs every build**
so they're surfaced (not shipped silently) for a human to act on the ones in our own deps — without
base-image noise gating the release. Restores green container publish; keeps O4's real deliverables
(Rust PR CI + fail-closed prod secrets + CLI/dep guards) intact.

## v0.3.184 — CI hotfix: scope Trivy HIGH past npm's bundled build tooling
The v0.3.183 Trivy bump to HIGH immediately flagged **12 HIGH CVEs — all in npm's own vendored
node_modules** (cross-spawn / glob / minimatch / tar, DoS/regex issues) that the `node:20-slim` layer
carries; they're build-time tooling, not runtime attack surface, and can't be pinned by us (they track
the base image). The scan now `skip-dirs` npm's bundled tree, so real HIGH/CRITICAL CVEs in **our**
fragments/web-ifc + Python deps still block the publish, without base-image tooling noise. (The API test
gate, web build, and full backend suite were already green on v0.3.183 — this only unblocks the container
publish.)

## v0.3.183 — Ops/build hardening (Wave 1/6: O3 · O4 · B4) + A1 lint fix
Cross-cutting hardening + a follow-up to v0.3.181.
- **O3 — fail-closed prod secrets.** The prod compose overlay now sets `POSTGRES_PASSWORD` (postgres +
  the API's `DATABASE_URL`) and `S3_SECRET_KEY` (minio + the API) via `${VAR:?}`, so the stack **refuses
  to start** without real credentials instead of silently inheriting the dev `bim`/`minioadmin` defaults.
- **O4 — Rust PR CI + Trivy HIGH.** New `rust-ci.yml` runs `cargo clippy -D warnings` + `cargo fmt
  --check` on the Tauri shell, path-filtered to `apps/web/src-tauri/**` (no cost on unrelated PRs) — it
  previously only compiled at release time. The container scan now gates on **HIGH + CRITICAL** fixable
  CVEs (was CRITICAL-only).
- **B4 — converter CLI + Dependabot.** `cli.mjs` no longer clobbers its input when the file lacks an
  `.ifc/.rvt` extension (appends `.frag` instead); the Dependabot npm ecosystem points at the repo root
  (where the workspace `package-lock.json` actually lives) so it can open working PRs.
- **A1 fix.** Import-sort (ruff I001) slip in `evm.py` from the v0.3.181 `model_index` rename — the only
  thing that had gone red (lint, not tests). Whole-tree ruff is green again.

## v0.3.182 — Single-source the fragments/web-ifc version (Wave 6, B1)
Closes the version-coupling landmine CLAUDE.md warns about. `@thatopen/fragments@3.4.5` +
`web-ifc@0.0.77` were hardcoded in **three** independent places — the web client parser
(`apps/web/package.json`, the source of truth) and the two server-side `.frag` producers
(`services/api/Dockerfile`, `services/converter/Dockerfile`) — with nothing keeping them in lockstep, so
a client bump could silently leave the server emitting fragments the browser can't parse. The Dockerfiles
now take the versions as build ARGs (self-documenting, overridable), and a new
`scripts/check-fragments-version.mjs` (wired into the CI **web-build** job) fails the build if either
Dockerfile drifts from the `package.json` pins. `package.json` is now the one source of truth; CI enforces
agreement.

## v0.3.181 — Extract the model-index engine (Wave 5, A1)
Fixes the worst dependency inversion in the backend. The in-process **property index**
(`pid → {guid → record}`) and the model-version-keyed **scan-result cache** lived as private globals
inside `routers/properties.py`, yet five engines (`bim_kpi`, `energy`, `evm`, `mcp_tools`, `reports`)
reached in with `from .routers.properties import _INDEX, _ensure_loaded` — engines depending on an
HTTP-layer module's internals. Moved to a new `model_index.py` engine with a public API
(`ensure_loaded` / `get_index` / `get_meta` / `load` / `scan_cached`); the router now imports from it
(keeping its endpoints), and the five engines import the engine instead of the router. Compatibility
aliases (`_INDEX`/`_ensure_loaded`/`_scan_cached`) preserve behaviour exactly — same cache objects, so
in-place mutation stays shared. No API or runtime change; the dependency arrow now points the right
way and the index is testable/reusable without importing FastAPI. `test_scan_cache` updated to the new
module.

## v0.3.180 — OpenAPI-generated TypeScript types (Wave 4, T1 foundation)
Establishes a compiler-checked contract to the backend. `openapi-typescript` now generates
`apps/web/src/api/schema.d.ts` (types-only — erased at build, no bundle cost) from the FastAPI
`/openapi.json`, and a thin `openapiTypes.ts` seam re-exports `paths`/`components`/`operations` plus
`Schema<K>` / `OkJson<Op>` / `ReqJson<Op>` helpers so endpoints can adopt generated request/response
types. Regenerate with `npm run gen:api-types` (the intermediate `openapi.json` is gitignored;
`schema.d.ts` is committed). **Scope note, honestly stated:** the backend returns raw dicts on most
endpoints — only ~11 of ~540 declare a response model — so today the generated types are precise for
request bodies, path/query params, the 134 input schemas, and those typed responses; the hand-written
DTOs in `types.ts` remain the source for untyped responses. Coverage grows automatically as backend
endpoints adopt `response_model=` (a follow-on track). tsc/eslint/vitest green; bundle size unchanged.

## v0.3.179 — Scale: SQL-aggregate the portfolio & related-record hot paths (Wave 3)
Removing the linear-in-project-size loads. **P3 — WIP portfolio N+1:** the WIP schedule loaded up to
100k owner-invoice rows into Python *per project* to sum billed-to-date, and the portfolio roll-up runs
that for every job — the worst scale hazard in the codebase. Added a portable
`modules.sum_field(db, key, pid, field)` (SQL `SUM` over the JSON column: Postgres `->>`+cast,
SQLite `json_extract`) and pointed the WIP billed-to-date total at it. **P4 — dashboard timesheet
hours:** the safety-metrics endpoint summed `timesheet.hours` by loading every row; now a single SQL
sum (the manpower log stays row-wise because it needs the headcount→hours fallback). **related_records:**
the per-record detail view full-scanned each reverse-referencing module and filtered the match in Python;
the reference match is now pushed into SQL via the existing `_json_text` extraction (mirrors `_rollup`).
Identical output, far less work at scale. *(The schedule/CPM/gantt `list_records` loads were reviewed and
left as-is — they legitimately need every activity row. The ref-uniqueness DB backstop is deferred as
low-value/higher-risk.)*

## v0.3.178 — Perf & concurrency hardening (code-quality Wave 2)
Applying the audit's highest value-to-effort fixes. **P1 — event-loop stall:** the
`POST /scan/deviation` endpoint was `async` but ran `ifcopenshell.open` + full tessellation and the
point-cloud parse synchronously, stalling every other request on the worker for the duration of a large
scan; all three now run in `run_in_threadpool` (mirroring `run_validate`). **P2 — uncached hot scans:**
the model **data-QA**, **code-readiness**, and **by-discipline** viewer scans recomputed `O(n·psets)`
on every request while their siblings (facets/color-by) were cached; they now go through the same
model-version-keyed `_scan_cached` (Redis-backed, auto-invalidated on republish) — repeat loads are
served from cache. **P5 — concurrency/scale hardening:** a composite `(project_id, ts)` index on
`record_activity` turns the frequently-polled notifications feed from an index-scan-plus-filesort into
one ordered range scan (auto-backfilled on existing DBs); and the in-process property index
(`_INDEX`/`_LRU`) — mutated from multiple threadpool threads — is now guarded by a lock so an eviction
can't fire mid-populate and drop a live project. No API shape changes; behaviour identical, just faster
and safer under load.

## v0.3.177 — Error-log observability (see when things break)
The first wave of the code-quality/hardening initiative: a **background place to see failures** instead
of them dying in a server's stdout. A global exception handler + request-id middleware now catch every
**unhandled server error**, record it (with traceback, route, user, and a correlation id) to a new
`error_log` table, and return a clean `500 {detail, request_id}` — and every response carries an
**`X-Request-ID`** header so a user-reported failure maps straight to its logged row. **Browser errors**
are captured too: a `window.onerror` / `unhandledrejection` hook (throttled + deduped) posts to
`POST /client-errors`, landing in the same feed tagged `source:"web"` — so a viewer crash or a failed
upload is finally visible. Admins get an **Errors** console (account menu → Errors) with source/level
filters, a totals header, expandable tracebacks, and a prune button; the log is **retention-capped**
(rows + age, env-tunable) so it can't grow unbounded on the read-only prod tree. Engine `errorlog.py`,
`routers/observability.py` (`GET/DELETE /admin/errors`, admin-gated), `ErrorLog` model,
`errorReporting.ts`. Test `test_errorlog.py` covers the engine, the 500 handler end-to-end, the intake,
and the admin feed. In-house only — no external APM, consistent with the offline mandate.

## v0.3.176 — 2D → BIM raise (DXF floor plan → IFC model)
The complement to scan-to-BIM: where deviation checks the *built* result against the model, this
raises design intent *up* from flat 2D CAD into one. Upload a **DXF floor plan** and get a real,
GUID-keyed **IFC4 model** — an `IfcWall` extruded from each line-work segment (auto-detecting "wall"
layers, falling back to all line-work) and an `IfcSpace` (with its floor area in the Qto) from every
closed room polygon. Drawing units are read from the DXF `$INSUNITS` header and normalised to metres.
The raised model is registered as a **"2D Raise"** discipline model, so it opens in the viewer and
takes part in federated clash immediately. A `preview` mode returns the detected wall/room counts
without writing anything. Engine `plan_to_bim.py` (ezdxf for the CAD read — MIT, no AGPL; ifcopenshell
for the model, same wall/space patterns as the massing generator), endpoint
`POST /projects/{pid}/raise-plan` (multipart; temp-dir scratch, never the read-only tree), a client
method, and a **🏗 Raise 2D→BIM** viewer tool. Test `test_plan_to_bim.py` round-trips the IFC.

## v0.3.175 — Scan-to-BIM deviation (as-built QA/QC)
Close the reality-capture loop: upload an as-built **point cloud** (ASCII XYZ / CSV / PTS) from a laser
scan or photogrammetry survey and compare it against the model surface to see **where the built work
departs from the design beyond tolerance** — the QA/QC check after a pour or a steel erection. For every
scan point we take the nearest distance to the model's triangulated surface (a KD-tree over the model
vertices), then summarize: **% within tolerance**, mean / 95th-percentile / max deviation, an
out-of-tolerance count, and a **deviation histogram** banded in multiples of the tolerance — the numbers
behind a red/green deviation heatmap. Engine `scan_deviation.py` (numpy + scipy cKDTree; model surface
pulled via `ifcopenshell.geom`, capped so a huge model can't blow memory), endpoint
`POST /projects/{pid}/scan/deviation?tolerance=` (multipart upload; 409 without a source IFC), a client
method, and a **▦ Scan-to-BIM deviation** viewer tool that renders the summary + histogram. All units in
metres; GUID-keyed model geometry, fully offline. Test `test_scan_deviation.py`.

## v0.3.174 — AI / data-readiness scorecard
Roadmap item from the "hidden bottleneck of agentic AI" research: the blocker to AI isn't the model,
it's the **data**. A new scorecard grades a project **0–100 on four measurable dimensions** — **single
source of truth** (a GUID-keyed IFC + federated models), **information completeness** (CDE metadata +
core requirements), **model integrity** (the model-QA defect ratio, when an IFC is loaded), and
**governance** (requirement traceability + a responsibility matrix, on top of always-on RBAC/audit) —
with a per-dimension recommendation and a **ready / partial / not-ready** verdict. Answers "can an agent
act on this project's data yet, and if not, what to fix first?". Engine `ai_readiness.py`, endpoint
`GET /projects/{pid}/ai-readiness`, an **AI / data-readiness** card atop the CDE / Standards panel, and
`test_ai_readiness`. Honest heuristic — a readiness indicator, not a guarantee.

## v0.3.173 — PM: portfolio prioritization matrix
Roadmap **PM artifacts #2.** The Portfolio view now ranks every project you can see with a
**prioritization matrix** — each scored **0–100** on four criteria (financial **return** / equity IRR,
**on-budget** / CPI + variance, **on-schedule** / SPI + % complete penalized for late milestones, and
**delivery-risk** / status) into a weighted composite, ranked best-first with a color-graded score per
criterion. Reuses the executive-portfolio rows (and their membership scoping), so no double-counting.
New engine `prioritization.py` (pure, weight-configurable), endpoint `GET /portfolio/prioritization`,
a ranked card in the Portfolio panel, and `test_prioritization`. Answers "where do capital and attention
go across the book?"

## v0.3.172 — PM: stakeholder register + power/interest analysis
Roadmap **PM artifacts #1** (from the PM-template research). A new **Stakeholders** module (under Project
Controls) registers each party — organization, role, category, power/influence, interest, stance,
engagement strategy. A `stakeholder.py` engine turns the register into the **Mendelow power/interest
grid** — *manage closely* (high/high), *keep satisfied* (high power), *keep informed* (high interest),
*monitor* (low/low) — with a stance tally and, crucially, the **high-power blockers** to address. Exposed
as `GET /projects/{pid}/stakeholders/analysis` and a **Stakeholder Analysis** report (power/interest
quadrants + roster + blockers) in the Report Center, exportable to PDF/Excel. New `test_stakeholder`.

## v0.3.171 — Model QA: integrity / hygiene checks
Roadmap **Model-QA** (from the second research batch's "common modelling mistakes"). Complementing the
LOIN/IDS *data-quality* checks, a new **🩺 Model QA** tool scans the source IFC for the defects a
coordinator catches by eye: **duplicate GlobalIds**, **orphaned elements** (not placed in any storey),
**overlapping duplicates** (same class stacked at one spot), **unenclosed spaces** (an IfcSpace with no
boundaries — the classic "Room is not enclosed"), and **blank element names**. Each check returns a
count + a sample of offenders and a clean/not-clean verdict. New engine `model_qa.py`, endpoint
`GET /projects/{pid}/models/qa`, and `test_model_qa` (builds an IFC in-memory with every defect and
checks each is caught). ifcopenshell only, no new deps.

## v0.3.170 — Coordination: shared coordinates / BIM-to-field setout
Roadmap **Phase C** (from the second research batch's BIM Control Stack). The alignment report only read
a model's eastings/northings; this reads the **full survey basis**. A new **📍 Georeferencing** model
tool reports the complete `IfcMapConversion` — eastings/northings/height, the **true-north bearing**
(derived from the X-axis rotation), and scale — plus the `IfcProjectedCRS` (EPSG name, geodetic/vertical
datums, map projection + zone), and a site lat/long fallback. It grades the model with a **LoGeoRef
level** (0 → 50) so a coordinator sees at a glance how well-referenced it is — the basis federation and
**BIM-to-field layout/setout** both depend on. New engine `georef.py`, endpoint
`GET /projects/{pid}/models/georeferencing`, and `test_georef` (builds a georeferenced IFC in-memory and
checks the bearing/CRS/level). Permissive: reads via ifcopenshell, no new deps.

## v0.3.169 — openBIM: ISO 19650-6 exchange acceptance
Roadmap **Phase A #3.** Distinct from the project-level handover gate, this reviews **each exchanged
container** (anything past Work-in-Progress) against the four ISO 19650-6 acceptance criteria —
**completeness** (type/discipline/originator set), **suitability** (a suitability code), **authorization**
(published/archived, not merely shared), and **traceability** (a revision) — and flags the ones **not yet
acceptable** before the next decision point. Reuses the container data already tracked; no new module.
`cde.exchange_acceptance()`, endpoint `GET /projects/{pid}/cde/exchange-acceptance`, and an **Exchange
acceptance** card (per-criterion % + non-conformances) in the CDE / Standards panel. Extends `test_cde`.
Completes the ISO 19650 delivery-checklist "exchange assurance" step.

## v0.3.168 — openBIM: LOIN + MIDP/TIDP delivery plan
Roadmap **Phase A #2** (from the second research batch). Two ISO 19650 depth items on information
requirements. **LOIN** — each requirement now records its **Level of Information Need** per EN 17412-1 /
ISO 7817: the required depth of **geometry**, **alphanumeric** data, and **documentation** (three
ordered selects), so an EIR states *how much* information a deliverable needs, not just that it's needed.
**MIDP / TIDP delivery plan** — a new engine (`cde.delivery_plan()`) lays the requirements out against
their **programme dates**: each gets an overdue / due-soon / scheduled / issued status, a per-milestone
(due-month) roll-up, the next deliverable, and **LOIN coverage** (the share that actually state a level).
Surfaced as a **Delivery plan (MIDP/TIDP)** card in the CDE / Standards panel with overdue/due-soon
flags. Endpoint `GET /projects/{pid}/info-requirements/delivery-plan`; extends `test_cde`. Ties every
information exchange to a milestone — the "align exchanges with programme dates" step of the ISO 19650
delivery checklist.

## v0.3.167 — openBIM: information-requirement flow-down (ISO 19650 cascade)
Roadmap **Phase A #1.** The requirements register listed OIR/AIR/PIR/EIR/BEP/MIDP/TIDP but nothing tied
a requirement to the higher-level one it flows down from — so there was no actual traceability. Each
Information Requirement now has a **Derives from** link (to another requirement), and the CDE / Standards
panel shows a **Requirement flow-down** card: how many requirements trace up (OIR → PIR/AIR → EIR →
MIDP/TIDP), which ones **don't** (orphans that don't reach organizational intent — a broken cascade),
and any links pointing the **wrong way** (to an equal-or-lower tier). Engine `cde.cascade()`, endpoint
`GET /projects/{pid}/info-requirements/cascade`, extends `test_cde`. The link is set/edited inline with
the relational grid (v0.3.159). This is the openBIM information-delivery moat: intent traced from the
client's organizational requirements down to what each task actually delivers.

## v0.3.166 — Estimating: quantity takeoff from 2D CAD (DXF)
Roadmap **Phase B #4.** Estimating no longer needs an IFC model — a new **▤ DXF takeoff** model tool
takes an uploaded **.dxf** drawing and measures it **by layer**: linear metres (walls, pipe/conduit
runs), enclosed area (rooms, slabs — closed polylines + circles), and **block counts** (doors, fixtures,
devices), converting to metres from the drawing's own units. Built on **ezdxf** (MIT, pure-Python — no
AGPL); DWG converts to DXF first (external, optional). The upload is parsed in a temp file and
discarded, never written to the source tree; a non-DXF file returns a clean 400. New engine
`dxf_takeoff.py`, endpoint `POST /projects/{pid}/takeoff/dxf`, and `test_dxf_takeoff`. Estimators who
live in 2D CAD can now get measured quantities without a full BIM model.

## v0.3.165 — Estimating: labor demand by trade (estimate → staffing)
Roadmap **Phase B #3.** The resource estimate now rolls its crew-hours **up by trade** — total hours
and cost per trade (carpenter, ironworker, cement-mason…), sorted biggest-first — so the model answers
"how many carpenter-hours does this building need?", the input a scheduler or PM uses to staff and load
the schedule. The engine's `labor_demand()` can also imply an **average crew size** to finish in a given
number of weeks (hours ÷ weeks ÷ 40). Shown as a "Labor demand by trade" table in the 🧱 Resource
estimate model tool. Extends `test_assemblies`. This is the bridge from the estimate's L/M/E split to
resource loading — the point of computing crew-hours in the first place.

## v0.3.164 — Estimating: resource estimate in the viewer (labor · material · equipment)
Roadmap **Phase B #2** — surfaces v0.3.163's engine. The model tools now have a **🧱 Resource estimate**
button next to the blended "Estimate from model": it prices the takeoff by building each element up from
a crew and shows the **labor / material / equipment split** (with % of total), **total crew-hours**, and
a per-assembly breakdown (quantity, built-up unit cost, hours). Where the blended estimate answers "how
much," this answers "made of what" — the split a real estimate carries and the crew-hours that feed
resource loading. Unmapped element classes are noted, not hidden.

## v0.3.163 — Estimating: resource-based (assembly) cost build-up
Roadmap **Phase B #1.** Model-based estimating used a single blended $/unit per element class. Real
estimators build a unit cost **up** from a crew: labor hours × rate + materials × quantity + equipment
× hours. A new engine (`assemblies.py`) does exactly that — a catalog of labor/material/equipment
**resources** and **assemblies** (recipes like "cast-in-place wall" = concrete + rebar + formwork +
cement-mason + laborer + pump). Pricing any quantity now returns the **labor / material / equipment
split**, the built-up unit cost, **and total crew-hours** — the last of which can drive resource loading
and the schedule, not just a dollar figure. Two endpoints: `GET /estimate/resources/catalog` (the
reference book, each assembly with its built-up unit cost) and `GET /projects/{pid}/estimate/resource-based`
(prices the IFC takeoff by mapping each element class to an assembly; unmapped classes are surfaced, not
silently dropped). Backend-only this release; a UI to compare blended-vs-resource follows. New
`test_assemblies` (build-up math, L/M/E split, crew-hours, takeoff) — full suite green.

## v0.3.162 — Data-grid UX: choose which columns show
Roadmap **Track X #3.** A module list showed a fixed set of columns (whatever the module defined), so
wide record types either hid fields you needed or you scrolled past ones you didn't. A new **⚙ Columns**
button opens a checklist of every field — tick the ones you want as columns and they render in field
order; **Reset to default** returns to the module's built-in set. The choice is remembered per module on
this device, and the button highlights when a custom set is active. Ref, Title, Assignee, Ball-in-court
and Status always frame the row. Pairs with inline edit / paste so you can shape a wide table down to
just the columns you're working in.

## v0.3.161 — Relational fabric: "referenced by" now reads distinctly on a record
Roadmap **Track R #3.** A record's Related section already listed both the records it points to and the
records that point back at it — but with one identical icon and no labels, so you couldn't tell the two
directions apart. It's now split into two counted groups: **References (n)** — what this record points
to — and **Referenced by (n)** — its dependents, e.g. the change orders raised against a budget line —
each with its own direction icon and a one-line caption. Also hardens the section: linked-record titles
(user text) are now HTML-escaped rather than injected raw. Completes the record-level relational view
alongside the grid's clickable links (v0.3.157) and inline linking (v0.3.159).

## v0.3.160 — Data-grid UX: paste rows straight from Excel
Roadmap **Track X #2.** Getting a batch of records in used to mean saving a spreadsheet and uploading
it. Every module list now has a **⎘ Paste** button: copy a block of cells from Excel or Google Sheets,
paste them in, and the pasted table flows into the **same import step you already know** — column
mapping, preview, then commit. No file, no new code path: paste is converted to CSV and handed to the
existing importer, so it inherits its validation and field-mapping. Keep the header row and map each
column once. Rounds out in-grid data entry alongside inline edit (v0.3.158) and inline linking (v0.3.159).

## v0.3.159 — Relational fabric: link records inline from the grid
Roadmap **Track R #2** (extends v0.3.158's inline edit). In **✎ Edit inline** mode, a reference cell
now becomes a **record picker** — a dropdown of the linked module's records reading as *ref · title* —
so you set or change what a record points at without opening its form. Options come from the data
already fetched for the relational links (no extra requests); a current link that sits outside the
loaded window is preserved so toggling edit mode never drops it. Saves on change with the same green
flash. Read mode still shows the clickable link (v0.3.157). Together with v0.3.158 the whole row —
data fields and relationships — is now editable in place.

## v0.3.158 — Data-grid UX: inline-edit cells for fast bulk entry
Roadmap **Track X #1.** Editing many records meant opening a form for each one. Every module list now
has an **✎ Edit inline** toggle: data cells become inputs (text / number / date / dropdown / checkbox)
you edit straight in the table, and each change **saves automatically** with a brief green flash — no
form round-trip. Enter or blur commits a cell. Works across all 120 config modules and composes with
the existing filter / sort / bulk-select / templates. Reference cells stay as their new relational
links (v0.3.157); the inline record-picker for references comes next. Opt-in — the read view is
unchanged until you toggle it on.

## v0.3.157 — Relational fabric: reference cells become clickable links
Roadmap **Track R #1.** The 120 tools are deeply relational, but in a module's list a reference field
(a commitment's cost code, an RFI's spec section, a change event's PCO…) showed only a truncated id.
Now every reference cell resolves to the **linked record's ref + title** and is a **link** — one click
opens that record in its own module. The list pre-fetches each referenced module once (one lookup per
reference column, not per cell), so it stays fast; unresolved ids fall back to the short id. Applies
automatically to all 120 config modules. Foundation for the record-picker + inline-edit grid to come.

## v0.3.156 — Responsibility matrix (RACI / DACI) — roadmap Phase A, item 1
The role-clarity that ran through the field research (PM vs Superintendent, PM vs CM, RACI vs DACI)
had no home in the app. New **Responsibility** destination (under Plan & Derisk for the GC, and under
Model & Standards for the design seat, where it doubles as the ISO 19650 MIDP/TIDP task-team
responsibility view): an editable grid of activities × project roles, each cell an assignment letter.
- **RACI** (Responsible / Accountable / Consulted / Informed) or **DACI** (Driver / Approver /
  Contributor / Informed) — one-click toggle that remaps the doer letter across the matrix.
- **Live validation** enforces the rules that make a RAM useful: exactly one Accountable per row, at
  least one Responsible — flagged inline as you edit.
- **Starter templates** (design delivery, buyout, construction, closeout) seed a valid matrix in a
  click; add/rename/remove role columns and activities; export to CSV.
- Built on the config-module engine (new `responsibility` module + `responsibility.py`) so every row
  gets CRUD, RBAC, audit and search for free; the panel degrades to a clean empty state offline.

## v0.3.155 — Enterprise: SAML 2.0 single sign-on
Massing can now sit behind a corporate IdP over SAML (Okta, Azure AD/Entra, OneLogin, ADFS,
Shibboleth), alongside the existing OAuth providers. A new SP surface: **`GET /auth/saml/metadata`**
(SP metadata to register), **`GET /auth/saml/login`** (SP-initiated redirect, HTTP-Redirect binding),
and **`POST /auth/saml/acs`** (Assertion Consumer Service). A verified email maps to an
auto-provisioned free-tier user (honoring the same `AEC_OAUTH_ALLOWED_DOMAINS` / no-autoprovision
gates as OAuth); `/auth/providers` now reports `saml: true` when configured.

Verification is the whole game, so it's done carefully (`saml.py`, using `signxml`): the IdP signing
cert is **pinned** from config (never trusted from the message's KeyInfo); identity is read **only
from the cryptographically-verified subtree**, defeating XML Signature Wrapping; and the signed
assertion's **Conditions** (validity window ± a small clock-skew, AudienceRestriction == our SP) and
**SubjectConfirmation Recipient** (== our ACS) are enforced. `test_saml` drives real signed assertions
through the ACS and proves tampered, unsigned, wrong-key, expired, and wrong-audience responses are
all rejected (403). Enabled only when the IdP entityID + SSO URL + cert are set.

## v0.3.154 — Enterprise: SCIM 2.0 user provisioning
Enterprises can now automate account lifecycle from their IdP (Okta, Azure AD/Entra, OneLogin,
JumpCloud) instead of managing users by hand. A new **`/scim/v2`** surface (RFC 7643/7644) implements
the Users resource: **create** (provision), **read / filter** (`userName eq`), **PUT / PATCH**
(including both the Okta `path:active` and Azure `value:{active}` deactivation shapes), and
**DELETE** (de-provision). Provisioned accounts are SSO-only (a random, unusable password — they sign
in via OAuth/SAML), and **deactivation revokes any live token immediately** (bumps the session
watermark), not just at expiry; DELETE is a soft-delete so the audit trail and record authorship
survive, and a later re-provision reactivates (rehire). The whole surface is gated by a single
constant-time bearer token (`AEC_SCIM_TOKEN`); unset ⇒ 503 (disabled), so it can't be probed open.
Adds `User.external_id` (IdP correlation) + `User.provisioned` (additive schema sync).

## v0.3.153 — Search: GIN index behind module full-text search (Postgres)
Module full-text search already used Postgres `to_tsvector(...) @@ to_tsquery(...)`, but nothing
indexed that document — so every search recomputed `to_tsvector` for **every row** (a sequential
scan, brutal past ~100k records). `init_db` now creates a **GIN expression index** on the exact same
`to_tsvector(ref + title + data)` document the query matches (built from the shared `_pg_document`
helper, so the index and the query can't drift). Postgres-only and idempotent
(`CREATE INDEX IF NOT EXISTS`); a **no-op on SQLite** (dev/CI use the substring-LIKE fallback, which
needs no index). The regconfig is rendered as a literal so the expression is index-safe.

## v0.3.152 — Web: decompose the two remaining god-files (client.ts / portal.ts)
No behavior change — the two largest web modules are split along their existing seams:
- **`api/client.ts` 2905 → 2612**: the ~300 lines of DTO `interface`/`type` declarations move to a new
  **`api/types.ts`**; the client re-exports them (`export * from "./types"`) so every
  `import { … } from "../api/client"` site across the app keeps resolving unchanged.
- **`portal/portal.ts` 2816 → 2302**: the GMP **Budget** dashboard and the unified **Schedule** views
  (pull-plan board, lookahead, milestones, CPM, EV, baseline/variance, Gantt/LoB) extract to
  **`portal/panels/budget.ts`** and **`portal/panels/schedule.ts`** via the established `PanelContext`
  seam (the 11 panels already living there); the class keeps one-line delegators.

## v0.3.151 — Web: global keyboard focus indicator (WCAG 2.4.7)
Keyboard users had no consistent visible focus ring — many interactive controls relied on the browser
default, which the app's custom control styling suppressed in places. A single `:focus-visible` rule now
draws a 2px accent outline (with offset) on every focusable control — buttons, links, inputs, selects,
textareas, `summary`, and anything with `tabindex` — **only** for keyboard/AT focus, so mouse clicks
don't get the ring. Meets WCAG 2.4.7 (Focus Visible). CSS-only, no markup or behavior change.

## v0.3.150 — Report dispatch: data-driven registry (replaces the 90-line if/elif ladder)
`reports.build()` chose a builder through a ~90-line `if report == "…"` ladder. It's now a
`_BUILDERS` dict (key → builder) + a `_LOGS` dict for the module-log reports — adding a report is one
registry line, and the dispatch can no longer silently drift from the `REPORTS` catalog. `test_reports`
gains a parity assertion (`REPORTS` keys == builders+logs) so a new report without a builder (or vice
versa) fails the gate. No behavior change — all 50 reports still render.

## v0.3.149 — Primavera P6 **XML (PMXML)** import (alongside the existing XER)
The schedule importer now accepts both Primavera P6 export formats, auto-detected from the content.
- **`schedule.parse_pmxml`** reads a P6 XML (PMXML) export into the same activity rows
  (id / name / planned-or-actual start+finish) as the XER parser — namespace-agnostic (the P6
  namespace varies by version, so it matches on local tag names). **`parse_schedule`** dispatches
  XER vs PMXML by sniffing the first non-space character.
- The existing **`POST /projects/{pid}/schedule/import-xer`** now upserts activities from either
  format (same re-import idempotency, milestone tagging, and 4D date window); the web import button
  and file picker accept **.xer / .xml**.
- `test_research` extends to import a PMXML export end-to-end.

## v0.3.148 — Webhook hardening: HMAC signing + retry/backoff + delivery log
Makes the outbound webhooks (module transitions → external automation) production-grade.
- **HMAC signing** — when `AEC_WEBHOOK_SECRET` is set, every delivery carries
  `X-Massing-Signature: sha256=HMAC(secret, "<timestamp>." + body)` + `X-Massing-Event-Timestamp`, so
  a receiver can verify authenticity and reject replays (the timestamp binds the signature).
- **Retry with exponential backoff** — a failed delivery retries up to `AEC_WEBHOOK_RETRIES` (default
  3) with `AEC_WEBHOOK_RETRY_BASE`-second backoff (0.5s, 1s, 2s…) before giving up. Still fail-open —
  a broken endpoint never blocks the transition.
- **Delivery log** — a bounded, process-local ring of recent attempts (url, event, ok, status,
  attempts, error), surfaced to platform admins at **`GET /webhooks/deliveries`** with the signing
  state — "did my hook fire?" observability.
- `test_webhooks` extends to pin the signature, the retry (2 fails → 3rd ok) + log, and the admin gate.

## v0.3.147 — openBIM: IFC4.3 infrastructure discipline + full ISO 19650 suitability codes
Closes the openBIM standards remainder.
- **IFC4.3 infrastructure entities** (`IfcAlignment`, `IfcRoad`, `IfcRailway`, `IfcBridge`,
  `IfcMarineFacility`, `IfcTunnel`, `IfcCourse`, `IfcPavement`, earthworks, …) now classify to the
  **Civil (C)** discipline instead of being lost to the default — their MasterFormat divisions (34
  Transportation / 35 Marine) sit outside the building divisions, so they're mapped directly.
  `classification.is_infra_class()` exposes the set. (`IFC4X3` was already a supported read schema.)
- **CDE suitability codes** — the information-container vocabulary now carries the higher ISO 19650
  codes **S5 (manufacture/procurement), S6 (PIM authorization), S7 (AIM authorization)** alongside
  the existing S0–S4 / A / B / CR / AB.
- `test_disciplines` pins the infra→Civil mapping.

## v0.3.146 — fix: `test_stored_ids` must set `IFC_DIR` (the actual red-CI cause)
`test_stored_ids` uploads a source IFC via `/source-ifc`, which writes to `IFC_DIR` (default
`/app/ifc`, read-only on CI/in the container). Sibling upload tests set `IFC_DIR` to a writable path;
this one didn't, so the upload — not the `/validate` temp write fixed in v0.3.145 — was what reddened
CI. Test now sets `IFC_DIR=./test_ifc_stored_ids`. (The v0.3.145 tempdir fix remains a valid
defense-in-depth for the `/validate` path.)

## v0.3.145 — fix: `/validate` wrote its temp IDS into the read-only container path
The stored-IDS validation (v0.3.143) wrote the temporary `.ids` next to the source tree
(`_DATA_SRC.parent`), which is writable locally but **read-only (`/app`) in the deployed container** —
so `POST /validate` with an uploaded or pinned IDS raised `PermissionError` in production (and reddened
CI once `test_stored_ids` first exercised that path). Now writes to the OS temp dir via
`tempfile.mkstemp`. No API change.

## v0.3.144 — openBIM: COBie Contact / Zone / System tabs
Rounds out the COBie handover workbook with the three tabs owners most often flag as missing, all
derived from the model.
- **Contact** — the people/organizations behind the model (keyed by email), from
  IfcPersonAndOrganization / IfcPerson / IfcOrganization, deduped.
- **Zone** — spatial groupings of spaces (IfcZone) with their member space names.
- **System** — functional groupings of components (IfcSystem / IfcDistributionSystem) with their
  member component names + predefined type.
- The COBie export now **merges** same-named sheets across sources instead of clobbering — so the
  model-derived System and the commissioning-derived System land in one tab; `_rows_to_sheet` takes
  the **union** of columns so no source loses a field.
- `test_cobie` (synthetic IFC) pins the extraction; `test_closeout` asserts the tabs + the merge.

## v0.3.143 — openBIM: pin a project IDS + validate against it
A project can now **pin the information-delivery specification (IDS)** its model must satisfy — the
EIR/BEP-mandated one — so validation runs against it every time without re-uploading.
- **`PUT/GET/DELETE /projects/{pid}/ids`** store, inspect (`?download=1` streams it), and clear the
  pinned IDS (object storage; editor to change, viewer to read). Store/clear are audit-logged.
- **`/validate` precedence**: an uploaded `.ids` still wins; otherwise `ids=auto` (default) uses the
  pinned IDS when present, else the built-in QA specs. `ids=stored` forces the pinned one (404 if
  none); `ids=default` forces the built-ins. Both JSON summary and the BCF punch list honor it.
- **Web**: the IDS Requirements panel gains a **"📌 Pin as project IDS"** action (builds the selected
  use-case IDS and pins it) with live status + unpin; `client` gets `pinProjectIds`/`projectIdsStatus`/
  `unpinProjectIds`/`idsBuildBlob`.
- Fixed a latent shared-temp-file collision in `/validate` (per-project temp name now).
  `test_stored_ids` pins the full lifecycle + precedence end-to-end (real IFC + real IDS engine run).

## v0.3.142 — openBIM: real bSDD linked-data alignment
Turns the bSDD story from "is it classified?" into "is it *linked* to a buildingSMART Data
Dictionary?" — genuine linked-data alignment, building on the v0.3.137 bSDD client + registry.
- **`bsdd.is_bsdd_uri()` / `parse_uri()`** recognize and decompose real bSDD class URIs
  (`identifier.buildingsmart.org/uri/<org>/<dictionary>/<version>/class/<code>`).
- **Alignment scoring** now reports two honest tiers — `classified` (has any type/classification)
  vs **`bsdd_linked`** (classification is an actual bSDD URI) — plus the distinct dictionaries the
  model references (Uniclass, IFC, an EIR-mandated one…), so a reviewer sees *which* it aligns to.
- **JSON-LD export** emits a bSDD-classified element's URI as a resolvable `@id` classification node
  (`"classification": {"@type": "@id"}` in the context), so the model graph is true linked data that
  resolves against bSDD — not just a bag of local codes.
- `test_bsdd` extends to pin URI recognition/parse, the two-tier alignment, and the JSON-LD linkage.

## v0.3.141 — Enterprise auth: TOTP two-factor authentication
Optional time-based one-time-password MFA, stdlib-only (no new dependencies) — a second factor at
sign-in for accounts that opt in.
- **`totp.py`** implements HOTP/TOTP (RFC 4226 / 6238) with HMAC-SHA1, a ±1-step skew window, an
  `otpauth://` provisioning URI for any authenticator app, and salted one-time recovery codes. The
  crypto is pinned to the published RFC test vectors.
- **Enrollment**: `POST /auth/mfa/setup` issues a secret + QR/manual key; `POST /auth/mfa/enable`
  confirms with a live code and returns 10 one-time **recovery codes** (shown once; only hashes are
  stored). `GET /auth/mfa/status`; `POST /auth/mfa/disable` requires password **and** a live code.
- **Login becomes two-step** when MFA is on: password → a short-lived challenge ticket, then
  `POST /auth/mfa/verify` with a TOTP *or* a (single-use) recovery code → session. Accounts without
  MFA are unchanged.
- **Web**: account-menu "Two-factor auth…" (enroll with key + code, view recovery status, disable)
  and a sign-in challenge step; `askText` gains a masked-`password` option.
- Additive schema sync adds `mfa_secret/mfa_enabled/mfa_recovery`. `test_mfa` pins RFC vectors + the
  full enroll → challenge → recovery → disable flow. Enable/disable/recovery-use are audit-logged.
  (SAML 2.0 SP + SCIM 2.0 remain — they need a live test IdP.)

## v0.3.140 — Enterprise auth: session revocation ("sign out everywhere")
Bearer tokens can now be revoked before they expire — closing a real gap where a leaked token
stayed valid for its full 7-day life even after the password was changed.
- **Token epoch** — every auth token carries an issued-at (`iat`); each account has a `token_epoch`
  watermark. The RBAC gate rejects any token issued before the watermark, so revocation is immediate
  (no session table needed). Additive schema sync adds the column to existing DBs.
- **Password change now revokes other sessions** — changing your password (or an admin resetting it,
  or a reset-token redemption) bumps the watermark, invalidating every other outstanding token. The
  current tab is handed a fresh token so it stays signed in.
- **"Sign out everywhere"** — a new account-menu action (`POST /auth/logout-all`) revokes all other
  sessions after a suspected token leak. Admins get a per-user **Revoke sessions**
  (`POST /auth/users/{u}/revoke-sessions`) for offboarding / lost devices — distinct from
  deactivation (revoke lets them sign in again; deactivate blocks re-login).
- All revocation events are audit-logged. `test_sessions` pins the contract end-to-end.
  (SAML/SCIM and TOTP MFA are the next enterprise-auth increments.)

## v0.3.139 — Web lint gate (ESLint, flat config) wired into CI
Adds static analysis to the web app so genuine defects (unreachable code, bad awaits, dead
expressions) are caught in CI alongside the strict `tsc` typecheck and the Vitest suite.
- **ESLint 9 flat config** (`apps/web/eslint.config.js`) with a pragmatic, low-noise ruleset:
  real-bug rules stay errors; patterns this codebase adopts on purpose (`any` at IFC/three/@thatopen
  boundaries, non-null assertions, `const self = this` closure capture in object-literal getters) are
  off or warnings, so the signal isn't drowned out. New `npm run lint` / `lint:fix` scripts.
- **CI gate** — a Lint (ESLint) step runs before the Vitest job in the web workflow.
- **Baseline cleaned to zero** — the 70-file baseline surfaced only 3 errors + 1 warning, all in
  `portal.ts`/`proforma.ts`; fixed by converting two side-effecting ternaries to `if/else` and one
  `let`→`const`. No behavior change.
- **Single, pinned toolchain** — a root `eslint` pin + override collapses the dependency tree to one
  ESLint (9.39.5), so `npm ci` is deterministic and the CLI resolves the same version everywhere.

## v0.3.138 — Security: pin the auth path fail-closed (regression guard)
Audited the whole auth/authz path for fail-open behavior and confirmed it is already **fail-closed** —
`verify_token` / `verify_password` / `signing.verify_path` all return a deny value (None/False) on any
malformed input or exception, never an allow, and the RBAC middleware denies anonymous callers under
RBAC. To keep it that way, `test_security` now pins the contract: a garbage / undotted / **tampered**
bearer token is rejected (401/403) by the gate and `verify_token` returns `None` for it, while the
genuine token still resolves — so a future edit can't silently turn an auth error into access.

## v0.3.137 — openBIM: version-pluggable standards registry + BCF 3.0 + bSDD; money-math tests
Makes the platform's open-standard support **pluggable to any version**, widens interoperability, and
pins the most error-prone financial math.
- **Money-math correctness tests** — the **equity waterfall** (`proforma/waterfall.run_waterfall`:
  pref accrual → return-of-capital → IRR-hurdle promote tiers) and the **GL trial balance** were only
  exercised indirectly. `test_waterfall` pins them to hand-computed numbers (72 pref + 428 RoC = 500 to
  the LP, 472 unreturned) plus hard invariants: dollar conservation across arbitrary multi-period cash,
  full return of capital before promote, the promote actually promoting the GP, and European style
  withholding promote until the LP is whole. `test_accounting` now asserts the double-entry invariant —
  trial balance debits == credits (== 125000) and the GL columns balance.
- **openBIM version registry** (`openbim.py`) + **`GET /openbim/capabilities`** — one source of truth
  for which open standards the platform speaks (IFC, BCF, IDS, bSDD, COBie, ISO 19650 CDE) and, per
  standard, which versions it **reads** and **writes**. The version lists are **derived from the live
  engines** (BCF versions from `bcf_io`, IFC schemas from `model_capabilities`) so the matrix can't
  drift from what's actually implemented, and adding a future version (IFC5, BCF 3.x, IDS 2.0) is a
  registry entry + an adapter rather than scattered `if version ==` edits. `supports(standard, version,
  mode)` answers "do we read/write X vN?" for guards and agents. `test_openbim_registry`.
- **BCF 3.0 read/write.** `bcf_io.py` (previously 2.1-only) now writes **BCF 3.0** on request and
  auto-detects the version on import. In 3.0 the `<Comments>` and `<Viewpoints>` move inside `<Topic>`
  and `<Labels>` become a `<Labels><Label>…</Label></Labels>` group — so a 3.0 file from a newer
  BIMcollab / ACC no longer silently loses its comments and labels on import. Both BCF export endpoints
  (`GET …/bcf/export` and `GET …/modules/{key}/bcf/export`) take `?version=2.1|3.0` (2.1 remains the
  default); import auto-detects. `test_bcf` gains a 3.0 round-trip + a crafted-3.0-file read.
- **bSDD lookup.** New `bsdd.py` — a thin, cached client for the buildingSMART Data Dictionary
  (`api.bsdd.buildingsmart.org`): `GET /bsdd/search?q=` finds classes, `GET /bsdd/class?uri=` resolves
  a class's canonical URI + property set. Fixed trusted host (no SSRF surface), 8s timeout, graceful
  502 on outage. Turns the classification alignment proxy into a path to real dictionary URIs.
  `test_bsdd` mocks the HTTP (no live network) — search/class parse, cache-hit, defensive parse, 404/502.

## v0.3.136 — openBIM: IDS validation failures export as a BCF punch list
Closes the model-QA loop. `POST /projects/{pid}/validate?format=bcf` now returns a **.bcfzip** of the
IDS non-conformances — one topic per failing specification, with that spec's failing elements selected
as the topic's components — so an IDS audit round-trips into Solibri / ACC / BIMcollab exactly like any
coordination issue, and a coordinator can jump straight to the offending elements. `format=json`
(default) is unchanged. Reuses the existing IDS validator (`aec_data.validate`) and BCF writer
(`bcf_io.export_records_bcfzip`); the new pure `validate.failures_to_bcf_records()` does the mapping.
`test_ids_authoring` covers the conversion + a real round-trip through `parse_records_bcfzip`.

## v0.3.135 — Accessibility: every native prompt/confirm replaced with keyboard-navigable modals
Removes the last blocking `window.prompt()`/`window.confirm()` dialogs from the app — 42 call sites
across the viewer, portal, drawings, connections, account, finance, and PDF-takeoff flows now use the
shared accessible modal helpers (`confirmModal` / `askText` / `promptModal`), which trap focus, close
on Esc/backdrop, restore focus on close, and carry `role="dialog"` + `aria-modal`. Destructive actions
(delete/remove/untie) get a red-styled confirm button. Behavior and every message string are unchanged;
only the dialog is now navigable and screen-reader friendly. (The remaining `window.prompt` in the
built bundle lives inside the third-party @thatopen viewer library, not our code.)

## v0.3.134 — Accessibility: reduced-motion support + screen-reader announcements
P2 a11y quick wins (Section 508 / WCAG 2.1 — often a procurement gate), no functional change.
- **Reduced motion:** a global `@media (prefers-reduced-motion: reduce)` rule near-instantly completes
  every transition/animation (toast slide-ins, spinner, panel fades) for users who set that OS
  preference — state still changes, just without the motion. Leaves the 3D viewer's own render loop
  alone (that's content, not decoration).
- **Screen-reader announcements:** the toast host is now a polite `aria-live` region (`role="status"`),
  so notifications are announced instead of being silently invisible to assistive tech; **error** toasts
  use `role="alert"` for immediate (assertive) announcement. The loading overlay is likewise a
  `role="status"` live region that announces its label (incl. download progress), with the spinner
  marked `aria-hidden`.

## v0.3.133 — P1 hardening: audit the contractual mutations + count without loading + CI test guard
Follow-on to the v0.3.132 P0 block — enterprise-readiness P1 items, all behavior-preserving.
- **Audit-log coverage for contractual mutations:** module workflow **transitions** (RFI answered,
  CO approved — `module.transition:<key>:<action>`, with actor, record id, and the resulting state),
  record **deletes** (`module.delete:<key>`), and **bulk** actions now write to the append-only
  `audit_log` (readable at `GET /audit`). Previously only project/member/user/settings/contract/IFC
  events were audited; the config-engine state changes — the ones an owner or auditor most needs to
  reconstruct — were not. `test_audit_coverage`.
- **Executive report counts via SQL aggregate:** the executive summary tallied open/total RFIs,
  submittals, change orders and incidents by loading every record (up to 100k per module) into memory;
  it now uses a single `GROUP BY workflow_state` per module (`state_counts`), which is hardened to
  return `{}` for an unknown module and key a NULL state by `""`. `test_search_alerts` covers it.
- **CI test-manifest guard:** `run_tests.py` now fails the gate if any `test_*.py` on disk isn't
  registered in its hand-maintained `TESTS` list — a test nobody runs can no longer slip in silently.
- **Green CI restored (bundle-budget false positive):** the app-shell size guard filename-matched every
  `index-*.js` chunk, so it wrongly counted the lazy **pdf.js** vendor chunk (its source module is
  `index.js`, ~163 KB, loaded only when a PDF opens) as part of the eager shell — pushing the reported
  shell to 330 KB and failing the build on every push. It now derives the true entry from
  `dist/index.html` (entry chunk + CSS + the split `app-*` chunk); the real first-party shell is 166 KB,
  well within the 220 KB budget.

## v0.3.132 — P0 security: close cross-tenant access + gate SSO + atomic refs
The must-fix block from the enterprise-readiness audit — no data-shape or workflow change, pure hardening.
- **Cross-tenant access closed:** every `/projects/{pid}/…` route now enforces **project membership**
  via `require_role` (reads→viewer, writes→reviewer/editor) — 59 routes that authorized on identity
  alone (incl. full model exports and financial reads) are gated. A new **CI guard** (`test_route_authz`)
  enumerates all 381 project routes and fails the build if any lacks a membership check, so it can't
  regress. `require_role` is tagged (`_role_gate`) for detection.
- **Portfolio roll-ups scoped to memberships:** the cross-project proforma / construction / executive /
  FCA roll-ups now return only the caller's projects (`rbac.member_project_ids`), never every tenant's
  GMP / EAC / IRR / equity.
- **SSO provisioning gated:** OAuth self-provisioning honors `AEC_OAUTH_ALLOWED_DOMAINS` (and an optional
  `AEC_OAUTH_NO_AUTOPROVISION=1` invite-only mode). The production boot guard now also refuses to start
  on Postgres when `AEC_TRUST_XUSER=1` (impersonation) or when `S3_ENDPOINT` is set with default
  `minioadmin` credentials.
- **Atomic human refs:** record refs (RFI-001…) now come from a per-(project,module) counter row taken
  under a row lock — concurrent creates can't collide, and deleting a record no longer lets a later
  create reuse a ref (the old `COUNT(*)` scheme did). `test_ref_counter`.

## v0.3.131 — Unified sheet view: PDF-editor markups appear on the SVG sheet (shared coordinates)
Completes the 2D convergence with a **shared coordinate space**. Every takeoff markup now stores a
page-normalized (0..1) anchor when saved from the PDF editor, so the SVG drawings viewer renders those
markups **on the same sheet** alongside its native pins — one place to see everything on a drawing.
- **PDF editor** (`pdfTakeoff`): the ⭳ Save-to-sheet path computes each markup's normalized anchor from the
  PDF page dimensions and persists `data.nx/ny`.
- **SVG sheet viewer** (`drawings.ts`): loads both its pins and the PDF-editor's takeoff markups, placing the
  latter by `nx/ny × content-box` (a distinct amber ◆ badge showing the measurement). They're the same
  `drawing_markups` rows, so they promote to RFI / delete right from the SVG view.
- No schema change (nx/ny ride in the existing `data` JSON). Web-only.

## v0.3.130 — One 2D markup model: takeoff markups persist to the sheet + promote to RFI
Converges the two previously-disconnected 2D markup systems onto one server-side store. The pdf.js
takeoff editor's structured markups (distance / area / count / rect / text / stamp) now persist into the
same `drawing_markups` table as the SVG sheet pins — so they reload on reopen and can be **promoted to an
RFI** exactly like a pin, instead of only flattening to a throwaway PDF.
- **Backend** (additive, no migration tool): `drawing_markups` gains `kind` + `data` (JSON geometry).
  New `POST /projects/{pid}/drawings/markup/bulk` saves a whole sheet's scene (`replace` clears the
  caller's own prior unpromoted markups — anything promoted to an RFI is kept). RFI promotion now carries
  the markup's measurement into the issue.
- **2D editor**: opening a drawing sheet's PDF binds it to the sheet — it **loads** existing markups and a
  new **⭳ Save to sheet** button persists them. The SVG pin view is untouched (PDF markups live in their
  own coordinate namespace on the shared store). `test_markup`.

## v0.3.129 — The 2D editor everywhere + save generated PDFs to Documents + pin perf
Optimizes the two editors and uses them to best intention throughout (from an audit of both):
- **Save generated PDFs to Documents** — a marked-up report / pay app / statement / drawing sheet can now
  be filed into the Document Manager (a folder picker → real, versioned revision) via a shared
  `saveToDocuments` helper, not just downloaded.
- **The 2D editor replaces native PDF tabs throughout** — the sheet **PDF markup** button in the drawings
  editor, the viewer's **Compose sheet (PDF)**, **G702/G703 pay app**, **lien waivers**, the project
  **status report**, **investment memo / pitch deck**, the **G702 draw package**, and **WH-347** now open in
  the in-app 2D editor (measure / mark up / save) instead of the browser's native PDF tab.
- **3D pin-overlay perf** — the BCF/RFI pin overlay reprojected every marker every frame; it now skips the
  reprojection + DOM writes unless the camera moved, the viewport resized, or the pin set changed (a still
  scene with many pins costs ~nothing).

## v0.3.128 — Every PDF opens in the in-app viewer, marks up, and saves back
Closes the gap where only local files reached the markup viewer and annotations only downloaded. The
takeoff/markup viewer (`pdfTakeoff.ts`) now opens a PDF from a **server URL** (fetched with auth), not
just a local `File`, and takes an optional **save-back callback** — with a new **⭱ Save to source**
toolbar button that flattens the markups and posts them back. A shared `openPdfUrl(api, url, name, opts)`
helper (`drawings/openPdf.ts`) is the single entry every surface routes through:
- **Record attachments** — a stored PDF attachment now opens in the viewer (📄 tile) instead of a bare
  link; the marked-up copy saves back as a new attachment on the record.
- **Document manager** — each PDF gets a **✎** action: open in the viewer, mark up, and **save as a new
  revision** (docmanager versioning/supersede).
- **Contracts / change orders** — "🖊 View & markup" now saves the redlined copy back as an attachment
  (previously the annotations were lost on download).
- **Module record PDF** — a **🖊 Markup** button opens the generated record PDF in the viewer and saves
  the marked-up copy back as an attachment.
- **Report Center** — a **🖊 Markup** button opens any report in the viewer; **PDF tools** gained
  **👁 Open & mark up…** so any PDF (including a downloaded generated one) can be viewed/marked up in-app.

## v0.3.127 — A/E/C stamps & professional seals (submittal review + PE/RA seal)
Real construction/design stamping on PDFs — the two legally distinct classes, done properly.
- **Stamp template library** (server = source of truth, `stamps.py` + `GET /stamps/library`): submittal
  **review** (both **EJCDC** — Approved / Approved as Noted / Revise and Resubmit / Rejected, and **CSI**
  — No Exceptions Taken / Make Corrections Noted / Amend and Resubmit / Rejected / For Record Only),
  **inspection** (Pass / Partial / Fail), and **status** (For Construction / Void / As-Built …). Review
  stamps carry reviewer, firm, in-responsible-charge, submittal no., spec section, date — and bake in the
  standard **design-conformance disclaimer** (review is only for general conformance with the design
  concept; the contractor keeps responsibility for quantities, dimensions, means/methods, coordination).
- **Professional seal + signature** (`POST /pdf/seal`): renders a *visible* PE/RA seal + signature/date
  block, then applies a **tamper-evident PAdES digital signature LAST** so any later change is detectable.
  Honest about compliance — the self-signed platform certificate is demonstration / tamper-evidence, not
  board-accepted sealing; configure the licensee's own certificate (`ESIGN_P12`) for regulatory use.
- **UI**: a **🏛 Stamp & seal PDF** tool — pick a PDF, choose a template, fill fields / disposition, place,
  and download the stamped or sealed PDF. Client methods `stampLibrary` / `pdfStamp` / `pdfSeal`.
- Rendering is reportlab overlay + pypdf composite (permissive licenses; **no PyMuPDF**). `test_stamps`.

## v0.3.126 — PDF markup: stamps + tool sets + server merge/split/rotate (phases 2–3)
Completes the PDF markup/manipulation stack — interactive stamps/text + reusable tool sets on the
client, and server-side page ops via pypdf. Still permissive-only (no PyMuPDF/AGPL).

- **Text + dynamic stamps** in the PDF takeoff — a 𝗧 Text tool and a 🔖 Stamp picker with dynamic
  stamps (APPROVED / REVIEWED / FOR CONSTRUCTION / VOID / AS-BUILT / `{{user}} · {{date}}` …) whose
  `{{user}}/{{date}}/{{time}}/{{file}}` fields resolve at placement. They render on the overlay and
  **flatten into the exported PDF** (stamps in a red box).
- **Tool sets** — 💾 Save / 📂 Load the whole markup scene (calibration + all markups) as JSON, so a
  set of stamps/measurements is reusable and shareable across sheets (the Bluebeam Tool Chest idea).
- **Server PDF ops (`pdfops.py`, pypdf)** — `POST /pdf/{info,merge,split,extract,rotate}`: merge a
  drawing set into one file, split to one-PDF-per-page (zip), extract a page range (`1,3,5-7`), rotate
  by 90°. A **🗂 PDF tools** launcher (merge/split/rotate/extract uploaded PDFs). Non-PDF uploads 422.

Verified: `test_pdfops` (engine + HTTP merge/split/extract/rotate + non-PDF reject); web typecheck +
build + 59 vitest.

## v0.3.125 — PDF markup: flatten to a real PDF (markup stack, phase 1)
First phase of a Bluebeam-Revu-style PDF markup/manipulation stack (three decoupled layers: PDF.js
render · interactive markup · pdf-lib/pypdf persistence). Built on the existing PDF takeoff.

- **Flatten markups into a downloadable PDF** — the ⤓ PDF button in the PDF takeoff burns every markup
  (distance, area, count, rectangle + label/quantity) into a real PDF via **pdf-lib** (MIT), so a
  marked-up drawing round-trips as a PDF, not just CSV. Handles the PDF.js(top-left)→PDF(bottom-left)
  Y-flip; markups are page-tagged so multi-page sets export to the right page (also fixes cross-page
  overlay bleed).
- pdf-lib is code-split (dynamic import) — no cost to the main bundle until you export.

Deliberately **permissive-only**: pdf-lib (client) + pypdf (server, already a dep) — **no PyMuPDF**
(AGPL, incompatible with a proprietary product without a paid Artifex license). Next phases: Fabric.js
interactive stamps + tool sets, and server-side pypdf merge/split/rotate.

Verified: web typecheck + build (pdf-lib bundles) + 59 vitest.

## v0.3.124 — Drawing revisions, sealed issuances, title blocks (AIA completion)
Completes the AIA drawing-issuance chain from v0.3.123 — revision deltas, digital seals, and title-block
metadata.

- **Revision / delta register**: `POST /projects/{id}/drawings/{drawing_id}/revise` records a delta on a
  sheet (rev, date, description) and can cite the driving change instrument (**ASI / CCD / Addendum /
  Bulletin**); it appends to the sheet's revision block and bumps the current revision.
  `GET …/drawing-set/revisions` is the cross-sheet register (newest first) with a by-instrument rollup —
  the "what changed, when, and why" log a set carries.
- **Sealed issuances (PAdES)**: `GET …/drawing-set/issuances/{iid}/sealed.pdf` returns the issuance
  transmittal **digitally sealed** by the professional of record via the existing e-sign — the
  tamper-evident electronic seal jurisdictions require for permit/IFC submittal (unsealed with
  `X-Sealed: false` when e-sign isn't configured).
- **Title-block completeness**: generated sheets (`sheet.svg`/`sheet.pdf`) now carry **ISSUED FOR** +
  **REV** in the title block (`?purpose=&rev=`).
- Web: a revision register + 🔏 sealed-PDF links on the Drawing-set register; `reviseDrawing` /
  `drawingRevisions` / `issuanceSealedUrl` client methods.

Verified: `test_drawing_revision` (deltas cite ASI, register rollup, sealed PDF) + `test_preview`
(title-block change safe); ruff clean; web typecheck + build.

## v0.3.123 — AIA drawing issuance: per-discipline sheet set + issuance register
Turn the model into a full, correctly-numbered 2D drawing set, then release it the way an A/E office
does — dated issuances for a purpose, with the sheet-index × issuance matrix the standards expect.

**Discipline sheet-set generation.** **`sheetgen.py`** generates a standard set — **G-** General ·
**C-** Civil · **L-** Landscape · **S-** Structural · **A-** Architectural · **FP-** Fire Protection ·
**FA-** Fire Alarm · **P-** Plumbing · **M-** Mechanical · **E-** Electrical · **T-** Telecom — each a
cover/notes sheet, one plan **per building level** (S-101…S-1NN), and the usual elevations/sections/
details/schedules, numbered per NCS (`M-101` = Mechanical / Plans / 01). **Fire Alarm (FA-)** is a
distinct series from Fire Protection (FP-) in the vocabulary, `parse_sheet_id`, naming validation and
the `drawing` module. `GET …/drawing-set/plan` (preview) + `POST …/drawing-set/generate` (auto-detects
disciplines from the model, or `{all:true}`/explicit list; idempotent). **Mass-ready**: bulk-inserts in
one transaction — a 50-storey, 9-discipline set (532 sheets) generates in ~0.1s (was ~11s).

**Drawing issuance register (AIA/CD).** New **`issuance.py`** + `drawing_issuance` module: issue the
current set for a **purpose** (SD/DD/CD/Issued-for-Permit/Bid/Construction/Addendum/Conformed/Record),
snapshotting every sheet + its revision. `POST …/drawing-set/issue`, `GET …/issuances` (history),
`GET …/issuance-matrix` (the **sheet-index × issuance grid** — each sheet's revision in each issue),
per-issuance transmittal PDF stamped with the purpose. A **📤 Issue set** control + issuance table +
matrix on the Drawing-set register.

Verified: `test_sheetgen` + `test_issuance` (issue snapshots, matrix reconstructs which sheet went in
which issuance, per-issuance transmittal, AIA purposes); mass test 532 sheets / 0.1s; ruff clean; web
typecheck + build clean.

## v0.3.122 — Battle-tested for mega-project scale (200k+ records)
Load-tested every heavy read path against a seeded ~220k-record project (research-sized for a $500M+
job: ~10k RFIs, 20k cost lines, 12k punchlist, 15k timesheets, …) and fixed what didn't hold up.

- **my-work** was returning **every** actionable row across all modules — a ~25 MB, 4 s response on a
  mega project. Now a bounded to-do queue: newest-N per module (indexed) + a 500-item cap, lean columns
  only (no JSON blob). 25 MB → ~100 KB, 4 s → ~0.5 s.
- **BCF export** ran a per-record `get_record` (comments/timeline/rollups it never uses) — an N+1 that
  took ~12 s on an 8k-issue module. `list_records` already returns every column BCF needs, so it's one
  query now (~1 s) with a 25k-record cap (logged when hit).
- **Dashboard** loaded the JSON `data` of the entire non-terminal tail of all 118 modules just to check
  due dates. Now it reads JSON only for modules that have a due-date field and pulls action items from a
  bounded, state-filtered query. 3.8 s → ~1.2 s.
- **Indexes**: added `(project_id, created_at)` — every list does `ORDER BY created_at`, previously a
  filesort — and `(project_id, assignee)` for the work queues. Backfilled on existing DBs at startup.
- **Connection pool** is now sized from the environment (`AEC_DB_POOL_SIZE`/`_MAX_OVERFLOW`/`_RECYCLE`/
  `_TIMEOUT`) instead of SQLAlchemy's 5+10 default, which starves a multi-worker API under load.
- New reusable harness: `seed_scale.py` (bulk-seeds every module at configurable volume) +
  `loadtest.py` (per-endpoint latency + concurrency), and a `test_scale` regression that locks in the
  pagination clamp, bounded my-work, single-query BCF, and index presence.

Verified: full backend suite green (incl. `test_scale`); ruff clean; security review clean.

## v0.3.121 — Cost traceability by IFC GlobalId (model → cost → GL)
Closes the moat of the resourcing/accounting plan — cost and billing tied to the actual model elements
they pay for, by GlobalId. A cost-code-only ledger can't answer "what did *this* column cost?"; this can.

- **`traceability.py`** walks every cost line (budget / commitment / direct cost / sub invoice) that
  carries `element_guids` and computes **coverage** — the share of job cost tied to real model elements —
  overall and **per cost code**, plus `element_costs(guid)` for "what did this element cost?" (by kind).
- Endpoints `GET /projects/{pid}/cost/traceability` and `GET /projects/{pid}/elements/{guid}/costs`.
  A **🔗 Cost Traceability** panel: coverage KPIs (color-banded), a GlobalId lookup, and a
  per-cost-code coverage table. `costTraceability` / `elementCosts` client methods.

Verified: `test_traceability` (coverage 93.3%, element→cost by GUID and by kind, untagged→0); ruff clean;
web typecheck + vitest + build.

## v0.3.120 — General ledger: balanced double-entry journal + trial balance + chart of accounts
Closes A2 of the resourcing/accounting plan — the posting bridge to the accounting system of record.

- **`accounting.py`** gains a standard construction **chart of accounts** (AR, contract asset/liability,
  AP, contract revenue, construction costs) and a **balanced double-entry journal** posted from job cost
  (Dr Construction Costs / Cr AP), owner billing (Dr AR / Cr Revenue) and the **WIP percentage-of-completion
  adjustment** (under-billing → Dr Contract Asset / Cr Revenue; over-billing → Dr Revenue / Cr Contract
  Liability) — so Contract Revenue nets to **earned**. Plus a **trial balance** (debits = credits, per account).
- Endpoints `GET /accounting/chart-of-accounts`, `/accounting/journal-entries`, `/accounting/trial-balance`
  (the GL-CSV + QuickBooks-IIF exports already existed). A **📒 General Ledger** panel (trial balance +
  journal + CSV/IIF export). `journalEntries` / `trialBalance` client methods.

Verified: `test_wip` extended (journal balanced, trial balance ties, revenue nets to earned, over-billing
posts to contract liability) + `test_accounting`; ruff clean; web typecheck + vitest + build.

## v0.3.119 — Contractor financial statements (POC income statement + contract position)
The construction-only statement lines a generic P&L / balance sheet miss — the balance-sheet twin to the
WIP schedule (A2 of the resourcing/accounting plan).

- **`contractor.py`** — from the WIP: a **percentage-of-completion income statement** (revenue = earned,
  not billed; cost of revenue = cost-to-date; gross profit + margin) and a **contract-position** section
  (**contract asset** = under-billings, **contract liability** = over-billings, **retainage receivable**,
  **accounts payable** from unpaid sub invoices, and **net contract working capital** = under-billings +
  retainage − over-billings − AP). Company-wide roll-up too.
- Endpoints `GET /projects/{id}/contractor-statements` + `/contractor-statements/portfolio`; a
  **Contractor Financial Statements** report; the statements render on the WIP panel + a second PDF link.
- `contractorStatements` client method.

Verified: `test_wip` extended (POC income statement, contract asset/liability, net working capital,
portfolio, both report PDFs); ruff clean; web typecheck + vitest + build.

## v0.3.118 — WIP schedule: percentage-of-completion + over/under-billing
The defining construction-accounting artifact, and the accounting twin to the earned-value module —
built on the job cost that already exists, no new cost model.

- **`wip.py`** — percentage-of-completion (**cost-to-cost**: cost-to-date ÷ total estimated cost) →
  **earned revenue** = % complete × contract value → compared to billed for the contract position:
  **over-billing** (billings in excess of costs & earnings — a **liability**) or **under-billing** (costs
  & earnings in excess of billings — an **asset**, and the classic cash drag on profitable jobs). Plus
  retainage, cost-to-complete, gross profit/margin, profit-to-date and backlog.
- Endpoints `GET /projects/{id}/wip` and `GET /wip/portfolio` (one row per job, worst cash position
  first). A **📄 WIP Schedule** panel (KPIs + a colour-coded over/under-billing callout + contract-position
  table + portfolio roll-up) and a signed PDF report. Client `wip` / `wipPortfolio`.
- Contract value comes from the prime contract + approved COs (falling back to the SOV); billings from
  owner invoices; retainage from the G703 — all reused from `cost.py`.

Verified: `test_wip` (POC 50%, under-billed 200k asset flips to over-billed 200k liability, gross profit
+ margin, backlog, retainage, portfolio + PDF); ruff clean; web typecheck + vitest + build. Demo shows a
39%-complete job under-billed ~$7.8M — the profitable-but-cash-short story.

## v0.3.117 — Resource loading, made real: cost-loaded, relational, with leveling
Promotes resource loading from a flat crew-count (and no UI) to a relational, cost-loaded engine with a
panel — tying the schedule to resources and cost codes.

- **`resource_assignment` model** — ties a resource (Labor / Equipment / Material, with a rate) to a
  **schedule activity** and a **cost code**. That's the schedule ↔ resource ↔ cost join; the cost also
  rolls up onto the cost code (`resource_budget`).
- **Cost-loaded engine** — `resource_loading.py` now spreads assignment units + cost across each week
  into a **manpower histogram** (by trade / type) and cumulative **unit + cost S-curves**, with
  over-allocation flags against an availability cap. Falls back to activity `crew_size` when no
  assignments exist, so the classic curve still renders.
- **Leveling advisory** — `GET /schedule/resource-leveling?cap=` lists over-allocated work that still
  has **CPM total float** and can be smoothed (shifted within float) to shave the peak without moving the
  finish; critical-path work is reported as locked. Advisory only.
- **UI** — a `👷 Resource loading` panel (Schedule stage): editable availability cap, stacked-by-trade
  histogram, cost S-curve, KPIs (peak / total cost / over-allocated weeks) and the leveling table, plus a
  PDF report. Demo seeds six crews so the sample shows a real peak + leveling candidates.

Verified: `test_resource_loading` (cost-loaded histogram + S-curves, over-allocation, `resource_budget`
rollup, leveling picks the float-bearing work, crew_size fallback, PDF) + the module-contiguity gate;
ruff clean; web typecheck + vitest + build.

## v0.3.116 — Portfolio CPI (cost efficiency) in the executive roll-up
The cross-project executive dashboard already showed SPI + EAC + variance-at-completion per project;
it now also shows **CPI** — cost efficiency (EV ÷ AC) — so the "which jobs are bleeding money?"
question is answerable at the portfolio level alongside schedule.

- `px.summary()` gains a `cpi` in its budget block (EV/AC, the same numbers the project dashboard
  uses); surfaced per-project in `/portfolio/executive` and as a new **CPI** column (green ≥ 0.95,
  red below) next to SPI in the executive table.

Verified: `test_dashboard`; ruff clean; web typecheck + vitest + build. (Additive field — no
behaviour change to existing rows.)

## v0.3.115 — EVM charts: CPI–SPI quadrant + captured-snapshot performance trend
Two earned-value visualizations that make cost/schedule performance readable at a glance, plus the
persisted snapshots that back a real historical trend.

- **CPI–SPI quadrant (the "bullseye")** — a new `scatterQuadrant` chart plots the project and every
  control account on the cost × schedule plane, split at 1.0: upper-right is under budget + ahead,
  lower-left is trouble. Built from the existing EVM snapshot — no extra query.
- **Persisted EVM snapshots** — a new `evm_snapshot` module + `POST /projects/{id}/evm/snapshot`
  captures the current state (CPI/SPI/SPI(t)/EAC/% complete) as a dated baseline. `GET …/evm/trend`
  returns them oldest-first, and the dashboard shows a **CPI/SPI performance-index trend** (a falling
  line = efficiency slipping) with a 📸 Capture-snapshot button. The trend line also renders in the
  EVM PDF report once ≥ 2 snapshots exist.
- **Sample model** now seeds six weekly snapshots so the demo trend tells a real "schedule slipping"
  story out of the box.

Verified: `test_evm` (capture → trend, quadrant data, PDF with trend) + `charts` (scatterQuadrant plots
+ escapes) ; ruff clean; web typecheck + vitest + build.

## v0.3.114 — Element property + classification editor; sample model refreshed
Closes the model-authoring loop and brings the demo sample in line with everything shipped this cycle.

- **Structured property + classification editor** — selecting an element in the viewer now offers an
  **✎ Edit / Classify** form: set a Pset property (typed str/float/int/bool) and attach a
  **classification reference** (Uniclass 2015 · OmniClass · Uniformat II · MasterFormat), replacing the
  old free-text prompt. Backed by the `set_element_pset` and new **`set_classification`** edit recipes
  (GUID-stable; reuses one `IfcClassification` source per system so tags don't duplicate). Each edit
  re-publishes and the panel re-reads the element.
- **Model-based EV, no false alarms** — `evm.model_ev()` now only flags a *front-loaded SOV* once field
  verification actually exists (`has_field_data`); an un-surveyed job no longer reads as a distortion.
- **Sample model refreshed** — the Pages demo model now carries the full Draft-family set (steel
  columns/beams, rebar, footings, duct/pipe/cable-tray runs, ceiling + floor coverings, railing,
  electrical panel + sanitary terminal), realistic **EVM data** (cost-coded activities with EV methods +
  actuals → CPI/SPI, S-curve, Earned Schedule, model-EV) and a derived grid — surfaced across Model
  Analysis, Earned Value and the drafting refs.

Verified: `test_authoring_props` (Pset + classification round-trip) + `test_evm`; the model-authoring
+ structural/MEP/architectural/grid suites; typecheck + vitest (58) + build; ruff clean.

## v0.3.113 — Earned Value Management, E7: model-based EV (module complete)
The differentiator — earn value off the **physically installed model**, not a billing SOV — completes
the EVM module (E1–E7).

- **Model-based EV** (`evm.model_ev()` + `GET /projects/{id}/evm/model-ev`) — EV grounded in
  field-verified installed model elements (the install-coverage engine): **model % complete = installed
  elements ÷ total × BAC**, the units-complete method sourced from the model. It's independent of the
  schedule/billing %, so it **cross-checks the schedule EV**: when reported EV runs materially ahead of
  physical installation, it flags a likely **front-loaded SOV** — the exact distortion the research warns
  about. Surfaced on the EVM dashboard (with a ⚠ when divergent).
- With this the EVM module is complete: unified metrics + control accounts (E1), forecast family (E2),
  Earned Schedule (E3), S-curve + dashboard + report (E4/E5), EV measurement methods + stage-adaptive
  forecast (E6), and model-based EV (E7).

Verified: `test_evm` (model-EV graceful with no index + structure) + the full E1–E6 checks; typecheck +
vitest (56) + build; ruff clean.

## v0.3.112 — Earned Value Management, E6 + adaptive forecast
EV measurement rules of credit + the stage-adaptive forecast guidance from the construction-forecasting
research.

- **EV measurement methods** — `schedule_activity` gains an **EV method** (percent · **0-100** ·
  **50-50** · **units** · milestone · **LOE**) + units-complete/units-total. The engine honours the rule
  of credit: 0/100 earns nothing until complete; 50/50 earns half once started; units earns
  units_complete/units_total; **LOE earns exactly its planned value (EV=PV)** so it can't distort the
  schedule variance. Applied consistently in the metrics, S-curve, and Earned Schedule.
- **Stage-adaptive forecast guidance** — the forecast now flags the project **stage** and which forecast
  to trust: **early/mid → Earned Schedule (SPI(t))** is most accurate (cost EAC is volatile), **late
  (≥55%) → cost-efficiency (BAC/CPI)** firms up. Straight from the study finding that no single EAC
  formula is best at every stage. Shown on the EVM dashboard forecast card.

Verified: `test_evm` extended (0/100 → EV 0, 50/50 → 50k, units 3/4 → 75k; stage recommendation) +
`test_modules` (new fieldset passes the contiguity gate) + typecheck + vitest (56) + build; ruff clean.

## v0.3.111 — Earned Value Management, E4+E5: S-curve + EVM dashboard
Makes the EVM engine **visible** — an **📊 Earned Value** destination in the construction workspace.

- **S-curve** (`evm.scurve()` + `GET /projects/{id}/evm/scurve`) — cumulative **PV** (full planned
  baseline) plus **EV** and **AC** to the data date, over week/month buckets, drawn as the classic
  three-line performance chart (EV/AC lines end at the data date while PV runs to the planned finish). EV
  is reconstructed from each activity's actual window; AC from dated direct costs.
- **EVM dashboard** (`portal/panels/evm.ts`) — an indices dashboard (**CPI · SPI · SPI(t)** with health
  bands, CV/SV/SV(t)), the **forecast panel** (EAC family, ETC, VAC, TCPI + warning), the **S-curve**,
  the **Earned Schedule** summary (forecast finish + days-late), and the **control-account (cost code)
  table** — worst variance first.
- **EVM report upgraded** — the `evm` report now emits CPI/SPI/SPI(t), the full performance + forecast
  tables, Earned Schedule, control accounts, and the PV/EV/AC S-curve (was SPI + a cash curve).

Verified: `test_evm` extended (S-curve PV-full / EV-AC-to-date shape; upgraded report PDF renders) +
typecheck + vitest (56) + build; ruff clean.

## v0.3.110 — Earned Value Management, E3: Earned Schedule
Adds the modern **time-based** EVM extension that fixes the well-known defect where dollar SV/SPI decay
to $0 / 1.0 at project end regardless of lateness.

- **`evm.earned_schedule()` + `GET /projects/{id}/evm/earned-schedule?period=week|month`** — builds the
  time-phased **PV baseline curve** from the schedule, then projects current EV onto its time axis:
  **ES = C + (EV−PV_C)/(PV_{C+1}−PV_C)**, and from it **SV(t) = ES−AT**, **SPI(t) = ES/AT**, and
  **IEAC(t) = PD/SPI(t) → forecast finish date** (+ days-late). Included in the `/evm` snapshot too.
- SPI(t) stays meaningful right through completion, so a superintendent gets "**4 weeks behind, forecast
  finish 2026-XX-XX**" instead of a dollar SV that quietly returns to zero. The PV curve it returns is
  the same one the S-curve dashboard (E4/E5) will draw.

Verified: `test_evm` extended — a 40-week job at 40% complete in week 20 yields **ES ≈ 16 wk, SPI(t) ≈
0.80, forecast finish beyond plan** — plus the E1/E2 checks; typecheck + vitest (56) + build; ruff clean.

## v0.3.109 — Earned Value Management, E1+E2: unified engine + forecast family
Research-backed (PMI/ANSI-EIA-748 + a construction-forecasting study) EVM. The app had two disconnected
halves — schedule earned value (no Actual Cost) and cost actuals by cost code (heuristic forecast). This
**joins them by cost code (the control account)** into one standards-aligned metric set.

- **`evm.py` + `GET /projects/{id}/evm`** — PV, EV, AC, BAC; **CV = EV−AC, SV = EV−PV, CPI = EV/AC,
  SPI = EV/PV**, % complete, % spent, with **health bands** (good ≥1.0 · acceptable ≥0.95 · concerning
  ≥0.90 · critical). A **per-control-account (cost code) table** joins schedule EV/PV with cost AC, so you
  see which cost codes are over budget vs behind schedule.
- **Forecast family** — the four canonical **EACs** (BAC/CPI · AC+(BAC−EV) · AC+(BAC−EV)/(CPI×SPI)),
  a working EAC, **ETC**, **VAC**, and **TCPI** to BAC and to the working EAC — with the **>1.10
  structural-warning** flag. Shown together, because the best EAC is stage-dependent, not one formula.
- A `data_date` cut-off parameter for period reporting.

This is phase 1 of a full EVM module; Earned Schedule (SPI(t)), the time-phased S-curve + dashboard, EV
measurement methods, and **model-based EV from IFC quantities** follow.

Verified: `test_evm` (BAC 200k / EV 75k / PV 150k / AC 80k → CV −5k, SV −75k, CPI 0.938, SPI 0.5; the full
forecast family + TCPI warning; control-account join) + typecheck + vitest (56) + build; ruff clean.

## v0.3.108 — Model authoring: incremental preview fragments + MEP fittings
Completes the draft-performance work and rounds out MEP.

- **Incremental preview fragment** — `POST /projects/{id}/edit-preview` authors *just the placed element*
  into a minimal one-element IFC at the target level's elevation (`aec_data/preview.py`) and converts
  only that to a fragment, which the viewer loads immediately as real geometry — so the whole-model
  reconvert no longer gates what you see. Fully **fail-open**: if the source or converter is unavailable
  the viewer just keeps the optimistic amber proxy and waits for the normal publish. The preview is
  auto-disposed when the full model re-streams.
- **MEP fittings** — duct/pipe **elbows** and **tees / junctions** (`IfcDuctFitting` / `IfcPipeFitting`
  with BEND / JUNCTION predefined types) join the MEP palette, to detail the runs.
- **Testing & debug pass** — the new `test_preview` plus a regression sweep across the authoring and
  generate paths (`test_generate` / `test_estimate` / `test_engines` and the four model-authoring
  suites) all green, confirming the `edit.py` refactor (optional `profile` arg + the new recipes) didn't
  regress existing authoring.

Verified: `test_preview` (one-element metre model at the target level carrying the steel profile) + the
model-authoring + regression subset + web typecheck / vitest (56) / build; ruff clean.

## v0.3.107 — Model authoring, P6: optimistic draft placement
Drafting now gives **instant feedback** instead of a blank wait while the server authors and re-streams.

- **Optimistic proxy** (`viewer/draft/draftProxy.ts`) — the moment you place an element, a lightweight
  amber proxy (box for equipment, line for a wall/beam/duct/pipe/rebar/railing, polygon outline for a
  slab/roof/covering) appears exactly where it will land, at the active level. When the server finishes
  authoring the real IFC and the fragment is re-streamed, the proxy clears and the real geometry takes
  its place (proxies also clear on failure).

This is the client half of the draft-performance work; the server-side **incremental single-element
fragment** append (converting just the new element instead of the whole model) is the remaining
optimization and is tracked for a follow-up, since it touches the IFC→fragments publish pipeline.

Verified: web typecheck + vitest (56) + build.

## v0.3.106 — Model authoring, P3: architectural finishes (ceilings · tile · wood · cladding · railings)
Interior/finish elements complete the discipline set the Draft palette can author.

- **Coverings** (`IfcCovering`) drawn as a polygon: **ceiling** (hung near the top of the storey),
  **floor tile** (FLOORING + a ceramic-tile material), **wood flooring** (FLOORING + a Wood material),
  and **wall cladding** (CLADDING) — each by PredefinedType with an optional finish **material** and
  `Pset_CoveringCommon`.
- **Railings** (`IfcRailing`) drawn between two points at a set height.
- New `edit.py` recipes `add_covering` / `add_railing`; Architectural Draft entries for the four
  coverings + railing. Placement uses the P1 grid snap + active level.

With this the Draft palette spans all three disciplines (Architectural · Structural · MEP) — from grid
and levels to steel, rebar, MEP runs and equipment, and now finishes.

Verified: `test_architectural` (ceiling at 2.7 m, wood flooring material, cladding, railing) + typecheck
+ vitest (56) + build; ruff clean.

## v0.3.105 — Model authoring, P5: MEP families (HVAC · plumbing · electrical · fire · telecom)
The biggest discipline slice — draw distribution runs and drop equipment, authored as real IFC MEP.

- **Distribution runs** you draw as a segment: **duct** (`IfcDuctSegment`), **pipe** (`IfcPipeSegment`),
  **cable tray / conduit** (`IfcCableCarrierSegment`), and **cable / wire** (`IfcCableSegment`). Each is
  a swept section (round, or rectangular for tray) with two **connection ports** and assignment to a
  named **`IfcDistributionSystem`** (HVAC Supply / Domestic Water / Power).
- **Point equipment** you click to place: **electrical panel** (`IfcElectricDistributionBoard`),
  **outlet** (`IfcOutlet`), **light** (`IfcLightFixture`), **air diffuser** (`IfcAirTerminal`), **floor
  drain** (`IfcWasteTerminal`), **plumbing fixture** (`IfcSanitaryTerminal`), **fire alarm**
  (`IfcAlarm`), **smoke detector** (`IfcSensor`), and **data/telecom outlet**
  (`IfcCommunicationsAppliance`) — each with the correct IFC class + PredefinedType.
- New `edit.py` recipes `add_duct` / `add_pipe` / `add_cable_tray` / `add_wire` / `add_mep_terminal`;
  MEP entries fill out the Draft palette's MEP discipline. Placement uses the P1 grid snap + level.

Verified: `test_mep_families` (four run types + named systems + round/rect sections; seven point-
equipment classes with PredefinedType preserved) + typecheck + vitest (56) + build; ruff clean.

## v0.3.104 — Model authoring, P4: structural steel + rebar + footings
Real structural members in the Draft palette — authored as native, standards-compliant IFC.

- **Steel W-shapes** — `steel.py` holds the AISC W-shape table (W8×31 … W24×76, dimensions re-keyed as
  facts, [attributed](docs/ATTRIBUTIONS.md)); `add_steel_column` / `add_steel_beam` author an `IfcColumn`
  / `IfcBeam` with a **native parametric `IfcIShapeProfileDef`** (no imported geometry), with the section
  name stamped on `Pset_*Common.Reference`. A **Section** picker in the Draft form.
- **Rebar** — `add_rebar` authors a straight **`IfcReinforcingBar`** (circular section swept along the
  bar) sized by US bar designation (#3–#11) with `NominalDiameter` + `BarLength`.
- **Pad footings** — `add_footing` authors an `IfcFooting` pad below the level.
- Draft catalog gains a **`select`** parameter type (for the section / bar-size pickers); placement uses
  the P1 grid snap + active level.

Verified: `test_structural` (W-shape table inches→m; steel column → native IfcIShapeProfileDef W14×30 +
section on Pset; steel beam; #5 rebar nominal diameter + circular section; footing) + typecheck +
vitest (56) + build; ruff clean.

## v0.3.103 — Model authoring, P1: grid + levels as drafting references
The drafting reference frame — so placement lands on a grid and the right level, not free space.

- **Grid & Levels panel** in the Model tools rail. **Load grid + levels** reads the project's grid
  (`services/data/.../grid.py`): real **`IfcGrid`** axes (U/V + bubble tags) when present, else a grid
  **derived from `IfcColumn` centres** (numbered 1,2,3… / lettered A,B,C…). Axes render in 3D with
  bubbles; Draft placement now **snaps to grid intersections**.
- **Editable levels.** An active-level selector sets the **work-plane** (Draft points project onto the
  level's elevation) and passes the storey to every authoring recipe, so elements land on the chosen
  level. New `edit.py` recipes **add / rename / move** a storey (`add_storey`, `rename_storey`,
  `set_storey_elevation`) — authoring real `IfcBuildingStorey` levels.
- New endpoint `GET /projects/{id}/model/grid` (grid axes + snap intersections + storey levels).

Verified: `test_grid` (derived grid from 4 columns → axes 1/2/A/B + 4 intersections snapping to column
centres; add/rename/move-storey recipes) + web typecheck + vitest (56) + build; ruff clean.

## v0.3.102 — Model authoring, P0: the Draft panel (parametric family/element placement)
First slice of the "true model-creation program" upgrade — foundations for a full BIM family library
authored in the browser (intent) and written as real IFC on the server (source of truth), then
re-streamed as fragments.

- **Draft panel** in the Model workspace tools rail (`viewer/draft/`) — a discipline-grouped palette
  (Architectural · Structural · MEP · Site) of parametric elements and the server family catalog, each
  with a **named parameter form** (height, thickness, width, …). Pick an element, set parameters, arm
  **Place**, then click in the model: the server authors the IFC (walls, slabs, columns, beams, roofs,
  and any catalogued family) and streams it back. **Replaces the old `prompt()`-per-dimension flow** —
  no more native prompts for wall height/thickness. Supports point, two-point, and **polygon** (double-
  click to close) placement, with grid/vertex snap, ortho lock (Shift), and Esc to cancel.
- This is additive: the existing authoring recipes (`edit.py`) and the `/families/catalog` + `/edit`
  round-trip are unchanged; the Draft panel is a cleaner front-end over them. Structural depth (steel
  profiles + rebar), then MEP, then architectural coverings/finishes follow in subsequent releases,
  alongside real grid/level drafting refs.

Verified: `draftCatalog.test.ts` (recipe-param mapping for every element + family) + web typecheck +
vitest (56) + build green.

## v0.3.101 — Market intelligence & cost escalation + AI concept-render bridge
Two additions from an industry-research pass:

- **Market Intelligence & cost escalation** (`market_intelligence.py` + `market_assumption` module +
  `/market/*` endpoints + 💹 **Market Intelligence** panel in the developer workspace). A regional table
  (annual escalation %, average labour US$/hr, location index) plus a **two-speed warm/cold** demand
  signal by sector (tech-led sectors — data centres, advanced manufacturing — running hot; residential /
  commercial cold). The engine **escalates a base cost to the midpoint of construction** in the project's
  region — not just "next year" — reading a project's adopted `market_assumption` (region · sector ·
  construction start · duration) or query-param overrides. The **conceptual estimate now carries a market
  block** (regional labour + sector temperature + escalation-to-midpoint), and there's a **Market
  Intelligence & Escalation report**. Seed defaults are the **public headline figures** from Turner &
  Townsend's *Global Construction Market Intelligence 2026* — illustrative, **editable** defaults
  (attributed, not their dataset); a deployment overrides them with its own current rates.
- **AI concept-render bridge** (`render_bridge.py` + `concept_render` module + `/concept-render/*`
  endpoints + 🖼 **Concept Renders** panel in the design workspace). Like the CV-progress and RVT / payment
  bridges, it's **feature-flagged and off by default** (`AEC_RENDER_BRIDGE`): the platform builds a
  **grounded prompt** from the project's space program + massing and hands it to a connected image service,
  then ingests returned image references as reviewable `concept_render` records. When the flag is off, the
  endpoints report the bridge unavailable and **fabricate nothing** — no placeholder images. Reference
  adapter in `docs/render-bridge.md`.

Verified: new `test_market` (escalation-to-midpoint math, warm/cold signal, `market_assumption`-driven
context + escalate, conceptual-estimate market block, report PDF; bridge off fabricates nothing / on
builds a clamped grounded prompt + requires `image_url`) + full suite green, ruff clean; web typecheck +
build green.

## v0.3.100 — Close the two deferred perf items: compressed color-by + cross-worker scan cache
The two follow-ups the audit deferred are now done:

- **Compressed `color-by` + compact `ids=false` mode** — the viewer's colour-by needs the full
  GUID→bucket mapping (inherently O(elements)), so instead of capping it (which would break colouring) the
  large payload is now **gzipped on the wire** (`Content-Encoding: gzip`, transparently decompressed by
  the browser). A new **`?ids=false`** returns just labels + counts — a compact distribution for a legend
  or picker with no per-element payload.
- **Cross-worker scan cache** — the per-model-version cache for the hot `facets-list` / `color-by` scans
  is now **shared via Redis** (gzip+JSON values, TTL `AEC_SCAN_CACHE_TTL`, default 1 h) when
  `AEC_REDIS_URL` is set, so one worker's scan is reused by every other; **fail-open** to the in-process
  cache on any Redis error, matching `model_events` / the rate-limiter. Single-worker / no-Redis is
  unchanged.

Verified: new `test_scan_cache` (gzip round-trip, Redis fail-open, `ids=false`) + full suite green, ruff
clean. This closes every item from the four-dimension code audit.

## v0.3.99 — Audit follow-through (Batch 3): cache the hot model scans + windowed portfolio query
The deep-performance items from the audit — attacking the "recomputed on every request" cost of the
property-index scans:

- **Per-model-version scan cache** — the two hottest read scans (`elements/facets-list`, the O(n·psets)
  distinct-value scan, and `elements/color-by`) are now memoised keyed on the **model version**
  (`model_events`, bumped on publish). Repeated analytics requests for an unchanged model are served from
  cache instead of re-scanning every element × every property; the cache invalidates automatically when a
  new model is published, and evicts LRU-style (bounded).
- **Windowed portfolio scenario query** — `executive_portfolio` fetched **every** scenario's full result
  JSON across all projects just to keep the latest per project; it now uses a windowed
  `GROUP BY project → MAX(created_at)` join to load only the latest scenario per project.

(`color-by` still returns the full GUID→bucket mapping — the 3D viewer needs it to colour — so its payload
size is inherent; a compact run-length encoding is a tracked follow-up rather than a break-the-viewer cap.)

Verified: affected suites (analytics / portfolio / dashboard / api) green, ruff clean. Frontend bundle was
already healthy (code-split + Brotli budget) — no change. This completes the four-dimension audit
follow-through (Batch 1 perf/UX/analytics · Batch 2 demo data · Batch 3 deep perf).

## v0.3.98 — Audit follow-through (Batch 1): perf quick-wins, Documents a11y, surfaced analytics
A four-dimension code audit (wiring, UI/UX, sample data, performance) found the platform structurally
sound — **zero broken wiring** (46/46 routers, 47/47 reports, 32/32 module refs), all panels reachable.
This ships the low-risk quick wins from it:

- **Performance:** dashboard/AI-ask/closeout counts now use a SQL `COUNT` (`count_records`) instead of
  materialising whole JSON tables just to call `len()`; `properties/index` upload parses off the event
  loop (`run_in_threadpool`) and stores the received bytes verbatim (no redundant re-serialize); the
  document-manager `tree()` computes its active-file set once instead of per folder node.
- **Documents file manager (a11y + UX):** the folder tree is now keyboard-operable (`role`/`tabindex`/
  Enter-Space) instead of mouse-only; delete uses the app's accessible modal instead of the native
  `confirm()`; the two-pane layout wraps to stacked on narrow viewports; a **role filter** (PM /
  Superintendent / Architect / Engineer / QS) and a **phase-gap check** (AIA SD/DD/CD/CA/CLOSEOUT) are
  now surfaced (they reuse the by-role and phase-gaps endpoints that were built but unwired).
- **Surfaced built-but-invisible analytics:** the 🔬 Model Analysis panel now shows the **fast STEP model
  summary** (entity-type histogram, no full parse — G3), the **columnar interning efficiency** stat + an
  **EAV `params.parquet`** download (G1), and a **VIM / G3D inspect** control (G2); export links are gated
  on a loaded model (no raw 409s), and Documents + Model Analysis are now reachable from the **developer**
  workspace too.
- **A11y polish:** `th scope="col"` + `aria-label`s on the Model Analysis tables/selects.

Verified: full backend suite green, web typecheck + vitest 49/49, ruff clean.

## v0.3.97 — Ara3D-inspired efficiency track: columnar BIM data, BFAST/VIM reader, fast STEP scan
Three efficiency/interop wins drawn from a review of the [Ara3D SDK](https://github.com/ara3d/ara3d-sdk)
(MIT; see [ATTRIBUTIONS](docs/ATTRIBUTIONS.md)) — ported/adapted where it added value, skipped where our
numpy/trimesh/ifcopenshell stack already wins.

- **Columnar / interned BIM data layer** (`bim_columns.py`, inspired by Ara3D `BimOpenSchema`) — a
  **string/number-interned columnar** view of the property index + an **EAV parameter table** exported as
  **Parquet** for DuckDB/pandas/Polars analytics. Psets repeat the same keys/values across thousands of
  elements, so interning cuts RAM sharply (a small 4-wall fixture already shows ~3.4× string dedup). New
  endpoints: `/model/columnar/stats` (dedup ratio + estimated bytes saved), `/model/columnar/aggregate`
  (group-by via pyarrow compute — no Python row loop), `/model/export/params.parquet`.
- **BFAST / G3D / VIM reader** (`aec_data/bfast.py`) — a pure-Python reader/writer for the BFAST container
  + summarisers for G3D geometry (vertex/index counts + bbox) and VIM files (schema/version, buffer
  inventory, geometry stats). Opens `.vim` / `.g3d` offline via `POST /convert/vim/inspect`. Independent
  re-implementation of the public format; no Ara3D code copied.
- **Fast STEP metadata scanner** (`aec_data/step_scan.py`) — a streaming line-scan of an IFC-SPF file for
  its header + **entity-type histogram** without a full `ifcopenshell` parse (milliseconds, bounded
  memory). `GET /model/step-summary` for an instant "what's in this IFC" on large files.

Also reviewed the OpenAEC-BIM-validator repo — no integration needed: we already validate IFC against IDS
via `ifctester` (per-spec pass/fail + failing GUIDs + BCF) in `aec_data/validate.py`. Verified: new
`test_bim_columns` / `test_bfast` / `test_step_scan` + full backend suite green, web build green, ruff clean.

## v0.3.96 — Document Control: a role-based standard file manager over the project
A first-class **📁 Documents** workspace — an elFinder-style two-pane file manager (folder tree + file
list) built on a **standard, role-based project folder taxonomy** so every project is organised the same
way and required documents are never missing.

- **Standard taxonomy** (`folder_template.py`) — the industry `01_Contract Documents … 11_Final Account`
  tree with sub-folders, each node tagged with an **owner role** (PM owns the business — contracts,
  payments, variations, procurement; the **Superintendent** owns field execution — site instructions,
  inspections, NCRs, daily reports, photos; the **Architect/Engineer** own the drawing set), a discipline
  (NCS), a default **CDE state** (ISO 19650 WIP/Shared/Published) and a **required** flag.
- **Document manager** (`docmanager.py`) — bytes in object storage (`{pid}/docs/<folder>/<name>`) with a
  per-project sidecar index. Uploads **auto-name to the information standard**
  (`Type_Discipline_Description_Revision_Date`) and **never overwrite**: a new upload of the same document
  supersedes the prior revision (P01→P02…), the old one archived for audit. Move, soft/hard delete,
  download, per-folder counts that roll up to parents, and required-doc **gap** flags.
- **Role-based views** — a `by-role` endpoint and owner-role chips per folder, so a PM / Superintendent /
  architect sees the folders they own.
- **Document-Control health** — a Report Center report (naming compliance, required-folder coverage,
  revision control, CDE-state spread, orphans) + AIA **phase-gap** checks (SD/DD/CD/CA/CLOSEOUT flag the
  documents a phase is missing, e.g. a CD set lacking structural drawings).
- **Web**: the 📁 Documents destination in the Construction and Design workspaces — clickable folder
  tree, upload (auto-named, supersede-aware), download, move, delete, and a health strip.

Reuses the discipline spine (NCS), the ISO 19650 CDE states, the naming validator, and the storage
backend already in place. Verified: new `test_docmanager` + full backend suite green, web typecheck +
vitest 49/49, ruff clean.

## v0.3.95 — Close the five deferred slices: Parquet + glTF export, CV bridge end-to-end, live 2D propagation, IFC5 data reads
The items previously scoped as "needs a dependency / external service / upstream support" are now shipped
as far as each honestly can be:

- **Parquet export** — added `pyarrow`; `GET /model/export.parquet` writes a Snappy-compressed columnar
  file (DuckDB / pandas / Polars), alongside the existing CSV + JSON-LD. Returns a clean 503 (never a
  500) if the optional dep is absent.
- **glTF geometry export** — `GET /model/export.gltf` triangulates the model with the same
  `ifcopenshell.geom` iterator the section/clash tools use and writes a **self-contained glTF 2.0**
  (binary buffer embedded as a data-URI), meshes merged per IFC class with per-class colours, Z-up→Y-up.
  The viewer still streams Fragments — this is the portable geometry-*out* path (Blender / Three.js /
  any DCC). Honest scope: triangulated meshes + flat colours, no PBR/textures.
- **CV site-progress bridge, end-to-end** — the feature-flagged bridge now resolves an activity by **id
  or name**, accepts a **batch** (`/cv-progress/ingest-batch` — the per-photo-sweep shape), and writes
  straight to `schedule_activity.percent`. A runnable **reference adapter** ([docs/cv-bridge.md](docs/cv-bridge.md))
  documents the HTTP contract so any vision service wires in. Still no bundled model — that stays external
  by design — but the entire integration surface is complete and tested.
- **Live 2D propagation** — a per-project **model version** bumps whenever a new model is published;
  `GET /drawings/sync-status` surfaces it and `GET /drawings/stream` (SSE) **pushes** the change, so open
  on-demand 2D views regenerate themselves. Single-worker uses an in-process registry; **multi-worker
  shares it via Redis** (atomic `HINCRBY`, keyed off `AEC_REDIS_URL`) so a publish on any worker reaches
  a stream on any other — fail-open to in-process if Redis blips, matching the rate-limiter/lockout.
- **IFC5 / IFCX / ifcJSON data reads** — a tolerant JSON reader parses these into the same element-index
  shape a STEP model produces, so analytics, LOD/naming/envelope audits and CSV/JSON-LD/Parquet export all
  work on an IFC5 file **now**. Capabilities report it as `ifc5: data` (geometry rendering still lands
  upstream when web-ifc / Fragments add it).

Web: the 🔬 Model Analysis panel gains an **Export** row (CSV / JSON-LD / Parquet / glTF) and reflects the
IFC5 data-read distinction. Verified: 6 new/extended backend suites green, web typecheck + vitest 49/49,
ruff clean.

## v0.3.94 — Model Analysis panel: the new model-reading tools, first-class in the UI
A consolidated **🔬 Model Analysis** destination in the Design workspace surfaces the model-reading
endpoints that previously had no bespoke UI (the register-backed features already had module CRUD +
Report Center reports): **IFC capabilities** (supported schemas + the loaded model's detected schema,
IFC5/IFCX reported), a **model query** (saved views — count by discipline / class / storey / type),
**LOD coverage**, **envelope code compliance**, **MEP counts off the model**, and **naming compliance**.
Each section loads independently and degrades gracefully when no model is published. New client methods
wrap the endpoints; the panel follows the extracted-panel (`PanelContext`) pattern. Verified: web
typecheck clean, vitest 49/49, build green, **and live** — booted the full dev stack (API on :8093 +
Vite), navigated to Design → Model Analysis; all six sections render with zero console errors, and IFC
capabilities correctly detected the loaded model as IFC4.

## v0.3.93 — Deferred-item slices: model-driven MEP, staleness, schema detect, CV write-path
The tractable slice of each remaining backlog item (the fuller versions need infrastructure noted below).
- **Model-driven MEP extraction (C1x)** — `mep.extract_from_model` reads MEP elements off the loaded
  model by IFC class (ducts / pipes / terminals / equipment / electrical), counted by class + discipline.
  `GET /mep/model-extract`, and the MEP Equipment Schedule report now shows model counts beside the register.
- **Model-staleness signature (B2x)** — `GET /drawings/sync-status` returns a cheap fingerprint of the
  loaded model (element count + GlobalId hash); the client compares it across renders to know when the
  on-demand 2D is stale. The tractable slice of live-2D propagation, without an event bus.
- **IFC schema detection + capabilities (D4x)** — `GET /model/capabilities` sniffs the source model's
  header, reports the detected schema (IFC2X3 / IFC4 / IFC4X3), and **detects IFC5/IFCX (JSON) and says
  plainly it's not yet parsed** rather than failing cryptically. The read path still lands upstream.
- **CV bridge write-path (E2x)** — with `AEC_CV_BRIDGE` on, `POST /cv-progress/ingest` now **writes the
  estimate to the named schedule activity's percent** (a bad id is handled, not a 500). A real CV service
  now has a working endpoint to drive progress; the vision model remains external.

Still genuinely deferred (need infra, not effort): **Parquet export** (needs the `pyarrow` dependency —
a decision, not built by default), **glTF geometry export** (needs the geometry pipeline), a **real CV
model** (external service), and **full auto-propagate-on-edit** (needs an event bus). Backend 129/129,
ruff clean.

## v0.3.92 — Field AI: labor productivity + CV progress bridge (Phase E)
The final phase of the upgrade initiative.
- **Field labor productivity (E1)** — a new `productivity_log` register (quantity installed · workers ·
  hours) + `productivity.py`: **units per man-hour** per entry, rolled up by trade, with an overall rate.
  `GET /productivity/summary` + a **Field Labor Productivity** report. The field-productivity signal
  Rhumbix-style tools surface, on the same project record.
- **Computer-vision site-progress bridge (E2)** — real CV % complete needs an external vision model, so
  this is a **feature-flagged bridge** (like the RVT and money-processor bridges): with `AEC_CV_BRIDGE`
  off (default) the endpoints report the bridge as unavailable and **fabricate nothing**; an operator
  enables the flag and connects a CV service that POSTs estimates to `/cv-progress/ingest` (clamped
  0–100). `GET /cv-progress/status` documents the contract.
Backend 128/128, ruff clean. **The A–E upgrade initiative (authoring depth · design engine · engineering
depth · interoperability/analytics · field AI) is complete** — 16 items across v0.3.87–v0.3.92.

## v0.3.91 — Interoperability & analytics: model query + data export + envelope compliance (Phase D)
The ifc-lite-inspired items, on our server-Fragments architecture.
- **Model analytics query (D1)** — `model_query.py` + `GET /model/query`: group elements by any
  attribute (ifc_class / discipline / storey / type / `Pset::Property`) and **count** them or **sum a
  quantity** from the IFC quantity sets, with filters and four saved views. The "ask the model a
  question" analytics without shipping the model to the browser.
- **Model data export (D2)** — `GET /model/export.csv` (columnar, one row per element) and
  `GET /model/export.jsonld` (a JSON-LD graph, bSDD-style vocab, GlobalId as `@id`). No external
  dependency. (Parquet + glTF geometry export remain future items.)
- **Envelope code-compliance (D3)** — new `envelope_assembly` register + `envelope.py`: opaque
  assemblies checked against IECC 2021 minimum R-values and fenestration against maximum U-factors by
  climate zone. `GET /envelope/{audit,check}` + an **Envelope Code Compliance** report. A first-pass
  screen, not a stamped energy model.
- **IFC5 / IFCX (D4)** — tracked as a watch-item; the read path lands when web-ifc / Fragments ship
  IFC5 support.
Backend 127/127, ruff clean. Phases A–D of the authoring/design/engineering/interop initiative complete.

## v0.3.90 — Engineering depth: MEP sizing/schedules + resource-loaded scheduling (Phase C)
- **MEP engineering (C1)** — a new `mep_equipment` register (equipment schedule) + `mep.py` with
  deterministic first-pass calculators: **duct sizing** (equal-velocity), **pipe sizing** (velocity
  method → nominal pipe size), **cooling load → tonnage** + a block-load rule-of-thumb, and
  **hanger/support spacing** (SMACNA for duct, MSS SP-58 for pipe). `GET /mep/schedule` rolls the
  equipment up per system; `GET /mep/size` is a stateless sizing calc. An **MEP Equipment Schedule**
  report with sizing reference tables. Extends the D5 parametric MEP (which lays the geometry) with the
  numbers behind it.
- **Resource-loaded scheduling (C2)** — schedule activities gain a **crew_size**; `resource_loading.py`
  buckets every week an activity spans and sums concurrent crew into a **resource histogram** (by trade
  + total), a cumulative **man-week S-curve**, **peak manpower**, and **over-allocation** flags against
  an optional `?cap=` availability. `GET /schedule/resource-loading` + a **Resource-Loaded Schedule**
  report (histogram + S-curve charts). Rides on the existing CPM schedule.
Backend 125/125, ruff clean.

## v0.3.89 — The design engine: options / variants + standards ruleset (Phase B)
Design-side depth so a project can carry, compare and standardize schemes.
- **Design options / variants (B1)** — a new `design_option` register (program + economics per scheme)
  and `GET /design/options/compare`: options compared apples-to-apples with **best-in-class per metric**
  (lowest cost/sf, lowest EUI, highest IRR, largest area, highest efficiency), deltas vs the **selected**
  option, and a state rollup (proposed → shortlisted → selected → rejected). A **Design Options
  Comparison** report (PDF + Excel).
- **Selected-option → drawing linkage (B2)** — each option references a `drawing_set`; the selected
  option's set is the project's current documentation. The 2D drawings (plan / section / elevation /
  sheet) already **generate on demand from the live model**, so they reflect the current state whenever
  requested. (Full auto-propagate-on-every-edit — Higharc-style instant regeneration — remains a future
  item; it needs event wiring on top of the parametric model.)
- **Design standards ruleset (B3)** — a new `design_standard` register (approved / preferred /
  prohibited assemblies, materials, products) with `GET /design/standards` + `GET /design/standards/check`:
  the loaded model is audited against the ruleset — elements are flagged when their type/material matches
  a **prohibited** standard, or (when an approved set is declared) match nothing approved. Keyword-based on
  the openBIM property data the model already carries. A **Design Standards Compliance** report.
Both registers get CRUD via the module engine; both reports surface under a new **Design** group. Backend
123/123, ruff clean.

## v0.3.88 — Authoring depth: LOD matrix + naming-convention validator (A2 + A3)
Completes the authoring-depth phase.
- **LOD matrix & coverage (A2)** — a new `lod_target` register (stage × discipline × element-category →
  LOD 100–500; RIBA/AIA stage defaults when empty) plus an **achieved-LOD assessment** of the loaded
  model. Achieved LOD is *inferred* from the same LOIN facet completeness the quality scorecard scores
  (geometry/type/classification/properties/quantities) and capped at LOD 400 — LOD 500 is a verified
  as-built assertion, not a model read. Endpoints `GET /lod/matrix` + `GET /lod/assessment`, and a
  **LOD Matrix & Coverage** report (target matrix + achieved distribution + per-discipline average).
- **Naming-convention validator (A3)** — validates document/container filenames against
  `Type_Discipline_Description_Revision_Date` (revision-controlled) and drawing sheet numbers against
  the **NCS Sheet ID** grammar (reusing the D3 parser). `GET /naming/{conventions,validate,audit}` and
  a **Naming Convention Compliance** report that audits the CDE containers + drawing register with
  compliance % and a violation list.
Both surface automatically in the Report Center (Quality group, PDF + Excel); the LOD targets get CRUD
via the module engine. Backend 122/122, ruff clean.

## v0.3.87 — BEP generator: the ISO 19650 BIM Execution Plan as a produced document (A1)
The first of an authoring-depth initiative (informed by an industry-practice scan). We already held the
information-requirements register (EIR/BEP/AIR), the CDE, the discipline vocabulary and the delivery
register — now they **assemble into a produced BIM Execution Plan**. A new Report Center entry (**Quality**
group, PDF + Excel) composes the ISO 19650 BEP: an information-requirements register, a **roles,
responsibilities & authorities** matrix (appointing party / lead appointed party / information manager +
an authoring lead per discipline), the **Level of Information Need** targets by delivery stage (LOD
200→500), the **information-delivery schedule** (from the drawing/delivery sets), **information standards
& naming** (NCS sheet IDs + `Type_Discipline_Description_Revision_Date` + MasterFormat/Uniformat
classification), the **CDE workflow** (WIP→Shared→Published→Archived with revision/approval coverage), and
the **model-coordination & QA** process — with core EIR/BEP/AIR coverage flagged. No new data entry: it
reads the registers you already keep. Next in the phase: a per-element **LOD matrix** (A2) and a
**naming-convention validator** (A3).

## v0.3.86 — Code standards S3: lint lock-in (consistency enforced in CI)
The final phase of the standards initiative — the PEP 8-aligned rules the S1 pass satisfied are now
**enforced in CI**, so they stay satisfied. Ruff's rule set expands from correctness-only
(`F`, `E9`, `B`) to add:
- **`I`** — import ordering (isort), with `aec_api`/`aec_data` pinned as first-party.
- **`UP`** — pyupgrade: modern syntax for the Python 3.10+ target.
- **`C4`** — flake8-comprehensions: no needless comprehensions or collection calls.

Nine residual violations (unnecessary comprehensions, `%`-format strings, a redundant `dict()` call)
were cleaned up by hand — all behaviour-preserving. Deliberately **not** enforced, with the rationale
recorded inline in `ruff.toml`: line-length (`E501`) and one-statement-per-line (`E702`), because the
codebase intentionally uses compact one-liners and dense table/PDF/SVG builders; and `RUF100`, because
it would strip the intentional `# noqa: BLE001` annotations that document the logged fail-open idiom.
**120/120 backend suites pass**; no runtime change.

## v0.3.85 — Code standards S1: safe PEP 8-aligned auto-fixes
A mechanical, behaviour-preserving compliance pass across the Python backend (`services/api` +
`services/data`) — the first of a phased standards initiative. Ruff's **safe** auto-fixes only:
- **Import ordering** (isort / PEP 8) — imports sorted into stdlib / third-party / first-party groups.
- **pyupgrade** — deprecated import paths, quoted annotations, and old-style `%` formatting modernized.
- **Comprehension simplifications** — unnecessary `dict()`/`list()` comprehensions and calls collapsed.
- **`contextlib.suppress`** in place of `try/except/pass`.
~200 fixes across 52 files. No behaviour change (**120/120 backend suites pass**, imports clean). The
codebase's deliberate compact idiom (compact one-liners, unused FastAPI-DI args, typographic unicode) is
intentionally preserved. Line-length wrapping (S2) and CI lock-in (S3) follow.

## v0.3.84 — Discipline Spine D5b: parametric MEP generation (spine complete)
The generator now produces real **parametric MEP distribution**, so a generated building reads as a
layered structural / architectural / **MEP** model — completing the five-phase Discipline Spine.
- Beyond the two core risers, each floor gets a **supply-air duct main** and a **domestic-water main**
  at ceiling height plus **ceiling diffusers on a ~bay grid** (`IfcFlowTerminal`, air-terminal). Fully
  parametric — the mains span the plate and the diffuser count scales with the floor size and bay.
- The new elements classify to the right disciplines automatically (D2): ducts + diffusers →
  **Mechanical**, pipes → **Plumbing** — so colour-by-discipline and the `?discipline=` filter show the
  MEP layer, and the takeoff/spine pick it up. Verified: a 7-floor model generates 14 duct segments,
  14 pipe segments and 112 diffusers, correctly disciplined.

**Discipline Spine complete (D1→D5):** shared NCS/MasterFormat vocabularies → discipline-tagged elements
→ discipline sheets + sets → connected spec/bid/cost-code traceability → discipline-aware generation
with parametric MEP. The model, the documents and the money are one traceable thread. (A true multi-file
federation split of the generated model — separate STR/ARCH/MEP IFCs sharing one grid — and a first-class
`IfcGrid` remain as optional model-realism follow-ups; the layered reading already works via the
discipline tagging.)

## v0.3.83 — Discipline Spine D5a: generation seeds a connected spine
Generating a project now produces a **fully-connected discipline spine** out of the box, not just a
model + budget. The GC-portal seeder that already creates cost codes now also seeds a **bid package per
discipline** (Structural / Architectural / Mechanical / Electrical), each linked to its cost code, and a
**spec section per division** linked to that package — so a freshly generated project is **100%
traceable model → specs → bid packages → cost codes → budget** the moment it exists.
- Discipline budgets are computed from the same hard-cost division fractions (Structural, Architectural,
  Mechanical, Electrical), so the seeded packages reconcile with the GMP.
- `test_disciplines` extended: a generated project shows 100% specs-packaged / packages-costed /
  spec-to-budget and every spec fully linked. Reuses the D1 classification vocabulary + the D4 links.
- First half of D5 (discipline-aware generation); D5b adds a real `IfcGrid` + parametric MEP depth.

## v0.3.82 — Discipline Spine D4: connect the procurement chain (traceability)
The payoff phase — the model, the documents and the money are now one connected thread, with the broken
links surfaced so scope can't fall between them.
- **Links wired**: `spec_section` gains **`bid_package`** (which package procures this spec) + a
  discipline field; `bid_package` gains a **`cost_code`** reference + discipline. Spec→bid is N:1, the
  correct direction — a package's specs are all the specs pointing to it.
- **`spine.py` traceability engine** + `GET /projects/{id}/spine/traceability` — traces
  **discipline → sheets → specs → bid packages → cost codes → budget**, with per-discipline rollups
  (sheets/specs/packages/cost-codes/budget) and **coverage bars** for each join (sheets→spec,
  specs→package, packages→cost-code, spec→budget). Discipline is resolved consistently — from the field,
  else derived from the MasterFormat division or the NCS sheet number.
- **Coverage gaps** list the broken links: unpackaged specs, unbudgeted packages, un-specced sheets.
- New **🔗 Discipline Spine** panel (Design workspace): coverage bars, budget-by-discipline chart,
  the gap lists, and the spec→package→cost-code trace. `test_disciplines` extended. Fourth of five phases.

## v0.3.81 — Discipline Spine D3: discipline-tagged drawing sheets + sets
Drawing sheets now read as a proper **discipline-ordered set**, and each sheet links to the specification
and drawing set it belongs to — the documentation layer of the spine.
- **NCS Sheet ID parsing** (`drawingset.parse_sheet_id`) — `A-101` → discipline **A** (Architectural),
  sheet type **1** (Plans), sequence **01**. The drawing-set register now carries the parsed sheet ID on
  every sheet, derives the discipline from the sheet number when the field is blank, and **orders the
  sheet index the way a set is bound** — by NCS discipline (General → Civil → Structural → Architectural
  → MEP), then sheet number.
- **`drawing_set` module** — named issued sets (Schematic Design / Permit / Bid / Issued for Construction
  / Record) with discipline, issue date and purpose.
- `drawing` gains **`drawing_set`** and **governing `spec_section`** references (the sheet→spec link that
  feeds D4) plus issued-date / revision-purpose fields.
- `test_disciplines` extended. Third of five phases (D1→D5).

## v0.3.80 — Discipline Spine D2: discipline-tagged model elements
Every model element now carries its **NCS discipline**, derived from its IFC class through the D1
MasterFormat map — so the model reads as layered structural / architectural / MEP even from a single
federated file, with no republish and no extra scan (pure function of the already-indexed IFC class).
- `GET /projects/{id}/elements?discipline=S` (accepts an NCS code **or** name) filters the property
  index; every element is returned with its derived `discipline`.
- `GET /projects/{id}/elements/by-discipline` — model composition: element count + IFC-class breakdown
  per discipline, in NCS sheet order (Structural → Architectural → MEP).
- **Discipline** is now a first-class **colour-by facet** — it appears automatically in the viewer's
  "Colour by…" picker and buckets the model by discipline in 3D (no client change needed).
- `test_disciplines` extended. Second of five phases (D1→D5) of the model→sheets→specs→bid→budget spine.

## v0.3.79 — Discipline Spine D1: shared classification vocabularies
The foundation for representing a project as layered **structural / MEP / architectural** models whose
sheets, specs, bid packages and budget all thread through two shared, validated vocabularies (rather
than free text). Based on the US National CAD Standard discipline designators + CSI MasterFormat.
- **Discipline vocabulary** (`classification.py`) — the NCS discipline designators (**A** architectural ·
  **S** structural · **M** mechanical · **E** electrical · **P** plumbing · **F** fire · **C** civil ·
  **T** telecom · **G/L/Q**), each with its default MasterFormat divisions + Uniformat groups.
  Derives an element's discipline from its IFC class (via the existing MasterFormat map), and normalizes
  legacy free-text values (e.g. "MEP" → M, "Geotechnical" → C).
- **MasterFormat division master** (25 divisions) + the **Uniformat II ↔ MasterFormat crosswalk** that
  migrates a concept-phase budget into the procurement budget.
- `GET /reference/disciplines` serves all three catalogs (drives the selects + the spine joins).
- Converted the free-text `discipline` (drawings) and CSI `division` (cost codes, spec sections) fields
  to validated **selects**. `test_disciplines`. Deterministic, no new deps. First of five phases
  (D1→D5) building the model→sheets→specs→bid→budget spine.

## v0.3.78 — Performance: trim the physical-climate-risk fan-out
Tightens the scans behind the physical-climate-risk rollup that feeds the ESG scorecard.
- The rollup previously ran the full weather engine — including a scan of `schedule_activity` (one of
  the larger tables) — even though it only needs the site-weather register and the logged delay days.
  Split out a `_weather_exposure` helper so `climate_risk` (and therefore every **ESG summary** load)
  no longer scans `schedule_activity` at all.
- Made `climate_risk` composable: the resilience **report** now passes in the flood / stormwater /
  exposure it already computed instead of recomputing those scans a second time.
- No behaviour change (rollup output is byte-identical); verified. Backs the config-module engine that
  already ships every tool's CRUD, CSV export, kanban board and workflow-flowchart for free.

## v0.3.77 — Real-time collaborative pull board (M3)
The Last Planner pull board becomes a live, multi-trade workspace — every stakeholder edits the same
board and sees each other's changes as they happen, without a page refresh.
- **Live board** — a lightweight Server-Sent-Events stream (`GET /projects/{id}/pull-plan/stream`)
  polls a cheap board change-signature (row count + latest `modified_at`) server-side and pushes it
  when it moves, so the board auto-refreshes the moment any trade adds or moves a sticky note. A
  **🟢 live** indicator sits in the board header.
- **Presence** — reuses the existing presence infra: a heartbeat marks who else is on the board and
  renders **👤 peer chips** in the header (self-cleans when you leave the view).
- **Edit locks / no silent overwrite** — records now expose `modified_at`, and the record editor sends
  it back as an optimistic lock: if someone changed the record while you had it open, the save returns
  **409** (rather than clobbering their edit) and the editor reloads the latest with a *"re-apply your
  edit"* nudge. Opt-in and backward-compatible — an un-locked write still succeeds.
- Reuses the SSE + presence primitives already in the codebase — **no new dependencies**, no CRDT.
  `test_pull_realtime`; the lock is generic (available to every module, not just the pull board).

## v0.3.76 — Climate resilience: weather-sequenced construction + physical-risk rollup (W3–W4)
Extends the **🌊 Climate Resilience** panel from the design phase into construction and up into ESG.
- **Weather-sequenced construction (W3)** — a `weather_sensitivity` flag on schedule activities (rain /
  wind / freeze / heat) so exposed work can be sequenced out of the wet/freeze season, plus a new
  `climate_site_risk` register (hazard type, exposure season, severity, controls) for standing
  site-weather hazards. **Weather-delay days** roll up automatically from the daily reports'
  weather-impact field. Reachable in the construction **Build** stage as well as design/developer.
- **Physical climate-risk rollup (W4)** — a scored **Low / Moderate / High / Severe** rating that
  folds flood-plain exposure, assets below the Design Flood Elevation, open site-weather hazards and
  logged weather delays into one number with its driving factors — and feeds the **ESG scorecard**
  (`physical_risk`).
- Endpoints `GET /projects/{id}/resilience/weather` + `/resilience/climate-risk`; the Resilience
  report gains the rating, the site-weather register and the risk factors; `test_resilience` extended;
  demo seeded. Deterministic — no new deps, no external calls.

## v0.3.75 — Climate & water resilience: flood + stormwater (W1–W2)
Treat rainfall and flooding as **quantifiable design parameters** — a new **🌊 Climate Resilience**
panel in the Design (and Developer) workspace.
- **Flood risk (ASCE 24 / FEMA)** — a `flood_risk` assessment (FEMA zone, Base Flood Elevation, Flood
  Design Class, freeboard) computes the **Design Flood Elevation** (DFE = BFE + freeboard, ASCE 24
  minimum by class) and runs the **flood-proof-MEP check**: any Asset Register item whose new
  *Installed Elevation* is below the DFE is flagged to be elevated or flood-proofed. Flags whether the
  site is in a Special Flood Hazard Area.
- **Stormwater (Rational Method)** — a `drainage_area` (catchment) module → peak runoff **Q = C·i·A**
  (runoff coefficient × rainfall intensity × area), composite C, and a first-order detention volume,
  so drainage is sized against a real design storm rather than guessed.
- Endpoints `GET /projects/{id}/resilience/flood` + `/resilience/stormwater`; a Report Center entry
  (flood + stormwater, PDF/Excel); `test_resilience`; demo seeded. Deterministic — no new deps, no
  external calls.

## v0.3.74 — Docs + hardening pass (M1/M2 consolidation)
- **Docs**: README (operations + schedule) and the in-app guide now cover the Facility Condition
  Index and the pull-planning reliability analytics.
- **Security**: reviewed the new operations/schedule endpoints — authorization matches the existing
  patterns (`current_user` for the cross-project roll-ups, `require_role("viewer")` for project-scoped
  reads); no money movement (facility-condition is cost *estimation* only); no new dependencies or
  outbound calls. Bandit + ruff clean (tightened the portfolio roll-up's defensive catch to log
  rather than swallow). Full backend suite (117) + web typecheck green; live console clean across the
  new panels.

## v0.3.73 — Pull-planning reliability analytics (M2)
Deeper Last Planner metrics on the pull-plan board — the learning-loop signals a team improves week
over week, beyond a single PPC number.
- **`pull_plan.metrics()`** — **Tasks-Made-Ready %** (are constraints cleared ahead of the work?),
  **make-ready runway** (weeks of ready work staged), **perfect-handoff %** (predecessor done and
  successor ready ÷ hand-offs), **PPC trend by week**, and the **variance-reason Pareto** (why
  commitments miss). Endpoint `GET /projects/{id}/pull-plan/metrics`.
- **Cross-project benchmark** — `benchmarking.pull_planning()` + `GET /benchmarks/pull-planning`:
  the PPC and TMR distribution across every project vs the ≥80% target, so a plan is judged against
  the team's own portfolio.
- **Board Analytics view** — a 📊 Analytics toggle on the Pull Planning card renders the reliability
  chips (PPC / TMR / perfect hand-offs / runway), the PPC-trend and variance-Pareto charts, and the
  portfolio benchmark. Test coverage extended; demo seeded.

## v0.3.72 — Facility Condition Assessment + FCI (operations phase, M1)
A facility-condition capability for the operate phase: assess building elements, price their
deficiencies, and score the asset's condition — the metric owners and facility managers use to
prioritize capital.
- **`fca_element` module** (Operations; construction + developer) — one record per building element:
  UNIFORMAT II group, linked building system, condition rating (1 Excellent…5 Critical), install /
  expected-life / replacement cost, deficiency + repair cost, recommended year, photo. Workflow
  identified → planned → funded → resolved (resolved leaves the backlog).
- **`fca.py` engine** — **Facility Condition Index** = (deferred maintenance + capital renewal) ÷
  current replacement value, with the band (Good <5% · Fair 5–10% · Poor 10–30% · Critical >30%), the
  deferred/renewal split, and breakdowns by UNIFORMAT group, condition, worst elements, and
  recommended-year forecast. A **portfolio** roll-up ranks buildings worst-first for capital
  prioritization. FCA deficiency costs now also feed the **reserve study** (condition-based, not just
  age-based).
- Endpoints `GET /projects/{id}/fca/index` + `/fca/portfolio`; a **Report Center** entry (FCA / FCI,
  PDF + Excel); a **🏥 Facility Condition** panel in the Operations stage (FCI + band, deferred vs
  CRV, by-UNIFORMAT table, recommended-spend chart, worst-elements, portfolio card). `test_fca`;
  demo seeded.

## v0.3.71 — Nav polish: fix garbled icons + a naming collision surfaced by the Design workspace
Cleanup found while reviewing the new Design nav.
- **Fixed 5 corrupted module icons** — `daily_report`, `incident`, `inspection`, `ncr`, and `permit`
  carried double-encoded (mojibake) icon glyphs from a past edit; they rendered as garbage (e.g.
  "â–£ Permitting"). Restored to their intended symbols (☼ ⚑ ✓ ⚠ ▣).
- **Renamed the drawing register "Drawings & Specs" → "Drawings"** — its fields are all
  sheet-index data (number, revision, discipline, sheet number); the "& Specs" was a misnomer that
  collided with the real **Specifications** register (`spec_section`, the CSI spec book that drives
  the submittal log). The two are now clearly distinct in the nav.
- **`engines: node >=20`** added to the web package so `npm` warns when an older Node is on PATH (the
  production build's post-step needs the global `crypto`, stable since Node 19).

## v0.3.70 — A Design workspace for the architect & engineer, and role-based tool placement
The platform now has a home for the **design phase**. A new **Design** workspace sits between
Drawings and Construction — the architect/engineer's seat (AIA SD/DD/CD · RIBA stages 2–4) — and the
design tools that were scattered across the GC and developer portals now live there. This is a
methodical placement pass so every tool shows in the view(s) whose role owns it; see
[docs/roles-views.md](docs/roles-views.md) for the full role→view map.
- **Design workspace** — nav grouped by design stage: **Brief & program** (Space Program · Project
  Lifecycle) and **Model & standards** (IDS Requirements · CDE / Standards · BIM KPIs · **Model
  Health**). The Model-Health launcher deep-links to the model-QA checks in the Model **Tools** rail
  (Data QA, code-readiness, clash, IDS validate — they run on the loaded geometry). A design
  command-center dashboard (phase, standards, and register tiles) is the landing page.
- **Registers move to their owner** — Space Program, Project Lifecycle, design reviews, selections,
  information requirements/containers, coordination issues, and the design document register are now
  Design-workspace registers.
- **Shared tools show in both workspaces** — a register can now belong to more than one workspace, so
  the A/E↔GC workflows (RFIs, submittals, drawings, transmittals, meetings, permits, specs) appear by
  default in **both** Design and Construction without duplicating records. The GC's Construction view
  is unchanged; the architect/engineer get a focused Design view.
- **Role routing** — the architect and engineer personas now home into Design; every role can still
  reach every register via **Show all modules** or **⌘K**.

## v0.3.69 — Pull planning: the Last Planner phase board
Collaborative pull planning next to the schedule views — the Last Planner System level that sits
between the master schedule and the weekly work plan. The team pulls a phase backward from a
milestone; every trade posts its own tasks and the hand-offs between them; the lookahead makes work
ready by removing constraints; commitments are scored by PPC.
- **`pull_plan_task` module** (Schedule, construction workspace) — a sticky note per task: milestone,
  trade, responsible party, duration, planned week, **predecessor** (the hand-off), and the
  **constraints** that keep it from being ready (design/RFI, submittals, materials, labour,
  equipment, prerequisite work, permits/inspections, space/access, information). Workflow:
  pulled → made ready → committed → done, with a **missed** state gated on a variance reason, and
  paths to reconstrain or recommit.
- **Phase board** — a trade-swimlane × week matrix built over those records, with the hand-off
  sequence, a make-ready log of open constraints, and readiness / commitment / **PPC** (Percent Plan
  Complete = completed ÷ committed). Rendered at the top of the **📅 Schedule** panel with a
  milestone filter, an inline editor (every trade edits its own notes), and a printable **PDF** of
  the board — the hand-out a pull-planning session runs from. Feeds the existing weekly-plan PPC
  analytics rather than replacing them.

## v0.3.68 — Concept space programming: the adjacency graph (standards C8 of 8)
The front of the lifecycle — programming a building before it's massed — closing the eight-release
standards + AI track. The platform now spans land acquisition → programming → design (ISO 19650) →
construction → turnover → operations.
- **`space_program` module** (Programming, developer workspace) — program spaces as nodes: name,
  use type, target area, quantity, level preference, and **“should be adjacent to”** (the edges).
- **`adjacency.py`** (`GET /projects/{pid}/program/summary`) — the program as a graph: total/net/
  gross area, use mix, the node/edge adjacency graph with **unmet preferences** flagged, an
  efficiency %, and the **massing hints** (gross area + use mix) that feed the zoning→massing
  generator and the proforma.
- **“🧩 Space Program” panel** (Design & build) — area KPI cards, the use-mix table, adjacency chips
  (unmet flagged), and the massing hand-off line.
- **Docs** — README + roadmap now describe the full span (acquisition → programming → ISO-19650
  design → construction → turnover → twin/ESG operations) and the C1–C8 track.
- Verified live (4 nodes, 38,700 sf gross / 35,500 net, 91.7% efficiency, Lobby→Retail unmet) +
  `test_program`. Typecheck + 49 vitest + Pages build green.

## v0.3.67 — Drawing-sheet extraction (standards C7 of 8)
Reading a drawing set into structured data — offline-first and honest, never inventing a sheet.
- **`sheet_extract.py`** (`POST /projects/{pid}/extract/sheets`) — parses an uploaded PDF's text
  layer (pypdf) or a pasted sheet index into `{number, title, discipline}`, inferring the discipline
  from the sheet prefix (A→Architectural, S→Structural, M/E/P→MEP, C→Civil…). Deterministic; an
  image-only scan with no text layer returns nothing and says so (set an Anthropic key to read page
  images). With `create=true` the extracted sheets become **Drawing records** in one step.
- **“🗂 Sheet index” tab** in AI Assist — upload a PDF or paste a list, preview the extracted table,
  optionally create the drawing records.
- Verified live (paste → 3 sheets extracted with disciplines) + `test_sheet_extract` (9-sheet index
  parsed, noise ignored, 9 drawing records created). Typecheck + 49 vitest + Pages build green.

## v0.3.66 — Procurement compliance gate (standards C6 of 8)
Turns the platform's existing COI / prequal / subcontract / lien-waiver records into an enforceable
compliance posture — the “can this sub bid or bill yet?” gate, plus the outbound nudge list.
- **`procurement_gate.py`** — per-vendor readiness from the compliance records:
  - `GET /projects/{pid}/procurement/gate?vendor=` → **can bid** (approved prequalification + active
    insurance) and **can bill** (executed subcontract + active insurance) with the specific blockers;
    reports the COI status/expiry, prequal status, subcontract execution, and whether a waiver is on file.
  - `GET /projects/{pid}/procurement/compliance-feed` → the outbound nudge list: every vendor with an
    expiring / expired / missing COI or an unapproved prequal, so the GC chases the paperwork before it
    blocks a bid invitation or a pay application.
- **Procurement-compliance-gate card** in the ⚖️ Risk & Cost panel (flagged vendors, issues, bid/bill
  status). Money movement stays behind the flagged licensed-rail bridge — this gates on paperwork only.
- Verified live (Bedrock flagged: expired COI + unapproved prequal → can't bid/bill; Acme clears) +
  `test_procurement_gate`. Typecheck + 49 vitest + Pages build green.

## v0.3.65 — Digital-twin readiness + Digital Product Passport (standards C5 of 8)
Deepens the two KPI categories that were placeholders — the data a building needs to run as a digital
twin, and the emerging EU product-passport requirement.
- **`building_system` module** — the HVAC / electrical / plumbing / fire / vertical-transport / BMS
  systems an asset belongs to, with the BMS integration protocol (BACnet, Modbus, KNX, MQTT…).
- **Asset register gains a “Digital Twin” fieldset** (link to a building system + sensor/telemetry
  point ID + sensor type) and a **“Product Passport” fieldset** (GS1 Digital Link ID, EPD/
  environmental reference, manufacturer-data URL).
- **`twin.py`** (`GET /projects/{pid}/twin/readiness`) — asset↔system linkage %, sensor-mapping %,
  a combined twin-readiness score (ISO 23247), the building-system graph with BMS-integration count,
  and **DPP completeness** (honest about the passport being an emerging 2028-30 EU requirement).
- The BIM KPI scorecard’s **Digital Twin Readiness** and **Construction Data Readiness** categories
  now read these richer signals (system-linked + sensor-mapped; product data + DPP).
- **Digital-twin readiness card** in the 🔧 Operations panel.
- Verified live (25% twin-ready on the seeded assets, DPP note) + `test_twin` (66.7% linked / 33.3%
  sensored → 50% twin-ready; DPP 33.3%; KPI reflects both). Typecheck + 49 vitest + Pages build green.

## v0.3.64 — AI over the model: MCP server + standards experts (standards C4 of 8)
Two ways an AI works *with* a project — both offline-first and grounded in real data, never a model
guessing from memory.
- **Standards-compliance experts** (`standards_expert.py`, `GET /projects/{pid}/standards/check?
  standard=iso19650|cobie|ids|uniclass`) — run the named standard against the project's own CDE,
  requirements register, asset data and model-quality index; return findings each with the **clause
  it references** and a recommendation, plus a 0–100 readiness score. Fully deterministic, no key.
  Surfaced as a **Compliance check** card (four standard buttons) in the CDE / Standards panel.
- **MCP server** (`mcp_server.py` + `mcp_tools.py`, `GET /mcp/tools`) — exposes the project to
  external AI agents (Claude Desktop, Cursor) as callable tools: project snapshot, list records, CDE
  status, BIM KPI scorecard, openBIM quality, standards check, and **create RFI** (a write tool).
  Tool logic reuses the same engines the HTTP API does, so an agent's reads/writes pass the exact
  same validation and workflow gates as the UI. The MCP SDK is an **optional** dependency (offline-
  first); the stdio server prints install guidance if it's absent. [docs/mcp.md](docs/mcp.md).
- Verified + `test_mcp_standards` (catalog exposes 8 tools; dispatch runs snapshot/records/CDE and
  creates a real RFI; unknown tool raises; experts return clause-referenced findings). Live:
  compliance card renders ISO 19650 findings with clauses. Typecheck + 49 vitest + Pages build green.

## v0.3.63 — BIM KPI scorecard + handover acceptance (standards C3 of 8)
The information-management scorecard the industry runs on — ten categories, graded from data the
platform already holds, with a formal owner's-acceptance gate at handover.
- **`bim_kpi.py`** (`GET /projects/{pid}/bim-kpi/scorecard`) — the ten categories graded
  good/warn/poor/**n-a**: Information Requirements, Model Authoring Quality, openBIM Exchange,
  Coordination Control, Issue Resolution, CDE Discipline, Asset Data Readiness, Construction Data
  Readiness, Handover Assurance, Digital Twin Readiness. Each rolls up existing data — the CDE
  (C1), model quality (C2, when a model is loaded), and the RFI / coordination / asset / closeout
  records — and shows **n/a rather than a guess** when its inputs are absent. Overall health %.
- **Handover data-drop acceptance gate** (`GET …/handover/acceptance`) — the owner's checklist
  against the AIR: requirements issued, assets tagged for CMMS (≥90%), as-builts, O&M, accepted
  completion certificate → one accept/not-ready verdict.
- **“📊 BIM KPIs” panel** (Plan & derisk) — health + grade-count cards, the acceptance banner, and
  the traffic-light category table. **Report Center: “BIM KPI Scorecard (ISO 19650)”** (PDF/Excel).
- Verified live (health %, 🟢🟡🔴⚪ grades, handover checklist) + `test_bim_kpi` (empty → 10 n/a;
  populated → info-reqs/CDE/asset/handover good; report PDF). Typecheck + 49 vitest + Pages build green.

## v0.3.62 — openBIM model-quality scoring (standards C2 of 8)
Turns the loaded IFC model into measurable buildingSMART quality signals — the layer that makes IDS
authoring (already shipped) actionable, and feeds the coming BIM KPI scorecard.
- **`openbim_quality.py`** (`GET /projects/{pid}/openbim/quality`) — pure scoring over the model's
  property index:
  - **LOIN per element** (Level of Information Need, the ISO 19650 successor to "LOD") — each element
    scored across geometry / type / classification / properties / quantities; reports average score,
    the “coordinated” share (≥4 of 5 facets), and per-facet coverage.
  - **IDS rule-compliance %** — pass `?use_case=` (fire & life safety, handover COBie, energy,
    quantities) and every applicable element is scored against its IDS spec (must carry every
    required property) → per-spec and overall compliance %.
  - **IFC export health** — proxy/untyped share, type coverage, property coverage graded pass/warn/
    fail (the authoring-export defects that quietly break QTO, carbon and IDS).
  - **bSDD / classification alignment %.**
- Surfaced as an **openBIM model-quality card** in the CDE / Standards panel (degrades to a
  “load a model” hint when none is open).
- Verified + `test_openbim_quality` (LOIN distribution, IDS walls 2/3 → 66.7%, export-health proxy
  flag, bSDD %) over a synthetic index — no live model needed. Typecheck + 49 vitest + Pages build green.

## v0.3.61 — ISO 19650 information management: CDE + requirements register (standards C1 of 8)
Opens a standards-alignment track (grounded in ISO 19650, buildingSMART, and the industry BIM-KPI
frameworks). First: formal information management, replacing scattered document status with a proper
Common Data Environment.
- **`information_container` module** — deliverables (models, drawings, docs) move through the ISO
  19650 CDE states **Work-in-progress → Shared → Published → Archived**, carrying a
  **suitability/status code** (S0–S4 shared, A published-for-construction, CR/AB record) and a
  **revision**. Sharing requires a suitability code; publishing requires a revision (the review gates).
- **`info_requirement` module** — the requirements register: OIR/AIR/PIR/**EIR**/**BEP**/MIDP/TIDP
  with appointing / lead-appointed / appointed parties, `draft → issued → superseded`.
- **`GET /projects/{pid}/cde/status`** (`cde.py`) — container state distribution, suitability
  spread, and the three **CDE-discipline** metrics (revision control %, approval-status coverage,
  metadata completeness) that feed the forthcoming BIM KPI scorecard.
- **`GET /projects/{pid}/info-requirements/register`** — requirements by type + **core-document
  coverage** (flags a missing EIR/BEP/AIR).
- **“🗂 CDE / Standards” panel** (Plan & derisk) — container-state cards, CDE-discipline table,
  requirements register with the core-coverage banner.
- Verified live (panel shows 2 WIP / 1 Published, discipline metrics, missing-AIR flag) +
  `test_cde` (WIP→Shared→Published gated on suitability then revision; core-coverage). Typecheck green.

## v0.3.60 — Navigation at scale + a current demo
The panel list had outgrown a flat sidebar. Research pass over the published evidence on
information architecture for feature-dense products (navigation-depth studies, journey-based
step navigation, design-system shell-capacity guidance, and how large platforms restructured
around starred/recent + curated workspaces) — recorded in [docs/ux-ia.md](docs/ux-ia.md) with
the rules for future features (no new top-level items; two disclosure tiers max).
- **Lifecycle-stage navigation** — the portal's first-class destinations are grouped under stage
  headers instead of one flat list. Construction: *Plan & derisk → Build → Turn over & operate*;
  Developer: *Acquire → Design & build → Operate*; both end with *Across projects* (Portfolio,
  Benchmarks). Journey-based IA, matching how AEC teams already think in phases.
- **🕘 Recent** — the last five opened registers surface automatically at the top of the module
  list (below the opt-in ★ Favorites) — zero-setup wayfinding for ~100 registers.
- **⌘K taught in context** — a persistent "Jump anywhere: Ctrl/⌘+K" hint anchors the nav; the
  command palette is the long-tail navigator.
- **Pages demo brought current** — the captured massing.build/app snapshot pre-dated v0.3.49;
  every newer panel (Lifecycle, Turnover, Diligence, Operations, Energy, Asset Mgmt, ESG & POE,
  Risk & Cost, Benchmarks) rendered empty. The demo project now runs the full lifecycle (DD +
  entitlements, design gates, PM-generated work orders, 6 months of meter readings, reserve/CIP,
  leases + CAM, POE) and captures all engine endpoints — 608 fixtures, verified with a full
  two-persona walkthrough and a clean console.
- **Guide updated** — new "Tutorial 7 · Operate it" (diligence go/no-go, PM work orders, EUI,
  reserve study, CAM statements, ESG/POE) + ten plain-English glossary entries (EUI, CAM
  gross-up, Scope 1/2, POE, …).

## v0.3.59 — ESG rollup + post-occupancy evaluation (lifecycle R7 of 7)
The final lifecycle release: the asset's sustainability scorecard and the feedback loop from measured
performance back to design — all computed locally from the platform's own data.
- **ESG rollup** (`esg.py`, `GET /projects/{pid}/esg`) — metered energy (EUI via energy.py),
  **operational GHG Scope 1/2** from a transparent local factor table (on-site fuel vs purchased
  energy; set `AEC_GRID_KGCO2E_PER_KWH` to the local grid subregion factor), GHG intensity, water +
  intensity, and certification tracking (LEED credits targeted vs achieved). Nothing fetched,
  nothing fabricated.
- **`poe` module** — post-occupancy evaluations at levels 1 (indicative) / 2 (investigative) /
  3 (diagnostic) with occupant-satisfaction score, design EUI, findings and feed-forward lessons;
  workflow `planned → fieldwork → reported` (report requires findings). The rollup compares
  **design EUI vs metered actual** and reports the gap.
- **“🌱 ESG & POE” developer panel** — EUI/GHG/water/cert KPI cards, scope split with the factor
  note, latest-POE card with the vs-design gap, one-click PDF.
- **Report Center: “ESG / Sustainability Summary”** — PDF/Excel with GHG table, POE comparison,
  and data-coverage caveats.
- **Docs** — README + roadmap now describe the full span: land acquisition → due diligence &
  entitlements → design → construction → turnover → operations (CMMS, energy, reserves/CIP, CAM,
  ESG/POE). Lifecycle releases R1–R7 complete.
- Verified live (panel + PDF; grid-factor override changes Scope 2) + `test_esg`; typecheck +
  49 vitest + Pages build green.

## v0.3.58 — Capital planning + CAM reconciliation (lifecycle R6 of 7)
Hold-phase capital stewardship: will the reserves cover the roof in 2031, and did tenants pay their
fair share of operating expenses this year?
- **Reserve study** (`reserve.py`) — the asset register grows Reserve Study fields (expected life,
  replacement cost); `GET /projects/{pid}/reserves/study` projects recurring component replacements
  plus open capital-plan items over a 20–40 yr horizon (inflation-escalated), runs the year-by-year
  reserve balance, flags the **first underfunded year**, and solves the **suggested level annual
  contribution** that keeps the fund solvent.
- **`capital_plan` module (CIP)** — capital items with planned year, cost, priority
  (critical/recommended/discretionary), funding source and ROI note; workflow
  `proposed → approved → funded → complete`. Open items ride the reserve projection.
- **`cam_expense` module + CAM true-up** (`cam.py`) — operating-expense lines by standard category
  (janitorial, R&M, utilities, security, admin, management, insurance, taxes) with budget/actual and
  variable/recoverable flags. `GET …/cam/reconciliation`: recoverable pool with **variable-only
  gross-up** to a stated occupancy (fixed expenses pass at actual), each tenant's pro-rata share vs
  estimated payments (lease `recovery_psf` × sf), balance due or credit.
- **Per-tenant statement PDF** — `GET …/cam/statement/{lease}.pdf`: expense pool by category, the
  tenant's share, estimated payments, true-up balance.
- **Finance ▸ “Asset Mgmt” tab** — reserve-study runner (balance / contribution / horizon /
  inflation inputs, funding banner, replacement schedule), CIP table, CAM reconciliation with
  per-tenant statement downloads.
- Verified live (underfunded banner + suggested $/yr, escalated recurring events, CAM table w/ PDF
  served) + `test_reserves_cam`; typecheck green.

## v0.3.57 — Operations: CMMS + metered energy (lifecycle R5 of 7)
The biggest post-turnover gap: ~80% of a building's lifetime cost is operations. Adds the CMMS loop
(preventive maintenance before failures) and utility metering (EUI benchmarking) — fully offline.
- **`work_order` / `pm_schedule` modules** (Operations section) — corrective/preventive/emergency
  work orders with asset refs, priority, labor hours and cost; workflow
  `open → assigned → in_progress → completed → verified` (completion requires a completed date).
  PM schedules carry a task list, frequency and next-due date.
- **PM generation + KPIs** (`cmms.py`) — `POST /projects/{pid}/cmms/generate-pm` turns every due,
  active PM schedule into a preventive work order (idempotent per cycle; advances next-due).
  `GET …/cmms/kpis`: open by priority/type, overdue backlog, **PM compliance %**, **MTTR** (days).
- **`meter` / `meter_reading` modules** — electric/gas/water/steam/chilled-water meters with dated
  consumption + cost readings, entered manually or CSV-imported via the generic module import.
- **Metered energy rollup** (`energy.py`) — `GET …/energy/actual`: site kBtu by utility (standard
  conversion factors), monthly trend, water (tracked in gallons, not energy), utility cost, and
  **EUI (kBtu/sf/yr)** annualized over covered months using the model's GFA (or `?gfa_sf=`).
  Distinct from the design-model simulation at `GET …/energy`.
- **Benchmarking bridge** (`energy_star_bridge.py`, feature-flagged) — reports honestly that no
  provider is configured until a deployment sets `ENERGY_STAR_*` credentials; never fabricates a
  score. Local EUI/trends need no account.
- **“🔧 Operations” + “⚡ Energy” construction panels** — maintenance KPI cards, one-click PM
  generation, open-WO table; EUI/energy/cost/water cards, monthly trend chart, by-utility table.
- Verified live (both panels with seeded meters/readings/schedules; PM generation created WOs and
  was idempotent on re-run) + `test_operations`; typecheck + 49 vitest green.

## v0.3.56 — Pre-acquisition: due diligence + entitlements (lifecycle R4 of 7)
Fills the pre-construction gap the lifecycle research surfaced — the 6–36 months of study and
approvals between site control and capital commitment (grounded in institutional due-diligence
practice: ALTA/ASTM E1527 categories and the standard entitlement pipeline).
- **`due_diligence` module** (Acquisition, developer workspace) — study items by category
  (Title/ALTA survey, Phase I ESA (ASTM E1527), Phase II, Geotechnical, Utility capacity, Traffic,
  Wetlands/species, Zoning verification, Tax/legal) with consultant, findings, risk level, study cost
  and ordered/due/received dates. Workflow `open → in_review → cleared | flagged` — a report can't be
  submitted without findings, and flagging requires a risk level.
- **`entitlement` module** — applications (Rezoning, Site plan, CUP, Variance, Plat, Comp-plan
  amendment, Environmental review, Annexation) with agency, submitted/hearing/decision dates, a
  public-meeting/opposition log, conditions imposed, and **approval expiration**. Workflow
  `draft → submitted → hearing → approved | denied → appealed → hearing`; revisable for resubmittals.
- **Go/no-go rollup** — `GET /projects/{pid}/diligence/readiness`: DD by category
  (cleared/flagged/open), high-risk findings, the entitlement pipeline by state, and approvals
  expiring within 180 days → one `go` flag. New **“📜 Diligence & Entitlements”** developer panel
  (readiness banner, high-risk card, category table).
- Verified live (panel renders the NOT-READY banner, high-risk card, category rollup) +
  `test_diligence` (workflow gates + rollup), typecheck + 49 vitest green.

## v0.3.55 — UX, accessibility & front-end performance (readiness R3 of 7)
- **`prompt()` fully retired from the portal** — a new accessible `promptModal` (on the shared
  modalShell: role=dialog, focus trap, Esc/backdrop close, Enter submits, required-field validation)
  replaces all ten remaining `window.prompt()` calls: lifecycle **gate sign-off**, turnover
  **G704 certify** (both fields in one dialog), save view, templates (apply/save), add enum option,
  quick-create reference records, send-for-signature, and reassign.
- **Accessibility** — all **53** portal table headers now carry `scope="col"`; verified the viewer
  toolbar's icon buttons already ship `aria-label`s.
- **Performance measured** — the portal ships in the main `index` chunk at **92 KB Brotli** (shell
  budget 156/220 KB) — under the lazy-split threshold, so no code-motion was needed; recorded so
  future growth has a baseline.
- Verified **live**: certify flow end-to-end through the new dialog (open → validate → certify →
  “Architect certified” + G704 download), 375 px mobile viewport with no horizontal scroll, zero
  console errors; 49 vitest + typecheck + Pages build + budget green.

## v0.3.54 — Production hardening: ops & supply chain (readiness R2 of 7)
The deployment/ops half of the production-readiness plan — making "did we configure it right?"
a runnable gate and the supply chain deterministic:
- **Runnable go-live gate** — new [docs/PRODUCTION_CHECKLIST.md](docs/PRODUCTION_CHECKLIST.md) +
  `scripts/validate_prod_config.py` preflight (asserts RBAC, real secrets, secure cookies, CSP/HSTS,
  Redis-when-multi-worker, non-default DB/MinIO credentials; exit 0 = go). Referenced from deploy.md.
- **Supply chain** — Dependabot across pip/npm/cargo/actions (the viewer's pinned three/@thatopen pair
  moves as a group); CI now **builds the api+web images, scans them with Trivy (CRITICAL+fix = fail),
  and publishes to ghcr** with immutable `:sha` tags; a one-shot workflow generates + commits
  **Cargo.lock** so desktop builds stop floating transitive Rust deps.
- **Desktop trust** — the PyInstaller backend **sidecar is now Authenticode-signed** alongside the
  Tauri shell when a certificate is configured (SmartScreen inspects it separately).
- **Guardrails** — `seed_demo.py` refuses to run against an instance that already has projects
  (`--force` for labs); Host-header pinning via `AEC_ALLOWED_HOSTS` (TrustedHostMiddleware, opt-in);
  `/metrics` gains `http_responses_by_class_total` (2xx/4xx/5xx) for one-label alerting.
- Verified: preflight self-test (bad env → exit 1 with 4 failures; good env → exit 0), metrics smoke,
  all workflow/compose YAML parse, ruff clean.

## v0.3.53 — Production hardening: backend blockers (readiness R1 of 7)
From a full production-readiness audit (code + docs + deployment). Fixes the findings that make the
difference between "works in dev" and "safe under load, multi-worker, and misconfiguration":
- **Fail-fast production guard** — booting on **Postgres** without `AEC_RBAC=1` or with the default
  auth secret now **refuses to start** (explicit `AEC_ALLOW_OPEN=1` escape hatch). A forgotten env var
  is a loud crash at boot, not an open platform discovered later. CRITICAL log when the rate limit is
  on with multiple workers but no shared Redis counter.
- **Project list scales + doesn't leak** — `GET /projects` filters membership in SQL (join) instead of
  loading every project then running one role query each (N+1), and is paginated.
- **Bounded loads everywhere** — kanban `board()` returns capped per-state cards plus TRUE counts from
  a GROUP BY (was: materialize up to 100k records per request); CSV export **streams** page-by-page;
  the list `?limit=` param is clamped; Procore sync reads only the `procore_id` column via SQL json
  extraction (was: `limit=1_000_000` full-record load).
- **Observability** — fragment-conversion and publish failures now `logging.exception` (they were
  visible only in a status JSON nobody polls); auto-sync schedule failures log at WARNING.
- **Multi-worker autosync** — a Postgres advisory lock elects one runner per tick, so N workers no
  longer each pull the same external records.
- **Uploads & traversal** — the properties-index upload is size-gated (413 over `AEC_PROPS_MAX_MB`,
  default 100); attachment filenames explicitly collapse `..` sequences (belt on top of the existing
  storage containment guard).
- **Complete project deletion** — deleting a project now removes the **whole `{pid}/` storage prefix**
  (source-IFC copies, props index, publish status — not just the model tile) via a new
  `storage.delete_prefix` on both local and S3 backends.
- **Rate limiter** — evicts oldest buckets under IP churn instead of clearing all state at once.
- Verified: new `test_prod_hardening` + adjacent regressions (modules/rbac/security/connections/api/
  bcf) green, ruff + bandit clean.

## v0.3.52 — Architect sign-off + G704 substantial completion + record turnover (lifecycle track 4 of 4)
The final track closes the loop to turnover: the **Architect certifies substantial completion**, signs
off the punch list, and the as-built **record model** is stamped for handover.
- **`turnover.py` + `/turnover/*` endpoints** — `readiness` (punch rollup + latest model version; a
  G704 certifies *with* an open punch list, so the gate is that a punch list is prepared), `certify`
  (Architect certifies on a `completion_certificate` record: records the **Architect (certifying) +
  Owner + Contractor** signatures, stamps the current model version as the record model, issues the
  certificate), and `status` (signed cert + record-model summary).
- **G704 Certificate of Substantial Completion** generator in `contracts.py` — attaches the punch-list
  summary, the record-model version, and the occupancy date; reachable via
  `…/contracts/completion_certificate/{rid}/document.pdf?doc=g704`. The **Architect** is now a signatory
  on the G701 change order too.
- **Turnover package** — `closeout/package.zip` gains `turnover/status.json` (readiness + signed
  substantial-completion cert + record model version) alongside the as-built model, COBie and closeout
  manifest. `completion_certificate` gains occupancy-date / record-model-version / punch-% fields.
- **UI** — a **"🏁 Turnover"** construction-workspace panel: punch readiness, architect certification
  (with signatories), and one-click **G704** download.
- Verified: ruff + bandit clean, backend gate (new `test_turnover` — gate refuses with no punch list;
  architect certifies + Owner/Contractor sign; G704 renders; status reflects the signed cert) +
  `test_contracts`/`test_closeout` regressions, web typecheck + 49 vitest + Pages build + budget green.

**This completes the architect/engineer design-to-turnover lifecycle upgrade (4 tracks, v0.3.49–52).**

## v0.3.51 — Design-change instruments: ASI / Bulletin / Sketch (lifecycle track 3 of 4)
The standard AIA construction-phase change instruments, wired into the existing change chain.
- **New modules `asi`, `bulletin`, `sketch`** (Change Management section, config-driven CRUD + workflow):
  - **ASI** (AIA G710) — the Architect issues a supplemental instruction; **no cost/time**; the
    Contractor acknowledges (`issued → acknowledged → closed`).
  - **Bulletin** — a formal design revision; when it carries cost/time it links to a `change_event`
    (→ `pco_request → cor`) for pricing (`draft → issued → priced → closed`).
  - **Sketch (SK)** — a clarification sketch that attaches to an ASI / Bulletin / RFI / drawing.
- **Document generation** — G710 ASI + Bulletin cover-sheet + **G714 Construction Change Directive**
  (rendered from a `directive` record) added to `contracts.py`; all reachable through the existing
  `GET /projects/{pid}/contracts/{key}/{rid}/document.pdf?doc=asi|bulletin|ccd`. `directive` is the
  platform's CCD (G714) instrument.
- Verified: ruff + bandit clean, `test_change_instruments` (ASI issue→ack no cost; Bulletin cost impact
  links a change_event; SK attaches; ASI/Bulletin/CCD render as PDFs) + `test_contracts` regression,
  web typecheck green.

## v0.3.50 — IFC family library (lifecycle track 2 of 4)
The "families" folder now ships real `.ifc` content and a browsable library, fully offline.
- **Generated parametric core library** — `build_family_library.py` writes the whole catalog to a
  shippable **`services/data/families/library.ifc`** (46 families, each a GUID-stable `IfcTypeProduct`
  with mapped geometry, IFC4). The catalog gained **openings** (single/double door, fixed/sliding
  window), **enclosure** (interior partition, exterior wall, curtain-wall panel), and **concrete
  columns/beams** on top of the existing furniture / sanitary / appliance / lighting / MEP /
  structural / transport / plant families.
- **Family-library server** — `GET /families/library` (generated catalog grouped by category +
  the generated library + any curated external files) and `POST /projects/{pid}/families/place`
  (place a library family, GUID-stable, via the `add_family` recipe). The viewer's **Furnish & equip**
  picker now reflects the full library and its family count.
- **Curated external** — `services/data/families/external/` with a `SOURCES.md` of vetted free openBIM
  sources (buildingSMART samples, opensourceBIM/IFC-files, NBS National BIM Library, bSDD); drop an
  `.ifc` there or use `POST /families/import` to bring in manufacturer content. No third-party binaries
  are bundled without explicit review.
- Verified: ruff + bandit clean, backend gate (new `test_family_library` — library builds + reopens +
  place-from-library), web typecheck + 49 vitest + Pages build + budget green.

## v0.3.49 — Design-phase spine + itemized soft costs (lifecycle track 1 of 4)
Makes the architect/engineer design lifecycle explicit. Grounded in the RIBA Plan of Work 2020 (stages
0–7) mapped to the AIA design phases (Schematic Design → Design Development → Construction Documents →
Construction Administration), ISO 19650 information stages, and standard development soft-cost / design-
fee breakdowns.
- **`design_phase.py` + `project_phase` module** — the eight RIBA/AIA phases as **formal gates**. Each
  phase carries its deliverables, A/E design-fee %, and ISO-19650 status (S0→AM); the gate advances only
  when the **Architect + Owner** sign it off (`approve_gate` transition, requires a signer). Generating a
  project now seeds the eight phases automatically.
- **`soft_costs.py` — itemized, phase-aware soft costs** — the flat "soft = 25% of hard" is replaced by
  a transparent taxonomy (architecture & engineering fee, permits/entitlements, legal, financing &
  interest, insurance & bonds, developer fee, FF&E, marketing/lease-up, soft contingency). Totals are
  unchanged by default, but the **A/E design fee is drawn down across SD/DD/CD/Bid/CA** per standard
  splits. The generate seed (`_seed_dev_budget`, `_proforma_seed`) now emits itemized soft-cost lines.
- **Endpoints** `GET /projects/{pid}/lifecycle` (phases + gate state + soft-cost allocation + current
  stage), `POST …/lifecycle/seed`, `GET /lifecycle/reference`. New **"🧭 Project Lifecycle"** developer-
  workspace panel: the phase rail with deliverables, fee %, ISO status, gate sign-off, and the itemized
  soft-cost table.
- Verified: ruff + bandit clean, backend gate (new `test_design_phase`), web typecheck + 49 vitest +
  Pages build + budget green.

## v0.3.48 — Hardening, accessibility & documentation pass
A quality pass over the recently-shipped features: debug + full test sweep, a security-hardening
review, accessibility on the new UI, and a documentation refresh.
- **Security — outbound-URL guard.** New `net.py` `validate_outbound_url()` gates the bridges that
  fetch an **operator-configured** URL — **webhooks**, the real-estate syndication bridge, and the
  e-sign bridge — rejecting non-http(s) schemes (blocks `file://` / `gopher://` local-file-read + SSRF
  vectors) with an opt-in private-host check. The fixed-provider fetches (Autodesk, Google/Microsoft
  OAuth, Procore) and the already-guarded Speckle bridge were reviewed and left as-is.
- **Accessibility.** The new **Land Screening**, **IDS Requirements** and **conceptual-estimate**
  forms had placeholder-only inputs; every field now carries an `aria-label` so screen readers
  announce it. All new destinations confirmed reachable from the workspace nav (native `<button>`s,
  keyboard-operable).
- **Tests.** New `test_net`; backend gate now **97/97** suites. Web typecheck + 49 vitest + Pages
  build + bundle budget (156 KB shell < 220 KB) all green. `ruff` + `bandit` clean.
- **Docs.** Competitive/vendor comparison removed from the documentation set (README, the public
  landing page, the lifecycle graphic, roadmap/audit notes) in favor of neutral capability language;
  integration/connector references (Procore SSO + sync, ACC, QuickBooks/Sage) are retained as the
  factual product features they describe. README "Recent work", CHANGELOG and the GitHub About refreshed
  to current state; stale internal links removed.

## v0.3.47 — Land parcel screening + data connector
Land acquisition screening. The nationwide parcel dataset is a licensing play, so it's a
feature-flagged connector; the pure-software win — which plays to our GIS + feasibility + proforma
engines — is **screening**.
- **`parcels.py`** — screen a parcel set (imported GeoJSON / entered) by **size, zoning, flood zone,
  sewer/water, price**, and **rank by max-buildable opportunity**: each parcel gets a max envelope
  (area × FAR) and a **conceptual cost** (via `conceptual_estimate`), plus **land cost per buildable SF**
  — a screen → envelope → proforma chain that runs before acquisition, not just after.
- **`parcels_bridge.py`** — nationwide parcel/ownership/comps data is an optional paid connector
  (`PARCEL_PROVIDER`, Regrid/ATTOM/CoreLogic pattern) that raises rather than shipping fake data; the
  screening engine works on parcels you supply without it.
- Endpoints: `POST /parcels/screen`, `GET /parcels/data-status`. A **🗺️ Land Screening** developer-
  workspace panel (paste parcels → set criteria → ranked buildable-opportunity table).
- Verified: ruff clean, 96/96 backend suites (new `test_parcels`), web typecheck + 49 vitest + Pages
  build + budget green.

**This completes the second capability round (4 tracks, v0.3.44–47) on top of the code-quality gate
(v0.3.43).**

## v0.3.46 — Conceptual estimating + AI IFC classification
Two model-native intelligence features that leverage our IFC/massing strengths.
- **`conceptual_estimate.py`** — a parametric **$/SF** cost from building type + GFA + units at the
  massing stage (on-brand for a product called Massing): a low/base/high range **escalated for region
  and year**, with derived $/SF, $/unit and $/key for the proforma before there's a detailed takeoff.
  Built-in cost-per-SF table (16 building types) + regional index + ~4.5%/yr escalation, all overridable.
- **`ifc_classify.py`** — a transparent rules classifier that suggests the right **IfcClass** for
  `IfcBuildingElementProxy`/generic or mis-named elements (a proxy gets no quantity or carbon factor, so
  this directly improves **QTO + embodied carbon** accuracy). Every suggestion carries its reason;
  human-approved — reads the loaded property index or a posted element list.
- Endpoints: `GET /estimate/conceptual/catalog`, `POST …/estimate/conceptual`, `POST …/ifc/classify`.
  Surfaced in the **🛡 Risk & Cost** panel (a $/SF estimate mini-form + a model-classification summary).
- Verified: ruff clean, 95/95 backend suites (new `test_conceptual`), web typecheck + 49 vitest +
  Pages build + budget green.

## v0.3.45 — Materials procure-to-pay: quote leveling + 3-way match
The materials buying loop — distinct from sub-bid leveling. Deterministic/offline on top of the
modules we already have (`commitment` = PO, `delivery`, `sub_invoice`).
- **`procurement.py` — quote leveling** — normalize competing supplier quotes into an apples-to-apples
  grid with the low price per line item, the best-value supplier, per-supplier totals, and line-by-line
  savings (handles split awards where the cheapest supplier differs per item).
- **3-way match** — reconcile each PO against its deliveries and invoices, flagging **over-billing**
  (invoiced > PO), **pay-before-receipt** (invoiced with nothing received), and **un-invoiced
  deliveries**. Surfaced in the **🛡 Risk & Cost** panel.
- **`procurement_bridge.py`** — RFQ dispatch to suppliers is a feature-flagged stub (`RFQ_PROVIDER`)
  that raises rather than pretending to send; the *quote leveling* and *3-way match* work without it.
- Endpoints: `POST /projects/{pid}/procurement/level-quotes`, `GET …/three-way-match`, `/procurement/rfq-status`.
- Verified: ruff clean, 94/94 backend suites (new `test_procurement`), web typecheck + 49 vitest +
  Pages build + budget green.

## v0.3.44 — IDS authoring + EIR
Closing the BIM-standards loop upstream. We already *validate* models against an IDS; the demand is
upstream of that — **authoring** the requirements in the first place.
- **`ids_authoring.py`** — a starter requirements template library (what data each element type should
  carry: walls → FireRating/LoadBearing/…, doors, windows, slabs, spaces, columns, beams — from the
  standard `Pset_*Common` sets), bundled into **use cases** (handover/COBie, fire & life safety, energy,
  quantities). `build_ids()` emits a **standards-valid buildingSMART IDS 1.0** file via `ifctester` that
  **round-trips through our own validator**, and `eir_markdown()` generates an **EIR** (Exchange
  Information Requirements) document for the BIM contract.
- Endpoints: `GET /ids/templates`, `POST /ids/build` (→ downloadable `.ids`), `POST /ids/eir` (→ EIR.md).
  Model compliance-checking stays the existing `/validate` endpoint — closing the spec → implement →
  validate loop.
- **UI:** a **📋 IDS Requirements** portal panel — pick a use case, preview the required properties,
  download the IDS + EIR.
- Verified: ruff clean, 93/93 backend suites (new `test_ids_authoring` round-trips the IDS through
  ifctester), web typecheck + 49 vitest + Pages build + budget green.

## v0.3.43 — Code-quality gate (ruff + bandit in the loop) + BCF XXE fix
Applying the "enterprise-quality code with AI agents" discipline — verification *in the loop*, not after.
- **Static-analysis gate (ruff)** — a tuned config (`services/api/ruff.toml`) enforces the high-signal
  rules that catch real defects and dead code (pyflakes `F`, syntax `E9`, bugbear `B`) while respecting
  the codebase's deliberate idioms (compact `;` one-liners; the logged fail-open `except Exception`
  pattern is *not* linted). Wired into CI as a **blocking** step. Fixed everything it found: **14 unused
  imports + 2 unused variables** (dead code removed) and a **loop-variable closure bug** in the BCF
  camera parser.
- **Security scan (bandit)** — added to the report-only security workflow and run before shipping. It
  surfaced a real one: **`bcf_io.py` parsed untrusted uploaded BCF XML with the vulnerable stdlib
  parser (XXE / billion-laughs vector)** — now uses **`defusedxml`**, the same hardening already applied
  to CityGML import. Fixes an actual vulnerability on the BCF import path.
- `ruff` + `bandit` added to `requirements-dev.txt`; `CONTRIBUTING.md` documents the local gates.
- Verified: ruff clean, 92/92 backend suites, bandit XXE finding resolved.

## v0.3.42 — Tiers 2 & 3: fintech depth + differentiated (carbon, code, pricing)
The rest of the capability roadmap. Every engine is offline/deterministic (AI only where it helps),
source-linked, and never fabricates; money movement and live pricing are feature-flagged bridge stubs
that raise actionable errors rather than faking a result.
- **Subcontractor prequalification** — a transparent Q-score (safety/EMR, financial, experience, rating,
  currency = 100 pts, every point traceable) + a **COI-expiry** feed. A single sub default costs a GC
  1.5-3× the subcontract, so this is a core risk gate before award.
- **Pay-app ↔ lien-waiver reconciliation** — matches what was **paid** (`sub_invoice`) against **waivers**
  on file (`lien_waiver`, conditional vs unconditional) and surfaces per-vendor **lien exposure**. Massing
  never moves money: a `payments_bridge` stub disburses only through a licensed processor and refuses
  release while exposure remains.
- **Accounting export** — double-entry **GL CSV** + **QuickBooks IIF** bills from the cost records, so
  finance stops re-keying. (Live two-way sync remains the connection framework's job.)
- **Embodied carbon (A1-A3)** — computed from `production_quantity` × a built-in EPD factor table with
  unit conversion, rolled up by material + cost code. Zero of this existed before, and it plays to our
  IFC/quantity strength as embodied-carbon reporting goes mandatory on public work.
- **Code-compliance assistant** — describe a project → applicable **IBC/ADA/IECC** sections with citations
  (Claude when keyed; a deterministic IBC checklist triggered by occupancy/area/stories otherwise).
- **Takeoff pricing** — reconcile the takeoff to a built-in unit price book (+ a `pricing_bridge` stub for
  a live supplier/RSMeans feed) with **variance vs the estimate**.
- **UI:** a **🛡 Risk & Cost** portal panel (prequal scores, COI expiry, lien exposure, carbon, priced-
  takeoff variance, GL/IIF export) and a **Code check** tab in AI Assist.
- Verified: 92/92 backend suites, web typecheck + 49 vitest + Pages build + bundle budget all green.

## v0.3.41 — Tier 1: AI drafting, bid leveling, cross-project benchmarking
Market-driven upgrades. Each AI engine mirrors the existing
`review.py`: Claude when `ANTHROPIC_API_KEY` is set, a deterministic **offline fallback** otherwise,
every output **source-linked**, never fabricated; heavy calls run off the event loop and are throttled.
- **AI drafting** (`drafting.py`, **AI Assist** panel) — turn a note or a PDF into an editable
  first-draft **RFI**, **submittal summary**, or trade **scope of work** with page citations, so teams
  stop retyping from documents (the report's "18% of project time is spent searching for data").
  Human-in-the-loop: nothing is created until you click **Create**.
- **Bid leveling** (`bid_leveling.py`) — level a package's `bid_submission` records into an
  apples-to-apples grid: base-bid stats + >25% **outlier** flags, a **scope matrix** (who includes/
  excludes each item), **scope-gap** detection, and a **scope-adjusted low** recommendation (a low bid
  missing scope others carry is flagged). Optional AI canonicalizes free-text scope phrases.
  `GET /projects/{pid}/bids/leveling/{package_rid}`; shown as a grid in the AI Assist panel.
- **Cross-project benchmarking** (`benchmarking.py`, **Benchmarks** panel) — your own history across
  every project: actual **cost distribution** (low/p25/median/p75/high) per cost code, and RFI/submittal
  **turnaround + overdue %** (ball-in-court accountability). Answers the survey's "76% aren't realizing
  their data's potential." `GET /benchmarks/costs`, `/benchmarks/response-rates`.
- **Test-gate fix:** `run_tests.py` used a hardcoded list that silently skipped 12 on-disk suites
  (this session's throttle/route-order/module-schema/interop + pre-existing review/gbxml/analytics/
  discipline/module-config). All are now wired in — the gate runs **86 suites** (was counting 74).
- Verified: 86/86 backend suites, web typecheck + 49 vitest + Pages build + bundle budget all green.

## v0.3.40 — P2: Pydantic module-schema layer (single source of truth for module.json)
- **`module_schema.py`** — a Pydantic `ModuleSchema`/`FieldDef`/`Workflow`/`Transition` layer that
  formalizes what a valid `module.json` is. The config test and the runtime loader now validate against
  the *same* definition: `test_module_config` asserts every shipped module passes it (authoritative,
  fails the build); `load_registry` runs it at startup and logs a warning for a malformed module rather
  than crashing (advisory). New `test_module_schema` proves the layer catches each misconfig class
  (dup fields, unknown types, select-without-options, bad reference target, bad title_field /
  list_column / workflow state / transition / requires) and stays quiet on valid input.
- **Record value validation** (`validate_record`) at create/update: rejects a non-numeric value in a
  numeric field (`number`/`currency`/`percent`) with a 422 before it can land in the JSON `data` blob.
  Select `options` are treated as *suggestions*, not a closed enum (the system routinely stores
  free-form values a picklist didn't anticipate), so membership is deliberately not enforced.
- Fixed the `party` transition key to accept a bare string as well as a list (matches
  `rbac.party_allowed`), and corrected the module-authoring guide's workflow example (`action`, not
  `label`; `party`; convention-based due dates; derived terminal states).

## v0.3.39 — P1: don't block the event loop on heavy IFC/convert/AI work
- **Async offload of blocking work** (P1 from the review). Several `async` endpoints ran CPU/network-
  bound work directly on the event loop, stalling *every* other request on that worker for its whole
  duration. Each now runs in a threadpool (`run_in_threadpool`):
  - `POST …/validate` — `ifcopenshell.open` + IDS validation (seconds+).
  - `POST /convert` — the APS RVT→IFC `subprocess.run` (up to a 30-minute block!) and the E57
    point-cloud decode.
  - `POST /convert/citygml` — CityGML XML parse.
  - `POST …/review/{contract,scope,ask}` — server-side PDF text extraction and the LLM calls.
- **Model load progress** was already real (streamed % + MB with a graceful fallback when the server
  sends no `Content-Length`) — verified, no change needed.

## v0.3.38 — P0 hardening: SQL aggregates, SSRF guard, per-endpoint throttle, bounded property cache
Quick, safe, high-value fixes from the code/UX/perf/security review (Cesium globe deferred — the
recommendation is to adopt the OGC **3D Tiles** format into the existing three.js viewer if geospatial
demand arises, not build a bespoke globe).
- **Performance — SQL aggregates over full-table Python scans.** `due_feed` now filters unfinished,
  soon-due records in SQL (JSON due-date `< horizon` + state `not in` terminal) instead of loading
  every module row + JSON blob; `project_pins` prunes un-anchored rows in SQL; the construction
  **portfolio** dashboard loads only open/mitigating risks and counts open RFIs with a SQL `COUNT`
  rather than three `limit=1_000_000` full scans per project. (`my_work` was already SQL-filtered.)
- **Security — SSRF guard on the admin-settable Speckle URL.** The Speckle server URL comes from the
  Settings UI (untrusted), so `speckle_bridge` now requires `https://` and refuses hosts that resolve
  to private / loopback / link-local / cloud-metadata addresses before any request — closing an
  internal-network / metadata-probe vector. A self-hosted LAN server can opt back in with
  `SPECKLE_ALLOW_PRIVATE=1`.
- **Security — per-endpoint rate limiting for expensive ops** (`throttle.py`). The AI **review**
  endpoints (LLM per call) and the **convert** endpoints (subprocess / paid APS cloud translation)
  now get an always-on per-caller cap independent of the opt-in global limiter; tune or disable per
  bucket via `AEC_THROTTLE_<BUCKET>_RPM`. The "Test connection" AI probe is bounded to a 10s timeout
  with no retries so it can't hang a worker.
- **Perf/memory — bounded property cache.** The in-process element index (`properties.py`) is now an
  LRU capped at ~16 projects/worker (`AEC_PROPS_CACHE_PROJECTS`); evicted projects reload transparently
  from storage — a busy worker no longer holds every project's full element list forever.
- **UX — discoverable command palette.** Added a visible **🔍 Search ⌘K** button in the header so the
  palette isn't hidden behind a keyboard shortcut. Backend suite + web typecheck green.

## v0.3.37 — Design tokens: theme-aware modal error text
- Modal/error message colors across the Account, Connections, and Settings dialogs now use the
  theme-aware **`--err`** token instead of a hardcoded red, so they read correctly in light mode too
  (completing the v0.3.23 status-token pass). The remaining literal colors are intentionally raw:
  canvas drawing colors (takeoff/markup — canvas can't read CSS variables) and already-tokenized
  `var(--status-*, #fallback)` uses. Web typecheck + production build clean.

## v0.3.36 — Module-config validator + forms/CRUD audit
- **Forms/CRUD audit** across all 85 modules — found + fixed a broken list view: `asset_register`
  listed a `warranty_expiry` column that didn't exist (the field is `warranty_expires`).
- **`test_module_config.py`** now validates every `modules/*/module.json` on each test run and fails the
  build on: duplicate field names, `reference` fields with a missing/non-existent target module,
  `select`/`multiselect` with no options, unknown field types, `title_field` or `list_columns` pointing
  at non-existent fields, and workflow `initial`/transition states or `requires` that reference
  unknown states/fields. Prevents the whole class of config-driven-CRUD misconfig going forward.

## v0.3.35 — Frontend load speed: code-split the secondary workspaces
- **~24% smaller initial shell** — the **Finance (proforma)** and **Drawings** panels are now
  code-split and load on first open instead of shipping in the startup bundle. Initial `index` chunk
  **646 kB → 535 kB (139 → 106 kB gzip)**; proforma (77 kB) + drawings (8.8 kB) are separate chunks.
  The default **Construction/Developer** portal stays eager; the 3D viewer engine (@thatopen, ~6 MB)
  and **Studio** were already lazy. Verified live: Finance + Drawings load on first switch with no
  errors; web typecheck + production build clean.

## v0.3.34 — Security hardening: gate the conversion + interop endpoints
- **Auth gap closed.** `POST /convert` (RVT/DWG/NWC bridge) and `POST /convert/citygml` were reachable
  anonymously — they now require an authenticated identity (`current_user`), and `/convert` + `/interop`
  were added to the RBAC middleware's protected-prefix list (defense-in-depth when `AEC_RBAC=1`).
  Combined with the earlier defusedxml + body-cap hardening, the CityGML endpoint is now auth-gated,
  XXE-safe, and size-bounded.
- Web dependency audit clean (`npm audit --omit=dev`: 0 vulnerabilities); Python dep scan runs in CI.

## v0.3.33 — Discipline quantities: rebar tonnage + MEP runs (C)
- **🔩 Discipline quantities** in the viewer's Exports — a quantity roll-up straight from the IFC:
  **reinforcement tonnage** (from `NetWeight`, or estimated from volume × steel density when bars
  aren't weighed), **MEP linear runs** (duct / pipe / cable metres + segment & fitting counts), and
  **structural element volume**. Backs the rebar-viz / MEP-takeoff use case (Koh · WithRebar).
- New `aec_data.qto.discipline_summary` (reuses the QTO quantity reader + geometry fallback) +
  endpoint `GET /projects/{pid}/quantities/disciplines`. `test_discipline.py` covers weights (modelled
  vs volume-estimated), MEP runs, and structural volume; verified live against a real IFC. Typecheck clean.

## v0.3.32 — gbXML energy-model export (B4)
- **↓ gbXML (energy model)** in the viewer's Exports — exports the model to **Green Building XML** for
  OpenStudio / EnergyPlus / IES / DesignBuilder. Spaces carry **area + volume + occupancy from the real
  IFC geometry**, plus building-level **exterior envelope** surfaces (wall + window opening / roof /
  ground slab) with areas from geometry. Valid gbXML 6.01.
  - Honest scope: a **simplified early-design (shoebox) model** — building-level envelope, not a full
    per-space surface-boundary thermal model (that needs IfcRelSpaceBoundary geometry). It seeds an
    energy tool with the spaces/areas/volumes rather than replacing detailed energy modelling.
  - New `aec_data/gbxml.py` (reuses the space schedule + envelope-area extractors) + endpoint
    `GET /projects/{pid}/exports/model.gbxml`. `test_gbxml.py` validates the structure; verified live
    against a real IFC (72 spaces). Web typecheck clean.

## v0.3.31 — Settings: "Test connection" per integration
- Every integration in **Settings ▸ Integrations & API keys** gets a **Test** button with instant
  ✓/✗ + message, so a non-technical admin knows a key actually works before relying on it:
  - **AI** — validates the Anthropic key with a 1-token call.
  - **Email** — connects + STARTTLS + login (no send).
  - **Speckle** — live GraphQL `serverInfo` connectivity check.
  - **Autodesk APS** — 2-legged OAuth (validates client id/secret).
  - **SSO** — confirms client id/secret are present (full sign-in still completes from the login page).
  - **Licence** — key-format check.
- New `conntest.py` dispatcher + `POST /settings/integrations/test` (admin-only). `test_interop.py`
  covers the dispatcher; suite + web typecheck green.

## v0.3.30 — Settings: add all API keys in the UI (no code/env editing)
- **Speckle** and **Autodesk APS** are now in the **Settings ▸ Integrations & API keys** panel, joining
  AI (Anthropic), Email (SMTP), SSO (Google / Microsoft / Procore), and licensing. A non-technical
  admin pastes keys and hits **Save** — no editing `.env` files or code. Secrets stay **write-only**
  (the catalog reports only whether a key is configured, never the value).
- The Speckle and APS bridges now read config via the settings store (DB-saved UI value wins, else the
  env var), so keys entered in the app take effect immediately — same pattern as the AI key.
- Clarified the admin hint: "add API keys here — no code or config files to edit."
- `test_interop.py` asserts the catalog exposes Speckle/APS with write-only secrets; suite + typecheck green.

## v0.3.29 — Federation alignment report + security hardening
- **Model alignment check** (Coordination) — a lightweight companion to federated clash: do a
  project's discipline models share the same **storey scheme** and **georeferenced origin**? Reads each
  model's storey elevations + IfcMapConversion and flags mismatched storey counts/elevations (different
  datums) and survey-origin offsets — the #1 coordination problem. New endpoint
  `/projects/{pid}/models/alignment` + a "📐 Alignment check" viewer action beside Federated clash.
- **Security hardening** of this session's new upload/parse surfaces:
  - CityGML parsing now uses **defusedxml** → XXE / billion-laughs / external-entity bombs are
    rejected (`EntitiesForbidden`) instead of expanding, so a tiny malicious file can't exhaust memory.
  - The contract/spec review engine caps analysed text (~800k chars) so a huge PDF can't drive the
    regex scan unbounded (the global 1 GB body cap still applies to the upload itself).
  - `pypdf` + `defusedxml` pinned in `requirements.txt`.
- `test_interop.py` extended (XXE bomb → 422, alignment → 409); backend suite + web typecheck green.

## v0.3.28 — Interoperability: Speckle bridge + CityGML site-context import
- **Speckle bridge** (Interoperability) — optional, open-source & self-hostable data exchange with the
  wider AEC ecosystem (Rhino/Grasshopper, Revit, Blender, web). Off unless `SPECKLE_SERVER` +
  `SPECKLE_TOKEN` are set; when on, `status()` verifies live connectivity (GraphQL `serverInfo`).
  IFC/Fragments stay the source of truth. Endpoints `/interop/speckle/status` + `…/send` (the chunked
  object upload runs in your credentialed deployment — it never fabricates a commit).
- **CityGML → GeoJSON site context** (GIS & Site) — import CityGML (the OGC standard behind the 3D City
  Database / Cesium city tiles) via **Open mesh / point cloud / GIS…**; the server extracts building
  footprints (with heights) → GeoJSON that renders in the existing GIS reference layer. Namespace-
  agnostic (CityGML 1.0–3.0), fully offline. Endpoint `/convert/citygml`; `.gml/.citygml` accepted.
- `test_interop.py` (Speckle gating + CityGML parse/422) green; web typecheck clean.

## v0.3.27 — Code-readiness check (Safety & Compliance)
- **🏛 Code-readiness check** in the viewer — does the model carry the *data* a plan review needs?
  A property-level rule engine (not a certified geometric code review) checks: egress door width
  recorded (≥ 0.813 m, IBC 1010.1.1), fire rating on walls (IBC Table 601/602), spaces carry floor
  area (IBC 1004.5) + occupancy classification (IBC 1004), egress stairs modelled (IBC 1011), and
  elements typed/classified. Returns a readiness %, a per-rule table with code references, and a
  one-click **3D highlight of the elements to review**. New endpoint `/elements/code-check`.
- Extends the v0.3.25 Data-QA into rule-based checks (Kestrel-style). Rules target IFC classes,
  try several attribute/pset keys, and check presence or a numeric minimum. `test_analytics.py`
  covers it; web typecheck clean.

## v0.3.26 — Preconstruction intelligence: contract risk review + scope-gap + doc Q&A
- **Risk Review** (new Construction-workspace destination — preconstruction intelligence, inspired by
  the AI pre-con review category). Upload a contract/spec PDF (or paste text) and:
  - **Contract risk review** — flags risky clauses by severity (high/med/low) with rationale + a
    suggested redline: pay-if-paid, no-damage-for-delay, broad indemnity, termination-for-convenience,
    sole discretion, lien waivers, LDs, backcharges, retainage, etc. One click adds a finding to the
    **Risk Register**.
  - **Scope-gap detection** — surfaces ambiguous/missing scope in specs & drawing notes ("by others",
    "N.I.C.", "TBD", "as required", "or equal", "match existing"…).
  - **Ask a document** — answers a question grounded in the uploaded doc with **page citations**.
  - New `review.py` engine + `/projects/{pid}/review/{contract,scope,ask}` endpoints. Uses Claude when
    an Anthropic key is set; otherwise a **deterministic clause/marker library** so it works fully
    offline and never fabricates (only flags language actually present).
- **Risk register depth** — the `risk` module gains **response strategy** (Avoid/Transfer/Mitigate/
  Accept), **trigger / warning signs**, and **contingency (Plan B)** to match risk-register best practice.
- Backend suite green (+ test_review, test_analytics); web typecheck clean.

## v0.3.25 — Thematic "Color by property" + BIM data-QA (built-world analytics)
- **Color by any property.** Generalized the 5D heatmaps into a thematic override: pick any IFC
  attribute (class, storey, type, name) or pset/qto property and the model recolours by value —
  numeric ranges get a blue→red ramp, categorical values distinct hues, with a live legend and an
  "N unset" count. New endpoints `GET /projects/{pid}/elements/facets-list` (the picker) and
  `…/color-by?prop=` (server-side bucketing over the property index — scales to large models).
- **BIM data-QA (completeness).** A validation pass over the property index: for each element,
  which required (Name / IFC class / Storey) and recommended (Type / property sets) attributes are
  present vs missing → a headline compliance %, a per-rule table, a one-click **3D highlight of the
  non-compliant elements**, and a CSV export. Endpoint `GET /projects/{pid}/elements/qa`.
- Inspired by computational-AEC data-viz/asset-data workflows; both reuse the existing viewer
  colorize/selection plumbing. Backend 75/75 + web typecheck green.

## v0.3.24 — Construction ↔ Developer split + role-geared dashboards
- **Workspace split.** The oversized single "Construction" portal is now two role-scoped workspaces
  driven by a new `workspace` tag on every `module.json`: **Construction** (the GC build lifecycle —
  Engineering, Preconstruction, Field, Cost, Change Management, Quality, Contracts, Safety, Closeout,
  BIM, Schedule, Resources, Sustainability) and **Developer** (real estate — **Feasibility** `zoning`,
  **Market & Sales** `comparable`/`listing`, **Capital** `investor`, **Operations** `lease`, plus the
  proforma via a one-click **Underwriting →**). A **Show all modules** toggle keeps every register one
  click away for every role — everyone still has access to all data.
- **Role-geared dashboards.** The Developer workspace opens on a real-estate command center (deal
  returns · listings · comps · capital · leases · feasibility) instead of the GC KPIs. The GC
  dashboard now orders its KPI cards by role: the **superintendent** leads with the field
  (punchlist/safety/quality), the **project manager** with controls (RFIs/COs/overdue). Same cards,
  role-appropriate emphasis.
- **Top header.** The role picker is now labeled **👤 Viewing as** and grouped by function
  (Real estate · Construction office · Construction field · Design), set off with a divider.
- **Deeper registers.** `comparable` rebuilt into a full appraisal-grade sales/rent comparison grid
  (comp type, $/unit, NOI, GBA, units, land area, year built, occupancy, condition, distance to
  subject, net adjustment, adjusted price, source + a recorded→verified→excluded workflow);
  `investor` gains ownership %, preferred return %, and commit date. Backend 74/74 + web typecheck green.

## v0.3.23 — Design tokens: theme-aware status colors
- Extracted the hardcoded traffic-light status colors (green/amber/red — 43 occurrences across the
  portal dashboard + proforma) into CSS variables (`--status-good/warn/crit`, `--err`) defined for
  both dark and light themes. Previously the dark-mode hexes bled into light mode; now status colors
  adapt to the theme and there's a single place to tune them. Web typecheck + 49 tests green.

## v0.3.22 — Speed: rollup fields filter in SQL (no more full-table scan per read)
- **Rollup fields** (e.g. a cost code's committed/budgeted/direct totals, a COR's PCO sum) previously
  loaded *every* source-module record for the project and matched the reference in Python on each
  `get_record` — O(N) per rollup, amplified by rollup-heavy dashboards. Now the reference match runs
  **in SQL** via portable JSON extraction (Postgres `->>` / SQLite `json_extract`), so only the
  matching rows are fetched. Same values, far less data scanned/shipped as record counts grow.
  Backend 74/74 (rollup-exercising tests unchanged).

## v0.3.21 — Forms/CRUD accuracy pass (field types, required flags, itemized costs)
- Audited all ~80 module forms against construction best practice and fixed the concrete, verified
  issues:
  - **Currency types**: material/equipment/labor unit rates and `budget.budget` / `budget.forecast`
    were plain numbers — now `currency` (proper `$` formatting, consistent with the rest of the budget).
  - **Required flags** where the field is genuinely mandatory: `submittal.type`,
    `inspection.inspection_type`, `ncr.disposition` — the form now blocks submit + the API validates.
  - **Itemized change-order cost breakdown**: `cor` gains Labor / Material / Equipment / Overhead &
    profit currency fields backing the total (standard COR format).
  - **Process fields**: `permit.applied_date` (processing time), `incident.reported_date` (OSHA
    reporting window), `daily_report.crew_by_trade` (manpower breakdown).
- Demo seed + test updated to supply the newly-required fields. Backend 74/74; web typecheck + 49
  tests green. (Riskier dedup/reference-type findings from the audit are deferred pending consumer
  analysis.)

## v0.3.20 — Command palette (⌘K / Ctrl-K)
- A global **command palette** (Cmd/Ctrl-K from anywhere) — the fast way to reach any workspace,
  module, action, or record without hunting through menus. Fuzzy-ranked, keyboard-first (↑/↓, Enter,
  Esc), with live **record search** (matches ref/title/data via the search endpoint) appended as you
  type. Commands cover the 5 workspaces, shell actions (new project, open IFC/mesh, Report Center,
  save, help), and every construction module (jump straight to its register). First of the Tier-1
  UX-2.0 upgrades from the audit; new `ui/palette.ts` + `PortalUI` open-by-key/record hooks.
- Verified live: opens on Ctrl-K, "fin"→Finance ranks first, Enter navigates; no console errors.
  Web typecheck + 49 tests green.

## v0.3.19 — Fix: attachment images / thumbnails not loading (route collision + COEP/CORP)
- **Portal record images now load.** Three compounding bugs, found by driving the app + reading
  network traces:
  1. **Route collision** — bim.py's `GET /attachments/{id}/download` (the `Attachment` table,
     registered first) shadowed the module-record handler (`RecordAttachment` table), so every
     module attachment 404'd. Moved module attachments to a distinct `/module-attachments/{id}/download`.
  2. **Bad auth gate** — that handler used `require_role("viewer")`, which reads the project id from
     the path; with no `pid` in the path FastAPI demanded it as a query param → 422. Now authenticated
     like bim's download: `current_user` + the attachment's own project (+ signed-URL support).
  3. **COEP blocked the `<img>`** — the SPA is cross-origin isolated (`require-corp`, for the viewer's
     SharedArrayBuffer WASM), which blocks cross-origin image subresources without a
     `Cross-Origin-Resource-Policy` header. Added `CORP: cross-origin` to the module-attachment
     download and to `range_response` (so BIM/topic attachments **and** `model.frag` embed cross-origin too).
- Verified live: an uploaded photo renders on the record (decodes, `naturalWidth>0`, no COEP block).
  Backend 74/74 (new `test_attachments`: distinct path 200 + bytes + `inline` + CORP; old path 404s);
  web typecheck + 49 tests green.

## v0.3.18 — Security: fix stored XSS in portal record rendering
- **Stored-XSS fix (high severity)**: record list cells, the record-detail title/fields, the
  cross-module search results, action-item / due / notification feeds, and the portfolio table all
  rendered user-entered values (titles, field data, project names) via `innerHTML` without escaping —
  a malicious record title like `<img src=x onerror=…>` executed for every user who viewed it. List
  cells now use `textContent`; every remaining `innerHTML` interpolation of record/user data is passed
  through `escapeHtml()`. Verified live: a hostile-title RFI renders as literal text on both the list
  and detail pages, injects no elements, and does not execute. (Found in a full-codebase UI/UX audit.)
- Web typecheck + 49 tests green.

## v0.3.17 — Saved-search alerts + Postgres full-text search
- **Saved-search alerts**: every saved view now tracks a `last_seen_at`, and the portal home shows a
  **🔔 Saved searches with new matches** band — each saved view with its **new-since-you-last-opened**
  count (a never-opened view counts all matches as new). Click a chip to open that filtered list; it
  clears the count. New `GET /projects/{pid}/views/alerts` + `POST …/views/{vid}/seen` + a
  `count_records` engine helper. Opening a view from the dropdown also marks it seen.
- **Postgres full-text search**: cross-module + in-module search is now **dialect-aware** — on Postgres
  it uses `to_tsvector` + a safe **prefix `to_tsquery`** (`conc beam` → `conc:* & beam:*`, so partial
  words and multi-term queries match) ranked by **`ts_rank`**; SQLite (dev) keeps the substring-LIKE
  fallback. No new service (per the earlier no-Elasticsearch decision) and no schema change — the FTS
  is a query-time expression. (For very large prod tables, a GIN index on the tsvector is the natural
  follow-up.)
- Additive migration adds `saved_views.last_seen_at` on startup (nullable ADD COLUMN). Backend 73/73
  (new `test_search_alerts`: alert lifecycle + prefix-tsquery builder + SQLite search); Postgres FTS
  SQL compile-verified (`to_tsvector @@ to_tsquery` + `ts_rank`); web typecheck + 49 tests green.

## v0.3.16 — Bulk-action pickers replace raw prompts (data-entry polish)
- The list bulk-action bar no longer uses `prompt()` for **Assign** / **Transition**: Transition is
  now a dropdown of the module's valid workflow actions + Apply, and Assign is an inline input + Apply
  (Delete stays behind a confirm). Faster, less error-prone bulk edits on a selection — the last
  rough edge from the CRUD/UX audit. Web typecheck + 49 tests green.

## v0.3.15 — Paginated module lists (large registers stay snappy)
- Module list views now **page** the records (100/page) with **‹ Prev / Next ›** controls and a
  position indicator, instead of fetching and rendering every record at once. A register with
  thousands of RFIs/issues/cost codes no longer stalls the browser on open; filter/search/state
  changes reset to the first page. Uses the list endpoint's existing `limit`/`offset` (fetches one
  extra row to detect "more"), so no API change — the pager only appears when the list spills past a
  page. Completes the data-entry UX upgrade set (import → validation → search → pagination).
- Backend 72/72 (limit/offset assertions added); web typecheck + 49 tests green.

## v0.3.14 — Data-entry UX upgrade Phases 2–4: form validation, searchable pickers, faster search
- **Form validation (buy-in + clean data)**: create/edit forms now enforce **required fields
  client-side** — offending inputs get outlined, the first is focused, and submit is blocked with a
  clear "Please fill required field(s): …" message instead of a silent server 422. If the server does
  reject (`missing required field(s): …`), the exact fields are parsed out and highlighted; the form
  keeps all entered values.
- **Searchable reference picker (ties everything together at scale)**: a reference field with more
  than 8 options gets a type-to-filter box, so picking e.g. a cost code stays fast when a project has
  hundreds — the "＋ Add new" inline-create still works.
- **Server-side search (easy to access, scalable — no Elasticsearch)**: the module list/search `q`
  filter now runs in **SQL** (`ref`/`title`/`data`-as-text `LIKE`, applied before `LIMIT`) instead of
  loading a page of rows and scanning JSON in Python — so a search returns the right matches across the
  whole module, not just those on the first page, and scales. Portable across SQLite (dev) and
  Postgres (prod); the JSONB/`tsvector` + GIN upgrade is a clean future step on the same query.
- Backend 72/72 (search assertions added to `test_imports`); web typecheck + 49 tests + Pages build green.

## v0.3.13 — Generic Excel / CSV import for any module (Phase 1 of the data-entry UX upgrade)
- **The #1 data-entry / adoption lever**: every module now has an **⤓ Import** button that bulk-loads
  records from an Excel (.xlsx) or CSV file. New `imports.py` + endpoints
  (`/modules/{key}/import/preview`, `/modules/{key}/import`, `/modules/{key}/import-template.csv`).
- **Two-step, mapping-driven UX**: pick a file → the server sniffs the header row and **auto-maps
  columns to fields** by name/label → a mapping screen lets you adjust each column (or skip), warns
  about unmapped required fields, and shows a sample → import. Type coercion (currency `$1,250` →
  1250.5, dates → ISO, multi-select split); rollup/computed fields excluded. A **blank template**
  download seeds the right headers.
- **Robust + safe**: required-field validation per row (a bad row is reported, never aborts the
  batch), 10k-row import cap, editor-gated + audit-logged. Answers "how do I create a new cost code" —
  the ＋ New form, the inline "＋ Add new" on a reference field, or now a spreadsheet import.
- Verified live: 3 cost codes imported from a CSV via the mapping UI, no console errors. Backend
  72/72 (new `test_imports`); web typecheck + 49 tests green.
- Decision (researched): **no Elasticsearch** — a self-hosted/offline app on Postgres should use
  built-in full-text search; a portable search upgrade lands in a follow-up phase.

## v0.3.12 — UI/UX + security pass over recently-added features
- Consolidated review of four features (site feasibility, feasibility scenario compare, clash-report
  import, BCF viewpoint fidelity).
- **Security**: hardened the clash-report XLSX import against oversized sheets — caps imported issues
  at 5,000 rows and scanned rows at 200,000 (surfacing a `truncated` flag), on top of the existing
  request body-size limit; `read_only` streaming keeps memory bounded. Audited RBAC on every new
  endpoint (feasibility / compare → viewer; clash import → editor + audit log) and confirmed the BCF
  XML parse path uses stdlib ElementTree (no external-entity expansion → not XXE-exploitable).
- **UI/UX**: verified all three new Report-Center tool launchers render and function live against a
  real backend (feasibility envelope, scenario ranking with deltas, clash-report file import), with
  graceful empty states and no console errors.

## v0.3.11 — BCF viewpoint fidelity: orthographic cameras + per-element coloring
- BCF viewpoints now round-trip the **full camera**, not just the view point: camera direction
  (derived from position→target when absent), up-vector, and field-of-view for perspective — plus
  **OrthogonalCamera** (view point + direction + up + view-to-world-scale) so section/elevation
  viewpoints from Solibri / ACC / BIMcollab survive the round-trip instead of collapsing to a bare
  point. Shared helpers (`_camera_xml`/`_parse_camera`) used across every export/import path.
- **Per-element coloring** in viewpoints (`<Coloring><Color><Component/>`) now exports and imports —
  the "the clashing beam is red" emphasis state carries through BCF. Imported viewpoints (incl.
  orthographic + coloured) are re-materialised as `Viewpoint` rows, not just the pin anchor.
- Viewer `captureViewpoint()` now records the projection (perspective/orthographic) + FOV, and
  `jumpToViewpoint()` restores the projection — shared/presence and saved views recreate the actual
  camera. Closes the fidelity gap flagged in the arsray146/ifc-bcf-viewer review.
- Backend 71/71 (BCF test extended with perspective + orthographic + coloring round-trips and an
  end-to-end orthographic-camera import); web typecheck + 49 tests green.

## v0.3.10 — Feasibility scenario comparison (test schemes side by side)
- **New `GET /projects/{pid}/feasibility/compare`** + `feasibility.compare()`: rank every zoning
  scheme (one `zoning` record = one scheme, e.g. "Scheme A · FAR 6" vs "Scheme B · FAR 8") by
  buildable yield — units then GFA — with the binding constraint and Δ-units / Δ-GFA vs. the top
  scheme. The Giraffe-style "test 20 scenarios in the time others analyze one," on the feasibility
  engine shipped in v0.3.8.
- `api.feasibilityCompare()` client + a "▟ Compare feasibility scenarios" tool launcher.
- Backend 71/71; web typecheck + 49 tests green.

## v0.3.9 — Import Solibri / Navisworks clash reports (XLSX → coordination issues)
- **New `clash_import.py` + `POST /projects/{pid}/coordination/import-xlsx`**: drop in a Solibri or
  Navisworks (or any tabular) clash/coordination report `.xlsx` and each row becomes a tracked
  **coordination issue** — which already round-trips to BCF and drops a model pin. GCs receive these
  reports constantly from the BIM coordinator; this turns the spreadsheet into model-anchored issues
  with no re-keying.
- Tolerant parser: sniffs the header row (skips title/preamble rows), maps a wide set of column
  aliases (Solibri Name/Description/Severity/Ruleset/Component-GUID/Location; Navisworks
  Clash-Name/Status/Grid-Location/Item 1/Item 2) by best whole-word match, maps severity → priority
  (Critical/High/Medium/Low), and extracts IFC GlobalIds from one or more component columns into
  `element_guids` so issues anchor on the model.
- `api.importClashXlsx()` client + an "⤓ Import clash report" tool launcher. Inspired by the
  arsray146/ifc-bcf-viewer + addd.io reviews (Solibri/QA-report ingest).
- Backend 71/71; web typecheck + 49 tests green.

## v0.3.8 — Site feasibility / zoning envelope (Giraffe-style) + live-demo fix
- **Fixed the broken live demo**: `massing.build/app/` was 404'ing — GitHub Pages had been switched to
  the legacy branch source (`/docs`), which serves the landing page but not the viewer and conflicts
  with the `pages.yml` Actions deploy. Restored Pages to the "GitHub Actions" source so `/app/`
  deploys again; regenerated the demo snapshot.
- **New `zoning` module + `feasibility.py` engine + `GET /projects/{pid}/feasibility`**: a site
  feasibility / zoning-envelope study (the "Massing" feasibility tool, inspired by Giraffe). From site
  area + zoning controls (FAR, height, floor-to-floor, lot coverage, setbacks, open space, parking,
  unit size) it computes the **maximum buildable GFA as the binding minimum of the FAR cap vs. the
  physical envelope** (footprint × floors), then net buildable area, **unit yield**, parking demand and
  required open space — and **reconciles allowed GFA against the model's actual GFA** (FAR used,
  % of allowed, headroom, over/under) when a source IFC is present.
- New **Site Feasibility / Zoning Envelope** report (Report Center) + a "▟ Site feasibility" tool
  launcher + `api.feasibility()` client method. Demo seeds a zoning record so it's demonstrable.
- Reviewed giraffe.build, synaps.app, addd.io and arsray146/ifc-bcf-viewer; most of their AEC
  capabilities are already covered (clash/BCF, IFC takeoff, dashboards, ask-the-model, reports). Site
  feasibility was the clearest on-brand gap; shipped first.
- Backend 70/70; web typecheck + Pages build green; demo verified live.

## v0.3.7 — Specifications → submittals: spec register, spec-driven submittal log, AI extraction
- New `spec_section` module — the project manual / specification register (CSI MasterFormat section
  number + title, division, the Part 1 "Submittals" article text, Part 2 products, responsible party;
  issued/under-revision/void workflow).
- **Spec-driven submittal log** (`specs.py` + `GET /projects/{pid}/specs/submittal-log`): derives the
  required submittals per spec section from the SectionFormat Part 1 Submittals article (typed via a
  submittal-type classifier — Shop Drawing, Product Data, Sample, Mock-up, Certificate, Test Report,
  Calculations, O&M, Warranty), reconciles them against the submittals actually logged (matched by
  MasterFormat section number), and surfaces **missing submittals** per section with a coverage %.
- **AI/rules submittal extraction** (`ai.extract_submittals` + `POST /specs/extract-submittals`):
  paste spec text → a typed submittal list (Claude when configured, deterministic rules fallback
  offline); `create=true` logs each item as a `submittal` and records the `spec_section`, building the
  log straight from the spec book.
- New **Spec-Driven Submittal Log** report (KPIs, by-type chart, by-section table flagging gaps);
  two tool launchers (spec submittal log; extract submittals from a spec) + client methods.
- Backend 69/69; web typecheck + 49 tests + Pages build green.

## v0.3.6 — Preconstruction depth: decision log, assumptions, VE cycle + alignment dashboard
- New `decision` (cross-stakeholder decision log: rationale, alternatives, cost/schedule impact,
  Aligned/Pending/Disputed) and `assumption` (assumptions & clarifications register with allowance
  exposure) modules. `precon.py` rollups + `GET /precon/decisions` and `/precon/assumptions`:
  open counts, disputed, open cost & schedule exposure, by category.
- **VE cycle** analytics on the existing `value_engineering` module — `GET /precon/ve?target=`:
  proposed/accepted/rejected savings + gap-to-close against an over-budget target.
- **Calibrate-style alignment dashboard** — `GET /precon/alignment`: per-domain RAG (estimate vs budget,
  VE coverage of the gap, decisions, assumptions) + an alignment score. New reports: Decision Log,
  Assumptions & Clarifications, Preconstruction Alignment; tool launchers + client methods.
- Completes the preconstruction-depth parity vs Concntric (estimate continuity + decisions + assumptions
  + VE + alignment). Backend 68/68; typecheck + build green.

## v0.3.5 — Preconstruction estimate continuity (Concntric-style design-phase cost tracking)
- New `estimate_set` module (snapshot tagged by design **milestone** — Concept/SD/DD/CD/IFC/GMP/Award —
  with total, gross SF, basis, source) + `precon.py` engine + `GET /projects/{pid}/precon/estimate-continuity`:
  per-milestone **$/SF**, **milestone-to-milestone cost drift**, first→latest drift, and the **gap vs the
  project budget/GMP** (over/under). A one-click `POST /precon/snapshot?milestone=` prices the current
  model (IFC takeoff) and saves it as an estimate set.
- An **Estimate Continuity** report (PDF/Excel) + Report Center tool launcher; client `estimateContinuity`
  + `preconSnapshot`. Closes the design-phase cost-tracking gap vs Concntric, built on Massing's existing
  estimate/budget primitives. Backend 68/68.

## v0.3.4 — Optional licence enforcement (off by default)
- Licence entitlements can now be **enforced**, but it's **opt-in and OFF by default** — the app stays
  fully open and a licence is optional (no registration) until the operator sets `MASSING_LICENSE_ENFORCE=1`
  (Settings ▸ Massing licence). In open mode every `allows()/require()` gate is a no-op.
- When enabled, gates bite by tier: **IFC export** (`GET /source.ifc`) needs Commercial+ (402 otherwise),
  and **programmatic publishing via the REST API key** (e.g. the pyRevit bridge) needs Commercial+ —
  while interactive "Open IFC…" by a signed-in user stays free on any plan. `require()/require_export()`
  helpers + `_MIN_TIER` upgrade messaging; `/license` + `/capabilities` report `enforced`.
- Settings shows an **"open mode — licence optional"** status when enforcement is off (no nagging).
  Backend 67/67 (open mode grants all; enabling gates IFC/API by tier and clears on upgrade).

## v0.3.3 — Help surfaces the Revit add-in
- The in-app **"Import from Revit for free"** dialog now leads with the one-click **Massing for Revit**
  pyRevit add-in (Publish to Massing), then the free manual IFC-export path and batch pyRevit export,
  with a direct link to the add-in. The docs guide FAQ ("Do I need Revit?") lists the same three paths.
  Keeps the help current with the v0.3.2 bridge + licensing.

## v0.3.2 — Massing for Revit (free pyRevit bridge)
- New **pyRevit extension** (`integrations/pyrevit/Massing.extension`) — a free, open **Revit → Massing**
  bridge that needs no paid Autodesk APS bridge. A **Massing** tab with **Publish to Massing** (exports
  the active model to IFC via Revit's built-in exporter, uploads it, runs the server-side Fragments
  conversion, opens the web viewer), **Open in Massing**, **Sync Issues (BCF)** (RFI/clash/punch
  round-trip over BCF, keyed by IFC GlobalId), and **Settings**.
- `lib/massing_api.py` — a std-lib REST client (works on pyRevit's IronPython 2.7 + CPython 3 engines,
  no `requests`): find/create project → upload `source-ifc` → poll `publish/status` → BCF in/out.
  Covered by `test_revit_bridge.py` (67/67). Built on the LearnRevitAPI StarterKit conventions; uses
  the REST API, so it's a Commercial-plan (and up) path while manual IFC export stays free on any plan.

## v0.3.1 — Massing licensing in Settings
- New `licensing.py` engine + `GET /license`: records the workspace's **Massing licence key**
  (`MASS-XXXX-XXXX-XXXX-XXXX`) and **plan tier** (Free · Home · Commercial · Enterprise) and exposes the
  per-tier feature entitlements (export formats, REST API, SSO, Navisworks) per massing.cloud/docs.
- **Settings** gains a "Massing licence" group (paste key + set plan) and a licence-status line showing
  the active plan, masked key, what it unlocks, and a link to manage at massing.cloud. The key format is
  validated on save (malformed keys / unknown plans are rejected); the key is **masked and never echoed
  back**. `/capabilities` now reports `license_tier`. Backend 66/66.

## v0.3.0 — Massing milestone (analytics + RE/capital depth, hardened, rebranded)
First minor release on the Massing brand — marks a coherent, production-ready milestone after the
0.2.x line: the full **construction-analytics suite** (quality · RFI · submittal · T&M · field-log ·
OSHA safety · closeout) stitched into an executive **project-health rollup**; **real-estate / capital
depth** (lease management, equity-waterfall distributions, investor-portal signed statements, comps
import, WPRealWise/MLS syndication); **production hardening** (non-root API container, `/metrics`,
empty-project + malformed-input regression tests); and the **Massing rebrand** end-to-end. All verified
live in the browser. Backend 65/65; web typecheck + vitest (49) + Pages build green; `npm audit` clean.
- Polish: Excel-export buttons alongside the PDF ones on the rent-roll and cap-table Finance cards
  (backend already served `.xlsx`); optimized the social `og-image.png` (674 KB → 94 KB, palette PNG).

## v0.2.16 — Rebrand to Massing (massing.build)
- Renamed the product from "AEC BIM Platform / ModelMaker" to **Massing** across the app, docs, and
  packaging: window title + PWA name, README/CHANGELOG/SECURITY/guide/roadmap/capability-matrix, the
  Pages landing page (canonical + OG → massing.build), and backend report/branding strings.
- New brand assets — Massing isometric-massing logo + icon (`favicon.svg` / `icon.svg`, header logo,
  landing hero, `docs/img/massing-*`).
- GitHub repo renamed to **ibuilder/massing**; GitHub Pages now serves at **massing.build** (CNAME),
  with `VITE_BASE` switched to root `/app/`. Desktop bundle identifier kept (`com.ibuilder.aecbim`) so
  existing installs keep auto-updating; the updater endpoint follows the renamed repo.
- No functional change — backend 65/65, web typecheck + build green; verified live (title/header/favicon).

## v0.2.15 — Wrap-up: reachability, docs & GitHub refresh
- UI reachability audit of the whole v0.2.x arc — all new features confirmed reachable; closed the one
  gap by folding the **T&M-by-change-event** breakdown into the T&M rollup tool (was PDF-only).
- Docs refreshed to current: README "Recent platform work" now leads with the construction-analytics
  suite + RE/capital depth + production hardening; `SECURITY.md` documents the second signed-anonymous
  surface (investor `statement.public.pdf`) and the non-root API container; GitHub About updated.
- Verified green: backend 65/65, web typecheck + vitest (49) + Pages build, `npm audit` 0 vulnerabilities.

## v0.2.14 — Production hardening: non-root API container + observability test
- The API image now runs as a **non-root user** (`appuser`, uid 10001) — `/app` and the `ifc-data`
  volume path are chowned before mount so the named volume inherits writable ownership; added a
  container-level `HEALTHCHECK` for bare `docker run` (compose already health-gates the stack).
- New `test_metrics.py` (65 suites) locks the `/metrics` Prometheus surface: text exposition with
  `http_requests_total` + latency summary + in-flight gauge + uptime, counted by route template and
  incrementing across requests.
- Closes the production/ops phase — backup/restore runbook, `/metrics`, full healthchecks +
  depends-on conditions, rate-limit env knobs, and the Caddy HTTPS overlay were already in place.

## v0.2.13 — Polish & harden: empty-project robustness + a11y
- New `test_empty_project.py` (64 suites): every analytics / RE surface (14 endpoints + 13 PDF/XLSX
  reports) must return 200 with a sane zeroed structure on a brand-new project — guards the "no data
  yet" path against 500s and blank crashes.
- **Hardened** the equity-waterfall scenario: with no investors in the cap table it now returns a clean
  zeroed result + an explanatory note instead of phantom LP/GP splits; the UI surfaces the note.
- Accessibility: `aria-label`s on the new Finance inputs (capital-call amount, waterfall exit/years,
  comparables CSV textarea + file upload).

## v0.2.12 — Comparables import automation (CSV / RESO) — completes RE/capital depth
- New `comps.py` + `POST /projects/{pid}/comparables/import`: bulk-load comparables from **CSV**
  (`{csv}`) or a **RESO array** (`{reso|rows}`) into the `comparable` module, feeding the
  sales-comparison appraisal. Forgiving header mapping (case/space/underscore-insensitive; accepts
  human headers *and* RESO field names like `UnparsedAddress`/`ClosePrice`/`ClosePricePerSquareFoot`);
  coerces `$1,250,000`/`5.5%`; rows without an address are skipped.
- Appraisal tab: an **Import comparables** card (paste CSV or upload a file → recomputes the sales
  approach); client `importComparables`. Backend 63/63.
- **Milestone:** completes the real-estate / capital depth phase (syndication bridge, lease management,
  equity-waterfall scenarios, investor-portal sharing, comps import). Next: polish & harden, then production/ops.

## v0.2.11 — Investor-portal document sharing (signed statement links)
- `POST /projects/{pid}/investors/{iid}/share` mints a signed, expiring (default 30-day) link to an
  investor's capital-account statement, and `GET …/statement.public.pdf` serves it behind HMAC sig
  verification — the investor opens their statement with **no login** (the private analog of the public
  listing). Forged/absent signatures → 403; reuses `signing.py`, so the RBAC posture is unchanged.
- Finance ▸ Investors: a **🔗** button per cap-table row mints the link and shows a QR/share modal;
  client `shareInvestorStatement`. Backend 63/63 (signed link passes, forged/absent → 403).

## v0.2.10 — Equity-waterfall distribution scenarios (cap-table-tied)
- New `distwaterfall.py` + `POST /projects/{pid}/waterfall`: model a distribution / exit through the
  equity waterfall (preferred return → return of capital → IRR-hurdle **promote tiers**, reusing the
  proforma `run_waterfall`), then **allocate each side's take pro-rata across the actual investor
  records** by commitment. Body: `{exit_amount, contribution_date, exit_date}` or `{distributable[],
  dates[]}`; pref/tiers/style default from the latest proforma scenario, overridable. Returns LP/GP
  totals, IRR & equity multiple, period splits, and the per-investor allocation.
- Finance ▸ Investors gains a **Distribution waterfall (scenario)** card (exit $ + years → LP/GP +
  per-investor); client `waterfallScenario`. Backend 63/63 (waterfall clears to the exit, GP earns
  promote, LP split 2:1 by commitment).

## v0.2.9 — Lease-management depth (renewals · escalations · CAM recovery)
- New `leasemgmt.py` + `GET /projects/{pid}/leases/management`: the **renewal/expiration pipeline**
  (leases expiring ≤90/180/365 days, holdover, options outstanding, rent-at-risk), a forward
  **rent-escalation schedule** (each active lease compounded by its `escalation_pct`, plus the
  portfolio base-rent curve by year), and **CAM / expense-recovery reconciliation** (recoverable
  income = `recovery_psf × rentable_sf` for NNN/recovery leases; pass `?recoverable_opex=` for the
  recovery ratio + over/under-recovery gap).
- A **Lease Management** report (PDF/Excel) + a lease-management card under Finance ▸ Operations
  (expiry buckets, escalation step, CAM recovery); client `leaseManagement`. Backend 63/63.

## v0.2.8 — Real-estate Phase 4: WPRealWise / MLS listing syndication + marketing flyer
- New `re_bridge.py` — a feature-flagged outbound syndication bridge (off unless `REALWISE_URL` +
  `REALWISE_API_KEY` set), mirroring the APS / e-sign bridges. `GET /re-syndication/status` reports
  config; `POST /projects/{pid}/listings/{lid}/syndicate` serializes the listing via `marketing.to_reso()`
  and **upserts it into WPRealWise** (`/wp-json/realwise/v1/listings`, Bearer auth, keyed by `ListingKey`
  so re-pushes update not duplicate). Unconfigured → actionable 422; the RESO export endpoint still works.
- Disposition tab gains **⤴ Syndicate to WPRealWise** (bridge-aware) and a **Marketing Flyer** report
  (`marketing_flyer`, PDF/Excel) alongside the fact sheet. Client `reSyndicationStatus` + `syndicateListing`.
- This completes Phase 4 of docs/realestate-marketing.md (the only deferred real-estate item). `.env.example`
  documents the bridge. Backend 63/63 (test_marketing extended: gate-off 422 + stubbed push asserts
  RESO + ListingKey + Bearer); typecheck + vitest (49) + build green.

## v0.2.7 — Field-capture depth (GPS geotag, offline-queue review, PWA shortcut)
- Field capture now **geotags** records: a "📍 Tag GPS location" one-shot fix stores `gps_lat`/`gps_lon`/
  `gps_accuracy_m` on the captured record (online + queued offline).
- New **offline-queue review** sheet: list pending captures (photo/note + geotag), **Sync now**, or
  discard individual items — reachable from the capture sheet (shown when the queue is non-empty).
- **PWA app shortcut** "Field capture" (manifest `shortcuts`) + a `?capture=1` deep link that opens the
  capture sheet on load — long-press the installed icon to snap a jobsite photo in one tap.

## v0.2.6 — Opt-in self-hosted basemap tiles (GIS)
- New `gis.loadBasemap` + **Open → "Add basemap (self-hosted tiles)…"**: lays a Web-Mercator XYZ raster
  tile grid on the ground as a georeferenced reference overlay (focus lat/lon + zoom; tiles placed at
  their projected metric positions, North → −Z). Lists in the federation panel (align ⛭ / remove) via a
  new `viewer.addReferenceObject`.
- **Offline-first / honors CLAUDE.md:** nothing loads unless the operator supplies a tile-URL template
  (e.g. their own/self-hosted `https://tiles.internal/{z}/{x}/{y}.png`) — no public CDN default.

## v0.2.5 — E57 point-cloud import (server-side, optional pye57)
- New `e57.py` + `POST /convert` (`.e57`) / `GET /convert/e57/status`: converts E57 laser-scan files
  to a decimated `.xyz` (x y z [r g b], capped at 2M points) **server-side**, since there is no viable
  in-browser E57 parser. Optional, dependency-flagged on `pye57` (heavy/native, not a default dep) — the
  status/gate is testable without it and the convert returns an actionable 503 until `pip install pye57`.
- The viewer's **Open mesh / point cloud / GIS…** now accepts `.e57`: it routes the file through the
  converter and loads the resulting point cloud as a reference overlay (federation list, align, remove).
  Clients `e57Status`, `convertE57`. Backend 63/63.

## v0.2.4 — Live e-signature bridge (DocuSeal, self-hosted OSS)
- The feature-flagged 3rd-party e-signature bridge (`esign_bridge.py`) now **implements DocuSeal
  end-to-end** over its REST API (stdlib `urllib`, no SDK): create a template from the rendered PDF →
  open a submission with the signers → return submission id + per-signer signing URLs.
- New `POST /projects/{pid}/contracts/{key}/{rid}/send-for-signature` (renders the doc, routes it,
  stores `data.esign_submission`, audited) + a **"Send for signature"** action in the contract record
  tools; `POST /esign/webhook` reflects provider completion. `GET /esign/status` now reports whether the
  configured provider is `implemented`. Off unless `ESIGN_PROVIDER=docuseal` + `ESIGN_API_KEY`/`ESIGN_BASE_URL`.
- Clients `esignStatus`, `sendForSignature`; transport is monkeypatchable + unit-tested (gating 409,
  template+submission shaping, stored submission, webhook parse). Other providers keep an actionable
  stub. Backend 62/62.

## v0.2.3 — Change-order log + meeting action-item tracker (analytics suite rounded out)
- New `changeorders.py` + `GET /projects/{pid}/change-orders/log`: the **CO value pipeline**
  (pending / approved / executed / rejected), reason mix, schedule-day exposure, ball-in-court, plus
  the upstream **change-event ROM exposure** (potential cost not yet a CO).
- New `actions.py` + `GET /projects/{pid}/action-items/tracker`: **action items** open / overdue /
  by assignee & priority, completion %, and the **meeting log** (by type, last meeting).
- Two new reports — **Change-Order Log** and **Meeting Action-Item Tracker** (PDF/Excel) — plus tool
  launchers; clients `coLog`, `actionTracker`. Backend 62/62.

## v0.2.2 — Executive health banner on the GC dashboard
- The GC dashboard now leads with a **project-health banner** driven by `GET /projects/{pid}/health`:
  a 0–100 score, overall green/amber/red, open/overdue totals, a per-domain RAG chip strip (hover for
  each domain's headline), and the top ranked attention items — the executive rollup surfaced
  first-class instead of only in a tool modal.

## v0.2.1 — Closeout dashboard + project-health executive rollup
- New `closeout.py` engine + `GET /projects/{pid}/closeout/summary`: **punchlist completion &
  ball-in-court** (open=Subcontractor, ready=GC-verify, verified; % complete, overdue, open-cost,
  by trade/priority), **commissioning pass rate** (by result & test type), **completion certificates**,
  **warranty expirations** (active / expiring-90d / expired), and **O&M-manual turnover** (% accepted).
- New `projecthealth.py` engine + `GET /projects/{pid}/health`: an **executive rollup** that stitches
  the seven analytics domains (RFIs, submittals, quality, safety, T&M, field reporting, closeout) into
  per-domain green/amber/red status, an overall 0–100 health score, open/overdue totals, and a ranked
  list of attention items.
- Two new Report-Center reports — **Closeout Dashboard** and **Project Health (Executive)** (PDF/Excel) —
  plus "Project health" (top of tools) and "Closeout dashboard" launchers; clients `projectHealth`,
  `closeoutSummary`. Verified live over HTTP against the preview DB (endpoints + all 6 new PDFs). Backend 62/62.

## v0.2.0 — Safety dashboard (OSHA TRIR / DART) + construction analytics suite complete
- New `safety.py` engine + `GET /projects/{pid}/safety/summary`: **OSHA incident rates** — TRIR,
  DART, LTIFR, and severity rate on the 200,000-hour base, computed from the incident module's
  classification / osha_recordable / lost-days / restricted-days fields. Worker-hours are taken from
  `?hours=`, else estimated from daily-report manpower (man-days × 8h). Also rolls up the
  **safety-observation leading-indicator mix** (safe vs at-risk, safe:at-risk ratio, close-out %),
  **toolbox-talk coverage** (talks + attendees), and the **safety-violation log** (open / overdue / by severity).
- A **Safety Dashboard (OSHA)** report (PDF/Excel) — distinct from the existing simple Safety/Incident
  Log — plus a "Safety dashboard (OSHA)" tool launcher; client `safetySummary`. Backend 62/62.
- **Milestone:** this completes the construction analytics suite — every core field log (submittals,
  RFIs, T&M, quality, daily reports, safety) now has a first-class rollup, exportable report, and tool launcher.

## v0.1.99 — Field-log rollup (daily reports → manpower / weather / coverage)
- New `dailylog.py` engine + `GET /projects/{pid}/daily-reports/summary`: **manpower trend**
  (total / avg-per-day / peak with date, preferring the manpower_log rollup over the typed count),
  **weather-impact lost-day equivalents** (Minor 0.1 / Half 0.5 / Full & Stoppage 1.0), **delay days**,
  and **reporting coverage** (logged days vs the date span), with by-weather & by-impact breakdowns.
- A **Field-Log Rollup** report (PDF/Excel) in the Report Center + a "Field-log rollup" tool launcher;
  client `fieldLogSummary`. Backend 62/62.

## v0.1.98 — RFI register / log analytics
- New `rfi.py` engine + `GET /projects/{pid}/rfi/register`: **ball-in-court** (draft→GC, open→Consultant,
  answered→GC-accept, closed/void), **overdue** (date-required passed while awaiting a response),
  **response turnaround**, and **cost/schedule-impact exposure**, with by-discipline & by-priority breakdowns.
- An **RFI Register** report (PDF/Excel) in the Report Center + an "RFI register" tool launcher;
  client `rfiRegister`. Backend 62/62.

## v0.1.97 — Quality dashboard (inspections / NCR loop / deficiency ball-in-court)
- New `quality.py` engine + `GET /projects/{pid}/quality/summary`: **inspection pass-rate KPIs**
  (pass rate = pass+conditional / decided, first-pass yield = clean pass / decided, by type & result,
  agency count); the **NCR disposition→corrective-action→close loop** (by state/disposition/severity,
  overdue, undispositioned, avg days-to-close); and the **deficiency ball-in-court rollup**
  (open=Subcontractor, corrected=GC-verify, closed; by trade & severity, overdue).
- A **Quality Dashboard** report (PDF/Excel) in the Report Center + a "Quality dashboard" tool
  launcher; client `qualitySummary`. Backend 62/62.

## v0.1.96 — T&M → change-event tie
- eTickets gain a **change_event** link; `tm.by_change_event` rolls up field T&M by the change event
  it belongs to (`GET /tm-by-change-event`), with linked vs unassigned totals — closing the chain
  field T&M → change event → CO → SOV → AIA billing (G702/G703 already in `cost.py`). The T&M Log
  report gains a "T&M by change event" table. Backend 62/62.

## v0.1.95 — RFI/submittal distribution lists
- RFIs & submittals gain a **Distribution (CC)** field; `distribution.py` resolves it (names or emails,
  comma/semicolon/newline-separated) against the **Contact directory** into recipients + emails.
- `GET /projects/{id}/modules/{key}/{rid}/distribution` returns the resolved list; the resolved emails
  now ride the **record.transition webhook** (`distribution: [...]`) so a listener can notify the CC list.
- Tests in `test_distribution.py` (backend 62/62; rfi/submittal fieldsets kept contiguous).

## v0.1.94 — drawing transmittals + issuance diff
- The drawing-set register now classifies each current sheet as **new** vs **revised** (issuance diff)
  and reports `new_count` / `revised_count`.
- **Drawing transmittal PDF** (`GET /drawing-set/transmittal.pdf?to=…&note=…`): the controlled current
  set grouped by discipline with current revision + New/Revised status, recipients and a note — a ⬇
  Transmittal button in the drawing-set view. Backend 61/61.

## v0.1.93 — construction depth: T&M rollup + submittal register
- **T&M / eTicket cost rollup** (`tm.py`): aggregates eTickets into labor/material/equipment totals,
  by status, with **billed vs unbilled**; `GET /tm-summary` + a T&M / eTicket Log report.
- **Submittal register** (`submittals.py`): spec-section-organized log with **turnaround**
  (received→returned), **ball-in-court**, and **overdue** flags (required-on-site passed, not closed);
  `GET /submittals/register` + a Submittal Register report.
- Both auto-list in the Report Center (PDF/Excel) and have interactive launchers in "Project tools &
  analytics". Tests in `test_construction_depth.py` (backend 61/61).

## v0.1.92 — capital calls & distributions now post to the cap table
- `POST /capital-call` and `/distribution` accept `persist: true` — posting each allocation to the
  investor's **contributed** / **distributed** running total, so the cap table's contributed /
  distributed / unreturned (and the statement PDF) track over time instead of being preview-only.
- Investors tab: **Preview** vs **Record** buttons; recording refreshes the cap table live.
- Backend 60/60 (incl. a persisted-call assertion).

## v0.1.91 — dedicated Operations & Investors tabs + investor statements
- Finance gains two first-class sub-tabs: **Operations** (the hold-phase rent roll — occupancy, WALT,
  in-place income, value-from-rent-roll) and **Investors** (cap table, capital-call/distribution
  tools, per-investor downloads) — moved out of the Valuation tab so each has a clean home.
- **Per-investor capital-account statement PDF** (`GET /projects/{id}/investors/{iid}/statement.pdf`):
  commitment, ownership, contributed/distributed, unreturned + unfunded — a ⬇ per row on the cap table.
- Verified live (both tabs render with seeded data; statement link present); backend 60/60.

## v0.1.90 — accessibility pass: every feature reachable in the UI
A UX audit found seven computed features were API/report-only (no buttons). All are now wired in:
- **Finance ▸ Valuation tab** gains a **Rent roll** card (occupancy/WALT/in-place income + "value
  from rent roll"), an **Investor cap table** card with **capital-call / distribution** tools, and
  the existing appraisal/disposition cards.
- **Report Center ▸ Project tools & analytics** adds launchers for the **Project assistant**,
  **WH-347 certified payroll** (week picker + preview), **Drawing-set register**, **ITB coverage**,
  and **Field-verification coverage**. (The rent_roll/cap_table/appraisal/listing reports already
  auto-list there.)
- **Login** now shows an "SSO available — set `AEC_OAUTH_*`" hint when no providers are configured,
  instead of silently hiding sign-in options.
- Verified live (all surfaces render, console clean), authz re-audited (every new endpoint
  `require_role` + project-scoped; financial writes = editor), `npm audit` 0 vulns, and the new
  tables (`mod_lease`, `mod_investor`, `element_verifications`) confirmed to migrate on **Postgres**.

## v0.1.89 — operate, capital, payroll, drawing-set, assistant & ITB
Six capability gaps closed across operations, capital, payroll, drawing-set control, the project
assistant, and invitation-to-bid.
- **Operating asset mgmt (rent roll):** a `lease` module (Operations) + `rentroll.py` — occupancy,
  WALT, lease-expiration schedule, in-place income; `GET /rent-roll` + a Rent Roll report. The
  appraisal income approach can value off the actual roll: `GET /appraisal?rentroll=1`.
- **Investor / LP capital:** an `investor` module (Capital) + `capital.py` — cap table by commitment,
  pro-rata **capital-call** & **distribution** allocation; `GET /cap-table`, `POST /capital-call`,
  `POST /distribution` + a Cap-Table report. Data-room reuses the document module + attachments.
- **Certified payroll (WH-347):** `payroll.py` aggregates timesheets × labor rates into a weekly
  Davis-Bacon certified-payroll PDF (straight/OT split, prevailing-wage flags); `GET /payroll`,
  `GET /payroll/wh347.pdf`.
- **Drawing-set register:** `drawingset.py` derives the controlled current set from `drawing`
  records (latest revision per sheet = current, earlier = superseded) + sheet index + discipline
  rollup; `GET /drawing-set`.
- **Project assistant:** `assistant.py` extends "ask" from the BIM index to the whole project
  (module tallies, schedule, budget, risk, rent roll); `POST /assistant` (+ `/assistant/snapshot`),
  AI-optional (returns the snapshot without a key).
- **ITB tracking:** `itb.py` rolls up bid packages vs submissions (invited / responded / bonded /
  low bid / coverage gaps); `GET /bidding/itb` + `POST /bidding/packages/{id}/invite`.
- Tests: `test_operate_capital`, `test_payroll_drawings`, `test_assistant_itb` (backend 60/60).

## v0.1.88 — model intelligence, field verification & embeddability
Three features adapted from a scan of **Argyle** (AR field verification) and **Flinker** (OpenBIM in
M365) — built to Massing's open, self-hosted, $0 identity (no AR hardware, no MS-365 lock-in).
- **Ask the model** — `POST /projects/{id}/ask` answers plain-English questions ("how many fire-rated
  doors on L3?", "total curtain-wall area") grounded in a snapshot of the property index (counts by
  class/storey, Psets, facets). Uses the configured AI provider; **degrades to the data snapshot**
  when no key is set. A "✦ Ask" button in the Model workspace.
- **Field verification + install coverage** — mark elements **installed / verified / deviation**
  against design (keyed by GUID, photo-anchored) from the element panel; a coverage summary
  (`GET …/verification/coverage`, % verified/installed of the model total) + a **deviation log** for
  the verified-handover to operations. Argyle's core value, no AR hardware. New `ElementVerification`
  table + `routers/verification.py`.
- **Embeddable viewer + outbound webhooks** — `?embed=1` renders a chrome-less, read-only viewer for
  an `<iframe>` / web-component / Teams tab; module transitions fire **outbound webhooks**
  (`AEC_WEBHOOK_URLS`, fail-open) so Power Automate / Zapier / a custom listener can react. New
  `webhooks.py`.
- Tests: `test_ask.py`, `test_verification.py`, `test_webhooks.py`. Verified live (Ask snapshot,
  embed chrome-less, webhook dispatch + fail-open).

## v0.1.87 — workflow engine upgrades
Cross-cutting upgrades to the config-driven modules engine — each lights up across all ~75 modules,
drawn from construction-management workflow best practice.
- **Transition field-gating** — a workflow transition can declare `requires: [field, …]` that must be
  filled before it fires (RFI can't be *Answered* without an answer). `available_actions` advertises
  it; the action button disables with a "(needs …)" hint until satisfied. Generalizes the attachment
  evidence-gate.
- **Company / Contact directory + first-class lookups** — new `company` + `contact` modules; vendor /
  sub / contact fields become `reference` lookups into the directory (`subcontract.vendor_company`),
  with the picker, resolution and reverse links for free.
- **Due dates / SLA feed** — `GET /projects/{pid}/due-feed` + a "⏰ Deadlines" portal-home widget:
  open records past or near their due date (overdue / due-this-week), across the 11 modules with a
  due field; terminal/closed records excluded.
- **In-app workflow map** — the record view renders a compact state diagram (current state
  highlighted, reachable next-states emphasized). (Saved views already existed.)
- Tests: `test_workflow_gate.py`, `test_due_feed.py`, `test_directory.py` (backend 54 suites).

## v0.1.86 — disposition & valuation (real-estate marketing)
Close the development loop from build to **sell/lease** and **market value** — the two things only a
BIM-native platform can do, because Massing owns the model + proforma. (See
[docs/realestate-marketing.md](docs/realestate-marketing.md).)
- **BIM-native marketing kit** — a config-driven `listing` module (RESO-aligned fields + a workflow
  mirroring RESO `StandardStatus`) that **auto-fills from the project**: areas/unit-mix from the model,
  NOI/cap/asking price from the proforma. One click generates a **Listing Fact Sheet** PDF and a
  signed, expiring **public link + QR** to share a listing without a session (the only anonymous
  surface — token-scoped, read-only, rate-limited).
- **Tri-approach appraisal** — `appraisal.py` fuses the three classic approaches from data already
  in-system: **Cost** (replacement cost from the estimate + land − depreciation), **Income** (NOI ÷
  cap from the proforma), **Sales comparison** (adjusted $/SF from the `comparable` module),
  reconciled into an opinion of value with a range. New **Valuation** tab in Finance (three approach
  cards, editable reconciliation weights, value-by-approach chart) + a **Valuation report** (PDF/Excel).
- **RESO export seam** — `marketing.to_reso()` serializes a listing to RESO Data Dictionary fields, so
  a later bridge can push listings to WPRealWise / an MLS as a serialization, not a rewrite.
- Endpoints: `GET /projects/{pid}/listings/autofill`, `GET|POST /projects/{pid}/appraisal`,
  `GET …/listings/{lid}/reso`, `POST …/listings/{lid}/share`, `GET …/listings/{lid}/public`.
  Tests: `test_appraisal.py` (engine) + `test_marketing.py` (autofill → appraisal → reports → RESO →
  signed public link).

## v0.1.85 — production readiness
- **Readiness probe:** new `GET /ready` (and `/readyz`) pings the DB (`SELECT 1`) and returns `503`
  when it's unreachable, so a load balancer / orchestrator stops routing to a degraded instance;
  `GET /health` (`/healthz`) stays a cheap dependency-free liveness check. The ping runs under a hard
  wall-clock timeout (`AEC_READY_TIMEOUT`, default 3s) and the Postgres engine gets a connect timeout +
  TCP keepalives, so a *black-holed* DB (paused host / partition) yields a prompt `503` instead of
  hanging the probe — verified against a real paused Postgres.
- **Multi-worker login lockout:** the brute-force lockout now shares its counter across workers via
  `AEC_REDIS_URL` (atomic Redis `INCR`+`EXPIRE`), fail-open to the in-process counter — matching the
  per-IP rate limiter. The API runs multi-worker in production, so the lockout now actually holds.
- **Hardened-by-default deploy:** `docker-compose.prod.yml` now sets RBAC, `AEC_REQUIRE_SECRET`,
  HSTS, secure cookie, strict CSP, body cap, rate limit, and ships a `redis` service for the shared
  counters; `.env.example` documents every hardening flag (and how to generate a strong secret).
- **Schema migrations documented + tested:** the app uses an additive, dbDelta-style startup sync
  (fits the config-driven dynamic module tables) rather than Alembic; `SECURITY.md` documents the
  policy + the manual escape hatch for non-additive changes, and `test_migrate.py` proves a new
  nullable model column is ALTERed onto an existing DB and new indexes backfill (additive-only).

## v0.1.84 — security hardening
- **Access control:** RBAC defense-in-depth gate (anonymous blocked from project/finance/admin
  prefixes when `AEC_RBAC=1`), `require_role` on every project-scoped finance/data endpoint, attachment
  download IDOR fixed, projects list scoped to the caller's memberships.
- **Hardening headers** on every response (nosniff, frame DENY, referrer, CSP) + **opt-in strict CSP**
  (`AEC_CSP=1`); **request body-size cap** (`AEC_MAX_UPLOAD_MB` → 413).
- **Path traversal** closed at the storage layer (resolved-path containment) + upload-filename sanitization.
- **Auth:** login brute-force lockout (429), `Secure` auth cookie over HTTPS, fail-fast on a default
  signing secret (`AEC_REQUIRE_SECRET=1`).
- **Signed/expiring download URLs** for `model.frag` + attachments (HMAC, short-lived) — for QR share /
  worker fetch / deep links without a session.
- **Docs:** new `SECURITY.md` (disclosure policy, threat model, production env-flag checklist).
- Production npm dependencies carry no known vulnerabilities (CI runs `pip-audit` + `npm audit`).

## v0.1.83 — charts & graphs (construction + real-estate best practice)
- **Reusable SVG chart kit** (`ui/charts.ts`, dependency-free, theme-aware): multi-series line
  (S-curve), grouped/stacked bar, waterfall, tornado, histogram, donut, progress bar, sparkline.
- **Finance (proforma)** — Underwriting: a **capital-stack donut** (debt/LP/GP), a **JV-distributions
  donut**, equity cash-flow bars, and a one-way **IRR tornado** (derived from the 2-way matrix).
  Statements: **NOI vs net-income** line + **cash-flow-by-year** stacked bar.
- **Construction (GC portal)** — executive **progress bars** (% complete · bought-out · spent) and a
  **budget vs committed vs actual vs EAC** grouped bar by category.
- **Report Center** — charts embedded in the PDFs (cost bar, EVM cash-flow S-curve, financials
  NOI/net-income line) via reportlab's built-in graphics; Excel keeps the data tables for re-charting.

## v0.1.82 — financial statements & tax modeling
- **Three financial statements + tax** — the Finance proforma gains a **Statements** tab (and a
  Report-Center "Financial Statements" PDF/Excel) built on `financials.py`:
  - **Income statement** — stabilized operating P&L (Potential Gross Rent → vacancy/credit → Effective
    Gross Income → operating expenses → **NOI**; then interest, straight-line **depreciation**, income
    tax → **net income**) plus a year-by-year operating summary.
  - **Balance sheet** — Assets (land + improvements net of accumulated depreciation + capitalized
    financing + cash) = Liabilities (loan) + Equity (paid-in + retained); **balances every year**.
  - **Cash-flow statement** — GAAP three-section (Operating / Investing / Financing), indirect method.
  - **Tax** — 27.5-yr residential / 39-yr commercial straight-line (land non-depreciable), annual income
    tax with **passive-loss carryforward** (§469: loss years are suspended, offset later income, and the
    remainder releases against the gain at sale), and at sale **§1250 depreciation recapture** (≤25%)
    stacked on **capital gains** (+ NIIT) — driving an **after-tax** equity IRR / multiple. Institutional
    defaults, overridable via a `tax` block.
  - **Per-year columns** — columnar **balance sheet by year** (balances every column) and **cash flow by
    year** alongside the stabilized-snapshot cards.
  - **Two-sided budget** — the development budget as **Uses** (left) vs **Sources** (right); both tie.
  - Endpoints: `POST /proforma/financials`, `GET /projects/{pid}/financials`,
    `GET /projects/{pid}/budget/two-sided`.

## v0.1.81 — properties panel, multi-city permits, money + BCF hardening
- **Robust properties panel** — the element inspector is now structured (IFC-class badge, copyable GUID,
  collapsible **Attributes / Quantities / Property Sets** with counts), formats values (numbers,
  Yes/No, dashed empties, `{value,unit}`), and adds a live **filter**, per-row click-to-copy, and
  **Copy all**. Quantities (qtos) are shown for the first time; the no-backend fallback renders a
  collapsible tree instead of raw JSON.
- **Interchangeable multi-city permit open data** — a Socrata-based feed (NYC · SF · Chicago · LA ·
  Austin, one-entry to add a city) normalized to one record shape; query near a point/by text, a GeoJSON
  GIS overlay, and a **"Import from city open data"** action that seeds the GC `permit` log
  (source-tagged, deduped). From the github.com/ibuilder portfolio review.
- **Sources & Uses reconciles to the dollar** — line items now sum exactly to the totals and sources tie
  to uses (no per-line rounding drift); `balanced` is a strict check. (WPLedger money-handling review.)
- **BCF round-trip preserves pins** — project-Topic export/import now carry a pin's element GUIDs +
  anchor (previously dropped); 5 orphaned test suites wired into CI; empty/cyclic-project edge cases and
  a 404 (not 500) for unknown modules. Backend suites: 47.
- **Schedule acceleration advisory** — rule-based crash / fast-track / near-critical levers off the CPM
  critical path; `GET /projects/{pid}/schedule/optimize` + an "Accelerate (advisory)" tool. Advisory only.
- **Project risk digest** — cost + schedule + open-items + safety drivers with a prioritized narrative;
  `GET /projects/{pid}/risk-digest` + a Report Center "Risk Digest" report.

### audit follow-ups (ties, queue-readiness, RFI triage, schedule alerts)
- **Predictive schedule alerts** — `GET /projects/{pid}/schedule/alerts` (+ a section in the Executive
  report): overdue work, late / at-risk starts (incomplete predecessor), behind-schedule SPI, and a
  procurement-risk proxy, from the cost-loaded schedule + CPM.
- **AI RFI triage** — categorize + ball-in-court + draft response (see e-sign/AI sections).
- **Relationship ties** — COR ⤳ SOV line, awarded bid ⤳ subcontract conversions; cor→change_event ref.
- **Queue-readiness (no Celery)** — IFC publish extracted to a worker-callable `run_publish(pid)` +
  interrupted-job recovery; rationale in docs/audit-2026-06.md.

### PDF digital signatures (PAdES) + e-sign options
- **Digitally sign (PAdES)** — a contract/CO can be signed with a certificate-based **PAdES** digital
  signature (Bluebeam's model) via **pyHanko**: the document is rendered, signed (tamper-evident,
  self-validating), attached, and the signer + cert **fingerprint** recorded. Uses a self-signed
  platform certificate by default (offline, no cost); set `ESIGN_P12` to sign with your own / a CA cert.
- **3rd-party bridge (feature-flagged)** — `esign_bridge.py` + `GET /esign/status` scope DocuSign /
  Dropbox Sign / self-hosted DocuSeal·Documenso for legally-binding multi-party signing (off until
  `ESIGN_PROVIDER` is configured). Decision write-up in **docs/esign-options.md** (electronic vs
  digital vs SaaS vs OSS; eIDAS / ESIGN Act / UETA; recommendation).

### Report Center (detailed, exportable reports)
- **📊 Report Center** — a catalog of detailed reports, each downloadable as **PDF or Excel**:
  **Executive Summary** (CPI/SPI/EAC, % complete, open RFIs/submittals/COs, safety), **Cost Report**
  (budget/committed/actual/forecast/variance by category), **EVM / S-Curve** (SPI, EAC, cash-flow
  curve), and operational logs (Change Order / RFI / Submittal / Daily / Safety) + **Contracts &
  Signatures**. Built from the existing px / budget / module engines (`reports.py`); endpoints
  `GET /reports` + `GET /projects/{pid}/reports/{report}.{pdf,xlsx}`. Opens from the 📊 toolbar button.

### contract & change-order document lifecycle
- **Generate contract documents** — from a contract record: **Prime Contract**, **Subcontract**
  (AIA A401-style), and **Change Order** (AIA G701-style, showing original → revised contract sum)
  PDFs, merged with project/contract data (`contracts.py`, reportlab).
- **Exhibit generator** — **Compose Exhibit A — Scope of Work** from an editable clause/scope library
  (`scope_library.py`: general/supplementary conditions + per-CSI-division scopes with `{{merge}}`
  tokens); pick clauses → exhibit PDF, attachable to the record.
- **View & markup** — open any generated contract/CO in the PDF markup overlay to redline
  before signing.
- **Signatures & approval** — capture per-party typed signatures (`POST …/contracts/{key}/{rid}/sign`,
  one per party, audited) that render into the document; route/approve via the existing party-gated
  workflow. Endpoints: `GET /scope-library`, `GET …/contracts/{key}/{rid}/document.pdf?doc=&clauses=&attach=`.

### AI estimate (text → BOQ)
- **Draft a Bill of Quantities from a description** — the conceptual-estimate tool gains
  **✨ Draft BOQ from description**: type the scope and the AI returns priced line items
  (description / qty / unit / rate / CSI division) with a rolled-up total. Reuses the existing
  Anthropic provider + `ai_enabled()` gate; degrades to a clean stub (no fabricated numbers) when no
  API key is configured. Endpoint `POST /projects/{pid}/ai/estimate`.

### regional classification standards + GAEB export
- **Regional classifications** — map the model estimate's IFC-class line items to **DIN 276** (DACH),
  **RICS NRM 1** (UK), or **CSI MasterFormat** (US/CA) via `GET /classifications` + a built-in code
  table (`classification.py`).
- **GAEB DA XML (X83) export** — `GET /projects/{pid}/estimate/gaeb.x83?system=…` exports the
  estimate as a GAEB 3.2 Bill of Quantities (the DACH tender standard); the conceptual-estimate
  result now has **↧ GAEB · DIN 276 / NRM 1 / MasterFormat** download buttons.

### PDF takeoff & markup
- **PDF takeoff** — **Drawings → 📄 PDF Takeoff** opens a PDF drawing (pdf.js, offline worker),
  lets you **calibrate the scale** (draw a line, enter its real length), then **measure distance /
  area**, **count** items, and drop **rectangle** annotations directly on the sheet — with a running
  Σ length / area / count panel, an editable measurement list, and **CSV export** of the takeoff
  lines. Coordinates are stored in PDF user-space so measurements stay correct as you zoom.

### GIS / topography layer
- **Import GIS & topography** — **Open ▾ → Open mesh / point cloud / GIS…** now also opens
  **GeoJSON** (parcels, contours, site vectors → points/lines/filled polygons) and **GeoTIFF DEMs**
  (→ a hypsometric terrain mesh displaced by elevation). Layers are georeferenced (lon/lat projected
  to metres; projected coords pass through), list in the federation panel, and align with the same
  ⛭ transform / working-origin as other reference models. Offline (`geotiff` + `earcut`, no CDN).

### model federation, alignment & federated clash
- **Navisworks-style model layering** — each reference overlay (mesh / point cloud) now has a ⛭
  transform panel in the federation list: X/Y/Z offset, a **Z-up → Y-up** flip, uniform scale,
  **Move to picked point**, and Reset — so you can align several models in one space.
- **Multi-discipline models** — append discipline IFCs (STR / MEP / ARCH …) to a project via the
  Coordination panel's **＋ Add discipline IFC** (or `POST /projects/{pid}/models`); they layer in
  the viewer and join clash.
- **Federated (cross-discipline) clash** — **🔗 Federated clash** runs `detect_federated_files`
  across the project's layered models (primary source IFC + appended disciplines), excludes
  intra-model overlaps, lists clashes grouped by model-pair, and turns the top hits into BCF clash
  topics → pins / Issues. (Clash needs real IFC geometry — meshes/point clouds don't clash.)

### multi-format reference models + QR share
- **Open meshes & point clouds** — alongside IFC/Fragments, the viewer now opens **OBJ, STL, PLY,
  glTF/GLB** meshes and **PCD, XYZ, LAS, LAZ** point clouds as **view-only reference overlays** (IFC
  stays the source of truth). LAS/LAZ are decoded locally (offline) via a vendored `laz-perf` WASM;
  big clouds are decimated to stay responsive. Reference models list in the federation panel with
  visibility + remove. **Open ▾ → Open mesh / point cloud…**
- **QR share** — a toolbar **📱 Share via QR** shows a scannable deep link to open the project on a
  phone/tablet.
- **Faster Open IFC** — the native file dialog now appears instantly (the heavy 3D module warms in
  parallel); large IFCs (>~60 MB) route through the server pipeline and stream optimized fragments
  instead of parsing the whole file in-browser.
- **Live demo shows the full platform** — the GitHub Pages viewer-only build now bundles a read-only
  sample project so the GC portal, Budget/GMP, Schedule and Finance panels render with real data.

## v0.1.80 — multi-user persona views + optional paid RVT→IFC bridge
- **Membership shapes the view** — a project member's party role (GC / Owner / Consultant /
  Subcontractor) now auto-selects their persona on open, so they land in the right workspace set;
  capability role already gated edit controls. Members modal (add / role / party / remove) present.
- **Revit (.rvt) → IFC bridge (optional, paid)** — feature-flagged on `APS_CLIENT_ID/SECRET`, doubly
  gated: bridge off → 501 + the free IFC-export path; on → must `confirm_cost` (Autodesk bills per
  conversion). Real RVT→IFC runs Revit's exporter via APS Design Automation (`APS_DA_ACTIVITY`).

## v0.1.79 — 4D colour scrub + quantity takeoff by floor
- **Time-aware 4D scrub** — scrubbing the timeline paints the model green floor-by-floor (rest
  ghosted) with a live **cost-burn** readout from the cost-loaded cash-flow curve.
- **QTO by floor & discipline** — quantities + cost mapped to the storey they sit on, per-floor
  totals + a discipline (IFC class) roll-up.

## v0.1.77–78 — 5D element intelligence
- **Click an element → its 5D** — schedule activity (%-complete, dates, hard-tied vs by-trade) +
  cost-code budget vs committed vs actual. **Model heatmap** — colour by %-complete or cost variance.
- **One-click generate seeds the GC portal** — lot→building→deal also creates cost codes, a
  hard-cost-allocated budget, a GMP prime contract, and a cost-loaded schedule.

## v0.1.73–76 — dashboards + investor deliverables, one language
- **Developer Overview command center** + cross-pillar **Portfolio** (GC status *and* developer
  returns per project, blended IRR), one-click **Save scenario**, and a **Construction Status**
  section in the investor memo + deck. **PX executive band** — on-schedule next to on-budget.

## v0.1.67–72 — developer ↔ GC capital chain
- **GMP ↔ hard-cost reconciliation + one-click sync**, construction **draws** from the schedule, an
  **actuals loop** (owner invoices → re-forecast IRR), **construction-loan draws** (equity-first)
  with **interest accrual** + **per-cost-code composition**, and a **lender draw-request PDF**.

## v0.1.60–66 — GMP project budget (its own destination)
- **Budget** is a first-class destination: the agreed GMP broken to every cost code & bid package +
  General Conditions / Requirements (incl. **staffing** projections) + overhead / fee / contingency,
  each budget vs committed vs actual vs **EAC/ETC**. **Buyout savings**, **change orders → revised
  GMP**, owner **SOV from the budget**, a **cash-flow S-curve**, **baseline + variance** — reconciled
  to the developer proforma's hard cost.

## v0.1.53–59 — relational schedule, field/mobile, GC module depth
- **Relational scheduling** — `schedule_activity` drives the Gantt / Line-of-Balance / CPM **and**
  the 3D 4D model; editable P6 `.xer` import; **lookahead** + **milestone** schedules.
- **Field/mobile** — bulk photo + camera capture, photo-first records, offline upload queue;
  **coordination-issue BCF round-trip**.
- **GC module depth** — ball-in-court, super/PM personas, fieldsets, researched Tier-1/2/3 field sets
  across the 73 modules. **Release pipeline hardened** (version from git tag; single-draft publish).

## v0.1.52 — GC dashboard redesigned as a command center
- **Dashboard rebuilt around the new nav rail** — the redundant "All modules" catalog is gone (the
  persistent left rail owns navigation now), and the dashboard is a focused command center: **clickable
  KPI cards** that jump straight to the relevant filtered module (Open RFIs → RFIs · open), a risk
  summary, a prominent **"Ball in your court"** action list (with a caught-up empty state), a grouped
  **Project health** card (budget over/under + safety + lean PPC), trend charts, and Ask AI at the
  bottom — in a two-column layout that stacks on narrow screens.

## v0.1.51 — cost-code workflow: inline add + wider links (roadmap D1 + X1)
- **Inline "add new" from reference dropdowns (D1)** — every reference field (cost code, location, sub…)
  now has a "＋ Add new …" option that creates the record without leaving the form and selects it. So
  while coding a budget line you add the cost code on the spot. Falls back to the target module's
  required field, so a new Cost Code is created with its `code`.
- **Cost-code links on cost-impacting modules (X1)** — RFIs, CORs, change events, PCO requests and
  proposals gained a `cost_code` reference, so impacts tag a code and roll up to the budget (joining
  budget/commitment/direct-cost/timesheet). `/modules` now exposes `title_field`/`ref_prefix`.

## v0.1.50 — GC portal navigation rail + module improvement roadmap
- **Persistent left nav rail in the GC portal** — opening a module used to replace the whole panel, so
  moving between the 73 modules meant going "back" every time. Now a sticky left rail (Dashboard +
  filter + favorites + collapsible sections) stays visible and loads each module into a content pane —
  jump anywhere in one click, with the active module highlighted. (Stacks above the content on phones.)
- **GC module deep-dive roadmap** ([docs/gc-modules-roadmap.md](docs/gc-modules-roadmap.md)) — a
  field-by-field audit of all 73 modules against how large GCs run these workflows, with cross-cutting
  themes (cost-code links everywhere, ball-in-court
  /assignee, fieldsets, inline add-from-dropdown, super-vs-PM views, cross-module conversions) and
  tiered per-module priorities. How to **add cost codes**: Construction → Cost Codes (Resources) → + Add.

## v0.1.49 — left rail revamp (crisp icons + expandable labels)
- **Modernized the left icon rail** — the oldest piece of the UI. The cryptic `⌗`/`≣` Unicode glyphs
  are replaced with crisp inline **SVG icons** (hierarchy / layers / flag / gear), and the rail is now
  **expandable** (VS Code activity-bar style): a `‹`/`›` toggle widens it 46→150 px to show **Tree /
  Layers / Issues / Tools** labels beside each icon, persisted to localStorage. Structure unchanged
  (the four Model-workspace panels were already the right set); this is legibility + feel.

## v0.1.48 — closeout package reachable in the UI
- **Full turnover .zip now has UI access** — the `closeout/package.zip` deliverable (as-built IFC +
  COBie/QTO/space workbooks + status report + closeout records) worked via the API but had **no
  button anywhere**. Added it to **Save ▾ → Closeout package (.zip)** and the **Tools → Exports**
  panel (📦). Found by debugging every menu item against a real demo project. (The `.mmproj` bundle —
  geometry + full database + blobs, round-trips via Open/Save — was already wired.)

## v0.1.47 — end-to-end demo hardening (closeout filename + generate→finance)
Two real bugs found by a full login→closeout demo run (only surface with a realistic project):
- **Closeout package 500** on any project name containing a non-latin-1 char (em-dash, smart quote,
  accent, emoji): the name went into a `Content-Disposition` header, which HTTP encodes as latin-1 →
  crash. Fixed with a shared `safe_filename()` (also hardens the `.mmproj` bundle vs CJK/emoji).
- **Finance showed $0 right after generating a model**: generate didn't persist a cost budget, so
  Sources & Uses read the empty starter. Generate now seeds a `dev_budget` (land + hard from GFA×$/sf
  + soft) → Finance immediately shows the real deal ($21.2M uses on the demo).
Regression-locked: the closeout test now uses an em-dash project name; the generate test asserts
non-zero Sources & Uses. Full gate green (API 30/30).

## v0.1.46 — Studio UX hardening
- **Studio layout bug fixed** — `#panel-studio` carries both `.fullpanel` and `.studio`, and
  `.fullpanel.active{display:block}` was overriding `.studio{display:flex}`, so the node canvas grew
  to its full 1700 px content instead of filling the viewport. Now a higher-specificity rule forces
  the flex column; the canvas is viewport-bounded and **scrolls internally**.
- **Touch support** — node dragging uses pointer events (+ `setPointerCapture`, `touch-action:none`),
  so it works on tablets/phones, not just mouse.
- **Empty-state guidance** — an in-viewport hint ("add a node… then wire… Run", or "connect the API")
  when the canvas is empty.
- **Smarter node placement** — new nodes drop into the current scroll viewport (with a small cascade)
  instead of a fixed corner that overlapped after a few adds.

## v0.1.45 — custom unit-mix editor (A1b — Test Fit A-theme complete)
- **Define your own unit mix** — the Test Fit panel gains an editor to add/remove unit types
  (name · target SF · mix %), saved to localStorage. "Compare schemes" sends it with `with_defaults`
  so your mix is **ranked against the built-in presets**. Completes A1b — the Test Fit A-theme
  (A1–A6 + egress check + auto egress geometry) is now fully done.

## v0.1.44 — P6 .xer → 4D dates + auto code-positioned egress (A2)
- **Primavera P6 schedule → 4D dates** — `POST /projects/{id}/schedule/import-xer` parses a P6 `.xer`
  (TASK table) and stores it; the **4D scrub then reports real calendar dates** (`source:"p6"`, the
  project's start→finish window) instead of relative takt days. New "⬆ Import P6 schedule (.xer)"
  button beside the 4D tool; a 📅 line shows the imported range. `DELETE …/import-xer` reverts to takt.
  (Element build-order stays takt-derived — no per-activity element mapping is claimed.)
- **A2 — auto code-positioned egress geometry** — generated models with a service core now place
  **two means of egress**: the core stair plus a second "Egress stair 2" at the opposite corner
  (≥⅓-diagonal remoteness, IBC 1007.1.1). Completes the generative half of Test Fit A2 (the egress
  pass/fail check already existed).

## v0.1.43 — demo-aware empty states, mobile/PWA polish, P6 .xer import
- **Demo-aware empty states** — the GC portal & drawings no longer show a misleading "pick a project"
  in the viewer-only Pages demo (there's no backend there). A shared `noProjectHtml` explains it's the
  viewer demo + links to the full app; in the real app it gives an actionable "create/open a project"
  hint.
- **Mobile / PWA polish** — `touch-action:none` + `overscroll-behavior:none` on the 3D container so
  camera-controls own touch gestures (orbit/pan/pinch) instead of the page scrolling; PWA install meta
  (theme-color, apple-mobile-web-app-*, viewport-fit=cover); bigger tap targets for the rail + viewer
  tools on phones.
- **Primavera P6 .xer schedule import** — `schedule.parse_xer` reads the TASK table (planned→actual→
  early date fallback) into the activity rows the CSV mapping path consumes, so a P6 schedule can drive
  the 4D scrub. `.mpp` stays export-to-XML/CSV (proprietary binary). Gated in test_analysis.
- **Roadmap reconciled** — A-theme status clarified (A1/A3/A4/A5/A6 + egress check + parking geometry
  + polygon offset done; only unit-type presets + auto-placed egress geometry remain); schedule-import
  + "what else to import" + Revit/Navisworks-plugin + IFC5-alpha verdicts recorded.

## v0.1.42 — main.ts refactor round 2 (account/admin UI) + login on modalShell
- **Modularization** — the account / auth / admin surface (sign-in + SSO, reset, account menu,
  self-service password, admin user management, audit log, project-member management; ~330 lines)
  moves out of `main.ts` into `account/accountUI.ts` behind a small deps object. With round 1's
  connections extraction, **`main.ts` drops from 1205 → 657 lines**.
- **Login fix** — the sign-in dialog hand-rolled its own overlay and so lacked Esc-to-close, a focus
  trap and dialog ARIA. It's now built on the shared `modalShell` like every other modal — consistent
  look + behaviour + accessibility.

## v0.1.41 — main.ts modularization (round 1) + XSS hardening
- **Security (stored-XSS fixes)** — admin modals interpolated user/remote values straight into
  `innerHTML`. Now escaped via a shared `escapeHtml`: connection **name/type**, Procore **project ID**
  + sync info, **browsed DB** column names & cell values, and audit-log fields (the audit modal's
  weaker local escaper is replaced). No user- or database-controlled string renders as HTML anymore.
- **Modularization + perf** — the ~240-line admin **Data-connections UI** (list/add, Procore
  schedules + field-mapping, SQL browser) moved out of `main.ts` into `connections/connectionsUI.ts`,
  **lazily imported** so its ~13 kB leaves the initial bundle and loads only when an admin opens it.
  `main.ts` drops from ~1205 to 963 lines. Behavior unchanged; verified via the vite transform
  pipeline + typecheck + web unit tests.

## v0.1.40 — viewer camera fix + egress surfaced (UX verification pass)
- **Fix: NaN camera / broken 3D view** — loading a model while the Model workspace wasn't visible
  (e.g. a reload that restored the Finance/Drawings workspace, or opening a model from another
  workspace) created the viewer in a 0×0 container, making `camera.aspect` = 0/0 = NaN; the subsequent
  `fitToSphere` baked NaN into the camera position and the viewport showed nothing once you switched
  to Model. Now the fit is **deferred while the viewport is hidden** and run once it has real
  dimensions, the aspect is forced valid synchronously (OBC's ResizeObserver is async), and a
  hard camera reset recovers an already-NaN camera that `setLookAt` alone can't clear.
- **Egress / life-safety now reachable** — the deepened A2 check (occupant load, travel distance,
  required exits, exit separation) was computed but had no UI. `test-fit/compare` now returns the
  plate-level egress result and the Test Fit panel shows a ✅/⚠️ life-safety line with the figures and
  any code flags.
- Found during a full hands-on verification of everything built this session (viewer tools, Studio
  node editor, generate+parking, families/import, deck, lien waivers, COBie, dashboard, 4D) — all
  others confirmed working end-to-end.

## v0.1.39 — accessibility pass (tab semantics, labels, live region)
- **a11y** — the workspace switcher and finance sub-tabs now carry `role="tablist"`/`role="tab"` with
  `aria-selected` kept in sync as you switch (screen readers announce the active view); the role/persona
  picker gained an `aria-label`; and the status bar is a polite `role="status"` live region so status
  updates are announced. Builds on the existing landmarks (`main`/`nav`/`header`/`footer`), `lang`, and
  icon-button `aria-label`s.

## v0.1.38 — Redis rate limiting (multi-worker) + dashboard perf
- **Distributed rate limiter** — set `AEC_REDIS_URL` and the per-IP request limit is now shared across
  workers/processes via an atomic Redis `INCR`+`EXPIRE` (fixed 60s window), so the limit holds under a
  multi-worker deployment instead of being per-process. Fail-open: any Redis error falls back to the
  in-process bucket so limiter infrastructure can never take the API down; redis is imported lazily
  only when the URL is set (no new dependency for the single-worker/desktop build). New `test_ratelimit`
  gate covers the enforcement path (health/metrics exempt, 429 + Retry-After past the limit).
- **Dashboard perf** — the GC dashboard no longer loads and JSON-parses every record across all
  modules. Status tallies now come from a single indexed `GROUP BY workflow_state` per module (zero
  JSON), and the `data` blob is parsed only for the **active** (non-terminal) records that feed
  overdue + action-items — so completed-record-heavy projects build the dashboard far faster. Output
  is byte-for-byte identical (`test_dashboard` unchanged).

## v0.1.37 — COBie field depth (C2) + investment-deck market/timeline slides
- **COBie model-derived field enrichment (C2)** — the handover sheets gain the fields FM teams use:
  Space net/gross **area** + usable height (from Qto), Type **manufacturer / model / warranty /
  expected-life / replacement-cost / color / material**, Component **serial / install-date /
  warranty-start / tag / asset-id**, plus a new **Attribute** sheet that flattens every remaining
  property set (Name/Value/SheetName/RowName) so nothing is lost in handover.
- **Investment deck — Market & Timeline slides** — the pitch deck grows from 4 to 6 slides: a
  **Market & positioning** slide plotting the deal's yield/IRR/soft-cost against conceptual benchmark
  bands, and a **Development timeline** gantt bar (predev → construction → lease-up → stabilization →
  exit, durations from the saved scenario), plus a **site photo** on the cover from project attachments.

## v0.1.36 — printable statutory lien-waiver documents
- **Lien-waiver documents / PDFs** — pay-app accounting, lien-waiver *record tracking* and COBie
  enrichment already shipped earlier; this adds the piece they lacked: the actual **printable
  statutory waiver form**. `cost.lien_waiver` renders the four conditional/unconditional ×
  progress/final forms (Cal. Civ. Code §8132–8138 style) from a pay application — notice, body and
  amount (current payment due for progress, contract sum to date for final) — exposed as
  `GET /projects/{id}/cost/lien-waiver` (JSON) and `.pdf`, plus a "⚖ Lien waiver / release" action in
  the viewer cost panel. Complements the existing `POST /cost/lien-waiver` record-tracking endpoint.

## v0.1.35 — Test Fit depth (egress · parking · polygon footprint · proforma)
- **Deeper egress / life-safety check (A2)** — `test_fit.egress` now screens the big four IBC fails:
  max travel distance, **occupant load** & required **egress width**, minimum **number of exits**, and
  **exit separation** (½ diagonal / ⅓ sprinklered) — with per-check detail + flags (e.g. an assembly
  hall trips ≥4 exits). Back-compatible with the prior keys.
- **Parking as real IFC geometry** — `generate(..., parking=N)` lays out a surface lot of `N`
  IfcSpace `PARKING` stalls (2.5×5 m + drive aisles) on a dedicated *Site Parking* storey, each with
  area QTOs. Exposed on the generate API + a "Surface parking stalls" field in the proforma form.
- **True polygon-offset footprint** — for `lot_polygon` parcels the buildable footprint is now a real
  inward setback (`offset_polygon`, handles reflex vertices + over-collapse), surfaced as
  `buildable_polygon`, instead of a bounding-box approximation.
- **Optimize tied to the proforma** — the generative sweep's yield-on-cost + new **development
  spread** (bps vs exit cap) come from the canonical `proforma.returns` functions (with stabilized
  occupancy), so the quick screen matches the full underwriting; you can rank by `dev_spread_bps`.

## v0.1.34 — import external IFC families (M3) + visual node editor (M4 complete)
- **Import IFC type content** — bring manufacturer / 3rd-party families into a project from any IFC:
  `families.import_types_from_ifc` copies every IfcTypeProduct (with geometry) in via
  `project.append_asset` (deduped, idempotent), then they're placeable like the built-in catalog.
  New endpoint `POST /projects/{id}/families/import` + *"⇪ Import IFC families…"* in the authoring
  panel. Completes M3.
- **Studio — visual computational graph (M4)** — a new **Studio** workspace renders the Dynamo/
  Hypar-style compute engine as a node editor: drag node types from a palette, wire output→input
  ports (click-to-connect, SVG bezier edges), edit params inline, and **Run** to execute the graph
  server-side in dependency order with values flowing through the wires (zoning → cost → yield, etc.).
  Graph persists locally; shown for developer/architect/engineer personas. Completes M4 — the whole
  **M-theme (M1–M4) is now done**.

## v0.1.33 — material layer sets + family library (M3)
- **Layered construction assemblies** — generated models now carry real **IfcMaterialLayerSet**
  data on walls, slabs and roofs (e.g. exterior wall = brick · cavity · insulation · CMU · gypsum),
  the way Revit's compound structures work — attached via IfcMaterialLayerSetUsage and chosen from
  `IsExternal` / slab type. Feeds take-off, U-value and schedules.
- **Expanded parametric family library** — the placeable catalog grows from 16 to 37 entries across
  new **Lighting**, **MEP** (AHU, fan-coil, diffuser, electrical panel), **Structural** (steel
  column/beam) and **Transport** categories, plus more furniture/sanitary/appliances. Families are
  now **parametric**: pass `dims` to place a distinctly-named, correctly-sized **type variant**
  (Revit-style type families). New element classes get palette colours too.

## v0.1.32 — first-person walkthrough (M2 complete)
- **Walkthrough mode** (🚶 toolbar) — Matterport-style first-person navigation: drops to eye height
  (1.6 m), **W/A/S/D** to walk (locked horizontal so you stay on the floor) and drag to look around.
  Switches to a perspective view on enter and restores your prior camera on exit. Completes M2.

## v0.1.31 — sun & shadow study (M2)
- **Sun / shadow study** (☀ toolbar) — drive the render-mode sun by **date, time-of-day and
  latitude/longitude** with a live panel; shadows track the real solar arc (NOAA solar-position
  math), with warm low-angle light and a below-horizon night state. Opening it auto-enables render
  mode. Pure solar math is unit-tested.

## v0.1.30 — PBR materials + free Revit import
- **PBR pass (M2)** — render mode now upgrades plain lit surfaces to `MeshStandardMaterial`
  (roughness/metalness, keeps the M1 IFC colours) lit by an **IBL studio environment** for soft
  ambient + reflections, on top of the sun/shadows. Reversible; Fragments' own shader meshes are
  left untouched so the engine renderer is never at risk.
- **Free Revit → IFC path** — the Open menu now has *"Free: export IFC from Revit (no bridge)…"*:
  a guide to Revit's built-in IFC export + the free, open-source **pyRevit**, so getting a model in
  doesn't require the paid Autodesk bridge.
- **Docs** — library interoperability evaluation (roadmap §L: IFClite, pyRevit, FreeCAD, Pascal
  Editor) and ADR 0001 on dependency bundling & the signed-update policy (deps are pinned and ship
  inside the app update — never background-updated independently).

## v0.1.29 — render mode (M2 start)
- **Viewer render mode** (◓ toolbar) — a directional **sun with soft (PCF) shadows**, hemisphere
  sky/ground fill + fill light, **ACES tone mapping** and sRGB output, and a shadow-catching ground
  plane. Off by default (flat shading stays the cheap default); re-applies as new models load.
  First step toward Revit/Rhino/Matterport-style rendering.

## v0.1.28 — faster large-model loading
- **Download progress** — large models stream with a live "downloading N% (x/y MB) → preparing
  geometry" label instead of a generic spinner that looked frozen.
- **ETag revalidation** — `model.frag` now serves an ETag + `must-revalidate`: unchanged models
  re-open instantly via **304**, while a republished/edited model is always refetched (fixes a
  stale-cache bug where an immutable 1-year cache served the old geometry forever).

## v0.1.27 — computational graph (M4 start)
- **Dynamo-style node graph** over the pure engines: `GET /compute/nodes` (palette) and
  `POST /compute/graph` run a {nodes, edges} graph in dependency order (zoning → structure / takt /
  cost → yield-on-cost). Zero-touch: function params become input ports, dict returns become outputs.

## v0.1.26 — IFC materials & surface colours (M1 start)
- **Materials & surface styles** — generated/dome models get an IfcMaterial + IfcSurfaceStyle colour
  per element class (concrete, glazing, steel, vegetation…), so models carry real material data.

## v0.1.25 — gamified getting-started
- **Getting-started checklist** — a floating progress pill guides new users through the 6 core
  actions (load a model, generate, test-fit, budget, project, memo) with a progress bar + celebration.

## v0.1.22 — 4D & the vertical assembly line
- **4D construction sequencing** — map model elements onto a takt plan; **scrub the build sequence
  in the viewer** (a slider isolates what's built to date).
- **Takt / line-of-balance chart** (SVG) and an **egress check** (two means + travel distance).

## v0.1.21 — lean & multi-period billing
- **Lean / Last-Planner PPC** — a weekly-plan module + Plan-Percent-Complete analytics with reasons
  for non-completion.
- **Multi-period pay apps** — roll completed-to-date across successive draws; retainage release on
  the final application.

## v0.1.20 — underwriting realism (II)
- **Capital reserves above NOI**, **citable guardrail bands** (sourced from the benchmarks), and
  **Test Fit optimize seeded from the live project** (real land + cost budget).

## v0.1.19 — built-world techniques (Willis · Salvadori · CM/RE research)
- **Takt / line-of-balance** scheduling with a just-in-time delivery plan (R2).
- **Lean PPC** engine (R4) and citable **benchmarks + a comparables module** (R5).

## v0.1.18 — structural-system advisor (R3)
- Pick a plausible system by height/span (flat-plate · shear-core · outrigger) with rough member
  sizing + a load-path read — driving the generated frame (after Salvadori).

## v0.1.17 — form follows finance (R1)
- Generative massing / Test Fit reward **daylight-limited rentable depth** + core efficiency — the
  highest rentable yield wins, not max FAR (after Carol Willis).

## v0.1.16 — underwriting realism (I) + Finance revamp
- **Risk-adjusted** specialty/operating revenue + **guardrails** that flag returns outside market
  bands. Finance reorganized into sub-tabs with a sticky live-returns bar.

## v0.1.15 — pitch deck
- One-click **pitch-deck PDF** variant of the investment memo (B6).

## v0.1.14 — generative optimize + real parcels
- **Generative design** sweeps unit-mix × parking and ranks by yield-on-cost (A5); **real lot
  polygons** drive the program by shoelace area (A6).

## v0.1.13 — Test Fit + property/tax
- **Test Fit** — corridor unit-mix layout, parking solver, scheme compare (A1/A3/A4); **property &
  tax assumptions** feeding OPEX (B3).

## v0.1.11 — specialty assets
- On-site **energy** (solar/wind/battery/rainwater) and **vertical-farm (PFAL)** revenue flow into
  capex / revenue / opex (B4).

## v0.1.10 — developer cost portal
- Line-item **hard/soft cost budgets** (B1), **Sources & Uses** (B2), and a one-click **investment
  memo PDF** (B5).

## v0.1.6–0.1.8 — accounts, AI & hardening
- **SSO** (Google / Microsoft / Procore) + a no-admin free-tier model; first-run **onboarding + tour**.
- **"Ask AI"** project assistant over a live snapshot; AI risk summaries + drafted RFIs.
- **Field capture** (offline photo → punchlist/observation, syncs on reconnect).
- Production hardening — rate limiting, security headers, auth-secret fail-safe, takeoff caching.
- Full generative lifecycle from zoning (frame + units + envelope + core).

## v0.1.0–0.1.5 — foundation
- **BIM viewer** (Three.js + Fragments, offline WASM), federation, clash, IDS, 2D drawings/sheets,
  in-viewer authoring round-trip.
- **GC portal** — config-driven modules (RFIs, submittals, change-order chain, daily, QA, safety…),
  CPM, pay apps, dashboards.
- **Development proforma** — S&U with interest-reserve circularity, XIRR/NPV/EM, JV waterfall,
  sensitivity + Monte Carlo.
- **Generative massing + family library**; free single-project **desktop app** with signed,
  auto-updating releases.

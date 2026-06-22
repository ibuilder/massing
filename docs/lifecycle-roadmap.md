# Full-lifecycle roadmap — concrete residential tower, acquisition → turnover

This doc is the output of an end-to-end drive (`services/api/e2e_tower.py`) that takes one project —
a concrete-superstructure residential tower ("Maple Street Tower") — through **every** phase of the
platform and records what works and what's missing. It's both a regression harness and the punch
list for finishing the start-to-finish story.

Run it against a live API: `python services/api/e2e_tower.py`. It prints PASS/FAIL per step and the
final source-IFC path; the deliverable model is saved to `samples/maple_tower.ifc`.

## What works today (verified end-to-end)
The whole chain runs green — one project, one GUID-stable IFC, from a zoning envelope to a completion
certificate:

| Phase | Proven in the E2E |
|---|---|
| **0 · Acquisition / feasibility** | Zoning envelope → generative massing → **IFC model** (8 floors, 55 units) + acquisition **proforma** scenario (S&U, IRR, waterfall). |
| **1 · Design** | Authored a real **concrete superstructure** onto the massing — 12 columns, 12 beams, 3 core shear walls — plus a **unit fit-out** (fridge/range/dishwasher/sink + sofa/table/bed), concrete material tag, published (reconvert + reindex). Metre-scale, GUID-stable, renders in the viewer. |
| **2 · Preconstruction** | Model **takeoff → estimate**, **cost codes + budget + commitments**, **bid package → submissions → leveling → award**, **CPM schedule** (critical path). |
| **3 · Construction** | **RFI** (submit→respond), **submittal**, full **change chain** (change event → PCO → COR submit→approve→execute), **daily report + manpower**, **inspection** (fail → NCR), **safety incident**, **SOV → G703/G702 pay app**, dashboard, AI ask. |
| **4 · Turnover / closeout** | **Punchlist** (open→ready→**evidence-gated** verify), **commissioning** (test→accept), **O&M manual**, **warranty**, **as-built**, **asset register**, **completion certificate** (issue→accept), **COBie / QTO / space-schedule** exports, **status report PDF**. |

## Bugs fixed while driving it
- **Authoring path-length blow-up (Windows).** Each `/edit` derived the new IFC filename from the
  *previous* versioned name, so chained edits compounded the stem (`source_<ts>_<ts>_…ifc`) until it
  passed the 260-char limit and the write failed. Now each version is named off the original stem +
  a microsecond stamp. *(This blocked any multi-edit authoring session — the single most important
  fix here.)*
- **web-ifc invisibility across all authoring recipes.** `IfcRectangleProfileDef` was created without
  a `Position`; ifcopenshell tolerates that but web-ifc silently skips the element, so authored
  walls/columns/beams/openings rendered invisible. Centralized a `_rect_profile()` helper that always
  sets the placement (same fix already applied to massing + families).
- (Earlier in the session: massing built in millimetres → 1000× too small; demo seed aborting on
  missing required fields.)

## Gaps to build out (prioritized) — to finish "start to finish for real"

### A. Design / modeling depth (biggest gap)
The generated model is **massing-grade** (floor-plate spaces + slabs) plus whatever you author by
hand. To carry a *real* tower to turnover it needs to be generated, not hand-placed:
1. ✅ **DONE — Generative structural framing.** `generate_ifc(frame=True, bay=…)` auto-frames every
   floor on a ~bay-metre column grid: columns at each grid intersection + beams along both axes,
   GUID-stable and metre-scale. Exposed via the generate endpoint (`frame`, `bay_m`) and a
   "Generate concrete structural frame" checkbox in the massing form — massing → structural model in
   one click. Verified (test_massing: 175 columns + 290 beams on a 7×5 grid) and visually (a framed
   tower renders columns/beams/slabs across all floors). *Next: size members from spans, two-way
   slab bands, and a proper core (stairs/elevator shafts) instead of a single shear wall.*
2. ✅ **DONE — Unit-layout generator.** `generate_ifc(units=True)` subdivides each floor into the
   proforma's per-floor unit count — a grid of per-apartment `IfcSpace`s, each with a real
   `Qto_SpaceBaseQuantities.NetFloorArea` and `Pset_SpaceCommon.Reference="UNIT"`, so areas / COBie /
   rent are grounded in actual apartments instead of one plate-sized space. Endpoint `units` flag +
   a "Subdivide floors into units" checkbox. Verified (test_massing: 65 unit spaces, 13/floor × 5
   floors, each with area). *Next: a real double-loaded corridor + core carve-out, and a unit-mix
   (studio/1BR/2BR) instead of uniform cells.*
3. ✅ **DONE — Envelope.** `generate_ifc(envelope=True, wwr=…)` wraps each floor in perimeter
   facade `IfcWall`s (IsExternal) + ribbon `IfcWindow`s at the window-to-wall ratio. The energy model
   reads the real exterior-wall + glazing areas (UA, EUI, WWR) and elevations show an enclosure.
   Endpoint `envelope`/`wwr` + a "Wrap in facade + windows" checkbox. Verified (test_massing: 20
   walls + 20 windows; energy WWR 0.36, UA 6318 W/K) and visually (the developed tower renders facade
   + ribbon windows). *Next: real curtain-wall mullions, punched vs. ribbon options, spandrel/shading.*
4. ✅ **DONE — Core & MEP stubs.** `generate_ifc(core=True)` adds a service core per floor — core
   walls + an `IfcTransportElement` (ELEVATOR) + an `IfcStair` + `IfcDuctSegment`/`IfcPipeSegment`
   risers — so coordination/clash and MEP counts have real elements. Endpoint `core` flag + an "Add
   service core" checkbox. Verified (test_massing: elevator/stair + duct/pipe risers + core walls per
   floor). *Next: connect risers floor-to-floor, add equipment (AHU/pumps), and zone the core.*

### B. Estimating realism ✅ DONE
- **Assembly-based concrete takeoff.** The estimate now bills the superstructure by **volume**
  (columns/beams/slabs × $/m³ in place), and `takeoff(force_geometry=True)` computes real area+volume
  from geometry for every billable element (no cost map or Qto psets needed). On a framed tower the
  model estimate jumped from a misleading **$5,400** (12 columns × count) to **~$906k** of actual
  concrete (slabs/beams/columns).
- **GFA benchmark + recommended source.** `estimate_from_takeoff(gfa_sf=…)` also returns a GFA × $/sf
  benchmark and a `recommended` source ("model" vs "gfa") + `recommended_total`, so a sparse model
  surfaces the honest underwriting number instead of a misleadingly tiny total. Verified live
  (276 elements → $906k model takeoff, $8.0M GFA benchmark, recommends gfa). *Next: formwork m² +
  rebar tonnes line items; finishes/MEP assemblies; per-CSI rollup into the budget module.*

### C. Construction depth
- ✅ **DONE — Logs to PDF.** `GET /projects/{id}/modules/{key}/log.pdf` renders any module as a
  printable register (RFI log, submittal log, change-order log, …) from the same engine —
  ref/title/status/assignee. Verified (test_closeout).
- ✅ **DONE — Multi-period pay apps + auto lien waivers.** `POST /cost/pay-app/advance` closes a
  period (rolls each SOV line's `completed_this` → `completed_prev`, zeroes this) so the next
  G702/G703 application shows prior work as previous certificates; `POST /cost/lien-waiver` generates
  a lien-waiver record for the current pay app (amount = G702 current payment due). Verified
  (test_closeout: $237,500 waiver, advance rolls this→prev).
- **Field/mobile capture** *(remaining — separate app effort)* — photo → daily report / punchlist with
  offline support (the Capacitor scaffold exists). Where GC adoption is won.

### D. Turnover completeness
- ✅ **DONE — Final completion package.** `GET /projects/{id}/closeout/package.zip` bundles the
  as-built IFC, COBie / QTO / space-schedule workbooks, the status-report PDF, and a JSON manifest of
  the closeout records (commissioning, O&M, warranties, as-builts, asset register, completion
  certificate, punchlist). Verified (test_closeout: ZIP contents + manifest).
- ✅ **DONE — COBie field enrichment.** The COBie export (and the closeout package) now fold the
  closeout records into the workbook as **Warranty / System (commissioning) / Asset (asset register) /
  Document (O&M)** tabs alongside the model-derived Facility/Space/Type/Component sheets. Verified
  (test_closeout: tabs present).
- ✅ **DONE — Warranty expiry tracking.** `GET /projects/{id}/warranties/expiring?within_days=N`
  returns warranties expiring within the window + any already expired (with `days_left`), reading the
  `expires` date — so warranties don't lapse silently. Verified (test_closeout: expiring + expired).

### E. Cross-cutting consistency ✅ DONE
- ✅ **`subject` is now a universal title alias.** Modules name their title field differently
  (`title`/`name`/`number`/`system`); `create_record` fills it from `subject` when absent, so
  callers/scripts/integrations don't special-case each module. Verified (subject → om_manual `name`,
  as_built `number`, commissioning `system`).
- ✅ **Safety TRIR/DART auto-derives man-hours.** When `hours` isn't passed, hours = timesheet hours +
  manpower-log (`count`/`headcount` × an 8h shift), so TRIR/DART populate from normal field logging.
  Verified (20-crew log → 160 man-hours → TRIR computed).

## The artifact
The end-to-end run saves the final model to **`samples/maple_tower.ifc`** — IFC4, metre-scale,
GUID-stable: site → building → 8 storeys, each with a floor-plate space + slab; 12 concrete columns,
12 beams and 3 core walls across the framed floors; and a Level-1 unit fit-out (appliances, sanitary,
furniture). It opens in the viewer and round-trips through the converter to Fragments.

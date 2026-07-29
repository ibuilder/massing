# Drawings, schedules and the specification manual

Massing generates a permit-ready construction-document set **from the model**. Drawings are not drawn;
they are derived, which is why they cannot disagree with the building.

## What gets generated

| Artifact | Formats | Endpoint |
| --- | --- | --- |
| Plans, sections, elevations | SVG · PDF · DXF (R12) | `/drawings/{plan,section,elevation}.{svg,dxf}` |
| Issuable sheet (ARCH-D, border + titleblock) | SVG · PDF | `/drawings/sheet.{svg,pdf}` |
| Door / window / room schedules | SVG · PDF | `/drawings/schedules`, `/drawings/schedule.{svg,pdf}` |
| 3-part MasterFormat project manual | TXT | `/spec/manual[.txt]` |

Drawings derive from **extruded-profile geometry**, not from an OCC section of the mesh. That is a
deliberate choice: profile extrusion gives clean, dimensionable linework where a mesh section gives
you an outline that looks right and measures wrong.

## The dimensioned plan

The structural grid is derived **from column positions** — no `IfcGrid` entity required, because most
real models do not have one. The plan then adds numbered and lettered grid bubbles and grid-spacing
dimensions automatically.

Elevations use hidden-line removal. Room tags come from `IfcSpace`, so a model without spaces produces
a plan without room tags rather than a plan with invented ones.

## Sheets and the drawing set

A sheet composes per-storey plans and a section under a title block, and issues as PDF. Per-discipline
sets follow the **NCS** sheet-type convention — and fire alarm (FA) is generated as a distinct
discipline from fire protection (FP), because they are distinct disciplines with distinct reviewers.

The **controlled drawing set** (`/drawing-set`) tracks current versus superseded revisions, so "which
drawing is current" has one answer.

## Specifications

The project manual generates as a **3-part MasterFormat** spec book. The specification register then
drives a **spec-driven submittal log**: typed submittals are extracted from the spec book by rules and
AI, and coverage reporting names the submittals that are *missing*.

That direction matters — the submittal log is derived from the specs rather than re-keyed beside them,
so the two cannot drift.

## Code intelligence

| Check | What it produces |
| --- | --- |
| Code analysis (G-series) | IBC code-analysis summary sheet |
| Occupancy + egress | Edition-aware occupancy load and egress capacity, IBC-cited |
| Jurisdiction editions | Which code edition a jurisdiction has actually adopted (facts only) |
| Approvability pre-flight | Permit-readiness before you submit |
| Detail rules | A detail-rule engine plus per-element codes and documentation |
| Decision readiness | Ranked gaps that will become RFIs if you issue as-is |

Jurisdiction adoptions are **facts only** — the platform reports which edition a jurisdiction adopted,
and does not infer or interpolate one it has no record of.

## 2D takeoff and markup

The 2D editor is a first-class part of the product, not a preview: **calibrated PDF takeoff** — measure,
area and count — with markup that flattens into the PDF on export.

Both editors are standard: the 3D authoring editor and the 2D takeoff/markup editor. Reuse both rather
than treating 2D as a fallback.

## Quantities and cost

Quantity takeoff feeds the 5D chain: `POST /cost/estimate` prices the model through the selector spine,
and `POST /cost/sov` builds a schedule of values **from that estimate** rather than re-keying it.
`POST /estimate/diff` diffs two estimates by GlobalId with every delta attributed.

> **One caution when reading areas.** Surface area from a mesh is the whole **skin**. Price the
> *measured* area for the trade in question — a naive mesh-area call doubles every area line, and it is
> the kind of error that only shows up in your own output, so no import ever catches it.

## Exports

`/exports/{qto,cobie,spaces,schedule}.xlsx` — quantity takeoff, COBie, space schedule, activity
schedule. COBie carries Contact, Zone and System, which is what makes the handover chain into a CMMS
work.

Everything is also available from the CLI:

```bash
cd services/data
PYTHONPATH=src python -m aec_data.cli qto model.ifc qto.xlsx
```

## Related

- [reference/api.md](../reference/api.md) — the full endpoint list.
- [authoring.md](authoring.md) — making the model the drawings come from.
- [engineering/calculation-precision.md](../engineering/calculation-precision.md) — rounding and
  tolerance rules for anything numeric.

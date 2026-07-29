# API reference

**The authoritative reference is `/docs` on a running instance** — FastAPI generates it from the code, so
it cannot be stale. This page is the map: what exists, grouped by what you are trying to do.

66 routers. The selection below is the significant surface, not the complete one.

## Conventions

- Everything project-scoped lives under `/projects/{id}/…`.
- Elements are addressed by **IFC GlobalId**, never by a viewer id.
- Every `/projects/{pid}/…` route is role-guarded. RBAC is on when `AEC_RBAC=1`.
- Module **create** wraps its payload (`{"data": {…}}`); module **update** takes the field map directly.

## Projects and elements

```
POST   /projects                              create (name, source_ifc, origin)
DELETE /projects/{id}                         delete rows + geometry + attachments
GET    /projects/{id}/elements[/{guid}]       properties index
GET    /projects/{id}/query                   power selection (IfcOpenShell selector DSL)
GET    /projects/{id}/bundle                  portable .mmproj save
POST   /projects/import-bundle                …and open
```

## Authoring

```
POST   /projects/{id}/edit                    apply a recipe (add_family, set_wall_slope,
                                                add_mesh_representation, place_content, connect_mep, …)
POST   /projects/{id}/publish                 write the edited IFC back
POST   /projects/{id}/edit/precheck           guardrail — reject broken IFC before writing
POST   /projects/{id}/edit/{undo,redo}        model undo / redo (versioned, GUID-stable)
GET    /projects/{id}/edit/history            edit history
POST   /projects/{id}/ai/author               natural-language authoring → validated plan
GET    /authoring/capabilities                sandboxed execute_ifc_code probe (off unless flagged)
GET    /reference/authoring-matrix            recipe coverage matrix
```

## Generation

```
POST   /projects/{id}/generate/massing        zoning → IFC massing + acquisition proforma
POST   /generate/massing/preview              stateless: program + proforma, no model written
GET    /families/catalog                      starter IFC family library
GET    /content/catalog                       site content (logistics / furniture / landscaping)
```

## Drawings, schedules and specs

```
GET    /projects/{id}/drawings/{plan,section,elevation}.{svg,dxf}
GET    /projects/{id}/drawings/sheet.{svg,pdf}        issuable ARCH-D sheet (border + titleblock)
GET    /projects/{id}/drawings/schedules              computed door / window / room schedules
GET    /projects/{id}/drawings/schedule.{svg,pdf}
GET    /projects/{id}/spec/manual[.txt]               3-part MasterFormat project manual
GET    /projects/{id}/drawing-set                     controlled set (current vs superseded)
```

## Quality, standards and code

```
POST   /projects/{id}/clash                   clash detection → BCF clash topics
POST   /projects/{id}/validate                IDS validation
GET    /projects/{id}/lod                     LOD-stage distribution
GET    /projects/{id}/lod500                  LOD-500 field-verified as-built readiness
GET    /projects/{id}/codecheck/{analysis,occupancy,approvability}
                                              IBC code analysis · edition-aware egress · permit readiness
GET    /projects/{id}/rfi/readiness           decision-readiness audit — ranked gaps
GET    /projects/{id}/mep/connectivity        port connectivity + dangling-element report
GET    /projects/{id}/detailing/{guid}        element codes + documentation
GET    /projects/{id}/detailing/rules/validate detail-rule QA
GET    /codes/{families,adoptions,seeded}      jurisdiction-adopted code editions (facts only)
GET    /projects/{id}/verification/coverage   install coverage (verified/installed %)
PUT    /projects/{id}/verification/{guid}     record a field verification
GET    /projects/{id}/verification/deviations  as-built variance
```

## Issues (BCF)

```
GET/POST /projects/{id}/topics …              topics/RFIs/pins, comments, viewpoints, attachments
GET      /projects/{id}/bcf/export            .bcfzip out
POST     /projects/{id}/bcf/import            .bcfzip in
GET      /projects/{id}/module-pins           anchored records → viewer overlay
```

## Cost (5D)

```
POST   /projects/{id}/cost/estimate           price the model through the selector spine
POST   /projects/{id}/cost/sov                schedule of values built FROM that estimate
POST   /projects/{id}/estimate/diff           two estimates diffed by GlobalId, deltas attributed
GET    /estimate/labor/rates                  productivity rates
GET    /projects/{id}/estimate/labor          man-hours → labour cost + crew-days
GET    /projects/{id}/cost/{g703,g702,summary} financials (+ g702.pdf)
POST   /projects/{id}/cost/tm                 T&M ticket
GET    /projects/{id}/payroll[/wh347.pdf]     weekly certified payroll from timesheets
GET    /projects/{id}/elements/{guid}/5d      one element's cost-code budget + schedule activity
GET    /projects/{id}/elements/{guid}/lifecycle the six-state strip behind the Inspector
```

## Schedule

```
GET    /projects/{id}/schedule/{gantt,lob}.svg      Gantt + Line of Balance
GET    /projects/{id}/schedule/cpm                  critical path
GET    /projects/{id}/schedule/alerts               predictive alerts
GET    /projects/{id}/schedule/optimize             acceleration advisory
GET    /projects/{id}/risk-digest                   cost + schedule + open items + safety
```

## Modules (the GC portal)

```
GET    /modules                                     module catalog (an allowlist — see below)
GET/POST /projects/{id}/modules/{key}[/{rid}]       config-driven CRUD
POST   .../{rid}/{transition,link}                  workflow · relate
GET    .../{rid}/{comments,pdf}                     thread · render
GET    .../export.csv                               export the register
GET    /projects/{id}/dashboard                     role-tailored rollup
GET    /projects/{id}/due-feed                      cross-module due/overdue SLA feed
GET    /reports                                     Report Center catalog
GET    /projects/{id}/reports/{report}.{pdf,xlsx}   incl. appraisal · listing_factsheet
```

> `GET /modules` is an **allowlist** and silently drops keys it does not know. A new `module.json` key
> that appears to lose data is usually being filtered here.

## Real estate and operations

```
GET/POST /projects/{id}/appraisal             tri-approach valuation (cost · income · sales-comparison)
GET    /projects/{id}/listings/autofill       listing fields from the model + proforma
GET    /projects/{id}/listings/{lid}/reso     RESO Data Dictionary export
POST   /projects/{id}/listings/{lid}/share    signed read-only public link (QR share)
GET    /projects/{id}/listings/{lid}/public   the public view
GET    /projects/{id}/rent-roll               occupancy / WALT
GET    /projects/{id}/cap-table               investor cap table
POST   /projects/{id}/capital-call            pro-rata investor allocation
POST   /projects/{id}/distribution
GET    /projects/{id}/bidding/itb             ITB coverage tracking
POST   /projects/{id}/bidding/packages/{id}/invite
```

## Exports

```
GET    /projects/{id}/exports/{qto,cobie,spaces,schedule}.xlsx
```

## Interoperability

```
GET/POST /connections[/{id}]                  data sources (Postgres/Supabase/Procore/ACC)
GET    /connections/{id}/tables               read-only browse
POST   /connections/{id}/query                read-only SELECT
GET/PUT /connections/{id}/mappings            external field → module field mapping
POST   /projects/{id}/sync/procore[/push]     import + two-way push
POST   /projects/{id}/sync/schedules
GET    /connections/{id}/acc/projects/{pid}/issues   Autodesk Construction Cloud issue read
GET    /opendata/permit-cities                municipal permit feeds available
GET    /projects/{id}/opendata/permits[.geojson]
POST   /projects/{id}/opendata/permits/import seed the permit log from a city's open data
```

## Q&A and AI

```
POST   /projects/{id}/ask                     Q&A over the model index
POST   /projects/{id}/assistant               over the whole project (modules/schedule/budget)
GET    /rooms                                 the room allocation (section→room derived)
GET    /health                                liveness — a 000 means the process is down
```

MCP access for external agents is documented in [mcp.md](../mcp.md), with a drop-in skill pack in
[mcp-skills/](../mcp-skills/). Agents drive the same gated engines the UI uses; nothing is fabricated.

## Related

- [architecture.md](architecture.md) — what sits behind these routes.
- [modules.md](../user-guide/modules.md) — the record model in practice.
- [authoring-matrix.md](../authoring-matrix.md) — every recipe, generated from `edit.RECIPES`.

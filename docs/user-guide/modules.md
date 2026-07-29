# Records and registers

A **module** is a record type: RFIs, submittals, change orders, pay applications, punch items, leases,
work orders — anything with a form, a list and a workflow. There are **133** of them, and each is one
folder of plain JSON. No code.

## How a module works

Each module is `services/api/modules/<key>/module.json`, defining its fields, its list columns, and its
workflow states. The API then serves generic CRUD for it:

```
GET    /modules                                    the catalog
GET    /projects/{id}/modules/{key}                list records
POST   /projects/{id}/modules/{key}                create
GET    /projects/{id}/modules/{key}/{rid}          read one
PATCH  /projects/{id}/modules/{key}/{rid}          update
POST   .../{rid}/transition                        advance the workflow
POST   .../{rid}/link                              relate to another record
GET    .../{rid}/comments                          discussion thread
GET    .../{rid}/pdf                               render the record
GET    .../export.csv                              export the register
```

Two shapes catch people out:

- **Creating** a record wraps the field map: `POST` body is `{"data": {…}}`.
- **Updating** takes the field map **directly**: `PATCH` body is the fields themselves.

## Records are anchored to the model

A record can be anchored to an IFC element by **GlobalId**. `GET /projects/{id}/module-pins` returns
anchored records as a viewer overlay, so an RFI about a specific beam appears *on* that beam — and stays
on it after the model is edited, because the anchor is a GUID and not a coordinate.

This is the payoff of the one-model design: the RFI, the cost line, the schedule activity and the
element are all the same identity.

## Finding things

- **⌘K** — any module by name.
- **Its room** — see [rooms.md](rooms.md).
- **The work queue** — ball-in-court items across every module, which is the honest answer to "what do
  I owe someone".
- **`/due-feed`** — cross-module due and overdue SLA feed.
- **`/dashboard`** — role-tailored rollup.
- Search filters run **in SQL**, not in the browser, so they work on a register with real volume.

## Importing

Generic Excel/CSV import exists for every module — see `imports.py`. For connected systems there are
data-source connections (Postgres/Supabase/Procore/ACC) with an admin field-mapping editor that maps
external fields onto module fields, plus two-way Procore sync.

## The registers, by area

Grouped by the room they live in. This is a map, not the catalog — `GET /modules` is authoritative.

| Room | Registers include |
| --- | --- |
| **Deal** | Due-diligence studies, entitlement pipeline, market comps, land/site search, portfolio, ESG, investor cap table, capital calls and distributions |
| **Design** | Specification register, documents, materials, standards compliance, model QA, issues/topics, information requirements (EIR/BEP/AIR), space program, responsibility matrix |
| **Planning** | Takeoff, estimates, benchmarks, bid packages and ITB coverage, buyout, contracts, selections, approvals, risk review |
| **Schedule** | CPM activities, resource loading, equipment, daily reports, weather delays, turnover, pull-plan / Last Planner board |
| **Cost** | Budget, cost codes, change orders, pay applications (G702/G703), T&M tickets, WIP, earned value, ledger, certified payroll (WH-347) |
| **Work** | The queue itself — not a register |
| **Operate** | CMMS work orders, preventive maintenance, asset register, facility condition assessment, utility meters, reserve study and capital plan, CAM reconciliation, post-occupancy evaluation |

## Documents and reporting

**Contract and change-order documents** generate in AIA-style, with Exhibit A scope, redlining, and
per-party e-signature including **PAdES** digital signatures. Professional **stamps and seals** (PE/RA)
apply both visibly and as a PAdES signature.

The **Report Center** (`GET /reports`, `/reports/{report}.{pdf,xlsx}`) covers executive, cost, EVM and
log reports as PDF and Excel — including appraisal and listing factsheets.

## Adding your own record type

You do not need to write code. [authoring-modules.md](../authoring-modules.md) is the full guide. Three
things to know before you start:

1. **A new `module.json` creates its table (`mod_<key>`) at runtime**, but a new table still needs an
   **Alembic autogenerate revision** committed — and keep the Postgres FTS GIN index tail. Skipping this
   works locally and fails on a fresh deploy.
2. **Fields in the same fieldset must stay adjacent** in the field list, or the form renders them apart.
3. **`GET /modules` is an allowlist** — it silently drops keys it does not know. If you add a new key to
   the schema and your module looks like it lost data, check there first.

The module schema itself is defined once, in `module_schema.py`.

## Related

- [authoring-modules.md](../authoring-modules.md) — the how-to.
- [roles-views.md](../roles-views.md) — the rule for deciding which room a new module belongs in.
- [reference/api.md](../reference/api.md) — endpoint reference.

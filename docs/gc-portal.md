# General Contracting Portal

A construction-management portal layered on the BIM platform — connecting GC, owner, owner's
rep, consultants and subcontractors, digitizing the **change-order process end to end**, and
**pinning every record to the 3D model**. Modeled on the system in provisional patent
514712205, modernised on FastAPI + the That Open viewer.

## The core idea: one engine, many modules

Every business process (RFIs, Submittals, PCO Requests, Change Orders, Daily Reports, …) is
a **module** described by a single `module.json`, stored in its **own table** (`mod_<key>`,
created automatically). One shared engine gives every module — **with no per-module code** —
CRUD, a role-gated workflow state machine, comments, CSV/PDF export, model pins, and an
activity timeline. Adding a module = dropping a JSON file in `services/api/modules/<key>/`.

```json
// services/api/modules/rfi/module.json (excerpt)
{
  "key": "rfi", "name": "RFIs", "section": "Engineering", "pinnable": true,
  "fields": [ {"name": "subject", "type": "text", "required": true},
              {"name": "answer", "type": "textarea"} ],
  "workflow": {
    "initial": "draft",
    "transitions": [
      {"from": "draft", "to": "open", "action": "submit", "party": ["GC"]},
      {"from": "open", "to": "answered", "action": "respond", "party": ["Consultant"], "requires": ["answer"]},
      {"from": "answered", "to": "closed", "action": "accept", "party": ["GC"]}
    ]
  }
}
```

**139 modules across 37 sections** ship today. The sections span the whole job — Acquisition,
Feasibility, Design Phases, Estimating, Bidding, Contracts, Coordination, Drawings, Quality, Safety,
Progress, Change Management, Closeout, Handover and Operations among them. `GET /modules` is
authoritative; the section→room allocation lives in `rooms.py`. Regenerate/extend via
`services/api/generate_modules.py`.

## Two role dimensions

- **Capability roles** (RBAC): `viewer < reviewer < editor < admin` — gate reads/writes.
- **Party roles** (workflow gates): `GC · Owner · OwnersRep · Consultant · Subcontractor` —
  gate workflow *transitions*. GC/admin pass every gate so the process never stalls.

Enforced when `AEC_RBAC=1`; the caller is identified by `X-User` (swap for your IdP/JWT).
The project creator becomes admin + GC. Set party roles via `POST /projects/{id}/members`.

## Transition field-gating

Workflow transitions can declare `"requires": ["<field>"]` (see the RFI example above): the engine
refuses the transition — and the UI **disables the workflow button** — until those fields are filled.
So an RFI can't move to **Answered** without an answer, a punchlist item can't be **verified** without
its photo, and so on. Field-gating composes with the party-role gate.

## Directory (Company / Contact)

A first-class **directory** ships as two config modules — **Company** and **Contact** — so vendors,
consultants and owners' reps are real records, not free-text strings. Any module field can declare a
`reference` to a directory record (e.g. `subcontract.vendor_company → Company`,
`rfi.assigned_contact → Contact`), giving typeahead lookup, a stable link, and rollups back to the
referenced company/contact.

## Deadlines / SLA feed

`GET /projects/{id}/due-feed` is a **cross-module due/overdue feed**: it scans every due-bearing
module (11 of them — RFIs, submittals, change orders, tasks, inspections, punchlist, …), computes
due/overdue status against each record's due date, and returns one ranked SLA list. A **"Deadlines"**
widget on the portal home surfaces overdue + due-this-week items at a glance.

## Workflow map

Every record view shows an **in-app workflow map** — a state diagram of the module's workflow with
the current state highlighted and the available (party- and field-gated) transitions drawn as edges,
so anyone can see where a record is and what moves it forward.

## Change-order chain (records hand off across modules)

```
PCO Request ─▶ NOC ─▶ Scope/PCO Directive ─▶ Subcontractor Proposal ─▶ COR/AL ─▶ eTicket
   (GC)        (Owner    (GC ▸ Sub)              (Sub ▸ GC reconcile)    (Owner)    (T&M)
            P&P/PO/DNP)
```

Each step is gated by the acting party's role, linked with `POST /modules/{key}/{id}/link`,
and stamped to the activity timeline. **Approved/executed CORs flow into the contract sum**
(G702 line 2) and the revised budget (Cost Summary).

## Financials

- **Project Budget (GMP)** — `GET /projects/{id}/budget/gmp` assembles the Guaranteed Maximum
  Price from direct trade cost codes (by CSI division), executed subcontracts (buyout), GC/GR
  staffing, and overhead / fee / contingency markups off the prime contract. Each line carries
  budget → committed → actual → **forecast (EAC)** → variance, and reconciles to the prime-contract
  value and the developer proforma's hard cost. `GET /budget/cashflow` spreads it to a monthly
  S-curve; `POST /budget/baseline` + `GET /budget/variance` track drift. The SOV can be seeded
  straight from the budget (`POST /cost/sov/from-budget`).
- **G703 Schedule of Values** — computed columns (completed+stored, %, balance, retainage).
- **G702 Pay Application** — the 9-line AIA certificate (+ formatted PDF continuation sheet).
- **Cost Summary** — budget vs committed vs actual vs forecast, projected over/under.
- **5D (cost on the model)** — `GET /elements/{guid}/5d` for a single element; `GET /5d/heatmap?by=cost|progress`
  colors the whole model by spend or % complete.
- **eTicket T&M builder** — line items priced from the project `labor/material/equipment_rate`
  tables, with per-type subtotals and grand total, written back onto the eTicket.

## Schedule visuals

- **Gantt** — `/schedule/gantt.svg` (time bars, %-complete shading, today line).
- **Line of Balance** — `/schedule/lob.svg` (x=time, y=location; one production line per
  task across locations — takt/location-based scheduling).

![gantt](img/gantt.png)
![lob](img/lob.png)

## Role-tailored dashboard

`GET /projects/{id}/dashboard?party=` — per-party KPIs, **"ball-in-your-court"** action
items (records that party can advance right now), per-module status counts, and a cost
snapshot. The web Portal lands on this dashboard.

## Model pins (the BIM integration)

Any record with a 3D anchor + element GUID(s) is **pinnable**: `GET /module-pins` feeds the
viewer overlay, so RFIs, PCOs, CORs, punchlist, inspections, NCRs, coordination issues, etc.
appear as markers on the model. Clicking a pin selects the referenced element and opens the
record — the same GUID keys geometry, BCF, and GC records.

## API surface (GC portal)

```
GET    /modules                                   module catalog (drives the dynamic UI)
GET/POST /projects/{id}/modules/{key}             list / create records
GET    /projects/{id}/modules/{key}/export.csv    CSV export
GET/PATCH /projects/{id}/modules/{key}/{rid}      record view / update
POST   /projects/{id}/modules/{key}/{rid}/transition   workflow action (party-gated)
POST   /projects/{id}/modules/{key}/{rid}/link         link records (change-order chain)
POST   /projects/{id}/modules/{key}/{rid}/comments     comment
GET    /projects/{id}/modules/{key}/{rid}/pdf          record PDF
GET    /projects/{id}/module-pins                 anchored records → viewer overlay
POST   /projects/{id}/members                     assign capability + party role
GET    /projects/{id}/cost/{g703,g702,summary}    financials (+ /cost/g702.pdf)
POST   /projects/{id}/cost/tm                      eTicket T&M pricing from rate tables
GET    /projects/{id}/budget/{gmp,cashflow,variance}   GMP budget, S-curve, baseline variance
POST   /projects/{id}/budget/baseline             snapshot the GMP as the baseline
POST   /projects/{id}/cost/sov/from-budget        seed the owner SOV from budget lines
GET    /projects/{id}/elements/{guid}/5d          per-element 5D (cost + progress)
GET    /projects/{id}/5d/heatmap?by=cost|progress model heatmap (cost or % complete)
GET    /projects/{id}/schedule/{gantt,lob}.svg    schedule visuals
GET    /projects/{id}/dashboard                    role-tailored dashboard
GET    /projects/{id}/due-feed                     cross-module due/overdue SLA feed
GET/POST /projects/{id}/appraisal                  tri-approach appraisal (cost/income/sales-comp)
```

## Verified

`test_modules.py` (engine, party-gated workflow, change-order chain, pins, comments,
CSV/PDF), `test_cost.py` (G702/G703 + T&M), `test_dashboard.py` (role tailoring),
`test_workflow_gate.py` (transition field-gating), `test_due_feed.py` (cross-module SLA feed),
`test_directory.py` (Company/Contact + reference lookups). The web
Portal renders the dashboard, module catalog, forms (incl. signature pads), records with
workflow buttons, and the pins on the model.

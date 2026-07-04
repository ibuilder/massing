# Roles → Views: where every tool lives, and why

The platform is organised by the **real-estate project lifecycle**, and each top-level workspace is the
home of the role that owns that phase. This is the source-of-truth map used to decide where a tool
belongs. A register can belong to **more than one** workspace (its `workspace` field is a
`|`-separated list) when the workflow genuinely spans roles — e.g. an RFI is raised by the GC and
answered by the architect/engineer, so it lives in both Construction and Design.

## Lifecycle roles → workspace

| Role (real-estate lifecycle) | Home workspace | Also sees |
|---|---|---|
| Owner / Developer | **Developer** | Finance, Design, Construction, Model |
| Lender / Investor / Underwriter | **Finance** (proforma) | Developer |
| Architect | **Design** | Model, Studio, Drawings, Construction |
| Engineer (structural / MEP) | **Design** | Model, Studio, Drawings |
| BIM coordinator | **Model** (3D + Tools) | Design |
| GC / Project Manager | **Construction** | Model, Drawings, Design, Finance |
| Superintendent | **Construction** (field) | Model, Drawings |
| Subcontractor | **Construction** | Model, Drawings |
| Facility manager / Operator | **Construction → Operations** | Developer → ESG |

Personas (the "Viewing as" selector) set each role's `home` workspace, its allowed workspace tabs,
and which nav sections open first (`PERSONAS` in `apps/web/src/main.ts`; `SECTIONS_BY_PERSONA` in
`apps/web/src/portal/portal.ts`). Every role can still reach every register via **Show all modules**
or **⌘K** — placement decides the *default*, not access.

## Workspaces (top-level tabs, left→right = lifecycle order)

- **Model** — the 3D viewer + the model-health Tools rail (Data QA, Code-readiness, clash / federated
  clash, alignment, IDS validate, colour-by-property). These need the loaded geometry, so they live
  here; the Design workspace links to them via **Model Health**.
- **Drawings** — the drawing-set / sheet register.
- **Studio** — the computational (node-graph) design surface.
- **Design** — architect + engineer, the design-phase seat (AIA SD/DD/CD · RIBA stages 2–4).
- **Construction** — the GC/builder portal (plan → build → turn over → operate).
- **Developer** — the owner/real-estate portal (acquire → design & build → operate).
- **Finance** — the proforma / underwriting workspace.

## Design workspace — nav (lifecycle-stage groups)

- **Brief & program**: Space Program (adjacency graph → massing) · Project Lifecycle (phase gates).
- **Model & standards**: IDS Requirements · CDE / Standards (ISO 19650) · BIM KPIs · Model Health
  (deep-links to the Model Tools checks).
- **Registers** (module sections): Programming, Design Phases, Engineering, BIM, Information
  Management — the drawings, submittals, RFIs, design reviews, transmittals, coordination issues,
  information containers, and selections the design team authors and coordinates.

## Module placement (the design-relevant re-tags)

| Module | Section | `workspace` | Rationale |
|---|---|---|---|
| space_program | Programming | `design` | Architect programs the brief |
| project_phase | Design Phases | `developer\|design` | Owner tracks phase gates; architect executes them |
| design_review | Engineering | `design` | A/E design QA |
| selection | Engineering | `design` | Finishes/product selections (A/E-led) |
| information_container | Information Management | `design` | ISO 19650 CDE container (design authoring) |
| info_requirement | Information Management | `design` | EIR / information requirements |
| coordination_issue | BIM | `design` | Model coordination (clash → issue) |
| document | Engineering | `design` | Design document register |
| rfi | Engineering | `construction\|design` | GC raises, A/E answers |
| submittal | Engineering | `construction\|design` | GC submits, A/E reviews |
| drawing | Engineering | `construction\|design` | Shared drawing register |
| transmittal | Engineering | `construction\|design` | Document transmittals both ways |
| meeting | Engineering | `construction\|design` | Design + construction meetings |
| permit | Engineering | `construction\|design` | A/E files, GC pulls |
| spec_section | Preconstruction | `construction\|design` | Specs authored by A/E, used by GC |

Everything else keeps its prior workspace. Notable **intentional** construction-only holds:
`action_item` and `issue` (generic GC coordination — reachable in Design via Show-all if needed).

## Special destinations (portal render-methods) → workspace

| Destination | Workspace | Owner |
|---|---|---|
| Risk Review, Risk & Cost, Schedule, Budget, AI Assist | Construction | GC/PM |
| Turnover, Operations, Energy | Construction | GC → FM |
| Space Program, Project Lifecycle, IDS, CDE/Standards, BIM KPIs, Model Health | **Design** | Architect/Engineer |
| Underwriting, Land Screening, Diligence & Entitlements | Developer | Owner |
| Project Lifecycle (phase gates), ESG & POE | Developer | Owner |
| Portfolio, Benchmarks | all (Across projects) | cross-project |

This table is the checklist to re-run whenever a new module or destination is added: decide the owning
role first, then place it in that role's workspace (and add the second workspace only if the workflow
truly spans two roles).

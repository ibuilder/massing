# GC Portal — module deep-dive & improvement roadmap

A field-by-field audit of the 73 config-driven GC modules and a plan to make each one genuinely useful
to **both superintendents (field) and project managers (office)**, benchmarked against how leading GCs
(Turner, Suffolk, Balfour Beatty) and the dominant tools (Procore, Fieldwire) run these workflows.

## How the system works today
Every module is a `module.json` (no code) describing **fields** (`text · textarea · select · multiselect ·
date · number · currency · reference · rollup · signature`), a **workflow** (states + party-gated
transitions), `list_columns`, and a `section`. Records live in a per-module table (`mod_<key>`), key off
the IFC GlobalId when pinned, and roll up across modules. 73 modules in 14 sections (Field, Engineering,
Cost, Change Management, Safety, Quality, Contracts, Preconstruction, Closeout, Resources, Schedule,
Finance, Sustainability, BIM).

**Strengths:** config-driven (new fields/modules are JSON), `reference` fields link records, `rollup`
fields auto-aggregate (e.g. a Cost Code sums committed/direct/budget/labor across modules), persona-aware
catalog with favorites + filter.

## Cost codes — how they work + the gap
**To add cost codes:** Construction workspace → **Cost Codes** (Resources section) → **+ Add** → enter
`Code`, `Description`, `CSI Division`. They then appear as a **dropdown** wherever a module has a
`reference → cost_code` field. Each cost code auto-rolls-up **Committed** (from `commitment`), **Direct**
(`direct_cost`), **Budget** (`budget`), and **Labor hours** (`timesheet`).

*Gap:* only `budget · commitment · direct_cost · timesheet` carry a cost-code link today. Best practice
(Procore RFI/COR fields) is to tag **RFIs, change events, CORs, daily reports, POs, and material/equipment
logs** with a cost code so impacts roll to the budget. → add `cost_code` references widely (theme **X1**).

## Cross-cutting improvements (apply to many modules)

| # | Improvement | Why (field benchmark) | Status |
|---|---|---|---|
| **N1** | **Persistent navigation rail** — sections → modules, always visible; module content loads in a content pane instead of replacing the whole panel | jumping between 73 modules currently requires going "back" each time | ▶ **building now** |
| **X1** | **Cost-code links everywhere** — add `reference → cost_code` to RFI, change_event, cor, daily_cost, PO/commitment, material/equipment logs | Procore tags RFIs/COs with cost codes so impacts roll to budget | ✅ rfi·cor·change_event·pco_request·proposal (more in tier-2) |
| **A1** | **Ball-in-court / assignee on every actionable module** — explicit `assignee` + ball-in-court party so super/PM instantly see *who owes what* | Procore requires Assignees to open an RFI; "ball in court" is the core metric | ✅ ball-in-court party (computed from workflow transitions) shows as a column in every module list **and** in the record detail header, on top of the existing inline-editable assignee |
| **F1** | **Fieldsets** — group a module's fields into labeled sections in the form (e.g. RFI → *Question / Response / Impacts*) | long flat forms are slow on a phone in the field | ✅ `fieldset` on each field; form renderer emits a labeled header per contiguous run. Applied to all 8 tier-1 modules |
| **D1** | **Inline "add new" from reference dropdowns** — create a cost code / location / sub without leaving the form | supers shouldn't navigate away mid-entry | ✅ done (any reference field) |
| **R1** | **Super vs PM views** — per-role default columns + favorites + which fields show first (field-first vs office-first) | a super needs manpower/weather/safety; a PM needs RFI/submittal/cost/change | planned |
| **C1** | **Cross-module conversions** — RFI → Change Event/COR, Observation → NCR, Inspection fail → Punchlist | Procore "convert RFI to PCO" is a daily move | ✅ record-view "⤳ convert" buttons: RFI→Change Event/PCO, Observation→NCR/Punch, Inspection(fail/conditional)→Deficiency/NCR, Deficiency→Punch. New record is pre-filled + linked back; verified live |
| **E1** | **Extendable `select` options** — admin can add an enum value (discipline, trade, type) without editing JSON | every firm's trade list differs | planned |

## Per-module priorities (research-backed)

### Tier 1 — daily drivers (✅ field completeness done in v0.1.54; ball-in-court via A1)
- **rfi** ✅ — `cost_code` + `drawing` refs (X1), ball-in-court (A1); added `priority`, `location`
  (reference), `rfi_manager`, `received_from`, richer discipline list. *Remaining:* convert→change_event
  (C1), fieldsets Question/Response/Impacts (F1).
- **submittal** ✅ — added `rev`, `responsible_contractor`, `required_on_site`/`date_received`/
  `date_returned`, `cost_code`, expanded type + disposition enums. Strong workflow already
  (draft→submitted→gc_review→ae_review→returned→closed) + `revisable`. *Remaining:* lead-time analytics (Tier 2).
- **cor / change_event / pco_request** ✅ — `reason`, `received_from` on all; `scope_status` +
  `schedule_impact_days` on change_event; `schedule_impact_days` on pco. Already had `cost_code` (X1) +
  cross-links. *Remaining:* tie to SOV/pay-app (Tier 2).
- **daily_report** ✅ — weather as enum + `temp_f`, `weather_impact`, `equipment_on_site`, `delays`,
  `visitors`, `safety_note`, `photos`; list surfaces weather impact; still rolls up manpower/equipment.
- **punchlist** ✅ — added `verified_by` + before/after `photos` (already had location/trade/priority/
  due_date/responsible + verify-requires-attachment). *Remaining:* location→reference (C1).
- **sov / pay app** — link `cost_code`, per-line `change_order_amount` + retainage; already has G702/G703. *(Tier 2)*
- **inspection** ✅ — added `reinspection_date` + `photos` (already had type/inspector/result/location/
  agency/spec + NCR/deficiency rollups). *Remaining:* fail → punchlist conversion (C1).

### Tier 2 — weekly / cost / safety
`submittal` log analytics, `meeting` (agenda/minutes/action-items→action_item), `coordination_issue`
(BCF round-trip), `incident`/`observation`/`jha`/`pretask_plan` (OSHA fields + photos), `commitment`/
`subcontract`/`prime_contract` (SOV link, retainage, exhibits), `budget`/`direct_cost`/`change_event`
(cost-code rollups), `manpower_log`/`timesheet`/`production_quantity` (cost-code + per-trade).

### Tier 3 — preconstruction, closeout, sustainability
`bid_package`/`bid_solicitation`/`bid_submission`/`prequalification`/`comparable` (leveling), `coi`/`permit`/
`noc`/`directive` (compliance dates + expiry alerts), `warranty`/`om_manual`/`as_built`/`asset_register`/
`completion_certificate`/`commissioning` (closeout package — already folds to COBie), `leed_credit`/
`waste_diversion`/`environmental_monitoring` (sustainability tracking).

## Phasing
1. **N1 navigation rail** (this pass) — unblocks navigating everything.
2. **D1 add-from-dropdown + X1 cost-code links** — the cost-code workflow end-to-end.
3. **A1 ball-in-court** ✅ **+ R1 super/PM views** — the "who owes what" layer both roles live in.
4. **Tier-1 field completeness** ✅ (rfi → submittal → cor → daily → punchlist → inspection) + **F1 fieldsets** ✅.
5. **C1 conversions** ✅ **+ E1 extendable enums** ◀ next, then Tier 2/3 field depth.

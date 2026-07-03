# GC Portal — module deep-dive & improvement roadmap

A field-by-field audit of the 73 config-driven GC modules and a plan to make each one genuinely useful
to **both superintendents (field) and project managers (office)**, informed by how leading GCs
(Turner, Suffolk, Balfour Beatty) run these workflows.

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
| **R1** | **Super vs PM views** — per-role default columns + favorites + which fields show first (field-first vs office-first) | a super needs manpower/weather/safety; a PM needs RFI/submittal/cost/change | ✅ two GC personas — **Superintendent** opens Field/Safety/Quality/Schedule first; **Project Manager** opens Engineering/Cost/Change/Contracts first; each gets a tailored workspace/rail set. Verified live |
| **C1** | **Cross-module conversions** — RFI → Change Event/COR, Observation → NCR, Inspection fail → Punchlist | Procore "convert RFI to PCO" is a daily move | ✅ record-view "⤳ convert" buttons: RFI→Change Event/PCO, Observation→NCR/Punch, Inspection(fail/conditional)→Deficiency/NCR, Deficiency→Punch. New record is pre-filled + linked back; verified live |
| **E1** | **Extendable `select` options** — admin can add an enum value (discipline, trade, type) without editing JSON | every firm's trade list differs | ✅ "＋ option" on every select/multiselect; values persist per-project (`enum_options` table) + merge into the dropdown for all users. Verified live + end-to-end test |

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
- ✅ **incident** — full OSHA-recordable log (injured person/employer, body part, injury type,
  witnesses, recordable flag, days-away/restricted, reported-to, root cause + corrective action,
  photos) in Incident / People / OSHA / Investigation fieldsets; list shows recordable.
- ✅ **meeting** — agenda, attendees, old business, distribution, next-meeting + expanded type list;
  Meeting / Content / Follow-up fieldsets (already rolls up action items).
- ✅ **subcontract** — scope, retainage %, cost_code, executed date, insurance expiry, bond-required.
- ✅ **prime_contract** — owner, type expansion, executed date, retainage %, substantial completion,
  liquidated-damages/day (keeps invoiced + SOV rollups).
- ✅ **commitment** — type (PO/Subcontract/Work-Auth), PO date, retainage % (keeps cost_code + rollup).
- ✅ **timesheet / production_quantity** — already carry `cost_code` + trade (goal already met).
- *Remaining:* `submittal` log analytics, `coordination_issue` BCF round-trip, `observation`/`jha`/
  `pretask_plan` OSHA photos, `budget`/`direct_cost` cost-code rollup views.

### Tier 3 — preconstruction, closeout, sustainability
- ✅ **coi / permit** — consolidated the duplicate `expires`/`expiry` date to the canonical `expires`
  (warranty/COBie convention) so expiry alerts key off one field; coi got coverage-type + endorsements,
  permit got a real type enum + status + fee. Regression-locked (no module may carry both date names).
- ✅ **bid leveling** — `bid_submission` (base bid, alternates, unit prices, inclusions/exclusions/
  qualifications, bond), `bid_package` (scope, spec sections, walkthrough/RFI dates), `prequalification`
  (contact, revenue, references, expiry).
- ✅ **closeout depth** — `warranty` (type, start, term-years), `asset_register` (install date, service
  contact, barcode — **fixed a duplicate `warranty_expires`/`warranty_expiry`**), `commissioning`
  (Cx agent, test type, result, deficiencies), `om_manual` (spec section, responsible).
- ✅ **sustainability** — `leed_credit` (points targeted vs achieved), `waste_diversion` (hauler,
  destination, diversion %), `environmental_monitoring` (location, compliant/exceedance status).
- ✅ **coordination_issue BCF round-trip** — export/import `.bcfzip` with Solibri/ACC/BIMcollab.
- *Remaining:* `noc`/`directive` compliance dates, `as_built` depth; a unified **compliance-expiring**
  endpoint already covers coi/permit.

## Builder-readiness review (how a real super/PM uses this daily)
A pass over whether the tools fit batch-oriented field work, not just one-record-at-a-time office use:
- ✅ **Bulk photo/file upload** — drag-drop a *batch* of site photos onto any record (was one-at-a-time);
  image attachments show as a thumbnail gallery. `POST …/attachments/bulk`.
- ✅ **Bulk record actions** — multi-select + **select-all** in every list → assign / transition / delete
  many at once (e.g. close a whole location's punch list); bulk transition now lists the module's
  valid actions instead of blind typing.
- ✅ **Tie model elements** — select in 3D, tie to a record (exact 4D, or "what this RFI concerns").
- Already builder-ready: kanban **boards**, saved **views**, filters, inline-edit assignee/status,
  ball-in-court, persona (super vs PM) nav, add-from-dropdown, fieldset-grouped forms.
- *Remaining builder polish:* per-record photo capture from mobile, offline queue, push/email digests
  (digest infra exists), and a few modules still want a `photos`/attachment-first layout.

## Phasing
1. **N1 navigation rail** (this pass) — unblocks navigating everything.
2. **D1 add-from-dropdown + X1 cost-code links** — the cost-code workflow end-to-end.
3. **A1 ball-in-court** ✅ **+ R1 super/PM views** — the "who owes what" layer both roles live in.
4. **Tier-1 field completeness** ✅ (rfi → submittal → cor → daily → punchlist → inspection) + **F1 fieldsets** ✅.
5. **C1 conversions** ✅ **+ E1 extendable enums** ✅ **+ R1 super/PM views** ✅. **All cross-cutting themes (N1·X1·D1·A1·F1·C1·E1·R1) done.**
6. **Tier-2 depth** ✅ incident(OSHA)·meeting·subcontract·prime_contract·commitment; **Tier-3** ✅ coi·permit
   expiry cleanup. Remaining Tier-2/3 = bid leveling, closeout (warranty/O&M/as-built), sustainability,
   coordination BCF, + a unified compliance-expiring endpoint.

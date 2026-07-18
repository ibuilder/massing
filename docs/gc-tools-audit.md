# GC tools audit & todo (per module)

> **Point-in-time audit (June 2026) — superseded.** Kept for the record; current state lives in
> [roadmap.md](roadmap.md) + [roadmap-completed.md](roadmap-completed.md) and the [changelog](../CHANGELOG.md).

A research-backed pass over all **69 GC-portal modules** to bring each toward the field/workflow
depth of industry-standard tools (Procore / Autodesk Construction Cloud conventions). Each module
is one `services/api/modules/<key>/module.json` driving the config-driven engine (CRUD, workflow,
list/board, relations, PDF, CSV).

Sources: [Procore punch list](https://www.procore.com/project-management/punch-list) ·
[Procore observations](https://www.procore.com/quality-safety/observations) ·
[Procore daily log fields](https://support.procore.com/faq/which-fields-in-the-daily-log-tool-can-be-configured-as-required-optional-or-hidden) ·
[Procore inspections](https://support.procore.com/products/online/user-guide/project-level/inspections).

## Batch 1 — DONE (2026-06)
Enriched **51 modules (+122 fields)** with standard fields + list columns; registry loads all 69,
module CRUD/sync tests green. `list_columns` now on 53/69 (was 3). Highlights of what each got:

### Field
- **punchlist** — +priority, responsible, due_date, est. cost · cols trade/priority/due.
- **checklist** — +category, result(Pass/Fail/N/A), notes, location.
- **photo** — +location, date_taken, trade, tags(multiselect).
- **manpower_log** — +trade, workers, hours. **timesheet** — +trade, hours, date, cost_code.
- **delivery** — +supplier, PO#, received_by, date, status. **site_logistics** — +description, date, type.

### Quality
- **inspection** — +type, inspector, date, agency, spec_section (keeps NCR/deficiency rollups).
- **deficiency** — +severity, trade, due_date, corrective_action.
- **ncr** — +severity, root_cause, disposition(Use-As-Is/Rework/Repair/Reject), corrective_action, due_date.
- **test_record** — +test_type, result, date, lab, spec_section.

### Safety
- **observation** — +type(Safe/At-Risk/Hazard), severity, location, trade, corrective_action.
- **jha / pretask_plan** — +task, hazards, controls, ppe / crew_size.
- **toolbox_talk** — +topic, date, presenter, attendees. **orientation** — +worker, company, date, trainer.
- **safety_violation** — +severity(Minor/Serious/Willful), corrective_action, due_date.

### Change / Cost / Contracts
- **noc** +description/cost/days · **proposal** +amount/scope/days.
- **budget** +original/revised/committed · **direct_cost** +vendor/amount/date/type · **owner_invoice** +amount/period/status.
- **coi** +carrier/policy/coverage/expiry · **lien_waiver** +type/amount/through_date.

### Engineering / Precon / Closeout / Resources / Sustainability / BIM
- **drawing/document** +discipline/revision/status · **permit** +type/authority/number/dates/status · **meeting/action_item/issue/design_review/transmittal** standardized.
- **bid_package/bid_solicitation/bid_submission/estimate/prequalification/value_engineering** +trade/amount/status/dates.
- **as_built/asset_register/commissioning/completion_certificate/om_manual** +system/status/dates/asset attrs.
- **cost_code/equipment_rate/labor_rate/location** rate+lookup attrs · **environmental_monitoring/leed_credit/waste_diversion** +metrics/status · **coordination_issue** +discipline/priority/location.

Left intentionally lean: the **rate/lookup tables** (equipment_rate, labor_rate, material_rate,
location, cost_code) and already-rich modules (**rfi, submittal, sov, commitment, incident,
daily_report, equipment_log, production_quantity, schedule_activity, cor, pco_request, change_event,
warranty, subcontract, prime_contract**).

## Batch 2 — DONE (workflow depth + cost chain + required fields)
- **Workflow depth** — real party-gated lifecycles for **observation** (open→assigned→corrected→
  closed), **deficiency** (corrective loop), **coi** (open→active→closed), **lien_waiver**
  (open→received→closed), **permit** (applied→issued→closed), **toolbox_talk**, **checklist**.
  Every replacement keeps the module's prior states, so no live record is stranded.
- **Reference/rollup audit** — the chains were already extensive (deficiency/ncr/test→inspection,
  daily_report→manpower/equipment, change_event→pco, prime_contract→sov/invoiced, cost_code rollups,
  etc.). Completed the one missing cost link: **direct_cost → commitment** + **commitment.spent**
  rollup (sum of direct costs).
- **Required-field validation** — marked 10 truly-required fields (ncr/deficiency severity,
  inspection date, permit/coi expiry, lien_waiver/direct_cost amount, test result, …).

## Batch 3 — DONE (evidence gate, engine-level)
- **Attachment-required sign-off** — a `close_requires_attachment` flag (engine-enforced in the
  transition path) blocks a record from entering a sign-off state until it has a photo/attachment.
  Enabled on **punchlist** (verify), **observation/incident/deficiency/ncr** (close). Other tools
  and the test suite are unaffected (opt-in). Covered by `test_evidence_gate.py`.

## Remaining (optional, larger engine features)
- **Reusable checklist / inspection templates** (Procore parity) — a templates store + apply-to-record
  UI. Largest remaining item.
- **Per-tool branded PDFs** — the engine already emits a generic per-record PDF + CSV; branded,
  form-specific layouts (signable daily report / JHA / toolbox talk) are polish.
- **TRIR / safety analytics** — recordable-count rollups feeding a safety KPI on the dashboard.

## How to extend
Edit `services/api/modules/<key>/module.json` (field types: text, textarea, number, currency, date,
select+options, multiselect, reference{module}, rollup{source_module,source_field,op}, signature).
The engine auto-creates the table; new fields live in the JSON `data` column (no migration). Then
restart the API (registry loads on boot) — the list/form/board/PDF all update for free.

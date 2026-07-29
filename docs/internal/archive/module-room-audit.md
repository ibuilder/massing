# Module & Room Audit — 133 registers, six rooms

**Date:** 2026-07-29 · **Against:** v0.3.788 · **Status:** audit + plan. **Sprints 1 and 2 are built**
(see §7); sprints 3–6 remain proposed.

This audits every `services/api/modules/*/module.json`: where it sits in the six-room IA and why, how
close it is to the artifact it claims to represent, and what it would take for each to stop being a
web version of a paper form.

---

## 0. What was actually checked (and what wasn't)

State the grade of a check with its conclusion, so a reader knows which claims to trust.

| # | Check | Method | Grade |
|---|---|---|---|
| C1 | Module inventory, sections, field counts, workflow states | Parsed all 133 `module.json` from disk | **Verified** |
| C2 | Room allocation | Ran `ROOM_OF_SECTION` from `rooms.py` over C1 | **Verified** |
| C3 | Reference graph / rollups / field-type census | Static parse of every `fields[]` entry | **Verified** |
| C4 | Module ↔ engine coupling | Grepped 313 `aec_api/*.py` for each module key as a quoted string | **Indicative** — a string match proves a mention, not a live call path |
| C5 | Register → tool linkage in the web shell | Counted `needs:` against `ALL_DESTS` in `destinations.ts` | **Verified** — **47 unique** destinations, 5 declare a module. (First pass said 58; that was a raw `grep -c` over the file, which counts a destination once per workspace rail it appears in. 47 is the deduped `ALL_DESTS` figure and is the right denominator.) |
| C6 | "Is the artifact complete?" | Web research per artifact **family** (see §6), compared to fields | **Family-level.** I did not research 133 artifacts individually; I researched the standards that govern them and checked the modules those standards apply to. Findings named below are checked one-by-one; unnamed modules were not individually verified. |

Not checked: runtime behaviour, whether any engine is reachable over HTTP, and whether the web
register actually renders every declared field. Those need a started app
(`route-check-needs-started-app`), and I did not start one.

---

## 1. The headline

**The depth is not missing. It is somewhere the user can't see it.**

The instinct behind the question — "these are paper forms with a web coat of paint" — is right about
the *register UI* and wrong about the *platform*. There are 313 engine files behind these 133
registers, and many of them are genuinely deep: `fca.py` computes a real FCI against ASTM E1557
UNIFORMAT II, `schedule_cpm.py` does forward/backward pass float, `sov_build.py` regroups estimate
lines into a G703, `bid_leveling.py` builds a scope-adjusted comparison grid, `turnover.py` issues an
AIA G704.

What's missing is the **seam**. `module.json` has no way to say *"this register has a tool behind
it."* The complete list of optional keys across all 133 modules is:

```
icon · list_columns · pinnable · ref_prefix · title_field · workspace · revisable ·
close_requires_attachment · help
```

Every one is presentation. None is capability. So a register renders as: a table, a form, a status
chip — which is, precisely, a paper form. The engine that would make it a tool is on a different
screen with no link in either direction. Of 47 panel destinations, **5** declared which module they
operate on, and nothing let a register declare the reverse.

That single gap explains most of what looks like thinness, and fixing it is cheaper than rebuilding
133 modules.

---

## 2. The measurable thinness

| Signal | Count | Reading |
|---|---|---|
| Modules with **zero reference fields** | **69 / 133** | Half the system is islands. A record that points at nothing can't participate in a chain. |
| Modules **never referenced by anything** | **96 / 133** | Same wall from the other side. |
| Modules using **rollups** | **10** (18 fields) | The only computation a register can express today. |
| Modules with the boilerplate `open → closed` workflow | **36** | A two-state workflow is a checkbox wearing a costume. |
| Modules with **no fieldsets** (one undifferentiated column of inputs) | **62** | The form has no structure — the clearest paper-form tell. |
| `file` fields across all 133 modules | **3** | See below. |
| Textareas standing in for a table | **22** | See below. |
| Modules with **no engine mention at all** (C4) | **29** | Registers with nothing behind them. |

### 2a. Attachments are fiction

Three `file` fields exist in the entire system. Meanwhile: `incident.photos`, `punchlist.photos`,
`inspection.photos`, `daily_report.photos` are all **textarea**. A safety incident's photographic
evidence — the thing that decides a claim — is a box you type into. There *is* a storage layer
(`storage.py`, `docmanager.py`, MinIO). The register just can't reach it.

### 2b. Twenty-two places a table was flattened into prose

```
bid_submission.alternates · bid_submission.unit_prices · commissioning.deficiencies
daily_report.crew_by_trade · .deliveries · .equipment_on_site · .visitors · .photos
incident.witnesses · .photos · inspection.photos · punchlist.photos
meeting.distribution · rfi.distribution · submittal.distribution
project_charter.key_deliverables · .key_milestones · .high_level_risks · .key_stakeholders
project_phase.deliverables · spec_section.submittals_required · transmittal.items
```

Each is a **list of records typed into one string**. `bid_submission.unit_prices` is the sharpest:
bid leveling is *defined* as a row-per-scope-item comparison, and `bid_leveling.py` exists to do
it — but the unit prices it needs are stored as free text, so the engine is parsing prose that a
structured child table would have handed it clean.

**There is no line-item field type.** `FIELD_TYPES` in `module_schema.py` has 15 entries; none of
them is a table. That is why `sov` is *one record per line* with no parent document, why `estimate`
is a single `amount:number`, and why `budget` is a row rather than a budget.

---

## 3. Room-by-room: what's there, why, and what's wrong

Current allocation (`rooms.py` derives room from `section` — a module's room is never stored per
module, which is the right design and should stay):

**Design 39 · Planning 16 · Cost 20 · Schedule 42 · Deal 16 · Work 0**

### Design (39) — the room that is really four rooms

`BIM · Design · Design Phases · Engineering · Information Management · Programming · Quality ·
Resilience · Specifications · Sustainability`

The stated intent — "the architect's and engineer's room: model it, draw it, specify it" — is right.
The execution has 39 modules in one flat list, which the memory note already flags as the wall the
spine exists to replace. Three specific misplacements:

- **Quality (7 modules) does not belong in Design.** `inspection`, `itp`, `ncr`, `deficiency`,
  `test_record`, `compliance_evidence`, `risk` are filed here on the reasoning that "inspections/ITP
  describe the built thing against the design." That is true of the *reference standard* and false
  of the *user*. An ITP hold point is released by a field engineer standing at the pour; an NCR is
  written by a superintendent. `deficiency` and `ncr` are near-twins of `punchlist`, which is in
  Schedule. Sending an inspector to the architect's room to close a hold point is the exact
  navigation failure the spine exists to prevent.
- **`permit` (Engineering → Design) is split from `entitlement` (Acquisition → Deal).** These are
  one approvals spine — a zoning approval, a building permit, and a certificate of occupancy are
  successive gates on the same path — cut across two rooms by an accident of sectioning.
  `permit_timeline.py` and `entitlements.py` both exist and don't meet.
- **`meeting`, `action_item`, `issue`, `document`, `transmittal` are not design artifacts.** They're
  project-wide. A GC's meeting minutes and an owner's action item currently live in the architect's
  room because their section is "Engineering."

### Planning (16) — the cleanest room, and the most under-built

`Preconstruction · Contracts`. The split out of Cost was correct: estimating and buying out is
planning work with an outcome in money, not accounting.

But this room holds the **thinnest modules in the system relative to what they represent**:
`estimate` has 4 fields (`name`, `amount`, `basis`, `date`), `value_engineering` has 4, and
`bid_submission` keeps its unit prices and alternates as prose. This is the room where a
preconstruction lead works daily, and it is the one that most resembles a paper form.

### Cost (20) — mostly right, one clear intruder

`Cost · Change Management · Capital`. Change Management alongside the ledger is correct — a COR is
a money event.

- **`investor` (section Capital) is in the wrong room.** Investor records, capital calls and
  distributions are *deal* work — `distwaterfall.py`, `securities_bridge.py` and `capital.py` all
  serve the equity side. Capital is a one-module section whose only member belongs in Deal.

### Schedule (42) — the dumping ground

`Closeout · Field · Project Controls · Resources · Safety · Schedule`

This is the largest room and the least coherent. Three problems:

- **`Resources` (10 modules) is a reference library, not schedule work.** `cost_code`, `labor_rate`,
  `material_rate`, `equipment_rate`, `price_observation`, `company`, `contact`, `location`. A cost
  code library is consumed by Cost and Planning; it has nothing to do with sequencing. Ten modules
  sit in the Schedule room because "Resources" sounded like resource loading.
- **The actual schedule is filed under `Field`.** `schedule_activity` — 20 fields, the CPM
  activity that `schedule_cpm.py`, `evm.py` and `schedule_baselines.py` all read — has
  `"section": "Field"`. Meanwhile the `Schedule` section contains three modules: `prefab_kit`,
  `pull_plan_task`, `weekly_plan`. Same room, so no user-visible break today — but it means the
  Schedule room's own section is not the schedule.
- **`Closeout` (7) is orphaned from its consumer.** `asset_register`, `om_manual`, `warranty`,
  `as_built`, `commissioning`, `completion_certificate` are the handover package. Their consumer —
  `work_order`, `pm_schedule`, `meter`, `building_system`, `fca_element` — is in **Deal**. The COBie
  chain that the research confirms is the whole point of handover (assets, warranties, spares, PM
  schedules moving into the CMMS on day one) is cut in half by a room boundary.

### Deal (16) — two unrelated jobs in one room

`Acquisition · Feasibility · Finance · Market & Sales · Operations`

`Operations` carries **10 modules doing two different jobs**: `lease` and `cam_expense` are deal/
asset-management work; `work_order`, `pm_schedule`, `meter`, `meter_reading`, `building_system`,
`fca_element`, `capital_plan`, `poe` are **facilities management**. An FM tech logging a work order
currently opens a room labelled "Underwrite it, fund it, lease it and dispose of it." That is the
single worst room fit in the system, and it affects the users who log the most records over an
asset's life.

### Work (0) — correct

Holds records, not registers. The gate exempts it. No change.

---

## 4. Proposed placement

The mechanism stays: **room is derived from section, one table, never stored per module.** So every
move below is either a `ROOM_OF_SECTION` edit or a `section` edit in a `module.json` — both cheap,
both gated by `test_module_rooms.py`.

### 4a. New sections (each needs a deliberate `ROOM_OF_SECTION` entry)

| New section | Room | Modules moved in | Why |
|---|---|---|---|
| **Facilities** | new **Operate** room *(or Deal, see 4c)* | `work_order`, `pm_schedule`, `meter`, `meter_reading`, `building_system`, `fca_element`, `poe`, `capital_plan` | FM is a distinct job from leasing |
| **Quality** *(re-pointed)* | **schedule** | `inspection`, `itp`, `ncr`, `deficiency`, `test_record`, `compliance_evidence` | quality is executed in the field |
| **Reference Data** | **planning** | `cost_code`, `labor_rate`, `material_rate`, `equipment_rate`, `price_observation` | rate libraries feed estimating |
| **Directory** | **planning** | `company`, `contact` | the vendor/contact book, used at prequal and buyout |
| **Approvals** | **planning** | `permit`, `entitlement`, `checklist`(permit-check) | one approvals spine, one room |
| **Coordination** | **design** | `meeting`, `action_item`, `issue`, `document`, `transmittal` | project-wide, but design-adjacent; keep in Design until sub-rooms land |

### 4b. Single-module moves

| Module | From section → room | To section → room | Why |
|---|---|---|---|
| `investor` | Capital → cost | Finance → **deal** | equity, not the ledger. Retires the one-module `Capital` section |
| `schedule_activity` | Field → schedule | Schedule → schedule | same room; makes the Schedule section actually contain the schedule |
| `risk` | Quality → design | Project Controls → schedule | project risk register, not design QA |
| `location` | Resources → schedule | Design → design | it's a spatial breakdown of the building |
| `material_request` | Resources → schedule | Field → schedule | field requisition; stays in room, correct section |
| `resource_assignment` | Resources → schedule | Schedule → schedule | genuine resource loading; stays in room |
| `staffing` | Cost → cost | Schedule → schedule | duplicates `resource_assignment`'s job from the money side — see §5 dedup |

### 4c. The seventh room — decided

**FM gets its own room: `operate`, between Schedule and Deal.** Settled 2026-07-29 and shipped in
Sprint 1. The reasoning below is kept so the decision can be re-read rather than re-argued.

- *Seventh room "Operate"* — honest to the lifecycle (design → plan → cost → schedule → **operate**
  → deal), and FM users get a home instead of a corner of someone else's. Cost: the spine constant
  goes 6 → 7 in three places, and `test_module_rooms.py` hardcodes room ids **on purpose** so the
  rename breaks a test before it breaks a user. That's a feature; it just means the change is
  deliberate.
- *Stay in Deal, as a distinct `Facilities` section* — zero structural change, and the sub-room work
  already planned for Design would give FM its own group inside Deal.

The seventh room won. FM is where the asset spends most of its life and most of its cost, the
platform already has `cmms.py`, `fca.py`, `reserve.py`, `twin.py`, `energy.py` and `cx.py` serving
it, and burying that under "Deal" mis-sells the strongest part of the back half of the product.

The same change moved the **handover package** — `asset_register`, `om_manual`, `warranty`,
`commissioning` — into a `Handover` section in `operate`, reuniting it with the CMMS that consumes
it. What genuinely belongs to the end of construction (`completion_certificate`, `as_built`,
`lessons_learned`) stayed in `Closeout` under Schedule.

**Allocation after Sprint 1:** Deal 8 · Design 32 · Planning 25 · Schedule 38 · Cost 18 · Work 0 ·
Operate 12 = 133, none unplaced, no section mapped that no module uses.

**Room order** is the user's, set 2026-07-29: `deal · design · planning · schedule · cost · work ·
operate`. It lives in four places that must agree — `ROOMS` (rooms.py), `ROOM_IDS` and
`FALLBACK_ROOMS` (spine.ts), `PROFESSIONAL` (roomNames.test.ts, asserted with `toEqual`, so
order-sensitive by design), and the id/label lists in `test_module_rooms.py`. Note this is the
*unweighted* order: `orderRooms()` promotes a workspace's own room to the front, so a Construction
user still opens on Schedule. Four of the seven rooms (cost, planning, work, operate) have no
workspace preselecting them, which is the design — a workspace picks a starting room, it does not
need to own one.

### 4d. Design sub-rooms (already flagged as open; this is the shape)

39 flat modules → **Model** (`clash_run`, `coordination_issue`, `information_container`,
`info_requirement`, `lod_target`, `location`, `space_program`) · **Drawings** (`drawing`,
`drawing_set`, `drawing_issuance`, `sketch`, `concept_render`) · **Specs** (`spec_section`,
`selection`, `design_standard`, `submittal`) · **Analysis** (`envelope_assembly`, `mep_equipment`,
`climate_site_risk`, `flood_risk`, `drainage_area`, `leed_credit`, `waste_diversion`,
`environmental_monitoring`) · **Coordination** (`rfi`, `meeting`, `action_item`, `issue`, `document`,
`transmittal`, `design_review`, `design_option`, `project_phase`).

---

## 5. Making them tools, not forms

Four changes to the `module.json` contract, in dependency order. Everything else is downstream.

### T1 — `tools:` — link a register to the tool that already exists ✅ *shipped in Sprint 2*

One optional key naming the destination(s) that operate on this register, rendered as actions on the
register header:

```jsonc
"tools": [
  { "dest": "__aiassist__", "label": "Level bids" },
  { "dest": "__evm__",      "label": "Earned value", "scope": "record" }
]
```

This is the inverse of the `needs:` key `destinations.ts` already had (5 of 47 destinations used it).
Wiring both directions turns a panel from "a screen you have to know about" into "what this register
can do." Nothing new was built — it exposes what was already written.

**Shipped: 40 links across 32 registers**, covering 17 of the 47 destinations.

`module_schema.ToolRef` validates the shape and deliberately does **not** validate the key — the
catalog lives in TypeScript, and a Python copy of it would be a third table encoding one fact.
`moduleTools.test.ts` reads the module files and asserts every `dest` resolves against `ALL_DESTS`,
the same arrangement as `roomNames.test.ts` reading `rooms.py`.

**Only verified pairs were wired.** A link was written when the panel's API call path traced to an
engine that actually reads that module — e.g. `__aiassist__` calls `api.bidLeveling`, `__operations__`
calls `api.cmmsKpis`/`api.fcaIndex`/`api.cxDossier`, `__standards__` calls
`api.infoRequirementsRegister`/`api.lodAssessment`. Two candidates were **dropped** on inspection:
`__topicboard__` names no module key in `topic_board.py`, and `__equipment__` calls
`api.modelEquipment` — it is the MEP model extract, not the equipment-rate library it looked like.

The hardcoded `if (m.key === "schedule_activity")` branch that gave exactly one register a "Views"
button was deleted; `schedule_activity` now declares `__schedule__` like everything else. That branch
was the whole problem in miniature — one register got a door because someone remembered to write it.

Still unwired, and the highest-value remaining work: `sov`/`owner_invoice` → `sov_build.py` →
`cost.g703` → `report.payapp_pdf`, `lien_waiver` → `payapp.py`, `clash_run` → `clash_intel.py`,
`lease` → `leasemgmt.py`/`net_effective.py`, `estimate_set` → `conceptual_estimate.py`. Each needs a
destination that does not exist yet, so each is a panel to build rather than a link to declare.

### T2 — a `table` field type — kill the 22 flattened lists

Add `table` to `FIELD_TYPES` with a declared column set, so a child-row grid renders inside a record.
This is what turns `bid_submission.unit_prices` from prose into something `bid_leveling.py` can read
without guessing, `sov` from a row into a document, `estimate` from a number into an estimate, and
`daily_report.crew_by_trade` into a manpower table that `productivity.py` can sum.

Order of attack (by value of what's currently lost): `sov` → `bid_submission` → `estimate` →
`daily_report` → `budget` → `project_charter` → `transmittal` → `spec_section`.

### T3 — make `file` real, retire the photo textareas

Wire the `file` type to the existing storage/`docmanager` layer, then convert
`incident.photos`, `punchlist.photos`, `inspection.photos`, `daily_report.photos`,
`commissioning.deficiencies` and `incident.witnesses` from textarea to their proper types.
`close_requires_attachment` already exists on 5 modules and is currently enforcing a rule against a
field that can't hold an attachment.

### T4 — an element link field type

The project's first non-negotiable is *"reference model elements by IFC GlobalId, never by transient
viewer IDs."* Only **3** modules carry a GUID today (`field_verification.guid`,
`material_request.guids`, `prefab_kit.frozen_guids`), and they do it as plain text. Every one of
`punchlist`, `deficiency`, `ncr`, `inspection`, `observation`, `coordination_issue`, `asset_register`,
`fca_element`, `mep_equipment`, `envelope_assembly` describes a thing that *is* a model element.

A first-class `element` field (GUID + IFC class + display name, validated against the model) is what
separates this from every other register product — and it's the platform's own stated premise going
unused in the layer users touch most.

---

## 6. Depth gaps found against the standards (C6)

Researched at family level; the modules named here were each checked against the sources in §8.

| Module | Gap vs the real artifact | Fix |
|---|---|---|
| `sov` | No parent document; `retainage_pct` per line but no `balance_to_finish`, no G702 summary record | T2 + wire `cost.g703` |
| `owner_invoice` | 5 fields for an AIA G702 pay application. No retainage, no stored materials, no period dates, no certification | Rebuild as G702 head over an SOV child table |
| `bid_submission` | Alternates and unit prices as prose; no leveled/adjusted total, no scope-gap rows | T2 + `bid_leveling.py` link |
| `estimate` | 4 fields. No line items, no WBS/CSI, no unit rates, no markup or contingency, no AACE class | T2; adopt AACE 18R-97 Class 1–5 in `basis` |
| `estimate_set` | `basis` list (`Conceptual/Schematic/DD/CD/GMP`) is design-phase, not estimate class; carries no accuracy range | Add AACE class + expected accuracy band |
| `submittal` | Has type/disposition/lead time — good. Missing ball-in-court, required-by-date derived from lead time + procurement, and the A/B/C/D action-code convention | Add fields; link `submittals.py` |
| `coi` | Good bones (`additional_insured`, `waiver_of_subrogation` as selects). But a checked box on an ACORD 25 proves nothing — the *endorsement* does | Add endorsement-form fields (CG 20 10 / CG 20 37) + attachment via T3 |
| `incident` | Strong — 21 fields, near OSHA-301 complete | Witnesses/photos → T2/T3. Add 7-day-completion clock |
| `itp` | Correct control-point model (H/W/M/R) | `acceptance_criteria` should cite standard + clause, not free text. Add sign-off signature |
| `information_container` | Has `suitability_code` + `revision` — ISO 19650 correct | Add classification code (4th required attribute) and enforce the `S2–P03` pairing |
| `lease` | Solid abstract | Missing ASC 842 essentials: commencement vs rent-start, base-year/expense-stop, escalation *formula* (not just `%`), termination rights |
| `asset_register` | 20 fields, best in the system; `gs1_id`/`epd_reference` are ahead of the market | Missing COBie `Spare` and `Job` — the rows a CMMS needs to open a PM |
| `schedule_activity` | 20 fields, EV method, actuals — real | Predecessors as text; no relationship type or lag, so DCMA logic/lead/lag checks can't run |
| `clash_run` | **No workflow at all** — the only such module | Give it states, or make it a computed artifact rather than a register |
| `value_engineering` | 4 fields for a VE log | Needs originator, lifecycle-cost impact, schedule impact, disposition-by, and a link to the estimate line it changes |
| `project_charter` | 4 of its 17 fields are lists-as-prose | T2 |

---

## 7. Sequenced plan

Per the sprint directive: one release, one full-suite run, one CI watch per sprint.

**Sprint 1 — Placement.** ✅ **Shipped.** 33 modules re-sectioned; `operate` added as the seventh
room; `Resources` and `Capital` retired. `test_module_rooms.py` now asserts the *specific* allocation
by module name — the old gate proved every module had *a* room and could never tell you it had the
*wrong* one, which is exactly how `work_order` sat in Deal while being perfectly reachable. It also
fails on a retired section reappearing and on a `ROOM_OF_SECTION` entry no module uses.

**Sprint 2 — T1 `tools:`.** ✅ **Shipped.** `ToolRef` in `module_schema.py`, register-header rendering
in `portal.ts`, 40 links across 32 registers. `moduleTools.test.ts` asserts every `dest` resolves,
that labels exist, that no register lists a dest twice, and — the inverse question that actually finds
things — reports which destinations still have no register naming them, failing if coverage regresses.

**Two defects found while shipping these, both of the same shape — a value that never arrives, and
nothing that fails when it doesn't:**

1. **`GET /modules` is a hand-written allowlist, not a passthrough.** `routers/modules.py::list_modules`
   projects a fixed key set, so `tools[]` was present in `module.json`, present in the web's
   `ModuleDef` type, and still arrived `undefined`. An undefined list renders as no buttons — which
   looks exactly like "the feature isn't built" rather than "the feature isn't served". Every unit
   test passed; it surfaced only by querying a running server. `test_modules.py` now asserts a
   declared key survives the wire. **Any new `module.json` key needs a line in that projection.**
2. **`/rooms` was never in the demo capture at all.** `build_demo_data.py` grabbed `/modules`,
   `/modules/graph` and the portfolio routes but not `/rooms`, so the public demo's rail has always
   rendered from the web's `FALLBACK_ROOMS`. That is why a taxonomy change could rot the demo
   silently — the fallback still drew something plausible, so there was nothing to notice. Now
   captured, and the snapshot carries the real allocation, labels and `tools[]`.

**Sprint 3 — T2 `table`.** Field type, renderer, `validate_module` rules. Convert `sov`,
`bid_submission`, `estimate`. Gate: a test that no field named in the §2b list is still a textarea.

**Sprint 4 — T3 attachments + T4 element link.** Wire `file` to storage; convert the photo fields;
add the `element` type and put it on the 10 modules that describe model elements. Gate: assert
`close_requires_attachment` modules have an attachment-capable field.

**Sprint 5 — Depth.** The §6 field work, module by module, plus the Design sub-rooms (4d).

**Sprint 6 — Dedup and prune.** Findings held for last because they need judgment, not mechanism:
`staffing` vs `resource_assignment` (two staffing registers, two rooms); `deficiency` vs `ncr` vs
`punchlist` (three near-identical defect registers); `issue` vs `coordination_issue`; `drawing_set`
vs `drawing_issuance`; and the 29 modules C4 found with no engine mention — each is either wired,
merged, or removed.

---

## 8. Sources

Grounding for §6, one per artifact family:

- AIA G702/G703 continuation sheet, retainage and stored-materials columns — [AIA Contract Documents: G703 instructions](https://help.aiacontracts.com/hc/en-us/articles/1500009308302-instructions-g703-1992-continuation-sheet), [G702/G703 billing walkthrough](https://payapppro.com/learn/aia-g702-g703-billing-guide.php)
- AACE 18R-97 estimate classification, Class 1–5 and accuracy ranges — [AACE 18R-97 TOC](https://web.aacei.org/docs/default-source/toc/toc_18r-97.pdf), [AACE Professional Guidance Document 01](https://library.aacei.org/pgd01/pgd01.shtml)
- ISO 19650 information-container metadata (container ID, revision, status/suitability, classification) — [UK BIM Framework Guidance Part C](https://ukbimframework.org/wp-content/uploads/2020/09/Guidance-Part-C_Facilitating-the-common-data-environment-workflow-and-technical-solutions_Edition-1.pdf), [ISO 19650 status codes S0–S7](https://goto.archi/blog/post/iso-19650-status-codes-explained)
- Submittal register fields and A/B/C action codes — [Submittals (construction)](https://en.wikipedia.org/wiki/Submittals_(construction)), [USACE ENG Form 4025-R](https://www.publications.usace.army.mil/Portals/76/Publications/EngineerForms/Eng_Form_4025-R.pdf), [Section 013300 Submittal Procedures](https://www.cuanschutz.edu/docs/librariesprovider260/design-and-construction/guidelines-and-standards/division-01/013300---submittal-procedures.pdf?sfvrsn=bf9eb8b9_2)
- OSHA 300/301 recordable case fields and classification — [OSHA recordkeeping guidance, Forms 301/300/300A](https://ogletree.com/insights-resources/blog-posts/osha-recordkeeping-and-reporting-guidance-for-employers-part-ii-completing-osha-forms-301-300-and-300a/)
- ACORD 25 certificate fields; endorsement vs checkbox — [How to read a COI field by field](https://www.getbcs.com/blog/how-to-read-a-certificate-of-insurance-a-field-by-field-guide), [ACORD 25/27 guide](https://www.vertikalrms.com/article/acord-25-27-forms-complete-insurance-certificate-guide/)
- ITP hold/witness/monitor/review points and acceptance criteria — [ITP complete guide](https://quollnet.com/article/itp-inspection-test-plan-construction), [Inspection for Industry: ITP](https://www.inspection-for-industry.com/pipe-inspection-and-test-plan.html)
- Lease abstraction fields for ASC 842 — [Lease data abstraction for ASC 842](https://costarmanager.com/blog/lease-data-abstraction-for-asc-842), [Commercial lease abstract key terms](https://ddee.ai/resources/guides/commercial-lease-abstract)
- COBie handover content (assets, warranties, spares, PM jobs → CMMS) — [What is COBie data](https://cobiedatacottage.com/what-is-cobie-data.html), [BIM→CMMS integration](https://oxmaint.com/industries/facility-management/bim-cmms-integration-facility-lifecycle-management)
- DCMA 14-point schedule checks (logic, leads, lags, float, relationship types) — [DCMA 14-point assessment](https://www.planacademy.com/dcma-14-point-schedule-assessment/), [DCMA 14 checks](https://smartpm.com/blog/dcma-14-checks)
- Bid leveling sheet structure (row per scope item, adjusted totals) — [Bid leveling in construction](https://buildern.com/resources/blog/bid-leveling/), [Bid tabulation guide](https://www.speclens.ai/guides/bid-tabulation)

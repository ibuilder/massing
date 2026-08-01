# Module field sweep — fields, fieldsets, relationships, CRUD

**Date:** 2026-07-29 · **Against:** v0.3.799 (`bf9c53f2`) · **Scope:** all 133 modules, 1171 fields.
**Internal.** `docs/` is the Pages web root and gets published wholesale — working notes belong here.

Reference material: **[eManagerNYC/django_emanager](https://github.com/eManagerNYC/django_emanager)**,
a Django construction-management app the user built previously. 7 apps, 21 models. Its value is not its
depth — it is an early scaffold — but that it makes **different structural choices** in exactly the
places this sweep is about.

---

## 0. What was checked

| # | Check | Method | Grade |
|---|---|---|---|
| F1 | Field/fieldset/type census | Parsed all 133 `module.json` | **Verified** |
| F2 | Reference graph | Static parse of `type: reference` | **Verified** |
| F3 | Missed relationships | Field name matched against module keys + domain aliases | **Verified list, triaged by hand** — the alias table produces candidates, not conclusions; 20 of 74 were rejected on inspection |
| F4 | Reference render path | Read `portal.ts` | **Verified** — two live defects, below |
| F5 | Filter/sort capability | Read `moduleRecordsFiltered` signature + `openModule` | **Verified** |
| F6 | Reference repo comparison | Downloaded and read all 7 `models.py` | **Verified** |

---

## 1. The field vocabulary was eleven words long

Across 1171 fields, the complete set of attributes in use:

```
name · label · type · fieldset · options · required · module ·
source_module · source_field · op · help
```

Every one is structural or presentational. **Nothing said what a number measures.** No `unit`, no
`default`, no `min`/`max`, no `placeholder`, no `unique`, no `readonly`, no `depends_on`. A field could
declare that it *is* a number and never what kind.

The tell was units living in field **names**: `elevation_ft`, `expected_life_years`, `ld_per_day`,
`temp_f`, `distance_mi`. A unit in a name is readable only by a human — it cannot be rendered beside an
input, appended to a cell, converted, or checked.

## 2. Two live defects in the reference renderer

**F4a — an unresolvable reference rendered as a working link.** `portal.ts` resolved reference columns
into an id→label map, then fell back to `String(v).slice(0, 8)` **as a clickable link**. Three
different situations took that path and all three looked identical to a resolved reference:

1. the target record was deleted since it was referenced;
2. the target lies past the resolve bound (below);
3. — the one that matters here — the value is **legacy free text** in a field that used to be `text`.

Truncating to 8 characters was the specific harm: short enough to look like an id, long enough to look
deliberate. Converting `coi.vendor` to a reference would have turned `"Acme Electrical Inc"` into a
link reading **`Acme Ele`** that opens nothing.

**F4b — reference resolution is capped at 500 records.** One fetch per referenced module, `limit: 500`.
On a project with 600 companies, company #550's references fall into the same fake-link path. Silent.

Both fixed: `refCell` now distinguishes *resolved* (link) from *unresolved id* (short id, not a link,
marked) from *not an id at all* (the value in full, marked as unlinked text). The bound is a named
constant because it is a correctness boundary, not a tuning parameter. The same 8-character truncation
existed a second time in `fmtCell` and is fixed there too.

## 3. Relationships — 74 strings that name a register

Only **98** reference fields existed across 133 modules; **69** modules had none at all. Meanwhile 74
text fields named a concept with its own register: `vendor`, `location`, `spec_section`, `system`,
`inspector`, `bidder`, `tenant`, `carrier`, `responsible`.

**This is precisely where the reference repo differs.** `django_emanager` uses ForeignKeys throughout —
`rfi.division → divisions`, `submittal.division → divisions`, `ticket.labor_rate → laborrates` (M2M),
`contracts.company → company`, `budget.project → projects`. Where Massing stores a trade name as text,
the reference app stores a link.

**They were not converted in place.** The codebase already contained the safe pattern in three places —
`investor` + `investor_company`, `lease` + `tenant_company`, `subcontract` + `vendor_company` — all
adding a reference *beside* the text field. That is the precedent this sweep followed rather than
inventing one: the text keeps rendering so no stored value breaks, the reference carries the link, and a
backfill can populate it. **54 reference fields added**, each adjacent to its text twin and sharing its
fieldset (both asserted, because a pair rendered in two different places is a pair nobody recognises).

**20 candidates were rejected**, and the reasons are the useful part:

- `permit.authority`, `entitlement.agency` → an AHJ is not a project company.
- `asset_register.manufacturer` → a product maker, not a project party.
- `risk.owner`, `assumption.owner`, `lessons_learned.owner` → a *person* accountable, and whether that
  is `contact` or `company` genuinely differs per module. Left alone rather than guessed.
- `photos`, `deficiencies`, `deliveries`, `assumptions`, `spec_sections` → **plural**. These are child
  lists, not single references. They need the `table` type (still unbuilt) and a reference would be
  wrong in a way that looks right.

## 4. Ideas worth taking from the reference repo

Beyond the FK habit, four structural ideas Massing lacks:

| `django_emanager` | Massing today |
|---|---|
| `ticket` links `labor_rate` (M2M), `material_rate` (M2M), `equipment_rate` (O2O) and totals them into `total_labor` / `total_material` / `total_equipment` / `total_cost` with `work_shifts`, `work_start`, `work_end` | `eticket` has 6 fields and **no link to any rate library**. The rate registers exist and nothing consumes them — the T&M ticket is where they should compose |
| `requisition` carries `coi` and `lienwaiver` on the record, plus `prev_amount` and `stored_materials` | `owner_invoice` has 5 fields, no lien-waiver or COI link, no stored materials — matches the G702 gap from the room audit |
| `contracts.contract_file` is a `FileField`; `submittal.submittal_file` too | 3 `file` fields exist system-wide; `prime_contract` and `submittal` have none |
| `exclusion_assumption` on `changeorder`, `contracts`, `ticket` — exclusions are first-class | only `bid_submission` carries inclusions/exclusions, as prose |

The `ticket` → rate-library composition is the sharpest of these and is now the top item for the next
pass: it is the same shape as the SOV-from-estimate gap — the data exists, the consumer exists, the
link does not.

## 5. Field typing

- **20 `*_pct` fields were typed `number`**, so 7.5% and 7.5 rendered identically and formatted with
  thousands separators. Retyped to `percent` (19 by suffix + `evm_snapshot.percent_complete`, which a
  suffix-only rule missed — the usual reason to widen a pattern rather than enumerate).
- **67 units declared**, moved *out of field names* and into the schema. Lossless: a unit was declared
  only where the name already stated it.
- **Four inferences were wrong and were caught by reading the output**, not by a test:
  `capital_plan.planned_year`, `fca_element.recommended_year`,
  `market_assumption.construction_start_year` are **calendar years, not durations** — the suffix rule
  labelled all three `yr`. And `prime_contract.ld_per_day` is dollars *per* day, not days. The gate now
  asserts those three carry no unit, so a future bulk pass cannot re-lose the distinction.

## 6. CRUD and filters

- **`list_columns`: 15 registers had none, 40 had two.** So the table was a title and a status chip — a
  list you must open every row of is not a register. Widened on **41** registers, **append-only**: the
  first attempt chose columns by type priority and silently dropped human-chosen ones like
  `bid_package.trade`, so it was redone to preserve every existing column and append.
- **A reference appeared in only 2 of 133 registers' columns** while 98 reference fields existed — the
  tool had the relationship and the table didn't show it. Now **32**.
- **Filtering is `q` + `state` only.** `moduleRecordsFiltered` accepts `{q, state, limit, offset}` and
  nothing else. On a 20-field register you cannot filter by discipline, vendor, cost code, or a date
  range; sorting is client-side over the fetched page only. **This is the largest remaining CRUD gap**
  and it is not addressed here — it needs a query parameter per filterable field plus a server-side
  sort, which is an API change, not a config change.

## 7. Result

| | before | after |
|---|---|---|
| reference fields | 98 | **152** |
| modules with no reference at all | 69 | **49** |
| `percent`-typed fields | 2 | **22** |
| fields declaring a unit | 0 | **67** |
| registers with fewer than 3 columns | 55 | **17** |
| registers surfacing a reference as a column | 2 | **32** |

`test_module_fields.py` holds each of these as a **floor**, not an equality — adding a module never
requires editing it, undoing the work fails it. It also asserts the pair-adjacency and shared-fieldset
rules, and the three calendar-year exceptions by name.

## 8. Not done — CLOSED 2026-07-31

All six items shipped. Kept with their outcomes rather than deleted, because what each one turned
into is more useful than the fact that it is finished.

| # | Item | Shipped as | What it actually turned out to be |
|---|---|---|---|
| 1 | Per-field filters + server-side sort | `MOD-FILTER` (#109) | The sort was the real defect: it ran in the browser over the fetched page, so "sort by amount" on a 500-row register ordered 200 rows and presented them as the largest. Nothing looked wrong; it was the wrong 200 rows |
| 2 | The `table` field type | `MOD-TABLE` (#111) | Shippable only because a **legacy string is preserved**, not rejected — 22 of these were textareas, so live records hold prose where rows are expected |
| 3 | Backfill the 54 references | `MOD-BACKFILL` (#113) | A refusal engine. Exact-match-only, unique-or-nothing, every skip reported. *An empty reference is visibly empty and gets filled; a wrong one resolves, opens a real record, shows a plausible name, and is never questioned* |
| 4 | `eticket` → rate libraries | `MOD-TOTALS` (#134) | The rate is **snapshot, not referenced** — re-pricing the library must not change what is already owed. And the workflow had three states *named* for signing with no `requires`, so a ticket reached `super_signed` unsigned |
| 5 | `min` / `max` / `placeholder` / `default` | `MOD-FIELDATTRS` | `default` is different in kind from the other three: it **writes a value nobody chose**. Four fields in 133 modules carry one, and the gate is a **ceiling** |
| 6 | Fieldsets on 62 modules | `MOD-FIELDSET` (#112) | Surfaced three modules non-contiguous since before the sweep, because `test_modules` checked contiguity for an *enumerated list of thirteen* |

**`readonly` was dropped rather than built.** It was listed here as a field attribute, but nothing in
the sweep found a field that needed one: a value the user must not edit is either computed (`rollup`,
or a table's `totals_into` target) or set by a workflow transition. A `readonly` flag would have been
a fourth way to say the same thing, and the first place it disagreed with the other three would have
been a bug nobody could locate.

### Still open, and genuinely so

**Nothing is. All three items in this section shipped between 2026-07-29 and 2026-07-31**, and each
is kept below with what it turned into, because that is more useful than the fact that it is done.
Two of the three turned up a defect underneath the item as written — a negative payment due, and a
demo corpus filing prose into GlobalId fields — which is the argument for working the list rather
than declaring it low-value.

- ~~**`sov` and `owner_invoice` as documents.**~~ **Shipped as `MOD-G702`.** The structural item was
  real — `owner_invoice` had five fields standing in for an AIA G702, and the continuation sheet was
  assembled on every read rather than stored. But looking for the missing fields turned up a **money
  bug** underneath it:

  `g703` retained each SOV line at that line's own `retainage_pct`; `g702` line 7 applied the global
  `DEFAULT_RETAINAGE` to the aggregate. Any contract not on the default made the two disagree. On a
  10% contract with $50,000 completed and nothing this period, **line 8 — current payment due — came
  out at −$2,500**, and `closeout.py` reads line 8 for the final-payment amount.

  **`test_cost.py` contains no assertion on line 7, line 8, or retainage at all.** It was not a weak
  test of this behaviour; it was structurally unable to see it. That is the shape worth remembering
  from this item, more than the fields that were added.

  The deeper fix is that an application is now a **document**: `POST /cost/pay-application` freezes
  the G703 sheet and lines 1-9 into an `owner_invoice`, and line 7 deducts what was actually
  certified - including a reduced architect certification - instead of reconstructing it from
  `completed_prev`, which moves whenever anyone edits an earlier period. `GET /cost/g702` stays a
  live view, because "where do we stand today" is a real question; it is just not a certificate.
- ~~**A `reference` column type for tables.**~~ **Shipped as `MOD-TABLEREF`.** It came off the
  exclusion list by MEETING the condition it was excluded over, not by deleting the sentence — and
  building it showed the condition was understated. Inside a `<select>`, an unresolvable id is not a
  bad label, it is **silent data loss**: a stored value matching no `<option>` leaves the control on
  the blank option, and the next save writes that blank over a link somebody made. Nothing errors,
  nothing is marked, and the evidence is gone. A fake link at least still contains the id.

  Two ordinary situations produce it — the target was deleted or lies past `REF_RESOLVE_LIMIT`, and
  the column used to be free text (`bid_package.spec_sections` held prose). Both now get an option
  of their own, marked and selected, so the row round-trips.

  `TABLE_COLUMN_TYPES` still refuses nested tables, rollups, files, signatures and multiselects, each
  for its own stated reason.
- ~~**The element link (`§5 T4`).**~~ **Shipped as `MOD-GUID`.** Three defects, and the second was
  the one worth having:
  1. All three GlobalId fields were plain `text`, so `"TBD"`, a truncated paste and a *transient
     viewer id* — the thing the repo's first non-negotiable forbids by name — were indistinguishable
     from a real one. The rule was prose, and prose cannot fail.
  2. **Two stores held one fact.** `element_facts._claims` checked `element_guids` **or**
     `data["guid"]`, so a record could be anchored to element A by its column and element B by its
     field, with each consumer correct about a different element. It also read only the *singular*
     `guid`, so `material_request.guids` and `prefab_kit.frozen_guids` never matched at all.
  3. `parse_guids` was a second reader of the same list format, defined independently.

  **This item was written once and pulled, for a reason that turned out to be wrong.** The stated
  reason was that it had no legacy story — that live records holding a malformed id would become
  un-saveable. They would not: `update_record` validates only the fields in the patch, so an
  untouched bad value keeps saving. The blast radius was also given as ~25 test files; it was **one**
  (`test_verified_progress`), the rest being element-level fixtures that never reach the module
  engine. Both figures came from pattern-matching rather than reading, which is the same failure the
  work itself is about: a confident answer where the honest one was "I have not checked". The claim
  is now `test_guid_integrity` §2 rather than a belief.

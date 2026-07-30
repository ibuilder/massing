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

## 8. Not done

1. **Per-field filters and server-side sort** (§6) — the biggest remaining CRUD gap.
2. **The `table` field type** — still the blocker for the 22 list-in-a-textarea fields and for `sov`,
   `estimate`, `bid_submission` being documents rather than rows.
3. **Backfilling the 54 new reference fields** from their text twins — needs a matcher and a review
   step; a wrong auto-link is worse than an empty one.
4. **`eticket` → rate libraries** (§4), the highest-value relationship still missing.
5. **`default`, `min`/`max`, `placeholder`, `readonly`** — the rest of the field vocabulary.
6. **Fieldsets on the remaining 62 modules** with none.

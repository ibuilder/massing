# Authoring a module (no code required)

A **module** is a record type — RFIs, submittals, punch items, leases, anything with a form, a list,
and a workflow. Every module is one folder of plain JSON under `services/api/modules/<key>/`. There is
no code to write: you add a `module.json`, the API creates a `mod_<key>` table on next start, and the
web app renders the form, the list, the detail view, search, import, and the workflow buttons for you.

If you can fill out a form, you can author a module. This guide is the whole thing.

## 1. The smallest possible module

Create `services/api/modules/site_visit/module.json`:

```json
{
  "key": "site_visit",
  "name": "Site Visits",
  "section": "Field",
  "ref_prefix": "SV",
  "title_field": "subject",
  "fields": [
    { "name": "subject", "label": "Subject", "type": "text", "required": true },
    { "name": "visited_on", "label": "Date", "type": "date" },
    { "name": "notes", "label": "Notes", "type": "textarea" }
  ]
}
```

Restart the API. You now have a **Site Visits** module: a create form, a searchable/paginated list,
record detail, CSV/Excel import, and auto-numbered references (`SV-0001`, `SV-0002`, …).

- `key` — lowercase, letters/numbers/underscore. This is the URL slug and the table name (`mod_site_visit`). **Never rename a key after records exist** (it would orphan the table).
- `name` — plural, human label shown in the nav.
- `section` — which nav group it appears under (existing ones: Engineering, Field, Cost, Schedule, Quality, Closeout, Real Estate, …). A new name creates a new group.
- `ref_prefix` — the auto-number prefix.
- `title_field` — which field shows as the record's title. Must be one of your `fields`.

## 2. Fields

Each field is `{ "name", "label", "type", … }`. `name` is the stored key (don't rename once in use);
`label` is what the user sees.

**Every field type the platform accepts is listed below.** This table is not a summary — it is the
complete set, and `test_docs_module_schema.py` fails the build if it drifts from
`module_schema.FIELD_TYPES`. If a type is not here, the loader will refuse it.

| `type` | Renders as | Requires / accepts |
|---|---|---|
| `text` | single-line input | |
| `textarea` | multi-line input | |
| `number` | numeric input | `unit` |
| `currency` | money input | `unit`. Use this, not `number`, for money |
| `percent` | numeric input, shown with `%` | `unit`. Use this, not `number`, for any percentage |
| `date` | date picker | stored ISO `YYYY-MM-DD` |
| `checkbox` | tick box | |
| `email` | email input | |
| `phone` | telephone input | |
| `select` | dropdown | **needs** `options: ["A","B",…]` |
| `multiselect` | multi-pick | **needs** `options` |
| `reference` | picker of another module's records | **needs** `module: "<other_key>"` |
| `table` | repeating line-item grid | **needs** `columns`; accepts `total_column`. See §2.3 |
| `file` | file attachment | |
| `signature` | typed/drawn signature capture | |
| `rollup` | read-only aggregate from a related module | `source_module`, `source_field`, `op`. See §4 |

Optional on **any** field: `"required": true`, `"description": "hint text"`, `"fieldset": "Group"`.

### 2.1 `unit` — say what a number measures

A numeric field (`number`, `currency`, `percent`) may declare a `unit`. It renders beside the input and
after the value in a table cell.

```json
{ "name": "expected_life", "label": "Expected life", "type": "number", "unit": "yr" }
```

**Put the unit here, not in the field name.** `elevation_ft` encodes its unit somewhere only a human
can read — it cannot be rendered next to an input, appended to a cell, converted, or checked. A `unit`
on a non-numeric field is refused.

A *calendar year* (2027) is a point in time, not a duration, and takes **no** unit. A *duration* in
years does.

### 2.2 `reference` — how modules relate

```json
{ "name": "location", "label": "Location", "type": "reference", "module": "location", "fieldset": "Links" }
```

The picker searches the target module; the value stored is that record's **id**. The register table
resolves it to `REF-001 · Title` and links through to the record.

**Converting an existing `text` field to `reference` is not safe.** Every stored string would become an
unresolvable id. The convention is **additive** — keep the text field and add a reference beside it:

```json
{ "name": "vendor",         "label": "Vendor",          "type": "text",      "fieldset": "Parties" },
{ "name": "vendor_company", "label": "Vendor (linked)", "type": "reference", "module": "company",
  "fieldset": "Parties" }
```

Recognised suffixes: `_company` · `_loc` · `_spec` · `_system` · `_contact` · `_package`. The pair
**must be adjacent and share a fieldset** — a pair rendered in two places is a pair nobody recognises —
and `test_module_fields.py` enforces it. `POST /projects/{pid}/modules/backfill-references` fills the
reference from the text by exact match; it refuses ambiguous ones rather than guessing.

### 2.3 `table` — line items

For anything that is a *list of rows* rather than one value: a schedule of values, bid unit prices,
crew by trade, witnesses.

```json
{
  "name": "line_items", "label": "Line items", "type": "table", "total_column": "amount",
  "columns": [
    { "name": "description", "label": "Description", "type": "text" },
    { "name": "qty",         "label": "Qty",         "type": "number" },
    { "name": "amount",      "label": "Amount",      "type": "currency" }
  ]
}
```

Column types are a **deliberate subset** — `checkbox` · `currency` · `date` · `number` · `percent` ·
`select` · `text`. No nested table, no rollup, no file, no signature, no reference: each needs
per-record machinery a repeating row has no room for. A column accepts `label`, `required`, `options`
(for `select`), `unit`, `width`.

`total_column` must name a column that exists **and is numeric**. The register cell shows a summary
(`3 lines · $118,260`) rather than the grid.

**`totals_into`** writes that sum into a sibling numeric field on every write:

```json
{ "name": "labor_total", "label": "Labor", "type": "currency" },
{ "name": "labor_lines", "label": "Labor", "type": "table",
  "total_column": "amount", "totals_into": "labor_total", "columns": [ … ] }
```

Use it when an engine or report reads a single number that the rows are the evidence for — an eTicket
itemises labour but `tm.summarize` reads `labor_total`. The lines win: a hand-typed total cannot
contradict them, and a `PATCH` touching only the rows still moves the total. The target must exist and
be numeric.

**Snapshot, do not reference, a rate.** A line that records work done at an agreed rate stores that
rate. If it pointed at the rate library, re-pricing the library would retroactively change what is
owed for work already done — an accounting error, not a feature. This is also why `reference` is not a
column type.

**Do not use a `textarea` for a list.** Prose cannot be summed, filtered, or read by the engines.

## Bounds, hints and defaults

`min` / `max` (numeric only) are enforced **server-side** in `validate_record`, not just rendered as
input attributes — an HTML `min` is advice to one browser and nothing to a CSV import, an integration
or a script, which is how out-of-range values actually arrive.

A bound that rejects a real value is worse than no bound: it makes the honest number un-enterable and
pushes it somewhere unvalidated. `percent` means *proportion*, not *0..100* — an IRR is negative on a
losing deal and over 100% on a fast one, and escalation is negative under deflation. Bound a
percentage only when the quantity genuinely cannot leave the range.

`placeholder` is hint text inside an empty box, so it is rejected on types that have no box (select,
checkbox, table, reference, …) rather than declared and silently never rendered.

**`default` is different in kind from the other three, and is deliberately rare.** They constrain or
explain a value the user supplies; a default **writes a value nobody chose**. Default `retainage_pct`
to 10 and every record on a 5% job carries the wrong number — formatted correctly, in the right
field, looking exactly like something somebody decided.

Use it only where the value is a fact about the **record**, never a **policy**:

```json
{ "name": "report_date", "type": "date", "default": "@today" }
```

`@today` resolves on both sides — the form shows the date about to be saved, the server fills it for
any caller that never opened a form. Applied on **create only**: re-filling on update would make
"empty" unreachable and a user's clearing look like it failed. An explicit `0` is an answer and
survives. `test_field_attrs.py` caps the number of defaulted fields — the only **ceiling** in the
module gates, because here the risk runs the other way.

## 3. Workflow (states + buttons)

Add a `workflow` to give records a lifecycle (draft → submitted → answered → closed). Each transition
becomes a button; `initial` is the state new records start in.

```json
"workflow": {
  "initial": "draft",
  "states": ["draft", "open", "answered", "closed"],
  "transitions": [
    { "from": "draft",  "to": "open",     "action": "submit",  "party": ["GC"] },
    { "from": "open",   "to": "answered", "action": "respond", "party": ["Consultant"], "requires": ["response"] },
    { "from": "answered", "to": "closed", "action": "close" }
  ]
}
```

Each transition is `{ "from", "to", "action" }` — `action` is the verb (it becomes the button); add an
optional `"party"` array to restrict who may click it (the record's party gating), and `"requires"` to
gate it on fields.

- **Terminal ("done") states are derived, not declared:** any state with no outgoing transition
  (here, `closed`) is treated as done and drops out of the overdue / due-soon feeds and open counts.
  So make sure your closed/void/rejected states have no transition leaving them — don't add a
  `terminal` key (there isn't one).
- `requires` on a transition gates the button until those fields are filled (e.g. you can't
  **respond** to an RFI until `response` has a value). Names must be real fields.

## 4. Lists, search, due dates, pins

- `"list_columns": ["subject", "status", "visited_on"]` — which columns the table shows (defaults to
  the title + status). Every name must be a real field.
- Search (the top search box and ⌘K) filters your text fields in SQL automatically — nothing to wire.
- **Due dates are automatic by naming convention:** give the module a `date` field named `due_date`
  (or `response_due`, `need_by`, or `due`) and its open records feed the **overdue / due-soon**
  dashboard and the saved-search alerts — no extra config. A record counts as open until it reaches a
  terminal (no-outgoing-transition) state.
- `"pinnable": true` — lets a record be pinned to a spot in the 3D model (BCF-style), like RFIs.
- `"workspace": "construction"` or `"developer"` — tags which of the two portals it belongs to.
- **Rollups** are a *field type*, not a top-level key: add a field of `"type": "rollup"` that counts or
  sums records in a related module. Shape:
  ```json
  { "name": "warranty_count", "label": "# warranties", "type": "rollup",
    "source_module": "warranty", "source_field": "name", "op": "count" }
  ```
  `op` is `count` or `sum` (sum a numeric `source_field`). Copy from `asset_register` or `daily_report`.

### 4.1 `fieldset` — sections on the form, and the one rule that bites

`"fieldset": "Money"` groups fields under a heading. Two rules:

- **Fields sharing a fieldset must be adjacent in the `fields` array.** The renderer emits one heading
  per *run*, so an interleaved fieldset draws its heading twice. This is a renderer constraint, not a
  style preference, and `test_modules.py` fails the build on it — for every module, not a list of them.
- **All or nothing.** Either every non-rollup field has a fieldset or none does. A three-field lookup
  table legitimately has none; a half-grouped form renders an unlabelled group.

`rollup` fields take no fieldset — they are computed and never rendered as inputs.

The core registers use: **Identity · Classification · Parties · Dates · Money · Quantities · Status ·
Links · Notes**. Reuse them unless your register genuinely needs its own vocabulary.

### 4.2 `tools` — point a register at the panel that operates on it

A register renders a table, a form and a status chip. `tools` is how it says what it can *do*:

```json
"tools": [
  { "dest": "__evm__", "label": "Earned value" },
  { "dest": "__budget__", "label": "Budget" }
]
```

`dest` is a first-class destination key (`__evm__`, `__operations__`, `__aiassist__`, …). `label` is
the button text. `scope` is `register` (default). An unknown `dest` renders nothing rather than a dead
button, and `moduleTools.test.ts` fails the build if it does not resolve.

### 4.3 Where a module appears

`section` decides the nav group; the **room** is derived from the section by one table
(`rooms.ROOM_OF_SECTION`), so a new section must be given a room deliberately — an unmapped section is
a hard failure, never a default, because a module with no room is one nobody can reach.

The seven rooms: **Deal · Design · Planning · Schedule · Cost · Work · Operate**.

## 5. Validate before you ship

The test suite validates **every** `module.json` on each run, so a typo fails the build instead of
breaking the app at runtime. Run it after editing:

```bash
cd services/api
PYTHONPATH=src ./.venv/Scripts/python.exe run_tests.py     # runs test_module_config.py among others
```

`test_module_config.py` catches: duplicate field names, a `reference` pointing at a module that
doesn't exist, a `select`/`multiselect` with no options, unknown field types, `title_field` /
`list_columns` naming a field that doesn't exist, and workflow `initial` / transition states or
`requires` that reference something undefined. Green = your module is well-formed.

## 6. Look at a real one

The built-in modules are the best templates — copy the closest match and edit:

- `services/api/modules/rfi/` — fields + fieldsets + a full workflow with `requires` gating.
- `services/api/modules/daily_report/` — many field types + rollups.
- `services/api/modules/lease/` — Real Estate workspace + references.

## 7. The API is self-documenting

Everything the web app does is a plain REST call. Browse and try every endpoint live at
**`/docs`** on the running API (FastAPI's interactive Swagger UI) — e.g. `http://localhost:8000/docs`.
Your new module shows up there automatically under `/projects/{pid}/modules/site_visit`.

---

See also: [deploy.md](deploy.md) (running + configuring the stack), [operations.md](operations.md)
(day-2 operator runbook).

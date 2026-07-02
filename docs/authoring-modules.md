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
`label` is what the user sees. Optional on any field: `"required": true`, `"description": "hint text"`,
`"fieldset": "Group name"` (groups fields into sections on the form).

| `type` | Renders as | Notes |
|---|---|---|
| `text` | single-line input | |
| `textarea` | multi-line input | |
| `number` | numeric input | |
| `currency` | money input | formatted as currency (use this instead of a plain number for money) |
| `date` | date picker | stored ISO `YYYY-MM-DD` |
| `select` | dropdown | needs `"options": ["A","B",…]` |
| `multiselect` | multi-pick | needs `"options"` |
| `reference` | picker of another module's records | needs `"module": "<other_key>"` |
| `rollup` | read-only aggregate from a related module | see §4 |
| `signature` | typed/drawn signature capture | |

Example with a reference and a fieldset:

```json
{ "name": "rfi", "label": "Related RFI", "type": "reference", "module": "rfi", "fieldset": "Links" }
```

`reference` is how modules relate to each other (an RFI points at a `location`, a change order points
at a `prime_contract`, etc.). The picker searches the target module; the value stored is that record's
GUID, so links survive renames.

## 3. Workflow (states + buttons)

Add a `workflow` to give records a lifecycle (draft → submitted → answered → closed). Each transition
becomes a button; `initial` is the state new records start in.

```json
"workflow": {
  "initial": "draft",
  "states": ["draft", "submitted", "answered", "closed"],
  "transitions": [
    { "from": "draft",     "to": "submitted", "label": "Submit" },
    { "from": "submitted", "to": "answered",  "label": "Answer", "requires": ["response"] },
    { "from": "answered",  "to": "closed",    "label": "Close" }
  ]
}
```

- **Terminal ("done") states are derived, not declared:** any state with no outgoing transition
  (here, `closed`) is treated as done and drops out of the overdue / due-soon feeds and open counts.
  So make sure your closed/void/rejected states have no transition leaving them — don't add a
  `terminal` key (there isn't one).
- `requires` on a transition gates the button until those fields are filled (e.g. you can't **Answer**
  an RFI until `response` has a value). Names must be real fields.

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

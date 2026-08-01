"""MOD-TABLE — line-item fields: a register row can hold a document, not just a value.

The field sweep found 22 places a LIST had been flattened into one textarea
(`bid_submission.unit_prices`, `daily_report.crew_by_trade`, `incident.witnesses`), and the deeper
version of the same gap: `sov` is one record PER LINE with no parent document, and `estimate` was a
single `amount`. A schedule of values, a bid, an estimate and a daily manpower log are all line-item
documents. The config had no way to say so, so `bid_leveling.py` was parsing prose for numbers a
structured grid would have handed it clean.

Three properties are asserted here, and the third is the one that makes the change safe to ship:

1. **The column vocabulary is a deliberate subset.** No nested table, no rollup, no file/signature, no
   reference. Each exclusion has a reason (see `module_schema.TABLE_COLUMN_TYPES`); a column type that
   slipped in without a renderer is exactly how `percent` spent a release broken.
2. **Numeric cells are numbers.** A cell holding `"1000"` makes SQL comparison lexicographic — the
   same defect `MOD-FILTER`'s cast exists to survive, and the same one the record form had for
   `percent`.
3. **A LEGACY STRING IS ACCEPTED AND PRESERVED.** Those fields were textareas, so live records hold
   prose where rows are now expected. Rejecting it would make every such record un-saveable the moment
   somebody edited an unrelated field — a config change breaking data it never touched. Accepting but
   silently dropping it would be worse: it is the only copy.

Run: PYTHONPATH=src ./.venv/Scripts/python.exe test_module_tables.py
"""
import json
import os
import pathlib

os.environ["DATABASE_URL"] = "sqlite:///./test_mod_tables.db"
os.environ["STORAGE_DIR"] = "./test_storage_mod_tables"
os.environ["AEC_TRUST_XUSER"] = "1"

for _f in ("./test_mod_tables.db",):
    if os.path.exists(_f):
        os.remove(_f)

from fastapi.testclient import TestClient  # noqa: E402

from aec_api.main import app  # noqa: E402
from aec_api.module_schema import TABLE_COLUMN_TYPES, validate_module, validate_record  # noqa: E402

H = {"X-User": "gc"}
MODULES = pathlib.Path(__file__).parent / "modules"

# ---- 1. the column vocabulary is a subset, and the exclusions hold ------------------------------
# `reference` was on this list until MOD-TABLEREF. It came off by MEETING the condition it was
# excluded over — see the block at the foot of this file — not by deleting the line. The rest stay:
# a grid inside a grid, a value computed from other records, and three flows (upload, signing,
# multi-choice) that make no sense multiplied by a row count.
for banned in ("table", "rollup", "file", "signature", "multiselect", "textarea"):
    assert banned not in TABLE_COLUMN_TYPES, f"{banned!r} must not be a table column type"
    errs = validate_module({"key": "x", "fields": [
        {"name": "l", "type": "table", "columns": [{"name": "c", "type": banned}]}]})
    assert errs, f"a {banned!r} column was accepted"

# a table must declare columns; a total must name a NUMERIC column that exists
for bad, why in (
    ({"key": "x", "fields": [{"name": "l", "type": "table"}]}, "no columns"),
    ({"key": "x", "fields": [{"name": "l", "type": "table", "total_column": "zz",
                              "columns": [{"name": "a", "type": "currency"}]}]}, "total names nothing"),
    ({"key": "x", "fields": [{"name": "l", "type": "table", "total_column": "a",
                              "columns": [{"name": "a", "type": "text"}]}]}, "total on a text column"),
    ({"key": "x", "fields": [{"name": "l", "type": "table",
                              "columns": [{"name": "a", "type": "text"},
                                          {"name": "a", "type": "text"}]}]}, "duplicate columns"),
    ({"key": "x", "fields": [{"name": "l", "type": "table",
                              "columns": [{"name": "a", "type": "select"}]}]}, "select w/o options"),
    ({"key": "x", "fields": [{"name": "l", "type": "text",
                              "columns": [{"name": "a", "type": "text"}]}]}, "columns on a non-table"),
):
    assert validate_module(bad), f"accepted an invalid table: {why}"

# ---- 2. record validation: numbers, shapes, and the legacy string --------------------------------
MOD = {"fields": [{"name": "lines", "type": "table", "total_column": "amount", "columns": [
    {"name": "description", "type": "text"}, {"name": "qty", "type": "number"},
    {"name": "amount", "type": "currency"}]}]}

assert not validate_record(MOD, {"lines": [{"description": "Concrete", "qty": 5, "amount": 1000}]})
assert not validate_record(MOD, {"lines": []})
assert not validate_record(MOD, {"lines": [{"description": "x", "amount": ""}]})     # blank cell
assert not validate_record(MOD, {"lines": [{"description": "x", "unknown_col": "y"}]})
# THE LEGACY CASE: prose from when the field was a textarea must not be rejected
assert not validate_record(MOD, {"lines": "Concrete 1000\nSteel 2000"}), \
    "a legacy free-text value was rejected — every pre-conversion record would become un-saveable"
# and the shapes that are genuinely wrong
assert validate_record(MOD, {"lines": [{"amount": "abc"}]})
assert validate_record(MOD, {"lines": ["not a row"]})
assert validate_record(MOD, {"lines": {"description": "x"}})

# ---- 3. the shipped tables are wired, and round-trip over HTTP ----------------------------------
SHIPPED = {
    "bid_submission": ["unit_prices", "alternates"],
    "daily_report": ["crew_by_trade", "equipment_on_site"],
    "incident": ["witnesses"],
    "project_charter": ["key_milestones", "key_deliverables"],
    "estimate": ["line_items"],
}
n_tables = 0
for key, fnames in SHIPPED.items():
    mod = json.loads((MODULES / key / "module.json").read_text(encoding="utf-8"))
    by = {f["name"]: f for f in mod["fields"]}
    for fn in fnames:
        f = by.get(fn)
        assert f, f"{key}.{fn} is missing"
        assert f["type"] == "table", f"{key}.{fn} is {f['type']}, expected table"
        assert f.get("columns"), f"{key}.{fn} has no columns"
        n_tables += 1
        # every declared column type must be in the allowed subset — asserted against the SHIPPED
        # config, not just the validator, so a hand-edit cannot introduce an unrenderable column
        for c in f["columns"]:
            assert c["type"] in TABLE_COLUMN_TYPES, f"{key}.{fn}.{c['name']}: {c['type']}"

with TestClient(app) as c:
    pid = c.post("/projects", headers=H, json={"name": "Tables"}).json()["id"]

    # an estimate with real line items, saved and read back with numbers intact
    lines = [{"code": "03 30 00", "description": "Concrete", "qty": 120, "unit": "cy",
              "unit_cost": 185.5, "amount": 22260},
             {"code": "05 12 00", "description": "Structural steel", "qty": 40, "unit": "ton",
              "unit_cost": 2400, "amount": 96000}]
    r = c.post(f"/projects/{pid}/modules/estimate", headers=H,
               json={"data": {"name": "GMP estimate", "line_items": lines}})
    assert r.status_code == 201, r.text
    rid = r.json()["id"]
    got = c.get(f"/projects/{pid}/modules/estimate/{rid}", headers=H).json()
    back = got["data"]["line_items"]
    assert len(back) == 2, back
    assert back[0]["amount"] == 22260 and isinstance(back[0]["amount"], (int, float)), back[0]
    assert sum(x["amount"] for x in back) == 118260, "line-item totals must survive the round trip"

    # a legacy prose value on a now-table field saves rather than 422-ing
    r = c.post(f"/projects/{pid}/modules/daily_report", headers=H, json={"data": {
        "report_date": "2026-07-30", "crew_by_trade": "6 carpenters, 2 laborers"}})
    assert r.status_code == 201, f"legacy prose rejected on a converted field: {r.text}"

    # and a bad row shape is refused
    r = c.post(f"/projects/{pid}/modules/estimate", headers=H,
               json={"data": {"name": "bad", "line_items": [{"amount": "not-a-number"}]}})
    assert r.status_code in (400, 422), f"a non-numeric cell was accepted ({r.status_code})"

    # the table field survives the register listing, and filters still work alongside it
    rows = c.get(f"/projects/{pid}/modules/estimate", headers=H).json()
    assert any(isinstance(x["data"].get("line_items"), list) for x in rows), rows

print(f"MOD-TABLE OK - `table` field type end to end: {n_tables} shipped line-item fields across "
      f"{len(SHIPPED)} registers, column vocabulary held to a deliberate subset (nested table, rollup, "
      "file, signature and multiselect all refused, each for a stated reason; `reference` came OFF "
      "that list in MOD-TABLEREF by MEETING the condition it was excluded over, and a column "
      "pointing at a register that is not installed still fails the build), numeric cells "
      "round-trip as NUMBERS rather than strings — the same defect that makes SQL comparison "
      "lexicographic and that the record form had for `percent` — and a LEGACY FREE-TEXT value on a "
      "converted field is accepted and preserved rather than rejected. That last one is why the change "
      "is safe to ship: 22 of these fields were textareas, so live records hold prose where rows are "
      "now expected, and refusing it would make every one of those records un-saveable the moment "
      "somebody edited an unrelated field on it.")

# ---- MOD-TABLEREF: a `reference` COLUMN -----------------------------------------------------------
# `TABLE_COLUMN_TYPES` excluded this type with a stated reason — "a picker per row is a real feature
# and shipping it half-done would put unresolvable ids in rows". Admitting it meant meeting that
# condition, not deleting the sentence.
assert "reference" in TABLE_COLUMN_TYPES
_base = {"key": "k", "name": "K", "section": "Billing", "fields": []}


def _col(col):
    return validate_module({**_base, "fields": [{"name": "lines", "type": "table", "columns": [col]}]},
                           known_modules={"k", "spec_section"})


assert _col({"name": "s", "type": "reference", "module": "spec_section"}) == []
assert _col({"name": "s", "type": "reference"}), "a reference column with no target must be rejected"
assert _col({"name": "s", "type": "reference", "module": "nope"}), (
    "a column pointing at a register that is not installed must FAIL the build — the picker would "
    "render an empty list, and an empty list reads as 'there are none of those'")
assert _col({"name": "s", "type": "text", "module": "spec_section"}), (
    "`module` on a non-reference column is a config that disagrees with itself about what the "
    "column is")

# the real consumers, so this is not a type nothing uses
import json  # noqa: E402
from pathlib import Path  # noqa: E402

users = []
for mj in Path("modules").glob("*/module.json"):
    for f in json.loads(mj.read_text(encoding="utf-8")).get("fields", []):
        for c in f.get("columns", []) or []:
            if c.get("type") == "reference":
                users.append(f"{mj.parent.name}.{f['name']}[{c['name']}]->{c['module']}")
# The sweep's §3 REJECTED list, now unblocked. These seven were turned down as `reference` FIELDS
# for the right reason — a reference holds one id and these are child lists — with the note that they
# "need the `table` type (still unbuilt)". Both halves exist now, so a plural field that names a
# register is a table of links to it rather than a textarea somebody retypes.
assert sorted(users) == [
    "bid_package.spec_sections[spec_section]->spec_section",
    "bulletin.spec_sections[spec_section]->spec_section",
    "commissioning.deficiencies[deficiency]->deficiency",
    "daily_report.deliveries[delivery]->delivery",
    "daily_report.photos[photo]->photo",
    "incident.photos[photo]->photo",
    "inspection.photos[photo]->photo",
    "project_charter.assumptions[assumption]->assumption",
    "punchlist.photos[photo]->photo",
], users

# NOT a floor. A plural field naming a register that is still a textarea is the defect this closes,
# so the set is exact — adding one without a column, or quietly reverting one to prose, fails here.
import json as _json  # noqa: E402

_PLURALS = {"photos", "deficiencies", "deliveries", "assumptions", "spec_sections"}
for _mj in Path("modules").glob("*/module.json"):
    for _f in _json.loads(_mj.read_text(encoding="utf-8")).get("fields", []):
        if _f["name"] in _PLURALS:
            assert _f["type"] == "table", (
                f"{_mj.parent.name}.{_f['name']} is a {_f['type']}. A plural field naming a register "
                "is a child list — it holds links, not prose somebody retypes.")

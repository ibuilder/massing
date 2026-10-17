"""Unit tests for the module_schema Pydantic layer — proves it accepts a good module and rejects each
class of misconfig (so test_module_config's green light is meaningful, not vacuous).
Run: PYTHONPATH=src ./.venv/Scripts/python.exe test_module_schema.py"""
from aec_api.module_schema import validate_module, validate_record

GOOD = {
    "key": "widget", "name": "Widgets", "title_field": "subject",
    "list_columns": ["subject", "status"],
    "fields": [
        {"name": "subject", "label": "Subject", "type": "text", "required": True},
        {"name": "status", "label": "Status", "type": "select", "options": ["a", "b"]},
        {"name": "rfi", "label": "RFI", "type": "reference", "module": "rfi"},
    ],
    "workflow": {
        "initial": "draft", "states": ["draft", "done"],
        "transitions": [{"from": "draft", "to": "done", "action": "finish",
                         "party": "GC", "requires": ["subject"]}],
    },
}
KNOWN = {"widget", "rfi"}

# a valid module -> no problems; note party accepts a bare string
assert validate_module(GOOD, known_modules=KNOWN, folder="widget") == [], validate_module(GOOD, known_modules=KNOWN)


def _bad(mut):
    import copy
    d = copy.deepcopy(GOOD)
    mut(d)
    return validate_module(d, known_modules=KNOWN, folder="widget")


# each misconfig class produces at least one error, mentioning the culprit
def has(errs, needle):
    return any(needle in e for e in errs)


assert has(_bad(lambda d: d["fields"].append({"name": "subject", "type": "text"})), "duplicate"), "dup field"
assert has(_bad(lambda d: d["fields"].append({"name": "x", "type": "bogus"})), "type"), "bad type"
assert has(_bad(lambda d: d["fields"].append({"name": "y", "type": "select"})), "options"), "select w/o options"
assert has(_bad(lambda d: d["fields"].append({"name": "z", "type": "reference"})), "module"), "ref w/o target"
assert has(_bad(lambda d: d["fields"].append({"name": "w", "type": "reference", "module": "nope"})),
           "does not exist"), "ref bad target"
assert has(_bad(lambda d: d.update(title_field="ghost")), "title_field"), "bad title_field"
assert has(_bad(lambda d: d["list_columns"].append("ghost")), "list_column"), "bad list_column"
assert has(_bad(lambda d: d["workflow"].update(initial="ghost")), "initial"), "bad initial"
assert has(_bad(lambda d: d["workflow"]["transitions"][0].update(to="ghost")), "transition"), "bad transition to"
assert has(_bad(lambda d: d["workflow"]["transitions"][0].update(requires=["ghost"])), "non-existent field"), "bad requires"
assert has(_bad(lambda d: d.update(key="mismatch")), "folder name"), "key != folder"
# a missing required top-level key (key) is a structural error
assert validate_module({"name": "x"}, folder="x"), "missing key must error"

# validate_record: numeric fields reject non-numbers; select options are suggestions (NOT enforced);
# partial/empty/unknown values are tolerated.
_recmod = {"fields": [
    {"name": "amount", "type": "currency"},
    {"name": "pct", "type": "percent"},
    {"name": "discipline", "type": "select", "options": ["Structural", "MEP"]},
    {"name": "note", "type": "text"},
]}
assert validate_record(_recmod, {"amount": "1000", "pct": 12.5}) == []            # numeric strings ok
assert has(validate_record(_recmod, {"amount": "lots"}), "not a number"), "non-numeric money"
assert validate_record(_recmod, {"discipline": "Acoustics"}) == [], "select options are suggestions"
assert validate_record(_recmod, {"amount": "", "unknown": "x"}) == [], "empty + unknown tolerated"

# --- EXPIRY-UNDATED: a `date` field was declared and never validated -----------------------------
# 136 `date` fields across 87 of 139 modules, read by ~70 `fromisoformat` call sites, and
# `validate_record` checked numbers, table rows and GUIDs — not dates. `12/31/2026` went into
# `coi.expires`, a REQUIRED field, and every expiry window then skipped the record while the
# project-health banner printed "Compliance: no COI/permit expiries ✓" over it.
_datemod = {"key": "d", "name": "D", "fields": [{"name": "expires", "type": "date"},
                                                {"name": "note", "type": "text"}]}
assert validate_record(_datemod, {"expires": "2026-12-31"}) == [], "a plain ISO date"
assert validate_record(_datemod, {"expires": ""}) == [], "blank clears the field (partial PATCH)"
assert validate_record(_datemod, {"note": "12/31/2026"}) == [], "only `date` FIELDS are checked"
for _bad in ("12/31/2026", "1/5/2027", "31-12-2026", "Dec 31 2026", "TBD", "soon", True):
    assert has(validate_record(_datemod, {"expires": _bad}), "is not a date"), _bad
    assert has(validate_record(_datemod, {"expires": _bad}), "ISO-8601"), _bad

# THE LOAD-BEARING EQUIVALENCE: the validator must accept EXACTLY what the readers accept. A
# validator stricter than its readers refuses data that works; one looser leaves the defect in
# place. Every consumer in this service reads a stored date as `fromisoformat(str(v)[:10])`, so
# that is the rule here too — which is why a full timestamp passes.
import datetime as _dt  # noqa: E402

# `20261231` is in this list on purpose, and it is why the rule DEFERS rather than opining:
# `fromisoformat` accepts the basic ISO form `YYYYMMDD`, so every reader in this service already
# reads that value fine — and a hand-written "must look like YYYY-MM-DD" would have refused data
# that works. *The equivalence is not a convenience, it is the only way to be sure the validator
# and the readers agree.* (The int form passes too, since both sides go through `str(v)`.)
for _v in ("2026-12-31", "2026-11-02T00:00:00Z", "2026-01-05T23:59:59", "2026-02-29",
           "20261231", 20261231):
    _reader_ok = True
    try:
        _dt.date.fromisoformat(str(_v)[:10])
    except (TypeError, ValueError):
        _reader_ok = False
    _validator_ok = validate_record(_datemod, {"expires": _v}) == []
    assert _reader_ok == _validator_ok, (_v, _reader_ok, _validator_ok)
# ...including the ones BOTH must refuse: 2026-02-29 is not a date in a non-leap year, and the
# reader would raise on it just as loudly.
assert has(validate_record(_datemod, {"expires": "2026-02-29"}), "is not a date")

print("MODULE SCHEMA OK - accepts a valid module (party as bare string coerced); rejects duplicate "
      "fields, unknown types, select-without-options, reference-without/-bad-target, bad title_field / "
      "list_column / workflow initial / transition state / requires, and key!=folder; and (EXPIRY-UNDATED) "
      "a `date` field now refuses what no reader could parse, accepting exactly what "
      "`fromisoformat(str(v)[:10])` accepts")

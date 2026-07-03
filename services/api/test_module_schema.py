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

print("MODULE SCHEMA OK - accepts a valid module (party as bare string coerced); rejects duplicate "
      "fields, unknown types, select-without-options, reference-without/-bad-target, bad title_field / "
      "list_column / workflow initial / transition state / requires, and key!=folder")

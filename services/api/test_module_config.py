"""Module-config validator — guards every modules/*/module.json against the classes of misconfig
that break the config-driven CRUD UI (duplicate fields, references with no target, selects with no
options, title_field / list_columns pointing at non-existent fields, bad workflow transitions).
Run: PYTHONPATH=src ./.venv/Scripts/python.exe test_module_config.py"""
import json
from collections import Counter
from pathlib import Path

MOD = Path(__file__).resolve().parent / "modules"
FIELD_TYPES = {"text", "number", "currency", "date", "textarea", "select", "multiselect",
               "reference", "signature", "rollup", "checkbox", "email", "phone", "percent", "file"}

errors: list[str] = []
n = 0
for p in sorted(MOD.glob("*/module.json")):
    n += 1
    d = json.loads(p.read_text(encoding="utf-8"))
    key = d.get("key")
    assert key == p.parent.name, f"{p.parent.name}: key '{key}' != folder name"
    fields = d.get("fields", [])
    names = [f["name"] for f in fields]

    for nm, c in Counter(names).items():
        if c > 1:
            errors.append(f"{key}: duplicate field '{nm}' ({c}x)")
    for f in fields:
        if f.get("type") not in FIELD_TYPES:
            errors.append(f"{key}.{f.get('name')}: unknown field type '{f.get('type')}'")
        if f.get("type") == "reference" and not f.get("module"):
            errors.append(f"{key}.{f['name']}: reference field has no 'module' target")
        if f.get("type") in ("select", "multiselect") and not f.get("options"):
            errors.append(f"{key}.{f['name']}: {f['type']} field has no options")
        if f.get("type") == "reference" and f.get("module") and not (MOD / f["module"]).exists():
            errors.append(f"{key}.{f['name']}: reference target module '{f['module']}' does not exist")

    tf = d.get("title_field")
    if tf and tf not in names:
        errors.append(f"{key}: title_field '{tf}' is not a field")
    for c in d.get("list_columns", []):
        if c not in names:
            errors.append(f"{key}: list_column '{c}' is not a field")

    wf = d.get("workflow") or {}
    states = set(wf.get("states", []))
    if wf.get("initial") and wf["initial"] not in states:
        errors.append(f"{key}: workflow.initial '{wf['initial']}' not in states")
    for t in wf.get("transitions", []):
        for s in ("from", "to"):
            if t.get(s) and t[s] not in states:
                errors.append(f"{key}: transition {s} '{t[s]}' not in states")
        for req in t.get("requires", []):
            if req not in names:
                errors.append(f"{key}: transition '{t.get('action')}' requires non-existent field '{req}'")

assert not errors, f"{len(errors)} module-config issue(s):\n  " + "\n  ".join(errors)
print(f"MODULE CONFIG OK - {n} modules valid: no duplicate fields, references have existing targets, "
      "selects have options, title_field + list_columns + workflow states/transitions all reference "
      "real fields/states")

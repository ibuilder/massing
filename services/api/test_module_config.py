"""Module-config validator — guards every modules/*/module.json against the classes of misconfig
that break the config-driven CRUD UI (duplicate fields, references with no target, selects with no
options, title_field / list_columns pointing at non-existent fields, bad workflow transitions).

The rules live in `aec_api.module_schema` (a Pydantic layer) so the config test and the runtime loader
validate against the exact same definition. This test asserts every shipped module passes it.
Run: PYTHONPATH=src ./.venv/Scripts/python.exe test_module_config.py"""
from pathlib import Path

from aec_api.module_schema import validate_dir

MOD = Path(__file__).resolve().parent / "modules"

problems = validate_dir(MOD)
n = len({p.parent.name for p in MOD.glob("*/module.json")})

if problems:
    lines = [f"{len(problems)} module(s) with config issue(s):"]
    for folder, errs in sorted(problems.items()):
        for e in errs:
            lines.append(f"  {e}")
    raise AssertionError("\n".join(lines))

print(f"MODULE CONFIG OK - {n} modules valid (via module_schema.ModuleSchema): no duplicate fields, "
      "references have existing targets, selects have options, title_field + list_columns + workflow "
      "states/transitions all reference real fields/states")

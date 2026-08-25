"""R22-REPORT-BUILDER — group a module's records by a declared field and aggregate over them.

The entry called this "the substantive one" of four, and it is what separates a saved LIST from a
REPORT: before this, the only `group_by` anywhere in the module path was hardcoded to
`workflow_state` (`modules_query.py`, two call sites), so "cost by discipline" or "RFIs by month" had
no expression at all and the answer was an export into a spreadsheet.

**The load-bearing assertion here is the REFUSAL, and it has a twin.** SQLite sums text as zero and
returns a confident `0`, which a reader sees as *this project has none* rather than *you asked a
meaningless question*. So `sum` over a text field must 400 — and a `sum` over a real numeric field
must return the right number, or "it refuses" is satisfied by an implementation that refuses
everything.

The other property worth naming: field names are validated by `_resolve_field`, the SAME function the
filters and sort already use. `_json_text` interpolates a field name into a SQLite JSON path, so an
unvalidated name is an injection site rather than a typo — and a second validator here would be a
second answer to "what is a field".

Run: PYTHONPATH="src;../data/src" ./.venv/Scripts/python.exe test_module_aggregate.py
"""
from __future__ import annotations

import os

os.environ["DATABASE_URL"] = "sqlite:///./test_module_aggregate.db"
os.environ["STORAGE_DIR"] = "./test_storage_module_aggregate"
os.environ["IFC_DIR"] = "./test_ifc_module_aggregate"
os.environ.pop("AEC_RBAC", None)
for _f in ("./test_module_aggregate.db",):
    if os.path.exists(_f):
        os.remove(_f)

import sys  # noqa: E402
from pathlib import Path  # noqa: E402

sys.path.insert(0, "src")
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "data" / "src"))

from fastapi import HTTPException  # noqa: E402

from aec_api import modules, modules_query  # noqa: E402
from aec_api.db import Base, SessionLocal, engine  # noqa: E402
from aec_api.models import Project  # noqa: E402
from aec_api.modules_registry import load_registry  # noqa: E402

# The registry is populated from modules/*/module.json at startup, not at import. Without this the
# fixture search below finds nothing and every check reports "cannot say anything" — which is the
# right failure for an empty population, and the reason the first assertion exists at all.
load_registry()

FAILED: list[str] = []


def check(name: str, ok: bool, detail: object = "") -> None:
    print(("PASS  " if ok else "FAIL  ") + name + (f"   {detail}" if detail and not ok else ""))
    if not ok:
        FAILED.append(name)


Base.metadata.create_all(engine)
db = SessionLocal()
PID = "agg-proj"
db.add(Project(id=PID, name="Aggregate probe"))
db.commit()

# --- pick a real module with both a text and a numeric declared field ------------------------------
# Derived from the registry rather than hardcoded: a fixture naming a module that was renamed would
# fail as "aggregation is broken" instead of "the fixture is stale".
KEY = None
for key, mod in modules.REGISTRY.items():
    if key not in modules.TABLES:
        continue
    fields = mod.get("fields") or []
    texts = [f["name"] for f in fields if f.get("type") in (None, "text", "select")]
    nums = [f["name"] for f in fields if f.get("type") in ("number", "currency", "percent")]
    if texts and nums:
        KEY, TEXT_FIELD, NUM_FIELD = key, texts[0], nums[0]
        break
check("found a module with both a text and a numeric declared field", KEY is not None,
      "no module in the registry has both — this test cannot say anything")
if KEY is None:
    raise SystemExit(1)
print(f"      using module {KEY!r}: text={TEXT_FIELD!r} numeric={NUM_FIELD!r}")

#: The module's OTHER required fields, filled generically. Derived rather than hardcoded for the same
#: reason the module itself is: a fixture that names fields would break as "aggregation is broken" the
#: next time a module gains a required field.
MOD = modules.REGISTRY[KEY]
_REQUIRED = [f for f in (MOD.get("fields") or [])
             if f.get("required") and f["name"] not in (TEXT_FIELD, NUM_FIELD)]


def _filler(f: dict):
    t = f.get("type")
    if t in ("number", "currency", "percent"):
        return 1
    if t == "select" and f.get("options"):
        return f["options"][0]
    return "x"


def _row(**vals) -> dict:
    return {**{f["name"]: _filler(f) for f in _REQUIRED}, **vals}


for data in ({TEXT_FIELD: "alpha", NUM_FIELD: 100},
             {TEXT_FIELD: "alpha", NUM_FIELD: 50},
             {TEXT_FIELD: "beta", NUM_FIELD: 7}):
    # POST-create wraps the field map in {"data": …}; only PATCH takes it flat. Getting this
    # wrong reports as "missing required field(s)", which reads like a bad fixture.
    modules.create_record(db, KEY, PID, {"data": _row(**data)}, actor="tester", party=None)
db.commit()

# --- grouping -------------------------------------------------------------------------------------
res = modules.aggregate(db, KEY, PID, group_by=TEXT_FIELD)
by = {g["key"]: g["count"] for g in res["groups"]}
check("groups by a declared text field and counts each group",
      by.get("alpha") == 2 and by.get("beta") == 1, res)

res = modules.aggregate(db, KEY, PID, group_by=TEXT_FIELD, agg="sum", agg_field=NUM_FIELD)
vals = {g["key"]: g["value"] for g in res["groups"]}
check("SUMS A NUMERIC FIELD PER GROUP — the number a report is actually for",
      float(vals.get("alpha") or 0) == 150.0 and float(vals.get("beta") or 0) == 7.0, res)

res = modules.aggregate(db, KEY, PID, group_by=TEXT_FIELD, agg="avg", agg_field=NUM_FIELD)
avgs = {g["key"]: float(g["value"] or 0) for g in res["groups"]}
check("...and averages it", abs(avgs.get("alpha", 0) - 75.0) < 1e-9, res)

# --- THE REFUSAL, and its twin --------------------------------------------------------------------
try:
    modules.aggregate(db, KEY, PID, group_by=TEXT_FIELD, agg="sum", agg_field=TEXT_FIELD)
    refused, why = False, "no error raised"
except HTTPException as e:
    refused, why = e.status_code == 400, f"{e.status_code} {e.detail}"
check("SUM OVER A TEXT FIELD IS REFUSED — not answered with a confident 0", refused, why)
check("  ...and the refusal names the declared type, so the caller can act on it",
      refused and "numeric" in why.lower(), why)
# The twin. Without it, an implementation that refuses EVERY sum satisfies the line above.
check("  ...while sum over the NUMERIC field still works, so the refusal is not blanket",
      float(sum(float(g["value"] or 0) for g in
                modules.aggregate(db, KEY, PID, group_by=TEXT_FIELD, agg="sum",
                                  agg_field=NUM_FIELD)["groups"])) == 157.0)

# --- field names are validated by the SAME resolver the filters use --------------------------------
for bad_kwargs in ({"group_by": "not_a_field"},
                   {"group_by": TEXT_FIELD, "agg": "sum", "agg_field": "not_a_field"}):
    try:
        modules.aggregate(db, KEY, PID, **bad_kwargs)
        ok, detail = False, f"{bad_kwargs} was accepted"
    except HTTPException as e:
        ok, detail = e.status_code == 400, f"{e.status_code} {e.detail}"
    check(f"an undeclared field is refused ({sorted(bad_kwargs)[0]})", ok, detail)

try:
    modules.aggregate(db, KEY, PID, group_by=TEXT_FIELD, agg="median", agg_field=NUM_FIELD)
    ok = False
except HTTPException as e:
    ok = e.status_code == 400
check("an unknown aggregate function is refused", ok)

try:
    modules.aggregate(db, KEY, PID, group_by=TEXT_FIELD, agg="sum")
    ok = False
except HTTPException as e:
    ok = e.status_code == 400
check("sum with no field is refused rather than silently counting", ok)

# --- the same filters the list route takes --------------------------------------------------------
res = modules.aggregate(db, KEY, PID, group_by=TEXT_FIELD,
                        filters=[(TEXT_FIELD, "eq", "alpha")])
check("honours the register's own per-field filters, so a report and its list agree",
      [g["key"] for g in res["groups"]] == ["alpha"] and res["groups"][0]["count"] == 2, res)

# --- the cap is reported, not silently applied ----------------------------------------------------
check("a small result is NOT marked truncated", modules.aggregate(
    db, KEY, PID, group_by=TEXT_FIELD)["truncated"] is False)
_saved = modules_query.MAX_GROUPS
try:
    modules_query.MAX_GROUPS = 1
    capped = modules.aggregate(db, KEY, PID, group_by=TEXT_FIELD)
    # Two distinct groups exist and the cap is 1, so the answer is necessarily partial. A short list
    # that does not say so reads as the whole answer — the failure this flag exists to prevent.
    check("OVER THE CAP IT SAYS SO, rather than returning a short list that looks complete",
          capped["truncated"] is True and len(capped["groups"]) == 1
          and capped["max_groups"] == 1, capped)
finally:
    modules_query.MAX_GROUPS = _saved

db.close()
for _f in ("./test_module_aggregate.db",):
    if os.path.exists(_f):
        try:
            os.remove(_f)
        except OSError:
            pass

if FAILED:
    print("FAILED:", ", ".join(FAILED))
    raise SystemExit(1)
print("test_module_aggregate OK")

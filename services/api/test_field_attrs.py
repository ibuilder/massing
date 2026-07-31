"""MOD-FIELDATTRS — the rest of the field vocabulary: min, max, placeholder, default.

The sweep found the whole vocabulary was eleven attributes and every one was structural or
presentational. `unit` closed part of that; this closes the rest. Three of the four merely CONSTRAIN
or EXPLAIN a value the user supplies. The fourth is different in kind and most of this file is about
it.

**A `default` writes a value nobody chose.** Default `retainage_pct` to 10 and every record on a 5%
job silently carries the wrong number — formatted correctly, in the right field, looking exactly like
something somebody decided. That is this codebase's signature defect, the plausible answer for the
missing case, and it is why only FOUR fields in 133 modules carry a default: each is a fact about the
*record* (a daily report is filed for today) rather than a *policy* (retainage is 10%).

**A bound must be enforced where the data enters, not where it is typed.** An HTML `min` is advice to
one browser and nothing at all to a CSV import, an integration or a script — which is how
out-of-range values actually arrive. Enforced in `validate_record`.

**A bound that rejects a real value is worse than no bound**: it makes the honest number un-enterable
and pushes it somewhere unvalidated. Three of the 22 percent fields are asserted to be UNBOUNDED for
exactly that reason.

Run: PYTHONPATH=src ./.venv/Scripts/python.exe test_field_attrs.py
"""
import json
import os
import pathlib

os.environ["DATABASE_URL"] = "sqlite:///./test_field_attrs.db"
os.environ["STORAGE_DIR"] = "./test_storage_field_attrs"
os.environ["AEC_TRUST_XUSER"] = "1"

for _f in ("./test_field_attrs.db",):
    if os.path.exists(_f):
        os.remove(_f)

from fastapi.testclient import TestClient  # noqa: E402

from aec_api.main import app  # noqa: E402
from aec_api.module_schema import validate_module, validate_record  # noqa: E402
from aec_api.modules import apply_defaults  # noqa: E402
from aec_api.timeutil import utc_today  # noqa: E402

H = {"X-User": "gc"}
MODULES = pathlib.Path(__file__).parent / "modules"

# ---- 1. the misconfigurations that must be refused ----------------------------------------------
for label, mod in (
    ("min on a text field", {"key": "x", "fields": [{"name": "a", "type": "text", "min": 0}]}),
    ("inverted range", {"key": "x", "fields": [{"name": "a", "type": "number", "min": 10, "max": 5}]}),
    ("placeholder with nowhere to render",
     {"key": "x", "fields": [{"name": "a", "type": "select", "options": ["y"], "placeholder": "hi"}]}),
    ("default on a signature", {"key": "x", "fields": [{"name": "a", "type": "signature", "default": "s"}]}),
    ("default below its own min",
     {"key": "x", "fields": [{"name": "a", "type": "number", "min": 5, "default": 1}]}),
    ("default outside the options",
     {"key": "x", "fields": [{"name": "a", "type": "select", "options": ["y"], "default": "z"}]}),
    ("non-numeric default on a number",
     {"key": "x", "fields": [{"name": "a", "type": "number", "default": "abc"}]}),
):
    assert validate_module(mod, known_modules={"x"}), f"accepted: {label}"

# a default REFERENCE would invent a link and a default SIGNATURE would forge an attestation —
# neither is a value a config file gets to supply
assert validate_module({"key": "x", "fields": [
    {"name": "b", "type": "text"},
    {"name": "a", "type": "reference", "module": "x", "default": "z"}]}, known_modules={"x"})

# ---- 2. bounds are enforced on the VALUE, not just rendered --------------------------------------
MOD = {"fields": [{"name": "p", "type": "percent", "min": 0, "max": 100},
                  {"name": "q", "type": "number", "min": 0}]}
assert not validate_record(MOD, {"p": 50, "q": 0})
assert validate_record(MOD, {"p": 5000})          # a percentage of 5000 rendered as "5,000%" happily
assert validate_record(MOD, {"p": -1})
assert validate_record(MOD, {"q": -3})
assert not validate_record(MOD, {"p": ""})        # blank is still "not answered", not a violation

# ---- 3. defaults fill only what was not answered, and only on create -----------------------------
DMOD = {"fields": [{"name": "d", "type": "date", "default": "@today"},
                   {"name": "n", "type": "number", "default": 5},
                   {"name": "s", "type": "text"}]}
filled = apply_defaults(DMOD, {})
assert filled["d"] == utc_today().isoformat(), filled
assert filled["n"] == 5
# a caller that said something keeps it — INCLUDING a zero, which is an answer, not an absence
assert apply_defaults(DMOD, {"n": 0})["n"] == 0, "a default overrode an explicit 0"
assert apply_defaults(DMOD, {"n": 99})["n"] == 99
# a field with no default is not invented
assert "s" not in apply_defaults(DMOD, {})

with TestClient(app) as c:
    pid = c.post("/projects", headers=H, json={"name": "Attrs"}).json()["id"]

    # ---- 4. the default reaches a caller that never opened a form ---------------------------------
    r = c.post(f"/projects/{pid}/modules/daily_report", headers=H,
               json={"data": {"weather": "Clear"}})
    assert r.status_code == 201, r.text
    rid = r.json()["id"]
    got = c.get(f"/projects/{pid}/modules/daily_report/{rid}", headers=H).json()["data"]
    assert got["report_date"] == utc_today().isoformat(), got
    # ...and it satisfies `required` rather than failing it: report_date is a required field, so the
    # default has to be applied BEFORE the required check or an API create would 422 on a field the
    # config says it can fill itself.

    # ---- 5. AN UPDATE NEVER RE-FILLS ---------------------------------------------------------------
    # The case create-only exists for: re-filling on update makes "empty" unreachable, and the user's
    # clearing look like it silently failed.
    c.patch(f"/projects/{pid}/modules/daily_report/{rid}", headers=H, json={"report_date": ""})
    got = c.get(f"/projects/{pid}/modules/daily_report/{rid}", headers=H).json()["data"]
    assert got["report_date"] == "", f"an update re-applied the default: {got['report_date']!r}"

    # ---- 6. an out-of-range value is refused over HTTP, not merely un-typeable --------------------
    r = c.post(f"/projects/{pid}/modules/prime_contract", headers=H,
               json={"data": {"name": "PC", "retainage_pct": 500}})
    assert r.status_code == 422, f"a 500% retainage was accepted ({r.status_code})"
    r = c.post(f"/projects/{pid}/modules/prime_contract", headers=H,
               json={"data": {"name": "PC", "retainage_pct": 10}})
    assert r.status_code == 201, r.text

# ---- 7. THE SHIPPED BOUNDS, INCLUDING THE FIELDS DELIBERATELY LEFT UNBOUNDED ---------------------
mods = {p.parent.name: json.loads(p.read_text(encoding="utf-8"))
        for p in MODULES.glob("*/module.json")}
fields = {(k, f["name"]): f for k, m in mods.items() for f in m.get("fields", [])}

pct = [(k, f) for (k, n), f in fields.items() if f["type"] == "percent"]
bounded = [f for _k, f in pct if f.get("min") == 0 and f.get("max") == 100]
assert len(bounded) >= 18, f"only {len(bounded)} percent fields are bounded 0..100"

# `percent` says "this is a proportion", NOT "this is between 0 and 100". These three are unbounded
# on purpose, and naming them here stops a future bulk pass from "fixing" them: a bound that rejects a
# real value makes the honest number un-enterable and pushes it somewhere unvalidated.
for key, fname, why in (
    ("design_option", "irr_pct", "an IRR is negative on a losing deal and exceeds 100% on a fast one"),
    ("market_assumption", "escalation_override_pct", "escalation is negative under deflation"),
    ("lease", "escalation_pct", "a step-down lease escalates negatively"),
):
    f = fields[(key, fname)]
    assert "min" not in f and "max" not in f, f"{key}.{fname} was bounded — {why}"

# quantities that cannot be negative carry min 0; things that CAN go negative must not
neg_ok = [(k, n) for (k, n), f in fields.items()
          if f.get("min") == 0 and any(w in n for w in ("variance", "float", "adjust", "delta"))]
assert not neg_ok, f"fields that can legitimately go negative were bounded at 0: {neg_ok}"
zeroed = [1 for f in fields.values() if f.get("min") == 0]
assert len(zeroed) >= 100, f"only {len(zeroed)} fields carry a non-negative bound"

# DEFAULTS ARE RARE ON PURPOSE. This is a CEILING, not a floor — the only such assertion in the
# module gates, because the risk here runs the other way. Every default is a value nobody chose, and
# the temptation to add "helpful" ones is exactly what makes a register quietly wrong.
defaulted = sorted(f"{k}.{n}" for (k, n), f in fields.items() if "default" in f)
assert len(defaulted) <= 8, (
    f"{len(defaulted)} fields carry a default: {defaulted}. Each writes a value nobody chose, and a "
    "wrong one is invisible because it looks deliberate. Add one only when the value is a fact about "
    "the RECORD (a daily report is filed today), never a policy (retainage is 10%).")
for d in defaulted:
    assert d.endswith(("_date", ".date")), f"{d}: the only safe defaults so far are dates-of-record"

print(f"MOD-FIELDATTRS OK - min/max/placeholder/default complete the field vocabulary. "
      f"{len(bounded)} percent fields bounded 0..100 and {len(zeroed)} quantities held non-negative, "
      "enforced in validate_record rather than as HTML attributes — an HTML `min` is advice to one "
      "browser and nothing to a CSV import, an integration or a script, which is how out-of-range "
      "values actually arrive. THREE percent fields are asserted UNBOUNDED by name (irr_pct, "
      "escalation_override_pct, lease.escalation_pct): `percent` means proportion, not 0..100, and a "
      "bound that rejects a real value makes the honest number un-enterable and pushes it somewhere "
      f"unvalidated. Defaults number {len(defaulted)} across 133 modules and the gate is a CEILING "
      "rather than a floor — the only such assertion here, because a default writes a value nobody "
      "chose and a wrong one is invisible precisely because it looks deliberate. Each is a fact about "
      "the record (a daily report is filed today), never a policy. Applied on CREATE only: re-filling "
      "on update would make 'empty' unreachable, and an explicit 0 is an answer that survives.")

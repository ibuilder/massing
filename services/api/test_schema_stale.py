"""R41-SCHEMA-STALE — a record that predates a schema change must not read back quietly wrong.

THE DEFECT. A module record's `data` is a JSON blob keyed by field name, and `modules.get_record`
resolves it against the module's **current** field list. Nothing recorded which field list the
values were written against, so a schema change reinterpreted history in silence:

  * a RENAMED field renders **empty** — indistinguishable from "never filled in" — while its value
    sits orphaned in the payload, unread and unreachable;
  * a REMOVED field's value is likewise invisible;
  * a RETYPED field is rendered under the new type.

Nothing raised. This is the failure mode the project notes keep naming — a wrong answer that looks
like an empty form — applied to customer data rather than to a gate.

WHAT THIS ASSERTS, AND THE PART THAT IS A DELIBERATE DEVIATION. The item as filed prescribed
"payload forced to null" on any version difference. That is implemented differently on purpose and
the reason is the whole point of the item: **adding a field is the common change and is
compatible**, so nulling on any difference would blank every historical record for a routine
addition — rendering them exactly as "empty and indistinguishable from never filled in". The
prescription would have reproduced the bug it was written to fix. Values are kept; the specific
discrepancy is reported.

So the severity split below is the load-bearing claim, and it is asserted in both directions:
  * a field ADDED           -> changed=True,  stale=False   (nothing about old rows is wrong)
  * a field RENAMED/REMOVED -> stale=True with the orphaned key named
  * a field RETYPED         -> stale=True with the mistyped key named
  * a MEANING change        -> invisible to any payload check, so it must be DECLARED via
                               `schema_epoch`; a record from a lower epoch reads stale

WHY THE NO-FALSE-POSITIVE CHECK IS NOT OPTIONAL. A staleness flag that fires on healthy records is
worse than no flag: it gets muted in a week and then the real one is invisible too. The last block
creates a record through the real engine in EVERY registered module and asserts not one of them
reports stale. That is the check that would have caught an incomplete `ENGINE_DATA_KEYS` list —
the engine writes `subject`, `revision`, `revises` and `superseded_by` into `data`, and without all
four every revised record in the system would report orphans on day one.

Run: PYTHONPATH="src;../data/src" ./.venv/Scripts/python.exe test_schema_stale.py
"""
import os
import sys

os.environ["DATABASE_URL"] = "sqlite:///./test_schema_stale.db"
os.environ["STORAGE_DIR"] = "./test_storage_schema_stale"
for _f in ("./test_schema_stale.db",):
    if os.path.exists(_f):
        os.remove(_f)

from aec_api import (
    module_schema,  # noqa: E402
    modules,  # noqa: E402
    modules_registry,  # noqa: E402
)
from aec_api.db import Base, SessionLocal, engine  # noqa: E402
from aec_api.models import Project  # noqa: E402

failures: list[str] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    print(f"  {'ok  ' if ok else 'FAIL'}  {name}{('  — ' + detail) if detail and not ok else ''}")
    if not ok:
        failures.append(name)


# --------------------------------------------------------------------------------------------
# 1) The pure severity logic. No database — these are the four cases the item names.
# --------------------------------------------------------------------------------------------
BEFORE = {"key": "t", "fields": [
    {"name": "cause", "type": "text"},
    {"name": "cost", "type": "currency"},
    {"name": "trade", "type": "select", "options": ["mech", "elec"]},
]}
RECORD = {"cause": "burst riser", "cost": 12500.0, "trade": "mech"}

stamp_before = module_schema.schema_stamp(BEFORE)

st = module_schema.schema_status(BEFORE, stamp_before, RECORD)
check("an unchanged schema is neither changed nor stale",
      st["changed"] is False and st["stale"] is False, f"got {st}")

# ADD a field — compatible. This is the assertion that rules out the "null the payload" design.
added = {"key": "t", "fields": BEFORE["fields"] + [{"name": "photo", "type": "file"}]}
st = module_schema.schema_status(added, stamp_before, RECORD)
check("adding a field is CHANGED but not STALE", st["changed"] is True and st["stale"] is False,
      f"got {st} — every historical record would be flagged for a routine addition")

# RENAME cause -> root_cause. The value is now orphaned and the new field renders empty.
renamed = {"key": "t", "fields": [
    {"name": "root_cause", "type": "text"},
    *BEFORE["fields"][1:],
]}
st = module_schema.schema_status(renamed, stamp_before, RECORD)
check("a renamed field is stale and names the orphaned key",
      st["stale"] is True and st["orphaned"] == ["cause"], f"got {st}")

# REMOVE cost. Its value is unread and invisible.
removed = {"key": "t", "fields": [f for f in BEFORE["fields"] if f["name"] != "cost"]}
st = module_schema.schema_status(removed, stamp_before, RECORD)
check("a removed field is stale and names the orphaned key",
      st["stale"] is True and st["orphaned"] == ["cost"], f"got {st}")

# RETYPE cost currency -> text. The stored float no longer matches its declaration.
retyped = {"key": "t", "fields": [
    BEFORE["fields"][0], {"name": "cost", "type": "text"}, BEFORE["fields"][2],
]}
st = module_schema.schema_status(retyped, stamp_before, RECORD)
check("a retyped field is stale and names the mistyped key",
      st["stale"] is True and st["mistyped"] == ["cost"], f"got {st}")

# The bool/int trap: isinstance(True, int) is True in Python, so an unguarded numeric check would
# accept a checkbox value as a currency amount and report nothing wrong.
boolish = module_schema.schema_status(BEFORE, stamp_before, {**RECORD, "cost": True})
check("a bool stored where currency is declared is caught (isinstance(True, int) is True)",
      boolish["mistyped"] == ["cost"], f"got {boolish}")

# MEANING change with no shape change — undetectable from the payload, so it is declared.
epoch1 = {**BEFORE, "schema_epoch": 1}
st = module_schema.schema_status(epoch1, stamp_before, RECORD)
check("a declared epoch bump makes earlier records stale",
      st["stale"] is True and st["epoch_behind"] is True, f"got {st}")
check("the epoch delimiter prevents a digit-collision",
      module_schema.schema_stamp({**BEFORE, "schema_epoch": 1})
      != module_schema.schema_stamp({**BEFORE, "schema_epoch": 12}))

# A historical row has no stamp at all. The payload checks must still work — they are what covers
# the 100% of rows written before this shipped.
st = module_schema.schema_status(renamed, None, RECORD)
check("an UNSTAMPED historical row still reports the orphan",
      st["stale"] is True and st["orphaned"] == ["cause"] and st["stored"] is None, f"got {st}")

# Presentation-only edits must not version. Otherwise a copy edit marks a whole register stale.
relabelled = {"key": "t", "fields": [{**f, "label": "X", "help": "y", "fieldset": "z"}
                                     for f in BEFORE["fields"]]}
check("a relabelled field does not change the signature",
      module_schema.schema_signature(relabelled) == module_schema.schema_signature(BEFORE))

# Field ORDER must not change the signature — reordering a form is presentation.
reordered = {"key": "t", "fields": list(reversed(BEFORE["fields"]))}
check("reordering fields does not change the signature",
      module_schema.schema_signature(reordered) == module_schema.schema_signature(BEFORE))

# ...but the select's value space MUST, because a dropped option reinterprets a stored value.
fewer_options = {"key": "t", "fields": [
    *BEFORE["fields"][:2], {"name": "trade", "type": "select", "options": ["mech"]},
]}
check("changing a select's options changes the signature",
      module_schema.schema_signature(fewer_options) != module_schema.schema_signature(BEFORE))

# --------------------------------------------------------------------------------------------
# 2) End to end: the stamp is really written, and the read really carries the verdict.
# --------------------------------------------------------------------------------------------
# The registry is loaded at app startup; this test drives the engine directly, so load it here.
# Without this every mod_* Table is absent from the metadata and create_all makes none of them.
modules_registry.load_registry()
Base.metadata.create_all(bind=engine)
db = SessionLocal()
db.add(Project(id="p-stale", name="Schema Stale"))
db.commit()

#: A minimal payload that satisfies a module's required fields. Written as a helper rather than
#: skipping the modules that have them: "create failed, so skip" would silently shrink the corpus
#: sweep in section 3 to the handful of registers with no required field, and report a confident
#: pass over a population far smaller than the one it claims.
_SAMPLES = {
    "number": 1, "currency": 1.0, "percent": 1.0, "checkbox": False,
    "date": "2026-08-07", "email": "probe@example.com", "phone": "555-0100",
    "multiselect": [], "table": [],
}


def minimal(m: dict, label: str) -> dict:
    data: dict = {}
    tf = m.get("title_field") or (m["fields"][0]["name"] if m.get("fields") else None)
    for f in m.get("fields", []):
        if f.get("type") == "rollup" or not (f.get("required") or f["name"] == tf):
            continue
        t = f.get("type") or "text"
        if t == "select":
            opts = f.get("options") or []
            data[f["name"]] = opts[0] if opts else "n/a"
        else:
            data[f["name"]] = _SAMPLES.get(t, label)
    if tf:
        data[tf] = label
    return data


KEY = "rfi"
mod = modules.get_module(KEY)
title_field = mod.get("title_field") or mod["fields"][0]["name"]
rec = modules.create_record(db, KEY, "p-stale", {"data": minimal(mod, "does the stamp land?")},
                            "tester", None)

check("a newly created record carries a schema stamp",
      rec.get("schema_version") == module_schema.schema_stamp(mod),
      f"got {rec.get('schema_version')!r}")
check("the read carries a schema verdict block",
      isinstance(rec.get("schema"), dict) and rec["schema"]["stale"] is False,
      f"got {rec.get('schema')!r}")

# Simulate the change: a field this record filled in gets renamed under it.
stored = modules.get_record(db, KEY, "p-stale", rec["id"])
live = modules.get_module(KEY)
victim = next(f["name"] for f in live["fields"]
              if f["name"] in (stored.get("data") or {})
              and f["name"] not in module_schema.ENGINE_DATA_KEYS)
mutated = {**live, "fields": [({**f, "name": f["name"] + "_v2"} if f["name"] == victim else f)
                              for f in live["fields"]]}
verdict = module_schema.schema_status(mutated, stored.get("schema_version"), stored.get("data"))
check(f"renaming {victim!r}, a field this live record filled in, makes THAT record stale",
      verdict["stale"] is True and victim in verdict["orphaned"], f"got {verdict}")

# THE BLIND SPOT, asserted so it is a known limit rather than a surprise. `subject` is the universal
# title alias: `create_record` copies it into the module's own title field and LEAVES IT IN `data`,
# so a module that never declares a `subject` field still has one in every payload. It is therefore
# in ENGINE_DATA_KEYS — and `rfi` is a module whose title_field IS literally `subject`. Rename that
# field and the orphan is invisible, because nothing in the payload distinguishes "alias residue"
# from "the value of a field that used to be called subject". Undecidable from the record alone;
# the stamp still moves, so `changed` is true and the record is not silently identical.
alias_renamed = {**live, "fields": [({**f, "name": "subject_v2"} if f["name"] == "subject" else f)
                                    for f in live["fields"]]}
blind = module_schema.schema_status(alias_renamed, stored.get("schema_version"), stored.get("data"))
check("renaming the `subject` alias is a KNOWN blind spot — changed, but not orphan-detected",
      blind["changed"] is True and "subject" not in blind["orphaned"],
      f"got {blind} — if this now detects the orphan, delete this check and the note above")

# --------------------------------------------------------------------------------------------
# 3) No false positives across the whole register corpus. See the module docstring.
# --------------------------------------------------------------------------------------------
noisy: list[str] = []
skipped: list[str] = []
checked = 0
total = len(modules_registry.REGISTRY)
for key in sorted(modules_registry.REGISTRY):
    m = modules.get_module(key)
    if not m.get("fields"):
        continue
    try:
        r = modules.create_record(db, key, "p-stale",
                                  {"data": minimal(m, f"corpus probe {key}")}, "tester", None)
    except Exception as e:                      # noqa: BLE001 — reported, never silently dropped
        skipped.append(f"{key}: {type(e).__name__}")
        continue
    checked += 1
    s = r.get("schema") or {}
    if s.get("stale"):
        noisy.append(f"{key}: orphaned={s.get('orphaned')} mistyped={s.get('mistyped')}")

#: The REACH is asserted alongside the verdict. "No register reported stale" is a different claim
#: depending on whether it probed 8 registers or 130, and a silent skip list would let the first
#: masquerade as the second — the shape recorded as "derive the population AND the reach".
print(f"  ..    corpus reach: probed {checked} of {total} registers; "
      f"{len(skipped)} could not be seeded{': ' + ', '.join(skipped[:6]) if skipped else ''}")
check(f"the corpus sweep actually reached most of the {total} registers",
      checked >= int(total * 0.8), f"only {checked}/{total} probed — the sweep proves little")
check(f"no healthy record in any of the {checked} probed registers reports stale",
      not noisy, f"noisy={noisy[:5]}")

db.close()
print(f"\ntest_schema_stale {'OK' if not failures else 'FAILED: ' + ', '.join(failures)}")
sys.exit(1 if failures else 0)

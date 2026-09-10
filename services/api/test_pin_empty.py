"""PIN-EMPTY — the migration's predicate agrees with the runtime one, and actually sweeps.

`pins._topic_pin_where` selects pin candidates in SQL (`anchor IS NOT NULL OR element_guids IS NOT
NULL`); `pins.pin_fields` applies the exact test in Python. A stored `{}`, `[]` or `[""]` is
**non-NULL**, so it passes the first and fails the second — which is the whole reason `resolve_pins`
reports `total_counts_candidates` and the plan sheet prints `~` before the project total.

Migration `e4a7c2b81f60` nulls those rows. It carries a SELF-CONTAINED copy of the predicate,
because a migration must keep meaning what it meant when it ran even after the app's definition
moves. **A copy is exactly what drifts**, so this asserts the two agree today — over a table of
values, not over one example, because the first draft of this file agreed on `{}` and `[]` and would
have passed with `[""]` classified either way.

Run: `PYTHONPATH=src:../data/src python test_pin_empty.py`
"""
from __future__ import annotations

import importlib.util
import pathlib
import sys

FAILED: list[str] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    if not ok:
        FAILED.append(f"{name} — {detail}")


sys.path.insert(0, "src")
sys.path.insert(0, "../data/src")

from aec_api import pins as pin_engine  # noqa: E402

_MIG = pathlib.Path("migrations/versions/2026_09_10_0115-e4a7c2b81f60_pin_empty_json_to_null.py")
check("the migration this gate is about exists", _MIG.exists(), f"{_MIG} not found")
if not _MIG.exists():
    print("FAIL test_pin_empty")
    sys.exit(1)

_spec = importlib.util.spec_from_file_location("_pin_empty_mig", _MIG)
mig = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(mig)

# --- the two predicates must agree, over a TABLE of values -----------------------------------------
# Each case is (anchor, element_guids, is_a_pin). The migration nulls a field exactly when the
# runtime test cannot use it; disagreement in either direction is a defect:
#   - migration nulls something runtime WOULD have used  -> a real pin silently deleted
#   - migration keeps something runtime rejects          -> the upper bound survives the sweep
CASES = [
    # anchor,                     element_guids,        is a pin?
    ({"x": 1.0, "y": 2.0, "z": 0.0}, None,              True),
    (None,                        ["G1"],               True),
    ({"x": 0.0, "y": 0.0, "z": 0.0}, [],                True),   # a zero anchor is still an anchor
    (None,                        ["", "G2"],           True),   # one usable guid is enough
    ({},                          None,                 False),  # THE CASE: empty dict, non-NULL
    (None,                        [],                   False),  # THE CASE: empty list, non-NULL
    (None,                        [""],                 False),  # THE CASE: blank guid only
    (None,                        ["", ""],             False),
    ({},                          [],                   False),  # both empty
    ({},                          [""],                 False),
    (None,                        None,                 False),  # honest negative: plain issue
]

for anchor, guids, is_pin in CASES:
    a, g = pin_engine.pin_fields(anchor, guids)
    runtime_pin = bool(a or g)
    check(f"runtime agrees this {'IS' if is_pin else 'is NOT'} a pin: {anchor!r}/{guids!r}",
          runtime_pin == is_pin,
          f"pin_fields returned ({a!r}, {g!r}) -> {runtime_pin}, expected {is_pin}")

    # The migration's view, field by field.
    mig_drops_anchor = mig._is_empty_anchor(anchor) if anchor is not None else None
    mig_drops_guids = mig._is_empty_guids(guids) if guids is not None else None

    if anchor is not None:
        check(f"migration keeps the anchor iff runtime uses it: {anchor!r}",
              mig_drops_anchor == (a is None),
              f"migration drop={mig_drops_anchor} but runtime usable={a is not None} — "
              f"dropping one runtime WOULD use deletes a real pin; keeping one it rejects "
              f"leaves the upper bound in place after the sweep")
    if guids is not None:
        check(f"migration keeps the guids iff runtime uses them: {guids!r}",
              mig_drops_guids == (not g),
              f"migration drop={mig_drops_guids} but runtime usable={bool(g)}")

# --- the migration accepts BOTH shapes a JSON column comes back as ---------------------------------
# Some drivers decode JSON columns, some hand back text. A predicate that only understands one
# silently sweeps nothing on the other -- a migration that runs, reports success, and changes zero
# rows, which is indistinguishable from a database that was already clean.
check("an empty anchor is recognised when the driver returns TEXT",
      mig._is_empty_anchor("{}") is True,
      "a text-returning driver would leave every legacy row in place, silently")
check("an empty guid list is recognised when the driver returns TEXT",
      mig._is_empty_guids("[]") is True and mig._is_empty_guids('[""]') is True)
check("a REAL anchor is not dropped when the driver returns TEXT",
      mig._is_empty_anchor('{"x": 1, "y": 2, "z": 3}') is False,
      "the text path must not delete real pins")
check("a REAL guid list is not dropped when the driver returns TEXT",
      mig._is_empty_guids('["G1"]') is False)
check("unparseable text is treated as empty, not crashed on",
      mig._is_empty_anchor("not json") is True)

# --- the sweep covers every spatial register -------------------------------------------------------
# Derived from the runtime tuple rather than eyeballed: a register added to SPATIAL_MODULES and not
# to the migration is a table the sweep silently skips.
missing = [k for k in pin_engine.SPATIAL_MODULES if k not in mig._SPATIAL]
check("the migration sweeps every spatial register the engine reads",
      not missing,
      f"in SPATIAL_MODULES but not swept: {missing} — those registers keep their legacy "
      f"empty rows and stay counted as candidates")
check("...and sweeps nothing the engine does not read",
      not [k for k in mig._SPATIAL if k not in pin_engine.SPATIAL_MODULES],
      "sweeping a table the pin engine never reads is scope this migration did not claim")

# --- the downgrade is a no-op ON PURPOSE, and says so ----------------------------------------------
check("downgrade exists and is a documented no-op",
      callable(mig.downgrade) and (mig.downgrade.__doc__ or "").strip().startswith("Not reversible"),
      "an empty downgrade with no docstring reads as an oversight; this one is a decision")

# --- THE SWEEP ACTUALLY SWEEPS ---------------------------------------------------------------------
# `test_alembic_migrations` runs the chain against an EMPTY database, so it proves this migration
# does not crash and nothing more: `_sweep` matched zero rows. A migration that runs, reports
# success and changes nothing is indistinguishable from a database that was already clean, which is
# the same "reports less than the truth" shape this whole line of work is about.
import sqlalchemy as _sa  # noqa: E402

_eng = _sa.create_engine("sqlite://")          # in-memory; no DATABASE_URL, no file to sweep up
with _eng.begin() as _c:
    _c.execute(_sa.text("CREATE TABLE topics (id TEXT PRIMARY KEY, anchor TEXT, element_guids TEXT)"))
    _c.execute(_sa.text("CREATE TABLE mod_rfi (id TEXT PRIMARY KEY, element_guids TEXT)"))
    rows = [
        ("keep-anchor", '{"x": 1, "y": 2, "z": 3}', None),
        ("keep-guids",  None,                        '["G1"]'),
        ("keep-mixed",  '{"x": 0, "y": 0, "z": 0}',  '[]'),      # anchor real, guids empty
        ("drop-both",   "{}",                        '[]'),
        ("drop-anchor", "{}",                        '["G2"]'),  # only the anchor is empty
        ("drop-blank",  None,                        '[""]'),
        ("untouched",   None,                        None),
    ]
    for rid, a, g in rows:
        _c.execute(_sa.text("INSERT INTO topics VALUES (:i, :a, :g)"), {"i": rid, "a": a, "g": g})
    _c.execute(_sa.text("INSERT INTO mod_rfi VALUES ('r-empty', '[]')"))
    _c.execute(_sa.text("INSERT INTO mod_rfi VALUES ('r-real', '[\"G9\"]')"))

    changed = mig._sweep(_c, "topics", ("anchor", "element_guids"))
    changed_r = mig._sweep(_c, "mod_rfi", ("element_guids",))

    got = {r["id"]: (r["anchor"], r["element_guids"])
           for r in _c.execute(_sa.text("SELECT * FROM topics")).mappings()}
    got_r = {r["id"]: r["element_guids"]
             for r in _c.execute(_sa.text("SELECT * FROM mod_rfi")).mappings()}

check("THE SWEEP CHANGES ROWS — 4 topics carried an empty value", changed == 4,
      f"changed={changed}, expected 4 — a migration that sweeps nothing passes the chain test "
      f"and leaves every legacy row exactly as it was")
check("...and one register row", changed_r == 1, f"changed={changed_r}")

check("a real anchor survives", got["keep-anchor"][0] is not None)
check("real guids survive", got["keep-guids"][1] is not None)
check("A ZERO ANCHOR SURVIVES — {x:0,y:0,z:0} is a place, not an absence",
      got["keep-mixed"][0] is not None,
      "0,0,0 is the project origin; treating it as empty deletes every pin at the origin")
check("...while the empty guid list beside it is nulled", got["keep-mixed"][1] is None)
check("both empty fields are nulled", got["drop-both"] == (None, None))
check("only the empty field is nulled, the real one is kept",
      got["drop-anchor"][0] is None and got["drop-anchor"][1] is not None,
      f"got {got['drop-anchor']!r} — nulling a whole row would delete a real pin")
check("a list of only blank guids is nulled", got["drop-blank"][1] is None)
check("an already-NULL row is left alone", got["untouched"] == (None, None))
check("the register's empty list is nulled", got_r["r-empty"] is None)
check("the register's real list survives", got_r["r-real"] is not None)

# A table that is not present is skipped, not crashed on: a deployment without every register
# module installed must still be able to run this migration.
with _eng.begin() as _c:
    check("a missing table is skipped rather than raising",
          mig._sweep(_c, "mod_not_installed", ("element_guids",)) == 0)

if FAILED:
    print("FAIL test_pin_empty")
    for f in FAILED:
        print("  -", f)
    sys.exit(1)
print(f"test_pin_empty OK  ({len(CASES)} value cases; migration and runtime agree; "
      f"{len(mig._SPATIAL)} registers swept)")

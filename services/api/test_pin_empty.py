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

import ast
import importlib.util
import pathlib
import sys
import types
import typing

FAILED: list[str] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    if not ok:
        FAILED.append(f"{name} — {detail}")


sys.path.insert(0, "src")
sys.path.insert(0, "../data/src")

from aec_api import modules_registry  # noqa: E402
from aec_api import pins as pin_engine  # noqa: E402

# `spatial_modules()` reads the REGISTRY, which the app fills at startup. A bare import leaves it
# empty, and an empty registry makes every coverage assertion below vacuously true — so load it
# here, and assert below that it actually loaded.
modules_registry.load_registry()

_MIG = pathlib.Path("migrations/versions/2026_09_10_0115-e4a7c2b81f60_pin_empty_json_to_null.py")
check("the migration this gate is about exists", _MIG.exists(), f"{_MIG} not found")
if not _MIG.exists():
    print("FAIL test_pin_empty")
    sys.exit(1)

_spec = importlib.util.spec_from_file_location("_pin_empty_mig", _MIG)
mig = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(mig)

# PIN-POPULATION added a SECOND sweep. `pins.spatial_modules()` is now derived from the registry's
# `pinnable` flag instead of a hand-written tuple, which took the engine from 5 real registers to 37,
# and the registers it newly reads needed the same backfill. Both migrations are loaded because the
# coverage question is about their UNION: which registers has the sweep reached, across everything
# that has run. Asserting against either alone would report a gap that the other closes, or miss one
# that neither does.
_MIG2 = pathlib.Path(
    "migrations/versions/2026_09_10_1400-f2b6d31a7c04_pin_empty_widened_registers.py")
check("the widening migration exists", _MIG2.exists(), f"{_MIG2} not found")
if not _MIG2.exists():
    print("FAIL test_pin_empty")
    sys.exit(1)
_spec2 = importlib.util.spec_from_file_location("_pin_empty_mig2", _MIG2)
mig2 = importlib.util.module_from_spec(_spec2)
_spec2.loader.exec_module(mig2)
check("the widening migration follows the first", mig2.down_revision == mig.revision,
      f"{mig2.down_revision!r} != {mig.revision!r} — a sweep off the chain sweeps nothing")

# PIN-ANCHOR added a THIRD sweep. `pins.resolve_pins` now selects register rows with the shared
# `pins.pin_where` — `anchor IS NOT NULL OR element_guids IS NOT NULL` — so a register's `anchor`
# is read by a reader that reports a total for the first time. No sweep had ever touched one.
_MIG3 = pathlib.Path(
    "migrations/versions/2026_09_10_1700-b3c9e42d18a5_pin_anchor_register_sweep.py")
check("the anchor migration exists", _MIG3.exists(), f"{_MIG3} not found")
if not _MIG3.exists():
    print("FAIL test_pin_empty")
    sys.exit(1)
_spec3 = importlib.util.spec_from_file_location("_pin_empty_mig3", _MIG3)
mig3 = importlib.util.module_from_spec(_spec3)
_spec3.loader.exec_module(mig3)
check("the anchor migration follows the widening one", mig3.down_revision == mig2.revision,
      f"{mig3.down_revision!r} != {mig2.revision!r} — a sweep off the chain sweeps nothing")

#: Every register any sweep has reached, by NAME. Kept for the dead-name record below; it is NOT
#: what coverage is measured on any more — see `SWEPT_PAIRS`.
SWEPT = set(mig._SPATIAL) | set(mig2._SPATIAL) | set(mig3._SPATIAL)

#: All three migrations, so every check below that exercises a COPY of the predicate exercises all
#: of them. The copy-don't-import rule is what makes a migration a record of what it did; the price
#: is that each new copy can drift from the last, and only running every one can see that.
MIGS = (mig, mig2, mig3)


def _swept_pairs(m) -> set[tuple[str, str]]:
    """`(table, column)` for everything this migration actually sweeps — by RUNNING `upgrade()`.

    **Not by reading `_SPATIAL`.** That list is the migration's *population*; the columns are an
    argument at the call site, and reading one without the other is exactly the blindness this
    function exists to end (see `SWEPT_PAIRS`). Stubbing `_sweep` and executing the real `upgrade()`
    reports what the migration does, including any table it sweeps that is in no list at all —
    `e4a7c2b81f60` sweeps `topics` that way.
    """
    seen: set[tuple[str, str]] = set()
    real_sweep, real_op = m._sweep, m.op
    m._sweep = lambda conn, table, cols: (seen.update((table, c) for c in cols), 0)[1]
    m.op = types.SimpleNamespace(get_bind=lambda: None)
    try:
        m.upgrade()
    finally:
        m._sweep, m.op = real_sweep, real_op
    return seen


#: What the sweeps have reached, as (table, column) pairs across every migration that has run.
SWEPT_PAIRS: set[tuple[str, str]] = set()
for _m in MIGS:
    SWEPT_PAIRS |= _swept_pairs(_m)
    # `upgrade()` ran for real above (only `_sweep` was stubbed), so a migration that accumulates
    # into `SKIPPED` must not leave that state for the behavioural sections further down. It is
    # empty here either way; clearing it is cheap and makes the assertions below independent of
    # whether this block ran at all.
    getattr(_m, "SKIPPED", []).clear()
check("the derived sweep is non-trivial", len(SWEPT_PAIRS) > 10,
      f"{len(SWEPT_PAIRS)} pairs — a derivation that collapses makes every coverage check below "
      f"vacuously true, which is the failure mode that looks like a pass")


# --- WHICH COLUMNS DOES THE ENGINE READ? Derived from `pins.py`, and it FAILS CLOSED ---------------
# `pins.pin_where(project_col, anchor_col, guids_col, pid)` takes its columns positionally, so the
# predicate alone cannot say what they are NAMED. The names live at the call sites, so that is where
# they are read from — every `pin_where(...)` in `pins.py`, via AST. An argument this cannot resolve
# to a column name is reported and FAILS, rather than being skipped into invisibility: a predicate
# that decides what to LOOK at hides its own misses, which is the defect this whole line of work is
# about.
_SRC = pathlib.Path("src/aec_api/pins.py")
_TREE = ast.parse(_SRC.read_text(encoding="utf-8"), str(_SRC))
_CALLS: list[ast.Call] = [n for n in ast.walk(_TREE)
                          if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)
                          and n.func.id == "pin_where"]
check("the engine calls the shared predicate from more than one place", len(_CALLS) >= 2,
      f"{len(_CALLS)} call site(s) — this gate assumes the topic read and the register read both "
      f"go through `pin_where`; if one stopped, its columns are no longer covered here")
READ_COLS: set[str] = set()
_UNRESOLVED: list[str] = []
for _c in _CALLS:
    # args[0] is the project scope, not part of the pin test. args[1:3] are the pin columns.
    for _a in _c.args[1:3]:
        if isinstance(_a, ast.Attribute):
            READ_COLS.add(_a.attr)
        else:
            _UNRESOLVED.append(ast.dump(_a)[:80])
check("every column handed to the pin predicate resolves to a name", not _UNRESOLVED,
      f"unresolved: {_UNRESOLVED} — an argument this cannot read is a column that may be unswept "
      f"and would be silently excluded from the coverage check below")
check("the column derivation found columns", bool(READ_COLS),
      "no columns derived — the coverage check below would compare nothing against nothing")

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

    # Every migration's view, field by field. **Both copies are checked, not just the first.** The
    # copy-don't-import rule is what makes a migration a record of what it did; the price of it is
    # that a second copy can drift from the first, and only running both can see that.
    for _m in MIGS:
        _n = _m.revision
        mig_drops_anchor = _m._is_empty_anchor(anchor) if anchor is not None else None
        mig_drops_guids = _m._is_empty_guids(guids) if guids is not None else None

        if anchor is not None:
            check(f"{_n} keeps the anchor iff runtime uses it: {anchor!r}",
                  mig_drops_anchor == (a is None),
                  f"migration drop={mig_drops_anchor} but runtime usable={a is not None} — "
                  f"dropping one runtime WOULD use deletes a real pin; keeping one it rejects "
                  f"leaves the upper bound in place after the sweep")
        if guids is not None:
            check(f"{_n} keeps the guids iff runtime uses them: {guids!r}",
                  mig_drops_guids == (not g),
                  f"migration drop={mig_drops_guids} but runtime usable={bool(g)}")

# --- the migration accepts BOTH shapes a JSON column comes back as ---------------------------------
# Some drivers decode JSON columns, some hand back text. A predicate that only understands one
# silently sweeps nothing on the other -- a migration that runs, reports success, and changes zero
# rows, which is indistinguishable from a database that was already clean.
for _m in MIGS:
    check(f"{_m.revision}: an empty anchor is recognised when the driver returns TEXT",
          _m._is_empty_anchor("{}") is True,
          "a text-returning driver would leave every legacy row in place, silently")
    check(f"{_m.revision}: an empty guid list is recognised when the driver returns TEXT",
          _m._is_empty_guids("[]") is True and _m._is_empty_guids('[""]') is True)
    check(f"{_m.revision}: a REAL anchor is not dropped on the TEXT path",
          _m._is_empty_anchor('{"x": 1, "y": 2, "z": 3}') is False,
          "the text path must not delete real pins")
    check(f"{_m.revision}: a REAL guid list is not dropped on the TEXT path",
          _m._is_empty_guids('["G1"]') is False)
    check(f"{_m.revision}: unparseable text is treated as empty, not crashed on",
          _m._is_empty_anchor("not json") is True)

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
# Derived from the runtime POPULATION rather than eyeballed: a register the engine reads and no
# migration sweeps is a table that keeps its legacy empty rows and stays counted as a candidate.
#
# **This check was green while it was measuring nothing.** It compared the migration's list against
# `pins.SPATIAL_MODULES`, a hand-written tuple — so it asserted that one list matched another list,
# and both listed six registers that do not exist. Now the left side is `spatial_modules()`, derived
# from the registry, so the question is "does the sweep reach what the engine reads" rather than
# "do two hand-written tuples agree".
_population = list(pin_engine.spatial_modules())
check("the derived population is not empty",
      len(_population) > 10,
      f"only {len(_population)} pinnable registers — a population that collapses makes every "
      f"coverage check below vacuously true, which is the failure mode that looks like a pass")
# **Coverage is measured on (register, COLUMN) pairs, and that distinction is the whole point of
# this migration.** This check used to compare register NAMES, and every one of the thirty-seven
# registers was already recorded as swept — for `element_guids`. When `resolve_pins` started reading
# `anchor` on those same tables, not one name changed, so the check that exists to notice an unswept
# register reported full coverage over a column no sweep had ever touched. **A coverage gate is
# bounded by the shape of the thing it counts**, and a name is a coarser shape than a read.
_pop_pairs = {(f"mod_{k}", c) for k in _population for c in READ_COLS}
missing = sorted(_pop_pairs - SWEPT_PAIRS)
check("every (register, column) the engine reads has been swept",
      not missing,
      f"read but never swept: {missing} — add a migration rather than widening a list")

# The topic table goes through the same predicate and is swept by `e4a7c2b81f60`, which names it
# directly rather than through `_SPATIAL` — which is why `_swept_pairs` runs `upgrade()` instead of
# reading the list.
_topic_missing = sorted(c for c in READ_COLS if ("topics", c) not in SWEPT_PAIRS)
check("the topics table is swept on every column the engine reads",
      not _topic_missing,
      f"unswept on topics: {_topic_missing}")

# The name-level question is still worth asking, and is now strictly weaker than the pair-level one
# — kept so a register that appears in NO sweep at all is named plainly rather than as a list of
# pairs.
_missing_names = [k for k in _population if k not in SWEPT]
check("every register the engine reads appears in some sweep",
      not _missing_names,
      f"read but named by no migration: {_missing_names}")

# The other direction is now an OBSERVATION, not a failure. `mig._SPATIAL` names six registers that
# never existed (`clash`, `defect`, `snag`, `quality_issue`, `safety_observation`, `field_report`);
# `_sweep` no-ops on a missing table, so they cost nothing and cannot be un-named — that migration
# already ran. What matters is that they are RECORDED as dead rather than mistaken for coverage.
_dead = sorted(k for k in SWEPT if k not in _population)
check("the dead names in the shipped sweep are exactly the six known ones",
      _dead == ["clash", "defect", "field_report", "quality_issue", "safety_observation", "snag"],
      f"swept but not read: {_dead} — a NEW name here means a register stopped being pinnable "
      f"and its sweep is now unexplained scope; a MISSING one means this record drifted")

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

# --- and THE SECOND COPY OF `_sweep` sweeps too ----------------------------------------------------
# `f2b6d31a7c04` carries its own `_sweep` for the reason its docstring gives. A copy that is never
# executed by a test is a copy that can be subtly wrong forever: it runs against thirty-two register
# tables, all of which are usually empty, so it would report success either way. Same fixture, its
# own function.
_eng2 = _sa.create_engine("sqlite://")
with _eng2.begin() as _c:
    _c.execute(_sa.text("CREATE TABLE mod_ncr (id TEXT PRIMARY KEY, element_guids TEXT)"))
    _c.execute(_sa.text("INSERT INTO mod_ncr VALUES ('n-empty', '[]')"))
    _c.execute(_sa.text("INSERT INTO mod_ncr VALUES ('n-blank', '[\"\"]')"))
    _c.execute(_sa.text("INSERT INTO mod_ncr VALUES ('n-real', '[\"G7\"]')"))
    changed2 = mig2._sweep(_c, "mod_ncr", ("element_guids",))
    got2 = {r["id"]: r["element_guids"]
            for r in _c.execute(_sa.text("SELECT * FROM mod_ncr")).mappings()}
    check("the widening migration's own _sweep changes rows", changed2 == 2,
          f"changed={changed2}, expected 2")
    check("...nulls the empty list", got2["n-empty"] is None)
    check("...nulls the blank-only list", got2["n-blank"] is None)
    check("...and keeps the real one", got2["n-real"] is not None,
          "a second copy that deletes real pins is worse than no second copy")
    check("...and skips a table it does not have",
          mig2._sweep(_c, "mod_not_installed", ("element_guids",)) == 0)

# --- AND THE THIRD COPY SWEEPS A REGISTER **ANCHOR** ----------------------------------------------
# `b3c9e42d18a5` is the first sweep ever to touch a register's `anchor`, and its own `_sweep` has
# never run against one in any test: the two earlier copies were only ever exercised on
# `element_guids` (and on `topics`, whose anchor sweep lives in a migration that already ran).
# **A copy that is never executed on the column it exists for is a copy that can be wrong forever**
# — it runs against thirty-seven usually-empty register tables and reports success either way.
_eng6 = _sa.create_engine("sqlite://")
with _eng6.begin() as _c:
    _c.execute(_sa.text("CREATE TABLE mod_asi (id TEXT PRIMARY KEY, anchor TEXT, "
                        "element_guids TEXT)"))
    _c.execute(_sa.text("INSERT INTO mod_asi VALUES ('a-empty', '{}', '[\"G1\"]')"))
    _c.execute(_sa.text("INSERT INTO mod_asi VALUES ('a-zero', "
                        "'{\"x\": 0, \"y\": 0, \"z\": 0}', NULL)"))
    _c.execute(_sa.text("INSERT INTO mod_asi VALUES ('a-real', "
                        "'{\"x\": 1, \"y\": 2, \"z\": 3}', NULL)"))
    _c.execute(_sa.text("INSERT INTO mod_asi VALUES ('a-null', NULL, '[]')"))
    # Scoped to `anchor` deliberately: this section is about the anchor SEMANTICS (a zero anchor is
    # a place), and `mig3._COLS` also carries `element_guids`, which the row below uses as the
    # control. The pair-coverage check above is what asserts `_COLS` itself.
    _n6 = mig3._sweep(_c, "mod_asi", ("anchor",))
    _got6 = {r["id"]: (r["anchor"], r["element_guids"])
             for r in _c.execute(_sa.text("SELECT * FROM mod_asi")).mappings()}
check("the anchor migration's own _sweep changes rows", _n6 == 1,
      f"changed={_n6}, expected 1 — only 'a-empty' carries an empty anchor")
check("...it nulls the empty register anchor", _got6["a-empty"][0] is None)
check("...WITHOUT touching the real element GUIDs on the same row",
      _got6["a-empty"][1] is not None,
      f"got {_got6['a-empty']!r} — this sweep is scoped to `anchor`; clearing the guids beside it "
      f"would delete a pin the engine can still place")
check("A ZERO ANCHOR SURVIVES on a register too — {x:0,y:0,z:0} is the project origin",
      _got6["a-zero"][0] is not None,
      "the first sweep learned this on `topics`; a copy is exactly what forgets it")
check("...a real anchor survives", _got6["a-real"][0] is not None)
check("...and the column this CALL did not name is left alone",
      _got6["a-null"][1] is not None,
      "`_sweep` must touch exactly the columns it is handed; one that quietly does more than it "
      "was asked is a record of something other than what happened")
with _eng6.begin() as _c:
    check("...and it skips a table it does not have",
          mig3._sweep(_c, "mod_not_installed", mig3._COLS) == 0)

# This sweep claims BOTH pin columns: `anchor` because the engine newly reads it, and
# `element_guids` again because the JSON-null defect meant no earlier sweep left it SQL NULL for
# long — SQLAlchemy stored a Python `None` as the JSON scalar `null`, so `IS NOT NULL` matched
# every row and the earlier backfills were running behind a source that refilled.
check("the anchor migration sweeps every column the engine reads",
      set(mig3._COLS) == READ_COLS,
      f"_COLS={sorted(mig3._COLS)}, engine reads {sorted(READ_COLS)}")

# --- EVERY COPY THAT CAN, ON THE COLUMN IT EXISTS FOR ---------------------------------------------
# The three sections below used to name `mig2` and only `mig2`. Three mutations to `mig3` — clipping
# its chunk loop to one batch, and making its `_decode` call a parse failure a success — both
# SURVIVED, in a file whose own new section had just argued that "a copy that is never executed on
# the column it exists for is a copy that can be wrong forever". **Writing the argument down is not
# running it.** So the copies are a table now, and each is driven on its own column: a fourth
# migration inherits these three checks by being added to it, rather than by someone remembering.
#
# `e4a7c2b81f60` is deliberately absent. It predates `_decode` and `_BATCH` entirely — it NULLs a
# malformed value and issues one UPDATE per row — and it has already run, so it cannot be corrected.
# Its divergence from the others is asserted below rather than smoothed over.
class _Copy(typing.NamedTuple):
    mig: object          #: the migration module
    table: str           #: a register table it claims
    col: str             #: the column this copy exists for
    malformed: str       #: stored text that is not JSON at all, holding recoverable evidence
    evidence: str        #: the substring that would be lost if the row were nulled
    empty: str           #: a value that is non-NULL and fails the exact test
    real: str            #: a value the exact test accepts


COPIES = (
    _Copy(mig2, "mod_ncr", "element_guids", '["1WrzGm1SD2ev45B_OWQ39B", "2Ab',
          "1WrzGm1SD2ev45B_OWQ39B", "[]", '["G9"]'),
    _Copy(mig3, "mod_asi", "anchor", '{"x": 1.5, "y": 2.25, "z"',
          "2.25", "{}", '{"x": 1, "y": 2, "z": 3}'),
)

# Each copy must be exercised on ground no EARLIER copy already covers, or it is being tested
# through someone else's sweep. Derived from what the migrations do, not from their lists.
_seen_pairs: set[tuple[str, str]] = set()
for _c in COPIES:
    _own = _swept_pairs(_c.mig)
    _c.mig.SKIPPED.clear()
    check(f"{_c.mig.revision} claims ({_c.table}, {_c.col})", (_c.table, _c.col) in _own,
          "the fixture below sweeps a pair this migration does not claim")
    check(f"{_c.mig.revision}: ...and no earlier copy already swept it",
          (_c.table, _c.col) not in _seen_pairs,
          f"({_c.table}, {_c.col}) is already covered — this copy is being tested on ground "
          f"another one holds, which is how a broken copy passes")
    _seen_pairs |= _own

# --- MALFORMED IS NOT EMPTY, and `e4a7c2b81f60` deliberately DISAGREES ----------------------------
# `_loads` collapses "not JSON at all" and "decoded to nothing" into the same `None`, and
# `_is_empty_guids(None)` is True — so `e4a7c2b81f60` NULLs a malformed value. Measured on a
# truncated list holding a well-formed GlobalId, the row was cleared and the GUID went with it, and
# `downgrade()` is a documented no-op. Found in review of PR #500.
#
# The later copies route through `_decode` instead and leave those rows alone, recording them in
# `SKIPPED`. The first migration has already run and cannot be changed, so the copies differ — in
# the safe direction. **That difference is asserted** so it can never be mistaken for the silent
# drift the copy-don't-import rule exists to catch.
for _c in COPIES:
    _m, _n = _c.mig, _c.mig.revision
    check(f"{_n}: the fixture really is unparseable", _m._decode(_c.malformed)[0] is False)
    check(f"{_n}: ...and really does carry recoverable evidence", _c.evidence in _c.malformed,
          "if it did not, nothing would be lost by nulling it and this check would prove nothing")
    _m.SKIPPED.clear()
    _e = _sa.create_engine("sqlite://")
    with _e.begin() as _conn:
        _conn.execute(_sa.text(
            f"CREATE TABLE {_c.table} (id TEXT PRIMARY KEY, {_c.col} TEXT)"))
        _conn.execute(_sa.text(f"INSERT INTO {_c.table} VALUES ('truncated', :v)"),
                      {"v": _c.malformed})
        _conn.execute(_sa.text(f"INSERT INTO {_c.table} VALUES ('empty', :v)"), {"v": _c.empty})
        _conn.execute(_sa.text(f"INSERT INTO {_c.table} VALUES ('real', :v)"), {"v": _c.real})
        _n3 = _m._sweep(_conn, _c.table, (_c.col,))
        _got3 = {r["id"]: r[_c.col]
                 for r in _conn.execute(_sa.text(f"SELECT * FROM {_c.table}")).mappings()}
    check(f"{_n}: A MALFORMED VALUE IS NOT DESTROYED — it is evidence, downgrade cannot restore it",
          _got3["truncated"] == _c.malformed,
          f"got {_got3['truncated']!r} — the {_c.evidence!r} inside it is unrecoverable once nulled")
    check(f"{_n}: ...and it is REPORTED rather than silently left",
          _m.SKIPPED == [(_c.table, "truncated", _c.col)],
          f"SKIPPED={_m.SKIPPED!r} — a row the sweep cannot judge must be nameable by a human")
    check(f"{_n}: ...while a genuinely empty value beside it is still swept",
          _got3["empty"] is None)
    check(f"{_n}: ...and a real value is still kept", _got3["real"] is not None)
    check(f"{_n}: ...and the changed count counts only what actually changed", _n3 == 1,
          f"changed={_n3}")
    _m.SKIPPED.clear()

check("THE FIRST MIGRATION STILL NULLS IT — the divergence is real, not imagined",
      mig._is_empty_guids(COPIES[0].malformed) is True,
      "if this ever becomes False the copies agree again and the note above is stale")

# --- THE SWEEP MUST NOT MUTATE THE CONNECTION IT WAS HANDED ---------------------------------------
# `Connection.execution_options()` applies to the connection, not to one statement. The first draft
# of the batching fix called it that way to get `stream_results`, so EVERY statement afterwards on
# that connection inherited it — including alembic's own version bump, which Postgres rejected:
#
#     ERROR: syntax error at or near "UPDATE"
#     STATEMENT: DECLARE "c_7f7b459f32f0_9d" CURSOR FOR UPDATE alembic_version SET version_num=...
#
# **SQLite has no server-side cursor, ignores the option entirely, and stayed green**, so no local
# test could have caught the symptom — only the Postgres runtime-parity job did. What SQLite CAN see
# is the cause: whether the connection came back the way it was handed over. That is the assertion,
# and it is why this is here rather than left to CI.
for _c in COPIES:
    _m, _n = _c.mig, _c.mig.revision
    _e = _sa.create_engine("sqlite://")
    with _e.begin() as _conn:
        _before = dict(_conn.get_execution_options())
        _conn.execute(_sa.text(f"CREATE TABLE {_c.table} (id TEXT PRIMARY KEY, {_c.col} TEXT)"))
        _conn.execute(_sa.text(f"INSERT INTO {_c.table} VALUES ('a', :v)"), {"v": _c.empty})
        _m._sweep(_conn, _c.table, (_c.col,))
        _after = dict(_conn.get_execution_options())
        # The statement that broke: a non-SELECT run on the same connection after the sweep.
        _conn.execute(_sa.text(f"UPDATE {_c.table} SET id = 'a' WHERE id = 'a'"))
    check(f"{_n}: the sweep leaves the connection's execution options exactly as it found them",
          _before == _after,
          f"before={_before!r} after={_after!r} — options set on a CONNECTION outlive the statement "
          f"and are inherited by alembic's own version bump")
    check(f"{_n}: ...and `stream_results` in particular never lands on the connection",
          "stream_results" not in _after and "yield_per" not in _after,
          f"{_after!r} — this is the exact option that turned `UPDATE alembic_version` into "
          f"`DECLARE ... CURSOR FOR UPDATE ...` on Postgres")

# --- the batched update writes the same rows as one-at-a-time would --------------------------------
# `_sweep` drains the SELECT before updating and clears ids in chunks of `_BATCH`. Exercise a set
# LARGER than one batch, or the chunking loop never runs a second iteration and is untested — which
# is exactly the state `mig3` shipped in until the mutation above was run against it.
for _c in COPIES:
    _m, _n = _c.mig, _c.mig.revision
    _m.SKIPPED.clear()
    _e = _sa.create_engine("sqlite://")
    _N = _m._BATCH * 2 + 7
    with _e.begin() as _conn:
        _conn.execute(_sa.text(f"CREATE TABLE {_c.table} (id TEXT PRIMARY KEY, {_c.col} TEXT)"))
        _conn.execute(_sa.text(f"INSERT INTO {_c.table} VALUES (:i, :v)"),
                      [{"i": f"e{n}", "v": _c.empty} for n in range(_N)])
        _conn.execute(_sa.text(f"INSERT INTO {_c.table} VALUES (:i, :v)"),
                      [{"i": f"k{n}", "v": _c.real} for n in range(50)])
        _n4 = _m._sweep(_conn, _c.table, (_c.col,))
        _left = _conn.execute(_sa.text(
            f"SELECT COUNT(*) FROM {_c.table} WHERE {_c.col} IS NOT NULL")).scalar()
    check(f"{_n}: a set spanning several batches is swept completely", _n4 == _N,
          f"changed={_n4}, expected {_N} — a chunking loop that stops early sweeps a prefix and "
          f"reports success")
    check(f"{_n}: ...and the rows it must not touch are all still there", _left == 50,
          f"left={_left}")
    check(f"{_n}: ...over more than one batch, so the loop actually iterated", _N > _m._BATCH)
    _m.SKIPPED.clear()

if FAILED:
    print("FAIL test_pin_empty")
    for f in FAILED:
        print("  -", f)
    sys.exit(1)
print(f"test_pin_empty OK  ({len(CASES)} value cases; {len(MIGS)} migrations agree with the "
      f"runtime predicate; {len(_population)} pinnable registers read on {sorted(READ_COLS)}, "
      f"{len(SWEPT_PAIRS)} (table, column) pairs swept, {len(_dead)} swept names that no longer "
      f"exist)")

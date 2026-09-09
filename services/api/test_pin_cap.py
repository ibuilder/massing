"""PINS-CAP — the pin overlay's cap is spent on PINS, and what it could not reach is counted.

Two defects, one function, and the first is the one that shows on a screen.

**The topic query capped 2,000 rows and THEN dropped the ones that are not pins.** Ordered
oldest-first, so a project whose 2,000 oldest topics are ordinary un-pinned issues drew **no topic
pins at all** — and a pin placed today never appeared, because the window never advanced past the
same 2,000 rows. It did not degrade as the project grew busier; it went blank and stayed blank.

That site carried the verdict `SQL_SCOPED` in `test_limit_filter.py`, on the reasoning that the
`continue` means *"not a pin"* rather than *"not mine"*. **That reasoning is the trap.** Whether a
Python `if` reads as a filter or as a dispatch says nothing about the defect; what decides it is
whether the cap can be spent on rows the `if` then throws away. It can be here, and the same wrong
verdict had already been written once, for `topic_lifecycle.timeline`.

The second: each of the eleven spatial registers was capped at `_MAX_PINS` **separately** and the
concatenation truncated to `_MAX_PINS`, so topics filling the budget deleted every register pin
without a word.

Run: `PYTHONPATH=src:../data/src python test_pin_cap.py`
"""
from __future__ import annotations

import os

# BEFORE importing `aec_api.db`, which builds its engine from `DATABASE_URL` at import time. This
# test calls `create_all`, so without an unconditional assignment here it would create its schema
# in whatever database the operator happens to have exported. `test_db_url_isolation.py` enforces
# it, and enforced it on this file the first time the suite ran it.
os.environ["DATABASE_URL"] = "sqlite:///./test_pin_cap.db"
os.environ.pop("AEC_RBAC", None)   # isolation: never inherit the operator's access mode

import sys  # noqa: E402

FAILED: list[str] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    if not ok:
        FAILED.append(f"{name} — {detail}")


from aec_api import modules_registry as _mr  # noqa: E402
from aec_api import pins as pin_engine  # noqa: E402
from aec_api.db import Base, SessionLocal, engine  # noqa: E402
from aec_api.models import Topic  # noqa: E402

# BEFORE `create_all`. The eleven spatial register tables are built by `load_registry()` and only
# then attached to `Base.metadata`, so creating the schema first leaves `mod_rfi` absent and the
# cross-source fixture below cannot run at all.
_mr.load_registry()
Base.metadata.create_all(bind=engine)

# The cap is lowered rather than 2,000 rows written: the assertion is about WHICH rows the cap is
# spent on, not about the constant's value.
_real = pin_engine._MAX_PINS
PID = "p-pincap"
try:
    pin_engine._MAX_PINS = 5

    with SessionLocal() as db:
        db.query(Topic).filter(Topic.project_id == PID).delete()
        db.commit()
        # 20 ordinary issues — no anchor, no elements — then ONE real pin, newest of all.
        # Under the old code the cap took the 5 OLDEST rows, every one of them a non-pin, and the
        # overlay came back empty while the project plainly had a pin.
        for i in range(20):
            db.add(Topic(id=f"t-plain-{i}", project_id=PID, guid=f"G-plain-{i}", type="rfi",
                         title=f"Ordinary issue {i}", status="open",
                         created_at=__import__("datetime").datetime(2026, 1, 1, 0, i)))
        db.add(Topic(id="t-pin", project_id=PID, guid="G-pin", type="rfi", title="Placed",
                     status="open", anchor={"x": 1.0, "y": 2.0, "z": 3.0},
                     created_at=__import__("datetime").datetime(2026, 6, 1)))
        db.commit()

        env = pin_engine.resolve_pins(db, PID)
        ids = [p["id"] for p in env["pins"]]
        check("THE DEFECT: a pin behind 20 un-pinned issues is still found",
              ids == ["t-pin"],
              f"got {ids} — the cap must be spent on PIN CANDIDATES. Capping topics first and "
              f"dropping non-pins afterwards returns [] here, which reads as 'this project has "
              f"no pins' on the overlay and on every plan sheet")
        check("an uncapped project reports an EXACT total, verified pin by pin",
              (env["pin_total"], env["truncated"], env["total_counts_candidates"]) == (1, False, False),
              f"total={env['pin_total']} truncated={env['truncated']} "
              f"counts_candidates={env['total_counts_candidates']} — every candidate was read here, "
              f"so the total is the pin count and nothing about it is approximate")

        # Now past the cap: 8 pins, budget 5.
        for i in range(7):
            db.add(Topic(id=f"t-pin-{i}", project_id=PID, guid=f"G-pin-{i}", type="rfi",
                         title=f"Placed {i}", status="open", anchor={"x": i, "y": i, "z": 0.0},
                         created_at=__import__("datetime").datetime(2026, 7, 1, 0, i)))
        db.commit()
        env = pin_engine.resolve_pins(db, PID)
        check("a capped overlay says so, and its total is the PROJECT's",
              (len(env["pins"]), env["pin_total"], env["truncated"]) == (5, 8, True),
              f"shown={len(env['pins'])} total={env['pin_total']} truncated={env['truncated']} — "
              f"8 pins exist, 5 fit. `pin_total` used to be absent entirely, and the route "
              f"reported the capped length under the name `total`")
        check("a capped total admits it counted candidates rather than verified pins",
              env["total_counts_candidates"] is True,
              f"counts_candidates={env['total_counts_candidates']} — past the cap the total comes "
              f"from the SUPERSET predicate, so it may overstate, and saying so is the point. The "
              f"honest negative for this flag is the uncapped case asserted above, which is what "
              f"stops it being a flag that is always on")

        db.query(Topic).filter(Topic.project_id == PID).delete()
        db.commit()

    # ---------------------------------------------------------------------------------------
    # THE SHARED BUDGET, across sources. Everything above writes only `Topic` rows, so none of
    # it can tell whether the registers get their own cap, whether a final slice silently
    # deletes them, or whether their read is ordered at all. Review caught that the roadmap
    # claimed this file asserted the shared budget when the fixture could not reach it —
    # a coverage claim its own coverage did not back, which is the class this PR is about.
    # ---------------------------------------------------------------------------------------
    rfi = _mr.TABLES["rfi"]
    with SessionLocal() as db:
        db.execute(rfi.delete().where(rfi.c.project_id == PID))
        db.query(Topic).filter(Topic.project_id == PID).delete()
        # 3 topic pins + 6 register pins, budget 5. Topics are resolved first, so the budget
        # leaves room for exactly 2 register rows and the other 4 must be COUNTED, not dropped.
        for i in range(3):
            db.add(Topic(id=f"t-mix-{i}", project_id=PID, guid=f"G-mix-{i}", type="rfi",
                         title=f"Placed {i}", status="open", anchor={"x": i, "y": i, "z": 0.0},
                         created_at=__import__("datetime").datetime(2026, 8, 1, 0, i)))
        for i in range(6):
            db.execute(rfi.insert().values(
                id=f"r-{i:02d}", project_id=PID, ref=f"RFI-{i:02d}", title=f"Register pin {i}",
                element_guids=[f"E-{i}"], workflow_state="open",
                # explicit, because NULL ordering under DESC is dialect-dependent and this
                # fixture asserts WHICH rows survive the cap
                created_at=__import__("datetime").datetime(2026, 8, 3, 0, i)))
        db.commit()

        mixed = pin_engine.resolve_pins(db, PID)
        ids = [p["id"] for p in mixed["pins"]]
        check("topics and registers are resolved into one list under one budget, NEWEST kept",
              ids == ["t-mix-0", "t-mix-1", "t-mix-2", "r-04", "r-05"],
              f"got {ids} — 3 topic pins then the 2 NEWEST of 6 register rows under a budget "
              f"of 5, in display order. Keeping `r-00`/`r-01` means the read is ascending and a "
              f"register pin filed today never reaches the sheet")
        check("the register read is ordered, so a cap that bites is reproducible",
              ids[3:] == ["r-04", "r-05"],
              f"got {ids[3:]} — without an ORDER BY the two that survive differ between runs, "
              f"so the same request draws different pins")
        check("what the budget could not reach is COUNTED, not silently dropped",
              (mixed["pin_total"], mixed["truncated"]) == (9, True),
              f"total={mixed['pin_total']} truncated={mixed['truncated']} — 3 topics + 6 "
              f"register rows exist and 5 fit")

    # PAST THE CAP, THE NEWEST PINS SURVIVE. Ordering ascending and cutting at the limit keeps
    # the OLDEST, so a project past the cap never shows a pin placed today — the same symptom
    # this function exists to fix, moved from "more than N topics" to "more than N pins". Review
    # caught that the first fix inherited the ascending order it was replacing.
    with SessionLocal() as db:
        db.execute(rfi.delete().where(rfi.c.project_id == PID))   # topics only, for this one
        db.query(Topic).filter(Topic.project_id == PID).delete()
        for i in range(9):
            db.add(Topic(id=f"t-age-{i}", project_id=PID, guid=f"G-age-{i}", type="rfi",
                         title=f"Placed {i}", status="open", anchor={"x": i, "y": 0.0, "z": 0.0},
                         created_at=__import__("datetime").datetime(2026, 8, 4, 0, i)))
        db.commit()
        aged = pin_engine.resolve_pins(db, PID)
        check("a capped overlay keeps the NEWEST pins, in display order",
              [p["id"] for p in aged["pins"]]
              == ["t-age-4", "t-age-5", "t-age-6", "t-age-7", "t-age-8"],
              f"got {[p['id'] for p in aged['pins']]} — ascending order returns t-age-0..4 and "
              f"a pin placed today is invisible on a busy project, which is this defect again")
        check("and still discloses the whole population",
              (aged["pin_total"], aged["truncated"]) == (9, True),
              f"total={aged['pin_total']} truncated={aged['truncated']}")
        # NOT ASSERTED HERE, and said so rather than implied: each source's count comes from a
        # `count(*) OVER ()` in the SAME statement as its window, so a concurrent write cannot
        # leave `pin_total` describing a different population from `pins`. Replacing it with a
        # second `SELECT count(*)` passes every assertion in this file, because a single-threaded
        # test cannot open the window the fix closes. Proving it needs two sessions and a
        # controlled commit between them. Recording the gap beats a comment claiming coverage.
        db.query(Topic).filter(Topic.project_id == PID).delete()
        db.commit()

    # THE CASE THAT ACTUALLY DISTINGUISHES THE SHARED BUDGET, and the reason the assertion above
    # is worded the way it is. **A per-source cap plus a final `out[:_MAX_PINS]` returns exactly
    # the same pins as one shared budget** — both keep the same prefix — so no assertion on
    # `pins` can tell them apart, and the first draft of this file claimed one could. What the
    # shared budget changes is that a source the budget cannot reach at all is **counted** rather
    # than concatenated and then sliced away uncounted. Fill the budget with topics and the
    # registers become exactly that source.
    with SessionLocal() as db:
        db.query(Topic).filter(Topic.project_id == PID).delete()
        # self-contained: re-seed the registers rather than depending on a previous block's rows
        db.execute(rfi.delete().where(rfi.c.project_id == PID))
        for i in range(6):
            db.execute(rfi.insert().values(
                id=f"u-{i:02d}", project_id=PID, ref=f"RFI-U{i:02d}", title=f"Unreachable {i}",
                element_guids=[f"U-{i}"], workflow_state="open",
                created_at=__import__("datetime").datetime(2026, 8, 5, 0, i)))
        for i in range(5):
            db.add(Topic(id=f"t-full-{i}", project_id=PID, guid=f"G-full-{i}", type="rfi",
                         title=f"Placed {i}", status="open", anchor={"x": i, "y": 0.0, "z": 0.0},
                         created_at=__import__("datetime").datetime(2026, 8, 2, 0, i)))
        db.commit()
        full = pin_engine.resolve_pins(db, PID)
        check("a source the budget cannot reach is counted, not silently skipped",
              (len(full["pins"]), full["pin_total"], full["truncated"]) == (5, 11, True),
              f"shown={len(full['pins'])} total={full['pin_total']} "
              f"truncated={full['truncated']} — the 5 topic pins consume the whole budget and "
              f"the 6 register rows are unreachable. Skipping them WITHOUT counting reports "
              f"(5, 5, False): a full window that claims to be the whole project")

        db.execute(rfi.delete().where(rfi.c.project_id == PID))
        db.query(Topic).filter(Topic.project_id == PID).delete()
        db.commit()
finally:
    pin_engine._MAX_PINS = _real

check("the cap constant was restored", pin_engine._MAX_PINS == _real,
      f"{pin_engine._MAX_PINS} != {_real} — a test that leaks a lowered cap into the rest of the "
      f"suite makes every later pin assertion meaningless")

# ------------------------------------------------------------------------------------------------
# NULL ORDERING, asserted against the POSTGRES dialect rather than by behaviour.
#
# A register's `created_at` is nullable (`_table()` builds it as a bare Core column), and
# **PostgreSQL sorts NULLs FIRST under DESC** — so in production an undated row is "newest" and
# eats the capped window ahead of a pin filed today. That is this PR's own defect, one dialect over.
#
# **No behavioural test in this file can catch it**, because SQLite already puts NULLs last under
# DESC: the fixture passes with or without the fix. So the check compiles the ordering against the
# Postgres dialect and asserts the emitted SQL, the way `test_fts_index.py` checks its GIN
# expression without a live Postgres. Asserting behaviour here would be a test that cannot fail.
# ------------------------------------------------------------------------------------------------
from sqlalchemy import select as _select  # noqa: E402
from sqlalchemy.dialects import postgresql as _pg  # noqa: E402

# `pin_engine.register_order(...)` — the function the query itself calls. The first draft of
# this check rebuilt the ORDER BY expression here and so PASSED with `.nulls_last()` removed from
# the source: a narrative copy of the code cannot test the code.
_t = _mr.TABLES["rfi"]
_sql = str(_select(_t.c.id).order_by(*pin_engine.register_order(_t))
           .compile(dialect=_pg.dialect()))
check("the register ordering pins NULL dates LAST in Postgres",
      "NULLS LAST" in _sql.upper(),
      f"compiled ORDER BY has no NULLS LAST: {_sql!r} — under Postgres a NULL `created_at` "
      f"sorts FIRST on DESC, so undated register rows would consume the cap ahead of recent ones")
# The negative, so the check above is known to be capable of failing: the bare `desc()` this
# replaced must NOT satisfy it.
_bare = str(_select(_t.c.id).order_by(_t.c.created_at.desc(), _t.c.id.desc())
            .compile(dialect=_pg.dialect()))
check("...and the assertion can fail: a bare desc() does not satisfy it",
      "NULLS LAST" not in _bare.upper(),
      f"a plain desc() already compiled to NULLS LAST, so the check above proves nothing: {_bare!r}")

# --- PINS-SHEET: the envelope has to reach PAPER, not just the API -------------------------------
# `resolve_pins` was honest from the day PINS-CAP landed and the plan sheet still printed a
# confident subset, because `_plan_pins` read `["pins"]` and dropped the rest of the envelope on the
# floor. The API being right does not help someone holding a printout — and the printout is what a
# superintendent walks the building with.
#
# This is the WIRING half. `test_plan_pins.py` proves the engine renders the note; without this, a
# deleted `pin_cap=` at the call site would leave every engine assertion green and the sheet silent
# again. That is the tested-but-unwired shape this repo already has a gate for.
from aec_api.routers import drawings as _dr  # noqa: E402

_real2 = pin_engine._MAX_PINS
SPID = "p-sheet-capped"
try:
    pin_engine._MAX_PINS = 5
    with SessionLocal() as db:
        # Self-contained: the block above deletes its rows on the way out, so seed our own rather
        # than inheriting a project that may or may not still exist.
        db.query(Topic).filter(Topic.project_id == SPID).delete()
        # Alternating Z **on purpose**: odd pins sit on a far-away storey, so the sheet's Z band
        # drops some of what the cap already returned. Without that the sheet row count and the
        # project count coincide at the cap and the `shown` assertion below cannot fail — an
        # assertion whose failure message describes a scenario it does not test reads as coverage
        # and is worse than no assertion.
        for i in range(8):
            db.add(Topic(id=f"t-sheet-{i}", project_id=SPID, guid=f"G-sheet-{i}", type="rfi",
                         title=f"Placed {i}", status="open",
                         anchor={"x": float(i), "y": 0.0, "z": 0.5 if i % 2 == 0 else 50.0},
                         created_at=__import__("datetime").datetime(2026, 8, 9, 0, i)))
        db.commit()
        rows, cap = _dr._plan_pins(db, SPID, 0.0, 1.2)
        check("_plan_pins returns the cap envelope, not just positions",
              isinstance(cap, dict) and set(cap) == {"truncated", "shown", "total", "approx"},
              f"got {cap!r} — the sheet cannot warn about a cap it was never told about")
        check("a capped project reaches the sheet marked as capped",
              cap["truncated"] is True and cap["total"] == 8,
              f"{cap!r} — 8 pins exist and 5 fit, so the note must print with the project total")
        # `shown` is the PROJECT-wide resolved count, deliberately NOT len(rows): the cap is spent
        # before the storey filter, so len(rows) would understate by however many pins the Z band
        # excluded and would read as a per-sheet number the code cannot actually compute.
        check("the fixture actually exercises the storey filter",
              len(rows) < cap["shown"],
              f"rows_on_sheet={len(rows)} shown={cap['shown']} — if the Z band drops nothing, the "
              f"next assertion holds under the very mutation it exists to catch")
        check("`shown` is the project count, not this storey's row count",
              cap["shown"] == pin_engine._MAX_PINS,
              f"shown={cap['shown']} rows_on_sheet={len(rows)} cap={pin_engine._MAX_PINS} — "
              f"binding `shown` to the filtered list invents a per-sheet shortfall")

        db.query(Topic).filter(Topic.project_id == SPID).delete()
        db.commit()

    # The honest negative, on a project small enough that nothing is capped.
    with SessionLocal() as db:
        db.query(Topic).filter(Topic.project_id == "p-sheet-whole").delete()
        db.add(Topic(id="t-whole", project_id="p-sheet-whole", guid="G-whole", type="rfi",
                     title="Only one", status="open", anchor={"x": 1.0, "y": 1.0, "z": 0.0},
                     created_at=__import__("datetime").datetime(2026, 6, 1)))
        db.commit()
        _, cap_ok = _dr._plan_pins(db, "p-sheet-whole", 0.0, 1.2)
        check("an UNCAPPED project reaches the sheet unmarked",
              cap_ok["truncated"] is False,
              f"{cap_ok!r} — a note that prints on every sheet is one nobody reads")
        db.query(Topic).filter(Topic.project_id == "p-sheet-whole").delete()
        db.commit()
finally:
    pin_engine._MAX_PINS = _real2
check("the cap constant was restored after the sheet block", pin_engine._MAX_PINS == _real2,
      f"{pin_engine._MAX_PINS} != {_real2}")

# The last link, asserted structurally because the two behavioural halves above cannot see it.
# `_plan_pins` returns the envelope (tested) and `_pin_layer` renders it (tested in
# `test_plan_pins.py`) — but if the router stops PASSING it, both stay green and the sheet goes
# silent. Deleting one keyword argument is exactly the kind of edit that survives a green suite.
import ast as _ast  # noqa: E402
import pathlib as _pathlib  # noqa: E402

_src = _pathlib.Path("src/aec_api/routers/drawings.py").read_text(encoding="utf-8")
_calls = [n for n in _ast.walk(_ast.parse(_src))
          if isinstance(n, _ast.Call) and isinstance(n.func, _ast.Attribute)
          and n.func.attr == "plan_svg"]
check("the plan route still calls the drawing engine",
      len(_calls) == 1,
      f"found {len(_calls)} plan_svg call(s) — this check assumes exactly one and must be "
      f"revisited, not silently widened, if the route grows another")
_kw = {k.arg for c in _calls for k in c.keywords}
check("the route passes the cap envelope through to the sheet",
      "pin_cap" in _kw and "pins" in _kw,
      f"plan_svg called with {sorted(_kw)} — without `pin_cap` the engine renders no note and "
      f"every other assertion in this file and in test_plan_pins.py still passes")

if FAILED:
    print("FAIL test_pin_cap")
    for f in FAILED:
        print("  -", f)
    sys.exit(1)
print("test_pin_cap OK  (cap spent on candidates; envelope exact when whole, flagged when not)")

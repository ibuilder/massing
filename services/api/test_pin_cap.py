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
                element_guids=[f"E-{i}"], workflow_state="open"))
        db.commit()

        mixed = pin_engine.resolve_pins(db, PID)
        ids = [p["id"] for p in mixed["pins"]]
        check("topics and registers are resolved into one list under one budget",
              ids == ["t-mix-0", "t-mix-1", "t-mix-2", "r-00", "r-01"],
              f"got {ids} — 3 topic pins then 2 register pins under a budget of 5")
        check("the register read is ordered, so a cap that bites is reproducible",
              ids[3:] == ["r-00", "r-01"],
              f"got {ids[3:]} — without an ORDER BY the two that survive differ between runs, "
              f"so the same request draws different pins")
        check("what the budget could not reach is COUNTED, not silently dropped",
              (mixed["pin_total"], mixed["truncated"]) == (9, True),
              f"total={mixed['pin_total']} truncated={mixed['truncated']} — 3 topics + 6 "
              f"register rows exist and 5 fit")

    # THE CASE THAT ACTUALLY DISTINGUISHES THE SHARED BUDGET, and the reason the assertion above
    # is worded the way it is. **A per-source cap plus a final `out[:_MAX_PINS]` returns exactly
    # the same pins as one shared budget** — both keep the same prefix — so no assertion on
    # `pins` can tell them apart, and the first draft of this file claimed one could. What the
    # shared budget changes is that a source the budget cannot reach at all is **counted** rather
    # than concatenated and then sliced away uncounted. Fill the budget with topics and the
    # registers become exactly that source.
    with SessionLocal() as db:
        db.query(Topic).filter(Topic.project_id == PID).delete()
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

if FAILED:
    print("FAIL test_pin_cap")
    for f in FAILED:
        print("  -", f)
    sys.exit(1)
print("test_pin_cap OK  (cap spent on candidates; envelope exact when whole, flagged when not)")

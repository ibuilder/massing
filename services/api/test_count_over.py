"""COUNT-OVER — the pin read's count and its rows come from ONE statement, provably.

`resolve_pins` reads each source with `func.count().over()` — `count(*) OVER ()` — so the
project-wide total and the returned window come from a single snapshot. It replaced two separate
statements, where a write committed between them leaves `pin_total` describing a different
population from `pins`.

**That fix shipped in #492 with no assertion at all.** Mutating it back to two statements passed
every one of the 688 suites, because nothing in the suite ever opened a second connection — so
nothing could observe the difference. It was named as a stated gap in four consecutive PR bodies
(#492, #493, #494 and this one) before being closed. *A fix nobody can distinguish from its absence
is a claim, not a verified behaviour.*

**How this observes it.** The count and the rows arriving in ONE SQL statement is not a proxy for
the snapshot property — it *implies* it, under any isolation level, because there is no "between" for
a write to land in. So the statement count IS the proof, and it is asserted directly: exactly one
SELECT against `topics`, carrying `OVER ()`. Reverting to two statements fails both.

**The behavioural race is NOT reproducible under this harness, and the test says so rather than
pretending.** Two attempts, both measured: `before_cursor_execute` lands the insert ahead of both
statements, and `after_cursor_execute` fires before SQLite steps the rows, so the "already-executed"
statement still sees the new row. The defect needs a reader taking a fresh snapshot per statement —
PostgreSQL READ COMMITTED. A behavioural assertion here would pass with or without the fix, which is
exactly the kind of coverage-shaped nothing this line of work exists to remove.

Run: `PYTHONPATH=src:../data/src python test_count_over.py`
"""
from __future__ import annotations

import os

# BEFORE importing `aec_api.db` — see the same note in `test_pin_cap.py`. This file calls
# `create_all`, and `test_db_url_isolation.py` enforces that it declares its own database.
os.environ["DATABASE_URL"] = "sqlite:///./test_count_over.db"
os.environ.pop("AEC_RBAC", None)

import datetime  # noqa: E402
import sys  # noqa: E402

FAILED: list[str] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    if not ok:
        FAILED.append(f"{name} — {detail}")


from sqlalchemy import event  # noqa: E402

from aec_api import modules_registry as _mr  # noqa: E402
from aec_api import pins as pin_engine  # noqa: E402
from aec_api.db import Base, SessionLocal, engine  # noqa: E402
from aec_api.models import Topic  # noqa: E402

_mr.load_registry()
Base.metadata.create_all(bind=engine)

# WAL, because the race below needs a SECOND connection to COMMIT while the first is mid-read.
# SQLite's default rollback journal is single-writer: that commit raises "database is locked" and the
# test dies instead of measuring anything. WAL lets one writer proceed alongside readers, which is
# the concurrency this test exists to exercise — and is also what Postgres does natively, so the
# shape being tested is the shape production runs.
with engine.connect() as _c:
    _c.exec_driver_sql("PRAGMA journal_mode=WAL")
    _c.commit()

PID = "p-countover"


def _pin(i: int, tag: str) -> Topic:
    return Topic(id=f"t-{tag}-{i}", project_id=PID, guid=f"G-{tag}-{i}", type="rfi",
                 title=f"Placed {i}", status="open", anchor={"x": float(i), "y": 0.0, "z": 0.0},
                 created_at=datetime.datetime(2026, 9, 1, 0, i))


def _seed(n: int) -> None:
    with SessionLocal() as db:
        db.query(Topic).filter(Topic.project_id == PID).delete()
        for i in range(n):
            db.add(_pin(i, "base"))
        db.commit()


# --- how many statements does one source's read take? ----------------------------------------------
# The mechanism, asserted directly. A read that takes two statements has a gap; one that takes one
# has nowhere for a write to land.
_seen: list[str] = []


def _record(conn, cursor, statement, parameters, context, executemany):  # noqa: ANN001, ARG001
    if "topics" in statement.lower() and statement.lstrip().lower().startswith("select"):
        _seen.append(statement)


_seed(4)
event.listen(engine, "before_cursor_execute", _record)
try:
    with SessionLocal() as db:
        env = pin_engine.resolve_pins(db, PID)
finally:
    event.remove(engine, "before_cursor_execute", _record)

check("the topic source reads rows and total in ONE statement",
      len(_seen) == 1,
      f"{len(_seen)} SELECT(s) against `topics`: {[s.split(chr(10))[0][:70] for s in _seen]} — "
      f"two statements is two snapshots, and a write can commit between them")
check("...and that one statement carries the window function",
      bool(_seen) and "over ()" in _seen[0].lower().replace("over()", "over ()"),
      f"no OVER () in: {_seen[0][:200] if _seen else '<none>'}")
check("the uncapped read is self-consistent to begin with",
      (len(env["pins"]), env["pin_total"], env["truncated"]) == (4, 4, False),
      f"shown={len(env['pins'])} total={env['pin_total']} truncated={env['truncated']}")


# --- a concurrent commit during the read must not break it -----------------------------------------
# **This block does NOT prove the snapshot property, and must not be read as doing so.** The
# structural assertions above are what prove it: one statement cannot be interleaved, under any
# isolation level, because there is no "between".
#
# Reproducing the race behaviourally was attempted and **is not possible under this harness**, for
# two independent reasons found by measurement rather than assumed:
#
#   1. `before_cursor_execute` fires ahead of the statement, so an insert made there lands before
#      BOTH statements of the two-statement shape and they agree anyway.
#   2. `after_cursor_execute` fires before SQLite has stepped the result rows, so an insert made
#      there can still be seen by the statement that supposedly already ran — measured directly:
#      under the two-statement mutation both the count and the window returned 5, not 4 then 5.
#
# The defect needs a reader whose statements each take a FRESH snapshot — PostgreSQL's default READ
# COMMITTED. SQLite gives a reader a stable view and the hook cannot place a commit between two
# statements, so a behavioural assertion here would pass whether or not the fix is present. That is
# the shape this whole line of work exists to stamp out, so it is stated instead of written.
#
# What this DOES assert: the read completes and stays self-consistent while another connection
# commits a qualifying pin. That is a real regression guard (an exception, a partial read, a torn
# envelope would all fail it) and it is not the snapshot proof.
_fired: list[int] = []


def _inject(conn, cursor, statement, parameters, context, executemany):  # noqa: ANN001, ARG001
    """Commit a qualifying pin from a separate connection while the read is in flight."""
    if _fired or "topics" not in statement.lower():
        return
    if not statement.lstrip().lower().startswith("select"):
        return
    _fired.append(1)
    with engine.connect() as other:
        other.execute(
            Topic.__table__.insert().values(
                id="t-racer", project_id=PID, guid="G-racer", type="rfi", title="Raced in",
                status="open", anchor={"x": 9.0, "y": 9.0, "z": 0.0},
                created_at=datetime.datetime(2026, 9, 2)))
        other.commit()


_seed(4)
event.listen(engine, "after_cursor_execute", _inject)
try:
    with SessionLocal() as db:
        raced = pin_engine.resolve_pins(db, PID)
finally:
    event.remove(engine, "after_cursor_execute", _inject)

check("the injected write actually fired — otherwise this block measures nothing",
      bool(_fired),
      "no statement matched the hook, so no concurrent commit happened at all")

shown, total = len(raced["pins"]), raced["pin_total"]
check("the read survives a concurrent commit and returns a self-consistent envelope",
      total >= shown and shown == total and raced["truncated"] is (total > shown),
      f"shown={shown} total={total} truncated={raced['truncated']} — uncapped, so these must "
      f"agree; a mismatch here means the read tore, not that the snapshot property failed")
check("...and it saw one of the two whole states, not a mixture",
      total in (4, 5),
      f"total={total} — 4 (before the racing insert) or 5 (after) are the only coherent answers")

with SessionLocal() as db:
    db.query(Topic).filter(Topic.project_id == PID).delete()
    db.commit()

if FAILED:
    print("FAIL test_count_over")
    for f in FAILED:
        print("  -", f)
    sys.exit(1)
print(f"test_count_over OK  (1 statement per source; race injected and survived; "
      f"total={total} shown={shown})")

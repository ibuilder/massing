"""R22-ROUTINES — due work actually gets enqueued, and the same window never fires twice.

`routines.due()` already decides correctly and refuses well; `jobs.enqueue` already rejects an
unregistered kind; `worker.py` already runs the queue. **Nothing joined them** — both `/routines/due`
endpoints are read-only, so "what should run now" was computed, returned and dropped. That is the
entry's own complaint: a tool you remember to use rather than infrastructure.

**The defect worth the test is the one that was latent.** `routines.from_project(db, pid, now,
in_flight)` takes `in_flight` as a parameter and **no caller supplied it**, so the one refusal in the
chain that needs outside knowledge — "the previous run has not finished" — could never fire. With the
default empty set a monthly report that takes an hour is re-enqueued on every sweep for that hour.

So these run against a real session and the real `jobs.enqueue`, not a stub: the join is the subject,
and a fake queue would agree with whatever I wrote.

Run: PYTHONPATH="src;../data/src" ./.venv/Scripts/python.exe test_routines_run.py
"""
import os
import sys

os.environ["DATABASE_URL"] = "sqlite:///./test_routines_run.db"
os.environ["STORAGE_DIR"] = "./test_storage_routines_run"
for _f in ("./test_routines_run.db",):
    if os.path.exists(_f):
        os.remove(_f)

sys.path.insert(0, "src")

from datetime import datetime, timezone  # noqa: E402

from aec_api import jobs, modules_registry, routines_run  # noqa: E402
from aec_api import modules as me  # noqa: E402
from aec_api.db import Base, SessionLocal, engine  # noqa: E402
from aec_api.models import Job, Project  # noqa: E402

FAILED: list[str] = []


def check(label, ok, detail=""):
    print(f"{'PASS' if ok else 'FAIL'}  {label}{(' — ' + str(detail)) if detail and not ok else ''}")
    if not ok:
        FAILED.append(label)


# The register must be loaded explicitly outside the app lifespan. Skipping this is the same trap as
# a TestClient built outside a `with` block: every module reads as absent and the failure looks like a
# missing feature rather than an unstarted registry.
modules_registry.load_registry()
Base.metadata.create_all(engine)
db = SessionLocal()
PID = "p-routines"
db.add(Project(id=PID, name="Routines")); db.commit()

# `echo` is a registered kind; `not_a_kind` is not. Both are needed: the refusal only means something
# if a real kind succeeds beside it in the same sweep.
check("the queue really registers `echo`, so a success here is not vacuous", "echo" in jobs.KINDS,
      sorted(jobs.KINDS))


def routine(name, kind, cadence="daily", state="active", last_run=None):
    """Create a routine in a given workflow state.

    `create_record` files new records as **draft**, and `from_project` deliberately evaluates only
    `active` ones — draft was never switched on, retired was switched off. So the state has to be set
    explicitly here; a test that skipped it would assert on routines the scheduler correctly ignores
    and prove nothing.
    """
    rec = me.create_record(db, "routine", PID,
                           {"data": {"name": name, "kind": kind, "cadence": cadence,
                                     **({"last_run": last_run} if last_run else {})}},
                           "tester", None)
    rid = rec["id"]
    t = me.TABLES["routine"]          # a Core Table, so columns are t.c.*, not attributes
    db.execute(t.update().where(t.c.id == rid).values(workflow_state=state))
    db.commit()
    return rid


NOW = datetime(2026, 8, 7, 9, 0, tzinfo=timezone.utc)

r_ok = routine("Nightly model CI", "echo")
r_bad = routine("Broken", "not_a_kind")
r_draft = routine("Never switched on", "echo", state="draft")

# --- 1. THE JOIN: due work becomes queued work ----------------------------------------------------
# Called inside a guard on purpose. If a misconfigured routine aborts the sweep, `run_due` raises and
# every check below would die with a traceback instead of one named failure — a gate that crashes
# still gates, but it stops saying WHAT is wrong. This turns that case into a named FAIL.
try:
    out = routines_run.run_due(db, PID, now=NOW, actor="test")
    _raised = None
except Exception as _e:                                    # noqa: BLE001
    out, _raised = {"enqueued": [], "enqueued_count": 0, "refused": [], "note": "",
                    "in_flight_kinds": []}, _e
check("THE SWEEP SURVIVES A MISCONFIGURED ROUTINE — it must not raise out of run_due",
      _raised is None, repr(_raised))
check("a due routine is ENQUEUED, not merely reported as due",
      [e["routine_id"] for e in out["enqueued"]] == [r_ok], out["enqueued"])
check("  and a real job row exists for it",
      db.query(Job).filter(Job.id == out["enqueued"][0]["job_id"]).one().state == "queued")
check("  carrying the routine and window it came from, so the job is traceable",
      (db.query(Job).filter(Job.id == out["enqueued"][0]["job_id"]).one().params or {}
       ).get("routine_id") == r_ok)

# --- 2. AN UNKNOWN KIND IS REPORTED, NOT FATAL ----------------------------------------------------
check("THE MISCONFIGURED ROUTINE DID NOT ABORT THE SWEEP — the good one still ran",
      out["enqueued_count"] == 1 and any(f["routine_id"] == r_bad for f in out["refused"]),
      (out["enqueued_count"], out["refused"]))
check("  and it is refused by name with the registered kinds listed",
      out["refused"][0]["status"] == routines_run.STATUS_UNKNOWN_KIND
      and "not_a_kind" in out["refused"][0]["reason"], out["refused"])
check("a draft routine is never fired", all(e["routine_id"] != r_draft for e in out["enqueued"]))

# --- 3. THE SAME WINDOW DOES NOT FIRE TWICE -------------------------------------------------------
again = routines_run.run_due(db, PID, now=NOW, actor="test")
check("A SECOND SWEEP IN THE SAME WINDOW ENQUEUES NOTHING — the window was consumed at enqueue",
      again["enqueued_count"] == 0, again["enqueued"])
check("  and the queue did not grow",
      db.query(Job).filter(Job.project_id == PID, Job.kind == "echo").count() == 1)

# --- 4. THE LATENT ONE: in_flight is DERIVED, so unfinished work blocks the next fire --------------
# Move to the next window so the routine is due again, but leave its job unfinished.
NEXT = datetime(2026, 8, 8, 9, 0, tzinfo=timezone.utc)
busy = routines_run.in_flight_kinds(db, PID)
check("in-flight kinds are read from the JOBS TABLE, not assumed empty", "echo" in busy, busy)

third = routines_run.run_due(db, PID, now=NEXT, actor="test")
check("A ROUTINE WHOSE PREVIOUS JOB IS STILL QUEUED IS NOT RE-ENQUEUED",
      third["enqueued_count"] == 0, third["enqueued"])
check("  and the sweep says which kinds it is waiting on",
      third["in_flight_kinds"] == ["echo"], third["in_flight_kinds"])

# finish the job; now the next window may fire
db.query(Job).filter(Job.project_id == PID, Job.kind == "echo").update({"state": "done"}); db.commit()
fourth = routines_run.run_due(db, PID, now=NEXT, actor="test")
check("ONCE THE JOB FINISHES the next window fires — the block was in-flight, not permanent",
      fourth["enqueued_count"] == 1, fourth["enqueued"])

# --- 5. missed windows fire ONCE, never one job per window ----------------------------------------
r_old = routine("Monthly, dormant a year", "echo", cadence="monthly", last_run="2025-08-01")
db.query(Job).filter(Job.project_id == PID).update({"state": "done"}); db.commit()
LATER = datetime(2026, 8, 9, 9, 0, tzinfo=timezone.utc)
n_before = db.query(Job).filter(Job.project_id == PID).count()
fifth = routines_run.run_due(db, PID, now=LATER, actor="test")
n_after = db.query(Job).filter(Job.project_id == PID).count()
fired = [e for e in fifth["enqueued"] if e["routine_id"] == r_old]
check("A ROUTINE DORMANT FOR TWELVE WINDOWS FIRES ONCE, not twelve times",
      len(fired) == 1, fired)
check("  and the missed count is reported rather than replayed",
      (fired[0]["missed_windows"] or 0) >= 1, fired[0])
check("  so the queue grew by the number of DUE routines, not by windows missed",
      n_after - n_before == fifth["enqueued_count"], (n_before, n_after, fifth["enqueued_count"]))
check("the note names the flood it is preventing", "flood the queue" in fifth["note"])

db.close()
engine.dispose()

print()
if FAILED:
    print(f"routines_run: {len(FAILED)} FAILED — {FAILED}")
    sys.exit(1)
print("routines_run: all checks passed")

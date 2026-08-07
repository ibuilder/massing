"""JOB-WORKER-SCALE — orphan recovery must not steal a job a live worker is running.

THE DEFECT. `start_worker()` re-queued **every** `running` row in the database:

    orphans = list(db.scalars(select(Job).where(Job.state == "running")))

Correct while exactly one process ever ran the queue. `docker-compose.yml` now documents
`docker compose --profile full up -d --scale worker=3`, and under that a worker booting re-queued the
jobs its siblings were mid-execution on. Each of those then ran in **two processes at once** — for a
mutating kind, two writers inside one project.

**The compare-and-swap does not close this, and the compose comment claiming it does was the most
dangerous part.** `_claim_next`'s CAS arbitrates who may take a row that is already `queued`. A row
reset to `queued` underneath a live worker is not a race it can detect — it is the CAS faithfully
handing out a job somebody is still running. "Handlers are idempotent" is the contract for a
crash-recovery RE-RUN; it says nothing about two copies interleaving at the same instant.

THE FIX. A claim stamps `heartbeat_at` in the same statement that wins the row, a running job
refreshes it on a background thread, and recovery re-queues only rows whose heartbeat has stopped.

WHAT THIS ASSERTS, and the pairing is the point — a recovery that re-queues nothing passes the first
check as easily as a correct one:
  * a `running` row with a FRESH heartbeat is left alone (the sibling-worker case, the actual bug);
  * a `running` row with a STALE heartbeat is re-queued (crash recovery still works);
  * a legacy row with NO heartbeat is recovered via `started_at`, so rows claimed before the column
    existed are not immortal;
  * ...but a legacy-shaped row claimed moments ago is NOT — a new claim writes both fields together,
    so "no heartbeat" alone must never be enough.

Run: PYTHONPATH="src;../data/src" ./.venv/Scripts/python.exe test_job_orphan_scope.py
"""
import os
import sys
from datetime import timedelta

os.environ["DATABASE_URL"] = "sqlite:///./test_job_orphan_scope.db"
os.environ["STORAGE_DIR"] = "./test_storage_job_orphan_scope"
for _f in ("./test_job_orphan_scope.db",):
    if os.path.exists(_f):
        os.remove(_f)

from aec_api import jobs  # noqa: E402
from aec_api.db import Base, SessionLocal, engine  # noqa: E402
from aec_api.models import Job  # noqa: E402
from aec_api.timeutil import utc_now  # noqa: E402

Base.metadata.create_all(bind=engine)
failures: list[str] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    print(f"  {'ok  ' if ok else 'FAIL'}  {name}{('  — ' + detail) if detail and not ok else ''}")
    if not ok:
        failures.append(name)


STALE = jobs._STALE_AFTER_SECONDS
now = utc_now()


def mk(jid: str, *, heartbeat, started) -> None:
    with SessionLocal() as db:
        db.add(Job(id=jid, kind="probe", project_id="p1", state="running",
                   params={}, started_at=started, heartbeat_at=heartbeat))
        db.commit()


# A sibling worker's live job: claimed a while ago, heartbeat current.
mk("live", heartbeat=now, started=now - timedelta(seconds=STALE * 3))
# A crashed process's job: heartbeat stopped well beyond the window.
mk("dead", heartbeat=now - timedelta(seconds=STALE * 2), started=now - timedelta(seconds=STALE * 3))
# A row from a build older than the column: no heartbeat, claimed long ago.
mk("legacy-old", heartbeat=None, started=now - timedelta(seconds=STALE * 2))
# A row claimed moments ago whose heartbeat has not been written yet.
mk("legacy-fresh", heartbeat=None, started=now)

with SessionLocal() as db:
    requeued = set(jobs.recover_orphans(db))

check("a LIVE sibling's job is NOT re-queued — the defect this fixes", "live" not in requeued,
      "a job another worker is executing was handed back to the queue; it now runs twice")
check("a crashed process's job IS re-queued — recovery still works", "dead" in requeued,
      f"got {sorted(requeued)}")
check("a legacy row with no heartbeat and an old claim is recovered", "legacy-old" in requeued,
      f"got {sorted(requeued)}")
check("a legacy-shaped row claimed moments ago is NOT recovered",
      "legacy-fresh" not in requeued,
      "absence of a heartbeat alone was treated as death — a just-claimed job would be stolen")

with SessionLocal() as db:
    states = {j.id: (j.state, j.started_at, j.heartbeat_at)
              for j in db.scalars(jobs.select(Job)).all()}
check("the re-queued rows are actually back in `queued`",
      states["dead"][0] == "queued" and states["legacy-old"][0] == "queued",
      str({k: v[0] for k, v in states.items()}))
check("...with their claim stamps cleared, so they look unclaimed to the next worker",
      states["dead"][1] is None and states["dead"][2] is None, str(states["dead"]))
check("the live job is untouched — still running, heartbeat intact",
      states["live"][0] == "running" and states["live"][2] is not None, str(states["live"]))

# The claim must stamp the heartbeat in the SAME statement, or a sibling booting inside the gap
# between "state=running" and "heartbeat written" sees an orphan and steals a job about to start.
with SessionLocal() as db:
    db.add(Job(id="fresh-claim", kind="probe", project_id="p1", state="queued", params={}))
    db.commit()
with SessionLocal() as db:
    claimed = jobs._claim_next(db)
check("a freshly claimed job carries a heartbeat immediately",
      claimed is not None and claimed.heartbeat_at is not None,
      f"claimed={getattr(claimed, 'id', None)} heartbeat={getattr(claimed, 'heartbeat_at', None)}")

# And that job must survive a recovery pass run a moment later — the exact sibling-boot sequence.
with SessionLocal() as db:
    again = set(jobs.recover_orphans(db))
check("a job claimed one moment ago survives a sibling's boot-time recovery",
      "fresh-claim" not in again, f"re-queued {sorted(again)} — the boot race is still open")

print(f"\ntest_job_orphan_scope {'OK' if not failures else 'FAILED: ' + ', '.join(failures)}")
sys.exit(1 if failures else 0)

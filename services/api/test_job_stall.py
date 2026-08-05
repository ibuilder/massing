"""JOB-STALL-VISIBLE: a wedged queue is distinguishable from an idle one, and from an unreadable one.

JOB-WORKER-SPLIT (v0.3.869) let the job worker run in its own container. That closed a scaling
ceiling and opened an observability hole: with the worker somewhere else, **nothing the API can see
changes when the worker dies.** The API is healthy — it does not run jobs. The worker container may
even be up and wedged. Every enqueue keeps succeeding. The only thing that differs between a stalled
queue and a healthy idle one is that a stalled queue has an *old job at its head*.

So the metric is the age of the head, and these tests are about the three ways such a metric lies:

  1. **zero-for-absent** — reporting `oldest_queued_seconds 0` on an empty queue reads as "the oldest
     job is brand new" and makes an `> N` alert useless for the case it was written for;
  2. **absent-for-broken** — if a failed DB read also produces no series, "could not measure" and
     "nothing queued" render identically, and an operator will read the reassuring one;
  3. **depth-as-alarm** — a single job wedged for six hours never crosses a depth threshold, and a
     deep queue draining fast crosses it while healthy.

Run: PYTHONPATH=src ./.venv/Scripts/python.exe test_job_stall.py
"""
import os

os.environ.setdefault("DATABASE_URL", "sqlite:///./_job_stall_test.db")
os.environ.setdefault("STORAGE_DIR", "./_storage_job_stall")
os.environ.setdefault("IFC_DIR", "./_ifc_job_stall")
os.environ.pop("AEC_RBAC", None)
if os.path.exists("./_job_stall_test.db"):
    os.remove("./_job_stall_test.db")

import sys  # noqa: E402
from datetime import timedelta  # noqa: E402
from pathlib import Path  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "data" / "src"))

from aec_api import jobs, metrics  # noqa: E402
from aec_api.db import SessionLocal, init_db  # noqa: E402
from aec_api.models import Job  # noqa: E402
from aec_api.timeutil import utc_now  # noqa: E402

init_db()


def lines(stats, inline=True) -> str:
    return "\n".join(metrics.render_queue(stats, inline))


# --- an empty queue reports NO age, not a zero age ------------------------------------------------
with SessionLocal() as db:
    empty = jobs.queue_stats(db)
assert empty["queued"] == 0, empty
assert empty["oldest_queued_seconds"] is None, (
    "an empty queue must report None, not 0.0 — zero says 'the head of the queue is brand new', "
    "which is the opposite of 'there is no head'")
assert "aec_jobs_oldest_queued_seconds" not in lines(empty), (
    "the age series must be OMITTED on an empty queue. Emitting 0 makes `> 600` never fire on a "
    "stall AND always look healthy, which is the exact failure this metric exists to prevent")

# --- a queued job produces an age, and the age is the HEAD's, not the newest ----------------------
jobs.register_kind("_stall_probe", lambda db, params: {"ok": True})
with SessionLocal() as db:
    old = Job(kind="_stall_probe", project_id=None, params={}, state="queued",
              created_at=utc_now() - timedelta(hours=6))
    new = Job(kind="_stall_probe", project_id=None, params={}, state="queued",
              created_at=utc_now() - timedelta(seconds=5))
    db.add_all([old, new])
    db.commit()

with SessionLocal() as db:
    s = jobs.queue_stats(db)
assert s["queued"] == 2, s
age = s["oldest_queued_seconds"]
assert age is not None and age > 20_000, (
    f"age must come from the OLDEST queued row (~21600s), got {age}. Reading the newest — or a mean "
    "of the two — would report ~5s and call a six-hour stall healthy")
assert "aec_jobs_oldest_queued_seconds 21" in lines(s), lines(s)

# --- a RUNNING job is not part of the head-of-line age --------------------------------------------
# A job that has been claimed is being worked on; its age is a different question (a slow job, not a
# stalled queue). Counting it here would make a legitimately long conversion look like a stall.
with SessionLocal() as db:
    db.add(Job(kind="_stall_probe", project_id=None, params={}, state="running",
               created_at=utc_now() - timedelta(days=3)))
    db.commit()
    s2 = jobs.queue_stats(db)
assert s2["running"] == 1, s2
assert abs(s2["oldest_queued_seconds"] - age) < 60, (
    "a 3-day-old RUNNING job changed the queued age — the alarm would fire for a long job rather "
    "than a stalled queue")

# --- 'could not read' is DISTINCT from 'nothing queued' -------------------------------------------
# The load-bearing assertion. Without the ok-gauge these two render identically, and the difference
# between "the database is unreachable" and "all quiet" is the difference between an incident and a
# normal Tuesday.
broken, quiet = lines(None), lines(empty)
assert "aec_jobs_stats_ok 0" in broken, broken
assert "aec_jobs_stats_ok 1" in quiet, quiet
assert broken != quiet, "an unreadable queue and an empty queue must not produce the same output"
assert "aec_jobs_by_state" not in broken, "no state counts may be invented when the read failed"

# --- the worker-location gauge reports THIS process, both ways -------------------------------------
# After the split an operator needs to see that *somebody* runs a worker. If every scraped process
# reports inline=0 and no worker container is scraped at all, that is the misconfiguration.
assert "aec_jobs_worker_inline 1" in lines(empty, inline=True)
assert "aec_jobs_worker_inline 0" in lines(empty, inline=False)

# --- the exposition stays parseable ---------------------------------------------------------------
# Prometheus rejects a whole scrape on a malformed line, so a broken HELP/TYPE here would silently
# take out the request metrics too.
for ln in lines(s).splitlines():
    if ln.startswith("#"):
        assert ln.split()[1] in ("HELP", "TYPE"), ln
    else:
        parts = ln.rsplit(" ", 1)
        assert len(parts) == 2, ln
        float(parts[1])                                # raises if the value is not a number

# --- and it actually comes out of /metrics ---------------------------------------------------------
# Everything above tests pure functions. A perfect metric that no endpoint serves is invisible, which
# is the same defect as a tested module behind no route — and it is the one this repo has shipped
# most often. So assert over HTTP, against the app, with a real queued row in the database.
from fastapi.testclient import TestClient  # noqa: E402

from aec_api.main import app  # noqa: E402

os.environ["AEC_JOB_WORKER"] = "off"          # also proves the gauge reflects the live env
with TestClient(app) as c:
    body = c.get("/metrics").text
assert "aec_jobs_stats_ok 1" in body, "the /metrics scrape did not include the queue block"
assert "aec_jobs_worker_inline 0" in body, "worker_inline must reflect AEC_JOB_WORKER at scrape time"
assert 'aec_jobs_by_state{state="queued"} 2' in body, body[-600:]
assert "aec_jobs_oldest_queued_seconds 21" in body, (
    "the six-hour-old head of the queue is not visible in the scrape — an operator alerting on this "
    "series would see nothing while the queue was stalled")
# the pre-existing request metrics must survive the append
assert "http_requests_total" in body, "appending the queue block broke the existing exposition"
os.environ.pop("AEC_JOB_WORKER", None)

for f in ("./_job_stall_test.db",):
    if os.path.exists(f):
        try:
            os.remove(f)
        except OSError:
            pass

print("JOB-STALL OK - an empty queue reports None and OMITS the age series (never 0, which would "
      "make a `> N` stall alert both silent and reassuring); the age is the OLDEST queued row's, "
      "unaffected by a 3-day-old RUNNING job; an unreadable queue renders aec_jobs_stats_ok 0 and "
      "invents no counts, so 'could not measure' is distinguishable from 'nothing queued'; the "
      "worker-location gauge reports both ways; and the exposition parses.")

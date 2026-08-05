"""JOB-WORKER-SPLIT — run the durable job queue in its own process: `python -m aec_api.worker`.

The queue's heavy kinds are full-model IFC parses (COBie handover export, bundle generation,
generative runs). Run inline in the API process — which is where they have always run, and still run
by default — one large reconvert competes for CPU and memory with every HTTP request the same
container is serving. The symptom is not an error; it is the whole application getting slower for
everyone while one person converts a model, which is the failure mode that looks like "the product is
slow" rather than "a job is running".

Splitting them apart is possible only because two things already landed and are load-bearing here:

  · `jobs._claim_next` is a **compare-and-swap** (`UPDATE … WHERE id = :id AND state = 'queued'`), so
    two processes racing for one job cannot both win — the loser sees rowcount 0 and takes the next
    job rather than sleeping. Notably NOT `FOR UPDATE SKIP LOCKED`, which is a silent no-op on SQLite;
  · `pid_lock` became cross-process in R35-PIDLOCK-XPROC (a Postgres session advisory lock), so a
    mutating job in this process still serialises against an API edit in another.

Neither was written for this split, and both are exactly what it needs. Nothing here re-implements
them — `run_forever()` calls the same `start_worker()` the API calls, for the same reason: a second
copy of a concurrency-critical loop drifts, and nothing fails when it does.

## What this process does NOT do

It builds no FastAPI app, binds no port, and serves no request. It therefore has **no HTTP
healthcheck** — liveness is "the process is up and the queue is draining", which is a property of the
queue, not of this process. A worker container that is running but wedged looks identical to a
healthy idle one from the outside, and only the queue can tell them apart.

That signal now exists, so alert on it rather than on this container: the API's `/metrics` exposes
`aec_jobs_oldest_queued_seconds` (JOB-STALL-VISIBLE, v0.3.870), the age of the head of the queue,
**absent when nothing is queued** so a `> N` rule stays quiet on an idle system. Alert on that age,
not on `aec_jobs_by_state{state="queued"}` — a deep queue draining fast is healthy, and one job
wedged for six hours never crosses a depth threshold.

## The failure mode to know about

Setting `AEC_JOB_WORKER=off` on the API without running this process means every job queues forever
and **nothing raises** — the enqueue succeeds, the row is written, the caller is told the work is
under way, and it never happens. That silence is defended in three places: `main.py` logs a warning
at boot naming this exact command, `test_worker_split.py` fails the build if a compose file sets
`off` without a service that runs it, and this docstring, for whoever is reading at 3am.
"""
from __future__ import annotations

import logging
import os
import sys


def main() -> int:
    logging.basicConfig(
        level=os.environ.get("AEC_LOG_LEVEL", "INFO").upper(),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    log = logging.getLogger("aec.worker")

    # Import inside main so a bad DATABASE_URL surfaces as a logged failure from a running process
    # rather than an import-time traceback before logging is configured.
    from . import jobs

    # The registry is populated as a side effect of importing the app module — the handlers live
    # beside the routes that enqueue them. Without this the worker starts happily and every job fails
    # with "unknown kind", which reads like bad data rather than a missing import.
    from . import main as app_main  # noqa: F401
    if not jobs.KINDS:
        log.error("no job kinds registered — refusing to run a worker that cannot handle anything")
        return 2

    log.info("starting dedicated job worker (%d kinds)", len(jobs.KINDS))
    jobs.run_forever()
    return 0


if __name__ == "__main__":
    sys.exit(main())

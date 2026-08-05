"""JOB-WORKER-SPLIT: the job queue can run in its own process, and a deployment cannot half-do it.

The split's whole risk is **silence**. Setting `AEC_JOB_WORKER=off` on the API without running a
worker leaves every enqueue succeeding, every Job row written, every caller told the work is under
way — and nothing ever runs it. No exception, no 500, no failed healthcheck. The queue simply grows.

So the checks here are chosen by asking the mutation question — *which of these still passes if the
code does nothing?* — and the answers shaped the file:

  · asserting `worker_enabled()` alone would pass even if `main.py` ignored it entirely, so the flag
    is checked **through a started app**, by looking for the worker thread;
  · asserting the `off` case alone would pass on a build where the worker never starts at all, so it
    is paired with its twin (default → the thread IS running);
  · asserting `worker.py` imports would pass on an empty module, so `run_forever()` is made to drain
    a real job;
  · and none of the above can see a compose file that turns the API's worker off without adding the
    container that replaces it — which is the actual production accident — so that is checked
    against the compose files themselves.

Run: PYTHONPATH=src ./.venv/Scripts/python.exe test_worker_split.py
"""
import os
import time

os.environ.setdefault("DATABASE_URL", "sqlite:///./_worker_split_test.db")
os.environ.setdefault("STORAGE_DIR", "./_storage_worker_split")
os.environ.setdefault("IFC_DIR", "./_ifc_worker_split")
os.environ.pop("AEC_RBAC", None)
os.environ["AEC_AUTOSYNC"] = "0"          # the boot autosync loop is unrelated noise here
if os.path.exists("./_worker_split_test.db"):
    os.remove("./_worker_split_test.db")

import sys  # noqa: E402
import threading  # noqa: E402
from pathlib import Path  # noqa: E402

import yaml  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "data" / "src"))

from aec_api import jobs  # noqa: E402
from aec_api.db import SessionLocal, init_db  # noqa: E402
from aec_api.models import Job  # noqa: E402

init_db()
REPO = Path(__file__).resolve().parents[2]


def _worker_alive() -> bool:
    return any(t.name == "aec-job-worker" and t.is_alive() for t in threading.enumerate())


# --- A. the flag's truth table ---------------------------------------------------------------------
# `inline` is the default because an unset variable must mean "behave as before". Defaulting to `off`
# would be the plausible-sounding choice and would silently stop every existing single-container
# deployment from running any job, with nothing raising anywhere.
os.environ.pop(jobs.WORKER_ENV, None)
assert jobs.worker_enabled(), "unset must mean inline — an upgrade must not stop an existing deployment"
for off in ("off", "OFF", " off ", "Off"):
    os.environ[jobs.WORKER_ENV] = off
    assert not jobs.worker_enabled(), f"{off!r} must disable the in-process worker"
for on in ("inline", "1", "yes", "", "onlnie"):
    os.environ[jobs.WORKER_ENV] = on
    assert jobs.worker_enabled(), (
        f"{on!r} must fall through to inline — a typo'd value must not silently stop the queue, "
        "which is the unrecoverable reading of an ambiguous instruction")
os.environ.pop(jobs.WORKER_ENV, None)

# the value is read per call, never cached at import: an env change must take effect
os.environ[jobs.WORKER_ENV] = "off"
assert not jobs.worker_enabled()
os.environ[jobs.WORKER_ENV] = "inline"
assert jobs.worker_enabled(), "worker_enabled() must not cache its answer at import time"

# --- B. a STARTED app honours the flag, in both directions -----------------------------------------
# This is the half that cannot be faked. `worker_enabled()` returning the right boolean proves nothing
# about `main.py` reading it; only a real startup does. The `off` assertion runs FIRST and before
# anything else in this file starts a worker, so the `inline` assertion that follows genuinely
# demonstrates the flag changed the behaviour rather than the thread having been there all along.
from fastapi.testclient import TestClient  # noqa: E402

from aec_api.main import app  # noqa: E402

assert not _worker_alive(), "no worker should be running before the first app start"

os.environ[jobs.WORKER_ENV] = "off"
with TestClient(app):
    assert not _worker_alive(), (
        "AEC_JOB_WORKER=off but main.py started the in-process worker anyway — the API would be doing "
        "the heavy parses the split exists to move off it")

os.environ[jobs.WORKER_ENV] = "inline"
with TestClient(app):
    assert _worker_alive(), (
        "the default deployment lost its worker. This is the twin of the assertion above: without it, "
        "a build where start_worker() never runs at all would pass the `off` check and look correct")
jobs.stop_worker()
time.sleep(0.2)

# --- C. the dedicated entrypoint actually drains the queue -----------------------------------------
# `jobs.run_forever()` is what `python -m aec_api.worker` runs. An entrypoint that starts cleanly and
# processes nothing is precisely the failure this split can produce, so assert on a finished job.
from aec_api import worker  # noqa: E402

assert callable(worker.main), "the worker entrypoint must be callable"
assert jobs.KINDS, (
    "importing aec_api.main must populate the kind registry — worker.py depends on that import for "
    "its handlers, and without it every job fails as 'unknown kind', which reads like bad data")

_ran: list[dict] = []
jobs.register_kind("_split_probe", lambda db, params: _ran.append(params) or {"ok": True})

with SessionLocal() as db:
    probe = jobs.enqueue(db, "_split_probe", None, {"n": 7})
    db.commit()
    probe_id = probe.id

t = threading.Thread(target=jobs.run_forever, daemon=True, name="probe-run-forever")
t.start()   # off the main thread on purpose: run_forever must survive not being able to trap signals

deadline = time.time() + 20.0
state = None
while time.time() < deadline:
    with SessionLocal() as db:
        j = db.get(Job, probe_id)
        state = j.state if j else None
    if state in ("done", "error"):
        break
    time.sleep(0.1)

jobs.stop_worker()
t.join(timeout=10.0)
assert state == "done", f"run_forever() did not drain the queue (job state={state!r})"
assert _ran == [{"n": 7}], f"the handler did not receive its params: {_ran!r}"
assert not t.is_alive(), "run_forever() ignored stop_worker() — a worker container would never shut down"

# --- C2. the split is only SAFE where pid_lock spans processes -------------------------------------
# The gap this file missed when it was written (v0.3.869) and that closed in v0.3.872: a dedicated
# worker is a second writer, and `pid_lock` serialises across processes ONLY on Postgres. On any
# other backend it is a `threading.RLock`, which two processes cannot share — so a mutating job here
# and a document upload in the API interleave their load→save on one sidecar index and an entry
# disappears with nothing raised. This test process is on SQLite, which is exactly the unsafe case.
from aec_api import pid_lock  # noqa: E402

assert not pid_lock.cross_process_status()["cross_process"], (
    "this test asserts the REFUSAL path and needs a backend without an advisory lock; on Postgres "
    "it would be asserting nothing")

os.environ.pop(worker.UNSAFE_LOCK_ENV, None)
ok, why = worker.lock_check()
assert ok is False, "a dedicated worker must refuse to start where pid_lock cannot span processes"
assert "second writer" in why and "Postgres" in why, why
assert jobs.WORKER_ENV in why, "the refusal must name the way out, not just the problem"

# ...and the operator can accept the risk explicitly, which must WARN rather than go quiet. An
# override that silences the message would leave no trace of a knowingly unsafe deployment.
os.environ[worker.UNSAFE_LOCK_ENV] = "1"
ok, why = worker.lock_check()
assert ok is True, "the explicit override must allow the worker to run"
assert why and "silently lost" in why, f"the override must still warn: {why!r}"
os.environ.pop(worker.UNSAFE_LOCK_ENV, None)

# --- C3. the API's boot guard counts WRITER PROCESSES, not uvicorn workers -------------------------
# `_production_guard` asked `_worker_count() > 1` — one route to two writers. AEC_JOB_WORKER=off is a
# second, independent one, so UVICORN_WORKERS=1 plus a dedicated worker container sailed straight
# through. The guard was correct when written and became wrong when the product grew a new way to do
# the thing it forbids.
from aec_api.main import _production_guard  # noqa: E402

_saved = {k: os.environ.get(k) for k in
          ("AEC_ENV", "UVICORN_WORKERS", "AEC_RBAC", "AEC_AUTH_SECRET", "AEC_ALLOW_OPEN",
           jobs.WORKER_ENV)}


def _guard_problem() -> str:
    try:
        _production_guard()
        return ""
    except RuntimeError as exc:
        return str(exc)


os.environ.update({"AEC_ENV": "production", "UVICORN_WORKERS": "1", "AEC_RBAC": "1",
                   "AEC_AUTH_SECRET": "x" * 32})
os.environ.pop("AEC_ALLOW_OPEN", None)
import aec_api.rbac  # noqa: E402

aec_api.rbac.RBAC_ON = True                      # the guard reads the module flag, set at import

os.environ.pop(jobs.WORKER_ENV, None)            # in-process worker ⇒ ONE writer ⇒ allowed
assert "writer processes" not in _guard_problem(), (
    "a single uvicorn worker with the in-process job worker is ONE writer and must boot — without "
    "this twin, a guard that refused everything would pass the assertion below")

os.environ[jobs.WORKER_ENV] = "off"              # dedicated worker ⇒ TWO writers on SQLite ⇒ refuse
problem = _guard_problem()
assert "writer processes" in problem, (
    f"UVICORN_WORKERS=1 + {jobs.WORKER_ENV}=off is two writer processes on SQLite and must be "
    f"refused at boot; guard said: {problem!r}")
assert "dedicated job-worker process" in problem, "the message must say WHICH second writer"

for _k, _v in _saved.items():
    if _v is None:
        os.environ.pop(_k, None)
    else:
        os.environ[_k] = _v

# --- D. no compose file may turn the API's worker off without replacing it -------------------------
# The production accident this exists to catch: `AEC_JOB_WORKER=off` lands on the api service, the
# worker container is forgotten or deleted, and the stack comes up perfectly healthy while doing no
# background work at all. Every healthcheck passes, because the API is genuinely fine.
COMPOSE = sorted(REPO.glob("docker-compose*.yml"))
assert len(COMPOSE) >= 2, f"expected the base + prod compose files, found {[p.name for p in COMPOSE]}"


def _default_of(raw) -> str:
    """Resolve `${VAR:-default}` to its default; anything else is returned as-is, lowercased."""
    s = str(raw).strip()
    if s.startswith("${") and s.endswith("}") and ":-" in s:
        s = s.split(":-", 1)[1][:-1]
    return s.strip().lower()


def _services(path: Path) -> dict:
    """Parse ONE compose file on its own — the isolation is load-bearing, not incidental.

    Both files use YAML anchors to stop the API's and the worker's environments drifting apart
    (`&api-env` in the base, `&prod-datastore` in the overlay). Anchors do **not** cross files in
    docker compose: an alias defined in the base file is simply undefined when the overlay is parsed.
    Loading each file standalone is what would catch that — an undefined alias raises here rather
    than at deploy time.

    What this does NOT check: docker's own merge semantics for layered files. Docker is not installed
    on the machine this was written on, so `docker compose config` was never run against it.
    """
    return (yaml.safe_load(path.read_text(encoding="utf-8")) or {}).get("services") or {}


def _runs_worker(svc: dict) -> bool:
    return "aec_api.worker" in " ".join(map(str, svc.get("command") or []))


turned_off, runs_worker_anywhere = [], []
for path in COMPOSE:
    svcs = _services(path)
    for name, svc in svcs.items():
        env = svc.get("environment") or {}
        if isinstance(env, dict) and _default_of(env.get(jobs.WORKER_ENV, "inline")) == "off":
            turned_off.append(f"{path.name}:{name}")
        if _runs_worker(svc):
            runs_worker_anywhere.append(f"{path.name}:{name}")

# Population floor: if nothing sets `off`, this whole section is vacuous and would pass on a compose
# file that had lost the split entirely.
assert turned_off, (
    "no compose service sets AEC_JOB_WORKER=off — either the split was reverted in the compose files "
    "(in which case the heavy parses are back inside the API container) or this check is now blind")
assert runs_worker_anywhere, (
    f"{turned_off} run the API without an in-process worker, and NO compose service runs "
    "`python -m aec_api.worker`. Jobs would queue forever and nothing would raise: the enqueue "
    "succeeds, the row is written, the caller is told the work is under way, and it never happens")

# ...and the worker must be built from the same image as the API, or it runs different code than the
# API that enqueued the job — a handler the API knows about would be an unknown kind in the worker.
base = _services(REPO / "docker-compose.yml")
assert "worker" in base, "the base compose must define the worker service the prod overlay refines"
api_df = ((base["api"].get("build") or {}) or {}).get("dockerfile")
wrk_df = ((base["worker"].get("build") or {}) or {}).get("dockerfile")
assert api_df and wrk_df and api_df == wrk_df, (
    f"worker builds from {wrk_df!r} but the API builds from {api_df!r} — they must be the same image "
    "or the worker can be running a different set of registered kinds than the API enqueueing them")

# --- E. the stale note that said none of this was possible is gone ---------------------------------
# It read: "the in-process claim is safe for the supported single-writer deployment; multi-worker
# deployments would add a DB row-lock claim (SELECT … FOR UPDATE SKIP LOCKED)". Both halves were
# false — the claim is already a cross-process CAS, and pid_lock became cross-process in
# R35-PIDLOCK-XPROC. A comment that talks the reader out of a capability the code has is worse than
# no comment, and this one would have blocked exactly this change.
#
# Note what this can and cannot check. A substring test cannot tell a *claim* from a *quotation*: the
# replacement docstring quotes the old sentence verbatim in order to explain why it was wrong, so
# "does the phrase appear?" answers the wrong question — the first version of this assertion failed
# on the very doc that corrects the error. What is checkable is that the doc documents the switch, so
# a revert to the stale text (which knows nothing about `AEC_JOB_WORKER`) fires.
doc = (jobs.__doc__ or "")
assert jobs.WORKER_ENV in doc, (
    f"jobs.py's docstring no longer documents {jobs.WORKER_ENV}. The note it replaced actively told "
    "the reader multi-worker deployments were unsupported and needed FOR UPDATE SKIP LOCKED — both "
    "false, and it would have blocked this change")
for mode in ("inline", "off"):
    assert f"`{mode}`" in doc, f"jobs.py's docstring must say what {mode!r} does — it is a deployment switch"

for f in ("./_worker_split_test.db",):
    if os.path.exists(f):
        try:
            os.remove(f)
        except OSError:
            pass

print("WORKER-SPLIT OK - AEC_JOB_WORKER defaults to inline (unset/typo → inline, only 'off' disables) "
      "and a STARTED app honours it in BOTH directions; `run_forever()` (what `python -m aec_api.worker` "
      "runs) drained a real queued job off the main thread and shut down on stop_worker(); the worker "
      "REFUSES to start where pid_lock cannot span processes (a dedicated worker is a second writer, "
      "and on anything but Postgres the sidecar lock is an in-process RLock two processes cannot "
      "share) while an explicit AEC_WORKER_ALLOW_UNSAFE_LOCK=1 still warns; the boot guard counts "
      "WRITER PROCESSES rather than uvicorn workers, so UVICORN_WORKERS=1 plus a dedicated worker is "
      "refused on SQLite and the single-writer twin still boots; every compose service that sets off "
      "is matched by a service running the worker, built from the same Dockerfile as the API; and the "
      "stale single-writer/FOR-UPDATE note is gone.")

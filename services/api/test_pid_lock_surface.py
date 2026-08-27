"""R37-TESTED-UNWIRED — `pid_lock.cross_process_status()` now has callers, and they are the right two.

## What was wrong

The function reports what serialisation is ACTUALLY in force for the sidecar write lock — a Postgres
session advisory lock, or nothing but a `threading.RLock` that a second worker cannot see. Its own
docstring said it was "callable from a health surface and from the production guard". It was called
from neither. R37-TESTED-UNWIRED measured which public functions nothing outside the test tree calls
and this one came back with no caller at all — only `test_pid_lock_xproc.py`.

Both named callers were fiction, in two different ways:

* **The "health surface" was never built.** `/health` returns `{"status": "ok"}` with no dependencies,
  deliberately, so it was never going to be the home — and "in-process only" is a supported deployment
  shape, not a failed probe. A comment can name a surface into existence for every future reader
  without anything ever being added.

* **The guard derived the dialect itself**, with `db_url.split("://", 1)[0].split("+", 1)[0]`, under a
  comment explaining that it must not call `cross_process_status()` because that "opens a live
  session, so a transient connection blip would return '' and refuse to boot a perfectly configured
  Postgres deployment". **It does not open a session.** `SessionLocal()` is lazy and `db.get_bind()`
  returns the engine, whose dialect is parsed from the URL string; it answers `postgresql` for a DSN
  pointing at an address nothing is listening on, which is what the first check below pins.

## The guard still reads the env var, and the attempt to change that is the lesson

The first version of this work made the guard call `cross_process_status()`, on the reasoning above:
the stated objection was false, so the duplicate derivation should go. **That broke
`test_perf_rate.py::test_a_correctly_configured_production_still_starts` on the next full run**, and
that test carried the real reason in a comment beside it — the engine is built once, at import, from
whatever `DATABASE_URL` said then, so under a test runner it is SQLite whatever a fixture's env
claims, and an earlier engine-probing version of that branch "shipped a guard no fixture could ever
satisfy".

So the guard reads the env var, the comment above it now says *why* instead of saying something false,
and the two are pinned here as answering **different questions**: the guard asks whether the database
this deployment is CONFIGURED for can serialise, and `cross_process_status()` asks whether the engine
this process is actually USING can. At boot they name the same database.

*A stated reason that is false is worse than no comment at all* — not because it misleads, but
because the true constraint stands behind it unrecorded, and the only thing that finds it is breaking
the thing it was protecting.

## Why `/metrics`, and why the writer count ships with it

The dangerous condition is a conjunction: no cross-process lock AND more than one writer process.
That is exactly what `_production_guard` refuses to boot on — so the deployments that need telling are
the ones the guard never sees. It runs only when the DB is non-SQLite or `AEC_ENV` says production,
and is skipped entirely under `AEC_ALLOW_OPEN=1`. A self-hosted SQLite deployment with two uvicorn
workers boots clean and is exposed. Hence both gauges, from one `_writer_processes()` so a refusal at
boot and a scrape at runtime cannot disagree about how many writers there are.

Run: cd services/api && PYTHONPATH=src:../data/src ./.venv/bin/python test_pid_lock_surface.py
"""
from __future__ import annotations

import os
import subprocess
import sys
import time

os.environ["DATABASE_URL"] = "sqlite:///./test_pid_lock_surface.db"
os.environ["STORAGE_DIR"] = "./test_storage_pid_lock_surface"
os.environ.pop("AEC_RBAC", None)
os.environ.pop("AEC_ENV", None)
os.environ.pop("AEC_ALLOW_OPEN", None)
for _v in ("UVICORN_WORKERS", "WEB_CONCURRENCY", "AEC_JOB_WORKER"):
    os.environ.pop(_v, None)
if os.path.exists("./test_pid_lock_surface.db"):
    os.remove("./test_pid_lock_surface.db")

_DATA_SRC = os.path.join(os.path.dirname(__file__), "..", "data", "src")
if _DATA_SRC not in sys.path:
    sys.path.insert(0, _DATA_SRC)

from fastapi.testclient import TestClient  # noqa: E402

from aec_api import main as main_mod  # noqa: E402
from aec_api import metrics, pid_lock  # noqa: E402
from aec_api.main import app  # noqa: E402

FAILED: list[str] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    print(("PASS  " if ok else "FAIL  ") + name + ("   " + detail if detail else ""))
    if not ok:
        FAILED.append(name)


# ---- 1. it does NOT connect, which is what makes it safe at boot and on a scrape -----------------
# In a SUBPROCESS, because `db.py` builds its engine at import from DATABASE_URL and this process is
# already committed to SQLite. 192.0.2.1 is TEST-NET-1 (RFC 5737): reserved for documentation and
# routed nowhere, so a real connection attempt cannot succeed. If the call connected, the failure
# would be caught inside `_dialect()` and come back as dialect "unknown" — so the VALUE alone settles
# it, and the elapsed time is only corroboration.
_probe = ("import json,sys; sys.path.insert(0,'src'); sys.path.insert(0,'../data/src');\n"
          "from aec_api import pid_lock; print(json.dumps(pid_lock.cross_process_status()))")
_env = {**os.environ, "DATABASE_URL": "postgresql+psycopg://u:p@192.0.2.1:5432/nope",
        "PYTHONPATH": "src:../data/src"}
_t0 = time.time()
_out = subprocess.run([sys.executable, "-c", _probe], capture_output=True, text=True, timeout=120,
                      env=_env, cwd=os.path.dirname(__file__) or ".")
_elapsed = time.time() - _t0
try:
    import json as _json
    remote = _json.loads(_out.stdout.strip().splitlines()[-1]) if _out.returncode == 0 else {}
except Exception:                                   # noqa: BLE001 — reported by the check below
    remote = {}
check("the status call answers for an UNREACHABLE Postgres DSN, so it never connected",
      remote.get("dialect") == "postgresql" and remote.get("cross_process") is True,
      f"rc={_out.returncode} out={_out.stdout.strip()[:120]!r} err={_out.stderr.strip()[-160:]!r}")
check("...promptly, rather than after a TCP timeout", _elapsed < 30, f"{_elapsed:.1f}s")

# ---- 2. and it tells the truth about THIS process, which is SQLite -------------------------------
st = pid_lock.cross_process_status()
check("on SQLite it reports in-process only", st["cross_process"] is False
      and st["backend"] == pid_lock.BACKEND_IN_PROCESS, str(st["backend"]))
check("...and says in words what that costs, not just which backend",
      "silently lose" in st["meaning"], st["meaning"][:70])

# ---- 3. the gauges say different things for the two backends ------------------------------------
# Anti-vacuity first: a renderer that emitted the same lines regardless would pass every check below
# about "the gauge is present" while reporting nothing.
pg = {"cross_process": True, "backend": pid_lock.BACKEND_ADVISORY, "dialect": "postgresql",
      "meaning": "x"}
lines_pg = metrics.render_pid_lock(pg, 4)
lines_sq = metrics.render_pid_lock(st, 1)
check("the two backends render DIFFERENT gauge values", lines_pg != lines_sq)
check("cross-process renders 1", "aec_pid_lock_cross_process 1" in lines_pg)
check("...and in-process-only renders 0", "aec_pid_lock_cross_process 0" in lines_sq)
check("the backend rides as a label, so the number stays a number",
      any('aec_pid_lock_backend_info{backend="postgres_advisory",dialect="postgresql"} 1' == ln
          for ln in lines_pg), str(lines_pg[-4:]))
check("the writer count is exported beside it — neither is the alarm alone",
      "aec_pid_lock_writers 4" in lines_pg and "aec_pid_lock_writers 1" in lines_sq)

# Every declared series must actually be emitted. A `# TYPE` for a gauge that is never rendered is
# the same class of defect as the docstring that named a /health surface nobody built.
declared = {ln.split()[2] for ln in lines_pg if ln.startswith("# TYPE ")}
emitted = {ln.split("{")[0].split()[0] for ln in lines_pg if not ln.startswith("#")}
check("every declared series is emitted, and every emitted one declared", declared == emitted,
      f"declared-only={sorted(declared - emitted)} emitted-only={sorted(emitted - declared)}")

# ---- 4. THE WIRING: the gauges reach a live scrape ------------------------------------------------
# The point of the whole item. A render function nobody calls is exactly where this started.
with TestClient(app) as c:
    body = c.get("/metrics").text
check("/metrics carries the lock gauge", "aec_pid_lock_cross_process " in body)
check("...and the writer count", "aec_pid_lock_writers " in body)
check("...and the backend label", "aec_pid_lock_backend_info{" in body)
check("...reporting THIS process's real backend, not a constant",
      f"aec_pid_lock_cross_process {1 if st['cross_process'] else 0}" in body)

# ---- 5. writers are counted the same way for the refusal and for the gauge ------------------------
# Two independent routes to more than one writer. The guard asked only about the first for a release
# and a half after JOB-WORKER-SPLIT invented the second.
def writers(**env) -> tuple[int, str]:
    old = {k: os.environ.get(k) for k in ("UVICORN_WORKERS", "AEC_JOB_WORKER")}
    try:
        for k, v in env.items():
            os.environ[k] = v
        return main_mod._writer_processes()
    finally:
        for k, v in old.items():
            os.environ.pop(k, None) if v is None else os.environ.__setitem__(k, v)


check("one uvicorn worker with the inline job worker is one writer", writers()[0] == 1)
check("three uvicorn workers are three writers", writers(UVICORN_WORKERS="3")[0] == 3)
check("a dedicated job-worker process is a writer TOO — the route added after the guard was written",
      writers(AEC_JOB_WORKER="off")[0] == 2, str(writers(AEC_JOB_WORKER="off")))
check("...and it says so in words, so the refusal explains itself",
      "dedicated job-worker" in writers(AEC_JOB_WORKER="off")[1])

# ---- 6. the guard refuses on the conjunction, and agrees with the gauge about it ------------------
def guard(**env) -> str:
    """Run `_production_guard` under `env` and return the refusal text, or "" if it started."""
    keys = ("UVICORN_WORKERS", "AEC_JOB_WORKER", "AEC_ENV", "AEC_RBAC", "AEC_AUTH_SECRET",
            "AEC_ALLOW_OPEN", "DATABASE_URL")
    old = {k: os.environ.get(k) for k in keys}
    try:
        for k in keys:
            os.environ.pop(k, None)
        for k, v in env.items():
            os.environ[k] = v
        try:
            main_mod._production_guard()
            return ""
        except RuntimeError as e:
            return str(e)
    finally:
        for k, v in old.items():
            os.environ.pop(k, None) if v is None else os.environ.__setitem__(k, v)


#: RBAC and the auth secret are unrelated problems this guard also refuses on; they would be in the
#: message whatever the lock said, so every assertion below is about the SIDECAR sentence specifically.
SIDECAR = "sidecar write lock cannot serialise"
PROD = {"AEC_ENV": "production", "DATABASE_URL": "sqlite:///./test_pid_lock_surface.db"}

check("a single writer is not refused for the lock, whatever else is wrong",
      SIDECAR not in guard(**PROD), guard(**PROD)[:90])
msg = guard(**PROD, UVICORN_WORKERS="2")
check("two writers on SQLite ARE refused", SIDECAR in msg, msg[-140:])
check("...naming the dialect, so the message says which database it means", "'sqlite'" in msg,
      msg[-140:])
check("...and the job-worker route reaches the same refusal with ONE uvicorn worker",
      SIDECAR in guard(**PROD, AEC_JOB_WORKER="off"))
check("AEC_ALLOW_OPEN skips the guard entirely — the case only the gauge can report",
      guard(**PROD, UVICORN_WORKERS="2", AEC_ALLOW_OPEN="1") == "")

# ---- 7. the guard reads the ENV, the gauge reads the ENGINE, and that is deliberate ---------------
# The first version of this work made the guard call `cross_process_status()` — the objection its
# comment gave was false, so the duplicate derivation looked like dead weight. It broke
# `test_perf_rate.py::test_a_correctly_configured_production_still_starts` on the next full run: the
# engine is fixed at import, so under any test runner it is SQLite whatever a fixture's env says, and
# that file records an earlier engine-probing version as "a guard no fixture could ever satisfy".
#
# Both directions are pinned, because a later reader will have the same idea. A Postgres URL exported
# now cannot reach the already-built engine — so the guard follows it and the gauge does not, and the
# assertions below FAIL if either is quietly switched to the other source.
check("the guard follows DATABASE_URL exported after import — the property the fixtures need",
      SIDECAR not in guard(AEC_ENV="production", UVICORN_WORKERS="2",
                           DATABASE_URL="postgresql://u@h/db", AEC_RBAC="1",
                           AEC_AUTH_SECRET="x" * 40),
      guard(AEC_ENV="production", UVICORN_WORKERS="2", DATABASE_URL="postgresql://u@h/db",
            AEC_RBAC="1", AEC_AUTH_SECRET="x" * 40)[:120])
_was = os.environ.get("DATABASE_URL")
os.environ["DATABASE_URL"] = "postgresql://u@h/db"
try:
    check("...while the gauge does NOT — it reports the engine this process actually uses",
          pid_lock.cross_process_status()["dialect"] == "sqlite",
          str(pid_lock.cross_process_status()))
finally:
    os.environ.pop("DATABASE_URL", None) if _was is None else os.environ.__setitem__("DATABASE_URL", _was)

# And they answer the same at boot, which is the whole reason two sources are tolerable. This process
# IS a boot: the engine was built from this file's own DATABASE_URL and never diverged.
check("at boot the two agree — the condition under which the duplication is safe",
      (pid_lock.cross_process_status()["dialect"] == "sqlite")
      and (SIDECAR in guard(**PROD, UVICORN_WORKERS="2")))

for _f in ("./test_pid_lock_surface.db",):
    if os.path.exists(_f):
        os.remove(_f)

if FAILED:
    print("FAILED:", ", ".join(FAILED))
    sys.exit(1)
print("PID LOCK SURFACE OK - cross_process_status() has a caller: /metrics exports it as "
      "aec_pid_lock_cross_process beside aec_pid_lock_writers, for the deployments the boot guard "
      "never sees. Both callers its docstring claimed were fiction - the /health surface was never "
      "built, and the guard hand-parsed DATABASE_URL under a comment giving a reason that is false "
      "(it never connects; pinned above against an unroutable DSN). The guard still reads the env "
      "var, for the reason `test_perf_rate.py` recorded and this file now pins: the engine is fixed "
      "at import, so it answers about the process, and only the env var answers about the "
      "configuration a fixture - or a deploy - just set.")

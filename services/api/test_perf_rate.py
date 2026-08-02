"""PERF-RATE — a rate limit that is silently N x its configured value refuses to start.

Verified at `main.py` before changing anything: with `AEC_RATE_LIMIT_RPM` set, several workers and no
`AEC_REDIS_URL`, each worker kept its own counter, so the effective limit was N x the configured one.
The code logged `CRITICAL` — the loudest message available — and then started anyway.

That is worse than having no limit at all. An absent control is a known gap; a control that announces
it is broken and then runs leaves the operator believing they are protected. The remedy needed no new
machinery: `_production_guard` already collects `problems`, raises once naming all of them, and
offers `AEC_ALLOW_OPEN=1` for deliberately-open deployments. This joins that list, so it inherits the
escape hatch and the production-only scope — a dev box on SQLite is untouched.

Run: PYTHONPATH="src;../data/src" ./.venv/Scripts/python.exe test_perf_rate.py
"""
from __future__ import annotations

import os
import sys

_DATA_SRC = os.path.join(os.path.dirname(__file__), "..", "data", "src")
if _DATA_SRC not in sys.path:
    sys.path.insert(0, _DATA_SRC)

from aec_api import auth, main, rbac  # noqa: E402

# `rbac.RBAC_ON` and the auth secret are read at IMPORT time, so setting the env afterwards does not
# change them — the seam has to be patched. Pinned to "correctly configured" for the whole file so
# each case isolates the RATE LIMIT rather than re-testing the RBAC guard, which has its own tests.
rbac.RBAC_ON = True
rbac.TRUST_XUSER = False
auth.secret_is_default = lambda: False

_KEYS = ("AEC_RATE_LIMIT_RPM", "AEC_REDIS_URL", "UVICORN_WORKERS", "WEB_CONCURRENCY",
         "DATABASE_URL", "AEC_ENV", "AEC_ALLOW_OPEN", "AEC_RBAC", "AEC_AUTH_SECRET")


class env:
    """Set exactly these vars, clear the rest of `_KEYS`, restore on exit."""

    def __init__(self, **kw):
        self.kw = kw

    def __enter__(self):
        self.old = {k: os.environ.get(k) for k in _KEYS}
        for k in _KEYS:
            os.environ.pop(k, None)
        os.environ.update({k: str(v) for k, v in self.kw.items()})

    def __exit__(self, *a):
        for k in _KEYS:
            os.environ.pop(k, None)
            if self.old.get(k) is not None:
                os.environ[k] = self.old[k]


# --- the detector -----------------------------------------------------------------------------------
def test_several_workers_with_no_shared_store_is_per_worker():
    with env(AEC_RATE_LIMIT_RPM=60, UVICORN_WORKERS=4):
        assert main._rate_limit_is_per_worker() is True
        assert main._worker_count() == 4


def test_a_shared_store_makes_it_global():
    with env(AEC_RATE_LIMIT_RPM=60, UVICORN_WORKERS=4, AEC_REDIS_URL="redis://x:6379/0"):
        assert main._rate_limit_is_per_worker() is False


def test_one_worker_is_fine_without_redis():
    with env(AEC_RATE_LIMIT_RPM=60, UVICORN_WORKERS=1):
        assert main._rate_limit_is_per_worker() is False


def test_no_rate_limit_configured_is_not_a_problem():
    with env(UVICORN_WORKERS=8):
        assert main._rate_limit_is_per_worker() is False


def test_WEB_CONCURRENCY_counts_too():
    with env(AEC_RATE_LIMIT_RPM=60, WEB_CONCURRENCY=3):
        assert main._worker_count() == 3 and main._rate_limit_is_per_worker() is True


def test_an_unreadable_worker_count_reads_as_one_not_as_a_crash():
    # The safe direction: we must never CLAIM a limit is per-worker when we cannot tell, and we must
    # never fail to boot over a malformed variable that is not itself a security problem.
    with env(AEC_RATE_LIMIT_RPM=60, UVICORN_WORKERS="four"):
        assert main._worker_count() == 1
        assert main._rate_limit_is_per_worker() is False


def test_an_unreadable_rate_limit_is_not_a_rate_limit():
    with env(AEC_RATE_LIMIT_RPM="lots", UVICORN_WORKERS=4):
        assert main._rate_limit_is_per_worker() is False


# --- what it now DOES about it ------------------------------------------------------------------------
def test_a_PRODUCTION_deployment_REFUSES_TO_START():
    # THE FIX. Previously: log.critical(...) and carry on.
    with env(AEC_RATE_LIMIT_RPM=60, UVICORN_WORKERS=4, DATABASE_URL="postgresql://u@h/db",
             AEC_RBAC="1", AEC_AUTH_SECRET="x" * 40):
        try:
            main._production_guard()
        except RuntimeError as e:
            assert "AEC_RATE_LIMIT_RPM" in str(e) and "4x" in str(e), str(e)
            assert "AEC_REDIS_URL" in str(e), "the message must say how to fix it"
        else:
            raise AssertionError("production started with a per-worker rate limit")


def test_the_escape_hatch_still_works():
    # A deliberately-open internal deployment must still be able to boot; refusing something the
    # operator has explicitly accepted would just teach them to stop setting the flag.
    with env(AEC_RATE_LIMIT_RPM=60, UVICORN_WORKERS=4, DATABASE_URL="postgresql://u@h/db",
             AEC_ALLOW_OPEN="1"):
        main._production_guard()          # must not raise


def test_a_DEV_box_is_untouched():
    # SQLite and no AEC_ENV: not a production deployment, so this warns rather than refusing. Making
    # every developer set AEC_REDIS_URL to run two workers locally would be a gate people route
    # around, and a gate people route around protects nothing.
    with env(AEC_RATE_LIMIT_RPM=60, UVICORN_WORKERS=4, DATABASE_URL="sqlite:///./dev.db"):
        main._production_guard()          # must not raise


def test_a_correctly_configured_production_still_starts():
    with env(AEC_RATE_LIMIT_RPM=60, UVICORN_WORKERS=4, AEC_REDIS_URL="redis://x:6379/0",
             DATABASE_URL="postgresql://u@h/db", AEC_RBAC="1", AEC_AUTH_SECRET="x" * 40):
        main._production_guard()          # must not raise


# --- R35-PIDLOCK-XPROC: multi-worker needs a cross-process sidecar lock ------------------------------
# The guard derives the dialect from DATABASE_URL, not from a live engine probe: at boot they name
# the same database, but the env var cannot blip the way a connection can — and it makes this branch
# checkable here without rebuilding the process-wide engine (which is SQLite under the test runner,
# whatever the fixture's env claims; that mismatch shipped a guard no fixture could ever satisfy).

def test_multiworker_on_a_DECLARED_sqlite_production_refuses_over_the_sidecar_lock():
    with env(UVICORN_WORKERS=4, AEC_ENV="production", DATABASE_URL="sqlite:///./prod.db",
             AEC_RBAC="1", AEC_AUTH_SECRET="x" * 40):
        try:
            main._production_guard()
        except RuntimeError as e:
            assert "sidecar write lock" in str(e) and "'sqlite'" in str(e), str(e)
        else:
            raise AssertionError("4 workers on sqlite started without a cross-process lock")


def test_a_driver_qualified_postgres_url_counts_as_postgres():
    # postgresql+psycopg:// is the same server capability as postgresql:// — the advisory lock works.
    with env(UVICORN_WORKERS=4, DATABASE_URL="postgresql+psycopg://u@h/db",
             AEC_RBAC="1", AEC_AUTH_SECRET="x" * 40):
        main._production_guard()          # must not raise


def test_a_single_worker_on_declared_sqlite_production_is_fine():
    # One worker: in-process serialisation IS cross-request serialisation. Nothing to refuse.
    with env(UVICORN_WORKERS=1, AEC_ENV="production", DATABASE_URL="sqlite:///./prod.db",
             AEC_RBAC="1", AEC_AUTH_SECRET="x" * 40):
        main._production_guard()          # must not raise


for _n, _f in sorted(globals().items()):
    if _n.startswith("test_") and callable(_f):
        _f()

print("PERF-RATE OK - a rate limit that is silently N x its configured value now REFUSES to start a "
      "production deployment. It previously logged CRITICAL - the loudest message available - and "
      "then started anyway, which is worse than having no limit: an absent control is a known gap, "
      "while one that announces it is broken and runs leaves the operator believing they are "
      "protected. The fix needed no new machinery; `_production_guard` already collected `problems`, "
      "raised once naming all of them, and offered AEC_ALLOW_OPEN=1 for deliberately-open "
      "deployments, so this joins that list and inherits the escape hatch and the production-only "
      "scope. A dev box on SQLite still just warns - making every developer run Redis to use two "
      "workers locally would be a gate people route around, and a gate people route around protects "
      "nothing. An unreadable worker count reads as ONE, the safe direction: we never claim a limit "
      "is per-worker when we cannot actually tell.")

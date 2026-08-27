"""Per-project mutation locks for sidecar JSON indexes (docmanager, edit_history).

The sidecar pattern is read-modify-write on a single JSON blob in object storage; FastAPI runs sync
endpoints in a threadpool, so two concurrent mutations could interleave load→save and silently lose
the first writer's entry (or double-allocate `seq` ids). `mutating(pid)` serialises mutations per
project.

**R35-PIDLOCK-XPROC.** Until now that serialisation was *in-process only*: a `threading.RLock` keyed
by project. Under `uvicorn --workers > 1` two workers could interleave load→save on the same project
and the first writer's entry was silently lost — no error, no duplicate, just an index that forgot
something. The sidecars write to object storage, so there is no row to arbitrate them; the lock now
takes a **Postgres session advisory lock** in addition to the in-process one.

The interface is unchanged — `with mutating(pid):` — because ten call sites depend on it.

## Four things that would each have made this lock silently useless

1. **`hash(pid)` is not a stable key.** PEP 456 randomises string hashing per process, so
   `hash("project-abc")` returns a different value in every worker: each would take a *different*
   advisory lock and none would ever collide. The lock would appear to work, cost a round trip, and
   serialise nothing — the exact bug this item exists to fix, reintroduced by its fix, and invisible
   to any single-process test. Keys come from `blake2b`, which is stable across processes.

2. **The lock nests.** `jobs.py` holds `mutating(project_id)` for the whole handler, and handlers
   call `docmanager` / `edit_history`, which take it again — which is why the in-process lock is an
   `RLock`. A cross-process lock that opened a fresh session per acquisition would have the nested
   call wait on a lock its own caller holds, in a different session: a **permanent deadlock** on the
   ordinary path. Depth is tracked per thread and the advisory lock is taken only at depth 0.

3. **A `yield` inside a `try` whose `except` also yields.** The first version did exactly that, so an
   exception thrown in at the first yield landed in the handler and yielded again — contextlib then
   raised `"generator didn't stop after throw()"`, **replacing whatever the caller's body actually
   raised**. Every real error inside `with mutating(pid):` was masked on the SQLite path, which is
   the default for dev and for the test suite. Acquisition now completes before any yield.

4. **On SQLite there is no advisory lock at all.** Rather than pretend, two separate mechanisms say
   so, and they read two different sources on purpose: `main._production_guard` refuses to boot a
   multi-worker deployment that cannot serialise, reading `DATABASE_URL`; `cross_process_status()`
   reports what is in force at runtime, reading the engine, and `/metrics` exports it. A constraint
   the product genuinely has should fail at boot, not be a sentence in a docstring nobody reads.

   *This sentence used to coordinate the two into one clause — "`cross_process_status()` reports …
   and `main._production_guard` refuses …" — which reads as the guard calling the function.* It does
   not, for the reason four paragraphs down. Each half was true alone and the pair implied something
   false, which is the same defect as the two below it and the hardest of the three to see.

   **And for a release and a half, that is what it was.** R37-TESTED-UNWIRED measured which public
   functions nothing outside the test tree calls, and `cross_process_status()` came back with no
   caller at all: the guard derived the dialect itself with `db_url.split("://")`, and the "health
   surface" its own docstring pointed at had never been built. `/metrics` now exports it as
   `aec_pid_lock_cross_process` beside `aec_pid_lock_writers` — because the guard runs only on a
   production deployment and is skipped under `AEC_ALLOW_OPEN=1`, so the deployments actually exposed
   to this are the ones it never sees. Not `/health`: that is dependency-free on purpose, and
   "in-process only" is a supported shape, not a failed probe.

   **The guard is still not a caller, and that is now a decision rather than an accident.** Making it
   one broke `test_perf_rate.py` immediately: this function reports on the ENGINE, which is built once
   at import, while the guard must answer about the DATABASE_URL a deployment (or a fixture) just set.
   At boot they name the same database. `services/api/test_pid_lock_surface.py` pins both directions
   so the next reader who spots the duplication finds the reason instead of the false one.
"""
from __future__ import annotations

import hashlib
import logging
import threading
from contextlib import contextmanager
from typing import Any

_log = logging.getLogger("aec.pid_lock")

_LOCKS: dict[str, threading.RLock] = {}
_REGISTRY = threading.Lock()

#: Per-thread reentrancy depth, keyed by pid. The advisory lock is acquired at depth 0 and released
#: when it returns to 0 — see note 2 above.
_local = threading.local()

#: Namespace mixed into every key so a project id cannot collide with an unrelated advisory lock in
#: the same database (`main._AUTOSYNC_LOCK_KEY` shares the space).
_NAMESPACE = b"aec.pid_lock:"

BACKEND_ADVISORY = "postgres_advisory"
BACKEND_IN_PROCESS = "in_process_only"

_STATUS_MEANING = {
    BACKEND_ADVISORY: "a Postgres session advisory lock serialises this project's sidecar writes "
                      "across every worker and process sharing the database",
    BACKEND_IN_PROCESS: "serialisation is WITHIN ONE PROCESS ONLY — this backend has no advisory "
                        "lock, so two workers can still interleave a sidecar read-modify-write and "
                        "silently lose the first writer's entry. Single-writer-per-project is the "
                        "supported deployment shape here, and it is a real product constraint.",
}


def advisory_key(pid: str) -> int:
    """A stable signed 64-bit advisory-lock id for `pid`.

    **Never `hash()`** — see note 1 in the module docstring. `blake2b` gives the same key in every
    process, which is the entire point of a cross-process lock."""
    digest = hashlib.blake2b(_NAMESPACE + str(pid).encode("utf-8"), digest_size=8).digest()
    return int.from_bytes(digest, "big", signed=True)


def _lock_for(pid: str) -> threading.RLock:
    with _REGISTRY:
        lk = _LOCKS.get(pid)
        if lk is None:
            lk = _LOCKS[pid] = threading.RLock()
        return lk


def _dialect() -> str:
    """The database dialect, or "" when it cannot be determined. Never raises: a lock that refused to
    be taken because the DB was briefly unreachable would take the API down with it."""
    try:
        from .db import SessionLocal
        with SessionLocal() as db:
            return db.get_bind().dialect.name
    except Exception:                                  # noqa: BLE001 — reported, never fatal
        return ""


def cross_process_status() -> dict[str, Any]:
    """What serialisation is ACTUALLY in force, as opposed to what the docstring hopes.

    Read by `/metrics`, which exports it as `aec_pid_lock_cross_process` beside
    `aec_pid_lock_writers`, so "this deployment cannot serialise sidecar writes across workers" is a
    fact somebody can read rather than infer.

    **This docstring used to say "callable from a health surface and from the production guard", and
    neither was true** — that fiction is what R37-TESTED-UNWIRED found, and note 4 in the module
    docstring records it. The health surface was never built; the guard reads DATABASE_URL, for the
    reason stated at its call site and pinned in `services/api/test_pid_lock_surface.py`. Naming a
    caller here that does not exist is precisely the defect, so this line names the one that does.

    Note it reports on the ENGINE, which is built once at import. That is the right answer for a
    scrape and the wrong one for a boot check, which must see the DATABASE_URL just set."""
    dialect = _dialect()
    ok = dialect == "postgresql"
    backend = BACKEND_ADVISORY if ok else BACKEND_IN_PROCESS
    return {"cross_process": ok, "backend": backend, "dialect": dialect or "unknown",
            "meaning": _STATUS_MEANING[backend]}


@contextmanager
def _advisory(pid: str):
    """Hold a Postgres session advisory lock for `pid`, or yield having taken nothing.

    Blocking rather than `try_`: these are short read-modify-write cycles and the caller's contract is
    "the sidecar is mine for this block". A `try_` variant would have to spin or fail the request, and
    failing a document upload because another upload was in flight is worse than waiting for it."""
    depth: dict[str, int] = getattr(_local, "depth", None) or {}
    _local.depth = depth
    if depth.get(pid, 0) > 0:                          # already held by THIS thread — see note 2
        depth[pid] += 1
        try:
            yield False
        finally:
            depth[pid] -= 1
        return

    try:
        from sqlalchemy import text

        from .db import SessionLocal
    except Exception:                                  # noqa: BLE001
        yield False
        return

    key = advisory_key(pid)
    db = None
    acquired = False
    # ACQUISITION FIRST, and no `yield` anywhere inside this try — see note 3. A yield inside a try
    # whose `except` also yields is a generator that can yield TWICE when an exception is thrown in at
    # the first one, and contextlib then replaces the caller's real exception with a generator error.
    try:
        db = SessionLocal()
        if db.get_bind().dialect.name == "postgresql":
            db.execute(text("SELECT pg_advisory_lock(:k)"), {"k": key})
            acquired = True
    except Exception as e:                             # noqa: BLE001 — degrade to in-process, loudly
        _log.warning("pid_lock: cross-process lock unavailable for %s (%s); this write is serialised "
                     "within this process only", pid, e)
        acquired = False
    if not acquired:
        if db is not None:
            try:
                db.close()
            except Exception:                          # noqa: BLE001,S110
                pass
        yield False
        return

    depth[pid] = 1
    try:
        yield True
    finally:
        depth[pid] -= 1
        try:
            db.execute(text("SELECT pg_advisory_unlock(:k)"), {"k": key})
            db.commit()
        except Exception as e:                         # noqa: BLE001
            # Postgres releases session-level advisory locks when the connection drops, so a failed
            # unlock cannot strand the lock forever — the close below is the backstop.
            _log.warning("pid_lock: advisory unlock failed for %s (%s); the lock releases when this "
                         "connection closes", pid, e)
        finally:
            try:
                db.close()
            except Exception:                          # noqa: BLE001,S110
                pass


@contextmanager
def mutating(pid: str):
    """Hold the per-project sidecar write lock for a load→mutate→save cycle.

    In-process first, then cross-process. That order matters: the threading lock is uncontended in the
    common case and cheap, and holding it while waiting on the database means the threads of one
    process queue locally rather than each opening a connection to wait on the same advisory lock."""
    with _lock_for(pid), _advisory(pid):
        yield

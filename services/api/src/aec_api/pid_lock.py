"""Per-project mutation locks for sidecar JSON indexes (docmanager, edit_history).

The sidecar pattern is read-modify-write on a single JSON blob in object storage; FastAPI runs sync
endpoints in a threadpool, so two concurrent mutations could interleave load→save and silently lose the
first writer's entry (or double-allocate `seq` ids). `mutating(pid)` serializes mutations per project
within this process. NOTE: cross-worker serialization (`uvicorn --workers >1`) additionally needs a
shared lock (storage CAS / DB advisory lock) — until then, single-writer-per-project deployments are the
supported shape for these sidecars and the lock closes the in-process race entirely."""
from __future__ import annotations

import threading
from contextlib import contextmanager

_LOCKS: dict[str, threading.RLock] = {}
_REGISTRY = threading.Lock()


def _lock_for(pid: str) -> threading.RLock:
    with _REGISTRY:
        lk = _LOCKS.get(pid)
        if lk is None:
            lk = _LOCKS[pid] = threading.RLock()
        return lk


@contextmanager
def mutating(pid: str):
    """Hold the per-project sidecar write lock for the duration of a load→mutate→save cycle."""
    with _lock_for(pid):
        yield

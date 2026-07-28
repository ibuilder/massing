"""Geometry tessellation config — the ifcopenshell iterator worker count, env-overridable.

Every geometry pass (bake / clash / export / edit republish) runs ifcopenshell's iterator across
`cpu_count()-1` worker processes by default. That's right for a single interactive request, but it
*oversubscribes* the CPU when many passes run at once — e.g. the test gate runs ~180 tests concurrently,
each doing geometry, so cpu-1 workers × cpu-1 tests thrashes. Set `AEC_GEOM_WORKERS=1` in that outer-
parallel context so each pass is single-threaded and the outer parallelism owns the cores.
"""
from __future__ import annotations

import multiprocessing
import os


def geom_workers() -> int:
    """Worker-process count for an ifcopenshell geometry iterator. `AEC_GEOM_WORKERS` overrides it
    (e.g. `1` under a parallel test/CI runner); the default is `cpu_count() - 1`, floored at 1."""
    override = os.environ.get("AEC_GEOM_WORKERS")
    if override:
        try:
            return max(1, int(override))
        except ValueError:
            pass
    return max(1, multiprocessing.cpu_count() - 1)


# --- PERF-THREADS: bound how many geometry passes run at once -----------------------------------
#
# `geom_workers()` above answers "how many processes should ONE pass use". It cannot answer "how many
# passes should run at once", and that is the number that actually thrashes a server: eight concurrent
# requests each starting a cpu-1 iterator asks for 8x(cpu-1) processes on a machine that has cpu.
#
# The existing mitigation is `AEC_GEOM_WORKERS=1`, which fixes it by turning per-pass parallelism OFF
# — right for the test gate, where the runner owns the cores, and wrong for a server, where a single
# interactive render should still use the machine. A semaphore separates the two questions: each pass
# keeps its workers, and the number of simultaneous passes is what gets bounded.
#
# Deliberately NOT a global lock around all model work. Reading properties, walking the spatial tree
# and serialising records are not CPU-bound and have no business queueing behind a tessellation.
import contextlib
import logging
import threading

_log = logging.getLogger("aec.geom")

#: Concurrent geometry passes allowed in this process. Derived so that slots x per-pass workers stays
#: near the core count, floored at 1 — one pass must always be able to run or nothing renders at all.
def geom_slots() -> int:
    override = os.environ.get("AEC_GEOM_SLOTS")
    if override:
        try:
            return max(1, int(override))
        except ValueError:
            pass
    return max(1, multiprocessing.cpu_count() // max(1, geom_workers()))


_SLOTS = threading.BoundedSemaphore(geom_slots())
_depth = threading.local()

#: How long a pass waits for a slot before going ahead anyway. This is a fairness guard, not a
#: correctness gate — see `geometry_slot`.
_WAIT_S = float(os.environ.get("AEC_GEOM_WAIT_S", "30"))


@contextlib.contextmanager
def geometry_slot():
    """Hold one of the geometry slots for the duration of a tessellation pass.

    **Re-entrant per thread.** A nested pass on a thread that already holds a slot does not try to
    take a second one. Without this, any future call chain where one geometry pass invokes another
    deadlocks the moment slots are scarce — and a deadlock inside a render is about the least
    diagnosable failure this codebase could ship. Nothing nests today; this makes it safe when
    something does.

    **A timeout proceeds rather than fails.** If no slot frees within the wait, the pass runs anyway
    and says so. The semaphore exists to stop a thundering herd of iterators, not to decide whether a
    user gets their drawing — briefly oversubscribing the CPU is a worse outcome than a request that
    hangs forever, and much better than one that errors because the machine was busy.
    """
    if getattr(_depth, "n", 0):
        _depth.n += 1
        try:
            yield
        finally:
            _depth.n -= 1
        return

    got = _SLOTS.acquire(timeout=_WAIT_S)
    if not got:
        _log.warning("geometry slot wait exceeded %.0fs — proceeding unbounded", _WAIT_S)
    _depth.n = 1
    try:
        yield
    finally:
        _depth.n = 0
        if got:
            _SLOTS.release()

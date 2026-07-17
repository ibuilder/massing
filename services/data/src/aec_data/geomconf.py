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

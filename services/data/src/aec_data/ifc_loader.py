"""Shared IFC open/iteration helpers. All extraction is keyed by IFC GlobalId (GUID)
so results reconcile against model updates (CLAUDE.md non-negotiable)."""
from __future__ import annotations

import os
from collections.abc import Iterable
from functools import lru_cache

import ifcopenshell
import ifcopenshell.util.element as ue


def open_model(path: str) -> ifcopenshell.file:
    """Open an IFC file, cached by (path, mtime, size). Keying on the file's stat — not the path alone —
    means a **re-written** file (a re-upload or republish to the *same* `source.ifc` path) is reloaded
    fresh instead of served stale from the cache. (The /edit path already writes a new timestamped file,
    so it was never affected; whole-model replacement to a fixed path was.)"""
    try:
        st = os.stat(path)
        key = (st.st_mtime_ns, st.st_size)
    except OSError:
        key = None
    return _open_cached(path, key)


@lru_cache(maxsize=8)
def _open_cached(path: str, _key) -> ifcopenshell.file:
    return ifcopenshell.open(path)


def physical_elements(model: ifcopenshell.file) -> Iterable:
    """All physical building elements (walls, slabs, members, doors, equipment...).

    IfcBuildingElement covers IFC4; IfcElement is the broader supertype used as a
    fallback for distribution/MEP elements not under IfcBuildingElement.
    """
    seen = set()
    for cls in ("IfcBuildingElement", "IfcElement"):
        try:
            for el in model.by_type(cls):
                if el.id() not in seen:
                    seen.add(el.id())
                    yield el
        except RuntimeError:
            # class not in this schema
            continue


def storey_name(element) -> str | None:
    """Name of the IfcBuildingStorey for this element — via spatial containment (most
    elements) or aggregation (IfcSpace decomposes from its storey)."""
    # containment chain
    container = ue.get_container(element)
    while container is not None:
        if container.is_a("IfcBuildingStorey"):
            return container.Name
        container = ue.get_aggregate(container) if hasattr(ue, "get_aggregate") else None
    # aggregation parent (spaces, etc.)
    if hasattr(ue, "get_aggregate"):
        agg = ue.get_aggregate(element)
        while agg is not None:
            if agg.is_a("IfcBuildingStorey"):
                return agg.Name
            agg = ue.get_aggregate(agg)
    return None

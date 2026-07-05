"""Shared IFC open/iteration helpers. All extraction is keyed by IFC GlobalId (GUID)
so results reconcile against model updates (CLAUDE.md non-negotiable)."""
from __future__ import annotations

from collections.abc import Iterable
from functools import lru_cache

import ifcopenshell
import ifcopenshell.util.element as ue


@lru_cache(maxsize=8)
def open_model(path: str) -> ifcopenshell.file:
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

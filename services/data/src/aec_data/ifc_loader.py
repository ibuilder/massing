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
    model = _open_cached(path, key)
    # CACHE-KEY (v0.3.722) — stamp the CONTENT identity onto the model so derived caches can key on
    # *which file this is* rather than on `id(model)`, which is process-local and reused after a GC.
    # `(path, mtime, size)` is already the identity this cache uses, so nothing new is being decided
    # here; it is being made available to the layers above. Prerequisite for sharing baked geometry
    # across workers — a shared cache cannot be keyed on an address in one process's heap.
    try:
        model.__aec_content_key__ = content_key(path, key)
    except AttributeError:                      # a future ifcopenshell may forbid it; not fatal
        pass
    return model


def content_key(path: str, stat_key: tuple[int, int] | None) -> str:
    """Stable identity for the FILE behind a model: absolute path + mtime + size.

    Not a hash of the bytes — deliberately. Hashing a 2 GB IFC on every open would cost more than the
    work being cached, and stat already distinguishes a re-written file, which is the case that
    matters (a republish to the same `source.ifc`). `unknown:` when the file could not be stat'd, so a
    missing key is never mistaken for a matching one.
    """
    if stat_key is None:
        return f"unknown:{os.path.abspath(path)}"
    return f"{os.path.abspath(path)}:{stat_key[0]}:{stat_key[1]}"


class UnreadableIfc(ValueError):
    """An IFC refused BEFORE ifcopenshell sees it, because ifcopenshell would crash on it."""


@lru_cache(maxsize=8)
def _open_cached(path: str, _key) -> ifcopenshell.file:
    # R31-SCHEMA-DIAG pre-flight. ifcopenshell 0.8.5 **segfaults** (exit 139, reproduced 3/3) on an
    # IFC that ends inside an unclosed `'` literal — the shape a truncated upload or an interrupted
    # write produces. A segfault is not an exception: no `try/except` here or in any of this
    # function's 133 callers can catch it, and the process handling the request dies. So the one
    # input that crashes is detected first and refused as an ordinary error.
    #
    # Deliberately NARROW. Other structural faults are not like this: an unclosed parenthesis and a
    # file truncated mid-instance both fail `schema_diag`'s checks and ifcopenshell opens them without
    # complaint. Screening on "does not parse structurally" would reject files that work today, which
    # is a worse bug than the one being fixed. The full diagnostic stays opt-in via
    # `schema_diag.diagnose_file` — it costs ~38 s on a 51 MB model and has no business on this path.
    #
    # Imported here rather than at module scope: `schema_diag` reads the ifcopenshell schema wrapper,
    # and `ifc_loader` is imported by nearly everything.
    from .schema_diag import scan_unterminated_string
    try:
        bad = scan_unterminated_string(path)
    except OSError:
        bad = False                             # unreadable for other reasons — let ifcopenshell say so
    if bad:
        raise UnreadableIfc(
            f"{os.path.basename(path)} ends inside an unclosed string literal, which crashes the IFC "
            f"parser. The file is most likely truncated — re-export or re-upload it.")
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

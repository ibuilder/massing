"""Shared IFC open/iteration helpers. All extraction is keyed by IFC GlobalId (GUID)
so results reconcile against model updates (CLAUDE.md non-negotiable)."""
from __future__ import annotations

import os
from collections import OrderedDict
from collections.abc import Iterable

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


class _ModelCache:
    """Bounded `(path, stat) -> model` cache, replacing `lru_cache` so an edit can SEED it.

    R42-SESSION-MODEL. The cache was correct and structurally unable to help the one loop that
    needs it most. `open_model` keys on `(path, mtime, size)` — right, because a rewritten file must
    not be served stale — but **every authoring edit writes a NEW timestamped file**, so the next
    edit's key differs and misses by construction. `open_model`'s own docstring says as much: *"The
    /edit path already writes a new timestamped file, so it was never affected."* Read as a
    reassurance, it is actually the diagnosis.

    The post-write model is already in memory and is byte-for-byte what was just saved, so seeding it
    under the new file's key is not a guess — it is registering a fact the writer already knows. What
    `lru_cache` cannot express is exactly that: it can only populate itself by calling the function
    it wraps, i.e. by re-reading a file it already has the answer for.

    Same maxsize, same key, same eviction order as before. `cache_clear` is kept because callers and
    `test_cache_key.py` use it.
    """

    def __init__(self, maxsize: int = 8) -> None:
        self._d: OrderedDict = OrderedDict()
        self.maxsize = maxsize

    def __call__(self, path: str, key) -> ifcopenshell.file:
        k = (path, key)
        hit = self._d.get(k)
        if hit is not None:
            self._d.move_to_end(k)
            return hit
        model = _open_uncached(path)
        self._put(k, model)
        return model

    def _put(self, k, model) -> None:
        self._d[k] = model
        self._d.move_to_end(k)
        while len(self._d) > self.maxsize:
            self._d.popitem(last=False)         # evict least-recently-used, as lru_cache did

    def seed(self, path: str, model: ifcopenshell.file) -> bool:
        """Register `model` as the content of `path`, which the caller has just written.

        Stats the file itself rather than taking a key: the key MUST be the one `open_model` will
        compute, and deriving it here is the only way to be sure. Returns False when the file cannot
        be stat'd — a seed that cannot be keyed is dropped rather than stored under a guess, because
        a wrongly-keyed model is served to the next reader as if it were their file.
        """
        try:
            st = os.stat(path)
        except OSError:
            return False
        key = (st.st_mtime_ns, st.st_size)
        self._put((path, key), model)
        # Keep the content stamp consistent with where the model now LIVES. `open_model` re-stamps on
        # every call, so this only matters for a reader that touches the seeded object before the
        # next `open_model` — but that reader would otherwise see the PREVIOUS version's key on
        # post-edit geometry, which is the kind of quiet mismatch derived caches are built on.
        try:
            model.__aec_content_key__ = content_key(path, key)
        except AttributeError:
            pass
        return True

    def evict(self, path: str) -> int:
        """Forget every entry for `path`. Returns how many went, so a caller can assert on it.

        ── WHY A MUTATING READER MUST CALL THIS ──────────────────────────────────────────────────
        This cache hands out a SHARED, MUTABLE model. `apply_recipe` opens its input through here and
        then mutates that object in place before writing the result to a *different* file — so the
        moment an edit finishes, the entry for its INPUT path describes a file it no longer matches.

        Measured 2026-08-09 on a freshly written base with no walls::

            walls on disk in base .............. 0
            walls via open_model(base) [cached]  1     <-- after one edit that merely READ base

        Anything that reopens that path afterwards is handed the next version's content under the
        previous version's name: undo/redo restoring a prior version, a version-to-version compare, a
        drawing or export generated from an earlier source, or simply two edits branching off one
        base. It fails silently and in the most convincing possible way — a real model, fully
        readable, just not the one that was asked for.

        This is NOT new with the seeding work; `lru_cache` keyed the same way and had the same hole.
        What changed is that R42's authoring loop finally hits the cache often enough to matter.

        Evicting rather than deep-copying is deliberate: a copy of a multi-hundred-MB model on every
        edit would cost more than the cache saves, and the mutator genuinely wants the object it was
        given. What it must not do is leave that object registered under its old name.
        """
        stale = [k for k in self._d if k[0] == path]
        for k in stale:
            del self._d[k]
        return len(stale)

    def cache_clear(self) -> None:
        self._d.clear()

    def cache_info(self) -> dict:
        return {"size": len(self._d), "maxsize": self.maxsize}


def _open_uncached(path: str) -> ifcopenshell.file:
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


#: The one cache. A second cache keyed on the same thing is how two answers to "what is in this
#: file" start disagreeing, so seeding goes through this object rather than beside it.
_open_cached = _ModelCache(maxsize=8)


def open_model_for_write(path: str) -> ifcopenshell.file:
    """Open a model you intend to MUTATE. Same object `open_model` gives you, minus the cache entry.

    Use this — never bare `open_model` — whenever the returned model will be mutated and written,
    which in practice means "anywhere a `.write(...)` follows in the same function".

    The cache hands out a shared, mutable model. Mutating one obtained through `open_model` leaves the
    entry for that path describing a file it no longer matches, and the next reader of that version
    is silently handed a different model under its name (see `_ModelCache.evict` for the measurement).

    A named entry point rather than "remember to call evict": the four mutating readers in this
    codebase were written by different people at different times, and three of them did not know the
    hazard existed. The one that did — the subset export in `routers/bim.py` — worked around it
    locally with an uncached `ifcopenshell.open` and a comment, which fixed that site and taught
    nothing to the others. `services/api/test_mutating_readers.py` now enumerates them instead.
    """
    model = open_model(path)
    evict_model_cache(path)
    return model


def evict_model_cache(path: str) -> int:
    """Drop every cached model for `path` — call before mutating a model this cache handed out.

    Module-level twin of `seed_model_cache`, so `edit.py` need not reach into `_open_cached`.
    """
    return _open_cached.evict(path)


def seed_model_cache(path: str, model: ifcopenshell.file) -> bool:
    """Public seam for a writer that has just saved `model` to `path` — see `_ModelCache.seed`."""
    return _open_cached.seed(path, model)


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


def storey_of(element):
    """The IfcBuildingStorey ENTITY for this element — via spatial containment (most elements) or
    aggregation (IfcSpace decomposes from its storey).

    Split out from `storey_name` so a caller can have the storey's **GlobalId**. The name alone is
    not an identity: two buildings on one site each having a "Level 2" is the ordinary case, and any
    grouping keyed on the string merges them without a symptom. Returns the entity or None; the
    caller decides which attribute it wants.
    """
    # containment chain
    container = ue.get_container(element)
    while container is not None:
        if container.is_a("IfcBuildingStorey"):
            return container
        container = ue.get_aggregate(container) if hasattr(ue, "get_aggregate") else None
    # aggregation parent (spaces, etc.)
    if hasattr(ue, "get_aggregate"):
        agg = ue.get_aggregate(element)
        while agg is not None:
            if agg.is_a("IfcBuildingStorey"):
                return agg
            agg = ue.get_aggregate(agg)
    return None


def storey_name(element) -> str | None:
    """Name of the IfcBuildingStorey for this element. Thin wrapper over `storey_of` — kept because
    a dozen call sites want the label and nothing else."""
    st = storey_of(element)
    return st.Name if st is not None else None

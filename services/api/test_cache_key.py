"""CACHE-KEY — the geometry cache is keyed by WHICH FILE, not by a memory address.

`bake()` memoized on `id(model)` with a strong reference held per entry to stop the address being
reused after a GC. That worked, and the guard's existence is the tell: an identity key is only valid
inside one process, for as long as nothing is collected.

It also capped what the cache could ever become. Tessellation is the dominant per-request cost and
the same file is opened by every worker, but an address in one worker's heap means nothing in
another — so the expensive half could never be shared however it was stored. Keying on the file's
identity (path + mtime + size, which `open_model` already uses) is the prerequisite for that, and
removes the `id()`-reuse fragility whether sharing ever happens or not.

Run: PYTHONPATH="src;../data/src" ./.venv/Scripts/python.exe test_cache_key.py
"""
from __future__ import annotations

import os
import sys

_DATA_SRC = os.path.join(os.path.dirname(__file__), "..", "data", "src")
if _DATA_SRC not in sys.path:
    sys.path.insert(0, _DATA_SRC)

import ifcopenshell  # noqa: E402

from aec_data import drawings, ifc_loader  # noqa: E402


def test_a_model_opened_through_open_model_carries_its_content_key():
    import tempfile
    f = ifcopenshell.file(schema="IFC4")
    with tempfile.TemporaryDirectory() as d:
        p = os.path.join(d, "m.ifc")
        f.write(p)
        m = ifc_loader.open_model(p)
        assert getattr(m, "__aec_content_key__", None), "open_model must stamp the key"
        assert drawings._bake_key(m)[0] == "content"


def test_the_key_names_the_FILE_not_the_object():
    import tempfile
    f = ifcopenshell.file(schema="IFC4")
    with tempfile.TemporaryDirectory() as d:
        p = os.path.join(d, "m.ifc")
        f.write(p)
        a = ifc_loader.open_model(p)
        ifc_loader._open_cached.cache_clear()          # force a genuinely new object
        b = ifc_loader.open_model(p)
        assert a is not b, "expected two distinct model objects"
        assert drawings._bake_key(a) == drawings._bake_key(b), (
            "the same file must produce the same key — this is what makes the bake shareable")


def test_a_REWRITTEN_file_is_a_DIFFERENT_key():
    # The case the stat key exists for: republishing to the same `source.ifc` path. A cache that
    # served the old geometry here would draw the previous revision of the building.
    import tempfile
    import time
    with tempfile.TemporaryDirectory() as d:
        p = os.path.join(d, "m.ifc")
        ifcopenshell.file(schema="IFC4").write(p)
        first = ifc_loader.open_model(p)
        k1 = drawings._bake_key(first)
        time.sleep(0.01)
        m2 = ifcopenshell.file(schema="IFC4")
        m2.create_entity("IfcProject", GlobalId="0" * 22)      # different content → different size
        m2.write(p)
        ifc_loader._open_cached.cache_clear()
        k2 = drawings._bake_key(ifc_loader.open_model(p))
        assert k1 != k2, "a rewritten file must not hit the previous geometry"


def test_a_model_opened_DIRECTLY_falls_back_to_identity():
    # Bypassing open_model means no known file identity. Falling back to id() is the previous
    # behaviour and the correct one: an UNKNOWN identity must never collide with a known one.
    m = ifcopenshell.file(schema="IFC4")
    kind, val = drawings._bake_key(m)
    assert kind == "id" and val == id(m)


def test_an_unstattable_path_is_marked_unknown_not_given_a_shared_key():
    k = ifc_loader.content_key("/no/such/file.ifc", None)
    assert k.startswith("unknown:"), k
    # Two different missing files must still differ — "unknown" is not one bucket.
    assert k != ifc_loader.content_key("/no/other/file.ifc", None)


def test_the_content_key_is_stable_for_the_same_stat():
    a = ifc_loader.content_key("/x/y.ifc", (123, 456))
    b = ifc_loader.content_key("/x/y.ifc", (123, 456))
    assert a == b and ifc_loader.content_key("/x/y.ifc", (124, 456)) != a


for _n, _f in sorted(list(globals().items())):
    if _n.startswith("test_") and callable(_f):
        _f()

print("CACHE-KEY OK - the geometry cache is keyed by WHICH FILE (path+mtime+size, the identity "
      "open_model already uses) rather than by id(model). The old key worked only inside one process "
      "and only while a strong ref stopped the address being reused after a GC - a guard whose "
      "existence is the tell. It also capped what the cache could become: tessellation is the "
      "dominant per-request cost and every worker opens the same file, but an address in one "
      "worker's heap means nothing in another, so the expensive half could never be shared however "
      "it was stored. A REWRITTEN file is a different key, so republishing to the same source.ifc "
      "cannot draw the previous revision. And a model opened directly, bypassing open_model, still "
      "falls back to identity - an UNKNOWN file identity must never collide with a known one.")

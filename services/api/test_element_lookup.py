"""PERF-LOOKUP — `edit_core._element` resolves a GlobalId in constant time, and still narrows to
IfcElement.

Every bulk record-layer recipe (`set_phase`, `verify_asbuilt`, `record_asbuilt_dimension`,
`set_manufacturer_info`, `classify`, `set_spec_link`, `set_lod`, `attach_document`) loops a guid list
calling `_element` once per guid. While that was a linear scan of `by_type("IfcElement")`, stamping N
elements in a model of N elements was O(N**2) — on a 1,153-product model the record pass took 27.6 s,
and 2.4 s once it became a hash lookup.

A wall-clock assertion would be flaky on shared CI, so the guard here is *shape*, not speed: stamping
a model four times larger must not cost sixteen times as much. Quadratic growth fails that; linear
growth passes it with room to spare.

Run: PYTHONPATH="src;../data/src" ./.venv/Scripts/python.exe test_element_lookup.py
"""
import os
import sys
import tempfile
import time
from pathlib import Path

_DATA_SRC = os.path.join(os.path.dirname(__file__), "..", "data", "src")
if _DATA_SRC not in sys.path:
    sys.path.insert(0, _DATA_SRC)

from aec_data import edit, edit_core, massing  # noqa: E402
from aec_data.ifc_loader import open_model  # noqa: E402


def _build(n_columns: int):
    """A model of `n_columns` columns, and the list of their GlobalIds."""
    path = Path(tempfile.gettempdir()) / f"_lookup_{n_columns}.ifc"
    massing.generate_blank_ifc(str(path), name="Lookup", storeys=1, storey_height=3.0,
                               ground_size=10.0)
    m = open_model(str(path))
    st = m.by_type("IfcBuildingStorey")[0].Name
    guids = [edit.add_column(m, [i % 40 * 1.5, i // 40 * 1.5], 3.0, 0.3, 0.3, st)
             for i in range(n_columns)]
    return path, m, guids


def _stamp(model, guids) -> float:
    t0 = time.perf_counter()
    edit.set_phase(model, guids, "new")
    return time.perf_counter() - t0


# --- correctness: it resolves, and it still refuses non-elements -----------------------------------
p1, m1, g1 = _build(40)
el = edit_core._element(m1, g1[0])
assert el.GlobalId == g1[0] and el.is_a("IfcColumn"), el

# an unknown GUID raises, exactly as the scan did — callers catch ValueError
try:
    edit_core._element(m1, "0nOtArEaLgUiD00000000x")
    raise AssertionError("an unknown GUID must raise")
except ValueError:
    pass

# a storey is a rooted entity with a GlobalId, and `by_guid` will happily return it. The narrowing
# matters: without it a stamp aimed at an element could land on a storey, a space, or the project.
storey = m1.by_type("IfcBuildingStorey")[0]
try:
    edit_core._element(m1, storey.GlobalId)
    raise AssertionError("a non-IfcElement must not resolve as an element")
except ValueError:
    pass

# --- shape: cost grows with N, not with N squared --------------------------------------------------
SMALL, LARGE = 60, 240                     # a 4x model
ps, ms, gs = _build(SMALL)
pl, ml, gl = _build(LARGE)
_stamp(ms, gs)                             # warm any first-call overhead
small = min(_stamp(ms, gs) for _ in range(3))
large = min(_stamp(ml, gl) for _ in range(3))

growth = large / small if small > 0 else 1.0
# Quadratic would be ~16x. Linear is ~4x. 9x is the midpoint on a log scale — comfortably above
# linear-plus-noise and comfortably below quadratic, so this fails on a regression and not on a
# slow runner.
assert growth < 9.0, (
    f"stamping 4x the elements cost {growth:.1f}x — that is quadratic growth, so `_element` is "
    f"scanning again rather than hashing ({small * 1000:.1f} ms -> {large * 1000:.1f} ms)")

for p in (p1, ps, pl):
    if p.exists():
        p.unlink()

print(f"PERF-LOOKUP OK - _element resolves by hash, raises on an unknown GUID, and still refuses a "
      f"non-IfcElement; stamping {LARGE} elements cost {growth:.1f}x stamping {SMALL} "
      f"({small * 1000:.1f} ms -> {large * 1000:.1f} ms), which is linear growth, not quadratic.")

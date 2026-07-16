"""ifc_loader.open_model cache correctness: keyed by (path, mtime, size), so a re-written file (a re-upload
/ republish to the SAME path) is reloaded fresh — not served stale from the cache (regression for the
whole-model-replacement bug where reindex/analysis read the previous model).
Run: PYTHONPATH=src ./.venv/Scripts/python.exe test_ifc_cache.py"""
import os
import sys
import tempfile

_DATA_SRC = os.path.join(os.path.dirname(__file__), "..", "data", "src")
if _DATA_SRC not in sys.path:
    sys.path.insert(0, _DATA_SRC)

from aec_data import massing  # noqa: E402
from aec_data.ifc_loader import open_model  # noqa: E402

P = os.path.join(tempfile.gettempdir(), "_ifc_cache_test.ifc")

# open model A (1 storey)
massing.generate_blank_ifc(P, name="A", storeys=1, storey_height=3.0, ground_size=20.0)
m1 = open_model(P)
assert len(m1.by_type("IfcBuildingStorey")) == 1, m1.by_type("IfcBuildingStorey")

# re-opening the UNCHANGED path returns the same cached instance (fast path still works)
assert open_model(P) is m1, "unchanged file should hit the cache"

# rewrite the SAME path with a DIFFERENT model (3 storeys) → must reload fresh, not serve the stale cache
massing.generate_blank_ifc(P, name="B", storeys=3, storey_height=3.0, ground_size=20.0)
m2 = open_model(P)
assert m2 is not m1, "a re-written file must not return the stale cached instance"
assert len(m2.by_type("IfcBuildingStorey")) == 3, "reloaded model must reflect the new file (3 storeys)"

if os.path.exists(P):
    os.remove(P)

print("IFC-CACHE OK - open_model caches by (path, mtime, size): an unchanged path hits the cache (same "
      "instance), but a file re-written in place reloads fresh (3 storeys, not the stale 1) — so a "
      "whole-model re-upload/republish is seen by reindex + all analysis instead of serving stale data.")

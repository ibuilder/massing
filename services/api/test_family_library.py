"""IFC family library — generated parametric catalog + shippable library.ifc + place-from-library.
Run: PYTHONPATH=src ./.venv/Scripts/python.exe test_family_library.py"""
import os
import tempfile

os.environ["DATABASE_URL"] = "sqlite:///./test_family_library.db"
os.environ["STORAGE_DIR"] = "./test_storage_family_library"
# IFC_DIR is read at import time by the authoring router (place-family writes IFC here); point it at a
# writable temp dir so this runs in CI's container (where the default /app/ifc is not writable).
os.environ["IFC_DIR"] = tempfile.mkdtemp(prefix="famlib_ifc_")
os.environ.pop("AEC_RBAC", None)
for _f in ("./test_family_library.db",):
    if os.path.exists(_f):
        os.remove(_f)

import sys  # noqa: E402

sys.path.insert(0, os.path.abspath(os.path.join("..", "data", "src")))

import ifcopenshell  # noqa: E402

from aec_data import families  # noqa: E402
from aec_data.build_family_library import LIBRARY_PATH, build_model  # noqa: E402

# --- catalog expanded with openings + enclosure ---
keys = {f["key"] for f in families.CATALOG}
for k in ("single_door", "double_door", "fixed_window", "partition_wall", "curtain_wall", "concrete_column"):
    assert k in keys, f"missing family {k}"
cats = {f["category"] for f in families.CATALOG}
assert {"Openings", "Enclosure", "Structural", "MEP", "Sanitary"} <= cats, cats

# --- the generated library builds real, geometry-bearing types + round-trips ---
model = build_model()
types = model.by_type("IfcTypeProduct")
assert len(types) == len(families.CATALOG), (len(types), len(families.CATALOG))
withgeom = [t for t in types if t.RepresentationMaps]
assert len(withgeom) == len(types), f"only {len(withgeom)}/{len(types)} types have geometry"
# the shipped library.ifc exists and reopens with the same content
assert LIBRARY_PATH.exists(), f"library.ifc not built at {LIBRARY_PATH}"
reopened = ifcopenshell.open(str(LIBRARY_PATH))
assert len(reopened.by_type("IfcTypeProduct")) == len(families.CATALOG), "library.ifc type count"
assert reopened.schema == "IFC4", reopened.schema

# --- OUTSIDE a checkout there is nowhere to write, and that must be a refusal, not a crash -------
# `LIBRARY_PATH` became Optional when the directory count that produced it was replaced with a walk
# to the repository's shape: outside a source tree there IS no committed artifact to regenerate. The
# annotation still said `Path` and the body still did `out_path.parent`, so
# `python -m aec_data.build_family_library` off a checkout raised
# `AttributeError: 'NoneType' object has no attribute 'parent'`.
#
# This case exists because a mutation said it had to: deleting the guard left every other test in
# this file green, since they all run in a checkout where LIBRARY_PATH is a real path. A guard whose
# removal nothing notices is a guard nobody has checked.
from aec_data.build_family_library import build  # noqa: E402

try:
    build(None)
except RuntimeError as e:
    assert "no checkout" in str(e), f"wrong refusal message: {e}"
except AttributeError as e:                      # the pre-fix behaviour
    raise AssertionError(
        f"build(None) crashed instead of refusing: {e!r}. Outside a source tree this must say what "
        f"is wrong, not dereference None.") from None
else:
    raise AssertionError("build(None) returned a result; it has nowhere to write and must refuse")

# --- endpoints: library listing + place-from-library into a generated project ---
from fastapi.testclient import TestClient  # noqa: E402

from aec_api.main import app  # noqa: E402

with TestClient(app) as c:
    lib = c.get("/families/library")
    assert lib.status_code == 200, lib.text[:160]
    j = lib.json()
    assert j["count"] == len(families.CATALOG) and j["generated_library"]["exists"], j["generated_library"]
    assert "Openings" in j["categories"] and "Enclosure" in j["categories"], list(j["categories"])
    # generate a tiny project, then place a library family (door) into it
    pid = c.post("/projects", json={"name": "P"}).json()["id"]
    g = c.post(f"/projects/{pid}/generate/massing",
               json={"lot_width": 30, "lot_depth": 20, "far": 1.0, "height_limit_m": 9, "use_type": "residential"})
    assert g.status_code == 200, g.text[:200]
    pl = c.post(f"/projects/{pid}/families/place", json={"family": "single_door", "position": [5.0, 5.0]})
    assert pl.status_code == 200 and pl.json().get("changed"), pl.text[:200]   # 'changed' = new GUID

print("FAMILY LIBRARY OK - catalog expanded (openings/enclosure/structural); build_model yields "
      f"{len(types)} geometry-bearing types; library.ifc ships + reopens (IFC4); /families/library lists "
      "generated catalog; place-from-library adds a GUID-stable door occurrence")

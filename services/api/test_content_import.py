"""CONTENT-1 (import): parse an uploaded mesh (OBJ/GLB) → verts/faces (recentred, metres), auto-detect the
catalog category from the filename, and place it as the RIGHT IFC via place_content.
Run: PYTHONPATH=src ./.venv/Scripts/python.exe test_content_import.py"""
import os
import sys

_DATA_SRC = os.path.join(os.path.dirname(__file__), "..", "data", "src")
if _DATA_SRC not in sys.path:
    sys.path.insert(0, _DATA_SRC)

import trimesh  # noqa: E402

from aec_data import content, edit, massing  # noqa: E402
from aec_data.ifc_loader import open_model  # noqa: E402

# --- category auto-detection from a filename (longest synonym wins) --------------------------------
assert content.detect_category("office-chair.glb") == "chair", content.detect_category("office-chair.glb")
assert content.detect_category("Tower_Crane_v3.obj") == "tower_crane"
assert content.detect_category("mobile crane.glb") == "mobile_crane"        # beats plain "crane"
assert content.detect_category("Porta-John.stl") == "sanitary_unit"
assert content.detect_category("oak-tree.glb") == "tree"
assert content.detect_category("nondescript-blob.glb") is None             # no match → caller must pick

# --- parse an OBJ box → verts (metres, recentred) + faces (0-based) --------------------------------
box = trimesh.creation.box(extents=[2.0, 1.0, 3.0])
obj_bytes = box.export(file_type="obj").encode() if isinstance(box.export(file_type="obj"), str) else box.export(file_type="obj")
verts, faces = content.parse_mesh(obj_bytes, ".obj")
assert len(verts) >= 8 and len(faces) >= 12, (len(verts), len(faces))      # a box: 8 verts, 12 tris
import numpy as np  # noqa: E402
vv = np.asarray(verts)
assert vv.min(axis=0).max() < 1e-6, vv.min(axis=0)                          # min-corner recentred to ~origin
ext = vv.max(axis=0) - vv.min(axis=0)
assert abs(ext[0] - 2.0) < 1e-6 and abs(ext[2] - 3.0) < 1e-6, ext          # OBJ (no rotation): x=2, z=3
# scale multiplies the size
v2, _ = content.parse_mesh(obj_bytes, ".obj", scale=2.0)
assert abs((np.asarray(v2).max(axis=0) - np.asarray(v2).min(axis=0))[0] - 4.0) < 1e-6

# --- GLB parse: Y-up → Z-up rotation applied (parses without error, valid mesh) --------------------
glb_bytes = box.export(file_type="glb")
gverts, gfaces = content.parse_mesh(glb_bytes, ".glb")
assert len(gverts) >= 8 and len(gfaces) >= 12, (len(gverts), len(gfaces))
assert np.asarray(gverts).min(axis=0).max() < 1e-6, "GLB mesh recentred too"

# --- place the parsed mesh as the RIGHT IFC (chair → IfcFurniture + classification) ----------------
TMP = os.path.join(os.path.dirname(__file__), "_import_test.ifc")
massing.generate_blank_ifc(TMP, name="Import Test", storeys=1, storey_height=3.0, ground_size=30.0)
m = open_model(TMP)
st = m.by_type("IfcBuildingStorey")[0].Name
r = edit.place_content(m, "chair", [5, 5], verts, faces, name="Imported chair", storey=st)
assert r["ifc_class"] == "IfcFurniture", r
el = next((e for e in m.by_type("IfcFurniture") if e.Name == "Imported chair"), None)
assert el is not None and el.Representation is not None, "imported chair authored with geometry"
# it carries the catalog classification (association present)
assert any(rel.is_a("IfcRelAssociatesClassification") for rel in m.by_type("IfcRelAssociatesClassification")), "classified"

# --- over-large mesh rejected ---------------------------------------------------------------------
raised = False
try:
    content.parse_mesh(obj_bytes, ".obj", max_faces=1)
except ValueError as e:
    raised = True
    assert "faces" in str(e), str(e)
assert raised, "an over-large mesh should be rejected"

if os.path.exists(TMP):
    os.remove(TMP)

print("CONTENT-IMPORT OK - detect_category maps filenames to catalog keys (office-chair->chair, mobile "
      "crane->mobile_crane, porta-john->sanitary_unit; no-match->None); parse_mesh loads OBJ/GLB into "
      "recentred metre verts + 0-based faces (scale multiplies; GLB Y-up->Z-up; over-large rejected); the "
      "parsed mesh places as the right IFC (chair->IfcFurniture with classification).")

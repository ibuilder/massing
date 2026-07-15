"""B4 procedural-mesh escape hatch: add_mesh_representation authors an element from a raw triangle mesh
(IfcTriangulatedFaceSet). Verified objectively — tessellate the result and confirm the mesh geometry
survives (same vertex extents), not by eyeballing.
Run: PYTHONPATH=src ./.venv/Scripts/python.exe test_mesh.py"""
import os
import sys

_DATA_SRC = os.path.join(os.path.dirname(__file__), "..", "data", "src")
if _DATA_SRC not in sys.path:
    sys.path.insert(0, _DATA_SRC)

import ifcopenshell.geom  # noqa: E402

from aec_data import edit, massing  # noqa: E402
from aec_data.ifc_loader import open_model  # noqa: E402

TMP = os.path.join(os.path.dirname(__file__), "_mesh_test.ifc")
massing.generate_blank_ifc(TMP, name="Mesh Test", storeys=1, storey_height=4.0, ground_size=20.0)
m = open_model(TMP)
st = m.by_type("IfcBuildingStorey")[0].Name

# a square pyramid (apex at 2 m): 5 verts, 6 triangles (4 sides + 2 base tris), 0-based faces
verts = [[0, 0, 0], [2, 0, 0], [2, 2, 0], [0, 2, 0], [1, 1, 2]]
faces = [[0, 1, 4], [1, 2, 4], [2, 3, 4], [3, 0, 4], [0, 2, 1], [0, 3, 2]]
guid = edit.add_mesh_representation(m, verts, faces, name="Pyramid", storey=st)

el = m.by_guid(guid)
assert el.is_a("IfcBuildingElementProxy") and el.Name == "Pyramid", el
# the representation is a Tessellation with an IfcTriangulatedFaceSet
rep = el.Representation.Representations[0]
assert rep.RepresentationType == "Tessellation", rep.RepresentationType
tfs = rep.Items[0]
assert tfs.is_a("IfcTriangulatedFaceSet") and len(tfs.CoordIndex) == 6, tfs
assert len(tfs.Coordinates.CoordList) == 5, "5 vertices"
# IFC CoordIndex is 1-based
assert all(all(1 <= i <= 5 for i in tri) for tri in tfs.CoordIndex), "1-based indices"

# OBJECTIVE: tessellate → the mesh geometry is present with the expected extents (2×2 base, apex at 2 m)
settings = ifcopenshell.geom.settings()
settings.set(settings.USE_WORLD_COORDS, True)
shp = ifcopenshell.geom.create_shape(settings, el)
vs = shp.geometry.verts
pts = [(vs[i], vs[i + 1], vs[i + 2]) for i in range(0, len(vs), 3)]
assert pts, "mesh tessellates"
assert abs(max(p[2] for p in pts) - 2.0) < 0.02, f"apex should be at 2 m, got {max(p[2] for p in pts):.2f}"
assert abs(max(p[0] for p in pts) - 2.0) < 0.02 and abs(max(p[1] for p in pts) - 2.0) < 0.02, "2×2 base"
assert abs(min(p[2] for p in pts)) < 0.02, "base at Z=0"
assert len(shp.geometry.faces) >= 6 * 3, "at least 6 triangles"

# bad input is rejected
for bad in (lambda: edit.add_mesh_representation(m, [[0, 0, 0]], [[0, 1, 2]]),       # <3 verts
            lambda: edit.add_mesh_representation(m, verts, [[0, 1, 99]])):           # index out of range
    try:
        bad()
        raise AssertionError("should have raised")
    except ValueError:
        pass

if os.path.exists(TMP):
    os.remove(TMP)

print("MESH OK - add_mesh_representation authors an IfcBuildingElementProxy with an IfcTriangulatedFaceSet "
      "(Tessellation rep, 1-based CoordIndex); tessellation confirms a square pyramid (2×2 base, apex at "
      "2 m, base at Z=0, ≥6 triangles); degenerate mesh + out-of-range face index are rejected.")

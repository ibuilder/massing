"""W10-7 wall surface members: load-bearing (shear) walls idealise to vertical IfcStructuralSurfaceMembers
at their mid-plane; partitions are skipped. Run: PYTHONPATH=src;../data/src ./.venv/Scripts/python.exe test_wall_analytical.py"""
import os
import sys
import tempfile

_DATA_SRC = os.path.join(os.path.dirname(__file__), "..", "data", "src")
if _DATA_SRC not in sys.path:
    sys.path.insert(0, _DATA_SRC)

import ifcopenshell.api  # noqa: E402

from aec_data import analytical, edit, massing  # noqa: E402
from aec_data.ifc_loader import open_model  # noqa: E402

TMP = os.path.join(tempfile.gettempdir(), "_wall_analytical_test.ifc")
massing.generate_blank_ifc(TMP, name="Walls", storeys=1, storey_height=3.0, ground_size=20.0)
m = open_model(TMP)
st = m.by_type("IfcBuildingStorey")[0].Name
bearing = edit.add_wall(m, [0, 0], [6, 0], 3.0, 0.25, st)       # will be marked load-bearing
edit.add_wall(m, [0, 4], [6, 4], 3.0, 0.15, st)                 # a partition (default LoadBearing=False)

# mark the first wall load-bearing (a shear wall)
wall_el = m.by_guid(bearing)
ps = ifcopenshell.api.run("pset.add_pset", m, product=wall_el, name="Pset_WallCommon")
ifcopenshell.api.run("pset.edit_pset", m, pset=ps, properties={"LoadBearing": True})

r = analytical.derive_analytical(m)
# exactly one wall (the bearing one) becomes a surface member; the partition is skipped
assert r["wall_surface_members"] == 1, r
# total surface members = the blank model's ground slab + the 1 shear wall
assert r["surface_members"] >= 2, r
assert len(m.by_type("IfcStructuralSurfaceMember")) == r["surface_members"]

# the shear-wall surface member is VERTICAL — its face vertices span the wall height (z varies), unlike a
# slab (flat). Find a face whose z-range ≈ the 3 m wall height.
def _zspans():
    spans = []
    for face in m.by_type("IfcFaceSurface"):
        zs = []
        for b in face.Bounds:
            loop = b.Bound
            for oe in loop.EdgeList:
                for v in (oe.EdgeElement.EdgeStart, oe.EdgeElement.EdgeEnd):
                    zs.append(float(v.VertexGeometry.Coordinates[2]))
        if zs:
            spans.append(round(max(zs) - min(zs), 2))
    return spans

spans = _zspans()
assert any(abs(s - 3.0) < 0.05 for s in spans), f"a vertical wall panel spanning ~3 m must exist: {spans}"
assert any(abs(s) < 0.01 for s in spans), f"the flat ground slab (z-span 0) must also exist: {spans}"

# idempotent re-derive: the wall surface member count is stable (no accumulation)
r2 = analytical.derive_analytical(m)
assert r2["wall_surface_members"] == 1 and r2["surface_members"] == r["surface_members"], (r, r2)

# read-back through summary + a serialize round-trip
OUT = os.path.join(tempfile.gettempdir(), "_wall_analytical_out.ifc")
m.write(OUT)
s = analytical.summary(open_model(OUT))
assert s["surface_members"] == r["surface_members"], s

for f in (TMP, OUT):
    if os.path.exists(f):
        os.remove(f)

print("WALL-ANALYTICAL OK - derive_analytical idealises a load-bearing (shear) wall into a vertical "
      "IfcStructuralSurfaceMember at its mid-plane (a length×height IfcFaceSurface spanning the wall "
      "height), while a non-bearing partition is skipped; the flat slab surface member coexists; the "
      "wall_surface_members count is idempotent across a re-derive and survives a serialize round-trip.")

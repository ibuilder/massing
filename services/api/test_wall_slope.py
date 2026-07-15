"""B3 sloped-top wall: set_wall_slope rebuilds the wall Body as a trapezoidal side-profile extruded across
the thickness, so the top slopes from start_height→end_height. Verified OBJECTIVELY by tessellating the
geometry (ifcopenshell.geom) and confirming the top actually varies with position — not by eyeballing.
Run: PYTHONPATH=src ./.venv/Scripts/python.exe test_wall_slope.py"""
import os
import sys

_DATA_SRC = os.path.join(os.path.dirname(__file__), "..", "data", "src")
if _DATA_SRC not in sys.path:
    sys.path.insert(0, _DATA_SRC)

import ifcopenshell.geom  # noqa: E402

from aec_data import edit, massing  # noqa: E402
from aec_data.ifc_loader import open_model  # noqa: E402

TMP = os.path.join(os.path.dirname(__file__), "_slope_test.ifc")
massing.generate_blank_ifc(TMP, name="Slope Test", storeys=1, storey_height=5.0, ground_size=20.0)
m = open_model(TMP)
st = m.by_type("IfcBuildingStorey")[0].Name

# a wall along +X so world coords == wall-local (no rotation); length 6, thickness 0.2, height 3
w = edit.add_wall(m, [0, 0], [6, 0], 3.0, 0.2, st)


def world_verts(guid):
    settings = ifcopenshell.geom.settings()
    settings.set(settings.USE_WORLD_COORDS, True)
    shp = ifcopenshell.geom.create_shape(settings, m.by_guid(guid))
    vs = shp.geometry.verts
    return [(vs[i], vs[i + 1], vs[i + 2]) for i in range(0, len(vs), 3)]


# BEFORE: a flat wall — every top vertex is at Z≈3
flat = world_verts(w)
assert flat, "flat wall tessellates"
assert abs(max(v[2] for v in flat) - 3.0) < 0.05, f"flat top should be 3, got {max(v[2] for v in flat):.2f}"

# slope the top: 2 m at the start end (x≈0) → 4 m at the far end (x≈6)
res = edit.set_wall_slope(m, w, start_height=2.0, end_height=4.0)
assert abs(res["length"] - 6.0) < 0.01 and abs(res["thickness"] - 0.2) < 0.01, res

sl = world_verts(w)
zmax = max(v[2] for v in sl)
zmin = min(v[2] for v in sl)
assert abs(zmax - 4.0) < 0.05, f"sloped top max should be 4 (end_height), got {zmax:.2f}"
assert zmin < 0.05, f"wall base should reach Z=0, got {zmin:.2f}"

# THE KEY CHECK — the top genuinely SLOPES: near the start end (min world X) the top is ~2 m,
# near the far end (max world X) the top is ~4 m. Bucket vertices by X and compare their max Z.
xs = [v[0] for v in sl]
xmin, xmax = min(xs), max(xs)
start_top = max((v[2] for v in sl if v[0] < xmin + 0.5), default=0)   # vertices at the start end
end_top = max((v[2] for v in sl if v[0] > xmax - 0.5), default=0)     # vertices at the far end
assert abs(start_top - 2.0) < 0.1, f"start-end top should be ~2, got {start_top:.2f}"
assert abs(end_top - 4.0) < 0.1, f"far-end top should be ~4, got {end_top:.2f}"
assert end_top - start_top > 1.5, "the top must actually rise from start to end (a real slope)"

# a level slope (start==end) reduces to a flat taller wall (both ends equal)
edit.set_wall_slope(m, w, start_height=3.5, end_height=3.5)
lv = world_verts(w)
assert abs(max(v[2] for v in lv) - 3.5) < 0.05, "equal heights → flat top at 3.5"

# non-wall / bad heights are rejected
for bad in (lambda: edit.set_wall_slope(m, "not-a-guid", 2, 4),
            lambda: edit.set_wall_slope(m, w, 0, 4)):
    try:
        bad()
        raise AssertionError("should have raised")
    except ValueError:
        pass

if os.path.exists(TMP):
    os.remove(TMP)

print("WALL-SLOPE OK - set_wall_slope rebuilds the wall Body as a trapezoidal extrusion; tessellation "
      "confirms a flat wall tops out at 3 m, and after sloping the start end is ~2 m and the far end ~4 m "
      "(a real rising slope, base at Z=0); equal heights give a flat top; non-wall / non-positive heights rejected.")

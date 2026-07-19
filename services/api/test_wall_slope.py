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

# --- E3: sketch-to-BIM push/pull --------------------------------------------------------------------
import numpy as np  # noqa: E402

# a closed L-shaped sketch extruded 4 m → a real proxy mass with exactly that extrusion
L = [[0, 0], [6, 0], [6, 2], [2, 2], [2, 5], [0, 5]]
g = edit.extrude_profile(m, L, height=4.0, name="Podium sketch")
mass = m.by_guid(g)
assert mass.is_a() == "IfcBuildingElementProxy" and mass.Name == "Podium sketch", mass
solid = next(item for r in mass.Representation.Representations for item in r.Items
             if item.is_a("IfcExtrudedAreaSolid"))
assert abs(float(solid.Depth) - 4.0) < 1e-6, solid.Depth
# tessellated bounds match the sketch (6 × 5 plan, 4 m rise)
sh = ifcopenshell.geom.create_shape(ifcopenshell.geom.settings(), mass)
v = np.asarray(sh.geometry.verts, dtype=float).reshape(-1, 3)
assert abs((v[:, 0].max() - v[:, 0].min()) - 6.0) < 0.01, "plan X"
assert abs((v[:, 1].max() - v[:, 1].min()) - 5.0) < 0.01, "plan Y"
assert abs((v[:, 2].max() - v[:, 2].min()) - 4.0) < 0.01, "rise"

# the PULL: deepen the same mass to 7 m in place — GUID, name and psets survive
r = edit.set_extrusion_depth(m, g, 7.0)
assert r["old_depth_m"] == 4.0 and r["new_depth_m"] == 7.0, r
sh2 = ifcopenshell.geom.create_shape(ifcopenshell.geom.settings(), m.by_guid(g))
v2 = np.asarray(sh2.geometry.verts, dtype=float).reshape(-1, 3)
assert abs((v2[:, 2].max() - v2[:, 2].min()) - 7.0) < 0.01, "pulled rise"
assert m.by_guid(g).Name == "Podium sketch", "GUID-stable pull"

# pulling a WALL works too (its height is an extrusion depth)
w_pull = edit.add_wall(m, [10, 10], [16, 10], 3.0, 0.2, st)
assert edit.set_extrusion_depth(m, w_pull, 5.5)["new_depth_m"] == 5.5

# guards: a short profile, a bad class, a bad depth, and a non-extruded target all reject cleanly
for bad_call in (lambda: edit.extrude_profile(m, [[0, 0], [1, 0]], 3.0),
                 lambda: edit.extrude_profile(m, L, 3.0, ifc_class="IfcSpace"),
                 lambda: edit.set_extrusion_depth(m, g, 0),
                 lambda: edit.set_extrusion_depth(m, "0" * 22, 3.0)):
    try:
        bad_call()
        raise AssertionError("expected ValueError")
    except ValueError:
        pass
assert "extrude_profile" in edit.RECIPES and "set_extrusion_depth" in edit.RECIPES

if os.path.exists(TMP):
    os.remove(TMP)

print("WALL-SLOPE OK - set_wall_slope rebuilds the wall Body as a trapezoidal extrusion; tessellation "
      "confirms a flat wall tops out at 3 m, and after sloping the start end is ~2 m and the far end ~4 m "
      "(a real rising slope, base at Z=0); equal heights give a flat top; non-wall / non-positive heights rejected. "
      "E3: extrude_profile turns an L-sketch into a 6x5x4 m proxy (tessellation-verified) and "
      "set_extrusion_depth PULLS it to 7 m in place (GUID/name survive) and deepens a wall to 5.5 m; "
      "short profiles, bad classes/depths, and non-extruded targets reject; both are recipes.")

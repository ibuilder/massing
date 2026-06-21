"""Generative massing: pure zoning math + a from-scratch IFC round-trip.
Run: PYTHONPATH=src ./.venv/Scripts/python.exe test_massing.py"""
import os
import tempfile
import warnings

warnings.filterwarnings("ignore")

from aec_data import massing  # noqa: E402

# --- pure zoning math --------------------------------------------------------
# 50 x 40 lot (2000 m2), FAR 3 -> 6000 m2 buildable. Setbacks 3 side / 6 front+rear.
# Plate = (50-6) x (40-12) = 44 x 28 = 1232 m2, but coverage 0.6 caps it at 1200 m2.
m = massing.compute_massing({
    "lot_width": 50, "lot_depth": 40, "far": 3.0, "coverage_max": 0.6,
    "front_setback": 6, "rear_setback": 6, "side_setback": 3,
    "floor_to_floor": 3.5, "efficiency": 0.8, "avg_unit_m2": 75,
})
assert m["lot_area_m2"] == 2000.0, m["lot_area_m2"]
assert abs(m["footprint_m2"] - 1200.0) < 1.0, m["footprint_m2"]      # coverage-capped
assert m["floors"] == 5, m["floors"]                                  # ceil(6000/1200) = 5
assert abs(m["buildable_gfa_m2"] - 6000.0) < 5.0, m["buildable_gfa_m2"]
assert m["binding_constraint"] in ("FAR", "coverage"), m["binding_constraint"]
assert m["units"] == int(6000 * 0.8 / 75), m["units"]                 # 64 units

# height limit binds before FAR: 14m / 3.5 = 4 floors (not 5)
mh = massing.compute_massing({"lot_area": 2000, "far": 3.0, "height_limit": 14, "floor_to_floor": 3.5})
assert mh["floors"] == 4 and mh["binding_constraint"] == "height", mh

# area-only input (no width/depth) still solves
ma = massing.compute_massing({"lot_area": 1000, "far": 2.0})
assert ma["floors"] >= 1 and ma["buildable_gfa_m2"] > 0, ma

# bad input is rejected
try:
    massing.compute_massing({"far": 2.0})
    assert False, "expected ValueError for missing lot"
except ValueError:
    pass

# --- IFC round-trip (needs ifcopenshell; skip cleanly if absent) -------------
try:
    import ifcopenshell  # noqa: F401
    _have_ifc = True
except ImportError:
    _have_ifc = False

if _have_ifc:
    from aec_data.ifc_loader import open_model
    fd, path = tempfile.mkstemp(suffix=".ifc"); os.close(fd)
    try:
        massing.generate_ifc(m, path, name="Test Massing")
        model = open_model(path)
        storeys = model.by_type("IfcBuildingStorey")
        spaces = model.by_type("IfcSpace")
        slabs = model.by_type("IfcSlab")
        assert len(storeys) == m["floors"], (len(storeys), m["floors"])
        assert len(spaces) == m["floors"], (len(spaces), m["floors"])
        assert len(slabs) == m["floors"], (len(slabs), m["floors"])   # renderable floor plate per level
        assert model.by_type("IfcProject") and model.by_type("IfcSite") and model.by_type("IfcBuilding")
        # spaces carry area; slabs (physical) carry the visible geometry the viewer renders
        assert all(s.Representation is not None for s in spaces), "spaces missing geometry"
        assert all(s.Representation is not None for s in slabs), "slabs missing geometry"
        # geometry must be at metre scale (regression: default mm units shrank the model 1000x)
        import ifcopenshell.geom
        import ifcopenshell.util.unit as _uu
        assert abs(_uu.calculate_unit_scale(model) - 1.0) < 1e-9, "model must be in metres"
        sh = ifcopenshell.geom.create_shape(ifcopenshell.geom.settings(), slabs[0])
        xs = sh.geometry.verts[0::3]
        span = max(xs) - min(xs)
        assert span > 5.0, f"slab too small ({span:.3f} m) — unit/scale regression"
        print(f"IFC OK - {len(storeys)} storeys, {len(spaces)} floor-plate spaces + "
              f"{len(slabs)} renderable slabs, sited + represented")
    finally:
        os.remove(path)
else:
    print("IFC round-trip SKIPPED (ifcopenshell not importable in this interpreter)")

print("MASSING OK - zoning math (FAR/coverage/height binding, units, area-only, validation)")

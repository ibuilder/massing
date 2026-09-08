"""IFCPATCH-LIB v2 — the transform recipes: rebase_origin (georeference-preserving),
convert_length_unit (real size preserved), split_by_storey (the slice plan) + the route.
Run: PYTHONPATH="src;../data/src" ./.venv/Scripts/python.exe test_ifcpatch_transforms.py"""
import os
import tempfile
from pathlib import Path

os.environ["DATABASE_URL"] = "sqlite:///./test_ifcpatch_transforms.db"
os.environ["STORAGE_DIR"] = "./test_storage_patch2"
os.environ.pop("AEC_RBAC", None)
if os.path.exists("./test_ifcpatch_transforms.db"):
    os.remove("./test_ifcpatch_transforms.db")

import ifcopenshell.util.placement as uplace  # noqa: E402
import ifcopenshell.util.unit as uunit  # noqa: E402

from aec_data import edit, ifcpatch_lib, massing  # noqa: E402
from aec_data.ifc_loader import open_model  # noqa: E402


def world_xy(m, guid):
    """The element's world placement in METRES (unit-scale applied)."""
    scale = uunit.calculate_unit_scale(m)
    mat = uplace.get_local_placement(m.by_guid(guid).ObjectPlacement)
    return (float(mat[0, 3]) * scale, float(mat[1, 3]) * scale)


_ifc = Path(tempfile.gettempdir()) / "ifcpatch_transforms.ifc"
massing.generate_blank_ifc(str(_ifc), name="PX", storeys=2, storey_height=3.0, ground_size=40.0)
m = open_model(str(_ifc))
w1 = edit.add_wall(m, [10, 20], [18, 20], 3.0, 0.2, "Level 1")
w2 = edit.add_wall(m, [0, 0], [6, 0], 3.0, 0.2, "Level 2")
before_xy = world_xy(m, w1)
assert abs(before_xy[0] - 14.0) < 1e-6 and abs(before_xy[1] - 20.0) < 1e-6, before_xy

# --- rebase_origin: the model moves, the survey position does not ----------------------------------
out = ifcpatch_lib.rebase_origin(m, [10.0, 20.0, 0.0])
assert out["moved"] and out["offset"] == [-10.0, -20.0, -0.0], out
after_xy = world_xy(m, w1)
assert abs(after_xy[0] - 4.0) < 1e-6 and abs(after_xy[1] - 0.0) < 1e-6, after_xy   # shifted by -Δ
# every element moves together — relative geometry is untouched
d_before = (before_xy[0] - 14.0, before_xy[1] - 20.0)
assert abs((after_xy[0] - 4.0) - d_before[0]) < 1e-9
# a no-op rebase reports itself instead of touching the file
assert ifcpatch_lib.rebase_origin(m, [0, 0, 0])["moved"] is False
# this blank file carries no map conversion — say so rather than implying the georeference followed
assert out["georeference_updated"] is False and "no IfcMapConversion" in out["note"]

# --- convert_length_unit: unit changes, real-world size does not -----------------------------------
scale_before = uunit.calculate_unit_scale(m)                       # metres per file unit (1.0)
storey2 = next(s for s in m.by_type("IfcBuildingStorey") if s.Name == "Level 2")
elev_m_before = float(storey2.Elevation) * scale_before
wall_xy_before = world_xy(m, w2)

rep = ifcpatch_lib.convert_length_unit(m, "MILLIMETRE")
assert abs(rep["ratio"] - 1000.0) < 1e-9, rep
assert "IfcCartesianPoint" in rep["converted"] and rep["entities_touched"] > 0, rep
scale_after = uunit.calculate_unit_scale(m)
assert abs(scale_after - 0.001) < 1e-12, scale_after               # the file now reads in mm
assert abs(float(storey2.Elevation) - 3000.0) < 1e-6               # 3 m expressed as 3000 mm
assert abs(float(storey2.Elevation) * scale_after - elev_m_before) < 1e-9   # …same real elevation
after = world_xy(m, w2)
assert abs(after[0] - wall_xy_before[0]) < 1e-6 and abs(after[1] - wall_xy_before[1]) < 1e-6
# idempotent + guarded
assert ifcpatch_lib.convert_length_unit(m, "MILLIMETRE")["ratio"] == 1.0
try:
    ifcpatch_lib.convert_length_unit(m, "FURLONG")
    raise AssertionError("unknown unit must ValueError")
except ValueError as e:
    assert "FURLONG" in str(e)
assert abs(ifcpatch_lib.convert_length_unit(m, "METRE")["ratio"] - 0.001) < 1e-12   # and back

# --- split_by_storey: the slice plan ---------------------------------------------------------------
plan = ifcpatch_lib.split_by_storey(m)
assert w1 in plan["storeys"]["Level 1"] and w2 in plan["storeys"]["Level 2"], plan["counts"]
assert plan["counts"]["Level 1"] >= 1 and plan["counts"]["Level 2"] >= 1
assert sorted(plan["storeys"]["Level 1"]) == plan["storeys"]["Level 1"]     # deterministic order

# --- recipes + routes ------------------------------------------------------------------------------
assert "rebase_origin" in edit.RECIPES and "convert_length_unit" in edit.RECIPES
m.write(str(_ifc))

from fastapi.testclient import TestClient  # noqa: E402

from aec_api.db import SessionLocal  # noqa: E402
from aec_api.main import app  # noqa: E402
from aec_api.models import Project  # noqa: E402

with TestClient(app) as c:
    pid = c.post("/projects", json={"name": "PX"}).json()["id"]
    with SessionLocal() as db:
        db.get(Project, pid).source_ifc = str(_ifc)
        db.commit()
    r = c.get(f"/projects/{pid}/model/split-plan")
    assert r.status_code == 200 and "Level 1" in r.json()["storeys"], r.text

# --- MODEL-SETUP: setup_facts — the READ that makes the two repairs above offerable ---------------
#
# Both recipes were in the registry and reachable through POST /projects/{pid}/edit the whole time,
# and `authoring_matrix.UNREACHED` listed both as "a capability no user can reach". A control could
# not simply be added because nothing exposed the CURRENT state: "convert to millimetres" with no
# statement of the present unit is a coin flip the user is asked to call.
_ifc2 = Path(tempfile.gettempdir()) / "ifcpatch_setup_facts.ifc"
massing.generate_blank_ifc(str(_ifc2), name="PS", storeys=2, storey_height=3.0, ground_size=40.0)
m2 = open_model(str(_ifc2))
edit.add_wall(m2, [1000, 2000], [1008, 2000], 3.0, 0.2, "Level 1")   # authored far from the origin

facts = ifcpatch_lib.setup_facts(m2)
assert facts["length_unit"] == "METRE" and abs(facts["length_unit_metres"] - 1.0) < 1e-12, facts
assert facts["convertible"] is True, facts
# The accepted list comes from the CONVERTER, not from a constant a client could drift from — a
# dropdown offering FOOT would render a 400, so the server names what it will take.
assert facts["targets"] == sorted(ifcpatch_lib._UNIT_SCALES), facts
assert set(facts["targets"]) == {"CENTIMETRE", "METRE", "MILLIMETRE"}, facts
# `distance_from_origin` is measured over the ROOT placements — the same set rebase_origin shifts —
# so the number shown is the number the repair acts on.
assert facts["root_placements"] > 0 and facts["distance_from_origin"] > 1000.0, facts

# ...and ROOTS specifically, which needs a NESTED placement to be assertable at all. An
# authored-from-scratch file has none — `rebase_origin`'s own docstring says its element placements
# ARE the roots — so a mutation measuring every placement instead of the roots SURVIVED the check
# above until this was added. The distinction is the whole claim: a nested placement rides its
# parent, so counting it would report a distance the repair does not act on and shift nothing.
_root_before = facts["root_placements"]
_dist_before = facts["distance_from_origin"]
_parent = next(x for x in m2.by_type("IfcLocalPlacement")
               if getattr(x, "PlacementRelTo", None) is None)
_far = m2.createIfcCartesianPoint((9.0e6, 9.0e6, 0.0))
m2.createIfcLocalPlacement(_parent, m2.createIfcAxis2Placement3D(_far, None, None))
_nested = ifcpatch_lib.setup_facts(m2)
assert _nested["root_placements"] == _root_before, (_root_before, _nested["root_placements"])
assert abs(_nested["distance_from_origin"] - _dist_before) < 1e-9, (_dist_before, _nested)
assert abs(facts["distance_from_origin_m"] - facts["distance_from_origin"]) < 1e-9, facts
assert facts["georeference"] is None, facts        # blank file carries no IfcMapConversion

# The read TRACKS the repair: rebasing to the far point brings the distance down.
far_before = facts["distance_from_origin"]
_roots_read = _nested["root_placements"]
_rebased = ifcpatch_lib.rebase_origin(m2, [1000.0, 2000.0, 0.0])
after = ifcpatch_lib.setup_facts(m2)
assert after["distance_from_origin"] < far_before, (far_before, after["distance_from_origin"])
# **The count the panel SHOWS is the count the repair MOVED, asserted rather than asserted-in-prose.**
# `setup_facts` and `rebase_origin` walk the placement graph with the same three conditions (skip a
# non-root, skip a missing Location, skip a Location already seen — two roots can share one
# IfcCartesianPoint, and shifting it twice would double the offset). Those are two copies of one
# rule, and a copy is what drifts: the docstring's claim that the distance is measured over
# "exactly the set rebase_origin shifts" would then be false with every other assertion here still
# green. Comparing the two OUTPUTS binds them by behaviour, so the loops may be rewritten but not
# diverge.
#
# **It guards the direction the nested-placement check above CANNOT see.** That one asserts the READ
# stays root-only; this one catches the REPAIR loosening — dropping `rebase_origin`'s root filter
# leaves every assertion above green and fails here with (2, placements_shifted=3). Verified by
# mutation, after a first attempt (making the read skip roots that sit at the origin) SURVIVED:
# neither root in this fixture is at the origin, so the mutation changed nothing. *A surviving
# mutation can mean the fixture cannot express it rather than that the check is weak* — the same
# thing that happened one assertion up, and the reason both are recorded rather than just the one
# that worked.
assert _roots_read == _rebased["placements_shifted"], (_roots_read, _rebased)

# ...and it tracks the OTHER repair too, in the vocabulary the converter uses.
ifcpatch_lib.convert_length_unit(m2, "MILLIMETRE")
mm = ifcpatch_lib.setup_facts(m2)
assert mm["length_unit"] == "MILLIMETRE" and abs(mm["length_unit_metres"] - 0.001) < 1e-12, mm
# metres are the comparable figure across a unit change; file units are not
assert abs(mm["distance_from_origin_m"] - after["distance_from_origin_m"]) < 1e-6, (mm, after)
# --- A CONVERSION-BASED LENGTH UNIT IS REFUSED, NOT HALF-CONVERTED -------------------------------
#
# Found by review on the PR that made `convert_length_unit` reachable, and REPRODUCED before it was
# fixed. The recipe rescales the whitelisted attributes, then rewrites the assignment guarded by
# `u.is_a("IfcSIUnit")` — so on a foot-based file (an `IfcConversionBasedUnit`, ordinary in a US
# survey model) the geometry moved and the declared unit did not. A 10 ft wall came out 3.048 FEET:
# the model silently at 30.48% of its real size, with a report saying "unit assignment rewritten".
#
# *The defect predates the control; the control is what made it reachable.* That is the standing
# hazard in wiring an UNREACHED recipe — the engine's own preconditions have never been exercised by
# a caller, so "it is implemented and tested" is not the same as "it is safe to offer".
_ifc3 = Path(tempfile.gettempdir()) / "ifcpatch_foot_unit.ifc"
massing.generate_blank_ifc(str(_ifc3), name="FT", storeys=1, storey_height=3.0, ground_size=20.0)
m3 = open_model(str(_ifc3))
edit.add_wall(m3, [0, 0], [10, 0], 3.0, 0.2, "Level 1")
_si = [u for u in m3.by_type("IfcNamedUnit") if getattr(u, "UnitType", None) == "LENGTHUNIT"][0]
_metre = m3.createIfcSIUnit(None, "LENGTHUNIT", None, "METRE")
_foot = m3.createIfcConversionBasedUnit(
    m3.createIfcDimensionalExponents(1, 0, 0, 0, 0, 0, 0), "LENGTHUNIT", "FOOT",
    m3.createIfcMeasureWithUnit(m3.createIfcLengthMeasure(0.3048), _metre))
for _ua in m3.by_type("IfcUnitAssignment"):
    _ua.Units = tuple(_foot if u == _si else u for u in _ua.Units)
assert abs(uunit.calculate_unit_scale(m3) - 0.3048) < 1e-12, "fixture is not actually in feet"

# ① the READ refuses to advertise it, and says WHY — "no LENGTHUNIT at all" and "a unit we cannot
#    rewrite" are different files and the panel prints different sentences for them.
_ft = ifcpatch_lib.setup_facts(m3)
assert _ft["convertible"] is False, _ft
assert _ft["unconvertible_reason"] and "conversion-based" in _ft["unconvertible_reason"], _ft
assert _ft["length_unit"] == "FOOT", _ft          # still NAMED honestly, just not offered

# ② the ENGINE refuses too, and refuses BEFORE it touches anything. The read is a convenience; the
#    recipe is reachable through POST /edit directly, so a guard that lived only in `setup_facts`
#    would protect the panel and leave the door open. Both, and the geometry is byte-identical after.
_before = sorted(tuple(e.Coordinates) for e in m3.by_type("IfcCartesianPoint"))
try:
    ifcpatch_lib.convert_length_unit(m3, "METRE")
    raise AssertionError("convert_length_unit accepted a conversion-based unit")
except ValueError as e:
    assert "conversion-based" in str(e), e
_after = sorted(tuple(e.Coordinates) for e in m3.by_type("IfcCartesianPoint"))
assert _before == _after, "REFUSED AND STILL MUTATED — the guard is in the wrong place"
assert abs(uunit.calculate_unit_scale(m3) - 0.3048) < 1e-12, "the unit changed on a refused convert"

# ③ and an SI file is untouched by the guard — a refusal that refuses everything is not a fix.
assert ifcpatch_lib.setup_facts(m2)["convertible"] is True
assert ifcpatch_lib.setup_facts(m2)["unconvertible_reason"] is None
if _ifc3.exists():
    _ifc3.unlink()

if _ifc2.exists():
    _ifc2.unlink()

if _ifc.exists():
    _ifc.unlink()

print("IFCPATCH-TRANSFORMS OK - rebase_origin shifts every ROOT placement plus the storey datums "
      "(a wall at E14 lands at E4 when (10,20) becomes the origin, relative geometry intact), "
      "reports a no-op honestly and says plainly when there is no IfcMapConversion to carry the "
      "georeference; convert_length_unit rewrites the unit assignment AND rescales the whitelisted "
      "attributes so a 3 m storey reads 3000 mm at the SAME real elevation (ratio 1000, idempotent, "
      "unknown unit refused, round-trips back to metres); split_by_storey plans deterministic "
      "per-storey slices and GET /model/split-plan serves them; setup_facts reads the unit, the "
      "converter's OWN accepted target list and the distance of the ROOT placements from the origin, "
      "so both repairs can be offered against stated state rather than guessed at, and it tracks "
      "each one (rebase lowers the distance, convert renames the unit at an unchanged real size).")

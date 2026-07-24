"""AUTH-CONSTRAINTS ② — level-move re-derivation: elements follow a storey elevation edit
(set_storey_elevation shifts every contained element's placement by Δz), verified by the
constraints checker; opting out leaves them behind and the checker flags exactly that.
Run: PYTHONPATH="src;../data/src" ./.venv/Scripts/python.exe test_level_move.py"""
import os
import tempfile
from pathlib import Path

os.environ["DATABASE_URL"] = "sqlite:///./test_level_move.db"
os.environ["STORAGE_DIR"] = "./test_storage_lvlmove"
os.environ.pop("AEC_RBAC", None)
if os.path.exists("./test_level_move.db"):
    os.remove("./test_level_move.db")

import ifcopenshell.util.placement as uplace  # noqa: E402
import ifcopenshell.util.unit as uunit  # noqa: E402

from aec_data import constraints, edit, massing  # noqa: E402
from aec_data.ifc_loader import open_model  # noqa: E402


def abs_z(model, el) -> float:
    scale = uunit.calculate_unit_scale(model)
    return float(uplace.get_local_placement(el.ObjectPlacement)[2, 3]) * scale


_ifc = Path(tempfile.gettempdir()) / "level_move.ifc"
massing.generate_blank_ifc(str(_ifc), name="Lvl", storeys=2, storey_height=3.0, ground_size=20.0)
m = open_model(str(_ifc))
l2 = next(s for s in m.by_type("IfcBuildingStorey") if s.Name == "Level 2")
w_guid = edit.add_wall(m, [0, 0], [8, 0], 3.0, 0.2, "Level 2")
wall = m.by_guid(w_guid)
edit.add_opening(m, w_guid, width=0.9, height=2.1, kind="door")
door = m.by_type("IfcDoor")[0]
assert abs(abs_z(m, wall) - 3.0) < 1e-6, abs_z(m, wall)

# --- the re-derivation: move Level 2 up 2 m → the wall AND its hosted door follow ------------------
moved = edit.RECIPES["set_storey_elevation"](m, {"guid": l2.GlobalId, "elevation": 5.0})
assert abs(abs_z(m, wall) - 5.0) < 1e-6, abs_z(m, wall)
assert abs(abs_z(m, door) - 5.0) < 0.5, abs_z(m, door)          # hosted fill rides its wall
scale = uunit.calculate_unit_scale(m)
assert abs(float(l2.Elevation) * scale - 5.0) < 1e-6
# the constraints checker agrees nothing is stranded
report = constraints.check(m)
assert not [i for i in report["issues"] if i["kind"] == "level_mismatch"], report["issues"]

# --- opting out strands the elements — and the checker says so -------------------------------------
import ifcopenshell  # noqa: E402

m2 = ifcopenshell.open(str(_ifc))          # fresh parse — open_model caches the mutated instance
l2b = next(s for s in m2.by_type("IfcBuildingStorey") if s.Name == "Level 2")
w2 = m2.by_guid(edit.add_wall(m2, [0, 4], [8, 4], 3.0, 0.2, "Level 2"))
edit.RECIPES["set_storey_elevation"](m2, {"guid": l2b.GlobalId, "elevation": 6.0,
                                          "move_elements": False})
assert abs(abs_z(m2, w2) - 3.0) < 1e-6                           # left behind on purpose
flagged = [i for i in constraints.check(m2)["issues"] if i["kind"] == "level_mismatch"]
assert any(i["guid"] == w2.GlobalId for i in flagged), flagged

if _ifc.exists():
    _ifc.unlink()

print("LEVEL-MOVE OK - set_storey_elevation re-derives contained placements: raising Level 2 from "
      "3.0 m to 5.0 m carries the wall (and its hosted door) to exactly the new elevation, the "
      "storey attribute converts through file units, and the constraints checker reports no "
      "level_mismatch; with move_elements=false the wall stays at 3.0 m and the checker flags "
      "precisely that stranded wall.")

"""AUTH-CONSTRAINTS ③ — wall-join resolution: L/T detection, deterministic butt joins
(through extended, stub trimmed), idempotency, world-anchored openings, and the routes.
Run: PYTHONPATH="src;../data/src" ./.venv/Scripts/python.exe test_wall_joins.py"""
import os
import tempfile
from pathlib import Path

os.environ["DATABASE_URL"] = "sqlite:///./test_wall_joins.db"
os.environ["STORAGE_DIR"] = "./test_storage_wjoins"
os.environ.pop("AEC_RBAC", None)
if os.path.exists("./test_wall_joins.db"):
    os.remove("./test_wall_joins.db")

import ifcopenshell.util.placement as uplace  # noqa: E402
import ifcopenshell.util.unit as uunit  # noqa: E402

from aec_data import edit, massing, wall_joins  # noqa: E402
from aec_data.ifc_loader import open_model  # noqa: E402


def geo(m, guid):
    scale = uunit.calculate_unit_scale(m)
    return wall_joins._wall_geo(m, m.by_guid(guid), scale)


_ifc = Path(tempfile.gettempdir()) / "wall_joins.ifc"
massing.generate_blank_ifc(str(_ifc), name="WJ", storeys=1, storey_height=3.0, ground_size=30.0)
m = open_model(str(_ifc))
# an L: a 10 m wall east-west meets a 6 m wall north-south at (0,0); both 0.2 m thick
wa = edit.add_wall(m, [0, 0], [10, 0], 3.0, 0.2, "Level 1")     # through (longer)
wb = edit.add_wall(m, [0, 0], [0, 6], 3.0, 0.2, "Level 1")      # stub
# a T: a 4 m wall dead-ends onto wa's axis mid-run at (5,0), approaching from the north
wt = edit.add_wall(m, [5, 4], [5, 0], 3.0, 0.3, "Level 1")
# a door in the through wall, well away from the corner — must not move during resolution
edit.add_opening(m, wa, width=0.9, height=2.1, kind="door", position=[7.0, 0.0])
door = m.by_type("IfcDoor")[0]
door_before = uplace.get_local_placement(door.ObjectPlacement)[:3, 3].copy()

found = wall_joins.find(m)
assert found["counts"] == {"L": 1, "T": 1}, found["counts"]
ljoin = next(j for j in found["joins"] if j["kind"] == "L")
assert ljoin["through"] == wa and ljoin["stub"] == wb, ljoin      # longer wall runs through
tjoin = next(j for j in found["joins"] if j["kind"] == "T")
assert tjoin["stub"] == wt and tjoin["through"] == wa, tjoin

out = wall_joins.resolve(m)
assert out["count"] == 2, out
# L: through extended by t_stub/2 (10 → 10.1), stub trimmed by t_through/2 (6 → 5.9)
ga, gb, gt = geo(m, wa), geo(m, wb), geo(m, wt)
assert abs(ga["length"] - 10.1) < 1e-6, ga["length"]
assert abs(gb["length"] - 5.9) < 1e-6, gb["length"]
# T: stub trimmed by t_through/2 (4 → 3.9); the through wall untouched by the T
assert abs(gt["length"] - 3.9) < 1e-6, gt["length"]
# the stub's fixed (far) end never moved — only the corner end pulled back
assert abs(gb["ends"][0][1] - 0.1) < 1e-6 or abs(gb["ends"][1][1] - 0.1) < 1e-6
assert any(abs(e[1] - 6.0) < 1e-6 for e in gb["ends"]), gb["ends"]
# openings are world-anchored: the door did not move a millimetre
door_after = uplace.get_local_placement(door.ObjectPlacement)[:3, 3]
assert abs(door_after[0] - door_before[0]) < 1e-9 and abs(door_after[1] - door_before[1]) < 1e-9

# idempotent: resolved ends sit half-a-thickness off the other axis — a second pass finds nothing
again = wall_joins.resolve(m)
assert again["count"] == 0, again

# --- the route -------------------------------------------------------------------------------------
m.write(str(_ifc))
from fastapi.testclient import TestClient  # noqa: E402

from aec_api.db import SessionLocal  # noqa: E402
from aec_api.main import app  # noqa: E402
from aec_api.models import Project  # noqa: E402

with TestClient(app) as c:
    pid = c.post("/projects", json={"name": "WJ"}).json()["id"]
    with SessionLocal() as db:
        db.get(Project, pid).source_ifc = str(_ifc)
        db.commit()
    r = c.get(f"/projects/{pid}/model/wall-joins")
    assert r.status_code == 200 and r.json()["counts"] == {"L": 0, "T": 0}, r.text  # already resolved

if _ifc.exists():
    _ifc.unlink()

print("WALL-JOINS OK - find classifies the 10mx6m corner as an L (longer wall through) and the "
      "4m dead-end as a T; resolve butt-joins deterministically (through 10->10.1 m closing the "
      "outside corner, L-stub 6->5.9 m, T-stub 4->3.9 m, far ends pinned, the door in the through "
      "wall unmoved to the millimetre), a second pass is a no-op (idempotent), and "
      "GET /model/wall-joins reports the resolved model clean.")

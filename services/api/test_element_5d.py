"""5D-BIND: GUID-keyed cost (+carbon) rows off the live index — hand-computed + reprice-on-edit
semantics (a changed quantity changes the row). Run: PYTHONPATH=src ./.venv/Scripts/python.exe test_element_5d.py"""
import os

os.environ.setdefault("DATABASE_URL", "sqlite:///./_el5d_test.db")
os.environ.setdefault("STORAGE_DIR", "./_storage_el5d")
os.environ.pop("AEC_RBAC", None)
if os.path.exists("./_el5d_test.db"):
    os.remove("./_el5d_test.db")

from aec_api import element_5d as E5  # noqa: E402


def el(guid, name, cls, storey, qtos):
    return {"guid": guid, "ifc_class": cls, "name": name, "storey": storey,
            "type_name": "", "psets": {}, "qtos": qtos}


# hand-computed:
#  W1 concrete wall  2 m2 area  × $160/m2 = $320 ; carbon: wall factor is per m3 → NO match on area? —
#     concrete factor is 300/m3, quantity family is m2 → carbon None (honest mismatch)
#  S1 slab 1.5 m3    × $550/m3 = $825    ; "Concrete Slab" matches concrete 300/m3 → 450 kg
#  D1 door count 1   × $1200   = $1200   ; no material match → carbon None
#  P1 pipe 10 m      × $180/m  = $1800   (length basis via Qto Length)
#  X1 IfcWall with volume-only qto → wall basis is AREA → family mismatch → NOT priced
idx = {
    "W1": el("W1", "Concrete Wall", "IfcWall", "L1", {"Q": {"NetArea": 2.0}}),
    "S1": el("S1", "Concrete Slab", "IfcSlab", "L1", {"Q": {"NetVolume": 1.5}}),
    "D1": el("D1", "Door 36in", "IfcDoor", "L2", {"Q": {}}),
    "P1": el("P1", "CHW Pipe", "IfcPipeSegment", "L2", {"Q": {"Length": 10.0}}),
    "X1": el("X1", "Odd Wall", "IfcWall", "L1", {"Q": {"NetVolume": 3.0}}),
}
r = E5.element_costs(idx)
assert r["element_count"] == 5 and r["priced"] == 4, (r["element_count"], r["priced"])
assert r["total_cost"] == 320.0 + 825.0 + 1200.0 + 1800.0, r["total_cost"]
rows = {x["guid"]: x for x in r["top_cost"]}
assert rows["P1"]["cost"] == 1800.0 and rows["P1"]["basis"] == "length"
assert rows["D1"]["cost"] == 1200.0 and rows["D1"]["quantity"] == 1.0
assert "X1" not in rows, "area-basis wall with volume-only qto must not be guessed"
# carbon rides the row only when BOTH material and unit family match
assert rows["S1"]["carbon_kgco2e"] == 450.0 and rows["S1"]["carbon_category"] == "concrete"
assert rows["W1"]["carbon_kgco2e"] is None, "wall carbon factor is per m3; area quantity → no guess"
assert r["carbon_matched"] == 1 and r["total_carbon_kgco2e"] == 450.0
assert r["by_storey"]["L1"] == 320.0 + 825.0 and r["by_storey"]["L2"] == 3000.0, r["by_storey"]

# reprice-on-edit: double the slab volume → the SAME call over the updated index doubles that row
idx["S1"]["qtos"]["Q"]["NetVolume"] = 3.0
r2 = E5.element_costs(idx)
s1 = next(x for x in r2["top_cost"] if x["guid"] == "S1")
assert s1["cost"] == 1650.0 and s1["carbon_kgco2e"] == 900.0, s1
assert r2["total_cost"] == r["total_cost"] + 825.0, "only the edited element repriced"

# endpoint: 404 until a model index exists
from fastapi.testclient import TestClient  # noqa: E402

from aec_api.main import app  # noqa: E402

with TestClient(app) as c:
    pid = c.post("/projects", json={"name": "5D"}).json()["id"]
    assert c.get(f"/projects/{pid}/5d/element-costs").status_code == 404

print("5D-BIND OK - GUID-keyed rows off the index: wall 2m2x$160=320, slab 1.5m3x$550=825 (+450 kg "
      "carbon on the same row), door $1200, pipe 10m x$180=1800; the volume-only wall is excluded "
      "(basis mismatch, never guessed) and wall carbon stays None (m3 factor vs m2 qty); doubling the "
      "slab volume reprices exactly that row (cost 1650, carbon 900) — edit->republish->reprice with "
      "nothing to resync; endpoint 404s without a model.")

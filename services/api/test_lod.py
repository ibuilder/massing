"""LOD (A2): target matrix register + achieved-LOD assessment inferred from LOIN facets.
Run: PYTHONPATH=src ./.venv/Scripts/python.exe test_lod.py"""
import os

os.environ["DATABASE_URL"] = "sqlite:///./test_lod.db"
os.environ["STORAGE_DIR"] = "./test_storage_lod"
os.environ.pop("AEC_RBAC", None)
for _f in ("./test_lod.db",):
    if os.path.exists(_f):
        os.remove(_f)

from fastapi.testclient import TestClient  # noqa: E402

from aec_api import lod, reports  # noqa: E402
from aec_api.db import SessionLocal  # noqa: E402
from aec_api.main import app  # noqa: E402

with TestClient(app) as c:
    pid = c.post("/projects", json={"name": "P"}).json()["id"]

    # --- empty register -> stage defaults --------------------------------------------------------
    m0 = c.get(f"/projects/{pid}/lod/matrix").json()
    assert m0["using_default"] is True and len(m0["default"]) == 5, m0
    assert m0["targets"] == [], m0

    # --- author a target -> register wins --------------------------------------------------------
    r = c.post(f"/projects/{pid}/modules/lod_target", json={"data": {
        "element_category": "Walls", "discipline": "Architectural",
        "phase": "Design Development", "target_lod": "LOD 300"}})
    assert r.status_code == 201, r.text[:160]
    m1 = c.get(f"/projects/{pid}/lod/matrix").json()
    assert m1["using_default"] is False and any(t["target_lod"] == "LOD 300" for t in m1["targets"]), m1

    # --- assessment with no model -> targets only ------------------------------------------------
    a0 = c.get(f"/projects/{pid}/lod/assessment").json()
    assert a0["model_scored"] is False and a0["elements"] == 0, a0

    # --- achieved-LOD inference from a synthetic index (engine unit) ------------------------------
    idx = {
        "g1": {"ifc_class": "IfcWall"},                                       # geometry only -> LOD 100
        "g2": {"ifc_class": "IfcWall", "type_name": "W1",                     # 5 facets      -> LOD 400
               "psets": {"Pset_WallCommon": {"a": 1}}, "qtos": {"Q": {"v": 1}}},
        "g3": {"ifc_class": "IfcDuctSegment", "type_name": "D1",              # 4 facets      -> LOD 350
               "psets": {"P": {"a": 1}}},
    }
    a = lod.assess(SessionLocal(), pid, idx)
    assert a["model_scored"] is True and a["elements"] == 3, a
    assert a["distribution"]["LOD 100"] == 1, a["distribution"]
    assert a["distribution"]["LOD 400"] == 1, a["distribution"]
    assert a["distribution"]["LOD 350"] == 1, a["distribution"]
    # per-discipline rollup keys elements by their IFC-class discipline
    assert sum(d["elements"] for d in a["by_discipline"]) == 3, a["by_discipline"]
    discs = {d["discipline"] for d in a["by_discipline"]}
    assert "Mechanical" in discs, discs                          # IfcDuctSegment -> Mechanical
    assert len(discs) == 2, discs                                # walls (one discipline) + ducts (another)
    # cap: no element can infer past LOD 400
    assert a["distribution"]["LOD 500"] == 0, a["distribution"]

    # --- report + PDF ----------------------------------------------------------------------------
    assert "lod" in {x["id"] for x in reports.catalog()}, "lod missing from catalog"
    rep = c.get(f"/projects/{pid}/reports/lod.pdf")
    assert rep.status_code == 200 and rep.content[:4] == b"%PDF", rep.status_code

print("LOD OK - empty register -> 5 stage defaults; authored target overrides; assessment w/o model = "
      "targets only; achieved LOD inferred from LOIN facets (1 facet->100, 4->350, 5->400, capped at 400); "
      "per-discipline rollup by IFC class (IfcDuctSegment->Mechanical); report PDF served")

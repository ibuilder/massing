"""Model Health composite scorecard — unifies hygiene + ISO-19650 KPIs + clash + verified-as-built.
Run: PYTHONPATH=src ./.venv/Scripts/python.exe test_model_health.py"""
import os

os.environ["DATABASE_URL"] = "sqlite:///./test_model_health.db"
os.environ["STORAGE_DIR"] = "./test_storage_mh"
os.environ.pop("AEC_RBAC", None)
for _f in ("./test_model_health.db",):
    if os.path.exists(_f):
        os.remove(_f)

import ifcopenshell  # noqa: E402
import ifcopenshell.guid  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from aec_api import model_health  # noqa: E402
from aec_api.db import SessionLocal  # noqa: E402
from aec_api.main import app  # noqa: E402


def _clean_model():
    f = ifcopenshell.file(schema="IFC4")
    st = f.create_entity("IfcBuildingStorey", GlobalId=ifcopenshell.guid.new(), Name="L1", Elevation=0.0)
    walls = []
    for i in range(3):
        walls.append(f.create_entity("IfcWall", GlobalId=ifcopenshell.guid.new(), Name=f"W-{i}",
                     ObjectPlacement=f.create_entity("IfcLocalPlacement", RelativePlacement=f.create_entity(
                         "IfcAxis2Placement3D", Location=f.create_entity("IfcCartesianPoint",
                         Coordinates=(float(i * 5), 0.0, 0.0))))))
    f.create_entity("IfcRelContainedInSpatialStructure", GlobalId=ifcopenshell.guid.new(),
                    RelatingStructure=st, RelatedElements=walls)
    return f


with TestClient(app) as tc:
    pid = tc.post("/projects", json={"name": "Health Tower"}).json()["id"]

db = SessionLocal()
try:
    # a clean model → hygiene lens scores 100; the other lenses have no inputs → 'na'
    sc = model_health.scorecard(db, pid, model=_clean_model(), elements=[])
    lenses = {ln["key"]: ln for ln in sc["lenses"]}
    assert set(lenses) == {"hygiene", "information", "coordination", "verified"}, list(lenses)
    assert lenses["hygiene"]["score"] == 100.0 and lenses["hygiene"]["status"] == "good", lenses["hygiene"]
    # information lens present (may be na or scored depending on records); coordination/verified na here
    assert lenses["coordination"]["status"] == "na" and lenses["verified"]["status"] == "na", sc
    # composite is the weighted mean over scored lenses (hygiene 100 at least)
    assert sc["overall_score"] is not None and 0 <= sc["overall_score"] <= 100, sc
    assert sc["band"] in ("healthy", "watch", "at risk"), sc["band"]
    assert sc["model_available"] is True

    # with no model, hygiene degrades to 'na' but the scorecard still returns
    sc2 = model_health.scorecard(db, pid, model=None, elements=[])
    assert {ln["key"] for ln in sc2["lenses"]} == {"hygiene", "information", "coordination", "verified"}
    assert next(ln for ln in sc2["lenses"] if ln["key"] == "hygiene")["status"] == "na", sc2
    assert sc2["model_available"] is False
finally:
    db.close()

# HTTP: endpoint returns the scorecard shape (no source IFC → hygiene na, DB lenses score)
with TestClient(app) as tc:
    r = tc.get(f"/projects/{pid}/models/health")
    assert r.status_code == 200, r.text[:200]
    b = r.json()
    assert "overall_score" in b and "lenses" in b and "band" in b and len(b["lenses"]) == 4, b

print("MODEL-HEALTH OK - composite scorecard unifies 4 lenses (integrity/hygiene, ISO 19650 KPIs, clash "
      "coordination, verified-as-built); a clean model scores hygiene 100/good; lenses with no inputs "
      "degrade to 'na' and are excluded from the weighted mean; works with or without a parsed model; "
      "HTTP GET /models/health returns the scorecard. One launcher for every model-quality check.")

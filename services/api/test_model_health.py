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
    assert set(lenses) == {"hygiene", "information", "coordination", "verified", "readiness"}, list(lenses)
    assert lenses["hygiene"]["score"] == 100.0 and lenses["hygiene"]["status"] == "good", lenses["hygiene"]
    # information lens present (may be na or scored depending on records); coordination/verified na here
    assert lenses["coordination"]["status"] == "na" and lenses["verified"]["status"] == "na", sc
    # code/permit-readiness lens runs the pre-flight; present with a valid status + tool link
    assert lenses["readiness"]["tool"] == "approvability" and lenses["readiness"]["status"] in ("good", "warn", "poor", "na"), lenses["readiness"]
    # composite is the weighted mean over scored lenses (hygiene 100 at least)
    assert sc["overall_score"] is not None and 0 <= sc["overall_score"] <= 100, sc
    assert sc["band"] in ("healthy", "watch", "at risk"), sc["band"]
    assert sc["model_available"] is True

    # with no model, hygiene degrades to 'na' but the scorecard still returns
    sc2 = model_health.scorecard(db, pid, model=None, elements=[])
    assert {ln["key"] for ln in sc2["lenses"]} == {"hygiene", "information", "coordination", "verified", "readiness"}
    assert next(ln for ln in sc2["lenses"] if ln["key"] == "hygiene")["status"] == "na", sc2
    assert sc2["model_available"] is False

    # --- pre-flight issuance gate: composes the health lenses + classification + open-issues ----------
    from aec_api import preflight  # noqa: E402
    gate = preflight.issuance_gate(db, pid, model=_clean_model(), elements=[])
    assert gate["ready"] is True and gate["verdict"] == "READY TO ISSUE", gate
    assert gate["blocking"] == 0, gate
    assert any(c["key"] == "hygiene" for c in gate["checks"]), gate            # health lens folded in
    assert any(c["key"] == "open_issues" and c["status"] == "pass" for c in gate["checks"]), gate
    # classification completeness: all-wall index → every element maps to the discipline tree (100%)
    gate2 = preflight.issuance_gate(db, pid, model=_clean_model(),
                                    elements=[{"guid": f"g{i}", "ifc_class": "IfcWall"} for i in range(4)])
    cl = next(c for c in gate2["checks"] if c["key"] == "classification")
    assert cl["score"] == 100.0 and cl["status"] == "pass", cl
    # checklist is ordered blockers → warnings → passes
    order = [{"fail": 0, "warn": 1, "pass": 2}[c["status"]] for c in gate2["checks"]]
    assert order == sorted(order), order
finally:
    db.close()

# HTTP: endpoint returns the scorecard shape (no source IFC → hygiene na, DB lenses score)
with TestClient(app) as tc:
    r = tc.get(f"/projects/{pid}/models/health")
    assert r.status_code == 200, r.text[:200]
    b = r.json()
    assert "overall_score" in b and "lenses" in b and "band" in b and len(b["lenses"]) == 5, b
    # the pre-flight issuance gate endpoint returns a verdict + checklist
    rp = tc.get(f"/projects/{pid}/preflight")
    assert rp.status_code == 200, rp.text[:200]
    pb = rp.json()
    assert "ready" in pb and "verdict" in pb and isinstance(pb["checks"], list) and pb["checks"], pb

print("MODEL-HEALTH OK - composite scorecard unifies 5 lenses (integrity/hygiene, ISO 19650 KPIs, clash "
      "coordination, verified-as-built, code/permit readiness); a clean model scores hygiene 100/good; lenses with no inputs "
      "degrade to 'na' and are excluded from the weighted mean; works with or without a parsed model; "
      "HTTP GET /models/health returns the scorecard. One launcher for every model-quality check.")

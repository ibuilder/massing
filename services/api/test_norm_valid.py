"""NORM-VALID — the normative openBIM conformance gauntlet (header + schema + IFC implementer-agreement
rules). Engine over a clean model (all pass/warn, none fail) + injected violations (bad GlobalId, a
second IfcProject) → fail, plus the /models/norm-valid route.
Run: PYTHONPATH="src;../data/src" ./.venv/Scripts/python.exe test_norm_valid.py"""
import os

TMP = os.path.join(os.path.dirname(__file__), "_normvalid.ifc")

from aec_data import massing, norm_valid  # noqa: E402
from aec_data.ifc_loader import open_model  # noqa: E402

# a clean blank model should conform — nothing FAILS (warnings for header/context are acceptable)
massing.generate_blank_ifc(TMP, name="NormValid", storeys=2, storey_height=3.5, ground_size=20.0)
m = open_model(TMP)
res = norm_valid.validate(m)
assert res["schema"] == "IFC4", res["schema"]
assert res["passed"] is True, res["summary"]
by_id = {c["id"]: c for c in res["checks"]}
# the core normative rules pass on a well-formed model
for cid in ("header.schema", "project.single", "project.units", "guid.format", "guid.unique"):
    assert by_id[cid]["status"] == "pass", (cid, by_id[cid])
assert res["summary"]["fail"] == 0 and res["summary"]["pass"] >= 5, res["summary"]
# STEP-syntax + bSDD/classification lanes are present (warn on an unclassified blank model, never fail)
assert "header.file_name" in by_id and by_id["header.file_name"]["status"] in ("pass", "warn"), by_id.get("header.file_name")
assert "classification.coverage" in by_id, list(by_id)
assert by_id["classification.coverage"]["status"] in ("pass", "warn"), by_id["classification.coverage"]
assert "%" in by_id["classification.coverage"]["note"], by_id["classification.coverage"]["note"]

# --- inject violations: a bad GlobalId + a duplicate GlobalId + a second IfcProject → fails ---------
import ifcopenshell  # noqa: E402

bad = ifcopenshell.open(TMP)
walls = bad.by_type("IfcWall") or bad.by_type("IfcSlab")
walls[0].GlobalId = "not-a-valid-guid"                 # 13 chars, illegal alphabet → guid.format fail
# duplicate a GlobalId across two roots → guid.unique fail
roots = bad.by_type("IfcBuildingStorey")
if len(roots) >= 2:
    roots[1].GlobalId = roots[0].GlobalId
bad.create_entity("IfcProject", GlobalId=ifcopenshell.guid.new(), Name="Second")  # project.single fail
res2 = norm_valid.validate(bad)
b = {c["id"]: c for c in res2["checks"]}
assert res2["passed"] is False, res2["summary"]
assert b["guid.format"]["status"] == "fail" and b["guid.format"]["count"] >= 1, b["guid.format"]
assert b["guid.unique"]["status"] == "fail", b["guid.unique"]
assert b["project.single"]["status"] == "fail" and b["project.single"]["count"] == 2, b["project.single"]
assert res2["summary"]["fail"] >= 3, res2["summary"]

# --- route -----------------------------------------------------------------------------------------
os.environ["DATABASE_URL"] = "sqlite:///./test_norm_valid.db"
os.environ["STORAGE_DIR"] = "./test_storage_normvalid"
os.environ.pop("AEC_RBAC", None)
if os.path.exists("./test_norm_valid.db"):
    os.remove("./test_norm_valid.db")
from fastapi.testclient import TestClient  # noqa: E402

from aec_api.db import SessionLocal  # noqa: E402
from aec_api.main import app  # noqa: E402
from aec_api.models import Project  # noqa: E402

with TestClient(app) as c:
    pid = c.post("/projects", json={"name": "NV"}).json()["id"]
    assert c.get(f"/projects/{pid}/models/norm-valid").status_code == 409   # no source IFC
    with SessionLocal() as db:
        db.get(Project, pid).source_ifc = TMP
        db.commit()
    r = c.get(f"/projects/{pid}/models/norm-valid")
    assert r.status_code == 200, r.status_code
    j = r.json()
    assert j["passed"] is True and j["schema"] == "IFC4" and j["summary"]["fail"] == 0, j["summary"]
    assert any(ck["id"] == "guid.format" for ck in j["checks"])

if os.path.exists(TMP):
    os.remove(TMP)

print("NORM-VALID OK - a clean IFC4 model passes the gauntlet (recognised schema, single IfcProject with "
      "units + context, valid+unique 22-char GlobalIds, no fails); injecting an illegal GlobalId + a "
      "duplicate GlobalId + a second IfcProject flips passed=False with guid.format/guid.unique/"
      "project.single all failing; the /models/norm-valid route 409s without a source IFC and returns the "
      "structured pass/warn/fail report otherwise.")

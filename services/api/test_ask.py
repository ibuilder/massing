"""Ask-the-model: a plain-English question is grounded in the property-index snapshot (counts by
class/storey, totals); degrades to returning the snapshot when no AI key is set.
Run: PYTHONPATH=src ./.venv/Scripts/python.exe test_ask.py"""
import json
import os

os.environ["DATABASE_URL"] = "sqlite:///./test_ask.db"
os.environ["STORAGE_DIR"] = "./test_storage_ask"
os.environ.pop("AEC_RBAC", None)
os.environ.pop("ANTHROPIC_API_KEY", None)        # ensure AI is OFF → snapshot path
for _f in ("./test_ask.db",):
    if os.path.exists(_f):
        os.remove(_f)

from fastapi.testclient import TestClient  # noqa: E402

from aec_api.main import app  # noqa: E402

PROPS = {
    "schema": "demo", "project": {"name": "Tower"},
    "counts": {"IfcWall": 2, "IfcDoor": 1}, "facets": {"storey": ["L1", "L2"]},
    "elements": [
        {"guid": "g1", "ifc_class": "IfcWall", "storey": "L1", "psets": {"Pset_WallCommon": {}}},
        {"guid": "g2", "ifc_class": "IfcWall", "storey": "L2", "psets": {"Pset_WallCommon": {}}},
        {"guid": "g3", "ifc_class": "IfcDoor", "storey": "L1", "psets": {"Pset_DoorCommon": {}}},
    ],
}

with TestClient(app) as c:
    pid = c.post("/projects", json={"name": "Tower"}).json()["id"]
    # ask before an index exists -> 404
    assert c.post(f"/projects/{pid}/ask", json={"question": "how many walls?"}).status_code == 404
    # upload the property index
    up = c.post(f"/projects/{pid}/properties/index",
                files={"file": ("props.json", json.dumps(PROPS).encode(), "application/json")})
    assert up.status_code == 200 and up.json()["loaded"] == 3, up.text[:160]

    # empty question -> 422
    assert c.post(f"/projects/{pid}/ask", json={"question": "  "}).status_code == 422

    r = c.post(f"/projects/{pid}/ask", json={"question": "How many walls are there?"})
    assert r.status_code == 200, r.text[:160]
    body = r.json()
    assert body["source"] == "disabled", body.get("source")        # no AI key → snapshot path
    snap = body["snapshot"]
    assert snap["total_elements"] == 3, snap
    assert snap["counts_by_class"]["IfcWall"] == 2 and snap["counts_by_class"]["IfcDoor"] == 1, snap["counts_by_class"]
    assert snap["counts_by_storey"]["L1"] == 2 and snap["counts_by_storey"]["L2"] == 1, snap["counts_by_storey"]
    assert "Pset_WallCommon" in snap["property_sets"], snap["property_sets"]

print("ASK OK - question grounded in the model snapshot (3 elements; 2 walls/1 door; storeys L1=2 L2=1; "
      "Psets surfaced); 404 before index, 422 on empty; degrades to snapshot without an AI key")

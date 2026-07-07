"""Model analytics query (D1) + data export (D2): group-by/aggregate + CSV/JSON-LD over the index.
Run: PYTHONPATH=src ./.venv/Scripts/python.exe test_model_query.py"""
import os

os.environ["DATABASE_URL"] = "sqlite:///./test_model_query.db"
os.environ["STORAGE_DIR"] = "./test_storage_model_query"
os.environ.pop("AEC_RBAC", None)
for _f in ("./test_model_query.db",):
    if os.path.exists(_f):
        os.remove(_f)

from fastapi.testclient import TestClient  # noqa: E402

from aec_api import model_query  # noqa: E402
from aec_api.main import app  # noqa: E402

IDX = {
    "g1": {"ifc_class": "IfcWall", "type_name": "W1", "storey": "L1",
           "qtos": {"Qto_WallBaseQuantities": {"NetVolume": 5.0}}},
    "g2": {"ifc_class": "IfcWall", "type_name": "W2", "storey": "L1",
           "qtos": {"Qto_WallBaseQuantities": {"NetVolume": 3.0}}},
    "g3": {"ifc_class": "IfcSlab", "type_name": "S1", "storey": "L2",
           "qtos": {"Qto_SlabBaseQuantities": {"NetVolume": 10.0}}},
}

# --- D1: query engine -----------------------------------------------------------------------------
q = model_query.query(IDX, group_by="ifc_class", agg="count")
assert q["matched"] == 3 and q["rows"][0] == {"group": "IfcWall", "value": 2, "count": 2}, q["rows"]
qs = model_query.query(IDX, group_by="ifc_class", agg="sum", quantity="NetVolume")
vols = {r["group"]: r["value"] for r in qs["rows"]}
assert vols == {"IfcWall": 8.0, "IfcSlab": 10.0}, vols
# filtered
qf = model_query.query(IDX, group_by="storey", agg="count", filters={"ifc_class": "IfcWall"})
assert qf["matched"] == 2 and qf["rows"][0]["group"] == "L1", qf
# saved views + no-model
assert {v["id"] for v in model_query.saved_views()} >= {"count_by_discipline", "count_by_class"}
assert model_query.query(None)["model_scored"] is False

# --- D2: export -----------------------------------------------------------------------------------
csv_txt = model_query.to_csv(IDX)
assert csv_txt.splitlines()[0].startswith("guid,ifc_class") and len(csv_txt.splitlines()) == 4, csv_txt[:80]
jl = model_query.to_jsonld(IDX)
assert jl["count"] == 3 and jl["@graph"][0]["@id"] in IDX, jl["@graph"][0]

with TestClient(app) as c:
    pid = c.post("/projects", json={"name": "P"}).json()["id"]
    assert "count_by_class" in {v["id"] for v in c.get(f"/projects/{pid}/model/query/views").json()["views"]}
    # no model loaded -> valid empty results
    assert c.get(f"/projects/{pid}/model/query").json()["model_scored"] is False
    assert c.get(f"/projects/{pid}/model/export.jsonld").json()["count"] == 0
    csv_resp = c.get(f"/projects/{pid}/model/export.csv")
    assert csv_resp.status_code == 200 and csv_resp.text.startswith("guid,ifc_class"), csv_resp.text[:60]

print("MODEL QUERY OK - D1: group-by count (IfcWall=2) + sum NetVolume (walls 8, slab 10) + filter "
      "(walls on L1) + saved views + no-model guard; D2: CSV (header + 3 rows) and JSON-LD graph "
      "(3 nodes, GlobalId @id); endpoints return valid empty results with no model loaded")

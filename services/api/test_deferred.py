"""Deferred-item slices: model-driven MEP extraction (C1x), model-staleness signature (B2x),
IFC schema detection / capabilities (D4x), CV bridge write-path (E2x).
Run: PYTHONPATH=src ./.venv/Scripts/python.exe test_deferred.py"""
import os
import tempfile

os.environ["DATABASE_URL"] = "sqlite:///./test_deferred.db"
os.environ["STORAGE_DIR"] = "./test_storage_deferred"
os.environ.pop("AEC_RBAC", None)
os.environ.pop("AEC_CV_BRIDGE", None)
for _f in ("./test_deferred.db",):
    if os.path.exists(_f):
        os.remove(_f)

from fastapi.testclient import TestClient  # noqa: E402

from aec_api import mep  # noqa: E402
from aec_api import model_capabilities as mc
from aec_api.main import app  # noqa: E402

# --- C1x: model-driven MEP extraction -------------------------------------------------------------
idx = {
    "d1": {"ifc_class": "IfcDuctSegment"}, "d2": {"ifc_class": "IfcDuctSegment"},
    "p1": {"ifc_class": "IfcPipeSegment"}, "t1": {"ifc_class": "IfcAirTerminal"},
    "w1": {"ifc_class": "IfcWall"},        # not MEP -> ignored
}
ex = mep.extract_from_model(idx)
assert ex["model_scored"] and ex["mep_elements"] == 4, ex
top = ex["by_class"][0]
assert top["ifc_class"] == "IfcDuctSegment" and top["count"] == 2, ex["by_class"]
assert mep.extract_from_model(None)["model_scored"] is False

# --- B2x: model-staleness signature ---------------------------------------------------------------
s1 = mc.model_signature(idx)
assert s1["model_loaded"] and s1["elements"] == 5 and s1["signature"], s1
s2 = mc.model_signature({**idx, "x9": {"ifc_class": "IfcSlab"}})
assert s2["signature"] != s1["signature"], "signature must change when the model changes"
assert mc.model_signature(None)["model_loaded"] is False

# --- D4x: IFC schema detection --------------------------------------------------------------------
with tempfile.TemporaryDirectory() as d:
    spf = os.path.join(d, "m.ifc")
    with open(spf, "w") as f:
        f.write("ISO-10303-21;\nHEADER;\nFILE_SCHEMA(('IFC4'));\nENDSEC;\n")
    assert mc.detect_schema(spf) == {"detected": "IFC4", "supported": True,
                                     "note": "STEP (IFC-SPF) schema read from the file header."}, mc.detect_schema(spf)
    j = os.path.join(d, "m.ifcx")
    with open(j, "w") as f:
        f.write('{\n "header": {"schema": "IFC5"}\n}')
    det = mc.detect_schema(j)
    assert det["supported"] is False and "IFC5" in det["detected"], det
assert mc.detect_schema(None)["detected"] is None
caps = mc.capabilities(None)
assert caps["supported_read_schemas"] == ["IFC2X3", "IFC4", "IFC4X3"]
assert caps["ifc5"]["status"] == "data" and caps["ifc5"]["data_read"] and not caps["ifc5"]["geometry_read"]

with TestClient(app) as c:
    pid = c.post("/projects", json={"name": "P"}).json()["id"]
    # endpoints valid with no model
    assert c.get(f"/projects/{pid}/mep/model-extract").json()["model_scored"] is False
    assert c.get(f"/projects/{pid}/drawings/sync-status").json()["model_loaded"] is False
    assert c.get(f"/projects/{pid}/model/capabilities").json()["ifc5"]["status"] == "data"

    # --- E2x: CV bridge write-path ---------------------------------------------------------------
    act = c.post(f"/projects/{pid}/modules/schedule_activity",
                 json={"data": {"name": "Frame L2", "percent": 0}}).json()
    # off by default -> no-op
    off = c.post(f"/projects/{pid}/cv-progress/ingest",
                 json={"activity": act["id"], "percent": 55}).json()
    assert off["accepted"] is False, off

    os.environ["AEC_CV_BRIDGE"] = "1"
    on = c.post(f"/projects/{pid}/cv-progress/ingest",
                json={"activity": act["id"], "percent": 55}).json()
    assert on["accepted"] is True and on.get("applied") is True, on
    # the activity's percent was actually written
    rec = c.get(f"/projects/{pid}/modules/schedule_activity/{act['id']}").json()
    assert float((rec.get("data") or rec).get("percent")) == 55.0, rec
    # a bad activity id doesn't 500 the bridge
    bad = c.post(f"/projects/{pid}/cv-progress/ingest",
                 json={"activity": "nope", "percent": 20}).json()
    assert bad["accepted"] is True and bad.get("applied") is False, bad
    # resolve by NAME (a CV service that only knows human labels), not just id
    byname = c.post(f"/projects/{pid}/cv-progress/ingest",
                    json={"activity": "Frame L2", "percent": 70}).json()
    assert byname.get("applied") is True and byname.get("activity_id") == act["id"], byname
    # batch ingest: one by-name (ok) + one bad → applied count = 1, per-item outcomes present
    act2 = c.post(f"/projects/{pid}/modules/schedule_activity",
                  json={"data": {"name": "Slab L3", "percent": 0}}).json()
    batch = c.post(f"/projects/{pid}/cv-progress/ingest-batch",
                   json={"estimates": [{"activity": "Slab L3", "percent": 30},
                                       {"activity": "ghost", "percent": 10}]}).json()
    assert batch["accepted"] and batch["count"] == 2 and batch["applied"] == 1, batch
    rec2 = c.get(f"/projects/{pid}/modules/schedule_activity/{act2['id']}").json()
    assert float((rec2.get("data") or rec2).get("percent")) == 30.0, rec2
    os.environ.pop("AEC_CV_BRIDGE", None)
    # batch is a no-op when the flag is off
    assert c.post(f"/projects/{pid}/cv-progress/ingest-batch",
                  json={"estimates": [{"activity": "Slab L3", "percent": 99}]}).json()["accepted"] is False

print("DEFERRED OK - C1x: MEP read off model by IFC class (4 elements, ducts top); B2x: model signature "
      "changes when the model changes + no-model guard; D4x: schema sniff (IFC4 STEP supported, IFC5/IFCX "
      "JSON detected+unsupported) + capabilities; E2x: CV bridge off=no-op, on=writes percent to the "
      "activity (55%), bad id handled")

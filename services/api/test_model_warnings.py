"""WARN-1 — the unified model-warnings feed. A blank model yields a small warn-only feed (no fails);
injecting a duplicate GlobalId surfaces a `duplicate_guids` fail row that sorts to the top; the feed is
severity-ranked (fails before warns) and the /models/warnings route 409s without a source IFC.
Run: PYTHONPATH="src;../data/src" ./.venv/Scripts/python.exe test_model_warnings.py"""
import os

TMP = os.path.join(os.path.dirname(__file__), "_warnfeed.ifc")

from aec_api import model_warnings  # noqa: E402
from aec_data import massing  # noqa: E402
from aec_data.ifc_loader import open_model  # noqa: E402

# --- clean-ish blank model: a feed with no fails (only conformance/hygiene warns) -------------------
massing.generate_blank_ifc(TMP, name="WarnFeed", storeys=2, storey_height=3.5, ground_size=20.0)
m = open_model(TMP)
res = model_warnings.feed(m)
assert set(res) >= {"total", "by_severity", "warnings", "clean"}, res
assert res["by_severity"]["fail"] == 0, res["by_severity"]         # a well-formed blank model never FAILS
# severity ordering holds: every fail precedes every warn precedes every info
ranks = [{"fail": 0, "warn": 1, "info": 2}[w["severity"]] for w in res["warnings"]]
assert ranks == sorted(ranks), ranks
# each row carries the punch-list shape
for w in res["warnings"]:
    assert {"source", "id", "severity", "label", "count"} <= set(w), w
    assert w["source"] in ("hygiene", "conformance"), w

# --- inject a duplicate GlobalId → a hygiene `duplicate_guids` FAIL row, sorted to the very top ------
import ifcopenshell  # noqa: E402

bad = ifcopenshell.open(TMP)
roots = bad.by_type("IfcBuildingStorey")
assert len(roots) >= 2, "blank model should have >=2 storeys"
roots[1].GlobalId = roots[0].GlobalId                              # duplicate → duplicate_guids fail
res2 = model_warnings.feed(bad)
by_id = {w["id"]: w for w in res2["warnings"]}
assert "duplicate_guids" in by_id, list(by_id)
dg = by_id["duplicate_guids"]
assert dg["severity"] == "fail" and dg["count"] >= 1, dg
assert res2["by_severity"]["fail"] >= 1 and res2["clean"] is False, res2["by_severity"]
assert res2["warnings"][0]["severity"] == "fail", res2["warnings"][0]   # a fail sorts to the top

# --- route -----------------------------------------------------------------------------------------
os.environ["DATABASE_URL"] = "sqlite:///./test_model_warnings.db"
os.environ["STORAGE_DIR"] = "./test_storage_warnfeed"
os.environ.pop("AEC_RBAC", None)
if os.path.exists("./test_model_warnings.db"):
    os.remove("./test_model_warnings.db")
from fastapi.testclient import TestClient  # noqa: E402

from aec_api.db import SessionLocal  # noqa: E402
from aec_api.main import app  # noqa: E402
from aec_api.models import Project  # noqa: E402

with TestClient(app) as c:
    pid = c.post("/projects", json={"name": "Warn"}).json()["id"]
    assert c.get(f"/projects/{pid}/models/warnings").status_code == 409   # no source IFC
    with SessionLocal() as db:
        db.get(Project, pid).source_ifc = TMP
        db.commit()
    r = c.get(f"/projects/{pid}/models/warnings")
    assert r.status_code == 200, r.status_code
    j = r.json()
    assert "warnings" in j and "by_severity" in j and j["by_severity"]["fail"] == 0, j

if os.path.exists(TMP):
    os.remove(TMP)

print("WARN-1 OK - the unified model-warnings feed flattens the hygiene (model_qa) + normative-conformance "
      "(norm_valid) lenses into one worst-first punch list: a well-formed blank model yields a warn-only "
      "feed (zero fails), a duplicate GlobalId surfaces a duplicate_guids FAIL row that sorts to the top, "
      "severity ordering (fail→warn→info) holds, and the /models/warnings route 409s without a source IFC "
      "and returns the structured feed otherwise.")

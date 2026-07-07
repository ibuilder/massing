"""Naming conventions (A3): container-filename + NCS sheet-ID validation and register audit.
Run: PYTHONPATH=src ./.venv/Scripts/python.exe test_naming.py"""
import os

os.environ["DATABASE_URL"] = "sqlite:///./test_naming.db"
os.environ["STORAGE_DIR"] = "./test_storage_naming"
os.environ.pop("AEC_RBAC", None)
for _f in ("./test_naming.db",):
    if os.path.exists(_f):
        os.remove(_f)

from fastapi.testclient import TestClient  # noqa: E402

from aec_api import naming, reports  # noqa: E402
from aec_api.main import app  # noqa: E402

# --- unit: the validators -------------------------------------------------------------------------
good = naming.validate_container_name("DR_A_GroundFloorPlan_P01_2026-07-05")
assert good["valid"] is True, good
assert good["fields"]["discipline"] == "A" and good["fields"]["revision"] == "P01", good
bad = naming.validate_container_name("Final.pdf")
assert bad["valid"] is False and bad["issues"], bad
bad_rev = naming.validate_container_name("DR_A_Plan_final_2026")   # revision not P01-like
assert bad_rev["valid"] is False, bad_rev

assert naming.validate_sheet_id("A-101")["valid"] is True, "A-101 should parse"
assert naming.validate_sheet_id("hello")["valid"] is False, "garbage should fail"

with TestClient(app) as c:
    pid = c.post("/projects", json={"name": "P"}).json()["id"]

    conv = c.get(f"/projects/{pid}/naming/conventions").json()
    assert conv["container"]["pattern"].startswith("Type_Discipline"), conv

    v = c.get(f"/projects/{pid}/naming/validate", params={"name": "S-201", "kind": "sheet"}).json()
    assert v["valid"] is True and v["fields"]["discipline_code"] == "S", v

    # --- registers: one compliant + one not, for both containers and drawings --------------------
    c.post(f"/projects/{pid}/modules/information_container",
           json={"data": {"title": "GF plan", "container_id": "DR_A_GroundFloorPlan_P01_2026-07-05"}})
    c.post(f"/projects/{pid}/modules/information_container",
           json={"data": {"title": "loose", "container_id": "New file (2).pdf"}})
    c.post(f"/projects/{pid}/modules/drawing", json={"data": {"number": "A-101", "sheet_number": "A-101"}})
    c.post(f"/projects/{pid}/modules/drawing", json={"data": {"number": "sketch", "sheet_number": "sketch"}})

    a = c.get(f"/projects/{pid}/naming/audit").json()
    assert a["containers"]["total"] == 2 and a["containers"]["compliant"] == 1, a["containers"]
    assert a["containers"]["compliance_pct"] == 50.0, a["containers"]
    assert a["sheets"]["total"] == 2 and a["sheets"]["compliant"] == 1, a["sheets"]
    assert len(a["containers"]["violations"]) == 1 and len(a["sheets"]["violations"]) == 1, a

    # --- report + PDF ----------------------------------------------------------------------------
    assert "naming" in {x["id"] for x in reports.catalog()}, "naming missing from catalog"
    rep = c.get(f"/projects/{pid}/reports/naming.pdf")
    assert rep.status_code == 200 and rep.content[:4] == b"%PDF", rep.status_code

print("NAMING OK - container pattern Type_Discipline_Description_Revision_Date validated (good/bad + "
      "bad revision); NCS sheet IDs via the D3 parser (A-101/S-201 ok, garbage fails); register audit "
      "= 50% container + 50% sheet compliance with violation lists; report PDF served")

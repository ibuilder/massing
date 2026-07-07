"""Design engine (Phase B): design options / variants comparison (B1), the selected-option drawing
linkage (B2), and the design-standards ruleset + model check (B3).
Run: PYTHONPATH=src ./.venv/Scripts/python.exe test_design_engine.py"""
import os

os.environ["DATABASE_URL"] = "sqlite:///./test_design_engine.db"
os.environ["STORAGE_DIR"] = "./test_storage_design_engine"
os.environ.pop("AEC_RBAC", None)
for _f in ("./test_design_engine.db",):
    if os.path.exists(_f):
        os.remove(_f)

from fastapi.testclient import TestClient  # noqa: E402

from aec_api import design_standards, reports  # noqa: E402
from aec_api.db import SessionLocal  # noqa: E402
from aec_api.main import app  # noqa: E402


def _mk(c, pid, key, data):
    r = c.post(f"/projects/{pid}/modules/{key}", json={"data": data})
    assert r.status_code == 201, f"{key}: {r.text[:160]}"
    return r.json()


def _act(c, pid, key, rid, action):
    c.post(f"/projects/{pid}/modules/{key}/{rid}/transition", json={"action": action})


with TestClient(app) as c:
    pid = c.post("/projects", json={"name": "P"}).json()["id"]

    # --- B1: design options comparison -----------------------------------------------------------
    a1 = _mk(c, pid, "design_option", {"name": "Scheme A — courtyard", "gross_area_sf": 10000,
                                       "unit_count": 40, "efficiency_pct": 82, "hard_cost": 2000000,
                                       "energy_eui": 38, "irr_pct": 15})
    _mk(c, pid, "design_option", {"name": "Scheme B — tower", "gross_area_sf": 12000,
                                  "unit_count": 52, "efficiency_pct": 80, "hard_cost": 2760000,
                                  "energy_eui": 42, "irr_pct": 18})
    _act(c, pid, "design_option", a1["id"], "shortlist")
    _act(c, pid, "design_option", a1["id"], "select")

    cmp = c.get(f"/projects/{pid}/design/options/compare").json()
    assert cmp["count"] == 2, cmp
    assert cmp["selected"] == "Scheme A — courtyard", cmp["selected"]
    a = next(o for o in cmp["options"] if o["name"].startswith("Scheme A"))
    assert a["cost_per_sf"] == 200.0, a                      # 2,000,000 / 10,000
    assert cmp["leaders"]["cost_per_sf"]["option"].startswith("Scheme A"), cmp["leaders"]
    assert cmp["leaders"]["irr_pct"]["option"].startswith("Scheme B"), cmp["leaders"]
    assert a["delta_vs_selected"]["irr_pct"] == 0, a         # A is the selected -> zero delta vs itself

    # --- B3: design standards ruleset + model check ----------------------------------------------
    _mk(c, pid, "design_standard", {"name": "PVC potable pipe (banned)", "category": "Material",
                                    "status": "prohibited", "match_keyword": "pvc"})
    _mk(c, pid, "design_standard", {"name": "Steel stud partitions", "category": "Assembly",
                                    "status": "approved", "match_keyword": "steel"})
    rs = c.get(f"/projects/{pid}/design/standards").json()
    assert rs["count"] == 2 and len(rs["by_status"]["prohibited"]) == 1, rs

    # no model -> ruleset only
    chk0 = c.get(f"/projects/{pid}/design/standards/check").json()
    assert chk0["model_scored"] is False, chk0

    # synthetic model -> prohibited hit + unapproved flag (engine unit)
    idx = {
        "e1": {"type_name": "PVC Pipe DN50", "ifc_class": "IfcPipeSegment"},   # prohibited (pvc)
        "e2": {"type_name": "Steel Stud 3-5/8", "ifc_class": "IfcWall"},       # approved (steel)
        "e3": {"type_name": "Concrete", "ifc_class": "IfcSlab"},               # matches nothing approved
    }
    chk = design_standards.check(SessionLocal(), pid, idx)
    assert chk["model_scored"] is True and chk["elements"] == 3, chk
    assert chk["prohibited_hits"] == 1, chk
    assert chk["unapproved"] == 1, chk                       # concrete matched no approved keyword
    issues = " ".join(v["issue"] for v in chk["violations"])
    assert "prohibited" in issues and "approved" in issues, chk["violations"]

    # --- reports (both surface under the Design group) -------------------------------------------
    ids = {x["id"] for x in reports.catalog()}
    assert {"design_options", "design_standards"} <= ids, ids
    for rk in ("design_options", "design_standards"):
        rep = c.get(f"/projects/{pid}/reports/{rk}.pdf")
        assert rep.status_code == 200 and rep.content[:4] == b"%PDF", (rk, rep.status_code)

print("DESIGN ENGINE OK - B1: options compared on program+economics (A $/sf=200, best cost=A, best "
      "IRR=B, selected=A); B3: ruleset (1 prohibited + 1 approved); no-model check = ruleset only; "
      "synthetic model flags 1 prohibited (PVC) + 1 unapproved (concrete); both Design reports PDF-served")

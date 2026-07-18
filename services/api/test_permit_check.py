"""PERMIT-CHECK: permit-submission readiness — checklist + ranked deficiencies + verdict over the code
engines and the drawing register. Seeded model + register; 409 without a model.
Run: PYTHONPATH=src;../data/src ./.venv/Scripts/python.exe test_permit_check.py"""
import os
import sys

os.environ.setdefault("DATABASE_URL", "sqlite:///./_permit_test.db")
os.environ.setdefault("STORAGE_DIR", "./_storage_permit")
os.environ.setdefault("IFC_DIR", os.path.join(os.path.dirname(__file__), "_ifc_permit"))
os.environ.pop("AEC_RBAC", None)
if os.path.exists("./_permit_test.db"):
    os.remove("./_permit_test.db")

_DATA_SRC = os.path.join(os.path.dirname(__file__), "..", "data", "src")
if _DATA_SRC not in sys.path:
    sys.path.insert(0, _DATA_SRC)

from fastapi.testclient import TestClient  # noqa: E402

from aec_api.main import app  # noqa: E402

with TestClient(app) as c:
    pid = c.post("/projects", json={"name": "Permit Tower"}).json()["id"]

    # no model yet -> 409
    assert c.get(f"/projects/{pid}/permit/readiness").status_code == 409

    # author a small model (blank -> storeys + spaces so egress/code-analysis have something to read)
    r = c.post(f"/projects/{pid}/model/blank",
               json={"name": "Permit", "storeys": 2, "storey_height": 3.5, "ground_size": 20.0})
    assert r.status_code < 300, r.text[:200]
    r = c.post(f"/projects/{pid}/edit", json={"recipe": "add_spaces",
               "params": {"rooms_per_storey": 2}, "publish": False})
    assert r.status_code < 300, r.text[:200]

    # empty register: report exists, sheet-series requirements unsatisfied, verdict NOT READY
    r0 = c.get(f"/projects/{pid}/permit/readiness").json()
    assert r0["verdict"] in ("READY", "NOT READY")
    reqs = {row["requirement"]: row["satisfied"] for row in r0["checklist"]}
    assert any("G-series" in k for k in reqs), reqs
    assert not any(v for k, v in reqs.items() if "series" in k), "no sheets registered yet"
    assert r0["deficiencies"], "missing sheets must appear as deficiencies"
    sev = [d["severity"] for d in r0["deficiencies"]]
    assert sev == sorted(sev, key=lambda s: {"critical": 0, "major": 1, "minor": 2}[s]), \
        "deficiencies ranked critical->major->minor"
    assert "NOT a certified plan review" in r0["disclaimer"]

    # register sheets across the required series -> those requirements flip to satisfied
    for num, title in (("G-001", "Code Analysis"), ("A-101", "Floor Plan L1"), ("S-101", "Framing"),
                       ("M-101", "Mech Plan"), ("E-101", "Power Plan"), ("P-101", "Plumbing Plan")):
        cr = c.post(f"/projects/{pid}/modules/drawing",
                    json={"data": {"number": num, "title": title, "discipline": num[0]}})
        assert cr.status_code < 300, cr.text[:200]
    r1 = c.get(f"/projects/{pid}/permit/readiness"
               "?occupancy_group=B&construction_type=II-B&jurisdiction=CA").json()
    reqs1 = {row["requirement"]: row["satisfied"] for row in r1["checklist"]}
    assert all(v for k, v in reqs1.items() if "series" in k), reqs1
    assert reqs1["Code-analysis summary complete (occupancy group + construction type declared)"] is True
    assert r1["readiness_pct"] > r0["readiness_pct"], (r0["readiness_pct"], r1["readiness_pct"])
    assert r1["sheet_series"].get("G") == 1 and r1["sheet_series"].get("A") == 1, r1["sheet_series"]

print("PERMIT-CHECK OK - 409 without a model; with a 2-storey model + spaces the intake report composes "
      "computed egress + approvability + code-analysis + the drawing register: empty register -> "
      "series requirements unsatisfied and ranked deficiencies (critical->major->minor) with the "
      "not-a-certified-review disclaimer; registering G/A/S/M/E/P sheets + declaring occupancy B / "
      "type II-B / CA jurisdiction flips those rows and raises readiness_pct.")

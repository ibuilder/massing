"""Substantial completion (G704) + record-model turnover — architect sign-off on the punch list.
Run: PYTHONPATH=src ./.venv/Scripts/python.exe test_turnover.py"""
import os

os.environ["DATABASE_URL"] = "sqlite:///./test_turnover.db"
os.environ["STORAGE_DIR"] = "./test_storage_turnover"
os.environ.pop("AEC_RBAC", None)
for _f in ("./test_turnover.db",):
    if os.path.exists(_f):
        os.remove(_f)

from fastapi.testclient import TestClient           # noqa: E402
from aec_api.main import app                          # noqa: E402


def _create(c, pid, key, data):
    r = c.post(f"/projects/{pid}/modules/{key}", json={"data": data})
    assert r.status_code == 201, f"{key}: {r.text[:160]}"
    return r.json()


with TestClient(app) as c:
    pid = c.post("/projects", json={"name": "P"}).json()["id"]

    # --- gate: no punch list -> not ready, certify refused ---
    rd0 = c.get(f"/projects/{pid}/turnover/readiness").json()
    assert rd0["punch_list_prepared"] is False and rd0["ready_for_substantial_completion"] is False, rd0
    cert = _create(c, pid, "completion_certificate", {"subject": "Substantial Completion", "type": "Substantial"})
    refused = c.post(f"/projects/{pid}/turnover/certify",
                     json={"cert_rid": cert["id"], "architect": "A. Architect, AIA"})
    assert refused.status_code == 400, refused.text[:160]           # no punch list -> gated

    # --- prepare a punch list (substantial completion is certified WITH an open punch list) ---
    _create(c, pid, "punchlist", {"description": "Touch up paint", "trade": "Finishes"})
    _create(c, pid, "punchlist", {"description": "Adjust door closer", "trade": "Doors"})

    rd = c.get(f"/projects/{pid}/turnover/readiness").json()
    assert rd["punch_list_prepared"] and rd["ready_for_substantial_completion"], rd
    assert rd["punch"]["count"] == 2 and rd["punch"]["open"] == 2, rd["punch"]

    cr = c.post(f"/projects/{pid}/turnover/certify", json={"cert_rid": cert["id"],
                "architect": "A. Architect, AIA", "owner": "Owner LLC", "contractor": "BuildCo",
                "occupancy_date": "2026-08-01"})
    assert cr.status_code == 200, cr.text[:200]
    sigs = (cr.json()["certificate"]["data"].get("signatures") or [])
    arch = next(s for s in sigs if s["party"] == "Architect")
    assert arch.get("certifies") is True and arch["name"] == "A. Architect, AIA", arch
    assert {s["party"] for s in sigs} >= {"Architect", "Owner", "Contractor"}, sigs
    # certificate issued + punch metrics stamped
    assert cr.json()["certificate"]["workflow_state"] == "issued", cr.json()["certificate"]["workflow_state"]
    assert cr.json()["certificate"]["data"]["punch_open"] == 2, cr.json()["certificate"]["data"]

    # --- G704 renders + turnover status reflects the signed certificate ---
    g704 = c.get(f"/projects/{pid}/contracts/completion_certificate/{cert['id']}/document.pdf?doc=g704")
    assert g704.status_code == 200 and g704.content[:4] == b"%PDF", g704.status_code
    st = c.get(f"/projects/{pid}/turnover/status").json()
    assert st["substantial_completion"] and st["substantial_completion"]["ref"], st

print("TURNOVER OK - readiness gate (no punch list -> certify refused 400); architect certifies "
      "substantial completion (Architect certifies + Owner + Contractor sign; cert issued; punch "
      "metrics stamped); G704 renders as PDF; turnover status reflects the signed certificate")

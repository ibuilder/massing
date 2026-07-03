"""Due diligence + entitlements (pre-acquisition) — modules, workflows, go/no-go rollup.
Run: PYTHONPATH=src ./.venv/Scripts/python.exe test_diligence.py"""
import os

os.environ["DATABASE_URL"] = "sqlite:///./test_diligence.db"
os.environ["STORAGE_DIR"] = "./test_storage_diligence"
os.environ.pop("AEC_RBAC", None)
for _f in ("./test_diligence.db",):
    if os.path.exists(_f):
        os.remove(_f)

from fastapi.testclient import TestClient           # noqa: E402
from aec_api.main import app                          # noqa: E402


def _create(c, pid, key, data):
    r = c.post(f"/projects/{pid}/modules/{key}", json={"data": data})
    assert r.status_code == 201, f"{key}: {r.text[:160]}"
    return r.json()


def _act(c, pid, key, rid, action):
    r = c.post(f"/projects/{pid}/modules/{key}/{rid}/transition", json={"action": action})
    assert r.status_code == 200, f"{action}: {r.text[:160]}"
    return r.json()


with TestClient(app) as c:
    pid = c.post("/projects", json={"name": "P"}).json()["id"]

    # --- due diligence: ESA cleared; geotech flagged high-risk --------------------------------
    esa = _create(c, pid, "due_diligence", {"subject": "Phase I ESA",
        "category": "Phase I ESA (ASTM E1527)", "consultant": "EnviroCo",
        "findings": "No RECs identified."})
    _act(c, pid, "due_diligence", esa["id"], "submit_report")
    _act(c, pid, "due_diligence", esa["id"], "clear")

    geo = _create(c, pid, "due_diligence", {"subject": "Geotech borings",
        "category": "Geotechnical", "findings": "High water table; deep foundations likely.",
        "risk": "High"})
    _act(c, pid, "due_diligence", geo["id"], "submit_report")
    fl = _act(c, pid, "due_diligence", geo["id"], "flag")
    assert fl["workflow_state"] == "flagged", fl["workflow_state"]

    # submit_report requires findings — a bare item can't advance
    bare = _create(c, pid, "due_diligence", {"subject": "Traffic study", "category": "Traffic Study"})
    r = c.post(f"/projects/{pid}/modules/due_diligence/{bare['id']}/transition",
               json={"action": "submit_report"})
    assert r.status_code == 400 and "Findings" in r.text, r.text[:160]

    # --- entitlement: rezoning through hearing -> approved with expiring approval --------------
    rez = _create(c, pid, "entitlement", {"subject": "Rezone to MU-2", "application_type": "Rezoning",
        "agency": "City Planning", "approval_expires": "2026-09-01"})
    _act(c, pid, "entitlement", rez["id"], "submit")
    c.patch(f"/projects/{pid}/modules/entitlement/{rez['id']}", json={"hearing_date": "2026-08-01"})
    _act(c, pid, "entitlement", rez["id"], "schedule_hearing")
    ap = _act(c, pid, "entitlement", rez["id"], "approve")
    assert ap["workflow_state"] == "approved", ap["workflow_state"]

    # --- readiness rollup: flagged high-risk + open item -> NO-GO ------------------------------
    rd = c.get(f"/projects/{pid}/diligence/readiness").json()
    assert rd["due_diligence"]["total"] == 3 and rd["due_diligence"]["cleared"] == 1, rd["due_diligence"]
    assert len(rd["due_diligence"]["high_risk"]) == 1, rd["due_diligence"]["high_risk"]
    assert rd["entitlements"]["approved"] == 1 and rd["entitlements"]["pending"] == 0, rd["entitlements"]
    assert len(rd["entitlements"]["expiring_within_180d"]) == 1, rd["entitlements"]
    assert rd["go"] is False, "flagged high-risk + open items must be no-go"

print("DILIGENCE OK - ESA cleared; geotech flagged High (report gate requires findings); rezoning "
      "submit->hearing->approved with 180d-expiry surfaced; rollup: 3 items / 1 cleared / 1 high-risk "
      "-> go=False")

"""Stakeholder register + power/interest (Mendelow) analysis.
Run: PYTHONPATH=src ./.venv/Scripts/python.exe test_stakeholder.py"""
import os

os.environ["DATABASE_URL"] = "sqlite:///./test_stakeholder.db"
os.environ["STORAGE_DIR"] = "./test_storage_stakeholder"
os.environ.pop("AEC_RBAC", None)
for _f in ("./test_stakeholder.db",):
    if os.path.exists(_f):
        os.remove(_f)

from fastapi.testclient import TestClient  # noqa: E402

from aec_api.main import app  # noqa: E402


def _stk(c, pid, **data):
    r = c.post(f"/projects/{pid}/modules/stakeholder", json={"data": data})
    assert r.status_code == 201, r.text[:160]
    return r.json()


with TestClient(app) as c:
    pid = c.post("/projects", json={"name": "P"}).json()["id"]
    _stk(c, pid, name="City Planning Dept", organization="City", category="Authority / Regulator",
         power="High", interest="High", stance="Neutral")               # manage closely
    _stk(c, pid, name="Lender", organization="BigBank", category="Investor / Lender",
         power="High", interest="Low", stance="Blocker")                 # keep satisfied + high-power blocker
    _stk(c, pid, name="Neighborhood Assoc.", organization="NA", category="Community",
         power="Low", interest="High", stance="Supporter")               # keep informed
    _stk(c, pid, name="Passerby", organization="", category="Community",
         power="Low", interest="Low", stance="Neutral")                  # monitor

    a = c.get(f"/projects/{pid}/stakeholders/analysis").json()
    assert a["total"] == 4, a["total"]
    q = a["quadrants"]
    assert q["manage_closely"]["count"] == 1 and q["keep_satisfied"]["count"] == 1, q
    assert q["keep_informed"]["count"] == 1 and q["monitor"]["count"] == 1, q
    assert a["stance"]["Blocker"] == 1 and a["stance"]["Supporter"] == 1, a["stance"]
    # the high-power blocker (the Lender) is flagged
    assert len(a["high_power_blockers"]) == 1 and a["high_power_blockers"][0]["organization"] == "BigBank", \
        a["high_power_blockers"]
    assert a["supporter_pct"] == 25.0, a["supporter_pct"]

    # the Stakeholder Analysis report is registered + builds (PDF endpoint)
    assert any(r["id"] == "stakeholder_analysis" for r in c.get("/reports").json()["reports"])
    rp = c.get(f"/projects/{pid}/reports/stakeholder_analysis.pdf")
    assert rp.status_code == 200 and rp.content[:4] == b"%PDF", rp.status_code

print(f"stakeholder OK — quadrants "
      f"{ {k: v['count'] for k, v in a['quadrants'].items()} }, {len(a['high_power_blockers'])} blocker(s)")
print("test_stakeholder OK")

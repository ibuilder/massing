"""Predictive schedule alerts — overdue, late start, at-risk start (incomplete predecessor).
Run: PYTHONPATH=src ./.venv/Scripts/python.exe test_schedule_alerts.py"""
import os
from datetime import date, timedelta

os.environ["DATABASE_URL"] = "sqlite:///./test_schedalerts.db"
os.environ["STORAGE_DIR"] = "./test_storage_schedalerts"
os.environ.pop("AEC_RBAC", None)
for f in ("./test_schedalerts.db",):
    if os.path.exists(f):
        os.remove(f)

from fastapi.testclient import TestClient  # noqa: E402

from aec_api.main import app  # noqa: E402

T = date.today()
def iso(days): return (T + timedelta(days=days)).isoformat()


def mk(c, pid, data):
    r = c.post(f"/projects/{pid}/modules/schedule_activity", json={"data": data})
    assert r.status_code in (200, 201), r.text[:160]
    return r.json()["id"]


with TestClient(app) as c:
    pid = c.post("/projects", json={"name": "Sched"}).json()["id"]
    mk(c, pid, {"name": "Foundations", "wbs": "01.01", "start": iso(-30), "finish": iso(-10),
                "percent": 50, "budget": 100000})                              # overdue (high)
    mk(c, pid, {"name": "Sitework", "wbs": "01.00", "start": iso(-5), "finish": iso(20),
                "percent": 0, "budget": 50000})                                # late start (medium)
    mk(c, pid, {"name": "Superstructure", "wbs": "01.02", "start": iso(7), "finish": iso(60),
                "percent": 0, "budget": 200000, "predecessors": "01.01"})      # at-risk start (pred 01.01 incomplete)

    res = c.get(f"/projects/{pid}/schedule/alerts").json()
    types = {a["type"] for a in res["alerts"]}
    assert "overdue" in types, res
    assert "late_start" in types, res
    assert "predecessor" in types, res
    assert res["counts"]["high"] >= 2, res          # overdue + at-risk predecessor
    # highest-severity first
    assert res["alerts"][0]["level"] == "high", res

print(f"SCHEDULE ALERTS OK - overdue + late-start + at-risk-predecessor detected; "
      f"{res['counts']['high']} high / {res['counts']['medium']} medium, sorted by severity")

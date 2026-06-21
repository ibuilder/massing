"""Construction program portfolio: cross-project cost over/under, open risks, recordables, RFIs.
Run: PYTHONPATH=src ./.venv/Scripts/python.exe test_portfolio.py"""
import os

os.environ["DATABASE_URL"] = "sqlite:///./portfolio_test.db"
os.environ["STORAGE_DIR"] = "./test_storage_pf"
os.environ.pop("AEC_RBAC", None)
for f in ("./portfolio_test.db",):
    if os.path.exists(f):
        os.remove(f)

from fastapi.testclient import TestClient  # noqa: E402
from aec_api.main import app  # noqa: E402

with TestClient(app) as c:
    a = c.post("/projects", json={"name": "Tower A"}).json()["id"]
    b = c.post("/projects", json={"name": "Tower B"}).json()["id"]
    # project A: 2 open risks (one with exposure), 1 recordable incident, 1 open RFI
    c.post(f"/projects/{a}/modules/risk", json={"data": {"title": "Permit delay", "probability": "High", "impact": "High", "cost_exposure": 50000}})
    c.post(f"/projects/{a}/modules/risk", json={"data": {"title": "Weather", "probability": "Medium", "impact": "Low"}})
    inc = c.post(f"/projects/{a}/modules/incident", json={"data": {"subject": "Fall", "classification": "Recordable", "date": "2026-06-01"}}).json()
    rfi = c.post(f"/projects/{a}/modules/rfi", json={"data": {"subject": "Q", "question": "?"}}).json()
    c.post(f"/projects/{a}/modules/rfi/{rfi['id']}/transition", json={"action": "submit"})   # draft -> open

    pf = c.get("/portfolio/construction").json()
    assert pf["project_count"] == 2, pf
    byname = {p["name"]: p for p in pf["projects"]}
    assert byname["Tower A"]["open_risks"] == 2 and byname["Tower A"]["risk_exposure"] == 50000.0, byname["Tower A"]
    assert byname["Tower A"]["recordables"] == 1 and byname["Tower A"]["open_rfis"] == 1, byname["Tower A"]
    assert byname["Tower B"]["open_risks"] == 0 and byname["Tower B"]["recordables"] == 0
    assert pf["totals"]["open_risks"] == 2 and pf["totals"]["risk_exposure"] == 50000.0
    assert pf["totals"]["recordables"] == 1 and pf["totals"]["open_rfis"] == 1
    assert "over_budget_count" in pf["totals"] and "projected_over_under" in pf["totals"]

    print("PORTFOLIO OK - program roll-up: open risks + exposure, recordables, open RFIs, cost over/under totals")

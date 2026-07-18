"""RISK-BOARD — the unified risk register: aggregates Monte-Carlo schedule risk, predictive alerts,
EVM indices, pre-flight blockers, and overdue coordination into one ranked, deep-linked board.
Run: PYTHONPATH=src ./.venv/Scripts/python.exe test_risk_board.py"""
import os

os.environ["DATABASE_URL"] = "sqlite:///./test_risk_board.db"
os.environ["STORAGE_DIR"] = "./test_storage_riskboard"
os.environ["AEC_TRUST_XUSER"] = "1"
os.environ.pop("AEC_RBAC", None)
for _f in ("./test_risk_board.db",):
    if os.path.exists(_f):
        os.remove(_f)

from datetime import date, timedelta  # noqa: E402

from fastapi.testclient import TestClient  # noqa: E402

from aec_api.main import app  # noqa: E402

HDR = {"X-User": "pm"}

with TestClient(app) as c:
    pid = c.post("/projects", json={"name": "Risk Board"}, headers=HDR).json()["id"]
    P = f"/projects/{pid}"

    # empty project → an empty-but-well-formed board (band clear, all lanes report)
    r0 = c.get(f"{P}/risk-board", headers=HDR)
    assert r0.status_code == 200, r0.text[:200]
    b0 = r0.json()
    assert b0["band"] in ("clear", "watch") and isinstance(b0["items"], list), b0["band"]
    assert set(b0["lanes"]) >= {"schedule_risk", "schedule_alerts", "evm", "preflight", "coordination"}, b0["lanes"]

    # seed real signals ------------------------------------------------------------------------------
    yesterday = (date.today() - timedelta(days=10)).isoformat()
    # (a) an overdue schedule activity → a predictive alert
    r1 = c.post(f"{P}/modules/schedule_activity", json={"data": {
        "name": "Foundations", "wbs": "1.1", "duration": 10,
        "start": yesterday, "finish": yesterday, "percent": 20}}, headers=HDR)
    assert r1.status_code == 201, r1.text[:200]
    assert c.post(f"{P}/modules/schedule_activity", json={"data": {
        "name": "Frame", "wbs": "1.2", "duration": 20, "predecessors": "1.1"}}, headers=HDR).status_code == 201
    # (b) an overdue open coordination topic
    c.post(f"{P}/topics", json={"type": "clash", "title": "Beam vs duct",
                                "priority": "high", "due_date": yesterday}, headers=HDR)

    b = c.get(f"{P}/risk-board", headers=HDR).json()
    assert b["count"] >= 2, b
    sources = {i["source"] for i in b["items"]}
    assert "schedule-alert" in sources, sources                      # the overdue activity surfaced
    assert "coordination" in sources, sources                        # the overdue topic surfaced
    assert "preflight" in sources, sources                           # open high topic blocks issuance
    # ranked high → medium → low, every item deep-linked
    order = [{"high": 0, "medium": 1, "low": 2}[i["severity"]] for i in b["items"]]
    assert order == sorted(order), order
    assert all(i.get("link") for i in b["items"]), b["items"]
    assert b["band"] in ("elevated", "critical"), b["band"]
    over = next(i for i in b["items"] if i["source"] == "coordination")
    assert "overdue open issue" in over["title"], over

print("RISK-BOARD OK - one register over 5 engines: empty project → clear board with lane report; an "
      "overdue activity raises a schedule alert, an overdue high topic raises coordination + preflight "
      "blockers; items ranked high→low, all deep-linked; band escalates to elevated/critical.")

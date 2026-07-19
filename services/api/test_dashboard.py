"""Role-tailored dashboard test. Run: PYTHONPATH=src ./.venv/Scripts/python.exe test_dashboard.py"""
import os

os.environ["DATABASE_URL"] = "sqlite:///./test_dash.db"
os.environ["STORAGE_DIR"] = "./test_storage"
os.environ["AEC_RBAC"] = "1"
os.environ["AEC_TRUST_XUSER"] = "1"  # tests act as users via X-User

for f in ("./test_dash.db",):
    if os.path.exists(f):
        os.remove(f)

from fastapi.testclient import TestClient  # noqa: E402

from aec_api.main import app  # noqa: E402

H = lambda u: {"X-User": u}  # noqa: E731

with TestClient(app) as c:
    pid = c.post("/projects", json={"name": "Tower"}, headers=H("gc")).json()["id"]
    for u, party in [("sub", "Subcontractor"), ("consultant", "Consultant"), ("owner", "Owner")]:
        c.post(f"/projects/{pid}/members", json={"user": u, "role": "reviewer", "party_role": party}, headers=H("gc"))

    rfi = c.post(f"/projects/{pid}/modules/rfi", json={"data": {"subject": "Q", "question": "?"}}, headers=H("gc")).json()
    c.post(f"/projects/{pid}/modules/rfi/{rfi['id']}/transition", json={"action": "submit"}, headers=H("gc"))
    cor = c.post(f"/projects/{pid}/modules/cor", json={"data": {"subject": "CO", "amount": 5000}}, headers=H("gc")).json()
    c.post(f"/projects/{pid}/modules/cor/{cor['id']}/transition", json={"action": "submit"}, headers=H("gc"))

    def items(party):
        return {a["module"] for a in c.get(f"/projects/{pid}/dashboard", params={"party": party}, headers=H("gc")).json()["action_items"]}

    assert items("GC") >= {"rfi", "cor"}                       # GC passes every gate
    assert "rfi" in items("Consultant") and "cor" not in items("Consultant")
    assert "cor" in items("Owner") and "rfi" not in items("Owner")
    assert items("Subcontractor") == set()                     # no sub steps available

    d = c.get(f"/projects/{pid}/dashboard", headers=H("gc")).json()
    assert d["kpis"]["open_rfis"] == 1 and d["kpis"]["pending_change_orders"] == 1

    # project status report (PDF aggregating the dashboard)
    rep = c.get(f"/projects/{pid}/report.pdf", headers=H("gc"))
    assert rep.status_code == 200 and rep.headers["content-type"] == "application/pdf", rep.status_code
    assert rep.content[:5] == b"%PDF-" and len(rep.content) > 1500, len(rep.content)

    # capability flags (no integrations configured in tests)
    cap = c.get("/capabilities").json()
    assert cap["ai"] is False and cap["email"] is False and cap["sso"] == [], cap

    # AI/rules risk summary over the dashboard (rules path when no Anthropic key)
    risk = c.get(f"/projects/{pid}/ai/risk-summary", headers=H("gc")).json()
    assert risk["source"] == "rules" and risk["ai_enabled"] is False
    assert all(r["level"] in ("low", "medium", "high") for r in risk["risks"]), risk
    texts = " ".join(r["text"].lower() for r in risk["risks"])
    assert "rfi" in texts and "change order" in texts, risk   # 1 open RFI + 1 pending CO above

    # DASH-UNION (PERF-4): the single UNION-ALL matches every per-module GROUP BY exactly, and no
    # non-empty module is missing from it — the dashboard's counts are provably unchanged.
    from aec_api import modules as me
    from aec_api.db import SessionLocal
    with SessionLocal() as s:
        uni = me.state_counts_all(s, pid)
        assert uni, "a seeded project must produce union counts"
        for k, states in uni.items():
            assert states == me.state_counts(s, k, pid), f"union mismatch for {k}"
        for k in me.REGISTRY:
            if me.state_counts(s, k, pid):
                assert k in uni, f"non-empty module {k} missing from the union"

    print("DASHBOARD OK")
    print(f"  GC={sorted(items('GC'))}  Consultant={sorted(items('Consultant'))}  Owner={sorted(items('Owner'))}")
    print(f"  kpis: {{k:v for non-zero}} = { {k: v for k, v in d['kpis'].items() if v} }")

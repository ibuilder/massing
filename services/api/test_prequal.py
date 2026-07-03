"""Sub prequalification Q-score + COI-expiry tracking.
Run: PYTHONPATH=src ./.venv/Scripts/python.exe test_prequal.py"""
import os
from datetime import date, timedelta

os.environ["DATABASE_URL"] = "sqlite:///./test_prequal.db"
os.environ["STORAGE_DIR"] = "./test_storage_prequal"
os.environ.pop("AEC_RBAC", None)
for _f in ("./test_prequal.db",):
    if os.path.exists(_f):
        os.remove(_f)

from fastapi.testclient import TestClient           # noqa: E402
from aec_api import prequalification as pq            # noqa: E402
from aec_api.main import app                          # noqa: E402

# --- engine: a strong sub scores high/low-risk; a weak one scores low/high-risk ---
strong = {"data": {"company": "Ace", "trade": "Concrete", "emr": 0.7, "annual_revenue": 50_000_000,
                   "bonding_capacity": 20_000_000, "largest_project": 8_000_000, "references": ["a", "b", "c"],
                   "rating": "A", "expires": "2999-01-01"}}
weak = {"data": {"company": "Risky", "trade": "Concrete", "emr": 1.4, "annual_revenue": 1_000_000,
                 "largest_project": 200_000, "references": [], "rating": "D", "status": "submitted",
                 "expires": "2000-01-01"}}
s = pq.score_record(strong, project_size=5_000_000)
w = pq.score_record(weak, project_size=5_000_000)
assert s["score"] > 75 and s["risk_band"] == "low", s
assert w["score"] < 50 and w["risk_band"] == "high", w
assert "EMR above 1.0" in w["flags"] and "no bonding capacity" in w["flags"] and "prequalification expired" in w["flags"], w
assert sum(f["of"] for f in s["factors"]) == 100                 # weights sum to 100
assert s["score"] > w["score"]

# --- endpoints ---
with TestClient(app) as c:
    pid = c.post("/projects", json={"name": "P"}).json()["id"]
    for r in (strong, weak):
        assert c.post(f"/projects/{pid}/modules/prequalification", json=r).status_code == 201
    sc = c.get(f"/projects/{pid}/prequal/scores?project_size=5000000").json()
    assert sc["count"] == 2 and sc["high_risk"] == 1, sc
    assert sc["subs"][0]["company"] == "Risky", sc["subs"][0]           # worst first

    # COI: one expired, one expiring within 30 days, one far future
    today = date.today()
    cois = [("expired", (today - timedelta(days=5)).isoformat()),
            ("soon", (today + timedelta(days=10)).isoformat()),
            ("ok", (today + timedelta(days=200)).isoformat())]
    for vendor, exp in cois:
        c.post(f"/projects/{pid}/modules/coi",
               json={"data": {"vendor": vendor, "coverage_type": "GL", "carrier": "X", "expires": exp}})
    ce = c.get(f"/projects/{pid}/prequal/coi-expiry?soon_days=30").json()
    assert ce["expired_count"] == 1 and ce["expiring_count"] == 1, ce
    assert ce["expired"][0]["vendor"] == "expired" and ce["expiring_soon"][0]["vendor"] == "soon", ce

print("PREQUAL OK - transparent Q-score (weights sum 100): strong sub low-risk >75, weak sub high-risk "
      "<50 with EMR/bonding/expired flags; scores sorted worst-first; COI expiry = 1 expired + 1 soon")

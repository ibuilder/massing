"""Portfolio prioritization matrix — weighted 0-100 scoring + ranking of projects.
Run: PYTHONPATH=src ./.venv/Scripts/python.exe test_prioritization.py"""
import os

os.environ["DATABASE_URL"] = "sqlite:///./test_prioritization.db"
os.environ["STORAGE_DIR"] = "./test_storage_prioritization"
os.environ.pop("AEC_RBAC", None)
for _f in ("./test_prioritization.db",):
    if os.path.exists(_f):
        os.remove(_f)

from aec_api import prioritization  # noqa: E402

# --- pure rank(): a strong project should outrank a weak one -------------------------------------
rows = [
    {"id": "a", "name": "Winner", "status": "on_track", "equity_irr": 0.22, "cpi": 1.05,
     "spi": 1.03, "pct_complete": 60, "milestones_late": 0, "variance_at_completion": 500000, "gmp": 1e7},
    {"id": "b", "name": "Laggard", "status": "behind", "equity_irr": 0.04, "cpi": 0.86,
     "spi": 0.88, "pct_complete": 30, "milestones_late": 4, "variance_at_completion": -800000, "gmp": 1e7},
    {"id": "c", "name": "Middle", "status": "at_risk", "equity_irr": 0.13, "cpi": 0.98,
     "spi": 0.99, "pct_complete": 45, "milestones_late": 1, "variance_at_completion": 0, "gmp": 1e7},
]
res = prioritization.rank(rows)
ranked = res["projects"]
assert [p["name"] for p in ranked] == ["Winner", "Middle", "Laggard"], [p["name"] for p in ranked]
assert ranked[0]["rank"] == 1 and ranked[-1]["rank"] == 3, ranked
assert ranked[0]["composite"] > ranked[1]["composite"] > ranked[2]["composite"], ranked
# scores are bounded 0-100 and every criterion present
for p in ranked:
    assert set(p["scores"]) == {"return", "budget", "schedule", "risk"}, p["scores"]
    assert all(0 <= v <= 100 for v in p["scores"].values()), p["scores"]
assert res["top"]["name"] == "Winner" and res["bottom"]["name"] == "Laggard", res
# weights normalize to 1
assert abs(sum(res["weights"].values()) - 1.0) < 1e-6, res["weights"]
print(f"prioritization: {[ (p['name'], p['composite']) for p in ranked ]}")

# custom weights (all on schedule) re-order toward the best scheduler
res2 = prioritization.rank(rows, weights={"return": 0, "budget": 0, "schedule": 1, "risk": 0})
assert res2["projects"][0]["name"] == "Winner", res2["projects"][0]

# --- endpoint smoke: a project with no data still ranks (default scores), returns 200 ------------
from fastapi.testclient import TestClient  # noqa: E402

from aec_api.main import app  # noqa: E402

with TestClient(app) as c:
    c.post("/projects", json={"name": "P1"})
    r = c.get("/portfolio/prioritization")
    assert r.status_code == 200, (r.status_code, r.text[:160])
    body = r.json()
    assert "projects" in body and body["criteria"] == ["return", "budget", "schedule", "risk"], body
    assert len(body["projects"]) >= 1 and body["projects"][0]["rank"] == 1, body

print("test_prioritization OK")

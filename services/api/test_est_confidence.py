"""EST-CONFIDENCE — per-line estimate maturity/confidence from source + phase → cost-weighted project
confidence + '% still assumption-based' + worst-value least-grounded lines.
Run: PYTHONPATH="src;../data/src" ./.venv/Scripts/python.exe test_est_confidence.py"""
import os

os.environ["DATABASE_URL"] = "sqlite:///./test_est_confidence.db"
os.environ["STORAGE_DIR"] = "./test_storage_estconf"
os.environ.pop("AEC_RBAC", None)

from aec_api import est_confidence as ec  # noqa: E402

lines = [
    {"description": "Slab concrete (measured)", "cost": 100000, "source": "model", "phase": "CD"},   # firm
    {"description": "Sitework allowance", "cost": 50000, "source": "allowance", "phase": "SD"},        # soft
    {"description": "Steel (quoted)", "cost": 30000, "source": "quote", "phase": "DD"},                # firm
    {"description": "Facade (parametric)", "cost": 20000, "source": "assembly", "phase": "concept",
     "contingency_pct": 25},                                                                          # soft + hi-cont
]
r = ec.score(lines)
assert r["line_count"] == 4 and r["total_cost"] == 200000, r
assert r["confidence"] == 0.739 and r["band"] == "medium", r          # cost-weighted 147880/200000
assert r["pct_assumption_based"] == 0.35 and r["assumption_based_cost"] == 70000, r
assert r["cost_by_band"] == {"high": 130000, "medium": 0, "low": 70000}, r["cost_by_band"]
assert r["avg_contingency_pct"] == 2.5, r["avg_contingency_pct"]        # (25×20000)/200000

by = {x["description"]: x for x in r["lines"]}
assert by["Slab concrete (measured)"]["confidence"] == 0.95 and by["Slab concrete (measured)"]["band"] == "high"
assert by["Sitework allowance"]["band"] == "low" and by["Sitework allowance"]["assumption_based"] is True
assert by["Steel (quoted)"]["confidence"] == 0.828 and by["Steel (quoted)"]["assumption_based"] is False
assert by["Facade (parametric)"]["high_contingency"] is True and by["Facade (parametric)"]["confidence"] == 0.562
# worst = highest-value least-grounded first (the allowance, lowest confidence)
assert r["worst_lines"][0]["source"] == "allowance", r["worst_lines"][0]

# empty input is well-formed
e = ec.score([])
assert e["line_count"] == 0 and e["confidence"] == 0.0 and e["pct_assumption_based"] == 0.0, e

# --- route: 404 missing project; 200 with lines ----------------------------------------------------
if os.path.exists("./test_est_confidence.db"):
    os.remove("./test_est_confidence.db")
from fastapi.testclient import TestClient  # noqa: E402

from aec_api.main import app  # noqa: E402

with TestClient(app) as c:
    assert c.post("/projects/nope/estimate/confidence", json={"lines": lines}).status_code == 404
    pid = c.post("/projects", json={"name": "Est"}).json()["id"]
    rr = c.post(f"/projects/{pid}/estimate/confidence", json={"lines": lines})
    assert rr.status_code == 200, rr.text
    j = rr.json()
    assert j["confidence"] == 0.739 and j["pct_assumption_based"] == 0.35, j

print("EST-CONFIDENCE OK - each estimate line is scored from source firmness (measured/quote > parametric/"
      "assembly > allowance/manual) modulated by design phase (CD > DD > SD): a measured CD slab is 0.95 "
      "(high), a quoted DD steel line 0.828 (high), an SD sitework allowance 0.336 (low, assumption-based), a "
      "concept parametric facade 0.562 (low, high-contingency flagged); cost-weighted the project is 0.739 "
      "(medium) with 35% of budget still assumption-based, and the worst-value least-grounded line (the "
      "allowance) surfaces first; the /estimate/confidence route 404s on a missing project.")

"""CONCEPT-BUDGET — massing program × own-history rates (escalated), p25–p75 range, default fallback,
UNPRICED surfaced. Run: PYTHONPATH="src;../data/src" ./.venv/Scripts/python.exe test_concept_budget.py"""
import os

os.environ["DATABASE_URL"] = "sqlite:///./test_concept_budget.db"
os.environ["STORAGE_DIR"] = "./test_storage_conceptb"
os.environ.pop("AEC_RBAC", None)

from aec_api import concept_budget as cb  # noqa: E402

history = [
    {"building_type": "Office", "gfa": 100_000, "actual_cost": 30_000_000, "year": 2024},   # 300/SF
    {"building_type": "Office", "gfa": 50_000, "actual_cost": 17_500_000, "year": 2024},    # 350/SF
    {"building_type": "Office", "gfa": 80_000, "actual_cost": 32_000_000, "year": 2024},    # 400/SF
    {"building_type": "Residential", "gfa": 60_000, "actual_cost": 15_000_000, "year": 2024},  # 250/SF
    {"building_type": "Bad", "gfa": 0, "actual_cost": 1},                                    # skipped
]

# --- rates: per-type stats, no escalation ----------------------------------------------------------
r = cb.derive_rates(history)
assert r["projects_used"] == 4 and r["projects_skipped"] == 1, r
off = r["rates"]["office"]
assert off["n"] == 3 and off["median"] == 350.0 and off["p25"] == 325.0 and off["p75"] == 375.0, off
assert r["rates"]["residential"]["median"] == 250.0, r["rates"]

# escalation: 2024 → 2026 at 5%/yr compounds ×1.1025
r2 = cb.derive_rates(history, to_year=2026, escalation_pct=5.0)
assert r2["rates"]["office"]["median"] == round(350 * 1.1025, 2), r2["rates"]["office"]

# --- budget: median × gfa, p25–p75 range, default fallback, UNPRICED surfaced ----------------------
program = [
    {"use": "Office", "gfa": 200_000, "stories": 10},
    {"use": "Retail", "gfa": 20_000},                       # no history → default rate
    {"use": "Lab", "gfa": 10_000},                          # no history, but default covers it
]
b = cb.budget(program, r, default_rate=500, contingency_pct=10)
assert b["line_count"] == 3 and b["unpriced"] == 0, b
l0 = b["lines"][0]
assert l0["cost"] == 70_000_000 and l0["source"] == "own-history (n=3)", l0
assert l0["range"] == {"low": 65_000_000, "high": 75_000_000}, l0["range"]
assert b["lines"][1]["cost"] == 10_000_000 and b["lines"][1]["source"] == "default rate", b["lines"][1]
assert b["subtotal"] == 85_000_000 and b["contingency"] == 8_500_000 and b["total"] == 93_500_000, b
assert b["range"]["low"] == 88_500_000 and b["range"]["high"] == 98_500_000, b["range"]

# no default → UNPRICED, never guessed
nb = cb.budget([{"use": "Datacenter", "gfa": 5000}], r)
assert nb["unpriced"] == 1 and nb["lines"][0]["source"].startswith("UNPRICED"), nb

# --- route -----------------------------------------------------------------------------------------
if os.path.exists("./test_concept_budget.db"):
    os.remove("./test_concept_budget.db")
from fastapi.testclient import TestClient  # noqa: E402

from aec_api.main import app  # noqa: E402

with TestClient(app) as c:
    assert c.post("/projects/nope/estimate/concept-budget", json={"program": program}).status_code == 404
    pid = c.post("/projects", json={"name": "Concept"}).json()["id"]
    rr = c.post(f"/projects/{pid}/estimate/concept-budget",
                json={"program": program, "history": history, "default_rate": 500, "contingency_pct": 10})
    assert rr.status_code == 200, rr.text
    j = rr.json()
    assert j["total"] == 93_500_000 and j["rates"]["rates"]["office"]["n"] == 3, j["total"]

print("CONCEPT-BUDGET OK - three own office projects (300/350/400 per SF) yield a median 350 with p25 325 / "
      "p75 375 (escalating 2024→2026 at 5%/yr compounds to 385.88); a 200k SF office massing prices at $70M "
      "(range $65–75M, source own-history n=3), retail/lab fall back to the $500 default, a use with no "
      "history and no default is UNPRICED rather than guessed; $85M subtotal + 10% contingency = $93.5M "
      "(range $88.5–98.5M); the /estimate/concept-budget route derives rates from history and prices the "
      "program in one call.")

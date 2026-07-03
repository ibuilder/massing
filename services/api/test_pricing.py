"""Takeoff pricing — price quantities from the built-in book + variance vs estimate; live bridge off.
Run: PYTHONPATH=src ./.venv/Scripts/python.exe test_pricing.py"""
import os

os.environ["DATABASE_URL"] = "sqlite:///./test_pricing.db"
os.environ["STORAGE_DIR"] = "./test_storage_pricing"
os.environ.pop("AEC_RBAC", None)
os.environ.pop("PRICING_PROVIDER", None)
for _f in ("./test_pricing.db",):
    if os.path.exists(_f):
        os.remove(_f)

from fastapi.testclient import TestClient           # noqa: E402
from aec_api import pricing, pricing_bridge           # noqa: E402
from aec_api.main import app                          # noqa: E402

assert pricing_bridge.is_enabled() is False and pricing_bridge.unit_price("concrete", "cy") is None

# --- engine ---
r = pricing.reconcile([
    {"description": "concrete footings", "quantity": 100, "unit": "cy", "estimated_unit_price": 200, "cost_code": "03-3000"},
    {"description": "drywall", "quantity": 5000, "unit": "sf"},
    {"description": "concrete", "quantity": 10, "unit": "kg"},          # unit != book unit (cy) -> flagged
    {"description": "unobtainium", "quantity": 3, "unit": "ea"},        # no match
])
concrete = r["lines"][0]
assert concrete["priced_amount"] == 100 * 185.0 and concrete["source"] == "book", concrete
# estimate was $200/cy vs book $185 -> negative variance (book cheaper)
assert concrete["variance"] == round(100 * 185 - 100 * 200, 2) and concrete["variance_pct"] == -7.5, concrete
assert r["lines"][1]["priced_amount"] == 5000 * 2.75, r["lines"][1]
assert r["lines"][2]["priced_amount"] is None and "unit" in r["lines"][2]["note"], r["lines"][2]
assert r["lines"][3]["matched"] is None, r["lines"][3]
assert r["matched"] == 2 and r["pricing_source"] == "book", r
assert r["priced_total"] == round(100 * 185 + 5000 * 2.75, 2), r

# --- endpoint from production_quantity ---
with TestClient(app) as c:
    pid = c.post("/projects", json={"name": "P"}).json()["id"]
    c.post(f"/projects/{pid}/modules/production_quantity",
           json={"data": {"description": "CMU wall", "quantity": 2000, "unit": "sf", "cost_code": "04-2000"}})
    pr = c.get(f"/projects/{pid}/pricing/reconcile").json()
    assert pr["matched"] == 1 and pr["priced_total"] == 2000 * 13.5, pr
    assert c.get("/pricing/status").json()["enabled"] is False

print("PRICING OK - book-priced takeoff (concrete/drywall/cmu); variance vs estimate (-7.5%); unit "
      "mismatch + unmatched material flagged (no guess); live bridge off falls back to the book")

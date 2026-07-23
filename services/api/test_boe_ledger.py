"""BOE-LEDGER — the Basis-of-Estimate assumption ledger: documentation completeness, assumption drift
between versions, and assumption→actual variance decomposed exactly into qty vs price effects.
Run: PYTHONPATH="src;../data/src" ./.venv/Scripts/python.exe test_boe_ledger.py"""
import os

os.environ["DATABASE_URL"] = "sqlite:///./test_boe_ledger.db"
os.environ["STORAGE_DIR"] = "./test_storage_boe"
os.environ.pop("AEC_RBAC", None)

from aec_api import boe_ledger as bl  # noqa: E402

sd = [
    {"cost_code": "03-30", "description": "Concrete", "phase": "SD", "qty": 100, "unit_cost": 500,
     "source": "allowance", "escalation_pct": 3, "contingency_pct": 15, "basis_date": "2026-01-10"},
    {"cost_code": "05-12", "description": "Steel", "phase": "SD", "qty": 20, "unit_cost": 3000,
     "source": "historical", "basis_date": "2026-01-10"},
]
dd = [
    {"cost_code": "03-30", "description": "Concrete", "phase": "DD", "qty": 110, "unit_cost": 520,
     "source": "quote", "quote_ref": "Q-118", "escalation_pct": 5, "contingency_pct": 10,
     "basis_date": "2026-04-02"},
    {"cost_code": "05-12", "description": "Steel", "phase": "DD", "qty": 20, "unit_cost": 3000,
     "source": "historical"},                                             # basis_date dropped → undocumented
    {"cost_code": "09-20", "description": "Finishes", "phase": "DD", "qty": 1, "unit_cost": 40000,
     "source": "quote"},                                                  # quote WITHOUT quote_ref → flagged
]

# --- ledger: documentation completeness ------------------------------------------------------------
led = bl.ledger(dd)
assert led["line_count"] == 3 and led["documented"] == 1 and led["pct_documented"] == 0.333, led
missing = {i["key"]: i["missing"] for i in led["undocumented"]}
assert missing["05-12"] == ["basis_date"], missing
assert set(missing["09-20"]) == {"basis_date", "quote_ref"}, missing

# --- phase drift SD→DD -----------------------------------------------------------------------------
pd = bl.phase_diff(sd, dd)
assert pd["compared"] == 2 and pd["changed"] == 1 and pd["added"] == ["09-20"] and pd["removed"] == [], pd
ch = pd["changes"][0]
assert ch["key"] == "03-30" and ch["total_delta"] == 7200.0, ch          # 110×520 − 100×500
fields = {c["field"]: (c["from"], c["to"]) for c in ch["changes"]}
assert fields["qty"] == (100, 110) and fields["unit_cost"] == (500, 520), fields
assert fields["source"] == ("allowance", "quote") and fields["escalation_pct"] == (3, 5), fields

# --- vs actuals: exact qty/price decomposition -----------------------------------------------------
actuals = [{"cost_code": "03-30", "qty": 120, "cost": 66000},            # 120 @ 550 vs assumed 110 @ 520
           {"cost_code": "05-12", "qty": 20, "cost": 58000}]             # 20 @ 2900 vs assumed 20 @ 3000
va = bl.vs_actuals(dd, actuals)
assert va["matched"] == 2, va
r0 = va["rows"][0]
assert r0["key"] == "03-30" and r0["variance"] == 8800.0, r0             # 66000 − 57200
assert r0["qty_effect"] == 5200.0 and r0["price_effect"] == 3600.0, r0   # (10×520) + (120×30)
assert round(r0["qty_effect"] + r0["price_effect"], 2) == r0["variance"], "decomposition must sum exactly"
assert r0["driver"] == "quantity", r0
r1 = va["rows"][1]
assert r1["variance"] == -2000.0 and r1["qty_effect"] == 0.0 and r1["driver"] == "price", r1
assert va["total_variance"] == 6800.0 and va["qty_effect"] == 5200.0 and va["price_effect"] == 1600.0, va

assert bl.ledger([])["pct_documented"] == 1.0                             # empty well-formed

# --- route -----------------------------------------------------------------------------------------
if os.path.exists("./test_boe_ledger.db"):
    os.remove("./test_boe_ledger.db")
from fastapi.testclient import TestClient  # noqa: E402

from aec_api.main import app  # noqa: E402

with TestClient(app) as c:
    assert c.post("/projects/nope/estimate/boe", json={"lines": dd}).status_code == 404
    pid = c.post("/projects", json={"name": "BoE"}).json()["id"]
    rr = c.post(f"/projects/{pid}/estimate/boe", json={"lines": dd, "prev": sd, "actuals": actuals})
    assert rr.status_code == 200, rr.text
    j = rr.json()
    assert j["ledger"]["pct_documented"] == 0.333 and j["phase_diff"]["changed"] == 1, j
    assert j["vs_actuals"]["total_variance"] == 6800.0, j["vs_actuals"]

print("BOE-LEDGER OK - the assumption ledger flags the undocumented basis (a quote line without a quote_ref, "
      "a line missing its basis date → 33% documented); SD→DD drift shows concrete re-based 100→110 qty and "
      "500→520 unit cost with the source upgraded allowance→quote (+$7,200, escalation 3→5%); against actuals "
      "the $8,800 concrete miss decomposes EXACTLY into $5,200 quantity effect + $3,600 price effect "
      "(quantity-driven) while steel's −$2,000 is pure price; the /estimate/boe route returns all three reads.")

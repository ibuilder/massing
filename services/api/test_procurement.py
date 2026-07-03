"""Materials procure-to-pay — quote leveling + 3-way match (PO<->delivery<->invoice) + RFQ bridge off.
Run: PYTHONPATH=src ./.venv/Scripts/python.exe test_procurement.py"""
import os

os.environ["DATABASE_URL"] = "sqlite:///./test_procurement.db"
os.environ["STORAGE_DIR"] = "./test_storage_procurement"
os.environ.pop("AEC_RBAC", None)
os.environ.pop("RFQ_PROVIDER", None)
for _f in ("./test_procurement.db",):
    if os.path.exists(_f):
        os.remove(_f)

from fastapi.testclient import TestClient           # noqa: E402
from aec_api import procurement, procurement_bridge   # noqa: E402
from aec_api.main import app                          # noqa: E402

# --- RFQ bridge off; never pretends to send ---
assert procurement_bridge.is_enabled() is False
try:
    procurement_bridge.send_rfq(["A"], [{"item": "rebar"}]); raise AssertionError("should refuse")
except RuntimeError as e:
    assert "not configured" in str(e), e

# --- quote leveling ---
q = procurement.level_quotes([
    {"supplier": "ABC Supply", "lines": [{"item": "Rebar #5", "qty": 1000, "unit": "lb", "unit_price": 1.20},
                                         {"item": "Concrete 4000psi", "qty": 100, "unit": "cy", "unit_price": 190}]},
    {"supplier": "BuildMart", "lines": [{"item": "Rebar #5", "qty": 1000, "unit": "lb", "unit_price": 1.05},
                                        {"item": "Concrete 4000psi", "qty": 100, "unit": "cy", "unit_price": 205}]},
])
rebar = next(r for r in q["items"] if "rebar" in r["item"].lower())
assert rebar["low_supplier"] == "BuildMart" and rebar["low_price"] == 1.05, rebar
conc = next(r for r in q["items"] if "concrete" in r["item"].lower())
assert conc["low_supplier"] == "ABC Supply", conc          # split award: cheapest differs per line
assert q["supplier_totals"]["BuildMart"] == round(1000*1.05 + 100*205, 2), q["supplier_totals"]
assert q["line_by_line_savings"] > 0

# --- 3-way match ---
with TestClient(app) as c:
    pid = c.post("/projects", json={"name": "P"}).json()["id"]
    # PO (commitment) $50k to Ace for cost code 03-2000
    po = c.post(f"/projects/{pid}/modules/commitment",
                json={"data": {"description": "Rebar PO", "vendor": "Ace", "amount": 50000, "cost_code": "03-2000"}}).json()
    # a delivery received against the PO
    dr = c.post(f"/projects/{pid}/modules/delivery",
                json={"data": {"description": "Rebar load", "date": "2024-02-01", "supplier": "Ace",
                               "commitment": po["id"], "status": "received"}})
    assert dr.status_code == 201, dr.text[:160]
    # an invoice for MORE than the PO (over-billing) from Ace on the same cost code
    c.post(f"/projects/{pid}/modules/sub_invoice",
           json={"data": {"vendor": "Ace", "amount": 60000, "cost_code": "03-2000"}})

    m = c.get(f"/projects/{pid}/procurement/three-way-match").json()
    row = next(r for r in m["pos"] if r["vendor"] == "Ace")
    assert row["po_amount"] == 50000 and row["received"] == 1 and row["invoiced"] == 60000, row
    assert row["variance"] == 10000 and row["status"] == "review", row
    assert any("exceeds PO" in f for f in row["flags"]), row["flags"]
    assert m["flagged"] == [row["po"]], m
    assert c.get("/procurement/rfq-status").json()["enabled"] is False

print("PROCUREMENT OK - quote leveling (split award: rebar->BuildMart, concrete->ABC; totals + "
      "savings); 3-way match flags $60k invoice > $50k PO (over-billing) with a received delivery; "
      "RFQ bridge off + never fabricates a send")

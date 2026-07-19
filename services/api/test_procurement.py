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

from fastapi.testclient import TestClient  # noqa: E402

from aec_api import procurement, procurement_bridge  # noqa: E402
from aec_api.main import app  # noqa: E402

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

    # --- PROC-LOOP price-observation ledger: level with record=true → durable observations ---------
    quotes = [
        {"supplier": "ABC Supply", "lines": [{"item": "Rebar #5", "qty": 1000, "unit": "lb", "unit_price": 1.20}]},
        {"supplier": "BuildMart", "lines": [{"item": "Rebar #5", "qty": 1000, "unit": "lb", "unit_price": 1.05},
                                            {"item": "Junk", "unit_price": 0}]},          # unpriced → skipped
    ]
    lv = c.post(f"/projects/{pid}/procurement/level-quotes?record=true", json={"quotes": quotes}).json()
    assert lv["recorded_observations"] == 2, lv
    # a later manual observation moves the ledger's latest + drift
    c.post(f"/projects/{pid}/modules/price_observation",
           json={"data": {"material": "Rebar #5", "unit_price": 1.50, "unit": "lb",
                          "vendor": "SteelCo", "date": "2099-01-01", "source": "manual"}})
    ph = c.get(f"/projects/{pid}/procurement/price-history").json()
    mat = next(x for x in ph["materials"] if "rebar" in x["material"].lower())
    assert mat["observations"] == 3 and mat["min"] == 1.05 and mat["max"] == 1.5, mat
    assert mat["median"] == 1.2 and mat["latest"]["vendor"] == "SteelCo", mat
    assert mat["latest_vs_median_pct"] == 25.0, mat                    # 1.50 vs 1.20 median
    assert set(mat["vendors"]) == {"ABC Supply", "BuildMart", "SteelCo"}, mat
    assert len(mat["series"]) == 3, mat
    # ?material= filters to one canonical material
    only = c.get(f"/projects/{pid}/procurement/price-history?material=Rebar%20%235").json()
    assert only["material_count"] == 1, only

    # --- PROC-LOOP material requests: pure QTO suggestion maths + the module round-trip ------------
    rows_tk = [{"guid": "w1", "ifc_class": "IfcWall", "area": 10.0, "volume": 2.0},
               {"guid": "w2", "ifc_class": "IfcWall", "area": 12.0, "volume": 2.5},
               {"guid": "d1", "ifc_class": "IfcDoor", "area": None, "volume": None}]
    sug = procurement.suggest_material_requests(rows_tk, None)
    wall = next(s for s in sug if s["ifc_class"] == "IfcWall")
    assert wall["qty"] == 4.5 and wall["unit"] == "m3" and wall["elements"] == 2, wall  # volume preferred
    door = next(s for s in sug if s["ifc_class"] == "IfcDoor")
    assert door["qty"] == 1 and door["unit"] == "ea", door                              # count fallback
    assert procurement.suggest_material_requests(rows_tk, {"d1"}) == [door | {"guids": ["d1"]}], "guid narrowing"
    # the module workflow: requested → approved → ordered → delivered
    mr = c.post(f"/projects/{pid}/modules/material_request",
                json={"data": {"material": "Wall", "qty": 4.5, "unit": "m3", "guids": "w1 w2"}}).json()
    assert mr["workflow_state"] == "requested", mr
    for a in ("approve", "order", "receive"):
        tr = c.post(f"/projects/{pid}/modules/material_request/{mr['id']}/transition", json={"action": a})
        assert tr.status_code == 200, (a, tr.text[:160])
    got = c.get(f"/projects/{pid}/modules/material_request/{mr['id']}").json()
    assert got["workflow_state"] == "delivered", got
    # the suggest route is registered; a bad selector 422s (no model needed for the check)
    assert "/projects/{pid}/procurement/material-request/suggest" in app.openapi()["paths"]
    bad = c.post(f"/projects/{pid}/procurement/material-request/suggest", json={"q": ""})
    assert bad.status_code == 422 and "bad selector" in bad.json()["detail"], bad.text

print("PROCUREMENT OK - quote leveling (split award: rebar->BuildMart, concrete->ABC; totals + "
      "savings); 3-way match flags $60k invoice > $50k PO (over-billing) with a received delivery; "
      "RFQ bridge off + never fabricates a send. PROC-LOOP: record=true persists priced quote lines "
      "as price_observations (unpriced skipped); the ledger rolls up min/median/max + latest + "
      "+25% latest-vs-median drift + vendors + series, ?material= filters canonically; QTO "
      "suggestions prefer volume>area>count with GUID narrowing; material_request walks "
      "requested→approved→ordered→delivered; empty selector 422s")

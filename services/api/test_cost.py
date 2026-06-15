"""G702/G703 + Cost Summary test. Run: PYTHONPATH=src ./.venv/Scripts/python.exe test_cost.py"""
import os

os.environ["DATABASE_URL"] = "sqlite:///./test_cost.db"
os.environ["STORAGE_DIR"] = "./test_storage"

for f in ("./test_cost.db",):
    if os.path.exists(f):
        os.remove(f)

from fastapi.testclient import TestClient  # noqa: E402
from aec_api.main import app  # noqa: E402

with TestClient(app) as c:
    pid = c.post("/projects", json={"name": "Mega Tower"}).json()["id"]

    # Schedule of Values: 3 line items
    sov = [
        {"item_no": "01", "description": "Mobilization", "scheduled_value": 100000,
         "completed_prev": 100000, "completed_this": 0, "retainage_pct": 5},
        {"item_no": "02", "description": "Concrete", "scheduled_value": 500000,
         "completed_prev": 200000, "completed_this": 150000, "materials_stored": 50000, "retainage_pct": 5},
        {"item_no": "03", "description": "Steel", "scheduled_value": 400000,
         "completed_prev": 0, "completed_this": 100000, "retainage_pct": 5},
    ]
    for line in sov:
        r = c.post(f"/projects/{pid}/modules/sov", json={"data": line})
        assert r.status_code == 201, r.text

    # an approved change order rolls into the contract sum
    cor = c.post(f"/projects/{pid}/modules/cor", json={"data": {"subject": "Added scope", "amount": 75000}}).json()
    c.post(f"/projects/{pid}/modules/cor/{cor['id']}/transition", json={"action": "submit"})
    c.post(f"/projects/{pid}/modules/cor/{cor['id']}/transition", json={"action": "approve"})

    # commitments + direct costs for the summary
    po = c.post(f"/projects/{pid}/modules/commitment", json={"data": {"description": "Concrete PO", "amount": 480000}}).json()
    c.post(f"/projects/{pid}/modules/commitment/{po['id']}/transition", json={"action": "execute"})
    c.post(f"/projects/{pid}/modules/direct_cost", json={"data": {"description": "Crew", "type": "Labor", "amount": 90000}})

    # ---- G703 ---------------------------------------------------------------
    g3 = c.get(f"/projects/{pid}/cost/g703").json()
    t = g3["totals"]
    assert t["scheduled"] == 1000000.0, t
    # completed+stored = 100000 + (200000+150000+50000) + 100000 = 600000
    assert t["completed"] == 600000.0, t
    assert t["retainage"] == round(600000 * 0.05, 2), t["retainage"]
    assert t["balance"] == 400000.0, t

    # ---- G702 (with change order) -------------------------------------------
    g7 = c.get(f"/projects/{pid}/cost/g702", params={"app_no": 2, "period": "2026-06"}).json()
    assert g7["line1_original_contract_sum"] == 1000000.0
    assert g7["line2_net_change_orders"] == 75000.0       # approved COR
    assert g7["line3_contract_sum_to_date"] == 1075000.0
    assert g7["line4_total_completed_stored"] == 600000.0
    assert g7["line5_retainage"] == 30000.0
    assert g7["line6_total_earned_less_retainage"] == 570000.0
    assert g7["line9_balance_to_finish_incl_retainage"] == round(1075000 - 570000, 2), g7

    # ---- Cost Summary -------------------------------------------------------
    s = c.get(f"/projects/{pid}/cost/summary").json()
    assert s["budget"] == 1075000.0, s            # SOV + approved CO
    assert s["committed"] == round(480000 + 75000, 2), s   # executed PO + approved CO
    assert s["actual"] == 90000.0, s              # direct cost
    assert s["projected_over_under"] == round(s["budget"] - s["forecast"], 2)

    # ---- G702 PDF -----------------------------------------------------------
    pdf = c.get(f"/projects/{pid}/cost/g702.pdf", params={"app_no": 2}).content
    assert pdf[:5] == b"%PDF-" and len(pdf) > 1500, len(pdf)

    print("COST OK")
    print(f"  G703 totals: scheduled={t['scheduled']:,} completed={t['completed']:,} retainage={t['retainage']:,}")
    print(f"  G702 current payment due: ${g7['line8_current_payment_due']:,.2f}  contract-to-date ${g7['line3_contract_sum_to_date']:,.2f}")
    print(f"  Summary: budget ${s['budget']:,} committed ${s['committed']:,} actual ${s['actual']:,} over/under ${s['projected_over_under']:,}")
    print(f"  G702 PDF: {len(pdf)} bytes")

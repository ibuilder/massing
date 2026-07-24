"""FIN-INGEST — actuals reconciliation (budget↔actuals matched both ways + uncoded rows) and
import lineage (audit-logged batches; the period lock catches locked-month import rows).
Run: PYTHONPATH="src;../data/src" ./.venv/Scripts/python.exe test_fin_ingest.py"""
import io
import os

os.environ["DATABASE_URL"] = "sqlite:///./test_fin_ingest.db"
os.environ["STORAGE_DIR"] = "./test_storage_fining"
os.environ.pop("AEC_RBAC", None)
if os.path.exists("./test_fin_ingest.db"):
    os.remove("./test_fin_ingest.db")

from fastapi.testclient import TestClient  # noqa: E402

from aec_api import fin_gov  # noqa: E402
from aec_api.main import app  # noqa: E402

with TestClient(app) as c:
    pid = c.post("/projects", json={"name": "Recon"}).json()["id"]

    def add(key, data):
        r = c.post(f"/projects/{pid}/modules/{key}", json={"data": data})
        assert r.status_code in (200, 201), r.text
        return r.json()

    # budget on 03-30 and 09-20; actuals on 03-30 (matched), 26-00 (actuals-only), one uncoded
    add("budget", {"cost_code": "03-30", "description": "Concrete", "original": 500_000})
    add("budget", {"cost_code": "09-20", "description": "Drywall", "original": 200_000})
    add("direct_cost", {"description": "Rebar", "cost_code": "03-30", "amount": 120_000,
                        "date": "2026-07-01"})
    add("direct_cost", {"description": "Switchgear", "cost_code": "26-00", "amount": 90_000,
                        "date": "2026-07-02"})
    add("direct_cost", {"description": "Mystery invoice", "amount": 15_000, "date": "2026-07-03"})

    r = c.get(f"/projects/{pid}/finance/reconcile")
    assert r.status_code == 200, r.text
    rec = r.json()
    codes = lambda rows: [x["cost_code"] for x in rows]  # noqa: E731
    assert any("03-30" in s for s in codes(rec["matched"])), rec["matched"]
    assert any("09-20" in s for s in codes(rec["budget_only"])), rec["budget_only"]
    assert any("26-00" in s for s in codes(rec["actuals_only"])), rec["actuals_only"]
    assert rec["counts"]["uncoded"] == 1 and rec["uncoded"][0]["amount"] == 15_000
    assert rec["fully_reconciled"] is False

    # ---- import lineage: a CSV import is audit-logged with its filename + counts
    csv = "description,cost_code,amount,date\nPumps,22-10,42000,2026-07-05\nValves,22-10,8000,2026-07-06\n"
    r = c.post(f"/projects/{pid}/modules/direct_cost/import",
               files={"file": ("july-actuals.csv", io.BytesIO(csv.encode()), "text/csv")},
               data={"mapping": '{"description":"description","cost_code":"cost_code",'
                                '"amount":"amount","date":"date"}'})
    assert r.status_code == 200 and r.json()["imported"] == 2, r.text
    hist = c.get(f"/projects/{pid}/finance/imports").json()
    assert hist and hist[0]["filename"] == "july-actuals.csv" and hist[0]["imported"] == 2, hist

    # ---- the period lock reaches imports: locked-month rows land in errors, not the ledger
    fin_gov.set_lock(pid, "2026-06", "cfo")
    csv2 = "description,cost_code,amount,date\nBackdated,03-30,999,2026-05-15\nCurrent,03-30,111,2026-07-15\n"
    r = c.post(f"/projects/{pid}/modules/direct_cost/import",
               files={"file": ("mixed.csv", io.BytesIO(csv2.encode()), "text/csv")},
               data={"mapping": '{"description":"description","cost_code":"cost_code",'
                                '"amount":"amount","date":"date"}'})
    body = r.json()
    assert body["imported"] == 1 and body["error_count"] == 1, body
    assert "locked" in body["errors"][0]["error"], body["errors"]

print("FIN-INGEST OK - /finance/reconcile matches budget<->actuals both ways on the cost-code spine "
      "(03-30 matched, 09-20 budget-only, 26-00 actuals-only, the $15k uncoded direct cost surfaced "
      "with its ref, fully_reconciled false); CSV imports are audit-logged as lineage batches "
      "(july-actuals.csv, 2 rows) served at /finance/imports; and with the books closed through "
      "2026-06 a backdated import row errors 'locked' while the current-month row lands.")

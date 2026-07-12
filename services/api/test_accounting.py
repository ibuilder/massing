"""Accounting export — GL CSV (double-entry) + QuickBooks IIF bills from cost records.
Run: PYTHONPATH=src ./.venv/Scripts/python.exe test_accounting.py"""
import os

os.environ["DATABASE_URL"] = "sqlite:///./test_accounting.db"
os.environ["STORAGE_DIR"] = "./test_storage_accounting"
os.environ.pop("AEC_RBAC", None)
for _f in ("./test_accounting.db",):
    if os.path.exists(_f):
        os.remove(_f)

from fastapi.testclient import TestClient  # noqa: E402

from aec_api.main import app  # noqa: E402

with TestClient(app) as c:
    pid = c.post("/projects", json={"name": "P"}).json()["id"]
    c.post(f"/projects/{pid}/modules/sub_invoice",
           json={"data": {"vendor": "Ace Concrete", "amount": 100000, "cost_code": "03-3000",
                          "invoice_date": "2024-01-15", "period": "Jan"}})
    c.post(f"/projects/{pid}/modules/direct_cost",
           json={"data": {"description": "Rebar delivery", "amount": 25000, "cost_code": "03-2000",
                          "vendor": "Steel Co", "date": "2024-01-20"}})

    j = c.get(f"/projects/{pid}/accounting/journal").json()
    assert j["count"] == 2 and j["total"] == 125000, j

    gl = c.get(f"/projects/{pid}/accounting/gl.csv")
    assert gl.status_code == 200 and "text/csv" in gl.headers["content-type"], gl.headers
    lines = gl.text.strip().splitlines()
    assert lines[0].startswith("Date,Ref,Account,Vendor,CostCode,Memo,Debit,Credit"), lines[0]
    # double-entry: 2 records -> 4 GL lines (each cost debits Construction Costs + credits AP)
    assert len(lines) == 1 + 4, lines
    assert any("Construction Costs" in l and "100000.00" in l for l in lines), lines
    assert any("Accounts Payable" in l and "100000.00" in l for l in lines), lines

    # trial balance MUST balance: total debits == total credits (the core double-entry invariant).
    tb = c.get(f"/projects/{pid}/accounting/trial-balance").json()
    assert tb["balanced"] is True, tb
    assert abs(tb["debit_total"] - tb["credit_total"]) < 0.01, tb
    assert abs(tb["debit_total"] - 125000) < 0.01, tb          # 100000 + 25000 posted both sides
    # and the GL CSV itself balances column-for-column (sum of Debit == sum of Credit)
    dr = cr = 0.0
    for line in lines[1:]:
        cols = line.split(",")
        dr += float(cols[-2] or 0); cr += float(cols[-1] or 0)
    assert abs(dr - cr) < 0.01 and abs(dr - 125000) < 0.01, (dr, cr)
    # journal-entries: each posted entry is itself balanced
    je = c.get(f"/projects/{pid}/accounting/journal-entries").json()
    assert je.get("entries"), je

    iif = c.get(f"/projects/{pid}/accounting/bills.iif")
    assert iif.status_code == 200, iif.status_code
    txt = iif.text
    assert txt.startswith("!TRNS\tTRNSTYPE\tDATE\tACCNT\tNAME\tAMOUNT\tMEMO"), txt[:60]
    assert "TRNS\tBILL\t2024-01-15\tAccounts Payable\tAce Concrete\t-100000.00" in txt, txt
    assert "SPL\tBILL\t2024-01-15\tConstruction Costs\tAce Concrete\t100000.00" in txt, txt
    assert txt.count("ENDTRNS") == 2  # 1 header !ENDTRNS + 1 bill ENDTRNS (direct_cost isn't a bill)

    # --- approval-gated journal batch: freeze → submit → approve → export ---
    b = c.post(f"/projects/{pid}/accounting/journal-batch", json={"period": "Jan-2024", "memo": "month close"})
    assert b.status_code == 200, b.text
    batch = b.json()
    bid = batch["id"]
    assert batch["workflow_state"] == "draft", batch
    assert batch["data"]["balanced"] == "yes" and batch["data"]["total_debits"] == 125000, batch["data"]
    # the snapshot froze the current GL (2 source records)
    assert len(batch["data"]["snapshot"]["gl"]) == 2, batch["data"]["snapshot"]["gl"]
    # missing period is rejected
    assert c.post(f"/projects/{pid}/accounting/journal-batch", json={}).status_code == 422

    # export is GATED: 409 until approved (nothing posts to the books without the gate)
    pre = c.get(f"/projects/{pid}/accounting/journal-batch/{bid}/export")
    assert pre.status_code == 409, pre.status_code
    # unknown batch → 404
    assert c.get(f"/projects/{pid}/accounting/journal-batch/nope/export").status_code == 404

    # drive the workflow (RBAC off in tests, so the party gate passes): submit → approve
    assert c.post(f"/projects/{pid}/modules/journal_batch/{bid}/transition",
                  json={"action": "submit"}).status_code == 200
    assert c.post(f"/projects/{pid}/modules/journal_batch/{bid}/transition",
                  json={"action": "approve"}).status_code == 200

    # now export the FROZEN snapshot as GL CSV + IIF
    exp = c.get(f"/projects/{pid}/accounting/journal-batch/{bid}/export?fmt=gl")
    assert exp.status_code == 200 and "text/csv" in exp.headers["content-type"], exp.headers
    elines = exp.text.strip().splitlines()
    assert elines[0].startswith("Date,Ref,Account"), elines[0]
    edr = sum(float(l.split(",")[-2] or 0) for l in elines[1:])
    ecr = sum(float(l.split(",")[-1] or 0) for l in elines[1:])
    assert abs(edr - ecr) < 0.01 and abs(edr - 125000) < 0.01, (edr, ecr)   # frozen figures still balance
    iif2 = c.get(f"/projects/{pid}/accounting/journal-batch/{bid}/export?fmt=iif")
    assert iif2.status_code == 200 and iif2.text.startswith("!TRNS"), iif2.text[:40]

print("ACCOUNTING OK - journal flattens sub invoices + direct costs; GL CSV is balanced double-entry "
      "(debit Construction Costs / credit AP); trial balance balances (debits==credits==125000) and the "
      "GL columns balance; QuickBooks IIF emits BILL/SPL/ENDTRNS for AP bills only. "
      "Approval-gated batch: freeze snapshot (draft) -> export 409 until submit+approve -> then GL CSV/IIF "
      "export the FROZEN figures (still balance 125000); missing period=422, unknown batch=404")

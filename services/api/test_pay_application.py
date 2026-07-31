"""MOD-G702 — the pay application as a document, and the retainage bug that exposed why it matters.

`estimate` gained `line_items`; the AIA G702/G703 pair did not. `sov` stayed one record per line with
no parent, so the continuation sheet was assembled by `cost.g703` on every read and the certificate by
`cost.g702` — both LIVE VIEWS over data that keeps moving. An application is a claim made on a date.

Two claims are asserted here and they fail for different reasons:

  1. THE MONEY. Line 5 used each SOV line's own `retainage_pct`; line 7 applied the global
     `DEFAULT_RETAINAGE` to the aggregate. Any contract not on the default rate made the two
     disagree, and on a 10% contract with work completed but none this period, line 8 — the current
     payment due, which `closeout.py` reads for the final-payment amount — came out NEGATIVE.

  2. THE FREEZE. A certificate reassembled on demand restates applications that were already signed
     and paid. Editing the SOV after an application is submitted must not change that application.

Run: PYTHONPATH=src ./.venv/Scripts/python.exe test_pay_application.py
"""
import os

os.environ["DATABASE_URL"] = "sqlite:///./test_pay_application.db"
os.environ["STORAGE_DIR"] = "./test_storage_g702"
os.environ.pop("AEC_RBAC", None)
for _f in ("./test_pay_application.db",):
    if os.path.exists(_f):
        os.remove(_f)

from fastapi.testclient import TestClient  # noqa: E402

from aec_api.main import app  # noqa: E402

FAILED = []


def check(label, ok, detail=None):
    print(f"{'PASS' if ok else 'FAIL'}  {label}{(' — ' + str(detail)) if detail and not ok else ''}")
    if not ok:
        FAILED.append(label)


with TestClient(app) as c:
    pid = c.post("/projects", json={"name": "G702 Tower"}).json()["id"]

    def sov(item, desc, sched, prev=0, this=0, stored=0, pct=None):
        d = {"item_no": item, "description": desc, "scheduled_value": sched,
             "completed_prev": prev, "completed_this": this, "materials_stored": stored}
        if pct is not None:
            d["retainage_pct"] = pct
        r = c.post(f"/projects/{pid}/modules/sov", json={"data": d})
        assert r.status_code in (200, 201), r.text[:200]
        return r.json()

    # --- 1. THE MONEY -------------------------------------------------------------------------------
    # One line, 10% retainage, $50k completed in earlier periods, nothing this period. Nothing is
    # owed and nothing is over-claimed: line 8 must be exactly zero.
    a = sov("01", "Sitework", 100000, prev=50000, pct=10)
    g = c.get(f"/projects/{pid}/cost/g702").json()
    check("  line5 uses the per-line 10% rate", g["line5_retainage"] == 5000.0, g["line5_retainage"])
    check("  line7 uses the SAME rate, not the 5% default",
          g["line7_less_previous_certificates"] == 45000.0, g["line7_less_previous_certificates"])
    check("  line8 current payment due is 0.00, not -2500.00",
          g["line8_current_payment_due"] == 0.0, g["line8_current_payment_due"])
    check("  and it is not negative", g["line8_current_payment_due"] >= 0, g["line8_current_payment_due"])

    # the default rate still applies where a line declares none — the fix is consistency, not a
    # behaviour change for contracts that were always on 5%
    b = sov("02", "Concrete", 100000, prev=50000)
    g = c.get(f"/projects/{pid}/cost/g702").json()
    check("  a line with no rate still retains at the 5% default",
          g["line5_retainage"] == 5000.0 + 2500.0, g["line5_retainage"])
    check("  mixed rates: line 8 still zero", g["line8_current_payment_due"] == 0.0,
          g["line8_current_payment_due"])
    c.delete(f"/projects/{pid}/modules/sov/{b['id']}")

    # real work this period, so there is genuinely something due
    c.patch(f"/projects/{pid}/modules/sov/{a['id']}", json={"completed_this": 20000})
    g = c.get(f"/projects/{pid}/cost/g702").json()
    # completed 70k; retainage 7k; earned 63k; previously certified 50k − 5k = 45k; due 18k
    check("  $20k of work at 10% retainage is $18,000 due",
          g["line8_current_payment_due"] == 18000.0, g["line8_current_payment_due"])

    # --- 2. THE FREEZE ------------------------------------------------------------------------------
    made = c.post(f"/projects/{pid}/cost/pay-application",
                  json={"period_from": "2026-07-01", "period_to": "2026-07-31"})
    check("  POST /cost/pay-application creates a record", made.status_code == 201, made.text[:200])
    app1 = made.json()
    d1 = app1["data"]
    check("  it is a DRAFT — a certificate nobody signed is not a certificate",
          app1["workflow_state"] == "draft", app1["workflow_state"])
    check("  the continuation sheet is STORED, not assembled on read",
          isinstance(d1.get("line_items"), list) and len(d1["line_items"]) == 1, d1.get("line_items"))
    check("  the stored line carries the G703 computed columns",
          d1["line_items"][0]["total_completed_stored"] == 70000.0, d1["line_items"][0])
    check("  line 8 is frozen into the document", d1["current_payment_due"] == 18000.0,
          d1["current_payment_due"])
    check("  and the period it covers is recorded", d1["period_to"] == "2026-07-31", d1["period_to"])

    # submit it, then move the SOV underneath it
    tr = c.post(f"/projects/{pid}/modules/owner_invoice/{app1['id']}/transition",
                json={"action": "submit"})
    check("  it can be submitted", tr.status_code == 200, tr.text[:200])
    c.patch(f"/projects/{pid}/modules/sov/{a['id']}", json={"scheduled_value": 250000,
                                                            "completed_this": 90000})
    still = c.get(f"/projects/{pid}/modules/owner_invoice/{app1['id']}").json()["data"]
    check("  a submitted application does NOT restate itself when the SOV moves",
          still["current_payment_due"] == 18000.0, still["current_payment_due"])
    check("  nor does its continuation sheet",
          still["line_items"][0]["scheduled_value"] == 100000.0, still["line_items"][0])

    # --- 3. line 7 now reads a FACT rather than a reconstruction ------------------------------------
    # App 1 certified $18,000 on top of $45,000 previously → $63,000 certified to date. The live G702
    # must deduct that, and it must NOT be re-derived from `completed_prev`, which the SOV edit above
    # has since changed.
    g = c.get(f"/projects/{pid}/cost/g702").json()
    check("  line 7 comes from the submitted certificate, not from completed_prev",
          g["line7_less_previous_certificates"] == 63000.0, g["line7_less_previous_certificates"])

    app2 = c.post(f"/projects/{pid}/cost/pay-application", json={"period_to": "2026-08-31"}).json()
    check("  the next application numbers itself", app2["data"]["number"] == "2", app2["data"]["number"])
    check("  and deducts what app 1 certified",
          app2["data"]["previous_certificates"] == 63000.0, app2["data"]["previous_certificates"])
    # completed 140k (50k prev + 90k this); retainage 14k; earned 126k; less 63k = 63k due
    check("  so app 2 asks for the increment only", app2["data"]["current_payment_due"] == 63000.0,
          app2["data"]["current_payment_due"])

    # an architect who certifies LESS than was applied for is what a later application must deduct
    c.post(f"/projects/{pid}/modules/owner_invoice/{app2['id']}/transition", json={"action": "submit"})
    c.patch(f"/projects/{pid}/modules/owner_invoice/{app2['id']}",
            json={"architect_certified_amount": 50000})
    g = c.get(f"/projects/{pid}/cost/g702").json()
    check("  a reduced certification is what counts, not the amount applied for",
          g["line7_less_previous_certificates"] == 113000.0, g["line7_less_previous_certificates"])

    # a DRAFT certifies nothing — it has been signed by nobody
    draft = c.post(f"/projects/{pid}/cost/pay-application", json={}).json()
    g2 = c.get(f"/projects/{pid}/cost/g702").json()
    check("  an unsubmitted draft does not move line 7",
          g2["line7_less_previous_certificates"] == 113000.0, g2["line7_less_previous_certificates"])
    assert draft["workflow_state"] == "draft"

    # --- 4. the form is a form ----------------------------------------------------------------------
    mods = {m["key"]: m for m in c.get("/modules").json()}
    oi = mods["owner_invoice"]
    names = {f["name"] for f in oi["fields"]}
    for need, why in [("period_from", "an application covers a period, not a vibe"),
                      ("retainage_work_pct", "G702 5a"),
                      ("retainage_stored_pct", "G702 5b — stored material is retained separately"),
                      ("contractor_signature", "the contractor's certification IS the G702"),
                      ("architect_certified_amount", "the architect may certify less than applied for"),
                      ("coi", "a pay app travels with insurance"),
                      ("lien_waiver", "and with a waiver")]:
        check(f"  owner_invoice carries `{need}` ({why})", need in names)
    lt = next(f for f in oi["fields"] if f["name"] == "line_items")
    check("  the continuation sheet totals into line 4", lt.get("totals_into") == "amount",
          lt.get("totals_into"))

print()
if FAILED:
    print(f"PAY-APPLICATION FAILED ({len(FAILED)}): " + "; ".join(FAILED))
    raise SystemExit(1)
print("PAY-APPLICATION OK - G702 line 7 now retains at each line's own rate, so a 10% contract no "
      "longer reports a NEGATIVE payment due (closeout.py reads that number); POST /cost/pay-application "
      "freezes the G703 continuation sheet and lines 1-9 into an owner_invoice, so editing the SOV "
      "cannot restate an application already submitted; and line 7 deducts what was actually "
      "certified — including a reduced architect certification — instead of reconstructing it.")

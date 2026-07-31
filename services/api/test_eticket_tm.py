"""MOD-TOTALS / T&M — an eTicket itemises labour, material and equipment, and the lines drive the total.

A time-and-material ticket is the record of *work done on a day at agreed rates*. The register had
six fields: a subject, a date, three totals somebody typed in, and a link. The rate libraries
(`labor_rate`, `material_rate`, `equipment_rate`) existed and **nothing consumed them** — the sweep's
sharpest finding, and the one idea the user's own earlier Django app had that this platform lacked:
its `ticket` model composes the rate tables into totals.

Two things are asserted here and they are the whole point:

**1. The lines drive the total, on create and on update.** `tm.summarize` reads
`eticket.labor_total`; the rows live in `labor_lines`. Before `totals_into` those were two facts a
human kept in agreement by hand, and every later edit could silently disagree with its own lines. A
PATCH touching only the lines must move the total — otherwise the summary outlives the evidence.

**2. The rate is SNAPSHOT, not referenced.** A T&M line stores the rate it was worked at. If it
referenced `labor_rate`, updating that library would retroactively change what a contractor is owed
for work done last month — an accounting error, not a modelling preference. The `table` type forbids
reference columns for its own reasons; here the constraint and the correct domain model agree, and
this test pins the behaviour so a future "improvement" to link them has to argue with it.

Run: PYTHONPATH=src ./.venv/Scripts/python.exe test_eticket_tm.py
"""
import os

os.environ["DATABASE_URL"] = "sqlite:///./test_eticket_tm.db"
os.environ["STORAGE_DIR"] = "./test_storage_eticket_tm"
os.environ["AEC_TRUST_XUSER"] = "1"

for _f in ("./test_eticket_tm.db",):
    if os.path.exists(_f):
        os.remove(_f)

from fastapi.testclient import TestClient  # noqa: E402

from aec_api.main import app  # noqa: E402
from aec_api.modules import apply_table_totals  # noqa: E402
from aec_api.tm import summarize  # noqa: E402

H = {"X-User": "gc"}

# ---- 1. the pure function, before any HTTP ------------------------------------------------------
MOD = {"fields": [
    {"name": "labor_total", "type": "currency"},
    {"name": "labor_lines", "type": "table", "total_column": "amount", "totals_into": "labor_total",
     "columns": [{"name": "amount", "type": "currency"}]}]}

assert apply_table_totals(MOD, {"labor_lines": [{"amount": 100}, {"amount": 250.5}]})["labor_total"] == 350.5
assert apply_table_totals(MOD, {"labor_lines": []})["labor_total"] == 0
# strings are the normal case — a form posts them, a CSV import posts them
assert apply_table_totals(MOD, {"labor_lines": [{"amount": "100"}, {"amount": "250.5"}]})["labor_total"] == 350.5
# a blank or junk cell contributes nothing rather than raising: validate_record already reports it,
# and a write that 500s because one cell is mistyped loses the whole ticket
assert apply_table_totals(MOD, {"labor_lines": [{"amount": ""}, {"amount": "x"}, {"amount": 5}]})["labor_total"] == 5
# legacy free text on a converted field must not be summed OR crash
assert "labor_total" not in apply_table_totals(MOD, {"labor_lines": "4 hrs @ 85"})
# a table with no rows key at all leaves the total untouched (a PATCH of an unrelated field)
assert apply_table_totals(MOD, {"labor_total": 999}) == {"labor_total": 999}

with TestClient(app) as c:
    pid = c.post("/projects", headers=H, json={"name": "T&M"}).json()["id"]

    # rate libraries exist and are the SOURCE a user copies from — they are not linked
    c.post(f"/projects/{pid}/modules/labor_rate", headers=H,
           json={"data": {"trade": "Electrician", "rate": 92.5, "unit": "Hour"}})
    c.post(f"/projects/{pid}/modules/equipment_rate", headers=H,
           json={"data": {"equipment": "60T crane", "rate": 310}})

    # ---- 2. create: the total is DERIVED, and the value the caller sent is overridden ------------
    r = c.post(f"/projects/{pid}/modules/eticket", headers=H, json={"data": {
        "subject": "Emergency conduit reroute", "work_date": "2026-07-30",
        "labor_total": 1,                       # deliberately wrong; the lines are the evidence
        "labor_lines": [
            {"worker": "J. Rivera", "trade": "Electrician", "classification": "Journeyman",
             "hours": 8, "ot_hours": 2, "rate": 92.5, "amount": 925},
            {"worker": "P. Osei", "trade": "Electrician", "classification": "Apprentice",
             "hours": 8, "rate": 61, "amount": 488}],
        "equipment_lines": [{"equipment": "60T crane", "hours": 4, "rate": 310, "amount": 1240}],
        "material_lines": [{"description": "EMT 2\"", "qty": 240, "unit": "lf",
                            "unit_price": 4.15, "amount": 996}],
        "signed_by": "M. Chen (owner's rep)", "signed_on": "2026-07-30"}})
    assert r.status_code == 201, r.text
    rid = r.json()["id"]
    got = c.get(f"/projects/{pid}/modules/eticket/{rid}", headers=H).json()["data"]
    assert got["labor_total"] == 1413, got["labor_total"]        # 925 + 488, NOT the 1 that was sent
    assert got["equipment_total"] == 1240, got["equipment_total"]
    assert got["material_total"] == 996, got["material_total"]

    # ---- 3. the engine that reads the totals now sees the itemised truth -------------------------
    s = summarize([{"data": got, "ref": "ETK-001", "workflow_state": "draft"}])
    assert s["labor_total"] == 1413 and s["equipment_total"] == 1240, s
    assert s["grand_total"] == 1413 + 1240 + 996, s["grand_total"]

    # ---- 4. PATCHING ONLY THE LINES MOVES THE TOTAL ----------------------------------------------
    # The case the derivation exists for: without it the summary outlives the evidence.
    r = c.patch(f"/projects/{pid}/modules/eticket/{rid}", headers=H, json={
        "labor_lines": [{"worker": "J. Rivera", "hours": 8, "rate": 92.5, "amount": 925}]})
    assert r.status_code == 200, r.text
    got = c.get(f"/projects/{pid}/modules/eticket/{rid}", headers=H).json()["data"]
    assert got["labor_total"] == 925, got["labor_total"]
    assert got["equipment_total"] == 1240, "an untouched table's total must not be disturbed"

    # ...and a PATCH of the total alone cannot contradict its own lines
    c.patch(f"/projects/{pid}/modules/eticket/{rid}", headers=H, json={"labor_total": 999999})
    got = c.get(f"/projects/{pid}/modules/eticket/{rid}", headers=H).json()["data"]
    assert got["labor_total"] == 925, "a hand-typed total overrode the lines it summarises"

    # ---- 5. THE RATE IS SNAPSHOT ------------------------------------------------------------------
    # Re-price the library. The ticket must not move: it records what was agreed on the day.
    rates = c.get(f"/projects/{pid}/modules/labor_rate", headers=H).json()
    c.patch(f"/projects/{pid}/modules/labor_rate/{rates[0]['id']}", headers=H, json={"rate": 140})
    got = c.get(f"/projects/{pid}/modules/eticket/{rid}", headers=H).json()["data"]
    assert got["labor_lines"][0]["rate"] == 92.5, "the ticket followed a later rate change"
    assert got["labor_total"] == 925, "a library re-price changed what was already owed"

    # ---- 6. A TICKET CANNOT ADVANCE UNSIGNED -----------------------------------------------------
    # The workflow already had three states NAMED for signing — draft, super_signed, gc_signed — and
    # not one `requires`, so a ticket could reach `super_signed` with no signature recorded anywhere.
    # The states described a process nothing enforced. An unsigned T&M ticket is unbillable in the
    # field and was freely billable here.
    unsigned = c.post(f"/projects/{pid}/modules/eticket", headers=H, json={"data": {
        "subject": "No signature yet", "work_date": "2026-07-30",
        "labor_lines": [{"worker": "A", "hours": 4, "rate": 90, "amount": 360}]}}).json()["id"]

    r = c.post(f"/projects/{pid}/modules/eticket/{unsigned}/transition", headers=H,
               json={"action": "super_sign"})
    # 400, not 422: the engine reports an unmet `requires` as a bad request against the state
    # machine rather than a validation error on the body. Asserted as the code the engine ACTUALLY
    # returns — the first version of this test guessed 422 and would have passed on a 500.
    assert r.status_code == 400, f"an unsigned ticket advanced ({r.status_code}): {r.text}"
    assert "signed_by" in r.text or "signature" in r.text, r.text

    # sign it in the field, and the same transition now goes through
    c.patch(f"/projects/{pid}/modules/eticket/{unsigned}", headers=H,
            json={"signed_by": "M. Chen", "signature": "data:image/png;base64,iVBORw0KGgo="})
    r = c.post(f"/projects/{pid}/modules/eticket/{unsigned}/transition", headers=H,
               json={"action": "super_sign"})
    assert r.status_code == 200, r.text
    assert r.json()["workflow_state"] == "super_signed", r.json()

    # ...and the GC's acceptance is its own gate, not a rubber stamp on the field signature
    r = c.post(f"/projects/{pid}/modules/eticket/{unsigned}/transition", headers=H,
               json={"action": "gc_sign"})
    assert r.status_code == 400, f"gc_sign passed without a GC approver ({r.status_code})"
    c.patch(f"/projects/{pid}/modules/eticket/{unsigned}", headers=H,
            json={"gc_approved_by": "R. Patel"})
    r = c.post(f"/projects/{pid}/modules/eticket/{unsigned}/transition", headers=H,
               json={"action": "gc_sign"})
    assert r.status_code == 200 and r.json()["workflow_state"] == "gc_signed", r.text

    # the sign-off is captured on the original ticket too
    assert got["signed_by"] == "M. Chen (owner's rep)" and got["signed_on"] == "2026-07-30"

print("ETICKET T&M OK - an eTicket now itemises labour (worker, trade, classification, hours, OT, "
      "rate), material (qty, unit, unit price) and equipment (hours, idle hours, rate), and each "
      "table's total is DERIVED into the currency field `tm.summarize` reads — on create, and on a "
      "PATCH that touches only the lines. A hand-typed total cannot contradict its own lines: the "
      "lines are the evidence, the total is the summary. The rate is SNAPSHOT on the line, never a "
      "reference to the rate library: re-pricing `labor_rate` afterwards leaves the ticket at what "
      "was agreed on the day, because a library edit that retroactively changes what a contractor is "
      "owed is an accounting error rather than a feature. And the field sign-off (who signed, when) "
      "is captured at last — an unsigned T&M ticket is unbillable, which made it the most "
      "consequential fact about the record and the one it did not store.")

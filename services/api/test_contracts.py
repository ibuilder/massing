"""Contract / exhibit / change-order document generation + scope library + signatures.
Run: PYTHONPATH=src ./.venv/Scripts/python.exe test_contracts.py"""
import io
import os

os.environ["DATABASE_URL"] = "sqlite:///./test_contracts.db"
os.environ["STORAGE_DIR"] = "./test_storage_contracts"
os.environ.pop("AEC_RBAC", None)
for f in ("./test_contracts.db",):
    if os.path.exists(f):
        os.remove(f)

import pypdf                                                  # noqa: E402
from fastapi.testclient import TestClient                    # noqa: E402
from aec_api.main import app                                 # noqa: E402


def mk(c, pid, key, data):
    r = c.post(f"/projects/{pid}/modules/{key}", json={"data": data})
    assert r.status_code in (200, 201), f"{key}: {r.status_code} {r.text[:160]}"
    return r.json()["id"]


def text_of(pdf_bytes):
    assert pdf_bytes[:4] == b"%PDF", "not a PDF"
    return "".join(pg.extract_text() or "" for pg in pypdf.PdfReader(io.BytesIO(pdf_bytes)).pages)


with TestClient(app) as c:
    # scope library
    lib = c.get("/scope-library").json()["clauses"]
    ids = {x["id"] for x in lib}
    assert "div03-concrete" in ids and "sc-insurance" in ids, ids

    pid = c.post("/projects", json={"name": "Tower A"}).json()["id"]
    mk(c, pid, "prime_contract", {"name": "GMP — Tower A", "type": "GMP", "value": 41_000_000,
                                  "owner": "Acme Developers", "retainage_pct": 5})
    sc = mk(c, pid, "subcontract", {"vendor": "ACME Concrete", "trade": "Concrete", "value": 4_800_000,
                                    "retainage_pct": 10})

    # subcontract agreement — merges vendor/value + attaches Exhibit A
    agr = text_of(c.get(f"/projects/{pid}/contracts/subcontract/{sc}/document.pdf?doc=agreement").content)
    assert "Subcontract Agreement" in agr and "ACME Concrete" in agr, agr[:300]
    assert "Exhibit A" in agr and "$4,800,000" in agr, agr[:300]

    # Exhibit A from selected clauses — merged project name + the chosen scope
    exb = text_of(c.get(f"/projects/{pid}/contracts/subcontract/{sc}/document.pdf?doc=exhibit&clauses=div03-concrete,sc-warranty").content)
    assert "Division 03" in exb and "Tower A" in exb and "Warranty" in exb, exb[:300]

    # change order — original → revised contract sum
    cor = mk(c, pid, "cor", {"subject": "Added steel at grid C4", "amount": 92_500, "schedule_days": 5,
                             "justification": "Owner-directed structural addition."})
    co = text_of(c.get(f"/projects/{pid}/contracts/cor/{cor}/document.pdf?doc=co").content)
    assert "Change Order" in co and "Added steel" in co, co[:300]
    assert "$41,000,000" in co and "$92,500" in co and "$41,092,500" in co, co[:400]

    # attach=1 saves the document onto the record
    c.get(f"/projects/{pid}/contracts/subcontract/{sc}/document.pdf?doc=agreement&attach=1")
    atts = c.get(f"/projects/{pid}/modules/subcontract/{sc}").json().get("attachments", [])
    assert any(a.get("filename", "").startswith("agreement-") for a in atts), atts

    # signatures — one per party, re-sign replaces, audited
    c.post(f"/projects/{pid}/contracts/subcontract/{sc}/sign", json={"party": "GC", "name": "Pat GC"})
    s = c.post(f"/projects/{pid}/contracts/subcontract/{sc}/sign", json={"party": "Subcontractor", "name": "Sam Sub"}).json()
    assert {x["party"] for x in s["signatures"]} == {"GC", "Subcontractor"}, s
    s2 = c.post(f"/projects/{pid}/contracts/subcontract/{sc}/sign", json={"party": "GC", "name": "Pat GC II"}).json()
    gc = [x for x in s2["signatures"] if x["party"] == "GC"]
    assert len(gc) == 1 and gc[0]["name"] == "Pat GC II", s2          # replaced, not duplicated
    assert c.post(f"/projects/{pid}/contracts/subcontract/{sc}/sign", json={"name": "x"}).status_code == 422  # party required

    # the signed name now renders into the regenerated agreement
    agr2 = text_of(c.get(f"/projects/{pid}/contracts/subcontract/{sc}/document.pdf?doc=agreement").content)
    assert "Pat GC II" in agr2 and "Sam Sub" in agr2, "signatures should appear on the document"

print("CONTRACTS OK - scope library; subcontract agreement + Exhibit A (merged); G701 change order "
      "(original->revised sum); attach-to-record; per-party signatures rendered on the document")

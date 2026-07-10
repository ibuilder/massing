"""Drawing issuance register (AIA/CD): issue the set for a purpose → a permanent snapshot of which
sheets at which revision went out; the sheet × issuance matrix reconstructs it; sheets added after an
issuance appear only in later issuances.
Run: PYTHONPATH=src ./.venv/Scripts/python.exe test_issuance.py"""
import os

os.environ["DATABASE_URL"] = "sqlite:///./test_issuance.db"
os.environ["STORAGE_DIR"] = "./test_storage_issuance"
os.environ["AEC_TRUST_XUSER"] = "1"
os.environ.pop("AEC_RBAC", None)
for _f in ("./test_issuance.db",):
    if os.path.exists(_f):
        os.remove(_f)

from fastapi.testclient import TestClient                 # noqa: E402
from aec_api import issuance                              # noqa: E402
from aec_api.main import app                              # noqa: E402

HDR = {"X-User": "architect"}

# purposes vocabulary is the AIA/CD set
assert "Issued for Permit" in issuance.PURPOSES and "Issued for Construction" in issuance.PURPOSES

with TestClient(app) as c:
    pid = c.post("/projects", json={"name": "Issuance Tower"}, headers=HDR).json()["id"]
    P = f"/projects/{pid}"

    # issuing with no sheets → 409
    assert c.post(f"{P}/drawing-set/issue", json={"purpose": "Issued for Permit"}, headers=HDR).status_code == 409

    # generate the mechanical series, then issue for permit — snapshots the current set
    c.post(f"{P}/drawing-set/generate", json={"disciplines": ["Mechanical"]}, headers=HDR)
    m_count = c.get(f"{P}/drawing-set", headers=HDR).json()["sheet_count"]
    i1 = c.post(f"{P}/drawing-set/issue", json={"purpose": "Issued for Permit",
                "recipients": "DOB, Owner", "description": "Permit set"}, headers=HDR)
    assert i1.status_code == 201 and i1.json()["sheet_count"] == m_count, i1.text

    # add the electrical series (new sheets), then issue for bid — a bigger snapshot
    c.post(f"{P}/drawing-set/generate", json={"disciplines": ["Electrical"]}, headers=HDR)
    total = c.get(f"{P}/drawing-set", headers=HDR).json()["sheet_count"]
    assert total > m_count, "electrical sheets should have been added"
    i2 = c.post(f"{P}/drawing-set/issue", json={"purpose": "Issued for Bid"}, headers=HDR).json()
    assert i2["sheet_count"] == total, i2

    # register: two issuances in bind order (permit before bid)
    reg = c.get(f"{P}/drawing-set/issuances", headers=HDR).json()
    assert reg["issuance_count"] == 2, reg
    assert [i["purpose"] for i in reg["issuances"]] == ["Issued for Permit", "Issued for Bid"], reg["issuances"]
    assert reg["issuances"][0]["sheet_count"] == m_count and reg["issuances"][1]["sheet_count"] == total

    # matrix: sheet × issuance grid. Mechanical sheets are in BOTH; Electrical sheets only in Bid.
    mx = c.get(f"{P}/drawing-set/issuance-matrix", headers=HDR).json()
    assert len(mx["issuances"]) == 2 and mx["sheet_count"] == total, mx["sheet_count"]
    m_rows = [r for r in mx["rows"] if r["sheet_number"].startswith("M-")]
    e_rows = [r for r in mx["rows"] if r["sheet_number"].startswith("E-")]
    assert m_rows and e_rows
    assert all(r["cells"][0] is not None and r["cells"][1] is not None for r in m_rows), "M in both issues"
    assert all(r["cells"][0] is None and r["cells"][1] is not None for r in e_rows), "E only in the 2nd issue"

    # per-issuance transmittal PDF, stamped with the purpose
    iid = reg["issuances"][0]["id"]
    pdf = c.get(f"{P}/drawing-set/issuances/{iid}/transmittal.pdf", headers=HDR)
    assert pdf.status_code == 200 and pdf.content[:4] == b"%PDF", pdf.status_code

    # purposes endpoint
    pu = c.get(f"{P}/drawing-set/issuance-purposes", headers=HDR).json()
    assert any(p["name"] == "Issued for Construction" and p["abbr"] == "IFC" for p in pu["purposes"])

print(f"ISSUANCE OK - 2 issuances (Permit {m_count} sheets, Bid {total}); sheet×issuance matrix shows "
      "Mechanical in both issues and Electrical only in the later one; per-issuance transmittal PDF; "
      "AIA purposes vocabulary (SD/DD/CD/Permit/Bid/IFC/…).")

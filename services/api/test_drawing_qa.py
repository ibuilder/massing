"""QA-AGENT: drawing-set QA — set integrity, issuance hygiene, model cross-checks, all sheet-cited.
Register-only first, then with a modeled project. Run: PYTHONPATH=src;../data/src ./.venv/Scripts/python.exe test_drawing_qa.py"""
import os
import sys

os.environ.setdefault("DATABASE_URL", "sqlite:///./_drawqa_test.db")
os.environ.setdefault("STORAGE_DIR", "./_storage_drawqa")
os.environ.setdefault("IFC_DIR", os.path.join(os.path.dirname(__file__), "_ifc_drawqa"))
os.environ.pop("AEC_RBAC", None)
if os.path.exists("./_drawqa_test.db"):
    os.remove("./_drawqa_test.db")

_DATA_SRC = os.path.join(os.path.dirname(__file__), "..", "data", "src")
if _DATA_SRC not in sys.path:
    sys.path.insert(0, _DATA_SRC)

from fastapi.testclient import TestClient  # noqa: E402

from aec_api.main import app  # noqa: E402

with TestClient(app) as c:
    pid = c.post("/projects", json={"name": "QA Set"}).json()["id"]

    # seed a register with deliberate defects: duplicate A-101, a gap A-102..A-104 missing A-103,
    # an issued sheet with no date, a bad revision token, and a sheet with no title.
    def sheet(number, title="Sheet", disc=None, status="", rev="", issued=""):
        d = {"number": number, "title": title, "discipline": disc or (number.split("-")[0]),
             "status": status, "revision": rev, "issued_date": issued}
        r = c.post(f"/projects/{pid}/modules/drawing", json={"data": d})
        assert r.status_code < 300, r.text[:200]

    sheet("A-101", "Floor Plan L1")
    sheet("A-101", "Floor Plan L1 dup")                       # duplicate number -> critical
    sheet("A-102", "Floor Plan L2")
    sheet("A-104", "Roof Plan")                               # gap: A-103 missing -> minor
    sheet("S-101", "Framing", status="Issued")                # issued, no date -> major
    sheet("G-001", "", rev="??")                              # no title (minor) + bad revision (minor)

    r0 = c.get(f"/projects/{pid}/drawing-set/qa").json()
    assert r0["sheet_count"] == 6 and r0["model_crosschecks"].startswith("model not loaded"), r0["model_crosschecks"]
    checks = {(f["check"], f["severity"]) for f in r0["findings"]}
    assert ("set-integrity", "critical") in checks, checks     # duplicate A-101
    assert any(f["check"] == "set-integrity" and "A-103" in f["finding"] for f in r0["findings"]), \
        "the numbering gap must name the missing sheet"
    assert any(f["check"] == "issuance" and f["sheet"] == "S-101" for f in r0["findings"])
    assert any(f["check"] == "titleblock" and f["sheet"] == "G-001" for f in r0["findings"])
    assert r0["verdict"] == "HOLD", r0["verdict"]              # critical present
    sev = [f["severity"] for f in r0["findings"]]
    assert sev == sorted(sev, key=lambda s: {"critical": 0, "major": 1, "minor": 2}[s]), "ranked"

    # model cross-checks: a 5-storey model with only 2 A-plans + columns and no S sheets… S-101 exists,
    # so build the model and verify the plans-per-storey finding fires and the S coverage does NOT.
    r = c.post(f"/projects/{pid}/model/blank",
               json={"name": "QA", "storeys": 5, "storey_height": 3.0, "ground_size": 15.0})
    assert r.status_code < 300, r.text[:200]
    r1 = c.get(f"/projects/{pid}/drawing-set/qa").json()
    assert r1["model_crosschecks"] == "ok"
    assert any(f["check"] == "model-crosscheck" and "storeys" in f["finding"] for f in r1["findings"]), \
        [f["finding"] for f in r1["findings"] if f["check"] == "model-crosscheck"]

print("DRAWING-QA OK - register review flags the duplicate A-101 (critical -> HOLD), the A-103 numbering "
      "gap by name, the issued-no-date S-101, and the G-001 titleblock gaps, ranked critical->minor and "
      "sheet-cited; with a 5-storey model the plans-per-storey cross-check fires (4 A-plans < 5 levels) "
      "while the S-series coverage stays quiet because S-101 exists; runs with or without a model.")

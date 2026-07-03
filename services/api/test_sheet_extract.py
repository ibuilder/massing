"""Drawing-sheet extraction — deterministic sheet-index parse + bulk drawing-record creation.
Run: PYTHONPATH=src ./.venv/Scripts/python.exe test_sheet_extract.py"""
import os

os.environ["DATABASE_URL"] = "sqlite:///./test_sheetx.db"
os.environ["STORAGE_DIR"] = "./test_storage_sheetx"
os.environ.pop("AEC_RBAC", None)
for _f in ("./test_sheetx.db",):
    if os.path.exists(_f):
        os.remove(_f)

from fastapi.testclient import TestClient             # noqa: E402
from aec_api.main import app                          # noqa: E402
from aec_api import sheet_extract                      # noqa: E402

# --- pure extraction over a typical sheet-index text blob --------------------------------------
INDEX = """
DRAWING INDEX
A-101 .... FIRST FLOOR PLAN
A-102     SECOND FLOOR PLAN
A201  BUILDING ELEVATIONS
S-101 - FOUNDATION PLAN
M-501 MECHANICAL SCHEDULES
E101   LIGHTING PLAN LEVEL 1
P-201 PLUMBING RISER DIAGRAM
C-100 SITE PLAN
G-001 COVER SHEET
random line with no sheet number
"""
sheets = sheet_extract.extract_from_text(INDEX)
by_num = {s["number"]: s for s in sheets}
assert "A-101" in by_num and by_num["A-101"]["title"].upper().startswith("FIRST FLOOR"), by_num.get("A-101")
assert by_num["A-101"]["discipline"] == "Architectural", by_num["A-101"]
assert by_num["S-101"]["discipline"] == "Structural", by_num["S-101"]
assert by_num["M-501"]["discipline"] == "Mechanical", by_num["M-501"]
assert by_num["E-101"]["discipline"] == "Electrical", by_num["E-101"]
assert by_num["C-100"]["discipline"] == "Civil", by_num["C-100"]
assert len(sheets) == 9, [s["number"] for s in sheets]     # the noise line is ignored

with TestClient(app) as c:
    pid = c.post("/projects", json={"name": "P"}).json()["id"]

    # --- endpoint: paste text, don't create -----------------------------------------------------
    r = c.post(f"/projects/{pid}/extract/sheets", data={"text": INDEX, "create": "false"})
    assert r.status_code == 200, r.text[:160]
    body = r.json()
    assert len(body["sheets"]) == 9 and body["method"] == "deterministic", body

    # --- endpoint: create drawing records -------------------------------------------------------
    r2 = c.post(f"/projects/{pid}/extract/sheets", data={"text": INDEX, "create": "true"})
    j = r2.json()
    assert len(j.get("created", [])) == 9, j.get("created")
    drawings = c.get(f"/projects/{pid}/modules/drawing").json()
    assert len(drawings) == 9, len(drawings)
    nums = {d["data"]["number"] for d in drawings}
    assert "A-101" in nums and "G-001" in nums, nums

print("SHEET EXTRACT OK - 9 sheets parsed from the index (noise ignored); disciplines inferred from "
      "prefix (A/S/M/E/C); endpoint created 9 drawing records")

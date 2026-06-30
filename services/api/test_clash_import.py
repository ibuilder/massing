"""Import a Solibri/Navisworks clash report (XLSX) -> coordination_issue records (header sniffing,
alias mapping, severity->priority, GUID extraction -> element_guids). Builds the workbooks in-memory.
Run: PYTHONPATH=src ./.venv/Scripts/python.exe test_clash_import.py"""
import io
import os

os.environ["DATABASE_URL"] = "sqlite:///./test_clash_import.db"
os.environ["STORAGE_DIR"] = "./test_storage_clash_import"
os.environ.pop("AEC_RBAC", None)
for _f in ("./test_clash_import.db",):
    if os.path.exists(_f):
        os.remove(_f)

from openpyxl import Workbook                 # noqa: E402
from aec_api import clash_import              # noqa: E402
from fastapi.testclient import TestClient     # noqa: E402
from aec_api.main import app                  # noqa: E402

G1 = "0abcdEFGHij12345KLmnoP"   # 22-char base64-ish IFC GlobalIds
G2 = "1ZYXwvuTSRqp98765kjihg"
assert len(G1) == 22 and len(G2) == 22, (len(G1), len(G2))


def solibri_xlsx() -> bytes:
    wb = Workbook(); ws = wb.active; ws.title = "Issues"
    ws.append(["Solibri Coordination Report"])                       # a title/preamble row
    ws.append(["Name", "Description", "Severity", "Ruleset", "Component GUID", "Location"])
    ws.append(["Beam vs duct", "WF beam clashes supply duct", "Critical", "MEP/Structural", G1, "L2 Grid C4"])
    ws.append(["Pipe vs wall", "Sprinkler main through shear wall", "Moderate", "Plumbing", G2, "L3 Core"])
    ws.append([None, None, None, None, None, None])                  # blank separator
    buf = io.BytesIO(); wb.save(buf); return buf.getvalue()


def navis_xlsx() -> bytes:
    wb = Workbook(); ws = wb.active; ws.title = "Clashes"
    ws.append(["Clash Name", "Status", "Grid Location", "Item 1", "Item 2"])
    ws.append(["Clash1", "New", "C-4 / L2", f"id {G1}", f"id {G2}"])
    buf = io.BytesIO(); wb.save(buf); return buf.getvalue()


# --- pure parse --------------------------------------------------------------
p = clash_import.parse_clash_xlsx(solibri_xlsx())
assert p["header_row"] == 1, p                                       # title row skipped
assert len(p["rows"]) == 2, p["rows"]
r0 = p["rows"][0]
assert r0["subject"] == "Beam vs duct" and r0["priority"] == "Critical", r0
assert r0["discipline"] == "MEP/Structural" and r0["location"] == "L2 Grid C4", r0
assert r0["_guids"] == [G1], r0
assert p["rows"][1]["priority"] == "Medium", p["rows"][1]            # "Moderate" -> Medium

# navisworks: two component columns -> both GUIDs captured, grid location mapped
pn = clash_import.parse_clash_xlsx(navis_xlsx())
assert len(pn["rows"]) == 1, pn["rows"]
assert set(pn["rows"][0]["_guids"]) == {G1, G2}, pn["rows"][0]
assert pn["rows"][0]["location"] == "C-4 / L2", pn["rows"][0]

with TestClient(app) as c:
    pid = c.post("/projects", json={"name": "Clash"}).json()["id"]
    assert "coordination_issue" in {m["key"] for m in c.get("/modules").json()}

    res = c.post(f"/projects/{pid}/coordination/import-xlsx",
                 files={"file": ("solibri.xlsx", solibri_xlsx(),
                                 "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")}).json()
    assert res["imported"] == 2, res
    recs = c.get(f"/projects/{pid}/modules/coordination_issue").json()
    assert len(recs) == 2, len(recs)
    crit = next(r for r in recs if (r.get("data") or {}).get("subject") == "Beam vs duct")
    assert (crit.get("data") or {}).get("priority") == "Critical", crit
    assert crit.get("element_guids") == [G1], crit                   # GUID anchored on the model

print("CLASH IMPORT OK - sniffs header past a title row, maps Solibri + Navisworks columns, "
      "severity->priority (Critical/Medium), extracts component GUIDs from one or two columns into "
      "element_guids, and creates coordination_issue records via the endpoint")

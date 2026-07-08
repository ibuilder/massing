"""Document-control file manager (F1-F6): standard folder taxonomy, upload + auto-naming + revision
supersede, role-based views, health + phase gaps.
Run: PYTHONPATH=src ./.venv/Scripts/python.exe test_docmanager.py"""
import io
import os

os.environ["DATABASE_URL"] = "sqlite:///./test_docmanager.db"
os.environ["STORAGE_DIR"] = "./test_storage_docmanager"
os.environ.pop("AEC_RBAC", None)
for _f in ("./test_docmanager.db",):
    if os.path.exists(_f):
        os.remove(_f)

from fastapi.testclient import TestClient  # noqa: E402

from aec_api import docmanager, folder_template  # noqa: E402
from aec_api.main import app  # noqa: E402

# --- F1: taxonomy ---------------------------------------------------------------------------------
tree = folder_template.tree()
paths = {n["path"] for n in tree}
assert "01_Contract Documents" in paths and "02_Drawings/Structural" in paths, "standard tree present"
assert "08_Site Documents/Daily Reports" in paths
assert folder_template.owner_of("08_Site Documents/RFI") == "Superintendent", "field folders = Super"
assert folder_template.owner_of("04_Payment Applications") == "PM", "business folders = PM"
assert folder_template.owner_of("02_Drawings/Architectural") == "Architect"
assert not folder_template.is_valid("99_Nonsense")
assert "CD" in folder_template.phases() and folder_template.phase_checklist("CD"), "AIA phase checklists"

# --- F2/F5 engine directly ------------------------------------------------------------------------
PID = "proj-dm"
r1 = docmanager.upload(PID, "02_Drawings/Structural", "S-201.pdf", b"%PDF-1 first", "eng",
                       title="Framing Plan", doc_type="Drawing")
assert r1["entry"]["revision"] == "P01" and r1["entry"]["discipline"] == "Structural", r1["entry"]
assert r1["entry"]["owner_role"] == "Engineer", r1["entry"]
# auto-named to the standard: Type_Discipline_Description_Revision_Date, discipline code S
assert r1["entry"]["name"].startswith("DRAWING_S_FramingPlan_P01_"), r1["entry"]["name"]
# re-upload same title -> supersede: prior archived, new is P02
r2 = docmanager.upload(PID, "02_Drawings/Structural", "S-201.pdf", b"%PDF-1 second", "eng",
                       title="Framing Plan", doc_type="Drawing")
assert r2["entry"]["revision"] == "P02" and r2["superseded"] == r1["entry"]["id"], r2
folder = docmanager.list_folder(PID, "02_Drawings/Structural")
assert folder["count"] == 1 and folder["files"][0]["revision"] == "P02", "only latest rev shows"
assert docmanager.list_folder(PID, "02_Drawings/Structural", include_superseded=True)["count"] == 2

# tree annotates counts + required gaps
t = docmanager.tree(PID)
struct = next(n for n in t["nodes"] if n["path"] == "02_Drawings/Structural")
assert struct["count"] == 1, struct
drawings_root = next(n for n in t["nodes"] if n["path"] == "02_Drawings")
assert drawings_root["count"] == 1, "counts roll up to parent"
assert "01_Contract Documents/Contract Agreement" in t["required_gaps"], "required-but-empty flagged"

# health
h = docmanager.health(PID)
assert h["total_files"] == 1 and h["revision_control_pct"] == 100.0, h
assert h["superseded_kept"] == 1, h
assert "01_Contract Documents/Contract Agreement" in h["required_missing"], h

# phase gaps: CD needs structural drawings (present) + specs/BOQ (missing)
pg = docmanager.phase_gaps(PID, "CD")
assert not pg["complete"] and pg["missing"] >= 1, pg
present_struct = next(i for i in pg["items"] if i["folder"] == "02_Drawings/Structural")
assert present_struct["present"] is True, pg

# --- endpoints ------------------------------------------------------------------------------------
with TestClient(app) as c:
    pid = c.post("/projects", json={"name": "Doc Test"}).json()["id"]
    assert c.get(f"/projects/{pid}/documents/template").json()["nodes"], "template served"
    # empty project tree still returns the full taxonomy with gaps
    tr = c.get(f"/projects/{pid}/documents/tree").json()
    assert tr["total_files"] == 0 and tr["required_gaps"], tr
    # upload via multipart
    up = c.post(f"/projects/{pid}/documents/upload",
                data={"path": "08_Site Documents/Daily Reports", "title": "Daily 2026-07-08",
                      "doc_type": "Report"},
                files={"file": ("daily.pdf", io.BytesIO(b"%PDF report"), "application/pdf")})
    assert up.status_code == 201, up.text[:200]
    fid = up.json()["entry"]["id"]
    assert up.json()["entry"]["owner_role"] == "Superintendent", up.json()["entry"]
    # folder listing + download
    fl = c.get(f"/projects/{pid}/documents/folder", params={"path": "08_Site Documents/Daily Reports"}).json()
    assert fl["count"] == 1 and fl["owner_role"] == "Superintendent", fl
    dl = c.get(f"/projects/{pid}/documents/{fid}/download")
    assert dl.status_code == 200 and dl.content == b"%PDF report", dl.status_code
    # by-role view (the role-based structure)
    su = c.get(f"/projects/{pid}/documents/by-role", params={"role": "Superintendent"}).json()
    assert su["count"] >= 5 and all(f["owner_role"] == "Superintendent" for f in su["folders"]), su
    # move to a bad folder -> 400; to a good one -> ok
    assert c.post(f"/projects/{pid}/documents/{fid}/move", data={"path": "zzz"}).status_code == 400
    mv = c.post(f"/projects/{pid}/documents/{fid}/move", data={"path": "10_Photos/During"})
    assert mv.status_code == 200 and mv.json()["folder"] == "10_Photos/During", mv.text[:120]
    # upload to a non-standard folder is rejected
    bad = c.post(f"/projects/{pid}/documents/upload",
                 data={"path": "made/up"}, files={"file": ("x.pdf", io.BytesIO(b"x"), "application/pdf")})
    assert bad.status_code == 400, bad.status_code
    # health + phase gaps endpoints
    assert c.get(f"/projects/{pid}/documents/health").json()["total_files"] == 1
    assert c.get(f"/projects/{pid}/documents/phase-gaps", params={"phase": "CLOSEOUT"}).json()["phase"] == "CLOSEOUT"

print("DOCMANAGER OK - F1 standard tree (owner roles: Super=field, PM=business, A/E=design) + AIA phase "
      "checklists; F2 upload auto-names to Type_Disc_Desc_Rev_Date, revision supersede keeps audit "
      "(P01->P02, only latest shows); counts roll up + required gaps flagged; F3 by-role view; F5 health; "
      "F6 phase gaps; endpoints: upload/folder/download/move/by-role/health all pass, bad folders 400")

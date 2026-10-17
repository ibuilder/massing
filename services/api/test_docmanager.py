"""Document-control file manager (F1-F6): standard folder taxonomy, upload + auto-naming + revision
supersede, role-based views, health + phase gaps.
Run: PYTHONPATH=src ./.venv/Scripts/python.exe test_docmanager.py"""
import io
import os
import shutil
from datetime import datetime

os.environ["DATABASE_URL"] = "sqlite:///./test_docmanager.db"
os.environ["STORAGE_DIR"] = "./test_storage_docmanager"
os.environ.pop("AEC_RBAC", None)
for _f in ("./test_docmanager.db",):
    if os.path.exists(_f):
        os.remove(_f)
# docmanager persists a sidecar index in STORAGE_DIR; clear it so the fixed-pid engine assertions
# below are isolated across runs (the runner also clears _storage_*, this covers standalone runs).
shutil.rmtree(os.environ["STORAGE_DIR"], ignore_errors=True)

from fastapi.testclient import TestClient  # noqa: E402

from aec_api import docmanager, folder_template, naming  # noqa: E402
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
# EVERY known phase must have a non-empty checklist, which is what makes `phase_gaps`'s `bool(items)`
# guard unreachable today — and this assertion is why keeping that guard is not superstition. A phase
# added to `REQUIRED_BY_PHASE` with an empty list would be `known_phase: true` with no items, and
# `not missing` alone would report the set COMPLETE for it. Mutating `bool(items)` away leaves the
# suite green (measured), so this is the check that gives the guard its reason: when the table stops
# satisfying it, THIS fails with the right diagnosis rather than `complete` going quietly wrong.
for _ph in folder_template.phases():
    assert folder_template.phase_checklist(_ph), f"{_ph} is a known phase with an empty checklist"

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

def _expect_value_error(fn):
    """Return the ValueError a call raises, or fail — `assertRaises` with the message in hand, so
    the refusal's TEXT can be asserted rather than only its type."""
    try:
        fn()
    except ValueError as e:
        return e
    raise AssertionError("expected a ValueError and the call succeeded")


# health
h = docmanager.health(PID)
assert h["total_files"] == 1 and h["revision_control_pct"] == 100.0, h
assert h["superseded_kept"] == 1, h
assert "01_Contract Documents/Contract Agreement" in h["required_missing"], h

# --- DOCHEALTH-VACUOUS: two of the three percentages cannot vary -------------------------------
# `upload` generates every filed name with `_standard_name` AND assigns every revision, so
# `naming_compliance_pct` and `revision_control_pct` both answer "did this module work" and are
# 100% by construction. The strip led with the first and printed the second beside it.
# PROVED rather than asserted on one fixture: every hostile title, doc_type and discipline the
# caller can supply still produces a name this project's own validator accepts.
_WHEN = datetime(2026, 10, 15)
for _t in ("", "   ", "...", "!!!", "a" * 300, "Final final v2", "Ünïcödé ✓", "a_b_c_d_e_f",
           "2026-01-01", "../../etc/passwd"):
    for _dt, _disc in (("", None), ("!!!", "Nonsense"), ("x" * 40, "Architectural"), ("a-b-c", "")):
        _nm = docmanager._safe(docmanager._standard_name(
            _dt, _disc, (_t or "Document").strip() or "Document", "P01", _WHEN) + ".pdf")
        _v = naming.validate_container_name(_nm)
        assert _v["valid"], (_t[:30], _dt, _disc, _nm, _v["issues"])
        # The two fields that MUST survive the length bound, which is the defect behind the 300-char
        # case: `_safe` truncates at 120 and used to be handed the whole assembled name, so a long
        # title pushed the revision and the date off the end — three fields, no revision, in a
        # revision-controlled CDE.
        assert _v["fields"]["revision"] == "P01", (_t[:30], _nm)
        assert _v["fields"]["date"] == "2026-10-15", (_t[:30], _nm)
        assert len(_nm) <= docmanager._MAX_NAME, (len(_nm), _nm)

# `named_at_source_pct` is the number about the PROJECT, free from the `orig_name` already stored.
_at_source = docmanager.upload(PID, "02_Drawings/Structural",
                               "DR_S_FoundationPlan_P01_2026-07-05.pdf", b"x", "dev")
_renamed = docmanager.upload(PID, "02_Drawings/Structural", "Final final v2.pdf", b"x", "dev")
h2 = docmanager.health(PID)
assert h2["naming_compliance_pct"] == 100.0, "the auto-namer always conforms"
assert h2["named_at_source_pct"] is not None and h2["named_at_source_pct"] < 100.0, h2
assert h2["renamed_on_intake"] >= 1, h2
_row = next(r for r in h2["renamed"] if r["orig_name"] == "Final final v2.pdf")
# `S`, not `G`: the discipline in the generated name comes from the FOLDER's declared discipline
# (`02_Drawings/Structural`), which is why filing into the taxonomy is what makes auto-naming work.
assert _row["name"].startswith("DOC_S_FinalFinalV2_P01_"), _row
assert h2["renamed_truncated"] is False, h2
assert "100% by construction" in h2["naming_basis"], h2["naming_basis"]

# A whitespace revision is an EMPTY revision — the one path by which a document could be filed with
# a blank revision field in its name, which is also the only way either percentage above could dip.
_ws = docmanager.upload(PID, "02_Drawings/Structural", "Blank rev.pdf", b"x", "dev",
                        revision="   ")
assert _ws["entry"]["revision"] == "P01", _ws["entry"]["revision"]
assert _ws["naming"]["valid"] is True, _ws["naming"]
assert docmanager.health(PID)["revision_control_pct"] == 100.0

# `required_total` is the denominator the percentage is over, and `orphans` is actionable rather
# than a list of bare ids a reader resolves one lookup at a time.
h3 = docmanager.health(PID)
assert h3["required_total"] == len(folder_template.required_paths()) > 0, h3["required_total"]
assert h3["orphan_count"] == 0 and h3["orphans"] == [], h3
# The list is empty BY CONSTRUCTION: both doors refuse a non-standard folder, so the only way it
# fills is a folder leaving the standard tree under documents already filed there.
assert "not a standard folder" in str(
    _expect_value_error(lambda: docmanager.upload(PID, "99_Loose", "x.pdf", b"x", "dev")))
assert "not a standard folder" in str(
    _expect_value_error(lambda: docmanager.move(PID, _at_source["entry"]["id"], "99_Loose", "dev")))
assert "by construction" in h3["orphan_basis"], h3["orphan_basis"]

# phase gaps: CD needs structural drawings (present) + specs/BOQ (missing)
pg = docmanager.phase_gaps(PID, "CD")
assert not pg["complete"] and pg["missing"] >= 1, pg
assert pg["known_phase"] is True and pg["refused"] is None, pg

# BARE-NEGATED. `complete` was `not missing`, and `phase_checklist` returns [] for a phase it does
# not know — so an unrecognised phase produced `items: [], missing: 0, complete: True` and told the
# caller its document set was COMPLETE for a phase that does not exist. `phase` is an unvalidated
# query parameter on `GET /projects/{pid}/documents/phase-gaps`, so this was reachable with one
# typo, and it answered 200 with the reassuring value rather than refusing — the severity ordering
# `test_system_columns.py` records: a defect that is refused loudly is nearly fixed.
for bad in ("NONSENSE", "", "../etc", "SD/CD", "99"):
    g = docmanager.phase_gaps(PID, bad)
    assert g["known_phase"] is False, (bad, g)
    assert g["complete"] is False, (bad, g)          # <- the field somebody actually reads
    assert g["items"] == [] and g["missing"] == 0, (bad, g)
    assert "not a design phase" in (g["refused"] or ""), (bad, g)
    assert "CD" in g["known_phases"], (bad, g)
# THE TOLERANCES ARE ASSERTED TOO, because trading one silent wrong answer for a loud wrong refusal
# is not a fix. `"CD "` belongs here and NOT in the list above — my first draft had it in both, with
# a comment arguing it should be accepted two lines above an assertion that it is refused. The
# pre-fix code accepted a trailing space by ACCIDENT (`phase.upper()` with no strip left `"CD "`
# unmatched -> empty checklist -> `complete: true`), so the trailing space was one of the inputs the
# defect fired on, and stripping it is part of the repair rather than an exception to it.
assert docmanager.phase_gaps(PID, "CD ")["known_phase"] is True, "a trailing space is a typo, not a phase"
assert docmanager.phase_gaps(PID, "CD ")["missing"] >= 1, "and it must give the real answer"
assert docmanager.phase_gaps(PID, "cd")["known_phase"] is True, "lowercase must still resolve"
assert docmanager.phase_gaps(PID, "cd")["phase"] == "CD"

# ...and the ROUTE gives it the right status code, which the engine's refusal body cannot: a 200
# carrying `complete: false` still reads as a result to anything counting HTTP codes. Two
# independent refusals — this one for the API's shape, the engine's for every caller that does not
# come through this route.
with TestClient(app) as _c:
    _p = _c.post("/projects", json={"name": "Phase Route"}).json()["id"]
    _ok = _c.get(f"/projects/{_p}/documents/phase-gaps", params={"phase": "CD"})
    assert _ok.status_code == 200 and _ok.json()["known_phase"] is True, _ok.text
    for _bad in ("NONSENSE", "", "../etc"):
        _r = _c.get(f"/projects/{_p}/documents/phase-gaps", params={"phase": _bad})
        assert _r.status_code == 422, (_bad, _r.status_code, _r.text[:200])
        assert "not a design phase" in _r.text, (_bad, _r.text[:200])
    # the known list is IN the refusal, so a caller can fix the call from the error alone
    assert "CLOSEOUT" in _c.get(f"/projects/{_p}/documents/phase-gaps",
                                params={"phase": "x"}).text
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

# --- DOC-RACE: concurrent uploads must not lose index entries or duplicate ids ---------------------
import threading  # noqa: E402

from aec_api import docmanager  # noqa: E402

_race_pid = "race-project"
N = 12
errs: list[Exception] = []


def _up(i: int) -> None:
    try:
        docmanager.upload(_race_pid, "02_Drawings/Architectural", f"race-{i}.pdf", b"%PDF race", "tester",
                          title=f"Race Doc {i}")
    except Exception as e:  # noqa: BLE001
        errs.append(e)


threads = [threading.Thread(target=_up, args=(i,)) for i in range(N)]
for t in threads:
    t.start()
for t in threads:
    t.join()
assert not errs, errs
_idx = docmanager._load(_race_pid)
_ids = [f["id"] for f in _idx["files"]]
assert len(_idx["files"]) == N, f"lost update: {len(_idx['files'])}/{N} index entries survived"
assert len(set(_ids)) == N, f"duplicate ids allocated: {sorted(_ids)}"
print(f"DOC-RACE OK - {N} concurrent uploads -> {N} index entries, {N} unique ids (per-project lock)")

print("DOCMANAGER OK - F1 standard tree (owner roles: Super=field, PM=business, A/E=design) + AIA phase "
      "checklists; F2 upload auto-names to Type_Disc_Desc_Rev_Date, revision supersede keeps audit "
      "(P01->P02, only latest shows); counts roll up + required gaps flagged; F3 by-role view; F5 health; "
      "F6 phase gaps; endpoints: upload/folder/download/move/by-role/health all pass, bad folders 400")

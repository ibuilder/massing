"""Drawing revision register (AIA revision block) + sealed issuance (PAdES). A sheet's deltas are
recorded with the driving change instrument (ASI/CCD/Addendum), roll up into a cross-sheet revision
register, and an issuance can be digitally sealed for permit submittal.
Run: PYTHONPATH=src ./.venv/Scripts/python.exe test_drawing_revision.py"""
import os

os.environ["DATABASE_URL"] = "sqlite:///./test_drawrev.db"
os.environ["STORAGE_DIR"] = "./test_storage_drawrev"
os.environ["AEC_TRUST_XUSER"] = "1"
os.environ.pop("AEC_RBAC", None)
for _f in ("./test_drawrev.db",):
    if os.path.exists(_f):
        os.remove(_f)

from fastapi.testclient import TestClient                 # noqa: E402
from aec_api.main import app                              # noqa: E402

HDR = {"X-User": "engineer"}

with TestClient(app) as c:
    pid = c.post("/projects", json={"name": "Revision Tower"}, headers=HDR).json()["id"]
    P = f"/projects/{pid}"

    # generate a small set, grab a structural sheet's record id
    c.post(f"{P}/drawing-set/generate", json={"disciplines": ["Structural"]}, headers=HDR)
    dwgs = c.get(f"{P}/modules/drawing?limit=1000", headers=HDR).json()
    sid = dwgs[0]["id"]
    assert dwgs[0]["data"].get("revision") in (None, "", "0"), dwgs[0]["data"]

    # revise requires a rev
    assert c.post(f"{P}/drawings/{sid}/revise", json={"description": "x"}, headers=HDR).status_code == 422

    # record two revisions, the 2nd citing an ASI
    r1 = c.post(f"{P}/drawings/{sid}/revise", json={"rev": "1", "description": "Rebar clarification",
                "date": "2026-05-01"}, headers=HDR)
    assert r1.status_code == 201 and r1.json()["revision"] == "1", r1.text
    r2 = c.post(f"{P}/drawings/{sid}/revise", json={"rev": "2", "description": "Added shear wall",
                "date": "2026-06-15", "instrument_type": "ASI", "instrument_ref": "ASI-003"}, headers=HDR).json()
    assert r2["delta_count"] == 2, r2

    # the sheet now carries revision "2" + a 2-delta revision block
    rec = c.get(f"{P}/modules/drawing/{sid}", headers=HDR).json()
    assert rec["data"]["revision"] == "2" and len(rec["data"]["revisions"]) == 2, rec["data"]

    # cross-sheet revision register — newest first, cites the ASI
    reg = c.get(f"{P}/drawing-set/revisions", headers=HDR).json()
    assert reg["delta_count"] == 2, reg
    assert reg["revisions"][0]["rev"] == "2" and reg["revisions"][0]["date"] == "2026-06-15", reg["revisions"][0]
    assert reg["revisions"][0]["instrument"]["ref"] == "ASI-003", reg["revisions"][0]
    assert reg["by_instrument"].get("ASI-003") == 1, reg["by_instrument"]

    # --- sealed issuance (PAdES) — 200 + a valid PDF whether or not e-sign is configured -----------
    c.post(f"{P}/drawing-set/issue", json={"purpose": "Issued for Permit"}, headers=HDR)
    iid = c.get(f"{P}/drawing-set/issuances", headers=HDR).json()["issuances"][0]["id"]
    sealed = c.get(f"{P}/drawing-set/issuances/{iid}/sealed.pdf?name=Jane Roe, AIA", headers=HDR)
    assert sealed.status_code == 200 and sealed.content[:4] == b"%PDF", sealed.status_code
    assert sealed.headers.get("X-Sealed") in ("true", "false")

print(f"DRAWING REVISION OK - two deltas recorded (rev 1, rev 2 citing ASI-003); sheet bumped to rev 2 "
      "with a 2-delta revision block; cross-sheet revision register newest-first w/ instrument rollup; "
      f"issuance sealed PDF (X-Sealed={sealed.headers.get('X-Sealed')}).")

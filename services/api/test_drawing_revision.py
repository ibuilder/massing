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

from fastapi.testclient import TestClient  # noqa: E402

from aec_api.main import app  # noqa: E402

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

    # --- SET-REVISED: the CONTROLLED register has to agree with the delta register above ----------
    #
    # Those two routes read the same record. `/drawing-set/revisions` walked `data["revisions"]` and
    # reported both deltas with their instruments -- correct, and asserted here since REVISE-DARK.
    # `/drawing-set` classified issuance by counting RECORDS per sheet (`"new" if len(revs) == 1`),
    # and `revise` keeps ONE record per sheet, so the same twice-revised sheet came back
    # `change: "new", revisions: 1, revised_count: 0, superseded_count: 0`.
    #
    # It reached the field: `transmittal_pdf` renders `change.title()` as the issuance column, so the
    # transmittal told subcontractors a revised sheet was New -- the flag that decides whether they
    # re-check their shop drawings against it.
    #
    # NOTHING WENT RED, and the reason is the shape of the coverage rather than its absence. The one
    # test of this classification, `test_payroll_drawings.py`, builds A-101 as three SEPARATE drawing
    # records (revs 0/1/2) -- the drawing-log import model, which is the model `register` was written
    # for -- and this file set up the delta model and then read only the route that handles it.
    # *A test that exercises one of two data models cannot see a function that handles only that
    # one, and a handoff each side tests alone is a handoff nobody tests.* So the assertion below is
    # DERIVED from the delta register's own answer rather than from a number written out here.
    ctrl = c.get(f"{P}/drawing-set", headers=HDR).json()
    # Derived from the record fetched above, not from `sheet_no` -- that name is bound 30 lines
    # BELOW this point, and a check that reads a variable the file happens to define later is one
    # reordering away from a NameError. (It would have been the loud kind, which is why the point is
    # worth making here rather than after paying for it.)
    _sheet = rec["data"].get("sheet_number") or rec["data"].get("number")
    a_sheet = next(s for s in ctrl["sheet_index"] if s["sheet_number"] == _sheet)
    assert a_sheet["revisions"] == reg["delta_count"], (a_sheet, reg["delta_count"])
    assert a_sheet["change"] == "revised", a_sheet
    # Exactly one sheet was revised; the rest of the generated Structural set never was. Stated as a
    # RELATION rather than as the fixture's size -- the first draft asserted `new_count == 0`, which
    # was a guess about how many sheets `drawing-set/generate` makes and reds if that series grows.
    assert ctrl["revised_count"] == 1, ctrl["sheet_index"]
    assert ctrl["new_count"] == ctrl["sheet_count"] - 1, (ctrl["new_count"], ctrl["sheet_count"])
    assert ctrl["new_count"] + ctrl["revised_count"] == ctrl["sheet_count"], ctrl
    # the earlier delta is now a superseded revision, carrying why it was superseded
    assert ctrl["superseded_count"] == 1, ctrl
    sup = ctrl["superseded"][0]
    assert (sup["revision"], sup["superseded_by"], sup["source"]) == ("1", "2", "delta"), sup
    assert sup["description"] == "Rebar clarification", sup
    # one record, so no cross-record label ranking happened and nothing is ambiguous
    assert ctrl["order_ambiguous_sheets"] == [], ctrl["order_ambiguous_sheets"]
    assert a_sheet["order_ambiguous"] is False, a_sheet

    # --- sealed issuance (PAdES) — 200 + a valid PDF whether or not e-sign is configured -----------
    c.post(f"{P}/drawing-set/issue", json={"purpose": "Issued for Permit"}, headers=HDR)
    iid = c.get(f"{P}/drawing-set/issuances", headers=HDR).json()["issuances"][0]["id"]
    sealed = c.get(f"{P}/drawing-set/issuances/{iid}/sealed.pdf?name=Jane Roe, AIA", headers=HDR)
    assert sealed.status_code == 200 and sealed.content[:4] == b"%PDF", sealed.status_code
    assert sealed.headers.get("X-Sealed") in ("true", "false")

    # --- REVISE-DARK: markups_carried must count what was COMMITTED ----------------------------
    #
    # Slip-sheeting tags every existing markup `carried_from` so a reviewer re-checks it against the
    # revised sheet. The tagging is wrapped in `except Exception: pass` on purpose — it must never
    # block a revision — and the count used to be incremented in the loop while `db.commit()` sat
    # INSIDE that try. So a failed commit returned a non-zero `markups_carried` over zero tagged
    # markups: the reviewer is told the re-check flags are in place and the marks say nothing.
    sheet_no = rec["data"].get("sheet_number") or rec["data"].get("number")
    for _i in range(3):
        mk = c.post(f"{P}/drawings/markup",
                    json={"sheet_id": sheet_no, "x": 10.0 + _i, "y": 20.0, "note": f"check {_i}"},
                    headers=HDR)
        assert mk.status_code == 201, mk.text[:160]

    r3 = c.post(f"{P}/drawings/{sid}/revise", json={"rev": "3", "description": "Slip-sheet"},
                headers=HDR).json()
    assert r3["markups_carried"] == 3 and r3["markups_to_carry"] == 3, r3
    assert r3["markups_carry_failed"] is None, r3
    tagged = [m for m in c.get(f"{P}/drawings/markup", params={"sheet": sheet_no},
                               headers=HDR).json()
              if (m.get("data") or {}).get("carried_from")]
    assert len(tagged) == 3, tagged

    # THE FAILURE PATH, injected rather than reasoned about. `revise_sheet` commits twice — the
    # revision through `update_record`, then the carried-forward tags — so raising on the second
    # reproduces exactly the swallowed failure.
    for _i in range(2):
        c.post(f"{P}/drawings/markup",
               json={"sheet_id": sheet_no, "x": 50.0 + _i, "y": 60.0, "note": f"new {_i}"},
               headers=HDR)
    from sqlalchemy.orm import Session  # noqa: E402
    _real_commit = Session.commit
    _state = {"n": 0, "arm": False}

    def _flaky_commit(self):
        if _state["arm"]:
            _state["n"] += 1
            if _state["n"] == 2:
                raise RuntimeError("injected: the markup-tagging commit failed")
        return _real_commit(self)

    Session.commit = _flaky_commit
    _state["arm"] = True
    try:
        r4 = c.post(f"{P}/drawings/{sid}/revise", json={"rev": "4", "description": "Slip-sheet 2"},
                    headers=HDR)
    finally:
        _state["arm"] = False
        Session.commit = _real_commit

    assert r4.status_code == 201, r4.text[:200]
    r4j = r4.json()
    # The revision still lands. That is the deliberate half and it is asserted, not assumed.
    assert r4j["revision"] == "4" and r4j["delta_count"] == 4, r4j
    assert c.get(f"{P}/modules/drawing/{sid}", headers=HDR).json()["data"]["revision"] == "4"
    # And the count reports what was persisted: nothing.
    assert r4j["markups_carried"] == 0, r4j
    assert r4j["markups_to_carry"] == 2, r4j
    assert r4j["markups_carry_failed"] == "RuntimeError", r4j
    still_untagged = [m for m in c.get(f"{P}/drawings/markup", params={"sheet": sheet_no},
                                       headers=HDR).json()
                      if not (m.get("data") or {}).get("carried_from")]
    assert len(still_untagged) == 2, still_untagged
    # The partial mutations are rolled back rather than left pending — a later commit in the same
    # request would otherwise flush tags the response says did not land.
    assert all((m.get("data") or {}).get("carried_from") is None for m in still_untagged)

print("REVISE-DARK OK - markups_carried counts what COMMITTED: happy path 3/3 with "
      "markups_carry_failed None; with the tagging commit made to fail, the revision still lands "
      "(rev 4, 4 deltas) and the response reports carried=0 of to_carry=2 with "
      "markups_carry_failed='RuntimeError', with the 2 markups left untagged and not pending")
print(f"DRAWING REVISION OK - two deltas recorded (rev 1, rev 2 citing ASI-003); sheet bumped to rev 2 "
      "with a 2-delta revision block; cross-sheet revision register newest-first w/ instrument rollup; "
      f"issuance sealed PDF (X-Sealed={sealed.headers.get('X-Sealed')}).")

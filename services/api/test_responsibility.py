"""Responsibility matrix (RACI / DACI) — the grid assembly, validation rules (exactly one
Accountable, at least one Responsible), role-column config, starter templates, and the DACI remap.
Run: PYTHONPATH=src ./.venv/Scripts/python.exe test_responsibility.py"""
import json
import os
import re

os.environ["DATABASE_URL"] = "sqlite:///./test_responsibility.db"
os.environ["STORAGE_DIR"] = "./test_storage_responsibility"
os.environ.pop("AEC_RBAC", None)
for _f in ("./test_responsibility.db",):
    if os.path.exists(_f):
        os.remove(_f)

from fastapi.testclient import TestClient  # noqa: E402

from aec_api import responsibility  # noqa: E402
from aec_api.main import app  # noqa: E402


def mk(c, pid, key, data):
    r = c.post(f"/projects/{pid}/modules/{key}", json={"data": data})
    assert r.status_code in (200, 201), f"{key}: {r.status_code} {r.text[:160]}"
    return r.json()["id"]


with TestClient(app) as c:
    pid = c.post("/projects", json={"name": "RACI Tower"}).json()["id"]

    # --- empty matrix: default roles, RACI mode, no rows --------------------------------------
    m = c.get(f"/projects/{pid}/responsibility").json()
    assert m["mode"] == "RACI" and m["count"] == 0, m
    assert "Owner" in m["roles"] and "GC / PM" in m["roles"], m["roles"]
    assert m["letters"] == ["R", "A", "C", "I"] and m["doer"] == "R", m

    # --- templates catalog --------------------------------------------------------------------
    tpls = c.get(f"/projects/{pid}/responsibility/templates").json()["templates"]
    keys = {t["key"] for t in tpls}
    assert {"design_delivery", "buyout", "construction", "closeout"} <= keys, keys

    # --- apply a template -> valid grid -------------------------------------------------------
    r = c.post(f"/projects/{pid}/responsibility/apply-template", json={"key": "construction"})
    assert r.status_code == 200 and r.json()["created"] == 5, r.text[:200]
    m = c.get(f"/projects/{pid}/responsibility").json()
    assert m["count"] == 5, m["count"]
    # every template row is well-formed: exactly one A, at least one R
    assert m["validation"]["clean"] is True, m["validation"]
    assert not m["validation"]["missing_accountable"] and not m["validation"]["no_responsible"], m["validation"]
    # a known cell landed
    rfi_row = next(r for r in m["rows"] if r["activity"].startswith("RFIs"))
    assert rfi_row["assignments"].get("Architect/EOR") == "A", rfi_row
    assert rfi_row["assignments"].get("GC / PM") == "R", rfi_row

    # --- validation catches a broken row (two Accountables, no Responsible) -------------------
    mk(c, pid, "responsibility", {"activity": "Orphan task",
                                  "assignments": {"Owner": "A", "GC / PM": "A"}})
    m = c.get(f"/projects/{pid}/responsibility").json()
    assert m["validation"]["clean"] is False, "double-A + no-R row must fail validation"
    bad = [x for x in m["validation"]["missing_accountable"] if x["activity"] == "Orphan task"]
    assert bad and bad[0]["count"] == 2, m["validation"]["missing_accountable"]
    assert any(x["activity"] == "Orphan task" for x in m["validation"]["no_responsible"]), m["validation"]

    # --- role-column config + DACI mode -------------------------------------------------------
    roles = ["Client", "Lead Appointed Party", "Task Team", "Cx"]
    r = c.put(f"/projects/{pid}/responsibility/config", json={"roles": roles, "mode": "DACI"})
    assert r.status_code == 200 and r.json()["mode"] == "DACI", r.text[:200]
    m = c.get(f"/projects/{pid}/responsibility").json()
    assert m["mode"] == "DACI" and m["doer"] == "D", m
    assert m["roles"] == roles, m["roles"]
    assert m["letters"] == ["D", "A", "C", "I"], m["letters"]

    # --- apply a DACI template: doer letter is remapped R->D ----------------------------------
    pid2 = c.post("/projects", json={"name": "DACI Tower"}).json()["id"]
    c.post(f"/projects/{pid2}/responsibility/apply-template", json={"key": "buyout", "mode": "DACI"})
    m2 = c.get(f"/projects/{pid2}/responsibility").json()
    assert m2["mode"] == "DACI", m2["mode"]
    letters_used = {v for row in m2["rows"] for v in row["assignments"].values()}
    assert "D" in letters_used and "R" not in letters_used, f"DACI template must use D not R: {letters_used}"
    assert m2["validation"]["clean"] is True, m2["validation"]

    # --- ROLES-BIM: the ISO 19650 template brings its OWN role columns (BIM-org personas) ------
    tpls = {t["key"]: t for t in c.get(f"/projects/{pid}/responsibility/templates").json()["templates"]}
    assert "bim_iso19650" in tpls, list(tpls)
    assert tpls["bim_iso19650"]["roles"][0] == "Appointing Party", tpls["bim_iso19650"]["roles"]
    pid3 = c.post("/projects", json={"name": "ISO 19650 Tower"}).json()["id"]
    c.post(f"/projects/{pid3}/responsibility/apply-template", json={"key": "bim_iso19650", "mode": "RACI"})
    m3 = c.get(f"/projects/{pid3}/responsibility").json()
    # applying the BIM template switches the matrix columns to the BIM-org personas
    assert m3["roles"] == ["Appointing Party", "Information Manager", "BIM Manager",
                           "BIM Coordinator", "Task Team", "QA/QC"], m3["roles"]
    assert m3["count"] == 9 and m3["validation"]["clean"] is True, (m3["count"], m3["validation"])
    # every duty has an Information Manager or BIM Manager involved (the info-management line)
    assert all(("Information Manager" in r["assignments"] or "BIM Manager" in r["assignments"])
               for r in m3["rows"]), m3["rows"]

    # unknown template -> 400
    assert c.post(f"/projects/{pid}/responsibility/apply-template", json={"key": "nope"}).status_code == 400

    # --- RESP-ORPHAN: an assignment on a column that is GONE must not count as an assignment -----
    # The defect: `_validate` counted every value in `assignments`, but the grid renders only the
    # CURRENT `roles`. A row whose letters all sit on removed columns therefore rendered as a blank
    # line while the matrix reported itself complete. `unknown_role` — computed since day one and
    # read by nobody — is the finding that explains the blank row.
    #
    # This state is reachable two ways and BOTH are exercised: a config swap (the block at the top
    # of this file already produced it and never looked), and `apply-template`, which appends rows
    # and used to replace the columns.
    pid4 = c.post("/projects", json={"name": "Orphan Tower"}).json()["id"]
    mk(c, pid4, "responsibility", {"activity": "Author models",
                                   "assignments": {"Architect/EOR": "A", "GC / PM": "R"}})
    m4 = c.get(f"/projects/{pid4}/responsibility").json()
    assert m4["validation"]["clean"] is True, "baseline row is well-formed"

    # swap the columns out from under it
    c.put(f"/projects/{pid4}/responsibility/config",
          json={"roles": ["Client", "Task Team"], "mode": "RACI"})
    m4 = c.get(f"/projects/{pid4}/responsibility").json()
    v4 = m4["validation"]
    assert v4["clean"] is False, "a row whose every letter is on a removed column is NOT clean"
    assert [x["activity"] for x in v4["missing_accountable"]] == ["Author models"], v4
    assert v4["missing_accountable"][0]["count"] == 0, v4["missing_accountable"]
    assert [x["activity"] for x in v4["no_responsible"]] == ["Author models"], v4
    assert sorted(x["role"] for x in v4["unknown_role"]) == ["Architect/EOR", "GC / PM"], v4
    # and the load must not credit a role that is not a column — that overstates a real person
    assert v4["accountable_load"] == {}, v4["accountable_load"]

    # --- RESP-ORPHAN: a second template MERGES its columns instead of replacing them -------------
    # The panel's dialog promises "Existing rows are kept". Keeping the rows and discarding what
    # they say is not keeping them.
    pid5 = c.post("/projects", json={"name": "Two Templates"}).json()["id"]
    c.post(f"/projects/{pid5}/responsibility/apply-template", json={"key": "construction"})
    before = c.get(f"/projects/{pid5}/responsibility").json()
    assert before["validation"]["clean"] is True, before["validation"]
    c.post(f"/projects/{pid5}/responsibility/apply-template", json={"key": "bim_iso19650"})
    after = c.get(f"/projects/{pid5}/responsibility").json()
    assert after["count"] == 5 + 9, after["count"]
    # the construction columns survive, the BIM personas are added after them
    assert after["roles"][:len(before["roles"])] == before["roles"], after["roles"]
    assert "Appointing Party" in after["roles"] and "Architect/EOR" in after["roles"], after["roles"]
    assert after["validation"]["unknown_role"] == [], after["validation"]["unknown_role"]
    assert after["validation"]["clean"] is True, after["validation"]

    # --- RESP-ORPHAN: the merge REFUSES rather than truncating past the column cap ---------------
    # `set_config` truncates at MAX_ROLES and the union puts the template's NEW columns last, so a
    # silent truncation would orphan exactly the rows the call is creating. Refuse before mutating.
    pid6 = c.post("/projects", json={"name": "Full House"}).json()["id"]
    c.post(f"/projects/{pid6}/responsibility/apply-template", json={"key": "construction"})
    wide = [f"Role {i}" for i in range(14)]      # 14 + the 6 BIM personas > MAX_ROLES
    c.put(f"/projects/{pid6}/responsibility/config", json={"roles": wide, "mode": "RACI"})
    r6 = c.post(f"/projects/{pid6}/responsibility/apply-template", json={"key": "bim_iso19650"})
    assert r6.status_code == 400, (r6.status_code, r6.text[:200])
    assert "Nothing was changed" in r6.json()["detail"], r6.json()
    m6 = c.get(f"/projects/{pid6}/responsibility").json()
    assert m6["count"] == 5 and m6["roles"] == wide, (m6["count"], m6["roles"])

    # --- RESP-ORPHAN: the rule agrees with the web implementation, case for case ----------------
    # The rule exists twice and cannot be deduplicated across the language boundary: the panel needs
    # it locally so a cell edit repaints the banner without a round-trip. Two copies of one rule is
    # what produced this defect — the client counted every assignment while the grid renders only
    # the current columns. `raciValidationCases.json` is the shared ground, and it is only shared if
    # BOTH sides read it, so this walks the same file `raciValidation.test.ts` walks.
    cases_path = os.path.join(os.path.dirname(__file__),
                              "../../apps/web/src/portal/panels/raciValidationCases.json")
    with open(cases_path, encoding="utf-8") as fh:
        cases = json.load(fh)["cases"]
    assert len(cases) >= 5, f"parity fixture has only {len(cases)} cases"
    for case in cases:
        rows = [{"ref": r["ref"], "activity": r["activity"], "assignments": r["assignments"]}
                for r in case["rows"]]
        mode = "DACI" if case["doer"] == "D" else "RACI"
        got = responsibility._validate(rows, set(case["roles"]), mode)
        want = case["expect"]
        assert got["clean"] is want["clean"], (case["name"], got)
        assert got["missing_accountable"] == want["missing"], (case["name"], got["missing_accountable"])
        assert got["no_responsible"] == want["noR"], (case["name"], got["no_responsible"])
        assert sorted({u["role"] for u in got["unknown_role"]}) == sorted(want["unknown"]), \
            (case["name"], got["unknown_role"])
        assert got["accountable_load"] == want["load"], (case["name"], got["accountable_load"])

    # --- RESP-ORPHAN: the client's copy of the column cap matches this one --------------------
    # The panel disables Restore when the union would overflow, because `set_config` TRUNCATES
    # rather than refusing and the orphans sit at the tail. A client guard set to the wrong number
    # is worse than none: it would refuse valid restores AND still let the real overflow through.
    # Raised in review; gated here because a constant duplicated across a language boundary drifts.
    raci_ts = os.path.join(os.path.dirname(__file__),
                           "../../apps/web/src/portal/panels/raciValidation.ts")
    with open(raci_ts, encoding="utf-8") as fh:
        ts_src = fh.read()
    m_cap = re.search(r"export const MAX_ROLES = (\d+);", ts_src)
    assert m_cap, "raciValidation.ts no longer declares MAX_ROLES — the guard or this gate moved"
    assert int(m_cap.group(1)) == responsibility.MAX_ROLES, \
        (int(m_cap.group(1)), responsibility.MAX_ROLES)

    # --- BULK-PATCH: a column edit and the cells keyed by it are ONE transaction ---------------
    # The panel used to send one PATCH per row and then the config update. A failure part-way
    # committed the rows it had already reached, so a rename left one logical role under two names,
    # only one of which was still a column — and re-running could not find the rows that had moved.
    # Assert by RE-READING every row, never by trusting the response: a response describes what the
    # server meant to do, and the whole defect is a gap between that and what is stored.
    bp = c.post("/projects", json={"name": "Bulk"}).json()["id"]
    c.post(f"/projects/{bp}/responsibility/apply-template", json={"key": "construction"})

    def cells(pid_):
        """role -> [activities carrying a letter on it], read back from the server."""
        out = {}
        for r in c.get(f"/projects/{pid_}/responsibility").json()["rows"]:
            for role in r["assignments"]:
                out.setdefault(role, []).append(r["activity"])
        return out

    before = cells(bp)
    assert before.get("GC / PM"), "the construction template must key cells on 'GC / PM'"
    n_gc = len(before["GC / PM"])
    assert n_gc >= 3, n_gc      # >1 row, or "half-applied" has no meaning to test

    # rename: cells move WITH the column, in one call
    cur = c.get(f"/projects/{bp}/responsibility").json()["roles"]
    r = c.put(f"/projects/{bp}/responsibility/config",
              json={"roles": ["Project Manager" if x == "GC / PM" else x for x in cur],
                    "mode": "RACI", "rename": {"GC / PM": "Project Manager"}})
    assert r.status_code == 200, r.text[:200]
    assert r.json()["rows_remapped"] == n_gc, (r.json(), n_gc)
    after = cells(bp)
    assert "GC / PM" not in after, f"rows left on the old name: {after.get('GC / PM')}"
    assert sorted(after["Project Manager"]) == sorted(before["GC / PM"]), after["Project Manager"]

    # ROLLBACK: a member the engine rejects rolls the WHOLE batch back, rows included.
    import aec_api.modules as _mod
    _real_update = _mod.update_record
    _seen = {"n": 0}

    def _fail_on_third(db, key, project_id, rid, data, actor, party, **kw):
        _seen["n"] += 1
        if _seen["n"] == 3:
            raise RuntimeError("row 3 refused")
        return _real_update(db, key, project_id, rid, data, actor, party, **kw)

    _mod.update_record = _fail_on_third
    try:
        cur = c.get(f"/projects/{bp}/responsibility").json()["roles"]
        try:
            c.put(f"/projects/{bp}/responsibility/config",
                  json={"roles": ["PM2" if x == "Project Manager" else x for x in cur],
                        "mode": "RACI", "rename": {"Project Manager": "PM2"}})
            raise AssertionError("the injected failure did not propagate")
        except RuntimeError as e:
            assert "row 3 refused" in str(e), e
    finally:
        _mod.update_record = _real_update
    assert _seen["n"] == 3, f"the batch kept going past the failure: {_seen['n']} writes attempted"
    rolled = cells(bp)
    assert "PM2" not in rolled, f"a rejected batch left {len(rolled['PM2'])} row(s) renamed"
    assert sorted(rolled["Project Manager"]) == sorted(after["Project Manager"]), rolled
    assert c.get(f"/projects/{bp}/responsibility").json()["roles"] == cur, "the config row survived a rollback"

    # drop: clearing a removed column's cells, also one call
    cur = c.get(f"/projects/{bp}/responsibility").json()["roles"]
    r = c.put(f"/projects/{bp}/responsibility/config",
              json={"roles": [x for x in cur if x != "Project Manager"], "mode": "RACI",
                    "drop": ["Project Manager"]})
    assert r.status_code == 200, r.text[:200]
    assert "Project Manager" not in cells(bp), "drop left cells on the removed column"

    # REFUSE a self-contradicting request, before writing anything.
    cur = c.get(f"/projects/{bp}/responsibility").json()["roles"]
    snapshot = cells(bp)
    # Each case must 400 for ITS OWN reason, so assert the message — the first draft of this loop
    # used a rename whose source AND target were both wrong, so removing the source check still
    # produced a 400 (from the target check) and the mutation survived. A test that asserts only
    # the status code cannot tell which rule refused. The source case below therefore renames one
    # LIVE column onto another live column, which is the merge that silently eats a column's cells.
    for bad, why, msg in (
        ({"roles": cur, "mode": "RACI", "rename": {"Owner": "Architect/EOR"}},
         "source still a column", "still one of the role columns"),
        ({"roles": cur, "mode": "RACI", "rename": {"Nobody": "Client"}},
         "target is not a column", "is not a role column"),
        ({"roles": cur, "mode": "RACI", "drop": ["Owner"]},
         "dropping a live column's cells", "still a role column"),
    ):
        r = c.put(f"/projects/{bp}/responsibility/config", json=bad)
        assert r.status_code == 400, (why, r.status_code, r.text[:160])
        assert msg in r.json()["detail"], (why, r.json()["detail"])
    assert cells(bp) == snapshot, "a refused request wrote something"

    # --- BULK-PATCH: a mode change migrates the doer letter on EXISTING rows -------------------
    # `matrix()` hides any letter not valid in the current mode, so a row left on the old doer does
    # not render wrong — it renders EMPTY, and reports no Responsible. Reached here through
    # apply-template, which is how the mode moves without anyone pressing the mode button.
    md = c.post("/projects", json={"name": "Mode"}).json()["id"]
    c.post(f"/projects/{md}/responsibility/apply-template", json={"key": "construction", "mode": "RACI"})
    seeded = c.get(f"/projects/{md}/responsibility").json()
    assert seeded["validation"]["clean"] is True, seeded["validation"]
    n_before = seeded["count"]
    r = c.post(f"/projects/{md}/responsibility/apply-template",
               json={"key": "closeout", "mode": "DACI"})
    assert r.status_code == 200, r.text[:200]
    assert r.json()["rows_remapped"] == n_before, (r.json(), n_before)
    flipped = c.get(f"/projects/{md}/responsibility").json()
    assert flipped["mode"] == "DACI" and flipped["doer"] == "D", flipped["mode"]
    assert flipped["validation"]["clean"] is True, \
        f"rows stranded on the old doer letter: {flipped['validation']['no_responsible']}"
    assert not any("R" in row["assignments"].values() for row in flipped["rows"]), \
        "an 'R' survived the flip to DACI"

    # --- BULK-PATCH: both routes' audit rows are actually COMMITTED ----------------------------
    # `get_db` never commits, and the engine commits BEFORE the route records the audit row — so
    # these two were writing an audit entry that was discarded when the session closed. The role
    # columns are the one edit that can orphan a whole grid; it left no trace.
    from aec_api.db import SessionLocal as _SL
    from aec_api.models import AuditLog as _AL
    with _SL() as _db:
        _acts = {a.action for a in _db.query(_AL).all()}
    assert "responsibility.config" in _acts, sorted(_acts)
    assert "responsibility.apply_template" in _acts, sorted(_acts)

print("RESPONSIBILITY OK - grid assembly, single-A / >=1-R validation, role config, RACI<->DACI, templates + "
      "remap, the ROLES-BIM ISO 19650 template (own BIM-org persona columns, 9 info-mgmt duties, clean), and "
      "RESP-ORPHAN: validity is counted over VISIBLE columns, unknown_role explains a blank row, a second "
      "template merges its columns, and the merge refuses past the cap instead of truncating; and "
      "BULK-PATCH: a column rename/drop moves its cells in ONE transaction that rolls back whole, a "
      "self-contradicting request is refused before writing, a mode change migrates the doer letter "
      "on existing rows, and both routes' audit rows are committed")

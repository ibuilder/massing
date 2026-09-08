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

print("RESPONSIBILITY OK - grid assembly, single-A / >=1-R validation, role config, RACI<->DACI, templates + "
      "remap, the ROLES-BIM ISO 19650 template (own BIM-org persona columns, 9 info-mgmt duties, clean), and "
      "RESP-ORPHAN: validity is counted over VISIBLE columns, unknown_role explains a blank row, a second "
      "template merges its columns, and the merge refuses past the cap instead of truncating")

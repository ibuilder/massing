"""Naming conventions (A3): container-filename + NCS sheet-ID validation and register audit.
Run: PYTHONPATH=src ./.venv/Scripts/python.exe test_naming.py"""
import os

os.environ["DATABASE_URL"] = "sqlite:///./test_naming.db"
os.environ["STORAGE_DIR"] = "./test_storage_naming"
os.environ.pop("AEC_RBAC", None)
for _f in ("./test_naming.db",):
    if os.path.exists(_f):
        os.remove(_f)

from fastapi.testclient import TestClient  # noqa: E402

from aec_api import naming, reports  # noqa: E402
from aec_api.main import app  # noqa: E402

# --- unit: the validators -------------------------------------------------------------------------
good = naming.validate_container_name("DR_A_GroundFloorPlan_P01_2026-07-05")
assert good["valid"] is True, good
assert good["fields"]["discipline"] == "A" and good["fields"]["revision"] == "P01", good
bad = naming.validate_container_name("Final.pdf")
assert bad["valid"] is False and bad["issues"], bad
bad_rev = naming.validate_container_name("DR_A_Plan_final_2026")   # revision not P01-like
assert bad_rev["valid"] is False, bad_rev

assert naming.validate_sheet_id("A-101")["valid"] is True, "A-101 should parse"
assert naming.validate_sheet_id("hello")["valid"] is False, "garbage should fail"

with TestClient(app) as c:
    pid = c.post("/projects", json={"name": "P"}).json()["id"]

    conv = c.get(f"/projects/{pid}/naming/conventions").json()
    assert conv["container"]["pattern"].startswith("Type_Discipline"), conv

    v = c.get(f"/projects/{pid}/naming/validate", params={"name": "S-201", "kind": "sheet"}).json()
    assert v["valid"] is True and v["fields"]["discipline_code"] == "S", v

    # --- registers: one compliant + one not, for both containers and drawings --------------------
    c.post(f"/projects/{pid}/modules/information_container",
           json={"data": {"title": "GF plan", "container_id": "DR_A_GroundFloorPlan_P01_2026-07-05"}})
    c.post(f"/projects/{pid}/modules/information_container",
           json={"data": {"title": "loose", "container_id": "New file (2).pdf"}})
    c.post(f"/projects/{pid}/modules/drawing", json={"data": {"number": "A-101", "sheet_number": "A-101"}})
    c.post(f"/projects/{pid}/modules/drawing", json={"data": {"number": "sketch", "sheet_number": "sketch"}})

    a = c.get(f"/projects/{pid}/naming/audit").json()
    assert a["containers"]["total"] == 2 and a["containers"]["compliant"] == 1, a["containers"]
    assert a["containers"]["compliance_pct"] == 50.0, a["containers"]
    assert a["sheets"]["total"] == 2 and a["sheets"]["compliant"] == 1, a["sheets"]
    assert len(a["containers"]["violations"]) == 1 and len(a["sheets"]["violations"]) == 1, a
    # Both containers above carry a `container_id`, so `named` IS `total` here and the 50% is over
    # the register. That is what made the defect below invisible: the fixture never had a row in
    # the normal pre-naming state.
    assert a["containers"]["named"] == 2 and a["containers"]["unnamed_count"] == 0, a["containers"]

    # --- NAMING-UNREAD: a container with no ISO 19650 ID recorded is not a MISNAMED container ----
    # `container_id` is an OPTIONAL field on `information_container` (only `title` is required), so
    # registering a container before its name is settled is the normal order of work. The audit used
    # to fall back to the title and validate THAT against the filename pattern, reporting the result
    # as a naming violation — character-for-character the same issue string as a genuinely misnamed
    # file. Three unnamed rows took a 1-of-2 register to "20.0% compliant" with 4 violations.
    for t in ("Ground floor plan", "Structural calcs", "Fire strategy"):
        assert c.post(f"/projects/{pid}/modules/information_container",
                      json={"data": {"title": t}}).status_code == 201, t
    a2 = c.get(f"/projects/{pid}/naming/audit").json()
    cb = a2["containers"]
    assert cb["total"] == 5, cb
    assert cb["named"] == 2 and cb["unnamed_count"] == 3, cb
    assert cb["compliance_pct"] == 50.0, "the percentage is over `named`, never over `total`"
    assert cb["violations_count"] == 1, "an unrecorded ID is not a violation"
    assert {u["title"] for u in cb["unnamed"]} == {"Ground floor plan", "Structural calcs",
                                                   "Fire strategy"}, cb["unnamed"]
    assert all(u["ref"].startswith("IC-") for u in cb["unnamed"]), cb["unnamed"]
    # The violation row is FINDABLE and names the string that was ruled on, which is NOT the title.
    v = cb["violations"][0]
    assert v["ref"].startswith("IC-") and v["name"] == "New file (2).pdf" and v["title"] == "loose", v
    assert v["issues"] and "_'-separated fields" in v["issues"][0], v
    assert cb["violations_truncated"] is False and cb["unnamed_truncated"] is False, cb
    assert a2["max_violations"] == naming.MAX_VIOLATIONS == 200, a2["max_violations"]

    # The basis travels WITH the verdict: `/naming/conventions` is a strict subset of this response,
    # which is why its client method was deleted rather than the audit's `conventions` key ignored.
    assert a2["conventions"] == conv == naming.conventions(), "the audit must carry its own basis"

    # --- the drawing side's `unnamed` is structurally empty, and this pins WHY ---------------------
    # `number` is a REQUIRED field on the `drawing` module, and the subject falls back from
    # `sheet_number` to it — both are drawing numbers, so that fallback stays inside the naming
    # family rather than crossing out of it the way the container one did. Make `number` optional
    # and un-numbered drawings start reporting as un-named instead of as misnamed, which is the
    # branch below existing rather than being pruned as unoccupiable.
    no_num = c.post(f"/projects/{pid}/modules/drawing", json={"data": {"title": "no number"}})
    assert no_num.status_code == 422, "the `number` field must stay required for the claim above"
    assert "number" in no_num.json()["detail"], no_num.json()
    assert a2["sheets"]["named"] == a2["sheets"]["total"] == 2, a2["sheets"]
    assert a2["sheets"]["unnamed"] == [] and a2["sheets"]["unnamed_count"] == 0, a2["sheets"]

    # --- the fix loop: check ONE name without touching a register --------------------------------
    good_chk = c.get(f"/projects/{pid}/naming/validate",
                     params={"name": "DR_A_GroundFloorPlan_P01_2026-07-05"}).json()
    assert good_chk["valid"] is True and good_chk["fields"]["revision"] == "P01", good_chk
    bad_chk = c.get(f"/projects/{pid}/naming/validate", params={"name": "New file (2).pdf"}).json()
    assert bad_chk["valid"] is False and bad_chk["issues"], bad_chk

    # --- report + PDF ----------------------------------------------------------------------------
    # The PDF carried the same defect and is the worse place for it: it leaves the building.
    assert "naming" in {x["id"] for x in reports.catalog()}, "naming missing from catalog"
    rep = c.get(f"/projects/{pid}/reports/naming.pdf")
    assert rep.status_code == 200 and rep.content[:4] == b"%PDF", rep.status_code
    from aec_api.db import SessionLocal
    from aec_api.report_builders import _naming
    _db = SessionLocal()
    try:
        rpt = _naming(_db, pid, "P")
    finally:
        _db.close()
    kpis = dict(rpt.kpis)
    assert kpis["Container compliance"] == "50.0% of 2 named, 3 awaiting a name", kpis
    tables = {t["name"]: t for t in rpt.tables}
    assert "Containers awaiting a recorded Container ID" in tables, sorted(tables)
    assert len(tables["Containers awaiting a recorded Container ID"]["rows"]) == 3, tables
    # The unnamed rows must NOT appear as violations, and the violation that remains carries its ref.
    viol = tables["Container naming violations"]["rows"]
    assert len(viol) == 1 and viol[0][1] == "New file (2).pdf", viol
    assert viol[0][0].startswith("IC-"), viol
    # "(all compliant)" is a claim. A drawing register with rows and no names must not make it.
    assert "Drawings awaiting a recorded number" not in tables, "`number` is required; see above"

print("NAMING OK - container pattern Type_Discipline_Description_Revision_Date validated (good/bad + "
      "bad revision); NCS sheet IDs via the D3 parser (A-101/S-201 ok, garbage fails); register audit "
      "= 50% container + 50% sheet compliance with violation lists; report PDF served. NAMING-UNREAD: "
      "3 containers with no container_id are 3 UNNAMED rows, not 3 violations - 50.0% over the 2 "
      "named, where the old denominator gave 20.0% of 5 with 4 identical-issue violations; the sheet "
      "side's unnamed list is empty BECAUSE `number` is required (a POST without it is 422); the "
      "audit carries its own `conventions`; /naming/validate checks one name on demand")

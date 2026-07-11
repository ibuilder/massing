"""Responsibility matrix (RACI / DACI) — the grid assembly, validation rules (exactly one
Accountable, at least one Responsible), role-column config, starter templates, and the DACI remap.
Run: PYTHONPATH=src ./.venv/Scripts/python.exe test_responsibility.py"""
import os

os.environ["DATABASE_URL"] = "sqlite:///./test_responsibility.db"
os.environ["STORAGE_DIR"] = "./test_storage_responsibility"
os.environ.pop("AEC_RBAC", None)
for _f in ("./test_responsibility.db",):
    if os.path.exists(_f):
        os.remove(_f)

from fastapi.testclient import TestClient  # noqa: E402

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

    # unknown template -> 400
    assert c.post(f"/projects/{pid}/responsibility/apply-template", json={"key": "nope"}).status_code == 400

print("RESPONSIBILITY OK - grid assembly, single-A / >=1-R validation, role config, RACI<->DACI, templates + remap")

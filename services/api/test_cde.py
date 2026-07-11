"""ISO 19650 CDE container discipline + information-requirements register.
Run: PYTHONPATH=src ./.venv/Scripts/python.exe test_cde.py"""
import os
from datetime import date, timedelta

os.environ["DATABASE_URL"] = "sqlite:///./test_cde.db"
os.environ["STORAGE_DIR"] = "./test_storage_cde"
os.environ.pop("AEC_RBAC", None)
for _f in ("./test_cde.db",):
    if os.path.exists(_f):
        os.remove(_f)

from fastapi.testclient import TestClient  # noqa: E402

from aec_api.main import app  # noqa: E402


def _create(c, pid, key, data):
    r = c.post(f"/projects/{pid}/modules/{key}", json={"data": data})
    assert r.status_code == 201, f"{key}: {r.text[:160]}"
    return r.json()


def _act(c, pid, key, rid, action):
    r = c.post(f"/projects/{pid}/modules/{key}/{rid}/transition", json={"action": action})
    assert r.status_code == 200, f"{action}: {r.text[:160]}"
    return r.json()


with TestClient(app) as c:
    pid = c.post("/projects", json={"name": "P"}).json()["id"]

    # --- requirements register: EIR + BEP issued; AIR missing -> core coverage incomplete ---------
    eir = _create(c, pid, "info_requirement", {"title": "Project EIR",
        "req_type": "EIR - Exchange Information Requirements", "appointing_party": "Owner LLC",
        "lead_appointed_party": "GC Inc"})
    _act(c, pid, "info_requirement", eir["id"], "issue")
    bep = _create(c, pid, "info_requirement", {"title": "BIM Execution Plan",
        "req_type": "BEP - BIM Execution Plan", "lead_appointed_party": "GC Inc"})
    _act(c, pid, "info_requirement", bep["id"], "issue")

    reg = c.get(f"/projects/{pid}/info-requirements/register").json()
    assert reg["total"] == 2, reg["total"]
    assert reg["by_type"]["EIR"]["issued"] == 1, reg["by_type"]
    assert "AIR" in reg["core_coverage"]["missing"] and reg["core_coverage"]["complete"] is False, \
        reg["core_coverage"]

    # --- cascade (ISO 19650 flow-down): link EIR -> OIR (valid); leave BEP orphan; a wrong-way PIR --
    oir = _create(c, pid, "info_requirement", {"title": "Org OIR",
        "req_type": "OIR - Organizational Information Requirements"})
    c.patch(f"/projects/{pid}/modules/info_requirement/{eir['id']}", json={"derives_from": oir["id"]})
    _create(c, pid, "info_requirement", {"title": "Wrong-way PIR",
        "req_type": "PIR - Project Information Requirements", "derives_from": eir["id"]})
    cas = c.get(f"/projects/{pid}/info-requirements/cascade").json()
    assert cas["total"] == 4, cas["total"]
    assert cas["linked"] == 2, cas["linked"]                       # eir->oir and pir->eir
    assert any(r["type"] == "OIR" for r in cas["roots"]), cas["roots"]
    assert any(o["type"] == "BEP" for o in cas["orphans"]), cas["orphans"]   # non-OIR, no upstream link
    assert any(m["type"] == "PIR" and m["parent_type"] == "EIR" for m in cas["misdirected"]), cas["misdirected"]
    assert oir["id"] in cas["children"] and eir["id"] in cas["children"][oir["id"]], cas["children"]

    # --- delivery plan (MIDP/TIDP): requirements against programme dates + LOIN coverage -----------
    today = date.today()
    _create(c, pid, "info_requirement", {"title": "Overdue struct EIR",
        "req_type": "TIDP - Task Information Delivery Plan",
        "due_date": (today - timedelta(days=5)).isoformat(),
        "loin_geometry": "Detailed / fabrication", "loin_information": "Full properties"})
    _create(c, pid, "info_requirement", {"title": "Due-soon arch EIR",
        "req_type": "TIDP - Task Information Delivery Plan",
        "due_date": (today + timedelta(days=10)).isoformat()})
    _create(c, pid, "info_requirement", {"title": "Future MEP EIR",
        "req_type": "TIDP - Task Information Delivery Plan",
        "due_date": (today + timedelta(days=90)).isoformat()})
    dp = c.get(f"/projects/{pid}/info-requirements/delivery-plan").json()
    assert dp["overdue"] >= 1, dp["overdue"]
    assert dp["due_soon"] >= 1, dp["due_soon"]
    # the next deliverable is the earliest un-issued dated one (the overdue TIDP)
    assert dp["next_deliverable"] and dp["next_deliverable"]["status"] == "overdue", dp["next_deliverable"]
    # LOIN coverage counts the one requirement that states a Level of Information Need
    assert dp["loin_coverage_pct"] and dp["loin_coverage_pct"] > 0, dp["loin_coverage_pct"]
    # per-month roll-up present for the dated requirements
    assert dp["by_month"] and any(m["overdue"] >= 1 for m in dp["by_month"]), dp["by_month"]

    # --- CDE container: WIP -> Shared -> Published, with gates --------------------------------------
    a1 = _create(c, pid, "information_container", {"title": "Arch GA plans", "info_type": "Drawing",
        "discipline": "Architectural", "originator": "AR"})
    # share requires a suitability code
    r = c.post(f"/projects/{pid}/modules/information_container/{a1['id']}/transition",
               json={"action": "share"})
    assert r.status_code == 400 and "Suitability" in r.text, r.text[:160]
    c.patch(f"/projects/{pid}/modules/information_container/{a1['id']}",
            json={"suitability_code": "S2 - Shared for information"})
    _act(c, pid, "information_container", a1["id"], "share")
    # publish requires a revision
    r = c.post(f"/projects/{pid}/modules/information_container/{a1['id']}/transition",
               json={"action": "publish"})
    assert r.status_code == 400 and "Revision" in r.text, r.text[:160]
    c.patch(f"/projects/{pid}/modules/information_container/{a1['id']}",
            json={"revision": "P01", "suitability_code": "A - Published for construction"})
    pub = _act(c, pid, "information_container", a1["id"], "publish")
    assert pub["workflow_state"] == "published", pub["workflow_state"]

    # a second container left in WIP with no metadata (drags completeness down)
    _create(c, pid, "information_container", {"title": "Draft struct model", "info_type": "Model"})

    st = c.get(f"/projects/{pid}/cde/status").json()
    assert st["total"] == 2, st["total"]
    assert st["by_state"]["published"] == 1 and st["by_state"]["wip"] == 1, st["by_state"]
    assert st["by_suitability"].get("A") == 1, st["by_suitability"]
    d = st["discipline"]
    assert d["revision_control_pct"] == 50.0, d          # 1 of 2 has a revision
    assert d["approval_status_pct"] == 50.0, d           # 1 of 2 past WIP
    assert d["metadata_completeness_pct"] == 50.0, d     # only the published one is complete

print("CDE OK - EIR+BEP issued (AIR missing -> core incomplete); container WIP->Shared->Published "
      "gated on suitability then revision; rollup 1 published / 1 wip, discipline 50% across the board")

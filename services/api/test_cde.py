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

from aec_api import cde  # noqa: E402
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

    # --- CASCADE-DARK: a ROOT is not a coverage failure ------------------------------------------
    # `coverage_pct` was `linked / total`, and this engine's own comment calls OIRs "legitimately
    # unlinked" two lines before putting them in that denominator — so the number had a permanent
    # ceiling below 100 on every well-formed cascade, and a project holding one OIR and nothing else
    # read 0.0% beside ZERO orphans. `expected` is the population that must trace up.
    assert cas["expected"] == 3, cas["expected"]            # 4 records, 1 of them the OIR root
    assert cas["linked"] == 2 and cas["coverage_pct"] == 66.7, cas["coverage_pct"]
    assert cas["linked"] <= cas["expected"], "linked must never exceed its own denominator"

    # --- "never linked" is not "linked to something that is GONE" --------------------------------
    # `derives_from` is a reference field and the parent can be deleted under it. Both used to land
    # in one undifferentiated `orphans` list, so a requirement somebody HAD linked rendered
    # character-for-character like one nobody had touched. Two repairs, so two lists.
    ghost = _create(c, pid, "info_requirement", {"title": "Interim PIR",
        "req_type": "PIR - Project Information Requirements", "derives_from": oir["id"]})
    child = _create(c, pid, "info_requirement", {"title": "Commissioning handover EIR",
        "req_type": "EIR - Exchange Information Requirements", "derives_from": ghost["id"]})
    assert c.delete(f"/projects/{pid}/modules/info_requirement/{ghost['id']}").status_code == 200
    cas2 = c.get(f"/projects/{pid}/info-requirements/cascade").json()
    assert cas2["dangling_count"] == 1, cas2["dangling"]
    dang = cas2["dangling"][0]
    assert dang["id"] == child["id"] and dang["missing_parent"] == ghost["id"], dang
    assert all(o["id"] != child["id"] for o in cas2["orphans"]), \
        "a broken reference is not an unlinked requirement"
    assert cas2["orphan_count"] == len(cas2["orphans"]) >= 1, cas2["orphan_count"]
    # The distinguishing fact was ALREADY in the response, in a key no client declared: `nodes`
    # carries the stored `derives_from` whether or not it resolves.
    by_id = {n["id"]: n for n in cas2["nodes"]}
    assert by_id[child["id"]]["derives_from"] == ghost["id"], by_id[child["id"]]
    assert ghost["id"] not in by_id, "the parent really is gone"
    # The tree the card is named after: every node and every edge, bounded and the bound declared.
    assert cas2["nodes_truncated"] is False and cas2["max_nodes"] == cde.MAX_CASCADE_NODES == 2000
    assert len(cas2["nodes"]) == cas2["total"], (len(cas2["nodes"]), cas2["total"])
    assert all(kids == sorted(kids) for kids in cas2["children"].values()), "edges sort, so the tree is deterministic"

    # A register holding nothing BELOW the top tier has no coverage question, and `None` says so
    # where `0.0` reads as a failure.
    pid2 = c.post("/projects", json={"name": "cascade-root-only"}).json()["id"]
    _create(c, pid2, "info_requirement", {"title": "Only OIR",
        "req_type": "OIR - Organizational Information Requirements"})
    solo = c.get(f"/projects/{pid2}/info-requirements/cascade").json()
    assert solo["total"] == 1 and solo["expected"] == 0, solo
    assert solo["coverage_pct"] is None, "0.0% over nothing expected is a failure claim about a root"
    assert solo["orphans"] == [] and solo["dangling"] == [] and len(solo["roots"]) == 1, solo

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

    # --- exchange acceptance (ISO 19650-6): the published container is acceptable; a shared one that
    #     lacks a revision fails traceability + authorization -------------------------------------------
    a2 = _create(c, pid, "information_container", {"title": "MEP model", "info_type": "Model",
        "discipline": "Mechanical", "originator": "ME", "suitability_code": "S2 - Shared for information"})
    _act(c, pid, "information_container", a2["id"], "share")   # shared, no revision -> not authorized/traceable
    ea = c.get(f"/projects/{pid}/cde/exchange-acceptance").json()
    assert ea["reviewed"] == 2, ea["reviewed"]               # the published + the shared one (WIP excluded)
    assert ea["nonconforming_count"] == 1, ea                # the shared MEP model
    nc = ea["nonconforming"][0]
    assert "authorization" in nc["failed"] and "traceability" in nc["failed"], nc
    assert ea["criteria_pct"]["suitability"] == 100.0, ea["criteria_pct"]   # both have a suitability code
    assert ea["acceptable"] is False, ea

print("CDE OK - EIR+BEP issued (AIR missing -> core incomplete); container WIP->Shared->Published "
      "gated on suitability then revision; rollup 1 published / 1 wip, discipline 50% across the "
      "board. CASCADE-DARK: coverage_pct is over `expected` (the requirements that must trace up) "
      "and not `total`, so a root no longer counts against it - 66.7% here, None on a register "
      "holding only an OIR where the shipped number said 0.0% beside zero orphans; a `derives_from` "
      "pointing at a DELETED record is `dangling` with the broken id named rather than an `orphan`, "
      "because re-pointing a reference and making a first link are different repairs; and `nodes` + "
      "`children` are the tree the flow-down card is named after, bounded at 2,000 with the bound "
      "declared")

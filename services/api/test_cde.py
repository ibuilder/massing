"""ISO 19650 CDE container discipline + information-requirements register.
Run: PYTHONPATH=src ./.venv/Scripts/python.exe test_cde.py"""
import os

os.environ["DATABASE_URL"] = "sqlite:///./test_cde.db"
os.environ["STORAGE_DIR"] = "./test_storage_cde"
os.environ.pop("AEC_RBAC", None)
for _f in ("./test_cde.db",):
    if os.path.exists(_f):
        os.remove(_f)

from fastapi.testclient import TestClient             # noqa: E402
from aec_api.main import app                          # noqa: E402


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

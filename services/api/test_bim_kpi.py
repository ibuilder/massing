"""BIM KPI scorecard (10-category rollup) + handover data-drop acceptance gate.
Run: PYTHONPATH=src ./.venv/Scripts/python.exe test_bim_kpi.py"""
import os

os.environ["DATABASE_URL"] = "sqlite:///./test_bim_kpi.db"
os.environ["STORAGE_DIR"] = "./test_storage_bim_kpi"
os.environ.pop("AEC_RBAC", None)
for _f in ("./test_bim_kpi.db",):
    if os.path.exists(_f):
        os.remove(_f)

from fastapi.testclient import TestClient  # noqa: E402

from aec_api.main import app  # noqa: E402


def _create(c, pid, key, data):
    r = c.post(f"/projects/{pid}/modules/{key}", json={"data": data})
    assert r.status_code == 201, f"{key}: {r.text[:160]}"
    return r.json()


def _act(c, pid, key, rid, action):
    c.post(f"/projects/{pid}/modules/{key}/{rid}/transition", json={"action": action})


with TestClient(app) as c:
    pid = c.post("/projects", json={"name": "P"}).json()["id"]

    # --- empty project: everything n/a, handover not accepted ---------------------------------------
    sc0 = c.get(f"/projects/{pid}/bim-kpi/scorecard").json()
    assert len(sc0["categories"]) == 10, len(sc0["categories"])
    assert sc0["summary"]["na"] == 10, sc0["summary"]        # nothing scored yet
    assert sc0["model_scored"] is False, sc0["model_scored"]
    ha0 = c.get(f"/projects/{pid}/handover/acceptance").json()
    assert ha0["accepted"] is False, ha0

    # --- populate the inputs the scorecard reads ---------------------------------------------------
    eir = _create(c, pid, "info_requirement", {"title": "EIR", "req_type": "EIR - Exchange Information Requirements"})
    _act(c, pid, "info_requirement", eir["id"], "issue")
    bep = _create(c, pid, "info_requirement", {"title": "BEP", "req_type": "BEP - BIM Execution Plan"})
    _act(c, pid, "info_requirement", bep["id"], "issue")
    air = _create(c, pid, "info_requirement", {"title": "AIR", "req_type": "AIR - Asset Information Requirements"})
    _act(c, pid, "info_requirement", air["id"], "issue")

    ic = _create(c, pid, "information_container", {"title": "GA", "info_type": "Drawing",
        "discipline": "Architectural", "originator": "AR"})
    c.patch(f"/projects/{pid}/modules/information_container/{ic['id']}",
            json={"suitability_code": "S2 - Shared for information"})
    _act(c, pid, "information_container", ic["id"], "share")
    c.patch(f"/projects/{pid}/modules/information_container/{ic['id']}", json={"revision": "P01"})
    _act(c, pid, "information_container", ic["id"], "publish")

    # RFIs — one closed, one open (drags issue resolution)
    r1 = _create(c, pid, "rfi", {"subject": "Q1", "question": "?"}); _act(c, pid, "rfi", r1["id"], "submit")
    _act(c, pid, "rfi", r1["id"], "respond")
    _create(c, pid, "rfi", {"subject": "Q2", "question": "?"})

    # assets with tags + product data
    for i in range(4):
        _create(c, pid, "asset_register", {"name": f"AHU-{i}", "tag": f"MECH-{i}",
                                           "manufacturer": "Trane", "model": "M-1"})

    # handover package
    _create(c, pid, "as_built", {"number": "AB-001"})
    _create(c, pid, "om_manual", {"name": "O&M vol 1"})
    cc = _create(c, pid, "completion_certificate", {"subject": "Substantial completion", "type": "Substantial"})
    _act(c, pid, "completion_certificate", cc["id"], "issue")

    sc = c.get(f"/projects/{pid}/bim-kpi/scorecard").json()
    cats = {x["key"]: x for x in sc["categories"]}
    assert cats["information_requirements"]["grade"] == "good", cats["information_requirements"]
    assert cats["cde_discipline"]["grade"] == "good", cats["cde_discipline"]     # the 1 container is complete
    assert cats["asset_data_readiness"]["grade"] == "good", cats["asset_data_readiness"]  # 100% tagged
    assert cats["handover_assurance"]["grade"] == "good", cats["handover_assurance"]
    assert cats["model_authoring_quality"]["grade"] == "na", cats["model_authoring_quality"]  # no model
    assert sc["summary"]["na"] < 10 and sc["summary"]["good"] >= 4, sc["summary"]

    ha = c.get(f"/projects/{pid}/handover/acceptance").json()
    assert ha["accepted"] is True, ha        # reqs + tags + as-built + O&M + accepted cert all present

    # report renders
    rep = c.get(f"/projects/{pid}/reports/bim_kpi.pdf")
    assert rep.status_code == 200 and rep.content[:4] == b"%PDF", rep.status_code

    # --- BEP (A1): ISO 19650 BIM Execution Plan assembled from the same registers -------------------
    from aec_api import reports as _reports  # noqa: E402
    from aec_api.db import SessionLocal as _SL  # noqa: E402
    assert "bep" in {x["id"] for x in _reports.catalog()}, "bep missing from report catalog"
    bepr = _reports.build(_SL(), pid, "bep")
    tnames = {t["name"] for t in bepr.tables}
    assert {"Information requirements register", "Roles, responsibilities & authorities",
            "Level of Information Need (target by stage)", "Information standards & naming",
            "CDE workflow (ISO 19650)", "Model coordination & QA"} <= tnames, tnames
    assert len(bepr.tables) >= 7 and len(bepr.kpis) >= 6, (len(bepr.tables), len(bepr.kpis))
    # every discipline appears as an authoring lead in the roles matrix
    roles = next(t for t in bepr.tables if t["name"] == "Roles, responsibilities & authorities")
    assert any("Architectural lead" in row[0] for row in roles["rows"]), roles["rows"][:3]
    # core coverage KPI reads "complete" (EIR + BEP + AIR all issued above)
    assert any(lbl.startswith("Core coverage") and "complete" in val for lbl, val in bepr.kpis), bepr.kpis
    bpdf = c.get(f"/projects/{pid}/reports/bep.pdf")
    assert bpdf.status_code == 200 and bpdf.content[:4] == b"%PDF", bpdf.status_code

print("BIM KPI OK - empty=10 n/a; populated: info-reqs/CDE/asset/handover all good, model-quality "
      "n/a (no model); handover acceptance passes with reqs+tags+as-built+O&M+cert; report PDF served. "
      "BEP OK - ISO 19650 execution plan assembles 7+ sections (reqs register, roles matrix w/ every "
      "discipline, LOIN-by-stage, naming, CDE workflow, coordination/QA); core EIR/BEP/AIR complete; PDF served")

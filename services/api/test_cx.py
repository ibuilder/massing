"""CX-1 — commissioning loop: model→asset seeding (deduped), phase-typed checklist seeding with
MEP FPT expected values, the system × phase matrix, and the per-system dossier.
Run: PYTHONPATH="src;../data/src" ./.venv/Scripts/python.exe test_cx.py"""
import os

os.environ["DATABASE_URL"] = "sqlite:///./test_cx.db"
os.environ["STORAGE_DIR"] = "./test_storage_cx"
os.environ.pop("AEC_RBAC", None)
for _f in ("./test_cx.db",):
    if os.path.exists(_f):
        os.remove(_f)

from fastapi.testclient import TestClient  # noqa: E402

from aec_api.main import app  # noqa: E402
from aec_api.routers.properties import _INDEX  # noqa: E402

# the five declared phases, spelled here rather than imported so a change to the engine's tuple
# has to be made in two places deliberately
PHASES_EXPECTED = ("Pre-Functional", "Functional", "Integrated Systems", "TAB", "Retro-Cx")

IDX = {
    "g-fan1": {"ifc_class": "IfcFan", "name": "SF-1", "storey": "L1", "system": "AHU-1"},
    "g-fan2": {"ifc_class": "IfcFan", "name": "SF-2", "storey": "L2", "system": "AHU-1"},
    "g-pump": {"ifc_class": "IfcPump", "name": "P-1", "storey": "B1"},          # no system → discipline
    "g-wall": {"ifc_class": "IfcWall", "name": "W1", "storey": "L1"},           # not an asset class
}

with TestClient(app) as c:
    pid = c.post("/projects", json={"name": "Cx"}).json()["id"]

    # no model → seed reports it, creates nothing
    r0 = c.post(f"/projects/{pid}/cx/seed").json()
    assert r0["model_scored"] is False and r0["created"] == 0, r0

    # the MEP register carries the AHU-1 engineering values BEFORE seeding (they become FPT expecteds)
    c.post(f"/projects/{pid}/modules/mep_equipment",
           json={"data": {"tag": "SF-1", "equipment_type": "Supply fan", "system": "AHU-1",
                          "capacity": 5, "capacity_unit": "hp", "flow": 2000, "size": "24x12"}})

    # inject the model index → seed assets + checklists
    _INDEX[pid] = IDX
    r1 = c.post(f"/projects/{pid}/cx/seed").json()
    assert r1["model_scored"] and r1["created"] == 3 and r1["skipped_existing"] == 0, r1
    assert r1["checklists"]["created"] == 6, r1                    # 3 assets × (Pre-Functional+Functional)
    # re-seed is idempotent: assets deduped by GUID, checklists by (asset, phase)
    r2 = c.post(f"/projects/{pid}/cx/seed").json()
    assert r2["created"] == 0 and r2["skipped_existing"] == 3, r2
    assert r2["checklists"]["created"] == 0, r2

    assets = c.get(f"/projects/{pid}/modules/asset_register?limit=100").json()
    rows = assets if isinstance(assets, list) else assets.get("items", [])
    ah = [a for a in rows if (a.get("data") or {}).get("system") == "AHU-1"]
    assert len(ah) == 2 and all((a["data"] or {}).get("guid", "").startswith("g-fan") for a in ah), rows
    pump = next(a for a in rows if (a.get("data") or {}).get("guid") == "g-pump")
    assert pump["data"]["system"] == "Plumbing", pump              # discipline fallback

    # Functional tests carry the FPT expected values from the MEP register (AHU-1 only)
    cx_recs = c.get(f"/projects/{pid}/modules/commissioning?limit=100").json()
    cx_rows = cx_recs if isinstance(cx_recs, list) else cx_recs.get("items", [])
    fn_ahu = [x for x in cx_rows if (x.get("data") or {}).get("test_type") == "Functional"
              and (x.get("data") or {}).get("system") == "AHU-1"]
    assert len(fn_ahu) == 2 and all("Expected (FPT)" in ((x["data"] or {}).get("deficiencies") or "")
                                    for x in fn_ahu), fn_ahu
    assert any("SF-1.flow=2000" in ((x["data"] or {}).get("deficiencies") or "") for x in fn_ahu), fn_ahu

    # walk one AHU-1 Functional test through: result Pass, tested → accepted
    t0 = fn_ahu[0]
    c.patch(f"/projects/{pid}/modules/commissioning/{t0['id']}", json={"result": "Pass"})
    for a in ("test", "accept"):
        tr = c.post(f"/projects/{pid}/modules/commissioning/{t0['id']}/transition", json={"action": a})
        assert tr.status_code == 200, (a, tr.text[:160])

    # matrix: AHU-1 row has 2 assets, 4 tests, 1 accepted; the Functional cell shows the pass
    mx = c.get(f"/projects/{pid}/cx/matrix").json()
    ahu = next(s for s in mx["systems"] if s["system"] == "AHU-1")
    assert ahu["assets"] == 2 and ahu["tests"] == 4 and ahu["accepted"] == 1, ahu
    assert ahu["complete_pct"] == 25.0, ahu
    fn_cell = ahu["phases"]["Functional"]
    assert fn_cell["total"] == 2 and fn_cell["tested"] == 1 and fn_cell["accepted"] == 1, fn_cell
    assert fn_cell["pass"] == 1 and fn_cell["fail"] == 0, fn_cell
    mech = next(s for s in mx["systems"] if s["system"] == "Plumbing")
    assert mech["assets"] == 1 and mech["tests"] == 2 and mech["accepted"] == 0, mech

    # ---- CX-CELL-FLAT -------------------------------------------------------------------
    # The four result states PARTITION the cell, on every cell of every row. This is the
    # assertion the old shape could not satisfy: it carried `pass` and `fail` only, so a
    # Conditional or unrecorded result was in no bucket and the parts never summed to `total`.
    for srow in mx["systems"]:
        for ph, cl in srow["phases"].items():
            if cl is None:
                continue
            assert cl["pass"] + cl["fail"] + cl["conditional"] + cl["no_result"] == cl["total"], \
                (srow["system"], ph, cl)
            assert cl["accepted"] <= cl["tested"] <= cl["total"], (srow["system"], ph, cl)
    # and every counted test is in a column — the row total cannot exceed the cells on screen
    for srow in mx["systems"]:
        shown = sum((srow["phases"].get(p) or {}).get("total", 0) for p in mx["phases"])
        assert shown == srow["tests"], (srow["system"], shown, srow["tests"], mx["phases"])

    # Defect 1, as measured: two systems of ten Functional tests, one ALL TESTED (5 Conditional,
    # 2 Pass, 1 Fail, 2 unrecorded) and one with nothing done. Before this item both cells read
    # `0/10` and only the single Fail distinguished them.
    for i in range(10):
        res = ("Conditional" if i < 5 else "Pass" if i < 7 else "Fail" if i == 7 else "")
        data = {"system": "FLAT-A", "test_type": "Functional"}
        if res:
            data["result"] = res
        rec = c.post(f"/projects/{pid}/modules/commissioning", json={"data": data}).json()
        tr = c.post(f"/projects/{pid}/modules/commissioning/{rec['id']}/transition",
                    json={"action": "test"})
        assert tr.status_code == 200, tr.text[:160]
    for _ in range(10):
        c.post(f"/projects/{pid}/modules/commissioning",
               json={"data": {"system": "FLAT-B", "test_type": "Functional"}})
    # Defect 3: `test_type` is a select and select options are SUGGESTIONS, not a closed enum
    # (`module_schema.validate_record` says so), so both of these are ordinary stored data.
    c.post(f"/projects/{pid}/modules/commissioning", json={"data": {"system": "CHW"}})
    c.post(f"/projects/{pid}/modules/commissioning",
           json={"data": {"system": "CHW", "test_type": "Seasonal"}})

    mx2 = c.get(f"/projects/{pid}/cx/matrix").json()
    a_cell = next(s for s in mx2["systems"] if s["system"] == "FLAT-A")["phases"]["Functional"]
    b_cell = next(s for s in mx2["systems"] if s["system"] == "FLAT-B")["phases"]["Functional"]
    assert a_cell == {"total": 10, "tested": 10, "accepted": 0, "pass": 2, "fail": 1,
                      "conditional": 5, "no_result": 2}, a_cell
    assert b_cell == {"total": 10, "tested": 0, "accepted": 0, "pass": 0, "fail": 0,
                      "conditional": 0, "no_result": 10}, b_cell
    # the two cells agree on `accepted/total`, which is what the grid used to render — so the pair
    # is only distinguishable through `tested` and the result split
    assert (a_cell["accepted"], a_cell["total"]) == (b_cell["accepted"], b_cell["total"]), (a_cell, b_cell)
    assert a_cell["tested"] != b_cell["tested"], (a_cell, b_cell)

    # Defect 2+3: the unphased test is NOT folded into Pre-Functional, the free-form phase gets a
    # column, and both are named in `extra_phases`.
    from aec_api.closeout import UNSPECIFIED_PHASE
    assert mx2["extra_phases"] == [UNSPECIFIED_PHASE, "Seasonal"], mx2["extra_phases"]
    assert mx2["phases"][:5] == list(PHASES_EXPECTED), mx2["phases"]
    assert mx2["phases"][5:] == [UNSPECIFIED_PHASE, "Seasonal"], mx2["phases"]
    chw = next(s for s in mx2["systems"] if s["system"] == "CHW")
    assert chw["tests"] == 2, chw
    assert chw["phases"]["Pre-Functional"] is None, chw["phases"]
    assert (chw["phases"][UNSPECIFIED_PHASE] or {}).get("total") == 1, chw["phases"]
    assert (chw["phases"]["Seasonal"] or {}).get("total") == 1, chw["phases"]
    assert sum((chw["phases"].get(p) or {}).get("total", 0) for p in mx2["phases"]) == 2, chw
    # row rollups the screen reads
    arow = next(s for s in mx2["systems"] if s["system"] == "FLAT-A")
    assert (arow["tested"], arow["accepted"], arow["conditional"], arow["failed"]) == (10, 0, 5, 1), arow
    assert mx2["note"] and mx2["test_result_basis"], mx2

    # The rollup one file over already drew all three distinctions — assert it still does, so the
    # name and the three buckets cannot drift apart from the matrix that now imports from it.
    roll = c.get(f"/projects/{pid}/closeout/summary").json()["commissioning"]
    assert roll["conditional"] == 5, roll
    assert roll["by_test_type"].get(UNSPECIFIED_PHASE) == 1, roll["by_test_type"]
    assert roll["by_test_type"].get("Seasonal") == 1, roll["by_test_type"]
    assert roll["pass_rate"] is not None and roll["by_result"] and roll["by_state"], roll

    # dossier: assets + tests by phase + expected values + a punch mention (substring, best-effort)
    c.post(f"/projects/{pid}/modules/punchlist",
           json={"data": {"description": "AHU-1 belt guard missing", "location": "L1 mech room"}})
    dz = c.get(f"/projects/{pid}/cx/dossier?system=AHU-1").json()
    assert dz["asset_count"] == 2 and dz["test_count"] == 4 and dz["accepted"] == 1, dz
    assert dz["complete_pct"] == 25.0, dz
    assert set(dz["tests"]) == {"Pre-Functional", "Functional"}, dz["tests"].keys()
    assert dz["expected_values"].get("SF-1.flow") == 2000 and dz["expected_values"].get("SF-1.size") == "24x12", dz
    assert dz["open_punch_mentions"] == 1, dz
    # unknown system → empty but well-formed
    dz2 = c.get(f"/projects/{pid}/cx/dossier?system=Nope").json()
    assert dz2["asset_count"] == 0 and dz2["test_count"] == 0 and dz2["complete_pct"] == 0.0, dz2

    _INDEX.pop(pid, None)

print("CX OK - seed: 3 equipment assets from the index (wall ignored, GUID-deduped on re-seed), "
      "6 phase checklists (assetxPre-Functional/Functional, (asset,phase)-deduped), Functional "
      "stamped with MEP FPT expecteds (SF-1.flow=2000); matrix: AHU-1 2 assets/4 tests/1 accepted "
      "= 25%, Functional cell 2/1/1 with the Pass; dossier: assets+tests-by-phase+expected values "
      "+ 1 open punch mention; unknown system empty but well-formed. "
      "CX-CELL-FLAT: pass+fail+conditional+no_result partitions every cell and every row total is "
      "in a column; FLAT-A (all 10 tested, 5 conditional) and FLAT-B (nothing done) agree on "
      "accepted/total and differ only in tested + the result split; the unphased test buckets as "
      "(unspecified) instead of Pre-Functional and 'Seasonal' gets its own column; the closeout "
      "rollup still draws the same three distinctions the matrix now imports from it")

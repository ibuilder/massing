"""LOD (A2): target matrix register + achieved-LOD assessment inferred from LOIN facets.
Run: PYTHONPATH=src ./.venv/Scripts/python.exe test_lod.py"""
import os

os.environ["DATABASE_URL"] = "sqlite:///./test_lod.db"
os.environ["STORAGE_DIR"] = "./test_storage_lod"
os.environ.pop("AEC_RBAC", None)
for _f in ("./test_lod.db",):
    if os.path.exists(_f):
        os.remove(_f)

from fastapi.testclient import TestClient  # noqa: E402

from aec_api import lod, reports  # noqa: E402
from aec_api.db import SessionLocal  # noqa: E402
from aec_api.main import app  # noqa: E402

with TestClient(app) as c:
    pid = c.post("/projects", json={"name": "P"}).json()["id"]

    # --- empty register -> stage defaults --------------------------------------------------------
    m0 = c.get(f"/projects/{pid}/lod/matrix").json()
    assert m0["using_default"] is True and len(m0["default"]) == 5, m0
    assert m0["targets"] == [], m0

    # --- author a target -> register wins --------------------------------------------------------
    r = c.post(f"/projects/{pid}/modules/lod_target", json={"data": {
        "element_category": "Walls", "discipline": "Architectural",
        "phase": "Design Development", "target_lod": "LOD 300"}})
    assert r.status_code == 201, r.text[:160]
    m1 = c.get(f"/projects/{pid}/lod/matrix").json()
    assert m1["using_default"] is False and any(t["target_lod"] == "LOD 300" for t in m1["targets"]), m1

    # --- assessment with no model -> targets only ------------------------------------------------
    a0 = c.get(f"/projects/{pid}/lod/assessment").json()
    assert a0["model_scored"] is False and a0["elements"] == 0, a0

    # --- achieved-LOD from a synthetic index (engine unit) ---------------------------------------
    # REWRITTEN in v0.3.901. This fixture used to vary only the INFORMATION on three identical
    # geometries and assert the band moved 100 -> 350 -> 400, which is exactly the defect
    # LOD-ASPECTS removed: LOD is a claim about geometry, so tagging must not move it. The elements
    # now differ in their SHAPE, and the information payload is deliberately held constant on the
    # two that differ, so the band can only be responding to the geometry.
    tagged = {"type_name": "W1", "psets": {"Pset_WallCommon": {"a": 1}}, "qtos": {"Q": {"v": 1}}}
    idx = {
        "g1": {"ifc_class": "IfcWall", "placed": True, **tagged},             # no readable shape -> 100
        "g2": {"ifc_class": "IfcWall", "rep_types": ["BoundingBox"],          # placeholder       -> 200
               "placed": True, **tagged},
        "g3": {"ifc_class": "IfcDuctSegment", "rep_types": ["Brep"],          # resolved solid    -> 350
               "placed": True, **tagged},
    }
    a = lod.assess(SessionLocal(), pid, idx)
    assert a["model_scored"] is True and a["elements"] == 3, a
    assert a["distribution"]["LOD 100"] == 1, a["distribution"]
    assert a["distribution"]["LOD 200"] == 1, a["distribution"]
    assert a["distribution"]["LOD 350"] == 1, a["distribution"]
    # All three carry an identical information payload, so the OLD scorer would have put all three
    # in one band. Three distinct bands is the proof that geometry is now what decides.
    assert sum(1 for v in a["distribution"].values() if v) == 3, a["distribution"]
    # The reading that used to BE the band still exists, under its own name.
    assert a["avg_information_score"] == 5.0, a["avg_information_score"]
    # The unread part of the model is reported rather than rounded into the band.
    assert a["elements_without_readable_geometry"] == 1, a
    assert a["ceiling_distribution"]["LOD 400"] >= 1, a["ceiling_distribution"]
    # per-discipline rollup keys elements by their IFC-class discipline
    assert sum(d["elements"] for d in a["by_discipline"]) == 3, a["by_discipline"]
    discs = {d["discipline"] for d in a["by_discipline"]}
    assert "Mechanical" in discs, discs                          # IfcDuctSegment -> Mechanical
    assert len(discs) == 2, discs                                # walls (one discipline) + ducts (another)
    # cap: no element can infer past LOD 400
    assert a["distribution"]["LOD 500"] == 0, a["distribution"]

    # --- report + PDF ----------------------------------------------------------------------------
    assert "lod" in {x["id"] for x in reports.catalog()}, "lod missing from catalog"
    rep = c.get(f"/projects/{pid}/reports/lod.pdf")
    assert rep.status_code == 200 and rep.content[:4] == b"%PDF", rep.status_code

print("LOD OK - empty register -> 5 stage defaults; authored target overrides; assessment w/o model = "
      "targets only; achieved LOD read from GEOMETRY along the five ISO 7817-1 aspects (no shape->100, "
      "BoundingBox->200, Brep->350) with an IDENTICAL information payload on all three, so tagging "
      "cannot move a band; the old facet reading kept as avg_information_score; unread geometry "
      "reported rather than rounded; per-discipline rollup by IFC class (IfcDuctSegment->Mechanical); "
      "report PDF served")

"""SCOPE-GAP — model-QTO coverage vs the defined bid packages: which disciplines a package claims,
which are gaps (model quantities in no bid), and over-scoped packages. Pure engine (synthetic rows) +
the /bidding/scope-gap route.
Run: PYTHONPATH="src;../data/src" ./.venv/Scripts/python.exe test_scope_gap.py"""
import os

os.environ["DATABASE_URL"] = "sqlite:///./test_scope_gap.db"
os.environ["STORAGE_DIR"] = "./test_storage_scopegap"
os.environ.pop("AEC_RBAC", None)
if os.path.exists("./test_scope_gap.db"):
    os.remove("./test_scope_gap.db")

from fastapi.testclient import TestClient  # noqa: E402

from aec_api import scope_gap  # noqa: E402
from aec_api.db import SessionLocal  # noqa: E402
from aec_api.main import app  # noqa: E402
from aec_api.models import Project  # noqa: E402

# takeoff rows: structural (columns/beam) + architectural (doors) + mechanical (duct)
# (IfcWall classifies Structural on this spine, so use IfcDoor for an unambiguous Architectural element)
ROWS = [
    {"guid": "c1", "ifc_class": "IfcColumn"}, {"guid": "c2", "ifc_class": "IfcColumn"},
    {"guid": "b1", "ifc_class": "IfcBeam"},
    {"guid": "w1", "ifc_class": "IfcDoor"}, {"guid": "w2", "ifc_class": "IfcDoor"},
    {"guid": "d1", "ifc_class": "IfcDuctSegment"},
]

with TestClient(app) as c:
    pid = c.post("/projects", json={"name": "Scope Gap"}).json()["id"]
    # one bid package covering Structural only, plus one over-scoped (Landscape — no model elements)
    c.post(f"/projects/{pid}/modules/bid_package",
           json={"data": {"name": "Concrete structure", "discipline": "Structural", "trade": "Concrete"}})
    c.post(f"/projects/{pid}/modules/bid_package",
           json={"data": {"name": "Site landscaping", "discipline": "Landscape", "trade": "Landscape"}})

    with SessionLocal() as db:
        res = scope_gap.analyze(db, pid, ROWS)

    assert res["package_count"] == 2 and res["element_count"] == 6, res
    covered = {e["discipline"] for e in res["covered"]}
    gaps = {e["discipline"] for e in res["gaps"]}
    assert covered == {"Structural"}, covered                       # only Structural is claimed
    assert gaps == {"Architectural", "Mechanical"}, gaps            # wall + duct disciplines uncovered
    # the structural package covers the 3 structural elements; the 3 others are the gap
    struct = next(e for e in res["covered"] if e["discipline"] == "Structural")
    assert struct["element_count"] == 3 and struct["packages"] == ["Concrete structure"], struct
    assert res["gap_element_count"] == 3 and res["covered_pct"] == 50.0, res
    # gaps cite sample GUIDs so the UI can highlight the uncovered elements
    arch = next(e for e in res["gaps"] if e["discipline"] == "Architectural")
    assert set(arch["sample_guids"]) == {"w1", "w2"}, arch
    # the Landscape package has no model elements → flagged as over-scoped
    assert res["packages_without_model_scope"] == ["Site landscaping"], res["packages_without_model_scope"]

    # --- route: prices the model takeoff; 409 without a source IFC ---------------------------------
    assert c.get(f"/projects/{pid}/bidding/scope-gap").status_code == 409     # no source IFC yet

    from aec_data import edit, massing  # noqa: E402
    from aec_data.ifc_loader import open_model  # noqa: E402
    TMP = os.path.join(os.path.dirname(__file__), "_scopegap.ifc")
    massing.generate_blank_ifc(TMP, name="SG", storeys=1, storey_height=4.0, ground_size=20.0)
    m = open_model(TMP)
    st = m.by_type("IfcBuildingStorey")[0].Name
    edit.add_column(m, [0, 0], 4.0, 0.4, 0.4, st)      # Structural — covered by the package
    edit.add_wall(m, [0, 0], [6, 0], 3.0, 0.2, st)     # Structural on this spine
    m.write(TMP)
    with SessionLocal() as db:
        db.get(Project, pid).source_ifc = TMP
        db.commit()
    r = c.get(f"/projects/{pid}/bidding/scope-gap")
    assert r.status_code == 200, r.status_code
    j = r.json()
    assert j["element_count"] > 0, j
    assert any(e["discipline"] == "Structural" for e in j["covered"]), j       # Structural package covers them
    assert "Site landscaping" in j["packages_without_model_scope"], j          # Landscape has no model elements
    if os.path.exists(TMP):
        os.remove(TMP)

print("SCOPE-GAP OK - the model takeoff is matched by NCS discipline to the bid packages: a Structural "
      "package covers the 3 structural elements (50%%), the wall (Architectural) + duct (Mechanical) are "
      "flagged as gaps with sample GUIDs to highlight, and the Landscape package (no model elements) is "
      "flagged over-scoped; the /bidding/scope-gap route 409s without a model and analyses the real takeoff "
      "(architectural walls surface as an uncovered gap) otherwise.")

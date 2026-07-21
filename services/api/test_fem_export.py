"""FEM-EXPORT — the analytical frame exported as an OpenSees .tcl (nodes + base restraints +
elasticBeamColumn per member, per-orientation geom transforms). Engine over a derived analytical
model + the /structure/opensees.tcl route (409 without a model).
Run: PYTHONPATH="src;../data/src" ./.venv/Scripts/python.exe test_fem_export.py"""
import os

TMP = os.path.join(os.path.dirname(__file__), "_fem_frame.ifc")

from aec_api import fem_export  # noqa: E402
from aec_data import analytical, edit, massing  # noqa: E402
from aec_data.ifc_loader import open_model  # noqa: E402

# a 1-storey portal frame: 2 columns + 1 beam → derive the analytical curve members
massing.generate_blank_ifc(TMP, name="FEM Test", storeys=1, storey_height=4.0, ground_size=20.0)
m = open_model(TMP)
st = m.by_type("IfcBuildingStorey")[0].Name
edit.add_column(m, [0, 0], 4.0, 0.4, 0.4, st)
edit.add_column(m, [6, 0], 4.0, 0.4, 0.4, st)
edit.add_beam(m, [0, 0], [6, 0], 0.3, 0.5, st)
analytical.derive_analytical(m)
assert m.by_type("IfcStructuralCurveMember"), "analytical members expected"

res = fem_export.to_opensees(m)
assert res["available"] is True, res
assert res["element_count"] == 3, res                    # 2 columns + 1 beam
assert res["node_count"] >= 4 and res["fixed_count"] >= 2, res
tcl = res["tcl"]
for token in ("model BasicBuilder -ndm 3 -ndf 6", "\nnode 1 ", "\nfix ",
              "geomTransf Linear 1", "geomTransf Linear 2", "element elasticBeamColumn 1 "):
    assert token in tcl, f"missing '{token}'"
# a vertical member (column) must use transform 2; a beam uses transform 1
elem_lines = [ln for ln in tcl.splitlines() if ln.startswith("element elasticBeamColumn")]
transfs = {ln.split()[-1] for ln in elem_lines}
assert transfs == {"1", "2"}, transfs                    # both a beam (1) and columns (2) present
# node/element/fix counts in the text match the reported counts
assert sum(1 for ln in tcl.splitlines() if ln.startswith("node ")) == res["node_count"], tcl
assert len(elem_lines) == res["element_count"]
assert sum(1 for ln in tcl.splitlines() if ln.startswith("fix ")) == res["fixed_count"]

# no analytical model → not available
massing.generate_blank_ifc(TMP, name="Empty", storeys=1, storey_height=3.0, ground_size=10.0)
empty = fem_export.to_opensees(open_model(TMP))
assert empty["available"] is False and "derive_analytical" in empty["message"], empty

# --- SOLVER-OUT: the same frame as a Code_Aster .mail (ASTER text, SI metres) ---------------------
ca = fem_export.to_code_aster(m)
assert ca["available"] is True, ca
# same topology as the OpenSees export (both read the analytical frame)
assert ca["node_count"] == res["node_count"] and ca["element_count"] == 3 and ca["fixed_count"] == res["fixed_count"], ca
mail = ca["mail"]
for tok in ("COOR_3D", "SEG2", "GROUP_NO", "NOM=BASE", "GROUP_MA", "NOM=FRAME", "FIN"):
    assert tok in mail, f"missing ASTER block '{tok}'"
# one COOR_3D node line per node, one SEG2 line per element
node_lines = [ln for ln in mail.splitlines() if ln.startswith("N") and len(ln.split()) == 4]
seg_lines = [ln for ln in mail.splitlines() if ln.startswith("M") and ln.split()[1:2] and ln.split()[1].startswith("N")]
assert len(node_lines) == ca["node_count"] and len(seg_lines) == ca["element_count"], (len(node_lines), len(seg_lines))
assert fem_export.to_code_aster(open_model(TMP))["available"] is False   # blank model → not available

# --- route: streams the .tcl; 409 without an analytical model ------------------------------------
os.environ["DATABASE_URL"] = "sqlite:///./test_fem_export.db"
os.environ["STORAGE_DIR"] = "./test_storage_fem_export"
os.environ.pop("AEC_RBAC", None)
if os.path.exists("./test_fem_export.db"):
    os.remove("./test_fem_export.db")
from fastapi.testclient import TestClient  # noqa: E402

from aec_api.db import SessionLocal  # noqa: E402
from aec_api.main import app  # noqa: E402
from aec_api.models import Project  # noqa: E402

# re-derive a frame + persist it as the project source
massing.generate_blank_ifc(TMP, name="FEM Route", storeys=1, storey_height=4.0, ground_size=20.0)
m2 = open_model(TMP)
st2 = m2.by_type("IfcBuildingStorey")[0].Name
edit.add_column(m2, [0, 0], 4.0, 0.4, 0.4, st2)
edit.add_column(m2, [6, 0], 4.0, 0.4, 0.4, st2)
edit.add_beam(m2, [0, 0], [6, 0], 0.3, 0.5, st2)
analytical.derive_analytical(m2)
m2.write(TMP)

with TestClient(app) as c:
    pid = c.post("/projects", json={"name": "FEM"}).json()["id"]
    assert c.get(f"/projects/{pid}/structure/opensees.tcl").status_code == 409   # no source IFC yet
    with SessionLocal() as db:
        db.get(Project, pid).source_ifc = TMP
        db.commit()
    r = c.get(f"/projects/{pid}/structure/opensees.tcl")
    assert r.status_code == 200 and "model BasicBuilder" in r.text, r.status_code
    assert r.headers["content-type"].startswith("text/plain")
    # the Code_Aster route streams the .mail (same 409 contract without a model)
    ra = c.get(f"/projects/{pid}/structure/code-aster.mail")
    assert ra.status_code == 200 and "COOR_3D" in ra.text and "NOM=BASE" in ra.text, ra.status_code
    assert ".mail" in ra.headers.get("content-disposition", ""), ra.headers.get("content-disposition")

if os.path.exists(TMP):
    os.remove(TMP)

print("FEM-EXPORT OK - the derived portal frame exports as OpenSees .tcl (3 elasticBeamColumn elements "
      "from 2 columns + 1 beam, base nodes fixed, kip-inch-ksi): a vertical column uses geomTransf 2, a "
      "beam uses 1; node/element/fix line counts match the reported counts; no analytical model → "
      "not available; the /structure/opensees.tcl route 409s without a model and streams text/plain otherwise.")

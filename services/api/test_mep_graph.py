"""MEP-GRAPH — port connectivity graph over IfcDistributionPort: connected runs (endpoints, branches,
longest path) + isolated elements. Built over an authored + connect_mep'd duct chain.
Run: PYTHONPATH="src;../data/src" ./.venv/Scripts/python.exe test_mep_graph.py"""
import os

TMP = os.path.join(os.path.dirname(__file__), "_mepgraph.ifc")

from aec_data import edit, massing, mep_graph  # noqa: E402
from aec_data.ifc_loader import open_model  # noqa: E402

massing.generate_blank_ifc(TMP, name="MEP Graph", storeys=1, storey_height=4.0, ground_size=30.0)
m = open_model(TMP)
st = m.by_type("IfcBuildingStorey")[0].Name
# three duct segments in a line + one isolated segment elsewhere
d1 = edit.add_mep_run(m, "IfcDuctSegment", [0, 0], [5, 0], "round", 0.3, st)
d2 = edit.add_mep_run(m, "IfcDuctSegment", [5, 0], [10, 0], "round", 0.3, st)
d3 = edit.add_mep_run(m, "IfcDuctSegment", [10, 0], [15, 0], "round", 0.3, st)
edit.add_mep_run(m, "IfcDuctSegment", [0, 20], [5, 20], "round", 0.3, st)   # isolated (never connected)
# wire the chain d1—d2—d3
edit.connect_mep(m, d1, d2)
edit.connect_mep(m, d2, d3)

g = mep_graph.graph(m)
assert g["element_count"] >= 4, g
assert g["connected_runs"] == 1, g                      # d1—d2—d3 is one run; the 4th is isolated
assert g["isolated_elements"] >= 1, g                   # the unconnected segment
run = g["runs"][0]
assert run["element_count"] == 3, run                   # d1, d2, d3
assert run["endpoints"] == 2 and run["branch_points"] == 0, run   # a straight run: 2 ends, no branch
assert run["longest_path_length"] == 3, run             # the whole chain is the index run
# the longest path runs end-to-end (d1 ... d3), all IfcDuctSegment
path_guids = [n["guid"] for n in run["longest_path"]]
assert set(path_guids) == {d1, d2, d3}, path_guids
assert path_guids[0] in (d1, d3) and path_guids[-1] in (d1, d3), path_guids   # endpoints at the ends

# --- route -----------------------------------------------------------------------------------------
os.environ["DATABASE_URL"] = "sqlite:///./test_mep_graph.db"
os.environ["STORAGE_DIR"] = "./test_storage_mepgraph"
os.environ.pop("AEC_RBAC", None)
if os.path.exists("./test_mep_graph.db"):
    os.remove("./test_mep_graph.db")
m.write(TMP)
from fastapi.testclient import TestClient  # noqa: E402

from aec_api.db import SessionLocal  # noqa: E402
from aec_api.main import app  # noqa: E402
from aec_api.models import Project  # noqa: E402

with TestClient(app) as c:
    pid = c.post("/projects", json={"name": "MEP"}).json()["id"]
    assert c.get(f"/projects/{pid}/mep/graph").status_code == 409   # no source IFC
    with SessionLocal() as db:
        db.get(Project, pid).source_ifc = TMP
        db.commit()
    r = c.get(f"/projects/{pid}/mep/graph")
    assert r.status_code == 200, r.status_code
    j = r.json()
    assert j["connected_runs"] == 1 and j["runs"][0]["element_count"] == 3, j

if os.path.exists(TMP):
    os.remove(TMP)

print("MEP-GRAPH OK - three duct segments wired d1-d2-d3 (+ one isolated) form ONE connected run of 3 "
      "elements with 2 endpoints, 0 branch points, and a longest linear path spanning the whole chain "
      "(the index-run backbone); the isolated segment is counted as the wiring gap; the /mep/graph route "
      "409s without a model and returns the run graph otherwise.")

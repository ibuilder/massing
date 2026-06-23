"""Computational graph (M4) — zero-touch nodes + the executor wiring a real design chain.
Run: PYTHONPATH=src ./.venv/Scripts/python.exe test_compute_graph.py"""
import os

os.environ["DATABASE_URL"] = "sqlite:///./test_cg.db"
os.environ["STORAGE_DIR"] = "./test_storage_cg"
os.environ.pop("AEC_RBAC", None)
for f in ("./test_cg.db",):
    if os.path.exists(f):
        os.remove(f)

from fastapi.testclient import TestClient  # noqa: E402
from aec_api import compute_graph as cg  # noqa: E402
from aec_api.main import app  # noqa: E402

# --- catalog: nodes expose inputs (with defaults) + outputs --------------------
cat = cg.node_catalog()["nodes"]
assert len(cat) >= 5, len(cat)
zm = next(n for n in cat if n["key"] == "zoning_massing")
assert any(i["name"] == "far" for i in zm["inputs"]) and "buildable_gfa_sf" in zm["outputs"], zm

# --- a real chain: zoning → (structure, takt, cost→yield) --------------------
graph = {
    "nodes": [
        {"id": "z", "type": "zoning_massing", "params": {"lot_width": 40, "lot_depth": 30, "far": 3.0}},
        {"id": "s", "type": "structure_advisor", "params": {"span_m": 8}},
        {"id": "t", "type": "takt_schedule", "params": {}},
        {"id": "c", "type": "cost_from_gfa", "params": {"hard_psf": 225, "land": 2_000_000}},
        {"id": "y", "type": "yield_on_cost", "params": {"rent_per_unit_month": 2800, "exit_cap": 0.05}},
    ],
    "edges": [
        {"from": "z", "from_port": "building_height_m", "to": "s", "to_port": "building_height_m"},
        {"from": "z", "from_port": "floors", "to": "s", "to_port": "floors"},
        {"from": "z", "from_port": "floors", "to": "t", "to_port": "floors"},
        {"from": "z", "from_port": "buildable_gfa_sf", "to": "c", "to_port": "buildable_gfa_sf"},
        {"from": "z", "from_port": "units", "to": "y", "to_port": "units"},
        {"from": "c", "from_port": "total_cost", "to": "y", "to_port": "total_cost"},
    ],
}
r = cg.run_graph(graph)
res = r["results"]
# zoning ran first (it's upstream of everything); yield ran last
assert r["order"].index("z") == 0 and r["order"].index("y") == len(r["order"]) - 1, r["order"]
# data flowed: cost used the wired GFA, yield used the wired cost + units
assert res["c"]["total_cost"] > 2_000_000, res["c"]            # land + hard + soft
assert res["y"]["yield_on_cost"] > 0 and res["y"]["noi"] > 0, res["y"]
assert res["s"]["system"] and res["s"]["column_mm"] > 0, res["s"]
assert res["t"]["duration_days"] > 0, res["t"]
# wiring changes results: a bigger lot → more GFA → higher cost
big = cg.run_graph({**graph, "nodes": [{**graph["nodes"][0], "params": {"lot_width": 60, "lot_depth": 40, "far": 3.0}}] + graph["nodes"][1:]})
assert big["results"]["c"]["total_cost"] > res["c"]["total_cost"], "more GFA should cost more"

# --- guards: unknown node + cycle --------------------------------------------
try:
    cg.run_graph({"nodes": [{"id": "x", "type": "nope"}], "edges": []}); assert False
except ValueError:
    pass
try:
    cg.run_graph({"nodes": [{"id": "a", "type": "cost_from_gfa"}, {"id": "b", "type": "cost_from_gfa"}],
                  "edges": [{"from": "a", "from_port": "total_cost", "to": "b", "to_port": "land"},
                            {"from": "b", "from_port": "total_cost", "to": "a", "to_port": "land"}]}); assert False
except ValueError:
    pass

# --- endpoints ----------------------------------------------------------------
with TestClient(app) as c:
    assert c.get("/compute/nodes").status_code == 200 and len(c.get("/compute/nodes").json()["nodes"]) >= 5
    rr = c.post("/compute/graph", json=graph)
    assert rr.status_code == 200 and rr.json()["results"]["y"]["yield_on_cost"] > 0, rr.text
    assert c.post("/compute/graph", json={"nodes": [{"id": "x", "type": "nope"}], "edges": []}).status_code == 422

print(f"COMPUTE-GRAPH OK - {len(cat)} zero-touch nodes; chain zoning->structure/takt/cost->yield ran "
      f"in order {r['order']}; YoC {res['y']['yield_on_cost']*100:.1f}%; cycle + unknown-node guarded")

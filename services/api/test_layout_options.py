"""MASSING-OPT — the layout/massing optioneer: sweep envelope levers over massing.compute_massing, score
each for developer yield, rank + Pareto-frontier. Covers the engine (feasible options, yield math, frontier
non-domination, objective switch) and the stateless POST /massing/optioneer route.
Run: PYTHONPATH="src;../data/src" ./.venv/Scripts/python.exe test_layout_options.py"""
import os

os.environ["DATABASE_URL"] = "sqlite:///./test_layout_options.db"
os.environ.pop("AEC_RBAC", None)

from aec_api import layout_options as lo  # noqa: E402

# a real residential envelope: 40×60 m lot, FAR 3, height-limited so floor-to-floor actually bites
BASE = {
    "use_type": "residential", "lot_width": 40.0, "lot_depth": 60.0, "far": 3.0, "coverage_max": 0.6,
    "front_setback": 6.0, "rear_setback": 6.0, "side_setback": 3.0, "height_limit": 40.0,
    "floor_to_floor": 3.5, "efficiency": 0.82, "avg_unit_m2": 75.0,
    "land_cost": 3_000_000.0, "hard_cost_psf": 225.0, "soft_cost_pct": 0.15, "contingency_pct": 0.05,
    "rent_per_unit_month": 3000.0, "opex_ratio": 0.35, "exit_cap": 0.05,
}

res = lo.optioneer(BASE)
assert res["scenarios"], res
assert res["best"] == res["scenarios"][0]["id"], res["best"]        # best == top-ranked
# ranking is by yield_on_cost descending (the default objective)
yocs = [s["proforma"]["yield_on_cost"] for s in res["scenarios"]]
assert yocs == sorted(yocs, reverse=True), yocs
# every scenario carries its lever values, a program, and a proforma; the swept levers are reported
s0 = res["scenarios"][0]
assert set(s0["levers"]) >= {"floor_to_floor", "efficiency", "coverage_max", "avg_unit_m2"}, s0["levers"]
assert s0["floors"] >= 1 and s0["gfa_sf"] > 0 and s0["proforma"]["total_cost"] > 0, s0
assert "floor_to_floor" in res["levers_swept"], res["levers_swept"]

# a tighter floor-to-floor fits more floors under the 40 m cap → more GFA than a taller one, all else equal
tight = lo.optioneer({**BASE, "floor_to_floor": 3.0}, levers={"floor_to_floor": [3.0]})
tall = lo.optioneer({**BASE, "floor_to_floor": 4.5}, levers={"floor_to_floor": [4.5]})
assert tight["scenarios"][0]["floors"] >= tall["scenarios"][0]["floors"], (
    tight["scenarios"][0]["floors"], tall["scenarios"][0]["floors"])

# the frontier is real non-domination: no frontier option is beaten on BOTH cost and profit
front = [s for s in res["scenarios"] if s["on_frontier"]]
assert front, "expected at least one frontier option"
for f in front:
    for o in res["scenarios"]:
        if o["id"] == f["id"]:
            continue
        beaten = (o["proforma"]["total_cost"] <= f["proforma"]["total_cost"]
                  and o["proforma"]["profit"] >= f["proforma"]["profit"]
                  and (o["proforma"]["total_cost"] < f["proforma"]["total_cost"]
                       or o["proforma"]["profit"] > f["proforma"]["profit"]))
        assert not beaten, (f["id"], o["id"])

# objective switch changes the ranking key: by "units", the top option maximises unit count
by_units = lo.optioneer(BASE, objective="units")
assert by_units["scenarios"][0]["units"] == max(s["units"] for s in by_units["scenarios"]), by_units["best"]

# yield math sanity: NOI = units·rent·12·(1−opex); value = NOI/cap; yoc = NOI/total_cost
pf = s0["proforma"]
if s0["units"]:
    egi = s0["units"] * 3000.0 * 12
    noi = egi * (1 - 0.35)
    assert abs(pf["noi"] - round(noi)) <= 1, (pf["noi"], noi)
    assert abs(pf["yield_on_cost"] - round(noi / pf["total_cost"], 4)) <= 0.001, pf

# --- phase 2: emit ONE option as the executable authoring chain, and actually EXECUTE it -----------
import math  # noqa: E402
import tempfile  # noqa: E402
from pathlib import Path  # noqa: E402

rec = lo.emit_recipes(s0, BASE)
assert rec["option"] == s0["id"] and rec["floors"] == s0["floors"], rec
assert rec["bootstrap"]["storeys"] == s0["floors"], rec["bootstrap"]
assert rec["bootstrap"]["storey_height"] == round(s0["levers"]["floor_to_floor"], 2), rec["bootstrap"]
# per storey: 1 slab + 4 perimeter walls (+4 core walls when a core box fits)
per = 5 + (4 if rec["core_side_m"] else 0)
assert rec["step_count"] == len(rec["steps"]) == s0["floors"] * per, (rec["step_count"], per)
# the plate side derives from the option's own program (side² · floors ≈ gfa)
assert abs(rec["plate_side_m"] ** 2 * rec["floors"] - s0["gfa_m2"]) / s0["gfa_m2"] < 0.02, rec
# determinism: the same option emits the same chain
assert lo.emit_recipes(s0, BASE) == rec

# EXECUTE the chain: bootstrap the blank model, run every step through the real edit recipes
from aec_data import edit, massing  # noqa: E402
from aec_data.ifc_loader import open_model  # noqa: E402

_ifc = Path(tempfile.gettempdir()) / "massing_opt_p2.ifc"
b = rec["bootstrap"]
massing.generate_blank_ifc(str(_ifc), name=b["name"], storeys=b["storeys"],
                           storey_height=b["storey_height"], ground_size=b["ground_size"])
m = open_model(str(_ifc))
for st in rec["steps"]:
    edit.RECIPES[st["recipe"]](m, st["params"])
walls, slabs = m.by_type("IfcWall"), m.by_type("IfcSlab")
want_walls = rec["floors"] * (4 + (4 if rec["core_side_m"] else 0))
assert len(walls) == want_walls, (len(walls), want_walls)
assert len(slabs) == rec["floors"] + 1, (len(slabs), rec["floors"])   # +1 ground-reference slab
# the top slab actually sits at (floors-1)·f2f — the chain respects the level datum
storeys = sorted(m.by_type("IfcBuildingStorey"), key=lambda s: float(s.Elevation or 0))
assert math.isclose(float(storeys[-1].Elevation), (rec["floors"] - 1) * b["storey_height"],
                    rel_tol=1e-6), storeys[-1].Elevation

# --- route: stateless POST /massing/optioneer ------------------------------------------------------
from fastapi.testclient import TestClient  # noqa: E402

from aec_api.main import app  # noqa: E402

with TestClient(app) as c:
    r = c.post("/massing/optioneer", json={"envelope": BASE, "objective": "profit", "limit": 10})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["objective"] == "profit" and len(body["scenarios"]) <= 10, body
    profits = [s["proforma"]["profit"] for s in body["scenarios"]]
    assert profits == sorted(profits, reverse=True), profits
    # an infeasible envelope (no area) → 422
    bad = c.post("/massing/optioneer", json={"envelope": {"use_type": "residential"}})
    assert bad.status_code == 422, bad.text

    # phase-2 route: default = the best option; explicit id honored; unknown id 404
    r2 = c.post("/massing/optioneer/recipes", json={"envelope": BASE})
    assert r2.status_code == 200, r2.text
    assert r2.json()["option"] == res["best"] and r2.json()["steps"], r2.json()["option"]
    pick = res["scenarios"][1]["id"]
    r3 = c.post("/massing/optioneer/recipes", json={"envelope": BASE, "option": pick})
    assert r3.status_code == 200 and r3.json()["option"] == pick, r3.text
    assert c.post("/massing/optioneer/recipes",
                  json={"envelope": BASE, "option": "opt-9999"}).status_code == 404

print("MASSING-OPT OK - the layout optioneer sweeps the massing levers (floor-to-floor, core efficiency, "
      "coverage strategy, unit size) over the zoning envelope through compute_massing, scores each option "
      "with a transparent yield-on-cost proforma (NOI/total_cost), and returns them ranked by the chosen "
      "objective (yield_on_cost | profit | units | net_sellable) plus a real Pareto cost-vs-profit frontier "
      "(verified: no frontier option is beaten on both cost and profit; a tighter floor-to-floor fits more "
      "floors under the height cap); the stateless POST /massing/optioneer route ranks by objective and "
      "422s an infeasible envelope. Phase 2: emit_recipes turns a ranked option into the blank-model "
      "bootstrap + a deterministic GUID-stable slab/perimeter/core recipe chain that was EXECUTED on a "
      "real blank IFC (wall/slab counts + the level datum verified); /massing/optioneer/recipes serves "
      "the best or a chosen option and 404s an unknown id.")

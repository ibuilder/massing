"""Embodied-carbon estimator — EPD factors x quantities with unit conversion + rollups.
Run: PYTHONPATH=src ./.venv/Scripts/python.exe test_carbon.py"""
import os

os.environ["DATABASE_URL"] = "sqlite:///./test_carbon.db"
os.environ["STORAGE_DIR"] = "./test_storage_carbon"
os.environ.pop("AEC_RBAC", None)
for _f in ("./test_carbon.db",):
    if os.path.exists(_f):
        os.remove(_f)

from fastapi.testclient import TestClient  # noqa: E402

from aec_api import carbon  # noqa: E402
from aec_api.main import app  # noqa: E402

# --- engine ---
# 100 m3 concrete @ 300 = 30,000 kg
r = carbon.compute_item("Cast-in-place concrete", 100, "m3")
assert r["kgco2e"] == 30000.0 and r["matched"] == "concrete", r
# 10 CY concrete -> 10*0.764555*300 = 2293.7 kg (unit conversion CY->m3)
r2 = carbon.compute_item("concrete footing", 10, "CY")
assert abs(r2["kgco2e"] - 2293.7) < 0.5, r2
# steel by tons -> kg conversion: 5 tons * 907.185 * 1.55
r3 = carbon.compute_item("structural steel", 5, "tons")
assert abs(r3["kgco2e"] - 5 * 907.185 * 1.55) < 1, r3
# unmatched material -> no factor, no guess
assert carbon.compute_item("unobtainium widget", 5, "ea")["kgco2e"] is None
# wrong unit family for the factor (concrete is volume) -> flagged, not computed
assert carbon.compute_item("concrete", 100, "kg")["kgco2e"] is None

agg = carbon.compute([
    {"description": "concrete slab", "quantity": 100, "unit": "m3", "cost_code": "03-3000"},
    {"description": "rebar", "quantity": 5000, "unit": "kg", "cost_code": "03-2000"},
    {"description": "mystery", "quantity": 1, "unit": "ea"},
])
assert agg["unmatched"] == 1, agg
assert agg["by_material"]["concrete"] == 30000.0, agg["by_material"]
assert agg["by_cost_code"]["03-3000"] == 30000.0, agg["by_cost_code"]
assert agg["total_kgco2e"] == 30000.0 + 5000 * 1.99, agg
assert agg["total_tco2e"] == round(agg["total_kgco2e"] / 1000, 2)

# --- CARBON-UNCONVERTED: the two refusals are different facts, and one of them hides an emitter ---
#
# `compute_item` has two ways to decline a line, and THIS FILE already asserts both, one level down
# (lines ~29-30): "no EPD factor matched" for an unrecognised material, and "unit not convertible"
# for a recognised one whose takeoff unit is in the wrong family. The AGGREGATE fixture above
# contains only the first -- `{"description": "mystery", "quantity": 1, "unit": "ea"}` -- so
# `agg["unmatched"] == 1` was asserted over a population holding one of the two cases, and the
# summary collapsing them was invisible. *The per-item refusal was tested and the aggregate's
# treatment of it was not, which is the third time that exact shape has hidden a defect this week.*
#
# The unit case is the dangerous one: the material IS recognised and IS an emitter, and it leaves
# `total_kgco2e`, `by_material` and `by_cost_code` with no trace but a tally.
_real = carbon.compute([
    {"description": "concrete, 4000 psi", "quantity": 2_400_000, "unit": "kg", "cost_code": "03-3000"},
    {"description": "structural steel", "quantity": 180_000, "unit": "kg", "cost_code": "05-1200"},
    {"description": "glazing", "quantity": 12_000, "unit": "sf", "cost_code": "08-4400"},
])
# The counts are DERIVED from the per-line notes rather than written out, so the split cannot drift
# from the refusals `compute_item` actually returned.
_no_factor = [ln for ln in _real["lines"] if ln["kgco2e"] is None and not ln.get("matched")]
_unconv = [ln for ln in _real["lines"] if ln["kgco2e"] is None and ln.get("matched")]
assert _real["no_factor"] == len(_no_factor) == 0, (_real["no_factor"], _no_factor)
assert _real["unit_mismatch"] == len(_unconv) == 1, (_real["unit_mismatch"], _unconv)
assert _real["unmatched"] == _real["no_factor"] + _real["unit_mismatch"], _real
assert _real["assessed"] == _real["line_count"] - _real["unmatched"] == 2, _real

# THE DEFECT: concrete is recognised, is the biggest emitter on this job, and is absent from the
# rollup. It is now NAMED rather than left as a count.
assert "concrete" not in _real["by_material"], _real["by_material"]
assert _real["unconverted_materials"] == {"concrete": 2_400_000.0}, _real["unconverted_materials"]
assert "concrete" in _real["coverage_note"], _real["coverage_note"]
assert "EXCLUDED" in _real["coverage_note"], _real["coverage_note"]
# ...and the engine still refuses to invent a density, which is the right refusal.
assert _real["lines"][0]["kgco2e"] is None and "not convertible" in _real["lines"][0]["note"], _real["lines"][0]
assert _real["total_tco2e"] == 329.17, _real["total_tco2e"]

# The two refusals told apart in one call, one of each.
_both = carbon.compute([{"description": "concrete", "quantity": 100, "unit": "kg"},
                        {"description": "unobtainium", "quantity": 5, "unit": "ea"}])
assert (_both["no_factor"], _both["unit_mismatch"], _both["unmatched"]) == (1, 1, 2), _both
assert _both["unconverted_materials"] == {"concrete": 100.0}, _both["unconverted_materials"]

# A recognised material with NO exclusions says so, rather than leaving the reader to infer it from
# the absence of a warning.
_clean = carbon.compute([{"description": "concrete slab", "quantity": 100, "unit": "m3"}])
assert _clean["unconverted_materials"] == {} and _clean["unit_mismatch"] == 0, _clean
assert "Every recognised material was counted" in _clean["coverage_note"], _clean["coverage_note"]
assert "EXCLUDED" not in _clean["coverage_note"], _clean["coverage_note"]

# `unmatched` is PRESERVED as the sum, because it is declared and rendered on the analytics card:
# splitting a published figure out from under its readers would be a second defect, not a fix.
assert agg["unmatched"] == agg["no_factor"] + agg["unit_mismatch"] == 1, agg
assert agg["unconverted_materials"] == {}, agg["unconverted_materials"]

assert carbon.compute([])["coverage_note"] == "No material quantities to assess."


# --- endpoint from production_quantity records ---
with TestClient(app) as c:
    pid = c.post("/projects", json={"name": "P"}).json()["id"]
    c.post(f"/projects/{pid}/modules/production_quantity",
           json={"data": {"description": "Concrete slab on grade", "quantity": 200, "unit": "m3", "cost_code": "03-3000"}})
    j = c.get(f"/projects/{pid}/carbon").json()
    assert j["total_kgco2e"] == 60000.0 and j["by_material"]["concrete"] == 60000.0, j
    assert j["total_tco2e"] == 60.0, j

print("CARBON OK - EPD factors x quantities with CY/ton unit conversion; unmatched + wrong-unit-family "
      "flagged (no guessing); rollups by material + cost code; endpoint from production_quantity = 60 tCO2e")

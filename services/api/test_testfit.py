"""Test fitting (unit-mix layout + parking + scheme compare) and property/tax assumptions.
Run: PYTHONPATH=src ./.venv/Scripts/python.exe test_testfit.py"""
import os

os.environ["DATABASE_URL"] = "sqlite:///./test_testfit.db"
os.environ["STORAGE_DIR"] = "./test_storage_testfit"
os.environ.pop("AEC_RBAC", None)
for f in ("./test_testfit.db",):
    if os.path.exists(f):
        os.remove(f)

from fastapi.testclient import TestClient  # noqa: E402
from aec_api import test_fit as tf, dev_property as dp  # noqa: E402
from aec_api.main import app  # noqa: E402

# --- unit-mix layout: double-loaded corridor, yield metrics ------------------
lay = tf.layout(40, 18, floors=5)
assert lay["units"], "should place units"
m = lay["metrics"]
assert m["units_per_floor"] > 0 and m["total_units"] == m["units_per_floor"] * 5
assert 0 < m["efficiency"] < 1, m["efficiency"]                # NSF < GSF (corridor + walls)
assert m["total_nsf"] < m["total_gsf"], m
# units sit on both sides of the corridor
assert any(u["cy"] > 0 for u in lay["units"]) and any(u["cy"] < 0 for u in lay["units"]), "double-loaded"
assert sum(m["mix"].values()) == m["total_units"], m["mix"]

# --- parking: stalls to ratio --------------------------------------------------
pk = tf.parking(100, ratio=1.25, kind="structured")
assert pk["stalls"] == 125 and pk["area_sf"] > 0 and pk["cost"] > 0, pk

# --- compare: ranked schemes ---------------------------------------------------
cmp = tf.compare(40, 18, 5, [
    {"name": "A", "unit_types": [{"name": "Studio", "target_sf": 480, "mix_pct": 1.0}], "parking_ratio": 1.0},
    {"name": "B", "unit_types": [{"name": "2BR", "target_sf": 1100, "mix_pct": 1.0}], "parking_ratio": 1.5},
])
assert len(cmp["schemes"]) == 2 and cmp["best"] in ("A", "B")
# all-studio packs more units than all-2BR on the same plate
a = next(s for s in cmp["schemes"] if s["name"] == "A")
b = next(s for s in cmp["schemes"] if s["name"] == "B")
assert a["total_units"] > b["total_units"], (a["total_units"], b["total_units"])
assert cmp["best"] == "A", cmp["best"]

# --- generative optimize: sweep + rank by yield-on-cost ----------------------
opt = tf.optimize(40, 18, 6, targets={"min_units": 1}, econ={"rent_psf_yr": 34, "hard_psf": 220})
assert opt["considered"] == 15, opt["considered"]            # 5 presets × 3 parking ratios
assert opt["feasible"] >= 1 and opt["best"], opt
assert opt["best"]["yield_on_cost"] == max(c["yield_on_cost"] for c in opt["ranked"]), "best ranks top"
# targets filter: an impossible yield floor yields nothing feasible
none_feasible = tf.optimize(40, 18, 6, targets={"min_yoc": 9.99})
assert none_feasible["feasible"] == 0 and none_feasible["best"] is None, none_feasible
# objective switch: rank by units
by_units = tf.optimize(40, 18, 6, targets={"objective": "total_units"})
assert by_units["best"]["total_units"] == max(c["total_units"] for c in by_units["ranked"]), by_units

# --- property & tax summary ----------------------------------------------------
ps = dp.summarize({"purchase_price": 15_744_700, "building_sf": 249_749, "land_sf": 598_668,
                   "taxes": {"school": 955_533, "county": 239_731, "town": 228_906, "fire": 79_055}})
assert ps["total_taxes"] == 955_533 + 239_731 + 228_906 + 79_055, ps["total_taxes"]
assert ps["price_per_building_sf"] > 0 and ps["deltas"]["opex_annual_add"] == ps["total_taxes"]

# --- endpoints -----------------------------------------------------------------
with TestClient(app) as c:
    pid = c.post("/projects", json={"name": "Fit"}).json()["id"]
    r = c.post("/test-fit/compare", json={"plate_w": 40, "plate_d": 18, "floors": 5, "schemes": []})
    assert r.status_code == 200 and len(r.json()["schemes"]) == 3, r.text   # default schemes
    o = c.post("/test-fit/optimize", json={"plate_w": 40, "plate_d": 18, "floors": 6, "targets": {"min_units": 1}})
    assert o.status_code == 200 and o.json()["best"] and o.json()["considered"] == 15, o.text
    pr = c.put(f"/projects/{pid}/property", json={"purchase_price": 15_744_700, "building_sf": 249_749,
                                                  "taxes": {"school": 955_533}})
    assert pr.status_code == 200 and pr.json()["summary"]["total_taxes"] == 955_533, pr.text
    assert c.get(f"/projects/{pid}/property").json()["summary"]["purchase_price"] == 15_744_700

print(f"TESTFIT OK - corridor layout {m['units_per_floor']} units/floor @ {m['efficiency']*100:.0f}% eff; "
      f"parking {pk['stalls']} stalls; compare ranks studio>2BR ({a['total_units']}>{b['total_units']}); "
      f"optimize swept {opt['considered']} schemes -> best YoC {opt['best']['yield_on_cost']*100:.1f}%; "
      f"property taxes ${ps['total_taxes']:,} -> opex; endpoints ok")

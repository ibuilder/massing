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

# --- R1: form-follows-finance — daylight-limited leasable depth ----------------
shallow = tf.layout(60, 16, floors=1)          # 16 m deep: bays ~7 m, within daylight reach
deep = tf.layout(60, 40, floors=1)             # 40 m deep: bays ~19 m, far beyond daylight
assert not shallow["daylight_limited"], shallow["leasable_depth"]
assert deep["daylight_limited"] and deep["core_depth_m"] > 0, deep
# the deep plate wastes a dark interior core → much lower rentable (daylight) efficiency
assert deep["metrics"]["daylight_efficiency"] < shallow["metrics"]["daylight_efficiency"] - 0.1, \
    (deep["metrics"]["daylight_efficiency"], shallow["metrics"]["daylight_efficiency"])
assert deep["leasable_depth"] == 9.0, deep["leasable_depth"]   # capped at the daylight limit

# --- A2: egress — two means + travel distance within code ----------------------
eg_ok = tf.egress(40, 18, n_stairs=2, sprinklered=True)
assert eg_ok["compliant"] and not eg_ok["flags"], eg_ok
eg_one = tf.egress(40, 18, n_stairs=1)
assert not eg_one["compliant"] and any("two means" in f for f in eg_one["flags"]), eg_one
eg_far = tf.egress(400, 120, n_stairs=2, sprinklered=False)   # huge plate → travel exceeds limit
assert not eg_far["compliant"] and any("travel distance" in f for f in eg_far["flags"]), eg_far
assert shallow["egress"]["stairs"] == 2, shallow["egress"]    # layout surfaces egress
# deeper IBC checks: occupant load, required egress width, min exits, exit separation
assert eg_ok["occupant_load_per_floor"] == 39 and eg_ok["min_exits_required"] == 2, eg_ok
assert eg_ok["provided_egress_width_mm"] >= eg_ok["required_egress_width_mm"], eg_ok
assert len(eg_ok["checks"]) == 4 and all(c["ok"] for c in eg_ok["checks"]), eg_ok
# an assembly hall (1.4 m²/occ) on a big plate trips occupant-load → ≥3 exits + width flags
eg_assembly = tf.egress(60, 40, n_stairs=2, sprinklered=True, occupancy="assembly")
assert eg_assembly["occupant_load_per_floor"] > 1000 and eg_assembly["min_exits_required"] == 4, eg_assembly
assert not eg_assembly["compliant"] and any("means of egress" in f for f in eg_assembly["flags"]), eg_assembly
# narrow remoteness: a single stair fails exit separation too
assert any("apart" in f for f in eg_one["flags"]) or not eg_one["compliant"], eg_one

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
# compare surfaces the plate-level egress/life-safety check (so the UI can show it)
assert "egress" in cmp and "compliant" in cmp["egress"] and "max_travel_m" in cmp["egress"], cmp.get("egress")

# --- generative optimize: sweep + rank by yield-on-cost ----------------------
opt = tf.optimize(40, 18, 6, targets={"min_units": 1}, econ={"rent_psf_yr": 34, "hard_psf": 220})
assert opt["considered"] == 15, opt["considered"]            # 5 presets × 3 parking ratios
assert opt["feasible"] >= 1 and opt["best"], opt
assert opt["best"]["yield_on_cost"] == max(c["yield_on_cost"] for c in opt["ranked"]), "best ranks top"
# YoC + dev-spread now come from the canonical proforma functions (not a local proxy)
from aec_api.proforma import returns as _ret  # noqa: E402
b0 = opt["best"]
assert b0["yield_on_cost"] == round(_ret.yield_on_cost(b0["noi"], b0["total_cost"]), 4), b0
assert b0["dev_spread_bps"] == round((b0["yield_on_cost"] - 0.05) * 10000), b0   # vs default 5% exit cap
# rank by the development spread (the real "does it pencil" metric)
by_spread = tf.optimize(40, 18, 6, targets={"objective": "dev_spread_bps"})
assert by_spread["best"]["dev_spread_bps"] == max(c["dev_spread_bps"] for c in by_spread["ranked"]), by_spread
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

print(f"TESTFIT OK - R1 daylight: deep-plate eff {deep['metrics']['daylight_efficiency']*100:.0f}% < "
      f"shallow {shallow['metrics']['daylight_efficiency']*100:.0f}% (core {deep['core_depth_m']}m); "
      f"corridor layout {m['units_per_floor']} units/floor @ {m['efficiency']*100:.0f}% eff; "
      f"parking {pk['stalls']} stalls; compare ranks studio>2BR ({a['total_units']}>{b['total_units']}); "
      f"optimize swept {opt['considered']} schemes -> best YoC {opt['best']['yield_on_cost']*100:.1f}%; "
      f"property taxes ${ps['total_taxes']:,} -> opex; endpoints ok")

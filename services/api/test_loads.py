"""Preliminary gravity load takedown + ASCE 7 combinations (Wave 8 ④).
Run: PYTHONPATH=src ./.venv/Scripts/python.exe test_loads.py"""
import os

os.environ["DATABASE_URL"] = "sqlite:///./test_loads.db"
os.environ["STORAGE_DIR"] = "./test_storage_loads"
os.environ.pop("AEC_RBAC", None)
for _f in ("./test_loads.db",):
    if os.path.exists(_f):
        os.remove(_f)

import ifcopenshell                                  # noqa: E402
from fastapi.testclient import TestClient            # noqa: E402

from aec_api import loads                            # noqa: E402
from aec_api.main import app                         # noqa: E402

# --- ASCE 7 combinations: 1.2D+1.6L governs gravity -------------------------------------------------
c = loads.asce7_combos(100, 50)
assert c["governing_lrfd"]["kips"] == 200.0, c["governing_lrfd"]      # 1.2*100 + 1.6*50
assert c["governing_lrfd"]["combo"].startswith("1.2D+1.6L"), c["governing_lrfd"]
assert c["governing_asd"]["kips"] == 150.0, c["governing_asd"]        # D + L
# dead-only case: 1.4D governs when there's no live
assert loads.asce7_combos(100, 0)["governing_lrfd"]["kips"] == 140.0

# --- ASCE 7 §4.7 live-load reduction: L = Lo(0.25 + 15/sqrt(K_LL*A_T)) ------------------------------
r = loads.live_load_reduction(50, 1000)              # infl = 4*1000 = 4000 ft^2
assert abs(r - 24.36) < 0.15, r
assert loads.live_load_reduction(50, 50) == 50       # tiny area: below 400 ft^2 → no reduction

# --- takedown: 3 storeys x 10,000 sf, office, 10 columns, 8" slab + 20 psf SDL ----------------------
storeys = [{"name": "Roof", "area_sf": 10000, "roof": True},
           {"name": "L2", "area_sf": 10000, "occupancy": "office"},
           {"name": "L1", "area_sf": 10000, "occupancy": "office"}]
t = loads.takedown(storeys, sdl_psf=20, slab_thickness_in=8, column_count=10)
assert t["assumptions"]["slab_self_weight_psf"] == 100.0     # 8/12 * 150
assert t["assumptions"]["dead_psf"] == 120.0                 # slab 100 + SDL 20
assert t["column"]["service_dead_kip"] == 360.0, t["column"]  # 3 floors * 120 psf * 1000 sf tributary
assert 480 < t["column"]["factored_lrfd_kip"] < 545, t["column"]   # ~508.8 (1.2D+1.6L+0.5Lr)
assert t["column"]["factored_lrfd_kip"] > t["column"]["service_total_kip"]
assert t["footing"]["service_total_kip"] == t["column"]["service_total_kip"]
assert len(t["storeys"]) == 3 and t["storeys"][0]["occupancy"] == "roof"
assert "licensed professional engineer" in t["disclaimer"]

# --- HTTP: explicit storeys need no model; auto-build path works with floor_area_sf ----------------
with TestClient(app) as cc:
    pid = cc.post("/projects", json={"name": "Load Tower"}).json()["id"]
    r1 = cc.post(f"/projects/{pid}/loads/takedown", json={"storeys": storeys, "column_count": 10,
                                                          "sdl_psf": 20, "slab_thickness_in": 8})
    assert r1.status_code == 200 and r1.json()["column"]["service_dead_kip"] == 360.0, r1.text[:200]
    # auto-build 4 uniform office storeys, 8000 sf, 8 columns
    r2 = cc.post(f"/projects/{pid}/loads/takedown",
                 json={"floor_area_sf": 8000, "storey_count": 4, "occupancy": "office", "column_count": 8})
    assert r2.status_code == 200 and len(r2.json()["storeys"]) == 4, r2.text[:200]
    # no storeys and no area → 422
    assert cc.post(f"/projects/{pid}/loads/takedown", json={}).status_code == 422

# --- from_model reads storeys + column count off a real IFC ----------------------------------------
m = ifcopenshell.open(os.path.join(os.path.dirname(__file__), "..", "..", "samples", "maple_tower.ifc"))
dm = loads.from_model(m)
assert dm["storey_count"] >= 1 and dm["column_count"] > 0, dm

print("LOADS OK - ASCE 7 combinations (1.2D+1.6L governs gravity=200k; 1.4D=140k dead-only); "
      "§4.7 live-load reduction (50->24.36 psf at 4000 sf influence); tributary takedown accumulates "
      "3 floors x120psf x1000sf = 360k dead per column, factored ~509k > service; auto-build + explicit "
      "storey paths via HTTP; from_model reads storeys/columns off maple_tower. Preliminary, PE caveat shipped.")

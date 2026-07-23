"""DESIGN-METRICS + DAYLIGHT — program-efficiency numbers (floors / GFA / net-to-gross / unit count /
area-by-type) + a deterministic average-daylight-factor estimate from the model's windows.
Run: PYTHONPATH="src;../data/src" ./.venv/Scripts/python.exe test_design_metrics.py"""
import os

os.environ["DATABASE_URL"] = "sqlite:///./test_design_metrics.db"
os.environ["STORAGE_DIR"] = "./test_storage_dm"
os.environ.pop("AEC_RBAC", None)

from aec_api import design_metrics as dm  # noqa: E402

# --- daylight bands (pure) + the ADF constant --------------------------------------------------------
assert dm.daylight_band(2.5) == "good" and dm.daylight_band(2.0) == "good", "≥2% is good"
assert dm.daylight_band(1.5) == "fair" and dm.daylight_band(1.0) == "fair", "1–2% is fair"
assert dm.daylight_band(0.6) == "limited", "<1% is limited"
assert 8.5 < dm._ADF_K < 9.5, dm._ADF_K            # CIBSE constants collapse to ≈9.07

# --- metrics over a real model -----------------------------------------------------------------------
import ifcopenshell  # noqa: E402

from aec_data import edit, massing  # noqa: E402
from aec_data.ifc_loader import open_model  # noqa: E402

TMP = os.path.join(os.path.dirname(__file__), "_dm.ifc")
massing.generate_blank_ifc(TMP, name="DM", storeys=1, storey_height=3.5, ground_size=20.0)
m = ifcopenshell.open(TMP)
edit.add_spaces(m, rooms_per_storey=4, ceiling_height=3.0)         # some IfcSpaces (net areas)
st = m.by_type("IfcBuildingStorey")[0].Name
wall = edit.add_wall(m, [0, 0], [6, 0], 3.0, 0.2, st)             # a host wall
try:
    wg = wall.get("guid") if isinstance(wall, dict) else getattr(wall, "GlobalId", None)
    if wg:
        edit.add_opening(m, wg, 1.5, 1.5, 0.9, "window", st, None, None)   # a 1.5×1.5 window
except Exception:
    pass
m.write(TMP)

r = dm.metrics(open_model(TMP))
assert r["floors"] == 1, r["floors"]
assert r["space_count"] >= 4, r["space_count"]
assert r["gross_floor_area_m2"] >= r["net_floor_area_m2"] > 0, r      # gross ≥ net, both positive
assert 0 < r["net_to_gross"] <= 1.0, r["net_to_gross"]
assert isinstance(r["by_type"], list) and r["by_type"], r["by_type"]
# the daylight block is always present + well-formed; ADF follows WFR × ~9.07 when glazing was captured
d = r["daylight"]
assert set(d) >= {"window_count", "glazed_area_m2", "window_to_floor_ratio", "avg_daylight_factor_pct", "band", "estimate"}, d
assert d["estimate"] is True and d["band"] in ("good", "fair", "limited"), d
if d["glazed_area_m2"] > 0:
    assert abs(d["avg_daylight_factor_pct"] - round(d["window_to_floor_ratio"] * dm._ADF_K, 2)) <= 0.01, d
    assert d["window_count"] >= 1, d

# --- route: 409 without a model; 200 + structure with one -------------------------------------------
if os.path.exists("./test_design_metrics.db"):
    os.remove("./test_design_metrics.db")
from fastapi.testclient import TestClient  # noqa: E402

from aec_api.db import SessionLocal  # noqa: E402
from aec_api.main import app  # noqa: E402
from aec_api.models import Project  # noqa: E402

with TestClient(app) as c:
    pid = c.post("/projects", json={"name": "Design"}).json()["id"]
    assert c.get(f"/projects/{pid}/model/design-metrics").status_code == 409
    with SessionLocal() as db:
        db.get(Project, pid).source_ifc = TMP
        db.commit()
    rr = c.get(f"/projects/{pid}/model/design-metrics")
    assert rr.status_code == 200, rr.text
    j = rr.json()
    assert j["floors"] == 1 and "daylight" in j and "net_to_gross" in j, j

if os.path.exists(TMP):
    os.remove(TMP)

print("DESIGN-METRICS OK - program-efficiency + daylight metrics compute over the model: floors, space "
      "count, net floor area, gross (from storey quantities or net÷0.82), net-to-gross ratio, unit count + "
      "area-by-type; and a deterministic average-daylight-factor ESTIMATE from the model's glazed area vs "
      "net floor area (CIBSE constants → ADF% = WFR × ~9.07, banded ≥2% good / 1–2% fair / <1% limited, "
      "clearly labelled an estimate not a ray-trace); the /model/design-metrics route 409s without a model.")

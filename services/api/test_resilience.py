"""Climate & water resilience — flood Design Flood Elevation + flood-proof-MEP check, and the
Rational-Method stormwater sizing. Run: PYTHONPATH=src ./.venv/Scripts/python.exe test_resilience.py"""
import os

os.environ["DATABASE_URL"] = "sqlite:///./test_resilience.db"
os.environ["STORAGE_DIR"] = "./test_storage_resilience"
os.environ.pop("AEC_RBAC", None)
for _f in ("./test_resilience.db",):
    if os.path.exists(_f):
        os.remove(_f)

from fastapi.testclient import TestClient            # noqa: E402
from aec_api.main import app                         # noqa: E402


def _mk(c, pid, key, data):
    r = c.post(f"/projects/{pid}/modules/{key}", json={"data": data})
    assert r.status_code == 201, f"{key}: {r.text[:160]}"
    return r.json()


with TestClient(app) as c:
    pid = c.post("/projects", json={"name": "Riverside Tower"}).json()["id"]

    # --- W1: flood risk / Design Flood Elevation ---
    # Zone AE (in the SFHA), BFE 12 ft, FDC 2 (freeboard blank -> ASCE 24 default 1.0) => DFE = 13
    _mk(c, pid, "flood_risk", {"name": "Site flood assessment", "flood_zone": "AE - 1% (with BFE)",
        "bfe_ft": 12, "flood_design_class": "2 - standard occupancy", "ground_elevation_ft": 10})
    # a chiller installed below the DFE (at risk) and a rooftop unit above it (safe)
    _mk(c, pid, "asset_register", {"name": "Basement chiller", "elevation_ft": 11, "expected_life_years": 20, "replacement_cost": 200000})
    _mk(c, pid, "asset_register", {"name": "Rooftop AHU", "elevation_ft": 55, "expected_life_years": 20, "replacement_cost": 150000})

    f = c.get(f"/projects/{pid}/resilience/flood").json()
    assert f["design_flood_elevation_ft"] == 13.0, f["design_flood_elevation_ft"]
    assert f["in_special_flood_hazard_area"] is True, f
    assert f["assets_checked"] == 2 and f["at_risk_count"] == 1, (f["assets_checked"], f["at_risk_count"])
    assert f["assets_at_risk"][0]["below_dfe_by_ft"] == 2.0, f["assets_at_risk"]
    assert f["compliant"] is False, f["compliant"]

    # --- W2: stormwater Rational Method ---
    # Roof: 1 acre (43,560 sf), C default 0.90, i 4 in/hr, depth 2 in  -> Q = 0.9*4*1 = 3.6 cfs
    _mk(c, pid, "drainage_area", {"name": "Roof catchment", "surface_type": "Roof", "area_sf": 43560,
        "rainfall_intensity_in_hr": 4, "rainfall_depth_in": 2, "return_period_years": "10"})
    # Lawn: 1 acre, C 0.25 -> Q = 0.25*4*1 = 1.0 cfs
    _mk(c, pid, "drainage_area", {"name": "Lawn catchment", "surface_type": "Lawn / landscaped", "area_sf": 43560,
        "runoff_coefficient": 0.25, "rainfall_intensity_in_hr": 4, "rainfall_depth_in": 2, "return_period_years": "10"})

    s = c.get(f"/projects/{pid}/resilience/stormwater").json()
    assert s["count"] == 2, s["count"]
    assert abs(s["peak_runoff_cfs"] - 4.6) < 0.01, s["peak_runoff_cfs"]        # 3.6 + 1.0
    assert abs(s["total_area_acres"] - 2.0) < 0.01, s["total_area_acres"]
    assert abs(s["composite_runoff_coefficient"] - 0.575) < 0.02, s["composite_runoff_coefficient"]
    # detention ≈ (0.9 + 0.25) × (2in/12) × 43560 = 8,349 cf
    assert abs(s["detention_volume_cf"] - 8349) < 5, s["detention_volume_cf"]
    assert s["catchments"][0]["peak_cfs"] == 3.6, s["catchments"][0]           # roof is the largest

    # --- W3: weather-sequenced construction ---
    # two weather-sensitive activities, one insensitive
    _mk(c, pid, "schedule_activity", {"name": "Pour foundations", "trade": "Concrete",
        "weather_sensitivity": "Rain / wet", "start": "2026-01-05", "finish": "2026-01-20"})
    _mk(c, pid, "schedule_activity", {"name": "Erect steel", "trade": "Steel",
        "weather_sensitivity": "Wind", "start": "2026-02-01", "finish": "2026-02-15"})
    _mk(c, pid, "schedule_activity", {"name": "Interior paint", "trade": "Finishes",
        "weather_sensitivity": "None"})
    # a high-severity open site hazard + a closed one
    _mk(c, pid, "climate_site_risk", {"name": "Excavation flooding", "hazard_type": "Dewatering / high water table",
        "season": "Wet / monsoon", "severity": "High", "location": "North cellar"})
    _mk(c, pid, "climate_site_risk", {"name": "Slippery ramp", "hazard_type": "Slips & access",
        "season": "Wet / monsoon", "severity": "Low"})
    # two daily reports with weather impact (Full-Day 1.0 + Half-Day 0.5 = 1.5 delay days)
    _mk(c, pid, "daily_report", {"report_date": "2026-01-08", "weather": "Rain", "weather_impact": "Full-Day Lost"})
    _mk(c, pid, "daily_report", {"report_date": "2026-01-09", "weather": "Rain", "weather_impact": "Half-Day Lost"})
    _mk(c, pid, "daily_report", {"report_date": "2026-01-10", "weather": "Clear", "weather_impact": "None"})

    w = c.get(f"/projects/{pid}/resilience/weather").json()
    assert w["sensitive_count"] == 2, w["sensitive_count"]                      # "None" excluded
    assert w["open_risk_count"] == 2 and w["high_severity_open"] == 1, (w["open_risk_count"], w["high_severity_open"])
    assert abs(w["weather_delay_days"] - 1.5) < 0.01, w["weather_delay_days"]   # 1.0 + 0.5, "None" ignored

    # --- W4: physical climate-risk rollup (feeds ESG) ---
    cr = c.get(f"/projects/{pid}/resilience/climate-risk").json()
    # in SFHA (+2) + assets below DFE (+2) + high-severity open hazard (+2) => score 6 => "Severe"
    assert cr["score"] == 6 and cr["rating"] == "Severe", (cr["score"], cr["rating"])
    assert cr["in_special_flood_hazard_area"] is True and cr["assets_at_risk"] == 1, cr
    esg = c.get(f"/projects/{pid}/esg").json()
    assert esg["physical_risk"]["rating"] == "Severe", esg["physical_risk"]

print("RESILIENCE OK - flood DFE 13ft (BFE 12 + ASCE 24 freeboard 1) in the SFHA; basement chiller "
      "2ft below DFE flagged for flood-proofing; stormwater Q=C·i·A peak 4.6 cfs over 2 ac, composite "
      "C 0.575, detention 8,349 cf; 2 weather-sensitive activities, 1.5 weather-delay days, physical "
      "climate-risk 'Severe' (score 6) rolled into ESG")

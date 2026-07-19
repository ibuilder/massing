"""ENV-1 — pedestrian wind-comfort screen: Lawson grading of corner/downwash/channelling heuristics.
Run: PYTHONPATH=src ./.venv/Scripts/python.exe test_env_wind.py"""
import os

os.environ["DATABASE_URL"] = "sqlite:///./test_env_wind.db"
os.environ["STORAGE_DIR"] = "./test_storage_wind"
os.environ["AEC_TRUST_XUSER"] = "1"
os.environ.pop("AEC_RBAC", None)
for _f in ("./test_env_wind.db",):
    if os.path.exists(_f):
        os.remove(_f)

from aec_api import env_wind  # noqa: E402

# --- a low suburban building on a calm site: everything comfortable, no downwash zone --------------
low = env_wind.screen(height_m=9, width_m=20, depth_m=15, wind_ms=3.0)
assert low["worst"]["lawson"] in ("A", "B"), low["worst"]
assert low["acceptable_for_entrances"] is True, low
assert not any("downwash" in z["zone"] for z in low["zones"]), "no downwash below 25 m"
assert all(z["speed_ms"] < 6 for z in low["zones"]), low["zones"]

# --- a 120 m tower on a breezy site: corner + downwash zones degrade comfort -----------------------
tall = env_wind.screen(height_m=120, width_m=40, depth_m=30, wind_ms=6.0)
zones = {z["zone"]: z for z in tall["zones"]}
assert "corners" in zones and "base (downwash)" in zones, list(zones)
assert zones["corners"]["speed_ms"] > 6.0 < zones["base (downwash)"]["speed_ms"], zones
assert tall["worst"]["lawson"] in ("C", "D", "E", "S"), tall["worst"]
assert tall["acceptable_for_entrances"] is False, tall
assert any("podium" in m or "canopy" in m for m in tall["mitigations"]), tall["mitigations"]

# a podium ≥20% of the height intercepts the downwash (lower factor than without)
pod = env_wind.screen(height_m=120, width_m=40, depth_m=30, wind_ms=6.0, podium_height_m=30)
dw_no = zones["base (downwash)"]["factor"]
dw_pod = next(z for z in pod["zones"] if "downwash" in z["zone"])["factor"]
assert dw_pod < dw_no, (dw_pod, dw_no)

# --- channelling: a narrow gap between tall masses raises a passage zone ---------------------------
ch = env_wind.screen(height_m=60, width_m=30, depth_m=20, wind_ms=5.0, gap_m=10)
passage = next((z for z in ch["zones"] if "passage" in z["zone"]), None)
assert passage is not None and passage["factor"] > 1.15, ch["zones"]
wide = env_wind.screen(height_m=60, width_m=30, depth_m=20, wind_ms=5.0, gap_m=40)
assert not any("passage" in z["zone"] for z in wide["zones"]), "a wide gap doesn't channel"

# unsafe classification above the 15 m/s criterion
gale = env_wind.screen(height_m=200, width_m=50, depth_m=40, wind_ms=11.0)
assert gale["worst"]["lawson"] == "S", gale["worst"]
assert "disclaimer" in gale and "NOT CFD" in gale["disclaimer"]

# --- endpoint: explicit dims + model-derived dims ---------------------------------------------------
import sys  # noqa: E402
from pathlib import Path  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "data" / "src"))
from fastapi.testclient import TestClient  # noqa: E402

from aec_api.main import app  # noqa: E402

HDR = {"X-User": "designer"}
with TestClient(app) as c:
    pid = c.post("/projects", json={"name": "Wind"}, headers=HDR).json()["id"]
    r = c.post(f"/projects/{pid}/env/wind",
               json={"height_m": 120, "width_m": 40, "depth_m": 30, "wind_ms": 6.0}, headers=HDR)
    assert r.status_code == 200 and r.json()["worst"]["lawson"] in ("C", "D", "E", "S"), r.text[:200]
    # no dims + no model → a clear 409
    assert c.post(f"/projects/{pid}/env/wind", json={}, headers=HDR).status_code == 409

print("ENV-WIND OK - Lawson screen: low/calm building all-comfortable (no downwash zone); a 120 m "
      "tower on 6 m/s degrades corners + base and fails the entrance criterion with podium/canopy "
      "mitigations; a 30 m podium cuts the downwash factor; a 10 m gap between 60 m masses channels "
      "(a 40 m gap doesn't); >15 m/s grades unsafe; endpoint serves explicit dims and 409s without any.")

"""Land parcel screening — filter/rank by size/zoning/flood + max-buildable envelope; data connector off.
Run: PYTHONPATH=src ./.venv/Scripts/python.exe test_parcels.py"""
import os

os.environ["DATABASE_URL"] = "sqlite:///./test_parcels.db"
os.environ["STORAGE_DIR"] = "./test_storage_parcels"
os.environ.pop("AEC_RBAC", None)
os.environ.pop("PARCEL_PROVIDER", None)
for _f in ("./test_parcels.db",):
    if os.path.exists(_f):
        os.remove(_f)

from fastapi.testclient import TestClient           # noqa: E402
from aec_api import parcels, parcels_bridge           # noqa: E402
from aec_api.main import app                          # noqa: E402

# --- data connector off; never fabricates parcels ---
assert parcels_bridge.is_enabled() is False
try:
    parcels_bridge.fetch_parcels(); raise AssertionError("should refuse")
except RuntimeError as e:
    assert "not connected" in str(e), e

# --- screening ---
plist = [
    {"id": "A", "acres": 5, "zoning": "MU", "flood_zone": "X", "sewer": True, "price": 2_000_000, "far": 2.0},
    {"id": "B", "acres": 0.5, "zoning": "R1", "flood_zone": "X"},                       # too small
    {"id": "C", "acres": 10, "zoning": "MU", "flood_zone": "AE", "sewer": True},        # flood
    {"id": "D", "acres": 8, "zoning": "MU", "flood_zone": "X", "sewer": False},         # no sewer (required)
    {"id": "E", "area_sf": 261360, "zoning": "MU", "flood_zone": "X", "sewer": True, "far": 3.0},  # 6 ac, biggest buildable
]
crit = {"min_acres": 2, "zoning_in": ["MU"], "exclude_flood": True, "require_sewer": True,
        "building_type": "multifamily", "region": "us_average"}
r = parcels.screen(plist, crit)
ids = [m["id"] for m in r["matches"]]
assert set(ids) == {"A", "E"}, r                       # B small, C flood, D no sewer
# E (6 ac x FAR 3 = 783,360 GFA) ranks above A (5 ac x FAR 2 = 435,600) by buildable size
assert ids[0] == "E", ids
eE = next(m for m in r["matches"] if m["id"] == "E")
assert eE["buildable"]["max_gfa_sf"] == round(6 * 43560 * 3.0, 0), eE["buildable"]
assert eE["buildable"]["conceptual_cost"] > 0, eE["buildable"]
# A has a price -> land cost per buildable sf computed
eA = next(m for m in r["matches"] if m["id"] == "A")
assert eA["buildable"]["land_cost_per_buildable_sf"] == round(2_000_000 / (5*43560*2.0), 2), eA["buildable"]
assert len(r["rejected"]) == 3 and all(x["failed"] for x in r["rejected"]), r["rejected"]

# --- endpoints ---
with TestClient(app) as c:
    resp = c.post("/parcels/screen", json={"parcels": plist, "criteria": crit})
    assert resp.status_code == 200 and resp.json()["match_count"] == 2, resp.text[:160]
    assert c.get("/parcels/data-status").json()["enabled"] is False

print("PARCELS OK - screen filters by size/zoning/flood/sewer (A,E pass; B small, C flood, D no sewer); "
      "ranks by max-buildable GFA (E>A); envelope = area x FAR -> conceptual cost + land $/buildable-sf; "
      "data connector off + never fabricates parcels")

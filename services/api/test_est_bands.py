"""EST-BANDS — range estimate: three-point (low/likely/high) bands per priced line from design-stage
cost uncertainty by discipline, rolled to a correlated envelope + an independent P10/P50/P90 range.
Pure-engine math (precise) + the /estimate/bands route.
Run: PYTHONPATH="src;../data/src" ./.venv/Scripts/python.exe test_est_bands.py"""
import os

from aec_api import estimate as est  # noqa: E402

# two lines with known point amounts: a structural column (spread 15%) + a mechanical duct (spread 30%)
# IfcColumn: 2 m3 x $650 = $1300 ; IfcDuctSegment: 100 m x $150 = $15000
rows = [
    {"guid": "c1", "ifc_class": "IfcColumn", "volume": 2.0},
    {"guid": "d1", "ifc_class": "IfcDuctSegment", "length": 100.0},
]
b = est.bands(rows)
by_class = {ln["ifc_class"]: ln for ln in b["lines"]}
col, duct = by_class["IfcColumn"], by_class["IfcDuctSegment"]
assert col["likely"] == 1300.0 and col["spread_pct"] == 15.0, col        # Structural 15%
assert col["low"] == 1105.0 and col["high"] == 1495.0, col               # 1300 ± 15%
assert duct["likely"] == 15000.0 and duct["spread_pct"] == 30.0, duct    # Mechanical 30%
assert duct["low"] == 10500.0 and duct["high"] == 19500.0, duct          # 15000 ± 30%

# expected = sum of likely; correlated envelope = sum of lows / sum of highs
assert b["expected"] == 16300.0, b["expected"]
assert b["envelope"]["low"] == 11605.0 and b["envelope"]["high"] == 20995.0, b["envelope"]

# the independent probabilistic range sits INSIDE the correlated envelope (diversification tightens it)
rng = b["range"]
assert rng["p50"] == 16300.0, rng
assert b["envelope"]["low"] < rng["p10"] < rng["p50"] < rng["p90"] < b["envelope"]["high"], rng
assert rng["std"] > 0, rng

# empty takeoff → zeroed bands, no crash
z = est.bands([])
assert z["expected"] == 0.0 and z["range"]["p90"] == 0.0 and z["lines"] == [], z

# --- route -----------------------------------------------------------------------------------------
os.environ["DATABASE_URL"] = "sqlite:///./test_est_bands.db"
os.environ["STORAGE_DIR"] = "./test_storage_estbands"
os.environ.pop("AEC_RBAC", None)
if os.path.exists("./test_est_bands.db"):
    os.remove("./test_est_bands.db")

TMP = os.path.join(os.path.dirname(__file__), "_estbands.ifc")

from aec_data import edit, massing  # noqa: E402
from aec_data.ifc_loader import open_model  # noqa: E402

massing.generate_blank_ifc(TMP, name="Bands", storeys=1, storey_height=4.0, ground_size=20.0)
m = open_model(TMP)
st = m.by_type("IfcBuildingStorey")[0].Name
edit.add_column(m, [0, 0], 4.0, 0.4, 0.4, st)
edit.add_column(m, [6, 0], 4.0, 0.4, 0.4, st)
m.write(TMP)

from fastapi.testclient import TestClient  # noqa: E402

from aec_api.db import SessionLocal  # noqa: E402
from aec_api.main import app  # noqa: E402
from aec_api.models import Project  # noqa: E402

with TestClient(app) as c:
    pid = c.post("/projects", json={"name": "Bands"}).json()["id"]
    assert c.get(f"/projects/{pid}/estimate/bands").status_code == 409   # no source IFC
    with SessionLocal() as db:
        db.get(Project, pid).source_ifc = TMP
        db.commit()
    r = c.get(f"/projects/{pid}/estimate/bands")
    assert r.status_code == 200, r.status_code
    j = r.json()
    assert j["expected"] > 0 and j["range"]["p10"] <= j["range"]["p50"] <= j["range"]["p90"], j
    assert j["envelope"]["low"] <= j["range"]["p10"] and j["range"]["p90"] <= j["envelope"]["high"], j
    assert all("low" in ln and "high" in ln for ln in j["lines"]), j["lines"]

if os.path.exists(TMP):
    os.remove(TMP)

print("EST-BANDS OK - three-point bands per line from discipline uncertainty (structural column $1300 "
      "+-15% = $1105/$1495; mechanical duct $15000 +-30% = $10500/$19500); expected $16300; the correlated "
      "envelope ($11605-$20995) brackets the tighter independent P10/P50/P90 range; empty takeoff zeroes "
      "cleanly; the /estimate/bands route 409s without a model and prices the takeoff otherwise.")

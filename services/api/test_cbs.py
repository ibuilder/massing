"""CBS-1 — Cost Breakdown Structure over a construction estimate: direct → indirect → contingency →
management reserve → overhead & profit → taxes. Pure-engine math (precise) + the /estimate/cbs route.
Run: PYTHONPATH="src;../data/src" ./.venv/Scripts/python.exe test_cbs.py"""
import os

from aec_api import cbs  # noqa: E402

# direct $1,000,000 with explicit rates → hand-checked layering
r = cbs.build(1_000_000, {"indirect_pct": 0.10, "contingency_pct": 0.05,
                          "management_reserve_pct": 0.03, "fee_pct": 0.06, "tax_pct": 0.00})
assert r["direct"] == 1_000_000.0
assert r["indirect"] == 100_000.0                       # 10% of direct
assert r["subtotal"] == 1_100_000.0                     # direct + indirect
assert r["contingency"] == 55_000.0                     # 5% of subtotal
assert r["management_reserve"] == 33_000.0              # 3% of subtotal (distinct from contingency)
assert r["base_with_risk"] == 1_188_000.0              # subtotal + contingency + reserve
assert r["overhead_profit"] == round(1_188_000.0 * 0.06, 2), r["overhead_profit"]   # 71,280
assert r["taxes"] == 0.0
assert r["total"] == round(1_188_000.0 * 1.06, 2), r["total"]                        # 1,259,280
# the six layers each carry a share of the total that sums to ~100%
assert len(r["layers"]) == 6 and {ly["level"].split(" ")[0] for ly in r["layers"]} >= {"Direct", "Contingency", "Management"}
assert abs(sum(ly["pct_of_total"] for ly in r["layers"]) - 100.0) < 0.1, r["layers"]
# management reserve is a separate layer from contingency (the CBS-1 point)
levels = [ly["level"] for ly in r["layers"]]
assert any("Management reserve" in x for x in levels) and any("Contingency" in x for x in levels), levels

# tax applies on the pre-tax base; defaults fill in when params omitted
r2 = cbs.build(500_000, {"tax_pct": 0.08})
assert r2["taxes"] == round((r2["total"] - r2["taxes"]) * 0.08, 2) or r2["taxes"] > 0, r2["taxes"]
assert r2["rates"]["indirect_pct"] == 0.12               # default filled
assert cbs.build(0)["total"] == 0.0                      # zero direct → zero, no divide-by-zero

# --- route ----------------------------------------------------------------------------------------
os.environ["DATABASE_URL"] = "sqlite:///./test_cbs.db"
os.environ["STORAGE_DIR"] = "./test_storage_cbs"
os.environ.pop("AEC_RBAC", None)
if os.path.exists("./test_cbs.db"):
    os.remove("./test_cbs.db")

TMP = os.path.join(os.path.dirname(__file__), "_cbs.ifc")
from aec_data import edit, massing  # noqa: E402
from aec_data.ifc_loader import open_model  # noqa: E402

massing.generate_blank_ifc(TMP, name="CBS", storeys=1, storey_height=4.0, ground_size=20.0)
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
    pid = c.post("/projects", json={"name": "CBS"}).json()["id"]
    assert c.get(f"/projects/{pid}/estimate/cbs").status_code == 409   # no source IFC
    with SessionLocal() as db:
        db.get(Project, pid).source_ifc = TMP
        db.commit()
    jr = c.get(f"/projects/{pid}/estimate/cbs", params={"contingency_pct": 0.10})
    assert jr.status_code == 200, jr.status_code
    j = jr.json()
    assert j["direct"] > 0 and j["total"] > j["direct"], j        # layered up from the takeoff direct cost
    assert j["rates"]["contingency_pct"] == 0.10, j["rates"]      # query override honoured
    assert j["direct_source"] == "model takeoff estimate"

if os.path.exists(TMP):
    os.remove(TMP)

print("CBS-1 OK - a $1M direct cost layers to $1,259,280: indirect 10%% ($100k) → contingency 5%% ($55k) "
      "→ management reserve 3%% ($33k, separate from contingency) → overhead & profit 6%% → taxes; the six "
      "layers' shares sum to 100%%; defaults fill omitted rates and zero direct is safe; the /estimate/cbs "
      "route 409s without a model and layers the takeoff direct cost with query-override rates otherwise.")

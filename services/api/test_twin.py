"""Digital-twin readiness + Digital Product Passport (asset↔system + sensor + DPP).
Run: PYTHONPATH=src ./.venv/Scripts/python.exe test_twin.py"""
import os

os.environ["DATABASE_URL"] = "sqlite:///./test_twin.db"
os.environ["STORAGE_DIR"] = "./test_storage_twin"
os.environ.pop("AEC_RBAC", None)
for _f in ("./test_twin.db",):
    if os.path.exists(_f):
        os.remove(_f)

from fastapi.testclient import TestClient             # noqa: E402
from aec_api.main import app                          # noqa: E402


def _create(c, pid, key, data):
    r = c.post(f"/projects/{pid}/modules/{key}", json={"data": data})
    assert r.status_code == 201, f"{key}: {r.text[:160]}"
    return r.json()


with TestClient(app) as c:
    pid = c.post("/projects", json={"name": "P"}).json()["id"]

    hvac = _create(c, pid, "building_system", {"name": "HVAC-1", "system_type": "HVAC",
        "bms_integration": "BACnet"})
    _create(c, pid, "building_system", {"name": "FP-1", "system_type": "Fire Protection",
        "bms_integration": "None"})

    # asset 1: fully twin-ready + DPP-complete
    _create(c, pid, "asset_register", {"name": "AHU-1", "tag": "M-1", "manufacturer": "Trane",
        "model": "T1", "system": hvac["id"], "sensor_id": "BMS:AHU1:SAT", "sensor_type": "Temperature",
        "gs1_id": "https://id.gs1.org/01/09506000134352", "epd_reference": "EPD-1234",
        "manufacturer_url": "https://trane.com/ahu1"})
    # asset 2: system-linked but no sensor, no DPP
    _create(c, pid, "asset_register", {"name": "AHU-2", "tag": "M-2", "system": hvac["id"]})
    # asset 3: bare
    _create(c, pid, "asset_register", {"name": "Pump-1", "tag": "M-3"})

    tw = c.get(f"/projects/{pid}/twin/readiness").json()
    assert tw["assets"] == 3 and tw["systems"] == 2, tw
    assert tw["system_linked_pct"] == 66.7, tw["system_linked_pct"]   # 2 of 3 linked
    assert tw["sensor_mapped_pct"] == 33.3, tw["sensor_mapped_pct"]   # 1 of 3 sensored
    assert tw["bms_integrated_systems"] == 1, tw["bms_integrated_systems"]  # HVAC on BACnet
    assert tw["dpp"]["complete"] == 1 and tw["dpp"]["complete_pct"] == 33.3, tw["dpp"]
    assert tw["twin_readiness_pct"] == 50.0, tw["twin_readiness_pct"]  # mean(66.7, 33.3)

    # the KPI scorecard's digital-twin + construction-data categories now read these signals
    sc = c.get(f"/projects/{pid}/bim-kpi/scorecard").json()
    cats = {x["key"]: x for x in sc["categories"]}
    assert cats["digital_twin_readiness"]["metrics"]["twin_readiness_pct"] == 50.0, cats["digital_twin_readiness"]
    assert cats["construction_data_readiness"]["metrics"]["dpp_pct"] == 33.3, cats["construction_data_readiness"]

print("TWIN OK - 2 systems (1 BMS-integrated); assets 66.7% system-linked / 33.3% sensor-mapped -> "
      "50% twin-ready; DPP 33.3% complete; KPI scorecard reflects both signals")

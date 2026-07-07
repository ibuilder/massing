"""MEP engineering (C1): first-pass sizing calculators + equipment schedule / system rollup.
Run: PYTHONPATH=src ./.venv/Scripts/python.exe test_mep.py"""
import os

os.environ["DATABASE_URL"] = "sqlite:///./test_mep.db"
os.environ["STORAGE_DIR"] = "./test_storage_mep"
os.environ.pop("AEC_RBAC", None)
for _f in ("./test_mep.db",):
    if os.path.exists(_f):
        os.remove(_f)

from fastapi.testclient import TestClient  # noqa: E402

from aec_api import mep, reports  # noqa: E402
from aec_api.main import app  # noqa: E402

# --- unit: the sizing calculators -----------------------------------------------------------------
d = mep.size_duct(2000, 1000)
assert d["area_sf"] == 2.0 and d["round_diameter_in"] == 20, d      # 2000/1000=2 sf -> ~19.2 in -> 20
p = mep.size_pipe(100, 6)
assert p["nominal_pipe_size_in"] == 3.0, p                          # ~2.6 in -> nominal 3
assert mep.size_cooling(120000)["tons"] == 10.0, "120k BTU/h = 10 tons"
bl = mep.block_cooling_load(35000, 350)
assert bl["tons"] == 100.0 and bl["load_btuh"] == 1200000, bl
assert mep.hanger_spacing("pipe_steel", 4)["max_spacing_ft"] == 14, "4in steel -> 14 ft (MSS SP-58)"
assert mep.hanger_spacing("duct", 24)["max_spacing_ft"] == 8, "duct -> 8 ft (SMACNA)"

with TestClient(app) as c:
    pid = c.post("/projects", json={"name": "P"}).json()["id"]

    # --- register -> schedule + per-system rollup ------------------------------------------------
    for data in [
        {"tag": "CH-1", "equipment_type": "Chiller", "system": "Chilled Water",
         "capacity": 300, "capacity_unit": "tons", "flow": 720, "size": "8"},
        {"tag": "CH-2", "equipment_type": "Chiller", "system": "Chilled Water",
         "capacity": 300, "capacity_unit": "tons"},
        {"tag": "P-1", "equipment_type": "Pump", "system": "Chilled Water",
         "capacity": 40, "capacity_unit": "HP", "flow": 1440},
        {"tag": "AHU-1", "equipment_type": "Air Handling Unit", "system": "Supply Air",
         "capacity": 20000, "capacity_unit": "CFM", "flow": 20000},
    ]:
        r = c.post(f"/projects/{pid}/modules/mep_equipment", json={"data": data})
        assert r.status_code == 201, r.text[:160]

    sch = c.get(f"/projects/{pid}/mep/schedule").json()
    assert sch["count"] == 4, sch
    chw = next(b for b in sch["by_system"] if b["system"] == "Chilled Water")
    assert chw["count"] == 3 and chw["capacity_by_unit"]["tons"] == 600.0, chw   # 300 + 300

    # --- sizing endpoint -------------------------------------------------------------------------
    sz = c.get(f"/projects/{pid}/mep/size", params={"kind": "duct", "flow": 2000, "velocity": 1000}).json()
    assert sz["round_diameter_in"] == 20, sz
    szp = c.get(f"/projects/{pid}/mep/size", params={"kind": "pipe", "flow": 100}).json()
    assert szp["nominal_pipe_size_in"] == 3.0, szp
    szc = c.get(f"/projects/{pid}/mep/size", params={"kind": "cooling", "load": 120000}).json()
    assert szc["tons"] == 10.0, szc

    # --- report + PDF ----------------------------------------------------------------------------
    assert "mep" in {x["id"] for x in reports.catalog()}, "mep missing from catalog"
    rep = c.get(f"/projects/{pid}/reports/mep.pdf")
    assert rep.status_code == 200 and rep.content[:4] == b"%PDF", rep.status_code

print("MEP OK - sizing calcs (2000 cfm@1000fpm -> 20in round; 100 gpm@6fps -> 3in nominal; 120k BTU/h "
      "-> 10 tons; 35k sf@350 -> 100 tons; 4in steel pipe -> 14 ft hangers; duct -> 8 ft); equipment "
      "schedule rolls up 3 CHW items @ 600 tons; sizing endpoint; report PDF served")

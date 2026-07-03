"""Concept space programming — adjacency graph + program rollup that feeds massing.
Run: PYTHONPATH=src ./.venv/Scripts/python.exe test_program.py"""
import os

os.environ["DATABASE_URL"] = "sqlite:///./test_program.db"
os.environ["STORAGE_DIR"] = "./test_storage_program"
os.environ.pop("AEC_RBAC", None)
for _f in ("./test_program.db",):
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

    # 40 residential units @ 850 sf, a lobby wanting to be near retail (which doesn't exist -> unmet),
    # a core, and an amenity next to residential.
    _create(c, pid, "space_program", {"name": "Typical unit", "space_type": "Residential Unit",
        "target_area_sf": 850, "quantity": 40, "adjacent_to": ["Circulation / Core"]})
    _create(c, pid, "space_program", {"name": "Lobby", "space_type": "Lobby", "target_area_sf": 1200,
        "quantity": 1, "adjacent_to": ["Retail", "Circulation / Core"]})   # Retail is unmet
    _create(c, pid, "space_program", {"name": "Core", "space_type": "Circulation / Core",
        "target_area_sf": 400, "quantity": 5})
    _create(c, pid, "space_program", {"name": "Fitness", "space_type": "Amenity", "target_area_sf": 1500,
        "quantity": 1, "adjacent_to": ["Residential Unit"]})

    s = c.get(f"/projects/{pid}/program/summary").json()
    # total = 40*850 + 1200 + 5*400 + 1500 = 34000 + 1200 + 2000 + 1500 = 38700
    assert s["total_area_sf"] == 38700, s["total_area_sf"]
    # net (Residential + Amenity) = 34000 + 1500 = 35500
    assert s["net_area_sf"] == 35500, s["net_area_sf"]
    assert s["by_type"]["Residential Unit"]["count"] == 40, s["by_type"]["Residential Unit"]
    assert len(s["graph"]["nodes"]) == 4, s["graph"]["nodes"]
    # edges: unit->core, lobby->retail, lobby->core, amenity->residential = 4; retail unmet
    assert s["adjacency"]["total"] == 4, s["adjacency"]
    assert any(u["to_type"] == "Retail" for u in s["adjacency"]["unmet"]), s["adjacency"]["unmet"]
    assert s["adjacency"]["satisfiable"] == 3, s["adjacency"]
    # massing hints carry the gross area + net-use mix
    assert s["massing_hints"]["gross_area_sf"] == 38700, s["massing_hints"]
    assert "Residential Unit" in s["massing_hints"]["mix_pct"], s["massing_hints"]

print("PROGRAM OK - 4 program nodes, total 38,700 sf / net 35,500 sf; adjacency graph 4 edges, "
      "Retail preference unmet (3/4 satisfiable); massing hints carry gross area + use mix")

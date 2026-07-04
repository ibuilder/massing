"""Facility Condition Assessment (FCA) + FCI engine — index math, bands, reserve integration,
portfolio roll-up, and the report. Run: PYTHONPATH=src ./.venv/Scripts/python.exe test_fca.py"""
import os

os.environ["DATABASE_URL"] = "sqlite:///./test_fca.db"
os.environ["STORAGE_DIR"] = "./test_storage_fca"
os.environ.pop("AEC_RBAC", None)
for _f in ("./test_fca.db",):
    if os.path.exists(_f):
        os.remove(_f)

from datetime import date                            # noqa: E402

from fastapi.testclient import TestClient            # noqa: E402
from aec_api.main import app                         # noqa: E402


def _create(c, pid, key, data):
    r = c.post(f"/projects/{pid}/modules/{key}", json={"data": data})
    assert r.status_code == 201, f"{key}: {r.text[:160]}"
    return r.json()


def _act(c, pid, key, rid, action):
    r = c.post(f"/projects/{pid}/modules/{key}/{rid}/transition", json={"action": action})
    assert r.status_code == 200, f"{action}: {r.text[:160]}"


with TestClient(app) as c:
    this_year = date.today().year
    pid = c.post("/projects", json={"name": "Tower FCA"}).json()["id"]

    # A: open roof deficiency $40k on a $200k element (deferred maintenance)
    _create(c, pid, "fca_element", {"element": "Roof membrane", "uniformat": "B - Shell / Envelope",
        "condition_rating": "4 - Poor", "replacement_cost": 200000, "deficiency": "Blistering",
        "deficiency_cost": 40000, "recommended_year": this_year})
    # B: open MEP deficiency $20k on a $200k element, in service life (no renewal owed)
    _create(c, pid, "fca_element", {"element": "AHU-1", "uniformat": "D - Services (MEP)",
        "condition_rating": "3 - Fair", "install_date": f"{this_year - 5}-01-01", "expected_life_years": 25,
        "replacement_cost": 200000, "deficiency_cost": 20000, "recommended_year": this_year + 1})
    # C: a $100k element with a big deficiency but RESOLVED — must leave the backlog (CRV still counts)
    cres = _create(c, pid, "fca_element", {"element": "Lobby finishes", "uniformat": "C - Interiors",
        "condition_rating": "2 - Good", "replacement_cost": 100000, "deficiency_cost": 999999})
    for a in ("plan", "fund", "resolve"):
        _act(c, pid, "fca_element", cres["id"], a)

    idx = c.get(f"/projects/{pid}/fca/index").json()
    # CRV = 200k + 200k + 100k = 500k; deferred = 40k + 20k = 60k (C excluded); renewal = 0
    assert idx["crv"] == 500000, idx["crv"]
    assert idx["deferred_maintenance"] == 60000, idx["deferred_maintenance"]
    assert idx["capital_renewal"] == 0, idx["capital_renewal"]
    assert idx["fci_pct"] == 12.0, idx["fci_pct"]          # 60k / 500k
    assert idx["band"] == "Poor", idx["band"]              # 10-30%
    assert idx["open_deficiencies"] == 2, idx["open_deficiencies"]
    assert idx["elements"] == 3, idx["elements"]
    # UNIFORMAT breakdown present, worst element is the $40k roof
    assert idx["worst_elements"][0]["cost"] == 40000, idx["worst_elements"][0]
    groups = {u["group"] for u in idx["by_uniformat"]}
    assert "B - Shell / Envelope" in groups and "D - Services (MEP)" in groups, groups

    # renewal band: an element past its useful life adds its full replacement value as capital renewal
    _create(c, pid, "fca_element", {"element": "Elevator cab", "uniformat": "D - Services (MEP)",
        "condition_rating": "5 - Critical", "install_date": f"{this_year - 30}-01-01",
        "expected_life_years": 25, "replacement_cost": 150000})
    idx2 = c.get(f"/projects/{pid}/fca/index").json()
    assert idx2["capital_renewal"] == 150000, idx2["capital_renewal"]   # past life → full renewal owed

    # reserve study picks up the FCA deferred costs as source="fca"
    rs = c.get(f"/projects/{pid}/reserves/study").json()
    sources = {e["source"] for e in rs["events"]}
    assert "fca" in sources, sources
    assert any(e["source"] == "fca" and e["cost"] == 40000 for e in rs["events"]), "roof deficiency in reserve"

    # portfolio roll-up includes this project, worst-first
    pf = c.get("/fca/portfolio").json()
    assert pf["count"] >= 1 and pf["projects"][0]["project_id"] == pid, pf
    assert pf["projects"][0]["backlog"] == 210000, pf["projects"][0]   # 60k deferred + 150k renewal

    # report renders
    rep = c.get(f"/projects/{pid}/reports/fca.pdf")
    assert rep.status_code == 200 and rep.content[:4] == b"%PDF", (rep.status_code, rep.content[:8])

print("FCA OK - FCI 12% (Poor) from 60k deferred / 500k CRV; resolved element leaves the backlog; "
      "past-life element adds 150k capital renewal; reserve study ingests FCA costs (source=fca); "
      "portfolio backlog 210k worst-first; FCA report PDF served")

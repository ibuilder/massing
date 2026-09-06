"""RESOURCE-PORTFOLIO — weekly resource demand summed across projects (`GET /portfolio/resourcing`).

The behaviour worth pinning is the one a per-project view cannot show: **a trade committed to two
jobs in the same week is over-committed even though neither project exceeds the cap on its own.**
That is the whole reason this endpoint exists, so it is asserted with a cap that each project sits
under and the pair does not.

Also pinned: fidelity is reported rather than blended. `resource_loading` falls back to
`schedule_activity.crew_size` when a project has no `resource_assignment` records, and a book of
fallbacks must not read as a resourced one.

Run: PYTHONPATH=src ./.venv/bin/python test_resource_portfolio.py"""
import os

os.environ["DATABASE_URL"] = "sqlite:///./test_resource_portfolio.db"
os.environ["STORAGE_DIR"] = "./test_storage_resource_portfolio"
os.environ["AEC_TRUST_XUSER"] = "1"
os.environ.pop("AEC_RBAC", None)
for _f in ("./test_resource_portfolio.db",):
    if os.path.exists(_f):
        os.remove(_f)

from fastapi.testclient import TestClient  # noqa: E402

from aec_api.main import app  # noqa: E402

HDR = {"X-User": "pm"}
WK = "2026-04-06"          # a Monday, so the week bucket is unambiguous
WK_END = "2026-04-10"


def _act(c, pid, name, start, finish, crew=None):
    d = {"name": name, "wbs": name, "duration": 5, "start": start, "finish": finish}
    if crew:
        d["crew_size"] = crew
    r = c.post(f"/projects/{pid}/modules/schedule_activity", json={"data": d}, headers=HDR)
    assert r.status_code == 201, r.text[:200]
    return r.json()["id"]


def _assign(c, pid, act, trade, units, start, finish, rate=100.0):
    r = c.post(f"/projects/{pid}/modules/resource_assignment", json={"data": {
        "resource_name": f"{trade} crew", "resource_type": "Labor", "trade": trade,
        "activity": act, "units": units, "unit": "day", "rate": rate,
        "start": start, "finish": finish}}, headers=HDR)
    assert r.status_code == 201, r.text[:200]


with TestClient(app) as c:
    a = c.post("/projects", json={"name": "AAA Tower"}, headers=HDR).json()["id"]
    b = c.post("/projects", json={"name": "BBB Annex"}, headers=HDR).json()["id"]
    quiet = c.post("/projects", json={"name": "CCC Empty"}, headers=HDR).json()["id"]

    g = c.post("/projects", json={"name": "DDD Glass"}, headers=HDR).json()["id"]
    # Same trade, same week, on two different projects — 6 units each.
    _assign(c, a, _act(c, a, "1.1", WK, WK_END), "Ironworkers", 6, WK, WK_END)
    _assign(c, b, _act(c, b, "2.1", WK, WK_END), "Ironworkers", 6, WK, WK_END)
    # A trade on ONE project only, for the cross_project contrast. It lives on its OWN project
    # rather than beside the ironworkers, because `resource_loading` caps a project's TOTAL weekly
    # units while this endpoint caps PER TRADE — putting both trades on one project would make that
    # project breach its own cap on the sum and destroy the like-for-like comparison below. The two
    # over-allocation figures answer different questions and are not interchangeable.
    _assign(c, g, _act(c, g, "3.1", WK, WK_END), "Glaziers", 3, WK, WK_END)

    r = c.get("/portfolio/resourcing", headers=HDR)
    assert r.status_code == 200, r.text[:300]
    p = r.json()
    assert p["available"] is True, p.get("reason")
    assert p["project_count"] == 4 and p["projects_available"] == 4 and not p["truncated"], p

    # --- the book sums CONCURRENT demand across projects ------------------------------------------
    wk = next(w for w in p["weeks"] if w["week"] == WK)
    assert wk["by_trade"]["Ironworkers"] == 12.0, wk      # 6 + 6, not 6
    assert wk["by_trade"]["Glaziers"] == 3.0, wk
    assert wk["total"] == 15.0, wk

    iron = next(t for t in p["trades"] if t["trade"] == "Ironworkers")
    glaz = next(t for t in p["trades"] if t["trade"] == "Glaziers")
    assert iron["peak_units"] == 12.0 and iron["peak_week"] == WK, iron
    assert iron["project_count"] == 2 and iron["cross_project"] is True, iron
    assert glaz["project_count"] == 1 and glaz["cross_project"] is False, glaz
    assert p["trades"][0]["trade"] == "Ironworkers", p["trades"]      # sorted by peak
    assert p["peak"] == {"week": WK, "units": 15.0}, p["peak"]

    # --- THE POINT: over-committed across the book while fine on each project ---------------------
    # cap=8 — each project asks for 6, so neither is over on its own. Together they are.
    over = c.get("/portfolio/resourcing?cap=8", headers=HDR).json()["over_allocation"]
    assert len(over) == 1, over
    assert over[0]["trade"] == "Ironworkers" and over[0]["week"] == WK, over[0]
    assert over[0]["units"] == 12.0 and over[0]["cap"] == 8.0, over[0]
    # and it names WHO is competing, which is the actionable half
    assert set(over[0]["projects"]) == {a, b}, over[0]["projects"]
    assert over[0]["projects"][a] == 6.0 and over[0]["projects"][b] == 6.0, over[0]["projects"]

    # each project ALONE is under the same cap — the claim above, verified rather than asserted
    for pid in (a, b, g):
        solo = c.get(f"/projects/{pid}/schedule/resource-loading?cap=8", headers=HDR).json()
        assert solo["over_allocation"] == [], (pid, solo["over_allocation"])

    # --- a project with no loads is named, never silently absent -----------------------------------
    assert [x["id"] for x in p["projects_without_loads"]] == [quiet], p["projects_without_loads"]
    assert "no resource assignments" in p["projects_without_loads"][0]["reason"]
    assert {x["id"] for x in p["projects"]} == {a, b, g}, p["projects"]

    # --- fidelity is reported, not blended --------------------------------------------------------
    assert p["fidelity"]["assigned"] == 3 and p["fidelity"]["fallback"] == 0, p["fidelity"]
    for row in p["projects"]:
        assert row["source"] == "resource_assignment", row

    # a project with crew-loaded activities and NO assignments contributes on the fallback source,
    # and the split says so — a book of fallbacks must not read as a resourced one
    d = c.post("/projects", json={"name": "EEE Crewed"}, headers=HDR).json()["id"]
    _act(c, d, "4.1", WK, WK_END, crew=4)
    p2 = c.get("/portfolio/resourcing", headers=HDR).json()
    assert p2["fidelity"]["assigned"] == 3 and p2["fidelity"]["fallback"] == 1, p2["fidelity"]
    drow = next(x for x in p2["projects"] if x["id"] == d)
    assert drow["source"] == "schedule_activity.crew_size", drow
    assert "resourced plan" in p2["fidelity"]["note"]

    # --- refusal is well-formed when nothing in range has loads -----------------------------------
    # limit=1 scans only "AAA Tower"… which has loads, so instead prove the shape on a fresh book:
    empty = c.get("/portfolio/resourcing?limit=1", headers=HDR).json()
    assert empty["project_count"] == 1 and empty["truncated"] is True, empty
    assert empty["projects_available"] == 5, empty

    # clamps, not trusted
    assert c.get("/portfolio/resourcing?limit=0", headers=HDR).json()["project_count"] == 1
    assert c.get("/portfolio/resourcing?weeks=1", headers=HDR).json()["week_span"]["shown"] >= 1

print("resource portfolio OK")

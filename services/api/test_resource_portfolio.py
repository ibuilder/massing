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

    # --- "BY DEPARTMENT" — a grouping the caller declares, not a field we hold -------------------
    # The book: Ironworkers 6+6 across two projects, Glaziers 3, and (from above) a crewed fallback.
    # Group them the way a GC would and the group view must answer the question the trade view
    # cannot: is STRUCTURE over-committed across the book, not just each trade within it.
    g1 = c.get("/portfolio/resourcing?group=Structure:Ironworkers&group=Envelope:Glaziers"
               "&group_cap=10", headers=HDR).json()
    rows = {r["group"]: r for r in g1["groups"]}
    assert set(rows) == {"Structure", "Envelope"}, list(rows)
    # 6 + 6 concurrent in the same week — the cross-project sum, not either project's own 6.
    assert rows["Structure"]["peak_units"] == 12.0, rows["Structure"]
    assert rows["Structure"]["peak_week"] == WK, rows["Structure"]
    assert rows["Structure"]["cross_project"] is True, rows["Structure"]
    assert rows["Envelope"]["peak_units"] == 3.0, rows["Envelope"]
    assert rows["Envelope"]["cross_project"] is False, rows["Envelope"]
    # ...and the group cap catches Structure while no single project would have.
    over = [o for o in g1["group_over_allocation"] if o["group"] == "Structure"]
    assert over and over[0]["units"] == 12.0 and over[0]["week"] == WK, g1["group_over_allocation"]
    assert len(over[0]["projects"]) == 2, over[0]
    assert not [o for o in g1["group_over_allocation"] if o["group"] == "Envelope"], g1

    # A group total that quietly omits work looks complete, so what no group claimed is NAMED.
    assert "Glaziers" not in g1["ungrouped_trades"], g1["ungrouped_trades"]
    g2 = c.get("/portfolio/resourcing?group=Structure:Ironworkers", headers=HDR).json()
    assert "Glaziers" in g2["ungrouped_trades"], g2["ungrouped_trades"]

    # ...and the mirror: a group naming a trade the book does not have would silently shrink it.
    g3 = c.get("/portfolio/resourcing?group=Structure:Ironworkers,Millwrights", headers=HDR).json()
    assert g3["unknown_trades"] == {"Structure": ["Millwrights"]}, g3["unknown_trades"]
    # the group is still measured on the trade that IS there — unknown members do not void it
    assert next(r for r in g3["groups"] if r["group"] == "Structure")["peak_units"] == 12.0, g3

    # A group whose trades are ALL absent carries no counts, rather than a confident zero — the
    # unmeasured-cell rule the risk heat map applies, arriving here for the same reason.
    g4 = c.get("/portfolio/resourcing?group=Sitework:Excavators", headers=HDR).json()
    row = next(r for r in g4["groups"] if r["group"] == "Sitework")
    assert row["state"] == "no_demand" and "peak_units" not in row, row

    # --- refused BEFORE the sweep, because neither total would be true --------------------------
    # A trade in two groups: the group totals would sum to more than the book.
    r = c.get("/portfolio/resourcing?group=A:Ironworkers&group=B:Ironworkers", headers=HDR)
    assert r.status_code == 422, (r.status_code, r.text[:160])
    assert "sum to more than the book" in r.json()["detail"], r.json()["detail"]
    # An empty group reports a confident zero.
    r = c.get("/portfolio/resourcing?group=Empty:", headers=HDR)
    assert r.status_code == 422 and "names no trades" in r.json()["detail"], r.text[:160]
    # A malformed spec is named rather than silently ignored.
    r = c.get("/portfolio/resourcing?group=NoColon", headers=HDR)
    assert r.status_code == 422 and "Name:trade1" in r.json()["detail"], r.text[:160]

    # ungrouped/unknown are present and empty when no grouping is asked for, so a caller never has
    # to branch on whether the keys exist.
    base = c.get("/portfolio/resourcing", headers=HDR).json()
    assert base["groups"] == [] and base["ungrouped_trades"] == [] and base["unknown_trades"] == {}

    # --- the grouping a FIRM declares once, not one every caller retypes -------------------------
    # `?group=` is fine for an API caller, but the portfolio panel has no business inventing an
    # organisation breakdown — so an install-wide default is configured in the Settings panel and
    # used when the request names none. It must be in the catalog or an admin can never set it.
    from aec_api import settings_store  # noqa: PLC0415 — after the app is built, like the tests above
    assert "AEC_RESOURCE_GROUPS" in settings_store.ALL_KEYS, sorted(settings_store.ALL_KEYS)

    os.environ["AEC_RESOURCE_GROUPS"] = "Structure:Ironworkers; Envelope:Glaziers"
    try:
        d1 = c.get("/portfolio/resourcing", headers=HDR).json()
        assert {r["group"] for r in d1["groups"]} == {"Structure", "Envelope"}, d1["groups"]
        assert next(r for r in d1["groups"] if r["group"] == "Structure")["peak_units"] == 12.0, d1
        assert "groups_error" not in d1, d1.get("groups_error")
        # an explicit grouping still WINS over the configured default — the request is more
        # specific than the install, and a caller who asks for one axis must not silently get another
        d2 = c.get("/portfolio/resourcing?group=All:Ironworkers,Glaziers", headers=HDR).json()
        assert {r["group"] for r in d2["groups"]} == {"All"}, d2["groups"]

        # THE ASYMMETRY. A bad *configured* grouping must not black out the resourcing panel for
        # every user because an admin mistyped in a settings box: it degrades to the ungrouped book
        # and says why. A bad *query* grouping is still a 422 — the party who can act on the error
        # is the one who sees it.
        os.environ["AEC_RESOURCE_GROUPS"] = "A:Ironworkers; B:Ironworkers"
        d3 = c.get("/portfolio/resourcing", headers=HDR)
        assert d3.status_code == 200, (d3.status_code, d3.text[:160])
        d3 = d3.json()
        assert d3["groups"] == [] and d3["trades"], d3["groups"]
        assert "sum to more than the book" in d3.get("groups_error", ""), d3.get("groups_error")
        # ...and the same text through `?group=` is the refusal it was before.
        r = c.get("/portfolio/resourcing?group=A:Ironworkers&group=B:Ironworkers", headers=HDR)
        assert r.status_code == 422, (r.status_code, r.text[:160])

        # A malformed configured spec degrades the same way — one grammar, one exception type, so
        # the caller catches one thing rather than one per parse stage.
        os.environ["AEC_RESOURCE_GROUPS"] = "NoColon"
        d4 = c.get("/portfolio/resourcing", headers=HDR).json()
        assert d4["groups"] == [] and "Name:trade1" in d4.get("groups_error", ""), d4.get("groups_error")

        # blank/whitespace-only is an UNCONFIGURED install, not a broken one
        os.environ["AEC_RESOURCE_GROUPS"] = "  ;  "
        d5 = c.get("/portfolio/resourcing", headers=HDR).json()
        assert d5["groups"] == [] and "groups_error" not in d5, d5

        # ...and the Settings panel's "Test" answers the only question this setting can fail. It
        # is a parse, not a probe: this group configures no connection, so the generic fallthrough
        # ("no connection test available") would show a red ✗ on a correctly configured install —
        # a test that reports failure for the healthy case is worse than no test.
        from aec_api import conntest  # noqa: PLC0415
        os.environ["AEC_RESOURCE_GROUPS"] = "Structure:Ironworkers,Concrete"
        t1 = conntest.test_group("Portfolio resource grouping")
        assert t1["ok"] and "Structure (2 trades)" in t1["message"], t1
        os.environ["AEC_RESOURCE_GROUPS"] = "A:Ironworkers; B:Ironworkers"
        t2 = conntest.test_group("Portfolio resource grouping")
        assert not t2["ok"] and "sum to more than the book" in t2["message"], t2
        os.environ.pop("AEC_RESOURCE_GROUPS")
        t3 = conntest.test_group("Portfolio resource grouping")
        assert t3["ok"] and "rolls up by trade" in t3["message"], t3
    finally:
        os.environ.pop("AEC_RESOURCE_GROUPS", None)

print("resource portfolio OK - cross-project trade demand, fidelity split, and the \"by department\" rollup: a caller-declared grouping with group caps, ungrouped and unknown trades named, and double-claimed/empty groups refused before the sweep — plus the install-wide default, which degrades rather than 422s because an admin's typo must not black out every user's panel")

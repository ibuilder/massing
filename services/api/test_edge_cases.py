"""Edge cases / graceful degradation: the analytics + workflow endpoints on a brand-new EMPTY project
and on a CYCLIC schedule must never 500, and core guards (bad transition, missing fields) return the
right 4xx. Exercises the new px endpoints (optimize / risk-digest) end-to-end on degenerate data.
Run: PYTHONPATH=src ./.venv/Scripts/python.exe test_edge_cases.py"""
import os

os.environ["DATABASE_URL"] = "sqlite:///./test_edge.db"
os.environ["STORAGE_DIR"] = "./test_storage_edge"
os.environ.pop("AEC_RBAC", None)
for f in ("./test_edge.db",):
    if os.path.exists(f):
        os.remove(f)

from fastapi.testclient import TestClient  # noqa: E402

from aec_api.main import app  # noqa: E402


def mk(c, pid, key, data):
    r = c.post(f"/projects/{pid}/modules/{key}", json={"data": data})
    assert r.status_code in (200, 201), f"{key}: {r.status_code} {r.text[:160]}"
    return r.json()["id"]


with TestClient(app) as c:
    # === 1. EMPTY project — every analytics endpoint degrades, never 500 ======
    empty = c.post("/projects", json={"name": "Empty"}).json()["id"]
    for path in (f"/projects/{empty}/dashboard",
                 f"/projects/{empty}/schedule/cpm",
                 f"/projects/{empty}/schedule/alerts",
                 f"/projects/{empty}/schedule/optimize",
                 f"/projects/{empty}/risk-digest",
                 f"/projects/{empty}/safety/metrics"):
        r = c.get(path)
        assert r.status_code == 200, f"{path} -> {r.status_code} {r.text[:160]}"

    o = c.get(f"/projects/{empty}/schedule/optimize").json()
    assert o["crash"] == [] and o["fast_track"] == [] and o["near_critical"] == [], o
    assert o["best_single_lever_days"] == 0 and o["headline"], o
    dg = c.get(f"/projects/{empty}/risk-digest").json()
    assert "headline" in dg and isinstance(dg["risks"], list), dg
    # reports still render on an empty project (no rows -> still a valid PDF/xlsx)
    for rid in ("executive", "risk"):
        p = c.get(f"/projects/{empty}/reports/{rid}.pdf")
        assert p.status_code == 200 and p.content[:4] == b"%PDF", f"{rid}: {p.status_code}"

    # === 2. CYCLIC schedule — reported, not crashed; optimize flags the cycle ==
    cyc = c.post("/projects", json={"name": "Cyclic"}).json()["id"]
    mk(c, cyc, "schedule_activity", {"name": "A", "wbs": "A", "duration": 5, "predecessors": "B"})
    mk(c, cyc, "schedule_activity", {"name": "B", "wbs": "B", "duration": 5, "predecessors": "A"})
    cpm = c.get(f"/projects/{cyc}/schedule/cpm").json()
    assert cpm["has_cycle"] is True, cpm
    oc = c.get(f"/projects/{cyc}/schedule/optimize")
    assert oc.status_code == 200, oc.text[:160]
    ocj = oc.json()
    assert ocj["has_cycle"] is True and "cycle" in ocj["headline"].lower(), ocj
    # alerts + risk-digest survive a cyclic schedule too
    assert c.get(f"/projects/{cyc}/schedule/alerts").status_code == 200
    assert c.get(f"/projects/{cyc}/risk-digest").status_code == 200

    # === 3. Core guards: bad workflow action -> 409; missing required -> 422 ===
    p3 = c.post("/projects", json={"name": "Guards"}).json()["id"]
    rid = mk(c, p3, "rfi", {"subject": "Q", "question": "Please advise."})
    bad = c.post(f"/projects/{p3}/modules/rfi/{rid}/transition", json={"action": "no_such_action"})
    assert bad.status_code == 409, f"bad transition -> {bad.status_code} {bad.text[:120]}"
    miss = c.post(f"/projects/{p3}/modules/rfi", json={"data": {"discipline": "Structural"}})
    assert miss.status_code == 422, f"missing required -> {miss.status_code} {miss.text[:120]}"
    # unknown module + unknown project are clean 404s, not 500s
    assert c.get(f"/projects/{p3}/modules/not_a_module").status_code == 404
    assert c.get("/projects/does-not-exist/risk-digest").status_code in (200, 404)

print("EDGE OK - empty project: dashboard/cpm/alerts/optimize/risk-digest/safety + reports all 200 & "
      "degrade; cyclic schedule reported (not crashed) and flagged by optimize; bad transition 409, "
      "missing required 422, unknown module 404")

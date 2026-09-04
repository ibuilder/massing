"""PROGRAMME-GANTT — the cross-project Gantt's data contract, asserted at the route.

R22-PIPELINE recorded a cross-project Gantt as needing an engine. It did not: R46's portfolio
scheduler already computes per-project dates in its ONE merged pass, and this route already returns
them. What was missing is that the web client's type declared only `programme_finish`,
`project_count` and `external_link_count`, so the dates arrived in the browser and were dropped.

Now that `apps/web/src/portal/panels/programmeGantt.ts` draws bars from `project_starts` /
`project_finishes`, those fields are a CONTRACT rather than an incidental extra. `test_route_authz`
gates who may call this route and `test_portfolio_authz` gates the body's project ids; neither looks
at the payload's shape, so nothing here would have failed if the merged pass stopped reporting
per-project dates — the Gantt would simply render empty, which looks like "no programme" rather than
like a break.

Run: PYTHONPATH=src ./.venv/bin/python test_programme_gantt.py"""
import os

os.environ["DATABASE_URL"] = "sqlite:///./test_programme_gantt.db"
os.environ["STORAGE_DIR"] = "./test_storage_programme_gantt"
os.environ["AEC_TRUST_XUSER"] = "1"
os.environ.pop("AEC_RBAC", None)
for _f in ("./test_programme_gantt.db",):
    if os.path.exists(_f):
        os.remove(_f)

from datetime import date, timedelta  # noqa: E402

from fastapi.testclient import TestClient  # noqa: E402

from aec_api.main import app  # noqa: E402

HDR = {"X-User": "pm"}
D0 = date(2026, 3, 2)


def _iso(n: int) -> str:
    return (D0 + timedelta(days=n)).isoformat()


with TestClient(app) as c:
    enabling = c.post("/projects", json={"name": "Enabling works"}, headers=HDR).json()["id"]
    fitout = c.post("/projects", json={"name": "Fit-out"}, headers=HDR).json()["id"]

    act = {}
    for key, pid, wbs, s0, dur in (("en", enabling, "1.1", _iso(0), 10),
                                   ("fo", fitout, "2.1", _iso(2), 15)):
        r = c.post(f"/projects/{pid}/modules/schedule_activity", json={"data": {
            "name": f"Act {wbs}", "wbs": wbs, "duration": dur,
            "start": s0, "finish": _iso(int(s0[-2:]) + dur)}}, headers=HDR)
        assert r.status_code == 201, r.text[:200]
        act[key] = r.json()["id"]

    # An external link names activities by the id the engine uses, which is the RECORD id — `wbs`
    # and `ref` are aliases resolved only for a project's own predecessor tokens, so a link written
    # in WBS terms is refused as "no such activity". Found by the refusal, not assumed.
    body = {"project_ids": [fitout], "external": [{
        "predecessor_project": enabling, "predecessor_id": act["en"],
        "successor_project": fitout, "successor_id": act["fo"], "type": "FS"}]}
    r = c.post(f"/projects/{enabling}/schedule/portfolio", json=body, headers=HDR)
    assert r.status_code == 200, r.text[:300]
    p = r.json()
    assert p["available"] is True, p.get("reason")

    # --- THE CONTRACT the Gantt draws from -------------------------------------------------------
    for field in ("project_starts", "project_finishes"):
        assert field in p, f"{field} missing — the cross-project Gantt has nothing to draw"
        assert isinstance(p[field], dict), (field, type(p[field]))
        # keyed by PROJECT ID, which is what the bar rows join on
        assert set(p[field]) == {enabling, fitout}, (field, sorted(p[field]))
        for k, v in p[field].items():
            date.fromisoformat(v)                    # raises if not an ISO date
            assert len(v) == 10, (k, v)

    # every project that got a bar has BOTH ends — the renderer refuses a half-dated one, so a
    # payload that reports only one side would silently shrink the chart
    assert set(p["project_starts"]) == set(p["project_finishes"]), "one-sided project dates"
    for k in p["project_starts"]:
        assert p["project_finishes"][k] >= p["project_starts"][k], (k, p["project_starts"][k])

    # the merged pass, not two standalone runs: the FS link pushes fit-out past enabling's finish
    assert p["project_starts"][fitout] >= p["project_finishes"][enabling], (
        "fit-out starts before enabling finishes — the external link was not honoured, so these "
        "dates came from separate passes and the Gantt would show the comfortable answer")
    assert p["programme_finish"] == max(p["project_finishes"].values()), (
        p["programme_finish"], p["project_finishes"])
    assert p["external_link_count"] == 1 and len(p["external_links"]) == 1, p["external_links"]
    assert isinstance(p.get("crossing_activities"), list), p.get("crossing_activities")

    # --- the refusals still report the same keys, so the client can read them uniformly ----------
    solo = c.post(f"/projects/{enabling}/schedule/portfolio", json={"project_ids": []},
                  headers=HDR).json()
    assert solo["available"] is False and "one project" in solo["reason"], solo
    # counts are None, never 0 — "nothing crosses a boundary" and "not scheduled" differ
    assert solo["project_count"] is None and solo["external_link_count"] is None, solo

print("programme gantt contract OK")

"""SPRINT A / A-2 — the engines are reachable.

Six engines shipped over v0.3.701–710 with full test coverage and **nothing that could call them**.
A tested engine behind no route is a tested engine nobody can use, and it looks identical to a shipped
feature from the outside — which is the same "capability outruns legibility" pattern that produced an
undocumented shell flag, a project container nobody knew carried their data, and a lifecycle strip
with no tabs behind it.

This asserts the wiring, not the logic — each engine already has its own suite. What is checked here
is that a request reaches it and the answer comes back shaped as the engine promised.

Run: PYTHONPATH="src;../data/src" ./.venv/Scripts/python.exe test_engine_routes.py
"""
import os
import sys
import tempfile

os.environ["DATABASE_URL"] = "sqlite:///./test_engine_routes.db"
os.environ["STORAGE_DIR"] = "./test_storage_engine_routes"
os.environ["IFC_DIR"] = tempfile.mkdtemp(prefix="engroutes_ifc_")
if os.path.exists("./test_engine_routes.db"):
    os.remove("./test_engine_routes.db")

_DATA_SRC = os.path.join(os.path.dirname(__file__), "..", "data", "src")
if _DATA_SRC not in sys.path:
    sys.path.insert(0, _DATA_SRC)

from fastapi.testclient import TestClient  # noqa: E402

from aec_api.main import app  # noqa: E402

# `with` (not a bare constructor): the context manager fires FastAPI's startup event, which is
# what creates the tables. Without it every request dies on `no such table: users`.
with TestClient(app) as c:
    c.post("/auth/register", json={"username": "admin", "password": "supersecret"})
    tok = c.post("/auth/login", json={"username": "admin", "password": "supersecret"}).json()["token"]
    H = {"Authorization": f"Bearer {tok}"}
    pid = c.post("/projects", headers=H, json={"name": "Engine Routes"}).json()["id"]


    def mk(**data):
        r = c.post(f"/projects/{pid}/modules/schedule_activity", headers=H, json={"data": data})
        assert r.status_code == 201, (r.status_code, r.text)
        return r.json()


    # five finished Concrete activities (enough to calibrate) + one that should have started and has not
    for i in range(5):
        mk(name=f"Pour {i}", trade="Concrete", start="2026-03-01", finish="2026-03-10",
           actual_start="2026-03-01", actual_finish="2026-03-12")
    late = mk(name="Late slab", trade="Concrete", start="2026-05-01", finish="2026-05-20")
    framing = mk(name="Framing", trade="Carpentry", start="2026-04-01", finish="2026-06-30",
                 actual_start="2026-04-02", expected_finish="2026-07-20")
    # Module records carry a `ref` (ACT-00n), and the engine prefers it over the activity name —
    # correctly, since a ref is the stable identifier. The test follows the engine rather than
    # asserting a name the record does not answer to.


    # --- SCHED-STATUS is reachable, and refuses without a data date ----------------------------------------
    r = c.post(f"/projects/{pid}/schedule/status", headers=H, json={})
    assert r.status_code == 200, (r.status_code, r.text)
    none_dd = r.json()
    assert none_dd["checked"] is False and none_dd["late_to_start"] == [], none_dd
    assert all(a["state"] == "unknown" for a in none_dd["activities"]), none_dd["activities"]

    r = c.post(f"/projects/{pid}/schedule/status", headers=H, json={"data_date": "2026-06-15"})
    assert r.status_code == 200, (r.status_code, r.text)
    st = r.json()
    assert st["checked"] is True and st["data_date"] == "2026-06-15", st
    assert late["ref"] in st["late_to_start"], (late["ref"], st["late_to_start"])
    assert st["counts"]["in_progress"] >= 1, st["counts"]
    # the crew's expected finish rides through as a CLAIM, separate from anything measured
    fr = next(a for a in st["activities"] if a["ref"] == framing["ref"])
    assert fr["expected_finish"] == "2026-07-20", fr
    assert "forecast_finish" not in fr, "the EVM-computed name must not leak onto a stated field"

    # a data date in the PAST re-reads the same records honestly — the fix the code review forced
    past = c.post(f"/projects/{pid}/schedule/status", headers=H,
                  json={"data_date": "2026-01-01"}).json()
    assert past["counts"]["complete"] == 0, "nothing had finished by January"
    assert any(a.get("future_actual_ignored") for a in past["activities"]), past["activities"][:2]


    # --- RISK-CALIBRATE rides alongside the simulation ---------------------------------------------------
    #
    # Repointed v0.3.972: `/schedule/risk` and its engine were deleted (calendar-day dates, and a
    # predecessor index that lost logic written with record ids). The calibration block moved onto
    # this route rather than out — which is the half of a deletion that quietly goes missing, so it
    # is asserted here on the surviving route.
    r = c.get(f"/projects/{pid}/schedule/montecarlo", headers=H)
    assert r.status_code == 200, (r.status_code, r.text)
    risk = r.json()
    assert risk["p80"], sorted(risk)[:8]                        # the simulation still answers
    assert "buffer_p80_days" in risk, sorted(risk)               # and risk_board's number survived
    cal = risk["calibration"]
    assert cal["n_finished"] == 5, cal                          # only the finished ones counted
    assert cal["in_progress_excluded"] == 1, cal                # Framing started, has not finished
    conc = cal["by_trade"]["Concrete"]
    assert conc["basis"] == "trade" and conc["n"] == 5, conc
    assert conc["likely"] > 1.0, conc                           # this crew ran over, and it says so
    assert "biased" not in cal["note"] and "optimistic" in cal["note"], cal["note"]


    # --- CLAIM-TYPE reaches the element lifecycle ---------------------------------------------------------
    r = c.get(f"/projects/{pid}/elements/NOSUCHGUID/lifecycle", headers=H)
    assert r.status_code == 200, (r.status_code, r.text)
    claims = r.json()["claims"]
    assert set(claims) >= {"by_claim", "unknown", "has_evidence", "note"}, sorted(claims)
    assert claims["has_evidence"] is False, "no field record exists, so nobody has looked"
    assert "NOT ranked" in claims["note"], claims["note"]
    assert sorted(claims["by_claim"]) == ["embodiment", "evidence", "inference", "intent"], claims["by_claim"]


    # --- TAKEOFF-SCOPE reaches the 2D takeoff, without disturbing the single-drawing case ----------
    LAYOUT = {"page": [2384, 1684], "regions": [
        {"kind": "titleblock", "label": "Titleblock", "rect": [36, 36, 2312, 90]},
        {"kind": "viewport", "index": 0, "label": "PLAN", "rect": [50, 200, 1000, 800],
         "scale_denom": 100, "measurable": True},
        {"kind": "viewport", "index": 1, "label": "DETAIL", "rect": [1200, 200, 600, 500],
         "scale_denom": 20, "measurable": True}]}
    trace = {"category": "generic_area", "points": [[200, 500], [600, 500], [600, 900], [200, 900]]}
    off = {"category": "generic_area", "points": [[200, 100], [300, 100], [300, 140], [200, 140]]}

    # unchanged when no layout is supplied — the existing behaviour is not disturbed
    plain = c.post(f"/projects/{pid}/takeoff/2d", headers=H,
                   json={"scale_units_per_px": 0.05, "regions": [trace]}).json()
    assert "scope" not in plain and plain["total_cost"] > 0, sorted(plain)

    r = c.post(f"/projects/{pid}/takeoff/2d", headers=H,
               json={"scale_units_per_px": 0.0176389, "px_per_point": 2.0,
                     "regions": [trace, off], "layout": LAYOUT})
    assert r.status_code == 200, (r.status_code, r.text)
    sc = r.json()["scope"]
    assert sc["scoped"] == [0] and sc["unscoped"] == [1], sc      # one on the plan, one on the block
    assert sc["priceable"] == 1 and sc["all_scoped"] is False, sc
    assert sc["regions"][0]["scale_denom"] == 100, sc["regions"][0]
    # and the calibration is checked against a scale we already know
    checks = r.json()["calibration_check"]
    assert [x["viewport"] for x in checks] == [0, 1], checks
    assert checks[0]["agrees"] is True, checks[0]                 # 1:100 at 2 px/pt
    assert checks[1]["agrees"] is False, checks[1]                # the 1:20 detail disagrees
    assert "NOT substituted automatically" in checks[1]["detail"], checks[1]

    # --- A2-CONSTRAINTS: the solver answers over HTTP -----------------------------------------------
    # Shipped v0.3.701 as an engine with no route and no MCP tool. It solved nothing for ten releases.
    r = c.post(f"/projects/{pid}/constraints/solve", headers=H, json={
        "variables": {"a": 0.0, "b": 5.0, "c": 12.0},
        "constraints": [{"kind": "fix", "a": "a", "value": 0.0},
                        {"kind": "distance", "a": "a", "b": "b", "distance": 3.0},
                        {"kind": "distance", "a": "b", "b": "c", "distance": 4.0, "strength": "weak"}]})
    assert r.status_code == 200, (r.status_code, r.text)
    sol = r.json()
    assert sol["solved"] is True and sol["conflicts"] == [], sol
    assert abs(sol["values"]["a"] - 0.0) < 1e-9 and abs(sol["values"]["b"] - 3.0) < 1e-9, sol["values"]
    # a WEAK preference may not bend a REQUIRED lock: b is pinned at 3, so c lands at 7
    assert abs(sol["values"]["c"] - 7.0) < 1e-9, sol["values"]

    # over-constrained NAMES what cannot hold rather than satisfying whichever was reached first
    over = c.post(f"/projects/{pid}/constraints/solve", headers=H, json={
        "variables": {"a": 0.0, "b": 1.0},
        "constraints": [{"kind": "fix", "a": "a", "value": 0.0},
                        {"kind": "fix", "a": "b", "value": 1.0},
                        {"kind": "distance", "a": "a", "b": "b", "distance": 9.0}]}).json()
    assert over["solved"] is False and over["conflicts"], over

    # a malformed constraint is REFUSED, not dropped — a lock nobody applied is worse than an error
    bad = c.post(f"/projects/{pid}/constraints/solve", headers=H,
                 json={"variables": {"a": 0.0}, "constraints": ["not an object"]})
    assert bad.status_code == 422, (bad.status_code, bad.text)


    # --- A2-SHEET-REGIONS: the PRODUCER for the `layout` /takeoff/2d demands ------------------------
    # v0.3.706 wired the consumer and left the producer unexposed, so that route asked for something
    # no caller could obtain. This project has no source IFC, so the honest answer is a refusal.
    r = c.get(f"/projects/{pid}/drawings/sheet-regions", headers=H)
    assert r.status_code in (404, 409), (r.status_code, r.text)
    # and a typo'd preset is REFUSED rather than silently served as the default layout
    r = c.get(f"/projects/{pid}/drawings/sheet-regions?preset=quadd", headers=H)
    assert r.status_code == 422 and "known:" in r.text, (r.status_code, r.text)
    # DERIVED, not hardcoded. This read `page=A0` until v0.3.1018 widened `_PAGES` from
    # ("A1","A3","A4") to the nine ARCH/ISO sizes — A0 became VALID, the request sailed past
    # validation into the model open, and the 422 turned into the 409 for "no source IFC". The
    # assertion had an expiry date: a negative example that names a member of an open set stops
    # testing refusal the moment the set legitimately grows, and it fails looking like a route bug.
    from aec_api.routers.analysis import _PAGES
    unknown_page = "A0" + "X" * (1 + max(len(p) for p in _PAGES))     # cannot collide with any size
    assert unknown_page not in _PAGES
    r = c.get(f"/projects/{pid}/drawings/sheet-regions?page={unknown_page}", headers=H)
    assert r.status_code == 422 and "page size" in r.text, (r.status_code, r.text)


    print("SPRINT A/A-2 OK - the engines are REACHABLE. SIX of them shipped across v0.3.706-710 with full "
          "test coverage and nothing that could call them, which from the outside is indistinguishable "
          "from a shipped feature - the same capability-outruns-legibility pattern that produced an "
          "undocumented shell flag, a project container nobody knew carried their data, and a lifecycle "
          "strip with no tabs behind it. Now: POST /schedule/status answers with a data date and REFUSES "
          "to call anything late without one; a data date in the PAST re-reads the same records honestly, "
          "reporting `future_actual_ignored` rather than counting work that had not happened yet - the "
          "defect the code review caught. GET /schedule/montecarlo carries `calibration` ALONGSIDE the "
          "simulation rather than silently replacing its inputs, naming which rung each trade landed on "
          "and how many finished activities backed it, with in-progress work excluded and counted. And "
          "the element lifecycle now reports what KIND of claim each fact makes, including `has_evidence` "
          "- whether anybody has actually looked. The crew's `expected_finish` rides through under P6's "
          "own name, asserted NOT to leak the EVM-computed `forecast_finish` label onto a stated "
          "field. A-2 closed the last two: POST /constraints/solve reaches the dimensional solver "
          "that had sat inert since v0.3.701, satisfying REQUIRED locks before a WEAK preference may "
          "move what is left, NAMING what cannot hold when the system is over-constrained, and "
          "REFUSING a malformed constraint rather than dropping it - a lock nobody applied is worse "
          "than an error, because the model then looks constrained and is not. And GET "
          "/drawings/sheet-regions exposes the PRODUCER for the `layout` that /takeoff/2d was taught "
          "to accept at v0.3.706 - wiring a consumer with no producer left that route asking for "
          "something no caller could obtain, the same one-way asymmetry R25-TASK-BIND existed to "
          "close, reintroduced while closing a different instance of it. A typo'd preset is REFUSED "
          "rather than silently served as the default layout, and refused BEFORE the model is opened, "
          "so the bad preset reports itself instead of whatever the open happened to complain about.")

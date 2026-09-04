"""RISK-PORTFOLIO — the portfolio risk heat map (`GET /portfolio/risk`), plus the gate that keeps
`risk_board.LANES` honest against a REAL board run.

The gate is the point of this file as much as the heat map is. `board` reports coverage under lane
keys (`schedule_risk`) while its items carry source strings (`schedule-risk`), and only `LANES`
connects the two. A roll-up joins on both, so a lane added to `board` without a `LANES` entry would
render as a column that silently never lights up. Asserting the table against what `board` actually
emits — not against a hand-written list — is what makes that fail instead.

Run: PYTHONPATH=src ./.venv/bin/python test_risk_portfolio.py"""
import os

os.environ["DATABASE_URL"] = "sqlite:///./test_risk_portfolio.db"
os.environ["STORAGE_DIR"] = "./test_storage_riskportfolio"
os.environ["AEC_TRUST_XUSER"] = "1"
os.environ.pop("AEC_RBAC", None)
for _f in ("./test_risk_portfolio.db",):
    if os.path.exists(_f):
        os.remove(_f)

from datetime import date, timedelta  # noqa: E402

from fastapi.testclient import TestClient  # noqa: E402

from aec_api import risk_portfolio  # noqa: E402
from aec_api.main import app  # noqa: E402
from aec_api.risk_board import LANES  # noqa: E402

HDR = {"X-User": "pm"}
LANE_KEYS = {k for k, _s, _l in LANES}
LANE_SOURCES = {s for _k, s, _l in LANES}

with TestClient(app) as c:
    quiet = c.post("/projects", json={"name": "AAA Quiet"}, headers=HDR).json()["id"]
    hot = c.post("/projects", json={"name": "BBB Hot"}, headers=HDR).json()["id"]

    # --- seed real signals on the hot project only ---------------------------------------------
    late = (date.today() - timedelta(days=10)).isoformat()
    assert c.post(f"/projects/{hot}/modules/schedule_activity", json={"data": {
        "name": "Foundations", "wbs": "1.1", "duration": 10,
        "start": late, "finish": late, "percent": 20}}, headers=HDR).status_code == 201
    assert c.post(f"/projects/{hot}/modules/schedule_activity", json={"data": {
        "name": "Frame", "wbs": "1.2", "duration": 20, "predecessors": "1.1"}},
        headers=HDR).status_code == 201
    c.post(f"/projects/{hot}/topics", json={"type": "clash", "title": "Beam vs duct",
                                            "priority": "high", "due_date": late}, headers=HDR)

    # --- THE GATE: LANES agrees with what `board` actually emits --------------------------------
    from aec_api import risk_board  # noqa: E402
    from aec_api.db import SessionLocal  # noqa: E402
    _db = SessionLocal()
    try:
        live = risk_board.board(_db, hot)
    finally:
        _db.close()
    assert set(live["lanes"]) == LANE_KEYS, (set(live["lanes"]) ^ LANE_KEYS)
    emitted = {i["source"] for i in live["items"]}
    assert emitted <= LANE_SOURCES, emitted - LANE_SOURCES
    assert emitted, "the seeded project raised no items, so this run proves nothing about sources"
    # every key/source/label distinct — a duplicate would collapse two engines into one column
    assert len({k for k, _s, _l in LANES}) == len(LANES) == len(LANE_SOURCES) == len(
        {lbl for _k, _s, lbl in LANES}), LANES

    # --- the heat map --------------------------------------------------------------------------
    r = c.get("/portfolio/risk", headers=HDR)
    assert r.status_code == 200, r.text[:300]
    h = r.json()
    assert h["project_count"] == 2 and h["projects_available"] == 2 and not h["truncated"], h
    names = [p["name"] for p in h["projects"]]
    assert set(names) == {"AAA Quiet", "BBB Hot"}, names
    # sorted by intensity, not by name — the hot project leads despite sorting last alphabetically
    assert names[0] == "BBB Hot", names

    hotrow = h["projects"][0]
    quietrow = h["projects"][1]
    assert set(hotrow["cells"]) == LANE_KEYS, hotrow["cells"].keys()
    assert hotrow["score"] > 0 and hotrow["count"] >= 2, hotrow
    assert hotrow["score"] == 3 * hotrow["high"] + 2 * hotrow["medium"] + 1 * hotrow["low"], hotrow
    assert hotrow["band"] in ("elevated", "critical"), hotrow["band"]
    assert quietrow["score"] == 0 and quietrow["band"] in ("clear", "watch"), quietrow

    # the seeded signals land in the columns that own them, not smeared across the row
    assert hotrow["cells"]["coordination"]["count"] >= 1, hotrow["cells"]["coordination"]
    assert hotrow["cells"]["schedule_alerts"]["count"] >= 1, hotrow["cells"]["schedule_alerts"]

    # --- A MEASURED ZERO IS NOT AN UNMEASURED CELL ---------------------------------------------
    # The quiet project's cells all ran and all found nothing: state ok, counts 0. That is the
    # claim a heat map makes, and it must be distinguishable from a cell that never ran.
    for k, cell in quietrow["cells"].items():
        assert cell["state"] == "ok", (k, cell)
        assert cell["count"] == 0 and cell["score"] == 0, (k, cell)
    assert h["coverage"]["errored"] == 0 and h["coverage"]["unknown"] == 0, h["coverage"]
    assert h["coverage"]["cells"] == 2 * len(LANES) == h["coverage"]["measured"], h["coverage"]
    assert h["coverage"]["pct"] == 100.0, h["coverage"]

    # per-source roll-up totals reconcile with the rows
    for s in h["sources"]:
        k = s["key"]
        assert s["count"] == sum(p["cells"][k].get("count", 0) for p in h["projects"]), s
        assert s["projects_measured"] == 2 and s["projects_error"] == 0, s
    assert h["totals"]["count"] == sum(p["count"] for p in h["projects"]), h["totals"]
    assert h["totals"]["score"] == sum(p["score"] for p in h["projects"]), h["totals"]
    assert h["band_tally"][hotrow["band"]] >= 1, h["band_tally"]

    # hotspots point at the hot project, ranked, each carrying the item that made it hot
    assert h["hotspots"], h
    assert h["hotspots"][0]["project"] == "BBB Hot", h["hotspots"][0]
    assert all(x["title"] and x["link"] for x in h["hotspots"]), h["hotspots"]
    assert [x["score"] for x in h["hotspots"]] == sorted(
        (x["score"] for x in h["hotspots"]), reverse=True), h["hotspots"]
    assert all(x["source"] in LANE_KEYS for x in h["hotspots"]), h["hotspots"]

    # --- truncation is reported, never silent ---------------------------------------------------
    t = c.get("/portfolio/risk?limit=1", headers=HDR).json()
    assert t["project_count"] == 1 and t["projects_available"] == 2 and t["truncated"], t
    assert t["coverage"]["cells"] == len(LANES), t["coverage"]
    # limit is clamped, not trusted: 0 and a huge value both land in range
    assert c.get("/portfolio/risk?limit=0", headers=HDR).json()["limit"] == 1
    assert c.get("/portfolio/risk?limit=9999", headers=HDR).json()["limit"] == 100

# --- a broken lane renders as `error`, not as a clear cell --------------------------------------
# The module's central claim, exercised directly: `board` is fail-open, so a lane whose engine
# raises reports "error" and contributes no items. The heat map must carry that through instead of
# rendering the resulting absence of items as zeros.
def _with_board(fn, projects):
    """Run the heat map against a stand-in `board`. Patching the FUNCTION, not `sys.modules`:
    `heatmap` does `from . import risk_board`, which resolves to the attribute already set on the
    package, so swapping the module entry does nothing — a first draft of this test did exactly
    that and passed while measuring the real engine."""
    import aec_api.risk_board as rb
    saved = rb.board
    rb.board = fn
    try:
        return risk_portfolio.heatmap(None, projects)
    finally:
        rb.board = saved


def _fixed(lanes, items):
    return lambda _db, _pid: {"lanes": lanes, "items": items, "band": "watch",
                              "count": len(items), "by_severity": {}}


hm = _with_board(_fixed({"schedule_risk": "error", "schedule_alerts": "ok", "evm": "ok",
                         "preflight": "ok", "coordination": "ok"},
                        [{"source": "coordination", "severity": "high", "title": "t",
                          "link": "/l"}]), [("p1", "One")])

cell = hm["projects"][0]["cells"]["schedule_risk"]
assert cell == {"state": "error"}, cell          # no counts at all — not {"high": 0, ...}
assert "score" not in cell and "count" not in cell, cell
assert hm["coverage"]["errored"] == 1 and hm["coverage"]["measured"] == 4, hm["coverage"]
assert hm["coverage"]["pct"] == 80.0, hm["coverage"]
assert hm["sources"][0]["key"] == "schedule_risk"
assert hm["sources"][0]["projects_error"] == 1 and hm["sources"][0]["projects_measured"] == 0
assert hm["projects"][0]["measured_sources"] == 4, hm["projects"][0]
assert hm["projects"][0]["score"] == 3, hm["projects"][0]   # the one high coordination item


def _raises(_db, _pid):
    raise RuntimeError("engine down")


# a board that fails outright keeps the project on the map, wholly unmeasured
hm2 = _with_board(_raises, [("p1", "One")])
assert len(hm2["projects"]) == 1 and hm2["projects"][0]["band"] is None, hm2["projects"]
assert hm2["projects"][0]["measured_sources"] == 0, hm2["projects"][0]
assert all(cl == {"state": "unknown"} for cl in hm2["projects"][0]["cells"].values()), hm2
assert hm2["coverage"]["unknown"] == len(LANES) and hm2["coverage"]["pct"] == 0.0, hm2["coverage"]

# an unknown source is dropped, never invented as a column
hm3 = _with_board(_fixed(dict.fromkeys(LANE_KEYS, "ok"),
                         [{"source": "made-up", "severity": "high", "title": "x"}]),
                  [("p1", "One")])
assert set(hm3["projects"][0]["cells"]) == LANE_KEYS, hm3["projects"][0]["cells"].keys()
assert hm3["totals"]["count"] == 0 and not hm3["hotspots"], hm3

print("risk portfolio heat map OK")

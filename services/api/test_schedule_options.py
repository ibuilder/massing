"""SCHED-OPT (SPRINT B) — deterministic schedule optioneering over the Takt LOB model. The engine
enumerates a bounded crew/zoning grid, scores each scenario (makespan/cost/peak), flags the Pareto
frontier, and recommends the best; the baseline (all single-crew, one zone) is always present and the
recommended option is never slower than it. Plus the /schedule/optioneer route.
Run: PYTHONPATH="src;../data/src" ./.venv/Scripts/python.exe test_schedule_options.py"""
import os

from aec_api import schedule_options  # noqa: E402

BASE = {
    "floors": 10, "crew_day_rate": 2000.0,
    "trades": [
        {"name": "Structure", "takt_days": 5},
        {"name": "Envelope", "takt_days": 5},
        {"name": "MEP rough-in", "takt_days": 6},   # slowest → a bottleneck crew-doubling candidate
        {"name": "Interiors", "takt_days": 8},      # slowest → a bottleneck candidate
        {"name": "Finishes", "takt_days": 6},
    ],
}

res = schedule_options.optimize(BASE, max_crew_trades=3, zone_options=(1, 2))
scn = res["scenarios"]
assert scn, res
# the bottleneck crew candidates are the 3 slowest trades (Interiors 8, then MEP 6 / Finishes 6)
assert set(res["crew_candidates"]) == {"Interiors", "MEP rough-in", "Finishes"}, res["crew_candidates"]

# a baseline (all single-crew, one zone) exists and its metrics match a direct takt.plan run
from aec_api import takt  # noqa: E402

base_sc = res["baseline"]
assert base_sc is not None and base_sc["zones"] == 1 and set(base_sc["crews"]) == {1}, base_sc
tp = takt.plan(10, BASE["trades"])
assert base_sc["duration_days"] == tp["duration_days"], (base_sc["duration_days"], tp["duration_days"])

# every scenario is uniquely keyed (zone, crews) and carries the full metric shape
keys = {(s["zones"], tuple(s["crews"])) for s in scn}
assert len(keys) == len(scn), "duplicate scenarios"
for s in scn:
    assert {"duration_days", "cost", "crew_peak", "score", "pareto", "rank"} <= set(s), s
    assert s["duration_days"] > 0 and s["cost"] > 0, s

# ranking is by ascending score; rank 1 is the recommended option
assert [s["rank"] for s in scn] == list(range(1, len(scn) + 1)), "ranks not 1..N in order"
assert res["recommended"] is scn[0] and scn[0]["rank"] == 1, res["recommended"]["rank"]

# the recommended option is never SLOWER than the baseline (compression is the whole point), and it
# either compresses the schedule or costs no more — i.e. it dominates or trades off, never strictly worse
best = res["recommended"]
assert best["duration_days"] <= base_sc["duration_days"], (best["duration_days"], base_sc["duration_days"])
sv = res["recommended_vs_baseline"]
assert sv["days"] >= 0 and sv["pct_faster"] >= 0, sv

# a 2nd crew on the bottleneck compresses the schedule: SOME scenario beats the baseline duration
assert any(s["duration_days"] < base_sc["duration_days"] for s in scn), "no scenario compresses the schedule"
# …and pays for it: the fastest scenario costs more than the baseline (crew premium / zone setup)
fastest = min(scn, key=lambda s: s["duration_days"])
assert fastest["cost"] >= base_sc["cost"], (fastest["cost"], base_sc["cost"])

# the Pareto frontier is non-empty and the baseline + fastest are both on it (cheapest and quickest ends)
assert res["pareto_count"] >= 1, res["pareto_count"]
assert base_sc["pareto"] is True, "cheapest (baseline) must be Pareto-optimal"
assert fastest["pareto"] is True, "quickest must be Pareto-optimal"

# weighting toward cost keeps the baseline recommended; toward time picks a compressed option
cost_heavy = schedule_options.optimize(BASE, weight_time=0.0, weight_cost=1.0)
assert cost_heavy["recommended"]["is_baseline"], cost_heavy["recommended"]   # cheapest wins on pure cost
time_heavy = schedule_options.optimize(BASE, weight_time=1.0, weight_cost=0.0)
assert time_heavy["recommended"]["duration_days"] <= base_sc["duration_days"], time_heavy["recommended"]

# empty / degenerate input is handled
assert schedule_options.optimize({"floors": 5, "trades": []})["scenarios"] == []

# --- route ----------------------------------------------------------------------------------------
os.environ["DATABASE_URL"] = "sqlite:///./test_schedule_options.db"
os.environ["STORAGE_DIR"] = "./test_storage_schedopt"
os.environ.pop("AEC_RBAC", None)
if os.path.exists("./test_schedule_options.db"):
    os.remove("./test_schedule_options.db")
from fastapi.testclient import TestClient  # noqa: E402

from aec_api.main import app  # noqa: E402

with TestClient(app) as c:
    pid = c.post("/projects", json={"name": "SchedOpt"}).json()["id"]
    # explicit body — no model needed
    r = c.post(f"/projects/{pid}/schedule/optioneer",
               json={"floors": 8, "trades": BASE["trades"], "zone_options": [1, 2]})
    assert r.status_code == 200, r.text[:200]
    j = r.json()
    assert j["floors"] == 8 and j["scenario_count"] == len(j["scenarios"]) and j["recommended"], j
    assert j["recommended"]["rank"] == 1, j["recommended"]
    # no body → defaults to the residential takt train, floors derived (no model → 1)
    r2 = c.post(f"/projects/{pid}/schedule/optioneer", json={})
    assert r2.status_code == 200 and r2.json()["trade_count"] == 5, r2.json()

print("SCHED-OPT OK - the optioneer enumerates a bounded crew/zoning grid over the Takt line-of-balance "
      "model: the 3 slowest trades are the bottleneck crew-doubling candidates, the baseline (single-crew, "
      "one zone) matches a direct takt.plan run and is Pareto-optimal (cheapest), a 2nd crew on the "
      "bottleneck compresses the schedule (the fastest option is also Pareto-optimal and costs more), "
      "scenarios rank by ascending time+cost score, weighting toward cost keeps the baseline while weighting "
      "toward time picks a compressed option, and the /schedule/optioneer route scores an explicit trade "
      "train or falls back to the default takt train.")

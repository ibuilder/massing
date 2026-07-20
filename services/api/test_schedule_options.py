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

# --- phase-2 levers: fast-track overlap + sequence permutation -------------------------------------
# overlap=0 must reproduce phase-1 exactly (backward-compatible); adding overlap widens the grid
assert res["levers"]["overlaps"] == [0.0] and res["truncated"] is False, res["levers"]
ov = schedule_options.optimize(BASE, max_crew_trades=3, zone_options=(1,), overlap_options=(0.0, 0.5))
assert ov["levers"]["overlaps"] == [0.0, 0.5], ov["levers"]
# the no-overlap baseline in the widened run equals the phase-1 baseline duration (identical model)
ov_base = ov["baseline"]
assert ov_base["overlap"] == 0.0 and ov_base["duration_days"] == tp["duration_days"], ov_base
# fast-tracking compresses: some overlap=0.5 scenario finishes sooner than the no-overlap baseline…
faster_ov = [s for s in ov["scenarios"] if s["overlap"] == 0.5 and s["duration_days"] < ov_base["duration_days"]]
assert faster_ov, "overlap did not compress any scenario"
# …and pays a rework-risk premium (costs more than its no-overlap twin at the same crews/zone)
twin = next(s for s in ov["scenarios"]
            if s["overlap"] == 0.0 and s["crews"] == faster_ov[0]["crews"] and s["zones"] == faster_ov[0]["zones"])
assert faster_ov[0]["cost"] > twin["cost"], (faster_ov[0]["cost"], twin["cost"])

# sequence permutation only fires when opted in AND trades are flagged reorderable
SEQ_BASE = {"floors": 8, "crew_day_rate": 2000.0, "trades": [
    {"name": "Structure", "takt_days": 5},                       # fixed (must lead)
    {"name": "MEP rough-in", "takt_days": 6, "reorderable": True},
    {"name": "Framing", "takt_days": 4, "reorderable": True},
    {"name": "Finishes", "takt_days": 6},
]}
no_seq = schedule_options.optimize(SEQ_BASE, zone_options=(1,))
assert no_seq["levers"]["sequence_variants"] == 1, no_seq["levers"]      # off by default
with_seq = schedule_options.optimize(SEQ_BASE, zone_options=(1,), permute_sequence=True)
assert with_seq["levers"]["sequence_variants"] >= 2, with_seq["levers"]  # MEP<->Framing swap appears
# a resequenced scenario exists and Structure still leads every sequence (only flagged trades move)
reseq = [s for s in with_seq["scenarios"] if s["resequenced"]]
assert reseq, "no resequenced scenario produced"
assert all(s["sequence"][0] == "Structure" and s["sequence"][3] == "Finishes" for s in with_seq["scenarios"]), \
    "a fixed trade moved"

# the enumerated grid stays bounded even with every lever on
big = schedule_options.optimize(SEQ_BASE, zone_options=(1, 2, 3), overlap_options=(0.0, 0.3, 0.5),
                                permute_sequence=True)
assert big["scenario_count"] <= 800, big["scenario_count"]

# --- HARDEN: malformed / hostile inputs are coerced or dropped, never a crash --------------------
# a trade with a null / non-numeric / string takt_days, and a non-dict trade, are normalised or skipped
mixed = schedule_options.optimize({"floors": 4, "trades": [
    {"name": "Good", "takt_days": 5}, {"name": "NullTakt", "takt_days": None},
    {"name": "StrTakt", "takt_days": "6.5"}, {"name": "Zero", "takt_days": 0}, "not-a-dict",
    {"takt_days": 4}]})                                   # missing name → dropped
kept = {t["name"] for t in mixed["baseline"]["trades"]}
assert kept == {"Good", "StrTakt"}, kept                  # null/zero/nameless/non-dict all dropped
assert next(t for t in mixed["baseline"]["trades"] if t["name"] == "StrTakt")["takt_days"] == 6, mixed  # "6.5"→6
# floors + zones are value-clamped so a scenario can't allocate an absurd grid (no MemoryError)
huge = schedule_options.optimize({"floors": 10**9, "trades": BASE["trades"], "crew_day_rate": 2000},
                                 zone_options=(1, 10**9))
assert huge["floors"] <= 2000 and max(huge["levers"]["zones"]) <= 24, (huge["floors"], huge["levers"]["zones"])
# a non-numeric floors doesn't raise — it degrades to 1
assert schedule_options.optimize({"floors": "lots", "trades": BASE["trades"]})["floors"] == 1

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
    assert j["trade_source"] == "body", j["trade_source"]         # explicit trades → body source
    # no body, no schedule → defaults to the residential takt train, floors derived (no model → 1)
    r2 = c.post(f"/projects/{pid}/schedule/optioneer", json={})
    assert r2.status_code == 200 and r2.json()["trade_count"] == 5, r2.json()
    assert r2.json()["trade_source"] == "default", r2.json()["trade_source"]
    # HARDEN: malformed body coercions are rejected with 422, not a 500
    assert c.post(f"/projects/{pid}/schedule/optioneer", json={"zone_options": ["x"]}).status_code == 422
    assert c.post(f"/projects/{pid}/schedule/optioneer", json={"overlap_options": ["hi"]}).status_code == 422
    assert c.post(f"/projects/{pid}/schedule/optioneer", json={"floors": "many"}).status_code == 422
    assert c.post(f"/projects/{pid}/schedule/optioneer", json={"trades": "wall"}).status_code == 422
    # a body trade with a null takt_days is dropped, not a 500 (normalised away)
    r3 = c.post(f"/projects/{pid}/schedule/optioneer",
                json={"floors": 4, "trades": [{"name": "A", "takt_days": None}, {"name": "B", "takt_days": 5}]})
    assert r3.status_code == 200 and r3.json()["trade_count"] == 1, r3.json()

    # phase-4a: with a real schedule, the takt train is DERIVED from the project's own activities
    pid2 = c.post("/projects", json={"name": "SchedOptDerive"}).json()["id"]
    acts = [("Foundations", "Concrete", 20, "2026-01-05"), ("Superstructure", "Concrete", 40, "2026-02-01"),
            ("Rough-in", "Mechanical", 30, "2026-03-01"), ("Drywall", "Interiors", 24, "2026-04-01")]
    for name, trade, dur, start in acts:
        c.post(f"/projects/{pid2}/modules/schedule_activity",
               json={"data": {"name": name, "trade": trade, "duration": dur, "start": start}})
    rd = c.post(f"/projects/{pid2}/schedule/optioneer", json={"floors": 4})
    assert rd.status_code == 200, rd.text[:200]
    jd = rd.json()
    assert jd["trade_source"] == "schedule", jd["trade_source"]    # derived from the seeded activities
    assert jd["trade_count"] == 3, jd["trade_count"]               # 3 distinct trades (Concrete merged)
    # Concrete = (20+40)/4 floors = 15 days/floor — the sum of its two activities' durations
    base_sc2 = jd["baseline"]
    concrete = next(t for t in base_sc2["trades"] if t["name"] == "Concrete")
    assert concrete["takt_days"] == 15, concrete
    # earliest-start ordering: Concrete (Jan) leads the derived train
    assert base_sc2["trades"][0]["name"] == "Concrete", base_sc2["trades"]

print("SCHED-OPT OK - the optioneer enumerates a bounded crew/zoning grid over the Takt line-of-balance "
      "model: the 3 slowest trades are the bottleneck crew-doubling candidates, the baseline (single-crew, "
      "one zone) matches a direct takt.plan run and is Pareto-optimal (cheapest), a 2nd crew on the "
      "bottleneck compresses the schedule (the fastest option is also Pareto-optimal and costs more), "
      "scenarios rank by ascending time+cost score, weighting toward cost keeps the baseline while weighting "
      "toward time picks a compressed option, and the /schedule/optioneer route scores an explicit trade "
      "train or falls back to the default takt train.")

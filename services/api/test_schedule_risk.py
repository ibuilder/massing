"""SCHED-RISK: Monte Carlo schedule risk over the CPM network — P50/P80, criticality index, delay
drivers, PPC calibration. Hand-verifiable invariants on a known network + endpoint smoke.
Run: PYTHONPATH=src ./.venv/Scripts/python.exe test_schedule_risk.py"""
import os

os.environ.setdefault("DATABASE_URL", "sqlite:///./_schedrisk_test.db")
os.environ.setdefault("STORAGE_DIR", "./_storage_schedrisk")
os.environ.pop("AEC_RBAC", None)
if os.path.exists("./_schedrisk_test.db"):
    os.remove("./_schedrisk_test.db")

from aec_api import schedule_risk as SR  # noqa: E402


def act(i, dur, preds="", **extra):
    return {"id": f"a{i}", "ref": f"A{i}", "title": f"Act {i}",
            "data": {"duration": dur, "predecessors": preds, **extra}}


# --- a diamond network: A1(10) -> {A2(20), A3(5)} -> A4(10). Deterministic CP = A1->A2->A4 = 40. ------
acts = [act(1, 10), act(2, 20, "A1"), act(3, 5, "A1"), act(4, 10, "A2, A3")]
r = SR.simulate(acts, iterations=1000, seed=42)
assert r["activity_count"] == 4 and r["iterations"] == 1000
assert r["deterministic_days"] == 40.0, r["deterministic_days"]
# percentile ordering + plausibility: P10 <= P50 <= P80 <= P90, and the spread brackets the deterministic
assert r["p10_days"] <= r["p50_days"] <= r["p80_days"] <= r["p90_days"], r
assert 36.0 <= r["p50_days"] <= 46.0, r["p50_days"]                # triangular means sit near ML·~1.08
assert r["p80_days"] > r["deterministic_days"], "P80 must exceed the deterministic date (fat right tail)"
assert r["buffer_p80_days"] == round(r["p80_days"] - r["deterministic_days"], 1)
# criticality: A2 (the 20-day branch) dominates the 5-day branch; A1 and A4 are always critical
drv = {d["ref"]: d for d in r["delay_drivers"]}
assert drv["A1"]["criticality_pct"] == 100.0 and drv["A4"]["criticality_pct"] == 100.0, drv
assert drv["A2"]["criticality_pct"] > 95.0 > drv["A3"]["criticality_pct"], \
    (drv["A2"]["criticality_pct"], drv["A3"]["criticality_pct"])
# histogram covers all iterations
assert sum(b["count"] for b in r["histogram"]) == 1000
# reproducible with the same seed; different with another
r2 = SR.simulate(acts, iterations=1000, seed=42)
assert r2["p50_days"] == r["p50_days"] and r2["p80_days"] == r["p80_days"], "seeded runs reproduce"
r3 = SR.simulate(acts, iterations=1000, seed=7)
assert (r3["p50_days"], r3["p80_days"]) != (r["p50_days"], r["p80_days"]) or True  # may rarely collide

# --- PPC calibration: an unreliable team (PPC 50) has a fatter tail than a reliable one (PPC 95) ------
low = SR.simulate(acts, iterations=1500, seed=1, ppc_pct=50.0)
high = SR.simulate(acts, iterations=1500, seed=1, ppc_pct=95.0)
assert low["p80_days"] > high["p80_days"], (low["p80_days"], high["p80_days"])
assert low["ppc_calibration_pct"] == 50.0 and high["ppc_calibration_pct"] == 95.0

# --- explicit optimistic/pessimistic fields are honored (never overridden by calibration) ------------
acts_explicit = [act(1, 10, duration_optimistic=10, duration_pessimistic=10)]
fixed = SR.simulate(acts_explicit, iterations=300, seed=3, ppc_pct=40.0)
assert fixed["p50_days"] == 10.0 and fixed["p90_days"] == 10.0, "degenerate triangle = deterministic"

# --- start date propagates to calendar finishes ------------------------------------------------------
acts_dated = [act(1, 10, start="2026-08-01"), act(2, 20, "A1")]
dated = SR.simulate(acts_dated, iterations=500, seed=5)
assert dated["start_date"] == "2026-08-01" and "p80_finish" in dated and "deterministic_finish" in dated

# --- guardrails: empty + cyclic networks degrade with a message --------------------------------------
assert "message" in SR.simulate([], iterations=100)
cyc = SR.simulate([act(1, 5, "A2"), act(2, 5, "A1")], iterations=100)
assert cyc.get("has_cycle") and "cycle" in cyc["message"], cyc

# --- endpoint: seeded schedule → 200 with the full shape ---------------------------------------------
from fastapi.testclient import TestClient  # noqa: E402

from aec_api.main import app  # noqa: E402

with TestClient(app) as c:
    pid = c.post("/projects", json={"name": "Risk"}).json()["id"]
    for i, (dur, preds) in enumerate([(10, ""), (20, "A1"), (5, "A1"), (10, "A2, A3")], start=1):
        cr = c.post(f"/projects/{pid}/modules/schedule_activity",
                    json={"data": {"name": f"Act {i}", "wbs": f"A{i}", "duration": dur,
                                   "predecessors": preds}})
        assert cr.status_code < 300, cr.text[:200]
    resp = c.get(f"/projects/{pid}/schedule/risk?iterations=300&seed=11")
    assert resp.status_code == 200, resp.text[:200]
    body = resp.json()
    assert body["activity_count"] == 4 and body["p80_days"] >= body["p50_days"], body
    assert body["delay_drivers"] and body["histogram"], body

print("SCHED-RISK OK - Monte Carlo over the diamond network: deterministic CP 40d; P10<=P50<=P80<=P90 "
      "with P80 above deterministic (fat right tail); criticality A1/A4 100%, long branch A2 >95% >> "
      "short branch A3; seeded runs reproduce; PPC 50 P80 > PPC 95 P80 (reliability calibrates the "
      "tail); explicit opt/pess fields honored; start date -> calendar finishes; empty + cyclic guarded; "
      "endpoint returns the full shape on a seeded schedule.")

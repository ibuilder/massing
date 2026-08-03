"""R24-PERF-BUDGET — the stated budget, asserted, and the two nobody can measure yet.

`metrics` was already built for this: the 0.1 histogram boundary is a bucket edge because 100 ms is
the budget, and `quantile` returns a bucket upper bound rather than interpolating a precise-looking
number out of bucketed data. What was missing is the assertion — per *Verify, don't recall*, a target
held only as prose is a target nobody enforces.

1. **the server budget is asserted against REAL traffic** — requests are driven through the app and
   the p95 read from the live histogram, not from a synthetic number;
2. **`quantile` returning None has two opposite causes** — no observations, or a tail beyond the
   largest bucket. Reading None as "no problem" would make the budget pass hardest exactly when
   latency is worst, so `beyond_histogram` is a FAILURE and `no_observations` is not a pass either;
3. **the two client-side budgets are reported as `unmeasured`, not omitted.** A budget file that
   lists three and quietly checks one is how a green suite comes to imply more than it tested.

Run: PYTHONPATH="src;../data/src" ./.venv/Scripts/python.exe test_perf_budget.py
"""
import os
import sys

sys.path.insert(0, "src")

os.environ["DATABASE_URL"] = "sqlite:///./test_perf_budget.db"
os.environ["STORAGE_DIR"] = "./test_storage_perf"
os.environ.pop("AEC_RBAC", None)
for _f in ("./test_perf_budget.db",):
    if os.path.exists(_f):
        os.remove(_f)

from fastapi.testclient import TestClient  # noqa: E402

from aec_api import metrics  # noqa: E402
from aec_api import perf_budget as pb  # noqa: E402
from aec_api.main import app  # noqa: E402

FAILED: list[str] = []


def check(label, ok, detail=""):
    print(f"{'PASS' if ok else 'FAIL'}  {label}{(' — ' + str(detail)) if detail and not ok else ''}")
    if not ok:
        FAILED.append(label)


# --- 3. EVERY STATED BUDGET IS DECLARED, MEASURABLE OR NOT ------------------------------------------
check("all three stated budgets are declared",
      set(pb.BUDGETS) == {"request_p95", "click_echo", "panel_load"}, sorted(pb.BUDGETS))
check("  the stated limits are 100 ms / 100 ms / 1 s",
      [pb.BUDGETS[k]["limit_s"] for k in ("request_p95", "click_echo", "panel_load")]
      == [0.1, 0.1, 1.0], {k: v["limit_s"] for k, v in pb.BUDGETS.items()})
check("  exactly ONE is server-measurable",
      [k for k, v in pb.BUDGETS.items() if v["measurable"]] == ["request_p95"],
      [k for k, v in pb.BUDGETS.items() if v["measurable"]])
check("  and the two client-side ones say WHY nothing measures them",
      all(pb.BUDGETS[k].get("why_unmeasured") for k in ("click_echo", "panel_load")))
check("  the 100 ms budget is a histogram BUCKET EDGE, so the reading is not an interpolation",
      0.1 in metrics._BUCKETS, metrics._BUCKETS)

# --- 2. None HAS TWO OPPOSITE CAUSES ------------------------------------------------------------------
none_idle = pb.evaluate(None, observations=0)
check("None with NO observations is 'no_observations', not a pass",
      none_idle["status"] == pb.STATUS_NO_DATA and none_idle["within"] is None, none_idle)
check("  and says a budget passing on an idle server measures uptime, not latency",
      "measures uptime, not latency" in none_idle["note"])
none_slow = pb.evaluate(None, observations=500)
check("NONE WITH OBSERVATIONS IS A FAILURE — the tail is beyond the histogram",
      none_slow["status"] == pb.STATUS_BEYOND_BUCKETS and none_slow["within"] is False, none_slow)
check("  naming the trap: None read as 'no problem' passes hardest when latency is worst",
      "hardest exactly when latency is worst" in none_slow["note"])
check("a p95 over budget is EXCEEDED",
      pb.evaluate(0.25, 100)["status"] == pb.STATUS_EXCEEDED)
check("  and one at the boundary is within it",
      pb.evaluate(0.1, 100)["within"] is True, pb.evaluate(0.1, 100))

# --- 1. THE SERVER BUDGET, AGAINST REAL TRAFFIC --------------------------------------------------------
with TestClient(app) as c:
    c.headers.update({"X-User": "perf@test"})
    for _ in range(40):
        c.get("/health")
    for _ in range(10):
        c.get("/capabilities")

    obs = metrics._hist_inf
    p95 = metrics.quantile(0.95)

check("real traffic was observed by the histogram", obs >= 50, obs)
check("  quantile returns a reading rather than None", p95 is not None, p95)
verdict = pb.evaluate(p95, obs)
check("SERVER REQUEST p95 IS WITHIN THE 100 ms BUDGET",
      verdict["within"] is True, {"p95_s": p95, "limit_s": 0.1, "observations": obs})
check("  judged from the LIVE histogram, not a supplied number",
      verdict["p95_s"] == p95 and verdict["observations"] == obs, verdict)

rep = pb.report(p95, obs)
check("the report lists all three budgets", len(rep["budgets"]) == 3, len(rep["budgets"]))
check("  one measured, two unmeasured", (rep["measured_count"], rep["unmeasured_count"]) == (1, 2),
      (rep["measured_count"], rep["unmeasured_count"]))
check("  the unmeasured two are NAMED, not omitted",
      {b["budget"] for b in rep["budgets"] if b["status"] == pb.STATUS_UNMEASURED}
      == {"click_echo", "panel_load"},
      [b["budget"] for b in rep["budgets"]])
check("  and the report says a green result must not read as 'all three verified'",
      "imply more than it tested" in rep["note"])
check("within_budget reflects only the measured one, honestly",
      rep["within_budget"] is True, rep["within_budget"])

for _f in ("./test_perf_budget.db",):
    if os.path.exists(_f):
        try:
            os.remove(_f)
        except OSError:
            pass

print()
if FAILED:
    print(f"perf_budget: {len(FAILED)} FAILED — {FAILED}")
    sys.exit(1)
print("perf_budget: all checks passed")

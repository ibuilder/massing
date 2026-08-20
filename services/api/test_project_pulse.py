"""Pulse mapping is a server fact. No FastAPI / DB required for the mappers.

Run: PYTHONPATH=src:../data/src python test_project_pulse.py
"""
import sys

sys.path.insert(0, "src")

from aec_api.project_pulse import (  # noqa: E402
    from_cost,
    from_deal,
    from_model,
    from_schedule,
    from_work,
)

FAILED = []


def check(label, ok, detail=""):
    print(f"{'PASS' if ok else 'FAIL'}  {label}" + (f"   {detail}" if detail else ""))
    if not ok:
        FAILED.append(label)


check("no score → no model card", from_model({"band": "watch"}) is None)
check("overall_score maps to Pulse score",
      from_model({"overall_score": 82, "lenses": [{"key": "hygiene", "issues": 12, "status": "warn"}]})
      == {"score": 82.0, "issues": 12, "blocking": None})
check("poor lens headline is blocking",
      from_model({"overall_score": 40, "lenses": [
          {"key": "readiness", "status": "poor", "headline": "2 checks to fix"}]})["blocking"]
      == "2 checks to fix")

check("budget 100 / over-under +0.7 → variance −0.7%",
      from_cost({"budget": 100, "projected_over_under": 0.7}) == {"variancePct": -0.7})
check("zero budget is not a confident 0%", from_cost({"budget": 0, "projected_over_under": 0}) is None)

check("avg slip 2 days is −2 d of float",
      from_schedule({"summary": {"avg_finish_var": 2},
                     "activities": [{"status": "slipped", "ref": "A-12"}]})
      == {"floatDays": -2.0, "atRisk": "A-12"})
check("no baseline payload → no schedule card", from_schedule(None) is None)

check("work total is open+mine",
      from_work({"total": 4, "buckets": [
          {"key": "overdue", "items": [{"ref": "RFI-118"}, {"ref": "SUB-2"}]}]})
      == {"open": 4, "mine": 4, "overdue": ["RFI-118", "SUB-2"]})

check("IRR fraction becomes percent",
      from_deal(0.182, {"suggestion_clears_horizon": True})
      == {"irrPct": 18.2, "reserveSuggestionFails": False, "nothingRenovated": None})
check("clears is False only — not missing",
      from_deal(0.12, {}) == {"irrPct": 12.0, "reserveSuggestionFails": None, "nothingRenovated": None})
check("clears False is a failing suggestion",
      from_deal(0.12, {"suggestion_clears_horizon": False})["reserveSuggestionFails"] is True)
check("no IRR → no deal card even with a failing reserve",
      from_deal(None, {"suggestion_clears_horizon": False}) is None)

print()
if FAILED:
    print("FAILED:", ", ".join(FAILED))
    sys.exit(1)
print("test_project_pulse OK")

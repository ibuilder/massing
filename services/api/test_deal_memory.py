"""R35-DEAL-MEMORY — the operator's own closed projects as comps, and the comp it refuses to invent.

The premise-check that shaped this: the roadmap asks for *exit cap achieved vs assumed* and *actual
lease-up months*. **Neither is recorded anywhere in this system** — no disposition record, no
lease-up actual. What IS recorded is cost (budget vs actual, from commitments and invoices) and
schedule (finish vs actual_finish).

So the assertions are about the circularity that would otherwise be irresistible:

1. **"realised" must come from a different record than "assumed".** The only exit cap in the system
   is the ASSUMED one on a scenario. Reading it back as the realised value would compare a number to
   itself and report perfect underwriting accuracy forever — and that figure would then justify the
   next deal. Reported as `no_recorded_source`, naming what would have to be captured, never computed;
2. **a project with no actual spend is not a project with zero variance.** Averaging it in as 0%
   drags every distribution toward "we were exactly right", which is the most flattering artefact
   available and the one nobody would question. Excluded and counted;
3. **a sample floor** — under MIN_SAMPLES a distribution is noise wearing a percentage sign;
4. **`beside` is a comparison, not a verdict** — it says where a number sits in the firm's own
   history, and refuses to place it at all when there is no history.

Run: PYTHONPATH="src;../data/src" ./.venv/Scripts/python.exe test_deal_memory.py
"""
import sys

sys.path.insert(0, "src")

from aec_api.deal_memory import (  # noqa: E402
    MIN_SAMPLES,
    STATUS_INSUFFICIENT,
    STATUS_NO_SOURCE,
    STATUS_OK,
    UNSOURCED,
    beside,
    distribution,
)

FAILED: list[str] = []


def check(label, ok, detail=""):
    print(f"{'PASS' if ok else 'FAIL'}  {label}{(' — ' + str(detail)) if detail and not ok else ''}")
    if not ok:
        FAILED.append(label)


# --- 3. THE SAMPLE FLOOR ---------------------------------------------------------------------------
few = distribution([1.0, 2.0, 3.0])
check("under the floor, no distribution is emitted",
      few["status"] == STATUS_INSUFFICIENT and few["median"] is None, few)
check("  and it says how many more closed projects it needs",
      few["needed"] == MIN_SAMPLES - 3, few)
check("  stating that nothing was substituted", "No default is substituted" in few["note"])

enough = distribution([0.0, 5.0, 10.0, 15.0, 20.0])
check("at the floor a distribution IS emitted", enough["status"] == STATUS_OK, enough)
check("  median is the middle observation", enough["median"] == 10.0, enough)
check("  with an interquartile range, not just a mean",
      enough["p25"] == 5.0 and enough["p75"] == 15.0, enough)
check("  and the extremes, so an outlier is visible",
      enough["min"] == 0.0 and enough["max"] == 20.0, enough)
check("a single observation does not crash the quantiles",
      distribution([7.0], min_samples=1)["median"] == 7.0)

# --- 1. THE CIRCULARITY REFUSAL — the reason this module exists -------------------------------------
from aec_api import deal_memory as dm  # noqa: E402

fake = {"metrics": {k: {"status": STATUS_NO_SOURCE, "note": v} for k, v in UNSOURCED.items()}}
check("EXIT CAP ACHIEVED IS NOT COMPUTED — it has no recorded source",
      fake["metrics"]["exit_cap_achieved"]["status"] == STATUS_NO_SOURCE)
check("  and the reason names the circularity explicitly",
      "compare a number to itself" in UNSOURCED["exit_cap_achieved"],
      UNSOURCED["exit_cap_achieved"])
check("  it also names what would have to be captured to make it real",
      "disposition record" in UNSOURCED["exit_cap_achieved"])
check("LEASE-UP MONTHS is refused too, distinguishing forecast from observation",
      "forecasts, not observations" in UNSOURCED["lease_up_months"])
check("  asking for it returns the refusal rather than a number",
      beside("exit_cap_achieved", 0.055, fake)["comparison"] is None
      and beside("exit_cap_achieved", 0.055, fake)["status"] == STATUS_NO_SOURCE,
      beside("exit_cap_achieved", 0.055, fake))
check("the unsourced metrics are NAMED in the output, not silently omitted",
      set(UNSOURCED) == {"exit_cap_achieved", "lease_up_months"}, sorted(UNSOURCED))

# --- 4. `beside` IS A COMPARISON, NOT A VERDICT ------------------------------------------------------
mem = {"metrics": {"cost_variance_pct": distribution([0.0, 5.0, 10.0, 15.0, 20.0])}}
b = beside("cost_variance_pct", 12.0, mem)
check("a value inside the IQR is reported as within_iqr", b["position"] == "within_iqr", b)
check("  with the firm's own median and quartiles beside it",
      (b["median"], b["p25"], b["p75"]) == (10.0, 5.0, 15.0), b)
check("  and it says it is a comparison, NOT a verdict",
      "not a verdict" in b["note"], b["note"])
check("a value below the lower quartile is placed, not graded",
      beside("cost_variance_pct", 1.0, mem)["position"] == "below_p25")
check("a value above the upper quartile likewise",
      beside("cost_variance_pct", 99.0, mem)["position"] == "above_p75")

thin = {"metrics": {"cost_variance_pct": distribution([1.0, 2.0])}}
check("with too little history it REFUSES to place the number at all",
      beside("cost_variance_pct", 12.0, thin)["comparison"] is None
      and beside("cost_variance_pct", 12.0, thin)["status"] == STATUS_INSUFFICIENT,
      beside("cost_variance_pct", 12.0, thin))
check("an unknown metric names the ones that exist rather than returning nothing",
      beside("made_up", 1, mem)["status"] == "unknown_metric"
      and "cost_variance_pct" in beside("made_up", 1, mem)["known"])
for bad in (None, "", "abc", True, float("inf")):
    check(f"entering {bad!r} is not coerced into a comparison",
          beside("cost_variance_pct", bad, mem)["status"] == "not_a_number",
          beside("cost_variance_pct", bad, mem))

# --- 2. A PROJECT WITH NO ACTUALS IS NOT A PROJECT WITH ZERO VARIANCE --------------------------------
# Exercised against the real engine over a DB below; asserted here on the arithmetic that decides it.
# Driven through the REAL engine against a real DB. Asserting this on arithmetic (or by grepping the
# source for a comment) would not reach the failure: the whole question is what `comps` DOES with a
# project that has no actual spend, and only calling it can answer that.
import os  # noqa: E402

os.environ["DATABASE_URL"] = "sqlite:///./test_deal_memory.db"
os.environ["STORAGE_DIR"] = "./test_storage_deal_memory"
os.environ.pop("AEC_RBAC", None)
for _f in ("./test_deal_memory.db",):
    if os.path.exists(_f):
        os.remove(_f)

from aec_api import cost as cost_engine  # noqa: E402
from aec_api.db import Base, SessionLocal, engine  # noqa: E402
from aec_api.models import Project  # noqa: E402

Base.metadata.create_all(engine)

# five built projects (real actuals) + two never built (no actual spend)
_FIXTURE = {f"built{i}": {"budget": 100.0, "actual": 100.0 + i * 5} for i in range(5)}
_FIXTURE.update({f"unbuilt{i}": {"budget": 100.0, "actual": 0.0} for i in range(2)})

with SessionLocal() as _db:
    for pid in _FIXTURE:
        _db.add(Project(id=pid, name=pid))
    _db.commit()

_real_summary = cost_engine.summary
cost_engine.summary = lambda db, pid: _FIXTURE.get(pid, {})   # noqa: E731 — focused seam
try:
    with SessionLocal() as _db:
        c = dm.comps(_db, min_samples=MIN_SAMPLES)
finally:
    cost_engine.summary = _real_summary

check("comps sees every project", c["project_count"] == 7, c["project_count"])
check("A PROJECT WITH NO ACTUAL SPEND IS EXCLUDED, not counted as 0% variance",
      c["excluded_count"] == 2 and {e["reason"] for e in c["excluded"]} == {"no_actual_cost"},
      c["excluded"])
cv = c["metrics"]["cost_variance_pct"]
check("  so the distribution is built from the five BUILT projects only",
      cv["status"] == STATUS_OK and cv["count"] == 5, cv)
check("  and its median is the real overrun (0/5/10/15/20 -> 10%), not dragged toward zero",
      cv["median"] == 10.0, cv)
check("  which it WOULD have been had the unbuilt two counted as zero",
      sorted([0.0, 5.0, 10.0, 15.0, 20.0, 0.0, 0.0])[3] == 5.0)
check("the unsourced metrics survive into the real output",
      c["metrics"]["exit_cap_achieved"]["status"] == STATUS_NO_SOURCE
      and c["metrics"]["lease_up_months"]["status"] == STATUS_NO_SOURCE,
      list(c["metrics"]))
check("cost_per_sf reports insufficient history when no project has a GFA",
      c["metrics"]["cost_per_sf"]["status"] == STATUS_INSUFFICIENT, c["metrics"]["cost_per_sf"])
check("  rather than dividing by a guessed area", c["metrics"]["cost_per_sf"]["median"] is None)

# Dispose the pool before unlinking: on Windows SQLite still holds the file through the engine's
# open connections, and os.remove raises WinError 32 rather than leaving a tidy directory.
engine.dispose()
for _f in ("./test_deal_memory.db",):
    if os.path.exists(_f):
        try:
            os.remove(_f)
        except OSError:                          # a leftover file is untidy, never a test failure
            pass

print()
if FAILED:
    print(f"deal_memory: {len(FAILED)} FAILED — {FAILED}")
    sys.exit(1)
print("deal_memory: all checks passed")

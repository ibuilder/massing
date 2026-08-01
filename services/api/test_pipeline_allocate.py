"""R31-PIPELINE-ALLOCATE — constrained capital allocated ACROSS the pipeline.

The load-bearing assertions are the ones a plausible-but-wrong allocator would fail:

1. **the crowding-out case** — greedy takes the best ratio and loses; if the optimum never beats greedy
   here, this module has no reason to exist;
2. **no fractional funding** — you cannot fund 60% of a building, so the solve is integer and the
   answer is never a relaxed LP wearing an optimiser's authority;
3. **absence is reported, never filled** — no solver, no convergence, or no stated value each produce a
   refusal rather than a number;
4. **the output is auditable** — what was displaced, by what, and the slack.

Run: PYTHONPATH="src;../data/src" ./.venv/Scripts/python.exe test_pipeline_allocate.py
"""
import sys

sys.path.insert(0, "src")

from aec_api.pipeline_allocate import (  # noqa: E402
    STATUS_NOTHING_FEASIBLE,
    STATUS_OK,
    STATUS_UNAVAILABLE,
    allocate,
    greedy,
)

FAILED: list[str] = []


def check(label, ok, detail=""):
    print(f"{'PASS' if ok else 'FAIL'}  {label}{(' — ' + str(detail)) if detail and not ok else ''}")
    if not ok:
        FAILED.append(label)


def C(cid, cost, value):
    return {"id": cid, "name": cid, "cost": cost, "value": value}


# --- 1. THE CROWDING-OUT CASE — the reason this module exists ------------------------------------
# Budget 100.
#   big  cost 60, value 66  -> ratio 1.10  (BEST ratio, so greedy takes it first)
#   a    cost 50, value 54  -> ratio 1.08
#   b    cost 50, value 54  -> ratio 1.08
# Greedy takes `big` (60 spent), then neither a nor b fits in the remaining 40. It stops at 66.
# The optimum skips the best-ratio item entirely and takes a+b: 100 spent, 108 value.
# This is precisely what `fca.portfolio`'s "fund those first" note would get wrong.
#
# The first version of this fixture had the ratios INVERTED (a/b at 1.10 beating big at 1.05), so
# greedy and the optimum agreed and the comparison proved nothing. The module's own self-check —
# "a difference of zero means the inputs lack the shape" — is what caught it.
CROWD = [C("big", 60.0, 66.0), C("a", 50.0, 54.0), C("b", 50.0, 54.0)]
r = allocate(CROWD, 100.0)
check("an optimal allocation is produced", r["status"] == STATUS_OK, r["status"])
ids = sorted(s["id"] for s in r["selected"])
check("the optimiser takes the PAIR, not the best single ratio", ids == ["a", "b"], ids)
check("  total value is the higher one", r["total_value"] == 108.0, r["total_value"])
check("  and it spends the budget exactly", r["total_cost"] == 100.0 and r["slack"] == 0.0, r)

g = r["greedy"]
check("greedy is reported alongside, and it chose differently",
      g["selected"] == ["big"], g["selected"])
check("  greedy's value is lower", g["value"] == 66.0, g["value"])
check("  and the difference is stated as value forgone", g["value_forgone"] == 42.0, g)
check("THE SELF-CHECK: the optimum beats greedy on this fixture — a zero difference here would mean "
      "the test lacks the shape, not that the solver works", r["total_value"] > g["value"])

# --- 2. NO FRACTIONAL FUNDING -----------------------------------------------------------------------
# An LP relaxation of this funds 2/3 of `x` and reports 100 value from a 100 budget. The integer
# answer is 1 unit of `y` (value 90) with 10 slack, and 90 < 100 is the whole point.
FRAC = [C("x", 150.0, 150.0), C("y", 90.0, 90.0)]
f = allocate(FRAC, 100.0)
check("nothing is part-funded — a project is in or out",
      all(float(s["cost"]).is_integer() or True for s in f["selected"])
      and [s["id"] for s in f["selected"]] == ["y"], f["selected"])
check("  the too-large project is NAMED as never fundable, not silently dropped",
      f["never_fundable"] and f["never_fundable"][0]["id"] == "x", f["never_fundable"])
check("  with how far over it was", f["never_fundable"][0]["over_by"] == 50.0, f["never_fundable"])
check("  and the leftover capital is reported rather than hidden", f["slack"] == 10.0, f["slack"])

# --- 3. ABSENCE IS REPORTED, NEVER FILLED -------------------------------------------------------------
# A missing value defaulted to 0 silently guarantees a project is never funded — a decision made by a
# `.get()` rather than by a committee.
miss = allocate([C("ok", 10.0, 20.0), {"id": "novalue", "cost": 10.0}], 100.0)
check("a candidate with no stated value is REFUSED, not defaulted to zero",
      [x["id"] for x in miss["refused"]] == ["novalue"], miss["refused"])
check("  and the refusal says why", "assumed zero" in miss["refused"][0]["reason"],
      miss["refused"][0]["reason"])
check("  the refused candidate does not appear in the selection",
      [s["id"] for s in miss["selected"]] == ["ok"], miss["selected"])

for bad, why in ((True, "JSON true is not a cost of 1"),
                 ("lots", "a word is not a cost"),
                 (float("inf"), "infinite cost is not a measurement"),
                 (-5, "a negative cost is not a quantity")):
    b = allocate([{"id": "bad", "cost": bad, "value": 10.0}], 100.0)
    check(f"cost={bad!r} is refused — {why}", [x["id"] for x in b["refused"]] == ["bad"], b["refused"])

# --- 4. nothing fits ------------------------------------------------------------------------------------
none_fit = allocate([C("huge", 500.0, 900.0)], 100.0)
check("when nothing fits, the status says so", none_fit["status"] == STATUS_NOTHING_FEASIBLE,
      none_fit["status"])
check("  and it is not reported as a successful empty allocation",
      none_fit["selected"] == [] and none_fit["total_value"] == 0.0, none_fit)
check("  the whole budget is reported as slack", none_fit["slack"] == 100.0, none_fit["slack"])

check("a zero budget funds nothing and says nothing was feasible",
      allocate([C("a", 1.0, 1.0)], 0.0)["status"] == STATUS_NOTHING_FEASIBLE)
check("an empty pipeline is nothing-feasible, not an error",
      allocate([], 100.0)["status"] == STATUS_NOTHING_FEASIBLE)

for bad in (-1, float("nan"), "abc", None, True):
    try:
        allocate([C("a", 1.0, 1.0)], bad)
        check(f"an unusable capital ({bad!r}) is refused", False, "accepted it")
    except ValueError:
        check(f"an unusable capital ({bad!r}) raises rather than allocating against nonsense", True)

# --- 5. the output is AUDITABLE ---------------------------------------------------------------------------
d = {x["id"]: x for x in r["displaced"]}
check("what was displaced is named", "big" in d, sorted(d))
check("  with its cost and value, not just an id",
      d["big"]["cost"] == 60.0 and d["big"]["value"] == 66.0, d["big"])
check("  and a reason a committee can read", "displacing" in d["big"]["reason"]
      or "not fit" in d["big"]["reason"], d["big"]["reason"])
check("every status used is documented in the payload", r["status"] in r["status_meaning"])
check("  and `unavailable` is documented as an ABSENT answer, not a recommendation",
      "not a recommendation" in r["status_meaning"][STATUS_UNAVAILABLE])

# --- 6. greedy() is honest on its own ----------------------------------------------------------------------
gg = greedy([C("a", 50.0, 54.0), C("b", 50.0, 54.0), C("big", 60.0, 66.0)], 100.0)
check("greedy ranks by value-per-cost and fills", gg["selected"] == ["big"], gg["selected"])
check("a free item is always taken — zero cost cannot crowd anything out",
      "free" in greedy([C("free", 0.0, 5.0), C("a", 100.0, 90.0)], 100.0)["selected"])

# --- 7. ties and duplicates do not corrupt the sum -----------------------------------------------------------
dup = allocate([C("a", 25.0, 30.0), C("a2", 25.0, 30.0), C("a3", 25.0, 30.0), C("a4", 25.0, 30.0)], 75.0)
check("with identical candidates it funds as many as fit, and no more",
      len(dup["selected"]) == 3 and dup["total_cost"] == 75.0, dup["total_cost"])
check("  the total value is the sum of the selected, not of all candidates",
      dup["total_value"] == 90.0, dup["total_value"])

print()
if FAILED:
    print(f"pipeline_allocate: {len(FAILED)} FAILED — {FAILED}")
    sys.exit(1)
print("pipeline_allocate: all checks passed")

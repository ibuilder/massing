"""R22-PIPELINE — the acquisition funnel, and the four numbers it refuses to invent.

A weighted pipeline value is the most dangerous number in the product: it is a guess about
conversion, multiplied by real money, summed over dozens of deals, and read as a forecast. These
assertions are about the places where this engine declines to produce one:

1. **stage probabilities are derived, never defaulted.** Under the sample floor a stage reports
   `insufficient_history` and its deals are EXCLUDED from the weighted total and counted — an
   excluded number is visibly incomplete, a defaulted one is invisibly wrong;
2. **where a deal died is recoverable.** `workflow_state` becomes `dead`, destroying the stage it
   reached; the transition log is the only honest source and the engine reads it;
3. **cycle time is right-censored** — the slow deals are the open ones, so closed-only means
   understate, and the two populations are never blended;
4. **a missing value is not zero** and a clean win record is a data-quality warning, not a triumph.

Run: PYTHONPATH="src;../data/src" ./.venv/Scripts/python.exe test_deal_funnel.py
"""
import sys
from datetime import date

sys.path.insert(0, "src")

from aec_api.deal_funnel import (  # noqa: E402
    MIN_CLOSED_SAMPLES,
    STAGES,
    STATUS_INSUFFICIENT,
    STATUS_OK,
    cycle_times,
    data_quality,
    funnel,
    furthest_stage,
    stage_conversion,
    weighted_value,
)

FAILED: list[str] = []


def check(label, ok, detail=""):
    print(f"{'PASS' if ok else 'FAIL'}  {label}{(' — ' + str(detail)) if detail and not ok else ''}")
    if not ok:
        FAILED.append(label)


def deal(did, state, price=None, sourced=None, closed=None):
    data = {}
    if price is not None:
        data["purchase_price"] = price
    if sourced:
        data["sourced_on"] = sourced
    if closed:
        data["closed_on"] = closed
    return {"id": did, "ref": f"DEAL-{did}", "workflow_state": state, "data": data}


def hist(*pairs):
    return [{"from": a, "to": b} for a, b in pairs]


# --- the book -------------------------------------------------------------------------------------
# 6 deals died in screening, 4 closed. That gives >= MIN_CLOSED_SAMPLES at screening (so a rate is
# derived) and only 4 at underwriting (so it is refused) — both branches from one fixture.
DEALS, HISTORY = [], {}
for i in range(6):
    d = deal(f"dead{i}", "dead", price=500_000, sourced="2026-01-01", closed="2026-02-01")
    DEALS.append(d)
    HISTORY[d["id"]] = hist(("sourced", "screening"), ("screening", "dead"))
for i in range(4):
    d = deal(f"won{i}", "won", price=1_000_000, sourced="2026-01-01", closed="2026-06-30")
    DEALS.append(d)
    HISTORY[d["id"]] = hist(("sourced", "screening"), ("screening", "underwriting"),
                            ("underwriting", "loi"), ("loi", "due_diligence"),
                            ("due_diligence", "closing"), ("closing", "won"))

# --- 2. WHERE A DEAL DIED IS RECOVERABLE ----------------------------------------------------------
check("a dead deal's workflow_state alone loses the stage it reached",
      DEALS[0]["workflow_state"] == "dead" and furthest_stage(DEALS[0], None) is None,
      furthest_stage(DEALS[0], None))
check("  the transition log recovers it — died in SCREENING",
      furthest_stage(DEALS[0], HISTORY["dead0"]) == "screening",
      furthest_stage(DEALS[0], HISTORY["dead0"]))
check("  and a won deal is credited with reaching CLOSING, not just 'won'",
      furthest_stage(DEALS[-1], HISTORY["won0"]) == "closing",
      furthest_stage(DEALS[-1], HISTORY["won0"]))

# --- 1. DERIVED, NEVER DEFAULTED ------------------------------------------------------------------
CONV = stage_conversion(DEALS, HISTORY)
check("screening has enough closed history — a rate is DERIVED",
      CONV["screening"]["status"] == STATUS_OK, CONV["screening"])
check("  and it is this firm's own number: 4 of 10 that reached screening closed",
      CONV["screening"]["probability"] == 0.4 and CONV["screening"]["closed_samples"] == 10,
      CONV["screening"])
check("underwriting has only 4 closed samples — REFUSED, not defaulted",
      CONV["underwriting"]["status"] == STATUS_INSUFFICIENT
      and CONV["underwriting"]["probability"] is None, CONV["underwriting"])
check("  and it says how many more closures it needs",
      CONV["underwriting"]["needed"] == MIN_CLOSED_SAMPLES - 4, CONV["underwriting"])
check("  no textbook ladder appears anywhere — every stage is derived or None",
      all(s["probability"] is None or s["status"] == STATUS_OK for s in CONV.values()))
check("  a deal counts toward every stage it PASSED THROUGH, not just its last",
      CONV["sourced"]["closed_samples"] == 10, CONV["sourced"])

# --- 4. A MISSING VALUE IS NOT ZERO ---------------------------------------------------------------
LIVE = [deal("live1", "screening", price=1_000_000),      # weightable: screening has a rate
        deal("live2", "underwriting", price=2_000_000),   # excluded: no derived rate
        deal("live3", "screening")]                       # excluded: no value at all
W = weighted_value(LIVE, CONV)
check("only the deal in a stage with real history is weighted (1M x 0.4)",
      W["weighted_value"] == 400_000.0 and W["deals_weighted"] == 1, W)
check("  the insufficient-history deal is EXCLUDED and named, not weighted by a guess",
      any(e["reason"] == STATUS_INSUFFICIENT and e["id"] == "live2" for e in W["excluded"]),
      W["excluded"])
check("  the valueless deal is EXCLUDED, never summed as zero",
      any(e["reason"] == "no_value" and e["id"] == "live3" for e in W["excluded"]), W["excluded"])
check("  COVERAGE says how much of the book the headline actually covers (1 of 3)",
      W["coverage"] == round(1 / 3, 4), W["coverage"])
check("  and the excluded value is stated, so the gap is a number not an absence",
      W["excluded_value"] == 2_000_000.0, W["excluded_value"])
check("  with a note saying a partial number beats a guessed one",
      "rather than weighted by a default" in W["note"], W["note"])

# A funnel with NO closed history at all must weight nothing — the cold-start case, where a default
# ladder would confidently value an entire book that has never closed a single deal.
COLD = stage_conversion(LIVE, {})
cold_w = weighted_value(LIVE, COLD)
check("A BRAND-NEW FIRM'S PIPELINE WEIGHTS TO ZERO, not to a textbook number",
      cold_w["weighted_value"] == 0.0 and cold_w["deals_weighted"] == 0, cold_w)
check("  and coverage reports 0.0 rather than pretending the book was valued",
      cold_w["coverage"] == 0.0, cold_w["coverage"])

# --- 3. CYCLE TIME IS RIGHT-CENSORED --------------------------------------------------------------
CT = cycle_times(DEALS + [deal("slow", "due_diligence", sourced="2025-01-01")],
                 as_of=date(2026, 8, 2))
check("closed cycle time is reported", CT["closed"]["count"] == 10, CT["closed"])
check("  open deals are counted SEPARATELY, not as closed", CT["open_age"]["count"] == 1,
      CT["open_age"])
check("  the long-running open deal is not folded into the closed mean",
      CT["closed"]["mean_days"] < CT["open_age"]["mean_days"], CT)
check("  and NO blended figure is offered at all", CT["blended"] is None)
check("  with the censoring stated in words",
      "understates" in CT["note"], CT["note"])

# --- 4b. DATA-QUALITY TELLS -----------------------------------------------------------------------
ALL_WON = [deal(f"w{i}", "won", price=1_000, sourced="2026-01-01", closed="2026-02-01")
           for i in range(6)]
codes = {w["code"] for w in data_quality(ALL_WON)}
check("a 100% win rate is flagged as MISSING LOSSES, not celebrated",
      "no_losses_recorded" in codes, codes)
check("  the real book, which records losses, is NOT flagged",
      "no_losses_recorded" not in {w["code"] for w in data_quality(DEALS)},
      [w["code"] for w in data_quality(DEALS)])
check("in-flight deals with no price are reported as a data gap",
      "deals_without_value" in {w["code"] for w in data_quality(LIVE)},
      [w["code"] for w in data_quality(LIVE)])

# --- malformed input is refused, never coerced -----------------------------------------------------
for bad in (None, "", "  ", "not-a-number", True, float("inf"), float("nan")):
    d = deal("bad", "screening", price=bad)
    ww = weighted_value([d], CONV)
    check(f"purchase_price={bad!r} is excluded as no_value, not coerced",
          ww["deals_weighted"] == 0 and ww["excluded"][0]["reason"] == "no_value", ww)
check("a deal in an unknown state is neither in-flight nor terminal",
      weighted_value([deal("x", "banana", price=9)], CONV)["deals_in_flight"] == 0)
check("an empty book yields coverage None rather than a divide-by-zero",
      weighted_value([], CONV)["coverage"] is None)

# --- the whole funnel ------------------------------------------------------------------------------
F = funnel(DEALS + LIVE, HISTORY, as_of=date(2026, 8, 2))
check("funnel counts every stage including terminals",
      F["by_stage"]["dead"]["count"] == 6 and F["by_stage"]["won"]["count"] == 4
      and F["by_stage"]["screening"]["count"] == 2, F["by_stage"])
check("  stage value sums only the deals that HAVE a value",
      F["by_stage"]["screening"]["value"] == 1_000_000.0
      and F["by_stage"]["screening"]["deals_with_value"] == 1, F["by_stage"]["screening"])
check("  the stage order is the funnel order", F["stages"] == STAGES, F["stages"])
check("  and it carries its conversion, weighting, cycle time and warnings together",
      all(k in F for k in ("conversion", "weighted", "cycle_time", "warnings")), list(F))

print()
if FAILED:
    print(f"deal_funnel: {len(FAILED)} FAILED — {FAILED}")
    sys.exit(1)
print("deal_funnel: all checks passed")

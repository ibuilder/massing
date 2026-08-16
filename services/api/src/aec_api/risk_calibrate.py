"""R27-RISK-CALIBRATE — the spread comes from this project's own history, not from a guess.

`schedule_risk_mc.risk` runs Monte Carlo over the CPM network and reports P10/P50/P80/P90.
(It was "schedule_risk.simulate" until v0.3.972, when that second simulator was deleted — the
name is in plain quotes because backticks are reserved here for files that exist.)
The *shape* has never been the problem. What it multiplies is: durations come from caller-supplied
optimistic / likely / pessimistic estimates, which on most projects is one person's opinion entered
three times. Percentiles computed from that are precise about an opinion and say nothing about risk.

The industry answer is calibration against a large corpus of historical schedules. We will never have
one offline, and pretending otherwise would be the same overclaim this codebase keeps refusing. **But
the project has its own history**: `schedule_activity` carries planned `start`/`finish` beside
`actual_start`/`actual_finish`, so every finished activity is a measured planned-vs-actual ratio. A
hundred of those from *this* job, by *these* trades, is worth more than a general prior anyway.

**Three refusals make it honest.**

*An activity that has started but not finished is NOT a data point.* It has an `actual_start` and no
`actual_finish`, so its measured duration is however far it has got — always shorter than the truth.
Including in-progress work would drag every ratio downward and produce a schedule risk that
systematically flatters the project, which is the exact direction that gets people hurt. Same family
of error as writing half a date range.

*`n` is reported, and too small means fall back.* A ratio distribution from three activities is
noise wearing a decimal point. Below `MIN_SAMPLES` the group falls back — trade → project → the
caller's three-point estimate — and the result **names which rung it landed on**. A number whose
provenance is invisible cannot be argued with, and this one should be.

*It never invents an optimistic case.* The observed minimum ratio is the optimistic bound, not some
fraction below it. Manufacturing a best case nobody has ever achieved on this job is how a forecast
becomes a wish.
"""
from __future__ import annotations

from datetime import date, datetime
from typing import Any

#: Completed activities a group needs before its own spread is used. Below this the sample is noise:
#: three activities produce a range, not a distribution, and dressing it as one is the failure this
#: module exists to avoid.
MIN_SAMPLES = 5

#: Ratios beyond this are treated as data errors rather than risk. An activity recorded as taking 40×
#: its plan is a typo or a re-baselined scope, and letting it into the distribution would swamp every
#: honest observation. Excluded ones are REPORTED, never dropped silently.
MAX_RATIO = 10.0

#: ...and the SAME guard on the low side, which the first version missed. `_three` takes the observed
#: MINIMUM verbatim as the optimistic bound, so a single typo — an actual finish equal to the actual
#: start on a 60-day activity — silently became a "best case" of 1.7% of plan, sitting in a
#: `basis="trade"` result as though five honest observations had backed it. The high guard alone left
#: the exact failure this module's own contract forbids: an optimistic case nobody has achieved.
#: Asymmetric thresholds are deliberate — finishing in a tenth of the plan is far less believable than
#: taking ten times it.
MIN_RATIO = 0.1

#: The rungs a calibration can land on, best first. Reported so the caller knows what it got.
BASES = ("trade", "project", "three-point")


def _d(v: Any) -> date | None:
    if isinstance(v, date) and not isinstance(v, datetime):
        return v
    if isinstance(v, datetime):
        return v.date()
    s = str(v or "").strip()
    if not s:
        return None
    try:
        return date.fromisoformat(s[:10])
    except ValueError:
        return None


def _days(a: Any, b: Any) -> float | None:
    """Inclusive duration in days, or None when either end is unreadable or the range is backwards."""
    s, f = _d(a), _d(b)
    if not s or not f:
        return None
    n = (f - s).days + 1
    return float(n) if n > 0 else None


def samples(activities: list[dict[str, Any]]) -> dict[str, Any]:
    """Measured actual÷planned duration ratios from finished activities, grouped by trade.

    Returns the ratios plus everything that was excluded and why — an activity left out of a
    calibration is a fact about the calibration, not a detail.
    """
    by_trade: dict[str, list[float]] = {}
    all_ratios: list[float] = []
    in_progress: list[str] = []
    unusable: list[dict[str, Any]] = []
    outliers: list[dict[str, Any]] = []

    for a in activities or []:
        d = a.get("data") if isinstance(a.get("data"), dict) else a
        ref = str(a.get("ref") or d.get("name") or "?")
        planned = _days(d.get("start"), d.get("finish"))
        a_start, a_finish = d.get("actual_start"), d.get("actual_finish")
        # STARTED BUT NOT FINISHED IS NOT A DATA POINT. Its measured duration is however far it has
        # got, which is always shorter than the truth, and including it would drag every ratio down
        # and flatter the schedule — the direction of error that gets people hurt.
        if _d(a_start) and not _d(a_finish):
            in_progress.append(ref)
            continue
        actual = _days(a_start, a_finish)
        if not planned or not actual:
            # NOT-YET-STARTED IS NOT A DATA PROBLEM. An activity with planned dates and no actuals is
            # simply future work, and on a live project that is most of the schedule — reporting each
            # one as "unusable" would bury the genuine data errors in noise and make the report worth
            # ignoring. Only a PARTIAL record is worth flagging: something was entered and cannot be
            # read.
            if _d(a_start) or _d(a_finish):
                unusable.append({"ref": ref, "why": "actual dates present but unreadable or "
                                                    "incomplete, or the planned range is missing"})
            continue
        ratio = actual / planned
        if ratio > MAX_RATIO or ratio < MIN_RATIO:
            why = (f"beyond {MAX_RATIO}× plan — read as a data error or a re-baselined scope, not "
                   "as risk") if ratio > MAX_RATIO else (
                   f"under {MIN_RATIO}× plan — an activity finishing in a tenth of its planned "
                   "duration is a data-entry error, and taking it as the optimistic bound would "
                   "manufacture a best case nobody achieved")
            outliers.append({"ref": ref, "ratio": round(ratio, 4), "why": why})
            continue
        trade = str(d.get("trade") or "").strip() or "(no trade)"
        by_trade.setdefault(trade, []).append(ratio)
        all_ratios.append(ratio)

    return {
        "by_trade": {k: sorted(v) for k, v in by_trade.items()},
        "all": sorted(all_ratios),
        "n": len(all_ratios),
        "in_progress": sorted(in_progress),
        "unusable": unusable,
        "outliers": outliers,
        "note": ("Only FINISHED activities contribute. An activity that has started and not finished "
                 "has a measured duration shorter than its true one, and including it would bias "
                 "every forecast optimistic."),
    }


def _three(ratios: list[float]) -> dict[str, float]:
    """Optimistic / likely / pessimistic from observed ratios.

    The optimistic bound is the observed **minimum**, not a fraction below it: manufacturing a best
    case nobody on this job has ever achieved is how a forecast becomes a wish.
    """
    s = sorted(ratios)
    n = len(s)
    mid = s[n // 2] if n % 2 else (s[n // 2 - 1] + s[n // 2]) / 2.0
    return {"optimistic": round(s[0], 4), "likely": round(mid, 4), "pessimistic": round(s[-1], 4)}


def calibrate(activities: list[dict[str, Any]], *, trade: str | None = None,
              fallback: dict[str, float] | None = None) -> dict[str, Any]:
    """A duration multiplier distribution for `trade`, drawn from this project's finished work.

    Falls back **trade → project → the caller's three-point**, and always reports which rung it used
    and how many observations backed it. A forecast whose provenance is invisible cannot be argued
    with, and this one should be.
    """
    s = samples(activities)
    key = (trade or "").strip() or "(no trade)"
    pool = s["by_trade"].get(key, [])
    if len(pool) >= MIN_SAMPLES:
        return {"basis": "trade", "trade": key, "n": len(pool), **_three(pool),
                "detail": f"calibrated from {len(pool)} finished {key} activities on this project"}
    if len(s["all"]) >= MIN_SAMPLES:
        return {"basis": "project", "trade": key, "n": len(s["all"]), **_three(s["all"]),
                "detail": (f"only {len(pool)} finished {key} activities — fewer than {MIN_SAMPLES}, "
                           f"so the project-wide spread from {len(s['all'])} activities is used "
                           "instead")}
    if fallback:
        return {"basis": "three-point", "trade": key, "n": len(s["all"]),
                "optimistic": float(fallback.get("optimistic", 1.0)),
                "likely": float(fallback.get("likely", 1.0)),
                "pessimistic": float(fallback.get("pessimistic", 1.0)),
                "detail": (f"only {len(s['all'])} finished activities on this project — too few to "
                           f"calibrate (need {MIN_SAMPLES}). The supplied three-point estimate is "
                           "used, and it is an ESTIMATE: this number carries no evidence from this "
                           "job.")}
    return {"basis": None, "trade": key, "n": len(s["all"]),
            "optimistic": None, "likely": None, "pessimistic": None,
            "detail": (f"only {len(s['all'])} finished activities and no three-point estimate "
                       "supplied — there is nothing to calibrate from and nothing to fall back on. "
                       "Refusing rather than returning 1.0, which would read as 'no risk'.")}

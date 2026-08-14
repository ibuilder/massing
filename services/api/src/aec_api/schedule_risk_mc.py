"""R45-SCHED-DEDUPE ② — Monte Carlo schedule risk on the real network.

This is the one R45 overlap that is a **true** overlap: `aec_api/schedule_risk.py` and
`massingplan/core/risk.py` both run a Monte Carlo over the schedule and both report a criticality
index. So this module follows the rule the ring settled on — *keep what is ours and distinctive, take
their engine* — rather than adding a second simulator beside the first.

## What is ours and worth keeping: PPC calibration

Our simulator widens or narrows the default pessimistic tail using the team's own Last Planner
reliability. An 80%-PPC team keeps the default; a 60%-PPC team's tail widens, because an unreliable
plan slips further, and that is exactly the calibration signal Last Planner theory says PPC carries.
The vendored engine has no such notion — and it does not need one, because it exposes
`default_estimates(tasks, optimistic_factor, pessimistic_factor)`, which is precisely the seam the
calibration belongs in. Our distinctive input, their arithmetic.

## What is theirs and materially better: the network it runs on

`schedule_risk._network` builds its own graph, and **it is FS-only, lag-free and calendar-free** —
checked, not assumed: the module contains zero occurrences of "calendar", and its node builder reads
only `predecessors`. The vendored engine simulates the same `Task`/`Link` network the CPM uses, so it
honours every relation type, every lag, and every work calendar.

**That difference produces a wrong number today, not a theoretical one.** Ours converts a duration to
a date with `start0 + timedelta(days=round(days))` — *calendar* days. `schedule_cpm` reports
*working*-day dates on a real calendar. The two appear in the same portal, and on a 200-working-day
programme they diverge by roughly eighty days. A P80 finish that counts Saturdays is not a
conservative estimate; it is a different question's answer.

Theirs also reports two things ours cannot:

* **`duration_sensitivity`** — the Pearson correlation between an activity's sampled duration and the
  project finish. Criticality index says how often an activity sat on the critical path; sensitivity
  says whether its duration actually *moves* the finish. A task can be critical in 90% of iterations
  and barely shift the date.
* **`confidence_in_deterministic`** — the share of iterations that finished on or before the CPM date,
  which is the direct answer to "how likely is the date on the programme, really?".

**Lags and constraint dates are never sampled**, only durations: a lag is a decision and a constraint
is a commitment, and sampling them makes the criticality index incomparable between iterations because
each run becomes a different plan rather than the same plan under different luck.

The seed defaults to a fixed value. A forecast that changes when nobody changed the plan is not a
forecast anyone can act on — the same reasoning as the levelling priority key.
"""
from __future__ import annotations

from typing import Any

from massingplan.core.graph import ScheduleCycleError
from massingplan.core.risk import (
    DEFAULT_OPTIMISTIC_FACTOR,
    DEFAULT_PESSIMISTIC_FACTOR,
    Distribution,
    default_estimates,
    simulate,
)

from . import schedule_engine

#: Last Planner's target reliability. At 80% PPC the default tail is kept as-is.
PPC_TARGET = 80.0


def ppc_tail_factor(ppc_pct: float | None) -> float:
    """The pessimistic factor, widened or narrowed by the team's PPC.

    Ported verbatim in spirit from `schedule_risk.simulate` so the calibration curve does not change
    while its engine does — every point of PPC below 80 widens the tail, every point above narrows it,
    clamped to [0.5, 2.0] so a wild PPC reading cannot produce a wild forecast.
    """
    if ppc_pct is None:
        return DEFAULT_PESSIMISTIC_FACTOR
    scale = max(0.5, min(2.0, 1.0 + (PPC_TARGET - float(ppc_pct)) / 50.0))
    return 1.0 + (DEFAULT_PESSIMISTIC_FACTOR - 1.0) * scale


def risk(activities: list[dict], *, iterations: int = 2000, seed: int | None = 12345,
         ppc_pct: float | None = None, distribution: str = "pert") -> dict[str, Any]:
    """Simulate the schedule and report the probabilistic finish.

    `ppc_pct` is the team's Last Planner reliability; it calibrates the **default** tail only, so a
    scheduler who supplied explicit three-point estimates is never overridden by a team-level average.
    """
    if not activities:
        return _unavailable("no activities — there is nothing to simulate")

    try:
        dist = Distribution(distribution)
    except ValueError:
        return _unavailable(
            f"unknown distribution {distribution!r} — use "
            f"{' or '.join(repr(d.value) for d in Distribution)}")

    tasks, links, calendars, issues = schedule_engine.build_network(activities)
    if not tasks:
        return _unavailable("no schedule activities could be read from the records")
    dd = schedule_engine.data_date_for(activities)

    estimates = default_estimates(
        tasks,
        optimistic_factor=DEFAULT_OPTIMISTIC_FACTOR,
        pessimistic_factor=ppc_tail_factor(ppc_pct),
    )

    try:
        result = simulate(
            tasks, links, calendars,
            estimates=estimates,
            iterations=max(100, min(int(iterations or 2000), 5000)),
            distribution=dist,
            seed=seed,
            data_date=dd,
        )
    except ScheduleCycleError as exc:
        # A loop has no finish to sample. Same refusal as every other adapter in this ring.
        return _unavailable(
            "the logic contains a loop, so there is no finish date to simulate",
            cycle=list(exc.cycle))

    # `most_critical` and `confidence_in_deterministic` are PROPERTIES; only `percentile` takes an
    # argument. Asked the class rather than read from the AST, which shows a decorated property as a
    # function and cost a TypeError here once already.
    top = result.most_critical[:5]
    return {
        "available": True,
        "iterations": result.iterations,
        "distribution": result.distribution.value,
        "seed": result.seed,
        "ppc_pct": ppc_pct,
        "pessimistic_factor": ppc_tail_factor(ppc_pct),
        "deterministic_finish": result.deterministic_finish.isoformat() if result.deterministic_finish else None,
        # The direct answer to "how likely is the date on the programme": the share of iterations that
        # finished on or before it. Ours could not report this at all.
        "confidence_in_deterministic": result.confidence_in_deterministic,
        "p10": _iso(result.percentile(10)),
        "p50": _iso(result.percentile(50)),
        "p80": _iso(result.percentile(80)),
        "p90": _iso(result.percentile(90)),
        # Criticality says how OFTEN an activity was on the path; sensitivity says whether its
        # duration actually MOVES the finish. Both, because either alone misleads.
        "most_critical": [a.to_dict() for a in top],
        "issues": [i.to_dict() for i in issues],
    }


def _iso(d: Any) -> str | None:
    return d.isoformat() if d is not None else None


def _unavailable(reason: str, **extra: Any) -> dict[str, Any]:
    """Nothing simulated. Percentiles are `None`, never a date — an invented P80 is the whole hazard."""
    return {
        "available": False,
        "reason": reason,
        "iterations": None,
        "distribution": None,
        "seed": None,
        "ppc_pct": None,
        "pessimistic_factor": None,
        "deterministic_finish": None,
        "confidence_in_deterministic": None,
        "p10": None, "p50": None, "p80": None, "p90": None,
        "most_critical": [],
        "issues": [],
        **extra,
    }

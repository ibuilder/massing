"""R35-DEAL-MEMORY — the operator's own closed projects as a comp set, and the comps it won't invent.

When somebody types an assumption into an underwriting, the most useful thing on the screen is what
this firm's *own* past projects actually did. That layer cannot be bought: it is made of the
operator's history, which is why it is the least commoditised part of the stack.

It is also the easiest place in the product to manufacture a flattering number, and the failure has
a specific shape:

**"Realised" must come from a different record than "assumed", or the comparison is circular.** The
roadmap asks for *exit cap achieved vs assumed* and *actual lease-up months*. Neither is recorded
anywhere in this system — there is no disposition record and no lease-up actual. The tempting move
is to read them off the latest scenario, but the latest scenario is an **assumption**. Comparing it
to the assumption being entered would report near-perfect underwriting accuracy forever, and that
number would then be used to justify the next deal. So those metrics are reported as
`no_recorded_source`, naming what would have to be captured, and are never computed.

What IS recorded, and is therefore reported:

* **cost variance** — `cost.summary` carries budget *and* actual, from commitments and invoices;
* **cost per SF** — the same actual over the model's own GFA;
* **schedule variance** — `schedule_activity` carries `finish` *and* `actual_finish`.

Each is a *measurement* sitting in a different record from the plan it is compared against. Two
further refusals, both shared with `deal_funnel`:

* **a sample floor.** Under `MIN_SAMPLES` closed projects a distribution is noise wearing a
  percentage sign, so no distribution is emitted — the count is, so the gap is visible;
* **a project with no actuals is not a project with zero variance.** It is excluded and counted;
  averaging it in as 0% would drag every distribution toward "we were exactly right".
"""
from __future__ import annotations

from datetime import date, datetime
from typing import Any

#: Closed projects a metric needs before its distribution is reported at all.
MIN_SAMPLES = 5

STATUS_OK = "ok"
STATUS_INSUFFICIENT = "insufficient_history"
STATUS_NO_SOURCE = "no_recorded_source"

#: Requested by R35-DEAL-MEMORY but with NO realised record anywhere in the system. Named rather
#: than silently omitted: a metric that is absent looks like a metric that was fine.
UNSOURCED: dict[str, str] = {
    "exit_cap_achieved": (
        "no disposition record exists — nothing captures the cap rate a sale actually achieved. "
        "The only exit cap in the system is the ASSUMED one on a scenario, so comparing it to the "
        "assumption being entered would compare a number to itself and report perfect accuracy "
        "forever. Needs a disposition record (sale date, price, trailing NOI) before it can be real."),
    "lease_up_months": (
        "no lease-up actual is recorded — there is no first-unit-leased or stabilisation date to "
        "measure from. The absorption figures in the system are forecasts, not observations."),
}


def _num(v: Any) -> float | None:
    if v is None or isinstance(v, bool) or v == "":
        return None
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    return None if f != f or f in (float("inf"), float("-inf")) else f


def _d(v: Any) -> date | None:
    if isinstance(v, datetime):
        return v.date()
    if isinstance(v, date):
        return v
    if not v:
        return None
    try:
        return date.fromisoformat(str(v)[:10])
    except ValueError:
        return None


def distribution(values: list[float], min_samples: int = MIN_SAMPLES) -> dict[str, Any]:
    """p25 / median / p75 over the observations, or a refusal naming how many more are needed."""
    n = len(values)
    if n < min_samples:
        return {"status": STATUS_INSUFFICIENT, "count": n, "needed": min_samples - n,
                "median": None, "p25": None, "p75": None,
                "note": (f"{n} closed project(s) carry this measurement; {min_samples - n} more "
                         "needed before a distribution means anything. No default is substituted.")}
    s = sorted(values)

    def q(p: float) -> float:
        if len(s) == 1:
            return s[0]
        i = p * (len(s) - 1)
        lo, hi = int(i), min(int(i) + 1, len(s) - 1)
        return s[lo] + (s[hi] - s[lo]) * (i - lo)

    return {"status": STATUS_OK, "count": n, "needed": 0,
            "median": round(q(0.5), 4), "p25": round(q(0.25), 4), "p75": round(q(0.75), 4),
            "min": round(s[0], 4), "max": round(s[-1], 4)}


def _schedule_variance_days(db, pid: str) -> float | None:
    """Days between the planned and actual finish of the project's LAST activity to finish.

    The project's finish is the latest finish among its activities, so the variance that matters is
    measured on the activity that actually ended last — not an average across activities, which
    would let an early trade's overrun cancel a late trade's recovery.
    """
    from . import modules as me
    try:
        rows = me.list_records(db, "schedule_activity", pid, limit=1_000_000)
    except Exception:                           # noqa: BLE001 — see below
        # `list_records` raises HTTPException(404) when the module is not registered (a trimmed
        # deployment, or a registry not yet loaded). A portfolio roll-up must not be able to die
        # because one module is absent: the honest answer for this project is "no measurement",
        # which is already how a project with no schedule is handled two lines down.
        return None
    planned_last = actual_last = None
    for r in rows:
        d = r.get("data") or {}
        p, a = _d(d.get("finish")), _d(d.get("actual_finish"))
        if p and (planned_last is None or p > planned_last):
            planned_last = p
        if a and (actual_last is None or a > actual_last):
            actual_last = a
    if planned_last is None or actual_last is None:
        return None
    return float((actual_last - planned_last).days)


def comps(db, project_ids: set[str] | None = None, min_samples: int = MIN_SAMPLES) -> dict[str, Any]:
    """Realised outcomes across the caller's own closed projects.

    `project_ids=None` means no restriction (RBAC off / admin); otherwise scoped exactly as
    `fca.portfolio` and `benchmarking` are, so one tenant's history never becomes another's comps.
    """
    from . import cost as cost_engine
    from . import energy
    from .models import Project

    q = db.query(Project)
    if project_ids is not None:
        q = q.filter(Project.id.in_(project_ids))

    cost_var: list[float] = []
    cost_sf: list[float] = []
    sched_var: list[float] = []
    rows: list[dict[str, Any]] = []
    excluded: list[dict[str, Any]] = []

    for p in q.all():
        try:
            cs = cost_engine.summary(db, p.id)
        except Exception:                       # noqa: BLE001 — a project with no cost data still lists
            cs = {}
        budget = _num(cs.get("budget"))
        actual = _num(cs.get("actual"))
        gfa = None
        try:
            gfa = _num(energy.project_gfa_sf(db, p.id))
        except Exception:                       # noqa: BLE001
            gfa = None
        sv = _schedule_variance_days(db, p.id)

        rec: dict[str, Any] = {"id": p.id, "name": p.name,
                               "vintage": p.created_at.year if p.created_at else None,
                               "budget": budget, "actual": actual, "gfa_sf": gfa,
                               "cost_variance_pct": None, "cost_per_sf": None,
                               "schedule_variance_days": sv}

        # A project with no ACTUAL spend has not been built yet. Counting it as 0% variance would
        # drag every distribution toward "we were exactly right" — the most flattering artefact
        # available and the one nobody would question.
        if budget and actual:
            rec["cost_variance_pct"] = round((actual - budget) / budget * 100.0, 2)
            cost_var.append(rec["cost_variance_pct"])
            if gfa:
                rec["cost_per_sf"] = round(actual / gfa, 2)
                cost_sf.append(rec["cost_per_sf"])
        else:
            excluded.append({"id": p.id, "name": p.name, "reason": "no_actual_cost",
                             "note": "no actual spend recorded; excluded rather than counted as "
                                     "zero variance"})
        if sv is not None:
            sched_var.append(sv)
        rows.append(rec)

    unsourced = {k: {"status": STATUS_NO_SOURCE, "note": v} for k, v in UNSOURCED.items()}
    return {
        "project_count": len(rows),
        "metrics": {
            "cost_variance_pct": distribution(cost_var, min_samples),
            "cost_per_sf": distribution(cost_sf, min_samples),
            "schedule_variance_days": distribution(sched_var, min_samples),
            **unsourced,
        },
        "projects": rows,
        "excluded": excluded,
        "excluded_count": len(excluded),
        "min_samples": min_samples,
        "note": ("every reported metric is a MEASUREMENT held in a different record from the plan it "
                 "is compared against. Metrics marked no_recorded_source are not computed at all — "
                 "deriving them from a scenario would compare an assumption to itself."),
    }


def beside(metric: str, value: Any, memory: dict[str, Any]) -> dict[str, Any]:
    """The firm's own realised distribution for `metric`, next to the value being entered.

    This is the shape the underwriting screen wants: not a verdict, a comparison. It reports where
    the entered value sits against the operator's own history and refuses to grade it when there is
    no history to grade against.
    """
    m = (memory.get("metrics") or {}).get(metric)
    if m is None:
        return {"metric": metric, "status": "unknown_metric", "entered": value,
                "known": sorted((memory.get("metrics") or {}).keys())}
    if m.get("status") != STATUS_OK:
        return {"metric": metric, "status": m.get("status"), "entered": value,
                "comparison": None, "note": m.get("note")}
    v = _num(value)
    if v is None:
        return {"metric": metric, "status": "not_a_number", "entered": value, "comparison": None}
    lo, hi, med = m["p25"], m["p75"], m["median"]
    where = "below_p25" if v < lo else "above_p75" if v > hi else "within_iqr"
    return {"metric": metric, "status": STATUS_OK, "entered": v, "median": med,
            "p25": lo, "p75": hi, "count": m["count"], "position": where,
            "note": (f"this firm's own {m['count']} closed project(s) landed between {lo} and {hi} "
                     f"(median {med}). This is a comparison, not a verdict — the history says where "
                     "the number sits, not whether it is right.")}

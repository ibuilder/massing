"""Compose the home Pulse inputs on the server.

The portal used to fan seven GETs and map foreign shapes in the browser. Those
mappings did not match the engines (`score` vs `overall_score`, `variance_pct`
vs `projected_over_under`, `float_days` absent from schedule variance), so the
rail fail-opened to empty on a healthy project. One GET returns `PulseInput`.

Each engine is asked independently. A missing schedule baseline, an unsolved
proforma, or a hygiene lens that needs an IFC is `null` for that card — never a
500 on the dashboard. Pulse invents no numbers.

Renovation is a POST that needs a programme body. This GET does not invent one;
`nothingRenovated` stays unset unless a caller later persists a programme.
"""
from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from sqlalchemy.orm import Session


def _n(v: Any) -> float | None:
    if isinstance(v, bool) or not isinstance(v, (int, float)):
        return None
    x = float(v)
    if x != x or abs(x) == float("inf"):
        return None
    return x


def _quiet(fn, *a, **kw):
    try:
        return fn(*a, **kw)
    except Exception:  # noqa: BLE001 — a pulse that cannot be built is simply absent
        return None


def from_model(health: dict[str, Any] | None) -> dict[str, Any] | None:
    if not health:
        return None
    score = _n(health.get("overall_score"))
    if score is None:
        return None
    issues = 0
    blocking: str | None = None
    for ln in health.get("lenses") or []:
        if not isinstance(ln, dict):
            continue
        if ln.get("key") == "hygiene":
            issues = int(ln.get("issues") or 0)
        if ln.get("status") == "poor" and blocking is None:
            h = ln.get("headline")
            blocking = h if isinstance(h, str) else None
    return {"score": score, "issues": issues, "blocking": blocking}


def from_cost(summary: dict[str, Any] | None) -> dict[str, Any] | None:
    if not summary:
        return None
    budget = _n(summary.get("budget"))
    ou = _n(summary.get("projected_over_under"))
    if budget is None or budget == 0 or ou is None:
        return None
    # Engine: projected_over_under = budget − forecast (positive = under).
    # Pulse: variancePct positive = over budget.
    return {"variancePct": round(-ou / budget * 100, 2)}


def from_schedule(payload: dict[str, Any] | None) -> dict[str, Any] | None:
    if not payload:
        return None
    sm = payload.get("summary") or {}
    avg = _n(sm.get("avg_finish_var"))
    if avg is None:
        return None
    at_risk = None
    for a in payload.get("activities") or []:
        if isinstance(a, dict) and a.get("status") == "slipped":
            at_risk = a.get("name") or a.get("ref")
            if isinstance(at_risk, str) and at_risk.strip():
                break
            at_risk = None
    # finish_var > 0 = later than baseline. Pulse floatDays > 0 = still has float.
    return {"floatDays": -avg, "atRisk": at_risk}


def from_work(queue: dict[str, Any] | None) -> dict[str, Any] | None:
    if not queue:
        return None
    total = queue.get("total")
    if not isinstance(total, int):
        return None
    overdue: list[str] = []
    for b in queue.get("buckets") or []:
        if not isinstance(b, dict) or b.get("key") != "overdue":
            continue
        for it in (b.get("items") or [])[:3]:
            if not isinstance(it, dict):
                continue
            ref = it.get("ref") or it.get("title")
            if isinstance(ref, str) and ref.strip():
                overdue.append(ref.strip())
    return {"open": total, "mine": total, "overdue": overdue or None}


def from_deal(
    irr_frac: float | None,
    reserve: dict[str, Any] | None,
) -> dict[str, Any] | None:
    """IRR is required for a deal card (same rule as the TS Pulse).

    `suggestion_clears_horizon is False` only — never truthiness. A missing
    field is "the engine did not answer", not "the suggestion fails".
    """
    irr_pct = None if irr_frac is None else round(float(irr_frac) * 100, 1)
    if irr_pct is None:
        return None
    fails = None
    if reserve is not None:
        clears = reserve.get("suggestion_clears_horizon")
        if clears is False:
            fails = True
        elif clears is True:
            fails = False
    return {"irrPct": irr_pct, "reserveSuggestionFails": fails, "nothingRenovated": None}


def compose(db: Session, pid: str, user: str) -> dict[str, Any]:
    """Fail-open PulseInput. Unknown project is the caller's 404, not this."""
    from . import cost as cost_mod
    from . import model_health, rbac
    from . import reserve as reserve_mod
    from . import work_queue as wq
    from .deps import open_source_ifc
    from .routers import _vitals_sources
    from .routers.schedule import variance as schedule_variance

    model = _quiet(open_source_ifc, db, pid)
    health = _quiet(model_health.scorecard, db, pid, model=model)
    cost = _quiet(cost_mod.summary, db, pid)
    sched = _quiet(schedule_variance, pid, db, "viewer")
    party = _quiet(rbac.party_role_for, db, pid, user)
    work = _quiet(wq.queue, db, pid, user, party)
    irr = _vitals_sources._irr(db, pid)
    res = _quiet(reserve_mod.study, db, pid)

    return {
        "model": from_model(health if isinstance(health, dict) else None),
        "cost": from_cost(cost if isinstance(cost, dict) else None),
        "schedule": from_schedule(sched if isinstance(sched, dict) else None),
        "work": from_work(work if isinstance(work, dict) else None),
        "deal": from_deal(irr, res if isinstance(res, dict) else None),
    }

"""R46 ⑥ — several projects, the links between them, and one pass over one network.

A construction programme above a certain size is not one schedule. It is enabling works, the main
contract, fit-out and a separate infrastructure package, with real logic crossing between them — and
until now every one of those was scheduled here in isolation, so a slip in enabling works reached the
fit-out programme only when somebody noticed and re-typed a date.

**One pass over one merged network, not a loop over projects.** Scheduling them in sequence would
propagate a delay only in whichever order somebody happened to list them: enabling → fit-out picks up
the slip, fit-out → enabling does not, and neither order is more correct than the other. Merging
first is the only way the direction of the arrow decides it rather than the order of the list.

## An external link is a different kind of thing, and is kept different

The engine types a cross-project relationship separately from an internal one, and that is not
tidiness. An internal link is a sequencing decision one team made and can change; an **external link
is a commitment between two parties**. A report that cannot tell them apart cannot say which delays
crossed a boundary — which is the only question a programme director is actually asking.

## Standalone float is kept, deliberately

`PortfolioResult` retains each project's own schedule as well as its place in the merged one. A
project can look comfortable alone and be critical to the programme, and showing only the merged
float would hide the first while showing only the standalone float would hide the second. Both are
returned.

## Authorisation

Membership is checked **per project** by the route, not once for the caller. A portfolio view that
required access to one project and returned dates from four would be a cross-tenant read wearing a
feature's name.
"""
from __future__ import annotations

from typing import Any

from massingplan.core.graph import ScheduleCycleError
from massingplan.core.network import RelationType
from massingplan.core.portfolio import (
    ExternalLink,
    PortfolioError,
    Project,
)
from massingplan.core.portfolio import (
    schedule_portfolio as _schedule,
)

from . import schedule_engine

_REL = {"FS": RelationType.FS, "SS": RelationType.SS,
        "FF": RelationType.FF, "SF": RelationType.SF}


def _links(raw: list[dict], known: set[str]) -> tuple[list[ExternalLink], list[str]]:
    """Cross-project links, with the ones that name an unknown project reported."""
    out, bad = [], []
    for i, ln in enumerate(raw or []):
        pp = str(ln.get("predecessor_project") or "").strip()
        sp = str(ln.get("successor_project") or "").strip()
        pid_ = str(ln.get("predecessor_id") or "").strip()
        sid = str(ln.get("successor_id") or "").strip()
        if not (pp and sp and pid_ and sid):
            bad.append(f"link {i + 1}: needs both ends, each a project and an activity")
            continue
        if pp not in known or sp not in known:
            # Named rather than dropped: a missing external link is a commitment quietly deleted,
            # and the programme reads better than it is.
            bad.append(f"link {i + 1}: {pp} -> {sp} names a project not in this portfolio")
            continue
        out.append(ExternalLink(
            predecessor_project=pp, predecessor_id=pid_,
            successor_project=sp, successor_id=sid,
            type=_REL.get(str(ln.get("type") or "FS").upper(), RelationType.FS),
            lag_days=int(float(ln.get("lag_days") or 0))))
    return out, bad


def portfolio(projects: list[dict], external: list[dict] | None = None) -> dict[str, Any]:
    """Schedule several projects together. `projects` is `[{id, name, activities: [...]}]`."""
    if not projects:
        return _unavailable("no projects — a portfolio needs at least one")
    if len(projects) < 2:
        # One project is a schedule, and `/schedule/cpm` already answers it. Reported rather than
        # computed, because a "portfolio" of one renders as a programme view of nothing.
        return _unavailable(
            "only one project — a portfolio is about the links BETWEEN schedules, and one schedule "
            "is already answered by the CPM view")

    built: list[Project] = []
    empty: list[str] = []
    seen: set[str] = set()
    for p in projects:
        pid = str(p.get("id") or "").strip()
        if not pid or pid in seen:
            continue
        seen.add(pid)
        acts = p.get("activities") or []
        if not acts:
            empty.append(pid)
            continue
        tasks, links, _cals, _ = schedule_engine.build_network(acts)
        built.append(Project(id=pid, tasks=tasks, links=links,
                             name=str(p.get("name") or pid)))

    if len(built) < 2:
        return _unavailable(
            "fewer than two projects have any activities, so there is nothing to link",
            projects_without_activities=empty)

    ext, bad = _links(external or [], {p.id for p in built})
    try:
        result = _schedule(built, ext)
    except ScheduleCycleError:
        return _unavailable(
            "the merged network contains a loop. A cycle can exist ACROSS projects even when every "
            "project is clean on its own — which is one of the things scheduling them together "
            "finds", rejected_links=bad, projects_without_activities=empty)
    except PortfolioError:
        # Composed here, never relayed — the v0.3.962 rule.
        return _unavailable("the portfolio inputs were refused; check that every project has a "
                            "distinct id", rejected_links=bad, projects_without_activities=empty)

    return {
        "available": True,
        "projects": [{"id": p.id, "name": p.name, "activities": len(p.tasks)} for p in built],
        "external_links": [ln.to_dict() for ln in ext],
        "rejected_links": bad,
        "projects_without_activities": empty,
        **result.summary(),
    }


def _unavailable(reason: str, **extra: Any) -> dict[str, Any]:
    """Counts `None`, never 0 — 'nothing crosses a boundary' and 'not scheduled' differ."""
    out: dict[str, Any] = {
        "available": False, "reason": reason, "projects": [], "external_links": [],
        "rejected_links": [], "projects_without_activities": [],
        "programme_finish": None, "project_count": None, "external_link_count": None,
    }
    out.update({k: v for k, v in extra.items() if v is not None})
    return out

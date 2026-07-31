"""R21-4D-CLASH (phase 1) — space contention: two trades in one place at one time.

Hard clash finds two things in one space. Soft clash asks whether a person can reach them. This asks
the third question, and it is the one a superintendent actually loses sleep over: **are two crews
scheduled into the same place in the same week?**

Nothing in the model is wrong when this happens. Every element clears every other element. The clash
is entirely in the *schedule*, which is why a geometric clash run cannot find it and why it surfaces
on site as two foremen arguing in a corridor.

**Scope, stated honestly.** The roadmap describes 4D clash as two things: space contention, and an
install sequenced before the support it hangs from. Only the first is built here, because only the
first is answerable from the data that exists — `schedule_activity` carries `location`, `trade`,
`start` and `finish`, but **no element GlobalId**. Without a task→element binding there is no way to
know what a task installs, so "installed before its support" cannot be computed without inventing the
link. That half is named as unbuilt rather than approximated.
"""
from __future__ import annotations

from datetime import date, datetime
from typing import Any

MAX_ACTIVITIES = 20_000          # bound the pairwise sweep on a mega-schedule

# How much simultaneous presence is a problem depends on the work, so the caller sets it; this is the
# default. Trades genuinely do share space — the question is whether they can share THIS space.
DEFAULT_MIN_OVERLAP_DAYS = 1


def _as_date(v: Any) -> date | None:
    if isinstance(v, datetime):
        return v.date()
    if isinstance(v, date):
        return v
    s = str(v or "").strip()[:10]
    if not s:
        return None
    try:
        return date.fromisoformat(s)
    except ValueError:
        return None


def _overlap_days(a_start, a_end, b_start, b_end) -> int:
    lo, hi = max(a_start, b_start), min(a_end, b_end)
    return (hi - lo).days + 1 if hi >= lo else 0


def _norm(v: Any) -> str:
    return " ".join(str(v or "").split()).strip().lower()


def analyze(activities: list[dict], min_overlap_days: int = DEFAULT_MIN_OVERLAP_DAYS,
            crew_threshold: int = 0) -> dict[str, Any]:
    """Find pairs of activities that share a location, overlap in time, and belong to DIFFERENT trades.

    Same-trade overlap is deliberately not a finding: one trade sequencing its own crews through a
    zone is planning, not contention. The finding is a *different* trade arriving in the same place.

    An activity missing a location or either date is **skipped and counted**, never silently dropped —
    an unschedulable activity is a data gap the planner needs to see, and reporting a clean result
    over a schedule that was half unreadable would be the same overstatement the clash matrix exists
    to prevent.
    """
    acts = list(activities or [])[:MAX_ACTIVITIES]
    usable, skipped = [], []
    for a in acts:
        data = a.get("data") if isinstance(a.get("data"), dict) else a
        loc = _norm(data.get("location"))
        s, f = _as_date(data.get("start")), _as_date(data.get("finish"))
        rec = {"id": a.get("id") or data.get("id"), "name": data.get("name") or "",
               "location": str(data.get("location") or "").strip(),
               "trade": str(data.get("trade") or "").strip(),
               "start": s, "finish": f,
               "crew": int(data.get("crew_size") or 0) if str(data.get("crew_size") or "").strip().isdigit() else 0}
        why = None
        if not loc:
            why = "no location"
        elif not s or not f:
            why = "missing start or finish"
        elif f < s:
            why = "finish before start"
        if why:
            skipped.append({"id": rec["id"], "name": rec["name"], "reason": why})
        else:
            rec["_loc"] = loc
            usable.append(rec)

    by_loc: dict[str, list[dict]] = {}
    for r in usable:
        by_loc.setdefault(r["_loc"], []).append(r)

    findings = []
    for loc, group in sorted(by_loc.items()):
        group.sort(key=lambda r: (r["start"], r["finish"]))
        for i, a in enumerate(group):
            for b in group[i + 1:]:
                if b["start"] > a["finish"]:
                    break                        # sorted by start — nothing later can overlap either
                if _norm(a["trade"]) == _norm(b["trade"]):
                    continue                     # one trade sequencing itself is planning
                days = _overlap_days(a["start"], a["finish"], b["start"], b["finish"])
                if days < max(1, min_overlap_days):
                    continue
                crew = a["crew"] + b["crew"]
                if crew_threshold and crew < crew_threshold:
                    continue
                findings.append({
                    "location": a["location"] or loc,
                    "a": {"id": a["id"], "name": a["name"], "trade": a["trade"]},
                    "b": {"id": b["id"], "name": b["name"], "trade": b["trade"]},
                    "overlap_days": days,
                    "combined_crew": crew,
                    "window": {"start": max(a["start"], b["start"]).isoformat(),
                               "finish": min(a["finish"], b["finish"]).isoformat()},
                })
    # worst first: the longest shared window with the most people in it
    findings.sort(key=lambda f: (-f["overlap_days"], -f["combined_crew"], f["location"]))

    return {
        "analyzed": len(usable),
        "skipped": skipped,
        "skipped_count": len(skipped),
        "locations": len(by_loc),
        "findings": findings,
        "finding_count": len(findings),
        # The claim is bounded by what was readable — see `skipped`. `usable` is required, so an empty
        # or entirely unreadable schedule reports NOT clean rather than vacuously perfect; same rule
        # the clash matrix follows, where a matrix that tested nothing is not "coordinated".
        "clean": bool(usable) and not findings and not skipped,
        "note": ("Same-trade overlap is not a finding — one trade sequencing its own crews through a "
                 "zone is planning. Activities without a location or dates are skipped and counted, "
                 "never silently dropped: a clean result over a half-unreadable schedule would "
                 "overstate what was checked."),
        # CORRECTED 2026-07-31. This previously read "schedule_activity carries no element GlobalId, so
        # there is no way to know what a task installs" — and that was **false**. `element_guids` is a
        # column on EVERY module record (`models.py:312`, written by `modules.set_element_guids`), and
        # `me.list_records` returns it, so each activity reaching `analyze()` already carries its
        # binding when a project has populated one. A stated blocker that is not real is worse than a
        # true one: it stops work that could have proceeded, and nobody re-checks a documented dead end.
        "not_covered": ("Install-before-support sequencing is NOT checked, and the reason is narrower "
                        "than it looks: the task→element binding EXISTS (`element_guids` on every "
                        "activity record). What is missing is the SUPPORT relationship — knowing that "
                        "element B holds up element A. Nothing here reads IfcRelConnectsElements or a "
                        "structural graph, and inferring support from bounding boxes would invent a "
                        "load path. That inference, not the binding, is the open work."),
        # Reported so the gap is measurable rather than asserted: how many activities could be checked
        # today if the support relationship existed. Zero here means the binding is unpopulated on this
        # project, which is a different problem from the engine being unable to use it.
        "bound_activities": sum(1 for a in (activities or []) if (a or {}).get("element_guids")),
    }

"""R21-4D-CLASH — space contention, and install-before-support.

Hard clash finds two things in one space. Soft clash asks whether a person can reach them. This asks
the third question, and it is the one a superintendent actually loses sleep over: **are two crews
scheduled into the same place in the same week?** And the fourth: **is an element scheduled to go
in before the thing the model says holds it up?**

Nothing in the model is wrong when space contention happens. Every element clears every other
element. The clash is entirely in the *schedule*, which is why a geometric clash run cannot find it
and why it surfaces on site as two foremen arguing in a corridor.

Install-before-support is the other half. Task→element binding is `element_guids` on every activity
record. Directed pairs come from `aec_data.support_graph.directed_install_pairs`: structural
relations that license a direction, and RelAggregates parent-before-part. Geometry is never used to
invent a load path, and unstated IfcRelConnectsElements joins are not treated as support.
"""
from __future__ import annotations

from datetime import date, datetime
from typing import Any

MAX_ACTIVITIES = 20_000          # bound the pairwise sweep on a mega-schedule

# How much simultaneous presence is a problem depends on the work, so the caller sets it; this is the
# default. Trades genuinely do share space — the question is whether they can share THIS space.
DEFAULT_MIN_OVERLAP_DAYS = 1

_NOT_FED = ("Install-before-support sequencing is NOT checked on this call: the task→element binding "
            "EXISTS (`element_guids` on every activity record), but no directed SUPPORT relationship "
            "was supplied. Pass `support_pairs` from `support_graph.directed_install_pairs` — that "
            "reads what the IFC states (structural direction, RelAggregates parent-before-part) and "
            "refuses to invent a load path from bounding boxes.")

_NOT_UNSTATED = ("Install-before-support IS checked against directed pairs the IFC licenses "
                 "(IfcRelConnectsStructuralMember, IfcRelAggregates parent-before-part). Unstated "
                 "IfcRelConnectsElements joins are NOT treated as support: Relating/Related is "
                 "authoring order, not a load path, and inferring support from geometry would invent "
                 "one. The binding EXISTS (`element_guids`); a pair whose element has no dated "
                 "activity is counted in `support_unscheduled`, not silently treated as clean.")


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


def _guids_of(a: dict) -> list[str]:
    data = a.get("data") if isinstance(a.get("data"), dict) else {}
    raw = a.get("element_guids")
    if raw is None:
        raw = data.get("element_guids")
    if not raw:
        return []
    if isinstance(raw, str):
        return [raw] if raw else []
    return [str(g) for g in raw if g]


def _norm_pairs(raw: list | None) -> list[tuple[str, str, str]]:
    out: list[tuple[str, str, str]] = []
    seen: set[tuple[str, str, str]] = set()
    for p in raw or []:
        if isinstance(p, dict):
            sup = p.get("support") or p.get("a")
            ted = p.get("supported") or p.get("b")
            grade = str(p.get("grade") or "structural")
        elif isinstance(p, (list, tuple)) and len(p) >= 2:
            sup, ted = p[0], p[1]
            grade = str(p[2] if len(p) > 2 else "structural")
        else:
            continue
        if not sup or not ted or str(sup) == str(ted):
            continue
        key = (str(sup), str(ted), grade)
        if key in seen:
            continue
        seen.add(key)
        out.append(key)
    return out


def _install_spans(activities: list[dict]) -> dict[str, dict[str, Any]]:
    """Per GlobalId, the earliest start and latest finish among dated activities that bind it."""
    spans: dict[str, dict[str, Any]] = {}
    for a in activities or []:
        data = a.get("data") if isinstance(a.get("data"), dict) else a
        s, f = _as_date(data.get("start")), _as_date(data.get("finish"))
        if not s or not f or f < s:
            continue
        rec = {"id": a.get("id") or data.get("id"), "name": data.get("name") or "",
               "trade": str(data.get("trade") or "").strip(), "start": s, "finish": f}
        for g in _guids_of(a):
            prev = spans.get(g)
            if prev is None:
                spans[g] = {**rec, "start": s, "finish": f}
            else:
                if s < prev["start"]:
                    prev["start"] = s
                    prev["id"] = rec["id"]
                    prev["name"] = rec["name"]
                    prev["trade"] = rec["trade"]
                if f > prev["finish"]:
                    prev["finish"] = f
    return spans


def analyze(activities: list[dict], min_overlap_days: int = DEFAULT_MIN_OVERLAP_DAYS,
            crew_threshold: int = 0, support_pairs: list | None = None) -> dict[str, Any]:
    """Find pairs of activities that share a location, overlap in time, and belong to DIFFERENT trades.

    Same-trade overlap is deliberately not a finding: one trade sequencing its own crews through a
    zone is planning, not contention. The finding is a *different* trade arriving in the same place.

    An activity missing a location or either date is **skipped and counted**, never silently dropped —
    an unschedulable activity is a data gap the planner needs to see, and reporting a clean result
    over a schedule that was half unreadable would be the same overstatement the clash matrix exists
    to prevent.

    When `support_pairs` is supplied (including an empty list), install-before-support is checked:
    the supported element's earliest start must not precede the supporting element's latest finish.
    `None` (the default) leaves that half unrun, so a space-contention unit test does not claim a
    support graph it never built.
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

    support_checked = support_pairs is not None
    support_findings: list[dict] = []
    support_unscheduled: list[dict] = []
    pairs = _norm_pairs(support_pairs) if support_checked else []
    if support_checked:
        spans = _install_spans(acts)
        for sup, ted, grade in pairs:
            sa, ta = spans.get(sup), spans.get(ted)
            if sa is None or ta is None:
                missing = []
                if sa is None:
                    missing.append("support")
                if ta is None:
                    missing.append("supported")
                support_unscheduled.append({
                    "support": sup, "supported": ted, "grade": grade,
                    "missing": missing,
                })
                continue
            # Supported starts while the support is still being installed (or before it starts).
            # Same-day handoff (supported.start == support.finish) is sequencing, not a finding.
            if ta["start"] < sa["finish"]:
                support_findings.append({
                    "kind": "install_before_support",
                    "grade": grade,
                    "support": {"guid": sup, "id": sa["id"], "name": sa["name"],
                                "trade": sa["trade"],
                                "start": sa["start"].isoformat(),
                                "finish": sa["finish"].isoformat()},
                    "supported": {"guid": ted, "id": ta["id"], "name": ta["name"],
                                  "trade": ta["trade"],
                                  "start": ta["start"].isoformat(),
                                  "finish": ta["finish"].isoformat()},
                })
        support_findings.sort(key=lambda f: (f["supported"]["start"], f["grade"]))

    return {
        "analyzed": len(usable),
        "skipped": skipped,
        "skipped_count": len(skipped),
        "locations": len(by_loc),
        "findings": findings,
        "finding_count": len(findings),
        "support_checked": support_checked,
        "support_pairs": len(pairs),
        "support_findings": support_findings,
        "support_finding_count": len(support_findings),
        "support_unscheduled": support_unscheduled,
        "support_unscheduled_count": len(support_unscheduled),
        # The claim is bounded by what was readable — see `skipped`. `usable` is required, so an empty
        # or entirely unreadable schedule reports NOT clean rather than vacuously perfect; same rule
        # the clash matrix follows, where a matrix that tested nothing is not "coordinated".
        "clean": bool(usable) and not findings and not skipped and not support_findings,
        "note": ("Same-trade overlap is not a finding — one trade sequencing its own crews through a "
                 "zone is planning. Activities without a location or dates are skipped and counted, "
                 "never silently dropped: a clean result over a half-unreadable schedule would "
                 "overstate what was checked."),
        "not_covered": _NOT_UNSTATED if support_checked else _NOT_FED,
        # Reported so the gap is measurable rather than asserted: how many activities could be checked
        # today if the support relationship existed. Zero here means the binding is unpopulated on this
        # project, which is a different problem from the engine being unable to use it.
        "bound_activities": sum(1 for a in (activities or []) if _guids_of(a)),
    }

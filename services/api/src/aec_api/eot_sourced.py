"""R40-EOT ② — the entitlement built from the project's OWN record, not from typed numbers.

`eot.analyse` is good and its refusals are the reason: the method is required and closed, concurrency
is named rather than apportioned, and float that absorbs a delay is reported as *absorbed* rather than
as zero delay. What it does not have is provenance for its inputs. `POST /schedule/eot` takes
`baseline_finish`, `actual_finish` and the whole `events` list **from the request body**, while
`schedule_baselines` (named, captured baselines with per-activity variance) and `notice_clock`
(typed weather / constructive-change / suspension events, each carrying the record it came from) sit
right there, wired to nothing.

**That is the wrong place to leave provenance on this particular number.** The baseline is the single
most contested input in a delay claim, and as a free-text parameter it is unauditable: two people can
produce different EOTs from the same project by typing different dates, and every careful refusal in
`eot.analyse` sits downstream of an input nobody can check. This number ends up in arbitration.

WHAT THE TWO SOURCES ACTUALLY GIVE, which decides the whole design
-----------------------------------------------------------------
* `schedule_baselines.variance()` gives **quantum**: `finish_var` per activity against a *named*
  baseline, so the slip is measured, attributable to a captured artefact, and re-derivable.
* `notice_clock.detect()` gives **cause**: `{type, date, description, source, source_id}` per event —
  and, crucially, **no `days` field at all**. Detection says an event happened. It never says what the
  event cost.

So the two are joined rather than substituted, and the gap between them is reported rather than
filled:

1.  **A detected event is not a quantified delay.** `eot.analyse` needs `days` per event; detection
    does not supply it. Inventing one — splitting the slip evenly, or attributing all of it to the
    nearest event — would be arithmetic presented as a finding, on the exact number a claim turns on.
    Events without a stated duration are returned as `needs_duration`, listed, and excluded from the
    figure.
2.  **Slip with no matching cause is `unattributed`, never `non_excusable`.** This is the one that
    matters most. Unattributed slip looks like contractor risk and defaulting it that way would hand
    one party an entitlement finding nobody demonstrated. It is reported as its own bucket, with its
    days, so a reader sees exactly how much of the overrun has no established cause.

This module composes; it does not re-derive. Every number comes from the engine that owns it, so it
cannot disagree with `/schedule/variance` or `/notice-clock` read beside it.
"""
from __future__ import annotations

from typing import Any

#: Why an activity's slip could not be attributed. Named rather than boolean so the report can say
#: which kind of ignorance it is — those send a reader to different places.
UNATTRIBUTED = "unattributed"
NEEDS_DURATION = "needs_duration"
ATTRIBUTED = "attributed"

STATUS_NO_BASELINE = "baseline_required"


def _num(v: Any) -> float | None:
    if v is None or isinstance(v, bool) or v == "":
        return None
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    return None if f != f else f


def _slipped(variance: dict | None) -> list[dict[str, Any]]:
    """Activities that finished later than the named baseline, with their measured slip."""
    rows = ((variance or {}).get("activities") or [])
    out = []
    for a in rows:
        if not isinstance(a, dict):
            continue
        fv = _num(a.get("finish_var"))
        if fv is not None and fv > 0:
            # `compute_variance` emits {ref, name, start_var, finish_var, status} — there is no
            # `id`, and `on_baseline` is a STATUS value, not a boolean field. Read, not assumed.
            out.append({"activity_id": a.get("ref"), "name": a.get("name"),
                        "ref": a.get("ref"), "slip_days": fv, "status_vs_baseline": a.get("status")})
    out.sort(key=lambda r: -r["slip_days"])
    return out


def attribute(slipped: list[dict], events: list[dict] | None) -> dict[str, Any]:
    """Match measured slip to detected causes. Reports what it could not match, rather than guessing.

    Matching is by explicit `activity_id` on the event only. Proximity matching — "this event is near
    that activity in time, so it probably caused it" — is deliberately not done: it manufactures a
    causal claim out of a coincidence, and causation is the contested half of every delay claim.
    """
    by_act: dict[str, list[dict]] = {}
    unlinked: list[dict] = []
    for e in events or []:
        if not isinstance(e, dict):
            continue
        aid = e.get("activity_id")
        if aid:
            by_act.setdefault(str(aid), []).append(e)
        else:
            unlinked.append(e)

    rows, needs_duration = [], []
    for s in slipped:
        evs = by_act.get(str(s["activity_id"]), [])
        quantified = [e for e in evs if _num(e.get("days")) is not None]
        unquantified = [e for e in evs if _num(e.get("days")) is None]
        needs_duration.extend({**e, "activity_id": s["activity_id"]} for e in unquantified)
        rows.append({
            **s,
            "status": ATTRIBUTED if quantified else (NEEDS_DURATION if evs else UNATTRIBUTED),
            "events": [{"type": e.get("type") or e.get("kind"), "days": _num(e.get("days")),
                        "source": e.get("source"), "source_id": e.get("source_id"),
                        "entitlement": e.get("entitlement")} for e in evs],
            "claimed_days": sum(_num(e.get("days")) or 0.0 for e in quantified) or None,
        })

    unattributed = [r for r in rows if r["status"] == UNATTRIBUTED]
    return {
        "activities": rows,
        "attributed_days": round(sum(r["claimed_days"] or 0.0 for r in rows), 1),
        "unattributed_days": round(sum(r["slip_days"] for r in unattributed), 1),
        "unattributed": [{"activity_id": r["activity_id"], "name": r["name"],
                          "slip_days": r["slip_days"]} for r in unattributed],
        "needs_duration": needs_duration,
        "events_without_activity": len(unlinked),
        "note": ("slip is measured against a NAMED baseline; cause comes from detected events matched "
                 "by explicit activity only. Slip with no matching event is `unattributed` — it is "
                 "NOT non-excusable, because defaulting unexplained slip to contractor risk hands one "
                 "party a finding nobody demonstrated. An event with no stated duration is "
                 "`needs_duration` and is excluded from the figure rather than being assigned days."),
    }


def for_project(db, project_id: str, method: str | None = None,
                baseline_id: str | None = None, events: list[dict] | None = None,
                baseline_finish: Any = None, actual_finish: Any = None) -> dict[str, Any]:
    """An EOT sourced from the project's named baseline and its own detected events."""
    from . import eot, notice_clock, schedule_baselines
    from . import modules as me

    var = schedule_baselines.variance(db, project_id, baseline_id)
    if not var:
        metas = schedule_baselines.list_metas(project_id)
        return {"status": STATUS_NO_BASELINE, "baseline": None, "baselines_available": metas,
                "note": ("no baseline is captured for this project, so there is nothing to measure "
                         "slip against. An EOT computed from a typed finish date is not auditable, "
                         "which is the whole reason this path exists — capture a baseline first.")}

    def load(key):
        return me.list_records(db, key, project_id, limit=100000) if key in me.TABLES else []

    detected = notice_clock.detect(daily_reports=load("daily_report"),
                                   change_events=load("change_event"))
    found = detected.get("events", detected) if isinstance(detected, dict) else (detected or [])
    supplied = list(events or [])
    attribution = attribute(_slipped(var), supplied + list(found))

    # Only durations somebody stated reach the entitlement engine.
    quantified = [e for e in supplied + list(found) if _num(e.get("days")) is not None]
    # `variance()` reports per-activity slip and counts; it carries NO project baseline/actual finish
    # date, so those are passed through from the caller when given and otherwise left absent. Deriving
    # a project completion date here by taking max(activity finish) would be this module inventing the
    # very input it exists to make auditable.
    analysis = eot.analyse(quantified, None, method=method,
                           baseline_finish=baseline_finish, actual_finish=actual_finish)
    return {
        "project_id": project_id,
        "baseline": {k: (var.get("baseline") or {}).get(k)
                     for k in ("id", "name", "captured_at", "count")},
        "slip_summary": var.get("summary"),
        "attribution": attribution,
        "analysis": analysis,
        "events_detected": len(found),
        "events_supplied": len(supplied),
        "events_quantified": len(quantified),
        "note": ("baseline and events come from the project's own record, so the two most contested "
                 "inputs to this number are auditable rather than typed. Detection establishes that "
                 "an event occurred; it does not establish what the event cost, and this does not "
                 "invent that."),
    }
